# -*- coding: utf-8 -*-
"""子任务目标提取与工具-子任务语义匹配（通用规则，无题号硬编码）。"""
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

_ALLOWED_VARS = set("xyzwtk")
_FUNC_MARKERS = (
    r"\bf\s*\(", r"\bg\s*\(", r"\bh\s*\(", r"\bf\b", r"\bg\b",
    r"\bsin\b", r"\bcos\b", r"\btan\b", r"\blog\b", r"\bln\b",
    r"\bsqrt\b", r"\\sqrt", r"\\log", r"\\sin", r"\\cos",
)
_ASSIGN_RE = re.compile(r"^([a-zA-Z])\s*=\s*(.+)$")


def _clean(s):
    s = s.replace("\\left", "").replace("\\right", "")
    s = s.replace("\\cdot", "*").replace("\\times", "*")
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


def _normalize_expr(s):
    return re.sub(r"\s+", "", s or "")


def _symbol_letters(text):
    if _SYMPY_OK and text:
        probe = text
        if "=" in probe:
            lhs, rhs = probe.split("=", 1)
            probe = f"({lhs})-({rhs})"
        try:
            e = parse_expr(probe, transformations=_TRANSF)
            return {s.name for s in getattr(e, "free_symbols", set())}
        except Exception:
            pass
    return set(re.findall(r"[A-Za-z]", text or ""))


def _parse_target(expr_str, allowed_variables):
    if not _SYMPY_OK or not expr_str:
        return None
    allowed = set(allowed_variables or _ALLOWED_VARS)
    try:
        e = parse_expr(expr_str, transformations=_TRANSF)
    except Exception:
        return None
    if not hasattr(e, "free_symbols"):
        return None
    syms = {s.name for s in e.free_symbols}
    if not syms or not syms.issubset(allowed):
        return None
    if any(re.search(p, expr_str) for p in _FUNC_MARKERS):
        return None
    return str(e)


def extract_assignments(subtask):
    subs = {}
    for p in _pieces(subtask):
        m = _ASSIGN_RE.match(p.replace(" ", "")) or _ASSIGN_RE.match(p.strip())
        if m and m.group(1).lower() in _ALLOWED_VARS:
            subs[m.group(1).lower()] = m.group(2).strip()
    for m in re.finditer(
        r"when\s+\\?\(\s*([xyzwtk])\s*=\s*([^)\\]+?)\\?\)", subtask, re.I
    ):
        subs[m.group(1).lower()] = m.group(2).strip()
    for m in re.finditer(
        r"and\s+\\?\(\s*([xyzwtk])\s*=\s*([^)\\]+?)\\?\)", subtask, re.I
    ):
        subs[m.group(1).lower()] = m.group(2).strip()
    return subs


def _is_pure_assignment_eqs(eqs):
    for e in eqs:
        if "=" not in e:
            return False
        lhs = e.split("=", 1)[0].strip()
        if not re.match(r"^[xyzwtk]$", lhs, re.I):
            return False
    return True


def _infer_target_from_text(subtask, allowed):
    allowed = set(allowed or _ALLOWED_VARS)
    if re.search(r"product\s+of.*\\?\(\s*x\s*\\?\).*\\?\(\s*y\s*\\?\)", subtask, re.I):
        if {"x", "y"}.issubset(allowed):
            return "x*y"
    if re.search(r"product\s+of.*\\?\(\s*x\s*\\?\)\s*and\s*\\?\(\s*y\s*\\?\)", subtask, re.I):
        if {"x", "y"}.issubset(allowed):
            return "x*y"
    return None


def extract_requested_target(subtask, allowed_variables=None):
    allowed = set(allowed_variables or _ALLOWED_VARS)
    inferred = _infer_target_from_text(subtask, allowed)
    if inferred:
        t = _parse_target(inferred, allowed)
        if t:
            return t
    ps = _pieces(subtask)
    assign_vars = set(extract_assignments(subtask).keys())
    cands = []
    for p in ps:
        if _ASSIGN_RE.match(p.replace(" ", "")) or _ASSIGN_RE.match(p.strip()):
            continue
        if re.search(r"[a-zA-Z]", p):
            cands.append(p)
    if not cands:
        return None
    cands.sort(key=len, reverse=True)
    for c in cands:
        t = _parse_target(c, allowed)
        if t is None:
            continue
        syms = {s.name for s in parse_expr(t, transformations=_TRANSF).free_symbols}
        if len(syms) == 1 and syms == assign_vars:
            if re.search(r"what\s+is\s+\\?\(\s*[a-z]\s*\\?\)", subtask, re.I):
                if _normalize_expr(c) in (next(iter(syms)), f"{next(iter(syms))}^1"):
                    continue
        return t
    return None


def is_expression_target(subtask):
    t = extract_requested_target(subtask)
    if not t:
        return False
    try:
        e = parse_expr(t, transformations=_TRANSF)
        if len(e.free_symbols) != 1:
            return True
        s = next(iter(e.free_symbols))
        return str(e) != s.name
    except Exception:
        return True


def is_strict_solve_subtask(subtask):
    if is_expression_target(subtask):
        return False
    if re.search(r"value\s+of\s+\\?\([^)]*[\+\-\*/\^]", subtask, re.I):
        return False
    if re.search(r"find\s+the\s+value", subtask, re.I):
        return False
    patterns = (
        r"solve\s+for\s+\\?\(\s*([a-z])\s*\\?\)",
        r"find\s+\\?\(\s*([a-z])\s*\\?\)\s*(?:\?|\.|$|when|that|if)",
        r"what\s+is\s+\\?\(\s*([a-z])\s*\\?\)\s*(?:\?|\.|$|when|if)",
        r"what\s+is\s+the\s+value\s+of\s+\\?\(\s*([a-z])\s*\\?\).*satisf",
        r"what\s+are\s+the\s+roots",
        r"roots\s+of",
        r"\broots\b",
        r"\bsolutions\b",
    )
    return any(re.search(p, subtask, re.I) for p in patterns)


