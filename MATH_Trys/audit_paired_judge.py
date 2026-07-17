# -*- coding: utf-8 -*-
"""离线配对 Judge 审计：保留原始 LLM Judge，并增加确定性数学等价审计。"""
import json
import os
import re
import sys
from collections import Counter

from sympy import Interval, FiniteSet, default_sort_key, nsimplify, simplify
from sympy.core.sympify import SympifyError
from sympy.parsing.sympy_parser import (
    convert_xor,
    implicit_multiplication_application,
    parse_expr,
    standard_transformations,
)

BASE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, BASE)
from compare_judge import normalize_final_answer

DATASET_PATH = os.path.join(BASE, '..', 'Task_Datasets', 'MATH', 'all_math_p.json')
AUDIT_STATUSES = (
    'DETERMINISTIC_CORRECT',
    'DETERMINISTIC_INCORRECT',
    'AMBIGUOUS',
    'PARSE_FAILED',
)
TRANSFORMATIONS = standard_transformations + (
    implicit_multiplication_application,
    convert_xor,
)
ASSIGNMENT_RE = re.compile(r'^\s*[A-Za-z][A-Za-z0-9_]*(?:\([^)]*\))?\s*=\s*(.+?)\s*$')


def _transition(no_ok, yes_ok):
    if not no_ok and yes_ok:
        return 'wrong_to_right'
    if no_ok and not yes_ok:
        return 'right_to_wrong'
    if no_ok and yes_ok:
        return 'right_to_right'
    return 'wrong_to_wrong'


def _load_pairs(log_dir):
    path = os.path.join(log_dir, 'pair_results.json')
    if not os.path.isfile(path):
        raise FileNotFoundError(f'missing {path}')
    data = json.load(open(path, encoding='utf-8'))
    return data.get('pairs', []), data.get('summary', {})


def _load_dataset():
    return json.load(open(DATASET_PATH, encoding='utf-8'))


def _extract_braced(text, start):
    if start >= len(text) or text[start] != '{':
        return None, start
    depth = 0
    out = []
    i = start
    while i < len(text):
        ch = text[i]
        if ch == '{':
            depth += 1
            if depth > 1:
                out.append(ch)
        elif ch == '}':
            depth -= 1
            if depth == 0:
                return ''.join(out), i + 1
            out.append(ch)
        else:
            out.append(ch)
        i += 1
    return None, start


def _extract_boxed_answers(text):
    if not text:
        return []
    answers = []
    i = 0
    token = r'\boxed'
    while True:
        pos = text.find(token, i)
        if pos < 0:
            break
        j = pos + len(token)
        while j < len(text) and text[j].isspace():
            j += 1
        if j < len(text) and text[j] == '{':
            value, end = _extract_braced(text, j)
            if value is not None:
                answers.append(value.strip())
                i = end
                continue
        i = j
    return answers


def _extract_math_segments(text):
    if not text:
        return []
    segs = []
    segs.extend(m.group(1).strip() for m in re.finditer(r'\\\((.*?)\\\)', text, flags=re.S))
    segs.extend(m.group(1).strip() for m in re.finditer(r'\\\[(.*?)\\\]', text, flags=re.S))
    return [s for s in segs if s]


def _strip_outer_delims(text):
    t = normalize_final_answer(text)
    for _ in range(3):
        prev = t
        t = t.strip().strip('*').strip()
        t = re.sub(r'^[\s:=,;]+', '', t)
        t = re.sub(r'[\s,;:.!]+$', '', t)
        if t.startswith('\\boxed{') and t.endswith('}'):
            t = t[7:-1].strip()
        if t.startswith('(') and t.endswith(')') and t.count('(') == 1 and t.count(')') == 1 and ',' not in t:
            t = t[1:-1].strip()
        if t == prev:
            break
    return t.strip()


