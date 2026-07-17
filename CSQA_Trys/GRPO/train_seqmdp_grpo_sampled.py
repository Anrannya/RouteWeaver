# -*- coding: utf-8 -*-
"""路线 C-sampled —— **端到端采样**的完整 GRPO（不枚举决策树；不改 A/B/C 任何代码）。

与 train_seqmdp_grpo_full.py 的区别（关键）：
  * grpo_full  : 训练时采样，但回报来自**预先枚举好**的 2^k 轨迹缓存（查表）。
  * grpo_sampled（本文件）: **连数据收集也不枚举**。每个外层迭代，对每题用 π_old 采样 G 条
    轨迹，**只对采样到的这几条轨迹**调用环境做一次 rollout 拿回报（带惰性缓存，重复采样
    不重复算）。整个流程从不展开全部 2^k 条——这才是教科书意义上"采样而非枚举"的 GRPO，
    且决策数 dmax 增大时成本按 G 线性增长，而非 2^k 指数爆炸。

为什么采样路径几乎零成本：node_state 只依赖 (qid证据[已缓存], dec_index, 已注入次数)，
不需要 LLM；所以"按 π_old 在链上掷骰子选注/不注"完全是本地计算。只有采样得到的**整条
动作序列**的最终对错(correct, n_inject)需要一次 rollout（LLM）。LLMBackend 本身又按 prompt
内容缓存，故共享子问题前缀的不同轨迹会大量命中缓存，真实 LLM 调用量被严格限制。

完整 GRPO 配方（每一条都满足）：
  ① 采样 G 条轨迹（本文件的核心）           ④ PPO-clip
  ② 组内相对优势 + std 归一化               ⑤ KL 正则（到参考策略）
  ③ 重要性采样比率 π_θ/π_θ_old             ⑥ 内层多 epoch    ⑦ 多步序贯（沿推理链）

评估：none(全不注)/full(全注)/learned(贪婪) 各走一次 rollout；oracle 在**评估集**上枚举
2^dmax（仅作为度量上界，不参与训练）。k 折交叉验证 + 与不注入 baseline 对比 + 出柱状图。

  # 冒烟（确定性 mock，无需 LLM/网络）
  python GRPO/train_seqmdp_grpo_sampled.py --backend mock --n 24 --kfold 3 --outer_iters 60 --no_plot
  # 真实后端（子问题→llama、最终→deepseek），tmux 里跑
  python GRPO/train_seqmdp_grpo_sampled.py --backend real --n 200 --kfold 5 \
      --G 8 --outer_iters 200 --inner_epochs 4 --clip_eps 0.2 --beta 0.01 --lr 0.3
"""

from __future__ import annotations

import argparse
import itertools
import json
import os
import sys
from typing import Any, Dict, List, Tuple

import numpy as np

HERE = os.path.dirname(__file__)
sys.path.insert(0, HERE)

from llm_backend import LLMBackend                      # noqa: E402
from seq_mdp_env import SequentialInjectionEnv, FINAL    # noqa: E402

OUT = os.path.join(HERE, "cache", "seqmdp_grpo_sampled_policy.json")
EPS = 1e-6


def sigmoid(z):
    return 1.0 / (1.0 + np.exp(-z))


