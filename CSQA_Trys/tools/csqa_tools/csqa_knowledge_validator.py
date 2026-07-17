# -*- coding: utf-8 -*-
"""Online lightweight CSQA knowledge validator (no LLM, no gold answer).

V1 flow per question:
    candidates
    -> direct head: keep facts that DIRECTLY answer the question
    -> option head: score the 5 options for each kept fact
    -> a fact "supports" its top option only if it clearly leads (top1 + margin)
    -> all supporting facts must agree on ONE option, else abstain
    -> accept with <=2 deduped supporting facts

Loads only sklearn/joblib models trained by train_csqa_light_validator.py.
Concept==option exact match is just one weak feature inside the learned models,
so it can no longer single-handedly accept a fact.
"""

from __future__ import annotations

import os
import re
import sys
from typing import Any, Dict, List, Optional

import joblib

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from train_csqa_light_validator import VALIDATOR_DIR, FeatureExtractor

# Decision thresholds (constants, reported in the audit).
DIRECT_THRESHOLD = 0.5
OPTION_TOP1_THRESHOLD = 0.5
OPTION_MARGIN_THRESHOLD = 0.15
MAX_SUPPORTING_FACTS = 2

# Backward-compatible aliases imported by the audit report.
TOP1_THRESHOLD = OPTION_TOP1_THRESHOLD
MARGIN_THRESHOLD = OPTION_MARGIN_THRESHOLD

# Negation / exclusion cues. A fact mentioning option X but containing one of
# these is RULING OUT X ("a desert is where one goes to AVOID crowds"), not
# supporting it. Such facts are treated as exclusions instead of positive support.
_EXCLUSION_PHRASES = (
    "rather than",
    "instead of",
    "but the question excludes",
    "excludes it",
    "exclude it",
    "not a ",
    "not the ",
    "not where",
    "not used",
    "not reliably",
    "is not",
    "are not",
    "does not",
    "do not",
    "no longer",
    "sparsely",
    "to avoid",
)
_EXCLUSION_WORDS = re.compile(r"\b(not|never|cannot|without|avoid|barely)\b")


def is_exclusion_fact(text: str) -> bool:
    """True if the fact rules an option OUT rather than supporting it."""
    low = (text or "").lower()
    if "n't" in low:
        return True
    if _EXCLUSION_WORDS.search(low):
        return True
    return any(p in low for p in _EXCLUSION_PHRASES)


