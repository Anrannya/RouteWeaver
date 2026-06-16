# -*- coding: utf-8 -*-
"""Phase 2.8 静态对比 phase27 验证集工具分配变化（不调用 API）"""
import json
import os

BASE = os.path.dirname(os.path.abspath(__file__))
BEFORE = os.path.join(BASE, "TmpRes/phase28_with_tool_before.json")
AFTER = os.path.join(BASE, "TmpRes/step2In_MATH_with_tool.json")
QIDS_PATH = os.path.join(BASE, "TmpRes/phase27_qids.json")
OUT = os.path.join(BASE, "Logs/phase28_slot_diff.json")


def _slots(data, qid):
    q = data[str(qid)]
    out = []
    for i, (t, m, a) in enumerate(zip(q["allo_tool"], q["tool_mode"], q["tool_args"]), start=1):
        if t != "no_tool":
            out.append({"step": i, "subtask": q["steps"][i - 1], "tool": t, "mode": m, "args": a})
    return out


def main():
    qids = json.load(open(QIDS_PATH))
    before = json.load(open(BEFORE))
    after = json.load(open(AFTER))
    before_n = after_n = 0
    added, removed, mode_changes, affected = [], [], [], set()
    focus = {26, 36, 44, 72, 118, 130, 179, 190}

    for qid in qids:
        bs = {(s["step"], s["tool"], s["mode"]): s for s in _slots(before, qid)}
        as_ = {(s["step"], s["tool"], s["mode"]): s for s in _slots(after, qid)}
        before_n += len(bs)
        after_n += len(as_)
        bkeys, akeys = set(bs), set(as_)
        for k in akeys - bkeys:
            added.append({"qid": qid, **as_[k]})
            affected.add(qid)
        for k in bkeys - akeys:
            removed.append({"qid": qid, **bs[k]})
            affected.add(qid)
        for k in bkeys & akeys:
            if bs[k]["args"] != as_[k]["args"]:
                mode_changes.append({"qid": qid, "step": k[0], "before": bs[k], "after": as_[k]})
                affected.add(qid)

    report = {
        "before_tool_slots": before_n,
        "after_tool_slots": after_n,
        "added_assignments": len(added),
        "removed_assignments": len(removed),
        "mode_or_args_changes": len(mode_changes),
        "affected_qids": sorted(affected),
        "focus_qids": {str(q): {
            "before": _slots(before, q),
            "after": _slots(after, q),
        } for q in sorted(focus)},
        "added_detail": added,
        "removed_detail": removed,
        "changes_detail": mode_changes,
    }
    os.makedirs(os.path.dirname(OUT), exist_ok=True)
    json.dump(report, open(OUT, "w", encoding="utf-8"), ensure_ascii=False, indent=2)
    print(json.dumps({k: report[k] for k in report if k != "added_detail" and k != "removed_detail"
                      and k != "changes_detail" and k != "focus_qids"}, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
