# -*- coding: utf-8 -*-
"""Phase 2.8 回归：概念型拒绝、展开语义、Judge 复用、hash 一致性"""
import os
import sys

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, BASE)
sys.path.insert(0, os.path.join(BASE, '..'))

from build_with_tool import assign
from tools.validate_assignment import validate_assignment
from tools.target_utils import (
    blocks_numeric_replace,
    is_conceptual_subtask,
    is_direct_expand_request,
    is_process_expand_subtask,
    should_use_subst,
)
from compare_judge import judge_with_cache, normalize_final_answer, stable_hash


def _assign(subtask, problem_text=""):
    mode, name, args = assign(subtask, 1, [], [subtask], problem_text=problem_text)
    return mode, name, args


def test_case1_conceptual_subst_rejected():
    sub = "What does inverse proportionality mean?"
    prob = "If j and k are inversely proportional and j=16 when k=21, find j when k=14."
    assert is_conceptual_subtask(sub)
    assert should_use_subst(sub, prob) is None
    mode, name, args = _assign(sub, prob)
    assert name == "no_tool"
    ok, reason = validate_assignment(
        sub, "subst", {"expression": "k", "subs": {"k": "14"}}, "replace",
    )
    assert not ok and "概念" in reason


def test_case2_explicit_subst_allowed():
    sub = "What is the value of \\(2x - y\\) when \\(x = 4\\) and \\(y = 3\\)?"
    sa = should_use_subst(sub)
    assert sa is not None
    mode, name, _ = _assign(sub)
    assert name == "subst" and mode == "replace"


def test_case3_direct_expand_replace():
    sub = "Expand the expression \\((2x+5)(x-3)\\)."
    assert is_direct_expand_request(sub)
    assert not is_process_expand_subtask(sub)
    mode, name, _ = _assign(sub)
    assert name == "expand" and mode == "replace"


def test_case4_process_expand_no_replace():
    sub = "How can we expand the expression \\((2x+5)(x-3)\\)?"
    assert is_process_expand_subtask(sub)
    assert not is_direct_expand_request(sub)
    mode, name, _ = _assign(sub)
    assert name == "no_tool"
    ok, reason = validate_assignment(sub, "expand", {"expression": "(2x+5)(x-3)"}, "assist")
    assert not ok


def test_case5_same_final_judge_reused():
    cache = {}
    calls = []

    def fake_ask(*_a, **_k):
        calls.append(1)
        return "True"

    r1, ok1, reused1 = judge_with_cache("q", "gold", "-22", fake_ask, "gpt", None, 0, 130, cache)
    r2, ok2, reused2 = judge_with_cache("q", "gold", "  -22  ", fake_ask, "gpt", None, 0, 130, cache)
    assert ok1 and ok2
    assert reused1 is False and reused2 is True
    assert len(calls) == 1
    assert normalize_final_answer("-22") == normalize_final_answer("  -22  ")


def test_case6_different_final_separate_judge():
    cache = {}
    calls = []

    def fake_ask(*_a, **_k):
        calls.append(1)
        return "False" if len(calls) == 1 else "True"

    judge_with_cache("q", "gold", "1", fake_ask, "gpt", None, 0, 1, cache)
    _, _, reused = judge_with_cache("q", "gold", "2", fake_ask, "gpt", None, 0, 1, cache)
    assert reused is False
    assert len(calls) == 2


def test_case7_no_tool_branch_hash_helpers():
    p1 = {'model': 'm', 'temperature': 0, 'system': 's', 'user': 'u'}
    p2 = {'temperature': 0, 'model': 'm', 'system': 's', 'user': 'u'}
    assert stable_hash(p1) == stable_hash(p2)


def test_q72_step1_blocked():
    sub = "What does it mean for j and k to be inversely proportional?"
    assert is_conceptual_subtask(sub)
    assert blocks_numeric_replace(sub, "subst")
    mode, name, _ = _assign(sub, "If j and k are inversely proportional...")
    assert name == "no_tool"


if __name__ == "__main__":
    test_case1_conceptual_subst_rejected()
    test_case2_explicit_subst_allowed()
    test_case3_direct_expand_replace()
    test_case4_process_expand_no_replace()
    test_case5_same_final_judge_reused()
    test_case6_different_final_separate_judge()
    test_case7_no_tool_branch_hash_helpers()
    test_q72_step1_blocked()
    print("all phase28 regression tests passed")
