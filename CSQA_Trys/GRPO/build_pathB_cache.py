# -*- coding: utf-8 -*-
"""Build the OFFLINE reward table for PATH B (sequential / multi-position GRPO).

Action = WHERE to inject the (forced best-guess) knowledge along the reasoning chain:
    no_inject     -> never inject (DoT baseline)
    inject_first  -> inject only at the earliest sub-question node
    inject_last   -> inject only at the terminal decision sub-question node
    inject_final  -> inject only at the final-summary prompt
    inject_all    -> inject at every sub-question node

For each action we record reward (1 if final letter == gold) and a cost proxy
(#injection points * hint length). State features are identical to path A (derived
offline from the retriever + validator on the main question), so the same policy /
featurizer code is reused. Sub-question calls hit the local model (cheap); only the
final summary hits the remote model. temperature=0 + on-disk cache => re-runs free.

    cd CSQA_Trys && python GRPO/build_pathB_cache.py --limit 200 --backend real
    cd CSQA_Trys && python GRPO/build_pathB_cache.py --limit 10 --backend mock   # plumbing
"""

from __future__ import annotations

import argparse
import importlib.util
import json
import os
from typing import Any, Dict, List

from injection_env import InjectionEnv
from llm_backend import LLMBackend
from pathB_probe import first_node, run_condition

HERE = os.path.dirname(__file__)
OUT_PATH = os.path.join(HERE, "cache", "reward_table_pathB.jsonl")
ARMS = ["no_inject", "inject_first", "inject_last", "inject_final", "inject_all"]

# reuse path A's offline feature extractor (single source of truth)
_spec = importlib.util.spec_from_file_location("brc", os.path.join(HERE, "build_reward_cache.py"))
brc = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(brc)
extract_features = brc.extract_features


def arm_cost(env: InjectionEnv, qid: int, arm: str, hint) -> int:
    if hint is None or arm == "no_inject":
        return 0
    if arm == "inject_all":
        n_nodes = len(env.dag[str(qid)]["steps_dict"])
        return len(hint) * n_nodes
    return len(hint)  # single injection point


def load_done(path: str) -> Dict[int, Dict[str, Any]]:
    done = {}
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
    ap.add_argument("--resume", action="store_true")
    args = ap.parse_args()

    os.makedirs(os.path.dirname(OUT_PATH), exist_ok=True)
    backend = LLMBackend(backend=args.backend, temperature=0.0)
    env = InjectionEnv(backend)
    n = min(args.limit, len(env.questions))

    done = load_done(OUT_PATH) if args.resume else {}
    rows: List[Dict[str, Any]] = [done[q] for q in sorted(done) if q < n]
    todo = [q for q in range(n) if q not in done]

    for idx, qid in enumerate(todo):
        feats = extract_features(env, qid)
        hint = env.build_forced_hint(qid, mode="bestguess")
        arms = {}
        for arm in ARMS:
            res = run_condition(env, qid, arm, hint)
            arms[arm] = {
                "final_letter": res["final_letter"],
                "reward": int(res["correct"]),
                "cost": arm_cost(env, qid, arm, hint),
                "injected": (arm != "no_inject" and hint is not None),
            }
        rows.append({"qid": qid, "gold": env.questions[qid]["answerKey"],
                     "features": feats, "arms": arms})
        backend.flush()
        if (idx + 1) % 10 == 0:
            print(f"  ... {idx + 1}/{len(todo)} new questions done")

    rows.sort(key=lambda r: r["qid"])
    with open(OUT_PATH, "w", encoding="utf-8") as f:
        for r in rows:
            f.write(json.dumps(r, ensure_ascii=False) + "\n")
    backend.flush()

    arm_acc = {a: sum(r["arms"][a]["reward"] for r in rows) for a in ARMS}
    oracle = sum(max(r["arms"][a]["reward"] for a in ARMS) for r in rows)
    decisive = sum(1 for r in rows if len({r["arms"][a]["reward"] for a in ARMS}) > 1)
    total = len(rows)
    print("\n" + "=" * 50)
    print(f"path B reward table: {total} questions  backend={args.backend}")
    for a in ARMS:
        print(f"  arm={a:13s} correct={arm_acc[a]:3d}/{total}  acc={arm_acc[a]/total:.4f}")
    print(f"  ORACLE (best position per q) = {oracle}/{total}  acc={oracle/total:.4f}")
    print(f"  decision-relevant (positions disagree) = {decisive}/{total}")
    print(f"\nOutput -> {OUT_PATH}")


if __name__ == "__main__":
    main()