def _replace_latex_commands(text):
    out = []
    i = 0
    while i < len(text):
        frac_token = None
        for token in (r'\dfrac', r'\tfrac', r'\frac'):
            if text.startswith(token, i):
                frac_token = token
                break
        if frac_token is not None:
            i += len(frac_token)
            while i < len(text) and text[i].isspace():
                i += 1
            if i < len(text) and text[i] == '{':
                num, i2 = _extract_braced(text, i)
                if num is None:
                    out.append(frac_token)
                    continue
                i = i2
                while i < len(text) and text[i].isspace():
                    i += 1
                if i < len(text) and text[i] == '{':
                    den, i2 = _extract_braced(text, i)
                    if den is None:
                        out.append(frac_token + '{' + num + '}')
                        continue
                else:
                    if i >= len(text):
                        out.append(frac_token + '{' + num + '}')
                        continue
                    den = text[i]
                    i2 = i + 1
            else:
                if i >= len(text):
                    out.append(frac_token)
                    continue
                num = text[i]
                i += 1
                while i < len(text) and text[i].isspace():
                    i += 1
                if i >= len(text):
                    out.append(frac_token + num)
                    continue
                if text[i] == '{':
                    den, i2 = _extract_braced(text, i)
                    if den is None:
                        out.append(frac_token + num)
                        continue
                else:
                    den = text[i]
                    i2 = i + 1
            out.append(f'(({_replace_latex_commands(num)})/({_replace_latex_commands(den)}))')
            i = i2
            continue
        if text.startswith(r'\sqrt', i):
            i += len(r'\sqrt')
            while i < len(text) and text[i].isspace():
                i += 1
            if i < len(text) and text[i] == '{':
                inner, i2 = _extract_braced(text, i)
                if inner is not None:
                    out.append(f'sqrt({_replace_latex_commands(inner)})')
                    i = i2
                    continue
            out.append('sqrt')
            continue
        out.append(text[i])
        i += 1
    return ''.join(out)


def _normalize_expr_text(text):
    t = _strip_outer_delims(text)
    t = t.replace('\n', ' ')
    t = t.replace('\u2212', '-')
    t = t.replace('\u2013', '-')
    t = t.replace('\u2014', '-')
    t = t.replace('\u221e', 'oo')
    t = t.replace(r'\left', '').replace(r'\right', '')
    t = t.replace(r'\cdot', '*').replace(r'\times', '*')
    t = t.replace(r'\infty', 'oo')
    t = t.replace(r'\,', '')
    t = _replace_latex_commands(t)
    t = re.sub(r'\\text\s*\{[^{}]*\}', ' ', t)
    t = t.replace(r'\!', '')
    t = t.replace('^', '**')
    t = t.replace('{', '(').replace('}', ')')
    t = re.sub(r'\\[a-zA-Z]+', ' ', t)
    t = t.replace('[', '(').replace(']', ')')
    t = re.sub(r'\s+', ' ', t).strip()
    return t


def _split_top_level(text, delimiter=','):
    parts = []
    depth = 0
    buf = []
    pairs = {'(': ')', '[': ']', '{': '}'}
    closing = set(pairs.values())
    for ch in text:
        if ch in pairs:
            depth += 1
        elif ch in closing and depth > 0:
            depth -= 1
        if ch == delimiter and depth == 0:
            part = ''.join(buf).strip()
            if part:
                parts.append(part)
            buf = []
        else:
            buf.append(ch)
    part = ''.join(buf).strip()
    if part:
        parts.append(part)
    return parts


def _split_solution_list(text):
    s = text
    s = re.sub(r'\s+or\s+', ',', s, flags=re.I)
    s = re.sub(r'\s+and\s+', ',', s, flags=re.I)
    return [p.strip() for p in _split_top_level(s, ',') if p.strip()]


def _parse_scalar(text):
    expr_text = _normalize_expr_text(text)
    if not expr_text:
        raise ValueError('empty scalar')
    candidates = [expr_text]
    tokens = expr_text.split()
    if len(tokens) > 1:
        for end in range(len(tokens) - 1, 0, -1):
            candidates.append(' '.join(tokens[:end]))
        for start in range(1, len(tokens)):
            candidates.append(' '.join(tokens[start:]))
    seen = set()
    last_error = None
    for candidate in candidates:
        candidate = candidate.strip()
        if not candidate or candidate in seen:
            continue
        seen.add(candidate)
        tokens = candidate.split()
        if len(tokens) > 1:
            long_word = False
            for token in tokens:
                if re.search(r'[A-Za-z]{2,}', token) and not token.startswith('sqrt') and token != 'oo':
                    long_word = True
                    break
            if long_word:
                continue
        try:
            expr = parse_expr(candidate, transformations=TRANSFORMATIONS, evaluate=True)
            if getattr(expr, 'free_symbols', None):
                expr = simplify(expr)
            if getattr(expr, 'is_number', False):
                expr = nsimplify(expr, rational=True)
            return expr
        except Exception as exc:
            last_error = exc
    if last_error is not None:
        raise last_error
    raise ValueError('failed to parse scalar')


