# -*- coding: utf-8 -*-
"""Train lightweight online validators from offline teacher labels.

Two logistic-regression heads (fast, interpretable):
  * direct head  : does a fact DIRECTLY answer the question? (per-fact)
  * option head  : does a fact support a GIVEN option? (per fact x option)

Shared feature extraction (`FeatureExtractor`, `direct_features`, `option_features`)
is reused by the online validator to guarantee train/inference parity. Importing this
module does NOT run training (guarded by __main__). Online inference needs only
sklearn + joblib (no torch / no LLM).

Run:
    cd CSQA_Trys && python tools/csqa_tools/train_csqa_light_validator.py
"""

from __future__ import annotations

import json
import os
import sys
from typing import Any, Dict, List, Tuple

import joblib
import numpy as np

BASE_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
sys.path.insert(0, os.path.join(BASE_DIR, "tools", "csqa_tools"))

from csqa_kb_retriever import (
    detect_question_type,
    dimension_multiplier,
    jaccard,
    phrase_match_score,
    tokenize,
)

# TF-IDF must be fitted on the SAME knowledge style that the online retriever
# now serves (csqa_kb_v2). Fitting on v1 here was the "old textbook for new exam"
# mismatch: v2 sentence vocabulary was scored with a v1 vocabulary.
KB_PATH = os.path.join(BASE_DIR, "knowledge_base", "csqa_kb_v2", "csqa_commonsense_kb_v2.jsonl")
VALIDATOR_DIR = os.path.join(BASE_DIR, "knowledge_base", "csqa_kb_v1", "validator")
TEACHER_LABELS = os.path.join(VALIDATOR_DIR, "teacher_labels.jsonl")
RANDOM_SEED = 42
WEAK_DIMENSIONS = {"category", "lexical_equivalence"}

DIRECT_FEATURE_NAMES = [
    "tfidf_q_fact",
    "tfidf_qopt_max",
    "tfidf_qopt_mean",
    "dim_type_match",
    "is_weak_dimension",
    "concept_opt_max",
    "jaccard_q_fact",
    "option_sim_spread",
]
OPTION_FEATURE_NAMES = [
    "tfidf_qopt_fact",
    "jaccard_opt_fact",
    "concept_opt_match",
    "specificity",
    "dim_type_match",
    "is_weak_dimension",
    "tfidf_q_fact",
    "option_sim_spread",
]


