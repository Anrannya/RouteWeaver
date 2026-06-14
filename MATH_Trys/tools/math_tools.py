# -*- coding: utf-8 -*-
"""
本地确定性数学工具集合（MATH 专用）。

设计原则：
1) 纯本地 + 确定性：仅依赖 sympy，相同输入必得相同输出，零网络、零大模型调用，便于复现与回滚。
2) 永不抛异常：任何失败都返回结构化的失败结果，绝不打断上层推理流程。
3) 接口统一：所有工具签名均为 (args: dict) -> dict，由 run_tool 统一调度。
"""
import re  # noqa: F401  预留：后续工具可能用到

try:
    import sympy as sp
    from sympy.parsing.sympy_parser import (
        parse_expr, standard_transformations,
        implicit_multiplication_application, convert_xor,
    )
    # 解析增强：隐式乘法（"2x"->2*x、"x(x+5)"->x*(x+5)）+ ^ 当幂运算（convert_xor）
    _TRANSF = standard_transformations + (implicit_multiplication_application, convert_xor)
    _SYMPY_OK = True
except Exception:                       # sympy 缺失时整体降级，主流程仍可回退到模型
    _SYMPY_OK = False


def _ok(result):
    # 统一的成功返回；result 一律转成字符串，保证能被 json 序列化
    return {"success": True, "result": str(result), "reason": ""}


def _fail(reason):
    # 统一的失败返回；reason 记录原因，便于排查
    return {"success": False, "result": None, "reason": reason}


def _expr(s):
    # 把入参表达式统一成 sympy 表达式：隐式乘法 + ^ 视为幂运算（详见 _TRANSF）
    return parse_expr(s, transformations=_TRANSF)


def tool_factor(args):
    # 因式分解：args = {"expression": "x^2 + x - 6"}
    if not _SYMPY_OK:
        return _fail("sympy 未安装")
    try:
        e = _expr(args.get("expression", ""))
        f = sp.factor(e)
        if f == e:                          # 因式分解没带来任何变化（如裸符号/已是最简）→ 无价值，拒绝
            return _fail("无法进一步因式分解")
        return _ok(f)
    except Exception as e:
        return _fail(f"factor 解析失败: {e}")


def tool_solve(args):
    # 解方程：args = {"equation": "x^2 + x - 6 = 0"}；缺 = 号时视为 表达式 = 0
    if not _SYMPY_OK:
        return _fail("sympy 未安装")
    try:
        eq = args.get("equation", "")
        if "=" in eq:
            lhs, rhs = eq.split("=", 1)
            f = _expr(lhs) - _expr(rhs)
        else:
            f = _expr(eq)
        syms = sorted(f.free_symbols, key=lambda x: x.name)
        if not syms:
            return _fail("方程中没有未知数")
        if len(syms) != 1:                  # 多未知数=意图易错配（如把多位字母当变量），保守拒绝
            return _fail("方程含多个未知数，非单变量求解")
        sol = sp.solve(f, syms[0])
        return _ok(sol) if sol else _fail("无解")
    except Exception as e:
        return _fail(f"solve 解析失败: {e}")


def tool_arith(args):
    # 纯数值计算：args = {"expression": "120/100*30"}；返回化简后的精确值
    if not _SYMPY_OK:
        return _fail("sympy 未安装")
    try:
        s = args.get("expression", "")
        # 用未求值解析判断结构：单个数字（如 -4）只是回显、无运算可代劳 → 拒绝
        if parse_expr(s, transformations=_TRANSF, evaluate=False).is_Atom:
            return _fail("非复合运算，无需工具")
        v = sp.simplify(_expr(s))
        if v.free_symbols:                 # 含未知数则不属于纯数值计算
            return _fail("表达式含未知数，非纯数值")
        if not v.is_number:                # 排除元组/坐标等“非数值”回显（如 (-8,6)）
            return _fail("结果非数值")
        return _ok(v)
    except Exception as e:
        return _fail(f"arith 解析失败: {e}")


