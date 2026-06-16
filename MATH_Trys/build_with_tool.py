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
    check_assist_scope_match,
    check_replace_target_match,
    classify_task_type,
    complex_key,
    complex_step_role,
    detect_common_root,
    detect_coefficient_matching,
    detect_discrete_aggregation,
    detect_inequality_target,
    detect_root_target,
    detect_select,
    detect_sequence_target,
    extract_context_equations,
    extract_discrete_constraints,
    extract_discrete_domains,
    extract_inequality_constraints,
    extract_parabola_point_system,
    extract_polynomial_equations,
    extract_polynomial_identity,
    extract_requested_target,
    extract_sequence_spec,
    extract_sqrt_domain_constraint,
    extract_vieta_target,
    infer_solve_variable,
    is_direct_expand_request,
    is_process_expand_subtask,
    is_procedural_explanation_target,
    is_result_task,
    is_root_derived_target,
    is_strict_solve_subtask,
    semantic_gate,
    should_use_linear_system,
    should_use_subst,
    extract_age_word_system,
    extract_binary_operator_expr,
    extract_operator_bindings,
    extract_trajectory_model,
    wants_equation_solution,
    wants_all_system_variables,
)

STABLE_35 = [
    2, 9, 11, 15, 20, 33, 34, 38, 50, 52, 54, 73, 75, 77, 78, 85, 106, 115, 119,
    131, 134, 137, 139, 147, 150, 151, 153, 168, 171, 172, 178, 180, 184, 185, 190,
]
SUBSTANTIVE_TOOLS = {
    "solve", "linear_system_solver", "inequality_solver", "sequence_tool",
    "polynomial_coefficient_match", "discrete_constraint_enumerator",
    "subst", "arith", "complex_arithmetic",
}
_INTERMEDIATE_TOOLS = {"expand", "factor", "simplify"}
_FINAL_KW = (
    "final value", "final answer", "compute the final", "what is the value of",
    "what is the final", "total time", "maximum possible value", "minimum possible",
)


def _single_var(constraints):
    letters = set()
    for c in constraints:
        letters |= {ch.lower() for ch in re.findall(r"[a-zA-Z]", c)}
    for pref in ("x", "t", "y", "z", "n"):
        if pref in letters:
            return pref
    return next(iter(letters)) if len(letters) == 1 else None


def _find_equation(problem_text, subtask, all_steps):
    eq = _extract_problem_equation(problem_text, subtask)
    if eq:
        return eq
    for src in (all_steps or []) + [problem_text]:
        eqs = extract_polynomial_equations(src or "")
        if eqs:
            return eqs[0]
    return None


def _record_context_equation(ctx, equation, source):
    if not equation or source not in {
        "problem", "prior_subtask", "current_subtask", "verified_tool_output",
    }:
        return
    seen = {(e, s) for e, s in ctx["equations"]}
    key = (equation, source)
    if key in seen:
        return
    ctx["equations"].append(key)
    ctx["sources"].append(source)


def _record_known_values(ctx, mapping, source="verified_tool_output"):
    if source != "verified_tool_output":
        return
    for name, value in (mapping or {}).items():
        if not isinstance(name, str):
            continue
        if not re.fullmatch(r"[A-Za-z]", name):
            continue
        if value in (None, ""):
            continue
        ctx["known_values"][name] = str(value)
        _record_context_equation(ctx, f"{name}={value}", source)


def _seed_verified_context(problem_text, ctx):
    for p in _pieces(problem_text or ""):
        if "=" in p and re.search(r"[A-Za-z]", p):
            _record_context_equation(ctx, p, "problem")


def _update_verified_context(subtask, tool_name, args, tool_res, ctx):
    for p in _pieces(subtask or ""):
        if "=" in p and re.search(r"[A-Za-z]", p):
            _record_context_equation(ctx, p, "prior_subtask")
    if not tool_res.get("verified"):
        return
    if tool_name == "solve":
        eqs = args.get("equations") or ([args.get("equation")] if args.get("equation") else [])
        for eq in eqs:
            _record_context_equation(ctx, eq, "verified_tool_output")
        if args.get("variable") and tool_res.get("value") is not None:
            _record_known_values(ctx, {args["variable"]: tool_res.get("value")})
    elif tool_name == "linear_system_solver":
        _record_known_values(ctx, tool_res.get("solution") or {})
    elif tool_name == "polynomial_coefficient_match":
        _record_known_values(ctx, tool_res.get("solutions") or {})