class SampledGRPO:
    def __init__(self, env: SequentialInjectionEnv, dmax: int, lam: float,
                 cost_outside: bool = True):
        self.env = env
        self.dmax = dmax
        self.lam = lam
        # cost_outside=True: 注入成本放在组内 std 归一化之外（保留 λ 的真实尺度，可扫出
        #   平滑 Pareto）。False: 旧行为，成本并入回报再一起 std 归一化（λ 尺度被抵消，
        #   任意 λ>0 都塌成零注入）。
        self.cost_outside = cost_outside
        self.reward_cache: Dict[Tuple[int, Tuple[int, ...]], Tuple[float, int]] = {}
        self.decisions: Dict[int, List[Any]] = {}

    def prepare(self, qid: int):
        if qid not in self.decisions:
            _order, dec = self.env.decision_nodes(qid, self.dmax)
            self.decisions[qid] = dec
        return self.decisions[qid]

    def states_for(self, qid: int, bits: List[int]) -> List[Tuple[np.ndarray, int]]:
        """沿采样路径解析地重建每个决策节点的状态（无 LLM）。"""
        dec = self.decisions[qid]
        total = len(dec)
        out = []
        ninj = 0
        for t, node in enumerate(dec):
            is_final = (node == FINAL)
            s = np.asarray(self.env.node_state(qid, is_final, t, total, ninj), dtype=np.float64)
            out.append((s, bits[t]))
            ninj += bits[t]
        return out

    def reward(self, qid: int, bits: List[int]) -> Tuple[float, int]:
        """采样到的整条轨迹的回报（带惰性缓存；只在这里真正触发 rollout/LLM）。"""
        key = (qid, tuple(bits))
        if key in self.reward_cache:
            return self.reward_cache[key]
        dec = self.decisions[qid]
        r = self.env.rollout(qid, dec, list(bits))
        val = (1.0 if r["correct"] else 0.0, r["n_inject"])
        self.reward_cache[key] = val
        return val

    def sample_bits(self, qid: int, theta: np.ndarray, rng) -> List[int]:
        dec = self.decisions[qid]
        total = len(dec)
        bits = []
        ninj = 0
        for t, node in enumerate(dec):
            is_final = (node == FINAL)
            s = np.asarray(self.env.node_state(qid, is_final, t, total, ninj), dtype=np.float64)
            p = float(sigmoid(s @ theta))
            a = 1 if rng.random() < p else 0
            bits.append(a)
            ninj += a
        return bits

    # ---------- 训练 ----------
    def train(self, train_qids: List[int], d: int, *, G=8, outer_iters=200, inner_epochs=4,
              clip_eps=0.2, beta=0.01, lr=0.3, p_ref=0.5, seed=0, verbose=False):
        rng = np.random.default_rng(seed)
        theta = np.zeros(d)
        active = [q for q in train_qids if len(self.prepare(q)) >= 1]
        for outer in range(outer_iters):
            theta_old = theta.copy()
            batch = []  # (list[(states, bits)], A[G])
            for qid in active:
                samples = []
                accs = []
                ks = []
                for _ in range(G):
                    bits = self.sample_bits(qid, theta_old, rng)
                    correct, ninj = self.reward(qid, bits)
                    samples.append(bits)
                    accs.append(correct)
                    ks.append(ninj)
                accs = np.asarray(accs, dtype=np.float64)
                ks = np.asarray(ks, dtype=np.float64)
                if self.cost_outside:
                    # 只对"准确率"做组内 std 归一化，注入成本作为未归一化的项单独扣，
                    # 这样 λ 保留真实档位 → 能扫出平滑的准确率/注入量 Pareto 曲线。
                    A = (accs - accs.mean()) / (accs.std() + 1e-8) \
                        - self.lam * (ks - ks.mean())
                else:
                    Rs = accs - self.lam * ks                    # 旧行为：成本并入回报
                    A = (Rs - Rs.mean()) / (Rs.std() + 1e-8)     # ② 组内 std 归一化优势
                batch.append((qid, samples, A))
            for _ in range(inner_epochs):                  # ⑥ 内层多 epoch
                grad = np.zeros(d)
                cnt = 0
                for qid, samples, A in batch:
                    for bits, adv in zip(samples, A):
                        states = self.states_for(qid, bits)
                        logp_new, glog = self._logp(theta, states)
                        logp_old, _ = self._logp(theta_old, states)
                        ratio = float(np.exp(np.clip(logp_new - logp_old, -20, 20)))  # ③ IS 比率
                        if adv >= 0:                       # ④ PPO-clip
                            binding = ratio > 1 + clip_eps
                        else:
                            binding = ratio < 1 - clip_eps
                        g_surr = np.zeros(d) if binding else adv * ratio * glog
                        g_kl = self._kl_grad(theta, states, p_ref)  # ⑤ KL 正则
                        grad += g_surr - beta * g_kl
                        cnt += 1
                if cnt:
                    theta += lr * grad / cnt
            if verbose and (outer % 40 == 0 or outer == outer_iters - 1):
                print(f"    outer {outer}: |theta|={np.linalg.norm(theta):.3f} "
                      f"reward_cache={len(self.reward_cache)}")
        return theta

    @staticmethod
    def _logp(theta, states):
        logp = 0.0
        glog = np.zeros_like(theta)
        for s, a in states:
            p = float(np.clip(sigmoid(s @ theta), EPS, 1 - EPS))
            logp += np.log(p if a == 1 else (1 - p))
            glog += (a - p) * s
        return logp, glog

    @staticmethod
    def _kl_grad(theta, states, p_ref):
        g = np.zeros_like(theta)
        for s, _a in states:
            p = float(np.clip(sigmoid(s @ theta), EPS, 1 - EPS))
            dkl_dp = np.log(p / p_ref) - np.log((1 - p) / (1 - p_ref))
            g += dkl_dp * p * (1 - p) * s
        return g

    # ---------- 评估（贪婪沿链；none/full/oracle 作对照）----------
    def evaluate(self, qids: List[int], theta: np.ndarray, exact_oracle=True):
        corr = inj = none_c = full_c = oracle_c = 0
        n = len(qids)
        for qid in qids:
            dec = self.prepare(qid)
            ndec = len(dec)
            if ndec == 0:  # 无知识可注入：三种都等于不注入
                c, _ = self.reward(qid, [])
                corr += c; none_c += c; full_c += c; oracle_c += c
                continue
            none_c += self.reward(qid, [0] * ndec)[0]
            full_c += self.reward(qid, [1] * ndec)[0]
            # 贪婪：逐节点 argmax
            bits = []
            ninj = 0
            for t, node in enumerate(dec):
                is_final = (node == FINAL)
                s = np.asarray(self.env.node_state(qid, is_final, t, ndec, ninj), dtype=np.float64)
                a = 1 if float(sigmoid(s @ theta)) > 0.5 else 0
                bits.append(a); ninj += a
            c, ninj_used = self.reward(qid, bits)
            corr += c; inj += ninj_used
            if exact_oracle:
                best = max(self.reward(qid, list(b))[0] for b in itertools.product([0, 1], repeat=ndec))
            else:
                best = max((v[0] for (q, _), v in self.reward_cache.items() if q == qid), default=none_c)
            oracle_c += best
        return corr / n, inj / n, none_c / n, full_c / n, oracle_c / n


