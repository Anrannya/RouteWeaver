# -*- coding: utf-8 -*-
"""Injection environment: a faithful, injection-capable replica of the DoT
CSQA_dotrun_step2.py sub-question solving loop.

This is the GRPO environment. `solve(qid, inject_subq, inject_final)` walks the
reasoning DAG node by node; at chosen nodes it appends the KB evidence hint to the
prompt. Because an injected node's answer is stored and fed to downstream nodes,
early injection changes later states -> genuine sequential (MDP) behaviour.

Knowledge evidence comes from the existing retriever + validator on the MAIN
question/options. We only inject when the validator ACCEPTS (high-precision gate).
"""

from __future__ import annotations

import json
import os
import re
import sys
from typing import Any, Dict, List, Optional, Set

CSQA_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
TOOLS_DIR = os.path.join(CSQA_DIR, "tools", "csqa_tools")
sys.path.insert(0, CSQA_DIR)
sys.path.insert(0, TOOLS_DIR)

from csqa_kb_retriever import CSQAKBRetriever  # noqa: E402
from csqa_knowledge_validator import CSQAKnowledgeValidator  # noqa: E402
from protocol import canonical_depths, model_for_step  # noqa: E402

DATA_PATH = os.path.join(CSQA_DIR, "..", "Task_Datasets", "CSQA", "train_rand_split.jsonl")
DAG_PATH = os.path.join(CSQA_DIR, "TmpRes", "step2In_csqa_last.json")


