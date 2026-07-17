#!/usr/bin/env python3
"""Validate rest KB batch modules for qids 4520-5519."""
from __future__ import annotations

import importlib
import sys
from pathlib import Path

TOOLS = Path(__file__).resolve().parent
sys.path.insert(0, str(TOOLS))

BATCHES = [
    (4520, 4619, "rest_kb_data_4520_4619", "KNOWLEDGE_REST_4520_4619"),
    (4620, 4719, "rest_kb_data_4620_4719", "KNOWLEDGE_REST_4620_4719"),
    (4720, 4819, "rest_kb_data_4720_4819", "KNOWLEDGE_REST_4720_4819"),
    (4820, 4919, "rest_kb_data_4820_4919", "KNOWLEDGE_REST_4820_4919"),
    (4920, 5019, "rest_kb_data_4920_5019", "KNOWLEDGE_REST_4920_5019"),
    (5020, 5119, "rest_kb_data_5020_5119", "KNOWLEDGE_REST_5020_5119"),
    (5120, 5219, "rest_kb_data_5120_5219", "KNOWLEDGE_REST_5120_5219"),
    (5220, 5319, "rest_kb_data_5220_5319", "KNOWLEDGE_REST_5220_5319"),
    (5320, 5419, "rest_kb_data_5320_5419", "KNOWLEDGE_REST_5320_5419"),
    (5420, 5519, "rest_kb_data_5420_5519", "KNOWLEDGE_REST_5420_5519"),
]

ALLOWED = {
    "primary_function", "used_for", "capability", "typical_location", "cause",
    "effect", "has_prerequisite", "motivation", "property", "part_whole",
}


def check_batch(start: int, end: int, mod_name: str, attr: str) -> tuple[bool, str]:
    path = TOOLS / f"{mod_name}.py"
    if not path.exists():
        return False, "missing"
    mod = importlib.import_module(mod_name)
    data = getattr(mod, attr)
    exp = end - start + 1
    if len(data) != exp:
        return False, f"count={len(data)} expected={exp}"
    for qid in range(start, end + 1):
        if qid not in data:
            return False, f"missing qid {qid}"
        facts = data[qid]
        if len(facts) != 5:
            return False, f"qid {qid} has {len(facts)} facts"
        labels = [f[0] for f in facts]
        if labels != ["A", "B", "C", "D", "E"]:
            return False, f"qid {qid} labels {labels}"
        for _label, dim, text in facts:
            if dim not in ALLOWED:
                return False, f"qid {qid} bad dim {dim}"
            if not text or not text.strip():
                return False, f"qid {qid} empty fact"
    return True, "ok"


def main() -> int:
    ok_n = 0
    for start, end, mod, attr in BATCHES:
        ok, msg = check_batch(start, end, mod, attr)
        print(f"{start}-{end}: {'OK' if ok else 'FAIL'} ({msg})")
        if ok:
            ok_n += 1
    print(f"ready: {ok_n}/{len(BATCHES)} batches")
    return 0 if ok_n == len(BATCHES) else 1


if __name__ == "__main__":
    raise SystemExit(main())
