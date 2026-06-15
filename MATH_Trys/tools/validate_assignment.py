# -*- coding: utf-8 -*-
"""
工具分配校验：分配阶段与运行阶段共用，拒绝明显错误的 replace/assist。

不读 gold、不按题号特判；仅依据子任务文本、工具名、参数与 mode。
"""
import re

try:
    import sympy as sp
    from sympy.parsing.sympy_parser import (
        parse_expr, standard_transformations,
        implicit_multiplication_application, convert_xor,
    )
    _TRANSF = standard_transformations + (implicit_multiplication_application, convert_xor)
    _SYMPY_OK = True
except Exception:
    _SYMPY_OK = False

_SOLVE_KW = (
    "solve for", "roots of", "values of", "satisfy",
    "equal to zero", "set equal", "quadratic equation",
)
_EQUATION_ASK = ("equation do", "equation from", "what equation", "equation we get")
_PLURAL_ROOT_KW = ("roots", "all possible values", "solutions of", "sum of the roots")
_PARAM_LETTERS = set("abckmnpr")


def _free_symbols(expr_str):
    if not _SYMPY_OK or not expr_str:
        return set()
    try:
        e = parse_expr(expr_str, transformations=_TRANSF)
        return {s.name for s in e.free_symbols}
    except Exception:
        return set()


def _is_pure_numeric(expr_str):
    if not _SYMPY_OK or not expr_str.strip():
        return False
    try:
        v = sp.simplify(parse_expr(expr_str, transformations=_TRANSF))
        return v.is_number and not v.free_symbols
    except Exception:
        return False


def _breaks_symbolic_structure(subtask, expr_str):
    """expanded form + 多因子乘积结构：不宜 arith replace。"""
    low = subtask.lower()
    if "expanded form" not in low:
        return False
    e = expr_str or ""
    if e.count("(") >= 2 and re.search(r"\)\s*[\*×]\s*\(", e):
        return True
    if len(re.findall(r"\)\s*[\+\-]", e)) >= 2:
        return True
    return False


def validate_assignment(subtask, tool_name, tool_args, mode="replace", all_steps=None, step_id=None, int_edges=None):
    if tool_name == "no_tool" or not tool_name:
        return True, "ok"

    tool_args = tool_args or {}
    low = subtask.lower()
    expr = tool_args.get("expression") or tool_args.get("equation") or ""

    # --- 参数完整性 ---
    if tool_name == "subst":
        if not tool_args.get("expression") or not tool_args.get("subs"):
            return False, "subst 参数不完整"
    elif tool_name == "aggregate":
        return False, "前驱无 verified 结构化数值，aggregate 暂不分配"
    elif tool_name == "solve":
        if not tool_args.get("equation", "").strip():
            return False, "solve 缺少 equation"
        if mode == "replace":
            if not tool_args.get("unique"):
                return False, "solve 多解或目标不明确，禁止 replace"
            if any(k in low for k in _PLURAL_ROOT_KW):
                return False, "求根集/和多解目标禁止 solve replace"
    elif tool_name == "complex_arithmetic":
        if not tool_args.get("expression", "").strip():
            return False, "complex_arithmetic 缺少 expression"
    elif tool_name == "linear_system_solver":
        eqs = tool_args.get("equations") or []
        vars_ = tool_args.get("variables") or []
        if len(eqs) < 2 or len(vars_) < 2:
            return False, "linear_system_solver 方程/变量不完整"
        if mode == "replace" and tool_args.get("target"):
            pass  # 目标量已内嵌求解
        elif mode == "replace" and not tool_args.get("target"):
            if not any(k in low for k in ("value of", "find ", "solve")):
                return False, "线性方程组 replace 需明确单变量或 target"
    elif tool_name in ("factor", "expand", "simplify", "arith"):
        if not expr.strip():
            return False, f"{tool_name} 缺少 expression"

    # --- arith replace 规则 ---
    if tool_name == "arith" and mode == "replace":
        if any(k in low for k in _SOLVE_KW):
            return False, "解方程类子任务禁止 arith replace"
        if "equation" in low and any(k in low for k in _EQUATION_ASK):
            return False, "求方程形式子任务禁止 arith replace"
        if "absolute difference" in low or "difference between" in low:
            return False, "绝对差子任务禁止 arith replace"
        if re.search(r"\\?i\b|imaginary|\d\s*i\b|-\s*i\b", subtask, re.I):
            return False, "含虚数 i 的子任务禁止 arith replace"
        if not _is_pure_numeric(expr):
            return False, "非纯数值表达式禁止 arith replace"
        if _breaks_symbolic_structure(subtask, expr):
            return False, "会破坏符号结构，禁止 arith replace"

    # --- 未绑定变量：replace ---
    if mode == "replace" and tool_name in ("expand", "factor", "simplify", "arith"):
        syms = _free_symbols(expr)
        subs_keys = {str(k).strip() for k in (tool_args.get("subs") or {}).keys()}
        bound = subs_keys | {"x", "y", "z", "t", "w", "n", "k"}
        unbound = {s for s in syms if s in _PARAM_LETTERS or (s not in bound and len(syms) >= 2)}
        if syms and unbound:
            return False, f"表达式含未绑定变量: {sorted(unbound)}"
        if len(syms) >= 3:
            return False, "replace 表达式含过多自由变量"

    return True, "ok"