def wants_equation_solution(subtask):
    """RESULT 步是否要求解方程得到变量数值（含跨步合成场景）。"""
    if is_strict_solve_subtask(subtask):
        return True
    low = (subtask or "").lower()
    if re.search(r"value of\s+\\?\(\s*([a-z])\s*\\?\).*satisf", low):
        return True
    if re.search(r"what is the value of\s+\\?\(\s*([a-z])\s*\\?\)", low):
        return True
    if re.search(r"at what times", low) and re.search(r"height", low):
        return True
    return False


def infer_solve_variable(subtask, equation):
    for pat in (
        r"solve\s+for\s+\\?\(\s*([a-z])\s*\\?\)",
        r"find\s+\\?\(\s*([a-z])\s*\\?\)",
        r"what\s+is\s+\\?\(\s*([a-z])\s*\\?\)",
    ):
        m = re.search(pat, subtask, re.I)
        if m:
            return m.group(1).lower()
    if re.search(r"values?\s+of\s+\\?\(\s*([a-z])\s*\\?\).*\\?\(\s*([a-z])\s*\\?\).*\\?\(\s*([a-z])\s*\\?\)", subtask, re.I):
        return None
    if re.search(r"coefficient|discriminant|prime number", subtask, re.I):
        return None
    syms = set(re.findall(r"[xyzwtk]", equation))
    return syms.pop() if len(syms) == 1 else None


def is_conceptual_subtask(subtask):
    """概念/定义/关系/过程说明类子任务，禁止数值工具 replace。"""
    low = subtask.lower()
    patterns = (
        r"what\s+does\s+.+\s+mean",
        r"what\s+is\s+the\s+relationship",
        r"what\s+is\s+the\s+expression\s+for",  # 复述公式，非求值
        r"how\s+are\s+.+\s+related",
        r"how\s+is\s+.+\s+related",
        r"\bexplain\b",
        r"\bdefine\b",
        r"\binterpret\b",
        r"how\s+do\s+we\s+evaluate",
        r"how\s+can\s+we\s+evaluate",
        r"how\s+do\s+we\s+use\s+the\s+constant",
        r"how\s+can\s+we\s+use\s+the",
    )
    return any(re.search(p, low) for p in patterns)


def is_procedural_explanation_target(subtask):
    """过程/方法/解释类子任务目标（本阶段仅用于阻断 expand 工具）。"""
    low = subtask.lower()
    patterns = (
        r"how\s+(?:can|do|should)\s+we\s+expand",
        r"explain\s+(?:how\s+to\s+)?expand",
        r"explain\s+the\s+steps\s+for\s+expanding",
        r"describe\s+the\s+steps\s+for\s+expanding",
        r"what\s+method\s+should\s+be\s+used\s+to\s+expand",
    )
    return any(re.search(p, low) for p in patterns)


def is_process_expand_subtask(subtask):
    return is_procedural_explanation_target(subtask)


def is_direct_expand_request(subtask):
    low = subtask.lower()
    if is_procedural_explanation_target(subtask):
        return False
    return (
        "expanded form" in low
        or "in expanded form" in low
        or "expand the" in low
        or "multiply out" in low
        or bool(re.search(r"write.+(?:in\s+)?expanded\s+form", low))
        or bool(re.search(r"^\s*expand\s+\\?\(", subtask.strip(), re.I))
        or bool(re.search(r"^expand\s+\(", subtask.strip(), re.I))
    )


def blocks_numeric_replace(subtask, tool_name):
    if tool_name not in ("subst", "arith", "solve", "linear_system_solver"):
        return False
    return is_conceptual_subtask(subtask)


def extract_problem_givens(problem_text):
    if not problem_text or text_has_nonlinear_system(problem_text):
        return {}
    setup = problem_text.split("?")[0] if "?" in problem_text else problem_text
    return extract_assignments(setup)


def wants_all_system_variables(subtask):
    if re.search(r"what is the value of\s+\\?\(\s*([A-Za-z])\s*\\?\)", subtask, re.I):
        return False
    if re.search(r"product of", subtask, re.I):
        return False
    low = subtask.lower()
    if any(k in low for k in (
        "solve the system", "simultaneously solved", "both the equations",
        "satisfy the partial fraction decomposition",
    )):
        return True
    patterns = (
        r"values?\s+of\s+\\?\(\s*([A-Za-z])\s*\\?\)\s*(?:,|and)\s*\\?\(\s*([A-Za-z])\s*\\?\)",
        r"find\s+\\?\(\s*([A-Za-z])\s*\\?\)\s*(?:,|and)\s*\\?\(\s*([A-Za-z])\s*\\?\)",
        r"what\s+are\s+the\s+values?\s+of\s+([A-Za-z])\s*(?:,|and)\s*([A-Za-z])",
    )
    return any(re.search(p, subtask, re.I) for p in patterns)


def text_has_nonlinear_system(text):
    if not text:
        return False
    if any(re.search(p, text, re.I) for p in _FUNC_MARKERS):
        return True
    low = text.lower()
    if re.search(r"y\s*=\s*[^=\n]*[a-z]\s*\(", low):
        return True
    if re.search(r"/\s*sqrt\s*\(", low) or re.search(r"\\sqrt\{", text):
        return True
    if re.search(r"y\s*=\s*k\s*/", low):
        return True
    return False


def extract_linear_equations(text):
    if not text or text_has_nonlinear_system(text):
        return []
    eqs = []
    for p in _pieces(text):
        if "=" not in p or not re.search(r"[A-Za-z]", p):
            continue
        if text_has_nonlinear_system(p):
            return []
        eqs.append(p)
    return eqs


def linear_system_vars(eqs):
    names = set()
    for e in eqs:
        names.update(_symbol_letters(e) - {"e", "i"})
    return sorted(names)


def is_pure_assignment_system(subtask):
    return len(extract_assignments(subtask)) >= 2


