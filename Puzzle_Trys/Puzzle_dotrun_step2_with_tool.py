# -*- coding: utf-8 -*-
"""
Puzzle step2（工具增强版）。

与原 Puzzle_dotrun_step2.py 的唯一区别：在每题推理前增加「工具优先」分支。
  - 读入 step2In_Puzzle_with_tool.json（含 build_with_tool.py 产出的 allo_tool / tool_args）；
  - 若本题分配了本地工具，则先用以 sat 为 oracle 的本地工具（search，内部即 verify 校验）求解；
  - 工具解出 → 直接采用其答案、跳过全部 LLM 调用（提升正确率 + 降低时间开销）；
  - 工具未命中 → 完全回退到原有 LLM 推理流程，行为与原 step2 一致。

计数口径与原 step2 相同：每题只判一次，Correct_Q + False_Q + Error_Q = N。

可回滚：本文件为新增脚本，不触碰原 Puzzle_dotrun_step2.py。
        删除本文件（及 tools/、build_with_tool.py、with_tool.json）即可完全还原。
运行：cd Puzzle_Trys && python Puzzle_dotrun_step2_with_tool.py
"""
import ast
import json
import os
import re
import sys
import time
from datetime import datetime
from typing import List
from tqdm import tqdm
sys.path.append('../')
import logging
from puzzle_utils import *
from utils import *

BASE = os.path.dirname(os.path.abspath(__file__))
sys.path.append(BASE)
from tools import run_tool   # 本地确定性工具统一入口（sat-oracle 的 verify / search）

openaiClient = setOpenAi(keyid=0)
llamaClient = setLocal()
clients = {'gpt': openaiClient, 'llama': llamaClient}
aftername = "with_tool-step2"

USE_TOOL = True   # 总开关：置 False 即退化为纯 LLM 流程，便于 A/B 对照


def solve_by_tool(record):
    # 工具优先：若本题分配了本地工具，运行之；解出则返回答案(repr 字符串)，否则 None
    for name, args in zip(record.get('allo_tool', []), record.get('tool_args', [])):
        if name and name != 'no_tool':
            res = run_tool(name, args)
            if res['success']:
                return res['result']
    return None


