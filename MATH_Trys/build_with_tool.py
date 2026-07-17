# -*- coding: utf-8 -*-
"""
MATH 工具分配器（题目级验证求解 + 子任务级验证闸门版）。

两级设计（依据 5 轮 x 200 题实验证据：verified replace +30.8pp，assist ≈0 且是全部 right→wrong 来源）：

一、题目级 final_tool（本版新增核心）
  子问题多为过程性提问（"How do we..."），真正可计算的结构在原题文本里，而判分只看 final answer。
  故对原题做四类结构提取（全部数学通用结构、无题材关键词），求解并验证后产出题级 final_tool：
    1) 不等式组（含绝对值）+ 整数聚合目标（sum/count/min/max）→ inequality_solver（逐点回代验证）
    2) 等差/等比数列（题面逗号分隔项列表，全部给定项交叉验证）→ sequence_tool
    3) 多点定多项式（多项式形式 + 足量数值点，全点回代验证）→ linear_system_solver
    4) 题面单方程单未知数 + 明确目标（solve for / 目标表达式 / select）→ solve（回代验证）
  运行时（step2）若 final_tool 复验通过，直接以其答案作为 final answer，跳过 summarize LLM
  （类比 Puzzle 的 solve_by_tool：省 1 次 LLM 调用/题，且答案可证明正确）。

二、子任务级（收紧版）
  候选仅 subst / solve / linear_system 三类；replace 只授予两类"确定可信"来源：
    - solve / linear_system 且 verified=True（解回代原方程验证过）；
    - subst 且结果为闭合数值（表达式与全部绑定由子任务显式给出）。
  assist 仅保留 verified 的 solve / linear_system（实验表明 expand/factor/simplify/complex/arith
  的 assist 无净收益且是全部 right→wrong 回归的来源，已全部裁撤）。
  两种模式都再经 validate_assignment + semantic_gate 校验；任何一关不过 → no_tool 回退。

输出 schema：allo_tool / tool_args / tool_mode（与 steps 等长）不变；新增可选题级字段 final_tool
  {"tool", "args", "answer", "answer_key", "verified", "basis"}，运行脚本向后兼容（无该字段则走原流程）。

运行（离线、无 API）：cd MATH_Trys && python build_with_tool.py
"""
import json
import os
import re
import sys
import warnings
from collections import Counter

import sympy as sp

# sympy 解析个别题面字符串（如含 {..}(..) 形态）会触发 SyntaxWarning，已由 try/except 兜底，静默即可。
warnings.filterwarnings("ignore", category=SyntaxWarning)
from sympy.parsing.sympy_parser import (
    parse_expr, standard_transformations,
    implicit_multiplication_application, convert_xor,
)

BASE = os.path.dirname(os.path.abspath(__file__))
sys.path.append(BASE)
from tools import run_tool, validate_assignment
from tools.target_utils import (
    detect_root_target, detect_select, extract_requested_target,
    is_result_task, is_root_derived_target, is_strict_solve_subtask,
    semantic_gate, should_use_subst, wants_all_system_variables,
)

_TRANSF = standard_transformations + (implicit_multiplication_application, convert_xor)

IN_PATH = os.path.join(BASE, "TmpRes/step2In_MATH_last.json")
OUT_PATH = os.path.join(BASE, "TmpRes/step2In_MATH_with_tool.json")
LOG_DIR = os.path.join(BASE, "Logs")
REJECT_JSON = os.path.join(LOG_DIR, "tool_assignment_rejections.json")

# 仅这两类工具能“回代验证”，故只有它们（且 verified=True）可获授 replace；其余一律 assist。
_REPLACE_TOOLS = {"solve", "linear_system_solver"}
_IGNORE_SYMS = {"e", "i", "I", "pi", "E"}


# ------------------------- 结构解析（无题材关键词） -------------------------
def _pieces(text):
    """从文本中抽取数学片段（$...$ / \\(...\\) / \\[...\\]），做最小 LaTeX 清洗。"""
    if not text:
        return []
    raw = []
    for pat in (r"\\\((.+?)\\\)", r"\\\[(.+?)\\\]", r"\$(.+?)\$"):
        raw += re.findall(pat, text, re.S)
    out = []
    for s in raw:
        # \text{...} 清洗为 ';'，据此把 "A and B" 形态拆成独立片段
        out += [p.strip() for p in _clean_latex(s).split(";")]
    return [s for s in out if s]


