# 路线 C：真正的序贯 MDP 注入策略（多步 GRPO）

> A/B 的代码与逻辑完全不动。路线 C 是全新文件，通过**子类化** `InjectionEnv` 复用检索器/验证器/提示构造，不修改父类。

## 为什么 C 才是「真 MDP」
- **路线 A/B**：事前一次性给定整套注入方案 → （多臂）老虎机，单步。
- **路线 C**：沿 DoT 推理链**逐节点**决策——每个决策节点先看状态再决定注/不注，
  被注入节点的答案写入 `answerDict` 并喂给后续节点，**前一步真实改变后一步的状态**，
  末端用最终答案对错作回报。这是教科书意义的多步序贯决策（MDP）。

## 组件（均在 `GRPO/`）
| 文件 | 作用 |
|---|---|
| `seq_mdp_env.py` | `SequentialInjectionEnv(InjectionEnv)`：逐节点 rollout + 决策时状态特征 |
| `build_seqmdp_cache.py` | 对每题**枚举决策树**，LLM 按 prompt 缓存去重，得精确多步 MDP 轨迹表 |
| `train_seqmdp_policy.py` | 在枚举树上做**精确多步 GRPO 策略梯度**（组内相对优势）+ 贪婪序贯评估 + k 折 |

## 决策节点
按真实求解顺序展开所有子问题，取**末尾 `dmax-1` 个子问题 + 最终总结**作决策节点
（最影响结果的枢纽），更早子问题强制不注入，以把枚举树规模控制在 `2^dmax`。
`dmax=3` 即每题 3 个连续决策点（仍是多步、状态向后传递的真 MDP）。

## GRPO 数学（精确、无采样噪声）
- 策略 `π(inject|s)=sigmoid(θ·s)`，θ 跨节点共享。
- 轨迹概率 `P(τ)=Π_t [a_t p_t+(1-a_t)(1-p_t)]`，回报 `R(τ)=正确-λ·注入次数`。
- 组基线 `b_q=Σ_τ P(τ)R(τ)`（同题所有轨迹为一个 group → 组内相对优势）。
- 精确梯度 `∇J=Σ_q Σ_τ P(τ)(R-b_q) Σ_t (a_t-p_t)s_t`（跨所有决策步的多步信用分配）。

## 运行
```bash
# 1) 冒烟（无 LLM，确定性 mock，几秒）
python GRPO/build_seqmdp_cache.py --backend mock --n 12 --dmax 3 --out GRPO/cache/seqmdp_table_mock.jsonl
python GRPO/train_seqmdp_policy.py --table GRPO/cache/seqmdp_table_mock.jsonl --kfold 3 --epochs 1500

# 2) 真实后端（子问题→本地 llama、最终→deepseek），tmux 里跑
python GRPO/build_seqmdp_cache.py --backend real --n 200 --dmax 3      # 离线枚举，~1.6k deepseek 调用
python GRPO/train_seqmdp_policy.py --kfold 5 --lam 0.0                 # 秒级，纯本地训练
```
温度固定 0 → 环境确定 → 缓存即可复现的离线奖励表；训练阶段不再调任何 LLM。

---

# 路线 C-full：**完全符合 GRPO 定义**的版本（`train_seqmdp_grpo_full.py`）

C-精确版用「枚举整棵决策树 + 精确期望梯度」，省去了采样/IS/clip——干净但不是教科书完整 GRPO。
C-full 改用**采样式训练**，把 DeepSeekMath GRPO 的**每一个定义性特征**都补齐，复用同一张
`seqmdp_table.jsonl` 缓存（采样=按 π_old 在树上走一条路、查表拿回报，**不额外调 LLM**）。

| GRPO 定义性特征 | C-full 是否实现 | 代码位置 |
|---|---|---|
| ① 采样一组 G 条输出（非枚举） | ✅ | `sample_trajectory` |
| ② 组内相对优势 + **std 归一化** `(R-mean)/(std+eps)` | ✅ | `train_full_grpo` 内 `A=` |
| ③ **重要性采样比率** π_θ/π_θ_old | ✅ | `traj_logp` + `ratio=` |
| ④ **PPO-clip** `min(ratio·A, clip(ratio,1±ε)·A)` | ✅ | `binding` 判定 |
| ⑤ **KL 正则** 到参考策略 β·KL | ✅ | `kl_grad_to_ref` |
| ⑥ **内层多 epoch**（固定 π_old 更新 μ 步） | ✅ | `inner_epochs` 循环 |
| ⑦ **多步序贯**（沿推理链、状态向后传递） | ✅ | 复用 C 的决策树 |

