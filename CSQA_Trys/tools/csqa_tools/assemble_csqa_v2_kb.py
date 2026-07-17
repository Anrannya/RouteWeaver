# -*- coding: utf-8 -*-
"""Assemble the v2 question-grounded CSQA knowledge base (offline, no LLM/API).

Knowledge is hand-authored in csqa_v2_knowledge_data.KNOWLEDGE, derived ONLY from
each question's stem + options (never from answerKey). Each entry is a tuple:
    (option_label, dimension, fact)
where `dimension` is a functional/relational type (not a bare definition) and
`fact` is one concise standalone commonsense sentence.

This assembler validates the data against the actual CSQA options, attaches the
option text as `concept`, assigns deterministic fact_ids, and writes:
    knowledge_base/csqa_kb_v2/question_grounded_kb.jsonl   (per-question packs)
    knowledge_base/csqa_kb_v2/csqa_commonsense_kb_v2.jsonl (retriever-compatible)

Run:
    cd CSQA_Trys && python tools/csqa_tools/assemble_csqa_v2_kb.py
"""

from __future__ import annotations

import json
import os
import sys
from typing import Any, Dict, List

BASE_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
sys.path.insert(0, os.path.join(BASE_DIR, "tools", "csqa_tools"))

from csqa_v2_knowledge_data import KNOWLEDGE

DATA_PATH = os.path.join(BASE_DIR, "..", "Task_Datasets", "CSQA", "train_rand_split.jsonl")
STEP2IN_PATH = os.path.join(BASE_DIR, "TmpRes", "step2In_csqa_last.json")
OUT_DIR = os.path.join(BASE_DIR, "knowledge_base", "csqa_kb_v2")
QKB_PATH = os.path.join(OUT_DIR, "question_grounded_kb.jsonl")
FLAT_PATH = os.path.join(OUT_DIR, "csqa_commonsense_kb_v2.jsonl")

ALLOWED_DIMENSIONS = {
    "primary_function",
    "used_for",
    "capability",
    "typical_location",
    "cause",
    "effect",
    "has_prerequisite",
    "motivation",
    "property",
    "part_whole",
}


def load_questions(path: str) -> List[Dict[str, Any]]:
    rows: List[Dict[str, Any]] = []
    with open(path, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                rows.append(json.loads(line))
    return rows


def target_ids() -> List[int]:
    with open(STEP2IN_PATH, "r", encoding="utf-8") as f:
        step2in = json.load(f)
    return sorted(int(k) for k in step2in.keys())


def main() -> None:
    os.makedirs(OUT_DIR, exist_ok=True)
    questions = load_questions(os.path.abspath(DATA_PATH))
    ids = target_ids()

    total_facts = 0
    missing_questions: List[int] = []
    coverage_warn: List[int] = []

    with open(QKB_PATH, "w", encoding="utf-8") as qout, \
            open(FLAT_PATH, "w", encoding="utf-8") as fout:
        for qid in ids:
            entry = questions[qid]["question"]
            stem = entry["stem"]
            concept = entry.get("question_concept", "")
            choices = [{"label": c["label"], "text": c["text"]} for c in entry["choices"]]
            label_to_text = {c["label"]: c["text"] for c in choices}

            authored = KNOWLEDGE.get(qid)
            if not authored:
                missing_questions.append(qid)
                continue

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
                fact = {
                    "fact_id": f"q{qid}_{label}_{idx}",
                    "question_id": qid,
                    "option_label": label,
                    "concept": label_to_text[label],
                    "dimension": dimension,
                    "fact": fact_text,
                    "conditions": [],
                }
                facts.append(fact)
                fout.write(json.dumps(fact, ensure_ascii=False) + "\n")
                total_facts += 1

            if len(per_option) < len(choices):
                coverage_warn.append(qid)

            qout.write(json.dumps(
                {
                    "question_id": qid,
                    "question": stem,
                    "question_concept": concept,
                    "options": choices,
                    "facts": facts,
                },
                ensure_ascii=False,
            ) + "\n")

    print(f"Questions targeted: {len(ids)}")
    print(f"Questions authored: {len(ids) - len(missing_questions)}")
    print(f"Total facts written: {total_facts}")
    print(f"Per-question pack -> {QKB_PATH}")
    print(f"Flat retriever KB  -> {FLAT_PATH}")
    if missing_questions:
        print(f"[WARN] missing authored knowledge for qids: {missing_questions}")
    if coverage_warn:
        print(f"[WARN] not all 5 options covered for qids: {coverage_warn}")


if __name__ == "__main__":
    main()