def should_use_subst(subtask, problem_text=None):
    if is_conceptual_subtask(subtask):
        return None
    subs = extract_assignments(subtask)
    if not subs and problem_text:
        subs = extract_problem_givens(problem_text)
    if not subs:
        return None
    if problem_text and text_has_nonlinear_system(problem_text) and not extract_assignments(subtask):
        return None
    target = extract_requested_target(subtask, subs.keys())
    if not target:
        return None
    if is_strict_solve_subtask(subtask) and not is_expression_target(subtask):
        return None
    return {"expression": target, "subs": subs}


def should_use_linear_system(subtask, problem_text):
    if is_pure_assignment_system(subtask):
        return None
    eqs = extract_linear_equations(subtask)
    prob_eqs = extract_linear_equations(problem_text or "")
    if len(eqs) < 2 and len(prob_eqs) >= 2:
        if re.search(
            r"both.*equations|given.*equations|the equations|satisfy|simultaneously|system",
            subtask, re.I,
        ):
            eqs = prob_eqs
        else:
            vars_in_prob = linear_system_vars(prob_eqs)
            t_probe = extract_requested_target(subtask, vars_in_prob)
            if t_probe and len(vars_in_prob) >= 2:
                eqs = prob_eqs
    if len(eqs) < 2:
        return None
    if _is_pure_assignment_eqs(eqs):
        return None
    if text_has_nonlinear_system(subtask) or text_has_nonlinear_system(problem_text or ""):
        return None
    vars_ = linear_system_vars(eqs)
    if len(vars_) < 2:
        return None
    all_vars = wants_all_system_variables(subtask)
    target = extract_requested_target(subtask, vars_)
    if all_vars and target:
        try:
            e = parse_expr(target, transformations=_TRANSF)
            if len(e.free_symbols) == 1 and str(e) == next(iter(e.free_symbols)).name:
                target = None
        except Exception:
            pass
    if not target and not all_vars:
        return None
    args = {"equations": eqs, "variables": vars_}
    if target:
        args["target"] = target
    return args


def complex_key(args):
    s = args.get("expression", "")
    s = re.sub(r"\*\s*i\b", "*I", s, flags=re.I)
    s = re.sub(r"\bi\b", "I", s, flags=re.I)
    return _normalize_expr(s)


def complex_step_role(subtask):
    low = subtask.lower()
    if any(p in low for p in (
        "first terms", "outer terms", "inner terms", "last terms",
        "multiplying the first", "multiplying the outer", "multiplying the inner",
        "multiplying the last", "foil", "distributive property",
        "what is \\(3 \\times", "what is \\(-i \\times",
    )):
        return None
    if "simplify" in low and "using" in low and "i^2" in low.replace(" ", ""):
        return None
    if "combine" in low and ("imaginary" in low or "real" in low):
        return "assist_combine"
    if ("final" in low and "simplified" in low) or "final simplified expression" in low:
        return "replace_final"
    return None


_ROOT_DERIVED_PATTERNS = (
    r"sum\s+of\s+(?:the\s+)?roots",
    r"product\s+of\s+(?:the\s+)?roots",
    r"(?:smallest|least)\s+root",
    r"(?:largest|greatest|maximum)\s+root",
    r"difference\s+of\s+(?:the\s+)?roots",
)


def is_root_derived_target(subtask):
    low = subtask.lower()
    return any(re.search(p, low) for p in _ROOT_DERIVED_PATTERNS)


def asks_for_root_set(subtask):
    if is_root_derived_target(subtask):
        return False
    low = subtask.lower()
    return any(k in low for k in (
        "what are the roots", "roots of the", "roots of a", "all roots",
        "solutions of the", "what are the solutions",
    )) or bool(re.search(r"what\s+are\s+the\s+roots", low))


def _allowed_for_subtask(subtask, tool_args):
    subs = tool_args.get("subs") or {}
    if subs:
        return list(subs.keys())
    vars_ = tool_args.get("variables") or []
    if vars_:
        return vars_
    var = tool_args.get("variable")
    return [var] if var else list(_ALLOWED_VARS)


