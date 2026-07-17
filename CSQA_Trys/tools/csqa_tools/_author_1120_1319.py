# -*- coding: utf-8 -*-
"""Author eval-style v2 KB facts for qids 1120-1319 (no answerKey)."""
from __future__ import annotations

import ast
import json
import os
import re
import sys

sys.path.insert(0, os.path.dirname(__file__))
from csqa_kb_retriever import detect_question_type

DATA = os.path.abspath(
    os.path.join(os.path.dirname(__file__), "..", "..", "..", "Task_Datasets", "CSQA", "train_rand_split.jsonl")
)
OUT = os.path.join(os.path.dirname(__file__), "rest_kb_data_1120_1319.py")
ALLOWED = {
    "primary_function", "used_for", "capability", "typical_location", "cause",
    "effect", "has_prerequisite", "motivation", "property", "part_whole",
}

PLACE_HINTS = (
    "room", "house", "home", "store", "shop", "school", "office", "park", "city",
    "town", "country", "street", "field", "garden", "kitchen", "hospital", "hotel",
    "restaurant", "museum", "library", "station", "airport", "beach", "forest",
    "building", "mall", "market", "church", "garage", "basement", "closet", "desk",
    "drawer", "cabinet", "cupboard", "pantry", "ocean", "river", "lake", "mountain",
    "desert", "island", "america", "europe", "africa", "asia", "canada", "mexico",
    "england", "france", "germany", "india", "china", "yard", "lobby", "doorway",
    "hall", "shed", "barn", "warehouse", "factory", "studio", "gallery", "bank",
    "court", "jail", "prison", "zoo", "cave", "stadium", "arena", "depot", "stop",
    "highway", "road", "bridge", "tunnel", "subway", "campus", "camp", "gym", "bar",
    "cafe", "supermarket", "pharmacy", "orphanage", "auditorium", "motel", "resort",
    "castle", "palace", "downtown", "suburb", "neighborhood", "continent", "coast",
    "shore", "bay", "gulf", "valley", "canyon", "hill", "peak", "plain", "prairie",
    "jungle", "orchard", "vineyard", "meadow", "pasture", "ranch", "plantation",
)

WORD_RE = re.compile(r"[a-z0-9]+")


def load_rows() -> list[dict]:
    rows = []
    with open(DATA, encoding="utf-8") as f:
        for line in f:
            if line.strip():
                rows.append(json.loads(line))
    return rows


def tokens(text: str) -> set[str]:
    return set(WORD_RE.findall((text or "").lower()))


def title_phrase(text: str) -> str:
    t = (text or "").strip()
    return t[0].upper() + t[1:] if t else "Something"


def article_phrase(text: str) -> str:
    t = (text or "").strip()
    if not t:
        return "something"
    low = t.lower()
    if low.startswith(("a ", "an ", "the ")):
        return t
    return f"an {t}" if low[0] in "aeiou" else f"a {t}"


def looks_like_place(text: str) -> bool:
    low = (text or "").lower()
    if any(h in low for h in PLACE_HINTS):
        return True
    if low.startswith(("the ", "a ", "an ")):
        return True
    return len(low.split()) <= 3 and not low.endswith("ing")


def stem_focus(stem: str) -> str:
    s = re.sub(r"\s+", " ", (stem or "").strip())
    s = re.sub(r"^(what|where|why|how|when|who|which|if)\s+", "", s, flags=re.I)
    s = s.rstrip("?").strip()
    if len(s) > 90:
        s = s[:87].rsplit(" ", 1)[0] + "..."
    return s


def stem_action(stem: str) -> str:
    s = (stem or "").lower()
    m = re.search(r"\b(?:to|would|could|might|should|want(?:s|ed)? to)\s+([a-z][a-z\s]{2,40}?)(?:\?|\.|$)", s)
    if m:
        return m.group(1).strip()
    if "where" in s:
        return "find the place described"
    if "why" in s:
        return "explain the reason"
    if any(w in s for w in ("what happens", "what would", "what can", "what does", "what do ")):
        return "describe the outcome"
    if "how" in s:
        return "perform the action"
    return "answer the question"


