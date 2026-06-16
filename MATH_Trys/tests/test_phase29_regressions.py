# -*- coding: utf-8 -*-
"""Phase 2.9 回归：过程型 expand 禁止、独立 Judge、离线冲突审计"""
import json
import os
import sys
import tempfile

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, BASE)

from build_with_tool import assign
from tools.validate_assignment import validate_assignment
from tools.target_utils import is_direct_expand_request, is_procedural_explanation_target
from audit_paired_judge import audit_pairs
from compare_judge import normalize_final_answer


def _assign(subtask, problem_text=""):
    return assign(subtask, 1, [], [subtask], problem_text=problem_text)


def test_case1_direct_expand_replace():
    sub = "Expand the expression \\((2x+5)(x-3)\\)."
    mode, name, _ = _assign(sub)
    assert name == "expand" and mode == "replace"


def test_case2_expanded_form_replace():
    sub = "What is the expanded form of \\((2x+5)(x-3)\\)?"
    assert is_direct_expand_request(sub)
    mode, name, _ = _assign(sub)
    assert name == "expand" and mode == "replace"


def test_case3_procedural_expand_no_tool():
    sub = "How can we expand the expression \\((2x+5)(x-3)\\)?"
    assert is_procedural_explanation_target(sub)
    mode, name, _ = _assign(sub)
    assert name == "no_tool"
    ok, _ = validate_assignment(sub, "expand", {"expression": "(2x+5)(x-3)"}, "assist")
    assert not ok


def test_case4_explain_expand_no_tool():
    sub = "Explain the steps for expanding \\((2x+5)(x-3)\\)."
    assert is_procedural_explanation_target(sub)
    mode, name, _ = _assign(sub)
    assert name == "no_tool"


def test_case5_independent_judge_no_reuse_in_compare():
    src = open(os.path.join(BASE, 'MATH_dotrun_step2_compare.py'), encoding='utf-8').read()
    assert 'judge_cache=judge_cache' not in src
    assert 'judge_reuse_enabled' in src and 'False' in src.split('judge_reuse_enabled')[1][:20]


def test_case6_offline_conflict_audit():
    pairs = [{
        'qid': 130, 'round': 1,
        'no_tool_correct': False, 'with_tool_correct': True,
        'no_tool_final': '-22', 'with_tool_final': '  -22 ',
        'no_tool_error': None, 'with_tool_error': None,
    }]
    report = audit_pairs(pairs)
    assert report['same_final_judge_conflict_count'] == 1
    assert 130 in report['same_final_judge_conflict_qids']
    assert report['raw_wrong_to_right'] == 1
    assert report['audited_wrong_to_right'] == 0
    assert normalize_final_answer('-22') == normalize_final_answer('  -22  ')


def test_case7_different_final_kept():
    pairs = [{
        'qid': 26, 'round': 1,
        'no_tool_correct': True, 'with_tool_correct': False,
        'no_tool_final': '0.5', 'with_tool_final': '1',
        'no_tool_error': None, 'with_tool_error': None,
    }]
    report = audit_pairs(pairs)
    assert report['same_final_judge_conflict_count'] == 0
    assert report['raw_right_to_wrong'] == 1
    assert report['audited_right_to_wrong'] == 1


# ============================================================
# 阶段 3.2：增强 solve / linear / inequality / sequence + 分配语义 + 反泄漏
# ============================================================
import re as _re
from tools.math_tools import run_tool
from tools.target_utils import (
    classify_task_type, extract_sequence_spec, detect_sequence_target,
    extract_inequality_constraints, extract_sqrt_domain_constraint,
    extract_vieta_target, extract_parabola_point_system, detect_common_root,
)


# ---- solve ----
def test_solve_select_minimum():
    r = run_tool("solve", {"equation": "x**2-5*x+6=0", "select": "minimum"})
    assert r["success"] and r["value"] == "2" and r["verified"]


def test_solve_parameter():
    r = run_tool("solve", {"equation": "2*k+6=0", "variable": "k"})
    assert r["success"] and r["value"] == "-3"


