#!/usr/bin/env python3
"""Validate 1-fact rest KB modules for qids 5520-9740."""
from __future__ import annotations

import importlib
import sys
from pathlib import Path

TOOLS = Path(__file__).resolve().parent
sys.path.insert(0, str(TOOLS))

ALLOWED = {
    "primary_function", "used_for", "capability", "typical_location", "cause",
    "effect", "has_prerequisite", "motivation", "property", "part_whole",
}


def batches():
    start = 5520
    end = 9740
    cur = start
    while cur <= end:
        hi = min(cur + 99, end)
        mod = f"rest_kb_data_{cur}_{hi}"
        attr = f"KNOWLEDGE_REST_{cur}_{hi}"
        yield cur, hi, mod, attr
        cur = hi + 1


def check_batch(start: int, end: int, mod_name: str, attr: str) -> tuple[bool, str]:
    path = TOOLS / f"{mod_name}.py"
    if not path.exists():
        return False, "missing"
    mod = importlib.import_module(mod_name)
    if mod_name in sys.modules:
        del sys.modules[mod_name]
    data = getattr(mod, attr)
    exp = end - start + 1
    if len(data) != exp:
        return False, f"count={len(data)} expected={exp}"
    for qid in range(start, end + 1):
        if qid not in data:
            return False, f"missing qid {qid}"
        facts = data[qid]
        if len(facts) != 1:
            return False, f"qid {qid} has {len(facts)} facts (want 1)"
        label, dim, text = facts[0]
        if label not in {"A", "B", "C", "D", "E"}:
            return False, f"qid {qid} bad label {label}"
        if dim not in ALLOWED:
            return False, f"qid {qid} bad dim {dim}"
        if not text or not text.strip():
            return False, f"qid {qid} empty fact"
    return True, "ok"


def main() -> int:
    ok_n = 0
    total = 0
    missing = []
    for start, end, mod, attr in batches():
        total += 1
        ok, msg = check_batch(start, end, mod, attr)
        if not ok:
            missing.append(f"{start}-{end}")
        else:
            ok_n += 1
    print(f"ready: {ok_n}/{total} batches")
    if missing:
        print("missing/fail:", ", ".join(missing[:20]), ("..." if len(missing) > 20 else ""))
    return 0 if ok_n == total else 1


if __name__ == "__main__":
    raise SystemExit(main())
