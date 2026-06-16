# Phase 26 配对诊断

题目总数: 35
no_tool正确: 10
with_tool正确: 12
wrong_to_right: 8
right_to_wrong: 6
right_to_right: 4
wrong_to_wrong: 17
net_gain: 2
DAG_missing: 0

## 逐题配对

| qid | no_tool | with_tool | transition | tools | diff |
|-----|---------|-----------|------------|-------|------|
| Q2 | True | False | right_to_wrong | - | final: no='x = 9/7', with='\\frac{16}{7}' |
| Q9 | False | False | wrong_to_wrong | solve | final_answer相同 |
| Q11 | False | False | wrong_to_wrong | inequality_solver | 工具介入后final变化: '-4' -> 'The final answer is 15.' |
| Q15 | True | False | right_to_wrong | inequality_solver | 工具介入后final变化: '5.5' -> '11/2' |
| Q20 | True | True | right_to_right | discrete_constraint_enumerator | 工具介入后final变化: 'Let’s list all valid pairs of prime roots \\( |
| Q33 | False | False | wrong_to_wrong | - | final: no='-12.6', with='-6.6' |
| Q34 | False | True | wrong_to_right | sequence_tool | 工具介入后final变化: 'The eighth term of the sequence is \\(\\frac{ |
| Q38 | False | False | wrong_to_wrong | - | final: no='The maximum value of \\( y \\) is \\(-23\\).\n\n\ |
| Q50 | False | False | wrong_to_wrong | - | final: no='The largest value of \\( f(x) - g(x) \\) is \\( 8 |
| Q52 | False | True | wrong_to_right | sequence_tool | 工具介入后final变化: '986' -> '12' |
| Q54 | False | True | wrong_to_right | inequality_solver | 工具介入后final变化: 'The largest \\( t \\) which will bring the am |
| Q73 | False | False | wrong_to_wrong | - | final: no='The final answer is \\( k = \\frac{3323}{1} \\).' |
| Q75 | False | True | wrong_to_right | linear_system_solver,linear_system_solver | 工具介入后final变化: '245' -> '-55' |
| Q77 | False | False | wrong_to_wrong | solve | 工具介入后final变化: 'The final answer is \\(\\frac{7}{4}\\).' -> ' |
| Q78 | False | False | wrong_to_wrong | arith | 工具介入后final变化: '0.83' -> '0.32' |
| Q85 | False | False | wrong_to_wrong | - | final: no='The final answer is 108.', with='The first term t |
| Q106 | False | False | wrong_to_wrong | - | final_answer相同 |
| Q115 | True | False | right_to_wrong | - | final: no="Let the son's current age be \\( x \\).  \nThe fa |
| Q119 | True | False | right_to_wrong | - | final: no='From the given information, the vertex form is \\ |
| Q131 | True | True | right_to_right | linear_system_solver,linear_system_solver,linear_system_solver,linear_system_solver | 工具介入后final变化: '-2' -> 'The product of \\(x\\) and \\(y\\) is |
| Q134 | False | True | wrong_to_right | - | final: no='The final answer is \\(a = 1\\).', with='We have  |
| Q137 | False | False | wrong_to_wrong | expand,solve | 工具介入后final变化: '14.5' -> "-3/2 + 17 = 31/2\n\nHowever, the pr |
| Q139 | True | True | right_to_right | solve,solve,solve | 工具介入后final变化: 'The final answer is $\\boxed{20}$.' -> 'The f |
| Q147 | True | False | right_to_wrong | polynomial_coefficient_match,polynomial_coefficient_match,factor | 工具介入后final变化: 'The final answer is \\(\\boxed{(-6, 10)}\\).' |
| Q150 | False | True | wrong_to_right | inequality_solver,inequality_solver | 工具介入后final变化: 'The final answer is \\(\\boxed{\\frac{108}{10 |
| Q151 | False | False | wrong_to_wrong | solve,solve,solve | 工具介入后final变化: '-4' -> '112' |
| Q153 | False | False | wrong_to_wrong | solve,solve,solve | 工具介入后final变化: 'There is no value of \\( x \\) that satisfies |
| Q168 | False | False | wrong_to_wrong | - | final_answer相同 |
| Q171 | False | True | wrong_to_right | sequence_tool | 工具介入后final变化: 'The eighth term of the sequence is \\(\\frac{ |
| Q172 | False | False | wrong_to_wrong | solve | 工具介入后final变化: '7' -> 'The final answer is \\(\\frac{\\sqrt{7 |
| Q178 | False | True | wrong_to_right | polynomial_coefficient_match,polynomial_coefficient_match,polynomial_coefficient_match,polynomial_coefficient_match | 工具介入后final变化: 'The final answer is \\(\\frac{5}{4}\\).' -> ' |
| Q180 | True | True | right_to_right | - | final_answer相同 |
| Q184 | False | False | wrong_to_wrong | - | final_answer相同 |
| Q185 | False | False | wrong_to_wrong | linear_system_solver,linear_system_solver | 工具介入后final变化: 'The final answer is \\(-\\frac{1}{33}\\).' -> |
| Q190 | True | False | right_to_wrong | expand,polynomial_coefficient_match | 工具介入后final变化: '-9' -> '-11' |
