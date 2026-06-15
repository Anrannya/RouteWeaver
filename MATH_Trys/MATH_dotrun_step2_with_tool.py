# -*- coding: utf-8 -*-
"""
MATH step2（工具增强版 / 辅助式注入）。

与原 MATH_dotrun_step2.py 的唯一区别：在「子任务」层增加工具分支，按 tool_mode 分流：
  - replace（覆盖）：工具结果即该子任务答案，跳过这一步 LLM（提正确率 + 省该步调用）；
  - assist （提示）：工具结果作为参考注入提示，LLM 仍自己作答这一步（更稳，错提示可被 LLM 纠偏）；
  - no_tool：完全回退原 LLM 推理。
  最终答案始终由 LLM 汇总各子任务后给出，judge 也照旧由 LLM 完成（不跳整链）。
  防泄漏：工具参数只来自 with_tool.json 中“当前子任务自身文字”的预构造结果，不读取任何其它子任务答案/gold。

USE_TOOL 总开关：True=工具增强；False=纯 LLM（同一份代码做 A/B，保证除工具分支外路径完全一致）。

计数口径：每题只判一次，Correct_Q + False_Q + Error_Q = N（不做 MAX_TRY 重试，便于对比与计时）。

可回滚：本文件为新增脚本，不触碰原 MATH_dotrun_step2.py。
        删除本文件（及 tools/、build_with_tool.py、with_tool.json）即可完全还原。
运行：cd MATH_Trys && python MATH_dotrun_step2_with_tool.py
"""
import json
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
from tools import run_tool, extract_number, validate_assignment   # 本地确定性工具统一入口 + 运行时取值辅助

openaiClient = setOpenAi(keyid=0)
llamaClient = setLocal()
clients = {'gpt': openaiClient, 'llama': llamaClient}
aftername = "with_tool-step2"

USE_TOOL = True   # 总开关：置 False 即退化为纯 LLM 流程，便于 A/B 对照


def _resolve_args(args, answerDict):
    # 运行时参数解析：含 from_steps 的（aggregate）从“前驱子任务答案”取数填入 values；
    # 取不到任何一个值就返回 None（安全降级：不注入）。其余工具原样返回。
    if 'from_steps' not in args:
        return args
    vals = []
    for sid in args['from_steps']:
        ans = answerDict.get(int(sid), {}).get('answer')
        num = extract_number(ans)
        if num is None:
            return None
        vals.append(num)
    return {'operation': args['operation'], 'values': vals}


