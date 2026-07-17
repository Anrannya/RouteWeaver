# -*- coding: utf-8 -*-
"""Offline sequential GRPO over INJECTION POSITIONS (path B). Pure numpy, NO LLM.

Action group per question = the 5 placement choices
    {no_inject, inject_first, inject_last, inject_final, inject_all}
with cached deterministic rewards (build_pathB_cache.py). Same GRPO machinery as
path A (group-relative advantage, KL-to-reference, entropy; no value network) but
the reference policy is `inject_final` and the headline comparison is against the
NO-INJECTION baseline: the goal here is simply policy_acc > no_inject.

This is a genuine multi-step formulation: injecting at an upstream node changes that
sub-answer, which propagates downstream (verified: ~17.5% of questions are
position-sensitive). The policy must learn to place injection safely (prefer
late/final, avoid harmful early/over-injection).

    cd CSQA_Trys && python GRPO/train_pathB_policy.py
    cd CSQA_Trys && python GRPO/train_pathB_policy.py --lambda_cost 0.1
"""

from __future__ import annotations

import argparse
import importlib.util
import json
import os

import numpy as np

HERE = os.path.dirname(__file__)
CACHE_PATH = os.path.join(HERE, "cache", "reward_table_pathB.jsonl")
ARMS = ["no_inject", "inject_first", "inject_last", "inject_final", "inject_all"]
REF_ARM = "inject_final"
BASELINE_ARM = "no_inject"

# reuse path A policy/feature math (single source of truth)
_spec = importlib.util.spec_from_file_location("tg", os.path.join(HERE, "train_grpo_policy.py"))
tg = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(tg)


def load_rows():
    return [json.loads(l) for l in open(CACHE_PATH, encoding="utf-8") if l.strip()]


def build_rewards(rows, lambda_cost):
    acc = np.array([[r["arms"][a]["reward"] for a in ARMS] for r in rows], dtype=np.float64)
    raw_cost = np.array([[r["arms"][a]["cost"] for a in ARMS] for r in rows], dtype=np.float64)
    cmax = raw_cost.max() if raw_cost.max() > 0 else 1.0
    cost = raw_cost / cmax
    return acc, cost, acc - lambda_cost * cost


def cv_policy(X, adv, acc, cost, folds, seeds, **hp):
    accs, costs, injs = [], [], []
    base_idx = ARMS.index(BASELINE_ARM)
    for seed in seeds:
        rng = np.random.default_rng(seed)
        order = rng.permutation(len(X))
        parts = np.array_split(order, folds)
        for k in range(folds):
            te = parts[k]
            tr = np.concatenate([parts[j] for j in range(folds) if j != k])
            W = tg.train_policy(X[tr], adv[tr], ref_idx=ARMS.index(REF_ARM), seed=seed, **hp)
            pi = tg.softmax(X[te] @ W)
            ch = pi.argmax(1)
            idx = np.arange(len(ch))
            accs.append(acc[te][idx, ch].mean())
            costs.append(cost[te][idx, ch].mean())
            injs.append((ch != base_idx).mean())
    return np.mean(accs), np.std(accs), np.mean(costs), np.mean(injs)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--lambda_cost", type=float, default=0.0)
    ap.add_argument("--folds", type=int, default=5)
    ap.add_argument("--epochs", type=int, default=2000)
    ap.add_argument("--lr", type=float, default=0.5)
    ap.add_argument("--beta_kl", type=float, default=0.02)
    ap.add_argument("--ent_coef", type=float, default=0.01)
    ap.add_argument("--l2", type=float, default=1e-3)
    args = ap.parse_args()

    rows = load_rows()
    X = tg.featurize(rows)
    n = len(rows)
    acc, cost, reward = build_rewards(rows, args.lambda_cost)
    adv = tg.group_advantage(reward)
    hp = dict(lr=args.lr, epochs=args.epochs, beta_kl=args.beta_kl,
              ent_coef=args.ent_coef, l2=args.l2)

    fixed = {a: float(acc[:, i].mean()) for i, a in enumerate(ARMS)}
    fixed_cost = {a: float(cost[:, i].mean()) for i, a in enumerate(ARMS)}
    oracle = float(acc.max(axis=1).mean())
    base = fixed[BASELINE_ARM]

    p_acc, p_std, p_cost, p_inj = cv_policy(X, adv, acc, cost, args.folds, range(5), **hp)

    print("=" * 60)
    print(f"Path B - offline sequential GRPO over injection positions")
    print(f"(N={n}, folds={args.folds}, lambda_cost={args.lambda_cost})")
    print("-" * 60)
    print("Fixed-position baselines:")
    for a in ARMS:
        flag = "  <- baseline" if a == BASELINE_ARM else ("  <- ref" if a == REF_ARM else "")
        print(f"  {a:13s} acc={fixed[a]:.4f}  avg_cost={fixed_cost[a]:.4f}{flag}")
    print(f"  {'ORACLE':13s} acc={oracle:.4f}  (best position per question)")
    print("-" * 60)
    print("Learned GRPO policy (5x5-fold CV, held-out):")
    print(f"  acc        = {p_acc:.4f} +/- {p_std:.4f}")
    print(f"  avg_cost   = {p_cost:.4f}   inject_rate = {p_inj:.4f}")
    print("-" * 60)
    delta = p_acc - base
    verdict = "PASS (policy beats no-injection)" if delta > 0 else "FAIL (policy <= no-injection)"
    print(f"  policy vs no_inject baseline: {p_acc:.4f} - {base:.4f} = {delta:+.4f}  -> {verdict}")
    print("=" * 60)


if __name__ == "__main__":
    main()
