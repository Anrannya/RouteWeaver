#!/usr/bin/env python3
"""Validate rest KB batch modules for qids 2520-3519."""
from __future__ import annotations

import importlib
import sys
from pathlib import Path

TOOLS = Path(__file__).resolve().parent
sys.path.insert(0, str(TOOLS))

BATCHES = [
    (2520, 2619, "rest_kb_data_2520_2619", "KNOWLEDGE_REST_2520_2619"),
    (2620, 2719, "rest_kb_data_2620_2719", "KNOWLEDGE_REST_2620_2719"),
    (2720, 2819, "rest_kb_data_2720_2819", "KNOWLEDGE_REST_2720_2819"),
    (2820, 2919, "rest_kb_data_2820_2919", "KNOWLEDGE_REST_2820_2919"),
    (2920, 3019, "rest_kb_data_2920_3019", "KNOWLEDGE_REST_2920_3019"),
    (3020, 3119, "rest_kb_data_3020_3119", "KNOWLEDGE_REST_3020_3119"),
    (3120, 3219, "rest_kb_data_3120_3219", "KNOWLEDGE_REST_3120_3219"),
    (3220, 3319, "rest_kb_data_3220_3319", "KNOWLEDGE_REST_3220_3319"),
    (3320, 3419, "rest_kb_data_3320_3419", "KNOWLEDGE_REST_3320_3419"),
    (3420, 3519, "rest_kb_data_3420_3519", "KNOWLEDGE_REST_3420_3519"),
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
