# -*- coding: utf-8 -*-
"""配对对比脚本：Judge 复用与答案规范化（无 API 依赖）"""
import hashlib
import json
import re


def stable_hash(obj):
    payload = json.dumps(obj, sort_keys=True, ensure_ascii=False, separators=(',', ':'))
    return hashlib.sha256(payload.encode('utf-8')).hexdigest()


def normalize_final_answer(text):
    """轻量规范化最终答案（不做数学等价重写）。"""
    if text is None:
        return ''
    t = str(text).strip()
    t = re.sub(r'\s+', ' ', t)
    for _ in range(3):
        prev = t
        if t.startswith('$') and t.endswith('$') and t.count('$') == 2:
            t = t[1:-1].strip()
        if t.startswith('\\(') and t.endswith('\\)'):
            t = t[2:-2].strip()
        if t.startswith('\\[') and t.endswith('\\]'):
            t = t[2:-2].strip()
        if t.startswith('\\boxed{') and t.endswith('}'):
            t = t[7:-1].strip()
        t = t.replace('\\(', '').replace('\\)', '')
        t = t.replace('$', '')
        t = re.sub(r'\s+', ' ', t).strip()
        if t == prev:
            break
    return t


def judge_with_cache(question, gold_answer, final_result, ask_fn, judge_model, tokens_path,
                     temperature, qid, judge_cache):
    """同一题规范化后相同最终答案只调用一次 Judge。返回 (raw, ok, reused)。"""
    norm = normalize_final_answer(final_result)
    key = (qid, norm)
    if key in judge_cache:
        entry = judge_cache[key]
        return entry['raw'], entry['ok'], True
    judge = {'role': 'user', 'content': f"""Here is a math problem with a standard answer and a student's solution. Please help me determine if the student's solution is correct.
Problem: {question}

Standard answer: {gold_answer}

Answer: {final_result}

If the student's answer is correct, just output True; otherwise, just output False.
No explanation is required.
"""}
    ifcorrect = ask_fn([judge], tokens_path=tokens_path, model=judge_model,
                       temperature=temperature, max_tokens=300)
    ok = 'True' in ifcorrect
    judge_cache[key] = {'raw': ifcorrect, 'ok': ok}
    return ifcorrect, ok, False
