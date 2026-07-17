#!/usr/bin/env python3
"""Validate rest KB batch modules for qids 3520-4519."""
from __future__ import annotations

import importlib
import sys
from pathlib import Path

TOOLS = Path(__file__).resolve().parent
sys.path.insert(0, str(TOOLS))

BATCHES = [
    (3520, 3619, "rest_kb_data_3520_3619", "KNOWLEDGE_REST_3520_3619"),
    (3620, 3719, "rest_kb_data_3620_3719", "KNOWLEDGE_REST_3620_3719"),
    (3720, 3819, "rest_kb_data_3720_3819", "KNOWLEDGE_REST_3720_3819"),
    (3820, 3919, "rest_kb_data_3820_3919", "KNOWLEDGE_REST_3820_3919"),
    (3920, 4019, "rest_kb_data_3920_4019", "KNOWLEDGE_REST_3920_4019"),
    (4020, 4119, "rest_kb_data_4020_4119", "KNOWLEDGE_REST_4020_4119"),
    (4120, 4219, "rest_kb_data_4120_4219", "KNOWLEDGE_REST_4120_4219"),
    (4220, 4319, "rest_kb_data_4220_4319", "KNOWLEDGE_REST_4220_4319"),
    (4320, 4419, "rest_kb_data_4320_4419", "KNOWLEDGE_REST_4320_4419"),
    (4420, 4519, "rest_kb_data_4420_4519", "KNOWLEDGE_REST_4420_4519"),
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
