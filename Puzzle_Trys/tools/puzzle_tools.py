# -*- coding: utf-8 -*-
"""
本地确定性谜题工具集合（Puzzle 专用）。

设计原则（与 MATH 工具保持一致）：
1) 纯本地 + 确定性：不调用大模型、不联网；以题目自带的 sat 判题函数作为唯一“裁判”，
   相同输入必得相同输出，便于复现与回滚。
2) 永不抛异常：任何失败都返回结构化的失败结果，绝不打断上层推理流程。
3) 接口统一：所有工具签名均为 (args: dict) -> dict，由 run_tool 统一调度。

为什么 Puzzle 工具围绕 sat 设计：
   Puzzle（P3）的目标是“找一个输入让 sat 返回 True”，sat 本身就是一个本地、确定、零成本的
   验证器（相当于 MATH 里的 judge，但更硬更便宜）。因此最稳的本地能力就是“用 sat 当 oracle”：
     - verify：校验候选答案是否真的满足 sat（给 LLM 的候选做实地检验）；
     - search：以 sat 为裁判做“候选枚举 + 验证”，命中即返回（复杂题自动回退）。

search 的候选从哪来（这是它“通用且抗过拟合”的关键）：
   采用 property-based testing / fuzzing 的通用思想——候选答案常与“问题自身的字面量及其可计算量”
   相关。因此候选只来自每道题 sat 源码里**现场抽取**的内容，绝不写死任何题型/具体答案：
     - int：0,±k + 源码中整数字面量的邻域 + 模约束 (i%m==r and i>B) 的构造解；
     - str：源码中字符串字面量、以及 base**exp 求值后的十进制串，取其子串/整串；
     - List[str]：把上述源串按定长切分。
   该机制与题型无关，对任何“带验证器”的任务都适用，故可辩护、可泛化。
"""
from typing import Dict, List, Set, Tuple  # noqa: F401  exec sat 源码时需要这些类型名
import ast
import re

_INT_LIMIT = 3000     # int 线性枚举范围（±_INT_LIMIT）
_STR_MAXLEN = 30      # str 子串候选的最大长度（控规模）
_POW_MAXEXP = 4000    # 计算 base**exp 时的指数上限（避免病态大数拖慢）
_CAND_CAP = 120000    # 单题候选总数上限（保证可控开销）


def _ok(result):
    # 统一的成功返回；result 一律转成字符串，保证能被 json 序列化
    return {"success": True, "result": str(result), "reason": ""}


def _fail(reason):
    # 统一的失败返回；reason 记录原因，便于排查
    return {"success": False, "result": None, "reason": reason}


def _load_sat(sat_src):
    # 加载题目源码中的 sat 函数；失败返回 None。提供 typing 名称以兼容 List[int] 等注解
    try:
        ns = {"List": List, "Dict": Dict, "Tuple": Tuple, "Set": Set}
        exec(sat_src, ns)
        return ns.get("sat")
    except Exception:
        return None


def _check(sat, cand):
    # 用 sat 校验候选：只认显式 True；任何异常（含 assert 失败）都视为不通过
    try:
        return sat(cand) is True
    except Exception:
        return False


def _literal(c):
    # 把字符串候选尽量还原成 Python 对象；纯文本（如答案本身就是字符串）则原样返回
    if not isinstance(c, str):
        return c
    try:
        return ast.literal_eval(c)
    except Exception:
        return c


def _source_strings(sat_src):
    # 通用源串池：sat 源码中的字符串字面量 + base**exp 求值后的十进制串（指数受 _POW_MAXEXP 限制）
    srcs = set(re.findall(r'"([^"]*)"', sat_src)) | set(re.findall(r"'([^']*)'", sat_src))
    for b, e in re.findall(r"(\d+)\s*\*\*\s*(\d+)", sat_src):
        try:
            if int(e) <= _POW_MAXEXP:
                srcs.add(str(int(b) ** int(e)))
        except Exception:
            pass
    return srcs


def _gen_int(sat_src, limit):
    # int 候选：0,±k + 源码整数字面量邻域 + 模约束 (i%m==r and i>B) 的构造解；全部来自问题自身
    seeds = {0}
    for k in range(1, limit + 1):
        seeds.add(k)
        seeds.add(-k)
    for lit in [int(x) for x in re.findall(r"-?\d+", sat_src)][:40]:
        for d in range(-30, 31):
            seeds.add(lit + d)
    for m, r in re.findall(r"%\s*(\d+)\s*==\s*(\d+)", sat_src):
        m, r = int(m), int(r)
        if m == 0:
            continue
        for bx in re.findall(r">\s*(\d+\s*\*\*\s*\d+|\d+)", sat_src):
            try:
                B = eval(bx.replace("^", "**"))          # 仅对“数字/数字**数字”求值，无变量、无副作用
                base = (B // m + 1) * m + r
                for d in range(-3, 4):
                    seeds.add(base + d * m)
            except Exception:
                pass
    return seeds


def _gen_str(sat_src):
    # str 候选：空串 + 各源串整串 + 各源串的有界子串
    cands = {""}
    for ss in _source_strings(sat_src):
        cands.add(ss)
        upper = min(len(ss), _STR_MAXLEN)
        for L in range(1, upper + 1):
            for j in range(len(ss) - L + 1):
                cands.add(ss[j:j + L])
                if len(cands) >= _CAND_CAP:
                    return cands
    return cands


def _gen_list_str(sat_src):
    # List[str] 候选：把各源串按定长切分（覆盖“将某字符串均分为等长片段”这类构造）
    for ss in _source_strings(sat_src):
        if not ss:
            continue
        for chunk in range(1, 12):
            if len(ss) % chunk == 0:
                yield [ss[j:j + chunk] for j in range(0, len(ss), chunk)]


def tool_verify(args):
    # 用 sat 校验候选答案；args = {"sat_src": "...", "candidate": "<literal>" 或 "candidates": [...]}
    sat = _load_sat(args.get("sat_src", ""))
    if sat is None:
        return _fail("sat 加载失败")
    cands = args.get("candidates")
    if cands is None:
        raw = args.get("candidate")
        cands = [raw] if raw is not None else []
    for c in cands:
        val = _literal(c)
        if _check(sat, val):
            return _ok(repr(val))
    return _fail("候选均未通过 sat")


def tool_search(args):
    # 字面量种子化搜索：以 sat 为 oracle，候选全部来自题目自身。
    # args = {"sat_src": "...", "ans_type": "int"/"str"/"List[str]", "limit": N(可选,int枚举范围)}
    src = args.get("sat_src", "")
    sat = _load_sat(src)
    if sat is None:
        return _fail("sat 加载失败")
    ans_type = args.get("ans_type", "")
    limit = int(args.get("limit", _INT_LIMIT))

    if ans_type == "int":
        cands = _gen_int(src, limit)
    elif ans_type == "str":
        cands = _gen_str(src)
    elif ans_type == "List[str]":
        cands = _gen_list_str(src)
    else:
        return _fail(f"search 不支持的类型: {ans_type}")

    for c in cands:
        if _check(sat, c):
            return _ok(repr(c))
    return _fail("种子化搜索未命中")


# 工具注册表：名称 -> 函数。新增工具只需在此登记一行（与 MATH 工具一致）。
_REGISTRY = {
    "verify": tool_verify,
    "search": tool_search,
}


def run_tool(name, args):
    # 统一调度入口；未知工具或 no_tool 一律返回失败（由上层决定是否回退到模型）
    fn = _REGISTRY.get(name)
    return fn(args or {}) if fn else _fail(f"未知工具: {name}")
