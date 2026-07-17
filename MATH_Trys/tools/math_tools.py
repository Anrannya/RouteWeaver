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


_SELECT_OPS = (
    "minimum", "maximum", "minimum_positive",
    "maximum_integer", "minimum_integer",
)


def _abs_to_func(s):
    """把 |expr| 改写成 Abs(expr)，兼容嵌套（如 |2-|x||）与并列（如 |x|+|y|）。

    启发式：优先选择内容不以二元运算符开头/结尾的相邻竖线对（即“完整”子式），
    从而先匹配内层 |x|，再匹配外层。
    """
    s = s.strip()
    ops = set("+-*/^")
    while "|" in s:
        idxs = [k for k, ch in enumerate(s) if ch == "|"]
        if len(idxs) < 2:
            break
        chosen = None
        for a in range(len(idxs) - 1):
            i, j = idxs[a], idxs[a + 1]
            content = s[i + 1:j].strip()
            if content and content[0] not in ops and content[-1] not in ops:
                chosen = (i, j)
                break
        if chosen is None:
            chosen = (idxs[0], idxs[1])
        i, j = chosen
        s = s[:i] + f"Abs({s[i + 1:j]})" + s[j + 1:]
    return s


def _to_expr_pair(eq_s):
    """方程串 -> (f) 使得 f = 0；无等号时按表达式本身。"""
    eq_s = _abs_to_func(eq_s.strip())
    if "=" in eq_s:
        lhs, rhs = eq_s.split("=", 1)
        return _expr(lhs) - _expr(rhs)
    return _expr(eq_s)


def _filter_domain(sols, domain):
    """按定义域过滤候选解，返回精确 sympy 值列表（已去重）。"""
    seen, out = set(), []
    for s in sols:
        s = sp.nsimplify(s)
        if s.free_symbols:
            continue
        if domain != "complex":
            if s.is_real is False:
                continue
            if s.has(sp.I) and sp.im(s) != 0:
                continue
        if domain in ("integer", "positive_integer"):
            if s.is_integer is not True:
                continue
            if domain == "positive_integer" and not (s.is_positive is True):
                continue
        k = str(s)
        if k not in seen:
            seen.add(k)
            out.append(s)
    return out


def _apply_select(sols, select):
    """从实数解中按语义挑选唯一解；失败返回 (None, reason)。"""
    reals = [s for s in sols if s.is_real]
    if not reals:
        return None, "无实数解可供 select"
    key = lambda v: float(v)
    if select == "minimum":
        return min(reals, key=key), ""
    if select == "maximum":
        return max(reals, key=key), ""
    if select == "minimum_positive":
        pos = [s for s in reals if s.is_positive is True]
        return (min(pos, key=key), "") if pos else (None, "无正数解")
    if select in ("minimum_integer", "maximum_integer"):
        ints = [s for s in reals if s.is_integer is True]
        if not ints:
            return None, "无整数解"
        return (min(ints, key=key) if select == "minimum_integer"
                else max(ints, key=key)), ""
    return None, f"未知 select: {select}"


_ROOT_TARGETS = (
    "sum", "product", "sum_of_squares", "product_of_squares", "sum_of_reciprocals",
    "absolute_difference", "positive_difference", "minimum", "maximum", "count",
)


def _apply_root_target(sols, root_target):
    """基于完整根集合计算派生目标。返回 (value_str, ok, reason)。"""
    if root_target == "count":
        return str(len(sols)), True, ""
    reals = [s for s in sols if s.is_real]
    if root_target == "sum":
        return _fmt_num(sum(sols, sp.Integer(0))), True, ""
    if root_target == "product":
        p = sp.Integer(1)
        for s in sols:
            p *= s
        return _fmt_num(sp.simplify(p)), True, ""
    if root_target == "sum_of_squares":
        return _fmt_num(sp.simplify(sum((s ** 2 for s in sols), sp.Integer(0)))), True, ""
    if root_target == "product_of_squares":
        p = sp.Integer(1)
        for s in sols:
            p *= s ** 2
        return _fmt_num(sp.simplify(p)), True, ""
    if root_target == "sum_of_reciprocals":
        if any(s == 0 for s in sols):
            return None, False, "根中含 0，倒数和无定义"
        return _fmt_num(sp.simplify(sum((1 / s for s in sols), sp.Integer(0)))), True, ""
    if root_target in ("absolute_difference", "positive_difference"):
        if len(sols) != 2:
            return None, False, "差值目标需恰好两个根"
        if not all(s.is_real for s in sols):
            return None, False, "差值目标需实根"
        hi, lo = max(reals, key=lambda v: float(v)), min(reals, key=lambda v: float(v))
        return _fmt_num(sp.simplify(hi - lo)), True, ""
    if root_target == "minimum":
        if not reals:
            return None, False, "无实根"
        return _fmt_num(min(reals, key=lambda v: float(v))), True, ""
    if root_target == "maximum":
        if not reals:
            return None, False, "无实根"
        return _fmt_num(max(reals, key=lambda v: float(v))), True, ""
    return None, False, f"未知 root_target: {root_target}"