class CSQAKnowledgeValidator:
    """Validate retrieved facts with two trained lightweight heads."""

    def __init__(self, validator_dir: str = VALIDATOR_DIR):
        self.validator_dir = validator_dir
        required = ["tfidf.joblib", "direct_model.joblib", "option_model.joblib"]
        missing = [f for f in required if not os.path.exists(os.path.join(validator_dir, f))]
        if missing:
            raise FileNotFoundError(
                f"Missing validator models {missing} in {validator_dir}. "
                "Run train_csqa_light_validator.py first."
            )
        self.fx = FeatureExtractor(joblib.load(os.path.join(validator_dir, "tfidf.joblib")))
        self.direct_model = joblib.load(os.path.join(validator_dir, "direct_model.joblib"))
        self.option_model = joblib.load(os.path.join(validator_dir, "option_model.joblib"))

    def validate(
        self,
        question: str,
        choices: List[Dict[str, str]],
        candidates: List[Dict[str, Any]],
    ) -> Dict[str, Any]:
        if not candidates:
            return {"status": "abstain", "reason": "no_candidates"}

        per_fact_details: List[Dict[str, Any]] = []
        positive: List[Dict[str, Any]] = []   # facts that SUPPORT their top option
        exclusions: List[Dict[str, Any]] = []  # facts that RULE OUT their top option

        direct_probs = self._batch_direct_probs(question, choices, candidates)
        option_prob_rows = self._batch_option_probs(question, choices, candidates)
        all_option_labels = [c["label"] for c in choices]

        for candidate, direct_prob, option_scores in zip(candidates, direct_probs, option_prob_rows):
            ordered = sorted(option_scores.items(), key=lambda x: x[1], reverse=True)
            top_label, top_score = ordered[0]
            runner_label, runner_score = ordered[1] if len(ordered) > 1 else ("", 0.0)
            margin = top_score - runner_score

            answers_question = direct_prob >= DIRECT_THRESHOLD
            option_clear = top_score >= OPTION_TOP1_THRESHOLD and margin >= OPTION_MARGIN_THRESHOLD
            qualifies = answers_question and option_clear
            exclusion = is_exclusion_fact(candidate.get("fact", ""))

            detail = {
                "fact_id": candidate["fact_id"],
                "concept": candidate.get("concept", ""),
                "dimension": candidate.get("dimension", ""),
                "fact": candidate.get("fact", ""),
                "direct_prob": round(direct_prob, 4),
                "scores_by_option": {k: round(v, 4) for k, v in option_scores.items()},
                "top_option": top_label,
                "runner_up_option": runner_label,
                "top1_score": round(top_score, 4),
                "margin": round(margin, 4),
                "polarity": "exclusion" if exclusion else "support",
                "accepted_fact": qualifies and not exclusion,
            }
            per_fact_details.append(detail)

            if not qualifies:
                continue
            tagged = {**detail, "supported_option": top_label, "support_margin": round(margin, 4)}
            if exclusion:
                exclusions.append(tagged)
            else:
                positive.append(tagged)

        positive_options = {item["supported_option"] for item in positive}
        excluded_options = {item["supported_option"] for item in exclusions}

        # Path 1: positive support. One agreed option wins; >1 is a real conflict.
        if len(positive_options) == 1:
            winner = next(iter(positive_options))
            if winner in excluded_options:
                # A positive and an exclusion fact contradict each other on the same option.
                return {
                    "status": "abstain",
                    "reason": "conflicting_supported_options",
                    "fact_evaluations": per_fact_details,
                    "conflicting_options": sorted(positive_options | excluded_options),
                }
            return self._accept(winner, positive, per_fact_details, mode="support")

        if len(positive_options) > 1:
            return {
                "status": "abstain",
                "reason": "conflicting_supported_options",
                "fact_evaluations": per_fact_details,
                "conflicting_options": sorted(positive_options),
            }

        # Path 2: elimination. No positive support, but exclusions may leave exactly
        # one viable option standing.
        remaining = [lbl for lbl in all_option_labels if lbl not in excluded_options]
        if excluded_options and len(remaining) == 1:
            return self._accept(remaining[0], exclusions, per_fact_details, mode="elimination")

        return {
            "status": "abstain",
            "reason": self._abstain_reason(per_fact_details),
            "fact_evaluations": per_fact_details,
        }

    def _accept(
        self,
        option: str,
        evidence_facts: List[Dict[str, Any]],
        per_fact_details: List[Dict[str, Any]],
        mode: str,
    ) -> Dict[str, Any]:
        if mode == "support":
            relevant = [f for f in evidence_facts if f["supported_option"] == option]
        else:
            relevant = list(evidence_facts)  # exclusion facts that cleared the field
        relevant.sort(key=lambda x: (x["top1_score"], x["support_margin"]), reverse=True)
        kept = self._dedupe(relevant)[:MAX_SUPPORTING_FACTS]
        best = kept[0]
        return {
            "status": "accepted",
            "supported_option": option,
            "runner_up_option": best.get("runner_up_option", ""),
            "supporting_facts": [{"fact_id": k["fact_id"], "fact": k["fact"]} for k in kept],
            "support_margin": best["support_margin"],
            "accept_mode": mode,
            "fact_evaluations": per_fact_details,
        }

    def _batch_direct_probs(self, question, choices, candidates) -> List[float]:
        feats = [self.fx.direct_features(question, choices, c) for c in candidates]
        return [float(p[1]) for p in self.direct_model.predict_proba(feats)]

    def _batch_option_probs(self, question, choices, candidates) -> List[Dict[str, float]]:
        feats, index = [], []
        for ci, cand in enumerate(candidates):
            for choice in choices:
                feats.append(self.fx.option_features(question, choices, cand, choice["text"]))
                index.append((ci, choice["label"]))
        probs = self.option_model.predict_proba(feats)
        rows: List[Dict[str, float]] = [{} for _ in candidates]
        for (ci, label), prob in zip(index, probs):
            rows[ci][label] = float(prob[1])
        return rows

    def _dedupe(self, supporting: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        seen = set()
        unique = []
        for item in supporting:
            if item["fact_id"] in seen:
                continue
            seen.add(item["fact_id"])
            unique.append(item)
        return unique

    def _abstain_reason(self, per_fact_details: List[Dict[str, Any]]) -> str:
        if not per_fact_details:
            return "no_candidates"
        if not any(d["direct_prob"] >= DIRECT_THRESHOLD for d in per_fact_details):
            return "no_direct_knowledge"
        best = max(per_fact_details, key=lambda x: x["top1_score"])
        if best["top1_score"] < OPTION_TOP1_THRESHOLD:
            return "low_option_confidence"
        if best["margin"] < OPTION_MARGIN_THRESHOLD:
            return "insufficient_margin"
        return "no_uniquely_discriminative_knowledge"
