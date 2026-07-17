# -*- coding: utf-8 -*-
"""
CSQA step2 三方在线对比：no_inject / offline_grpo / online_grpo。
对比真实**准确率**与**时间开销**（不报告美元成本，只附带真实 token 计数）。

三种模式（子问题求解路径完全相同，差别只在「要不要在最终总结追加知识」的决策方式）：
  * no_inject    : 原始 DoT，从不注入。
  * offline_grpo : 离线 GRPO 得出的固定规则（一致性门控）——先得到 DoT 自身答案 A，
                   本地检索得 best-guess 选项 bg；若 A != bg 则对最终总结追加知识再问一次。
  * online_grpo  : 加载离线训练好的 GRPO 策略权重（GRPO/cache/online_policy.json），
                   线上为每题打分；为公平起见，按与门控相同的注入预算（--online_budget，
                   默认 0.44），由策略分数挑出 top-k 题注入。即「同样的注入成本下，
                   学到的策略 vs 手写规则，谁挑得更准」。

说明：
  - 真实在线调用，不缓存，temperature 默认 1（与 DoT 同温），不固定随机种子。
  - 每轮按 ABBA 思路轮转三种模式的执行顺序，抵消运行期 API/负载漂移。
  - online_grpo 需要先看到 A 才能算「一致性」特征，故采用两阶段：先跑完所有题的
    无注入答案与分数，再对 top-k 题补一次带知识的最终总结。
  - 判对错：最终字母与 answerKey 直接比对。
  - 结果写 summary.json，供 plot_compare.py 画图。

运行：cd CSQA_Trys && python CSQA_dotrun_step2_grpo_compare.py --rounds 3 --n 200
"""

import argparse
import importlib.util
import json
import logging
import os
import re
import sys
import time
from datetime import datetime

import numpy as np
from tqdm import tqdm

sys.path.append('../')
from CSQA_Trys.CSQA_utils import *  # noqa: F401,F403
from CSQA_Trys.protocol import canonical_depths, model_for_step
from utils import *  # noqa: F401,F403

BASE = os.path.dirname(os.path.abspath(__file__))
GRPO_DIR = os.path.join(BASE, 'GRPO')
sys.path.append(GRPO_DIR)
from injection_env import InjectionEnv  # noqa: E402
from seq_mdp_env import SequentialInjectionEnv, FINAL  # noqa: E402