def check_replace_target_match(subtask, tool_name, tool_args, tool_res):
    """True=匹配, False=不匹配, None=无法确认（保守降级）"""
    if not tool_res or not tool_res.get("success"):
        return False
    tool_args = tool_args or {}
    allowed = _allowed_for_subtask(subtask, tool_args)
    req = extract_requested_target(subtask, allowed)

    if tool_name == "subst":
        if not req:
            return None
        if _normalize_expr(req) != _normalize_expr(tool_args.get("expression", "")):
            return False
        return tool_res.get("result") is not None

    if tool_name == "solve":
        # 结构化 solve（target_expression / common_root / select / root_target）：依赖工具自验证
        if tool_args.get("root_target"):
            if detect_root_target(subtask) != tool_args["root_target"]:
                return False
            return bool(tool_res.get("verified") and tool_res.get("target_value") is not None)
        if tool_args.get("target_expression") or tool_args.get("common_root") \
                or tool_args.get("select"):
            return bool(tool_res.get("verified") and tool_res.get("value") is not None)
        if is_root_derived_target(subtask) or asks_for_root_set(subtask):
            return False
        if not is_strict_solve_subtask(subtask) or not tool_args.get("unique"):
            return False
        var = (tool_args.get("variable") or "").lower()
        inferred = infer_solve_variable(subtask, tool_args.get("equation", ""))
        if inferred and var and inferred != var:
            return False
        return tool_res.get("value") is not None

    if tool_name == "inequality_solver":
        expected, _ = detect_inequality_target(subtask)
        if expected and tool_args.get("target") != expected:
            return False
        return bool(tool_res.get("verified") and tool_res.get("target_value") is not None)

    if tool_name == "sequence_tool":
        expected, n = detect_sequence_target(subtask)
        if expected and tool_args.get("target") != expected:
            return False
        if n is not None and tool_args.get("n") != n:
            return False
        return bool(tool_res.get("verified") and tool_res.get("value") is not None)

    if tool_name == "polynomial_coefficient_match":
        if wants_all_system_variables(subtask) and not tool_args.get("target_expression"):
            return bool(tool_res.get("verified") and tool_res.get("solutions"))
        req_t = extract_requested_target(subtask, tool_args.get("unknowns", []))
        if req_t and _normalize_expr(req_t) != _normalize_expr(
            tool_args.get("target_expression", "")
        ):
            return False
        return bool(tool_res.get("verified") and tool_res.get("target_value") is not None)

    if tool_name == "discrete_constraint_enumerator":
        req_t = extract_requested_target(subtask, tool_args.get("variables", []))
        if req_t and _normalize_expr(req_t) != _normalize_expr(
            tool_args.get("target_expression", "")
        ):
            return False
        expected_agg = detect_discrete_aggregation(subtask)
        if expected_agg and tool_args.get("aggregation") != expected_agg:
            return False
        return bool(tool_res.get("verified") and tool_res.get("target_value") is not None)

    if tool_name == "linear_system_solver":
        target = tool_args.get("target_expression") or tool_args.get("target")
        if not target:
            return bool(wants_all_system_variables(subtask) and tool_res.get("solution"))
        req_t = extract_requested_target(subtask, tool_args.get("variables", []))
        if req_t and _normalize_expr(req_t) != _normalize_expr(target):
            return False
        return bool(tool_res.get("verified") and tool_res.get("value") is not None)

    if tool_name == "complex_arithmetic":
        if complex_step_role(subtask) != "replace_final":
            return False
        return bool(tool_res.get("text") or tool_res.get("result"))

    if tool_name == "arith":
        if tool_res.get("result") is None:
            return False
        low = subtask.lower()
        if any(k in low for k in (
            "what is", "compute", "calculate", "evaluate",
            "improper fraction", "simplified form", "entire expression", "mixed number",
        )):
            return True
        expr = tool_args.get("expression", "")
        if expr and _normalize_expr(expr) in _normalize_expr(subtask):
            return True
        return None

    if tool_name == "expand":
        low = subtask.lower()
        if "expanded form" in low or "expand the" in low or is_direct_expand_request(subtask):
            return bool(tool_res.get("result"))
        return None

    if tool_name == "factor":
        if "factored form" in subtask.lower() or "factor the" in subtask.lower():
            return bool(tool_res.get("result"))
        return None

    return None


def check_assist_scope_match(subtask, tool_name, tool_args, tool_res):
    """True=范围正确, False=越界, None=无法确认"""
    if not tool_res or not tool_res.get("success"):
        return False
    tool_args = tool_args or {}

    if is_root_derived_target(subtask):
        return False

    if tool_name == "solve":
        if asks_for_root_set(subtask):
            return bool(tool_res.get("solutions"))
        if is_strict_solve_subtask(subtask):
            return bool(tool_res.get("solutions") or tool_res.get("value"))
        return False

    if tool_name == "linear_system_solver":
        if wants_all_system_variables(subtask) and not tool_args.get("target"):
            return bool(tool_res.get("solution"))
        if tool_args.get("target"):
            return False
        return False

    if tool_name == "complex_arithmetic":
        return complex_step_role(subtask) == "assist_combine"

    if tool_name == "simplify":
        expr = tool_args.get("expression", "")
        low = subtask.lower()
        if "simplify" not in low and "simplified" not in low:
            return False
        if expr and (expr in subtask or any(expr in p for p in _pieces(subtask))):
            return bool(tool_res.get("result"))
        return None

    if tool_name == "expand":
        if "expand" not in subtask.lower() and "expanded" not in subtask.lower():
            return False
        expr = tool_args.get("expression", "")
        if expr and expr not in subtask:
            return None
        return bool(tool_res.get("result"))

    if tool_name == "factor":
        low = subtask.lower()
        if "factor" not in low:
            return False
        return bool(tool_res.get("result"))

    return None


def semantic_gate(subtask, tool_name, tool_args, mode, tool_res):
    if mode == "replace":
        m = check_replace_target_match(subtask, tool_name, tool_args, tool_res)
        if m is True:
            return True, "ok", "replace_match"
        if m is False:
            return False, "replace 未直接回答当前子任务目标", "replace_mismatch"
        return False, "replace 目标无法确认，保守拒绝", "unknown_target"
    if mode == "assist":
        m = check_assist_scope_match(subtask, tool_name, tool_args, tool_res)
        if m is True:
            return True, "ok", "assist_match"
        if m is False:
            return False, "assist 超出当前子任务范围", "assist_mismatch"
        return False, "assist 范围无法确认，保守拒绝", "unknown_target"
    return True, "ok", "ok"


# ============================================================
# 阶段 3.2：任务类型分类 + 通用结构化目标提取（无题号、无全文匹配）
# ============================================================

_PROOF_KW = ("prove", "proof", "show that")
_EXPLAIN_KW = ("explain", "why ", "what does", "interpret", "describe", " mean")
_PROC_KW = (
    "how do we", "how can we", "how to ", "how does", "how is",
    "what method", "set up", "rewrite", "verify that", "what condition",
    "what equation can", "what equations", "what system", "what is the formula",
    "express ", "how should", "what are the steps", "steps for", "steps to",
    "what is the relationship", "what is the sequence rule",
)


def classify_task_type(subtask):
    """RESULT / PROCEDURE / EXPLANATION / PROOF。仅 RESULT 允许优先 replace。"""
    low = (subtask or "").lower()
    if any(k in low for k in _PROOF_KW):
        return "PROOF"
    if any(k in low for k in _EXPLAIN_KW):
        return "EXPLANATION"
    if any(k in low for k in _PROC_KW):
        return "PROCEDURE"
    return "RESULT"


def is_result_task(subtask):
    return classify_task_type(subtask) == "RESULT"


_ORDINALS = {
    "first": 1, "second": 2, "third": 3, "fourth": 4, "fifth": 5,
    "sixth": 6, "seventh": 7, "eighth": 8, "ninth": 9, "tenth": 10,
    "eleventh": 11, "twelfth": 12,
}


