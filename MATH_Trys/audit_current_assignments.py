"""Audit the current, tightened MATH tool-assignment artifact.

This script is deterministic and makes no API calls.  It writes the exact
counts used by the paper to ``Logs/current_assignment_audit.md``.
"""

from __future__ import annotations

import json
from collections import Counter
from pathlib import Path

from tools import run_tool
from tools.validate_assignment import validate_assignment


ROOT = Path(__file__).resolve().parent
INPUT = ROOT / "TmpRes" / "step2In_MATH_with_tool.json"
OUTPUT = ROOT / "Logs" / "current_assignment_audit.md"


def main() -> None:
    records = json.loads(INPUT.read_text(encoding="utf-8"))
    mode_counts: Counter[str] = Counter()
    tool_counts: Counter[str] = Counter()
    granted_questions: set[str] = set()
    validation_failures: list[str] = []
    execution_failures: list[str] = []
    final_counts: Counter[str] = Counter()

    total_slots = 0
    for qid, record in records.items():
        for index, (tool, args, mode) in enumerate(
            zip(record["allo_tool"], record["tool_args"], record["tool_mode"]), start=1
        ):
            total_slots += 1
            if mode == "no_tool" or tool == "no_tool":
                continue
            granted_questions.add(qid)
            mode_counts[mode] += 1
            tool_counts[tool] += 1
            valid, reason = validate_assignment(
                record["steps_dict"][str(index)],
                tool,
                args,
                mode,
                all_steps=record["steps"],
                step_id=index,
                int_edges=record["int_edges"],
            )
            if not valid:
                validation_failures.append(f"Q{qid}/Step{index}: {tool}/{mode}: {reason}")
                continue
            result = run_tool(tool, args)
            if not result.get("success"):
                execution_failures.append(f"Q{qid}/Step{index}: {tool}/{mode}")

        final_tool = record.get("final_tool")
        if final_tool:
            granted_questions.add(qid)
            final_counts[final_tool["tool"]] += 1
            result = run_tool(final_tool["tool"], final_tool["args"])
            value = (
                result.get(final_tool.get("answer_key") or "result")
                or result.get("target_value")
                or result.get("value")
                or result.get("result")
            )
            if (
                not result.get("success")
                or not result.get("verified")
                or str(value) != str(final_tool["answer"])
            ):
                execution_failures.append(f"Q{qid}/final: {final_tool['tool']}")

    granted_slots = sum(mode_counts.values())
    lines = [
        "# Current MATH Tool-Assignment Audit",
        "",
        "Generated from `TmpRes/step2In_MATH_with_tool.json` by "
        "`audit_current_assignments.py`. This report supersedes the phase25 audit.",
        "",
        f"- Questions: **{len(records)}**",
        f"- Sub-task slots: **{total_slots}**",
        f"- Granted sub-task slots: **{granted_slots}** "
        f"({100 * granted_slots / total_slots:.1f}%)",
        f"- Questions with any sub-task or final tool: **{len(granted_questions)}**",
        f"- Runtime validation failures: **{len(validation_failures)}**",
        f"- Tool execution/reverification failures: **{len(execution_failures)}**",
        "",
        "## Sub-task integration modes",
        "",
        *[f"- `{mode}`: {count}" for mode, count in sorted(mode_counts.items())],
        "",
        "## Sub-task tools",
        "",
        *[f"- `{tool}`: {count}" for tool, count in sorted(tool_counts.items())],
        "",
        "## Verified final tools",
        "",
        *([f"- `{tool}`: {count}" for tool, count in sorted(final_counts.items())]
          or ["- None"]),
    ]
    if validation_failures:
        lines.extend(["", "## Validation failures", "", *[f"- {x}" for x in validation_failures]])
    if execution_failures:
        lines.extend(["", "## Execution failures", "", *[f"- {x}" for x in execution_failures]])
    OUTPUT.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(f"Wrote {OUTPUT}")


if __name__ == "__main__":
    main()
