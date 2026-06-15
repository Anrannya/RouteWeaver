# Phase 2.5/2.6 工具分配语义审计

非 no_tool 槽位: 52
validation 失败: 0
tool_success 失败: 0
replace_target_match_true: 35
replace_target_match_false: 0
assist_scope_match_true: 17
assist_scope_match_false: 0
unknown_target_count: 0

## 明细

- [OK] Q0 Step1 | factor(replace) | req=x**2 + x - 6 | out=(x - 2)*(x + 3) | gate=True
- [OK] Q1 Step1 | arith(replace) | req=None | out=36 | gate=True
- [OK] Q1 Step2 | arith(replace) | req=None | out=26 | gate=True
- [OK] Q22 Step1 | arith(replace) | req=None | out=22717712 | gate=True
- [OK] Q26 Step1 | expand(replace) | req=(x - 3)*(2*x + 5) | out=2*x**2 - x - 15 | gate=True
- [OK] Q36 Step3 | simplify(assist) | req=x**4 + 4*x**2 | out=x**2*(x**2 + 4) | gate=True
- [OK] Q44 Step1 | arith(replace) | req=None | out=7/6 | gate=True
- [OK] Q44 Step2 | arith(replace) | req=None | out=14 | gate=True
- [OK] Q59 Step6 | complex_arithmetic(assist) | req=None | out=20 | gate=True
- [OK] Q59 Step9 | complex_arithmetic(replace) | req=None | out=20 | gate=True
- [OK] Q63 Step1 | solve(assist) | req=None | out=x = -6, -1/2 | gate=True
- [OK] Q70 Step1 | subst(replace) | req=y**2 | out=81 | gate=True
- [OK] Q70 Step2 | subst(replace) | req=3*x*y | out=81 | gate=True
- [OK] Q72 Step1 | subst(replace) | req=k | out=14 | gate=True
- [OK] Q74 Step3 | solve(assist) | req=None | out=5 | gate=True
- [OK] Q87 Step2 | arith(replace) | req=None | out=16 | gate=True
- [OK] Q100 Step1 | simplify(assist) | req=3**(6*k) | out=729**k | gate=True
- [OK] Q102 Step1 | arith(replace) | req=None | out=12 | gate=True
- [OK] Q116 Step2 | arith(replace) | req=None | out=22/7 | gate=True
- [OK] Q118 Step1 | linear_system_solver(replace) | req=x | out=8 | gate=True
- [OK] Q118 Step2 | linear_system_solver(replace) | req=y | out=-1 | gate=True
- [OK] Q118 Step3 | linear_system_solver(replace) | req=x*y | out=-8 | gate=True
- [OK] Q126 Step1 | subst(replace) | req=2*x | out=8 | gate=True
- [OK] Q126 Step2 | subst(replace) | req=2*x - y | out=5 | gate=True
- [OK] Q126 Step3 | subst(replace) | req=-2*x + y + 24 | out=19 | gate=True
- [OK] Q130 Step1 | solve(assist) | req=None | out=x = 5/2 - sqrt(15)/2, sqrt(15)/2 + 5/2 | gate=True
- [OK] Q131 Step1 | linear_system_solver(assist) | req=x | out={'x': '1', 'y': '-2'} | gate=True
- [OK] Q131 Step2 | linear_system_solver(replace) | req=x | out=1 | gate=True
- [OK] Q131 Step3 | linear_system_solver(replace) | req=y | out=-2 | gate=True
- [OK] Q131 Step4 | linear_system_solver(replace) | req=x*y | out=-2 | gate=True
- [OK] Q132 Step1 | linear_system_solver(replace) | req=x | out=10 | gate=True
- [OK] Q132 Step2 | linear_system_solver(replace) | req=y | out=2 | gate=True
- [OK] Q132 Step3 | linear_system_solver(replace) | req=2*x | out=20 | gate=True
- [OK] Q132 Step4 | linear_system_solver(replace) | req=x*y | out=20 | gate=True
- [OK] Q132 Step5 | linear_system_solver(replace) | req=-x*y + 2*x | out=0 | gate=True
- [OK] Q137 Step1 | solve(assist) | req=None | out=x = -1 + sqrt(2), -sqrt(2) - 1 | gate=True
- [OK] Q137 Step2 | expand(replace) | req=(x + 1)*(x + 2) | out=x**2 + 3*x + 2 | gate=True
- [OK] Q144 Step1 | expand(replace) | req=(2*x + 3*y)**2 | out=4*x**2 + 12*x*y + 9*y**2 | gate=True
- [OK] Q147 Step1 | factor(replace) | req=x**2 - 8*x + 15 | out=(x - 5)*(x - 3) | gate=True
- [OK] Q147 Step8 | factor(replace) | req=x**2 - 8*x + 15 | out=(x - 5)*(x - 3) | gate=True
- [OK] Q151 Step1 | solve(assist) | req=None | out=x = 7/4 - sqrt(33)/4, sqrt(33)/4 + 7/4 | gate=True
- [OK] Q153 Step1 | solve(assist) | req=None | out=x = -3/2, 1/9 | gate=True
- [OK] Q153 Step2 | solve(assist) | req=None | out=x = -3/2, -1/2 | gate=True
- [OK] Q172 Step5 | solve(assist) | req=None | out=x = -3, 10 | gate=True
- [OK] Q173 Step3 | subst(replace) | req=x**3/2 + 36 | out=144 | gate=True
- [OK] Q174 Step1 | solve(assist) | req=None | out=x = 2 - sqrt(10)/5, sqrt(10)/5 + 2 | gate=True
- [OK] Q174 Step3 | solve(assist) | req=None | out=x = 2 - sqrt(10)/5, sqrt(10)/5 + 2 | gate=True
- [OK] Q176 Step1 | simplify(assist) | req=None | out=5**(b + 1) | gate=True
- [OK] Q179 Step2 | subst(replace) | req=x | out=-1 | gate=True
- [OK] Q190 Step1 | expand(assist) | req=None | out=2*A*B*x**2 + A*C*x - 10*B*x - 5*C | gate=True
- [OK] Q191 Step2 | simplify(assist) | req=(19 - 7*x)**2 | out=(7*x - 19)**2 | gate=True
- [OK] Q191 Step3 | arith(replace) | req=49*x**2 + 14*x*(19 - 7*x) + (19 - 7*x)**2 | out=361 | gate=True