def _eval_solve_target(target_expr, primary_var, sols):
    """
    解出后代入 target_expression。
    - 目标符号 ⊆ {primary_var}：需唯一解。
    - 目标含多个根符号（如 a,b）：把解集按所有排列代入，要求取值唯一（对称式可验证）。
    返回 (value_str, ok, reason)。
    """
    import itertools
    te = _expr(target_expr)
    tsyms = sorted(te.free_symbols, key=lambda s: s.name)
    if not tsyms:
        return None, False, "target_expression 无变量"
    tnames = {s.name for s in tsyms}

    if tnames.issubset({primary_var}):
        if len(sols) != 1:
            return None, False, "target_expression 需唯一解"
        val = sp.simplify(te.subs(sp.Symbol(primary_var, real=True), sols[0]))
        if val.free_symbols:
            return None, False, "target 代入后仍含未知量"
        return _fmt_num(val), True, ""

    if len(tsyms) > len(sols):
        return None, False, "解的个数不足以匹配 target 变量"
    values = set()
    for perm in itertools.permutations(sols, len(tsyms)):
        mapping = {tsyms[i]: perm[i] for i in range(len(tsyms))}
        try:
            val = sp.simplify(te.subs(mapping))
        except Exception:
            return None, False, "target 代入失败"
        if val.free_symbols:
            return None, False, "target 代入后仍含未知量"
        values.add(_fmt_num(val))
    if len(values) != 1:
        return None, False, "target 取值随根的排列变化，非对称且不唯一"
    return next(iter(values)), True, ""