def _scalar_equal(left, right):
    try:
        diff = simplify(left - right)
        if diff == 0:
            return True
        if getattr(diff, 'is_number', False):
            return bool(nsimplify(diff, rational=True) == 0)
    except Exception:
        return False
    return False


def _parse_assignment_values(text):
    parts = _split_top_level(text, ',')
    if not parts:
        return None
    values = []
    for part in parts:
        match = ASSIGNMENT_RE.match(part)
        if not match:
            return None
        values.append(_parse_scalar(match.group(1)))
    if len(values) == 1:
        return {'kind': 'scalar', 'value': values[0]}
    return {'kind': 'tuple', 'value': tuple(values)}


def _parse_interval(text):
    s = _strip_outer_delims(text)
    s = s.replace(r'\in', 'in')
    s = re.sub(r'\s+', ' ', s).strip()
    match = re.match(r'^(?:[A-Za-z][A-Za-z0-9_]*\s*(?:in|∈)\s*)?([\[\(])(.+),(.+)([\]\)])$', s)
    if not match:
        return None
    has_membership_prefix = bool(re.match(r'^[A-Za-z][A-Za-z0-9_]*\s*(?:in|∈)\s*', s))
    if not has_membership_prefix and '[' not in s and ']' not in s:
        return None
    left_open = match.group(1) == '('
    right_open = match.group(4) == ')'
    start = _parse_scalar(match.group(2).strip())
    end = _parse_scalar(match.group(3).strip())
    return {'kind': 'interval', 'value': Interval(start, end, left_open=left_open, right_open=right_open)}


def _parse_tuple(text):
    s = _strip_outer_delims(text)
    if not (s.startswith('(') and s.endswith(')')):
        return None
    inner = s[1:-1].strip()
    parts = _split_top_level(inner, ',')
    if len(parts) < 2:
        return None
    return {'kind': 'tuple', 'value': tuple(_parse_scalar(p) for p in parts)}


def _parse_set(text):
    s = _strip_outer_delims(text)
    if s.startswith('{') and s.endswith('}'):
        parts = _split_solution_list(s[1:-1].strip())
        if not parts:
            return None
        vals = [_parse_scalar(p) for p in parts]
        return {'kind': 'set', 'value': FiniteSet(*vals)}
    parts = _split_solution_list(s)
    if len(parts) >= 2:
        vals = [_parse_scalar(p) for p in parts]
        return {'kind': 'set', 'value': FiniteSet(*vals)}
    return None


def _parse_math_object(text):
    if text is None:
        raise ValueError('empty text')
    stripped = _strip_outer_delims(text)
    if not stripped:
        raise ValueError('empty text')

    parsed = _parse_assignment_values(stripped)
    if parsed is not None:
        return parsed

    parsed = _parse_tuple(stripped)
    if parsed is not None:
        return parsed

    parsed = _parse_interval(stripped)
    if parsed is not None:
        return parsed

    parsed = _parse_set(stripped)
    if parsed is not None:
        return parsed

    if ASSIGNMENT_RE.match(stripped):
        return {'kind': 'scalar', 'value': _parse_scalar(stripped.split('=', 1)[1])}

    return {'kind': 'scalar', 'value': _parse_scalar(stripped)}


def _math_equal(left, right):
    if left['kind'] != right['kind']:
        return False
    if left['kind'] == 'scalar':
        return _scalar_equal(left['value'], right['value'])
    if left['kind'] == 'tuple':
        if len(left['value']) != len(right['value']):
            return False
        return all(_scalar_equal(a, b) for a, b in zip(left['value'], right['value']))
    if left['kind'] == 'set':
        lvals = sorted(list(left['value']), key=default_sort_key)
        rvals = sorted(list(right['value']), key=default_sort_key)
        if len(lvals) != len(rvals):
            return False
        return all(_scalar_equal(a, b) for a, b in zip(lvals, rvals))
    if left['kind'] == 'interval':
        if not hasattr(left['value'], 'left_open') or not hasattr(right['value'], 'left_open'):
            return left['value'] == right['value']
        return (
            left['value'].left_open == right['value'].left_open
            and left['value'].right_open == right['value'].right_open
            and _scalar_equal(left['value'].start, right['value'].start)
            and _scalar_equal(left['value'].end, right['value'].end)
        )
    return False


