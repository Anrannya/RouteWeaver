# Phase 2.8 关键题审计

来源日志：`Logs/phase26_pair_diagnostic/2026-06-15-17-44-45/`  
实验 SHA：`e23d2714f67e54b0e2a1aef50956be1d57eb0d68`

| QID | 归类 | 确定性工具错误 | 规则修改 | confirmed_tool_gain |
|-----|------|----------------|----------|---------------------|
| Q26 | B | 否 | 过程性 expand → assist | false |
| Q36 | D | 否 | 无 | false |
| Q44 | C | 否 | 无 | false |
| Q72 | A | **是** | 概念型禁止数值 replace | false |
| Q118 | F（收益已确认） | 否 | 无 | **true** |
| Q130 | E | 否 | Judge 复用 | false |
| Q179 | A | **是** | 过程 evaluate 禁止 subst replace | false |
| Q190 | B | 否 | 无 | **true** |

## Q26

- Step1：`How can we expand (2x+5)(x-3)?` → expand replace 输出 `2x²-x-15`（数学正确）
- 后续 LLM 因式分解/求根错误 → final `-2` vs gold `0.5`
- **结论**：replace 模式不当（过程说明），非 expand 工具本身错误；改为 assist，不禁全局 expand replace

## Q36

- simplify assist → `x²(x²+4)`，数学正确
- 区间求解仍由 LLM 完成且出错
- **结论**：模型波动，不禁止 simplify assist

## Q44

- arith replace：`7/6`、`14` 均正确
- Step4 LLM 交叉相乘得 `7/2`，非工具目标错误
- **结论**：后续推理丢失，无需改目标提取

## Q72

- Step1 概念问句 + subst replace `k→14` → 答案 `14` 污染链式推理 → final `48`
- **结论**：确定性误分配；已加概念型子任务通用规则

## Q118

- linear replace：`x=8`, `y=-1`, `xy=-8`
- no_tool final `-64`，with_tool `-8`（正确）
- **结论**：confirmed_tool_gain = true

## Q130

- 两分支 final 均为 `-22`
- no_tool judge false，with_tool judge true
- **结论**：Judge 波动；compare 脚本加入规范化后 Judge 复用

## Q179

- Step2 `How do we evaluate h(x) at x=-1` + subst replace bare `x=-1` → `-1`
- 非 `h(-1)=1`；后续步骤 LLM 自行代入纠正
- **结论**：确定性误分配；过程型 + 目标不一致

## Q190

- expand assist 系数展开正确
- with_tool `-9` 正确，no_tool `-35` 错误
- **结论**：confirmed_tool_gain = true（assist）
