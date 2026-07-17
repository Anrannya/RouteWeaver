# -*- coding: utf-8 -*-
"""Deterministic offline candidate retrieval for CSQA commonsense KB."""

from __future__ import annotations

import json
import math
import os
import re
from collections import defaultdict
from typing import Any, Dict, List, Optional, Sequence

DEFAULT_KB_PATH = os.path.join(
    os.path.dirname(os.path.abspath(__file__)),
    "..",
    "..",
    "knowledge_base",
    "csqa_kb_v2",
    "csqa_commonsense_kb_v2.jsonl",
)

MAX_CANDIDATES = 10
MAX_PER_OPTION = 4
WORD_RE = re.compile(r"[a-z0-9]+")

# Question-type -> preferred dimensions (multiplier applied after base score).
DIMENSION_PRIORITIES = {
    "purpose": {"primary_function": 1.5, "capability": 1.3},
    "location": {"typical_location": 1.5, "category": 1.2},
    "cause_effect": {"cause": 1.5, "effect": 1.5},
}

PURPOSE_PATTERNS = (
    r"\bused for\b",
    r"\buse(d|s)?\b",
    r"\bpurpose\b",
    r"\bfunction\b",
    r"\bwhat does\b",
    r"\bwhat do\b",
    r"\bwhat can\b",
    r"\bwhat would you use\b",
)
LOCATION_PATTERNS = (
    r"\bwhere\b",
    r"\bplace\b",
    r"\blocated\b",
    r"\bgo to\b",
    r"\bmight he go\b",
    r"\bwould you find\b",
    r"\bwould you go\b",
)
CAUSE_EFFECT_PATTERNS = (
    r"\bwhy\b",
    r"\bcause\b",
    r"\bbecause\b",
    r"\bresult\b",
    r"\beffect\b",
    r"\blead to\b",
    r"\bhappen\b",
    r"\bwhat sort of\b",
    r"\bwhat kind of\b",
)


def tokenize(text: str) -> List[str]:
    return WORD_RE.findall((text or "").lower())


def normalize_token(token: str) -> str:
    if len(token) > 3 and token.endswith("ies"):
        return token[:-3] + "y"
    if len(token) > 3 and token.endswith("es") and not token.endswith("ses"):
        return token[:-2]
    if len(token) > 2 and token.endswith("s") and not token.endswith("ss"):
        return token[:-1]
    return token


def normalize_phrase(text: str) -> str:
    text = (text or "").lower().strip()
    text = re.sub(r"\([^)]*\)", " ", text)
    text = re.sub(r"[^a-z0-9\s]", " ", text)
    tokens = [normalize_token(t) for t in text.split() if t]
    return " ".join(tokens)


def jaccard(a: Sequence[str], b: Sequence[str]) -> float:
    sa, sb = set(a), set(b)
    if not sa or not sb:
        return 0.0
    return len(sa & sb) / len(sa | sb)


def phrase_match_score(a: str, b: str) -> float:
    na, nb = normalize_phrase(a), normalize_phrase(b)
    if not na or not nb:
        return 0.0
    if na == nb:
        return 1.0
    if na in nb or nb in na:
        return 0.9
    ta, tb = na.split(), nb.split()
    if ta and tb and (ta[-1] == tb[-1] or ta[0] == tb[0]):
        return 0.75
    return jaccard(ta, tb)


def detect_question_type(question: str) -> str:
    q = (question or "").lower()
    if any(re.search(p, q) for p in LOCATION_PATTERNS):
        return "location"
    if any(re.search(p, q) for p in CAUSE_EFFECT_PATTERNS):
        return "cause_effect"
    if any(re.search(p, q) for p in PURPOSE_PATTERNS):
        return "purpose"
    return "general"


def dimension_multiplier(dimension: str, question_type: str) -> float:
    if question_type == "general":
        return 1.0
    return DIMENSION_PRIORITIES.get(question_type, {}).get(dimension, 1.0)


