# -*- coding: utf-8 -*-
"""路线 C-full —— **完全符合 GRPO 定义**的版本（不改动 A/B 与 C-精确版任何代码）。

这是真正的 GRPO：满足 DeepSeekMath GRPO 的**每一个**定义性特征——

  1. 采样一组输出：对每题，用旧策略 π_old 在推理链上**采样** G 条轨迹（不是枚举）。
  2. 组内相对优势 + **std 归一化**：A_i = (R_i - mean_G) / (std_G + eps)。
  3. **重要性采样比率**：ratio = π_θ(τ) / π_θ_old(τ)（逐决策步连乘）。
  4. **PPO 式 clip**：min(ratio·A, clip(ratio, 1-ε, 1+ε)·A)。
  5. **KL 正则**：- β·D_KL(π_θ ‖ π_ref)（逐步 Bernoulli KL，参考策略默认均匀 0.5）。
  6. **内层多 epoch**：固定 π_old，在同一批采样上更新 μ 步（让 ratio≠1，clip/IS 真正生效）。
  7. **多步序贯**：决策沿 DoT 推理链逐节点进行，前一步注入改变后一步状态（与 C 同环境）。

回报来自 C 已枚举好的轨迹缓存 `seqmdp_table.jsonl`：每题 2^k 条轨迹的对错都现成，
所以"采样"= 按 π_old 在这棵树上走一条路、查表拿回报，**不额外调用任何 LLM**。
这就是 outcome-supervision 的离线 GRPO：环境响应已缓存，采样/IS/clip/KL 全部在缓存上完成。

评估：贪婪沿链走（每步 argmax），与「不注入 baseline」「全注入」「oracle」对比；做 k 折交叉验证。

  # 冒烟（无 LLM）
  python GRPO/build_seqmdp_cache.py --backend mock --n 12 --dmax 3 --out GRPO/cache/seqmdp_table_mock.jsonl
  python GRPO/train_seqmdp_grpo_full.py --table GRPO/cache/seqmdp_table_mock.jsonl --kfold 3
  # 真实（先用 build_seqmdp_cache.py --backend real 建好缓存）
  python GRPO/train_seqmdp_grpo_full.py --kfold 5 --lam 0.0
"""

from __future__ import annotations

import argparse
import importlib.util
import json
import os
from typing import Any, Dict, List, Tuple

import numpy as np

HERE = os.path.dirname(__file__)
TABLE = os.path.join(HERE, "cache", "seqmdp_table.jsonl")
OUT = os.path.join(HERE, "cache", "seqmdp_grpo_full_policy.json")

# 复用 C-精确版的载入与贪婪评估（导入不会修改其文件）
_spec = importlib.util.spec_from_file_location("tsp", os.path.join(HERE, "train_seqmdp_policy.py"))
tsp = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(tsp)

EPS = 1e-6


def sigmoid(z):
    return 1.0 / (1.0 + np.exp(-z))


def build_tree(rec: Dict[str, Any]):
    """把一题的所有枚举轨迹整理成可采样的决策树：
    state_lut[(step_idx, action_prefix)] = 状态向量；leaf[action_tuple] = (correct, n_inject)。
    因为状态只依赖 (step_idx, 已注入次数=prefix之和)，同前缀状态一致，故树是良定义的。"""
    state_lut: Dict[Tuple[int, Tuple[int, ...]], np.ndarray] = {}
    leaf: Dict[Tuple[int, ...], Tuple[float, int]] = {}
    ndec = len(rec["decisions"])
    for t in rec["trajectories"]:
        acts = tuple(t["actions"])
        leaf[acts] = (1.0 if t["correct"] else 0.0, t["n_inject"])
        for ti, s in enumerate(t["steps"]):
            state_lut[(ti, acts[:ti])] = np.asarray(s["state"], dtype=np.float64)
    return state_lut, leaf, ndec


def sample_trajectory(theta, state_lut, leaf, ndec, rng):
    """用当前(旧)策略沿树采样一条轨迹。返回 (steps[(s,a)], reward_correct, n_inject)。"""
    prefix: Tuple[int, ...] = tuple()
    steps = []
    for ti in range(ndec):
        s = state_lut[(ti, prefix)]
        p = float(sigmoid(s @ theta))
        a = 1 if rng.random() < p else 0
        steps.append((s, a))
        prefix = prefix + (a,)
    correct, ninj = leaf[prefix]
    return steps, correct, ninj


def traj_logp(theta, steps):
    """log π_θ(τ) = Σ_t log[a·p + (1-a)(1-p)]，并返回 Σ_t (a-p)·s（=∇logπ）。"""
    logp = 0.0
    glog = np.zeros_like(theta)
    for s, a in steps:
        p = float(np.clip(sigmoid(s @ theta), EPS, 1 - EPS))
        logp += np.log(p if a == 1 else (1 - p))
        glog += (a - p) * s
    return logp, glog


