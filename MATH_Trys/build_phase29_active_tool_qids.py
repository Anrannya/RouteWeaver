# -*- coding: utf-8 -*-
"""生成 phase29 当前工具覆盖题列表（基于固定50题验证集）。"""
import json
import os
import subprocess
from collections import Counter

BASE = os.path.dirname(os.path.abspath(__file__))
VALIDATION = os.path.join(BASE, 'TmpRes/phase27_qids.json')
ASSIGNMENT = os.path.join(BASE, 'TmpRes/step2In_MATH_with_tool.json')
OUT = os.path.join(BASE, 'TmpRes/phase29_active_tool_qids.json')
OUT_DETAIL = os.path.join(BASE, 'TmpRes/phase29_active_tool_qids_detail.json')


def _git_head():
    try:
        return subprocess.check_output(
            ['git', 'rev-parse', 'HEAD'], cwd=os.path.dirname(BASE), stderr=subprocess.DEVNULL, text=True,
        ).strip()
    except Exception:
        return None


def main():
    qids = json.load(open(VALIDATION))
    data = json.load(open(ASSIGNMENT))
    active = []
    tool_type_counts = Counter()
    replace_n = assist_n = slot_n = 0
    per_q = {}

    for qid in qids:
        q = data[str(qid)]
        tools, modes = q.get('allo_tool', []), q.get('tool_mode', [])
        slots = []
        for i, (t, m) in enumerate(zip(tools, modes), start=1):
            if t != 'no_tool':
                slots.append({'step': i, 'subtask': q['steps'][i - 1], 'tool': t, 'mode': m})
                tool_type_counts[t] += 1
                slot_n += 1
                if m == 'replace':
                    replace_n += 1
                elif m == 'assist':
                    assist_n += 1
        if slots:
            active.append(qid)
            per_q[str(qid)] = slots

    assert len(active) == len(set(active))
    assert all(q in qids for q in active)

    json.dump(active, open(OUT, 'w', encoding='utf-8'), indent=2)
    detail = {
        'source_validation_qids': 'TmpRes/phase27_qids.json',
        'source_assignment': 'TmpRes/step2In_MATH_with_tool.json',
        'git_head': _git_head(),
        'active_tool_qids': active,
        'question_count': len(active),
        'tool_slot_count': slot_n,
        'replace_count': replace_n,
        'assist_count': assist_n,
        'tool_type_counts': dict(tool_type_counts),
        'per_question_slots': per_q,
    }
    json.dump(detail, open(OUT_DETAIL, 'w', encoding='utf-8'), ensure_ascii=False, indent=2)
    print(json.dumps({k: detail[k] for k in detail if k != 'per_question_slots'}, ensure_ascii=False, indent=2))


if __name__ == '__main__':
    main()
