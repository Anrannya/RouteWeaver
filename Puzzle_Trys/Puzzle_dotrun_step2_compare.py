# -*- coding: utf-8 -*-
"""
Puzzle step2 工具对比脚本：在同一轮内依次跑「不带工具 / 带工具」，用于验证工具有效性。

输出在 Puzzle_dotrun_step2.py 基础上仅新增：
  - Avg_time_per_Q：每一题回答的平均耗时（秒）

可选参数：
  - --rounds：对比轮数（每轮各跑一遍不带工具、带工具）

日志：
  - Logs/compare log/<运行时间戳>/  每次运行一个文件夹
  - 每轮对比一个 .log 文件，文件名用该轮开始时间戳命名（--rounds 5 则 5 个文件）

可回滚：本文件为新增脚本，不修改 Puzzle_dotrun_step2.py。
运行：cd Puzzle_Trys && python Puzzle_dotrun_step2_compare.py --rounds 1
"""
import argparse
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
from protocol import canonical_depths, model_for_step
from puzzle_utils import *
from utils import *

BASE = os.path.dirname(os.path.abspath(__file__))
sys.path.append(BASE)
from tools import run_tool

openaiClient = setOpenAi(keyid=0)
llamaClient = setLocal()
clients = {'gpt': openaiClient, 'llama': llamaClient}
N = 200
LOG_ROOT = os.path.join(BASE, "Logs", "compare log")


def setup_compare_logger(log_file):
    # 对比专用 logger：写入 Logs/compare log/<运行时间戳>/<轮次时间戳>.log
    os.makedirs(os.path.dirname(log_file), exist_ok=True)
    logger = logging.getLogger(log_file)
    logger.setLevel(logging.DEBUG)
    logger.handlers.clear()
    fmt = logging.Formatter('%(asctime)s [%(levelname)s] %(message)s', datefmt='%Y-%m-%d %H:%M:%S')
    fh = logging.FileHandler(log_file, encoding='utf-8')
    fh.setFormatter(fmt)
    sh = logging.StreamHandler(sys.stdout)
    sh.setFormatter(fmt)
    logger.addHandler(fh)
    logger.addHandler(sh)
    return logger


def solve_by_tool(record):
    for name, args in zip(record.get('allo_tool', []), record.get('tool_args', [])):
        if name and name != 'no_tool':
            res = run_tool(name, args)
            if res['success']:
                return res['result']
    return None


def run_llm(question_id, question, record, config, tokens_path):
    steps, steps_dict, allo_model, depths, int_edges = (
        record['steps'], record['steps_dict'], record['allo_model'],
        record['depths'], record['int_edges'],
    )
    depths = canonical_depths(record)
    answerDict = {}
    Q = None
    result = ''

    for i in sorted(depths):
        for subtaskid in sorted(depths[i]):
            number = int(re.findall(r'\d+', subtaskid)[0])
            subtask = steps_dict[str(number)]
            answer_MODEL = model_for_step(record, number)

            sys_q = f"""You will be provided with a Programming Puzzle. Your task is to find an input that will make the program return True.
Here is the puzzle:\n{question}

The data type of your final answer should be {puzzles[question_id]['ans_type']}.
I have broken this puzzle down into many easier subtasks. I will assign you sub-tasks one by one, and provide the results of the previous sub-tasks as a reference for your reasoning.
Please follow the logical sequence of our subtasks to find the correct input."""

            if answerDict:
                answersSoFar = """\nSo far, the answers to the resolved sub-tasks are as follows: The format is SubtaskId: xxx; Subtask: xxx; Answer: xxx."""
                for key in answerDict:
                    answersSoFar += f"""\nSubtaskId: {key}; Subtask: {answerDict[key]['subtask']}; Answer: {answerDict[key]['answer']}."""
                preds = search_Predecessors(int_edges, number)
                if set(answerDict.keys()) & set(preds):
                    answersSoFar += f"""\nAmong them, sub-tasks {preds} are directly related to this sub-task, so please pay special attention to them."""
                query = answersSoFar + f"""\nNow the subtask is: {subtask}
Based on the information above, please provide a concise and clear answer to this sub-task in one or two sentences.."""
            else:
                query = f"""\nNow the subtask is: {subtask}
Based on the information above, please provide a concise and clear answer to this sub-task in one or two sentences.."""

            Q = [{'role': 'system', 'content': sys_q}, {'role': 'user', 'content': query}]
            result = askLLM(clients, Q, tokens_path=tokens_path, model=answer_MODEL, temperature=1, max_tokens=300)
            answerDict[number] = {'subtask': subtask, 'answer': result}

    Q.append({'role': 'assistant', 'content': result})
    Q.append({'role': 'user', 'content': """Now that all the sub-tasks have been completed, so what is the correct input?
Please give the input in the format of a string and just give the answer without any additional explanation or clarification."""})
    finalResult = askLLM(clients, Q, tokens_path=tokens_path, model=config['finalSummarize_MODEL'], temperature=1)
    return remove_quotes(finalResult)


