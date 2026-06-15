# -*- coding: utf-8 -*-
"""
MATH 规则分配器：纯规则（关键字 + 公式抽取 + sympy 实测校验）为每个子任务分配本地工具。

与“模型分配 / Adapter 分配”的区别：
  本脚本完全不调用大模型，零成本、确定、可复现；分配出的工具还会被实地运行一次，
  只有工具能成功解析才真正分配，否则回退为 no_tool（高准确、保守）。

输入：TmpRes/step2In_MATH_last.json    （含 steps / int_edges 等，保持不动）
输出：TmpRes/step2In_MATH_with_tool.json（在原结构上新增 allo_tool / tool_args / tool_mode 三个对齐列表）
      tool_mode 取值：replace=工具结果覆盖该子任务答案（跳过该步 LLM）；assist=作提示注入、LLM 仍作答。

防泄漏（两类参数来源，均不可能泄漏后续答案或 gold）：
  1) 自包含工具（factor/expand/simplify/subst/arith/solve）：参数只取自“当前子任务自身文字”；
  2) 运行时依赖工具（aggregate）：分配阶段只记录“前驱子任务编号 from_steps”（由 int_edges 得到，
     严格是 DAG 上更早的步），其数值在运行阶段才从这些前驱答案里取——绝不取后续步、绝不读 gold。
  这套“仅前驱 + 运行时取值”借鉴自 baseline 的思路，但本实现只保留一个通用 aggregate 工具、
  且全部以 assist（提示）注入，刻意屏蔽了 baseline 中针对具体题目措辞/数字的硬编码规则（过拟合）。

可回滚：本脚本与 tools/ 均为新增文件，输出亦为新增 json；删除三者即可完全还原，不触碰原有代码。
运行：cd MATH_Trys && python build_with_tool.py
"""
import json
import os
import re
import sys

# 把脚本所在目录加入搜索路径，保证 tools 包可被导入、且路径不依赖运行位置
BASE = os.path.dirname(os.path.abspath(__file__))
sys.path.append(BASE)
from tools import run_tool
from tools.validate_assignment import validate_assignment

IN_PATH = os.path.join(BASE, "TmpRes/step2In_MATH_last.json")
OUT_PATH = os.path.join(BASE, "TmpRes/step2In_MATH_with_tool.json")


def _clean(s):
    # 把 LaTeX 片段尽量清洗成 sympy 能解析的纯 ASCII 数学式
    s = s.replace("\\left", "").replace("\\right", "")
    s = s.replace("\\cdot", "*").replace("\\times", "*")
    # 截断到不等式/比较关系之前，只保留左侧表达式（"\geq 0" 等会污染解析，且我们的工具只处理单个表达式）
    s = re.split(r"\\(?:geq|leq|ge|le|neq|gtr|less|approx)\b|[<>≤≥≠]", s)[0]
    # 混合数：数字紧跟分数 "1\frac{1}{6}" = 1+1/6 = 7/6（必须先于普通 \frac 处理，避免被当成相乘）
    s = re.sub(r"(\d+)\s*\\d?frac\{([^{}]*)\}\{([^{}]*)\}", r"(\1+(\2)/(\3))", s)
    s = re.sub(r"\\d?frac\{([^{}]*)\}\{([^{}]*)\}", r"((\1)/(\2))", s)  # \frac、\dfrac
    s = s.replace("\\", "")   # 其余 \xxx 命令无法处理：去掉引导符，多半会解析失败→自动回退
    return s.strip()


def _pieces(text):
    # 抽取并清洗所有 LaTeX 片段（\( \)、\[ \]、$ $），按出现顺序返回非空清洗结果列表
    cands = []
    for pat in (r"\\\((.+?)\\\)", r"\\\[(.+?)\\\]", r"\$(.+?)\$"):
        cands += re.findall(pat, text, re.S)
    return [c for c in (_clean(x) for x in cands) if c]


def _grab_latex(text):
    # 取最长的一段公式（通常是实质表达式），抽不到返回空串
    ps = _pieces(text)
    return max(ps, key=len) if ps else ""


