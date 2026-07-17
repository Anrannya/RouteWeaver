# -*- coding: utf-8 -*-
"""Bulk-author eval-style v2 KB facts (5 per question, one per option).

Mimics csqa_v2_knowledge_data / question_grounded_kb.jsonl style:
* functional / causal / locational / purpose relations (no bare definitions)
* one concise standalone sentence per option A-E
* answerKey is never read

Writes/updates rest_kb_data batch modules and rebuilds the flat KB via build_rest_kb.

Run:
    cd CSQA_Trys
    python tools/csqa_tools/bulk_author_rest_kb_eval_style.py --start 520 --count 1000
"""

from __future__ import annotations

import argparse
import importlib.util
import json
import os
import re
import sys
from typing import Any, Dict, List, Sequence, Tuple

BASE_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
sys.path.insert(0, os.path.join(BASE_DIR, "tools", "csqa_tools"))

from csqa_kb_retriever import detect_question_type

DATA_PATH = os.path.join(BASE_DIR, "..", "Task_Datasets", "CSQA", "train_rand_split.jsonl")
STEP2IN_PATH = os.path.join(BASE_DIR, "TmpRes", "step2In_csqa_last.json")
TOOLS_DIR = os.path.join(BASE_DIR, "tools", "csqa_tools")

ALLOWED_DIMENSIONS = {
    "primary_function", "used_for", "capability", "typical_location", "cause",
    "effect", "has_prerequisite", "motivation", "property", "part_whole",
}

PLACE_HINTS = (
    "room", "house", "home", "store", "shop", "school", "office", "park", "city",
    "town", "country", "street", "field", "garden", "kitchen", "hospital", "hotel",
    "restaurant", "museum", "library", "station", "airport", "beach", "forest",
    "woods", "farm", "yard", "building", "mall", "market", "church", "court",
    "stadium", "theater", "garage", "basement", "attic", "closet", "desk", "table",
    "shelf", "drawer", "cabinet", "cupboard", "pantry", "ocean", "river", "lake",
    "mountain", "desert", "island", "world", "earth", "america", "europe", "africa",
    "asia", "canada", "mexico", "england", "france", "germany", "india", "china",
)

ACTION_VERBS = (
    "go", "find", "keep", "put", "store", "buy", "get", "take", "bring", "leave",
    "visit", "see", "watch", "play", "eat", "drink", "use", "meet", "live", "work",
    "study", "learn", "teach", "drive", "travel", "wait", "look", "search", "build",
)

WORD_RE = re.compile(r"[a-z0-9]+")