def test_solve_target_expression():
    r = run_tool("solve", {"equation": "2*x**2-7*x+2=0",
                           "target_expression": "1/(a-1)+1/(b-1)"})
    assert r["success"] and r["target_value"] == "-1" and r["verified"]


def test_solve_common_root():
    r = run_tool("solve", {"equations": ["18*x**2+25*x-3=0", "4*x**2+8*x+3=0"],
                           "common_root": True})
    assert r["success"] and r["value"] == "-3/2"


def test_solve_no_common_root():
    r = run_tool("solve", {"equations": ["x**2-1=0", "x-2=0"], "common_root": True})
    assert not r["success"]


def test_solve_multi_common_root_complete():
    # x^2-1=0 与 x^3-x=0 公共根应同时含 1 与 -1，不得遗漏
    r = run_tool("solve", {"equations": ["x**2-1=0", "x**3-x=0"], "common_root": True})
    assert r["success"] and set(r["solutions"]) == {"1", "-1"}


def test_solve_domain_filter():
    r = run_tool("solve", {"equation": "x**2-2=0", "domain": "integer"})
    assert not r["success"]
    r = run_tool("solve", {"equation": "(x-4)*(x+1/2)=0", "domain": "integer"})
    assert r["success"] and r["solutions"] == ["4"]


# ---- linear_system_solver ----
def test_linear_2x2_target():
    r = run_tool("linear_system_solver", {
        "equations": ["2*x-3*y=8", "4*x+3*y=-2"], "variables": ["x", "y"],
        "target_expression": "x*y"})
    assert r["success"] and r["target_value"] == "-2" and r["verified"]


def test_linear_3x3_target():
    r = run_tool("linear_system_solver", {
        "equations": ["a+b+c=6", "4*a+2*b+c=11", "9*a+3*b+c=18"],
        "variables": ["a", "b", "c"], "target_expression": "100*a+10*b+c"})
    assert r["success"] and r["verified"]


def test_linear_underdetermined_reject():
    r = run_tool("linear_system_solver", {
        "equations": ["x+y=1", "2*x+2*y=2"], "variables": ["x", "y"]})
    assert not r["success"]


def test_linear_inconsistent_reject():
    r = run_tool("linear_system_solver", {
        "equations": ["x+y=1", "x+y=2"], "variables": ["x", "y"]})
    assert not r["success"]


def test_linear_nonlinear_reject():
    r = run_tool("linear_system_solver", {
        "equations": ["x**2+y=1", "x+y=0"], "variables": ["x", "y"]})
    assert not r["success"]


# ---- inequality_solver ----
def test_ineq_basic():
    r = run_tool("inequality_solver", {"constraints": ["x>=2", "x<=7"],
                                       "variable": "x", "target": "interval_length"})
    assert r["success"] and r["target_value"] == "5"


def test_ineq_absolute():
    r = run_tool("inequality_solver", {"constraints": ["abs(x-3)<=5"],
                                       "variable": "x", "domain": "integer",
                                       "target": "count"})
    assert r["success"] and r["target_value"] == "11"  # -2..8 共 11 个整数


def test_ineq_intersection_sum():
    r = run_tool("inequality_solver", {"constraints": ["abs(x)+1>7", "abs(x+1)<=7"],
                                       "variable": "x", "domain": "integer",
                                       "target": "sum"})
    assert r["success"] and r["target_value"] == "-15"
    assert r["integer_values"] == [-8, -7]


def test_ineq_min_max_integer():
    r = run_tool("inequality_solver", {"constraints": ["abs(x-3)<=5", "x>0"],
                                       "variable": "x", "domain": "integer",
                                       "target": "maximum_integer"})
    assert r["success"] and r["target_value"] == "8"
    r = run_tool("inequality_solver", {"constraints": ["abs(x-3)<=5", "x>0"],
                                       "variable": "x", "domain": "integer",
                                       "target": "minimum_integer"})
    assert r["success"] and r["target_value"] == "1"


def test_ineq_empty():
    r = run_tool("inequality_solver", {"constraints": ["x>5", "x<2"],
                                       "variable": "x", "domain": "integer",
                                       "target": "sum"})
    assert r["success"] and r.get("empty")