def run_mode(use_tool, middleRes, config, tokens_path, logger):
    success_Q = false_Q = error_Q = 0
    q_times = []

    for question_id in tqdm(range(N), desc='with_tool' if use_tool else 'no_tool'):
        question = puzzles[question_id]['sat']
        t0 = time.time()

        logger.info('\n\n\n')
        logger.info(f'number id: {question_id}')
        logger.info('label id: ' + puzzles[question_id]['name'])
        logger.info('puzzle content:')
        logger.info(question)

        # 阶段 A｜DoT 求解流程：只有这里抛异常才算 Error_Q（DoT 卡在回答过程中、没跑完整个流程）
        try:
            record = middleRes[str(question_id)]
            tool_result = solve_by_tool(record) if use_tool else None
            if tool_result is not None:
                logger.info('Tool->%s', tool_result)
                final_output = tool_result
            else:
                final_output = run_llm(question_id, question, record, config, tokens_path)
        except Exception as e:
            error_Q += 1
            logger.info('Runtime error: %s', e)
            print(f"error; taskid: {question_id}")
            q_times.append(time.time() - t0)
            continue

        # 阶段 B/C｜答案转换 + 裁判判定：DoT 已产出最终答案，这里任何异常都算 DoT 没答对 -> False_Q，直接进入下一题
        try:
            if use_tool and tool_result is not None:
                converted_result = ast.literal_eval(final_output)
            else:
                converted_result = convert_to_type(puzzles[question_id]['ans_type'], final_output)

            exec(question, globals())   # 注入到模块全局，使下方裸调用 sat(...) 可解析（函数内 exec 不进局部作用域）
            if sat(converted_result) is True:
                success_Q += 1
                logger.info('True->Success')
            else:
                false_Q += 1
                logger.info('False->Fail')
        except Exception as e:
            false_Q += 1
            logger.info('False->Fail (answer/judge error: %s)', e)
            q_times.append(time.time() - t0)
            continue

        q_times.append(time.time() - t0)

    elapsed = sum(q_times)
    hours, minutes, seconds = seconds_to_hms(elapsed)
    avg_t = elapsed / N

    logger.info(f"{N} solving 运行耗时: {hours}h, {minutes}min, {seconds}s")
    logger.info(f'\n{tokens_path}')
    logger.info(f'Correct_Q: {success_Q}')
    logger.info(f'False_Q: {false_Q}')
    logger.info(f'Error_Q: {error_Q}')
    logger.info(f'Sum_Q: {success_Q + false_Q + error_Q}')
    logger.info(f'Acc: {success_Q / N:.2%}')
    logger.info(f'Avg_time_per_Q: {avg_t:.2f}s')

    with open(tokens_path, 'r') as f:
        total_tokens, total_cost = CountCost(json.load(f))
    logger.info(f"Total Tokens: {total_tokens}")
    logger.info(f"Total Cost: ${total_cost:.2f}")

    return success_Q, avg_t


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--rounds', type=int, default=1, help='对比轮数')
    parser.add_argument('--n', type=int, default=200, help='每种模式评测的题目数量（前 n 题）')
    args = parser.parse_args()
    N = args.n   # 覆盖全局题数：run_mode 直接读取该全局变量

    with open('puzzles.json', 'r') as f:
        puzzles = json.load(f)
    with open('Puzzle_config.json', 'r') as f:
        config = json.load(f)
    with open('TmpRes/step2In_Puzzle_last.json', 'r') as f:
        middle_no_tool = json.loads(f.read())
    with open('TmpRes/step2In_Puzzle_with_tool.json', 'r') as f:
        middle_with_tool = json.loads(f.read())

    run_ts = datetime.now().strftime("%Y-%m-%d-%H-%M-%S")
    session_dir = os.path.join(LOG_ROOT, run_ts)
    os.makedirs(session_dir, exist_ok=True)
    print(f'日志目录: {session_dir}')

    for r in range(1, args.rounds + 1):
        round_ts = datetime.now().strftime("%Y-%m-%d-%H-%M-%S")
        log_file = os.path.join(session_dir, f"{round_ts}.log")
        logger = setup_compare_logger(log_file)

        logger.info('===== Round %d/%d =====', r, args.rounds)
        print(f'\n===== Round {r}/{args.rounds} -> {log_file} =====')

        tok_no = f'Tokens/token_usage_no_tool_{round_ts}.json'
        tok_yes = f'Tokens/token_usage_with_tool_{round_ts}.json'
        for p in (tok_no, tok_yes):
            os.makedirs(os.path.dirname(p), exist_ok=True)
            if not os.path.exists(p):
                json.dump({}, open(p, 'w'))

        config['tokens_path'] = tok_no
        logger.info('===== no_tool =====')
        acc_no, t_no = run_mode(False, middle_no_tool, config, tok_no, logger)

        config['tokens_path'] = tok_yes
        logger.info('===== with_tool =====')
        acc_yes, t_yes = run_mode(True, middle_with_tool, config, tok_yes, logger)

        logger.info('Round %d summary | no_tool: Acc=%d/%d, Avg_time=%.2fs', r, acc_no, N, t_no)
        logger.info('Round %d summary | with_tool: Acc=%d/%d, Avg_time=%.2fs', r, acc_yes, N, t_yes)
        print(f'Round {r} | no_tool: Acc={acc_no}/{N}, Avg_time={t_no:.2f}s')
        print(f'Round {r} | with_tool: Acc={acc_yes}/{N}, Avg_time={t_yes:.2f}s')
