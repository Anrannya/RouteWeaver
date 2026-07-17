#!/usr/bin/env python3
"""Append rest_kb_data imports and dict merges for qid range 5520-9740."""
from __future__ import annotations

from pathlib import Path

TOOLS = Path(__file__).resolve().parent
REST = TOOLS / "rest_kb_data.py"


def batches():
    start, end = 5520, 9740
    cur = start
    while cur <= end:
        hi = min(cur + 99, end)
        yield cur, hi
        cur = hi + 1


def main() -> None:
    text = REST.read_text(encoding="utf-8")
    imports = []
    merges = []
    for lo, hi in batches():
        mod = f"rest_kb_data_{lo}_{hi}"
        attr = f"KNOWLEDGE_REST_{lo}_{hi}"
        line = f"from {mod} import {attr}"
        if line not in text:
            imports.append(line)
        merge = f"    **{attr},"
        if merge not in text:
            merges.append(merge)

    if not imports and not merges:
        print("nothing to add")
        return

    if imports:
        anchor = "KNOWLEDGE_REST = {"
        idx = text.index(anchor)
        text = text[:idx] + "\n".join(imports) + "\n\n" + text[idx:]

    if merges:
        text = text.replace("\n}", "\n" + "\n".join(merges) + "\n}")

    REST.write_text(text, encoding="utf-8")
    print(f"added {len(imports)} imports, {len(merges)} merges")


if __name__ == "__main__":
    main()
