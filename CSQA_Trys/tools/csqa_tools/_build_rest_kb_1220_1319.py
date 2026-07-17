# -*- coding: utf-8 -*-
"""Build rest_kb_data_1220_1319.py from hand-authored fact chunks."""
from __future__ import annotations

import ast
import json
import os

DATA = os.path.abspath(
    os.path.join(os.path.dirname(__file__), "..", "..", "..", "Task_Datasets", "CSQA", "train_rand_split.jsonl")
)
OUT = os.path.join(os.path.dirname(__file__), "rest_kb_data_1220_1319.py")

ALLOWED = {
    "primary_function", "used_for", "capability", "typical_location", "cause",
    "effect", "has_prerequisite", "motivation", "property", "part_whole",
}

from _kb_chunk_1220_1269 import CHUNK as CHUNK_A  # noqa: E402
from _kb_chunk_1270_1319 import CHUNK as CHUNK_B  # noqa: E402

FACTS = {**CHUNK_A, **CHUNK_B}


def validate() -> None:
    rows = []
    with open(DATA, encoding="utf-8") as f:
        for line in f:
            if line.strip():
                rows.append(json.loads(line))

    missing = [q for q in range(1220, 1320) if q not in FACTS]
    if missing:
        raise SystemExit(f"Missing qids: {missing[:10]} ... total {len(missing)}")

    extra = [q for q in FACTS if q < 1220 or q > 1319]
    if extra:
        raise SystemExit(f"Extra qids outside range: {extra[:10]}")

    for qid in range(1220, 1320):
        entry = rows[qid]["question"]
        labels = {c["label"] for c in entry["choices"]}
        facts = FACTS[qid]
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


def render() -> str:
    lines = [
        "# -*- coding: utf-8 -*-",
        '"""Eval-style rest KB for qids 1220-1319 (100 questions, 5 facts each)."""',
        "",
        "KNOWLEDGE_REST_1220_1319 = {",
    ]
    for qid in range(1220, 1320):
        items = []
        for label, dim, fact in FACTS[qid]:
            esc = fact.replace("\\", "\\\\").replace('"', '\\"')
            items.append(f'("{label}", "{dim}", "{esc}")')
        lines.append(f"    {qid}: [{', '.join(items)}],")
    lines.append("}")
    lines.append("")
    return "\n".join(lines)


def main() -> None:
    validate()
    content = render()
    with open(OUT, "w", encoding="utf-8") as f:
        f.write(content)
    d = ast.literal_eval(content.split("=", 1)[1].strip())
    print(OUT)
    print(len(d))


if __name__ == "__main__":
    main()
