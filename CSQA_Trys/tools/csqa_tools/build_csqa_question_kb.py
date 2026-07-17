# -*- coding: utf-8 -*-
"""Generate question-grounded, answer-helpful commonsense knowledge for CSQA.

Why this exists
---------------
The original KB (knowledge_base/csqa_kb_v1) was built from WordNet, so ~80% of
its facts are dictionary "X is a kind of Y" definitions. A strong teacher
(DeepSeek) correctly rejects them as `defines_option_only`: a definition explains
what an option *is* but does not help DECIDE whether it answers the question.

This script builds a complementary KB (knowledge_base/csqa_kb_v2) that, for each
question, writes short FUNCTIONAL / CAUSAL / LOCATIONAL / PURPOSE facts about each
option, i.e. the relations that actually discriminate options.

Strict constraints
------------------
* Input is ONLY the question + 5 options (+ question_concept hint). answerKey is
  never read or sent to the model. The model is explicitly told not to reveal a
  correct option.
* Pure dictionary definitions are forbidden in the prompt.
* One API call per question, temperature 0, JSON output, resume + cache.

Default scope: the 200 questions in TmpRes/step2In_csqa_last.json (ids 0..199).

Run (DeepSeek, 200 questions):
    export DEEPSEEK_API_KEY=...
    cd CSQA_Trys && python tools/csqa_tools/build_csqa_question_kb.py --limit 200
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from typing import Any, Dict, List

BASE_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
sys.path.insert(0, os.path.join(BASE_DIR, "tools", "csqa_tools"))

from build_csqa_teacher_labels import DeepSeekTeacher, extract_json, options_block

DATA_PATH = os.path.join(BASE_DIR, "..", "Task_Datasets", "CSQA", "train_rand_split.jsonl")
STEP2IN_PATH = os.path.join(BASE_DIR, "TmpRes", "step2In_csqa_last.json")
OUT_DIR = os.path.join(BASE_DIR, "knowledge_base", "csqa_kb_v2")
QKB_PATH = os.path.join(OUT_DIR, "question_grounded_kb.jsonl")   # per-question packs
FLAT_PATH = os.path.join(OUT_DIR, "csqa_commonsense_kb_v2.jsonl")  # retriever-compatible

# Functional / relational dimensions we actually want (no bare definitions).
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

GEN_SYSTEM = (
    "You write short, standalone commonsense facts for a multiple-choice QA system. "
    "You are NOT told the correct answer and must NOT state or imply which option is "
    "correct. Your job is to surface the relations that let a solver DISTINGUISH the "
    "options.\n"
    "Rules:\n"
    "1. For EACH option, write 1-2 facts capturing its relation to the question's key "
    "condition: what it is used for, where it is found, what it causes, what it "
    "enables, what it requires, why someone does it, or its single most relevant "
    "property.\n"
    "2. FORBIDDEN: bare dictionary definitions such as 'X is a kind of Y' / 'X is a "
    "type of Z' with no functional, causal, locational, or purpose content.\n"
    "3. Facts must be generally true (decontextualized), not invented to fit this "
    "question, and must not reference the question text or answer.\n"
    "4. Keep each fact to one concise sentence.\n"
    "Output STRICT JSON only."
)


def load_questions(path: str) -> List[Dict[str, Any]]:
    rows: List[Dict[str, Any]] = []
    with open(path, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                rows.append(json.loads(line))
    return rows


def target_ids(limit: int) -> List[int]:
    with open(STEP2IN_PATH, "r", encoding="utf-8") as f:
        step2in = json.load(f)
    ids = sorted(int(k) for k in step2in.keys())
    return ids[:limit]


def build_prompt(question: str, concept: str, choices: List[Dict[str, str]]) -> str:
    return (
        f"Question: {question}\n"
        f"Key concept: {concept}\n"
        f"Options: {options_block(choices)}\n\n"
        "For EACH option output 1-2 JSON objects with keys:\n"
        '  "option_label": option letter (A-E),\n'
        '  "concept": the option text,\n'
        '  "dimension": one of '
        '["primary_function","used_for","capability","typical_location","cause",'
        '"effect","has_prerequisite","motivation","property","part_whole"],\n'
        '  "fact": one concise standalone commonsense sentence (no definitions, no '
        "reference to this question or its answer).\n"
        "Return a single JSON array of all objects. No extra text."
    )


def sanitize_facts(qid: int, choices: List[Dict[str, str]], parsed: Any) -> List[Dict[str, Any]]:
    valid_labels = {c["label"] for c in choices}
    facts: List[Dict[str, Any]] = []
    seen = set()
    if not isinstance(parsed, list):
        return facts
    per_option_counter: Dict[str, int] = {}
    for item in parsed:
        if not isinstance(item, dict):
            continue
        label = str(item.get("option_label", "")).strip().upper()[:1]
        if label not in valid_labels:
            continue
        dimension = str(item.get("dimension", "")).strip()
        if dimension not in ALLOWED_DIMENSIONS:
            dimension = "property"
        fact_text = str(item.get("fact", "")).strip()
        if len(fact_text) < 8:
            continue
        dedup_key = (label, fact_text.lower())
        if dedup_key in seen:
            continue
        seen.add(dedup_key)
        idx = per_option_counter.get(label, 0) + 1
        per_option_counter[label] = idx
        concept = str(item.get("concept", "")).strip() or next(
            c["text"] for c in choices if c["label"] == label
        )
        facts.append(
            {
                "fact_id": f"q{qid}_{label}_{idx}",
                "question_id": qid,
                "option_label": label,
                "concept": concept,
                "dimension": dimension,
                "fact": fact_text,
                "conditions": [],
            }
        )
    return facts


def load_done_ids(path: str) -> set:
    done = set()
    if os.path.exists(path):
        with open(path, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if line:
                    try:
                        done.add(json.loads(line)["question_id"])
                    except (json.JSONDecodeError, KeyError):
                        continue
    return done


def rewrite_flat_kb() -> int:
    """Flatten all per-question packs into a retriever-compatible jsonl."""
    count = 0
    with open(QKB_PATH, "r", encoding="utf-8") as src, open(FLAT_PATH, "w", encoding="utf-8") as dst:
        for line in src:
            line = line.strip()
            if not line:
                continue
            record = json.loads(line)
            for fact in record.get("facts", []):
                dst.write(json.dumps(fact, ensure_ascii=False) + "\n")
                count += 1
    return count


def main() -> None:
    parser = argparse.ArgumentParser(description="Generate question-grounded CSQA knowledge")
    parser.add_argument("--limit", type=int, default=200, help="Number of questions (ids 0..limit-1)")
    args = parser.parse_args()

    os.makedirs(OUT_DIR, exist_ok=True)
    questions = load_questions(os.path.abspath(DATA_PATH))
    ids = target_ids(args.limit)
    done_ids = load_done_ids(QKB_PATH)
    pending = [qid for qid in ids if qid not in done_ids]

    if not pending:
        n = rewrite_flat_kb()
        print(f"All {len(ids)} questions already generated. Flat KB facts: {n} -> {FLAT_PATH}")
        return

    teacher = DeepSeekTeacher()
    written = 0
    with open(QKB_PATH, "a", encoding="utf-8") as out:
        for qid in pending:
            entry = questions[qid]
            stem = entry["question"]["stem"]
            concept = entry["question"].get("question_concept", "")
            choices = [{"label": c["label"], "text": c["text"]} for c in entry["question"]["choices"]]

            raw = teacher.chat(GEN_SYSTEM, build_prompt(stem, concept, choices), max_new_tokens=900)
            facts = sanitize_facts(qid, choices, extract_json(raw))
            record = {
                "question_id": qid,
                "question": stem,
                "question_concept": concept,
                "options": choices,
                "facts": facts,
            }
            out.write(json.dumps(record, ensure_ascii=False) + "\n")
            out.flush()
            written += 1
            covered = len({f["option_label"] for f in facts})
            print(f"[{written}/{len(pending)}] qid={qid} facts={len(facts)} options_covered={covered}/5")

    total = rewrite_flat_kb()
    print(f"Done. Generated {written} new questions -> {QKB_PATH}")
    print(f"Flat retriever-compatible KB: {total} facts -> {FLAT_PATH}")


if __name__ == "__main__":
    main()
