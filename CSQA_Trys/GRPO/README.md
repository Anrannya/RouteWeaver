# GRPO 知识注入策略 —— 工作目录

本目录承载「把知识注入建模成推理图上的序贯决策、用 GRPO 训练一个轻量注入策略（LLM 冻结）」的全部代码与结果。

## 路线图（每一步都朝着可实现 GRPO）

- [x] **Step 1 注入环境骨架** (`injection_env.py`)
      忠实复刻 `CSQA_dotrun_step2.py` 的子问题求解流程，但支持「在指定子问题节点 / 最终总结环节注入 KB 证据」。这是 GRPO 的 environment。
- [x] **Step 2 无训练对照实验** (`compare_injection_positions.py`)
      同一批题，对比 4 种注入位置策略的最终答对率，验证"注入位置是否真的影响结果"（GRPO 价值的命门）。
- [ ] Step 3 离线奖励缓存（temperature=0，一次性算好所有轨迹奖励）
- [ ] Step 4 小策略网络 + 表上 GRPO 训练
- [ ] Step 5 主对比 + 消融 + 分析

## 组件

- `llm_backend.py`：统一的 LLM 调用入口，带磁盘缓存（为离线 GRPO 做准备）。
  - `--backend real`：用项目原生 `askLLM`（子问题=本地 ollama llama3-8b，最终总结=DeepSeek，需在 tmux 里有 DEEPSEEK_API_KEY）。
  - `--backend mock`：确定性假后端，仅用于管道自检，不产生科学结论。
- `injection_env.py`：注入环境。核心函数 `solve(qid, inject_subq, inject_final)`。
- `compare_injection_positions.py`：Step 2 对照实验驱动。

## 真实运行命令（在 tmux、DoT_env、已 export DEEPSEEK_API_KEY 下）

```bash
cd /data1/chenshangxiao/DoT/DoT/CSQA_Trys
python GRPO/compare_injection_positions.py --limit 100 --backend real
```

输出在 `GRPO/Logs/inject_compare/<时间戳>/`。