def test_ineq_unbounded_sum_reject():
    r = run_tool("inequality_solver", {"constraints": ["x>0"], "variable": "x",
                                       "domain": "integer", "target": "sum"})
    assert not r["success"]


def test_ineq_real_minimum():
    r = run_tool("inequality_solver", {"constraints": ["(x-3)**2-(x-8)**2>=0"],
                                       "variable": "x", "target": "minimum"})
    assert r["success"] and r["target_value"] == "11/2"


# ---- sequence_tool ----
def test_seq_arithmetic_nth():
    r = run_tool("sequence_tool", {"sequence_type": "arithmetic", "first_term": "1000",
                                   "difference": "-13", "target": "nth_term", "n": 3})
    assert r["success"] and r["value"] == "974"


def test_seq_geometric_nth():
    r = run_tool("sequence_tool", {"sequence_type": "geometric", "first_term": "125/9",
                                   "ratio": "3/5", "target": "nth_term", "n": 8})
    assert r["success"] and r["value"] == "243/625"


def test_seq_partial_sum():
    r = run_tool("sequence_tool", {"sequence_type": "arithmetic", "first_term": "1",
                                   "difference": "1", "target": "partial_sum", "n": 10})
    assert r["success"] and r["value"] == "55"


def test_seq_last_positive():
    r = run_tool("sequence_tool", {"sequence_type": "arithmetic", "first_term": "1000",
                                   "difference": "-13",
                                   "target": "last_positive_integer_index"})
    assert r["success"] and r["value"] == "77"


def test_seq_bad_n():
    r = run_tool("sequence_tool", {"sequence_type": "geometric", "first_term": "3",
                                   "ratio": "2", "target": "nth_term", "n": 0})
    assert not r["success"]


def test_seq_missing_param():
    r = run_tool("sequence_tool", {"sequence_type": "arithmetic", "first_term": "5",
                                   "target": "nth_term", "n": 3})
    assert not r["success"]


# ---- 分配语义 ----
def test_task_type_classification():
    assert classify_task_type("What is the value of the eighth term?") == "RESULT"
    assert classify_task_type("How do we expand this expression?") == "PROCEDURE"
    assert classify_task_type("Explain why this holds.") == "EXPLANATION"
    assert classify_task_type("Prove that the sum is even.") == "PROOF"


def test_result_allows_replace_procedure_rejected():
    ok_r, _ = validate_assignment("What is the factored form of \\(x^2-1\\)?",
                                  "factor", {"expression": "x^2-1"}, "replace")
    assert ok_r
    ok_p, _ = validate_assignment("How do we factor \\(x^2-1\\)?",
                                  "factor", {"expression": "x^2-1"}, "replace")
    assert not ok_p


def test_target_mismatch_downgrades():
    # 子任务问“sum of integers”，但工具只给区间端点 -> 应被拒绝/降级
    ok, _ = validate_assignment(
        "What is the sum of all integers that satisfy the condition?",
        "inequality_solver",
        {"constraints": ["x>0"], "variable": "x"}, "replace")
    assert not ok  # 缺 target，参数不完整


# ---- 通用提取（无题号、无全文匹配）----
def test_general_extractors():
    assert extract_sequence_spec(
        "the geometric sequence $3, 6, 12, \\ldots$")["sequence_type"] == "geometric"
    assert detect_sequence_target("What is the eighth term?")[0] == "nth_term"
    cons = extract_inequality_constraints("$|x|+1>7 \\text{ and } |x+1|\\le7$")
    assert len(cons) == 2
    assert extract_sqrt_domain_constraint("$\\sqrt{x-3}$") is not None
    assert detect_common_root("what is the common solution", "satisfies both equations")


# ============================================================
# 阶段 3.3：root_target / 系数匹配 / 离散枚举 / 跨步合成
# ============================================================
from tools.target_utils import (
    detect_root_target, extract_context_equations, extract_polynomial_identity,
    extract_discrete_domains, wants_equation_solution, extract_trajectory_model,
    extract_age_word_system, extract_operator_bindings,
)


