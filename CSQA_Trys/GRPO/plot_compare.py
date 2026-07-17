# -*- coding: utf-8 -*-
"""Plot the 3-way comparison (no_inject / offline_grpo / online_grpo).

Reads a summary.json produced by CSQA_dotrun_step2_grpo_compare.py and renders a
single figure with two panels:
  * left  : accuracy (%) per mode, with std error bars
  * right : average time per question (s) per mode, with std error bars
Also prints a Markdown table to stdout.

    cd CSQA_Trys && python GRPO/plot_compare.py \
        "Logs/grpo_compare/<timestamp>/summary.json"
If no path is given, the most recent summary.json under Logs/grpo_compare is used.
"""

from __future__ import annotations

import glob
import json
import os
import sys

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402

BASE = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
LABELS = {"no_inject": "No inject\n(DoT baseline)",
          "offline_grpo": "Offline GRPO\n(rule gate)",
          "online_grpo": "Online GRPO\n(learned, route A)",
          "seqmdp_grpo": "Seq GRPO\n(multi-step, sampled)"}
COLORS = {"no_inject": "#9aa0a6", "offline_grpo": "#4285f4",
          "online_grpo": "#ea4335", "seqmdp_grpo": "#34a853"}


def find_latest():
    cands = glob.glob(os.path.join(BASE, "Logs", "grpo_compare", "*", "summary.json"))
    if not cands:
        raise SystemExit("no summary.json found under Logs/grpo_compare")
    return max(cands, key=os.path.getmtime)


def main():
    path = sys.argv[1] if len(sys.argv) > 1 else find_latest()
    summary = json.load(open(path, encoding="utf-8"))
    m = summary["modes"]
    n = summary["n"]
    # 模式顺序：优先用 summary 里记录的 mode_order，否则用 modes dict 的键
    modes = summary.get("mode_order") or list(m.keys())
    modes = [k for k in modes if k in m]

    accs = [100 * m[k]["acc_mean"] for k in modes]
    acc_err = [100 * m[k]["acc_std"] for k in modes]
    times = [m[k]["avg_time_mean"] for k in modes]
    time_err = [m[k]["avg_time_std"] for k in modes]
    labels = [LABELS.get(k, k) for k in modes]
    colors = [COLORS.get(k, "#888888") for k in modes]

    # ---- Markdown table ----
    print(f"\n{len(modes)}-way comparison (N={n}, rounds={summary['rounds']}, "
          f"temperature={summary['temperature']}, online_budget={summary['online_budget']})\n")
    print("| mode | accuracy | avg time/q (s) | inject/round | tokens/round |")
    print("|---|---|---|---|---|")
    for k in modes:
        d = m[k]
        print(f"| {k} | {100*d['acc_mean']:.2f}% ± {100*d['acc_std']:.2f} | "
              f"{d['avg_time_mean']:.2f} ± {d['avg_time_std']:.2f} | "
              f"{d['inject_mean']:.1f}/{n} | {d['tokens_mean']:.0f} |")

    # ---- figure ----
    fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(11, 4.6))
    x = range(len(modes))

    b1 = ax1.bar(x, accs, yerr=acc_err, capsize=5, color=colors, edgecolor="black", linewidth=0.6)
    ax1.set_ylabel("Accuracy (%)")
    ax1.set_title("Accuracy by injection strategy")
    ax1.set_xticks(list(x)); ax1.set_xticklabels(labels)
    lo = min(accs) - 4
    ax1.set_ylim(max(0, lo), max(accs) + 3)
    for rect, v in zip(b1, accs):
        ax1.text(rect.get_x() + rect.get_width() / 2, v + 0.2, f"{v:.1f}%",
                 ha="center", va="bottom", fontsize=10, fontweight="bold")

    b2 = ax2.bar(x, times, yerr=time_err, capsize=5, color=colors, edgecolor="black", linewidth=0.6)
    ax2.set_ylabel("Avg time per question (s)")
    ax2.set_title("Latency by injection strategy")
    ax2.set_xticks(list(x)); ax2.set_xticklabels(labels)
    ax2.set_ylim(0, max(times) * 1.18)
    for rect, v in zip(b2, times):
        ax2.text(rect.get_x() + rect.get_width() / 2, v + max(times) * 0.01, f"{v:.2f}s",
                 ha="center", va="bottom", fontsize=10, fontweight="bold")

    fig.suptitle(f"DoT + knowledge injection: accuracy vs. latency  (CSQA, N={n}, "
                 f"{summary['rounds']} rounds)", fontsize=12)
    fig.tight_layout(rect=(0, 0, 1, 0.95))
    out_png = os.path.join(os.path.dirname(path), "compare.png")
    fig.savefig(out_png, dpi=150)
    print(f"\nfigure -> {out_png}")


if __name__ == "__main__":
    main()