def load_questions() -> List[Dict[str, Any]]:
    rows = []
    with open(os.path.abspath(DATA_PATH), "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                rows.append(json.loads(line))
    return rows


def load_dag() -> Dict[str, Any]:
    return json.load(open(DAG_PATH, "r", encoding="utf-8"))


def search_predecessors(int_edges: List[List[int]], node: int) -> List[int]:
    return [a for a, b in int_edges if b == node]


def extract_letter(text: str) -> Optional[str]:
    m = re.search(r"\b([A-E])\b", (text or "").upper())
    return m.group(1) if m else None


class InjectionEnv:
    def __init__(self, backend, retriever: Optional[CSQAKBRetriever] = None,
                 validator: Optional[CSQAKnowledgeValidator] = None):
        self.backend = backend
        self.retriever = retriever or CSQAKBRetriever()
        self.validator = validator or CSQAKnowledgeValidator()
        self.questions = load_questions()
        self.dag = load_dag()
        self._evidence_cache: Dict[int, Dict[str, Any]] = {}

    # ---------- knowledge evidence (retriever + validator on main question) ----------
    def build_evidence(self, qid: int) -> Dict[str, Any]:
        if qid in self._evidence_cache:
            return self._evidence_cache[qid]
        entry = self.questions[qid]
        stem = entry["question"]["stem"]
        choices = [{"label": c["label"], "text": c["text"]} for c in entry["question"]["choices"]]
        cands = self.retriever.retrieve(stem, choices)
        val = self.validator.validate(stem, choices, cands)
        ev: Dict[str, Any] = {"status": val["status"], "hint": None, "supported_option": None,
                              "_cands": cands, "_val": val}
        if val["status"] == "accepted":
            facts = val.get("supporting_facts", [])
            opt = val["supported_option"]
            opt_text = next((c["text"] for c in choices if c["label"] == opt), "")
            bullet = "\n".join(f"- {f['fact']}" for f in facts)
            ev["supported_option"] = opt
            ev["hint"] = (
                "\n\nRelevant background knowledge:\n"
                f"{bullet}\n"
                f"This evidence points to option {opt} ({opt_text})."
            )
        self._evidence_cache[qid] = ev
        return ev

    def build_forced_hint(self, qid: int, mode: str = "bestguess", top_k: int = 3) -> Optional[str]:
        """Build an injection hint EVEN WHEN the validator abstained, from the top
        retrieved candidate facts. Used to measure the abstain rescue space.
        mode='facts'    -> only the facts, no option claim.
        mode='bestguess'-> facts + a soft pointer to the validator's internally
                           highest-scoring option.
        """
        entry = self.questions[qid]
        choices = [{"label": c["label"], "text": c["text"]} for c in entry["question"]["choices"]]
        ev = self.build_evidence(qid)
        cands = ev["_cands"][:top_k]
        if not cands:
            return None
        bullet = "\n".join(f"- {c['fact']}" for c in cands)
        hint = "\n\nRelevant background knowledge:\n" + bullet
        if mode == "bestguess":
            best = None
            for fe in ev["_val"].get("fact_evaluations", []):
                if best is None or fe.get("top1_score", 0) > best.get("top1_score", 0):
                    best = fe
            if best and best.get("top_option"):
                opt = best["top_option"]
                opt_text = next((c["text"] for c in choices if c["label"] == opt), "")
                hint += f"\nThese clues may point to option {opt} ({opt_text})."
        else:
            hint += "\nUse this knowledge to help choose the best option."
        return hint

    def key_subq_node(self, qid: int) -> Optional[int]:
        rec = self.dag[str(qid)]
        steps = rec.get("steps_dict") or {}
        if not steps:
            return None
        return max(int(k) for k in steps.keys())

    # ---------- core: solve one question under an injection plan ----------
    def solve(self, qid: int, inject_subq: Optional[Set[int]] = None,
              inject_final: bool = False, max_tokens: int = 300,
              override_hint: Optional[str] = None) -> Dict[str, Any]:
        inject_subq = inject_subq or set()
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

        ev = self.build_evidence(qid)
        # override_hint forces injection even on abstain questions (rescue measurement).
        hint = override_hint if override_hint is not None else ev["hint"]

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
        trajectory: List[Dict[str, Any]] = []
        Q: List[Dict[str, str]] = []
        last_result = ""

        # Depth keys are zero-based and inclusive.  The historical
        # ``range(max(depths))`` loop silently skipped the terminal layer.
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

                do_inject = (number in inject_subq) and bool(hint)
                if do_inject:
                    query = query + hint

                Q = [{"role": "system", "content": sys_q},
                     {"role": "user", "content": query}]
                result = self.backend.chat(Q, model=answer_model, max_tokens=max_tokens)
                answerDict[number] = {"subtask": subtask, "answer": result}
                last_result = result
                trajectory.append({"node": number, "subtask": subtask,
                                   "injected": do_inject, "answer": result})

        expected = {
            int(re.findall(r"\d+", subtaskid)[0])
            for layer in depths.values()
            for subtaskid in layer
        }
        missing = expected.difference(answerDict)
        if missing:
            raise RuntimeError(f"Incomplete DAG execution; missing steps: {sorted(missing)}")

        # final summary
        Q.append({"role": "assistant", "content": last_result})
        final_user = (
            "Now that all the sub-questions have been solved, which answer do you ultimately choose?\n"
            "Please provide only the letter of the option, without any additional explanation or description."
        )
        if inject_final and hint:
            final_user = final_user + hint
        Q.append({"role": "user", "content": final_user})

        final_model = self._final_model()
        final_raw = self.backend.chat(Q, model=final_model, max_tokens=max_tokens)
        final_letter = extract_letter(final_raw)
        correct = (final_letter == gold)

        return {
            "qid": qid, "gold": gold, "final_letter": final_letter, "correct": correct,
            "evidence_status": ev["status"], "evidence_option": ev["supported_option"],
            "injected_subq": sorted(inject_subq) if hint else [],
            "injected_final": bool(inject_final and hint),
            "trajectory": trajectory,
        }

    @staticmethod
    def _final_model() -> str:
        cfg_path = os.path.join(CSQA_DIR, "CSQA_config.json")
        try:
            return json.load(open(cfg_path))["finalSummarize_MODEL"]
        except Exception:
            return "gpt-4-turbo"
