# -*- coding: utf-8 -*-
"""
统一 baseline 运行器：直接复用各 benchmark 的 step2In(TmpRes) 里已分解好的 200 题子问题，
在 **相同子问题** 上跑 CoT / ToT / SD 三个 baseline，用 deepseek 与 llama3:8b 两个模型。

覆盖：MATH / CSQA / Puzzle（这三者的 step2In 是 200 题且与原始数据集按题号对齐）。
  - WebShop 是实时环境驱动的 baseline（webshop_*.py），没有 step2In 200 题结构，不在本脚本内。

为什么读 step2In 而不重新分解：三个 baseline 原本每题都要各自调用 decompose_sql 现场分解，
既费 API 又导致“各 baseline / DoT 的子问题不一致”。这里统一喂 DoT step1 已分解好的同一套子问题，
使 CoT / ToT / SD / DoT 在完全相同的子问题上对比，公平且省钱。仅忽略 step2In 里的 allo_model 字段
（那是 DoT adapter 的分配结果，baseline 不需要）。

模型路由（沿用主 utils.askLLM）：
  deepseek -> "deepseek-v4-pro"（clients['gpt']，https://api.deepseek.com）
  llama    -> "llama3:8b"       （clients['llama']，本地 ollama :11434）

判分：
  MATH   -> 用 deepseek 做 True/False 裁判（与 DoT 主实验一致，避免 llama 自判不可靠）
  CSQA   -> 严格字母匹配（A-E）
  Puzzle -> 执行 sat() 代码验证（convert_to_type 后调用）

用法见文件末尾或 README 说明。
"""
import argparse
import json
import logging
import os
import re
import sys
import time
from typing import Any, List

from tqdm import tqdm

HERE = os.path.dirname(os.path.abspath(__file__))   # .../DoT/DoT/Baselines
ROOT = os.path.dirname(HERE)                          # .../DoT/DoT
sys.path.insert(0, ROOT)
from utils import CountCost, askLLM, seconds_to_hms, setLocal, setOpenAi  # noqa: E402

MODEL = {'deepseek': 'deepseek-v4-pro', 'llama': 'llama3:8b'}
LOG_DIR = os.path.join(HERE, 'Logs')

STEP2IN = {
    'MATH':   'MATH_Trys/TmpRes/step2In_MATH_last.json',
    'CSQA':   'CSQA_Trys/TmpRes/step2In_csqa_last.json',
    'Puzzle': 'Puzzle_Trys/TmpRes/step2In_Puzzle_last.json',
}


# ---------- MATH: 抽取标准答案（\boxed{...}） ----------
def last_boxed_only_string(string):
    idx = string.rfind('\\boxed')
    if idx < 0:
        idx = string.rfind('\\fbox')
        if idx < 0:
            return None
    i, depth, right = idx, 0, None
    while i < len(string):
        if string[i] == '{':
            depth += 1
        elif string[i] == '}':
            depth -= 1
            if depth == 0:
                right = i
                break
        i += 1
    return string[idx:right + 1] if right is not None else None


def remove_boxed(s):
    left = '\\boxed{'
    try:
        assert s[:len(left)] == left and s[-1] == '}'
        return s[len(left):-1]
    except Exception:
        return s


# ---------- Puzzle: 把模型输出转成 sat() 需要的类型 ----------
_TYPE = {
    'str': str, 'int': int, 'float': float, 'bool': bool,
    'List[int]': list, 'List[str]': list, 'List[float]': list, 'List[bool]': list,
    'List[List[int]]': list, 'List[List[float]]': list, 'List[List[str]]': list,
    'List[List[List[int]]]': list,
}


def convert_to_type(type_str: str, value_str: str) -> Any:
    if type_str.startswith('List'):
        return eval(value_str)  # noqa: S307 原 baseline 同款做法：列表字面量求值
    return _TYPE.get(type_str, str)(value_str)


def remove_quotes(s: str) -> str:
    s = s.strip()
    if len(s) >= 2 and s[0] == s[-1] and s[0] in ('"', "'"):
        return s[1:-1]
    return s