def kl_grad_to_ref(theta, steps, p_ref):
    """逐步 Bernoulli KL(π_θ‖π_ref) 的梯度: Σ_t [log(p/pref)-log((1-p)/(1-pref))]·p(1-p)·s。"""
    g = np.zeros_like(theta)
    kl = 0.0
    for s, _a in steps:
        p = float(np.clip(sigmoid(s @ theta), EPS, 1 - EPS))
        kl += p * np.log(p / p_ref) + (1 - p) * np.log((1 - p) / (1 - p_ref))
        dkl_dp = np.log(p / p_ref) - np.log((1 - p) / (1 - p_ref))
        g += dkl_dp * p * (1 - p) * s
    return g, kl


def train_full_grpo(train_recs, d, *, G=8, outer_iters=300, inner_epochs=4,
                    clip_eps=0.2, beta=0.01, lr=0.3, p_ref=0.5, seed=0, lam=0.0,
                    verbose=False):
    """完整 GRPO：外层刷新 π_old + 采样G条；内层多 epoch 做 clipped surrogate + KL 更新。"""
    rng = np.random.default_rng(seed)
    theta = np.zeros(d)
    trees = []
    for rec in train_recs:
        lut, leaf, ndec = build_tree(rec)
        if ndec >= 1 and len(rec["trajectories"]) > 1:
            trees.append((lut, leaf, ndec))

    for outer in range(outer_iters):
        theta_old = theta.copy()
        batch = []  # 每题: (samples, A[G])
        for lut, leaf, ndec in trees:
            samples = [sample_trajectory(theta_old, lut, leaf, ndec, rng) for _ in range(G)]
            R = np.array([c - lam * n for (_s, c, n) in samples], dtype=np.float64)
            A = (R - R.mean()) / (R.std() + 1e-8)   # 组内 std 归一化优势
            batch.append((samples, A))

        for _ in range(inner_epochs):
            grad = np.zeros(d)
            cnt = 0
            for samples, A in batch:
                for (steps, _c, _n), adv in zip(samples, A):
                    logp_new, glog = traj_logp(theta, steps)
                    logp_old, _ = traj_logp(theta_old, steps)
                    ratio = float(np.exp(np.clip(logp_new - logp_old, -20, 20)))
                    # PPO clip：判断裁剪是否生效（生效则该样本对 surrogate 无梯度）
                    if adv >= 0:
                        binding = ratio > 1 + clip_eps
                    else:
                        binding = ratio < 1 - clip_eps
                    g_surr = np.zeros(d) if binding else adv * ratio * glog
                    g_kl, _kl = kl_grad_to_ref(theta, steps, p_ref)
                    grad += g_surr - beta * g_kl
                    cnt += 1
            if cnt:
                theta += lr * grad / cnt
        if verbose and (outer % 50 == 0 or outer == outer_iters - 1):
            print(f"    outer {outer}: |theta|={np.linalg.norm(theta):.3f}")
    return theta


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--table", default=TABLE)
    ap.add_argument("--lam", type=float, default=0.0)
    ap.add_argument("--kfold", type=int, default=5)
    ap.add_argument("--G", type=int, default=8, help="每题采样轨迹数(组大小)")
    ap.add_argument("--outer_iters", type=int, default=300)
    ap.add_argument("--inner_epochs", type=int, default=4)
    ap.add_argument("--clip_eps", type=float, default=0.2)
    ap.add_argument("--beta", type=float, default=0.01, help="KL 正则系数")
    ap.add_argument("--lr", type=float, default=0.3)
    ap.add_argument("--p_ref", type=float, default=0.5, help="参考策略的注入概率")
    ap.add_argument("--seed", type=int, default=0)
    ap.add_argument("--no_plot", action="store_true")
    args = ap.parse_args()

    recs = tsp.load_table(args.table)
    d = None
    for r in recs:
        for t in r["trajectories"]:
            if t["steps"]:
                d = len(t["steps"][0]["state"]); break
        if d:
            break
    d = d or 10
    print(f"题数={len(recs)}  特征维度={d}  GRPO配方: G={args.G} outer={args.outer_iters} "
          f"inner={args.inner_epochs} clip_eps={args.clip_eps} beta={args.beta} lr={args.lr}")

    # ---- k 折交叉验证 ----
    rng = np.random.default_rng(args.seed)
    idx = np.arange(len(recs)); rng.shuffle(idx)
    folds = np.array_split(idx, args.kfold)
    accs, injs, nones, fulls, oracles = [], [], [], [], []
    for fi in range(args.kfold):
        test_ids = set(folds[fi].tolist())
        train_recs = [recs[i] for i in range(len(recs)) if i not in test_ids]
        test_recs = [recs[i] for i in range(len(recs)) if i in test_ids]
        theta = train_full_grpo(train_recs, d, G=args.G, outer_iters=args.outer_iters,
                                inner_epochs=args.inner_epochs, clip_eps=args.clip_eps,
                                beta=args.beta, lr=args.lr, p_ref=args.p_ref,
                                seed=args.seed + fi, lam=args.lam)
        a, j, nc, fc, oc = tsp.greedy_eval(theta, test_recs)
        accs.append(a); injs.append(j); nones.append(nc); fulls.append(fc); oracles.append(oc)
        print(f"  fold {fi}: true-GRPO={a:.3f} inj={j:.2f} | none={nc:.3f} full={fc:.3f} oracle={oc:.3f}")

    res = {
        "no_inject": {"acc_mean": float(np.mean(nones)), "acc_std": float(np.std(nones))},
        "true_grpo": {"acc_mean": float(np.mean(accs)), "acc_std": float(np.std(accs)),
                      "inject_mean": float(np.mean(injs))},
        "full_inject": {"acc_mean": float(np.mean(fulls)), "acc_std": float(np.std(fulls))},
        "oracle": {"acc_mean": float(np.mean(oracles)), "acc_std": float(np.std(oracles))},
        "kfold": args.kfold, "n": len(recs),
        "hyper": {"G": args.G, "outer_iters": args.outer_iters, "inner_epochs": args.inner_epochs,
                  "clip_eps": args.clip_eps, "beta": args.beta, "lr": args.lr, "lam": args.lam},
    }

    print("\n===== {}-折交叉验证（测试集平均）=====".format(args.kfold))
    print(f"  no-inject baseline : {res['no_inject']['acc_mean']:.3f} ± {res['no_inject']['acc_std']:.3f}")
    print(f"  TRUE GRPO (full)   : {res['true_grpo']['acc_mean']:.3f} ± {res['true_grpo']['acc_std']:.3f}"
          f"  平均注入 {res['true_grpo']['inject_mean']:.2f} 次/题")
    print(f"  full-inject        : {res['full_inject']['acc_mean']:.3f}")
    print(f"  oracle (上界)      : {res['oracle']['acc_mean']:.3f}")
    gain = 100 * (res['true_grpo']['acc_mean'] - res['no_inject']['acc_mean'])
    print(f"  >>> TRUE GRPO 相对不注入 baseline: {gain:+.2f} 个百分点")

    # ---- 全量训练导出权重 ----
    theta = train_full_grpo(recs, d, G=args.G, outer_iters=args.outer_iters,
                            inner_epochs=args.inner_epochs, clip_eps=args.clip_eps,
                            beta=args.beta, lr=args.lr, p_ref=args.p_ref,
                            seed=args.seed, lam=args.lam, verbose=True)
    a, j, nc, fc, oc = tsp.greedy_eval(theta, recs)
    res["theta_full"] = theta.tolist()
    res["model"] = "true_grpo_sampling_clip_kl_multistep"
    json.dump(res, open(OUT, "w", encoding="utf-8"), ensure_ascii=False, indent=2)
    print(f"\n完整 GRPO 策略 -> {OUT}")

    if not args.no_plot:
        make_plot(res, os.path.join(os.path.dirname(OUT), "grpo_full_vs_baseline.png"))