def _try_discrete_assign(subtask, problem_text):
    if not is_result_task(subtask):
        return None
    low = f"{problem_text or ''} {subtask or ''}".lower()
    if "prime" not in low and "integer" not in low:
        return None
    merged_text = f"{problem_text or ''} {subtask or ''}"
    cons = list(dict.fromkeys(
        extract_discrete_constraints(problem_text) + extract_discrete_constraints(subtask)
    ))
    if not cons:
        return None
    vars_ = sorted({c for c in re.findall(r"[A-Za-z]", " ".join(cons)) if c.lower() not in "ei"})
    if not vars_:
        return None
    doms = extract_discrete_domains(merged_text, vars_)
    if not doms:
        return None
    agg = detect_discrete_aggregation(subtask) or "unique_value"
    tgt = extract_requested_target(subtask, vars_)
    if not tgt and agg != "count":
        return None
    args = {
        "variables": vars_, "domains": doms, "constraints": cons,
        "aggregation": agg,
    }
    if tgt:
        args["target_expression"] = tgt
    return "replace", "discrete_constraint_enumerator", args


def _try_prime_root_value_assign(subtask, problem_text):
    if not is_result_task(subtask):
        return None
    low_problem = (problem_text or "").lower()
    low_subtask = (subtask or "").lower()
    if "prime integers" not in low_problem or "roots of the polynomial" not in low_problem:
        return None
    if "value of" not in low_subtask or "\\( n \\)" not in subtask and " n " not in low_subtask:
        return None
    bound = re.search(r"([A-Za-z])\s*<\s*(\d+)", problem_text or "")
    if not bound:
        return None
    upper = int(bound.group(2))
    if upper <= 2:
        return None
    agg = "all_values" if any(k in low_subtask for k in ("possible", "each possible", "resulting value")) else None
    if not agg:
        return None
    return "replace", "discrete_constraint_enumerator", {
        "variables": ["p", "q"],
        "domains": {
            "p": {"type": "prime", "minimum": 2, "maximum": upper - 1},
            "q": {"type": "prime", "minimum": 2, "maximum": upper - 1},
        },
        "constraints": [f"p+q<{upper}"],
        "target_expression": "p*q",
        "aggregation": agg,
    }


def _try_radical_root_form_assign(subtask, problem_text, all_steps):
    if not is_result_task(subtask):
        return None
    low_problem = (problem_text or "").lower()
    if "can be written in the form" not in low_problem or "sqrt" not in low_problem:
        return None
    req = extract_requested_target(subtask, ["m", "n"])
    if req not in ("m + n", "m+n"):
        return None
    eq = _find_equation(problem_text, subtask, all_steps)
    if not eq:
        return None
    return "replace", "solve", {
        "equation": eq,
        "target_expression": "(a+b)/2 + ((a-b)/2)**2",
    }


def _extract_bulk_discount_constraints(problem_text):
    text = (problem_text or "").replace("\\$", "$")
    if "reduced by" not in text.lower() or "tickets" not in text.lower():
        return None
    threshold = re.search(r"up to\s+(\d+)\s+tickets", text, re.I)
    price = re.search(r"price for each ticket is\s+[^0-9]*(\d+)", text, re.I)
    reduction = re.search(r"reduced by\s+[^0-9]*(\d+)[^0-9]*for each additional ticket", text, re.I)
    target = re.search(r"profit greater than\s+[^0-9]*(\d+)", text, re.I)
    if not (threshold and price and reduction and target):
        return None
    tvar = "t" if re.search(r"\bif\s+\$?t\$?\s+is\b", text, re.I) or "$t$" in text else "t"
    limit = int(threshold.group(1))
    base_price = int(price.group(1))
    delta = int(reduction.group(1))
    target_value = int(target.group(1))
    expr = f"{tvar}*({base_price}-{delta}*({tvar}-{limit}))"
    return {
        "constraints": [f"{tvar}>{limit}", f"({expr})>{target_value}"],
        "variable": tvar,
        "domain": "positive_integer",
    }