# ---------- 载入 200 题（子问题来自 step2In，题面/答案来自原始数据集） ----------
def load_records(task: str, n: int):
    mid = json.load(open(os.path.join(ROOT, STEP2IN[task]), encoding='utf-8'))
    n = min(n, len(mid))
    recs = []
    if task == 'MATH':
        data = json.load(open(os.path.join(ROOT, 'Task_Datasets/MATH/all_math_p.json'), encoding='utf-8'))
        for i in range(n):
            recs.append({'question': data[i]['problem'], 'subtasks': mid[str(i)]['steps'],
                         'gold': remove_boxed(last_boxed_only_string(data[i]['solution']))})
    elif task == 'CSQA':
        data = [json.loads(l) for l in open(os.path.join(ROOT, 'Task_Datasets/CSQA/train_rand_split.jsonl'), encoding='utf-8')]
        for i in range(n):
            recs.append({'question': mid[str(i)]['problemText'], 'subtasks': mid[str(i)]['steps'],
                         'gold': data[i]['answerKey']})
    else:  # Puzzle
        data = json.load(open(os.path.join(ROOT, 'Puzzle_Trys/puzzles.json'), encoding='utf-8'))
        for i in range(n):
            recs.append({'question': data[i]['sat'], 'subtasks': mid[str(i)]['steps'],
                         'gold': None, 'ans_type': data[i]['ans_type']})
    return recs


# ---------- prompt 构造 ----------
def sys_prompt(task: str, rec: dict) -> str:
    q = rec['question']
    if task == 'MATH':
        head = f'There is a math problem. I need you to solve it and give an answer.\nHere is the problem:\n{q}'
    elif task == 'CSQA':
        head = f'There is a common sense question. I need you to solve it and give an answer.\nHere is the problem:\n{q}'
    else:
        head = (f'You will be provided with a programming puzzle. Find an input that makes the function return True.\n'
                f'Here is the puzzle:\n{q}\nThe data type of your final answer should be {rec["ans_type"]}.')
    return head + ('\n\nI have broken this problem down into a series of smaller sub-problems. I will assign you '
                   'sub-problems one by one, and provide the results of the previous sub-problems as a reference. '
                   'Please solve step by step.')


def progress(answers: List[str], subtasks: List[str]) -> str:
    if not answers:
        return ''
    s = '\nSo far, the answers to the preceding sub-problems are as follows: (Sub-problem-Id; Sub-problem; Answer)'
    for i, a in enumerate(answers):
        s += f'\nSub-problem-Id: {i}; Sub-problem: {subtasks[i]}; Answer: {a}.'
    return s


def subask(sub: str) -> str:
    return f'\nThe sub-problem to solve now is: {sub}\nBased on the information above, please provide a concise and clear answer.'


def final_prompt(task: str, rec: dict, answers: List[str]) -> str:
    body = f'Problem:\n{rec["question"]}\n\nThe sub-problems and their answers are:'
    for i, a in enumerate(answers):
        body += f'\nSub-problem-Id: {i}; Sub-problem: {rec["subtasks"][i]}; Answer: {a}.'
    if task == 'CSQA':
        tail = ("\n\nNow that all the sub-problems have been solved, what is the final answer? "
                "Only give the letter of the correct answer, e.g. 'A'. No explanation.")
    elif task == 'Puzzle':
        tail = ("\n\nNow that all the sub-problems have been solved, what is the correct input? "
                "Give only the input value (matching the required data type), no explanation, prefix or suffix.")
    else:
        tail = ("\n\nNow that all the sub-problems have been solved, what is the final answer? "
                "Please give the final answer without any additional explanation or clarification.")
    return body + tail


