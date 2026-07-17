# -*- coding: utf-8 -*-
"""Build rest_kb_data_5020_5119.py from hand-authored fact chunks."""
from __future__ import annotations

import importlib.util
import json
import os
import sys

TOOLS = os.path.dirname(os.path.abspath(__file__))
DATA = os.path.abspath(
    os.path.join(TOOLS, "..", "..", "..", "Task_Datasets", "CSQA", "train_rand_split.jsonl")
)
OUT = os.path.join(TOOLS, "rest_kb_data_5020_5119.py")
CHUNKS = [
    os.path.join(TOOLS, "_kb_chunk_5020_5069.py"),
    os.path.join(TOOLS, "_kb_chunk_5070_5119.py"),
]
ALLOWED = {
    "primary_function", "used_for", "capability", "typical_location", "cause",
    "effect", "has_prerequisite", "motivation", "property", "part_whole",
}


def load_hand(path: str) -> dict:
    spec = importlib.util.spec_from_file_location("chunk", path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod.HAND


def validate(hand: dict) -> None:
    rows = []
    with open(DATA, encoding="utf-8") as f:
        for line in f:
            if line.strip():
                rows.append(json.loads(line))

    missing = [q for q in range(5020, 5120) if q not in hand]
    if missing:
        raise SystemExit(f"Missing qids: {missing[:10]} ... total {len(missing)}")

    extra = [q for q in hand if q < 5020 or q > 5119]
    if extra:
        raise SystemExit(f"Extra qids outside range: {extra[:10]}")

    for qid in range(5020, 5120):
        entry = rows[qid]["question"]
        labels = {c["label"] for c in entry["choices"]}
        facts = hand[qid]
        if len(facts) != 5:
            raise SystemExit(f"Q{qid}: expected 5 facts, got {len(facts)}")
        seen = set()
        for label, dim, fact in facts:
            if label not in labels:
                raise SystemExit(f"Q{qid}: bad label {label}")
            if dim not in ALLOWED:
                raise SystemExit(f"Q{qid}: bad dimension {dim}")
            if len(fact.strip()) < 8:
                raise SystemExit(f"Q{qid}: fact too short: {fact!r}")
            if label in seen:
                raise SystemExit(f"Q{qid}: duplicate label {label}")
            seen.add(label)
        if sorted(seen) != ["A", "B", "C", "D", "E"]:
            raise SystemExit(f"Q{qid}: labels not A-E: {sorted(seen)}")


def render(hand: dict) -> str:
    lines = [
        "# -*- coding: utf-8 -*-",
        '"""Eval-style rest KB for qids 5020-5119 (100 questions, 5 facts each)."""',
        "",
        "KNOWLEDGE_REST_5020_5119 = {",
    ]
    for qid in range(5020, 5120):
        parts = []
        for label, dim, fact in hand[qid]:
            esc = fact.replace("\\", "\\\\").replace('"', '\\"')
            parts.append(f'("{label}", "{dim}", "{esc}")')
        lines.append(f"    {qid}: [{', '.join(parts)}],")
    lines.append("}")
    lines.append("")
    return "\n".join(lines)


def main() -> None:
    hand: dict = {}
    for path in CHUNKS:
        hand.update(load_hand(path))
    validate(hand)
    with open(OUT, "w", encoding="utf-8") as f:
        f.write(render(hand))
    print(f"Wrote {OUT}")
    print(f"entries={len(hand)} facts={sum(len(v) for v in hand.values())}")


if __name__ == "__main__":
    main()