def make_plot(res, out_png):
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    keys = ["no_inject", "true_grpo", "full_inject", "oracle"]
    labels = ["No inject\n(baseline)", "TRUE GRPO\n(sampled, learned)", "Full inject", "Oracle\n(upper bound)"]
    colors = ["#9aa0a6", "#ea4335", "#4285f4", "#34a853"]
    vals = [100 * res[k]["acc_mean"] for k in keys]
    errs = [100 * res[k].get("acc_std", 0.0) for k in keys]
    fig, ax = plt.subplots(figsize=(8, 5))
    x = range(len(keys))
    bars = ax.bar(x, vals, yerr=errs, capsize=5, color=colors, edgecolor="black", linewidth=0.6)
    ax.set_ylabel("Accuracy (%)")
    ax.set_title(f"True GRPO (sampling-based, multi-step) vs no-inject baseline\n"
                 f"CSQA, {res['kfold']}-fold CV, N={res['n']}")
    ax.set_xticks(list(x)); ax.set_xticklabels(labels)
    ax.set_ylim(max(0, min(vals) - 6), min(100, max(vals) + 4))
    for rect, v in zip(bars, vals):
        ax.text(rect.get_x() + rect.get_width() / 2, v + 0.3, f"{v:.1f}%",
                ha="center", va="bottom", fontsize=10, fontweight="bold")
    fig.tight_layout()
    fig.savefig(out_png, dpi=150)
    print(f"对比图 -> {out_png}")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--backend", choices=["real", "mock"], default="mock")
    ap.add_argument("--n", type=int, default=200)
    ap.add_argument("--dmax", type=int, default=3)
    ap.add_argument("--lam", type=float, default=0.0)
    ap.add_argument("--kfold", type=int, default=5)
    ap.add_argument("--G", type=int, default=8)
    ap.add_argument("--outer_iters", type=int, default=200)
    ap.add_argument("--inner_epochs", type=int, default=4)
    ap.add_argument("--clip_eps", type=float, default=0.2)
    ap.add_argument("--beta", type=float, default=0.01)
    ap.add_argument("--lr", type=float, default=0.3)
    ap.add_argument("--p_ref", type=float, default=0.5)
    ap.add_argument("--seed", type=int, default=0)
    ap.add_argument("--temperature", type=float, default=0.0)
    ap.add_argument("--cost_outside", action=argparse.BooleanOptionalAction, default=True,
                    help="注入成本放在 std 归一化之外（默认开，保留 λ 尺度）；"
                         "--no-cost_outside 还原旧行为（成本并入回报再归一化）")
    ap.add_argument("--no_plot", action="store_true")
    args = ap.parse_args()

    backend = LLMBackend(backend=args.backend, temperature=args.temperature)
    env = SequentialInjectionEnv(backend=backend)
    N = min(args.n, len(env.questions))
    d = SequentialInjectionEnv.FEATURE_DIM

    print(f"题数={N}  特征维度={d}  backend={args.backend}  GRPO配方(纯采样): "
          f"G={args.G} outer={args.outer_iters} inner={args.inner_epochs} "
          f"clip_eps={args.clip_eps} beta={args.beta} lr={args.lr} lam={args.lam} "
          f"cost_outside={args.cost_outside}")

    trainer = SampledGRPO(env, args.dmax, args.lam, cost_outside=args.cost_outside)
    for qid in range(N):
        trainer.prepare(qid)

    rng = np.random.default_rng(args.seed)
    idx = np.arange(N); rng.shuffle(idx)
    folds = np.array_split(idx, args.kfold)
    accs, injs, nones, fulls, oracles = [], [], [], [], []
    for fi in range(args.kfold):
        test_ids = set(folds[fi].tolist())
        train_qids = [q for q in range(N) if q not in test_ids]
        test_qids = [q for q in range(N) if q in test_ids]
        theta = trainer.train(train_qids, d, G=args.G, outer_iters=args.outer_iters,
                              inner_epochs=args.inner_epochs, clip_eps=args.clip_eps,
                              beta=args.beta, lr=args.lr, p_ref=args.p_ref, seed=args.seed + fi)
        a, j, nc, fc, oc = trainer.evaluate(test_qids, theta)
        accs.append(a); injs.append(j); nones.append(nc); fulls.append(fc); oracles.append(oc)
        print(f"  fold {fi}: true-GRPO(sampled)={a:.3f} inj={j:.2f} | "
              f"none={nc:.3f} full={fc:.3f} oracle={oc:.3f}")
        backend.flush()

    # 全量训练，导出可部署的策略权重（供在线计时脚本 CSQA_dotrun_step2_grpo_compare.py 加载）
    print("  [全量训练导出权重 ...]")
    theta_full = trainer.train(list(range(N)), d, G=args.G, outer_iters=args.outer_iters,
                               inner_epochs=args.inner_epochs, clip_eps=args.clip_eps,
                               beta=args.beta, lr=args.lr, p_ref=args.p_ref,
                               seed=args.seed, verbose=True)
    backend.flush()

    res = {
        "no_inject": {"acc_mean": float(np.mean(nones)), "acc_std": float(np.std(nones))},
        "true_grpo": {"acc_mean": float(np.mean(accs)), "acc_std": float(np.std(accs)),
                      "inject_mean": float(np.mean(injs))},
        "full_inject": {"acc_mean": float(np.mean(fulls)), "acc_std": float(np.std(fulls))},
        "oracle": {"acc_mean": float(np.mean(oracles)), "acc_std": float(np.std(oracles))},
        "kfold": args.kfold, "n": N, "backend": args.backend,
        "hyper": {"G": args.G, "outer_iters": args.outer_iters, "inner_epochs": args.inner_epochs,
                  "clip_eps": args.clip_eps, "beta": args.beta, "lr": args.lr, "lam": args.lam,
                  "cost_outside": args.cost_outside},
        "distinct_rollouts": len(trainer.reward_cache),
        "model": "true_grpo_sampling_no_enumeration_multistep",
        "feature_dim": d, "dmax": args.dmax, "p_ref": args.p_ref,
        "theta": theta_full.tolist(),   # 10 维注入策略权重: P(inject)=sigmoid(state·theta)
    }
    print("\n===== {}-折交叉验证（测试集平均）=====".format(args.kfold))
    print(f"  no-inject baseline : {res['no_inject']['acc_mean']:.3f} ± {res['no_inject']['acc_std']:.3f}")
    print(f"  TRUE GRPO (sampled): {res['true_grpo']['acc_mean']:.3f} ± {res['true_grpo']['acc_std']:.3f}"
          f"  平均注入 {res['true_grpo']['inject_mean']:.2f} 次/题")
    print(f"  full-inject        : {res['full_inject']['acc_mean']:.3f}")
    print(f"  oracle (上界)      : {res['oracle']['acc_mean']:.3f}")
    gain = 100 * (res['true_grpo']['acc_mean'] - res['no_inject']['acc_mean'])
    print(f"  >>> TRUE GRPO(采样) 相对不注入 baseline: {gain:+.2f} 个百分点")
    print(f"  （训练共触发 {len(trainer.reward_cache)} 条不同轨迹的 rollout，体现'采样而非枚举'）")

    json.dump(res, open(OUT, "w", encoding="utf-8"), ensure_ascii=False, indent=2)
    print(f"\n采样式完整 GRPO 策略 -> {OUT}")

    # 自动把本次运行的关键结果追加落盘（不管怎么跑、滚不滚屏都不丢），供扫 λ 后统一分析
    scan_path = os.path.join(os.path.dirname(OUT), "lam_scan_results.jsonl")
    rec = {
        "lam": args.lam, "cost_outside": args.cost_outside, "n": N, "kfold": args.kfold,
        "acc": res["true_grpo"]["acc_mean"], "acc_std": res["true_grpo"]["acc_std"],
        "inject": res["true_grpo"]["inject_mean"],
        "none": res["no_inject"]["acc_mean"], "full": res["full_inject"]["acc_mean"],
        "oracle": res["oracle"]["acc_mean"], "gain_pp": gain,
        "hyper": res["hyper"],
    }
    with open(scan_path, "a", encoding="utf-8") as f:
        f.write(json.dumps(rec, ensure_ascii=False) + "\n")
    print(f"结果追加 -> {scan_path}")
    if not args.no_plot:
        make_plot(res, os.path.join(os.path.dirname(OUT), "grpo_sampled_vs_baseline.png"))


if __name__ == "__main__":
    main()