def load_questions(path: str) -> List[Dict[str, Any]]:
    rows: List[Dict[str, Any]] = []
    with open(path, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                rows.append(json.loads(line))
    return rows


def eval_ids() -> set:
    with open(STEP2IN_PATH, "r", encoding="utf-8") as f:
        step2in = json.load(f)
    return {int(k) for k in step2in.keys()}


def tokenize(text: str) -> List[str]:
    return WORD_RE.findall((text or "").lower())


def article_phrase(text: str) -> str:
    t = (text or "").strip()
    if not t:
        return "something"
    low = t.lower()
    if low.startswith(("a ", "an ", "the ")):
        return t
    return f"a {t}" if low[0] in "aeiou" else f"a {t}"


def title_phrase(text: str) -> str:
    t = (text or "").strip()
    if not t:
        return "Something"
    return t[0].upper() + t[1:]


def looks_like_place(text: str) -> bool:
    low = (text or "").lower()
    if any(h in low for h in PLACE_HINTS):
        return True
    if low.startswith(("the ", "a ", "an ")):
        return True
    return len(tokenize(low)) <= 3 and not low.endswith("ing")


def stem_action(stem: str) -> str:
    s = (stem or "").lower()
    m = re.search(r"\b(?:to|would|could|might|should|want(?:s|ed)? to)\s+([a-z][a-z\s]{2,30}?)(?:\?|\.|$)", s)
    if m:
        return m.group(1).strip()
    for v in ACTION_VERBS:
        if re.search(rf"\b{v}\b", s):
            return v
    if "where" in s:
        return "go there"
    if "what" in s:
        return "answer the question"
    if "why" in s:
        return "do that"
    return "do this"


def stem_constraint(stem: str) -> str | None:
    s = (stem or "").lower()
    if "not " in s or "n't " in s or "without" in s or "except" in s or "exclude" in s:
        return "but that does not fit the situation described"
    return None


def option_overlap(stem: str, option_text: str) -> float:
    s = set(tokenize(stem))
    o = set(tokenize(option_text))
    if not o:
        return 0.0
    return len(s & o) / len(o)


def pick_best_option(stem: str, choices: Sequence[Dict[str, str]], qtype: str) -> str:
    scores: Dict[str, float] = {}
    action = stem_action(stem)
    for c in choices:
        label = c["label"]
        text = c["text"]
        score = option_overlap(stem, text)
        low = text.lower()
        if qtype == "location" and looks_like_place(text):
            score += 1.5
        elif qtype != "location" and looks_like_place(text):
            score -= 0.3
        if qtype == "purpose" and any(v in low for v in ("use", "for", "help", "make")):
            score += 0.5
        if qtype == "cause_effect" and any(v in low for v in ("cause", "effect", "pain", "death", "feel")):
            score += 0.5
        if any(w in action for w in tokenize(text)):
            score += 0.8
        if len(text.split()) == 1:
            score += 0.2
        scores[label] = score
    return max(choices, key=lambda c: scores[c["label"]])["label"]


def dimension_for(qtype: str, option_text: str, supportive: bool) -> str:
    low = option_text.lower()
    if qtype == "location":
        return "typical_location" if looks_like_place(option_text) else "property"
    if qtype == "purpose":
        if supportive:
            return "primary_function" if any(v in low for v in ("use", "for")) else "motivation"
        return "property"
    if qtype == "cause_effect":
        return "effect" if supportive else "property"
    if any(v in low for v in ("need", "require", "must", "before")):
        return "has_prerequisite"
    if any(v in low for v in ("want", "try", "hope", "goal", "because")):
        return "motivation"
    if any(v in low for v in ("can", "able", "capable")):
        return "capability"
    if looks_like_place(option_text):
        return "typical_location"
    return "property"


def craft_fact(
    stem: str,
    qtype: str,
    option_text: str,
    supportive: bool,
    constraint: str | None,
) -> str:
    concept = option_text.strip()
    cap = title_phrase(concept)
    art = article_phrase(concept)
    action = stem_action(stem)

    if qtype == "location":
        if looks_like_place(concept):
            if supportive:
                fact = f"{cap} is a place where one might {action}."
            else:
                fact = f"{cap} is not typically the place where one would {action}."
        else:
            if supportive:
                fact = f"{cap} relates to the situation of {action}, though it is not itself a place."
            else:
                fact = f"{cap} is not a location; it does not answer a question about where to {action}."
        if constraint and not supportive:
            fact = fact.rstrip(".") + f", {constraint}."
        return fact

    if qtype == "purpose":
        if supportive:
            return f"{art.capitalize()} is used for or helps with {action}."
        return f"{cap} does not serve the purpose of {action}."

    if qtype == "cause_effect":
        if supportive:
            return f"{action.capitalize()} commonly leads to or involves {art}."
        return f"{cap} is not a typical result of {action}."

    # general
    if supportive:
        if looks_like_place(concept):
            return f"{cap} fits the context of {action} better than the other options."
        return f"{cap} is directly relevant to {action} in this kind of question."
    if looks_like_place(concept):
        return f"{cap} is a place or thing, not the kind of answer sought for {action}."
    return f"{cap} does not satisfy the condition implied by {action}."


def author_question(qid: int, entry: Dict[str, Any]) -> List[Tuple[str, str, str]]:
    stem = entry["question"]["stem"]
    choices = [{"label": c["label"], "text": c["text"]} for c in entry["question"]["choices"]]
    qtype = detect_question_type(stem)
    constraint = stem_constraint(stem)
    best = pick_best_option(stem, choices, qtype)

    facts: List[Tuple[str, str, str]] = []
    for c in choices:
        label = c["label"]
        text = c["text"]
        supportive = label == best
        dim = dimension_for(qtype, text, supportive)
        fact = craft_fact(stem, qtype, text, supportive, constraint if label != best else None)
        if len(fact) < 8:
            fact = f"{title_phrase(text)} is an option concept related to the question about {stem_action(stem)}."
        facts.append((label, dim, fact))
    return facts


def write_batch_module(start: int, end: int, knowledge: Dict[int, List[Tuple[str, str, str]]]) -> str:
    mod_name = f"rest_kb_data_{start}_{end}"
    path = os.path.join(TOOLS_DIR, f"{mod_name}.py")
    lines = [
        "# -*- coding: utf-8 -*-",
        f'"""Eval-style rest KB batch for qids {start}-{end} (5 facts per question)."""',
        "",
        f"KNOWLEDGE_REST_{start}_{end} = {{",
    ]
    for qid in range(start, end + 1):
        if qid not in knowledge:
            continue
        tuples = ", ".join(f'("{a}", "{b}", "{c.replace(chr(92), chr(92)+chr(92)).replace(chr(34), chr(92)+chr(34))}")' for a, b, c in knowledge[qid])
        lines.append(f"    {qid}: [{tuples}],")
    lines.append("}")
    lines.append("")
    with open(path, "w", encoding="utf-8") as f:
        f.write("\n".join(lines))
    return path


def merge_into_rest_kb_data(batch_paths: List[str]) -> None:
    rest_path = os.path.join(TOOLS_DIR, "rest_kb_data.py")
    with open(rest_path, "r", encoding="utf-8") as f:
        content = f.read()

    imports = []
    merge_keys = []
    for path in batch_paths:
        mod_name = os.path.splitext(os.path.basename(path))[0]
        dict_name = None
        with open(path, "r", encoding="utf-8") as f:
            for line in f:
                if line.startswith("KNOWLEDGE_REST_"):
                    dict_name = line.split("=")[0].strip()
                    break
        if not dict_name:
            continue
        imp = f"from {mod_name} import {dict_name}"
        if imp not in content:
            imports.append(imp)
        merge_keys.append(dict_name)

    if imports:
        anchor = "from rest_kb_data_320_519 import KNOWLEDGE_REST_320_519"
        if anchor in content:
            content = content.replace(anchor, anchor + "\n" + "\n".join(imports))
        else:
            content = content.replace(
                '"""',
                '"""\n' + "\n".join(imports),
                1,
            )

    if merge_keys and "**KNOWLEDGE_REST_320_519," in content:
        for key in merge_keys:
            marker = f"**{key},"
            if marker not in content:
                content = content.replace(
                    "**KNOWLEDGE_REST_320_519,",
                    f"**{key},\n    **KNOWLEDGE_REST_320_519,",
                )

    with open(rest_path, "w", encoding="utf-8") as f:
        f.write(content)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--start", type=int, default=520)
    parser.add_argument("--count", type=int, default=1000)
    parser.add_argument("--chunk", type=int, default=200, help="Questions per batch module file")
    parser.add_argument("--skip-build", action="store_true")
    args = parser.parse_args()

    end = args.start + args.count - 1
    questions = load_questions(os.path.abspath(DATA_PATH))
    excluded = eval_ids()
    if any(qid in excluded for qid in range(args.start, end + 1)):
        raise SystemExit("[ABORT] requested range overlaps eval ids")

    batch_paths: List[str] = []
    total_facts = 0
    for chunk_start in range(args.start, end + 1, args.chunk):
        chunk_end = min(chunk_start + args.chunk - 1, end)
        knowledge: Dict[int, List[Tuple[str, str, str]]] = {}
        for qid in range(chunk_start, chunk_end + 1):
            authored = author_question(qid, questions[qid])
            if len(authored) != 5:
                raise SystemExit(f"qid={qid}: expected 5 facts, got {len(authored)}")
            knowledge[qid] = authored
            total_facts += len(authored)
        batch_paths.append(write_batch_module(chunk_start, chunk_end, knowledge))
        print(f"written {batch_paths[-1]}  qids {chunk_start}-{chunk_end}  facts={sum(len(v) for v in knowledge.values())}")

    merge_into_rest_kb_data(batch_paths)

    if not args.skip_build:
        import build_rest_kb
        build_rest_kb.main()

    print(f"Done. {args.count} questions, {total_facts} facts authored (qids {args.start}-{end}).")


if __name__ == "__main__":
    main()
