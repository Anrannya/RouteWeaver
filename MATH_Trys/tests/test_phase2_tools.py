# -*- coding: utf-8 -*-
"""Phase2 工具单元测试：solve / complex_arithmetic / linear_system_solver"""
import os
import sys

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, BASE)

from tools.math_tools import tool_solve, tool_complex_arithmetic, tool_linear_system_solver
from tools.validate_assignment import validate_assignment


def _must_ok(fn, args):
    r = fn(args)
    assert r["success"], f"expected success, got {r}"
    return r


def _must_fail(fn, args):
    r = fn(args)
    assert not r["success"], f"expected fail, got {r}"
    return r


def test_solve():
    r = _must_ok(tool_solve, {"equation": "2*x+3=11", "variable": "x"})
    assert r["unique"] and r["value"] == "4" and r["text"] == "x = 4"

    r = _must_ok(tool_solve, {"equation": "(x-5)**2=0", "variable": "x"})
    assert r["unique"] and r["value"] == "5"

    r = _must_ok(tool_solve, {"equation": "x**2-5*x+6=0", "variable": "x"})
    assert not r["unique"] and set(r["solutions"]) == {"2", "3"}

    _must_fail(tool_solve, {"equation": "x=x+1", "variable": "x"})
    _must_fail(tool_solve, {"equation": "x+y=1", "variable": "x"})
    _must_fail(tool_solve, {"equation": "2*x+", "variable": "x"})
    _must_fail(tool_solve, {"equation": "", "variable": "x"})


def test_complex():
    r = _must_ok(tool_complex_arithmetic, {"expression": "(3-1*I)+(2+4*I)"})
    assert "5" in r["text"] and "3" in r["text"]

    r = _must_ok(tool_complex_arithmetic, {"expression": "(5-3*I)*(-4+3*I)"})
    assert r["text"] == "-11 + 27i"
    assert r["real_part"] == "-11" and r["imag_part"] == "27"

    r = _must_ok(tool_complex_arithmetic, {"expression": "I**2"})
    assert r["text"] == "-1"

    r = _must_ok(tool_complex_arithmetic, {"expression": "(2+3*I)*(2-3*I)"})
    assert r["text"] == "13"

    _must_fail(tool_complex_arithmetic, {"expression": "(a+3*I)*2"})
    _must_fail(tool_complex_arithmetic, {"expression": "2+3"})
    _must_fail(tool_complex_arithmetic, {"expression": "(((("})


def test_linear_system():
    r = _must_ok(tool_linear_system_solver, {
        "equations": ["2*x-3*y=8", "4*x+3*y=-2"],
        "variables": ["x", "y"],
    })
    assert r["solution"]["x"] == "1" and r["solution"]["y"] == "-2"

    r = _must_ok(tool_linear_system_solver, {
        "equations": ["2*x-3*y=8", "4*x+3*y=-2"],
        "variables": ["x", "y"],
        "target": "x*y",
    })
    assert r["value"] == "-2"

    _must_fail(tool_linear_system_solver, {
        "equations": ["x+y=1", "x+y=2"],
        "variables": ["x", "y"],
    })
    _must_fail(tool_linear_system_solver, {
        "equations": ["x+y=1", "2*x+2*y=2"],
        "variables": ["x", "y"],
    })
    _must_fail(tool_linear_system_solver, {"equations": ["x=1"], "variables": ["x"]})
    _must_fail(tool_linear_system_solver, {
        "equations": ["x**2+y=1", "x+y=0"],
        "variables": ["x", "y"],
    })
    _must_fail(tool_linear_system_solver, {
        "equations": ["x=1", "y=2"],
        "variables": [],
    })


def test_validate_q44_q191():
    ok, _ = validate_assignment(
        "What is the improper fraction form of 1 1/6?",
        "arith", {"expression": "(1+(1)/(6))"}, "replace",
    )
    assert ok

    # Q191 型：表达式对 x 恒等化简为常数 361，arith 合法
    ok, reason = validate_assignment(
        "What is the simplified form of the entire expression?",
        "arith", {"expression": "49x^2 + 14x(19 - 7x) + (19 - 7x)^2"}, "replace",
    )
    assert ok, reason


if __name__ == "__main__":
    test_solve()
    test_complex()
    test_linear_system()
    test_validate_q44_q191()
    print("all tests passed")
