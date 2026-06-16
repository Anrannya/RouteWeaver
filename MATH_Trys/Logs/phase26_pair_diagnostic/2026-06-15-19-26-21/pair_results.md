# Phase 26 配对诊断

题目总数: 32
no_tool正确: 21
with_tool正确: 21
wrong_to_right: 2
right_to_wrong: 2
right_to_right: 19
wrong_to_wrong: 9
net_gain: 0
DAG_missing: 0

## 逐题配对

| qid | no_tool | with_tool | transition | tools | diff |
|-----|---------|-----------|------------|-------|------|
| Q26 | True | False | right_to_wrong | expand | 工具介入后final变化: 'The sum of the possible values of \\(x\\) is  |
| Q36 | True | True | right_to_right | simplify | final_answer相同 |
| Q44 | False | False | wrong_to_wrong | arith,arith | 工具介入后final变化: 'The final answer is \\(\\frac{1}{2}\\).' -> ' |
| Q72 | True | True | right_to_right | - | final_answer相同 |
| Q118 | True | True | right_to_right | linear_system_solver,linear_system_solver,linear_system_solver | final_answer相同 |
| Q130 | True | True | right_to_right | solve | final_answer相同 |
| Q179 | True | True | right_to_right | - | final_answer相同 |
| Q190 | False | True | wrong_to_right | expand | 工具介入后final变化: '-19' -> 'Let’s go through the problem careful |
| Q26 | False | False | wrong_to_wrong | expand | 工具介入后final变化: 'The final answer is \\(\\frac{3}{2}\\).' -> ' |
| Q36 | True | True | right_to_right | simplify | final_answer相同 |
| Q44 | False | False | wrong_to_wrong | arith,arith | 工具介入后final变化: 'The final answer is \\(\\boxed{\\frac{1}{2}}\ |
| Q72 | True | True | right_to_right | - | final_answer相同 |
| Q118 | True | True | right_to_right | linear_system_solver,linear_system_solver,linear_system_solver | final_answer相同 |
| Q130 | True | True | right_to_right | solve | final_answer相同 |
| Q179 | True | True | right_to_right | - | final_answer相同 |
| Q190 | False | True | wrong_to_right | expand | 工具介入后final变化: '87 + 36√3' -> 'Let’s go through the problem c |
| Q26 | True | False | right_to_wrong | expand | 工具介入后final变化: 'The sum of the possible values of \\(x\\) is  |
| Q36 | True | True | right_to_right | simplify | final_answer相同 |
| Q44 | False | False | wrong_to_wrong | arith,arith | 工具介入后final变化: 'The final answer is \\(\\frac{7}{98}\\).' ->  |
| Q72 | True | True | right_to_right | - | final_answer相同 |
| Q118 | True | True | right_to_right | linear_system_solver,linear_system_solver,linear_system_solver | final_answer相同 |
| Q130 | True | True | right_to_right | solve | final_answer相同 |
| Q179 | True | True | right_to_right | - | final_answer相同 |
| Q190 | False | False | wrong_to_wrong | expand | 工具介入后final变化: '-12' -> '-98/5' |
| Q26 | False | False | wrong_to_wrong | expand | 工具介入后final变化: 'The final answer is \\(\\frac{3}{2}\\).' -> ' |
| Q36 | True | True | right_to_right | simplify | final_answer相同 |
| Q44 | False | False | wrong_to_wrong | arith,arith | 工具介入后final变化: 'The final answer is \\(\\frac{7}{98}\\).' ->  |
| Q72 | False | False | wrong_to_wrong | - | final_answer相同 |
| Q118 | True | True | right_to_right | linear_system_solver,linear_system_solver,linear_system_solver | final_answer相同 |
| Q130 | True | True | right_to_right | solve | final_answer相同 |
| Q179 | True | True | right_to_right | - | final_answer相同 |
| Q190 | False | False | wrong_to_wrong | expand | 工具介入后final变化: '87 + 36√3' -> 'The final answer is \\(-\\frac |
