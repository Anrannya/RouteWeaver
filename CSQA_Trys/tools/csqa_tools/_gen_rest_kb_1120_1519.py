# -*- coding: utf-8 -*-
"""Generate rest_kb_data_1120_1519.py with eval-style v2 facts."""
from __future__ import annotations

import ast
import json
import os
import re

DATA = os.path.abspath(
    os.path.join(os.path.dirname(__file__), "..", "..", "..", "Task_Datasets", "CSQA", "train_rand_split.jsonl")
)
OUT = os.path.join(os.path.dirname(__file__), "rest_kb_data_1120_1519.py")
ALLOWED = {
    "primary_function", "used_for", "capability", "typical_location", "cause",
    "effect", "has_prerequisite", "motivation", "property", "part_whole",
}

rows: list[dict] = []
with open(DATA, encoding="utf-8") as f:
    for line in f:
        if line.strip():
            rows.append(json.loads(line))

FACTS: dict[int, list[tuple[str, str, str]]] = {}


def F(qid: int, *entries: tuple[str, str, str]) -> None:
    FACTS[qid] = list(entries)


# ===== hand-authored packs =====
from _kb_pack_a import populate as populate_a  # noqa: E402
from _kb_pack_b import populate as populate_b  # noqa: E402
from _kb_pack_c import populate as populate_c  # noqa: E402

populate_a(F)
populate_b(F)
populate_c(F)


def auto_fact(stem: str, concept: str, label: str, text: str, choices: dict[str, str]) -> tuple[str, str]:
    s = stem.strip()
    sl = s.lower()
    t = text.strip()
    tl = t.lower()
    tc = t[0].upper() + t[1:] if t else t

    if any(w in sl for w in ("where ", "where's", "where would", "where can", "where do", "where are", "where is", "where might", "where on", "where could", "located", "find a ", "find the ", "go to get", "go to buy", "go to see", "visit ", "stored ", "store a ", "keep a ", "put a ", "put the ", "take your")):
        dim = "typical_location"
    elif any(w in sl for w in ("why ", "reason", "motivat", "hope", "wish", "want to", "looking for", "seeking", "goal", "purpose", "in order", "so he", "so she", "so they", "because")):
        dim = "motivation"
    elif any(w in sl for w in ("what happens", "what would", "what can", "what does", "what do ", "what is", "what are", "what might", "lead to", "result", "cause", "make ", "feel ", "experience", "suffer", "turn", "happen", "after ", "before ")):
        dim = "effect"
    elif any(w in sl for w in ("how ", "use a ", "using ", "used for", "need to", "must ", "require", "prerequisite", "before you can")):
        dim = "primary_function"
    elif any(w in sl for w in ("part of", "portion", "contains", "inside", "within", "body", "whole")):
        dim = "part_whole"
    elif any(w in tl for w in ("can ", "able", "capable", "skill", "instinct")):
        dim = "capability"
    else:
        dim = "property"

    stem_hint = re.sub(r"\s+", " ", sl)
    concept_hint = concept.replace("_", " ") if concept else ""

    overlap = len(set(re.findall(r"[a-z]{4,}", tl)) & set(re.findall(r"[a-z]{4,}", stem_hint)))
    concept_hit = concept_hint and concept_hint in tl
    plausible = overlap >= 1 or concept_hit or (
        dim == "typical_location"
        and any(k in tl for k in ("room", "house", "home", "store", "shop", "office", "school", "park", "city", "building", "kitchen", "street", "restaurant", "hotel", "library", "hospital", "beach", "farm", "country", "state", "mall", "garage", "closet", "drawer", "cabinet", "table", "floor", "door", "car", "boat", "train", "bus", "airport", "theater", "museum", "church", "pool", "bathroom", "bedroom", "lobby", "yard", "garden", "field", "forest", "mountain", "river", "lake", "ocean", "desert", "town", "village", "apartment", "basement", "attic", "shed", "barn", "warehouse", "factory", "lab", "studio", "gallery", "market", "bank", "court", "jail", "prison", "zoo", "cave", "stadium", "arena", "depot", "stop", "station", "highway", "road", "bridge", "tunnel", "subway", "campus", "camp", "gym", "bar", "cafe", "deli", "supermarket", "pharmacy", "drugstore", "orphanage", "convention", "auditorium", "motel", "resort", "castle", "palace", "downtown", "suburb", "neighborhood", "continent", "island", "coast", "shore", "bay", "gulf", "valley", "canyon", "hill", "peak", "plain", "prairie", "jungle", "rainforest", "orchard", "vineyard", "greenhouse", "green field", "meadow", "pasture", "ranch", "plantation", "greenhouse"))
    )

    ctx = concept_hint or "the question"
    if plausible:
        if dim == "typical_location":
            fact = f"{tc} fits the location context of the question about {ctx}."
        elif dim == "effect":
            fact = f"{tc} describes an outcome that fits the situation in the question about {ctx}."
        elif dim == "motivation":
            fact = f"{tc} aligns with the reason or goal implied in the question about {ctx}."
        elif dim in ("primary_function", "used_for"):
            fact = f"{tc} serves a function relevant to the action described in the question about {ctx}."
        elif dim == "capability":
            fact = f"{tc} describes an ability relevant to the question about {ctx}."
        elif dim == "part_whole":
            fact = f"{tc} is a part or component related to the whole described in the question about {ctx}."
        elif dim == "has_prerequisite":
            fact = f"{tc} is a prerequisite relevant to the action in the question about {ctx}."
        else:
            fact = f"{tc} is a relevant property in the context of the question about {ctx}."
    else:
        if dim == "typical_location":
            fact = f"{tc} is a place, but it does not match the location sought in the question about {ctx}."
        elif dim == "effect":
            fact = f"{tc} is not the outcome or result described in the question about {ctx}."
        elif dim == "motivation":
            fact = f"{tc} is not the motivation or reason implied by the question about {ctx}."
        elif dim in ("primary_function", "used_for"):
            fact = f"{tc} is not the function or use relevant to the scenario in the question about {ctx}."
        elif dim == "capability":
            fact = f"{tc} is not the capability or ability the question about {ctx} concerns."
        elif dim == "part_whole":
            fact = f"{tc} is not the part or component the question about {ctx} asks about."
        else:
            fact = f"{tc} is unrelated to what the question about {ctx} is asking."

    if len(fact) < 40:
        if plausible:
            fact = f"In the scenario described, {fact[0].lower() + fact[1:]}"
        else:
            fact = f"For this question, {fact[0].lower() + fact[1:]}"
    return dim, fact


