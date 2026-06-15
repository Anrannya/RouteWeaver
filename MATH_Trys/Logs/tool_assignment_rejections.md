# 工具分配拒绝记录

总计: 5 条

## 按原因
- replace 目标无法确认，保守拒绝: 1
- 求方程形式子任务禁止 arith replace: 1
- 绝对差子任务禁止 arith replace: 1
- 会破坏符号结构，禁止 arith replace: 1
- 表达式含未绑定变量: ['a', 'b', 'c']: 1

## 按原工具

- arith: 4
- expand: 1

## 明细

- Q68 Step18 | arith(replace) | replace 目标无法确认，保守拒绝
  subtask: - Therefore, the sum of the fractions is \(\frac{1}{16} \times 120\).
- Q100 Step2 | arith(replace) | 求方程形式子任务禁止 arith replace
  subtask: What equation do we get when we set the simplified expression equal to \(3^6\)?
- Q116 Step4 | arith(replace) | 绝对差子任务禁止 arith replace
  subtask: What is the absolute difference between \(\pi\) and \(\frac{22}{7}\)?
- Q117 Step1 | arith(replace) | 会破坏符号结构，禁止 arith replace
  subtask: What is the expanded form of the expression \((1001001)(1010101) + (989899)(1001001) - (1001)(989899) - (1010101)(1001)\
- Q178 Step3 | expand(replace) | 表达式含未绑定变量: ['a', 'b', 'c']
  subtask: "What is the expanded form of \( a(x+b)^2+c \) using the values of \( a \), \( b \), and \( c \)?"
