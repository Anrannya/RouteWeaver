# -*- coding: utf-8 -*-
"""
MATH 错因分类探针（离线）。

目的：在移植 baseline 专用求解器之前，用数据回答——
  DeepSeek + DoT 答错的题里，有多少属于「确定性计算工具可能救」的品类？

输入：
  - ../Task_Datasets/MATH/all_math_p.json
  - Logs/compare log/<session>/*.log（四轮 no_tool/with_tool 对错）

输出：
  - Logs/probe_error_cause/<timestamp>/report.txt
  - Logs/probe_error_cause/<timestamp>/per_question.csv

分类（与 baseline 工具品类对齐）：
  complex_arithmetic      复数乘法/化简
  function_algebra        函数复合/求值/反函数
  equation_solving        解方程/求根/韦达
  inequality_domain       不等式/定义域/区间
  log_radical             对数/根式精确求值
  coordinate_geometry       坐标/距离/面积
  sequence_series         数列/等差等比/递推
  proportion_linear         比例/线性方程组文字题
  combinatorics_finite      有限枚举/组合计数
  symbolic_manipulation     展开/因式/代数化简（非数值）
  conceptual_reasoning      概念/证明/构造/难以工具化

可回滚：本文件为新增探针，不修改任何运行脚本。
运行：cd MATH_Trys && python probe_error_cause.py
"""
import csv
import glob
import json
import os
import re
from collections import Counter, defaultdict
from datetime import datetime

BASE = os.path.dirname(os.path.abspath(__file__))
PROBLEMS_PATH = os.path.join(BASE, "../Task_Datasets/MATH/all_math_p.json")
DEFAULT_SESSION = os.path.join(BASE, "Logs/compare log/2026-06-14-23-29-44")
N = 200  # 与 MATH_dotrun_step2 / compare 一致，只评前 200 题


def _classify(problem: str, solution: str) -> list:
    """规则分类：一题可命中多个品类（多标签）。"""
    p = (problem + " " + solution).lower()
    tags = []

    if re.search(r"\bi\b|\(-?\d+\s*[+-]\s*\d*i\)|\(\d+\s*-\s*i\)|\(\d+\s*\+\s*\d*i\)", p):
        tags.append("complex_arithmetic")
    if re.search(r"f\(|g\(|h\(|inverse|f\^{-1}|f\^\{-1\}|composition|composite", p):
        tags.append("function_algebra")
    if re.search(r"solve|roots?|vieta|quadratic|equation|set equal|= 0\b", p):
        tags.append("equation_solving")
    if re.search(r"domain|interval|inequal|≤|≥|<|>|\\le|\\ge|sqrt\([^)]+\)\s*~?\?", p):
        tags.append("inequality_domain")
    if re.search(r"\\log|log_|sqrt\{|\\sqrt|\^\{1/2\}|\\frac\{1\}\{\\sqrt", p):
        tags.append("log_radical")
    if re.search(r"\(\s*-?\d+\s*,\s*-?\d+\s*\)|coordinate|midpoint|distance|kite|circle|polygon|graph of", p):
        tags.append("coordinate_geometry")
    if re.search(r"sequence|arithmetic sequence|geometric|term|100th term|revolution|interest rate|doubles every", p):
        tags.append("sequence_series")
    if re.search(r"percent|%|proportion|ratio|cost|calories|fluid ounce|pounds|ounces|interest", p):
        tags.append("proportion_linear")
    if re.search(r"subset|combin|distinct integer|how many possible|pairs", p):
        tags.append("combinatorics_finite")
    if re.search(r"expand|factor|simplif|polynomial|collect", p):
        tags.append("symbolic_manipulation")

    if not tags:
        tags.append("conceptual_reasoning")
    return tags


# baseline 工具可覆盖的品类（移植求解器时有 headroom 的集合）
TOOL_RELEVANT = {
    "complex_arithmetic", "function_algebra", "equation_solving",
    "inequality_domain", "log_radical", "coordinate_geometry",
    "sequence_series", "proportion_linear", "combinatorics_finite",
    "symbolic_manipulation",
}