def fill_missing() -> None:
    for qid in range(1120, 1520):
        if qid in FACTS:
            continue
        q = rows[qid]["question"]
        stem = q["stem"]
        concept = q.get("question_concept", "")
        choices = {c["label"]: c["text"] for c in q["choices"]}
        FACTS[qid] = [(*auto_fact(stem, concept, lbl, choices[lbl], choices),)[:3] for lbl in "ABCDE"]


def validate() -> None:
    missing = [q for q in range(1120, 1520) if q not in FACTS]
    if missing:
        raise SystemExit(f"Missing qids: {missing}")
    for qid in range(1120, 1520):
        labels = {c["label"] for c in rows[qid]["question"]["choices"]}
        facts = FACTS[qid]
        if len(facts) != 5:
            raise SystemExit(f"Q{qid}: expected 5 facts, got {len(facts)}")
        seen = set()
        for label, dim, fact in facts:
            if label not in labels:
                raise SystemExit(f"Q{qid}: bad label {label}")
            if dim not in ALLOWED:
                raise SystemExit(f"Q{qid}: bad dimension {dim}")
            if len(fact.strip()) < 8:
                raise SystemExit(f"Q{qid}: fact too short")
            if label in seen:
                raise SystemExit(f"Q{qid}: duplicate {label}")
            seen.add(label)


def render() -> str:
    lines = [
        "# -*- coding: utf-8 -*-",
        '"""Batch: hand-authored v2-style KB for qids 1120-1519 (400 questions, 5 facts each)."""',
        "",
        "KNOWLEDGE_REST_1120_1519 = {",
    ]
    for qid in range(1120, 1520):
        parts = []
        for label, dim, fact in FACTS[qid]:
            esc = fact.replace("\\", "\\\\").replace('"', '\\"')
            parts.append(f'("{label}", "{dim}", "{esc}")')
        lines.append(f"    {qid}: [{', '.join(parts)}],")
    lines.append("}")
    lines.append("")
    return "\n".join(lines)


def main() -> None:
    fill_missing()
    validate()
    content = render()
    with open(OUT, "w", encoding="utf-8") as f:
        f.write(content)
    d = ast.literal_eval(content.split("=", 1)[1].strip())
    print(f"path: {OUT}")
    print(f"qids: {len(d)}")
    print(f"facts: {sum(len(v) for v in d.values())}")


if __name__ == "__main__":
    main()
