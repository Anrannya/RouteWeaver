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

IN_PATH = os.path.join(BASE, "TmpRes/step2In_MATH_last.json")
OUT_PATH = os.path.join(BASE, "TmpRes/step2In_MATH_with_tool.json")
LOG_DIR = os.path.join(BASE, "Logs")
REJECT_JSON = os.path.join(LOG_DIR, "tool_assignment_rejections.json")
REJECT_MD = os.path.join(LOG_DIR, "tool_assignment_rejections.md")

_CONCEPT = ("formula", "relate", "which ", "how do", "how does", "how can", "why ",
            "explain", "define", " property", "rule for", "characteristic",
            "what form", "steps are needed", "steps do we", "steps to")
_SUBST_KW = ("value of", "evaluate", "compute", "calculate")
_SOLVE_KW = (
    "solve for", "find x", "find y", "find k", "find w", "find the value",
    "roots of", "roots", "solutions", "values of", "value of", "satisfy",
    "equal to zero", "set equal",
)
_PLURAL_ROOT_KW = ("roots", "all possible values", "solutions of", "sum of the roots", "sum of roots")
_COMPLEX_KW = ("simplify", "simplified", "final", "compute", "evaluate", "multiply", "product", "combine")
_VAR_RE = re.compile(r"value of\s*\\?\(\s*([a-zA-Z])\s*\\?\)|solve for\s*\\?\(\s*([a-zA-Z])\s*\\?\)|find\s+\\?\(\s*([a-zA-Z])\s*\\?\)", re.I)


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


def _extract_equations(text):
    eqs = []
    for p in _pieces(text):
        if "=" in p and re.search(r"[a-zA-Z]", p):
            eqs.append(p)
    return eqs


def _linear_vars(eqs):
    names = set()
    for e in eqs:
        names.update(re.findall(r"[xyzw]", e))
    return sorted(names)


def _wants_full_complex(subtask, cx, low):
    if any(p in low for p in (
        "first terms", "outer terms", "inner terms", "last terms",
        "multiplying the first", "multiplying the outer", "multiplying the inner",
        "multiplying the last",
    )):
        return False
    if any(k in low for k in ("final simplified", "combine these results", "combine the real",
                              "final simplified expression", "simplify the expression using")):
        return True
    if cx and (cx in subtask or cx.replace(" ", "") in subtask.replace(" ", "")):
        return True
    return any(k in low for k in ("simplify", "final", "compute", "evaluate")) and "partial" not in low


def _infer_solve_var(subtask, equation):
    m = _VAR_RE.search(subtask)
    if m:
        return (m.group(1) or m.group(2) or m.group(3)).lower()
    syms = set(re.findall(r"\b([xyzwtk])\b", equation))
    if len(syms) == 1:
        return syms.pop()
    return None


def _extract_problem_equation(problem_text, subtask):
    for src in (subtask, problem_text or ""):
        for p in _pieces(src):
            if "=" in p:
                return p
    return None


def _linear_target(subtask):
    low = subtask.lower()
    if "product" in low and "x" in low and "y" in low:
        return "x*y"
    m = _VAR_RE.search(subtask)
    if m:
        v = (m.group(1) or m.group(2) or m.group(3)).lower()
        return v
    return None


def _solve_mode(subtask, tool_res):
    low = subtask.lower()
    if any(k in low for k in _PLURAL_ROOT_KW):
        return "assist"
    if not tool_res.get("unique"):
        return "assist"
    if re.search(r"value of|solve for|find\s+\\?\(", subtask, re.I):
        return "replace"
    return "assist"


def _apply(subtask, step_id, int_edges, all_steps, mode, name, args, qid=None, rejections=None):
    if name == "no_tool":
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
    return mode, name, args


def assign(subtask, step_id=None, int_edges=None, all_steps=None, problem_text=None,
           qid=None, rejections=None):
    low = subtask.lower()
    ps = _pieces(subtask)
    expr = max(ps, key=len) if ps else ""

    # --- 二元线性方程组（自包含，不依赖前驱 LLM 文本）---
    eqs = _extract_equations(subtask) or _extract_equations(problem_text or "")
    if len(eqs) >= 2:
        vars_ = _linear_vars(eqs)
        if len(vars_) >= 2:
            target = _linear_target(subtask)
            args = {"equations": eqs[:2], "variables": vars_[:2]}
            if target:
                args["target"] = target
            res = run_tool("linear_system_solver", args)
            if res["success"]:
                mode = "replace" if (target or re.search(r"value of|find ", subtask, re.I)) else "assist"
                args["unique"] = res.get("unique", True)
                return _apply(subtask, step_id, int_edges, all_steps, mode,
                              "linear_system_solver", args, qid, rejections)

    # --- 完整复数表达式（优先于局部 arith）---
    cx = _extract_complex_expr(subtask) or _extract_complex_expr(problem_text or "")
    if cx and _wants_full_complex(subtask, cx, low):
        args = {"expression": cx}
        if run_tool("complex_arithmetic", args)["success"]:
            mode = "replace" if any(k in low for k in ("simplify", "final", "compute", "evaluate")) else "assist"
            return _apply(subtask, step_id, int_edges, all_steps, mode,
                          "complex_arithmetic", args, qid, rejections)

    # --- 单变量 solve ---
    eq = _extract_problem_equation(problem_text, subtask)
    if eq and any(k in low for k in _SOLVE_KW) and not any(c in low for c in _CONCEPT) \
            and not any(k in low for k in ("sum of the roots", "sum of roots")):
        var = _infer_solve_var(subtask, eq)
        if var:
            args = {"equation": eq, "variable": var}
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
        for i, s in enumerate(steps, start=1):
            mode, name, args = assign(
                s, i, q.get("int_edges", []), all_steps=steps,
                problem_text=problem_text, qid=qid_int, rejections=rejections,
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
    print(f"总子任务数: {total_subtasks}")
    print(f"非 no_tool 数: {non_no_tool}")
    print(f"replace 数: {replace_n}")
    print(f"assist 数: {assist_n}")
    print(f"solve 数: {tool_stat['solve']}")
    print(f"complex_arithmetic 数: {tool_stat['complex_arithmetic']}")
    print(f"linear_system_solver 数: {tool_stat['linear_system_solver']}")
    print(f"aggregate 数: {aggregate_n}")
    print(f"非法 mode 数: {illegal_mode}")
    print(f"数组长度不一致数: 0")
    print(f"覆盖题数: {len(covered_q)}")
    print(f"拒绝分配数: {len(rejections)}")

    assert illegal_mode == 0
    assert aggregate_n == 0
    assert non_no_tool == replace_n + assist_n


if __name__ == "__main__":
    main()