def _clean_latex(s):
    """最小 LaTeX 清洗：分数（含 \\frac16 / \\frac{42}3 简写与带分数）、乘号、不等号、括号修饰。"""
    s = s.replace("\\left", "").replace("\\right", "")
    s = s.replace("\\cdot", "*").replace("\\times", "*")
    s = s.replace("\\!", "").replace("\\,", " ").replace("~", " ")
    s = s.replace("\\leq", "<=").replace("\\le", "<=")
    s = s.replace("\\geq", ">=").replace("\\ge", ">=")
    s = re.sub(r"\\l?c?dots\b", " ", s)
    s = re.sub(r"\\text\{[^{}]*\}", ";", s)  # \text{ and } 等 → 片段分隔符
    # 分数处理做两遍以展开嵌套（如 \frac{1\frac16}{w}）
    for _ in range(2):
        # 统一 \frac 简写参数（数字/单字母）为花括号形式，便于后续单一规则处理
        s = re.sub(r"\\(d?frac)\s*([0-9A-Za-z])\s*([0-9A-Za-z])(?![A-Za-z])", r"\\\1{\2}{\3}", s)
        s = re.sub(r"\\(d?frac)\s*([0-9A-Za-z])\s*\{", r"\\\1{\2}{", s)
        s = re.sub(r"\\(d?frac)\{([^{}]*)\}\s*([0-9A-Za-z])(?![A-Za-z])", r"\\\1{\2}{\3}", s)
        # 带分数 N\frac{a}{b} = N + a/b，必须先于普通分数处理，否则会误解析为 N*(a/b)
        s = re.sub(r"(\d+)\s*\\d?frac\{([^{}]*)\}\{([^{}]*)\}", r"(\1+(\2)/(\3))", s)
        s = re.sub(r"\\d?frac\{([^{}]*)\}\{([^{}]*)\}", r"((\1)/(\2))", s)
    s = s.replace("\\", "").strip()
    return s


def _parse(s):
    return parse_expr(s, transformations=_TRANSF)


def _absify(s):
    """|expr| → Abs(expr)，使含绝对值的片段可被 sympy 解析。"""
    return re.sub(r"\|([^|]+)\|", r"Abs(\1)", s)


def _syms(s):
    """表达式/方程中的自由符号名集合（滤除常量符号）。"""
    try:
        s = _absify(s)
        e = (_parse(s.split("=", 1)[0]) - _parse(s.split("=", 1)[1])) if "=" in s else _parse(s)
        return {x.name for x in e.free_symbols if x.name not in _IGNORE_SYMS}
    except Exception:
        return set()


def _is_equation(s):
    return bool(s) and s.count("=") == 1 and re.search(r"[A-Za-z]", s) \
        and all(_safe_parse(part) for part in s.split("="))


def _safe_parse(s):
    try:
        _parse(s)
        return True
    except Exception:
        return False


def _is_numeric(s):
    try:
        v = sp.simplify(_parse(s))
        return v.is_number and not v.free_symbols
    except Exception:
        return False


def _has_op(s):
    return any(c in s for c in "+-*/^")


def _has_i(s):
    return bool(re.search(r"\bi\b", s) or "I" in s)


def _equations(subtask, problem_text, all_steps):
    """按结构收集候选方程（子任务优先，题面/前序为补充），去重保序。"""
    spans = _pieces(subtask) + _pieces(problem_text)
    for st in all_steps or []:
        spans += _pieces(st)
    seen, eqs = set(), []
    for s in spans:
        if _is_equation(s) and s not in seen:
            seen.add(s)
            eqs.append(s)
    return eqs


def _cand_solve(subtask, problem_text, eqs):
    """单方程单未知数 → solve；按子任务意图附加 root_target/select/target_expression。"""
    for eq in eqs:
        syms = _syms(eq)
        if len(syms) != 1:
            continue
        var = next(iter(syms))
        args = {"equation": eq, "variable": var, "domain": "real"}
        if re.search(r"\bi\b|imaginary|complex", (subtask + " " + (problem_text or "")).lower()):
            args["domain"] = "complex"
        rt = detect_root_target(subtask)
        sel = detect_select(subtask)
        tgt = extract_requested_target(subtask, [var])
        if rt:
            args["root_target"] = rt
        elif sel:
            args["select"] = sel
        elif tgt and tgt.strip() != var and set(re.findall(r"[A-Za-z]", tgt)) <= {var}:
            args["target_expression"] = tgt  # 仅当是变量的派生式（如 x^2+1），而非变量本身
        return args
    return None


