# -*- coding: utf-8 -*-
"""Offline directional audit of the v2 question-grounded KB (no LLM, no API).

What this measures
------------------
For each question we already have one or more v2 facts per option. This script
scores, per option, whether its attached facts SUPPORT that option (functional /
causal relation, no negation) or RULE IT OUT (a "property" fact phrased as
"... not what is asked"). It then picks the option the KB points to and compares
it with the gold answer (answerKey is used ONLY here, for scoring).

IMPORTANT INTERPRETATION
------------------------
v2 facts were hand-authored from question + options

Run:
    cd CSQA_Trys && python tools/csqa_tools/audit_csqa_v2_kb.py
"""

from __future__ import annotations

import json
import os
import re
from collections import Counter
from datetime import datetime
from typing import Any, Dict, List

BASE_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
QKB_PATH = os.path.join(BASE_DIR, "knowledge_base", "csqa_kb_v2", "question_grounded_kb.jsonl")
DATA_PATH = os.path.join(BASE_DIR, "..", "Task_Datasets", "CSQA", "train_rand_split.jsonl")
LOG_ROOT = os.path.join(BASE_DIR, "Logs", "csqa_kb_v2_audit")

# Dimensions that express a positive, answer-relevant relation.
SUPPORTIVE_DIMENSIONS = {
    "used_for",
    "primary_function",
    "capability",
    "cause",
    "effect",
    "motivation",
    "has_prerequisite",
    "part_whole",
    "typical_location",
}
# Negation cues that mark a fact as ruling its option OUT.
NEGATION_CUES = (
    " not ", "n't", "opposite", "unrelated", "rather than", "instead of",
    "excludes", "not what", "is not", "are not", "no real", " nor ",
    "too broad", "too large", "not the", "not a ", "not where", "not how",
    "not specifically", "not necessarily",
)

ACCEPT_MARGIN = 1  # top option must lead the runner-up by at least this score


def load_gold(path: str) -> Dict[int, str]:
    gold: Dict[int, str] = {}
    with open(path, "r", encoding="utf-8") as f:
        for idx, line in enumerate(f):
            line = line.strip()
            if line:
                gold[idx] = json.loads(line)["answerKey"]
    return gold


def fact_polarity(fact: Dict[str, Any]) -> int:
    """+1 supports the option, -1 rules it out, 0 neutral."""
    text = " " + fact.get("fact", "").lower() + " "
    has_negation = any(cue in text for cue in NEGATION_CUES)
    supportive_dim = fact.get("dimension") in SUPPORTIVE_DIMENSIONS
    if supportive_dim and not has_negation:
        return 1
    if has_negation:
        return -1
    return 0


def score_question(record: Dict[str, Any]) -> Dict[str, Any]:
    option_scores: Dict[str, int] = {c["label"]: 0 for c in record["options"]}
    for fact in record["facts"]:
        option_scores[fact["option_label"]] += fact_polarity(fact)

    ordered = sorted(option_scores.items(), key=lambda x: x[1], reverse=True)
    top_label, top_score = ordered[0]
    runner_label, runner_score = ordered[1] if len(ordered) > 1 else ("", -99)
    margin = top_score - runner_score

    if top_score > 0 and margin >= ACCEPT_MARGIN:
        status, supported = "accepted", top_label
    else:
        status, supported = "abstain", None
    return {
        "scores_by_option": option_scores,
        "supported_option": supported,
        "runner_up_option": runner_label,
        "top_score": top_score,
        "margin": margin,
        "status": status,
    }


def main() -> None:
    records = [json.loads(l) for l in open(QKB_PATH, "r", encoding="utf-8") if l.strip()]
    gold = load_gold(os.path.abspath(DATA_PATH))

    timestamp = datetime.now().strftime("%Y-%m-%d-%H-%M-%S")
    out_dir = os.path.join(LOG_ROOT, timestamp)
    os.makedirs(out_dir, exist_ok=True)

    details: List[Dict[str, Any]] = []
    accepted = 0
    accepted_correct = 0
    wrong_cases: List[Dict[str, Any]] = []

    for record in records:
        qid = record["question_id"]
        scored = score_question(record)
        gold_answer = gold.get(qid)
        correct = None
        if scored["status"] == "accepted":
            accepted += 1
            correct = scored["supported_option"] == gold_answer
            if correct:
                accepted_correct += 1
            else:
                wrong_cases.append({
                    "question_id": qid,
                    "question": record["question"],
                    "options": record["options"],
                    "kb_supported_option": scored["supported_option"],
                    "gold_answer": gold_answer,
                    "scores_by_option": scored["scores_by_option"],
                })
        details.append({
            "question_id": qid,
            "question": record["question"],
            "status": scored["status"],
            "kb_supported_option": scored["supported_option"],
            "gold_answer": gold_answer,
            "supported_option_correct": correct,
            "scores_by_option": scored["scores_by_option"],
            "margin": scored["margin"],
        })

    total = len(records)
    summary = {
        "kb": "csqa_kb_v2 (question-grounded, hand-authored)",
        "question_total": total,
        "accepted_question_count": accepted,
        "accepted_coverage": round(accepted / total, 4) if total else 0.0,
        "accepted_supported_option_accuracy": round(accepted_correct / accepted, 4) if accepted else 0.0,
        "overall_pick_accuracy_incl_abstain": round(accepted_correct / total, 4) if total else 0.0,
        "accept_margin_threshold": ACCEPT_MARGIN,
        "interpretation": (
            "Ceiling / authoring-quality check. v2 facts encode the author's per-option "
            "beliefs, so this mainly reflects authoring accuracy, not open-retrieval utility."
        ),
    }

    with open(os.path.join(out_dir, "details.jsonl"), "w", encoding="utf-8") as f:
        for row in details:
            f.write(json.dumps(row, ensure_ascii=False) + "\n")
    with open(os.path.join(out_dir, "wrong_cases.jsonl"), "w", encoding="utf-8") as f:
        for row in wrong_cases:
            f.write(json.dumps(row, ensure_ascii=False) + "\n")
    with open(os.path.join(out_dir, "summary.json"), "w", encoding="utf-8") as f:
        json.dump(summary, f, ensure_ascii=False, indent=2)

    print(json.dumps(summary, ensure_ascii=False, indent=2))
    print(f"\nWrong / mis-authored cases: {len(wrong_cases)} (see wrong_cases.jsonl)")
    print(f"Output dir: {out_dir}")


if __name__ == "__main__":
    main()