def _load(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


tg = _load("tg", os.path.join(GRPO_DIR, "train_grpo_policy.py"))
brc = _load("brc", os.path.join(GRPO_DIR, "build_reward_cache.py"))

openaiClient = setOpenAi(keyid=0)
llamaClient = setLocal()
clients = {'gpt': openaiClient, 'llama': llamaClient}
LOG_ROOT = os.path.join(BASE, "Logs", "grpo_compare")
# 可选模式：no_inject / offline_grpo / online_grpo（单步路线A） + seqmdp_grpo（多步采样GRPO）
ALL_MODES = ["no_inject", "offline_grpo", "online_grpo", "seqmdp_grpo"]
MODES = ["no_inject", "offline_grpo", "online_grpo"]  # 默认（向后兼容）
SEQ_DMAX = 3  # 多步序贯的决策节点数（末尾 dmax-1 个子问题 + 最终总结）

_ENV = InjectionEnv(backend=None)  # 仅复用检索/验证器与 build_forced_hint，不调 LLM
_SEQENV = SequentialInjectionEnv(backend=None)  # 多步模式：复用 decision_nodes/node_state，不调 LLM
_POLICY = None  # lazy-loaded weight matrix (路线A online)
_SEQ_POLICY = None  # lazy-loaded theta vector (多步采样GRPO)


def load_policy():
    global _POLICY
    if _POLICY is None:
        p = json.load(open(os.path.join(GRPO_DIR, "cache", "online_policy.json"), encoding="utf-8"))
        _POLICY = {"W": np.asarray(p["W"], dtype=np.float64), "dim": p["feature_dim"]}
    return _POLICY


def extract_letter(text):
    m = re.search(r'\b([A-E])\b', (text or '').upper())
    return m.group(1) if m else None


def best_guess_option(qid):
    ev = _ENV.build_evidence(qid)
    best = None
    for fe in ev["_val"].get("fact_evaluations", []):
        if best is None or fe.get("top1_score", 0) > best.get("top1_score", 0):
            best = fe
    return best.get("top_option") if best else None


def policy_inject_score(qid, a_none_letter):
    """线上为一题计算 P(inject)。特征经由与训练完全相同的代码路径重建。"""
    feat = brc.extract_features(_ENV, qid)
    bg = best_guess_option(qid)
    known = a_none_letter is not None and bg is not None
    feat["ni_bg_known"] = 1.0 if known else 0.0
    feat["ni_bg_disagree"] = 1.0 if (known and a_none_letter != bg) else 0.0
    X = tg.featurize([{"features": feat}])
    pol = load_policy()
    z = X @ pol["W"]
    z = z - z.max(axis=1, keepdims=True)
    e = np.exp(z)
    p = e / e.sum(axis=1, keepdims=True)
    return float(p[0, 1])


def run_blind(question, options_string, record, config, tokens_path, temperature):
    """跑子问题 + 无注入最终总结。返回 (a_none_letter, Q对话, 已用时间)。"""
    t0 = time.time()
    steps_dict, allo_model = record['steps_dict'], record['allo_model']
    depths = canonical_depths(record)
    int_edges = record['int_edges']
    answerDict = {}
    Q, result = [], ''
    for i in sorted(depths):
        for subtaskid in sorted(depths[i]):
            num = re.findall(r'\d+', subtaskid)
            number = int(num[0]) if num else None
            subtask = steps_dict[str(number)]
            answer_MODEL = model_for_step(record, number)
            sys_q = f"""There is a single-choice question involving common sense reasoning. I need you to solve it and give the right answer.
Here is the question:\n{question} 
Here are the options: \n{options_string}

I have broken this common sense reasoning question down into several smaller questions. I will assign you sub-questions one by one, and provide the results of the previous sub-questions as a reference for your reasoning."""
            if len(answerDict) > 0:
                answersSoFar = """\nSo far, the answers to the resolved sub-questions are as follows: The format is Sub-question-Id: xxx; Sub-question: xxx; Answer: xxx."""
                for key in answerDict:
                    answersSoFar += f"""\nSub-question-Id: {key}; Sub-question: {answerDict[key]['subtask']}; Answer: {answerDict[key]['answer']}."""
                predecessors = search_Predecessors(int_edges, number)
                if set(answerDict.keys()).intersection(set(predecessors)):
                    answersSoFar += f"""\nAmong them, sub-questions {predecessors} are directly related to this sub-question, so please pay special attention to them."""
            subask = f"""\nThe sub-question to solve now is xxx: {subtask}
Based on the information above, please provide a concise and clear answer"""
            query = (answersSoFar + subask) if len(answerDict) > 0 else subask
            Q = [{'role': 'system', 'content': sys_q}, {'role': 'user', 'content': query}]
            result = askLLM(clients, Q, tokens_path=tokens_path, model=answer_MODEL,
                            temperature=temperature, max_tokens=300)
            answerDict[number] = {'subtask': subtask, 'answer': result}

    Q.append({'role': 'assistant', 'content': result})
    final_user = """Now that all the sub-questions have been solved, which answer do you ultimately choose?
Please provide only the letter of the option, without any additional explanation or description."""
    Q.append({'role': 'user', 'content': final_user})
    final_raw = askLLM(clients, Q, tokens_path=tokens_path, model=config['finalSummarize_MODEL'],
                       temperature=temperature, max_tokens=300)
    return extract_letter(final_raw), Q, final_user, time.time() - t0


def load_seq_policy():
    """加载多步采样 GRPO 的策略权重 theta（10 维）。"""
    global _SEQ_POLICY
    if _SEQ_POLICY is None:
        path = os.path.join(GRPO_DIR, "cache", "seqmdp_grpo_sampled_policy.json")
        p = json.load(open(path, encoding="utf-8"))
        if "theta" not in p:
            raise RuntimeError(
                f"{path} 缺少 'theta'。请先运行 "
                "python GRPO/train_seqmdp_grpo_sampled.py --backend real ... 导出权重。")
        _SEQ_POLICY = np.asarray(p["theta"], dtype=np.float64)
    return _SEQ_POLICY


def run_seqmdp_rollout(qid, question, options_string, record, config, tokens_path,
                       temperature, theta):
    """多步序贯：沿推理链逐节点用策略实时决策注/不注（单趟，真实计时）。
    被注入节点的答案进入 answerDict 并喂给后续节点 → 真正的序贯影响。
    返回 (final_letter, n_inject, 已用时间)。"""
    t0 = time.time()
    _order, decisions = _SEQENV.decision_nodes(qid, SEQ_DMAX)
    hint = _SEQENV.build_forced_hint(qid, mode='bestguess')
    dec_subq = set(d for d in decisions if d != FINAL)
    final_is_dec = FINAL in decisions
    total_dec = len(decisions)

    steps_dict, allo_model = record['steps_dict'], record['allo_model']
    depths = canonical_depths(record)
    int_edges = record['int_edges']
    answerDict = {}
    Q, result = [], ''
    n_inject = 0
    dec_index = 0

    for i in sorted(depths):
        for subtaskid in sorted(depths[i]):
            num = re.findall(r'\d+', subtaskid)
            number = int(num[0]) if num else None
            subtask = steps_dict[str(number)]
            answer_MODEL = model_for_step(record, number)
            sys_q = f"""There is a single-choice question involving common sense reasoning. I need you to solve it and give the right answer.
Here is the question:\n{question} 
Here are the options: \n{options_string}

I have broken this common sense reasoning question down into several smaller questions. I will assign you sub-questions one by one, and provide the results of the previous sub-questions as a reference for your reasoning."""
            if len(answerDict) > 0:
                answersSoFar = """\nSo far, the answers to the resolved sub-questions are as follows: The format is Sub-question-Id: xxx; Sub-question: xxx; Answer: xxx."""
                for key in answerDict:
                    answersSoFar += f"""\nSub-question-Id: {key}; Sub-question: {answerDict[key]['subtask']}; Answer: {answerDict[key]['answer']}."""
                predecessors = search_Predecessors(int_edges, number)
                if set(answerDict.keys()).intersection(set(predecessors)):
                    answersSoFar += f"""\nAmong them, sub-questions {predecessors} are directly related to this sub-question, so please pay special attention to them."""
            subask = f"""\nThe sub-question to solve now is xxx: {subtask}
Based on the information above, please provide a concise and clear answer"""
            query = (answersSoFar + subask) if len(answerDict) > 0 else subask

            if hint and number in dec_subq:
                s = np.asarray(_SEQENV.node_state(qid, False, dec_index, total_dec, n_inject),
                               dtype=np.float64)
                if 1.0 / (1.0 + np.exp(-float(s @ theta))) > 0.5:
                    query = query + hint
                    n_inject += 1
                dec_index += 1

            Q = [{'role': 'system', 'content': sys_q}, {'role': 'user', 'content': query}]
            result = askLLM(clients, Q, tokens_path=tokens_path, model=answer_MODEL,
                            temperature=temperature, max_tokens=300)
            answerDict[number] = {'subtask': subtask, 'answer': result}

    Q.append({'role': 'assistant', 'content': result})
    final_user = """Now that all the sub-questions have been solved, which answer do you ultimately choose?
Please provide only the letter of the option, without any additional explanation or description."""
    if hint and final_is_dec:
        s = np.asarray(_SEQENV.node_state(qid, True, dec_index, total_dec, n_inject),
                       dtype=np.float64)
        if 1.0 / (1.0 + np.exp(-float(s @ theta))) > 0.5:
            final_user = final_user + hint
            n_inject += 1
        dec_index += 1
    Q.append({'role': 'user', 'content': final_user})
    final_raw = askLLM(clients, Q, tokens_path=tokens_path, model=config['finalSummarize_MODEL'],
                       temperature=temperature, max_tokens=300)
    return extract_letter(final_raw), n_inject, time.time() - t0


def hinted_final(qid, Q, final_user, config, tokens_path, temperature):
    """对最终总结追加知识再问一次。返回 (a_inj_letter, 已用时间)。"""
    t0 = time.time()
    hint = _ENV.build_forced_hint(qid, mode='bestguess')
    if not hint:
        return None, 0.0
    Q2 = Q[:-1] + [{'role': 'user', 'content': final_user + hint}]
    raw = askLLM(clients, Q2, tokens_path=tokens_path, model=config['finalSummarize_MODEL'],
                 temperature=temperature, max_tokens=300)
    return extract_letter(raw), time.time() - t0


def run_mode(mode, questions, middleRes, config, tokens_path, logger, N, temperature, online_budget):
    success = injected = 0
    q_times = []

    # ===== 多步采样 GRPO：单趟序贯决策，独立于下面的两阶段流程 =====
    if mode == 'seqmdp_grpo':
        theta = load_seq_policy()
        for qid in tqdm(range(N), desc=f'{mode}'):
            entry = questions[qid]
            question = entry['question']['stem']
            options = entry['question']['choices']
            options_string = "; ".join([f"{o['label']}: {o['text']}" for o in options])
            record = middleRes[str(qid)]
            record['_qid'] = qid
            try:
                fl, ninj, t = run_seqmdp_rollout(qid, question, options_string, record,
                                                 config, tokens_path, temperature, theta)
            except Exception as e:
                logger.info('seqmdp error qid=%d: %s', qid, e)
                fl, ninj, t = None, 0, 0.0
            success += int(fl == entry['answerKey'])
            if ninj > 0:
                injected += 1
            q_times.append(t)
        return _finalize_mode(mode, success, injected, q_times, tokens_path, logger, N)

    # 阶段一：所有题先跑无注入（三种模式都需要）
    blind = {}
    for qid in tqdm(range(N), desc=f'{mode}:blind'):
        entry = questions[qid]
        question = entry['question']['stem']
        options = entry['question']['choices']
        options_string = "; ".join([f"{o['label']}: {o['text']}" for o in options])
        record = middleRes[str(qid)]
        record['_qid'] = qid
        try:
            a_none, Q, final_user, t = run_blind(question, options_string, record, config,
                                                 tokens_path, temperature)
        except Exception as e:
            logger.info('blind error qid=%d: %s', qid, e)
            a_none, Q, final_user, t = None, [], '', 0.0
        blind[qid] = {'a_none': a_none, 'Q': Q, 'final_user': final_user, 'time': t,
                      'gold': entry['answerKey']}

    # 决定哪些题注入
    inject_ids = set()
    if mode == 'offline_grpo':
        for qid in range(N):
            a = blind[qid]['a_none']
            bg = best_guess_option(qid)
            if bg is not None and a is not None and a != bg:
                inject_ids.add(qid)
    elif mode == 'online_grpo':
        scores = []
        for qid in range(N):
            try:
                s = policy_inject_score(qid, blind[qid]['a_none'])
            except Exception as e:
                logger.info('score error qid=%d: %s', qid, e)
                s = 0.0
            scores.append((s, qid))
        k = int(round(online_budget * N))
        for _, qid in sorted(scores, key=lambda x: -x[0])[:k]:
            inject_ids.add(qid)

    # 阶段二：对需要注入的题补一次带知识的最终总结
    for qid in range(N):
        b = blind[qid]
        final_letter, extra_t = b['a_none'], 0.0
        if qid in inject_ids:
            try:
                a_inj, extra_t = hinted_final(qid, b['Q'], b['final_user'], config,
                                              tokens_path, temperature)
                if a_inj is not None:
                    final_letter = a_inj
                    injected += 1
                else:
                    extra_t = 0.0
            except Exception as e:
                logger.info('hinted error qid=%d: %s', qid, e)
        ok = (final_letter == b['gold'])
        success += int(ok)
        q_times.append(b['time'] + extra_t)

    return _finalize_mode(mode, success, injected, q_times, tokens_path, logger, N)


def _finalize_mode(mode, success, injected, q_times, tokens_path, logger, N):
    """统一汇总一个 mode 的结果（准确率 / 时间 / 注入 / tokens）。"""
    elapsed = sum(q_times)
    avg_t = elapsed / N if N else 0.0
    with open(tokens_path, 'r') as f:
        total_tokens, _ = CountCost(json.load(f))
    logger.info('[%s] Acc=%d/%d=%.2f%%  total_time=%.1fs  avg_time=%.2fs  inject=%d/%d  tokens=%d',
                mode, success, N, 100.0 * success / N, elapsed, avg_t, injected, N, total_tokens)
    return {'mode': mode, 'correct': success, 'acc': success / N, 'avg_time': avg_t,
            'total_time': elapsed, 'injected': injected, 'tokens': total_tokens}


def setup_logger(log_file):
    os.makedirs(os.path.dirname(log_file), exist_ok=True)
    logger = logging.getLogger(log_file)
    logger.setLevel(logging.INFO)
    logger.handlers.clear()
    fmt = logging.Formatter('%(asctime)s [%(levelname)s] %(message)s', datefmt='%Y-%m-%d %H:%M:%S')
    fh = logging.FileHandler(log_file, encoding='utf-8'); fh.setFormatter(fmt)
    sh = logging.StreamHandler(sys.stdout); sh.setFormatter(fmt)
    logger.addHandler(fh); logger.addHandler(sh)
    return logger


if __name__ == '__main__':
    ap = argparse.ArgumentParser()
    ap.add_argument('--rounds', type=int, default=3)
    ap.add_argument('--n', type=int, default=200)
    ap.add_argument('--temperature', type=float, default=1.0)
    ap.add_argument('--online_budget', type=float, default=0.44,
                    help='在线 GRPO 的注入预算（与门控大致相同，便于公平比较）')
    ap.add_argument('--modes', type=str, default=','.join(MODES),
                    help='逗号分隔，可选: ' + ','.join(ALL_MODES) +
                         '。例: --modes no_inject,seqmdp_grpo')
    args = ap.parse_args()

    modes = [m.strip() for m in args.modes.split(',') if m.strip()]
    bad = [m for m in modes if m not in ALL_MODES]
    if bad:
        raise SystemExit(f'未知 mode: {bad}；可选: {ALL_MODES}')

    questions = []
    with open('../Task_Datasets/CSQA/train_rand_split.jsonl', 'r') as f:
        for line in f:
            if line.strip():
                questions.append(json.loads(line))
    with open('CSQA_config.json', 'r') as f:
        config = json.load(f)
    with open('TmpRes/step2In_csqa_last.json', 'r') as f:
        middleRes = json.loads(f.read())

    N = min(args.n, len(questions))
    run_ts = datetime.now().strftime("%Y-%m-%d-%H-%M-%S")
    session_dir = os.path.join(LOG_ROOT, run_ts)
    os.makedirs(session_dir, exist_ok=True)
    print(f'日志目录: {session_dir}  N={N}  rounds={args.rounds}  modes={modes}  '
          f'temperature={args.temperature}  online_budget={args.online_budget}')

    agg = {m: [] for m in modes}
    for r in range(1, args.rounds + 1):
        round_ts = datetime.now().strftime("%Y-%m-%d-%H-%M-%S")
        log_file = os.path.join(session_dir, f"{round_ts}.log")
        logger = setup_logger(log_file)
        logger.info('===== Round %d/%d =====', r, args.rounds)
        print(f'\n===== Round {r}/{args.rounds} -> {log_file} =====')

        order = modes[(r - 1) % len(modes):] + modes[:(r - 1) % len(modes)]
        for mode in order:
            tok = f'Tokens/token_usage_{mode}_{round_ts}.json'
            os.makedirs(os.path.dirname(tok), exist_ok=True)
            json.dump({}, open(tok, 'w'))
            config['tokens_path'] = tok
            logger.info('===== %s =====', mode)
            res = run_mode(mode, questions, middleRes, config, tok, logger, N,
                           args.temperature, args.online_budget)
            agg[mode].append(res)

        line = ' | '.join(
            f'{m}: Acc={agg[m][-1]["correct"]}/{N} ({100*agg[m][-1]["acc"]:.1f}%) '
            f'avg_time={agg[m][-1]["avg_time"]:.2f}s inj={agg[m][-1]["injected"]}'
            for m in modes)
        print(f'Round {r} | {line}')

    # ===== 跨轮汇总 + 机读 summary.json =====
    summary = {'n': N, 'rounds': args.rounds, 'temperature': args.temperature,
               'online_budget': args.online_budget, 'mode_order': modes, 'modes': {}}
    slog = setup_logger(os.path.join(session_dir, "summary.log"))
    slog.info('===== 跨 %d 轮汇总 (N=%d, temperature=%s) =====', args.rounds, N, args.temperature)
    for m in modes:
        runs = agg[m]
        accs = [x['acc'] for x in runs]
        times = [x['avg_time'] for x in runs]
        injs = [x['injected'] for x in runs]
        toks = [x['tokens'] for x in runs]
        summary['modes'][m] = {
            'acc_mean': float(np.mean(accs)), 'acc_std': float(np.std(accs)),
            'avg_time_mean': float(np.mean(times)), 'avg_time_std': float(np.std(times)),
            'inject_mean': float(np.mean(injs)), 'tokens_mean': float(np.mean(toks)),
            'per_round_acc': accs, 'per_round_avg_time': times,
        }
        slog.info('%-13s | Acc=%.2f%%±%.2f  每题耗时=%.2fs±%.2f  注入=%.1f/%d  tokens=%.0f',
                  m, 100*np.mean(accs), 100*np.std(accs), np.mean(times), np.std(times),
                  np.mean(injs), N, np.mean(toks))
    json.dump(summary, open(os.path.join(session_dir, "summary.json"), "w", encoding="utf-8"),
              ensure_ascii=False, indent=2)
    print(f'\n汇总: {os.path.join(session_dir, "summary.log")}')
    print(f'机读: {os.path.join(session_dir, "summary.json")}')
