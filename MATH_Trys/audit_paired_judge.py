# -*- coding: utf-8 -*-
"""离线配对 Judge 冲突审计：只读日志，不调用 API，不修改原始结果。"""
import json
import os
import sys

BASE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, BASE)
from compare_judge import normalize_final_answer


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


def audit_pairs(pairs):
    raw = {'wrong_to_right': 0, 'right_to_wrong': 0, 'right_to_right': 0, 'wrong_to_wrong': 0}
    audited = dict(raw)
    conflicts = []
    for p in pairs:
        if p.get('no_tool_error') or p.get('with_tool_error'):
            continue
        no_ok = bool(p.get('no_tool_correct'))
        yes_ok = bool(p.get('with_tool_correct'))
        trans = _transition(no_ok, yes_ok)
        raw[trans] += 1
        nf = normalize_final_answer(p.get('no_tool_final'))
        yf = normalize_final_answer(p.get('with_tool_final'))
        is_conflict = nf == yf and nf and no_ok != yes_ok
        if is_conflict:
            conflicts.append({
                'qid': p.get('qid'),
                'round': p.get('round', 1),
                'normalized_final': nf,
                'no_tool_correct': no_ok,
                'with_tool_correct': yes_ok,
                'raw_transition': trans,
            })
            if trans not in ('wrong_to_right', 'right_to_wrong'):
                audited[trans] += 1
        else:
            audited[trans] += 1
    conflict_qids = sorted({c['qid'] for c in conflicts})
    return {
        'raw_wrong_to_right': raw['wrong_to_right'],
        'raw_right_to_wrong': raw['right_to_wrong'],
        'raw_net_gain': raw['wrong_to_right'] - raw['right_to_wrong'],
        'same_final_judge_conflict_count': len(conflicts),
        'same_final_judge_conflict_qids': conflict_qids,
        'conflicts': conflicts,
        'audited_wrong_to_right': audited['wrong_to_right'],
        'audited_right_to_wrong': audited['right_to_wrong'],
        'audited_net_gain': audited['wrong_to_right'] - audited['right_to_wrong'],
        'audited_right_to_right': audited['right_to_right'],
        'audited_wrong_to_wrong': audited['wrong_to_wrong'],
    }


def write_report(log_dir, report, source_summary):
    json_path = os.path.join(log_dir, 'paired_judge_audit.json')
    md_path = os.path.join(log_dir, 'paired_judge_audit.md')
    payload = {'source_summary': source_summary, **report}
    json.dump(payload, open(json_path, 'w', encoding='utf-8'), ensure_ascii=False, indent=2)
    lines = [
        '# Paired Judge Audit',
        '',
        f"experiment: `{log_dir}`",
        '',
        '## Raw transitions',
        f"- wrong_to_right: {report['raw_wrong_to_right']}",
        f"- right_to_wrong: {report['raw_right_to_wrong']}",
        f"- net_gain: {report['raw_net_gain']}",
        '',
        '## Judge conflicts (same normalized final, different judge)',
        f"- count: {report['same_final_judge_conflict_count']}",
        f"- qids: {report['same_final_judge_conflict_qids']}",
        '',
        '## Audited transitions (conflicts excluded from WTR/RTW)',
        f"- wrong_to_right: {report['audited_wrong_to_right']}",
        f"- right_to_wrong: {report['audited_right_to_wrong']}",
        f"- net_gain: {report['audited_net_gain']}",
    ]
    with open(md_path, 'w', encoding='utf-8') as f:
        f.write('\n'.join(lines) + '\n')
    return json_path, md_path


def main():
    if len(sys.argv) < 2:
        print('usage: python audit_paired_judge.py <experiment_log_dir>')
        sys.exit(1)
    log_dir = sys.argv[1]
    if not os.path.isabs(log_dir):
        log_dir = os.path.join(BASE, log_dir)
    pairs, summary = _load_pairs(log_dir)
    report = audit_pairs(pairs)
    jp, mp = write_report(log_dir, report, summary)
    print(json.dumps({k: report[k] for k in report if k != 'conflicts'}, ensure_ascii=False, indent=2))
    print('written:', jp, mp)


if __name__ == '__main__':
    main()