def tool_for(record, number, answerDict, subtask):
    # 子任务级工具：取该子任务（下标 number-1）的模式与工具，校验通过后实测，成功返回 (模式, 结果字符串)，否则 None。
    tools = record.get('allo_tool', [])
    targs = record.get('tool_args', [])
    modes = record.get('tool_mode', [])
    idx = number - 1
    if 0 <= idx < len(tools) and tools[idx] and tools[idx] != 'no_tool':
        mode = modes[idx] if idx < len(modes) else 'replace'
        ok, reason = validate_assignment(
            subtask, tools[idx], targs[idx], mode,
            all_steps=record.get('steps'), step_id=number,
            int_edges=record.get('int_edges'),
        )
        if not ok:
            return None
        args = _resolve_args(targs[idx], answerDict)
        if args is None:
            return None
        res = run_tool(tools[idx], args)
        if res['success']:
            return mode, res['result']
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

    with open('MATH_config.json', 'r') as f:
        config = json.load(f)
    config['tokens_path'] = tokens_path

    file_path = '../Task_Datasets/MATH/all_math_p.json'
    with open(file_path, 'r', encoding='utf-8') as file:
        problems = json.load(file)

    success_Q = 0
    false_Q = 0      # 正常完成判题但 judge 为 False（每题最多 +1）
    error_Q = 0      # 基础设施/运行异常，无法完成判题（每题最多 +1）
    replace_hit = 0  # 走“覆盖”的子任务次数（工具结果直接当答案）
    assist_hit = 0   # 走“提示”的子任务次数（工具结果作参考、LLM 仍作答）
    N = 200

    # 工具增强版读入 with_tool.json；其余结构与原 last.json 完全一致
    with open('TmpRes/step2In_MATH_with_tool.json', 'r') as f:
        middleRes = json.loads(f.read())

    for question_id in tqdm(range(N)):

        question = problems[question_id]['problem']
        gold_answer = problems[question_id]['solution']

        logger.info('\n\n\n')
        logger.info(f'number id: {question_id}')
        logger.info('problem content:\n')
        logger.info(question)

        try:
            record = middleRes[str(question_id)]
            steps, steps_dict, allo_model = record['steps'], record['steps_dict'], record['allo_model']
            depths, int_edges = record['depths'], record['int_edges']
            depths = {int(k): v for k, v in depths.items()}
            answerDict = {}

            for depth in sorted(depths.keys()):
                for subtaskid in sorted(depths[depth]):
                    number = int(re.findall(r'\d+', subtaskid)[0])
                    subtask = steps_dict[str(number)]
                    answer_MODEL = allo_model[number - 1]

                    # ===== 工具分支：按模式分流（aggregate 的值在此从 answerDict 的前驱取）=====
                    tinfo = tool_for(record, number, answerDict, subtask) if USE_TOOL else None
                    hint = ''
                    if tinfo is not None:
                        mode, tval = tinfo
                        if mode == 'replace':
                            # 覆盖：工具结果即该步答案，跳过该步 LLM
                            answerDict[number] = {'subtask': subtask, 'answer': tval}
                            result = tval
                            replace_hit += 1
                            logger.info('Subtask %s Replace->%s', number, tval)
                            continue
                        else:
                            # 提示：把工具结果作为参考注入，LLM 仍自己作答这一步
                            hint = f"\nHint: a deterministic math tool computed a reliable intermediate result: {tval}. Use it as a reference, but you decide the final answer to this sub-problem."
                            assist_hit += 1
                            logger.info('Subtask %s Assist-hint->%s', number, tval)

                    # ===== LLM 子问题推理（assist 模式带提示；no_tool 模式无提示）=====
                    sys_q = f"""There is a math_problem. I need you to solve it and give an answer.
Here is the problem:\n{question}

I have broken this math problem down into several smaller problems. I will assign you sub-problems one by one, and provide the results of the previous sub-problems as a reference for your reasoning.
Please solve the problem and respond according to mathematical logic.
        """

                    if len(answerDict) > 0:
                        answersSoFar = f"""\nSo far, the answers to the resolved sub-problems are as follows: The format is Sub-problem-Id: xxx; Sub-problem: xxx; Answer: xxx."""
                        for key, value in answerDict.items():
                            answersSoFar += f"""\nSub-problem-Id: {key}; Sub-problem: {answerDict[key]['subtask']}; Answer: {answerDict[key]['answer']}."""

                        predecessors = search_Predecessors(int_edges, number)
                        intersection = set(answerDict.keys()).intersection(set(predecessors))
                        if len(intersection) > 0:
                            answersSoFar += f"""\nAmong them, sub-problems {predecessors} are directly related to this sub-problem, so please pay special attention to them."""

                    subask = f"""\nThe sub-problem to solve now is xxx: {subtask}{hint}
Based on the information above, please provide a concise and clear answer"""
                    query = answersSoFar + subask if len(answerDict) > 0 else subask

                    Q = [{'role': 'system', 'content': sys_q},
                         {'role': 'user', 'content': query}]
                    result = askLLM(clients, Q, tokens_path=tokens_path, model=answer_MODEL, temperature=1, max_tokens=300)
                    answerDict[number] = {'subtask': subtask, 'answer': result}

            expected_steps = {
                int(re.findall(r"\d+", sid)[0])
                for layer in depths.values()
                for sid in layer
            }
            executed_steps = set(answerDict.keys())
            missing_steps = expected_steps - executed_steps
            if missing_steps:
                msg = f'DAG incomplete, missing steps: {sorted(missing_steps)}'
                logger.error('Q%d execution anomaly: %s', question_id, msg)
                raise RuntimeError(msg)

            # ===== 所有子任务完成后，汇总最终答案（始终由 LLM 完成）=====
            Q = [{'role': 'user', 'content': f"""There is a math problem and the answers to all its sub-problems. Please give the final answer to the problem.
Problem:\n{question}

The answers to the sub-problems are as follows:
""" + "".join(f"\nSub-problem-Id: {k}; Sub-problem: {v['subtask']}; Answer: {v['answer']}." for k, v in answerDict.items()) + """

Now that all the sub-problems have been solved, so what is the final answer?
Please give the final answer without any additional explanation or clarification."""}]
            finalResult = askLLM(clients, Q, tokens_path=tokens_path, model=config['finalSummarize_MODEL'], temperature=1, max_tokens=300)
            logger.info('finalResult: ')
            logger.info(finalResult)

            # ===== judge 始终由 LLM 完成（与原脚本一致）=====
            judgeAnswer = {'role': 'user', 'content': f"""Here is a math problem with a standard answer and a student's solution. Please help me determine if the student's solution is correct.
Problem: {question}

Standard answer: {gold_answer}

Answer: {finalResult}

If the student's answer is correct, just output True; otherwise, just output False.
No explanation is required.
"""}
            ifcorrect = askLLM(clients, [judgeAnswer], tokens_path=tokens_path, model=config['judgeCorrect_MODEL'], temperature=1, max_tokens=300)

            if 'True' in ifcorrect:
                success_Q += 1
                logger.info('correct')
            else:
                false_Q += 1
                logger.info('error')

        except Exception as e:
            error_Q += 1
            logger.info('Runtime error: %s', e)
            print(f"error; taskid: {question_id}")

    end_time = time.time()
    hours, minutes, seconds = seconds_to_hms(end_time - start_time)
    logger.info(f"{N} solving 运行耗时: {hours}h, {minutes}min, {seconds}s")

    logger.info(f'\n{tokens_path}')
    logger.info(f'Correct_Q: {success_Q}')
    logger.info(f'False_Q: {false_Q}')
    logger.info(f'Error_Q: {error_Q}')
    logger.info(f'Sum_Q: {success_Q + false_Q + error_Q}')
    logger.info(f'Acc: {success_Q / N:.2%}')
    logger.info(f'Replace_hit(subtask): {replace_hit}')   # 覆盖型工具介入的子任务次数
    logger.info(f'Assist_hit(subtask): {assist_hit}')     # 提示型工具介入的子任务次数

    with open(tokens_path, 'r') as f:
        token_usage = json.load(f)
        total_tokens, total_cost = CountCost(token_usage)
        logger.info(f"Total Tokens: {total_tokens}")
        logger.info(f"Total Cost: ${total_cost:.2f}")
