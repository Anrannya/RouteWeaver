# Phase 26 配对诊断

题目总数: 50
no_tool正确: 29
with_tool正确: 32
wrong_to_right: 7
right_to_wrong: 4
right_to_right: 25
wrong_to_wrong: 14
net_gain: 3
DAG_missing: 0

## 逐题配对

| qid | no_tool | with_tool | transition | tools | diff |
|-----|---------|-----------|------------|-------|------|
| Q0 | True | True | right_to_right | factor | 工具介入后final变化: 'The final answer is \\(2\\).' -> 'The final a |
| Q1 | True | True | right_to_right | arith,arith | final_answer相同 |
| Q8 | False | False | wrong_to_wrong | - | final_answer相同 |
| Q9 | False | False | wrong_to_wrong | - | final: no='The final answer is \\(-\\frac{3}{2}\\).', with=' |
| Q10 | True | True | right_to_right | - | final_answer相同 |
| Q22 | True | False | right_to_wrong | arith | 工具介入后final变化: 'The final answer is \\(x = 5\\).' -> 'The fin |
| Q25 | True | True | right_to_right | - | final_answer相同 |
| Q26 | False | False | wrong_to_wrong | expand | 工具介入后final变化: 'The final answer is \\(0\\).' -> '-5/4' |
| Q27 | True | True | right_to_right | - | final_answer相同 |
| Q30 | True | True | right_to_right | - | final: no='$2300', with='2300' |
| Q32 | False | True | wrong_to_right | - | final: no='The final answer is \\(90\\).', with='The sum of  |
| Q36 | True | True | right_to_right | simplify | final_answer相同 |
| Q40 | True | True | right_to_right | - | final_answer相同 |
| Q44 | False | False | wrong_to_wrong | arith,arith | 工具介入后final变化: 'The final answer is \\(\\frac{1}{2}\\).' -> ' |
| Q56 | True | True | right_to_right | - | final_answer相同 |
| Q62 | False | False | wrong_to_wrong | - | final: no='The final answer is $\\boxed{2}$.', with='2' |
| Q63 | False | False | wrong_to_wrong | - | final_answer相同 |
| Q64 | True | True | right_to_right | - | final: no='The final answer is \\(4\\).', with='The final an |
| Q65 | True | False | right_to_wrong | - | final: no='6', with='5' |
| Q67 | True | True | right_to_right | - | final_answer相同 |
| Q71 | False | False | wrong_to_wrong | - | final: no='15 5/9', with='10' |
| Q72 | True | False | right_to_wrong | subst | 工具介入后final变化: '24' -> '12' |
| Q81 | True | True | right_to_right | - | final: no='The final answer is \\(x = 50\\).', with='The fin |
| Q82 | False | False | wrong_to_wrong | - | final: no='63', with='125' |
| Q87 | True | True | right_to_right | arith | final_answer相同 |
| Q100 | True | True | right_to_right | simplify | 工具介入后final变化: 'The final answer is \\(k = 1\\).' -> '1' |
| Q102 | True | True | right_to_right | arith | final_answer相同 |
| Q116 | False | True | wrong_to_right | arith | 工具介入后final变化: '1/350' -> 'The final answer is \\(\\frac{1}{3 |
| Q118 | True | True | right_to_right | linear_system_solver,linear_system_solver,linear_system_solver | final_answer相同 |
| Q123 | True | False | right_to_wrong | - | final: no='The slope of line \\( j \\) is \\(\\frac{5}{6}\\) |
| Q124 | False | True | wrong_to_right | - | final: no='The final answer is 2.', with='The final answer i |
| Q130 | False | False | wrong_to_wrong | solve | final_answer相同 |
| Q134 | False | False | wrong_to_wrong | - | final_answer相同 |
| Q137 | True | True | right_to_right | expand | final_answer相同 |
| Q144 | False | True | wrong_to_right | expand | 工具介入后final变化: '-26' -> '64' |
| Q147 | False | True | wrong_to_right | factor,factor | 工具介入后final变化: '(-6, 10)' -> 'The final answer is \\(\\boxed{ |
| Q151 | False | False | wrong_to_wrong | solve | 工具介入后final变化: 'undefined' -> 'The final answer is \\(\\frac{ |
| Q153 | False | True | wrong_to_right | solve,solve | 工具介入后final变化: 'There is no common solution.' -> 'The final a |
| Q154 | True | True | right_to_right | - | final_answer相同 |
| Q165 | True | True | right_to_right | - | final: no='The sum is:\n\n1 × 3 = 3  \n2 × 5 = 10  \n3 × 7 = |
| Q169 | True | True | right_to_right | - | final_answer相同 |
| Q172 | False | False | wrong_to_wrong | solve | 工具介入后final变化: '√71 / 2' -> 'The final answer is \\(\\sqrt{71 |
| Q174 | True | True | right_to_right | solve,solve | final_answer相同 |
| Q176 | False | True | wrong_to_right | simplify | 工具介入后final变化: 'The final answer is \\(-\\frac{1}{3}\\).' ->  |
| Q179 | True | True | right_to_right | subst | final_answer相同 |
| Q183 | True | True | right_to_right | - | final_answer相同 |
| Q189 | False | False | wrong_to_wrong | - | final: no='The final answer is \\(c = \\frac{b}{2}\\).', wit |
| Q190 | False | False | wrong_to_wrong | expand | 工具介入后final变化: '-168/7' -> '-19' |
| Q197 | True | True | right_to_right | - | final_answer相同 |
| Q199 | True | True | right_to_right | - | final_answer相同 |