def _merge_gold_candidates(boxed_answers):
    unique = []
    for ans in boxed_answers:
        norm = _strip_outer_delims(ans)
        if not norm:
            continue
        try:
            parsed = _parse_math_object(norm)
        except Exception:
            parsed = None
        merged = False
        for item in unique:
            if norm == item['normalized']:
                merged = True
                break
            if parsed is not None and item['parsed'] is not None and _math_equal(parsed, item['parsed']):
                merged = True
                break
        if not merged:
            unique.append({'text': ans.strip(), 'normalized': norm, 'parsed': parsed})
    return unique


def _resolve_gold_answer(solution):
    boxed = _extract_boxed_answers(solution)
    if not boxed:
        return {
            'ok': False,
            'audit_status': 'PARSE_FAILED',
            'gold_answer': None,
            'change_reason': 'failed to extract boxed answer from gold solution',
        }
    merged = _merge_gold_candidates(boxed)
    if not merged:
        return {
            'ok': False,
            'audit_status': 'PARSE_FAILED',
            'gold_answer': None,
            'change_reason': 'boxed answer extraction produced no usable answer',
        }
    if len(merged) > 1:
        return {
            'ok': False,
            'audit_status': 'AMBIGUOUS',
            'gold_answer': None,
            'change_reason': 'multiple distinct boxed answers in gold solution',
        }
    item = merged[0]
    return {
        'ok': True,
        'audit_status': None,
        'gold_answer': item['normalized'],
        'parsed_gold': item['parsed'],
        'change_reason': 'unique boxed answer extracted from gold solution',
    }


def _looks_like_direct_answer(text):
    stripped = _strip_outer_delims(text)
    if not stripped or len(stripped) > 80 or '\n' in stripped:
        return False
    return re.search(r'[A-Za-z]{3,}', stripped) is None


def _is_hedged_context(text):
    lowered = text.lower()
    return any(token in lowered for token in ('however', 'according to', 'based on', 'based upon'))


def _candidate_variants(text):
    if text is None:
        return []
    raw = str(text).strip()
    if not raw:
        return []
    variants = []

    def add(value, source, high_confidence):
        v = _strip_outer_delims(value)
        if not v:
            return
        for item in variants:
            if item['value'] == v:
                if high_confidence and not item['high_confidence']:
                    item['source'] = source
                item['high_confidence'] = item['high_confidence'] or high_confidence
                return
        variants.append({'value': v, 'source': source, 'high_confidence': high_confidence})

    add(raw, 'raw', _looks_like_direct_answer(raw))
    add(normalize_final_answer(raw), 'normalized_raw', _looks_like_direct_answer(normalize_final_answer(raw)))

    for boxed in _extract_boxed_answers(raw):
        add(boxed, 'boxed', True)

    for seg in _extract_math_segments(raw):
        add(seg, 'math_segment', False)

    norm = normalize_final_answer(raw)
    for marker in ('final answer is', 'answer is', 'answer:'):
        idx = norm.lower().rfind(marker)
        if idx >= 0:
            high = not _is_hedged_context(norm[max(0, idx - 80): idx + len(marker) + 80])
            add(norm[idx + len(marker):], marker, high)
    if ' is ' in norm.lower():
        idx = norm.lower().rfind(' is ')
        high = not _is_hedged_context(norm[max(0, idx - 80): idx + 80])
        add(norm[idx + 4:], 'last_is', high)
    if ':' in norm:
        add(norm.rsplit(':', 1)[-1], 'suffix_colon', False)
    if '=' in norm:
        add(norm.rsplit('=', 1)[-1], 'suffix_equals', False)

    tuple_hits = re.findall(r'\([^\(\)\n]*,[^\(\)\n]*\)', norm)
    interval_hits = re.findall(r'(?:[A-Za-z][A-Za-z0-9_]*\s*(?:\\in|∈)\s*)?[\[\(][^\[\]\(\)\n]*,[^\[\]\(\)\n]*[\]\)]', norm)
    for hit in tuple_hits + interval_hits:
        add(hit, 'shape_match', False)

    return variants