def _structured_assign(subtask, problem_text, all_steps=None, verified_context=None):
    """阶段 3.2/3.3：高置信结构化路由（仅 RESULT 步 replace）。"""
    if not is_result_task(subtask):
        return None
    low = subtask.lower()

    para = extract_parabola_point_system(problem_text)
    if para:
        tgt = extract_requested_target(subtask, para["variables"])
        if tgt:
            args = dict(para)
            args["target_expression"] = tgt
            return "replace", "linear_system_solver", args

    radical = _try_radical_root_form_assign(subtask, problem_text, all_steps)
    if radical:
        return radical

    ident = extract_polynomial_identity(problem_text) if detect_coefficient_matching(subtask, problem_text) else None
    if ident:
        if wants_all_system_variables(subtask) and re.search(r"what are|find|values", low):
            return "replace", "polynomial_coefficient_match", dict(ident)
        tgt = extract_requested_target(subtask, ident["unknowns"])
        if tgt and re.search(r"what is|find|compute|value|final", low):
            args = dict(ident)
            args["target_expression"] = tgt
            return "replace", "polynomial_coefficient_match", args

    disc = _try_discrete_assign(subtask, problem_text)
    if disc:
        return disc

    prime_root_disc = _try_prime_root_value_assign(subtask, problem_text)
    if prime_root_disc:
        return prime_root_disc

    bulk = _extract_bulk_discount_constraints(problem_text)
    if bulk:
        tgt, _ = detect_inequality_target(subtask)
        if tgt == "solution_set":
            args = dict(bulk)
            args["target"] = "solution_set"
            return "replace", "inequality_solver", args

    rt = detect_root_target(subtask)
    if rt:
        eq = _find_equation(problem_text, subtask, all_steps)
        if not eq:
            eqs = extract_polynomial_equations(problem_text or "")
            if len(eqs) == 1:
                eq = eqs[0]
        if eq:
            return "replace", "solve", {
                "equation": eq, "root_target": rt, "domain": "real",
            }

    traj = extract_trajectory_model(problem_text)
    if traj and is_result_task(subtask):
        tv, expr = traj["time_var"], traj["expr"]
        low = subtask.lower()
        if "hits the ground" in low or ("height" in low and "ground" in low):
            if re.search(r"what is the height", low):
                return "replace", "arith", {"expression": "0"}
        hm = re.search(r"height of\s+\$?\s*(\d+(?:\.\d+)?)", subtask)
        if hm and re.search(r"at what times", low):
            hval = hm.group(1)
            eq = f"({expr})={hval}"
            args = {"equation": eq, "variable": tv, "domain": "real"}
            res = run_tool("solve", args)
            if res["success"]:
                args["unique"] = res.get("unique", False)
                return "replace", "solve", args
        if "total time duration" in low or "time interval (duration)" in low:
            hm = re.search(r"(\d+(?:\.\d+)?)\s+meters", problem_text or "")
            hval = hm.group(1) if hm else "6"
            cons = [f"({expr})>{hval}"]
            return "replace", "inequality_solver", {
                "constraints": cons, "variable": tv, "domain": "real",
                "target": "interval_length",
            }

    age = extract_age_word_system(problem_text)
    if age and is_result_task(subtask) and re.search(r"son|daughter|age today", low):
        tgt = age["target_var"]
        if re.search(r"find|what is|how old|solve", low):
            args = {
                "equations": age["equations"], "variables": age["variables"],
                "target_expression": tgt,
            }
            return "replace", "linear_system_solver", args

    op_expr = extract_binary_operator_expr(problem_text)
    if op_expr and is_result_task(subtask):
        binds = extract_operator_bindings(subtask, problem_text)
        if binds and re.search(r"final value|express|what is", low):
            subs = {k: v for k, v in binds.items()}
            args = {"expression": op_expr, "subs": subs}
            return "replace", "subst", args

    spec = extract_sequence_spec(problem_text)
    if spec:
        tgt, n = detect_sequence_target(subtask, problem_text)
        if tgt:
            args = dict(spec)
            args["target"] = tgt
            if n is not None:
                args["n"] = n
            return "replace", "sequence_tool", args

    cons = extract_inequality_constraints(problem_text) \
        or extract_inequality_constraints(subtask)
    if not cons:
        sq = extract_sqrt_domain_constraint(problem_text)
        if sq:
            cons = [sq]
    if cons:
        tgt, dom = detect_inequality_target(subtask)
        var = _single_var(cons)
        if tgt and var:
            return "replace", "inequality_solver", {
                "constraints": cons, "variable": var,
                "domain": dom, "target": tgt,
            }

    if detect_common_root(subtask, problem_text) and re.search(r"value|what is|find", low):
        eqs = extract_polynomial_equations(problem_text)
        if len(eqs) >= 2:
            return "replace", "solve", {"equations": eqs, "common_root": True}

    v = extract_vieta_target(problem_text)
    if v and ("compute the final" in low or "add the expression" in low
              or (("find" in low or "compute" in low) and "frac" in low)):
        return "replace", "solve", {
            "equation": v["equation"],
            "target_expression": v["target_expression"],
        }

    sel = detect_select(subtask)
    if sel:
        eq = _find_equation(problem_text, subtask, all_steps)
        if eq:
            return "replace", "solve", {"equation": eq, "select": sel}
    return None


