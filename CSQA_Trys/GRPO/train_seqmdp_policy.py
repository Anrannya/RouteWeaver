# -*- coding: utf-8 -*-
"""路线 C 训练：在枚举出的决策树上做**精确的多步 GRPO 策略梯度**。

策略：每个决策节点 π(inject|s) = sigmoid(θ·s)，θ 为线性权重（跨节点共享）。
轨迹概率：P_θ(τ) = Π_t [a_t·p_t + (1-a_t)(1-p_t)]，p_t = sigmoid(θ·s_t)。
回报：R(τ) = 正确 - λ·注入次数。
GRPO 组基线：b_q = Σ_τ P_θ(τ)·R(τ)（同一题的所有轨迹构成 group，组内相对优势）。
精确梯度（多步信用分配，跨轨迹所有决策步求和）：
    ∇J = Σ_q Σ_τ P_θ(τ)·(R(τ)-b_q)·Σ_t (a_t - p_t)·s_t
因为我们**枚举了整棵树**，这是无采样噪声的精确期望梯度——真正的序贯（多步）RL。

评估：贪婪地沿链走（每步按当前状态 argmax 选注/不注，注入数随路径更新），
落到对应叶子，查表得该轨迹的对错/注入数。与 none/full/oracle 对比，并做 k 折交叉验证。

  cd CSQA_Trys && python GRPO/train_seqmdp_policy.py --kfold 5 --lam 0.0
"""

from __future__ import annotations

import argparse
import json
import os
from typing import Any, Dict, List, Tuple

import numpy as np

HERE = os.path.dirname(__file__)
TABLE = os.path.join(HERE, "cache", "seqmdp_table.jsonl")
OUT = os.path.join(HERE, "cache", "seqmdp_policy.json")


def sigmoid(z):
    return 1.0 / (1.0 + np.exp(-z))


def load_table(path: str) -> List[Dict[str, Any]]:
    return [json.loads(l) for l in open(path, encoding="utf-8") if l.strip()]


def question_pack(rec: Dict[str, Any], lam: float):
    """把一题打包成 (列表[轨迹]) ，每条轨迹 = (S[n_dec,d], a[n_dec], R)。"""
    packs = []
    for t in rec["trajectories"]:
        steps = t["steps"]
        if steps:
            S = np.array([s["state"] for s in steps], dtype=np.float64)
            a = np.array([s["action"] for s in steps], dtype=np.float64)
        else:  # 无决策节点（无知识题）
            S = np.zeros((0, 1)); a = np.zeros((0,))
        R = (1.0 if t["correct"] else 0.0) - lam * t["n_inject"]
        packs.append((S, a, R, t["actions"], t["correct"], t["n_inject"]))
    return packs


def grad_and_obj(theta: np.ndarray, qpacks: List[List[Tuple]]):
    """精确多步 GRPO 梯度与目标（仅在 train 题上）。"""
    d = theta.shape[0]
    g = np.zeros(d)
    obj = 0.0
    nq = 0
    for packs in qpacks:
        if len(packs) <= 1:
            continue  # 单轨迹题无梯度信号
        Ps, Rs, grads = [], [], []
        for S, a, R, *_ in packs:
            if S.shape[0] == 0:
                Ps.append(1.0); Rs.append(R); grads.append(np.zeros(d)); continue
            p = sigmoid(S @ theta)
            # 轨迹概率
            traj_p = float(np.prod(a * p + (1 - a) * (1 - p)))
            # Σ_t ∇log π(a_t|s_t) = Σ_t (a_t - p_t) s_t
            glog = ((a - p)[:, None] * S).sum(axis=0)
            Ps.append(traj_p); Rs.append(R); grads.append(glog)
        Ps = np.array(Ps); Rs = np.array(Rs)
        b = float((Ps * Rs).sum())          # GRPO 组基线
        obj += float((Ps * Rs).sum())
        for k in range(len(packs)):
            g += Ps[k] * (Rs[k] - b) * grads[k]
        nq += 1
    if nq:
        g /= nq; obj /= nq
    return g, obj


def train(qpacks: List[List[Tuple]], d: int, epochs=4000, lr=0.5, l2=1e-4):
    theta = np.zeros(d)
    for _ in range(epochs):
        g, _ = grad_and_obj(theta, qpacks)
        theta += lr * (g - l2 * theta)
    return theta


