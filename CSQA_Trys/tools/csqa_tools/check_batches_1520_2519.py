#!/usr/bin/env python3
"""Validate and report rest KB batch modules for qids 1520-2519."""
from __future__ import annotations

import importlib
import sys
from pathlib import Path

TOOLS = Path(__file__).resolve().parent
sys.path.insert(0, str(TOOLS))

BATCHES = [
    (1520, 1619, "rest_kb_data_1520_1619", "KNOWLEDGE_REST_1520_1619"),
    (1620, 1719, "rest_kb_data_1620_1719", "KNOWLEDGE_REST_1620_1719"),
    (1720, 1819, "rest_kb_data_1720_1819", "KNOWLEDGE_REST_1720_1819"),
    (1820, 1919, "rest_kb_data_1820_1919", "KNOWLEDGE_REST_1820_1919"),
    (1920, 2019, "rest_kb_data_1920_2019", "KNOWLEDGE_REST_1920_2019"),
    (2020, 2119, "rest_kb_data_2020_2119", "KNOWLEDGE_REST_2020_2119"),
    (2120, 2219, "rest_kb_data_2120_2219", "KNOWLEDGE_REST_2120_2219"),
    (2220, 2319, "rest_kb_data_2220_2319", "KNOWLEDGE_REST_2220_2319"),
    (2320, 2419, "rest_kb_data_2320_2419", "KNOWLEDGE_REST_2320_2419"),
    (2420, 2519, "rest_kb_data_2420_2519", "KNOWLEDGE_REST_2420_2519"),
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
        for label, dim, text in facts:
            if dim not in ALLOWED:
                return False, f"qid {qid} bad dim {dim}"
            if not text or not text.strip():
                return False, f"qid {qid} empty fact"
    return True, "ok"


def main() -> int:
    ok_n = 0
    for start, end, mod, attr in BATCHES:
        ok, msg = check_batch(start, end, mod, attr)
        status = "OK" if ok else "FAIL"
        print(f"{start}-{end}: {status} ({msg})")
        if ok:
            ok_n += 1
    print(f"ready: {ok_n}/{len(BATCHES)} batches")
    return 0 if ok_n == len(BATCHES) else 1


if __name__ == "__main__":
    raise SystemExit(main())