# ---------- 三种求解方法 ----------
def solve_cot(task, rec, model, clients, tok, temp, max_tokens):
    sysq, answers = sys_prompt(task, rec), []
    for i, sub in enumerate(rec['subtasks']):
        Q = [{'role': 'system', 'content': sysq},
             {'role': 'user', 'content': progress(answers, rec['subtasks']) + subask(sub)}]
        answers.append(askLLM(clients, Q, tok, model=model, temperature=temp, max_tokens=max_tokens))
    Q = [{'role': 'system', 'content': sysq}, {'role': 'user', 'content': final_prompt(task, rec, answers)}]
    return askLLM(clients, Q, tok, model=model, temperature=temp, max_tokens=max_tokens)


def solve_tot(task, rec, model, clients, tok, temp, max_tokens, N=2, M=1):
    # 每个子问题采样 N 个候选并自评 1-5 分，按路径累计分保留最优 M 条（此处取分数最高，修正原 baseline 取最低的笔误）
    sysq = sys_prompt(task, rec)
    paths = [(0.0, [])]
    for i, sub in enumerate(rec['subtasks']):
        cand = []
        for score, ans in paths:
            Q = [{'role': 'system', 'content': sysq},
                 {'role': 'user', 'content': progress(ans, rec['subtasks']) + subask(sub)}]
            for _ in range(N):
                r = askLLM(clients, Q, tok, model=model, temperature=temp, max_tokens=max_tokens)
                ev = Q + [{'role': 'assistant', 'content': r},
                          {'role': 'user', 'content': "Rate the confidence of this answer's correctness from 1 to 5. Only output the number."}]
                sr = askLLM(clients, ev, tok, model=model, temperature=temp, max_tokens=10)
                m = re.search(r'[1-5]', sr)
                cand.append((score + (int(m.group()) if m else 1), ans + [r]))
        paths = sorted(cand, key=lambda x: x[0], reverse=True)[:M]
    best = paths[0][1]
    Q = [{'role': 'system', 'content': sysq}, {'role': 'user', 'content': final_prompt(task, rec, best)}]
    return askLLM(clients, Q, tok, model=model, temperature=temp, max_tokens=max_tokens)


def sd_pick_model(rec, clients, tok):
    # Data Shunt：先让云端(deepseek)判整题难易，hard 走 deepseek，easy 走本地 llama
    ask = (f"Here is a question:\n{rec['question']}\nAssess whether it is simple or difficult. "
           f"Answer 'hard' or 'easy'. No explanation.")
    out = askLLM(clients, [{'role': 'user', 'content': ask}], tok, model=MODEL['deepseek'], temperature=0.6, max_tokens=10)
    return MODEL['deepseek'] if 'hard' in out.lower() else MODEL['llama']


# ---------- 判分 ----------
def judge(task, rec, final, clients, tok):
    if task == 'CSQA':
        # 只认独立的大写 A-E（\b 排除单词内部字母，不 upper() 以避开冠词 "a"）；取最后一个作结论字母
        letters = re.findall(r'\b([A-E])\b', final)
        return bool(letters and rec['gold'] and letters[-1] == rec['gold'].upper())
    if task == 'Puzzle':
        try:
            ns: dict = {}
            exec(rec['question'], ns)  # noqa: S102 定义 sat
            return bool(ns['sat'](convert_to_type(rec['ans_type'], remove_quotes(final))))
        except Exception:
            return False
    jq = [{'role': 'user', 'content': (
        "Here is a math problem with a standard answer and a student's solution. "
        "If the numerical values are the same, it is correct.\n"
        f"Problem: {rec['question']}\nStandard answer: {rec['gold']}\nAnswer: {final}\n"
        "If the student's answer is correct, output True; otherwise output False. No explanation.")}]
    out = askLLM(clients, jq, tok, model=MODEL['deepseek'], temperature=0, max_tokens=10)
    return 'true' in out.lower()


# ---------- 运行 ----------
def make_logger(name, path):
    logger = logging.getLogger(name)
    logger.setLevel(logging.INFO)
    logger.handlers.clear()
    fmt = logging.Formatter('%(asctime)s [%(levelname)s] %(message)s', datefmt='%Y-%m-%d %H:%M:%S')
    for h in (logging.FileHandler(path, mode='w', encoding='utf-8'), logging.StreamHandler(sys.stdout)):
        h.setFormatter(fmt)
        logger.addHandler(h)
    return logger


