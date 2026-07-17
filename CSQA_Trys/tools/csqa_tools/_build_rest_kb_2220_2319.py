# -*- coding: utf-8 -*-
"""Build rest_kb_data_2220_2319.py from hand-authored fact chunks."""
from __future__ import annotations

import ast
import importlib.util
import json
import os

TOOLS = os.path.dirname(os.path.abspath(__file__))
DATA = os.path.abspath(
    os.path.join(TOOLS, "..", "..", "..", "Task_Datasets", "CSQA", "train_rand_split.jsonl")
)
OUT = os.path.join(TOOLS, "rest_kb_data_2220_2319.py")
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

    missing = [q for q in range(2220, 2320) if q not in hand]
    if missing:
        raise SystemExit(f"Missing qids: {missing[:10]} ... total {len(missing)}")

    extra = [q for q in hand if q < 2220 or q > 2319]
    if extra:
        raise SystemExit(f"Extra qids outside range: {extra[:10]}")

    for qid in range(2220, 2320):
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


def render(hand: dict) -> str:
    lines = [
        "# -*- coding: utf-8 -*-",
        '"""Eval-style rest KB for qids 2220-2319 (100 questions, 5 facts each)."""',
        "",
        "KNOWLEDGE_REST_2220_2319 = {",
    ]
    for qid in range(2220, 2320):
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
    chunk_paths = [
        os.path.join(TOOLS, "_kb_hand_2220_2269.py"),
        os.path.join(TOOLS, "_kb_hand_2270_2319.py"),
    ]
    for path in chunk_paths:
        if not os.path.exists(path):
            raise SystemExit(f"Missing chunk: {path}")
        chunk = load_hand(path)
        overlap = set(hand) & set(chunk)
        if overlap:
            raise SystemExit(f"Overlap in {path}: {sorted(overlap)[:5]}")
        hand.update(chunk)

    validate(hand)
    content = render(hand)
    with open(OUT, "w", encoding="utf-8") as f:
        f.write(content)
    d = ast.literal_eval(content.split("=", 1)[1].strip())
    print(f"path: {OUT}")
    print(f"qids: {len(d)}")
    print(f"facts: {sum(len(v) for v in d.values())}")


if __name__ == "__main__":
    main()