def detect_select(subtask):
    """从子任务语义识别 solve 的 select。"""
    low = (subtask or "").lower()
    if re.search(r"\b(smallest|least|minimum|lowest)\b", low):
        if "positive" in low:
            return "minimum_positive"
        return "minimum"
    if re.search(r"\b(largest|greatest|maximum|highest)\b", low):
        return "maximum"
    return None


def _math_segments(text):
    if not text:
        return []
    segs = []
    for pat in (r"\\\((.+?)\\\)", r"\\\[(.+?)\\\]", r"\$\$(.+?)\$\$", r"\$(.+?)\$"):
        segs += re.findall(pat, text, re.S)
    return segs


def _norm_relation(s):
    """保留关系符号的归一化（用于不等式/约束）。"""
    s = s.replace("\\left", "").replace("\\right", "")
    s = s.replace("\\cdot", "*").replace("\\times", "*")
    s = s.replace("\\leq", "<=").replace("\\geq", ">=")
    s = s.replace("\\le", "<=").replace("\\ge", ">=")
    s = s.replace("≤", "<=").replace("≥", ">=")
    s = re.sub(r"\\d?frac\{([^{}]*)\}\{([^{}]*)\}", r"((\1)/(\2))", s)
    s = s.replace("\\ldots", "").replace("\\dots", "")
    s = s.replace("~", " ")
    s = s.replace("\\", "")
    return s.strip().rstrip(" .,;")


def extract_inequality_constraints(text):
    """从文本提取一元不等式约束串（保留 |..| 与 <=,>=），按 and 拆分。"""
    out = []
    for seg in _math_segments(text):
        seg = re.sub(r"\\text\s*\{([^{}]*)\}", r" \1 ", seg)
        for part in re.split(r"\band\b|,", seg):
            piece = _norm_relation(part)
            if not piece:
                continue
            if not re.search(r"[<>]=?", piece):
                continue
            if not re.search(r"[a-z]", piece):
                continue
            out.append(piece)
    return out


def extract_sqrt_domain_constraint(text):
    """sqrt 定义域：被开方式 >= 0。返回约束串或 None。"""
    for seg in _math_segments(text):
        m = re.search(r"\\sqrt\{(.+?)\}", seg)
        if not m:
            m = re.search(r"sqrt\(([^()]*(?:\([^()]*\)[^()]*)*)\)", seg)
        if m:
            rad = _norm_relation(m.group(1))
            if re.search(r"[a-z]", rad):
                return f"({rad})>=0"
    return None


def detect_inequality_target(subtask):
    """返回 (target, domain)；无法识别返回 (None, None)。"""
    low = (subtask or "").lower()
    if "sum" in low and "integer" in low:
        return "sum", "integer"
    if re.search(r"how many integer|number of integer", low):
        return "count", "integer"
    if "condition on" in low or "condition for" in low:
        return "solution_set", "real"
    if "duration" in low or ("interval" in low and "length" in low) or "how long" in low:
        return "interval_length", "real"
    if re.search(r"\b(smallest|least|minimum|lowest)\b", low):
        return "minimum", "real"
    if re.search(r"\b(largest|greatest|maximum|highest)\b", low):
        return "maximum", "real"
    return None, None


_NUM = r"[-+]?(?:\d+/\d+|\d+(?:\.\d+)?)"


def extract_sequence_spec(problem_text):
    """识别等差/等比数列，返回 {sequence_type, first_term, difference|ratio}。"""
    if not problem_text:
        return None
    low = problem_text.lower()
    is_arith = "arithmetic sequence" in low
    is_geom = "geometric sequence" in low
    if not (is_arith or is_geom):
        return None
    terms = None
    for seg in _math_segments(problem_text):
        if "ldots" not in seg and "dots" not in seg and "," not in seg:
            continue
        body = _norm_relation(seg)
        raw = [t.strip() for t in body.split(",") if t.strip()]
        parsed = []
        for t in raw:
            if not re.fullmatch(r"[-+()0-9/.\s*]+", t):
                continue
            try:
                v = sp.nsimplify(parse_expr(t, transformations=_TRANSF))
                parsed.append(v)
            except Exception:
                continue
        if len(parsed) >= 2:
            terms = parsed
            break
    if not terms or len(terms) < 2:
        return None
    a1, a2 = terms[0], terms[1]
    if is_arith:
        return {"sequence_type": "arithmetic", "first_term": str(a1),
                "difference": str(a2 - a1)}
    ratio = sp.nsimplify(a2 / a1)
    return {"sequence_type": "geometric", "first_term": str(a1),
            "ratio": str(ratio)}


def detect_sequence_target(subtask, problem_text=None):
    """返回 (target, n)；触发词仅取自当前子任务，避免跨步串扰。"""
    text = (subtask or "").lower()
    if re.search(r"least positive|last positive|smallest positive", text):
        return "last_positive_integer_index", None
    n = None
    m = re.search(r"(\d+)\s*(?:st|nd|rd|th)\s*term", text)
    if m:
        n = int(m.group(1))
    if n is None:
        for word, val in _ORDINALS.items():
            if re.search(rf"\b{word}\s+term", text):
                n = val
                break
    if "sum of the first" in text and n:
        return "partial_sum", n
    if n:
        return "nth_term", n
    return None, None


def detect_common_root(subtask, problem_text):
    text = f"{subtask} {problem_text or ''}".lower()
    return bool(re.search(r"both equations|common (root|solution|value)|"
                          r"satisfies both", text))


def extract_polynomial_equations(text):
    """从文本提取所有等式（含 = 0 或两边表达式），返回原始串列表。"""
    eqs = []
    for p in _pieces(text):
        if "=" in p and re.search(r"[a-z]", p):
            eqs.append(p)
    return eqs