def parse_logs(session_dir):
    logs = sorted(p for p in glob.glob(os.path.join(session_dir, "*.log")) if "summary" not in p)
    wrong_no = defaultdict(int)
    wrong_yes = defaultdict(int)
    correct_no = defaultdict(int)
    for log in logs:
        mode = None
        cur = None
        for line in open(log, encoding="utf-8"):
            if "===== no_tool =====" in line:
                mode = "no"
            elif "===== with_tool =====" in line:
                mode = "yes"
            m = re.search(r"number id: (\d+)", line)
            if m:
                cur = int(m.group(1))
            m2 = re.search(r"(correct|error) \(tool_hit=(\d+)\)", line)
            if m2 and mode and cur is not None:
                ok = m2.group(1) == "correct"
                if mode == "no":
                    if ok:
                        correct_no[cur] += 1
                    else:
                        wrong_no[cur] += 1
                else:
                    if not ok:
                        wrong_yes[cur] += 1
    return logs, wrong_no, wrong_yes, correct_no


def main():
    problems = json.load(open(PROBLEMS_PATH, encoding="utf-8"))
    session = DEFAULT_SESSION
    if not os.path.isdir(session):
        # 找最新 session
        roots = sorted(glob.glob(os.path.join(BASE, "Logs/compare log/*")))
        session = roots[-1] if roots else session

    logs, wrong_no, wrong_yes, correct_no = parse_logs(session)
    K = len(logs)
    if K == 0:
        print("未找到对比日志，请先跑 MATH_dotrun_step2_compare.py")
        return

    ts = datetime.now().strftime("%Y-%m-%d-%H-%M-%S")
    out_dir = os.path.join(BASE, "Logs/probe_error_cause", ts)
    os.makedirs(out_dir, exist_ok=True)

    rows = []
    for qid in range(N):
        prob = problems[qid]["problem"]
        gold = problems[qid]["solution"]
        tags = _classify(prob, gold)
        primary = tags[0]
        tool_rel = any(t in TOOL_RELEVANT for t in tags)
        wn, wy = wrong_no.get(qid, 0), wrong_yes.get(qid, 0)
        cn = correct_no.get(qid, 0)
        rows.append({
            "qid": qid,
            "tags": "|".join(tags),
            "primary": primary,
            "tool_relevant": tool_rel,
            "no_wrong": wn,
            "no_correct": cn,
            "with_wrong": wy,
            "stable_wrong_no": wn >= max(3, K - 1) if K >= 3 else wn == K,
            "problem": prob[:120].replace("\n", " "),
        })

    csv_path = os.path.join(out_dir, "per_question.csv")
    with open(csv_path, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=list(rows[0].keys()))
        w.writeheader()
        w.writerows(rows)

    def summarize(subset_name, pred):
        sub = [r for r in rows if pred(r)]
        tag_cnt = Counter()
        tool_tag_cnt = Counter()
        for r in sub:
            for t in r["tags"].split("|"):
                tag_cnt[t] += 1
                if t in TOOL_RELEVANT:
                    tool_tag_cnt[t] += 1
        tool_rel_n = sum(1 for r in sub if r["tool_relevant"])
        return sub, tag_cnt, tool_tag_cnt, tool_rel_n

    lines = []
    lines.append(f"MATH 错因分类探针（前 {N} 题）")
    lines.append(f"日志: {session} (K={K} 轮)")
    lines.append(f"输出: {out_dir}")
    lines.append("")

    for name, pred in [
        (f"全部 {N} 题", lambda r: True),
        (f"no_tool 至少错 1 次 ({sum(1 for r in rows if r['no_wrong']>0)} 题)", lambda r: r["no_wrong"] > 0),
        (f"no_tool 稳定错 (>={max(3,K-1)}/{K}) ({sum(1 for r in rows if r['stable_wrong_no'])} 题)", lambda r: r["stable_wrong_no"]),
        (f"no_tool 4轮全错 ({sum(1 for r in rows if r['no_wrong']==K)} 题)", lambda r: r["no_wrong"] == K),
    ]:
        sub, tag_cnt, tool_tag_cnt, tool_rel_n = summarize(name, pred)
        n = len(sub)
        lines.append(f"=== {name} ===")
        lines.append(f"工具相关品类题数: {tool_rel_n}/{n} ({100*tool_rel_n/n:.1f}%)" if n else "无")
        lines.append("品类分布（多标签，一题可计多次）:")
        for t, c in tag_cnt.most_common():
            mark = " *" if t in TOOL_RELEVANT else ""
            lines.append(f"  {t:24s} {c:3d} ({100*c/n:.1f}%){mark}")
        lines.append("")

    # 稳定错题 × 工具品类：baseline 对齐
    stable = [r for r in rows if r["stable_wrong_no"]]
    lines.append("=== 稳定错题中「工具可能救」的题号（按品类）===")
    by_tag = defaultdict(list)
    for r in stable:
        if not r["tool_relevant"]:
            continue
        for t in r["tags"].split("|"):
            if t in TOOL_RELEVANT:
                by_tag[t].append(r["qid"])
    for t in sorted(TOOL_RELEVANT):
        qs = sorted(by_tag[t])
        if qs:
            lines.append(f"  {t:24s} {len(qs):2d} 题: {qs}")

    lines.append("")
    wt_path = os.path.join(BASE, "TmpRes/step2In_MATH_with_tool.json")
    covered = set()
    if os.path.exists(wt_path):
        wt = json.load(open(wt_path, encoding="utf-8"))
        covered = {int(k) for k, v in wt.items() if int(k) < N
                   and any(t != "no_tool" for t in v.get("allo_tool", []))}

    # baseline 实测 tool_direct 正贡献题（在其 ABBA 审计中，且 qid < 200）
    baseline_tool_win = {
        10: "function_algebra", 14: "coordinate_geometry", 53: "log_radical",
        59: "complex_arithmetic", 74: "equation_solving", 153: "equation_solving",
        164: "complex_arithmetic", 195: "inequality_domain",
    }
    lines.append("=== 与 baseline「工具真贡献」题的重叠（前200题内）===")
    for qid, cat in sorted(baseline_tool_win.items()):
        r = rows[qid]
        sw = "稳定错" if r["stable_wrong_no"] else f"错{r['no_wrong']}/{K}"
        cov = "已覆盖" if qid in covered else "未覆盖"
        lines.append(f"  Q{qid:3d} [{cat:22s}] no_tool:{sw:8s} 当前工具:{cov}")

    overlap = [q for q in baseline_tool_win if rows[q]["stable_wrong_no"]]
    lines.append(f"  → baseline 真贡献 8 题中，我们稳定错 {len(overlap)} 题: {overlap}")
    lines.append("")

    sw_set = {r["qid"] for r in rows if r["stable_wrong_no"]}
    lines.append("=== 当前工具覆盖 vs 稳定错题 ===")
    lines.append(f"  当前覆盖题: {len(covered)} 题")
    lines.append(f"  稳定错题: {len(sw_set)} 题")
    lines.append(f"  稳定错且已覆盖: {len(sw_set & covered)} 题 {sorted(sw_set & covered)}")
    lines.append(f"  稳定错但未覆盖: {len(sw_set - covered)} 题")
    lines.append("")

    lines.append("=== 解读 ===")
    sw = sum(1 for r in rows if r["stable_wrong_no"])
    sw_tool = sum(1 for r in rows if r["stable_wrong_no"] and r["tool_relevant"])
    lines.append(f"1) 稳定错题 {sw} 题中 {sw_tool} 题({100*sw_tool/sw:.1f}%) 命中工具相关品类（规则较宽，含 equation 等泛标签）。")
    lines.append(f"2) baseline 工具真贡献 8 题中，我们稳定错 {len(overlap)} 题 —— 这是移植 baseline 求解器的「高置信目标集」。")
    lines.append(f"3) 当前 36 题覆盖与稳定错交集仅 {len(sw_set & covered)} 题，且现有 arith/subst 未打中 baseline 品类。")
    lines.append("4) 建议优先移植: function_algebra, equation_solver, inequality_solver, coordinate_geometry + 复数 symbolic。")
    lines.append("5) 本探针按题干规则分类；conceptual_reasoning 类不宜硬用子任务工具。")

    report_path = os.path.join(out_dir, "report.txt")
    open(report_path, "w", encoding="utf-8").write("\n".join(lines))
    print("\n".join(lines))
    print(f"\n详细 CSV: {csv_path}")


if __name__ == "__main__":
    main()
