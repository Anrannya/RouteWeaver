# -*- coding: utf-8 -*-
"""路线 C 离线缓存：对每道题**枚举决策树**，得到精确的多步 MDP 轨迹表。

对每题：
  * 取决策节点 decisions（末尾 dmax-1 个子问题 + FINAL）；
  * 枚举所有 2^len(decisions) 个动作组合，逐一 rollout（LLM 调用按 prompt 内容缓存，
    共享前缀自动命中，所以总调用量远小于朴素 2^n）；
  * 记录每条轨迹：每个决策节点的状态特征+动作、最终对错、注入次数。
得到的就是该题**完整且精确**的小型 MDP（一棵决策树），训练时无需再调 LLM。

温度固定 0 → 环境确定 → 缓存即可复现的离线奖励表。

  # 冒烟（无 LLM、确定性 mock）
  cd CSQA_Trys && python GRPO/build_seqmdp_cache.py --backend mock --n 8 --dmax 3
  # 真实后端（子问题→本地 llama、最终→deepseek），建议 tmux 里跑
  cd CSQA_Trys && python GRPO/build_seqmdp_cache.py --backend real --n 200 --dmax 3
"""

from __future__ import annotations

import argparse
import itertools
import json
import os
import sys

HERE = os.path.dirname(__file__)
sys.path.insert(0, HERE)

from llm_backend import LLMBackend          # noqa: E402
from seq_mdp_env import SequentialInjectionEnv, FINAL  # noqa: E402

OUT_PATH = os.path.join(HERE, "cache", "seqmdp_table.jsonl")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--backend", choices=["real", "mock"], default="mock")
    ap.add_argument("--n", type=int, default=200)
    ap.add_argument("--dmax", type=int, default=3, help="每题决策节点数（含 FINAL）")
    ap.add_argument("--temperature", type=float, default=0.0)
    ap.add_argument("--out", default=OUT_PATH)
    args = ap.parse_args()

    backend = LLMBackend(backend=args.backend, temperature=args.temperature)
    env = SequentialInjectionEnv(backend=backend)
    N = min(args.n, len(env.questions))

    os.makedirs(os.path.dirname(args.out), exist_ok=True)
    n_traj = n_calls_q = 0
    with open(args.out, "w", encoding="utf-8") as fout:
        for qid in range(N):
            order, decisions = env.decision_nodes(qid, args.dmax)
            if not decisions:
                # 无可注入知识：单条全不注入轨迹
                r = env.rollout(qid, [], [])
                rec = {"qid": qid, "decisions": [], "hint_available": False,
                       "trajectories": [{"actions": [], "correct": r["correct"],
                                         "n_inject": 0, "steps": r["steps"]}]}
                fout.write(json.dumps(rec, ensure_ascii=False) + "\n")
                n_traj += 1
                print(f"[{qid+1}/{N}] no-knowledge  correct={r['correct']}")
                continue

            trajs = []
            for bits in itertools.product([0, 1], repeat=len(decisions)):
                r = env.rollout(qid, decisions, list(bits))
                trajs.append({"actions": list(bits), "correct": r["correct"],
                              "n_inject": r["n_inject"], "steps": r["steps"],
                              "final_letter": r["final_letter"]})
                n_traj += 1
            dec_repr = [("FINAL" if d == FINAL else d) for d in decisions]
            rec = {"qid": qid, "decisions": dec_repr, "hint_available": True,
                   "gold": trajs[0]["steps"] and env.questions[qid]["answerKey"],
                   "trajectories": trajs}
            fout.write(json.dumps(rec, ensure_ascii=False) + "\n")
            accs = [t["correct"] for t in trajs]
            print(f"[{qid+1}/{N}] decisions={dec_repr} trajs={len(trajs)} "
                  f"acc(none)={trajs[0]['correct']} acc(any)={any(accs)} best={max(accs)}")
    backend.flush()
    print(f"\n写出 {n_traj} 条轨迹 -> {args.out}")
    print(f"LLM 缓存条目数: {len(backend.cache)} (real 后端即去重后的真实调用次数)")


if __name__ == "__main__":
    main()