def test_root_target_sum():
    r = run_tool("solve", {"equation": "x**2-5*x+6=0", "root_target": "sum", "domain": "real"})
    assert r["success"] and r["target_value"] == "5" and r["verified"]


def test_root_target_product():
    r = run_tool("solve", {"equation": "x**2-5*x+6=0", "root_target": "product", "domain": "real"})
    assert r["success"] and r["target_value"] == "6"


def test_root_target_sum_of_squares():
    r = run_tool("solve", {"equation": "x**2-x-6=0", "root_target": "sum_of_squares", "domain": "real"})
    assert r["success"] and r["target_value"] == "13"


def test_root_target_reciprocals_reject_zero():
    r = run_tool("solve", {"equation": "x*(x-3)=0", "root_target": "sum_of_reciprocals", "domain": "real"})
    assert not r["success"]


def test_root_target_positive_difference():
    r = run_tool("solve", {"equation": "x**2-5*x+6=0", "root_target": "positive_difference", "domain": "real"})
    assert r["success"] and r["target_value"] == "1"


def test_root_target_absolute_difference_and_count():
    r = run_tool("solve", {"equation": "x**2-5*x+6=0", "root_target": "absolute_difference", "domain": "real"})
    assert r["success"] and r["target_value"] == "1"
    r = run_tool("solve", {"equation": "x**2-5*x+6=0", "root_target": "count", "domain": "real"})
    assert r["success"] and r["target_value"] == "2"


def test_root_target_domain_filter_complete():
    r = run_tool("solve", {"equation": "(x-4)*(x+1/2)=0", "root_target": "sum", "domain": "integer"})
    assert r["success"] and r["roots"] == ["4"] and r["target_value"] == "4"


def test_poly_coeff_match_linear():
    r = run_tool("polynomial_coefficient_match", {
        "left_expression": "a*(x+b)**2+c", "right_expression": "4*x**2+2*x-1",
        "polynomial_variable": "x", "unknowns": ["a", "b", "c"], "target_expression": "a+b+c",
    })
    assert r["success"] and r["target_value"] == "3" and r["verified"]


def test_poly_coeff_match_nonlinear():
    r = run_tool("polynomial_coefficient_match", {
        "left_expression": "(x+a)*(x+b)", "right_expression": "x**2+5*x+6",
        "polynomial_variable": "x", "unknowns": ["a", "b"], "target_expression": "a*b",
    })
    assert r["success"] and r["target_value"] == "6" and r["verified"]


def test_poly_coeff_match_nonunique_reject():
    r = run_tool("polynomial_coefficient_match", {
        "left_expression": "a*x+b", "right_expression": "x+2",
        "polynomial_variable": "x", "unknowns": ["a", "b", "c"], "target_expression": "a+b+c",
    })
    assert not r["success"]


def test_poly_coeff_match_nonpoly_reject():
    r = run_tool("polynomial_coefficient_match", {
        "left_expression": "a*x+b", "right_expression": "sin(x)",
        "polynomial_variable": "x", "unknowns": ["a", "b"], "target_expression": "a+b",
    })
    assert not r["success"]


def test_discrete_prime_enum():
    r = run_tool("discrete_constraint_enumerator", {
        "variables": ["p", "q"],
        "domains": {"p": {"type": "prime", "minimum": 2, "maximum": 100},
                    "q": {"type": "prime", "minimum": 2, "maximum": 100}},
        "constraints": ["p+q=20"], "target_expression": "p*q", "aggregation": "all_values",
    })
    assert r["success"] and r["verified"]


def test_discrete_unbounded_reject():
    r = run_tool("discrete_constraint_enumerator", {
        "variables": ["x"], "domains": {"x": {"type": "integer"}},
        "constraints": ["x>0"], "target_expression": "x", "aggregation": "sum",
    })
    assert not r["success"]


def test_discrete_finite_values_unique_value():
    r = run_tool("discrete_constraint_enumerator", {
        "variables": ["x", "y"],
        "domains": {
            "x": {"type": "finite_values", "values": [1, 2, 3]},
            "y": {"type": "finite_values", "values": [4, 5, 6]},
        },
        "constraints": ["x+y=7"],
        "target_expression": "x+y",
        "aggregation": "unique_value",
    })
    assert r["success"] and r["target_value"] == "7" and len(r["solutions"]) == 3


