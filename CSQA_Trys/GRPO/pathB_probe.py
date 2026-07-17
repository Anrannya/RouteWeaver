# -*- coding: utf-8 -*-
"""Path B (minimal probe): does the INJECTION POSITION along the reasoning chain
change the outcome? This is the make-or-break test for the sequential (MDP) GRPO.

Every CSQA question here is multi-step (3-5 sub-questions with dependency edges),
so injecting knowledge at an upstream node changes that sub-answer, which then
feeds downstream nodes. If the final answer is *sensitive* to WHERE we inject, the
sequential formulation carries signal that the single-step (path A) bandit cannot;
if positions are interchangeable, path B collapses to path A and we report that.

Unlike compare_injection_positions.py (which only injects ACCEPTED evidence), this
probe uses the FORCED best-guess hint so injection is defined on every question,
including abstained ones (where the headroom lives).

Conditions (same forced hint, only the position differs):
  * no_inject     : never inject (DoT baseline)
  * inject_first  : inject only at the earliest sub-question node
  * inject_last   : inject only at the terminal decision sub-question node
  * inject_final  : inject only at the final-summary prompt
  * inject_all    : inject at every sub-question node

Sub-question calls run on the local model (cheap); only the final summary hits the
remote model. Cached & temperature=0, so re-runs are free.

    cd CSQA_Trys && python GRPO/pathB_probe.py --limit 40 --backend real
    cd CSQA_Trys && python GRPO/pathB_probe.py --limit 20 --backend mock   # plumbing only
"""

from __future__ import annotations

import argparse
import json
import os
from datetime import datetime

from injection_env import InjectionEnv
from llm_backend import LLMBackend

LOG_ROOT = os.path.join(os.path.dirname(__file__), "Logs", "pathB_probe")
CONDITIONS = ["no_inject", "inject_first", "inject_last", "inject_final", "inject_all"]
POSITION_CONDS = ["inject_first", "inject_last", "inject_final"]  # same dose, different place


def first_node(env: InjectionEnv, qid: int):
    rec = env.dag[str(qid)]
    keys = [int(k) for k in rec["steps_dict"].keys()]
    return min(keys) if keys else None


def run_condition(env: InjectionEnv, qid: int, condition: str, hint):
    if condition == "no_inject" or hint is None:
        return env.solve(qid, inject_subq=set(), inject_final=False)
    if condition == "inject_final":
        return env.solve(qid, inject_subq=set(), inject_final=True, override_hint=hint)
    if condition == "inject_first":
        node = first_node(env, qid)
        return env.solve(qid, inject_subq={node} if node is not None else set(),
                         inject_final=False, override_hint=hint)
    if condition == "inject_last":
        node = env.key_subq_node(qid)
        return env.solve(qid, inject_subq={node} if node is not None else set(),
                         inject_final=False, override_hint=hint)
    if condition == "inject_all":
        rec = env.dag[str(qid)]
        nodes = {int(k) for k in rec["steps_dict"].keys()}
        return env.solve(qid, inject_subq=nodes, inject_final=False, override_hint=hint)
    raise ValueError(condition)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--limit", type=int, default=40)
    ap.add_argument("--backend", choices=["real", "mock"], default="real")
    args = ap.parse_args()

    backend = LLMBackend(backend=args.backend, temperature=0.0)
    env = InjectionEnv(backend)
    n = min(args.limit, len(env.questions))

    ts = datetime.now().strftime("%Y-%m-%d-%H-%M-%S")
    out_dir = os.path.join(LOG_ROOT, ts)
    os.makedirs(out_dir, exist_ok=True)

    per_q = []
    correct = {c: 0 for c in CONDITIONS}
    pos_sensitive = 0          # final answer differs across POSITION_CONDS
    pos_sensitive_among_inject = 0  # among inject conds only (excludes no_inject effect)
    for qid in range(n):
        hint = env.build_forced_hint(qid, mode="bestguess")
        row = {"qid": qid, "gold": env.questions[qid]["answerKey"],
               "evidence_status": env.build_evidence(qid)["status"],
               "n_nodes": len(env.dag[str(qid)]["steps_dict"]),
               "has_hint": hint is not None}
        finals = {}
        for c in CONDITIONS:
            res = run_condition(env, qid, c, hint)
            row[c] = {"final": res["final_letter"], "correct": res["correct"]}
            correct[c] += int(res["correct"])
            finals[c] = res["final_letter"]
        # position sensitivity: same knowledge dose, different placement -> different answer?
        pos_answers = {finals[c] for c in POSITION_CONDS}
        if len(pos_answers) > 1:
            pos_sensitive += 1
            if hint is not None:
                pos_sensitive_among_inject += 1
        row["position_sensitive"] = len(pos_answers) > 1
        per_q.append(row)
        backend.flush()

    summary = {
        "backend": args.backend,
        "question_total": n,
        "overall_accuracy": {c: round(correct[c] / n, 4) for c in CONDITIONS},
        "position_sensitive_questions": pos_sensitive,
        "position_sensitive_rate": round(pos_sensitive / n, 4),
    }
    json.dump(summary, open(os.path.join(out_dir, "summary.json"), "w", encoding="utf-8"),
              ensure_ascii=False, indent=2)
    with open(os.path.join(out_dir, "per_question.jsonl"), "w", encoding="utf-8") as f:
        for row in per_q:
            f.write(json.dumps(row, ensure_ascii=False) + "\n")

    lines = [
        "Path B Probe - does injection POSITION change the answer?",
        "=" * 58,
        f"backend={args.backend}  questions={n}",
        "",
        "Overall accuracy by injection position:",
    ]
    for c in CONDITIONS:
        lines.append(f"  {c:13s}: {summary['overall_accuracy'][c]}")
    lines += [
        "",
        f"Position-sensitive questions (final answer differs across "
        f"first/last/final placement): {pos_sensitive}/{n} = {summary['position_sensitive_rate']}",
        "",
        "Read: a high position-sensitive rate means upstream injection propagates",
        "through the reasoning chain -> the sequential MDP carries signal path A lacks.",
        "A near-zero rate means position is irrelevant -> path B collapses to path A.",
    ]
    open(os.path.join(out_dir, "report.txt"), "w", encoding="utf-8").write("\n".join(lines) + "\n")

    backend.flush()
    print("\n".join(lines))
    print(f"\nOutput -> {out_dir}")


if __name__ == "__main__":
    main()