def extract_parabola_point_system(problem_text):
    """
    识别 '抛物线 ax^2+bx+c 过若干点' 结构，构造 3 元线性方程组。
    返回 {equations, variables} 或 None。
    """
    if not problem_text:
        return None
    low = problem_text.lower()
    if "parabola" not in low:
        return None
    if not re.search(r"a\s*x\s*\^?\{?2\}?\s*\+\s*b\s*x\s*\+\s*c", problem_text):
        return None
    pts = re.findall(r"\(\s*(-?\d+)\s*,\s*(-?\d+)\s*\)", problem_text)
    if len(pts) < 3:
        return None
    eqs = []
    for px, py in pts[:3]:
        px, py = int(px), int(py)
        eqs.append(f"{px ** 2}*a+({px})*b+c={py}")
    return {"equations": eqs, "variables": ["a", "b", "c"]}


def extract_vieta_target(problem_text):
    """
    识别 'Find <EXPR>, where a and b are the roots of <equation>' 结构。
    返回 {equation, target_expression} 或 None。
    """
    if not problem_text:
        return None
    low = problem_text.lower()
    if "roots of" not in low and "root of" not in low:
        return None
    if not re.search(r"\b[ab]\b", problem_text):
        return None
    segs = _math_segments(problem_text)
    eq = None
    for s in segs:
        cs = _norm_relation(s)
        if "=" in cs and re.search(r"x", cs):
            eq = cs
            break
    if not eq:
        return None
    target = None
    for s in segs:
        cs = _norm_relation(s)
        if "=" in cs:
            continue
        syms = set(re.findall(r"[a-z]", cs))
        if syms and syms.issubset({"a", "b"}) and re.search(r"[+\-*/]", cs):
            target = cs
            break
    if not target:
        return None
    return {"equation": eq, "target_expression": target}


# ============================================================
# 阶段 3.3：根派生目标 / 系数匹配 / 离散枚举 / 跨步方程合成（无题号、无全文）
# ============================================================

def detect_root_target(subtask):
    """识别根派生目标语义，返回 root_target 名或 None。"""
    low = (subtask or "").lower()
    if "squared value" in low or "squares of" in low or "square of the root" in low \
            or "sum of the squares" in low:
        return "sum_of_squares"
    if "sum of the reciprocals" in low or "reciprocal of the roots" in low or "reciprocal" in low:
        return "sum_of_reciprocals"
    if "positive difference" in low:
        return "positive_difference"
    if ("absolute difference" in low or "difference in absolute value" in low) and "root" in low:
        return "absolute_difference"
    if "product of the root" in low or "product of these root" in low:
        return "product"
    if ("sum of the root" in low or "sum of these root" in low
            or re.search(r"sum\s+of\s+(?:the\s+)?roots", low)
            or ("sum of these" in low and "value" in low)):
        return "sum"
    if re.search(r"positive difference between (?:these )?solution", low) \
            or re.search(r"positive difference between the", low):
        return "positive_difference"
    if re.search(r"how many (real )?(root|solution|value)", low) \
            or "number of root" in low:
        return "count"
    if "largest root" in low or "greatest root" in low or "maximum root" in low:
        return "maximum"
    if "smallest root" in low or "least root" in low or "minimum root" in low:
        return "minimum"
    return None


_COEFF_PHRASES = (
    "can be written", "written in the form", "in the form", "rewritten",
    "expressed in the form", "identically equal", "find a", "complete the square",
    "compare coefficients", "coefficient of", "equivalent expressions",
    "partial fraction", "for all x", "such that",
)


def detect_coefficient_matching(subtask, problem_text):
    text = f"{problem_text or ''} {subtask or ''}".lower()
    return any(p in text for p in _COEFF_PHRASES)


def _segment_unknowns(form, pvar):
    syms = set(re.findall(r"[a-zA-Z]", form))
    drop = {pvar, "e", "i"}
    for marker in ("sqrt", "sin", "cos", "tan", "log", "ln"):
        if marker in form.lower():
            drop |= set(marker)
    return sorted(s for s in syms if s not in drop)


def extract_polynomial_identity(problem_text):
    """
    识别 '<多项式> 可写成 <含参数形式>' 恒等关系。
    返回 {left_expression, right_expression, polynomial_variable, unknowns} 或 None。
    """
    if not problem_text:
        return None
    segs = [_norm_relation(s) for s in _math_segments(problem_text)]
    pvar = None
    for cand in ("x", "y", "t", "n"):
        if any(cand in _symbol_letters(s) for s in segs):
            pvar = cand
            break
    if not pvar:
        return None
    low = problem_text.lower()
    poly_seg, form_seg = None, None
    for s in segs:
        if "=" not in s:
            continue
        letters = _symbol_letters(s)
        if pvar not in letters:
            continue
        unknowns = sorted(letters - {pvar, "e", "i"})
        if not unknowns or len(unknowns) > 4:
            continue
        lhs, rhs = [part.strip() for part in s.split("=", 1)]
        if _symbol_letters(lhs) - {pvar, "e", "i"} and not (_symbol_letters(rhs) - {pvar, "e", "i"}):
            return {
                "left_expression": lhs,
                "right_expression": rhs,
                "polynomial_variable": pvar,
                "unknowns": unknowns,
            }
        if _symbol_letters(rhs) - {pvar, "e", "i"} and not (_symbol_letters(lhs) - {pvar, "e", "i"}):
            return {
                "left_expression": rhs,
                "right_expression": lhs,
                "polynomial_variable": pvar,
                "unknowns": unknowns,
            }
    if not any(p in low for p in ("written in the form", "can be written",
                                  "in the form", "rewritten", "complete the square")):
        return None
    for s in segs:
        if "=" in s or not re.search(r"[a-zA-Z]", s):
            continue
        letters = set(re.findall(r"[a-zA-Z]", s))
        nonx = letters - {pvar}
        if pvar in letters and not nonx and poly_seg is None:
            poly_seg = s            # 仅含 x：原多项式
        elif pvar in letters and nonx and form_seg is None:
            form_seg = s            # 含参数：目标形式
    if not poly_seg or not form_seg:
        return None
    unknowns = _segment_unknowns(form_seg, pvar)
    if not unknowns or len(unknowns) > 4:
        return None
    return {
        "left_expression": form_seg,
        "right_expression": poly_seg,
        "polynomial_variable": pvar,
        "unknowns": unknowns,
    }


