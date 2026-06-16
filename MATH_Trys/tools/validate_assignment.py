# -*- coding: utf-8 -*-
"""
工具分配校验：分配阶段与运行阶段共用，拒绝明显错误的 replace/assist。
"""
import re

from .target_utils import (
    classify_task_type,
    extract_requested_target,
    is_conceptual_subtask,
    is_direct_expand_request,
    is_expression_target,
    is_procedural_explanation_target,
    is_process_expand_subtask,
    is_root_derived_target,
    is_strict_solve_subtask,
    blocks_numeric_replace,
    validate_target_match,
    wants_all_system_variables,
)

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

_EQUATION_ASK = ("equation do", "equation from", "what equation", "equation we get")
_PLURAL_ROOT_KW = ("roots", "all possible values", "solutions of", "sum of the roots")
_PARAM_LETTERS = set("abckmnpr")
_ALLOWED_CONTEXT_SOURCES = {
    "problem", "prior_subtask", "current_subtask", "verified_tool_output",
}


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
    low = subtask.lower()
    if "expanded form" not in low:
        return False
    e = expr_str or ""
    if e.count("(") >= 2 and re.search(r"\)\s*[\*×]\s*\(", e):
        return True
    if len(re.findall(r"\)\s*[\+\-]", e)) >= 2:
        return True
    return False


def _context_sources_valid(tool_args):
    sources = tool_args.get("context_sources") or []
    return all(src in _ALLOWED_CONTEXT_SOURCES for src in sources)


def validate_assignment(subtask, tool_name, tool_args, mode="replace", all_steps=None, step_id=None, int_edges=None):
    if tool_name == "no_tool" or not tool_name:
        return True, "ok"

    tool_args = tool_args or {}
    low = subtask.lower()
    expr = tool_args.get("expression") or tool_args.get("equation") or ""

    ok, reason = validate_target_match(subtask, tool_name, tool_args, mode)
    if not ok:
        return False, reason

    if mode == "replace" and blocks_numeric_replace(subtask, tool_name):
        return False, "概念/过程性子任务禁止数值工具 replace"
    if tool_name in ("factor", "expand") and mode == "replace" \
            and classify_task_type(subtask) == "PROCEDURE":
        return False, "过程型 factor/expand 禁止 replace"
    if tool_name == "expand" and is_procedural_explanation_target(subtask):
        return False, "过程说明型 expand 子任务禁止工具"

    if tool_name == "subst":
        if not tool_args.get("expression") or not tool_args.get("subs"):
            return False, "subst 参数不完整"
    elif tool_name == "aggregate":
        return False, "前驱无 verified 结构化数值，aggregate 暂不分配"
    elif tool_name == "solve":
        root_target = tool_args.get("root_target")
        structured = bool(
            tool_args.get("target_expression") or tool_args.get("common_root")
            or tool_args.get("select") or root_target
        )
        if tool_args.get("context_sources") and not _context_sources_valid(tool_args):
            return False, "solve context_sources 非法"
        if root_target:
            from .target_utils import detect_root_target
            if detect_root_target(subtask) != root_target:
                return False, "子任务未要求该根派生目标"
        if structured:
            has_eq = bool(tool_args.get("equation", "").strip()) or bool(
                tool_args.get("equations"))
            if not has_eq:
                return False, "solve 缺少 equation/equations"
        else:
            if is_root_derived_target(subtask):
                return False, "求根派生目标，solve 无法直接回答"
            if not tool_args.get("equation", "").strip():
                return False, "solve 缺少 equation"
            if mode == "replace":
                if not tool_args.get("unique"):
                    return False, "solve 多解或目标不明确，禁止 replace"
                if any(k in low for k in _PLURAL_ROOT_KW) and "what is" not in low:
                    return False, "求根集目标禁止 solve replace"
    elif tool_name == "inequality_solver":
        cons = tool_args.get("constraints") or ([tool_args.get("constraint")]
                                                if tool_args.get("constraint") else [])
        if not cons:
            return False, "inequality_solver 缺少 constraints"
        if not tool_args.get("variable"):
            return False, "inequality_solver 缺少 variable"
        if not tool_args.get("target"):
            return False, "inequality_solver 缺少 target"
    elif tool_name == "sequence_tool":
        if tool_args.get("sequence_type") not in ("arithmetic", "geometric"):
            return False, "sequence_tool 非法 sequence_type"
        if tool_args.get("first_term") in (None, ""):
            return False, "sequence_tool 缺少 first_term"
        if not tool_args.get("target"):
            return False, "sequence_tool 缺少 target"
    elif tool_name == "polynomial_coefficient_match":
        if not tool_args.get("left_expression") or not tool_args.get("right_expression"):
            return False, "polynomial_coefficient_match 缺少 left/right_expression"
        if not tool_args.get("polynomial_variable"):
            return False, "polynomial_coefficient_match 缺少 polynomial_variable"
        if not tool_args.get("unknowns"):
            return False, "polynomial_coefficient_match 缺少 unknowns"
        if not tool_args.get("target_expression") and not wants_all_system_variables(subtask):
            return False, "polynomial_coefficient_match 缺少 target_expression"
    elif tool_name == "discrete_constraint_enumerator":
        if not tool_args.get("variables"):
            return False, "discrete_constraint_enumerator 缺少 variables"
        doms = tool_args.get("domains") or {}
        search_space = 1
        for v in tool_args["variables"]:
            d = doms.get(v, {})
            finite = d.get("type") == "finite_values" or (
                d.get("minimum") is not None and d.get("maximum") is not None)
            if not finite:
                return False, f"变量 {v} 无有限域"
            if d.get("type") == "finite_values":
                size = len(d.get("values") or [])
            else:
                size = int(d.get("maximum")) - int(d.get("minimum")) + 1
            if size < 0:
                return False, f"变量 {v} 域上下界非法"
            search_space *= max(size, 1)
        if not tool_args.get("constraints"):
            return False, "discrete_constraint_enumerator 缺少 constraints"
        if not (tool_args.get("target_expression") or tool_args.get("aggregation")):
            return False, "discrete_constraint_enumerator 缺少 target/aggregation"
        if search_space > 100000:
            return False, "discrete_constraint_enumerator 搜索空间超限"
    elif tool_name == "complex_arithmetic":
        if not tool_args.get("expression", "").strip():
            return False, "complex_arithmetic 缺少 expression"
    elif tool_name == "linear_system_solver":
        eqs = tool_args.get("equations") or []
        vars_ = tool_args.get("variables") or []
        target = tool_args.get("target_expression") or tool_args.get("target")
        if len(eqs) < 2 or len(vars_) < 2:
            return False, "linear_system_solver 方程/变量不完整"
        if mode == "replace" and not target and not wants_all_system_variables(subtask):
            return False, "linear replace 需 target 或全部变量"
    elif tool_name in ("factor", "expand", "simplify", "arith"):
        if not expr.strip():
            return False, f"{tool_name} 缺少 expression"

    if tool_name == "arith" and mode == "replace":
        if is_strict_solve_subtask(subtask):
            return False, "求变量子任务禁止 arith replace"
        if is_expression_target(subtask) and not _is_pure_numeric(expr):
            return False, "含变量表达式子任务禁止 arith replace"
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