class SimpleBM25:
    """Lightweight Okapi BM25 without external dependencies."""

    def __init__(self, corpus: List[List[str]], k1: float = 1.5, b: float = 0.75):
        self.k1 = k1
        self.b = b
        self.corpus = corpus
        self.doc_len = [len(doc) for doc in corpus]
        self.avgdl = sum(self.doc_len) / max(len(corpus), 1)
        self.df: Dict[str, int] = defaultdict(int)
        for doc in corpus:
            for term in set(doc):
                self.df[term] += 1
        self.n_docs = len(corpus)

    def score_document(self, query: List[str], doc_idx: int) -> float:
        doc = self.corpus[doc_idx]
        if not doc:
            return 0.0
        tf: Dict[str, int] = defaultdict(int)
        for term in doc:
            tf[term] += 1
        dl = self.doc_len[doc_idx]
        score = 0.0
        for term in query:
            if term not in tf:
                continue
            idf = math.log(1 + (self.n_docs - self.df[term] + 0.5) / (self.df[term] + 0.5))
            freq = tf[term]
            denom = freq + self.k1 * (1 - self.b + self.b * dl / max(self.avgdl, 1.0))
            score += idf * (freq * (self.k1 + 1)) / max(denom, 1e-9)
        return score

    def score_all(self, query_text: str) -> List[float]:
        query = tokenize(query_text)
        if not query:
            return [0.0] * len(self.corpus)
        raw = [self.score_document(query, i) for i in range(len(self.corpus))]
        max_raw = max(raw) if raw else 0.0
        if max_raw <= 0:
            return [0.0] * len(raw)
        return [v / max_raw for v in raw]