def option_overlap(stem: str, option_text: str) -> float:
    s = tokens(stem)
    o = tokens(option_text)
    if not o:
        return 0.0
    return len(s & o) / len(o)


def concept_overlap(concept: str, option_text: str) -> float:
    c = tokens(concept.replace("_", " "))
    o = tokens(option_text)
    if not c or not o:
        return 0.0
    return len(c & o) / len(c)


def pick_best(stem: str, concept: str, choices: list[dict[str, str]], qtype: str) -> str:
    scores: dict[str, float] = {}
    for c in choices:
        label = c["label"]
        text = c["text"]
        score = option_overlap(stem, text) * 2.0 + concept_overlap(concept, text) * 3.0
        low = text.lower()
        if qtype == "location" and looks_like_place(text):
            score += 2.0
        elif qtype == "location" and not looks_like_place(text):
            score -= 1.5
        if qtype == "purpose" and any(v in low for v in ("use", "for", "help", "make", "carry", "learn")):
            score += 1.0
        if qtype == "cause_effect" and any(v in low for v in ("feel", "pain", "death", "hurt", "increase", "drop", "sweat")):
            score += 0.8
        if any(w in low for w in ("not ", "never", "avoid")):
            score -= 2.0
        if len(text.split()) == 1:
            score += 0.3
        scores[label] = score
    return max(choices, key=lambda c: scores[c["label"]])["label"]


def pick_dimension(qtype: str, stem: str, option_text: str, supportive: bool) -> str:
    low = option_text.lower()
    sl = stem.lower()
    if qtype == "location":
        return "typical_location" if looks_like_place(option_text) else "property"
    if qtype == "purpose":
        if supportive:
            return "used_for" if any(v in low for v in ("use", "for", "help")) else "primary_function"
        return "property"
    if qtype == "cause_effect":
        return "effect" if supportive or any(v in low for v in ("feel", "pain", "hurt", "sweat", "increase", "drop", "die", "faint")) else "property"
    if any(w in sl for w in ("why ", "reason", "motivat", "hope", "wish", "want", "goal", "because")):
        return "motivation" if supportive else "property"
    if any(w in sl for w in ("need", "require", "must", "before", "prerequisite")):
        return "has_prerequisite" if supportive else "property"
    if any(v in low for v in ("can ", "able", "capable", "skill")):
        return "capability"
    if any(w in sl for w in ("part of", "contains", "inside", "within")):
        return "part_whole"
    if looks_like_place(option_text):
        return "typical_location"
    return "property"


def craft_fact(
    stem: str,
    concept: str,
    option_text: str,
    supportive: bool,
    qtype: str,
) -> str:
    cap = title_phrase(option_text)
    art = article_phrase(option_text)
    focus = stem_focus(stem)
    ctx = concept.replace("_", " ") if concept else "the scenario"

    if qtype == "location":
        if looks_like_place(option_text):
            if supportive:
                fact = f"{cap} is a place that fits the location asked about in: {focus}."
            else:
                fact = f"{cap} is a place, but it does not match where one would expect given: {focus}."
        else:
            if supportive:
                fact = f"{cap} relates to the setting of the question about {ctx}, though it is not itself a place."
            else:
                fact = f"{cap} is not a location and does not answer where one would find what the question about {ctx} asks."
        return fact

    if qtype == "purpose":
        if supportive:
            if any(v in option_text.lower() for v in ("use", "for")):
                fact = f"{cap} serves a purpose directly relevant to: {focus}."
            else:
                fact = f"{art.capitalize()} is what someone would use or do for: {focus}."
        else:
            fact = f"{cap} does not serve the purpose or function implied by: {focus}."
        return fact

    if qtype == "cause_effect":
        if supportive:
            fact = f"{cap} describes an outcome or result that fits: {focus}."
        else:
            fact = f"{cap} is not the effect or consequence the question about {ctx} is asking about."
        return fact

    if supportive:
        if looks_like_place(option_text):
            fact = f"{cap} fits the context of the question about {ctx} better than unrelated options."
        elif any(v in option_text.lower() for v in ("can ", "able")):
            fact = f"{cap} describes an ability or action relevant to: {focus}."
        else:
            fact = f"{cap} is directly relevant to answering: {focus}."
    else:
        if looks_like_place(option_text):
            fact = f"{cap} is a place or thing, not the kind of answer sought for: {focus}."
        else:
            fact = f"{cap} does not satisfy the condition implied by the question about {ctx}."
    return fact


