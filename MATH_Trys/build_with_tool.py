# -*- coding: utf-8 -*-
"""
MATH 规则分配器：纯规则（关键字 + 公式抽取 + sympy 实测校验）为每个子任务分配本地工具。

与“模型分配 / Adapter 分配”的区别：
  本脚本完全不调用大模型，零成本、确定、可复现；分配出的工具还会被实地运行一次，
  只有工具能成功解析才真正分配，否则回退为 no_tool（高准确、保守）。

输入：TmpRes/step2In_MATH_last.json    （含 steps / int_edges 等，保持不动）
输出：TmpRes/step2In_MATH_with_tool.json（在原结构上新增 allo_tool / tool_args / tool_mode 三个对齐列表）
      tool_mode 取值：replace=工具结果覆盖该子任务答案（跳过该步 LLM）；assist=作提示注入、LLM 仍作答。

防泄漏（两类参数来源，均不可能泄漏后续答案或 gold）：
  1) 自包含工具（factor/expand/simplify/subst/arith/solve）：参数只取自“当前子任务自身文字”；
  2) 运行时依赖工具（aggregate）：分配阶段只记录“前驱子任务编号 from_steps”（由 int_edges 得到，
     严格是 DAG 上更早的步），其数值在运行阶段才从这些前驱答案里取——绝不取后续步、绝不读 gold。
  这套“仅前驱 + 运行时取值”借鉴自 baseline 的思路，但本实现只保留一个通用 aggregate 工具、
  且全部以 assist（提示）注入，刻意屏蔽了 baseline 中针对具体题目措辞/数字的硬编码规则（过拟合）。

可回滚：本脚本与 tools/ 均为新增文件，输出亦为新增 json；删除三者即可完全还原，不触碰原有代码。
运行：cd MATH_Trys && python build_with_tool.py
"""
import json
import os
import re
import sys
from collections import Counter

BASE = os.path.dirname(os.path.abspath(__file__))
sys.path.append(BASE)
from tools import run_tool
from tools.validate_assignment import validate_assignment

IN_PATH = os.path.join(BASE, "TmpRes/step2In_MATH_last.json")
OUT_PATH = os.path.join(BASE, "TmpRes/step2In_MATH_with_tool.json")
LOG_DIR = os.path.join(BASE, "Logs")
REJECT_JSON = os.path.join(LOG_DIR, "tool_assignment_rejections.json")
REJECT_MD = os.path.join(LOG_DIR, "tool_assignment_rejections.md")


def _clean(s):
    s = s.replace("\\left", "").replace("\\right", "")
    s = s.replace("\\cdot", "*").replace("\\times", "*")
    s = re.split(r"\\(?:geq|leq|ge|le|neq|gtr|less|approx)\b|[<>≤≥≠]", s)[0]
    s = re.sub(r"(\d+)\s*\\d?frac\{([^{}]*)\}\{([^{}]*)\}", r"(\1+(\2)/(\3))", s)
    s = re.sub(r"\\d?frac\{([^{}]*)\}\{([^{}]*)\}", r"((\1)/(\2))", s)
    s = s.replace("\\", "")
    return s.strip()


def _pieces(text):
    cands = []
    for pat in (r"\\\((.+?)\\\)", r"\\\[(.+?)\\\]", r"\$(.+?)\$"):
        cands += re.findall(pat, text, re.S)
    return [c for c in (_clean(x) for x in cands) if c]


_CONCEPT = ("formula", "relate", "which ", "how do", "how does", "how can", "why ",
            "explain", "define", " property", "rule for", "characteristic",
            "what form", "steps are needed", "steps do we", "steps to")
_SUBST_KW = ("value of", "evaluate", "compute", "calculate")
_SOLVE_KW = ("solve for", "roots of", "values of", "value of", "satisfy",
             "equal to zero", "set equal")


def _preds(step_id, int_edges):
    if not step_id or not int_edges:
        return []
    return sorted({int(a) for a, b in int_edges if int(b) == int(step_id)})


def _apply(subtask, step_id, int_edges, all_steps, mode, name, args, qid=None, rejections=None):
    """sympy 实测 + validate_assignment；不通过则降级 no_tool 并记录拒绝原因。"""
    if name == "no_tool":
        return "no_tool", "no_tool", {}
    ok, reason = validate_assignment(
        subtask, name, args, mode,
        all_steps=all_steps, step_id=step_id, int_edges=int_edges,
    )
    if not ok:
        if rejections is not None:
            rejections.append({
                "qid": qid,
                "step_id": step_id,
                "subtask": subtask[:240],
                "original_tool": name,
                "original_mode": mode,
                "original_args": args,
                "reason": reason,
            })
        return "no_tool", "no_tool", {}
    return mode, name, args


