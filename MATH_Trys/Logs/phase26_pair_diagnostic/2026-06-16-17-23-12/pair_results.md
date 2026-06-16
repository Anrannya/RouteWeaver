# Phase 26 配对诊断

题目总数: 35
no_tool正确: 6
with_tool正确: 18
wrong_to_right: 13
right_to_wrong: 1
right_to_right: 5
wrong_to_wrong: 16
net_gain: 12
DAG_missing: 0

## 逐题配对

| qid | no_tool | with_tool | transition | tools | diff |
|-----|---------|-----------|------------|-------|------|
| Q2 | True | True | right_to_right | - | final: no='x = 9/7', with='From the sub-problems, we have:\n |
| Q9 | False | False | wrong_to_wrong | solve | 工具介入后final变化: 'The smallest value of \\(x\\) is \\(-\\frac{3 |
| Q11 | False | True | wrong_to_right | inequality_solver | 工具介入后final变化: '15' -> '-15' |
| Q15 | True | True | right_to_right | inequality_solver | 工具介入后final变化: '5.5' -> '11/2' |
| Q20 | False | True | wrong_to_right | discrete_constraint_enumerator | 工具介入后final变化: 'Let’s list all valid pairs of prime roots \\( |
| Q33 | False | False | wrong_to_wrong | - | final: no='-6.6', with='-12.6' |
| Q34 | False | True | wrong_to_right | sequence_tool | 工具介入后final变化: 'The final answer is \\(\\frac{625}{63}\\).' - |
| Q38 | False | False | wrong_to_wrong | - | final: no='The maximum value of \\( y \\) is \\( 1 \\).', wi |
| Q50 | False | False | wrong_to_wrong | - | final: no='8', with='The largest value of \\( f(x) - g(x) \\ |
| Q52 | False | True | wrong_to_right | sequence_tool | 工具介入后final变化: 'The least positive integer in the sequence is |
| Q54 | False | True | wrong_to_right | inequality_solver | 工具介入后final变化: 'The largest \\( t \\) which will bring the am |
| Q73 | False | False | wrong_to_wrong | - | final: no='The final answer is \\( k = 600 - 104\\sqrt{131}  |
| Q75 | False | True | wrong_to_right | linear_system_solver,linear_system_solver | 工具介入后final变化: '-5' -> '-55' |
| Q77 | False | False | wrong_to_wrong | solve | 工具介入后final变化: '-2' -> 'The final answer is \\(\\frac{7}{4}\\ |
| Q78 | False | False | wrong_to_wrong | arith | 工具介入后final变化: '0.44' -> 'The final answer is \\(0.00\\).' |
| Q85 | False | False | wrong_to_wrong | - | final: no='The first term that is greater than 125 is 108.', |
| Q106 | False | False | wrong_to_wrong | - | final_answer相同 |
| Q115 | False | True | wrong_to_right | - | final: no='3.5', with="Let the son's current age be \\( x \\ |
| Q119 | False | True | wrong_to_right | - | final: no='-4', with='From the vertex form \\( y = a(x-p)^2  |
| Q131 | False | True | wrong_to_right | linear_system_solver,linear_system_solver,linear_system_solver,linear_system_solver | 工具介入后final变化: 'The product of \\(x\\) and \\(y\\) is \\(-\\f |
| Q134 | True | False | right_to_wrong | - | final: no='The final answer is \\(-\\frac{1}{4}\\).', with=' |
| Q137 | True | True | right_to_right | expand,solve | final_answer相同 |
| Q139 | False | True | wrong_to_right | solve,solve,solve | 工具介入后final变化: '10' -> 'The sum of the squares of all real va |
| Q147 | False | False | wrong_to_wrong | polynomial_coefficient_match,polynomial_coefficient_match,factor | 工具介入后final变化: '(4, -20)' -> '(-6, 10)' |
| Q150 | False | True | wrong_to_right | inequality_solver,inequality_solver | 工具介入后final变化: 'The final answer is \\(\\frac{20}{7}\\).' ->  |
| Q151 | False | False | wrong_to_wrong | solve,solve,solve | 工具介入后final变化: '-4' -> '-1' |
| Q153 | False | True | wrong_to_right | solve,solve,solve | 工具介入后final变化: 'There is no common solution.' -> 'The final a |
| Q168 | False | False | wrong_to_wrong | - | final_answer相同 |
| Q171 | False | True | wrong_to_right | sequence_tool | 工具介入后final变化: 'The eighth term of the sequence is \\(\\frac{ |
| Q172 | False | False | wrong_to_wrong | solve | 工具介入后final变化: '7' -> 'The final answer is \\(\\sqrt{71}/2\\) |
| Q178 | True | True | right_to_right | polynomial_coefficient_match,polynomial_coefficient_match,polynomial_coefficient_match,polynomial_coefficient_match | final_answer相同 |
| Q180 | True | True | right_to_right | - | final_answer相同 |
| Q184 | False | False | wrong_to_wrong | - | final: no='The function \\( k(x) \\) is:\n\n\\[\nk(x) = 3\n\ |
| Q185 | False | False | wrong_to_wrong | linear_system_solver,linear_system_solver | final_answer相同 |
| Q190 | False | False | wrong_to_wrong | expand,polynomial_coefficient_match | 工具介入后final变化: 'The final answer is \\(\\boxed{9}\\).' -> 'Th |