## 运行（与不注入 baseline 对比 + 出图）
```bash
# 冒烟（无 LLM）
python GRPO/build_seqmdp_cache.py --backend mock --n 24 --dmax 3 --out GRPO/cache/seqmdp_table_mock.jsonl
python GRPO/train_seqmdp_grpo_full.py --table GRPO/cache/seqmdp_table_mock.jsonl --kfold 3 --no_plot

# 真实（先 build_seqmdp_cache.py --backend real 建好缓存，再跑）
python GRPO/train_seqmdp_grpo_full.py --kfold 5 --lam 0.0 \
    --G 8 --outer_iters 300 --inner_epochs 4 --clip_eps 0.2 --beta 0.01 --lr 0.3
```
输出：k 折交叉验证下 **no-inject baseline / TRUE GRPO(full) / full-inject / oracle** 四者准确率，
打印「TRUE GRPO 相对不注入 baseline 的百分点增益」，并在 `cache/grpo_full_vs_baseline.png` 出柱状图。

> 说明：因动作空间可枚举、回报已缓存，C-精确版与 C-full 通常结果相当；C-full 的价值在于
> **算法完整性与论文叙事**（可正当声明实现了完整 GRPO 并与精确梯度变体做消融），不保证涨点。

---

# 路线 C-sampled：**端到端采样**的完整 GRPO（`train_seqmdp_grpo_sampled.py`）

三个版本的"采样 vs 枚举"层次：

| 版本 | 数据收集 | 训练 | 一句话 |
|---|---|---|---|
| C-精确 | 枚举 2^k | 精确期望梯度（无采样） | 最干净，但不带 IS/clip |
| C-full | 枚举 2^k | 在枚举缓存上**采样**训练 | 训练采样，数据仍枚举 |
| **C-sampled** | **采样**（只 rollout 采到的轨迹） | 采样训练 | **端到端不枚举**，真 GRPO |

C-sampled 每个外层迭代对每题用 π_old 采样 G 条轨迹，**只对采样到的轨迹调用环境 rollout**
（惰性缓存；node_state 不需 LLM，故采样路径零成本；LLMBackend 按 prompt 缓存进一步去重）。
决策数 dmax 增大时成本按 **G 线性增长**，而非 2^k 指数。完整 GRPO 七项特征全部满足。

## 运行（与不注入 baseline 对比 + 出图）
```bash
# 冒烟（确定性 mock，无需 LLM/网络）
python GRPO/train_seqmdp_grpo_sampled.py --backend mock --n 24 --kfold 3 --outer_iters 60 --no_plot

# 真实后端（子问题→llama、最终→deepseek），tmux 里跑；无需先建枚举缓存
python GRPO/train_seqmdp_grpo_sampled.py --backend real --n 200 --kfold 5 \
    --G 8 --outer_iters 200 --inner_epochs 4 --clip_eps 0.2 --beta 0.01 --lr 0.3
```
输出 **no-inject baseline / TRUE GRPO(sampled) / full-inject / oracle** 四者准确率、相对 baseline
的百分点增益、训练触发的不同轨迹 rollout 数（佐证"采样而非枚举"），并出 `cache/grpo_sampled_vs_baseline.png`。
温度默认 0 → 环境确定、可复现。**会导出可部署权重 `theta` 到 `cache/seqmdp_grpo_sampled_policy.json`。**

## 在线计时对比（准确率 + 时间，同口径对比 baseline）
多步采样 GRPO 已接入在线对比脚本 `CSQA_dotrun_step2_grpo_compare.py`，新增 mode `seqmdp_grpo`：
沿推理链逐节点用学好的策略**实时决策注/不注**（单趟，真实计时；被注入节点答案喂给后续节点）。
```bash
# 先用真实后端训练并导出 theta（上一节命令），再跑在线计时对比：
# 2方（最干净：baseline vs 多步GRPO）
python CSQA_dotrun_step2_grpo_compare.py --rounds 3 --n 200 --modes no_inject,seqmdp_grpo
# 或 4方（含路线A的两种）
python CSQA_dotrun_step2_grpo_compare.py --rounds 3 --n 200 \
    --modes no_inject,offline_grpo,online_grpo,seqmdp_grpo
# 出表 + 图（自动识别 summary.json 里的模式）
python GRPO/plot_compare.py
```
输出每题平均耗时 + 准确率（±std）+ 注入题数 + tokens。注意：多步注入是**单趟**完成（把知识
拼进对应节点 prompt），不像路线A需要对最终总结**再问一次**，因此其时间通常接近 no_inject。