def _audit_branch(qid, branch, raw_result, final_answer, solution, round_num):
    record = {
        'qid': qid,
        'round': round_num,
        'branch': branch,
        'raw_result': bool(raw_result),
        'audited_result': bool(raw_result),
        'audit_status': 'PARSE_FAILED',
        'candidate_answer': None,
        'gold_answer': None,
        'change_reason': '',
    }

    gold = _resolve_gold_answer(solution)
    record['gold_answer'] = gold.get('gold_answer')
    if not gold['ok']:
        record['audit_status'] = gold['audit_status']
        record['change_reason'] = gold['change_reason']
        return record

    variants = _candidate_variants(final_answer)
    if not variants:
        record['audit_status'] = 'PARSE_FAILED'
        record['change_reason'] = 'failed to extract candidate answer from final response'
        return record

    gold_obj = gold['parsed_gold']
    parseable_high_confidence = None
    parseable_any = None
    for item in variants:
        variant = item['value']
        try:
            cand_obj = _parse_math_object(variant)
        except (SympifyError, ValueError, SyntaxError):
            continue
        except Exception:
            continue
        if parseable_any is None:
            parseable_any = item
        if item['high_confidence'] and parseable_high_confidence is None:
            parseable_high_confidence = item
        if item['high_confidence'] and gold_obj is not None and _math_equal(cand_obj, gold_obj):
            record['candidate_answer'] = variant
            record['audited_result'] = True
            record['audit_status'] = 'DETERMINISTIC_CORRECT'
            record['change_reason'] = f"candidate is mathematically equivalent to gold answer ({item['source']})"
            return record

    if parseable_high_confidence is not None:
        record['candidate_answer'] = parseable_high_confidence['value']
        record['audited_result'] = False
        record['audit_status'] = 'DETERMINISTIC_INCORRECT'
        record['change_reason'] = (
            f"parsed candidate is not mathematically equivalent to gold answer "
            f"({parseable_high_confidence['source']})"
        )
        return record

    if parseable_any is None:
        record['audit_status'] = 'PARSE_FAILED'
        record['candidate_answer'] = variants[0]['value']
        record['change_reason'] = 'unable to parse any candidate variant deterministically'
        return record

    record['candidate_answer'] = parseable_any['value']
    record['audit_status'] = 'PARSE_FAILED'
    record['change_reason'] = (
        'only low-confidence candidate fragments were parseable; keep raw judge result'
    )
    return record


def audit_pairs(pairs, dataset):
    raw = Counter()
    audited = Counter()
    status_counts = Counter()
    changed_cases = []
    branch_audits = []
    pair_reports = []

    for p in pairs:
        if p.get('no_tool_error') or p.get('with_tool_error'):
            continue
        qid = p.get('qid')
        round_num = p.get('round', 1)
        solution = dataset[qid]['solution']

        no_audit = _audit_branch(qid, 'no_tool', p.get('no_tool_correct'), p.get('no_tool_final'), solution, round_num)
        yes_audit = _audit_branch(qid, 'with_tool', p.get('with_tool_correct'), p.get('with_tool_final'), solution, round_num)

        for item in (no_audit, yes_audit):
            branch_audits.append(item)
            status_counts[item['audit_status']] += 1
            if item['raw_result']:
                raw[f"{item['branch']}_correct"] += 1
            if item['audited_result']:
                audited[f"{item['branch']}_correct"] += 1
            if item['audited_result'] != item['raw_result']:
                changed_cases.append(item)

        raw_transition = _transition(bool(no_audit['raw_result']), bool(yes_audit['raw_result']))
        audited_transition = _transition(bool(no_audit['audited_result']), bool(yes_audit['audited_result']))
        raw[raw_transition] += 1
        audited[audited_transition] += 1
        pair_reports.append({
            'qid': qid,
            'round': round_num,
            'raw_transition': raw_transition,
            'audited_transition': audited_transition,
            'no_tool': no_audit,
            'with_tool': yes_audit,
        })

    return {
        'raw_no_tool_correct': raw['no_tool_correct'],
        'raw_with_tool_correct': raw['with_tool_correct'],
        'raw_wrong_to_right': raw['wrong_to_right'],
        'raw_right_to_wrong': raw['right_to_wrong'],
        'raw_right_to_right': raw['right_to_right'],
        'raw_wrong_to_wrong': raw['wrong_to_wrong'],
        'raw_net_gain': raw['wrong_to_right'] - raw['right_to_wrong'],
        'audited_no_tool_correct': audited['no_tool_correct'],
        'audited_with_tool_correct': audited['with_tool_correct'],
        'audited_wrong_to_right': audited['wrong_to_right'],
        'audited_right_to_wrong': audited['right_to_wrong'],
        'audited_right_to_right': audited['right_to_right'],
        'audited_wrong_to_wrong': audited['wrong_to_wrong'],
        'audited_net_gain': audited['wrong_to_right'] - audited['right_to_wrong'],
        'audit_status_counts': {k: status_counts[k] for k in AUDIT_STATUSES},
        'changed_case_count': len(changed_cases),
        'changed_cases': changed_cases,
        'branch_audits': branch_audits,
        'pair_reports': pair_reports,
    }