def _cand_linear(subtask, eqs):
    """多方程多未知数 → linear_system_solver。variables 取系统全部未知数，target_expression 为子任务所求。"""
    if len(eqs) < 2:
        return None
    allsyms = sorted({s for e in eqs for s in _syms(e)})
    if len(allsyms) < 2:
        return None
    use = [e for e in eqs if _syms(e) <= set(allsyms)]
    if len(use) < len(allsyms):  # 方程数需 ≥ 未知数，才可能有唯一解
        return None
    tgt = extract_requested_target(subtask, allsyms)
    if not tgt and not wants_all_system_variables(subtask):
        return None
    args = {"equations": use, "variables": allsyms}
    if tgt:
        args["target_expression"] = tgt
    return args


def _candidates(subtask, problem_text, all_steps):
    """子任务级候选（收紧版）：仅 subst / linear_system / solve 三类可验证工具。
    expand/factor/simplify/complex/arith 的 assist 经 5 轮实验证实无净收益且致错，已裁撤。"""
    eqs = _equations(subtask, problem_text, all_steps)
    out = []
    sa = should_use_subst(subtask, problem_text)
    if sa:
        out.append(("subst", sa))
    lin = _cand_linear(subtask, eqs)
    if lin:
        out.append(("linear_system_solver", lin))
    sv = _cand_solve(subtask, problem_text, eqs)
    if sv:
        out.append(("solve", sv))
    return out


# ------------------------- 分级信任闸门 + 模式决策 -------------------------
def _closed_numeric(res):
    """subst 结果是否为闭合数值（所有符号已被代入、无自由变量）→ 直接求值确定可信。"""
    try:
        v = sp.sympify(str(res.get("result")))
        return bool(v.is_number) and not v.free_symbols
    except Exception:
        return False


def _replace_ok(name, res):
    """可授 replace 的两类确定性来源：solve/linear 回代验证 verified；subst 闭合数值。"""
    return bool(res.get("verified")) or (name == "subst" and _closed_numeric(res))


def _desired_mode(name, args, subtask, res):
    """收紧后的模式决策：subst 仅闭合数值 replace；solve/linear 必须 verified（assist 也是）。"""
    if name == "subst":
        return "replace" if _closed_numeric(res) else None
    if not res.get("verified"):
        return None  # 未验证的 solve/linear 连 assist 都不给（right→wrong 的根源）
    if name == "solve":
        if args.get("root_target") or args.get("target_expression") or args.get("select"):
            return "replace" if is_result_task(subtask) else "assist"
        return "replace" if (args.get("unique") and is_strict_solve_subtask(subtask)
                             and not is_root_derived_target(subtask)) else "assist"
    return "replace" if (args.get("target_expression")
                         or wants_all_system_variables(subtask)) else "assist"


def _finalize(subtask, sid, int_edges, all_steps, name, args):
    """跑工具 -> 定模式 -> validate + semantic_gate 双闸门；通过返回 (mode,name,args)，否则 None。"""
    res = run_tool(name, args)
    if not res.get("success"):
        return None
    if name == "solve":
        args["unique"] = res.get("unique", False)
    desired = _desired_mode(name, args, subtask, res)
    if desired is None:
        return None
    for m in (("replace", "assist") if desired == "replace" else ("assist",)):
        if m == "replace" and not _replace_ok(name, res):
            continue
        ok, _ = validate_assignment(subtask, name, args, m, all_steps=all_steps,
                                    step_id=sid, int_edges=int_edges)
        if not ok:
            continue
        ok_gate, _, _ = semantic_gate(subtask, name, args, m, res)
        if ok_gate:
            return m, name, args
    return None


def assign(subtask, step_id, int_edges, all_steps, problem_text):
    for name, args in _candidates(subtask, problem_text, all_steps):
        out = _finalize(subtask, step_id, int_edges, all_steps, name, args)
        if out:
            return out
    return "no_tool", "no_tool", {}


