"""Offline checks for the CSQA DoT execution protocol.

Run from the repository root:
    python CSQA_Trys/test_protocol_integrity.py

This test never calls an LLM.  It verifies that every DAG layer is included
and that one-based ``Step k`` identifiers map to zero-based model slots.
"""

from __future__ import annotations

import json
import re
from pathlib import Path

from protocol import canonical_depths, model_for_step


ROOT = Path(__file__).resolve().parent
DAG_PATH = ROOT / "TmpRes" / "step2In_csqa_last.json"


def solve_order(record: dict) -> list[int]:
    depths = canonical_depths(record)
    return [
        int(re.findall(r"\d+", step_id)[0])
        for depth in sorted(depths)
        for step_id in sorted(depths[depth])
    ]


def test_all_records_cover_every_step_and_model_slot() -> None:
    records = json.loads(DAG_PATH.read_text(encoding="utf-8"))
    assert records, "CSQA DAG file is empty"

    for qid, record in records.items():
        order = solve_order(record)
        expected = sorted(int(step_id) for step_id in record["steps_dict"])
        assert sorted(order) == expected, f"Q{qid}: DAG does not cover every step"
        assert len(order) == len(set(order)), f"Q{qid}: duplicate DAG step"
        assert len(record["allo_model"]) == len(expected), f"Q{qid}: model count mismatch"
        for step_id in order:
            assert model_for_step(record, step_id), f"Q{qid}: empty model for Step {step_id}"


if __name__ == "__main__":
    test_all_records_cover_every_step_and_model_slot()
    print("PASS: all CSQA records cover every DAG step with aligned model slots")