if __name__ == '__main__':

    start_time = time.time()
    now = datetime.now()
    formatted_now = now.strftime("%Y-%m-%d-%H-%M-%S")
    tokens_path = f'Tokens/token_usage_{formatted_now}.json'
    if not os.path.exists(tokens_path):
        with open(tokens_path, 'w') as f:
            json.dump({}, f)
    logger, filename = setup_logger(aftername)

    with open("puzzles.json", "r") as f:
        puzzles = json.load(f)

    with open('Puzzle_config.json', 'r') as f:
        config = json.load(f)
    config['tokens_path'] = tokens_path

    success_Q = 0
    false_Q = 0      # 正常完成判题但 sat 为 False（每题最多 +1）
    error_Q = 0      # 基础设施/运行异常，无法完成判题（每题最多 +1）
    tool_hit = 0     # 由本地工具直接解出的题数（用于评估工具收益）
    N = 200

    # 工具增强版读入 with_tool.json；其余结构与原 last.json 完全一致
    with open('TmpRes/step2In_Puzzle_with_tool.json', 'r') as f:
        middleRes = json.loads(f.read())

    for question_id in tqdm(range(N)):
        question = puzzles[question_id]['sat']

        logger.info('\n\n\n')
        logger.info(f'number id: {question_id}')
        logger.info('label id: ' + puzzles[question_id]['name'])
        logger.info('puzzle content:')
        logger.info(question)

        try:
            record = middleRes[str(question_id)]

            # ===== 工具优先分支：本地解出则直接采用，跳过 LLM =====
            tool_result = solve_by_tool(record) if USE_TOOL else None
            if tool_result is not None:
                finalResult = tool_result
                converted_result = ast.literal_eval(tool_result)  # search 返回的恒为合法字面量
                tool_hit += 1
                logger.info('Tool->%s', finalResult)
            else:
                # ===== 回退：原有 LLM 子任务推理流程 =====
                steps, steps_dict, allo_model, depths, int_edges = record['steps'], record['steps_dict'], record['allo_model'], record['depths'], record['int_edges']
                depths = {int(k): v for k, v in depths.items()}
                heights = list(depths.keys())
                MAXHeight = max(heights)
                answerDict = {}

                for i in range(MAXHeight):
                    subtasks = depths[i]
                    for subtaskid in subtasks:

                        number = re.findall(r'\d+', subtaskid)
                        number = int(number[0]) if number else None
                        subtask = steps_dict[str(number)]
                        answer_MODEL = allo_model[number-1]

                        sys_q = f"""You will be provided with a Programming Puzzle. Your task is to find an input that will make the program return True.
Here is the puzzle:\n{question}

The data type of your final answer should be {puzzles[question_id]['ans_type']}.
I have broken this puzzle down into many easier subtasks. I will assign you sub-tasks one by one, and provide the results of the previous sub-tasks as a reference for your reasoning.
Please follow the logical sequence of our subtasks to find the correct input."""

                        if len(answerDict) > 0:
                            answersSoFar = f"""\nSo far, the answers to the resolved sub-tasks are as follows: The format is SubtaskId: xxx; Subtask: xxx; Answer: xxx."""
                            for key, value in answerDict.items():
                                answersSoFar += f"""\nSubtaskId: {key}; Subtask: {answerDict[key]['subtask']}; Answer: {answerDict[key]['answer']}."""

                            predecessors = search_Predecessors(int_edges, number)
                            intersection = set(answerDict.keys()).intersection(set(predecessors))
                            count = len(intersection)
                            if count > 0:
                                answersSoFar += f"""\nAmong them, sub-tasks {predecessors} are directly related to this sub-task, so please pay special attention to them."""

                        subask = f"""\nNow the subtask is: {subtask}
Based on the information above, please provide a concise and clear answer to this sub-task in one or two sentences.."""

                        query = answersSoFar + subask if len(answerDict) > 0 else subask

                        Q = [{'role': 'system', 'content': sys_q},
                             {'role': 'user', 'content': query}]

                        result = askLLM(clients, Q, tokens_path=tokens_path, model=answer_MODEL, temperature=1, max_tokens=300)
                        answerDict[number] = {'subtask': subtask, 'answer': result}

                Q.append({'role': 'assistant', 'content': result})
                Q.append({'role': 'user', 'content': f"""Now that all the sub-tasks have been completed, so what is the correct input?
Please give the input in the format of a string and just give the answer without any additional explanation or clarification."""})
                finalResult = askLLM(clients, Q, tokens_path=tokens_path, model=config['finalSummarize_MODEL'], temperature=1)
                finalResult = remove_quotes(finalResult)
                converted_result = convert_to_type(puzzles[question_id]['ans_type'], finalResult)

            # ===== 统一 sat 校验 + 计数（工具/LLM 两条路径共用）=====
            exec(question)
            result = sat(converted_result)
            if result == True:
                success_Q += 1
                logger.info('True->Success')
            else:
                false_Q += 1
                logger.info('False->Fail')

        except Exception as e:
            error_Q += 1
            logger.info('Runtime error: %s', e)
            print(f"error; taskid: {question_id}")

    end_time = time.time()
    elapsed_time = end_time - start_time
    hours, minutes, seconds = seconds_to_hms(elapsed_time)
    logger.info(f"200 solving 运行耗时: {hours}h, {minutes}min, {seconds}s")

    logger.info(f'\n{tokens_path}')
    logger.info(f'Correct_Q: {success_Q}')
    logger.info(f'False_Q: {false_Q}')
    logger.info(f'Error_Q: {error_Q}')
    logger.info(f'Sum_Q: {success_Q + false_Q + error_Q}')
    logger.info(f'Acc: {success_Q / N:.2%}')
    logger.info(f'Tool_hit: {tool_hit}')   # 本地工具直接解出的题数

    with open(tokens_path, 'r') as f:
        token_usage = json.load(f)
        total_tokens, total_cost = CountCost(token_usage)
        logger.info(f"Total Tokens: {total_tokens}")
        logger.info(f"Total Cost: ${total_cost:.2f}")