def _write_single_report(log_dir, report, source_summary):
    json_path = os.path.join(log_dir, 'paired_judge_audit.json')
    md_path = os.path.join(log_dir, 'paired_judge_audit.md')
    payload = {'source_summary': source_summary, **report}
    json.dump(payload, open(json_path, 'w', encoding='utf-8'), ensure_ascii=False, indent=2)

    changed = report['changed_cases']
    lines = [
        '# Paired Judge Audit',
        '',
        f"experiment: `{log_dir}`",
        '',
        '## Raw',
        f"- no_tool_correct: {report['raw_no_tool_correct']}",
        f"- with_tool_correct: {report['raw_with_tool_correct']}",
        f"- wrong_to_right: {report['raw_wrong_to_right']}",
        f"- right_to_wrong: {report['raw_right_to_wrong']}",
        f"- net_gain: {report['raw_net_gain']}",
        '',
        '## Audited',
        f"- no_tool_correct: {report['audited_no_tool_correct']}",
        f"- with_tool_correct: {report['audited_with_tool_correct']}",
        f"- wrong_to_right: {report['audited_wrong_to_right']}",
        f"- right_to_wrong: {report['audited_right_to_wrong']}",
        f"- net_gain: {report['audited_net_gain']}",
        '',
        '## Audit Status',
    ]
    for status in AUDIT_STATUSES:
        lines.append(f"- {status}: {report['audit_status_counts'][status]}")
    lines.extend([
        '',
        '## Changed Cases',
        f"- count: {report['changed_case_count']}",
        f"- qids: {sorted({c['qid'] for c in changed})}",
    ])
    with open(md_path, 'w', encoding='utf-8') as f:
        f.write('\n'.join(lines) + '\n')
    return json_path, md_path


