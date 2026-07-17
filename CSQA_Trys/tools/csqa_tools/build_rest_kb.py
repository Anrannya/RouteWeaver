# -*- coding: utf-8 -*-
"""Merge hand-authored rest-of-split knowledge (rest_kb_data.KNOWLEDGE_REST)
into the v2 CSQA KB, then rebuild the flat retriever KB.

* Writes per-question packs for non-eval qids to:
      knowledge_base/csqa_kb_v2/question_grounded_kb_rest.jsonl
  (idempotent: a qid already present is skipped, so you can grow
  rest_kb_data.py batch by batch and re-run.)
* Rebuilds the flat retriever KB:
      knowledge_base/csqa_kb_v2/csqa_commonsense_kb_v2.jsonl
  from BOTH the original 200-question pack (question_grounded_kb.jsonl)
  and the rest pack (question_grounded_kb_rest.jsonl).

Safety:
* answerKey is never read.
* The eval-200 qids (from TmpRes/step2In_csqa_last.json) are refused here,
  so this tool can only ADD non-eval questions.
* The original question_grounded_kb.jsonl is never modified.

Run:
    cd CSQA_Trys && python tools/csqa_tools/build_rest_kb.py
"""

from __future__ import annotations

import json
import os
import random
import sys
from typing import Any, Dict, List

FLAT_SHUFFLE_SEED = 42

BASE_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
sys.path.insert(0, os.path.join(BASE_DIR, "tools", "csqa_tools"))

from rest_kb_data import KNOWLEDGE_REST

DATA_PATH = os.path.join(BASE_DIR, "..", "Task_Datasets", "CSQA", "train_rand_split.jsonl")
STEP2IN_PATH = os.path.join(BASE_DIR, "TmpRes", "step2In_csqa_last.json")
OUT_DIR = os.path.join(BASE_DIR, "knowledge_base", "csqa_kb_v2")
QKB_MAIN = os.path.join(OUT_DIR, "question_grounded_kb.jsonl")        # original 200
QKB_REST = os.path.join(OUT_DIR, "question_grounded_kb_rest.jsonl")   # our additions
FLAT_PATH = os.path.join(OUT_DIR, "csqa_commonsense_kb_v2.jsonl")

ALLOWED_DIMENSIONS = {
    "primary_function", "used_for", "capability", "typical_location", "cause",
    "effect", "has_prerequisite", "motivation", "property", "part_whole",
}


def load_questions(path: str) -> List[Dict[str, Any]]:
    rows: List[Dict[str, Any]] = []
    with open(path, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                rows.append(json.loads(line))
    return rows


def eval_ids() -> set:
    with open(STEP2IN_PATH, "r", encoding="utf-8") as f:
        step2in = json.load(f)
    return {int(k) for k in step2in.keys()}


def load_existing_rest_ids() -> set:
    done = set()
    if os.path.exists(QKB_REST):
        with open(QKB_REST, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if line:
                    try:
                        done.add(json.loads(line)["question_id"])
                    except (json.JSONDecodeError, KeyError):
                        continue
    return done


def build_pack(qid: int, questions, authored) -> Dict[str, Any]:
    entry = questions[qid]["question"]
    stem = entry["stem"]
    concept = entry.get("question_concept", "")
    choices = [{"label": c["label"], "text": c["text"]} for c in entry["choices"]]
    label_to_text = {c["label"]: c["text"] for c in choices}

    facts: List[Dict[str, Any]] = []
    per_option: Dict[str, int] = {}
    seen = set()
    for label, dimension, fact_text in authored:
        label = label.strip().upper()[:1]
        assert label in label_to_text, f"Q{qid}: unknown option label {label}"
        assert dimension in ALLOWED_DIMENSIONS, f"Q{qid}: bad dimension {dimension}"
        fact_text = fact_text.strip()
        assert len(fact_text) >= 8, f"Q{qid}: fact too short: {fact_text!r}"
        key = (label, fact_text.lower())
        if key in seen:
            continue
        seen.add(key)
        idx = per_option.get(label, 0) + 1
        per_option[label] = idx
        facts.append({
            "fact_id": f"q{qid}_{label}_{idx}",
            "question_id": qid,
            "option_label": label,
            "concept": label_to_text[label],
            "dimension": dimension,
            "fact": fact_text,
            "conditions": [],
        })
    return {
        "question_id": qid,
        "question": stem,
        "question_concept": concept,
        "options": choices,
        "facts": facts,
    }


def rebuild_flat() -> int:
    """Rebuild flat retriever KB: strip metadata fields, shuffle, re-id."""
    rows: List[Dict[str, Any]] = []
    for pack_path in (QKB_MAIN, QKB_REST):
        if not os.path.exists(pack_path):
            continue
        with open(pack_path, "r", encoding="utf-8") as src:
            for line in src:
                line = line.strip()
                if not line:
                    continue
                record = json.loads(line)
                for fact in record.get("facts", []):
                    rows.append({
                        "concept": fact["concept"],
                        "dimension": fact["dimension"],
                        "fact": fact["fact"],
                    })

    random.seed(FLAT_SHUFFLE_SEED)
    random.shuffle(rows)

    with open(FLAT_PATH, "w", encoding="utf-8") as dst:
        for i, item in enumerate(rows, start=1):
            out = {"fact_id": f"fact_{i:06d}", **item}
            dst.write(json.dumps(out, ensure_ascii=False) + "\n")
    return len(rows)


def main() -> None:
    os.makedirs(OUT_DIR, exist_ok=True)
    questions = load_questions(os.path.abspath(DATA_PATH))
    excluded = eval_ids()
    existing = load_existing_rest_ids()

    authored_ids = sorted(KNOWLEDGE_REST.keys())
    refused_eval = [q for q in authored_ids if q in excluded]
    if refused_eval:
        raise SystemExit(f"[ABORT] these qids are eval questions and must not be added: {refused_eval}")

    to_write = [q for q in authored_ids if q not in existing]
    written = 0
    with open(QKB_REST, "a", encoding="utf-8") as out:
        for qid in to_write:
            pack = build_pack(qid, questions, KNOWLEDGE_REST[qid])
            out.write(json.dumps(pack, ensure_ascii=False) + "\n")
            written += 1

    total_rest = len(existing) + written
    flat = rebuild_flat()
    print(f"authored in data file : {len(authored_ids)}")
    print(f"newly written this run: {written}")
    print(f"rest packs total      : {total_rest}  -> {QKB_REST}")
    print(f"flat retriever facts  : {flat}  -> {FLAT_PATH}")
    print(f"(eval questions excluded: {len(excluded)})")


if __name__ == "__main__":
    main()