# 概念/陈述型措辞：这类子任务问的是“公式/关系/方法”，不是要算一个数 → 一律不配工具
_CONCEPT = ("formula", "relate", "which ", "how do", "how does", "how can", "why ",
            "explain", "define", " property", "rule for", "characteristic",
            "what form", "steps are needed", "steps do we", "steps to")
# subst 触发词：子任务要“求某表达式在给定取值下的数值”
_SUBST_KW = ("value of", "evaluate", "compute", "calculate")
# solve 触发词：真正的“解方程/求满足条件的解”
_SOLVE_KW = ("solve for", "roots of", "values of", "value of", "satisfy",
             "equal to zero", "set equal")


def _preds(step_id, int_edges):
    # 当前子任务（1 基编号 step_id）在依赖图 int_edges 上的前驱步号（严格更早，复用 DoT 的依赖结构）
    if not step_id or not int_edges:
        return []
    return sorted({int(a) for a, b in int_edges if int(b) == int(step_id)})


def _apply(subtask, step_id, int_edges, all_steps, mode, name, args):
    """sympy 实测 + validate_assignment；不通过则降级 no_tool。"""
    if name == "no_tool":
        return mode, name, args
    ok, _reason = validate_assignment(
        subtask, name, args, mode,
        all_steps=all_steps, step_id=step_id, int_edges=int_edges,
    )
    if not ok:
        return "no_tool", "no_tool", {}
    return mode, name, args


