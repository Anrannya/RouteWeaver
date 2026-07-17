# -*- coding: utf-8 -*-
"""Extend the v2 question-grounded KB to the REST of the CSQA training split.

Scope
-----
All questions in train_rand_split.jsonl EXCEPT the 200 evaluation questions
(the ids present in TmpRes/step2In_csqa_last.json). For each remaining
question we generate 1-2 short v2-style facts (functional / causal /
locational / purpose relations, no bare definitions), then rewrite the flat
retriever-compatible KB so the new facts join the existing v2 KB.

Same constraints as build_csqa_question_kb.py:
* Input is ONLY the question + 5 options (+ question_concept hint). answerKey
  is never read or sent to the model, and the model is told not to reveal a
  correct option.
* Records are appended to the SAME per-question pack file
  (question_grounded_kb.jsonl) with resume support, so the script can be
  stopped and restarted at any time.
* fact_id format q{qid}_{label}_{idx} is unchanged -> no id clashes with the
  existing 200-question packs.

Run (in tmux; ~9.5k questions, use --workers to parallelize API calls):
    export DEEPSEEK_API_KEY=...
    cd CSQA_Trys
    # smoke test on 20 questions first:
    python tools/csqa_tools/build_csqa_question_kb_rest.py --limit 20
    # full run:
    python tools/csqa_tools/build_csqa_question_kb_rest.py --workers 4
"""

from __future__ import annotations

import argparse
import json
import os
import shutil
import sys
import threading
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime
from typing import Any, Dict, List

BASE_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
sys.path.insert(0, os.path.join(BASE_DIR, "tools", "csqa_tools"))

from build_csqa_teacher_labels import DeepSeekTeacher, extract_json, options_block

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

MAX_FACTS_PER_QUESTION = 2

GEN_SYSTEM = (
    "You write short, standalone commonsense facts for a multiple-choice QA system. "
    "You are NOT told the correct answer and must NOT state or imply which option is "
    "correct. Your job is to surface the most informative relations for reasoning "
    "about the question.\n"
    "Rules:\n"
    "1. Write AT MOST 2 facts in total for the whole question. Pick the 1-2 option "
    "concepts whose relation to the question's key condition is most informative "
    "(what it is used for, where it is found, what it causes, what it enables, what "
    "it requires, why someone does it, or its single most relevant property).\n"
    "2. FORBIDDEN: bare dictionary definitions such as 'X is a kind of Y' / 'X is a "
    "type of Z' with no functional, causal, locational, or purpose content.\n"
    "3. Facts must be generally true (decontextualized), not invented to fit this "
    "question, and must not reference the question text or answer.\n"
    "4. Keep each fact to one concise sentence.\n"
    "Output STRICT JSON only."
)


def build_prompt(question: str, concept: str, choices: List[Dict[str, str]]) -> str:
    return (
        f"Question: {question}\n"
        f"Key concept: {concept}\n"
        f"Options: {options_block(choices)}\n\n"
        "Output 1-2 JSON objects (2 at most, total) with keys:\n"
        '  "option_label": option letter (A-E) the fact is about,\n'
        '  "concept": the option text,\n'
        '  "dimension": one of '
        '["primary_function","used_for","capability","typical_location","cause",'
        '"effect","has_prerequisite","motivation","property","part_whole"],\n'
        '  "fact": one concise standalone commonsense sentence (no definitions, no '
        "reference to this question or its answer).\n"
        "Return a single JSON array of all objects. No extra text."
    )


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


def sanitize_facts(qid: int, choices: List[Dict[str, str]], parsed: Any) -> List[Dict[str, Any]]:
    valid_labels = {c["label"] for c in choices}
    facts: List[Dict[str, Any]] = []
    seen = set()
    if not isinstance(parsed, list):
        return facts
    per_option_counter: Dict[str, int] = {}
    for item in parsed:
        if len(facts) >= MAX_FACTS_PER_QUESTION:
            break
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


def rewrite_flat_kb() -> int:
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