def make_plot(res, out_png):
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    keys = ["no_inject", "true_grpo", "full_inject", "oracle"]
    labels = ["No inject\n(baseline)", "TRUE GRPO\n(full, learned)", "Full inject", "Oracle\n(upper bound)"]
    colors = ["#9aa0a6", "#ea4335", "#4285f4", "#34a853"]
    vals = [100 * res[k]["acc_mean"] for k in keys]
    errs = [100 * res[k].get("acc_std", 0.0) for k in keys]
    fig, ax = plt.subplots(figsize=(8, 5))
    x = range(len(keys))
    bars = ax.bar(x, vals, yerr=errs, capsize=5, color=colors, edgecolor="black", linewidth=0.6)
    ax.set_ylabel("Accuracy (%)")
    ax.set_title(f"True GRPO (full recipe, multi-step) vs no-inject baseline\n"
                 f"CSQA, {res['kfold']}-fold CV, N={res['n']}")
    ax.set_xticks(list(x)); ax.set_xticklabels(labels)
    ax.set_ylim(max(0, min(vals) - 6), min(100, max(vals) + 4))
    for rect, v in zip(bars, vals):
        ax.text(rect.get_x() + rect.get_width() / 2, v + 0.3, f"{v:.1f}%",
                ha="center", va="bottom", fontsize=10, fontweight="bold")
    fig.tight_layout()
    fig.savefig(out_png, dpi=150)
    print(f"对比图 -> {out_png}")


if __name__ == "__main__":
    main()