class FeatureExtractor:
    """Deterministic features built on a TF-IDF model fitted over KB facts."""

    def __init__(self, vectorizer):
        self.vectorizer = vectorizer
        self._vec_cache: Dict[str, Any] = {}

    @classmethod
    def fit(cls, kb_path: str = KB_PATH) -> "FeatureExtractor":
        from sklearn.feature_extraction.text import TfidfVectorizer

        corpus = []
        with open(kb_path, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if line:
                    corpus.append(json.loads(line).get("fact", ""))
        vectorizer = TfidfVectorizer(stop_words="english", min_df=2)
        vectorizer.fit(corpus)
        return cls(vectorizer)

    def _vec(self, text: str):
        """L2-normalized TF-IDF row vector, memoized per unique string."""
        key = text or ""
        cached = self._vec_cache.get(key)
        if cached is None:
            row = self.vectorizer.transform([key])
            norm = float(np.sqrt(row.multiply(row).sum()))
            cached = (row, norm)
            if len(self._vec_cache) < 50000:
                self._vec_cache[key] = cached
        return cached

    def _cos(self, text_a: str, text_b: str) -> float:
        row_a, norm_a = self._vec(text_a)
        row_b, norm_b = self._vec(text_b)
        if norm_a == 0 or norm_b == 0:
            return 0.0
        return float(row_a.multiply(row_b).sum() / (norm_a * norm_b))

    def _option_sims(self, question: str, choices: List[Dict[str, str]], fact_text: str) -> List[float]:
        return [self._cos(f"{question} {c['text']}", fact_text) for c in choices]

    def direct_features(
        self, question: str, choices: List[Dict[str, str]], fact: Dict[str, Any]
    ) -> List[float]:
        fact_text = fact.get("fact", "")
        qtype = detect_question_type(question)
        opt_sims = self._option_sims(question, choices, fact_text)
        concept_matches = [phrase_match_score(fact.get("concept", ""), c["text"]) for c in choices]
        return [
            self._cos(question, fact_text),
            max(opt_sims) if opt_sims else 0.0,
            sum(opt_sims) / len(opt_sims) if opt_sims else 0.0,
            min(1.0, dimension_multiplier(fact.get("dimension", ""), qtype) / 1.5),
            1.0 if fact.get("dimension", "") in WEAK_DIMENSIONS else 0.0,
            max(concept_matches) if concept_matches else 0.0,
            jaccard(tokenize(question), tokenize(fact_text)),
            (max(opt_sims) - min(opt_sims)) if opt_sims else 0.0,
        ]

    def option_features(
        self,
        question: str,
        choices: List[Dict[str, str]],
        fact: Dict[str, Any],
        option_text: str,
    ) -> List[float]:
        fact_text = fact.get("fact", "")
        qtype = detect_question_type(question)
        opt_sims = self._option_sims(question, choices, fact_text)
        this_match = max(
            phrase_match_score(fact.get("concept", ""), option_text),
            jaccard(tokenize(option_text), tokenize(fact_text)),
        )
        all_matches = [
            max(
                phrase_match_score(fact.get("concept", ""), c["text"]),
                jaccard(tokenize(c["text"]), tokenize(fact_text)),
            )
            for c in choices
        ]
        mean_other = (sum(all_matches) - this_match) / max(len(all_matches) - 1, 1)
        return [
            self._cos(f"{question} {option_text}", fact_text),
            jaccard(tokenize(option_text), tokenize(fact_text)),
            phrase_match_score(fact.get("concept", ""), option_text),
            max(0.0, min(1.0, this_match - mean_other + 0.5)),
            min(1.0, dimension_multiplier(fact.get("dimension", ""), qtype) / 1.5),
            1.0 if fact.get("dimension", "") in WEAK_DIMENSIONS else 0.0,
            self._cos(question, fact_text),
            (max(opt_sims) - min(opt_sims)) if opt_sims else 0.0,
        ]


def load_teacher_records(path: str) -> List[Dict[str, Any]]:
    if not os.path.exists(path):
        raise FileNotFoundError(
            f"Teacher labels not found: {path}\n"
            "Run build_csqa_teacher_labels.py first."
        )
    records = []
    with open(path, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                records.append(json.loads(line))
    return records


def build_dataset(
    records: List[Dict[str, Any]], fx: FeatureExtractor
) -> Tuple[np.ndarray, np.ndarray, np.ndarray, np.ndarray, List[int], List[int]]:
    xd, yd, qd = [], [], []
    xo, yo, qo = [], [], []
    fact_by_id = {}
    for rec in records:
        for cand in rec.get("candidates", []):
            fact_by_id[cand["fact_id"]] = cand

    for rec in records:
        question = rec["question"]
        choices = rec["options"]
        for label in rec.get("labels", []):
            fact = fact_by_id.get(label["fact_id"])
            if not fact:
                continue
            is_direct = 1 if label["question_relevance"] == "direct" else 0
            xd.append(fx.direct_features(question, choices, fact))
            yd.append(is_direct)
            qd.append(rec["question_id"])

            positive_option = (
                label["supported_option"]
                if (label["question_relevance"] == "direct" and label["unique_support"])
                else None
            )
            for choice in choices:
                xo.append(fx.option_features(question, choices, fact, choice["text"]))
                yo.append(1 if choice["label"] == positive_option else 0)
                qo.append(rec["question_id"])

    return (
        np.array(xd, dtype=float),
        np.array(yd, dtype=int),
        np.array(xo, dtype=float),
        np.array(yo, dtype=int),
        qd,
        qo,
    )


def train_head(x: np.ndarray, y: np.ndarray):
    from sklearn.linear_model import LogisticRegression
    from sklearn.pipeline import make_pipeline
    from sklearn.preprocessing import StandardScaler

    model = make_pipeline(
        StandardScaler(),
        LogisticRegression(max_iter=1000, class_weight="balanced", random_state=RANDOM_SEED),
    )
    model.fit(x, y)
    return model


def agreement_metrics(
    records: List[Dict[str, Any]],
    fx: FeatureExtractor,
    direct_model,
    option_model,
    test_qids: set,
) -> Dict[str, Any]:
    fact_by_id = {c["fact_id"]: c for r in records for c in r.get("candidates", [])}
    direct_hit = direct_total = 0
    option_hit = option_total = 0
    for rec in records:
        if rec["question_id"] not in test_qids:
            continue
        question, choices = rec["question"], rec["options"]
        for label in rec.get("labels", []):
            fact = fact_by_id.get(label["fact_id"])
            if not fact:
                continue
            pred_direct = int(
                direct_model.predict([fx.direct_features(question, choices, fact)])[0]
            )
            direct_total += 1
            direct_hit += int(pred_direct == (1 if label["question_relevance"] == "direct" else 0))

            if label["question_relevance"] == "direct" and label["unique_support"]:
                probs = [
                    option_model.predict_proba([fx.option_features(question, choices, fact, c["text"])])[0][1]
                    for c in choices
                ]
                pred_opt = choices[int(np.argmax(probs))]["label"]
                option_total += 1
                option_hit += int(pred_opt == label["supported_option"])
    return {
        "direct_agreement": round(direct_hit / direct_total, 4) if direct_total else None,
        "option_agreement": round(option_hit / option_total, 4) if option_total else None,
        "teacher_student_agreement": round(direct_hit / direct_total, 4) if direct_total else None,
        "direct_eval_count": direct_total,
        "option_eval_count": option_total,
    }


def main() -> None:
    os.makedirs(VALIDATOR_DIR, exist_ok=True)
    records = load_teacher_records(TEACHER_LABELS)

    fx = FeatureExtractor.fit()
    xd, yd, xo, yo, qd, qo = build_dataset(records, fx)
    if len(xd) == 0:
        raise RuntimeError("No training rows built from teacher labels.")

    rng = np.random.RandomState(RANDOM_SEED)
    all_qids = sorted({r["question_id"] for r in records})
    rng.shuffle(all_qids)
    split = max(1, int(len(all_qids) * 0.2))
    test_qids = set(all_qids[:split])

    train_d = np.array([q not in test_qids for q in qd])
    train_o = np.array([q not in test_qids for q in qo])

    direct_model = train_head(xd[train_d] if train_d.any() else xd, yd[train_d] if train_d.any() else yd)
    option_model = train_head(xo[train_o] if train_o.any() else xo, yo[train_o] if train_o.any() else yo)

    metrics = agreement_metrics(records, fx, direct_model, option_model, test_qids or set(all_qids))

    joblib.dump(fx.vectorizer, os.path.join(VALIDATOR_DIR, "tfidf.joblib"))
    joblib.dump(direct_model, os.path.join(VALIDATOR_DIR, "direct_model.joblib"))
    joblib.dump(option_model, os.path.join(VALIDATOR_DIR, "option_model.joblib"))
    meta = {
        "random_seed": RANDOM_SEED,
        "question_count": len(all_qids),
        "direct_rows": int(len(xd)),
        "direct_positive": int(yd.sum()),
        "option_rows": int(len(xo)),
        "option_positive": int(yo.sum()),
        "test_question_count": len(test_qids),
        "direct_feature_names": DIRECT_FEATURE_NAMES,
        "option_feature_names": OPTION_FEATURE_NAMES,
        **metrics,
    }
    with open(os.path.join(VALIDATOR_DIR, "metrics.json"), "w", encoding="utf-8") as f:
        json.dump(meta, f, ensure_ascii=False, indent=2)

    print("Saved validator models ->", VALIDATOR_DIR)
    print(json.dumps(meta, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
