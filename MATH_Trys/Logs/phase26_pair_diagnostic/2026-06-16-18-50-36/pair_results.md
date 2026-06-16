# Phase 26 配对诊断

题目总数: 35
no_tool正确: 10
with_tool正确: 17
wrong_to_right: 11
right_to_wrong: 4
right_to_right: 6
wrong_to_wrong: 14
net_gain: 7
DAG_missing: 0

## 逐题配对

| qid | no_tool | with_tool | transition | tools | diff |
|-----|---------|-----------|------------|-------|------|
| Q2 | True | True | right_to_right | - | final: no='x = \\frac{9}{7}', with='\\frac{9}{7}' |
| Q9 | False | False | wrong_to_wrong | solve | final_answer相同 |
| Q11 | False | True | wrong_to_right | inequality_solver | 工具介入后final变化: '-4' -> 'The final answer is \\(-15\\).' |
| Q15 | True | True | right_to_right | inequality_solver | 工具介入后final变化: '5.5' -> '11/2' |
| Q20 | False | True | wrong_to_right | discrete_constraint_enumerator | 工具介入后final变化: 'The possible values of \\( n \\) are 6, 10, 1 |
| Q33 | False | False | wrong_to_wrong | - | final: no='-12.6', with='-6.6' |
| Q34 | False | True | wrong_to_right | sequence_tool | 工具介入后final变化: 'The eighth term of the sequence is \\(\\frac{ |
| Q38 | False | False | wrong_to_wrong | - | final: no='The maximum value of \\( y \\) is \\( -23 \\).',  |
| Q50 | False | False | wrong_to_wrong | - | final_answer相同 |
| Q52 | False | True | wrong_to_right | sequence_tool | 工具介入后final变化: '986' -> '12' |
| Q54 | False | True | wrong_to_right | inequality_solver | 工具介入后final变化: 'The largest \\( t \\) which will bring the am |
| Q73 | False | False | wrong_to_wrong | - | final: no='The final answer is \\( k = \\frac{3323}{1} \\).' |
| Q75 | False | True | wrong_to_right | linear_system_solver,linear_system_solver | 工具介入后final变化: '245' -> '-55' |
| Q77 | False | False | wrong_to_wrong | solve | 工具介入后final变化: 'The final answer is \\(\\frac{7}{4}\\).' -> ' |
| Q78 | False | False | wrong_to_wrong | arith | 工具介入后final变化: '0.83' -> '0.32' |
| Q85 | False | False | wrong_to_wrong | - | final: no='The first term that is greater than 125 is 108.', |
| Q106 | False | False | wrong_to_wrong | - | final_answer相同 |
| Q115 | True | False | right_to_wrong | - | final: no="Let the son's current age be \\( x \\).  \nThe fa |
| Q119 | True | False | right_to_wrong | - | final: no='From the vertex form \\( y = a(x-p)^2 + p \\), ex |
| Q131 | True | True | right_to_right | linear_system_solver,linear_system_solver,linear_system_solver,linear_system_solver | final_answer相同 |
| Q134 | False | True | wrong_to_right | - | final: no='1', with='We have \\( a = b^2 + b \\).  \nFor \\( |
| Q137 | False | True | wrong_to_right | expand,solve | 工具介入后final变化: '14.5' -> 'Let’s go through the steps carefull |
| Q139 | True | True | right_to_right | solve,solve,solve | 工具介入后final变化: 'The final answer is $\\boxed{20}$.' -> 'The f |
| Q147 | True | False | right_to_wrong | polynomial_coefficient_match,polynomial_coefficient_match,factor | 工具介入后final变化: 'The final answer is \\(\\boxed{(-6, 10)}\\).' |
| Q150 | False | True | wrong_to_right | inequality_solver,inequality_solver | 工具介入后final变化: 'The final answer is \\(\\boxed{\\frac{27}{25} |
| Q151 | False | False | wrong_to_wrong | solve,solve,solve | 工具介入后final变化: '-4' -> '112' |
| Q153 | False | False | wrong_to_wrong | solve,solve,solve | 工具介入后final变化: 'There is no value of \\( x \\) that satisfies |
| Q168 | False | False | wrong_to_wrong | - | final_answer相同 |
| Q171 | False | True | wrong_to_right | sequence_tool | 工具介入后final变化: 'The eighth term of the sequence is \\(\\frac{ |
| Q172 | False | False | wrong_to_wrong | solve | 工具介入后final变化: '7' -> 'The final answer is \\(\\sqrt{71}/2\\) |
| Q178 | False | True | wrong_to_right | polynomial_coefficient_match,polynomial_coefficient_match,polynomial_coefficient_match,polynomial_coefficient_match | 工具介入后final变化: 'The final answer is \\(\\frac{5}{4}\\).' -> ' |
| Q180 | True | True | right_to_right | - | final_answer相同 |
| Q184 | True | True | right_to_right | - | final: no='Let’s piece together the conditions from the sub- |
| Q185 | False | False | wrong_to_wrong | linear_system_solver,linear_system_solver | final_answer相同 |
| Q190 | True | False | right_to_wrong | expand,polynomial_coefficient_match | 工具介入后final变化: '-9' -> '-11' |
