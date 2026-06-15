# 工具分配拒绝记录

总计: 19 条

## 按原因
- 前驱无 verified 结构化数值，aggregate 暂不分配: 13
- 复杂多项式不宜 arith replace: 2
- 求方程形式子任务禁止 arith replace: 1
- 绝对差子任务禁止 arith replace: 1
- expanded form 子任务禁止 arith replace: 1
- 表达式含未绑定变量: ['a', 'b', 'c']: 1

## 按原工具

- aggregate: 13
- arith: 5
- expand: 1

## 明细

- Q1 Step3 | aggregate(assist) | 前驱无 verified 结构化数值，aggregate 暂不分配
  subtask: What is the positive difference between the result from step 1 and the result from step 2?
- Q3 Step5 | aggregate(assist) | 前驱无 verified 结构化数值，aggregate 暂不分配
  subtask: What is the sum of the simplified results from steps 2, 3, and 4?
- Q13 Step4 | aggregate(assist) | 前驱无 verified 结构化数值，aggregate 暂不分配
  subtask: What is the sum of the x and y coordinates of the midpoint?"
- Q14 Step9 | aggregate(assist) | 前驱无 verified 结构化数值，aggregate 暂不分配
  subtask: "What is the product of the lengths of diagonals \(AC\) and \(BD\)?"
- Q44 Step1 | arith(replace) | 复杂多项式不宜 arith replace
  subtask: What is the improper fraction form of \( 1\frac{1}{6} \)?
- Q100 Step2 | arith(replace) | 求方程形式子任务禁止 arith replace
  subtask: What equation do we get when we set the simplified expression equal to \(3^6\)?
- Q112 Step5 | aggregate(assist) | 前驱无 verified 结构化数值，aggregate 暂不分配
  subtask: What is the sum of the results from step 2 and step 4, \((b-c)^2 + a(b+c)\)?
- Q114 Step3 | aggregate(assist) | 前驱无 verified 结构化数值，aggregate 暂不分配
  subtask: What is the sum of the values found in steps 1 and 2?"
- Q115 Step4 | aggregate(assist) | 前驱无 verified 结构化数值，aggregate 暂不分配
  subtask: "What equation can be formed using the sum of their ages exactly three years ago?"
- Q116 Step4 | arith(replace) | 绝对差子任务禁止 arith replace
  subtask: What is the absolute difference between \(\pi\) and \(\frac{22}{7}\)?
- Q116 Step5 | aggregate(assist) | 前驱无 verified 结构化数值，aggregate 暂不分配
  subtask: Add the two absolute differences calculated in the previous steps.
- Q117 Step1 | arith(replace) | expanded form 子任务禁止 arith replace
  subtask: What is the expanded form of the expression \((1001001)(1010101) + (989899)(1001001) - (1001)(989899) - (1010101)(1001)\
- Q118 Step3 | aggregate(assist) | 前驱无 verified 结构化数值，aggregate 暂不分配
  subtask: "What is the product of \( x \) and \( y \) once you know both values?"
- Q131 Step4 | aggregate(assist) | 前驱无 verified 结构化数值，aggregate 暂不分配
  subtask: What is the product of the values of \(x\) and \(y\) once they are found?
- Q140 Step6 | aggregate(assist) | 前驱无 verified 结构化数值，aggregate 暂不分配
  subtask: "What is the sum of the sixth and seventh terms?"
- Q149 Step3 | aggregate(assist) | 前驱无 verified 结构化数值，aggregate 暂不分配
  subtask: What is the difference between the results from step 1 and step 2?".
- Q165 Step20 | aggregate(assist) | 前驱无 verified 结构化数值，aggregate 暂不分配
  subtask: What is the sum of all these values from steps 1 to 19?
- Q178 Step3 | expand(replace) | 表达式含未绑定变量: ['a', 'b', 'c']
  subtask: "What is the expanded form of \( a(x+b)^2+c \) using the values of \( a \), \( b \), and \( c \)?"
- Q191 Step3 | arith(replace) | 复杂多项式不宜 arith replace
  subtask: What is the simplified form of the entire expression \(49x^2 + 14x(19 - 7x) + (19 - 7x)^2\) after combining like terms?
