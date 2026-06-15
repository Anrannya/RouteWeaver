# -*- coding: utf-8 -*-
"""
MATH 规则分配器：纯规则 + sympy 实测 + validate_assignment。
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
from tools.target_utils import (
    complex_key,
    complex_step_role,
    check_assist_scope_match,
    check_replace_target_match,
    extract_requested_target,
    infer_solve_variable,
    is_root_derived_target,
    is_strict_solve_subtask,
    semantic_gate,
    should_use_linear_system,
    should_use_subst,
    wants_all_system_variables,
)

IN_PATH = os.path.join(BASE, "TmpRes/step2In_MATH_last.json")
OUT_PATH = os.path.join(BASE, "TmpRes/step2In_MATH_with_tool.json")
LOG_DIR = os.path.join(BASE, "Logs")
REJECT_JSON = os.path.join(LOG_DIR, "tool_assignment_rejections.json")
REJECT_MD = os.path.join(LOG_DIR, "tool_assignment_rejections.md")
AUDIT_JSON = os.path.join(LOG_DIR, "phase25_assignment_audit.json")
AUDIT_MD = os.path.join(LOG_DIR, "phase25_assignment_audit.md")

_CONCEPT = ("formula", "relate", "which ", "how do", "how does", "how can", "why ",
            "explain", "define", " property", "rule for", "characteristic",
            "what form", "steps are needed", "steps do we", "steps to")
_PLURAL_ROOT_KW = ("roots", "all possible values", "solutions of", "sum of the roots", "sum of roots")


def _clean(s):
    s = s.replace("\\left", "").replace("\\right", "")
    s = s.replace("\\cdot", "*").replace("\\times", "*")
    s = re.split(r"\\(?:geq|leq|ge|le|neq|gtr|less|approx)\b|[<>≤≥≠]", s)[0]
    s = re.sub(r"(\d+)\s*\\d?frac\{([^{}]*)\}\{([^{}]*)\}", r"(\1+(\2)/(\3))", s)
    s = re.sub(r"\\d?frac\{([^{}]*)\}\{([^{}]*)\}", r"((\1)/(\2))", s)
    s = s.replace("\\", "")
    return s.strip()


def _pieces(text):
    if not text:
        return []
    cands = []
    for pat in (r"\\\((.+?)\\\)", r"\\\[(.+?)\\\]", r"\$(.+?)\$"):
        cands += re.findall(pat, text, re.S)
    return [c for c in (_clean(x) for x in cands) if c]


def _extract_complex_expr(text):
    if not text or "i" not in text.lower():
        return None
    for p in _pieces(text):
        if "i" in p.lower() and re.search(r"\)\s*[\(*]?\s*\(", p.replace(" ", "")):
            return p
        if "i" in p.lower() and "*" in p:
            return p
    m = re.search(r"\([^)]*[iI][^)]*\)\s*[\*×]?\s*\([^)]*[iI][^)]*\)", text)
    return _clean(m.group(0)) if m else None


def _skip_partial_foil_arith(subtask, problem_text):
    if not problem_text or not _extract_complex_expr(problem_text):
        return False
    if _extract_complex_expr(subtask):
        return False
    if re.search(r"\\?i\b", subtask, re.I):
        return False
    return bool(re.search(r"\d+\s*(?:[\*×]|\\times)\s*\d+", subtask, re.I))


def _extract_problem_equation(problem_text, subtask):
    for src in (subtask, problem_text or ""):
        for p in _pieces(src):
            if "=" in p and re.search(r"[xyzwtk]", p):
                return p
    return None


def _solve_mode(subtask, tool_res):
    if any(k in subtask.lower() for k in _PLURAL_ROOT_KW):
        return "assist"
    if not tool_res.get("unique"):
        return "assist"
    if is_strict_solve_subtask(subtask):
        return "replace"
    return "assist"


def _linear_mode(subtask, args):
    if args.get("target"):
        return "replace"
    if wants_all_system_variables(subtask):
        return "assist"
    return "no_tool"


def _apply(subtask, step_id, int_edges, all_steps, mode, name, args, qid=None, rejections=None):
    if name == "no_tool" or mode == "no_tool":
        return "no_tool", "no_tool", {}
    ok, reason = validate_assignment(
        subtask, name, args, mode,
        all_steps=all_steps, step_id=step_id, int_edges=int_edges,
    )
    if not ok:
        if rejections is not None:
            rejections.append({
                "qid": qid, "step_id": step_id, "subtask": subtask[:240],
                "original_tool": name, "original_mode": mode,
                "original_args": args, "reason": reason,
            })
        return "no_tool", "no_tool", {}
    tool_res = run_tool(name, args)
    if not tool_res.get("success"):
        if rejections is not None:
            rejections.append({
                "qid": qid, "step_id": step_id, "subtask": subtask[:240],
                "original_tool": name, "original_mode": mode,
                "original_args": args, "reason": "工具执行失败",
            })
        return "no_tool", "no_tool", {}
    ok_gate, reason_gate, _ = semantic_gate(subtask, name, args, mode, tool_res)
    if not ok_gate:
        if rejections is not None:
            rejections.append({
                "qid": qid, "step_id": step_id, "subtask": subtask[:240],
                "original_tool": name, "original_mode": mode,
                "original_args": args, "reason": reason_gate,
            })
        return "no_tool", "no_tool", {}
    return mode, name, args


def assign(subtask, step_id=None, int_edges=None, all_steps=None, problem_text=None,
           qid=None, rejections=None, complex_used=None):
    low = subtask.lower()
    ps = _pieces(subtask)
    expr = max(ps, key=len) if ps else ""
    complex_used = complex_used if complex_used is not None else set()

    # --- subst：已知赋值 + 求表达式 ---
    subst_args = should_use_subst(subtask, problem_text)
    if subst_args and run_tool("subst", subst_args)["success"]:
        return _apply(subtask, step_id, int_edges, all_steps, "replace", "subst",
                      subst_args, qid, rejections)

    # --- 线性方程组（严格）---
    lin_args = should_use_linear_system(subtask, problem_text)
    if lin_args:
        res = run_tool("linear_system_solver", lin_args)
        if res["success"]:
            mode = _linear_mode(subtask, lin_args)
            if mode != "no_tool":
                lin_args["unique"] = res.get("unique", True)
                return _apply(subtask, step_id, int_edges, all_steps, mode,
                              "linear_system_solver", lin_args, qid, rejections)

    # --- 复数：去重 + 角色限制 ---
    cx = _extract_complex_expr(subtask) or _extract_complex_expr(problem_text or "")
    role = complex_step_role(subtask)
    if cx and role:
        args = {"expression": cx}
        mode = "replace" if role == "replace_final" else "assist"
        key = (mode, complex_key(args))
        if key in complex_used:
            pass
        elif run_tool("complex_arithmetic", args)["success"]:
            out = _apply(subtask, step_id, int_edges, all_steps, mode,
                         "complex_arithmetic", args, qid, rejections)
            if out[1] != "no_tool":
                complex_used.add(key)
            return out

    # --- 单变量 solve（严格触发 + 实数域默认）---
    eq = _extract_problem_equation(problem_text, subtask)
    if eq and is_strict_solve_subtask(subtask) and not is_root_derived_target(subtask) \
            and not any(c in low for c in _CONCEPT):
        var = infer_solve_variable(subtask, eq)
        if var:
            args = {"equation": eq, "variable": var, "domain": "real"}
            if re.search(r"\\?i\b|imaginary|complex", subtask + (problem_text or ""), re.I):
                args["domain"] = "complex"
            res = run_tool("solve", args)
            if res["success"]:
                args["unique"] = res.get("unique", False)
                mode = _solve_mode(subtask, res)
                return _apply(subtask, step_id, int_edges, all_steps, mode, "solve", args, qid, rejections)

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
        a, pct, b = mof.group(1), mof.group(2), mof.group(3)
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

    if expr and any(c in expr for c in "+-*/^") and not re.search(r"\bof\s+\d", low) \
            and not _skip_partial_foil_arith(subtask, problem_text) \
            and run_tool("arith", {"expression": expr})["success"]:
        return _apply(subtask, step_id, int_edges, all_steps, "replace", "arith",
                      {"expression": expr}, qid, rejections)

    return "no_tool", "no_tool", {}


def _check_question(qid, steps, tools, targs, modes):
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
    lines = ["# 工具分配拒绝记录", "", f"总计: {len(rejections)} 条", "", "## 按原因"]
    for reason, cnt in by_reason.most_common():
        lines.append(f"- {reason}: {cnt}")
    lines += ["", "## 按原工具", ""]
    for tool, cnt in by_tool.most_common():
        lines.append(f"- {tool}: {cnt}")
    lines += ["", "## 明细", ""]
    for r in rejections:
        lines.append(
            f"- Q{r['qid']} Step{r['step_id']} | {r['original_tool']}({r['original_mode']}) | {r['reason']}"
        )
        lines.append(f"  subtask: {r['subtask'][:120]}")
    with open(REJECT_MD, "w", encoding="utf-8") as f:
        f.write("\n".join(lines) + "\n")


def _output_target(tool_name, tool_res, args):
    if not tool_res.get("success"):
        return None
    if tool_name == "subst":
        return tool_res.get("result")
    if tool_name == "solve":
        return tool_res.get("value") or tool_res.get("text")
    if tool_name == "linear_system_solver":
        if args.get("target"):
            return tool_res.get("value") or tool_res.get("text")
        return tool_res.get("solution")
    if tool_name == "complex_arithmetic":
        return tool_res.get("text") or tool_res.get("result")
    return tool_res.get("result")


def _run_phase25_audit(data):
    records = []
    stats = {
        "replace_target_match_true": 0,
        "replace_target_match_false": 0,
        "assist_scope_match_true": 0,
        "assist_scope_match_false": 0,
        "unknown_target_count": 0,
        "validation_fail": 0,
        "tool_success_fail": 0,
    }
    for qid, q in data.items():
        steps = q["steps"]
        for i, (subtask, tool, mode, args) in enumerate(
            zip(steps, q["allo_tool"], q["tool_mode"], q["tool_args"]), start=1
        ):
            if tool == "no_tool":
                continue
            ok_val, reason = validate_assignment(
                subtask, tool, args, mode,
                all_steps=steps, step_id=i, int_edges=q.get("int_edges", []),
            )
            tool_res = run_tool(tool, args)
            allowed = list((args.get("subs") or {}).keys()) or args.get("variables") or None
            req_target = extract_requested_target(subtask, allowed)
            out_target = _output_target(tool, tool_res, args)
            rep_match = check_replace_target_match(subtask, tool, args, tool_res) if mode == "replace" else None
            ast_match = check_assist_scope_match(subtask, tool, args, tool_res) if mode == "assist" else None
            ok_gate, gate_reason, gate_tag = semantic_gate(subtask, tool, args, mode, tool_res)

            if mode == "replace":
                if rep_match is True and ok_gate:
                    stats["replace_target_match_true"] += 1
                elif rep_match is False or (rep_match is not True and not ok_gate and gate_tag == "replace_mismatch"):
                    stats["replace_target_match_false"] += 1
                else:
                    stats["unknown_target_count"] += 1
            elif mode == "assist":
                if ast_match is True and ok_gate:
                    stats["assist_scope_match_true"] += 1
                elif ast_match is False or (ast_match is not True and not ok_gate and gate_tag == "assist_mismatch"):
                    stats["assist_scope_match_false"] += 1
                else:
                    stats["unknown_target_count"] += 1

            if not ok_val:
                stats["validation_fail"] += 1
            if not tool_res.get("success"):
                stats["tool_success_fail"] += 1

            records.append({
                "qid": int(qid),
                "step_id": i,
                "subtask": subtask[:300],
                "tool_name": tool,
                "mode": mode,
                "tool_args": args,
                "tool_output": tool_res.get("result") or tool_res.get("text"),
                "requested_target": req_target,
                "output_target": out_target,
                "replace_target_match": rep_match,
                "assist_scope_match": ast_match,
                "semantic_gate_pass": ok_gate,
                "semantic_gate_reason": gate_reason,
                "validation_pass": ok_val,
                "validation_reason": reason if not ok_val else "ok",
                "tool_success": tool_res.get("success", False),
            })
    os.makedirs(LOG_DIR, exist_ok=True)
    with open(AUDIT_JSON, "w", encoding="utf-8") as f:
        json.dump({"stats": stats, "records": records}, f, ensure_ascii=False, indent=2)
    lines = [
        "# Phase 2.5/2.6 工具分配语义审计",
        "",
        f"非 no_tool 槽位: {len(records)}",
        f"validation 失败: {stats['validation_fail']}",
        f"tool_success 失败: {stats['tool_success_fail']}",
        f"replace_target_match_true: {stats['replace_target_match_true']}",
        f"replace_target_match_false: {stats['replace_target_match_false']}",
        f"assist_scope_match_true: {stats['assist_scope_match_true']}",
        f"assist_scope_match_false: {stats['assist_scope_match_false']}",
        f"unknown_target_count: {stats['unknown_target_count']}",
        "",
        "## 明细",
        "",
    ]
    for r in records:
        flag = "OK" if r["semantic_gate_pass"] and r["validation_pass"] and r["tool_success"] else "FAIL"
        lines.append(
            f"- [{flag}] Q{r['qid']} Step{r['step_id']} | {r['tool_name']}({r['mode']}) "
            f"| req={r['requested_target']} | out={r['output_target']} | gate={r['semantic_gate_pass']}"
        )
    with open(AUDIT_MD, "w", encoding="utf-8") as f:
        f.write("\n".join(lines) + "\n")
    return stats, records


def main():
    data = json.load(open(IN_PATH, encoding="utf-8"))
    rejections = []
    tool_stat = Counter()
    mode_stat = Counter()
    total_subtasks = 0
    covered_q = set()

    for qid, q in data.items():
        tools, targs, modes = [], [], []
        steps = q["steps"]
        problem_text = q.get("problemText", "")
        qid_int = int(qid)
        complex_used = set()
        for i, s in enumerate(steps, start=1):
            mode, name, args = assign(
                s, i, q.get("int_edges", []), all_steps=steps,
                problem_text=problem_text, qid=qid_int, rejections=rejections,
                complex_used=complex_used,
            )
            tools.append(name)
            targs.append(args)
            modes.append(mode)
            tool_stat[name] += 1
            mode_stat[mode] += 1
            if name != "no_tool":
                covered_q.add(qid_int)
        _check_question(qid_int, steps, tools, targs, modes)
        q["allo_tool"] = tools
        q["tool_args"] = targs
        q["tool_mode"] = modes
        total_subtasks += len(steps)

    json.dump(data, open(OUT_PATH, "w", encoding="utf-8"), ensure_ascii=False, indent=2)
    _write_rejection_logs(rejections)
    audit_stats, audit_records = _run_phase25_audit(data)

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
    print("语义审计 ->", AUDIT_JSON)
    print("--- 统计 ---")
    print(f"总子任务数: {total_subtasks}")
    print(f"非 no_tool 数: {non_no_tool}")
    print(f"replace 数: {replace_n}")
    print(f"assist 数: {assist_n}")
    print(f"solve 数: {tool_stat['solve']}")
    print(f"subst 数: {tool_stat['subst']}")
    print(f"complex_arithmetic 数: {tool_stat['complex_arithmetic']}")
    print(f"linear_system_solver 数: {tool_stat['linear_system_solver']}")
    print(f"aggregate 数: {aggregate_n}")
    print(f"非法 mode 数: {illegal_mode}")
    print(f"数组长度不一致数: 0")
    print(f"覆盖题数: {len(covered_q)}")
    print(f"拒绝分配数: {len(rejections)}")
    print(f"审计槽位数: {len(audit_records)}")
    print(f"validation 失败: {audit_stats['validation_fail']}")
    print(f"tool_success 失败: {audit_stats['tool_success_fail']}")
    print(f"replace_target_match_true: {audit_stats['replace_target_match_true']}")
    print(f"replace_target_match_false: {audit_stats['replace_target_match_false']}")
    print(f"assist_scope_match_true: {audit_stats['assist_scope_match_true']}")
    print(f"assist_scope_match_false: {audit_stats['assist_scope_match_false']}")
    print(f"unknown_target_count: {audit_stats['unknown_target_count']}")

    assert illegal_mode == 0
    assert aggregate_n == 0
    assert non_no_tool == replace_n + assist_n
    assert audit_stats["validation_fail"] == 0
    assert audit_stats["tool_success_fail"] == 0
    assert audit_stats["replace_target_match_false"] == 0
    assert audit_stats["assist_scope_match_false"] == 0


if __name__ == "__main__":
    main()
