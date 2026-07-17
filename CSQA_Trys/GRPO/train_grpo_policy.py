# -*- coding: utf-8 -*-
"""Offline GRPO policy over the injection action space (pure numpy, NO LLM calls).

Setup
-----
For every question q we have a deterministic, fully-cached reward for each of the
three injection arms a in {none, facts, bestguess} (see build_reward_cache.py):

    R(q, a) = acc_reward(q, a) - lambda_cost * norm_cost(q, a)

The policy pi_theta(a | s_q) is a softmax-linear model over offline state features
s_q (validator status/reason + retrieval scores). We never need a value network:
GRPO uses the GROUP-RELATIVE advantage, where the "group" is exactly the set of
candidate actions for one prompt:

    A(q, a) = R(q, a) - mean_{a'} R(q, a')          (group baseline = group mean)
    A(q, a) = A(q, a) / (std_{a'} R(q, a') + eps)   (group std normalisation)

Because the environment is deterministic and every arm's reward is cached, we can
take the *exact* expected GRPO surrogate over the action group instead of a single
sampled action (lower variance, identical in expectation):

    J(theta) = E_q [ sum_a pi_theta(a|s_q) * A(q,a) ]
               - beta_kl * E_q [ KL( pi_theta(.|s_q) || pi_ref(.|s_q) ) ]
               + ent_coef * E_q [ H(pi_theta(.|s_q)) ]

pi_ref is the fixed-rule reference policy (always 'bestguess'), matching GRPO's
KL-to-reference regulariser. We optimise by gradient ascent.

Evaluation uses K-fold cross-validation (N is small) and reports the learned
policy (argmax action) against the three fixed-arm rules and the per-question
ORACLE, on both accuracy and average injection cost.

    cd CSQA_Trys && python GRPO/train_grpo_policy.py
    cd CSQA_Trys && python GRPO/train_grpo_policy.py --lambda_cost 0.3 --folds 5
"""

from __future__ import annotations

import argparse
import json
import os
from typing import Any, Dict, List, Tuple

import numpy as np

CACHE_PATH = os.path.join(os.path.dirname(__file__), "cache", "reward_table.jsonl")
ARMS = ["none", "facts", "bestguess"]
REF_ARM = "bestguess"  # fixed-rule reference policy for the KL term
REASONS = [
    "__accepted__",  # status==accepted (reason is None)
    "conflicting_supported_options",
    "no_direct_knowledge",
    "no_uniquely_discriminative_knowledge",
    "insufficient_margin",
    "__other__",
]


def load_rows() -> List[Dict[str, Any]]:
    return [json.loads(l) for l in open(CACHE_PATH, encoding="utf-8") if l.strip()]


def featurize(rows: List[Dict[str, Any]]) -> np.ndarray:
    """State features the policy conditions on (all available offline pre-injection)."""
    feats = []
    for row in rows:
        f = row["features"]
        reason = f.get("reason")
        if f.get("status") == "accepted":
            reason_key = "__accepted__"
        elif reason in REASONS:
            reason_key = reason
        else:
            reason_key = "__other__"
        reason_oh = [1.0 if reason_key == r else 0.0 for r in REASONS]
        numeric = [
            1.0 if f.get("status") == "accepted" else 0.0,
            f.get("n_candidates", 0) / 10.0,
            f.get("n_fact_evals", 0) / 10.0,
            f.get("max_top1", 0.0),
            f.get("mean_top1", 0.0),
            f.get("max_margin", 0.0),
            f.get("n_distinct_supported_options", 0) / 5.0,
            f.get("n_conflicting_options", 0) / 5.0,
            f.get("n_supporting_facts", 0) / 5.0,
            f.get("stem_len", 0) / 30.0,
            # agreement signal (path B): does DoT's own no-inject answer disagree with
            # the retrieved best-guess option? injection benefit concentrates here.
            f.get("ni_bg_known", 0.0),
            f.get("ni_bg_disagree", 0.0),
        ]
        feats.append([1.0] + numeric + reason_oh)  # leading 1.0 = bias
    return np.asarray(feats, dtype=np.float64)


def build_rewards(rows: List[Dict[str, Any]], lambda_cost: float) -> Tuple[np.ndarray, np.ndarray, np.ndarray]:
    """Return acc[N,3], cost[N,3] (normalised to [0,1]), and shaped reward[N,3]."""
    acc = np.array([[row["arms"][a]["reward"] for a in ARMS] for row in rows], dtype=np.float64)
    raw_cost = np.array([[row["arms"][a]["cost"] for a in ARMS] for row in rows], dtype=np.float64)
    cmax = raw_cost.max() if raw_cost.max() > 0 else 1.0
    cost = raw_cost / cmax
    reward = acc - lambda_cost * cost
    return acc, cost, reward


def group_advantage(reward: np.ndarray) -> np.ndarray:
    """GRPO group-relative advantage: subtract group mean, divide by group std."""
    mean = reward.mean(axis=1, keepdims=True)
    std = reward.std(axis=1, keepdims=True)
    return (reward - mean) / (std + 1e-6)


def softmax(z: np.ndarray) -> np.ndarray:
    z = z - z.max(axis=1, keepdims=True)
    e = np.exp(z)
    return e / e.sum(axis=1, keepdims=True)