def assign(subtask, step_id=None, int_edges=None, all_steps=None):
    # 规则分配核心：返回 (模式, 工具名, 参数dict)。模式 ∈ {"no_tool","replace","assist"}：
    #   replace=工具结果就是该子任务确切答案（覆盖、跳过该步 LLM）；
    #   assist =工具结果只是可靠的支撑量（作提示，LLM 仍自己作答）。
    # 优先级 factor -> expand/simplify -> "X of Y" -> subst -> arith -> solve -> aggregate。
    low = subtask.lower()
    ps = _pieces(subtask)
    expr = max(ps, key=len) if ps else ""

    # 1) 因式分解：仅 replace（子任务直接问“factored form / factor the”，工具结果即答案）。
    #    依据：5 轮实测显示 factor-assist（对 GCF/判素数/概念题塞“因式形式”提示）零正收益、净负——
    #    因其注入了子任务并未要求的变换、易误导；故砍掉 assist 分支，只保留“求因式形式”这一对题场景。
    if (("factored form" in low) or ("factor the" in low)) \
            and expr and run_tool("factor", {"expression": expr})["success"]:
        return _apply(subtask, step_id, int_edges, all_steps, "replace", "factor", {"expression": expr})

    # 2) 展开：问“expand / expanded form”，展开式即所求 → replace（否则作提示）。
    if ("expand" in low or "expanded" in low) and expr and run_tool("expand", {"expression": expr})["success"]:
        direct = ("expanded form" in low) or ("expand the" in low)
        mode = "replace" if direct else "assist"
        return _apply(subtask, step_id, int_edges, all_steps, mode, "expand", {"expression": expr})

    # 3) 代数化简（仅符号化简，纯数值留给 arith）→ 作提示 assist。
    if ("simplify" in low or "simplified form" in low) and expr and run_tool("simplify", {"expression": expr})["success"]:
        return _apply(subtask, step_id, int_edges, all_steps, "assist", "simplify", {"expression": expr})

    # 4) “X% of Y” / “(分数) of Y”：把“…的几分之几/百分之几”补全为乘积（修复仅抽到分数、漏掉 of N 的偏差）。
    mof = re.search(r"(\d+(?:\.\d+)?)\s*(%)?\s+of\s+(\d+(?:\.\d+)?)", low)
    if mof:
        a, pct, b = mof.groups()
        e = f"{a}/100*{b}" if pct else f"{a}*{b}"
        if run_tool("arith", {"expression": e})["success"]:
            return _apply(subtask, step_id, int_edges, all_steps, "replace", "arith", {"expression": e})
    mfrac = re.search(r"\bof\s+(\d+(?:\.\d+)?)", low)
    if mfrac and expr and "/" in expr:
        e = f"({expr})*{mfrac.group(1)}"
        if run_tool("arith", {"expression": e})["success"]:
            return _apply(subtask, step_id, int_edges, all_steps, "replace", "arith", {"expression": e})

    # 5) 代入求值：子任务显式给出 var=val。带 = 的片段是赋值，唯一不带 = 的是目标表达式。
    if any(k in low for k in _SUBST_KW) and len(ps) >= 2:
        asg = [p for p in ps if "=" in p]
        tgt = [p for p in ps if "=" not in p]
        if len(tgt) == 1 and asg:
            subs = {}
            ok = True
            for a in asg:
                l, r = a.split("=", 1)
                if not l.strip() or not r.strip():
                    ok = False
                    break
                subs[l.strip()] = r.strip()
            if ok:
                args = {"expression": tgt[0], "subs": subs}
                if run_tool("subst", args)["success"]:
                    return _apply(subtask, step_id, int_edges, all_steps, "replace", "subst", args)

    # 6) 纯数值计算：整段公式化简为确定数值且含运算符 → replace。
    #    安全护栏：若子任务出现 "of <数字>"（如 "1/3 of 36"）却没被上面的乘积规则吃掉，
    #    说明抽取不完整，宁可不配工具，避免注入“半个式子”的错误中间值。
    if expr and any(c in expr for c in "+-*/^") and not re.search(r"\bof\s+\d", low) \
            and run_tool("arith", {"expression": expr})["success"]:
        return _apply(subtask, step_id, int_edges, all_steps, "replace", "arith", {"expression": expr})

    # 7) 解方程：含 =、排除概念题与代入、且恰含 1 个未知数；根集合作提示 → assist。
    if any(k in low for k in _SOLVE_KW) and not any(c in low for c in _CONCEPT) \
            and " when " not in low and " at " not in low and "given in" not in low \
            and "=" in expr:
        args = {"equation": expr}
        if run_tool("solve", args)["success"]:
            return _apply(subtask, step_id, int_edges, all_steps, "assist", "solve", args)

    # 8) 运行时依赖聚合（assist）：子任务要对“前序子任务结果”做 和/积/正差。
    #    分配阶段只记录前驱步号（from_steps），数值在运行阶段才从前驱答案取 → 不泄漏后续/ gold。
    preds = _preds(step_id, int_edges)
    if len(preds) >= 2:
        if "positive difference" in low or "difference between" in low:
            op = "positive_difference"
        elif "sum of" in low or "sum these" in low or "add " in low:
            op = "sum"
        elif "product of" in low or "multiply" in low:
            op = "product"
        else:
            op = None
        if op and (op != "positive_difference" or len(preds) == 2):
            fs = preds[:2] if op == "positive_difference" else preds
            args = {"operation": op, "from_steps": fs}
            return _apply(subtask, step_id, int_edges, all_steps, "assist", "aggregate", args)

    return "no_tool", "no_tool", {}


def main():
    data = json.load(open(IN_PATH, encoding="utf-8"))
    stat = {}
    mode_stat = {}
    for q in data.values():
        tools, targs, modes = [], [], []
        steps = q["steps"]
        int_edges = q.get("int_edges", [])
        for i, s in enumerate(steps, start=1):   # i 为 1 基步号，与 int_edges 对齐
            mode, name, args = assign(s, i, int_edges, all_steps=steps)
            tools.append(name)
            targs.append(args)
            modes.append(mode)                # 每个子任务的使用模式：no_tool/replace/assist
            stat[name] = stat.get(name, 0) + 1
            mode_stat[mode] = mode_stat.get(mode, 0) + 1
        q["allo_tool"] = tools                # 每个子任务分配到的本地工具
        q["tool_args"] = targs                # 对应工具的入参
        q["tool_mode"] = modes                # 对应工具的使用模式（覆盖/提示）
    json.dump(data, open(OUT_PATH, "w", encoding="utf-8"), ensure_ascii=False, indent=2)
    print("分配完成 ->", OUT_PATH)
    print("工具分布:", stat)
    print("模式分布:", mode_stat)


if __name__ == "__main__":
    main()