# ------------------------- 题目级 final_tool 提取 -------------------------
# 对原题文本做四类通用数学结构提取，求解 + 验证后产出题级最终答案。
# 只用数学通用词汇（sum/how many/greatest/nth term 等聚合与序数词），不含任何题材关键词。

_ORDINALS = {w: i for i, w in enumerate(
    ("first", "second", "third", "fourth", "fifth", "sixth", "seventh", "eighth",
     "ninth", "tenth", "eleventh", "twelfth", "thirteenth", "fourteenth", "fifteenth",
     "sixteenth", "seventeenth", "eighteenth", "nineteenth", "twentieth"), start=1)}


def _agg_kind(low):
    """从提问语句提取通用聚合目标：sum / count / maximum / minimum。
    命中多种聚合词（如 'smallest ... largest ... b-a' 的复合目标）时返回 None，避免意图误判。"""
    kinds = []
    if re.search(r"\bsum of\b", low):
        kinds.append("sum")
    if re.search(r"\bhow many\b", low):
        kinds.append("count")
    if re.search(r"\b(greatest|largest|maximum)\b", low):
        kinds.append("maximum")
    if re.search(r"\b(least|smallest|minimum)\b", low):
        kinds.append("minimum")
    return kinds[0] if len(kinds) == 1 else None


def _is_inequality(s):
    return bool(re.search(r"[<>]=?", s)) and "=" not in s.replace("<=", "").replace(">=", "")


def _numeric_terms(span):
    """把 'a, b, c, d' 形态的片段解析为精确数值列表；解析失败返回 None。"""
    parts = [p.strip() for p in span.split(",") if p.strip()]
    if len(parts) < 3:
        return None
    vals = []
    for p in parts:
        try:
            v = sp.nsimplify(_parse(p))
        except Exception:
            return None
        if not v.is_number:
            return None
        vals.append(v)
    return vals


def _final_from_inequalities(problem):
    """不等式组 + 整数聚合目标 → inequality_solver（工具内部逐点回代验证）。"""
    low = problem.lower()
    agg = _agg_kind(low)
    if not agg or "integer" not in low:
        return None
    ineqs = [s for s in _pieces(problem) if _is_inequality(s)]
    if not ineqs:
        return None
    allsyms = set().union(*[_syms(s) for s in ineqs])
    if len(allsyms) != 1:
        return None
    var = next(iter(allsyms))
    return ("inequality_solver",
            {"constraints": ineqs, "variable": var, "domain": "integer", "target": agg},
            "target_value", f"{len(ineqs)} 条不等式, 整数域 {agg}")


def _final_from_multiples(problem):
    """'multiples of N between/from A and/to B' + sum/count → 离散枚举（逐点验证）。"""
    low = problem.lower()
    agg = _agg_kind(low)
    if agg not in ("sum", "count"):
        return None
    m = re.search(r"multiples? of (\d+)\s+(?:between|from)\s+(\d+)\s+(?:and|to)\s+(\d+)", low)
    if not m:
        return None
    k, a, b = int(m.group(1)), int(m.group(2)), int(m.group(3))
    if k <= 0 or b <= a or (b - a) > 100000:
        return None
    return ("discrete_constraint_enumerator",
            {"variables": ["n"],
             "domains": {"n": {"type": "integer", "minimum": 0, "maximum": b}},
             "constraints": [f"{k}*n >= {a}", f"{k}*n <= {b}"],
             "target_expression": f"{k}*n", "aggregation": agg},
            "target_value", f"multiples of {k} in [{a},{b}] {agg}")