def assign(subtask, step_id=None, int_edges=None, all_steps=None, qid=None, rejections=None):
    low = subtask.lower()
    ps = _pieces(subtask)
    expr = max(ps, key=len) if ps else ""

    if (("factored form" in low) or ("factor the" in low)) \
            and expr and run_tool("factor", {"expression": expr})["success"]:
        return _apply(subtask, step_id, int_edges, all_steps, "replace", "factor",
                      {"expression": expr}, qid, rejections)

    if ("expand" in low or "expanded" in low) and expr and run_tool("expand", {"expression": expr})["success"]:
        direct = ("expanded form" in low) or ("expand the" in low)
        mode = "replace" if direct else "assist"
        return _apply(subtask, step_id, int_edges, all_steps, mode, "expand",
                      {"expression": expr}, qid, rejections)

    if ("simplify" in low or "simplified form" in low) and expr and run_tool("simplify", {"expression": expr})["success"]:
        return _apply(subtask, step_id, int_edges, all_steps, "assist", "simplify",
                      {"expression": expr}, qid, rejections)

    mof = re.search(r"(\d+(?:\.\d+)?)\s*(%)?\s+of\s+(\d+(?:\.\d+)?)", low)
    if mof:
        a, pct, b = mof.groups()
        e = f"{a}/100*{b}" if pct else f"{a}*{b}"
        if run_tool("arith", {"expression": e})["success"]:
            return _apply(subtask, step_id, int_edges, all_steps, "replace", "arith",
                          {"expression": e}, qid, rejections)
    mfrac = re.search(r"\bof\s+(\d+(?:\.\d+)?)", low)
    if mfrac and expr and "/" in expr:
        e = f"({expr})*{mfrac.group(1)}"
        if run_tool("arith", {"expression": e})["success"]:
            return _apply(subtask, step_id, int_edges, all_steps, "replace", "arith",
                          {"expression": e}, qid, rejections)

    if any(k in low for k in _SUBST_KW) and len(ps) >= 2:
        asg = [p for p in ps if "=" in p]
        tgt = [p for p in ps if "=" not in p]
        if len(tgt) == 1 and asg:
            subs = {}
            ok = True
            for a in asg:
                l, r = a.split("=", 1)
                if not l.strip() or not r.strip():
                    ok = False
                    break
                subs[l.strip()] = r.strip()
            if ok:
                args = {"expression": tgt[0], "subs": subs}
                if run_tool("subst", args)["success"]:
                    return _apply(subtask, step_id, int_edges, all_steps, "replace", "subst",
                                  args, qid, rejections)

    if expr and any(c in expr for c in "+-*/^") and not re.search(r"\bof\s+\d", low) \
            and run_tool("arith", {"expression": expr})["success"]:
        return _apply(subtask, step_id, int_edges, all_steps, "replace", "arith",
                      {"expression": expr}, qid, rejections)

    if any(k in low for k in _SOLVE_KW) and not any(c in low for c in _CONCEPT) \
            and " when " not in low and " at " not in low and "given in" not in low \
            and "=" in expr:
        args = {"equation": expr}
        if run_tool("solve", args)["success"]:
            return _apply(subtask, step_id, int_edges, all_steps, "assist", "solve",
                          args, qid, rejections)

    # aggregate：规则仍可匹配，但 validate_assignment 会因无 verified 前驱值而拒绝
    preds = _preds(step_id, int_edges)
    if len(preds) >= 2:
        if "positive difference" in low or "difference between" in low:
            op = "positive_difference"
        elif "sum of" in low or "sum these" in low or "add " in low:
            op = "sum"
        elif "product of" in low or "multiply" in low:
            op = "product"
        else:
            op = None
        if op and (op != "positive_difference" or len(preds) == 2):
            fs = preds[:2] if op == "positive_difference" else preds
            args = {"operation": op, "from_steps": fs}
            return _apply(subtask, step_id, int_edges, all_steps, "assist", "aggregate",
                          args, qid, rejections)

    return "no_tool", "no_tool", {}