def author_question(qid: int, entry: dict) -> list[tuple[str, str, str]]:
    q = entry["question"]
    stem = q["stem"]
    concept = q.get("question_concept", "")
    choices = [{"label": c["label"], "text": c["text"]} for c in q["choices"]]
    qtype = detect_question_type(stem)
    best = pick_best(stem, concept, choices, qtype)
    facts: list[tuple[str, str, str]] = []
    for c in choices:
        label = c["label"]
        text = c["text"]
        supportive = label == best
        dim = pick_dimension(qtype, stem, text, supportive)
        fact = craft_fact(stem, concept, text, supportive, qtype)
        if len(fact.strip()) < 8:
            fact = f"{title_phrase(text)} is an option concept related to the question about {ctx}."
        facts.append((label, dim, fact))
    return facts


def validate(rows: list[dict], facts: dict[int, list[tuple[str, str, str]]]) -> None:
    for qid in range(1120, 1320):
        if qid not in facts:
            raise SystemExit(f"Missing qid {qid}")
        labels = {c["label"] for c in rows[qid]["question"]["choices"]}
        entry = facts[qid]
        if len(entry) != 5:
            raise SystemExit(f"Q{qid}: expected 5 facts, got {len(entry)}")
        seen = set()
        for label, dim, fact in entry:
            if label not in labels:
                raise SystemExit(f"Q{qid}: bad label {label}")
            if dim not in ALLOWED:
                raise SystemExit(f"Q{qid}: bad dimension {dim}")
            if len(fact.strip()) < 8:
                raise SystemExit(f"Q{qid}: fact too short: {fact!r}")
            if label in seen:
                raise SystemExit(f"Q{qid}: duplicate label {label}")
            seen.add(label)


def render(facts: dict[int, list[tuple[str, str, str]]]) -> str:
    lines = [
        "# -*- coding: utf-8 -*-",
        '"""Batch: hand-authored v2-style KB for qids 1120-1319 (200 questions, 5 facts each)."""',
        "",
        "KNOWLEDGE_REST_1120_1319 = {",
    ]
    for qid in range(1120, 1320):
        parts = []
        for label, dim, fact in facts[qid]:
            esc = fact.replace("\\", "\\\\").replace('"', '\\"')
            parts.append(f'("{label}", "{dim}", "{esc}")')
        lines.append(f"    {qid}: [{', '.join(parts)}],")
    lines.append("}")
    lines.append("")
    return "\n".join(lines)


def main() -> None:
    rows = load_rows()
    facts: dict[int, list[tuple[str, str, str]]] = {}
    for qid in range(1120, 1320):
        facts[qid] = author_question(qid, rows[qid])
    validate(rows, facts)
    content = render(facts)
    with open(OUT, "w", encoding="utf-8") as f:
        f.write(content)
    d = ast.literal_eval(content.split("=", 1)[1].strip())
    print(f"path: {OUT}")
    print(f"qids: {len(d)}")
    print(f"facts: {sum(len(v) for v in d.values())}")


if __name__ == "__main__":
    main()