class CSQAKBRetriever:
    """Retrieve up to 10 discriminative KB facts for one CSQA question."""

    def __init__(self, kb_path: Optional[str] = None):
        self.kb_path = os.path.abspath(kb_path or DEFAULT_KB_PATH)
        self.facts: List[Dict[str, Any]] = []
        self.concept_index: Dict[str, List[int]] = defaultdict(list)
        self.concept_token_index: Dict[str, set] = defaultdict(set)
        self.bm25: Optional[SimpleBM25] = None
        self._load_kb()

    def _load_kb(self) -> None:
        with open(self.kb_path, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                fact = json.loads(line)
                idx = len(self.facts)
                self.facts.append(fact)
                norm_concept = normalize_phrase(fact.get("concept", ""))
                if norm_concept:
                    self.concept_index[norm_concept].append(idx)
                    for token in norm_concept.split():
                        self.concept_token_index[token].add(norm_concept)
        corpus = [tokenize(item.get("fact", "")) for item in self.facts]
        self.bm25 = SimpleBM25(corpus)

    def retrieve(self, question: str, choices: List[Dict[str, str]]) -> List[Dict[str, Any]]:
        """Return ranked candidate facts. Uses question + options only."""
        if not self.facts:
            return []

        question_type = detect_question_type(question)
        option_items = [(c["label"], c["text"]) for c in choices]
        query_text = question + " " + " ".join(text for _, text in option_items)
        bm25_scores = self.bm25.score_all(query_text) if self.bm25 else []

        scored: Dict[str, Dict[str, Any]] = {}

        def add_candidate(
            fact_idx: int,
            base_score: float,
            source: str,
            anchor_option: Optional[str] = None,
        ) -> None:
            fact = self.facts[fact_idx]
            fact_id = fact["fact_id"]
            bm25_part = bm25_scores[fact_idx] if bm25_scores else 0.0
            combined = max(base_score, 0.45 * base_score + 0.55 * bm25_part)
            dim_boost = dimension_multiplier(fact.get("dimension", ""), question_type)
            score = combined * dim_boost
            prev = scored.get(fact_id)
            if prev is None:
                scored[fact_id] = {
                    "fact_id": fact_id,
                    "concept": fact.get("concept", ""),
                    "dimension": fact.get("dimension", ""),
                    "fact": fact.get("fact", ""),
                    "retrieval_score": 0.0,
                    "_raw_score": score,
                    "_source": source,
                    "_fact_idx": fact_idx,
                    "_anchor": anchor_option,
                }
            else:
                if score > prev["_raw_score"]:
                    prev["_raw_score"] = score
                    prev["_source"] = source
                # Keep the strongest available anchor (an explicit option beats None).
                if anchor_option is not None:
                    prev["_anchor"] = anchor_option

        # Stage 1: exact concept-option match (anchored to that option).
        for option_label, option_text in option_items:
            norm_option = normalize_phrase(option_text)
            for idx in self.concept_index.get(norm_option, []):
                add_candidate(idx, 1.0, "exact_concept", anchor_option=option_label)

        # Stage 2: normalized / inflection match on token-overlapping concepts only.
        for option_label, option_text in option_items:
            norm_option = normalize_phrase(option_text)
            option_tokens = [t for t in norm_option.split() if len(t) > 2]
            candidate_concepts = set()
            for token in option_tokens:
                candidate_concepts.update(self.concept_token_index.get(token, set()))
            if not candidate_concepts and norm_option:
                candidate_concepts.add(norm_option)
            for concept in candidate_concepts:
                if phrase_match_score(norm_option, concept) >= 0.75:
                    for idx in self.concept_index.get(concept, []):
                        add_candidate(idx, 0.85, "normalized_concept", anchor_option=option_label)

        # Stage 3 (option-anchored re-ranking only): BM25 may *boost* a fact that is
        # already anchored to an option, but it can NOT introduce brand-new facts.
        # This removes cross-question noise (facts whose concept matches no option)
        # without relying on any per-question id.
        bm25_seen = {item["_fact_idx"] for item in scored.values()}
        for idx in bm25_seen:
            bm25_score = bm25_scores[idx] if bm25_scores else 0.0
            if bm25_score >= 0.15:
                anchor = scored[self.facts[idx]["fact_id"]].get("_anchor")
                add_candidate(idx, 0.35 + 0.65 * bm25_score, "bm25_boost", anchor_option=anchor)

        # Keep only option-anchored candidates. Fall back to raw BM25 only when no
        # fact anchors to any option (avoids empty result on odd questions).
        anchored = {fid: item for fid, item in scored.items() if item.get("_anchor")}
        if anchored:
            scored = anchored
        else:
            for idx, bm25_score in enumerate(bm25_scores):
                if bm25_score >= 0.25:
                    add_candidate(idx, 0.35 + 0.65 * bm25_score, "bm25_fallback")

        if not scored:
            return []

        deduped = self._deduplicate_facts(list(scored.values()))
        ranked = sorted(deduped, key=lambda x: x["_raw_score"], reverse=True)
        selected = self._select_diverse(ranked, option_items)
        max_raw = max(item["_raw_score"] for item in selected) or 1.0
        for item in selected:
            item["retrieval_score"] = round(item["_raw_score"] / max_raw, 4)
            item.pop("_raw_score", None)
            item.pop("_source", None)
            item.pop("_fact_idx", None)
            item.pop("_anchor", None)
        return selected

    def _deduplicate_facts(self, items: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        by_id: Dict[str, Dict[str, Any]] = {}
        normalized_facts: List[tuple] = []
        for item in items:
            fact_id = item["fact_id"]
            if fact_id not in by_id or item["_raw_score"] > by_id[fact_id]["_raw_score"]:
                by_id[fact_id] = item
        unique = list(by_id.values())
        kept: List[Dict[str, Any]] = []
        for item in sorted(unique, key=lambda x: x["_raw_score"], reverse=True):
            norm_fact = normalize_phrase(item["fact"])
            duplicate = False
            for prev_norm, prev_score in normalized_facts:
                if norm_fact == prev_norm or jaccard(norm_fact.split(), prev_norm.split()) >= 0.92:
                    duplicate = True
                    break
            if not duplicate:
                kept.append(item)
                normalized_facts.append((norm_fact, item["_raw_score"]))
        return kept

    def _best_option_for_fact(self, fact: Dict[str, Any], option_items: List[tuple]) -> str:
        best_label = option_items[0][0]
        best_score = -1.0
        for label, text in option_items:
            score = max(
                phrase_match_score(fact.get("concept", ""), text),
                jaccard(tokenize(text), tokenize(fact.get("fact", ""))),
            )
            if score > best_score:
                best_score = score
                best_label = label
        return best_label

    def _select_diverse(self, ranked: List[Dict[str, Any]], option_items: List[tuple]) -> List[Dict[str, Any]]:
        per_option: Dict[str, int] = defaultdict(int)
        selected: List[Dict[str, Any]] = []
        for item in ranked:
            if len(selected) >= MAX_CANDIDATES:
                break
            option_label = item.get("_anchor") or self._best_option_for_fact(item, option_items)
            if per_option[option_label] >= MAX_PER_OPTION and len(selected) >= 3:
                continue
            selected.append(item)
            per_option[option_label] += 1
        if not selected:
            return ranked[:MAX_CANDIDATES]
        if len(selected) < MAX_CANDIDATES:
            seen = {x["fact_id"] for x in selected}
            for item in ranked:
                if len(selected) >= MAX_CANDIDATES:
                    break
                if item["fact_id"] not in seen:
                    selected.append(item)
                    seen.add(item["fact_id"])
        return selected[:MAX_CANDIDATES]