def test_discrete_search_space_reject():
    r = run_tool("discrete_constraint_enumerator", {
        "variables": ["a", "b", "c"],
        "domains": {
            "a": {"type": "integer", "minimum": 1, "maximum": 50},
            "b": {"type": "integer", "minimum": 1, "maximum": 50},
            "c": {"type": "integer", "minimum": 1, "maximum": 50},
        },
        "constraints": ["a+b+c=12"],
        "target_expression": "a*b*c",
        "aggregation": "sum",
    })
    assert not r["success"]


def test_context_equations_prior_subtask():
    prob = "For what value of $x$ will fractions be equal?"
    prior = ["What equation when \\(\\frac{2x-1}{2x+2} = \\frac{x-3}{x-1}\\)?"]
    eqs = extract_context_equations("x", prob, prior)
    assert eqs and eqs[0][1] == "prior_subtask"


def test_context_equations_current_subtask_and_irrelevant_filtered():
    prob = "Solve for $x$ given \\(x+3=9\\)."
    prior = ["Find the perimeter of a square with side length 2."]
    eqs = extract_context_equations("x", prob, prior, current_subtask="What is \\(x\\) if \\(x+3=9\\)?")
    assert any(src == "current_subtask" for _, src in eqs)
    assert all("perimeter" not in eq.lower() for eq, _ in eqs)


def test_context_solve_assign():
    prob = "For what value of $x$ will fractions be equal?"
    steps = [
        "What equation when \\(\\frac{2x-1}{2x+2} = \\frac{x-3}{x-1}\\)?",
        "How to eliminate fractions?",
        "Steps to simplify?",
        "Excluded values?",
        "What is the value of \\(x\\) that satisfies the equation?",
    ]
    mode, name, args = assign(steps[-1], 5, [], steps[:-1], problem_text=prob)
    assert name == "solve" and mode == "replace" and args.get("variable") == "x"


def test_context_linear_assign_from_prior_equations():
    prob = "Find \\(A\\) and \\(B\\)."
    steps = [
        "From coefficient comparison, we get \\(A+B=4\\).",
        "Also, \\(-5A-3B=0\\).",
        "What are the values of \\(A\\) and \\(B\\) that satisfy the system?",
    ]
    mode, name, _ = assign(steps[-1], 3, [], steps[:-1], problem_text=prob)
    assert name == "linear_system_solver" and mode == "replace"


def test_context_linear_insufficient_equations_downgrades():
    prob = "Find \\(A\\) and \\(B\\)."
    steps = [
        "From coefficient comparison, we get \\(A+B=4\\).",
        "What are the values of \\(A\\) and \\(B\\) that satisfy the system?",
    ]
    mode, name, _ = assign(steps[-1], 2, [], steps[:-1], problem_text=prob)
    assert name == "no_tool"


def test_radical_root_form_target_assign():
    prob = "The solutions to $(x+1)(x+2)=x+3$ can be written in the form $m+\\sqrt n$ and $m-\\sqrt n$. What is $m+n$?"
    sub = "What is \\(m+n\\)?"
    mode, name, args = assign(sub, 1, [], [], problem_text=prob)
    assert name == "solve" and mode == "replace"
    assert args.get("target_expression") == "(a+b)/2 + ((a-b)/2)**2"


def test_prime_root_values_assign():
    prob = ("Suppose the roots of the polynomial $x^2-mx+n$ are positive prime integers. "
            "Given that $m<20$, what are the possible values of $n$?")
    sub = "For each possible pair of prime roots, what is the resulting value of \\(n\\)?"
    mode, name, args = assign(sub, 1, [], [], problem_text=prob)
    assert name == "discrete_constraint_enumerator" and mode == "replace"
    assert args["aggregation"] == "all_values"
    assert args["target_expression"] == "p*q"