def _final_from_sequence(problem):
    """题面逗号分隔项列表（>=3 项）→ 等差/等比判定（全部给定项交叉验证）→ sequence_tool。"""
    low = problem.lower()
    terms = next((t for s in _pieces(problem) if (t := _numeric_terms(s))), None)
    if not terms:
        return None
    diffs = [terms[i + 1] - terms[i] for i in range(len(terms) - 1)]
    ratios = ([terms[i + 1] / terms[i] for i in range(len(terms) - 1)]
              if all(t != 0 for t in terms) else [])
    if all(d == diffs[0] for d in diffs) and diffs[0] != 0:
        args = {"sequence_type": "arithmetic", "first_term": str(terms[0]),
                "difference": str(diffs[0])}
    elif ratios and all(r == ratios[0] for r in ratios) and ratios[0] not in (0, 1):
        args = {"sequence_type": "geometric", "first_term": str(terms[0]),
                "ratio": str(ratios[0])}
    else:
        return None
    args["given_terms"] = [str(t) for t in terms]

    # 目标 1：第 n 项（序数词或 "12th term"）
    n = None
    m = re.search(r"\b(\d+)(?:st|nd|rd|th)\s+term\b", low)
    if m:
        n = int(m.group(1))
    else:
        for w, i in _ORDINALS.items():
            if re.search(rf"\b{w}\s+term\b", low):
                n = i
                break
    if n and n > len(terms):
        args.update({"target": "nth_term", "n": n})
        return ("sequence_tool", args, "target_value", f"{args['sequence_type']} 第{n}项")
    # 目标 2：递减等差数列的最小正项
    if (args["sequence_type"] == "arithmetic" and sp.nsimplify(args["difference"]) < 0
            and re.search(r"\b(least|smallest)\s+positive\b", low)):
        args["target"] = "last_positive_integer_index"
        return ("sequence_tool", args, "term_value", "递减等差数列最小正项")
    return None


def _final_from_points_poly(problem):
    """多项式形式 + 足量数值点 → 系数线性方程组（全点回代验证）→ 目标表达式求值。"""
    spans = _pieces(problem)
    # 多项式形式：唯一主变量（最高次 >= 2）+ 若干一次系数符号
    poly_expr = main = None
    coeffs = []
    for s in spans:
        if "=" in s or "," in s or not _safe_parse(s):
            continue
        try:
            e = _parse(s)
        except Exception:
            continue
        syms = sorted(e.free_symbols, key=lambda x: x.name)
        if len(syms) < 2:
            continue
        deg = {v: sp.degree(sp.expand(e), v) for v in syms}
        mains = [v for v in syms if deg[v] >= 2]
        rest = [v for v in syms if deg[v] <= 1 and v not in mains]
        if len(mains) == 1 and len(rest) >= 2 and all(deg[v] == 1 for v in rest):
            poly_expr, main, coeffs = e, mains[0], rest
            break
    if poly_expr is None:
        return None
    # 数值点 (x, y)：从全文提取
    pts = []
    for mx, my in re.findall(r"\(\s*(-?\d+(?:[./]\d+)?)\s*,\s*(-?\d+(?:[./]\d+)?)\s*\)",
                             _clean_latex(problem)):
        try:
            pts.append((sp.nsimplify(mx), sp.nsimplify(my)))
        except Exception:
            continue
    pts = list(dict.fromkeys(pts))
    if len(pts) < len(coeffs):
        return None
    # 目标：仅含系数符号的表达式片段（带运算符，区别于多项式本体）
    coeff_names = {v.name for v in coeffs}
    tgt = next((s for s in spans
                if _safe_parse(s) and "=" not in s and _has_op(s)
                and _syms(s) and _syms(s) <= coeff_names), None)
    if not tgt:
        return None
    eqs = [f"{sp.expand(poly_expr.subs(main, px))} = {py}" for px, py in pts[: len(coeffs)]]
    args = {"equations": eqs, "variables": sorted(coeff_names), "target_expression": tgt}
    return ("linear_system_solver", args, "target_value",
            f"{len(pts)} 点定 {len(coeffs)} 系数多项式")


def _final_from_single_equation(problem):
    """题面唯一单未知数方程 + 明确目标（solve for / 目标式 / 根聚合）→ solve（回代验证）。"""
    low = problem.lower()
    eqs = list(dict.fromkeys(s for s in _pieces(problem) if _is_equation(s)))
    uni = [(e, next(iter(_syms(e)))) for e in eqs if len(_syms(e)) == 1]
    if len(eqs) != 1 or len(uni) != 1:
        return None  # 题面必须恰有一个方程且单未知数，否则该方程未必决定最终答案
    eq, var = uni[0]
    args = {"equation": eq, "variable": var, "domain": "real"}
    rt, sel = detect_root_target(problem), detect_select(problem)
    tgt = extract_requested_target(problem, [var])
    if rt:
        args["root_target"] = rt
    elif sel:
        args["select"] = sel
    elif tgt and tgt.strip() != var and set(re.findall(r"[A-Za-z]", tgt)) <= {var}:
        args["target_expression"] = tgt
    elif not re.search(rf"solve for\s+\W*{re.escape(var)}\b", low):
        return None
    return ("solve", args, None, f"题面单方程 solve {var}")


