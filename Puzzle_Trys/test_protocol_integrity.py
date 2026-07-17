"""Offline DAG/model-alignment checks for the released P3 records."""

from __future__ import annotations

import json
import re
from pathlib import Path

from protocol import canonical_depths, model_for_step


ROOT = Path(__file__).resolve().parent


def check(path: Path) -> None:
    records = json.loads(path.read_text(encoding="utf-8"))
    for qid, record in records.items():
        depths = canonical_depths(record)
        order = [
            int(re.findall(r"\d+", step_id)[0])
            for depth in sorted(depths)
            for step_id in depths[depth]
        ]
        expected = sorted(int(step_id) for step_id in record["steps_dict"])
        assert sorted(order) == expected, f"{path.name} Q{qid}: incomplete DAG"
        assert len(order) == len(set(order)), f"{path.name} Q{qid}: duplicate step"
        assert len(record["allo_model"]) == len(expected), f"{path.name} Q{qid}: model count"
        for step_id in order:
            assert model_for_step(record, step_id)


if __name__ == "__main__":
    check(ROOT / "TmpRes" / "step2In_Puzzle_last.json")
    check(ROOT / "TmpRes" / "step2In_Puzzle_with_tool.json")
    print("PASS: all P3 records cover every DAG step with aligned model slots")