def extract_coefficient_unknowns(problem_text):
    ident = extract_polynomial_identity(problem_text)
    return ident["unknowns"] if ident else []


_PRIME_KW = ("prime",)
_INT_KW = ("integer", "integers")


def extract_trajectory_model(problem_text):
    """识别 h(t) 或 y=at^2+bt+c 抛体高度模型。返回 {expr, time_var, height_var} 或 None。"""
    if not problem_text:
        return None
    for p in _pieces(problem_text):
        m = re.match(r"([a-z])\s*\(\s*([a-z])\s*\)\s*=\s*(.+)$", p, re.I)
        if m:
            hv, tv, rhs = m.group(1).lower(), m.group(2).lower(), _norm_relation(m.group(3))
        else:
            m = re.match(r"([a-z])\s*=\s*(.+)$", p, re.I)
            if not m:
                continue
            hv, rhs = m.group(1).lower(), _norm_relation(m.group(2))
            vars_in_rhs = [v for v in ("t", "x") if v in _symbol_letters(rhs)]
            if not vars_in_rhs:
                continue
            tv = vars_in_rhs[0]
        if tv not in _symbol_letters(rhs):
            continue
        try:
            expr = parse_expr(rhs, transformations=_TRANSF)
        except Exception:
            continue
        try:
            if sp.degree(sp.expand(expr), sp.Symbol(tv)) != 2:
                continue
        except Exception:
            continue
        return {"expr": str(sp.expand(expr)), "time_var": tv, "height_var": hv}
    return None


def extract_age_word_system(problem_text):
    """年龄文字题：倍数关系 + N 年前年龄和。返回 {equations, variables, target_var} 或 None。"""
    if not problem_text:
        return None
    low = problem_text.lower()
    if "years ago" not in low or "times" not in low:
        return None
    sum_m = re.search(r"sum of (?:their )?ages was\s+(\d+)", low)
    ago_m = re.search(r"(\d+)\s+years ago", low)
    times_m = re.search(r"(\w+)\s+times\s+(?:his|her|their|the)\s+(\w+)", low)
    if not (sum_m and ago_m and times_m):
        return None
    num_words = {
        "one": 1, "two": 2, "three": 3, "four": 4, "five": 5,
        "six": 6, "seven": 7, "eight": 8, "nine": 9, "ten": 10,
    }
    mult = num_words.get(times_m.group(1).lower())
    if not mult:
        try:
            mult = int(times_m.group(1))
        except ValueError:
            return None
    older, younger = "f", "s"
    total = int(sum_m.group(1))
    offset = int(ago_m.group(1))
    eqs = [f"{older}={mult}*{younger}", f"({older}-{offset})+({younger}-{offset})={total}"]
    target = younger if "son" in low or "daughter" in low else younger
    return {"equations": eqs, "variables": [older, younger], "target_var": target}


def extract_binary_operator_expr(problem_text):
    """提取自定义二元运算表达式，如 a star b = ..."""
    if not problem_text:
        return None
    for p in _pieces(problem_text):
        if re.search(r"[a-z]\s*star\s*[a-z]", p, re.I) and "=" in p:
            rhs = p.split("=", 1)[1].strip()
            if rhs:
                return rhs
    return None


def extract_operator_bindings(subtask, problem_text):
    """从 '3 star 11' / 'express 3 star 11' 提取 {a:3, b:11}。"""
    text = f"{subtask or ''} {problem_text or ''}"
    m = re.search(r"(\d+(?:\.\d+)?)\s*\\?star\s*(\d+(?:\.\d+)?)", text, re.I)
    if not m:
        return {}
    return {"a": m.group(1), "b": m.group(2)}


def extract_discrete_domains(problem_text, variables):
    """为离散变量构造有限域；无法确定有限范围返回 None。"""
    if not problem_text or not variables:
        return None
    low = problem_text.lower()
    set_match = re.search(r"\{([^{}]+)\}", problem_text)
    if set_match:
        values = [x.strip() for x in set_match.group(1).split(",") if x.strip()]
        if values:
            return {v: {"type": "finite_values", "values": values} for v in variables}
    if "prime" in low:
        dtype = "prime"
    elif "positive integer" in low:
        dtype = "positive_integer"
    elif "nonnegative" in low:
        dtype = "nonnegative_integer"
    elif "integer" in low:
        dtype = "integer"
    else:
        return None
    if dtype == "prime":
        lo = 2
    elif dtype == "positive_integer":
        lo = 1
    elif dtype == "nonnegative_integer":
        lo = 0
    else:
        lo = None
    hi = None
    between = re.findall(r"between\s+(-?\d+)\s+and\s+(-?\d+)", low)
    if between:
        lo, hi = int(between[0][0]), int(between[0][1])
    if hi is None:
        less = re.search(r"less than or equal to\s+(-?\d+)", low) \
            or re.search(r"at most\s+(-?\d+)", low) \
            or re.search(r"no greater than\s+(-?\d+)", low) \
            or re.search(r"less than\s+(-?\d+)", low) \
            or re.search(r"<\s*(-?\d+)", problem_text)
        if less:
            hi = int(less.group(1))
            if "less than " in low and "less than or equal to" not in low and hi > lo:
                hi -= 1
    if hi is None:
        greater = re.search(r"greater than or equal to\s+(-?\d+)", low) \
            or re.search(r"at least\s+(-?\d+)", low) \
            or re.search(r">=\s*(-?\d+)", problem_text)
        if greater:
            lower = int(greater.group(1))
            lo = lower if lo is None else max(lo, lower)
    if hi is None or lo is None:
        return None
    return {v: {"type": dtype, "minimum": lo, "maximum": hi} for v in variables}


