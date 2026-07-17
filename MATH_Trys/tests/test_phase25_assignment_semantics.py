# -*- coding: utf-8 -*-
"""
工具分配不变量测试（题目级 final_tool + 子任务级收紧版）。

只断言与设计对应的"契约"，不含题号硬编码：
  1) 子任务级正例：单方程单未知数→solve replace；subst 闭合数值→replace；双方程+目标→linear replace。
  2) 裁撤反例：expand/factor/simplify/arith/complex 不再产出任何分配；概念题→no_tool。
  3) 题目级正例：不等式组/数列/多点定多项式/multiples 四类结构 → final_tool 且 verified。
  4) 全局不变量（对生成的 with_tool.json）：
     - 每个子任务级 replace 必为 solve/linear(verified) 或 subst(闭合数值)；assist 仅 solve/linear。
     - 每个 final_tool 复跑必须 success+verified 且答案一致。

运行：cd MATH_Trys && python tests/test_phase25_assignment_semantics.py（无需 pytest）
"""
import json
import os
import sys

import sympy as sp

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, BASE)

from build_with_tool import assign, build_final_tool
from tools import run_tool


def _assign(subtask, problem_text=""):
    return assign(subtask, 1, [], [subtask], problem_text)


# ---------- 子任务级 ----------
def test_solve_single_equation_replace():
    mode, name, _ = _assign(r"Solve for \(x\): \(2x + 6 = 10\). What is the value of \(x\)?")
    assert name == "solve" and mode == "replace"


def test_subst_value_when_is_numeric_replace():
    mode, name, args = _assign(r"What is the value of \(3xy\) when \(x = 3\) and \(y = 9\)?")
    assert name == "subst" and mode == "replace"
    v = sp.sympify(str(run_tool(name, args)["result"]))
    assert v.is_number and not v.free_symbols


def test_linear_system_target_replace():
    mode, name, _ = _assign(
        r"Given \(a + b = 6\) and \(a - b = 2\), what is the value of \(a\)?")
    assert name == "linear_system_solver" and mode == "replace"


def test_symbolic_transform_assists_removed():
    for sub in (r"Expand the expression \((x + 1)^2\).",
                r"Factor the expression \(x^2 + x - 6\).",
                r"Simplify \(\frac{x^2-1}{x-1}\).",
                r"What is the simplified form of \(17^6 - 17^5\)?"):
        mode, name, _ = _assign(sub)
        assert name == "no_tool" and mode == "no_tool", f"{sub} -> {name}/{mode}"


def test_conceptual_subtask_no_tool():
    mode, name, _ = _assign("Explain the strategy for solving this problem step by step.")
    assert name == "no_tool" and mode == "no_tool"


# ---------- 题目级 final_tool ----------
def test_final_inequalities():
    ft = build_final_tool(
        r"Find the sum of all integers that satisfy these conditions: \[|x|+1>7\text{ and }|x+1|\le7.\]")
    assert ft and ft["tool"] == "inequality_solver" and ft["verified"]
    assert ft["answer"] == "-15"


def test_final_sequence_nth_term():
    ft = build_final_tool(
        r"Consider the geometric sequence $\frac{125}{9}, \frac{25}{3}, 5, 3, \ldots$. "
        r"What is the eighth term of the sequence?")
    assert ft and ft["tool"] == "sequence_tool" and ft["answer"] == "243/625"


def test_final_points_polynomial():
    ft = build_final_tool(
        r"A parabola $ax^2+bx+c$ contains the points $(-1,0)$, $(0,5)$, and $(5,0)$. "
        r"Find the value $100a+10b+c$.")
    assert ft and ft["tool"] == "linear_system_solver" and ft["answer"] == "-55"


def test_final_multiples():
    ft = build_final_tool("What is the sum of all of the multiples of 3 between 100 and 200?")
    assert ft and ft["tool"] == "discrete_constraint_enumerator" and ft["answer"] == "4950"


def test_final_none_for_plain_problem():
    assert build_final_tool("Describe the graph of a generic quadratic function.") is None


# ---------- 全局不变量 ----------
def test_global_invariants():
    path = os.path.join(BASE, "TmpRes/step2In_MATH_with_tool.json")
    if not os.path.exists(path):
        return  # 需先运行 build_with_tool.py
    data = json.load(open(path, encoding="utf-8"))
    for qid, rec in data.items():
        for t, a, m in zip(rec["allo_tool"], rec["tool_args"], rec["tool_mode"]):
            if m == "no_tool":
                continue
            assert t in ("solve", "linear_system_solver", "subst"), f"Q{qid} 非法工具 {t}"
            r = run_tool(t, a)
            if m == "replace":
                if t == "subst":
                    v = sp.sympify(str(r.get("result")))
                    assert v.is_number and not v.free_symbols, f"Q{qid} subst replace 非闭合数值"
                else:
                    assert r.get("success") and r.get("verified"), f"Q{qid} {t} replace 未验证"
            else:
                assert t != "subst" and r.get("verified"), f"Q{qid} {t} assist 未验证"
        ft = rec.get("final_tool")
        if ft:
            r = run_tool(ft["tool"], ft["args"])
            assert r.get("success") and r.get("verified"), f"Q{qid} final_tool 复跑未验证"
            fval = (r.get(ft.get("answer_key") or "result")
                    or r.get("target_value") or r.get("value") or r.get("result"))
            assert str(fval) == str(ft["answer"]), f"Q{qid} final_tool 答案不一致"


if __name__ == "__main__":
    fns = [v for k, v in sorted(globals().items()) if k.startswith("test_") and callable(v)]
    failed = 0
    for fn in fns:
        try:
            fn()
            print(f"PASS  {fn.__name__}")
        except Exception as e:
            failed += 1
            print(f"FAIL  {fn.__name__}: {e}")
    print(f"\n{len(fns) - failed}/{len(fns)} passed")
    sys.exit(1 if failed else 0)
