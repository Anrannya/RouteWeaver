# -*- coding: utf-8 -*-
"""Phase 2.5 工具分配语义集成测试（通用规则，无题号硬编码）"""
import os
import sys

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, BASE)

from build_with_tool import assign
from tools.math_tools import tool_solve, tool_subst, tool_linear_system_solver
from tools.target_utils import (
    extract_requested_target,
    should_use_linear_system,
    should_use_subst,
    text_has_nonlinear_system,
)
from tools.validate_assignment import validate_assignment


def _assign(subtask, problem_text=""):
    mode, name, args = assign(subtask, 1, [], [subtask], problem_text=problem_text)
    return mode, name, args


def test_case1_y_squared():
    sub = "What is the value of \\( y^2 \\) when \\( y = 9 \\)?"
    sa = should_use_subst(sub)
    assert sa is not None
    r = tool_subst(sa)
    assert r["success"] and r["result"] == "81"
    mode, name, args = _assign(sub)
    assert name == "subst" and mode == "replace"
    ok, _ = validate_assignment(sub, "subst", args, "replace")
    assert ok
    ok2, reason = validate_assignment(sub, "solve", {"equation": "y=9", "variable": "y", "unique": True}, "replace")
    assert not ok2 and "表达式" in reason


def test_case2_2x_minus_y():
    sub = "What is the value of \\(2x - y\\) when \\(x = 4\\) and \\(y = 3\\)?"
    sa = should_use_subst(sub)
    assert sa is not None
    assert tool_subst(sa)["result"] == "5"
    mode, name, _ = _assign(sub)
    assert name == "subst" and mode == "replace"


def test_case3_24_minus_expr():
    sub = "What is the value of \\(24 - (2x - y)\\) when \\(x = 4\\) and \\(y = 3\\)?"
    sa = should_use_subst(sub)
    assert sa is not None
    assert tool_subst(sa)["result"] == "19"
    mode, name, _ = _assign(sub)
    assert name == "subst" and mode == "replace"


def test_case4_linear_3xy():
    sub = "What is the value of \\(3xy\\)?"
    prob = "Given \\(2x - 3y = 8\\) and \\(4x + 3y = -2\\)."
    la = should_use_linear_system(sub, prob)
    assert la and la.get("target") == "3*x*y"
    r = tool_linear_system_solver(la)
    assert r["success"] and r["value"] == "-6"
    mode, name, args = _assign(sub, prob)
    assert name == "linear_system_solver" and args.get("target") == "3*x*y"


def test_case5_linear_2x_minus_xy():
    sub = "What is the value of \\(2x - xy\\)?"
    prob = "Solve \\(x + y = 12\\) and \\(x - y = 8\\)."
    la = should_use_linear_system(sub, prob)
    assert la and la.get("target")
    r = tool_linear_system_solver(la)
    assert r["success"]
    mode, name, args = _assign(sub, prob)
    assert name == "linear_system_solver"
    assert args.get("target")


def test_case6_function_transform():
    sub = "What transformations are applied to \\(y=f(x)\\)?"
    prob = "The graph of \\(y=\\frac{1}{4}f\\left(\\frac{1}{2}x\\right)\\)."
    assert text_has_nonlinear_system(prob)
    assert should_use_linear_system(sub, prob) is None
    mode, name, _ = _assign(sub, prob)
    assert name != "linear_system_solver"


def test_case7_inverse_sqrt():
    sub = "What is the relationship between $y$ and $\\sqrt x$?"
    prob = "$y$ varies inversely as $\\sqrt x$, and when $x=24$, $y=15$."
    assert text_has_nonlinear_system(prob)
    assert should_use_linear_system(sub, prob) is None
    mode, name, _ = _assign(sub, prob)
    assert name != "linear_system_solver"


def test_case8_subst_not_solve():
    sub = "What is the value of \\( \\frac{x^3 + 72}{2} \\) when \\( x = 6 \\)?"
    sa = should_use_subst(sub)
    assert sa is not None
    assert tool_subst(sa)["result"] == "144"
    mode, name, _ = _assign(sub)
    assert name == "subst"
    assert name != "solve"


def test_case9_complex_foil_dedup():
    prob = "Simplify \\((3-i)(6+2i)\\)."
    steps = [
        "How do you apply FOIL to \\((3-i)(6+2i)\\)?",
        "How do you combine the real and imaginary parts?",
        "What is the final simplified expression?",
        "What is the final simplified expression?",
    ]
    complex_used = set()
    results = []
    for i, s in enumerate(steps, 1):
        mode, name, args = assign(s, i, [], steps, problem_text=prob, complex_used=complex_used)
        results.append((name, mode))
    assert results[0][0] != "complex_arithmetic" or results[0][1] != "replace"
    replace_count = sum(1 for n, m in results if n == "complex_arithmetic" and m == "replace")
    assert replace_count == 1


def test_case10_solve_domain():
    r = tool_solve({"equation": "x**2+1=0", "variable": "x", "domain": "real"})
    assert not r["success"]
    r = tool_solve({"equation": "x**2+1=0", "variable": "x", "domain": "complex"})
    assert r["success"]
    assert set(r["solutions"]) == {"I", "-I"} or set(r["solutions"]) == {"-I", "I"}


def test_target_extraction():
    t = extract_requested_target("What is \\(y^2\\)?", ["y"])
    assert t == "y**2" or t == "y^2" or "y" in t
    t2 = extract_requested_target("What is \\(2*x-y\\)?", ["x", "y"])
    assert t2 is not None


def test_case11_root_sum_no_solve():
    from tools.target_utils import is_root_derived_target
    sub = "What is the sum of the roots of a quadratic equation?"
    prob = "Solve \\(2x(x-10)=-50\\)."
    assert is_root_derived_target(sub)
    mode, name, _ = _assign(sub, prob)
    assert name == "no_tool"
    ok, reason = validate_assignment(
        sub, "solve", {"equation": "2*x*(x-10)=-50", "variable": "x", "unique": True}, "assist"
    )
    assert not ok and "派生" in reason


if __name__ == "__main__":
    test_case1_y_squared()
    test_case2_2x_minus_y()
    test_case3_24_minus_expr()
    test_case4_linear_3xy()
    test_case5_linear_2x_minus_xy()
    test_case6_function_transform()
    test_case7_inverse_sqrt()
    test_case8_subst_not_solve()
    test_case9_complex_foil_dedup()
    test_case10_solve_domain()
    test_case11_root_sum_no_solve()
    test_target_extraction()
    print("all phase25 semantics tests passed")
