# Phase 2.5/2.6 工具分配语义审计

非 no_tool 槽位: 96
validation 失败: 0
tool_success 失败: 0
replace_target_match_true: 78
replace_target_match_false: 0
assist_scope_match_true: 18
assist_scope_match_false: 0
unknown_target_count: 0

## 明细

- [OK] Q0 Step1 | factor(replace) | req=x**2 + x - 6 | out=(x - 2)*(x + 3) | gate=True
- [OK] Q1 Step1 | arith(replace) | req=None | out=36 | gate=True
- [OK] Q1 Step2 | arith(replace) | req=None | out=26 | gate=True
- [OK] Q9 Step6 | solve(replace) | req=x | out=-1/8 | gate=True
- [OK] Q11 Step4 | inequality_solver(replace) | req=None | out=-15 | gate=True
- [OK] Q15 Step4 | inequality_solver(replace) | req=x | out=11/2 | gate=True
- [OK] Q20 Step5 | discrete_constraint_enumerator(replace) | req=None | out=['4', '6', '9', '10', '14', '15', '21', '22', '25', '26', '33', '34', '35', '39', '49', '55', '65', '77'] | gate=True
- [OK] Q22 Step1 | arith(replace) | req=None | out=22717712 | gate=True
- [OK] Q34 Step4 | sequence_tool(replace) | req=None | out=243/625 | gate=True
- [OK] Q36 Step2 | arith(replace) | req=y | out=-4 | gate=True
- [OK] Q36 Step3 | simplify(assist) | req=x**4 + 4*x**2 | out=x**2*(x**2 + 4) | gate=True
- [OK] Q36 Step4 | arith(replace) | req=-4 < x**4 + 4*x**2 | out=-4 | gate=True
- [OK] Q42 Step2 | solve(assist) | req=None | out=x = -6, 8 | gate=True
- [OK] Q42 Step3 | solve(replace) | req=x | out=2 | gate=True
- [OK] Q43 Step6 | inequality_solver(replace) | req=None | out=32 | gate=True
- [OK] Q43 Step8 | inequality_solver(replace) | req=None | out=32 | gate=True
- [OK] Q44 Step1 | arith(replace) | req=None | out=7/6 | gate=True
- [OK] Q44 Step2 | arith(replace) | req=None | out=14 | gate=True
- [OK] Q52 Step3 | sequence_tool(replace) | req=None | out=77 | gate=True
- [OK] Q54 Step3 | inequality_solver(replace) | req=t | out=Interval.open(60, 70) | gate=True
- [OK] Q57 Step4 | discrete_constraint_enumerator(replace) | req=n | out=0 | gate=True
- [OK] Q59 Step6 | complex_arithmetic(assist) | req=None | out=20 | gate=True
- [OK] Q59 Step9 | complex_arithmetic(replace) | req=None | out=20 | gate=True
- [OK] Q63 Step1 | solve(assist) | req=None | out=x = -6, -1/2 | gate=True
- [OK] Q70 Step1 | subst(replace) | req=y**2 | out=81 | gate=True
- [OK] Q70 Step2 | subst(replace) | req=3*x*y | out=81 | gate=True
- [OK] Q74 Step3 | solve(assist) | req=None | out=5 | gate=True
- [OK] Q74 Step4 | solve(replace) | req=None | out=5 | gate=True
- [OK] Q75 Step2 | linear_system_solver(replace) | req=a | out=-1 | gate=True
- [OK] Q75 Step3 | linear_system_solver(replace) | req=100*a + 10*b + c | out=-55 | gate=True
- [OK] Q77 Step5 | solve(replace) | req=x | out=-7 | gate=True
- [OK] Q78 Step1 | arith(replace) | req=None | out=0 | gate=True
- [OK] Q84 Step3 | linear_system_solver(replace) | req=-a*b + 2*a + 5*b | out=26 | gate=True
- [OK] Q87 Step2 | arith(replace) | req=None | out=16 | gate=True
- [OK] Q100 Step1 | simplify(assist) | req=3**(6*k) | out=729**k | gate=True
- [OK] Q102 Step1 | arith(replace) | req=None | out=12 | gate=True
- [OK] Q112 Step1 | linear_system_solver(replace) | req=b - c | out=-1 | gate=True
- [OK] Q112 Step2 | linear_system_solver(replace) | req=(b - c)**2 | out=1 | gate=True
- [OK] Q112 Step3 | linear_system_solver(replace) | req=b + c | out=7 | gate=True
- [OK] Q112 Step4 | linear_system_solver(replace) | req=a*(b + c) | out=14 | gate=True
- [OK] Q112 Step5 | linear_system_solver(replace) | req=a*(b + c) + (b - c)**2 | out=15 | gate=True
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
- [OK] Q137 Step1 | solve(replace) | req=None | out=1 | gate=True
- [OK] Q137 Step2 | expand(replace) | req=(x + 1)*(x + 2) | out=x**2 + 3*x + 2 | gate=True
- [OK] Q137 Step7 | solve(replace) | req=None | out=1 | gate=True
- [OK] Q139 Step3 | solve(assist) | req=x | out=x = -3, -1, 1, 3 | gate=True
- [OK] Q139 Step4 | solve(replace) | req=x | out=20 | gate=True
- [OK] Q139 Step5 | solve(replace) | req=x | out=20 | gate=True
- [OK] Q144 Step1 | expand(replace) | req=(2*x + 3*y)**2 | out=4*x**2 + 12*x*y + 9*y**2 | gate=True
- [OK] Q147 Step4 | polynomial_coefficient_match(replace) | req=x | out=-6 | gate=True
- [OK] Q147 Step5 | polynomial_coefficient_match(replace) | req=None | out={'A': '-6', 'B': '10'} | gate=True
- [OK] Q147 Step8 | factor(replace) | req=x**2 - 8*x + 15 | out=(x - 5)*(x - 3) | gate=True
- [OK] Q147 Step31 | polynomial_coefficient_match(replace) | req=None | out=10 | gate=True
- [OK] Q147 Step36 | polynomial_coefficient_match(replace) | req=None | out={'A': '-6', 'B': '10'} | gate=True
- [OK] Q150 Step6 | inequality_solver(replace) | req=t | out=12/7 | gate=True
- [OK] Q150 Step7 | inequality_solver(replace) | req=None | out=12/7 | gate=True
- [OK] Q151 Step1 | solve(assist) | req=None | out=x = 7/4 - sqrt(33)/4, sqrt(33)/4 + 7/4 | gate=True
- [OK] Q151 Step7 | solve(replace) | req=None | out=-1 | gate=True
- [OK] Q151 Step9 | solve(replace) | req=x | out=1 | gate=True
- [OK] Q151 Step12 | solve(replace) | req=None | out=-1 | gate=True
- [OK] Q153 Step1 | solve(assist) | req=None | out=x = -3/2, 1/9 | gate=True
- [OK] Q153 Step2 | solve(assist) | req=None | out=x = -3/2, -1/2 | gate=True
- [OK] Q153 Step4 | solve(replace) | req=x | out=-3/2 | gate=True
- [OK] Q171 Step5 | sequence_tool(replace) | req=None | out=243/8 | gate=True
- [OK] Q172 Step5 | solve(assist) | req=None | out=x = -3, 10 | gate=True
- [OK] Q173 Step3 | subst(replace) | req=x**3/2 + 36 | out=144 | gate=True
- [OK] Q174 Step1 | solve(assist) | req=None | out=x = 2 - sqrt(10)/5, sqrt(10)/5 + 2 | gate=True
- [OK] Q174 Step3 | solve(assist) | req=None | out=x = 2 - sqrt(10)/5, sqrt(10)/5 + 2 | gate=True
- [OK] Q176 Step1 | simplify(assist) | req=None | out=5**(b + 1) | gate=True
- [OK] Q178 Step1 | polynomial_coefficient_match(replace) | req=4*x**2 + 2*x - 1 | out=4 | gate=True
- [OK] Q178 Step3 | polynomial_coefficient_match(replace) | req=None | out={'a': '4', 'b': '1/4', 'c': '-5/4'} | gate=True
- [OK] Q178 Step4 | polynomial_coefficient_match(replace) | req=4*x**2 + 2*x - 1 | out={'a': '4', 'b': '1/4', 'c': '-5/4'} | gate=True
- [OK] Q178 Step5 | polynomial_coefficient_match(replace) | req=None | out=3 | gate=True
- [OK] Q185 Step4 | linear_system_solver(replace) | req=1/b - 1/a | out=-8/33 | gate=True
- [OK] Q185 Step5 | linear_system_solver(replace) | req=a - b | out=-8 | gate=True
- [OK] Q190 Step1 | expand(assist) | req=None | out=2*A*B*x**2 + A*C*x - 10*B*x - 5*C | gate=True
- [OK] Q190 Step7 | polynomial_coefficient_match(replace) | req=None | out=-9 | gate=True
- [OK] Q191 Step2 | simplify(assist) | req=(19 - 7*x)**2 | out=(7*x - 19)**2 | gate=True
- [OK] Q191 Step3 | arith(replace) | req=49*x**2 + 14*x*(19 - 7*x) + (19 - 7*x)**2 | out=361 | gate=True
- [OK] Q195 Step6 | inequality_solver(replace) | req=x | out=Interval(-3, 2) | gate=True