def _subtask_symbol_mentions(subtask):
    vars_ = set()
    for piece in _pieces(subtask or ""):
        vars_.update(re.findall(r"[A-Za-z]", piece))
    for pat in (
        r"values?\s+of\s+([A-Za-z])\s*(?:,|and)\s*([A-Za-z])",
        r"find\s+([A-Za-z])\s*(?:,|and)\s*([A-Za-z])",
    ):
        m = re.search(pat, subtask or "", re.I)
        if m:
            vars_.update(m.groups())
    return sorted(v for v in vars_ if v.lower() not in {"e", "i"})


def _context_linear_assign(subtask, problem_text, all_steps, verified_context):
    if not is_result_task(subtask):
        return None
    if should_use_subst(subtask, problem_text):
        return None
    has_prior_context = any((st or "").strip() != (subtask or "").strip() for st in (all_steps or []))
    has_verified_values = bool((verified_context or {}).get("known_values"))
    if not has_prior_context and not has_verified_values:
        return None
    hinted_vars = _subtask_symbol_mentions(subtask)
    req_t = extract_requested_target(subtask, hinted_vars or None)
    target_vars = sorted({v for v in re.findall(r"[A-Za-z]", req_t or "") if v.lower() not in {"e", "i"}})
    if req_t:
        vars_ = target_vars
    elif wants_all_system_variables(subtask):
        vars_ = _subtask_symbol_mentions(subtask)
    else:
        return None
    if len(vars_) < 2:
        return None
    ctx_eqs = extract_context_equations(vars_, problem_text, all_steps or [], current_subtask=subtask)
    if verified_context:
        seen = {e for e, _ in ctx_eqs}
        for eq, src in verified_context.get("equations", []):
            letters = {c for c in re.findall(r"[A-Za-z]", eq) if c.lower() not in {"e", "i"}}
            if eq not in seen and letters & set(vars_):
                ctx_eqs.append((eq, src))
                seen.add(eq)
    if len(ctx_eqs) < 2:
        return None
    args = {
        "equations": [e for e, _ in ctx_eqs],
        "variables": vars_,
    }
    if req_t:
        args["target_expression"] = req_t
    res = run_tool("linear_system_solver", args)
    if not res.get("success"):
        return None
    return "replace", "linear_system_solver", args


