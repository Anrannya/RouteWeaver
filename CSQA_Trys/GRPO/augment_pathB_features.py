# -*- coding: utf-8 -*-
"""Augment the path B reward table with the AGREEMENT feature (no LLM calls).

Key signal discovered offline: whether DoT's OWN no-injection answer already agrees
with the validator's retrieved best-guess option.
  * AGREE    -> injection is almost always redundant (helps ~1/118, else neutral)
  * DISAGREE -> essentially ALL injection benefit and risk lives here

Adding this feature lets the cost-aware policy learn a genuine per-question routing
("inject only when DoT disagrees with the evidence") instead of collapsing to a
constant action. The no-injection answer is already cached in the reward table; the
best-guess option is recomputed from the (offline, free) validator. We rewrite the
reward table in place with two extra feature keys: ni_bg_known, ni_bg_disagree.

    cd CSQA_Trys && python GRPO/augment_pathB_features.py
"""

from __future__ import annotations

import json
import os
import sys

CSQA_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, os.path.join(CSQA_DIR, "tools", "csqa_tools"))

from csqa_kb_retriever import CSQAKBRetriever  # noqa: E402
from csqa_knowledge_validator import CSQAKnowledgeValidator  # noqa: E402

CACHE_PATH = os.path.join(os.path.dirname(__file__), "cache", "reward_table_pathB.jsonl")
DATA_PATH = os.path.join(CSQA_DIR, "..", "Task_Datasets", "CSQA", "train_rand_split.jsonl")


def load_questions():
    return [json.loads(l) for l in open(os.path.abspath(DATA_PATH), encoding="utf-8") if l.strip()]


def best_guess_option(validator, retriever, q):
    stem = q["question"]["stem"]
    choices = [{"label": c["label"], "text": c["text"]} for c in q["question"]["choices"]]
    val = validator.validate(stem, choices, retriever.retrieve(stem, choices))
    best = None
    for fe in val.get("fact_evaluations", []):
        if best is None or fe.get("top1_score", 0) > best.get("top1_score", 0):
            best = fe
    return best.get("top_option") if best else None


def main():
    rows = [json.loads(l) for l in open(CACHE_PATH, encoding="utf-8") if l.strip()]
    questions = load_questions()
    retriever = CSQAKBRetriever()
    validator = CSQAKnowledgeValidator()

    n_known = n_disagree = 0
    for r in rows:
        qid = r["qid"]
        ni_letter = r["arms"]["no_inject"]["final_letter"]
        bg = best_guess_option(validator, retriever, questions[qid])
        known = ni_letter is not None and bg is not None
        disagree = known and ni_letter != bg
        r["features"]["ni_bg_known"] = 1.0 if known else 0.0
        r["features"]["ni_bg_disagree"] = 1.0 if disagree else 0.0
        n_known += int(known)
        n_disagree += int(disagree)

    with open(CACHE_PATH, "w", encoding="utf-8") as f:
        for r in rows:
            f.write(json.dumps(r, ensure_ascii=False) + "\n")

    print(f"augmented {len(rows)} rows: best-guess known={n_known}, "
          f"disagree(ni!=bestguess)={n_disagree}")
    print(f"-> {CACHE_PATH}")


if __name__ == "__main__":
    main()
