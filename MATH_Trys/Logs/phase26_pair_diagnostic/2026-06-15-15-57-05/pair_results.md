# Phase 26 配对诊断

题目总数: 10
no_tool正确: 4
with_tool正确: 8
wrong_to_right: 4
right_to_wrong: 0
right_to_right: 4
wrong_to_wrong: 2
net_gain: 4
DAG_missing: 0

## 逐题配对

| qid | no_tool | with_tool | transition | tools | diff |
|-----|---------|-----------|------------|-------|------|
| Q59 | True | True | right_to_right | complex_arithmetic,complex_arithmetic | final_answer相同 |
| Q70 | False | True | wrong_to_right | subst,subst | 工具介入后final变化: '62' -> '8' |
| Q74 | False | True | wrong_to_right | solve | 工具介入后final变化: '0' -> 'The sum of all possible values of \\(x |
| Q126 | True | True | right_to_right | subst,subst,subst | final_answer相同 |
| Q131 | False | True | wrong_to_right | linear_system_solver,linear_system_solver,linear_system_solver,linear_system_solver | 工具介入后final变化: 'The product of \\(x\\) and \\(y\\) is \\(-\\f |
| Q132 | True | True | right_to_right | linear_system_solver,linear_system_solver,linear_system_solver,linear_system_solver,linear_system_solver | final_answer相同 |
| Q162 | False | False | wrong_to_wrong | - | final: no='The final answer is \\( \\boxed{400} \\).', with= |
| Q170 | False | False | wrong_to_wrong | - | final: no='136', with='16' |
| Q173 | True | True | right_to_right | subst | final_answer相同 |
| Q191 | False | True | wrong_to_right | simplify,arith | 工具介入后final变化: '361+168x' -> '361' |
