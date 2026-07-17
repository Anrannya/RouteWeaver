# -*- coding: utf-8 -*-
"""Offline audit pipeline for CSQA commonsense knowledge base."""

from __future__ import annotations

import argparse
import json
import os
import random
import sys
import time
from collections import Counter
from datetime import datetime
from typing import Any, Dict, List

BASE_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
TOOLS_DIR = os.path.join(BASE_DIR, "tools", "csqa_tools")
sys.path.insert(0, TOOLS_DIR)

from csqa_kb_retriever import CSQAKBRetriever
from csqa_knowledge_validator import (
    MARGIN_THRESHOLD,
    TOP1_THRESHOLD,
    CSQAKnowledgeValidator,
)

DATA_PATH = os.path.join(BASE_DIR, "..", "Task_Datasets", "CSQA", "train_rand_split.jsonl")
LOG_ROOT = os.path.join(BASE_DIR, "Logs", "csqa_kb_audit")
RANDOM_SEED = 42


def load_csqa_questions(path: str) -> List[Dict[str, Any]]:
    questions: List[Dict[str, Any]] = []
    with open(path, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                questions.append(json.loads(line))
    return questions


def format_options(choices: List[Dict[str, str]]) -> List[Dict[str, str]]:
    return [{"label": c["label"], "text": c["text"]} for c in choices]


def select_question_ids(total: int, limit: int, run_index: int, runs: int) -> List[int]:
    limit = min(limit, total)
    if runs <= 1:
        return list(range(limit))
    rng = random.Random(RANDOM_SEED + run_index)
    return sorted(rng.sample(range(total), limit))


def audit_one_question(
    question_id: int,
    entry: Dict[str, Any],
    retriever: CSQAKBRetriever,
    validator: CSQAKnowledgeValidator,
) -> Dict[str, Any]:
    stem = entry["question"]["stem"]
    choices = format_options(entry["question"]["choices"])
    gold_answer = entry["answerKey"]

    candidates = retriever.retrieve(stem, choices)
    val_start = time.perf_counter()
    validation = validator.validate(stem, choices, candidates)
    validation_time_ms = (time.perf_counter() - val_start) * 1000.0

    audit_match = None
    if validation["status"] == "accepted":
        audit_match = validation["supported_option"] == gold_answer

    record = {
        "question_id": question_id,
        "question": stem,
        "options": choices,
        "retrieval_candidates": candidates,
        "validation_status": validation["status"],
        "validation_reason": validation.get("reason"),
        "fact_evaluations": validation.get("fact_evaluations", []),
        "evidence": None,
        "audit_answer_key": gold_answer,
        "audit_supported_option_correct": audit_match,
        "validation_time_ms": round(validation_time_ms, 3),
    }

    if validation["status"] == "accepted":
        record["evidence"] = {
            "status": "accepted",
            "supported_option": validation["supported_option"],
            "runner_up_option": validation["runner_up_option"],
            "supporting_facts": validation["supporting_facts"],
            "support_margin": validation["support_margin"],
        }
    else:
        record["evidence"] = {
            "status": "abstain",
            "reason": validation.get("reason", "no_uniquely_discriminative_knowledge"),
        }
        if validation.get("conflicting_options"):
            record["conflicting_options"] = validation["conflicting_options"]

    return record


def aggregate_run(records: List[Dict[str, Any]]) -> Dict[str, Any]:
    total = len(records)
    with_candidates = sum(1 for r in records if r["retrieval_candidates"])
    accepted = [r for r in records if r["validation_status"] == "accepted"]
    conflicts = [r for r in records if r.get("validation_reason") == "conflicting_supported_options"]
    accepted_correct = sum(1 for r in accepted if r["audit_supported_option_correct"])
    times = [r["validation_time_ms"] for r in records if "validation_time_ms" in r]

    return {
        "question_total": total,
        "retrieval_coverage": round(with_candidates / total, 4) if total else 0.0,
        "accepted_question_count": len(accepted),
        "accepted_coverage": round(len(accepted) / total, 4) if total else 0.0,
        "accepted_supported_option_accuracy": round(accepted_correct / len(accepted), 4) if accepted else 0.0,
        "conflicting_supported_options_count": len(conflicts),
        "online_validation_time_ms_avg": round(sum(times) / len(times), 3) if times else 0.0,
        "online_validation_time_ms_max": round(max(times), 3) if times else 0.0,
        "abstain_reason_counts": dict(Counter(
            r.get("validation_reason", "unknown")
            for r in records
            if r["validation_status"] == "abstain"
        )),
    }


def load_teacher_student_agreement() -> Any:
    metrics_path = os.path.join(BASE_DIR, "knowledge_base", "csqa_kb_v1", "validator", "metrics.json")
    if os.path.exists(metrics_path):
        with open(metrics_path, "r", encoding="utf-8") as f:
            return json.load(f).get("teacher_student_agreement")
    return None


def write_jsonl(path: str, rows: List[Dict[str, Any]]) -> None:
    with open(path, "w", encoding="utf-8") as f:
        for row in rows:
            f.write(json.dumps(row, ensure_ascii=False) + "\n")


def write_report(path: str, summary: Dict[str, Any], run_summaries: List[Dict[str, Any]]) -> None:
    lines = [
        "CSQA Knowledge Base Offline Audit Report",
        "=" * 44,
        f"Thresholds: top1 >= {TOP1_THRESHOLD}, margin >= {MARGIN_THRESHOLD}",
        "",
        "Overall Summary",
        f"- question_total: {summary['question_total']}",
        f"- retrieval_coverage: {summary['retrieval_coverage']}",
        f"- accepted_question_count: {summary['accepted_question_count']}",
        f"- accepted_coverage: {summary['accepted_coverage']}",
        f"- accepted_supported_option_accuracy: {summary['accepted_supported_option_accuracy']}",
        f"- conflicting_supported_options_count: {summary['conflicting_supported_options_count']}",
        f"- teacher_student_agreement: {summary.get('teacher_student_agreement')}",
        f"- online_validation_time_ms_avg: {summary['online_validation_time_ms_avg']}",
        f"- online_validation_time_ms_max: {summary['online_validation_time_ms_max']}",
        "",
        "Abstain Reasons",
    ]
    for reason, count in sorted(summary.get("abstain_reason_counts", {}).items()):
        lines.append(f"- {reason}: {count}")
    if len(run_summaries) > 1:
        lines.extend(["", "Per-run Summary"])
        for idx, run_summary in enumerate(run_summaries, start=1):
            lines.append(
                f"- run {idx}: accepted={run_summary['accepted_question_count']} "
                f"accuracy={run_summary['accepted_supported_option_accuracy']}"
            )
    with open(path, "w", encoding="utf-8") as f:
        f.write("\n".join(lines) + "\n")


def run_audit(limit: int, runs: int) -> str:
    random.seed(RANDOM_SEED)
    data_path = os.path.abspath(DATA_PATH)
    questions = load_csqa_questions(data_path)

    retriever = CSQAKBRetriever()
    validator = CSQAKnowledgeValidator()

    timestamp = datetime.now().strftime("%Y-%m-%d-%H-%M-%S")
    out_dir = os.path.join(LOG_ROOT, timestamp)
    os.makedirs(out_dir, exist_ok=True)

    all_records: List[Dict[str, Any]] = []
    run_summaries: List[Dict[str, Any]] = []

    for run_idx in range(runs):
        question_ids = select_question_ids(len(questions), limit, run_idx, runs)
        run_records: List[Dict[str, Any]] = []
        for qid in question_ids:
            record = audit_one_question(qid, questions[qid], retriever, validator)
            record["run_index"] = run_idx
            run_records.append(record)
            all_records.append(record)
        run_summaries.append(aggregate_run(run_records))

    summary = aggregate_run(all_records)
    summary["runs"] = runs
    summary["limit_per_run"] = limit
    summary["random_seed"] = RANDOM_SEED
    summary["thresholds"] = {
        "top1_threshold": TOP1_THRESHOLD,
        "margin_threshold": MARGIN_THRESHOLD,
    }
    summary["teacher_student_agreement"] = load_teacher_student_agreement()
    summary["run_summaries"] = run_summaries

    write_jsonl(os.path.join(out_dir, "details.jsonl"), all_records)
    write_jsonl(
        os.path.join(out_dir, "accepted.jsonl"),
        [r for r in all_records if r["validation_status"] == "accepted"],
    )
    write_jsonl(
        os.path.join(out_dir, "abstain.jsonl"),
        [r for r in all_records if r["validation_status"] == "abstain"],
    )
    write_jsonl(
        os.path.join(out_dir, "conflicts.jsonl"),
        [r for r in all_records if r.get("validation_reason") == "conflicting_supported_options"],
    )
    with open(os.path.join(out_dir, "summary.json"), "w", encoding="utf-8") as f:
        json.dump(summary, f, ensure_ascii=False, indent=2)
    write_report(os.path.join(out_dir, "report.txt"), summary, run_summaries)
    return out_dir


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Offline CSQA KB audit pipeline")
    parser.add_argument("--limit", type=int, default=100, help="Questions per run")
    parser.add_argument("--runs", type=int, default=1, help="Number of audit runs")
    return parser.parse_args()


if __name__ == "__main__":
    args = parse_args()
    output_dir = run_audit(limit=args.limit, runs=args.runs)
    print(f"Audit finished. Output directory: {output_dir}")
