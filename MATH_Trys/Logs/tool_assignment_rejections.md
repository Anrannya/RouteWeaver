# 工具分配拒绝记录

总计: 35 条

## 按原因
- 工具执行失败: 24
- 子任务未明确要求求变量/根: 2
- subst 表达式与子任务目标不一致: 2
- replace 目标无法确认，保守拒绝: 1
- 求变量子任务禁止 arith replace: 1
- 求方程形式子任务禁止 arith replace: 1
- 绝对差子任务禁止 arith replace: 1
- 会破坏符号结构，禁止 arith replace: 1
- 过程型 factor/expand 禁止 replace: 1
- 概念/过程性子任务禁止数值工具 replace: 1

## 按原工具

- discrete_constraint_enumerator: 11
- solve: 6
- polynomial_coefficient_match: 5
- arith: 5
- subst: 4
- inequality_solver: 3
- factor: 1

## 明细

- Q11 Step1 | discrete_constraint_enumerator(replace) | 工具执行失败
  subtask: "What values of \(x\) satisfy the inequality \(|x| + 1 > 7\)?"
- Q11 Step2 | discrete_constraint_enumerator(replace) | 工具执行失败
  subtask: "What values of \(x\) satisfy the inequality \(|x + 1| \leq 7\)?"
- Q11 Step3 | discrete_constraint_enumerator(replace) | 工具执行失败
  subtask: "What values of \(x\) satisfy both conditions simultaneously?"
- Q17 Step1 | discrete_constraint_enumerator(replace) | 工具执行失败
  subtask: "What can we equate from the equation \(\frac{A\sqrt{B}}{C} = \frac{9}{2\sqrt{3}}\) to find \(A\), \(B\), and \(C\)?",
- Q17 Step3 | discrete_constraint_enumerator(replace) | 工具执行失败
  subtask: "Since \(B\) has no perfect-square factors other than 1, what are the possible values of \(B\) when simplified with \(\s
- Q17 Step5 | discrete_constraint_enumerator(replace) | 工具执行失败
  subtask: "What are the values of \(A\), \(B\), and \(C\) once the expression is simplified, and what is their sum \(A + B + C\)?"
- Q20 Step2 | discrete_constraint_enumerator(replace) | 工具执行失败
  subtask: "How do the roots relate to the coefficients \( m \) and \( n \) in the polynomial \( x^2 - mx + n \)?"
- Q20 Step4 | discrete_constraint_enumerator(replace) | 工具执行失败
  subtask: "What are the restrictions on the value of \( m \) given \( m < 20 \)?"
- Q27 Step5 | polynomial_coefficient_match(replace) | 工具执行失败
  subtask: "What possible integer values of \( c \) make this discriminant a perfect square, thereby ensuring the roots are rationa
- Q29 Step6 | solve(replace) | 工具执行失败
  subtask: What is the largest possible value of \( b \) from the solutions obtained?"
- Q38 Step5 | solve(replace) | 工具执行失败
  subtask: With the equation written in standard circle form, what is the maximum possible value of \( y \) given the radius and ce
- Q50 Step4 | inequality_solver(replace) | 工具执行失败
  subtask: "What is the maximum value of these calculated differences \( f(x) - g(x) \)?"
- Q57 Step5 | solve(replace) | 工具执行失败
  subtask: How many values of \( n \) result in no real solutions to the equation?
- Q66 Step6 | solve(replace) | 工具执行失败
  subtask: "What is the value of the smallest squared distance \(a^2\), after evaluating the function at the critical point?"
- Q68 Step18 | arith(replace) | replace 目标无法确认，保守拒绝
  subtask: - Therefore, the sum of the fractions is \(\frac{1}{16} \times 120\).
- Q87 Step3 | arith(replace) | 求变量子任务禁止 arith replace
  subtask: How do we solve the equation that results from substituting \(-4\) into the quadratic equation to find \(b\)?
- Q100 Step2 | arith(replace) | 求方程形式子任务禁止 arith replace
  subtask: What equation do we get when we set the simplified expression equal to \(3^6\)?
- Q106 Step1 | discrete_constraint_enumerator(replace) | 工具执行失败
  subtask: What are the integer values of \(x\) in the interval \(0 \le x \le 8\)?
- Q106 Step3 | discrete_constraint_enumerator(replace) | 工具执行失败
  subtask: For which integer values of \(x\) is \(h(x) > x\)?
- Q106 Step4 | discrete_constraint_enumerator(replace) | 工具执行失败
  subtask: What is the sum of these integer values of \(x\) for which \(h(x) > x\)?
- Q109 Step3 | polynomial_coefficient_match(replace) | 工具执行失败
  subtask: "Is there a way to factor or otherwise simplify the equation to find a relation between \(x\) and \(y\)?"
- Q109 Step4 | polynomial_coefficient_match(replace) | 工具执行失败
  subtask: "Can we identify any integer values for \(x\) and \(y\) that satisfy the equation?"
- Q109 Step5 | polynomial_coefficient_match(replace) | 工具执行失败
  subtask: "After finding potential values for \(x\) and \(y\), does substituting them back into the original equation verify their
- Q109 Step6 | polynomial_coefficient_match(replace) | 工具执行失败
  subtask: "Once the correct values for \(x\) and \(y\) are found, what is the sum \(x + y\)?"
- Q116 Step4 | arith(replace) | 绝对差子任务禁止 arith replace
  subtask: What is the absolute difference between \(\pi\) and \(\frac{22}{7}\)?
- Q117 Step1 | arith(replace) | 会破坏符号结构，禁止 arith replace
  subtask: What is the expanded form of the expression \((1001001)(1010101) + (989899)(1001001) - (1001)(989899) - (1010101)(1001)\
- Q124 Step5 | inequality_solver(replace) | 工具执行失败
  subtask: "What is the smallest integer \( a \) and the largest integer \( b \) within this interval?"
- Q127 Step4 | solve(replace) | 子任务未明确要求求变量/根
  subtask: What is the value of \(x\) when the exponents of the powers of 2 are equated?
- Q147 Step1 | factor(replace) | 过程型 factor/expand 禁止 replace
  subtask: How do we factor the denominator \(x^2 - 8x + 15\)?
- Q150 Step1 | solve(replace) | 子任务未明确要求求变量/根
  subtask: "At what times (if any) is the cannonball exactly at a height of $6$ meters?"
- Q163 Step4 | inequality_solver(replace) | 工具执行失败
  subtask: "What is the largest integer value of \( n \) that satisfies the inequality?"
- Q185 Step1 | subst(replace) | 概念/过程性子任务禁止数值工具 replace
  subtask: "What is the expression for \(a \star b\) given in the problem?"
- Q185 Step4 | subst(replace) | subst 表达式与子任务目标不一致
  subtask: "What is the value of \(\dfrac{1}{b} - \dfrac{1}{a}\) when \(a = 3\) and \(b = 11\)?"
- Q185 Step5 | subst(replace) | subst 表达式与子任务目标不一致
  subtask: "What is the value of \(a - b\) when \(a = 3\) and \(b = 11\)?"
- Q185 Step7 | subst(replace) | 工具执行失败
  subtask: "What is the final value of \(3 \star 11\) as a common fraction?"