def tool_solve(args):
    """
    方程求解（单变量 / 公共根），支持定义域、select、target_expression。
    args 可含：equation 或 equations[]、variable 或 variables[]、
              domain(real|complex|integer|positive_integer)、
              common_root(bool)、select、target_expression。
    """
    if not _SYMPY_OK:
        return _fail("sympy 未安装")
    try:
        eqs_in = args.get("equations")
        if not eqs_in:
            single = (args.get("equation") or "").strip()
            eqs_in = [single] if single else []
        eqs_in = [e for e in eqs_in if e and str(e).strip()]
        if not eqs_in:
            return _fail("缺少 equation")

        exprs = [_to_expr_pair(str(e)) for e in eqs_in]

        var_names = args.get("variables") or []
        if not var_names and args.get("variable"):
            var_names = [args.get("variable")]
        var_names = [v.strip().lower() for v in var_names if v and str(v).strip()]

        all_syms = sorted(set().union(*[e.free_symbols for e in exprs]),
                          key=lambda s: s.name)
        if not all_syms:
            return _fail("方程中没有未知数")

        domain = (args.get("domain") or "real").lower()
        if domain not in ("real", "complex", "integer", "positive_integer"):
            return _fail("非法 domain")

        common_root = bool(args.get("common_root")) or len(exprs) > 1
        target_expr = args.get("target_expression")
        select = args.get("select")
        root_target = args.get("root_target")
        if select and select not in _SELECT_OPS:
            return _fail(f"非法 select: {select}")
        if root_target and root_target not in _ROOT_TARGETS:
            return _fail(f"非法 root_target: {root_target}")

        by_name = {s.name: s for s in all_syms}
        if var_names:
            if var_names[0] not in by_name:
                return _fail(f"指定变量 {var_names[0]} 不在方程中")
            sym = by_name[var_names[0]]
        elif len(all_syms) == 1:
            sym = all_syms[0]
        else:
            return _fail("方程含多个未知数，需指定 variable")

        if domain != "complex":
            real_sym = sp.Symbol(sym.name, real=True)
            exprs = [e.subs(sym, real_sym) for e in exprs]
            sym = real_sym

        if common_root:
            raw = sp.solve(exprs[0], sym)
            roots = []
            for r in raw:
                if all(sp.simplify(e.subs(sym, r)) == 0 for e in exprs):
                    roots.append(r)
            if not roots:
                return _fail("无公共根（空集）")
            sols = _filter_domain(roots, domain)
            primary = sym.name
        else:
            raw = sp.solve(exprs[0], sym)
            if raw is None or raw == []:
                return _fail("无解")
            if isinstance(raw, dict):
                return _fail("无法以单变量形式解析解")
            sols = _filter_domain(raw, domain)
            primary = sym.name

        if not sols:
            return _fail(f"{domain} 域下无解")

        if root_target:
            # 回代验证完整根集合满足全部原方程
            for r in sols:
                if any(sp.simplify(expr.subs(sym, r)) != 0 for expr in exprs):
                    return _fail("根回代验证失败")
            rval, ok_r, reason_r = _apply_root_target(sols, root_target)
            if not ok_r:
                return _fail(reason_r)
            text = f"{root_target} = {rval}"
            return _ok(text, text=text, value=rval, roots=[_fmt_num(s) for s in sols],
                       solutions=[_fmt_num(s) for s in sols], root_target=root_target,
                       target_value=rval, unique=True, verified=True, domain=domain)

        selected = None
        if select:
            sval, reason = _apply_select(sols, select)
            if sval is None:
                return _fail(reason)
            selected = sval
            sols = [sval]

        sol_strs = [_fmt_num(s) for s in sols]

        if target_expr:
            tval, ok_t, reason_t = _eval_solve_target(target_expr, primary, sols)
            if not ok_t:
                return _fail(reason_t)
            text = f"{target_expr} = {tval}"
            return _ok(text, text=text, value=tval, solutions=sol_strs,
                       target_expression=target_expr, target_value=tval,
                       unique=True, verified=True, domain=domain)

        unique = len(sol_strs) == 1
        extra = {"domain": domain}
        if selected is not None:
            extra["selected"] = _fmt_num(selected)
            extra["select"] = select
        if unique:
            text = f"{primary} = {sol_strs[0]}"
            return _ok(text, text=text, value=sol_strs[0], solutions=sol_strs,
                       unique=True, verified=True, **extra)
        text = f"{primary} = " + ", ".join(sol_strs)
        return _ok(text, text=text, value=None, solutions=sol_strs,
                   unique=False, verified=True, **extra)
    except Exception as e:
        return _fail(f"solve 解析失败: {e}")