def build_final_tool(problem_text):
    """依次尝试题目级提取器；工具运行成功且 verified 才产出 final_tool，否则 None。"""
    for extractor in (_final_from_inequalities, _final_from_multiples,
                      _final_from_sequence, _final_from_points_poly,
                      _final_from_single_equation):
        try:
            cand = extractor(problem_text)
        except Exception:
            cand = None
        if not cand:
            continue
        name, args, answer_key, basis = cand
        res = run_tool(name, args)
        if not (res.get("success") and res.get("verified")):
            continue
        if name == "solve" and not (res.get("unique") or args.get("root_target")
                                    or args.get("select") or args.get("target_expression")):
            continue  # 多解且无聚合目标 → 最终答案不确定
        keys = ((answer_key,) if answer_key else ()) + ("target_value", "value", "result")
        answer = key = None
        for k in keys:
            v = res.get(k)
            if v not in (None, "", "None"):
                answer, key = str(v), k
                break
        if answer is None:
            continue
        return {"tool": name, "args": args, "answer": answer,
                "answer_key": key, "verified": True, "basis": basis}
    return None


# ------------------------- 主流程 -------------------------
def _check(qid, steps, tools, targs, modes):
    assert len(steps) == len(tools) == len(targs) == len(modes), f"Q{qid} 数组长度不一致"
    for t, a, m in zip(tools, targs, modes):
        if t == "no_tool":
            assert m == "no_tool" and a == {}, f"Q{qid} no_tool 但 mode/args 非空"
        else:
            assert m in ("replace", "assist"), f"Q{qid} 非法 mode={m} tool={t}"


def main():
    data = json.load(open(IN_PATH, encoding="utf-8"))
    tool_stat, mode_stat, final_stat = Counter(), Counter(), Counter()
    covered, final_covered, rejections, total = set(), set(), [], 0

    for qid, q in data.items():
        steps = q["steps"]
        problem_text = q.get("problemText", "")
        int_edges = q.get("int_edges", [])
        tools, targs, modes = [], [], []
        for i, s in enumerate(steps, start=1):
            mode, name, args = assign(s, i, int_edges, steps[: i - 1], problem_text)
            tools.append(name)
            targs.append(args)
            modes.append(mode)
            tool_stat[name] += 1
            mode_stat[mode] += 1
            if name != "no_tool":
                covered.add(int(qid))
            else:
                rejections.append({"qid": int(qid), "step_id": i, "subtask": s[:200]})
        _check(qid, steps, tools, targs, modes)
        q["allo_tool"], q["tool_args"], q["tool_mode"] = tools, targs, modes

        ft = build_final_tool(problem_text)
        if ft:
            q["final_tool"] = ft
            final_stat[ft["tool"]] += 1
            final_covered.add(int(qid))
        else:
            q.pop("final_tool", None)
        total += len(steps)

    json.dump(data, open(OUT_PATH, "w", encoding="utf-8"), ensure_ascii=False, indent=2)
    os.makedirs(LOG_DIR, exist_ok=True)
    json.dump(rejections, open(REJECT_JSON, "w", encoding="utf-8"), ensure_ascii=False, indent=2)

    non_no_tool = total - tool_stat["no_tool"]
    print("分配完成 ->", OUT_PATH)
    print(f"总子任务数: {total}")
    print(f"子任务级: 非 no_tool={non_no_tool} (replace={mode_stat['replace']}, assist={mode_stat['assist']})")
    for name in ("solve", "linear_system_solver", "subst"):
        if tool_stat[name]:
            print(f"  {name}: {tool_stat[name]}")
    print(f"题目级 final_tool: {len(final_covered)} 题")
    for name, c in final_stat.most_common():
        print(f"  {name}: {c}")
    all_covered = covered | final_covered
    print(f"覆盖题数(子任务级∪题目级): {len(all_covered)}/{len(data)}")
    print("覆盖题号:", ",".join(str(x) for x in sorted(all_covered)))
    assert non_no_tool == mode_stat["replace"] + mode_stat["assist"]


if __name__ == "__main__":
    main()