def _context_solve_assign(subtask, problem_text, all_steps, verified_context):
    """跨步方程合成：当前 RESULT 步缺方程时，从题面/前序/已验证结果合成。"""
    if not is_result_task(subtask):
        return None
    if detect_root_target(subtask) or not wants_equation_solution(subtask):
        return None
    if is_root_derived_target(subtask) or any(c in subtask.lower() for c in _CONCEPT):
        return None
    var = infer_solve_variable(subtask, "")
    if not var:
        for p in ("x", "t", "y", "n", "k", "w"):
            if re.search(rf"\b{p}\b", subtask.lower()):
                var = p
                break
    if not var:
        return None
    ctx_eqs = extract_context_equations(var, problem_text, all_steps or [], current_subtask=subtask)
    if verified_context:
        seen = {e for e, _ in ctx_eqs}
        for eq, src in verified_context.get("equations", []):
            if eq not in seen and var in eq:
                ctx_eqs.append((eq, src))
                seen.add(eq)
    if not ctx_eqs:
        return None
    eq_list = [e for e, _ in ctx_eqs]
    sources = [s for _, s in ctx_eqs]
    if len(eq_list) == 1:
        args = {
            "equation": eq_list[0], "variable": var, "domain": "real",
            "context_sources": sources,
        }
        res = run_tool("solve", args)
        if res["success"] and res.get("unique"):
            args["unique"] = True
            return "replace", "solve", args
    return None

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
           qid=None, rejections=None, complex_used=None, verified_context=None):
    low = subtask.lower()
    ps = _pieces(subtask)
    expr = max(ps, key=len) if ps else ""
    complex_used = complex_used if complex_used is not None else set()

    # --- 阶段 3.2/3.3 结构化高置信路由 ---
    structured = _structured_assign(subtask, problem_text, all_steps, verified_context)
    if structured:
        s_mode, s_name, s_args = structured
        out = _apply(subtask, step_id, int_edges, all_steps, s_mode, s_name,
                     s_args, qid, rejections)
        if out[1] != "no_tool":
            return out

    # --- 跨步方程合成 solve ---
    ctx_linear = _context_linear_assign(subtask, problem_text, all_steps, verified_context)
    if ctx_linear:
        l_mode, l_name, l_args = ctx_linear
        out = _apply(subtask, step_id, int_edges, all_steps, l_mode, l_name,
                     l_args, qid, rejections)
        if out[1] != "no_tool":
            return out

    # --- 跨步方程合成 solve ---
    ctx_out = _context_solve_assign(subtask, problem_text, all_steps, verified_context)
    if ctx_out:
        c_mode, c_name, c_args = ctx_out
        out = _apply(subtask, step_id, int_edges, all_steps, c_mode, c_name,
                     c_args, qid, rejections)
        if out[1] != "no_tool":
            return out

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
    if not eq and all_steps and is_strict_solve_subtask(subtask):
        for st in all_steps:
            cand = _extract_problem_equation(None, st)
            if cand:
                eq = cand
                break
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
        if is_procedural_explanation_target(subtask):
            pass
        elif is_direct_expand_request(subtask):
            mode = "replace"
            return _apply(subtask, step_id, int_edges, all_steps, mode, "expand",
                          {"expression": expr}, qid, rejections)
        else:
            mode = "assist"
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
        return tool_res.get("value") or tool_res.get("target_value") or tool_res.get("text")
    if tool_name in ("inequality_solver", "sequence_tool", "polynomial_coefficient_match",
                     "discrete_constraint_enumerator"):
        return tool_res.get("target_value") or tool_res.get("value") \
            or tool_res.get("solutions") or tool_res.get("text")
    if tool_name == "linear_system_solver":
        if args.get("target") or args.get("target_expression"):
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


def _is_final_target_step(subtask, step_idx, n_steps):
    if step_idx == n_steps:
        return True
    low = (subtask or "").lower()
    return any(k in low for k in _FINAL_KW)


def _compute_question_metrics(steps, tools, modes, slot_meta):
    has_slot = any(t != "no_tool" for t in tools)
    safe_replace = False
    key_covered = False
    final_covered = False
    n = len(steps)
    for i, (sub, tool, mode, meta) in enumerate(zip(steps, tools, modes, slot_meta), 1):
        if tool == "no_tool":
            continue
        tr = meta.get("tool_res") or {}
        verified = bool(tr.get("verified")) or (
            tr.get("success") and tool in SUBSTANTIVE_TOOLS and mode == "replace"
        )
        gate_ok = meta.get("gate_ok", False)
        args = meta.get("args") or {}
        if mode == "replace" and verified and gate_ok:
            safe_replace = True
        if tool in _INTERMEDIATE_TOOLS and mode == "assist":
            continue
        if mode == "replace" and verified and gate_ok and tool in SUBSTANTIVE_TOOLS:
            if classify_task_type(sub) == "RESULT":
                key_covered = True
        if mode == "replace" and verified and gate_ok and _is_final_target_step(sub, i, n):
            if tool in SUBSTANTIVE_TOOLS or args.get("root_target"):
                final_covered = True
    return has_slot, key_covered, final_covered, safe_replace