def tool_arith(args):
    if not _SYMPY_OK:
        return _fail("sympy 未安装")
    try:
        s = args.get("expression", "")
        probe = parse_expr(s, transformations=_TRANSF, evaluate=False)
        if probe.is_Atom and not getattr(probe, "is_number", False):
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
    任意元线性方程组（N 个方程 / N 个变量），支持 target_expression 与回代验证。
    args: {
      "equations": ["a+b+c=6", "4*a+2*b+c=11", "9*a+3*b+c=18"],
      "variables": ["a", "b", "c"],
      "target_expression": "100*a+10*b+c"   # 可选，亦兼容旧字段 target
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
        if not isinstance(syms, (list, tuple)):
            syms = (syms,)
        local = {s.name: s for s in syms}
        eqs = []
        for es in eqs_in:
            if "=" not in es:
                return _fail("方程格式非法")
            lhs, rhs = es.split("=", 1)
            eqs.append(sp.Eq(_expr(lhs, local), _expr(rhs, local)))
        # 线性性检查（仅针对系统变量）
        for eq in eqs:
            poly = (eq.lhs - eq.rhs)
            for s in syms:
                if sp.degree(sp.expand(poly), s) > 1:
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
            return _fail("欠定系统，无唯一解")
        exact = {syms[i]: sp.nsimplify(sol_tuple[i]) for i in range(len(syms))}
        # 回代验证
        for eq in eqs:
            if sp.simplify(eq.lhs.subs(exact) - eq.rhs.subs(exact)) != 0:
                return _fail("回代验证失败")
        mapping = {var_names[i]: _fmt_num(sol_tuple[i]) for i in range(len(var_names))}

        target = (args.get("target_expression") or args.get("target") or "").strip()
        if target:
            t_expr = _expr(target, local)
            t_val = sp.simplify(t_expr.subs(exact))
            if t_val.free_symbols:
                return _fail("目标量仍含未知符号")
            t_val = _fmt_num(t_val)
            text = f"{target} = {t_val}"
            return _ok(text, text=text, value=t_val, solution=mapping,
                       target=target, target_expression=target,
                       target_value=t_val, verified=True, unique=True)

        text = ", ".join(f"{k} = {v}" for k, v in mapping.items())
        return _ok(text, text=text, solution=mapping, unique=True, verified=True)
    except Exception as e:
        return _fail(f"linear_system_solver 解析失败: {e}")


def _prep_inequality(s):
    """把 |expr| 写成 Abs(expr)，并归一化关系符号。"""
    s = s.strip()
    s = s.replace("\\le", "<=").replace("\\ge", ">=")
    s = s.replace("≤", "<=").replace("≥", ">=")
    s = s.replace("\\leq", "<=").replace("\\geq", ">=")
    return _abs_to_func(s)


def _interval_list(s):
    """把解集拆成 [(lo, hi, lo_open, hi_open), ...]；无法识别返回 None。"""
    out = []
    if s == sp.S.EmptySet:
        return out
    parts = s.args if isinstance(s, sp.Union) else [s]
    for p in parts:
        if isinstance(p, sp.Interval):
            out.append((p.start, p.end, bool(p.left_open), bool(p.right_open)))
        elif isinstance(p, sp.FiniteSet):
            for v in p.args:
                out.append((v, v, False, False))
        else:
            return None
    return out


def _integers_in(intervals):
    """枚举有限区间内的整数；任一无界区间返回 None。"""
    vals = set()
    for lo, hi, lo_open, hi_open in intervals:
        if lo == -sp.oo or hi == sp.oo:
            return None
        lo_i = int(sp.ceiling(lo))
        if lo_open and sp.Integer(lo_i) == lo:
            lo_i += 1
        hi_i = int(sp.floor(hi))
        if hi_open and sp.Integer(hi_i) == hi:
            hi_i -= 1
        for v in range(lo_i, hi_i + 1):
            vals.add(v)
    return sorted(vals)


def tool_inequality_solver(args):
    """
    多约束不等式求解器（含绝对值/根式定义域），支持整数聚合目标。
    args: {"constraints": ["abs(x-3)<=5", "x>0"], "variable": "x",
           "domain": "integer", "target": "sum"}
    """
    if not _SYMPY_OK:
        return _fail("sympy 未安装")
    try:
        constraints = args.get("constraints") or []
        if not constraints:
            single = (args.get("constraint") or "").strip()
            constraints = [single] if single else []
        constraints = [c for c in constraints if c and str(c).strip()]
        if not constraints:
            return _fail("缺少 constraints")
        var_name = (args.get("variable") or "x").strip().lower()
        x = sp.Symbol(var_name, real=True)
        domain = (args.get("domain") or "real").lower()
        if domain not in ("real", "integer", "positive_integer"):
            return _fail("非法 domain")
        target = args.get("target")

        sol = sp.S.Reals
        rels = []
        for c in constraints:
            cs = _prep_inequality(str(c))
            rel = parse_expr(cs, transformations=_TRANSF, local_dict={var_name: x})
            if not isinstance(rel, (sp.StrictLessThan, sp.LessThan,
                                    sp.StrictGreaterThan, sp.GreaterThan,
                                    sp.Eq, sp.Rel)):
                return _fail(f"非不等式约束: {c}")
            rels.append(rel)
            sset = sp.solveset(rel, x, domain=sp.S.Reals)
            sol = sp.Intersection(sol, sset)
        sol = sp.simplify(sol) if not isinstance(sol, sp.Set) else sol

        if domain == "positive_integer":
            sol = sp.Intersection(sol, sp.Interval.open(0, sp.oo))

        if sol == sp.S.EmptySet:
            return _ok("空集", text="空集", solution_set="EmptySet",
                       integer_values=[], target=target,
                       target_value=None, verified=True, empty=True)

        intervals = _interval_list(sol)
        sset_str = str(sol)

        if target in (None, "solution_set"):
            iv = _integers_in(intervals) if intervals is not None else None
            return _ok(sset_str, text=sset_str, solution_set=sset_str,
                       integer_values=iv, target=target or "solution_set",
                       target_value=sset_str, verified=True)

        if target == "interval_length":
            if intervals is None or len(intervals) != 1:
                return _fail("区间长度仅适用于单一有限区间")
            lo, hi, _, _ = intervals[0]
            if lo == -sp.oo or hi == sp.oo:
                return _fail("无界区间无长度")
            val = _fmt_num(sp.nsimplify(hi - lo))
            return _ok(val, text=f"interval_length = {val}", solution_set=sset_str,
                       target="interval_length", target_value=val, verified=True)

        use_integers = (domain in ("integer", "positive_integer")
                        or target in ("integer_values", "count", "sum",
                                      "minimum_integer", "maximum_integer"))

        if use_integers:
            if intervals is None:
                return _fail("解集结构无法枚举整数")
            int_vals = _integers_in(intervals)
            if int_vals is None:
                return _fail("无界整数集合，无法聚合")
            if len(int_vals) > 10000:
                return _fail("整数解过多，拒绝聚合")
            # 逐点回代验证：每个枚举出的整数都必须满足全部原始约束
            for v in int_vals:
                if not all(bool(r.subs(x, sp.Integer(v))) for r in rels):
                    return _fail(f"整数解 {v} 回代验证失败")
            if target == "integer_values":
                v = str(int_vals)
            elif target == "count":
                v = str(len(int_vals))
            elif target == "sum":
                v = str(sum(int_vals))
            elif target in ("minimum", "minimum_integer"):
                if not int_vals:
                    return _fail("整数解为空")
                v = str(min(int_vals))
            elif target in ("maximum", "maximum_integer"):
                if not int_vals:
                    return _fail("整数解为空")
                v = str(max(int_vals))
            else:
                return _fail(f"未知 target: {target}")
            return _ok(v, text=v, solution_set=sset_str, integer_values=int_vals,
                       target=target, target_value=v, verified=True)

        # 实数域 min/max：取可达到的区间端点
        if intervals is None:
            return _fail("解集结构无法取端点")
        if target == "minimum":
            cands = [(lo, op) for lo, hi, op, _ in intervals if lo != -sp.oo]
            if not cands:
                return _fail("无下界，最小值不存在")
            lo, op = min(cands, key=lambda t: float(t[0]))
            if op:
                return _fail("下界为开区间，最小值不可达")
            val = _fmt_num(sp.nsimplify(lo))
            return _ok(val, text=val, solution_set=sset_str, target=target,
                       target_value=val, verified=True)
        if target == "maximum":
            cands = [(hi, op) for lo, hi, _, op in intervals if hi != sp.oo]
            if not cands:
                return _fail("无上界，最大值不存在")
            hi, op = max(cands, key=lambda t: float(t[0]))
            if op:
                return _fail("上界为开区间，最大值不可达")
            val = _fmt_num(sp.nsimplify(hi))
            return _ok(val, text=val, solution_set=sset_str, target=target,
                       target_value=val, verified=True)
        return _fail(f"未知 target: {target}")
    except Exception as e:
        return _fail(f"inequality_solver 解析失败: {e}")


def tool_sequence_tool(args):
    """
    等差/等比数列工具，精确数值。
    args: {"sequence_type": "geometric", "first_term": "3", "ratio": "2",
           "target": "nth_term", "n": 8}
    """
    if not _SYMPY_OK:
        return _fail("sympy 未安装")
    try:
        stype = (args.get("sequence_type") or "").strip().lower()
        if stype not in ("arithmetic", "geometric"):
            return _fail("sequence_type 须为 arithmetic 或 geometric")
        ft = args.get("first_term")
        if ft is None or str(ft).strip() == "":
            return _fail("缺少 first_term")
        a1 = sp.nsimplify(_expr(str(ft)))
        target = (args.get("target") or "").strip()
        if not target:
            return _fail("缺少 target")

        if stype == "arithmetic":
            d_in = args.get("difference")
            if d_in is None or str(d_in).strip() == "":
                return _fail("等差数列缺少 difference")
            d = sp.nsimplify(_expr(str(d_in)))
            term = lambda n: a1 + (n - 1) * d
            psum = lambda n: n * (2 * a1 + (n - 1) * d) / 2
        else:
            r_in = args.get("ratio")
            if r_in is None or str(r_in).strip() == "":
                return _fail("等比数列缺少 ratio")
            r = sp.nsimplify(_expr(str(r_in)))
            term = lambda n: a1 * r ** (n - 1)
            psum = lambda n: a1 * n if r == 1 else a1 * (r ** n - 1) / (r - 1)

        # 一致性验证：若给出题面项列表，公式必须复现全部给定项，否则拒绝
        given = args.get("given_terms") or []
        for i, g in enumerate(given, start=1):
            try:
                gv = sp.nsimplify(_expr(str(g)))
            except Exception:
                return _fail(f"given_terms[{i}] 无法解析: {g}")
            if sp.simplify(term(i) - gv) != 0:
                return _fail(f"第 {i} 项验证失败: 公式={term(i)}, 给定={gv}")

        def _need_n():
            n = args.get("n")
            if n is None:
                return None
            try:
                ni = int(n)
            except Exception:
                return None
            return ni if ni >= 1 else None

        if target == "nth_term":
            n = _need_n()
            if n is None:
                return _fail("n 必须为正整数")
            v = _fmt_num(sp.nsimplify(term(n)))
            return _ok(v, text=f"a_{n} = {v}", target=target, n=n,
                       value=v, target_value=v, verified=True)
        if target == "partial_sum":
            n = _need_n()
            if n is None:
                return _fail("n 必须为正整数")
            v = _fmt_num(sp.nsimplify(psum(n)))
            return _ok(v, text=f"S_{n} = {v}", target=target, n=n,
                       value=v, target_value=v, verified=True)

        if target in ("first_positive_index", "first_threshold_index",
                      "last_positive_integer_index"):
            threshold = sp.nsimplify(_expr(str(args.get("threshold", "0"))))
            if stype != "arithmetic":
                return _fail("阈值/正项索引目标当前仅支持等差数列")
            if d == 0:
                return _fail("公差为 0，无法确定索引")
            # term(n) 关于 n 单调；解 term(n) (> / <) threshold 的整数边界
            n_sym = sp.Symbol("n", positive=True)
            expr_n = a1 + (n_sym - 1) * d
            if target == "first_positive_index":
                sol = sp.solve(expr_n > 0, n_sym)
            elif target == "first_threshold_index":
                sol = sp.solve(expr_n > threshold, n_sym)
            else:
                sol = sp.solve(expr_n > 0, n_sym)
            # 找满足条件的最小/最大正整数索引
            cond = (lambda n: term(n) > 0) if target != "first_threshold_index" \
                else (lambda n: term(n) > threshold)
            if d < 0:
                # 递减：最后一个满足正/阈值的索引
                n = 1
                if not cond(1):
                    return _fail("首项已不满足条件")
                while cond(n + 1) and n < 10 ** 6:
                    n += 1
                idx = n
            else:
                # 递增：第一个满足条件的索引
                n = 1
                while not cond(n) and n < 10 ** 6:
                    n += 1
                if not cond(n):
                    return _fail("未找到满足条件的索引")
                idx = n
            tval = _fmt_num(sp.nsimplify(term(idx)))
            return _ok(str(idx), text=f"n = {idx}, term = {tval}",
                       target=target, value=str(idx), target_value=str(idx),
                       term_value=tval, verified=True)

        return _fail(f"未知 target: {target}")
    except Exception as e:
        return _fail(f"sequence_tool 解析失败: {e}")


def tool_polynomial_coefficient_match(args):
    """
    多项式系数匹配：令两侧关于 polynomial_variable 恒等，解出待求参数。
    args: {left_expression, right_expression, polynomial_variable,
           unknowns[], target_expression, domain}
    """
    if not _SYMPY_OK:
        return _fail("sympy 未安装")
    try:
        left = args.get("left_expression", "")
        right = args.get("right_expression", "")
        pvar = (args.get("polynomial_variable") or "x").strip()
        unknowns = args.get("unknowns") or []
        target = (args.get("target_expression") or "").strip()
        if not left or not right:
            return _fail("缺少 left/right_expression")
        if not unknowns:
            return _fail("缺少 unknowns")

        xs = sp.Symbol(pvar)
        usyms = [sp.Symbol(u) for u in unknowns]
        local = {pvar: xs}
        local.update({u: s for u, s in zip(unknowns, usyms)})
        L = _expr(_abs_to_func(left), local)
        R = _expr(_abs_to_func(right), local)
        diff = sp.expand(L - R)
        try:
            poly = sp.Poly(diff, xs)
        except sp.PolynomialError:
            num, den = sp.fraction(sp.together(L - R))
            if xs not in (sp.expand(den)).free_symbols:
                try:
                    poly = sp.Poly(sp.expand(num), xs)
                except sp.PolynomialError:
                    return _fail("无法转为关于指定变量的多项式")
            else:
                try:
                    poly = sp.Poly(sp.expand(num), xs)
                except sp.PolynomialError:
                    return _fail("无法转为关于指定变量的多项式")
        if poly.free_symbols - set(usyms) - {xs}:
            return _fail("存在未声明参数，拒绝自由参数")
        coeff_eqs = [sp.Eq(c, 0) for c in poly.all_coeffs() if c != 0]
        if not coeff_eqs:
            coeff_eqs = [sp.Eq(0, 0)]

        linear = True
        for eq in coeff_eqs:
            expr = sp.expand(eq.lhs - eq.rhs)
            try:
                upoly = sp.Poly(expr, *usyms)
            except Exception:
                linear = False
                break
            if upoly.total_degree() > 1:
                linear = False
                break
            for us in usyms:
                if sp.degree(expr, us) not in (0, 1):
                    linear = False
                    break
            if not linear:
                break
        if linear:
            sol_set = sp.linsolve(coeff_eqs, usyms)
            if sol_set in (None, set()) or len(sol_set) != 1:
                return _fail("系数线性系统无唯一解")
            sol_tuple = next(iter(sol_set))
            if any(val.free_symbols for val in sol_tuple):
                return _fail("存在无法消除的自由参数")
            sols = [{usyms[i]: sp.nsimplify(sol_tuple[i]) for i in range(len(usyms))}]
        else:
            sols = sp.solve(coeff_eqs, usyms, dict=True)
        if not sols:
            return _fail("系数方程无解")

        target_expr = _expr(_abs_to_func(target), local) if target else None
        valid, target_vals = [], set()
        for s in sols:
            if not all(u in s for u in usyms):
                continue
            if any(v.free_symbols for v in s.values()):
                continue
            if sp.simplify(sp.together(L.subs(s) - R.subs(s))) != 0:
                continue
            if target_expr is not None:
                tv = sp.simplify(target_expr.subs(s))
                if tv.free_symbols:
                    continue
                target_vals.add(_fmt_num(tv))
            valid.append(s)
        if not valid:
            return _fail("参数未全部求出或代回验证失败")
        if target_expr is None and len(valid) != 1:
            return _fail("参数解不唯一")
        if target_expr is not None and len(target_vals) != 1:
            return _fail("多组解导致目标值不唯一")

        sol0 = valid[0]
        mapping = {u: _fmt_num(sol0[sp.Symbol(u)]) for u in unknowns}
        if target_expr is None:
            text = ", ".join(f"{k} = {v}" for k, v in mapping.items())
            return _ok(text, text=text, value=None,
                       coefficient_equations=[str(e) for e in coeff_eqs],
                       solutions=mapping, verified=True, unique=True)
        tval = next(iter(target_vals))
        text = f"{target} = {tval}"
        return _ok(text, text=text, value=tval,
                   coefficient_equations=[str(e) for e in coeff_eqs],
                   solutions=mapping, target_expression=target,
                   target_value=tval, verified=True, unique=True)
    except Exception as e:
        return _fail(f"polynomial_coefficient_match 解析失败: {e}")


_MAX_ENUM = 100000


def _domain_candidates(spec):
    """根据单变量域描述返回有限候选列表；无界/非法返回 None。"""
    dtype = (spec.get("type") or "").lower()
    if dtype == "finite_values":
        vals = spec.get("values")
        if not vals:
            return None
        out = []
        for v in vals:
            try:
                out.append(sp.nsimplify(_expr(str(v))))
            except Exception:
                return None
        return out
    lo, hi = spec.get("minimum"), spec.get("maximum")
    if lo is None or hi is None:
        return None
    lo, hi = int(lo), int(hi)
    if dtype == "positive_integer":
        lo = max(lo, 1)
    elif dtype == "nonnegative_integer":
        lo = max(lo, 0)
    elif dtype in ("integer", "prime"):
        pass
    else:
        return None
    if hi < lo:
        return []
    rng = range(lo, hi + 1)
    if dtype == "prime":
        return [sp.Integer(v) for v in rng if sp.isprime(v)]
    return [sp.Integer(v) for v in rng]


def tool_discrete_constraint_enumerator(args):
    """
    通用有限离散约束枚举。
    args: {variables[], domains{var:{type,minimum,maximum|values}},
           constraints[], target_expression, aggregation}
    """
    if not _SYMPY_OK:
        return _fail("sympy 未安装")
    try:
        import itertools
        variables = args.get("variables") or []
        domains = args.get("domains") or {}
        constraints = args.get("constraints") or []
        target = (args.get("target_expression") or "").strip()
        agg = (args.get("aggregation") or "").strip() or "all_solutions"
        if not variables:
            return _fail("缺少 variables")

        syms = {v: sp.Symbol(v) for v in variables}
        cand = {}
        total = 1
        for v in variables:
            c = _domain_candidates(domains.get(v, {}))
            if c is None:
                return _fail(f"变量 {v} 无有限域，拒绝无界枚举")
            cand[v] = c
            total *= max(len(c), 1)
            if total > _MAX_ENUM:
                return _fail("搜索空间超过上限，拒绝")

        rels = []
        for c in constraints:
            cs = _abs_to_func(str(c))
            if "=" in cs and not re.search(r"[<>]=?|!=", cs):
                lhs, rhs = cs.split("=", 1)
                rels.append(sp.Eq(_expr(lhs, syms), _expr(rhs, syms)))
            else:
                rels.append(parse_expr(cs, transformations=_TRANSF, local_dict=syms))

        target_expr = _expr(_abs_to_func(target), syms) if target else None
        solutions, values = [], []
        for combo in itertools.product(*[cand[v] for v in variables]):
            sub = {syms[v]: combo[i] for i, v in enumerate(variables)}
            if not all(bool(sp.simplify(r.subs(sub))) for r in rels):
                continue
            assignment = {v: _fmt_num(combo[i]) for i, v in enumerate(variables)}
            solutions.append(assignment)
            if target_expr is not None:
                tv = sp.simplify(target_expr.subs(sub))
                if tv.free_symbols:
                    return _fail("目标含未约束符号")
                values.append(sp.nsimplify(tv))

        if agg == "all_solutions":
            return _ok(str(solutions), text=str(solutions), solutions=solutions,
                       aggregation=agg, target_value=str(solutions),
                       count=len(solutions), verified=True)
        if not target and agg != "count":
            return _fail("该聚合需要 target_expression")
        if agg == "count":
            v = str(len(solutions))
        elif agg == "all_values":
            uniq = sorted(set(values), key=lambda z: float(z))
            v = str([_fmt_num(z) for z in uniq])
        elif agg == "sum":
            v = _fmt_num(sum(values, sp.Integer(0)))
        elif agg == "minimum":
            if not values:
                return _fail("无解，无法取最小")
            v = _fmt_num(min(values, key=lambda z: float(z)))
        elif agg == "maximum":
            if not values:
                return _fail("无解，无法取最大")
            v = _fmt_num(max(values, key=lambda z: float(z)))
        elif agg == "unique_value":
            uniq = set(_fmt_num(z) for z in values)
            if len(uniq) != 1:
                return _fail("目标值非唯一")
            v = next(iter(uniq))
        else:
            return _fail(f"未知 aggregation: {agg}")
        return _ok(v, text=v, solutions=solutions, aggregation=agg,
                   target_value=v, count=len(solutions), verified=True)
    except Exception as e:
        return _fail(f"discrete_constraint_enumerator 解析失败: {e}")


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
    "inequality_solver": tool_inequality_solver,
    "sequence_tool": tool_sequence_tool,
    "polynomial_coefficient_match": tool_polynomial_coefficient_match,
    "discrete_constraint_enumerator": tool_discrete_constraint_enumerator,
}


def run_tool(name, args):
    fn = _REGISTRY.get(name)
    return fn(args or {}) if fn else _fail(f"未知工具: {name}")