def train_policy(X: np.ndarray, adv: np.ndarray, *, ref_idx: int,
                 lr: float, epochs: int, beta_kl: float, ent_coef: float,
                 l2: float, seed: int = 0) -> np.ndarray:
    """Gradient ascent on the exact expected GRPO surrogate. W: [d, 3]."""
    rng = np.random.default_rng(seed)
    d = X.shape[1]
    n_actions = adv.shape[1]  # infer action count from the reward group (path A=3, path B=5)
    W = rng.normal(scale=0.01, size=(d, n_actions))
    # reference policy: deterministic 'always REF_ARM' smoothed to a valid distribution
    pi_ref = np.full((X.shape[0], n_actions), (1.0 - 0.9) / (n_actions - 1))
    pi_ref[:, ref_idx] = 0.9

    N = X.shape[0]
    for _ in range(epochs):
        logits = X @ W
        pi = softmax(logits)
        # dJ/dlogits for J = sum_a pi_a * A_a  ->  pi_a * (A_a - sum_b pi_b A_b)
        baseline = (pi * adv).sum(axis=1, keepdims=True)
        g_obj = pi * (adv - baseline)
        # entropy bonus gradient: H = -sum pi log pi ; dH/dlogit_a = -pi_a*(logpi_a - sum_b pi_b logpi_b)
        logpi = np.log(pi + 1e-12)
        ent_base = (pi * logpi).sum(axis=1, keepdims=True)
        g_ent = -pi * (logpi - ent_base)
        # KL(pi||pi_ref) gradient wrt logits: pi_a*( (logpi_a-logref_a) - sum_b pi_b(logpi_b-logref_b) )
        diff = logpi - np.log(pi_ref + 1e-12)
        kl_base = (pi * diff).sum(axis=1, keepdims=True)
        g_kl = pi * (diff - kl_base)

        grad_logits = g_obj + ent_coef * g_ent - beta_kl * g_kl
        grad_W = X.T @ grad_logits / N - l2 * W
        W += lr * grad_W
    return W


def evaluate(W: np.ndarray, X: np.ndarray, acc: np.ndarray, cost: np.ndarray) -> Dict[str, float]:
    pi = softmax(X @ W)
    choice = pi.argmax(axis=1)
    idx = np.arange(len(choice))
    return {
        "policy_acc": float(acc[idx, choice].mean()),
        "policy_cost": float(cost[idx, choice].mean()),
        "policy_inject_rate": float((choice != ARMS.index("none")).mean()),
    }


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--lambda_cost", type=float, default=0.0,
                    help="cost penalty weight in the reward (0 = pure accuracy)")
    ap.add_argument("--folds", type=int, default=5)
    ap.add_argument("--epochs", type=int, default=2000)
    ap.add_argument("--lr", type=float, default=0.5)
    ap.add_argument("--beta_kl", type=float, default=0.05)
    ap.add_argument("--ent_coef", type=float, default=0.01)
    ap.add_argument("--l2", type=float, default=1e-3)
    ap.add_argument("--seed", type=int, default=0)
    args = ap.parse_args()

    rows = load_rows()
    X = featurize(rows)
    acc, cost, reward = build_rewards(rows, args.lambda_cost)
    adv = group_advantage(reward)
    N = len(rows)
    ref_idx = ARMS.index(REF_ARM)

    # ---- fixed-rule and oracle references (full set) ----
    fixed = {a: float(acc[:, i].mean()) for i, a in enumerate(ARMS)}
    fixed_cost = {a: float(cost[:, i].mean()) for i, a in enumerate(ARMS)}
    oracle_acc = float(acc.max(axis=1).mean())

    # ---- K-fold cross-validated policy ----
    rng = np.random.default_rng(args.seed)
    order = rng.permutation(N)
    folds = np.array_split(order, args.folds)
    test_acc, test_cost, test_inj = [], [], []
    for k in range(args.folds):
        te = folds[k]
        tr = np.concatenate([folds[j] for j in range(args.folds) if j != k])
        W = train_policy(X[tr], adv[tr], ref_idx=ref_idx, lr=args.lr, epochs=args.epochs,
                         beta_kl=args.beta_kl, ent_coef=args.ent_coef, l2=args.l2, seed=args.seed)
        m = evaluate(W, X[te], acc[te], cost[te])
        test_acc.append(m["policy_acc"])
        test_cost.append(m["policy_cost"])
        test_inj.append(m["policy_inject_rate"])

    print("=" * 56)
    print(f"Offline GRPO over injection arms  (N={N}, folds={args.folds}, lambda_cost={args.lambda_cost})")
    print("-" * 56)
    print("Fixed-rule baselines (full set):")
    for a in ARMS:
        print(f"  {a:9s}  acc={fixed[a]:.4f}  avg_cost={fixed_cost[a]:.4f}")
    print(f"  ORACLE     acc={oracle_acc:.4f}  (per-question best arm)")
    print("-" * 56)
    print("Learned GRPO policy (cross-validated, held-out folds):")
    print(f"  acc        = {np.mean(test_acc):.4f}  +/- {np.std(test_acc):.4f}")
    print(f"  avg_cost   = {np.mean(test_cost):.4f}  +/- {np.std(test_cost):.4f}")
    print(f"  inject_rate= {np.mean(test_inj):.4f}  (fraction of questions injected)")
    print("=" * 56)
    print("Read: policy acc should sit between best fixed arm and ORACLE; with")
    print("lambda_cost>0 it should keep acc while dropping inject_rate/avg_cost.")


if __name__ == "__main__":
    main()