def test_bulk_discount_condition_assign():
    prob = ("If you buy up to 60 tickets in one order, the price for each ticket is $70$. "
            "If you buy more than 60 tickets, the price of every ticket is reduced by $1 "
            "for each additional ticket bought. If $t$ is the number of tickets bought, "
            "what is the largest $t$ which will bring a profit greater than $4200$?")
    sub = "What is the condition on \\(t\\) such that the revenue is greater than \\(4200\\)?"
    mode, name, args = assign(sub, 1, [], [], problem_text=prob)
    assert name == "inequality_solver" and mode == "replace"
    assert args["target"] == "solution_set"
    assert args["domain"] == "positive_integer"


def test_detect_root_target_sum_phrase():
    assert detect_root_target("What is the sum of the roots?") == "sum"


def test_detect_root_target_count_phrase():
    assert detect_root_target("How many real roots does the equation have?") == "count"


def test_trajectory_model_extract():
    m = extract_trajectory_model("The height $h(t) = -4.9t^2 + 14t - 0.4$ of a cannonball.")
    assert m and m["time_var"] == "t"


def test_age_word_system_extract():
    sys = extract_age_word_system(
        "Today a father's age is five times his son's age. "
        "Exactly three years ago, the sum of their ages was 30.")
    assert sys and len(sys["equations"]) == 2


def test_operator_bindings_extract():
    b = extract_operator_bindings("What is the final value of \\(3 \\star 11\\)?", "")
    assert b == {"a": "3", "b": "11"}


def test_wants_equation_solution_cross_step():
    assert wants_equation_solution("What is the value of \\(x\\) that satisfies the equation?")


def test_validate_context_source_rejects_illegal_source():
    ok, _ = validate_assignment(
        "What is the value of \\(x\\)?",
        "solve",
        {"equation": "x+1=3", "variable": "x", "context_sources": ["llm_answer"], "unique": True},
        "replace",
    )
    assert not ok


def test_validate_discrete_search_space_rejects_large_domain():
    ok, _ = validate_assignment(
        "What is the sum of all possible values?",
        "discrete_constraint_enumerator",
        {
            "variables": ["a", "b", "c"],
            "domains": {
                "a": {"type": "integer", "minimum": 1, "maximum": 50},
                "b": {"type": "integer", "minimum": 1, "maximum": 50},
                "c": {"type": "integer", "minimum": 1, "maximum": 50},
            },
            "constraints": ["a+b+c=12"],
            "target_expression": "a*b*c",
            "aggregation": "sum",
        },
        "replace",
    )
    assert not ok


# ---- 反泄漏静态扫描（仅工具/分配/执行/答案路径，排除 Judge 评价路径）----
def test_no_leakage_in_tool_chain():
    files = [
        "tools/math_tools.py", "tools/target_utils.py",
        "tools/validate_assignment.py", "build_with_tool.py",
    ]
    forbidden = [
        r"if\s+qid\s*==", r"TOOL_BY_QID", r"PRECOMPUTED",
        r"problem\s*==\s*['\"]",
    ]
    for fp in files:
        src = open(os.path.join(BASE, fp), encoding="utf-8").read()
        for pat in forbidden:
            assert not _re.search(pat, src), f"{fp} 命中疑似泄漏: {pat}"


def test_no_gold_access_in_assignment_path():
    # 工具选择/参数构造路径不得读取 gold / 标准答案数据集
    # 注：linear_system_solver 自身输出含 solution 映射字段，属合法工具结果
    for fp in ["tools/math_tools.py", "tools/target_utils.py",
               "tools/validate_assignment.py", "build_with_tool.py"]:
        src = open(os.path.join(BASE, fp), encoding="utf-8").read()
        assert "gold" not in src.lower()
        assert "all_math_p" not in src
        # 不得从题目字典读取 solution 字段
        assert not _re.search(r"problems?\b[^\n]*\[['\"]solution['\"]\]", src)


if __name__ == '__main__':
    test_case1_direct_expand_replace()
    test_case2_expanded_form_replace()
    test_case3_procedural_expand_no_tool()
    test_case4_explain_expand_no_tool()
    test_case5_independent_judge_no_reuse_in_compare()
    test_case6_offline_conflict_audit()
    test_case7_different_final_kept()
    print('all phase29 regression tests passed')