def backup_existing() -> None:
    stamp = datetime.now().strftime("%Y-%m-%d-%H-%M-%S")
    for path in (QKB_PATH, FLAT_PATH):
        if os.path.exists(path):
            bak = f"{path}.{stamp}.bak"
            shutil.copy2(path, bak)
            print(f"[backup] {os.path.basename(path)} -> {os.path.basename(bak)}")


def generate_one(teacher: DeepSeekTeacher, questions: List[Dict[str, Any]], qid: int) -> Dict[str, Any]:
    entry = questions[qid]
    stem = entry["question"]["stem"]
    concept = entry["question"].get("question_concept", "")
    choices = [{"label": c["label"], "text": c["text"]} for c in entry["question"]["choices"]]
    last_err: Exception | None = None
    for attempt in range(3):
        try:
            raw = teacher.chat(GEN_SYSTEM, build_prompt(stem, concept, choices), max_new_tokens=400)
            facts = sanitize_facts(qid, choices, extract_json(raw))
            return {
                "question_id": qid,
                "question": stem,
                "question_concept": concept,
                "options": choices,
                "facts": facts,
            }
        except Exception as exc:  # network / API errors: retry with backoff
            last_err = exc
            time.sleep(2 * (attempt + 1))
    raise RuntimeError(f"qid={qid} failed after retries: {last_err}")


def main() -> None:
    parser = argparse.ArgumentParser(description="Extend v2 KB to the rest of the CSQA train split")
    parser.add_argument("--limit", type=int, default=0,
                        help="Only process the first N pending questions (0 = all)")
    parser.add_argument("--workers", type=int, default=4, help="Concurrent API calls")
    parser.add_argument("--no-backup", action="store_true", help="Skip backing up existing KB files")
    args = parser.parse_args()

    os.makedirs(OUT_DIR, exist_ok=True)
    questions = load_questions(os.path.abspath(DATA_PATH))
    excluded = eval_ids()
    all_rest = [qid for qid in range(len(questions)) if qid not in excluded]
    done_ids = load_done_ids(QKB_PATH)
    pending = [qid for qid in all_rest if qid not in done_ids]
    if args.limit > 0:
        pending = pending[: args.limit]

    print(f"total questions={len(questions)}  excluded(eval)={len(excluded)}  "
          f"rest={len(all_rest)}  already_done={len(all_rest) - len(pending) if args.limit == 0 else len(done_ids & set(all_rest))}  "
          f"pending_now={len(pending)}  workers={args.workers}")

    if not pending:
        total = rewrite_flat_kb()
        print(f"Nothing pending. Flat KB rebuilt: {total} facts -> {FLAT_PATH}")
        return

    if not args.no_backup:
        backup_existing()

    teacher = DeepSeekTeacher()
    lock = threading.Lock()
    written = 0
    failed: List[int] = []
    t0 = time.time()

    with open(QKB_PATH, "a", encoding="utf-8") as out, \
            ThreadPoolExecutor(max_workers=args.workers) as pool:
        futures = {pool.submit(generate_one, teacher, questions, qid): qid for qid in pending}
        for fut in as_completed(futures):
            qid = futures[fut]
            try:
                record = fut.result()
            except Exception as exc:
                failed.append(qid)
                print(f"[FAIL] qid={qid}: {exc}")
                continue
            with lock:
                out.write(json.dumps(record, ensure_ascii=False) + "\n")
                out.flush()
                written += 1
                if written % 25 == 0 or written == len(pending):
                    rate = written / max(time.time() - t0, 1e-9)
                    eta_min = (len(pending) - written) / max(rate, 1e-9) / 60
                    print(f"[{written}/{len(pending)}] qid={qid} facts={len(record['facts'])} "
                          f"rate={rate:.2f} q/s ETA={eta_min:.0f} min")

    total = rewrite_flat_kb()
    print(f"\nDone. New question packs written: {written}  failed: {len(failed)}")
    if failed:
        print(f"Failed qids (rerun the script to retry them): {sorted(failed)[:50]}"
              + (" ..." if len(failed) > 50 else ""))
    print(f"Flat retriever-compatible KB: {total} facts -> {FLAT_PATH}")


if __name__ == "__main__":
    main()