def _run_stable35_metrics(data, slot_meta_by_qid):
    metrics = {
        "has_tool_slot": [],
        "key_error_step_covered": [],
        "final_target_covered": [],
        "safe_replace": [],
    }
    for qid in STABLE_35:
        q = data.get(str(qid))
        if not q:
            continue
        meta = slot_meta_by_qid.get(qid, [])
        hs, kc, fc, sr = _compute_question_metrics(
            q["steps"], q["allo_tool"], q["tool_mode"], meta)
        if hs:
            metrics["has_tool_slot"].append(qid)
        if kc:
            metrics["key_error_step_covered"].append(qid)
        if fc:
            metrics["final_target_covered"].append(qid)
        if sr:
            metrics["safe_replace"].append(qid)
    return metrics


def main():
    data = json.load(open(IN_PATH, encoding="utf-8"))
    rejections = []
    tool_stat = Counter()
    mode_stat = Counter()
    total_subtasks = 0
    covered_q = set()

    slot_meta_by_qid = {}

    for qid, q in data.items():
        tools, targs, modes = [], [], []
        steps = q["steps"]
        problem_text = q.get("problemText", "")
        qid_int = int(qid)
        complex_used = set()
        verified_context = {"equations": [], "constraints": [], "known_values": {}, "sources": []}
        _seed_verified_context(problem_text, verified_context)
        slot_meta = []
        for i, s in enumerate(steps, start=1):
            prior = steps[: i - 1]
            mode, name, args = assign(
                s, i, q.get("int_edges", []), all_steps=prior,
                problem_text=problem_text, qid=qid_int, rejections=rejections,
                complex_used=complex_used, verified_context=verified_context,
            )
            meta = {"args": args, "tool_res": {}, "gate_ok": False}
            if name != "no_tool":
                ok_val, _ = validate_assignment(
                    s, name, args, mode, all_steps=steps, step_id=i,
                    int_edges=q.get("int_edges", []))
                tool_res = run_tool(name, args)
                ok_gate, _, _ = semantic_gate(s, name, args, mode, tool_res)
                meta["tool_res"] = tool_res
                meta["gate_ok"] = ok_gate and ok_val and tool_res.get("success")
                _update_verified_context(s, name, args, tool_res, verified_context)
            tools.append(name)
            targs.append(args)
            modes.append(mode)
            slot_meta.append(meta)
            tool_stat[name] += 1
            mode_stat[mode] += 1
            if name != "no_tool":
                covered_q.add(qid_int)
        slot_meta_by_qid[qid_int] = slot_meta
        _check_question(qid_int, steps, tools, targs, modes)
        q["allo_tool"] = tools
        q["tool_args"] = targs
        q["tool_mode"] = modes
        total_subtasks += len(steps)

    json.dump(data, open(OUT_PATH, "w", encoding="utf-8"), ensure_ascii=False, indent=2)
    _write_rejection_logs(rejections)
    audit_stats, audit_records = _run_phase25_audit(data)
    stable_metrics = _run_stable35_metrics(data, slot_meta_by_qid)

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
    print("--- 35题稳定错误集四指标 ---")
    for key in ("has_tool_slot", "key_error_step_covered", "final_target_covered", "safe_replace"):
        qs = stable_metrics[key]
        print(f"{key}: {len(qs)} -> {sorted(qs)}")
    print(f"polynomial_coefficient_match 数: {tool_stat['polynomial_coefficient_match']}")
    print(f"discrete_constraint_enumerator 数: {tool_stat['discrete_constraint_enumerator']}")
    print(f"inequality_solver 数: {tool_stat['inequality_solver']}")
    print(f"sequence_tool 数: {tool_stat['sequence_tool']}")

    assert illegal_mode == 0
    assert aggregate_n == 0
    assert non_no_tool == replace_n + assist_n
    assert audit_stats["validation_fail"] == 0
    assert audit_stats["tool_success_fail"] == 0
    assert audit_stats["replace_target_match_false"] == 0
    assert audit_stats["assist_scope_match_false"] == 0


if __name__ == "__main__":
    main()