def _write_aggregate_report(root_dir, reports):
    aggregate = Counter()
    status_counts = Counter()
    changed_cases = []
    for entry in reports:
        report = entry['report']
        for key in (
            'raw_no_tool_correct',
            'raw_with_tool_correct',
            'raw_wrong_to_right',
            'raw_right_to_wrong',
            'raw_right_to_right',
            'raw_wrong_to_wrong',
            'audited_no_tool_correct',
            'audited_with_tool_correct',
            'audited_wrong_to_right',
            'audited_right_to_wrong',
            'audited_right_to_right',
            'audited_wrong_to_wrong',
        ):
            aggregate[key] += report[key]
        for status in AUDIT_STATUSES:
            status_counts[status] += report['audit_status_counts'][status]
        for item in report['changed_cases']:
            changed = dict(item)
            changed['experiment_dir'] = entry['log_dir']
            changed_cases.append(changed)

    aggregate_payload = {
        'experiments': [entry['log_dir'] for entry in reports],
        'experiment_count': len(reports),
        'raw_no_tool_correct': aggregate['raw_no_tool_correct'],
        'raw_with_tool_correct': aggregate['raw_with_tool_correct'],
        'raw_wrong_to_right': aggregate['raw_wrong_to_right'],
        'raw_right_to_wrong': aggregate['raw_right_to_wrong'],
        'raw_right_to_right': aggregate['raw_right_to_right'],
        'raw_wrong_to_wrong': aggregate['raw_wrong_to_wrong'],
        'raw_net_gain': aggregate['raw_wrong_to_right'] - aggregate['raw_right_to_wrong'],
        'audited_no_tool_correct': aggregate['audited_no_tool_correct'],
        'audited_with_tool_correct': aggregate['audited_with_tool_correct'],
        'audited_wrong_to_right': aggregate['audited_wrong_to_right'],
        'audited_right_to_wrong': aggregate['audited_right_to_wrong'],
        'audited_right_to_right': aggregate['audited_right_to_right'],
        'audited_wrong_to_wrong': aggregate['audited_wrong_to_wrong'],
        'audited_net_gain': aggregate['audited_wrong_to_right'] - aggregate['audited_right_to_wrong'],
        'audit_status_counts': {k: status_counts[k] for k in AUDIT_STATUSES},
        'changed_case_count': len(changed_cases),
        'changed_cases': changed_cases,
    }

    json_path = os.path.join(root_dir, 'paired_judge_audit_aggregate.json')
    md_path = os.path.join(root_dir, 'paired_judge_audit_aggregate.md')
    json.dump(aggregate_payload, open(json_path, 'w', encoding='utf-8'), ensure_ascii=False, indent=2)

    lines = [
        '# Paired Judge Audit Aggregate',
        '',
        f"root: `{root_dir}`",
        f"- experiments: {len(reports)}",
        '',
        '## Raw',
        f"- no_tool_correct: {aggregate_payload['raw_no_tool_correct']}",
        f"- with_tool_correct: {aggregate_payload['raw_with_tool_correct']}",
        f"- wrong_to_right: {aggregate_payload['raw_wrong_to_right']}",
        f"- right_to_wrong: {aggregate_payload['raw_right_to_wrong']}",
        f"- net_gain: {aggregate_payload['raw_net_gain']}",
        '',
        '## Audited',
        f"- no_tool_correct: {aggregate_payload['audited_no_tool_correct']}",
        f"- with_tool_correct: {aggregate_payload['audited_with_tool_correct']}",
        f"- wrong_to_right: {aggregate_payload['audited_wrong_to_right']}",
        f"- right_to_wrong: {aggregate_payload['audited_right_to_wrong']}",
        f"- net_gain: {aggregate_payload['audited_net_gain']}",
        '',
        '## Audit Status',
    ]
    for status in AUDIT_STATUSES:
        lines.append(f"- {status}: {aggregate_payload['audit_status_counts'][status]}")
    lines.extend([
        '',
        '## Changed Cases',
        f"- count: {aggregate_payload['changed_case_count']}",
        f"- qids: {sorted({c['qid'] for c in changed_cases})}",
    ])
    with open(md_path, 'w', encoding='utf-8') as f:
        f.write('\n'.join(lines) + '\n')
    return json_path, md_path, aggregate_payload


def _resolve_log_dirs(args):
    resolved = []
    seen = set()
    for arg in args:
        path = arg
        if not os.path.isabs(path):
            path = os.path.join(BASE, path)
        path = os.path.abspath(path)
        if os.path.isfile(os.path.join(path, 'pair_results.json')):
            if path not in seen:
                resolved.append(path)
                seen.add(path)
            continue
        if os.path.isdir(path):
            children = []
            for name in sorted(os.listdir(path)):
                child = os.path.join(path, name)
                if os.path.isfile(os.path.join(child, 'pair_results.json')):
                    children.append(child)
            if children:
                for child in children:
                    if child not in seen:
                        resolved.append(child)
                        seen.add(child)
                continue
        raise FileNotFoundError(f'no pair_results.json found under {arg}')
    return resolved


def main():
    if len(sys.argv) < 2:
        print('usage: python audit_paired_judge.py <experiment_log_dir> [more_dirs_or_root]')
        sys.exit(1)

    dataset = _load_dataset()
    log_dirs = _resolve_log_dirs(sys.argv[1:])
    reports = []
    for log_dir in log_dirs:
        pairs, summary = _load_pairs(log_dir)
        report = audit_pairs(pairs, dataset)
        jp, mp = _write_single_report(log_dir, report, summary)
        reports.append({'log_dir': log_dir, 'report': report, 'json_path': jp, 'md_path': mp})

    if len(reports) == 1:
        report = reports[0]['report']
        print(json.dumps({k: report[k] for k in report if k not in ('changed_cases', 'branch_audits', 'pair_reports')},
                         ensure_ascii=False, indent=2))
        print('written:', reports[0]['json_path'], reports[0]['md_path'])
        return

    common_root = os.path.commonpath([entry['log_dir'] for entry in reports])
    jp, mp, aggregate = _write_aggregate_report(common_root, reports)
    print(json.dumps({k: aggregate[k] for k in aggregate if k != 'changed_cases'}, ensure_ascii=False, indent=2))
    print('written aggregate:', jp, mp)


if __name__ == '__main__':
    main()
