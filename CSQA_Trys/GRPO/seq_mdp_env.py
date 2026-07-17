# -*- coding: utf-8 -*-
"""路线 C —— 真正的「序贯 MDP」注入环境（不改动 A/B 任何代码）。

与路线 A/B 的本质区别：
  * A/B：事前一次性给定整套注入方案（哪个位置注、哪个不注），属于（多臂）老虎机。
  * C ：沿 DoT 的推理链「逐节点」决策——在每个决策节点先观察状态，再决定注/不注，
        被注入节点的答案会写入 answerDict 并喂给后续节点，**前一步真实改变后一步的状态**。
        末端用最终答案对错作为回报。这才是教科书意义的多步序贯决策（MDP）。

实现方式：子类化现有 InjectionEnv，复用它的检索器/验证器/build_forced_hint，
但用一套**逐节点**的 rollout 替代父类「事前计划」的 solve()。父类一行不动。

决策节点的选取（用于把枚举树规模控制住，同时保持「序贯」）：
  按 DoT 的真实求解顺序展开所有子问题节点；取**最靠后的 (dmax-1) 个子问题**
  以及**最终总结**作为决策节点（这些是最影响最终答案的枢纽），更早的子问题强制不注入。
  这样每题决策点数 = dmax（默认 3），仍是「连续多步、状态向后传递」的真 MDP。

注入用的知识统一来自 build_forced_hint(qid, 'bestguess')（题级证据）；若该题检索不到
任何候选知识，则无注入动作可选，该题退化为单条「全不注入」轨迹。
"""

from __future__ import annotations

import re
from typing import Any, Dict, List, Optional, Tuple

from injection_env import InjectionEnv, extract_letter, search_predecessors
from protocol import canonical_depths, model_for_step

FINAL = "FINAL"  # 最终总结决策节点的哨兵


