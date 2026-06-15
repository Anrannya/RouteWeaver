# -*- coding: utf-8 -*-
"""生成阶段2.7固定50题分层验证集（纯离线，不调用LLM）。"""
import json
import os
import random
import subprocess
import sys
from collections import Counter

BASE = os.path.dirname(os.path.abspath(__file__))
SOURCE = os.path.join(BASE, "TmpRes/step2In_MATH_with_tool.json")
OUT_QIDS = os.path.join(BASE, "TmpRes/phase27_qids.json")
OUT_DETAIL = os.path.join(BASE, "TmpRes/phase27_qids_detail.json")

EXCLUDED = [59, 70, 74, 126, 131, 132, 162, 170, 173, 191]
SEED = 42
TARGET = 50


def git_head():
    try:
        return subprocess.check_output(
            ["git", "rev-parse", "HEAD"], cwd=os.path.dirname(BASE),
            stderr=subprocess.DEVNULL, text=True,
        ).strip()
    except Exception:
        return None


def classify(data):
    excluded_set = set(EXCLUDED)
    tool_q, no_q = [], []
    for qid_str in data:
        qid = int(qid_str)
        if qid in excluded_set:
            continue
        tools = data[qid_str].get("allo_tool", [])
        if any(t != "no_tool" for t in tools):
            tool_q.append(qid)
        else:
            no_q.append(qid)
    tool_q.sort()
    no_q.sort()
    return tool_q, no_q


def select(tool_q, no_q):
    rng = random.Random(SEED)
    if len(tool_q) >= TARGET:
        selected_tool = sorted(rng.sample(tool_q, TARGET))
        selected_no = []
    else:
        selected_tool = list(tool_q)
        need = TARGET - len(selected_tool)
        if need > len(no_q):
            raise RuntimeError(f"无工具题不足: 需要{need}, 可用{len(no_q)}")
        selected_no = sorted(rng.sample(no_q, need))
    selected_all = sorted(selected_tool + selected_no)
    return selected_tool, selected_no, selected_all


def slot_stats(data, qids):
    c = Counter()
    for qid in qids:
        rec = data[str(qid)]
        for tool, mode in zip(rec.get("allo_tool", []), rec.get("tool_mode", [])):
            if tool == "no_tool":
                continue
            c["non_no_tool_slots"] += 1
            c[f"tool_{tool}"] += 1
            c[f"mode_{mode}"] += 1
    return dict(c)


def validate(data, selected_tool, selected_no, selected_all):
    errors = []
    if len(selected_all) != TARGET:
        errors.append(f"总题数={len(selected_all)}, 期望{TARGET}")
    if len(set(selected_all)) != len(selected_all):
        errors.append("题号重复")
    missing = [q for q in selected_all if str(q) not in data]
    if missing:
        errors.append(f"题号不在JSON: {missing[:5]}")
    overlap_ex = set(selected_all) & set(EXCLUDED)
    if overlap_ex:
        errors.append(f"包含开发题: {sorted(overlap_ex)}")
    for q in selected_tool:
        tools = data[str(q)].get("allo_tool", [])
        if not any(t != "no_tool" for t in tools):
            errors.append(f"selected_tool Q{q} 无工具")
    for q in selected_no:
        tools = data[str(q)].get("allo_tool", [])
        if any(t != "no_tool" for t in tools):
            errors.append(f"selected_no_tool Q{q} 含工具")
    inter = set(selected_tool) & set(selected_no)
    if inter:
        errors.append(f"tool/no_tool 交集: {inter}")
    if set(selected_tool) | set(selected_no) != set(selected_all):
        errors.append("两类并集不等于 selected_all")
    return errors


def main():
    data = json.load(open(SOURCE, encoding="utf-8"))
    avail_tool, avail_no = classify(data)
    selected_tool, selected_no, selected_all = select(avail_tool, avail_no)
    errors = validate(data, selected_tool, selected_no, selected_all)
    if errors:
        print("校验失败:", errors, file=sys.stderr)
        sys.exit(1)

    stats = slot_stats(data, selected_all)
    detail = {
        "source_file": "TmpRes/step2In_MATH_with_tool.json",
        "git_head": git_head(),
        "seed": SEED,
        "target_size": TARGET,
        "excluded_development_qids": sorted(EXCLUDED),
        "remaining_total": len(avail_tool) + len(avail_no),
        "available_tool_qids": avail_tool,
        "available_no_tool_qids": avail_no,
        "available_tool_count": len(avail_tool),
        "available_no_tool_count": len(avail_no),
        "selected_tool_qids": selected_tool,
        "selected_no_tool_qids": selected_no,
        "selected_all_qids": selected_all,
        "tool_question_count": len(selected_tool),
        "no_tool_question_count": len(selected_no),
        "slot_stats": stats,
        "validation_passed": True,
    }
    json.dump(selected_all, open(OUT_QIDS, "w", encoding="utf-8"), indent=2)
    json.dump(detail, open(OUT_DETAIL, "w", encoding="utf-8"), ensure_ascii=False, indent=2)

    print("生成完成")
    print(f"剩余工具覆盖题: {len(avail_tool)}")
    print(f"剩余无工具题: {len(avail_no)}")
    print(f"选入工具题: {len(selected_tool)}")
    print(f"选入无工具题: {len(selected_no)}")
    print(f"50题: {selected_all}")
    print(f"校验: 通过")
    print(f"输出: {OUT_QIDS}")
    print(f"       {OUT_DETAIL}")


if __name__ == "__main__":
    main()