def run(task, method, model_flag, n, temp, max_tokens):
    os.makedirs(LOG_DIR, exist_ok=True)
    tag = f'{task}_{method}' + (f'_{model_flag}' if method != 'sd' else '')
    log_path = os.path.join(LOG_DIR, f'{tag}.log')
    tok = os.path.join(LOG_DIR, f'{tag}.tokens.json')
    json.dump({}, open(tok, 'w'))            # 每次运行重置 token 计数，避免累加与文件增长
    logger = make_logger(tag, log_path)

    need_gpt = method == 'sd' or model_flag == 'deepseek' or task == 'MATH'  # MATH 用 deepseek 裁判
    clients = {'llama': setLocal(), 'gpt': setOpenAi(0) if need_gpt else None}
    records = load_records(task, n)
    solve_model = MODEL.get(model_flag)     # cot/tot 固定模型；sd 逐题选择

    logger.info('task=%s method=%s model=%s n=%d temp=%s', task, method, model_flag, len(records), temp)
    ok_c = bad_c = err_c = 0
    q_times = []                                        # 每题墙钟耗时，记法与 DoT run_mode 一致
    for qid, rec in enumerate(tqdm(records, desc=tag)):
        t0 = time.time()
        try:
            if method == 'cot':
                final = solve_cot(task, rec, solve_model, clients, tok, temp, max_tokens)
            elif method == 'tot':
                final = solve_tot(task, rec, solve_model, clients, tok, temp, max_tokens)
            else:  # sd
                final = solve_cot(task, rec, sd_pick_model(rec, clients, tok), clients, tok, temp, max_tokens)
            correct = judge(task, rec, final, clients, tok)
            ok_c += correct
            bad_c += not correct
            logger.info('qid=%d %s | final=%r gold=%r', qid, 'correct' if correct else 'incorrect',
                        str(final)[:120], rec['gold'])
        except Exception as e:
            err_c += 1
            logger.info('qid=%d run error: %s', qid, e)
        q_times.append(time.time() - t0)

    total = ok_c + bad_c + err_c
    elapsed = sum(q_times)                              # 总耗时 = 各题耗时之和（同 DoT）
    hours, minutes, seconds = seconds_to_hms(elapsed)
    avg_t = elapsed / total if total else 0.0
    logger.info(f"{total} solving 运行耗时: {hours}h, {minutes}min, {seconds}s")
    logger.info('correct=%d incorrect=%d error=%d sum=%d acc=%.2f%%', ok_c, bad_c, err_c, total, 100.0 * ok_c / total)
    logger.info(f'Avg_time_per_Q: {avg_t:.2f}s')
    try:
        tt, tc = CountCost(json.load(open(tok)))
        avg_tok = tt / total if total else 0.0
        avg_cost = tc / total if total else 0.0
        logger.info('deepseek tokens=%d cost=$%.4f (llama 本地不计费)', tt, tc)
        logger.info(f'Avg_tokens_per_Q: {avg_tok:.1f}')
        logger.info(f'Avg_cost_per_Q: ${avg_cost:.6f}')
    except Exception:
        pass


if __name__ == '__main__':
    p = argparse.ArgumentParser(description='Run CoT/ToT/SD baselines on pre-decomposed step2In subtasks.')
    p.add_argument('--task', required=True, choices=list(STEP2IN))
    p.add_argument('--method', required=True, choices=['cot', 'tot', 'sd'])
    p.add_argument('--model', choices=['deepseek', 'llama'], help='cot/tot 必填；sd 忽略（混合）')
    p.add_argument('--n', type=int, default=200, help='题目数量（前 n 题）')
    p.add_argument('--temperature', type=float, default=1.0)
    p.add_argument('--max_tokens', type=int, default=1024)
    args = p.parse_args()
    if args.method in ('cot', 'tot') and not args.model:
        p.error("--model is required for cot/tot (deepseek 或 llama)")
    run(args.task, args.method, args.model, args.n, args.temperature, args.max_tokens)
