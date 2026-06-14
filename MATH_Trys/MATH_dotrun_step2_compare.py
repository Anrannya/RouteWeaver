# -*- coding: utf-8 -*-
"""
MATH step2 工具对比脚本：同一轮内依次跑「不带工具 / 带工具」，验证「辅助式」工具的有效性。

MATH 工具是「辅助」而非「整题替代」：某子任务若分配了工具且实测成功，则用工具精确结果作为
该子任务答案、跳过该步 LLM；最终答案与对错判定仍由 LLM 完成。两种模式除工具分支外路径完全一致。

相比逐轮 Acc，本脚本额外给出最有价值的指标——**覆盖题（被分配了工具的题）在 K 轮里的逐题正收益**：
  - c_yes / c_no：该题在 with_tool / no_tool 下 K 轮各自答对的次数；
  - 判定：c_yes > c_no 记正收益，< 记负收益，= 记中性；
  - 据此可直接回答“用了工具 K 次里有几次更好”，并把不达标的题退回 no_tool。

可选参数：
  - --rounds：对比轮数（每轮各跑一遍 no_tool / with_tool）
  - --n：每种模式评测的题目数量（前 n 题），默认 200

日志：Logs/compare log/<运行时间戳>/<轮次时间戳>.log（每轮一个文件）

可回滚：本文件为新增脚本，不修改原 MATH_dotrun_step2.py。
运行：cd MATH_Trys && python MATH_dotrun_step2_compare.py --rounds 10 --n 30
"""
import argparse
import json
import logging
import os
import re
import sys
import time
from datetime import datetime
from tqdm import tqdm

sys.path.append('../')
from MATH_Trys.MATH_utils import *
from utils import *

BASE = os.path.dirname(os.path.abspath(__file__))
sys.path.append(BASE)
from tools import run_tool, extract_number

openaiClient = setOpenAi(keyid=0)
llamaClient = setLocal()
clients = {'gpt': openaiClient, 'llama': llamaClient}
N = 200
LOG_ROOT = os.path.join(BASE, "Logs", "compare log")


def setup_compare_logger(log_file):
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


def _resolve_args(args, answerDict):
    # 运行时参数解析：含 from_steps 的（aggregate）从“前驱子任务答案”取数；取不到则 None（不注入）。
    if 'from_steps' not in args:
        return args
    vals = []
    for sid in args['from_steps']:
        num = extract_number(answerDict.get(int(sid), {}).get('answer'))
        if num is None:
            return None
        vals.append(num)
    return {'operation': args['operation'], 'values': vals}


def tool_for(record, number, answerDict):
    # 子任务级工具：取下标 number-1 的模式与工具，实测成功返回 (模式, 结果字符串)，否则 None
    tools = record.get('allo_tool', [])
    targs = record.get('tool_args', [])
    modes = record.get('tool_mode', [])
    idx = number - 1
    if 0 <= idx < len(tools) and tools[idx] and tools[idx] != 'no_tool':
        args = _resolve_args(targs[idx], answerDict)
        if args is None:
            return None
        res = run_tool(tools[idx], args)
        if res['success']:
            mode = modes[idx] if idx < len(modes) else 'replace'
            return mode, res['result']
    return None


