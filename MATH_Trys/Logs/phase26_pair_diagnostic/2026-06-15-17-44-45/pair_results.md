# Phase 26 配对诊断

题目总数: 50
no_tool正确: 26
with_tool正确: 33
wrong_to_right: 10
right_to_wrong: 3
right_to_right: 23
wrong_to_wrong: 14
net_gain: 7
DAG_missing: 0

## 逐题配对

| qid | no_tool | with_tool | transition | tools | diff |
|-----|---------|-----------|------------|-------|------|
| Q0 | True | True | right_to_right | factor | 工具介入后final变化: 'The final answer is \\(2\\).' -> '2' |
| Q1 | True | True | right_to_right | arith,arith | final_answer相同 |
| Q8 | False | False | wrong_to_wrong | - | final: no='-0.5, 8.5, 10.5, 20.5', with='-0.5, 10.5, 10.5, 1 |
| Q9 | False | False | wrong_to_wrong | - | final_answer相同 |
| Q10 | True | True | right_to_right | - | final_answer相同 |
| Q22 | False | False | wrong_to_wrong | arith | 工具介入后final变化: '-2' -> 'The final answer is \\(x = 2\\).' |
| Q25 | True | True | right_to_right | - | final_answer相同 |
| Q26 | True | False | right_to_wrong | expand | 工具介入后final变化: 'The sum of the possible values of \\(x\\) is  |
| Q27 | False | False | wrong_to_wrong | - | final_answer相同 |
| Q30 | False | True | wrong_to_right | - | final: no='$2450', with='$2300' |
| Q32 | False | True | wrong_to_right | - | final: no='The sum of these 15 sums is \\(\\boxed{90}\\).',  |
| Q36 | True | False | right_to_wrong | simplify | 工具介入后final变化: '(-\\sqrt{3}, \\sqrt{3})' -> '(-\\sqrt{21}, 0) |
| Q40 | False | False | wrong_to_wrong | - | final_answer相同 |
| Q44 | False | False | wrong_to_wrong | arith,arith | 工具介入后final变化: '7' -> '\\frac{7}{2}' |
| Q56 | True | True | right_to_right | - | final_answer相同 |
| Q62 | False | False | wrong_to_wrong | - | final_answer相同 |
| Q63 | False | False | wrong_to_wrong | - | final_answer相同 |
| Q64 | True | True | right_to_right | - | final_answer相同 |
| Q65 | True | True | right_to_right | - | final_answer相同 |
| Q67 | True | True | right_to_right | - | final_answer相同 |
| Q71 | True | True | right_to_right | - | final_answer相同 |
| Q72 | True | False | right_to_wrong | subst | 工具介入后final变化: '24' -> '48' |
| Q81 | True | True | right_to_right | - | final: no='The final answer is \\(\\boxed{50}\\).', with='50 |
| Q82 | True | True | right_to_right | - | final: no='Let’s correct the reasoning from the sub-problems |
| Q87 | True | True | right_to_right | arith | final_answer相同 |
| Q100 | True | True | right_to_right | simplify | final_answer相同 |
| Q102 | True | True | right_to_right | arith | final_answer相同 |
| Q116 | True | True | right_to_right | arith | final_answer相同 |
| Q118 | False | True | wrong_to_right | linear_system_solver,linear_system_solver,linear_system_solver | 工具介入后final变化: '-64' -> '-8' |
| Q123 | False | True | wrong_to_right | - | final: no='-2', with='The slope of line \\(j\\) is \\(\\frac |
| Q124 | False | True | wrong_to_right | - | final: no='The final answer is \\(7\\).', with='6' |
| Q130 | False | True | wrong_to_right | solve | final_answer相同 |
| Q134 | True | True | right_to_right | - | final_answer相同 |
| Q137 | False | True | wrong_to_right | expand | 工具介入后final变化: '14.5' -> '1' |
| Q144 | False | False | wrong_to_wrong | expand | 工具介入后final变化: '-26' -> '-56' |
| Q147 | True | True | right_to_right | factor,factor | 工具介入后final变化: 'The final answer is \\(\\boxed{(-6, 10)}\\).' |
| Q151 | False | False | wrong_to_wrong | solve | 工具介入后final变化: '-4' -> '-2' |
| Q153 | False | False | wrong_to_wrong | solve,solve | 工具介入后final变化: 'There is no value of \\( x \\) that satisfies |
| Q154 | True | True | right_to_right | - | final_answer相同 |
| Q165 | True | True | right_to_right | - | final: no='The final answer is \\(\\boxed{50}\\).', with='Th |
| Q169 | True | True | right_to_right | - | final_answer相同 |
| Q172 | False | False | wrong_to_wrong | solve | 工具介入后final变化: '7' -> 'The positive difference between the tw |
| Q174 | True | True | right_to_right | solve,solve | final_answer相同 |
| Q176 | False | False | wrong_to_wrong | simplify | 工具介入后final变化: 'The final answer is \\(\\frac{4}{1}\\).' -> ' |
| Q179 | False | True | wrong_to_right | subst | 工具介入后final变化: '1/√2' -> '1' |
| Q183 | False | True | wrong_to_right | - | final: no='The final answer is \\(6\\).', with='0' |
| Q189 | False | False | wrong_to_wrong | - | final_answer相同 |
| Q190 | False | True | wrong_to_right | expand | 工具介入后final变化: '-35' -> '-9' |
| Q197 | True | True | right_to_right | - | final: no='The final answer is \\(7\\).', with='7' |
| Q199 | True | True | right_to_right | - | final_answer相同 |
