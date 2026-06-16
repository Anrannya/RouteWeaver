# Phase 26 配对诊断

题目总数: 84
no_tool正确: 48
with_tool正确: 57
wrong_to_right: 16
right_to_wrong: 7
right_to_right: 41
wrong_to_wrong: 20
net_gain: 9
DAG_missing: 0

## 逐题配对

| qid | no_tool | with_tool | transition | tools | diff |
|-----|---------|-----------|------------|-------|------|
| Q0 | True | True | right_to_right | factor | 工具介入后final变化: 'The final answer is \\(2\\).' -> '2' |
| Q1 | True | True | right_to_right | arith,arith | final_answer相同 |
| Q22 | True | True | right_to_right | arith | 工具介入后final变化: '5' -> 'The final answer is \\(\\boxed{5}\\).' |
| Q36 | True | True | right_to_right | simplify | final_answer相同 |
| Q44 | False | False | wrong_to_wrong | arith,arith | 工具介入后final变化: 'The final answer is \\(\\boxed{\\frac{1}{2}}\ |
| Q63 | False | False | wrong_to_wrong | - | final: no='169/4', with='The product of the squares of the s |
| Q87 | True | True | right_to_right | arith | final_answer相同 |
| Q100 | True | True | right_to_right | simplify | 工具介入后final变化: 'The final answer is \\(k = 1\\).' -> '1' |
| Q102 | True | True | right_to_right | arith | final_answer相同 |
| Q116 | True | True | right_to_right | arith | final_answer相同 |
| Q118 | True | True | right_to_right | linear_system_solver,linear_system_solver,linear_system_solver | final_answer相同 |
| Q130 | False | False | wrong_to_wrong | solve | final_answer相同 |
| Q137 | True | False | right_to_wrong | expand | 工具介入后final变化: '1' -> '35/2' |
| Q144 | False | True | wrong_to_right | expand | 工具介入后final变化: '-26' -> '64' |
| Q147 | True | False | right_to_wrong | factor,factor | 工具介入后final变化: '(-6, 10)' -> 'The final answer is \\((2, -2)\ |
| Q151 | False | False | wrong_to_wrong | solve | 工具介入后final变化: 'undefined' -> 'The final answer is \\(\\frac{ |
| Q153 | False | True | wrong_to_right | solve,solve | 工具介入后final变化: 'There is no common solution.' -> 'The final a |
| Q172 | False | False | wrong_to_wrong | solve | 工具介入后final变化: '√71 / 2' -> 'The final answer is \\(\\sqrt{71 |
| Q174 | True | True | right_to_right | solve,solve | final_answer相同 |
| Q176 | False | True | wrong_to_right | simplify | 工具介入后final变化: 'The final answer is \\(-\\frac{1}{3}\\).' ->  |
| Q190 | False | False | wrong_to_wrong | expand | 工具介入后final变化: '-19' -> '-98/5' |
| Q0 | True | True | right_to_right | factor | final_answer相同 |
| Q1 | True | True | right_to_right | arith,arith | final_answer相同 |
| Q22 | True | False | right_to_wrong | arith | 工具介入后final变化: '5' -> '1' |
| Q36 | True | True | right_to_right | simplify | final_answer相同 |
| Q44 | False | False | wrong_to_wrong | arith,arith | 工具介入后final变化: 'The final answer is \\(\\frac{1}{2}\\).' -> ' |
| Q63 | False | False | wrong_to_wrong | - | final_answer相同 |
| Q87 | True | True | right_to_right | arith | 工具介入后final变化: '-5' -> 'b = -5' |
| Q100 | True | True | right_to_right | simplify | final_answer相同 |
| Q102 | True | True | right_to_right | arith | final_answer相同 |
| Q116 | True | True | right_to_right | arith | final_answer相同 |
| Q118 | True | True | right_to_right | linear_system_solver,linear_system_solver,linear_system_solver | final_answer相同 |
| Q130 | True | True | right_to_right | solve | final_answer相同 |
| Q137 | True | True | right_to_right | expand | 工具介入后final变化: 'The final answer is 1.' -> '1' |
| Q144 | False | False | wrong_to_wrong | expand | 工具介入后final变化: '-26' -> '16' |
| Q147 | False | False | wrong_to_wrong | factor,factor | 工具介入后final变化: '(-6, 10)' -> 'The final answer is \\(\\boxed{ |
| Q151 | False | True | wrong_to_right | solve | 工具介入后final变化: '3' -> 'We have:\n\n\\[\n\\frac{1}{a-1} + \\fr |
| Q153 | False | True | wrong_to_right | solve,solve | 工具介入后final变化: 'There is no common solution.' -> 'The final a |
| Q172 | False | False | wrong_to_wrong | solve | 工具介入后final变化: '√71 / 2' -> 'The final answer is \\(\\sqrt{71 |
| Q174 | True | True | right_to_right | solve,solve | final_answer相同 |
| Q176 | False | True | wrong_to_right | simplify | 工具介入后final变化: 'The final answer is \\(\\frac{4}{1}\\).' -> ' |
| Q190 | False | True | wrong_to_right | expand | 工具介入后final变化: '87 + 36√3' -> 'Let’s go through the problem c |
| Q0 | False | True | wrong_to_right | factor | 工具介入后final变化: 'The final answer is 0.' -> 'The graph has 2 v |
| Q1 | True | True | right_to_right | arith,arith | final_answer相同 |
| Q22 | True | False | right_to_wrong | arith | 工具介入后final变化: '5' -> '1' |
| Q36 | True | True | right_to_right | simplify | final_answer相同 |
| Q44 | False | False | wrong_to_wrong | arith,arith | 工具介入后final变化: 'The final answer is \\(\\frac{7}{98}\\).' ->  |
| Q63 | False | False | wrong_to_wrong | - | final_answer相同 |
| Q87 | True | True | right_to_right | arith | 工具介入后final变化: '-5' -> 'b = -5' |
| Q100 | True | True | right_to_right | simplify | final_answer相同 |
| Q102 | True | True | right_to_right | arith | final_answer相同 |
| Q116 | True | True | right_to_right | arith | 工具介入后final变化: 'The final answer is \\(\\frac{1}{350}\\).' -> |
| Q118 | True | True | right_to_right | linear_system_solver,linear_system_solver,linear_system_solver | final_answer相同 |
| Q130 | True | True | right_to_right | solve | final_answer相同 |
| Q137 | True | False | right_to_wrong | expand | 工具介入后final变化: '1' -> 'The final answer is \\( \\frac{35}{2}  |
| Q144 | False | True | wrong_to_right | expand | 工具介入后final变化: '-26' -> 'We are given:  \n\\((2x + 3y)^2 = 4\ |
| Q147 | True | False | right_to_wrong | factor,factor | 工具介入后final变化: '(-6, 10)' -> 'The final answer is \\((2, -2)\ |
| Q151 | False | False | wrong_to_wrong | solve | 工具介入后final变化: 'The expression is undefined.' -> 'The final a |
| Q153 | False | True | wrong_to_right | solve,solve | 工具介入后final变化: 'There is no value of \\( x \\) that satisfies |
| Q172 | False | False | wrong_to_wrong | solve | 工具介入后final变化: '√71 / 2' -> 'The final answer is \\(\\sqrt{71 |
| Q174 | True | True | right_to_right | solve,solve | final_answer相同 |
| Q176 | False | True | wrong_to_right | simplify | 工具介入后final变化: 'The final answer is \\(\\boxed{-\\frac{1}{3}} |
| Q190 | False | True | wrong_to_right | expand | 工具介入后final变化: '-12' -> 'Let’s go through the problem careful |
| Q0 | True | True | right_to_right | factor | 工具介入后final变化: 'The final answer is **2**.' -> '2' |
| Q1 | True | True | right_to_right | arith,arith | final_answer相同 |
| Q22 | True | False | right_to_wrong | arith | 工具介入后final变化: '5' -> '1' |
| Q36 | True | True | right_to_right | simplify | final_answer相同 |
| Q44 | False | False | wrong_to_wrong | arith,arith | 工具介入后final变化: 'The final answer is \\(\\frac{1}{2}\\).' -> ' |
| Q63 | False | False | wrong_to_wrong | - | final_answer相同 |
| Q87 | True | True | right_to_right | arith | final_answer相同 |
| Q100 | True | True | right_to_right | simplify | final_answer相同 |
| Q102 | True | True | right_to_right | arith | final_answer相同 |
| Q116 | True | True | right_to_right | arith | final_answer相同 |
| Q118 | True | True | right_to_right | linear_system_solver,linear_system_solver,linear_system_solver | final_answer相同 |
| Q130 | True | True | right_to_right | solve | final_answer相同 |
| Q137 | True | True | right_to_right | expand | 工具介入后final变化: 'The final answer is 1.' -> '1' |
| Q144 | False | False | wrong_to_wrong | expand | 工具介入后final变化: '-26' -> '16' |
| Q147 | False | False | wrong_to_wrong | factor,factor | 工具介入后final变化: '(-6, 10)' -> 'The final answer is \\(\\boxed{ |
| Q151 | False | True | wrong_to_right | solve | 工具介入后final变化: '3' -> 'We have:\n\n\\[\na+b = \\frac{7}{2}, \ |
| Q153 | False | True | wrong_to_right | solve,solve | 工具介入后final变化: 'Since there is no common solution, there is n |
| Q172 | False | False | wrong_to_wrong | solve | 工具介入后final变化: '√71 / 2' -> 'The final answer is \\(\\sqrt{71 |
| Q174 | True | True | right_to_right | solve,solve | final_answer相同 |
| Q176 | False | True | wrong_to_right | simplify | 工具介入后final变化: 'The final answer is \\(\\frac{4}{1}\\).' -> ' |
| Q190 | False | True | wrong_to_right | expand | 工具介入后final变化: '87 + 36√3' -> 'Let’s go through the problem c |