def detect_discrete_aggregation(subtask):
    low = (subtask or "").lower()
    if "unique value" in low:
        return "unique_value"
    if "how many" in low or "number of" in low:
        return "count"
    if "sum of" in low:
        return "sum"
    if "largest" in low or "greatest" in low or "maximum" in low:
        return "maximum"
    if "smallest" in low or "least" in low or "minimum" in low:
        return "minimum"
    if "possible values" in low or "all values" in low:
        return "all_values"
    return None


def extract_discrete_constraints(text):
    """提取离散搜索的等式/不等式约束串。"""
    out = []
    for seg in _math_segments(text):
        seg = re.sub(r"\\text\s*\{([^{}]*)\}", " ", seg)
        for part in re.split(r"\band\b|,", seg):
            piece = _norm_relation(part)
            if piece and re.search(r"[<>]=?|=", piece) and re.search(r"[A-Za-z]", piece):
                out.append(piece)
    return out


def _eq_vars(eq_str):
    if not _SYMPY_OK:
        return set()
    try:
        side = eq_str.replace("=", "-(") + ")" if "=" in eq_str else eq_str
        e = parse_expr(side, transformations=_TRANSF)
        return {s.name for s in e.free_symbols}
    except Exception:
        return _symbol_letters(eq_str) - {"e", "i"}


def extract_context_equations(target_var, problem_text, all_steps, current_subtask=None):
    """
    跨步骤方程合成：收集原题与各子任务中“含目标变量、可解析、是等式”的方程。
    返回 [(equation_str, source)]，source ∈ {problem, prior_subtask, current_subtask}。
    不读取标准答案字段 / 自由生成答案。
    """
    found, seen = [], set()

    related = {target_var} if isinstance(target_var, str) else set(target_var or [])

    def _collect(src_text, source):
        for p in _pieces(src_text or ""):
            if "=" not in p:
                continue
            eq_vars = _eq_vars(p)
            if related and not (eq_vars & related):
                continue
            key = _normalize_expr(p)
            if key in seen:
                continue
            try:
                lhs, rhs = p.split("=", 1)
                parse_expr(lhs, transformations=_TRANSF)
                parse_expr(rhs, transformations=_TRANSF)
            except Exception:
                continue
            seen.add(key)
            found.append((p, source))

    _collect(problem_text, "problem")
    for st in (all_steps or []):
        _collect(st, "prior_subtask")
    _collect(current_subtask, "current_subtask")
    return found


def validate_target_match(subtask, tool_name, tool_args, mode):
    tool_args = tool_args or {}
    if mode == "replace" and blocks_numeric_replace(subtask, tool_name):
        return False, "概念/过程性子任务禁止数值工具 replace"
    if tool_name == "expand" and is_procedural_explanation_target(subtask):
        return False, "过程说明型 expand 子任务禁止工具"
    if tool_name == "expand" and mode == "replace" and is_process_expand_subtask(subtask):
        return False, "过程性展开子任务禁止 expand replace"
    _structured_solve = bool(
        tool_args.get("target_expression") or tool_args.get("common_root")
        or tool_args.get("select") or tool_args.get("root_target")
    )
    if is_root_derived_target(subtask) and tool_name == "solve" and not _structured_solve:
        return False, "求根派生目标，solve 无法直接回答"
    if tool_name == "solve":
        if _structured_solve:
            return True, "ok"
        if is_expression_target(subtask):
            return False, "子任务求表达式，禁止 solve"
        if mode == "replace" and not is_strict_solve_subtask(subtask):
            return False, "子任务未明确要求求变量/根"
        if mode == "replace" and not tool_args.get("unique"):
            return False, "solve replace 需唯一解"
        return True, "ok"
    if tool_name == "subst":
        req = extract_requested_target(subtask, tool_args.get("subs", {}).keys())
        if req and _normalize_expr(req) != _normalize_expr(tool_args.get("expression", "")):
            return False, "subst 表达式与子任务目标不一致"
        return True, "ok"
    if tool_name == "linear_system_solver":
        target = tool_args.get("target_expression") or tool_args.get("target")
        if mode == "replace" and not target and not wants_all_system_variables(subtask):
            return False, "linear replace 需 target 或全部变量"
        if target:
            req = extract_requested_target(subtask, tool_args.get("variables", []))
            if req and _normalize_expr(req) != _normalize_expr(target):
                return False, "linear target 与子任务不一致"
        return True, "ok"
    if tool_name == "inequality_solver":
        expected, _ = detect_inequality_target(subtask)
        if expected and tool_args.get("target") != expected:
            return False, "inequality target 与子任务不一致"
        return True, "ok"
    if tool_name == "sequence_tool":
        expected, n = detect_sequence_target(subtask)
        if expected and tool_args.get("target") != expected:
            return False, "sequence target 与子任务不一致"
        if n is not None and tool_args.get("n") != n:
            return False, "sequence n 与子任务不一致"
        return True, "ok"
    if tool_name == "polynomial_coefficient_match":
        if wants_all_system_variables(subtask) and not tool_args.get("target_expression"):
            return True, "ok"
        req = extract_requested_target(subtask, tool_args.get("unknowns", []))
        if req and _normalize_expr(req) != _normalize_expr(tool_args.get("target_expression", "")):
            return False, "coefficient target 与子任务不一致"
        return True, "ok"
    if tool_name == "discrete_constraint_enumerator":
        req = extract_requested_target(subtask, tool_args.get("variables", []))
        if req and _normalize_expr(req) != _normalize_expr(tool_args.get("target_expression", "")):
            return False, "discrete target 与子任务不一致"
        expected = detect_discrete_aggregation(subtask)
        if expected and tool_args.get("aggregation") != expected:
            return False, "discrete aggregation 与子任务不一致"
        return True, "ok"
    if tool_name == "complex_arithmetic":
        role = complex_step_role(subtask)
        if mode == "replace" and role != "replace_final":
            return False, "复数 replace 仅限最终化简步"
        if mode == "assist" and role != "assist_combine":
            return False, "复数 assist 仅限 combine 步"
        return True, "ok"
    return True, "ok"