def _check_question(qid, steps, tools, targs, modes):
    """逐项一致性检查；不一致则抛 AssertionError。"""
    assert len(steps) == len(tools), f"Q{qid} steps/allo_tool 长度不一致"
    assert len(steps) == len(targs), f"Q{qid} steps/tool_args 长度不一致"
    assert len(steps) == len(modes), f"Q{qid} steps/tool_mode 长度不一致"
    for tool, args, mode in zip(tools, targs, modes):
        if tool == "no_tool":
            assert mode == "no_tool", f"Q{qid} no_tool 但 mode={mode}"
            assert args == {}, f"Q{qid} no_tool 但 args 非空"
        else:
            assert mode in {"replace", "assist"}, f"Q{qid} 非法 mode={mode} tool={tool}"


def _write_rejection_logs(rejections):
    os.makedirs(LOG_DIR, exist_ok=True)
    with open(REJECT_JSON, "w", encoding="utf-8") as f:
        json.dump(rejections, f, ensure_ascii=False, indent=2)
    by_reason = Counter(r["reason"] for r in rejections)
    by_tool = Counter(r["original_tool"] for r in rejections)
    lines = [
        "# 工具分配拒绝记录",
        "",
        f"总计: {len(rejections)} 条",
        "",
        "## 按原因",
    ]
    for reason, cnt in by_reason.most_common():
        lines.append(f"- {reason}: {cnt}")
    lines += ["", "## 按原工具", ""]
    for tool, cnt in by_tool.most_common():
        lines.append(f"- {tool}: {cnt}")
    lines += ["", "## 明细", ""]
    for r in rejections:
        lines.append(
            f"- Q{r['qid']} Step{r['step_id']} | {r['original_tool']}({r['original_mode']}) "
            f"| {r['reason']}"
        )
        lines.append(f"  subtask: {r['subtask'][:120]}")
    with open(REJECT_MD, "w", encoding="utf-8") as f:
        f.write("\n".join(lines) + "\n")


def main():
    data = json.load(open(IN_PATH, encoding="utf-8"))
    rejections = []
    tool_stat = Counter()
    mode_stat = Counter()
    len_mismatch = 0
    illegal_mode = 0
    total_subtasks = 0

    for qid, q in data.items():
        tools, targs, modes = [], [], []
        steps = q["steps"]
        int_edges = q.get("int_edges", [])
        qid_int = int(qid)
        for i, s in enumerate(steps, start=1):
            mode, name, args = assign(s, i, int_edges, all_steps=steps,
                                      qid=qid_int, rejections=rejections)
            tools.append(name)
            targs.append(args)
            modes.append(mode)
            tool_stat[name] += 1
            mode_stat[mode] += 1
        try:
            _check_question(qid_int, steps, tools, targs, modes)
        except AssertionError:
            len_mismatch += 1
            raise
        q["allo_tool"] = tools
        q["tool_args"] = targs
        q["tool_mode"] = modes
        total_subtasks += len(steps)

    json.dump(data, open(OUT_PATH, "w", encoding="utf-8"), ensure_ascii=False, indent=2)
    _write_rejection_logs(rejections)

    no_tool_n = tool_stat["no_tool"]
    non_no_tool = total_subtasks - no_tool_n
    replace_n = mode_stat["replace"]
    assist_n = mode_stat["assist"]
    aggregate_n = tool_stat["aggregate"]
    illegal_mode = sum(
        1 for q in data.values()
        for m, t in zip(q["tool_mode"], q["allo_tool"])
        if t != "no_tool" and m not in {"replace", "assist"}
    )

    print("分配完成 ->", OUT_PATH)
    print("拒绝记录 ->", REJECT_JSON)
    print("--- 统计 ---")
    print(f"总题数: {len(data)}")
    print(f"总子任务数: {total_subtasks}")
    print(f"no_tool 数: {no_tool_n}")
    print(f"非 no_tool 数: {non_no_tool}")
    print(f"replace 数: {replace_n}")
    print(f"assist 数: {assist_n}")
    print(f"aggregate 数: {aggregate_n}")
    print(f"非法 mode 数: {illegal_mode}")
    print(f"数组长度不一致题数: {len_mismatch}")
    print(f"拒绝分配数: {len(rejections)}")

    assert illegal_mode == 0, f"非法 mode 数={illegal_mode}"
    assert len_mismatch == 0
    assert aggregate_n == 0, f"aggregate 数={aggregate_n}"
    assert non_no_tool == replace_n + assist_n, (
        f"非 no_tool({non_no_tool}) != replace({replace_n})+assist({assist_n})"
    )


if __name__ == "__main__":
    main()
