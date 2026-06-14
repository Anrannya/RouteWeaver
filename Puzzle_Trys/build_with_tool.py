# -*- coding: utf-8 -*-
"""
Puzzle 规则分配器：基于题目 sat 函数 + 答案类型，为谜题分配本地工具。

与“模型分配 / Adapter 分配”的区别（与 MATH 工具一致）：
  本脚本完全不调用大模型，零成本、确定、可复现；分配出的工具还会被实地运行一次，
  只有工具能在有界预算内真正解出来才分配，否则回退为 no_tool（高准确、保守）。

分配粒度说明：
  Puzzle 的工具本质是“谜题级”的（目标是产出整道题的输入），而非“子任务级”的。
  为与 MATH 的输出结构对齐（allo_tool / tool_args 与 steps 等长、按下标对齐），
  这里把工具挂到“最后一个子任务”（即最终构造/校验答案的那一步），其余子任务记 no_tool。

输入：TmpRes/step2In_Puzzle_last.json   （含 steps / problemText 等，保持不动）
      puzzles.json                       （读取每题的 ans_type，与 step2 用法一致）
输出：TmpRes/step2In_Puzzle_with_tool.json（在原结构上新增 allo_tool / tool_args 两个对齐列表）

可回滚：本脚本与 tools/ 均为新增文件，输出亦为新增 json；删除三者即可完全还原，不触碰原有代码。
运行：cd Puzzle_Trys && python build_with_tool.py
"""
import json
import os
import sys

# 把脚本所在目录加入搜索路径，保证 tools 包可被导入、且路径不依赖运行位置
BASE = os.path.dirname(os.path.abspath(__file__))
sys.path.append(BASE)
from tools import run_tool

IN_PATH = os.path.join(BASE, "TmpRes/step2In_Puzzle_last.json")
OUT_PATH = os.path.join(BASE, "TmpRes/step2In_Puzzle_with_tool.json")
PUZZLES_PATH = os.path.join(BASE, "puzzles.json")

LIMIT = 3000  # 分配阶段 int 枚举范围；str/List[str] 由工具内部按字面量规模自适应

# search 支持的答案类型（数据类型，非题型）：标量 int/str + 由源串定长切分得到的 List[str]
SUPPORTED = ("int", "str", "List[str]")


def assign(sat_src, ans_type):
    # 谜题级分配：对受支持类型尝试“字面量种子化搜索”；工具实测命中才分配，否则保守回退 no_tool
    if ans_type not in SUPPORTED or not sat_src:
        return "no_tool", {}
    args = {"sat_src": sat_src, "ans_type": ans_type, "limit": LIMIT}
    return ("search", args) if run_tool("search", args)["success"] else ("no_tool", {})


def main():
    data = json.load(open(IN_PATH, encoding="utf-8"))
    puzzles = json.load(open(PUZZLES_PATH, encoding="utf-8"))
    stat = {}
    for qid, q in data.items():
        steps = q["steps"]
        n = len(steps)
        allo = ["no_tool"] * n
        targs = [{} for _ in range(n)]            # 每个下标独立 dict，避免共享引用
        sat_src = q.get("problemText", "")
        ans_type = puzzles[int(qid)].get("ans_type", "")  # 与 step2 相同的按序索引取 ans_type

        name, args = assign(sat_src, ans_type)
        if name != "no_tool" and n > 0:
            allo[-1] = name                        # 工具挂到最终构造/校验子任务
            targs[-1] = args

        for t in allo:
            stat[t] = stat.get(t, 0) + 1
        q["allo_tool"] = allo                      # 每个子任务分配到的本地工具
        q["tool_args"] = targs                     # 对应工具的入参（search 自带 sat_src，可独立运行）

    json.dump(data, open(OUT_PATH, "w", encoding="utf-8"), ensure_ascii=False, indent=2)
    print("分配完成 ->", OUT_PATH)
    print("工具分布:", stat)


if __name__ == "__main__":
    main()