def solve_one(question, gold_answer, record, config, tokens_path, use_tool):
    # 跑完一题：子任务（可选工具注入）-> LLM 汇总 -> LLM 判对错。返回 (是否正确, 工具介入子任务数)
    steps_dict, allo_model = record['steps_dict'], record['allo_model']
    depths, int_edges = {int(k): v for k, v in record['depths'].items()}, record['int_edges']
    answerDict, tool_hit = {}, 0

    for i in range(max(depths.keys())):
        for subtaskid in depths[i]:
            number = int(re.findall(r'\d+', subtaskid)[0])
            subtask = steps_dict[str(number)]
            answer_MODEL = allo_model[number - 1]

            tinfo = tool_for(record, number, answerDict) if use_tool else None
            hint = ''
            if tinfo is not None:
                mode, tval = tinfo
                if mode == 'replace':
                    answerDict[number] = {'subtask': subtask, 'answer': tval}
                    tool_hit += 1
                    continue
                else:
                    hint = f"\nHint: a deterministic math tool computed a reliable intermediate result: {tval}. Use it as a reference, but you decide the final answer to this sub-problem."
                    tool_hit += 1

            sys_q = f"""There is a math_problem. I need you to solve it and give an answer.
Here is the problem:\n{question}

I have broken this math problem down into several smaller problems. I will assign you sub-problems one by one, and provide the results of the previous sub-problems as a reference for your reasoning.
Please solve the problem and respond according to mathematical logic.
        """
            if answerDict:
                answersSoFar = """\nSo far, the answers to the resolved sub-problems are as follows: The format is Sub-problem-Id: xxx; Sub-problem: xxx; Answer: xxx."""
                for key in answerDict:
                    answersSoFar += f"""\nSub-problem-Id: {key}; Sub-problem: {answerDict[key]['subtask']}; Answer: {answerDict[key]['answer']}."""
                preds = search_Predecessors(int_edges, number)
                if set(answerDict.keys()) & set(preds):
                    answersSoFar += f"""\nAmong them, sub-problems {preds} are directly related to this sub-problem, so please pay special attention to them."""
                query = answersSoFar + f"""\nThe sub-problem to solve now is xxx: {subtask}{hint}
Based on the information above, please provide a concise and clear answer"""
            else:
                query = f"""\nThe sub-problem to solve now is xxx: {subtask}{hint}
Based on the information above, please provide a concise and clear answer"""

            Q = [{'role': 'system', 'content': sys_q}, {'role': 'user', 'content': query}]
            result = askLLM(clients, Q, tokens_path=tokens_path, model=answer_MODEL, temperature=1, max_tokens=300)
            answerDict[number] = {'subtask': subtask, 'answer': result}

    Q = [{'role': 'user', 'content': f"""There is a math problem and the answers to all its sub-problems. Please give the final answer to the problem.
Problem:\n{question}

The answers to the sub-problems are as follows:
""" + "".join(f"\nSub-problem-Id: {k}; Sub-problem: {v['subtask']}; Answer: {v['answer']}." for k, v in answerDict.items()) + """

Now that all the sub-problems have been solved, so what is the final answer?
Please give the final answer without any additional explanation or clarification."""}]
    finalResult = askLLM(clients, Q, tokens_path=tokens_path, model=config['finalSummarize_MODEL'], temperature=1, max_tokens=300)

    judge = {'role': 'user', 'content': f"""Here is a math problem with a standard answer and a student's solution. Please help me determine if the student's solution is correct.
Problem: {question}

Standard answer: {gold_answer}

Answer: {finalResult}

If the student's answer is correct, just output True; otherwise, just output False.
No explanation is required.
"""}
    ifcorrect = askLLM(clients, [judge], tokens_path=tokens_path, model=config['judgeCorrect_MODEL'], temperature=1, max_tokens=300)
    return ('True' in ifcorrect), tool_hit