def tool_subst(args):
    # 代入求值：args = {"expression": "2*x - y", "subs": {"x": "4", "y": "3"}}
    # 用途：子任务已显式给出各变量取值，工具确定性代入算出数值；LLM 在这类多步运算上最易手滑。
    if not _SYMPY_OK:
        return _fail("sympy 未安装")
    try:
        expr = _expr(args.get("expression", ""))
        subs = {}
        for k, v in (args.get("subs") or {}).items():
            sym = _expr(str(k))
            if not sym.is_Symbol:               # 赋值左边必须是单一符号，杜绝把方程误当代入
                return _fail(f"非法赋值变量: {k}")
            subs[sym] = _expr(str(v))
        val = sp.simplify(expr.subs(subs))
        if val.free_symbols:                    # 代入后仍含未知数，说明给定不全，非确定数值
            return _fail("代入后仍含未知数")
        return _ok(val)
    except Exception as e:
        return _fail(f"subst 解析失败: {e}")


def tool_expand(args):
    # 多项式展开：args = {"expression": "(2x+3)^2"}；展开后即子任务所求形式。
    if not _SYMPY_OK:
        return _fail("sympy 未安装")
    try:
        e = _expr(args.get("expression", ""))
        v = sp.expand(e)
        if v == e:                              # 没变化（已展开/无可展开）→ 无价值
            return _fail("无法展开")
        return _ok(v)
    except Exception as ex:
        return _fail(f"expand 解析失败: {ex}")


def tool_simplify(args):
    # 代数化简：args = {"expression": "(x^2-1)/(x-1)"}。仅处理“化简后仍含未知数”的符号化简；
    # 纯数值交给 arith，避免与之重叠。
    if not _SYMPY_OK:
        return _fail("sympy 未安装")
    try:
        e = _expr(args.get("expression", ""))
        v = sp.simplify(e)
        if not v.free_symbols:                  # 纯数值由 arith 负责
            return _fail("纯数值由 arith 处理")
        if v == e:                              # 没变化 → 无价值
            return _fail("无法进一步化简")
        return _ok(v)
    except Exception as ex:
        return _fail(f"simplify 解析失败: {ex}")


def tool_aggregate(args):
    # 运行时依赖聚合：args = {"operation": "sum"/"product"/"positive_difference", "values": [..]}
    # values 在运行阶段由上层从“前驱子任务答案”中抽取后填入（本函数只做确定性聚合运算）。
    if not _SYMPY_OK:
        return _fail("sympy 未安装")
    op = args.get("operation", "")
    vals = args.get("values") or []
    try:
        nums = [sp.nsimplify(_expr(str(v))) for v in vals]
    except Exception as ex:
        return _fail(f"aggregate 解析失败: {ex}")
    if not nums or not all(n.is_number for n in nums):
        return _fail("聚合值非数值")
    if op == "sum":
        r = sum(nums, sp.Integer(0))
    elif op == "product":
        r = sp.Integer(1)
        for n in nums:
            r *= n
    elif op == "positive_difference":
        if len(nums) != 2:
            return _fail("positive_difference 需恰好两个值")
        r = sp.Abs(nums[0] - nums[1])
    else:
        return _fail(f"不支持的聚合: {op}")
    return _ok(sp.simplify(r))


def extract_number(text):
    # 从文本中抽取“最后一个数”（整数/小数/分数）并返回字符串；无则 None。
    # 用途：聚合工具在运行时从前驱子任务答案里取值；子任务答案通常以结果数值结尾，故取最后一个最稳。
    if text is None:
        return None
    s = str(text).replace(",", "")
    m = re.findall(r"[-+]?\d+\s*/\s*\d+|[-+]?\d+\.\d+|[-+]?\d+", s)
    return m[-1].replace(" ", "") if m else None


# 工具注册表：名称 -> 函数。新增工具只需在此登记一行。
_REGISTRY = {
    "factor": tool_factor,
    "solve": tool_solve,
    "arith": tool_arith,
    "subst": tool_subst,
    "expand": tool_expand,
    "simplify": tool_simplify,
    "aggregate": tool_aggregate,
}


def run_tool(name, args):
    # 统一调度入口；未知工具或 no_tool 一律返回失败（由上层决定是否回退到模型）
    fn = _REGISTRY.get(name)
    return fn(args or {}) if fn else _fail(f"未知工具: {name}")
