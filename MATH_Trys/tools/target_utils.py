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
        r"what\s+are\s+the\s+roots",
        r"roots\s+of",
        r"\broots\b",
        r"\bsolutions\b",
    )
    return any(re.search(p, subtask, re.I) for p in patterns)


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


def extract_problem_givens(problem_text):
    if not problem_text or text_has_nonlinear_system(problem_text):
        return {}
    setup = problem_text.split("?")[0] if "?" in problem_text else problem_text
    return extract_assignments(setup)


def wants_all_system_variables(subtask):
    if re.search(r"what is the value of\s+\\?\(\s*([xyzw])\s*\\?\)", subtask, re.I):
        return False
    if re.search(r"product of", subtask, re.I):
        return False
    low = subtask.lower()
    return any(k in low for k in (
        "values of x and y", "x and y that satisfy", "solve the system",
        "simultaneously solved", "both the equations",
    )) or bool(re.search(
        r"values\s+of\s+\\?\(\s*x\s*\\?\).*and\s+\\?\(\s*y\s*\\?\)", subtask, re.I
    ))


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
        if "=" not in p or not re.search(r"[xyzw]", p):
            continue
        if text_has_nonlinear_system(p):
            return []
        eqs.append(p)
    return eqs


def linear_system_vars(eqs):
    names = set()
    for e in eqs:
        names.update(re.findall(r"[xyzw]", e))
    return sorted(names)


def is_pure_assignment_system(subtask):
    return len(extract_assignments(subtask)) >= 2


def should_use_subst(subtask, problem_text=None):
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
    args = {"equations": eqs[:2], "variables": vars_[:2]}
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
        if is_root_derived_target(subtask) or asks_for_root_set(subtask):
            return False
        if not is_strict_solve_subtask(subtask) or not tool_args.get("unique"):
            return False
        var = (tool_args.get("variable") or "").lower()
        inferred = infer_solve_variable(subtask, tool_args.get("equation", ""))
        if inferred and var and inferred != var:
            return False
        return tool_res.get("value") is not None

    if tool_name == "linear_system_solver":
        target = tool_args.get("target")
        if not target:
            return False
        req_t = extract_requested_target(subtask, tool_args.get("variables", []))
        if req_t and _normalize_expr(req_t) != _normalize_expr(target):
            return False
        return tool_res.get("value") is not None

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
        if "expanded form" in low or "expand the" in low:
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


def validate_target_match(subtask, tool_name, tool_args, mode):
    tool_args = tool_args or {}
    if is_root_derived_target(subtask) and tool_name == "solve":
        return False, "求根派生目标，solve 无法直接回答"
    if tool_name == "solve":
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
        target = tool_args.get("target")
        if mode == "replace" and not target and not wants_all_system_variables(subtask):
            return False, "linear replace 需 target 或全部变量"
        if target:
            req = extract_requested_target(subtask, tool_args.get("variables", []))
            if req and _normalize_expr(req) != _normalize_expr(target):
                return False, "linear target 与子任务不一致"
        return True, "ok"
    if tool_name == "complex_arithmetic":
        role = complex_step_role(subtask)
        if mode == "replace" and role != "replace_final":
            return False, "复数 replace 仅限最终化简步"
        if mode == "assist" and role != "assist_combine":
            return False, "复数 assist 仅限 combine 步"
        return True, "ok"
    return True, "ok"
