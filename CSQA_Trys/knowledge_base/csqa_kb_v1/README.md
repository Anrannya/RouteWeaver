# CSQA 本地常识知识库（阶段 1–3）

## 构建范围

输入为 `train_rand_split.jsonl`，共 9,741 道题。

本次只完成：

1. 从全部题目、候选选项和 `question_concept` 建立概念覆盖范围；
2. 为可识别概念生成脱离原题后仍成立的词义、类别、属性、能力、用途、位置等事实；
3. 进行格式清洗、原子性约束、空泛知识过滤、精确去重和数量控制。

本次没有实现运行时五选项区分验证，也没有训练 GRPO 注入路由。

## 数量

- 题目数：9,741
- 最低要求：19,482
- 最高限制：29,223
- 最终知识数：19,677
- 知识/题目比例：2.020018

## 运行版结构

主知识库 `csqa_commonsense_kb.jsonl` 每行一条记录，仅包含：

```json
{
  "fact_id": "fact_000001",
  "concept": "airport",
  "dimension": "category",
  "fact": "An airport is an airfield equipped with control tower and hangars as well as accommodations for passengers and cargo.",
  "conditions": []
}
```

运行版不保存题号、答案字母、正确选项映射、验证分数或 GRPO 字段。

## 文件说明

- `csqa_commonsense_kb.jsonl`：最终精简运行版知识库。
- `csqa_concept_inventory.json`：概念覆盖及保留词义清单。
- `csqa_kb_audit.jsonl`：离线构建来源和清洗审计信息，不应输入回答模型或 GRPO。
- `csqa_kb_summary.json`：数量、维度和来源统计。
- `build_csqa_kb_stage1_3.py`：可复现构建脚本。
- `SOURCE_NOTICE.txt`：知识来源说明。

## 数据使用边界

- CSQA 训练题用于确定概念范围和词义上下文。
- 不把 `answerKey`、题号或“某题应选择某选项”的映射写入运行知识库。
- 不把题目专属解释直接保存为事实。
- 知识正文主要由本地 WordNet 3.1 词义、类别和语义关系生成。

## 重要限制

这是一份自动构建的阶段 1–3 候选知识库，不代表其中每条事实都能区分当前五个选项，也不保证每次注入都提高正确率。

后续系统仍应完成：

1. 根据当前问题和五个选项检索少量候选事实；
2. 联合判断事实是否只明显支持一个选项；
3. 无法形成足够差距时拒绝注入；
4. 由 GRPO 学习是否注入以及注入到子问题、最终汇总或两者。
