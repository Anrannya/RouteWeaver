# Phase 26 配对诊断

题目总数: 35
no_tool正确: 6
with_tool正确: 16
wrong_to_right: 12
right_to_wrong: 2
right_to_right: 4
wrong_to_wrong: 17
net_gain: 10
DAG_missing: 0

## 逐题配对

| qid | no_tool | with_tool | transition | tools | diff |
|-----|---------|-----------|------------|-------|------|
| Q2 | True | True | right_to_right | - | final: no='Let’s piece together the final answer from the su |
| Q9 | False | False | wrong_to_wrong | solve | 工具介入后final变化: 'The smallest value of \\(x\\) is \\(-\\frac{3 |
| Q11 | False | False | wrong_to_wrong | inequality_solver | 工具介入后final变化: '15' -> 'The final answer is \\(-15\\).' |
| Q15 | True | False | right_to_wrong | inequality_solver | 工具介入后final变化: '5.5' -> '11/2' |
| Q20 | False | True | wrong_to_right | discrete_constraint_enumerator | 工具介入后final变化: 'The possible values of \\( n \\) are 6, 10, 1 |
| Q33 | False | False | wrong_to_wrong | - | final: no='-6.6', with='-12.6' |
| Q34 | False | False | wrong_to_wrong | sequence_tool | 工具介入后final变化: 'The eighth term of the sequence is \\(\\frac{ |
| Q38 | False | False | wrong_to_wrong | - | final: no='The maximum value of \\(y\\) is \\(1\\).', with=' |
| Q50 | False | False | wrong_to_wrong | - | final: no='8', with='The largest value of \\( f(x) - g(x) \\ |
| Q52 | False | True | wrong_to_right | sequence_tool | 工具介入后final变化: 'The least positive integer in the sequence is |
| Q54 | False | True | wrong_to_right | inequality_solver | 工具介入后final变化: 'The largest \\( t \\) which will bring the am |
| Q73 | False | False | wrong_to_wrong | - | final: no='The final answer is \\(k = 600 - 104\\sqrt{131}\\ |
| Q75 | False | True | wrong_to_right | linear_system_solver,linear_system_solver | 工具介入后final变化: '-5' -> '-55' |
| Q77 | False | False | wrong_to_wrong | solve | 工具介入后final变化: 'The final answer is \\(x = -2\\).' -> 'The fi |
| Q78 | False | True | wrong_to_right | arith | 工具介入后final变化: '0.44' -> 'The ball hits the ground when \\( y |
| Q85 | False | False | wrong_to_wrong | - | final_answer相同 |
| Q106 | False | False | wrong_to_wrong | - | final_answer相同 |
| Q115 | False | True | wrong_to_right | - | final: no='The son is 3.5 years old today.', with="Let the s |
| Q119 | False | True | wrong_to_right | - | final: no='-4', with='From the vertex form \\( y = a(x-p)^2  |
| Q131 | False | True | wrong_to_right | linear_system_solver,linear_system_solver,linear_system_solver,linear_system_solver | 工具介入后final变化: '-2.64' -> '-2' |
| Q134 | True | False | right_to_wrong | - | final: no='We have \\( a = b^2 + b \\) and we need a unique  |
| Q137 | True | True | right_to_right | expand,solve | final_answer相同 |
| Q139 | False | True | wrong_to_right | solve,solve,solve | 工具介入后final变化: '10' -> 'The sum of the squares of all real va |
| Q147 | False | False | wrong_to_wrong | polynomial_coefficient_match,polynomial_coefficient_match,factor | 工具介入后final变化: '(4, -20)' -> '(-6, 10)' |
| Q150 | False | True | wrong_to_right | inequality_solver,inequality_solver | 工具介入后final变化: 'The cannonball is above 6 meters between the  |
| Q151 | False | False | wrong_to_wrong | solve,solve,solve | 工具介入后final变化: '-4' -> '-1' |
| Q153 | False | True | wrong_to_right | solve,solve,solve | 工具介入后final变化: 'There is no value of \\( x \\) that satisfies |
| Q168 | False | False | wrong_to_wrong | - | final_answer相同 |
| Q171 | False | True | wrong_to_right | sequence_tool | 工具介入后final变化: 'The eighth term of the sequence is \\(\\frac{ |
| Q172 | False | False | wrong_to_wrong | solve | 工具介入后final变化: '7' -> 'The final answer is \\(\\sqrt{71}/2\\) |
| Q178 | True | True | right_to_right | polynomial_coefficient_match,polynomial_coefficient_match,polynomial_coefficient_match,polynomial_coefficient_match | final_answer相同 |
| Q180 | True | True | right_to_right | - | final_answer相同 |
| Q184 | False | False | wrong_to_wrong | - | final: no='Let’s piece together the conditions from the sub- |
| Q185 | False | False | wrong_to_wrong | linear_system_solver,linear_system_solver | final_answer相同 |
| Q190 | False | False | wrong_to_wrong | expand,polynomial_coefficient_match | 工具介入后final变化: 'The final answer is 9.' -> 'The final answer  |
