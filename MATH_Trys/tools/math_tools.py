# -*- coding: utf-8 -*-
"""
本地确定性数学工具集合（MATH 专用）。

设计原则：
1) 纯本地 + 确定性：仅依赖 sympy，相同输入必得相同输出，零网络、零大模型调用，便于复现与回滚。
2) 永不抛异常：任何失败都返回结构化的失败结果，绝不打断上层推理流程。
3) 接口统一：所有工具签名均为 (args: dict) -> dict，由 run_tool 统一调度。
"""
import re

try:
    import sympy as sp
    from sympy.parsing.sympy_parser import (
        parse_expr, standard_transformations,
        implicit_multiplication_application, convert_xor,
    )
    _TRANSF = standard_transformations + (implicit_multiplication_application, convert_xor)
    _SYMPY_OK = True
except Exception:
    _SYMPY_OK = False


def _ok(result, **extra):
    """成功返回；result 供上层注入，extra 携带结构化字段。"""
    out = {"success": True, "result": str(result), "reason": "", **extra}
    return out


def _fail(reason):
    return {"success": False, "result": None, "reason": reason}


def _expr(s, local_dict=None):
    return parse_expr(s, transformations=_TRANSF, local_dict=local_dict or {})


def _sym(name):
    return sp.Symbol(name, real=True)


def _fmt_num(v):
    """精确格式化，避免默认浮点。"""
    v = sp.nsimplify(v)
    if v.is_Rational:
        return f"{v.p}/{v.q}" if v.q != 1 else str(v.p)
    if v.is_Integer:
        return str(int(v))
    return str(v)


def _fmt_complex(v):
    v = sp.expand_complex(sp.nsimplify(v))
    re_, im_ = sp.re(v), sp.im(v)
    if im_ == 0:
        return _fmt_num(re_)
    if re_ == 0:
        c = _fmt_num(im_)
        return f"{c}i" if str(c).startswith("-") else f"{c}i"
    sign = "+" if im_ >= 0 else "-"
    im_abs = _fmt_num(sp.Abs(im_))
    return f"{_fmt_num(re_)} {sign} {im_abs}i"


def _prep_complex_expr(s):
    """将数学式中的虚数单位 i 映射为 SymPy 的 I。"""
    s = s.strip()
    s = re.sub(r"\*\s*i\b", "*I", s)
    s = re.sub(r"\b(\d+)\s*i\b", r"\1*I", s)
    s = re.sub(r"\(\s*([^)]*?)\s*\)\s*i\b", r"(\1)*I", s)
    s = re.sub(r"(?<=[+\-])\s*i\b", "I", s)
    s = re.sub(r"^\s*i\b", "I", s)
    s = re.sub(r"\bi\b(?!\w)", "I", s)
    return s


def tool_factor(args):
    if not _SYMPY_OK:
        return _fail("sympy 未安装")
    try:
        e = _expr(args.get("expression", ""))
        f = sp.factor(e)
        if f == e:
            return _fail("无法进一步因式分解")
        return _ok(f)
    except Exception as e:
        return _fail(f"factor 解析失败: {e}")


def tool_solve(args):
    """
    单变量方程求解。
    args: {"equation": "2*x*(x-10)=-50", "variable": "x"}
    """
    if not _SYMPY_OK:
        return _fail("sympy 未安装")
    try:
        eq_s = args.get("equation", "").strip()
        if not eq_s:
            return _fail("缺少 equation")
        var_name = (args.get("variable") or "").strip()
        if "=" in eq_s:
            lhs, rhs = eq_s.split("=", 1)
            f = _expr(lhs) - _expr(rhs)
        else:
            f = _expr(eq_s)

        syms = sorted(f.free_symbols, key=lambda x: x.name)
        if len(syms) == 0:
            return _fail("方程中没有未知数")
        if len(syms) > 1:
            return _fail("方程含多个未知数，非单变量求解")

        sym = syms[0]
        if var_name and sym.name != var_name.lower():
            return _fail(f"指定变量 {var_name} 与方程不符")

        sols = sp.solve(f, sym)
        if sols is None or sols == []:
            return _fail("无解")
        if isinstance(sols, dict):
            return _fail("无法以单变量形式解析解")

        # 去重保序
        seen, uniq = set(), []
        for s in sols:
            k = str(sp.nsimplify(s))
            if k not in seen:
                seen.add(k)
                uniq.append(sp.nsimplify(s))

        if len(uniq) == 0:
            return _fail("无解")

        sol_strs = [_fmt_num(s) for s in uniq]
        unique = len(sol_strs) == 1
        if unique:
            text = f"{sym.name} = {sol_strs[0]}"
            return _ok(text, text=text, value=sol_strs[0], solutions=sol_strs, unique=True)
        text = f"{sym.name} = " + ", ".join(sol_strs)
        return _ok(text, text=text, value=None, solutions=sol_strs, unique=False)
    except Exception as e:
        return _fail(f"solve 解析失败: {e}")


def tool_arith(args):
    if not _SYMPY_OK:
        return _fail("sympy 未安装")
    try:
        s = args.get("expression", "")
        if parse_expr(s, transformations=_TRANSF, evaluate=False).is_Atom:
            return _fail("非复合运算，无需工具")
        v = sp.simplify(_expr(s))
        if v.free_symbols:
            return _fail("表达式含未知数，非纯数值")
        if not v.is_number:
            return _fail("结果非数值")
        return _ok(_fmt_num(v))
    except Exception as e:
        return _fail(f"arith 解析失败: {e}")


