# -*- coding: utf-8 -*-
"""Build the OFFLINE reward table for GRPO (lightweight version).

For every covered question we evaluate the SAME 3 injection arms:
    none      -> no knowledge injected (let DoT answer on its own)
    facts     -> force-inject top-k retrieved facts at final summary (no option claim)
    bestguess -> facts + a soft pointer to the validator's top option

For each arm we record:
    * reward  : 1 if the final letter == gold else 0  (accuracy reward)
    * cost    : length (chars) of the injected hint   (proxy for token/inference cost)

We also record the per-question STATE FEATURES the policy will see at decision time
(all derived offline from the retriever + validator on the MAIN question/options).

The result is a single self-contained dataset (reward_table.jsonl). Training the GRPO
policy afterwards is pure numpy/sklearn and touches NO LLM. Because LLMBackend caches
every call keyed by (model, temperature, messages) with temperature=0, re-running this
script is free after the first full pass.

Run once in tmux (DoT_env active, DEEPSEEK_API_KEY set, ollama up):
    cd CSQA_Trys && python GRPO/build_reward_cache.py --limit 200 --backend real
Quick plumbing self-test (no scientific meaning):
    cd CSQA_Trys && python GRPO/build_reward_cache.py --limit 10 --backend mock
"""

from __future__ import annotations

import argparse
import json
import os
from typing import Any, Dict, List, Optional

from injection_env import InjectionEnv
from llm_backend import LLMBackend

ARMS = ["none", "facts", "bestguess"]
OUT_DIR = os.path.join(os.path.dirname(__file__), "cache")
OUT_PATH = os.path.join(OUT_DIR, "reward_table.jsonl")


def extract_features(env: InjectionEnv, qid: int) -> Dict[str, Any]:
    """Offline state the policy will condition on. Everything here is available
    BEFORE any (extra) LLM call, so it is a legal decision-time observation."""
    entry = env.questions[qid]
    stem = entry["question"]["stem"]
    choices = entry["question"]["choices"]
    ev = env.build_evidence(qid)
    val = ev["_val"]
    cands = ev["_cands"]
    fevals = val.get("fact_evaluations", []) or []

    top1_scores = [fe.get("top1_score", 0.0) for fe in fevals]
    margins = [fe.get("margin", 0.0) for fe in fevals]
    options_supported = {fe.get("top_option") for fe in fevals if fe.get("top_option")}

    return {
        "status": val.get("status"),
        "reason": val.get("reason"),
        "n_candidates": len(cands),
        "n_fact_evals": len(fevals),
        "max_top1": round(max(top1_scores), 4) if top1_scores else 0.0,
        "mean_top1": round(sum(top1_scores) / len(top1_scores), 4) if top1_scores else 0.0,
        "max_margin": round(max(margins), 4) if margins else 0.0,
        "n_distinct_supported_options": len(options_supported),
        "n_conflicting_options": len(val.get("conflicting_options", []) or []),
        "n_supporting_facts": len(val.get("supporting_facts", []) or []),
        "stem_len": len(stem.split()),
        "n_options": len(choices),
    }


def run_arm(env: InjectionEnv, qid: int, arm: str) -> Dict[str, Any]:
    if arm == "none":
        res = env.solve(qid)
        hint = None
    else:
        hint = env.build_forced_hint(qid, mode=arm)
        # If the KB has nothing to inject, the arm degenerates to 'none'.
        res = env.solve(qid, inject_final=True, override_hint=hint) if hint else env.solve(qid)
    return {
        "final_letter": res["final_letter"],
        "reward": int(res["correct"]),
        "cost": len(hint) if hint else 0,
        "injected": bool(hint),
    }


def load_done(path: str) -> Dict[int, Dict[str, Any]]:
    done: Dict[int, Dict[str, Any]] = {}
    if os.path.exists(path):
        for line in open(path, encoding="utf-8"):
            line = line.strip()
            if line:
                row = json.loads(line)
                done[row["qid"]] = row
    return done


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--limit", type=int, default=200)
    ap.add_argument("--backend", choices=["real", "mock"], default="real")
    ap.add_argument("--resume", action="store_true",
                    help="skip qids already present in reward_table.jsonl")
    args = ap.parse_args()

    os.makedirs(OUT_DIR, exist_ok=True)
    backend = LLMBackend(backend=args.backend, temperature=0.0)
    env = InjectionEnv(backend)
    n = min(args.limit, len(env.questions))

    done = load_done(OUT_PATH) if args.resume else {}
    rows: List[Dict[str, Any]] = [done[q] for q in sorted(done) if q < n]
    todo = [q for q in range(n) if q not in done]

    for idx, qid in enumerate(todo):
        feats = extract_features(env, qid)
        arms = {arm: run_arm(env, qid, arm) for arm in ARMS}
        rows.append({
            "qid": qid,
            "gold": env.questions[qid]["answerKey"],
            "features": feats,
            "arms": arms,
        })
        backend.flush()
        if (idx + 1) % 10 == 0:
            print(f"  ... {idx + 1}/{len(todo)} new questions done")

    rows.sort(key=lambda r: r["qid"])
    with open(OUT_PATH, "w", encoding="utf-8") as f:
        for r in rows:
            f.write(json.dumps(r, ensure_ascii=False) + "\n")
    backend.flush()

    # --- quick offline summary of the table (no LLM) ---
    arm_acc = {a: sum(r["arms"][a]["reward"] for r in rows) for a in ARMS}
    oracle = sum(max(r["arms"][a]["reward"] for a in ARMS) for r in rows)
    # how many questions are "decision-relevant" (arms disagree in correctness)
    decisive = sum(1 for r in rows if len({r["arms"][a]["reward"] for a in ARMS}) > 1)
    total = len(rows)
    print("\n" + "=" * 46)
    print(f"reward table built: {total} questions  backend={args.backend}")
    for a in ARMS:
        print(f"  arm={a:9s} correct={arm_acc[a]:3d}/{total}  acc={arm_acc[a]/total:.4f}")
    print(f"  ORACLE (best arm per q) = {oracle}/{total}  acc={oracle/total:.4f}")
    print(f"  decision-relevant (arms disagree) = {decisive}/{total}")
    print(f"\nOutput -> {OUT_PATH}")


if __name__ == "__main__":
    main()
