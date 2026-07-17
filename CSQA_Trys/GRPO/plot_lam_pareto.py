# -*- coding: utf-8 -*-
"""读取 lam_scan_results.jsonl，画成本敏感 GRPO 的 Pareto 图（准确率 vs 注入量 / vs λ）。"""
import json
import os

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

HERE = os.path.dirname(__file__)
JSONL = os.path.join(HERE, "cache", "lam_scan_results.jsonl")
OUT = os.path.join(HERE, "cache", "lam_pareto.png")

# 去重：同一 λ 保留最后一次
rows = {}
with open(JSONL, encoding="utf-8") as f:
    for line in f:
        line = line.strip()
        if not line:
            continue
        r = json.loads(line)
        rows[r["lam"]] = r
data = sorted(rows.values(), key=lambda r: r["lam"])

lams = [r["lam"] for r in data]
inj = [r["inject"] for r in data]
acc = [100 * r["acc"] for r in data]
none = 100 * data[0]["none"]
full = 100 * data[0]["full"]
oracle = 100 * data[0]["oracle"]

fig, axes = plt.subplots(1, 2, figsize=(13, 5))

# 左：准确率 vs 注入量（真正的 Pareto 前沿）
ax = axes[0]
ax.plot(inj, acc, "o-", color="#ea4335", lw=2, ms=8, zorder=3)
for r in data:
    ax.annotate(f"λ={r['lam']}", (r["inject"], 100 * r["acc"]),
                textcoords="offset points", xytext=(6, 6), fontsize=9)
ax.axhline(none, ls="--", color="#9aa0a6", label=f"no-inject {none:.1f}%")
ax.axhline(full, ls="--", color="#4285f4", label=f"full-inject {full:.1f}%")
ax.axhline(oracle, ls=":", color="#34a853", label=f"oracle {oracle:.1f}%")
ax.set_xlabel("Avg injections per question (cost)")
ax.set_ylabel("Accuracy (%)")
ax.set_title("Pareto: accuracy vs injection cost (cost-aware GRPO)")
ax.legend(loc="lower right", fontsize=9)
ax.grid(alpha=0.3)

# 右：注入量 & 准确率 随 λ 变化
ax = axes[1]
ax.plot(lams, inj, "s-", color="#ea4335", lw=2, ms=7, label="avg injections/q")
ax.set_xlabel("lambda (injection cost coeff.)")
ax.set_ylabel("Avg injections per question", color="#ea4335")
ax.tick_params(axis="y", labelcolor="#ea4335")
ax2 = ax.twinx()
ax2.plot(lams, acc, "o--", color="#1a73e8", lw=2, ms=7, label="accuracy (%)")
ax2.axhline(none, ls=":", color="#9aa0a6")
ax2.set_ylabel("Accuracy (%)", color="#1a73e8")
ax2.tick_params(axis="y", labelcolor="#1a73e8")
ax.set_title("lambda as a dial: injection rate decreases smoothly")
ax.grid(alpha=0.3)

fig.suptitle(f"Cost-aware sequential GRPO on CSQA (N={data[0]['n']}, {data[0]['kfold']}-fold CV)",
             fontsize=12)
fig.tight_layout()
fig.savefig(OUT, dpi=150)
print(f"Pareto 图 -> {OUT}")