def tool_subst(args):
    if not _SYMPY_OK:
        return _fail("sympy 未安装")
    try:
        expr = _expr(args.get("expression", ""))
        subs = {}
        for k, v in (args.get("subs") or {}).items():
            sym = _expr(str(k))
            if not sym.is_Symbol:
                return _fail(f"非法赋值变量: {k}")
            subs[sym] = _expr(str(v))
        val = sp.simplify(expr.subs(subs))
        if val.free_symbols:
            return _fail("代入后仍含未知数")
        return _ok(_fmt_num(val) if val.is_number else val)
    except Exception as e:
        return _fail(f"subst 解析失败: {e}")


def tool_expand(args):
    if not _SYMPY_OK:
        return _fail("sympy 未安装")
    try:
        e = _expr(args.get("expression", ""))
        v = sp.expand(e)
        if v == e:
            return _fail("无法展开")
        return _ok(v)
    except Exception as ex:
        return _fail(f"expand 解析失败: {ex}")


def tool_simplify(args):
    if not _SYMPY_OK:
        return _fail("sympy 未安装")
    try:
        e = _expr(args.get("expression", ""))
        v = sp.simplify(e)
        if not v.free_symbols:
            return _fail("纯数值由 arith 处理")
        if v == e:
            return _fail("无法进一步化简")
        return _ok(v)
    except Exception as ex:
        return _fail(f"simplify 解析失败: {ex}")


def tool_complex_arithmetic(args):
    """
    完整复数表达式求值/化简。
    args: {"expression": "(5-3*I)*(-4+3*I)"}
    """
    if not _SYMPY_OK:
        return _fail("sympy 未安装")
    try:
        raw = args.get("expression", "").strip()
        if not raw:
            return _fail("缺少 expression")
        prepped = _prep_complex_expr(raw)
        e = _expr(prepped)
        # 除 I 外不得有未绑定符号
        extra = {s.name for s in e.free_symbols if s.name not in ("I",)}
        if extra:
            return _fail(f"含未绑定符号: {sorted(extra)}")
        if "I" not in prepped and not any(s.name == "I" for s in e.free_symbols):
            return _fail("非复数表达式")
        v = sp.expand_complex(sp.simplify(e))
        text = _fmt_complex(v)
        re_, im_ = sp.re(v), sp.im(v)
        return _ok(
            text,
            text=text,
            value=str(v).replace("I", "i"),
            real_part=_fmt_num(re_),
            imag_part=_fmt_num(im_),
        )
    except Exception as e:
        return _fail(f"complex_arithmetic 解析失败: {e}")


def tool_linear_system_solver(args):
    """
    二元（可扩展）线性方程组。
    args: {
      "equations": ["2*x-3*y=8", "4*x+3*y=-2"],
      "variables": ["x", "y"],
      "target": "x*y"   # 可选：直接求目标量
    }
    """
    if not _SYMPY_OK:
        return _fail("sympy 未安装")
    try:
        eqs_in = args.get("equations") or []
        var_names = args.get("variables") or []
        if len(eqs_in) < 2 or len(var_names) < 2:
            return _fail("方程或变量不完整")
        syms = sp.symbols(" ".join(var_names))
        local = {s.name: s for s in syms}
        eqs = []
        for es in eqs_in:
            if "=" not in es:
                return _fail("方程格式非法")
            lhs, rhs = es.split("=", 1)
            eqs.append(sp.Eq(_expr(lhs, local), _expr(rhs, local)))
        # 线性性检查
        for eq in eqs:
            for s in syms:
                if sp.degree(eq.lhs, s) > 1 or sp.degree(eq.rhs, s) > 1:
                    return _fail("非线性方程")
        sol = sp.linsolve(eqs, syms)
        if sol is None:
            return _fail("求解失败")
        if sol == set():
            return _fail("无解")
        if len(sol) != 1:
            return _fail("无限多解或非唯一解")
        sol_tuple = next(iter(sol))
        if any(v.free_symbols for v in sol_tuple):
            return _fail("无限多解")
        mapping = {var_names[i]: _fmt_num(sol_tuple[i]) for i in range(len(var_names))}

        target = (args.get("target") or "").strip()
        if target:
            t_expr = _expr(target, local)
            t_val = sp.simplify(t_expr.subs({local[v]: sp.nsimplify(_expr(mapping[v])) for v in var_names}))
            if t_val.free_symbols:
                return _fail("目标量仍含未知符号")
            t_val = _fmt_num(t_val)
            text = f"{target} = {t_val}"
            return _ok(text, text=text, value=t_val, solution=mapping, target=target)

        text = ", ".join(f"{k} = {v}" for k, v in mapping.items())
        return _ok(text, text=text, solution=mapping, unique=True)
    except Exception as e:
        return _fail(f"linear_system_solver 解析失败: {e}")


def tool_aggregate(args):
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
    if text is None:
        return None
    s = str(text).replace(",", "")
    m = re.findall(r"[-+]?\d+\s*/\s*\d+|[-+]?\d+\.\d+|[-+]?\d+", s)
    return m[-1].replace(" ", "") if m else None


_REGISTRY = {
    "factor": tool_factor,
    "solve": tool_solve,
    "arith": tool_arith,
    "subst": tool_subst,
    "expand": tool_expand,
    "simplify": tool_simplify,
    "aggregate": tool_aggregate,
    "complex_arithmetic": tool_complex_arithmetic,
    "linear_system_solver": tool_linear_system_solver,
}


def run_tool(name, args):
    fn = _REGISTRY.get(name)
    return fn(args or {}) if fn else _fail(f"未知工具: {name}")
