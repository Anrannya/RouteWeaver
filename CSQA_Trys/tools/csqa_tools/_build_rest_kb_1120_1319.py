# -*- coding: utf-8 -*-
"""Build rest_kb_data_1120_1319.py from hand-authored chunk packs."""
from __future__ import annotations

import ast
import json
import os

DATA = os.path.abspath(
    os.path.join(os.path.dirname(__file__), "..", "..", "..", "Task_Datasets", "CSQA", "train_rand_split.jsonl")
)
OUT = os.path.join(os.path.dirname(__file__), "rest_kb_data_1120_1319.py")

ALLOWED = {
    "primary_function", "used_for", "capability", "typical_location", "cause",
    "effect", "has_prerequisite", "motivation", "property", "part_whole",
}

rows: list[dict] = []
with open(DATA, encoding="utf-8") as f:
    for line in f:
        if line.strip():
            rows.append(json.loads(line))

from _kb_chunk_1120_1169 import CHUNK as C1  # noqa: E402
from _kb_chunk_1170_1219 import CHUNK as C2  # noqa: E402
from _kb_chunk_1220_1269 import CHUNK as C3  # noqa: E402
from _kb_chunk_1270_1319 import CHUNK as C4  # noqa: E402

FACTS: dict[int, list[tuple[str, str, str]]] = {}
FACTS.update(C1)
FACTS.update(C2)
FACTS.update(C3)
FACTS.update(C4)


def validate() -> None:
    missing = [q for q in range(1120, 1320) if q not in FACTS]
    if missing:
        raise SystemExit(f"Missing qids: {missing[:10]} ... total {len(missing)}")
    for qid in range(1120, 1320):
        labels = {c["label"] for c in rows[qid]["question"]["choices"]}
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
        '"""Batch: hand-authored v2-style KB for qids 1120-1319 (200 questions, 5 facts each)."""',
        "",
        "KNOWLEDGE_REST_1120_1319 = {",
    ]
    for qid in range(1120, 1320):
        parts = []
        for label, dim, fact in FACTS[qid]:
            esc = fact.replace("\\", "\\\\").replace('"', '\\"')
            parts.append(f'("{label}", "{dim}", "{esc}")')
        lines.append(f"    {qid}: [{', '.join(parts)}],")
    lines.append("}")
    lines.append("")
    return "\n".join(lines)


def main() -> None:
    validate()
    content = render()
    with open(OUT, "w", encoding="utf-8") as f:
        f.write(content)
    d = ast.literal_eval(content.split("=", 1)[1].strip())
    print(f"path: {OUT}")
    print(f"qids: {len(d)}")
    print(f"facts: {sum(len(v) for v in d.values())}")


if __name__ == "__main__":
    main()
