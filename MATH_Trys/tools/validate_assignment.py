# -*- coding: utf-8 -*-
"""
工具分配校验：分配阶段与运行阶段共用，拒绝明显错误的 replace/assist。

不读 gold、不按题号特判；仅依据子任务文本、工具名、参数与 mode。
"""
import re

try:
    from sympy.parsing.sympy_parser import (
        parse_expr, standard_transformations,
        implicit_multiplication_application, convert_xor,
    )
    _TRANSF = standard_transformations + (implicit_multiplication_application, convert_xor)
    _SYMPY_OK = True
except Exception:
    _SYMPY_OK = False

# 解方程 / 求方程形式
_SOLVE_KW = (
    "solve for", "roots of", "values of", "satisfy",
    "equal to zero", "set equal", "quadratic equation",
)
_EQUATION_ASK = ("equation do", "equation from", "what equation", "equation we get")

# 前驱子任务若仅为「方法/公式」型，aggregate 不应分配
_CONCEPT_PRED = (
    "how do", "how can", "how to", "formula", "what is the formula",
    "explain", "describe",
)
_NUMERIC_PRED_KW = (
    "what is the value", "what is ", "calculate", "compute", "evaluate",
    "length of", "distance", "product of", "sum of",
)

# 未绑定参数字母（非常量、非唯一求解变量）
_PARAM_LETTERS = set("abckmnpr")


def _free_symbols(expr_str):
    if not _SYMPY_OK or not expr_str:
        return set()
    try:
        e = parse_expr(expr_str, transformations=_TRANSF)
        return {s.name for s in e.free_symbols}
    except Exception:
        return set()


def _pred_subtask(step_id, all_steps):
    if not all_steps or not step_id:
        return ""
    i = int(step_id) - 1
    return all_steps[i] if 0 <= i < len(all_steps) else ""


def _likely_numeric_answer_subtask(st):
    """前驱子任务是否可能产出 aggregate 可用的数值答案。"""
    low = st.lower()
    if any(c in low for c in _CONCEPT_PRED):
        return False
    if re.search(r"\d", st):
        return True
    return any(k in low for k in _NUMERIC_PRED_KW)


def validate_assignment(subtask, tool_name, tool_args, mode="replace", all_steps=None, step_id=None, int_edges=None):
    """
    返回 (allowed: bool, reason: str)。
    allowed=False 时分配阶段应降级 no_tool；运行阶段应回退 LLM。
    """
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
        # 前驱尚无 verified 结构化数值，运行期仍依赖 extract_number 抽 LLM 自由文本 → 本阶段一律禁用
        return False, "前驱无 verified 结构化数值，aggregate 暂不分配"
    elif tool_name == "solve":
        if not tool_args.get("equation", "").strip():
            return False, "solve 缺少 equation"
    elif tool_name in ("factor", "expand", "simplify", "arith"):
        if not expr.strip():
            return False, f"{tool_name} 缺少 expression"

    # --- 解方程 / 求方程：禁止 arith replace ---
    if tool_name == "arith" and mode == "replace":
        if any(k in low for k in _SOLVE_KW):
            return False, "解方程类子任务禁止 arith replace"
        if "equation" in low and any(k in low for k in _EQUATION_ASK):
            return False, "求方程形式子任务禁止 arith replace"

    # --- 绝对差：禁止 arith 只算式中常量子表达式 ---
    if tool_name == "arith" and mode == "replace":
        if "absolute difference" in low or "difference between" in low:
            return False, "绝对差子任务禁止 arith replace"

    # --- 虚数：禁止 arith replace ---
    if tool_name == "arith" and mode == "replace":
        if re.search(r"\\?i\b|imaginary|\d\s*i\b|-\s*i\b", subtask, re.I):
            return False, "含虚数 i 的子任务禁止 arith replace"

    # --- 大式展开：禁止 arith replace（避免 Q117 类破坏因式结构）---
    if tool_name == "arith" and mode == "replace":
        if "expanded form" in low:
            return False, "expanded form 子任务禁止 arith replace"
        e = tool_args.get("expression", "")
        if e.count("(") >= 2 and ("+" in e or "-" in e):
            return False, "复杂多项式不宜 arith replace"

    # --- 未绑定变量：replace 时表达式含参数符号且无 subst ---
    if mode == "replace" and tool_name in ("expand", "factor", "simplify", "arith"):
        syms = _free_symbols(expr)
        subs_keys = {str(k).strip() for k in (tool_args.get("subs") or {}).keys()}
        bound = subs_keys | {"x", "y", "z", "t", "w", "n", "k"}  # 常见求解变量可单独出现
        unbound = {s for s in syms if s in _PARAM_LETTERS or (s not in bound and len(syms) >= 2)}
        if syms and unbound:
            return False, f"表达式含未绑定变量: {sorted(unbound)}"
        if len(syms) >= 3:
            return False, "replace 表达式含过多自由变量"

    return True, "ok"