class SequentialInjectionEnv(InjectionEnv):
    # ---------- 推理链结构 ----------
    def solve_order(self, qid: int) -> List[int]:
        """DoT 真实求解顺序下的子问题节点 id 列表（与 InjectionEnv.solve 完全一致）。"""
        rec = self.dag[str(qid)]
        depths = canonical_depths(rec)
        order: List[int] = []
        for i in sorted(depths):
            for subtaskid in sorted(depths[i]):
                num = re.findall(r"\d+", subtaskid)
                order.append(int(num[0]) if num else None)
        return order

    def decision_nodes(self, qid: int, dmax: int = 3) -> Tuple[List[int], List[Any]]:
        """返回 (全部求解顺序 order, 决策节点列表 decisions)。
        decisions = 末尾 (dmax-1) 个子问题 + FINAL；无可注入知识时 decisions 为空。"""
        order = self.solve_order(qid)
        hint = self.build_forced_hint(qid, mode="bestguess")
        if not hint:
            return order, []
        n_subq_dec = max(0, dmax - 1)
        dec_subq = order[-n_subq_dec:] if n_subq_dec > 0 else []
        decisions: List[Any] = list(dec_subq) + [FINAL]
        return order, decisions

    # ---------- 决策时刻可观察的状态特征（动作发生前即可得，不偷看结果） ----------
    def node_state(self, qid: int, is_final: bool, dec_index: int, total_dec: int,
                   n_inject_so_far: int) -> List[float]:
        ev = self.build_evidence(qid)
        val = ev["_val"]
        fevals = val.get("fact_evaluations", []) or []
        top1 = [fe.get("top1_score", 0.0) for fe in fevals]
        margins = [fe.get("margin", 0.0) for fe in fevals]
        bg = None
        for fe in fevals:
            if bg is None or fe.get("top1_score", 0) > bg.get("top1_score", 0):
                bg = fe
        return [
            1.0,                                                   # bias
            1.0 if is_final else 0.0,                              # 是否最终节点
            dec_index / max(total_dec, 1),                         # 在决策序列中的进度
            1.0 if val.get("status") == "accepted" else 0.0,       # 验证器是否接受
            float(max(top1)) if top1 else 0.0,                     # 最高 top1 置信
            float(max(margins)) if margins else 0.0,               # 最大区分度
            len(val.get("conflicting_options", []) or []) / 5.0,   # 冲突选项数
            1.0 if (bg and bg.get("top_option")) else 0.0,         # 是否有 best-guess
            n_inject_so_far / max(total_dec, 1),                   # 已用注入比例（随轨迹变化）
            (total_dec - dec_index) / max(total_dec, 1),           # 剩余预算比例
        ]

    FEATURE_DIM = 10

    # ---------- 逐节点 rollout：沿链求解，按 action_bits 在决策节点决定注/不注 ----------
    def rollout(self, qid: int, decisions: List[Any], action_bits: List[int],
                max_tokens: int = 300) -> Dict[str, Any]:
        """action_bits 与 decisions 一一对应（0/1）。返回最终对错、注入次数、
        以及每个决策节点 (state, action) —— state 在决策当下按轨迹历史计算。"""
        entry = self.questions[qid]
        question = entry["question"]["stem"]
        options = entry["question"]["choices"]
        gold = entry["answerKey"]
        options_string = "; ".join(f"{c['label']}: {c['text']}" for c in options)

        rec = self.dag[str(qid)]
        steps_dict = rec["steps_dict"]
        allo_model = rec["allo_model"]
        depths = canonical_depths(rec)
        int_edges = rec["int_edges"]

        hint = self.build_forced_hint(qid, mode="bestguess")
        dec_lookup = {node: bit for node, bit in zip(decisions, action_bits)}
        total_dec = len(decisions)

        sys_q = (
            "There is a single-choice question involving common sense reasoning. "
            "I need you to solve it and give the right answer.\n"
            f"Here is the question:\n{question} \n"
            f"Here are the options: \n{options_string}\n\n"
            "I have broken this common sense reasoning question down into several smaller "
            "questions. I will assign you sub-questions one by one, and provide the results "
            "of the previous sub-questions as a reference for your reasoning."
        )

        answerDict: Dict[int, Dict[str, str]] = {}
        Q: List[Dict[str, str]] = []
        last_result = ""
        n_inject = 0
        steps_record: List[Dict[str, Any]] = []   # 每个决策节点的 (state, action)
        dec_index = 0

        for i in sorted(depths):
            for subtaskid in sorted(depths[i]):
                num = re.findall(r"\d+", subtaskid)
                number = int(num[0]) if num else None
                subtask = steps_dict[str(number)]
                answer_model = model_for_step(rec, number)

                if answerDict:
                    answersSoFar = (
                        "\nSo far, the answers to the resolved sub-questions are as follows: "
                        "The format is Sub-question-Id: xxx; Sub-question: xxx; Answer: xxx."
                    )
                    for key in answerDict:
                        answersSoFar += (
                            f"\nSub-question-Id: {key}; Sub-question: {answerDict[key]['subtask']}; "
                            f"Answer: {answerDict[key]['answer']}."
                        )
                    predecessors = search_predecessors(int_edges, number)
                    if set(answerDict.keys()).intersection(predecessors):
                        answersSoFar += (
                            f"\nAmong them, sub-questions {predecessors} are directly related to "
                            "this sub-question, so please pay special attention to them."
                        )
                else:
                    answersSoFar = ""

                subask = (
                    f"\nThe sub-question to solve now is xxx: {subtask}\n"
                    "Based on the information above, please provide a concise and clear answer"
                )
                query = (answersSoFar + subask) if answerDict else subask

                if number in dec_lookup:
                    state = self.node_state(qid, False, dec_index, total_dec, n_inject)
                    act = int(dec_lookup[number]) if hint else 0
                    if act:
                        query = query + hint
                        n_inject += 1
                    steps_record.append({"node": number, "is_final": False,
                                         "state": state, "action": act})
                    dec_index += 1

                Q = [{"role": "system", "content": sys_q},
                     {"role": "user", "content": query}]
                result = self.backend.chat(Q, model=answer_model, max_tokens=max_tokens)
                answerDict[number] = {"subtask": subtask, "answer": result}
                last_result = result

        expected = set(self.solve_order(qid))
        missing = expected.difference(answerDict)
        if missing:
            raise RuntimeError(f"Incomplete DAG execution; missing steps: {sorted(missing)}")

        # 最终总结节点
        Q.append({"role": "assistant", "content": last_result})
        final_user = (
            "Now that all the sub-questions have been solved, which answer do you ultimately choose?\n"
            "Please provide only the letter of the option, without any additional explanation or description."
        )
        if FINAL in dec_lookup:
            state = self.node_state(qid, True, dec_index, total_dec, n_inject)
            act = int(dec_lookup[FINAL]) if hint else 0
            if act:
                final_user = final_user + hint
                n_inject += 1
            steps_record.append({"node": FINAL, "is_final": True,
                                 "state": state, "action": act})
            dec_index += 1
        Q.append({"role": "user", "content": final_user})

        final_raw = self.backend.chat(Q, model=self._final_model(), max_tokens=max_tokens)
        final_letter = extract_letter(final_raw)
        correct = (final_letter == gold)

        return {
            "qid": qid, "gold": gold, "final_letter": final_letter,
            "correct": bool(correct), "n_inject": n_inject, "steps": steps_record,
        }