def run_mode(use_tool, problems, middleRes, config, tokens_path, logger):
    # 跑一种模式（全部 N 题）。返回 (答对数, 每题平均耗时, {qid: 是否正确})
    success_Q = false_Q = error_Q = 0
    q_times, per_q = [], {}

    for qid in tqdm(range(N), desc='with_tool' if use_tool else 'no_tool'):
        question = problems[qid]['problem']
        gold_answer = problems[qid]['solution']
        t0 = time.time()
        logger.info('\n\nnumber id: %d', qid)
        try:
            ok, hit = solve_one(question, gold_answer, middleRes[str(qid)], config, tokens_path, use_tool)
            per_q[qid] = ok
            if ok:
                success_Q += 1
                logger.info('correct (tool_hit=%d)', hit)
            else:
                false_Q += 1
                logger.info('error (tool_hit=%d)', hit)
        except Exception as e:
            error_Q += 1
            per_q[qid] = False
            logger.info('Runtime error: %s', e)
            print(f"error; taskid: {qid}")
        q_times.append(time.time() - t0)

    elapsed = sum(q_times)
    hours, minutes, seconds = seconds_to_hms(elapsed)
    avg_t = elapsed / N
    logger.info(f"{N} solving 运行耗时: {hours}h, {minutes}min, {seconds}s")
    logger.info(f'Correct_Q: {success_Q}')
    logger.info(f'False_Q: {false_Q}')
    logger.info(f'Error_Q: {error_Q}')
    logger.info(f'Sum_Q: {success_Q + false_Q + error_Q}')
    logger.info(f'Acc: {success_Q / N:.2%}')
    logger.info(f'Avg_time_per_Q: {avg_t:.2f}s')
    with open(tokens_path, 'r') as f:
        total_tokens, total_cost = CountCost(json.load(f))
    logger.info(f"Total Tokens: {total_tokens}; Total Cost: ${total_cost:.2f}")
    return success_Q, avg_t, per_q


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--rounds', type=int, default=1, help='对比轮数')
    parser.add_argument('--n', type=int, default=200, help='每种模式评测的题目数量（前 n 题）')
    args = parser.parse_args()
    N = args.n

    file_path = '../Task_Datasets/MATH/all_math_p.json'
    with open(file_path, 'r', encoding='utf-8') as f:
        problems = json.load(f)
    with open('MATH_config.json', 'r') as f:
        config = json.load(f)
    with open('TmpRes/step2In_MATH_last.json', 'r') as f:
        middle_no_tool = json.loads(f.read())
    with open('TmpRes/step2In_MATH_with_tool.json', 'r') as f:
        middle_with_tool = json.loads(f.read())

    # 覆盖题集合：前 N 题中被分配了任意工具的题（逐题正收益只统计这些题才有意义）
    covered = [qid for qid in range(N)
               if any(t != 'no_tool' for t in middle_with_tool[str(qid)].get('allo_tool', []))]

    # 跨轮累计每题答对次数
    cnt_no = {qid: 0 for qid in range(N)}
    cnt_yes = {qid: 0 for qid in range(N)}

    run_ts = datetime.now().strftime("%Y-%m-%d-%H-%M-%S")
    session_dir = os.path.join(LOG_ROOT, run_ts)
    os.makedirs(session_dir, exist_ok=True)
    print(f'日志目录: {session_dir}')
    print(f'前 {N} 题中被工具覆盖的题数: {len(covered)} -> {covered}')

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

        # ABBA 配重：奇数轮 no->with，偶数轮 with->no，抵消运行期的系统漂移（API/负载随时间变化）。
        # 与 DoT 完全同温（temperature=1），仅调整执行先后，公平且为对照实验标准做法。--rounds 2 即一个完整 ABBA。
        no_run = ('no_tool', False, middle_no_tool, tok_no)
        yes_run = ('with_tool', True, middle_with_tool, tok_yes)
        order = [no_run, yes_run] if r % 2 == 1 else [yes_run, no_run]

        res = {}
        for label, use_tool, middle, tok in order:
            config['tokens_path'] = tok
            logger.info('===== %s =====', label)
            res[use_tool] = run_mode(use_tool, problems, middle, config, tok, logger)
        acc_no, t_no, pq_no = res[False]
        acc_yes, t_yes, pq_yes = res[True]

        for qid in range(N):
            cnt_no[qid] += int(pq_no.get(qid, False))
            cnt_yes[qid] += int(pq_yes.get(qid, False))

        logger.info('Round %d | no_tool: Acc=%d/%d, Avg_time=%.2fs', r, acc_no, N, t_no)
        logger.info('Round %d | with_tool: Acc=%d/%d, Avg_time=%.2fs', r, acc_yes, N, t_yes)
        print(f'Round {r} | no_tool: Acc={acc_no}/{N}, Avg_time={t_no:.2f}s')
        print(f'Round {r} | with_tool: Acc={acc_yes}/{N}, Avg_time={t_yes:.2f}s')

    # ===== 跨轮逐题正收益汇总（只看覆盖题）=====
    summary_log = os.path.join(session_dir, "summary.log")
    slogger = setup_compare_logger(summary_log)
    K = args.rounds
    pos = neg = neu = 0
    slogger.info('===== 覆盖题逐题正收益（共 %d 题, K=%d 轮）=====', len(covered), K)
    slogger.info('题号 | with_tool对/K | no_tool对/K | 判定')
    for qid in covered:
        cy, cn = cnt_yes[qid], cnt_no[qid]
        verdict = '正收益' if cy > cn else ('负收益' if cy < cn else '中性')
        pos += cy > cn
        neg += cy < cn
        neu += cy == cn
        slogger.info('题%-4d | %d/%d | %d/%d | %s', qid, cy, K, cn, K, verdict)
    slogger.info('---- 覆盖题正收益分布: 正=%d, 负=%d, 中性=%d ----', pos, neg, neu)
    if covered:
        slogger.info('覆盖题正收益占比: %.1f%%', 100.0 * pos / len(covered))
    print(f'\n汇总已写入: {summary_log}')