def greedy_eval(theta: np.ndarray, recs: List[Dict[str, Any]]):
    """贪婪沿链决策，落叶查表。返回 (准确率, 平均注入, none准确率, full准确率, oracle准确率)。"""
    corr = inj = none_c = full_c = oracle_c = 0
    n = len(recs)
    for rec in recs:
        trajs = rec["trajectories"]
        by_actions = {tuple(t["actions"]): t for t in trajs}
        # 基线
        zero = tuple([0] * len(rec["decisions"]))
        one = tuple([1] * len(rec["decisions"]))
        none_t = by_actions.get(zero, trajs[0])
        full_t = by_actions.get(one, trajs[0])
        none_c += int(none_t["correct"]); full_c += int(full_t["correct"])
        oracle_c += int(max(t["correct"] for t in trajs))
        # 贪婪：逐步用当前前缀对应的 state 决策
        # 先建 (t, prefix) -> state 查表
        state_lut = {}
        for t in trajs:
            for ti, s in enumerate(t["steps"]):
                state_lut[(ti, tuple(t["actions"][:ti]))] = np.array(s["state"], dtype=np.float64)
        prefix: Tuple[int, ...] = tuple()
        ndec = len(rec["decisions"])
        for ti in range(ndec):
            s = state_lut.get((ti, prefix))
            if s is None:
                prefix = prefix + (0,); continue
            p = sigmoid(float(s @ theta))
            prefix = prefix + (1 if p > 0.5 else 0,)
        leaf = by_actions.get(prefix, none_t)
        corr += int(leaf["correct"]); inj += leaf["n_inject"]
    return corr / n, inj / n, none_c / n, full_c / n, oracle_c / n


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--table", default=TABLE)
    ap.add_argument("--lam", type=float, default=0.0, help="每次注入的成本惩罚")
    ap.add_argument("--kfold", type=int, default=5)
    ap.add_argument("--epochs", type=int, default=4000)
    ap.add_argument("--seed", type=int, default=0)
    args = ap.parse_args()

    recs = load_table(args.table)
    d = None
    for r in recs:
        for t in r["trajectories"]:
            if t["steps"]:
                d = len(t["steps"][0]["state"]); break
        if d:
            break
    d = d or 10
    print(f"题数={len(recs)}  特征维度={d}  λ={args.lam}")

    # ---- k 折交叉验证（看泛化）----
    rng = np.random.default_rng(args.seed)
    idx = np.arange(len(recs)); rng.shuffle(idx)
    folds = np.array_split(idx, args.kfold)
    accs, injs, nones, fulls, oracles = [], [], [], [], []
    for fi in range(args.kfold):
        test_ids = set(folds[fi].tolist())
        train_recs = [recs[i] for i in range(len(recs)) if i not in test_ids]
        test_recs = [recs[i] for i in range(len(recs)) if i in test_ids]
        qpacks = [question_pack(r, args.lam) for r in train_recs]
        theta = train(qpacks, d, epochs=args.epochs)
        a, j, nc, fc, oc = greedy_eval(theta, test_recs)
        accs.append(a); injs.append(j); nones.append(nc); fulls.append(fc); oracles.append(oc)
        print(f"  fold {fi}: learned={a:.3f} inj={j:.2f} | none={nc:.3f} full={fc:.3f} oracle={oc:.3f}")

    print("\n===== {}-折交叉验证（测试集平均）=====".format(args.kfold))
    print(f"  no-inject (全不注)  : {np.mean(nones):.3f}")
    print(f"  full-inject(全注)   : {np.mean(fulls):.3f}  (平均注入 {len(recs[0]['decisions'])} 次/题)")
    print(f"  learned policy (C)  : {np.mean(accs):.3f} ± {np.std(accs):.3f}  平均注入 {np.mean(injs):.2f} 次/题")
    print(f"  oracle (上界)       : {np.mean(oracles):.3f}")

    # ---- 全量训练，导出可部署权重 ----
    qpacks_all = [question_pack(r, args.lam) for r in recs]
    theta = train(qpacks_all, d, epochs=args.epochs)
    a, j, nc, fc, oc = greedy_eval(theta, recs)
    json.dump({"model": "sequential_mdp_sigmoid_linear", "feature_dim": d,
               "lam": args.lam, "theta": theta.tolist(),
               "train_acc": a, "train_inject": j, "none_acc": nc, "oracle_acc": oc},
              open(OUT, "w", encoding="utf-8"), ensure_ascii=False, indent=2)
    print(f"\n全量训练策略 -> {OUT}")
    print(f"  训练集: learned={a:.3f} inj={j:.2f}  none={nc:.3f} oracle={oc:.3f}")


if __name__ == "__main__":
    main()
