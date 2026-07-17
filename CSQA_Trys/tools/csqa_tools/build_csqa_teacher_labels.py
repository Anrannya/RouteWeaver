# -*- coding: utf-8 -*-
"""Offline strong-teacher labeling for CSQA KB.

Teacher backends (same labeling logic, pick one with --teacher):
  * api   : DeepSeek API (default; stronger judge, no GPU, needs DEEPSEEK_API_KEY)
  * local : local Meta-Llama-3-8B-Instruct via transformers (needs GPU)

For each question we send ONE labeling call (temperature 0, JSON output) covering
up to 5 retrieved candidate facts. Every fact first labeled `direct + unique_support`
is re-checked once by a focused yes/no call; only labels confirmed by both passes
are kept as positive (`confirmed_direct=true`).

The teacher never reads `answerKey`. Online inference does NOT use this script.

Run (100 questions, DeepSeek):
    export DEEPSEEK_API_KEY=...   # or OPENAI_API_KEY
    cd CSQA_Trys && python tools/csqa_tools/build_csqa_teacher_labels.py --limit 100

Run with local Llama instead:
    cd CSQA_Trys && python tools/csqa_tools/build_csqa_teacher_labels.py --limit 100 --teacher local
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
from typing import Any, Dict, List, Optional

BASE_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
sys.path.insert(0, os.path.join(BASE_DIR, "tools", "csqa_tools"))

from csqa_kb_retriever import CSQAKBRetriever

DATA_PATH = os.path.join(BASE_DIR, "..", "Task_Datasets", "CSQA", "train_rand_split.jsonl")
OUT_DIR = os.path.join(BASE_DIR, "knowledge_base", "csqa_kb_v1", "validator")
OUT_PATH = os.path.join(OUT_DIR, "teacher_labels.jsonl")
DEFAULT_MODEL = os.environ.get(
    "CSQA_TEACHER_MODEL",
    "/data1/chenshangxiao/DoT_main/DoT/VLLM/Models/Meta-Llama-3-8B-Instruct",
)
DEFAULT_API_MODEL = os.environ.get("CSQA_TEACHER_API_MODEL", "deepseek-v4-pro")
DEEPSEEK_BASE_URL = os.environ.get("CSQA_TEACHER_API_BASE", "https://api.deepseek.com")

MAX_FACTS_PER_QUESTION = 5
RELEVANCE_VALUES = {"direct", "partial", "irrelevant"}
REASON_CODES = {
    "directly_answers_question",
    "defines_option_only",
    "dimension_mismatch",
    "supports_multiple_options",
    "irrelevant_to_question",
    "insufficient_evidence",
}

LABEL_SYSTEM = (
    "You are a strict commonsense QA knowledge auditor. You judge whether a piece of "
    "knowledge actually helps ANSWER a multiple-choice question, not merely whether it "
    "mentions or defines an option.\n"
    "Core rules:\n"
    "1. Merely explaining or defining what an option means is NOT support; that is "
    "'defines_option_only'.\n"
    "2. Label 'direct' ONLY when the knowledge directly connects a CONDITION in the "
    "question to a specific option (it lets you pick that option over the others).\n"
    "3. If the knowledge fits several options equally, set reason_code "
    "'supports_multiple_options' and unique_support=false.\n"
    "4. If the knowledge is unrelated to the question, use 'irrelevant_to_question'.\n"
    "5. If a fact's KB dimension does not match what the question asks (e.g. a category "
    "definition for a 'why/how' question), prefer 'dimension_mismatch'.\n"
    "Output STRICT JSON only, no prose."
)

RECHECK_SYSTEM = (
    "You are double-checking one knowledge-option claim. Be conservative. "
    "Output STRICT JSON only."
)


def _load_api_key() -> str:
    """Read and validate DeepSeek/OpenAI API key from environment."""
    raw = os.environ.get("DEEPSEEK_API_KEY") or os.environ.get("OPENAI_API_KEY")
    if not raw:
        raise RuntimeError(
            "Set DEEPSEEK_API_KEY (or OPENAI_API_KEY) to use --teacher api."
        )
    api_key = raw.strip().strip('"').strip("'")
    if not api_key:
        raise RuntimeError("DEEPSEEK_API_KEY / OPENAI_API_KEY is empty after stripping.")
    try:
        api_key.encode("ascii")
    except UnicodeEncodeError as exc:
        raise RuntimeError(
            "DEEPSEEK_API_KEY / OPENAI_API_KEY contains non-ASCII characters "
            f"(around index {exc.start} in the key string). This usually means "
            "the key was copy-pasted with extra Chinese text or smart quotes. "
            "Re-export with ASCII only, e.g. export DEEPSEEK_API_KEY='sk-...'"
        ) from exc
    return api_key


def load_questions(path: str) -> List[Dict[str, Any]]:
    rows: List[Dict[str, Any]] = []
    with open(path, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                rows.append(json.loads(line))
    return rows


def options_block(choices: List[Dict[str, str]]) -> str:
    return "; ".join(f"{c['label']}: {c['text']}" for c in choices)


def facts_block(facts: List[Dict[str, Any]]) -> str:
    lines = []
    for fact in facts:
        lines.append(
            f"- fact_id={fact['fact_id']} | concept=\"{fact.get('concept', '')}\" | "
            f"dimension={fact.get('dimension', '')} | fact: {fact.get('fact', '')}"
        )
    return "\n".join(lines)


def build_label_prompt(question: str, choices: List[Dict[str, str]], facts: List[Dict[str, Any]]) -> str:
    return (
        f"Question: {question}\n"
        f"Options: {options_block(choices)}\n\n"
        f"Candidate knowledge ({len(facts)} items):\n{facts_block(facts)}\n\n"
        "For EACH candidate output one JSON object with keys:\n"
        '  "fact_id": string,\n'
        '  "question_relevance": one of ["direct","partial","irrelevant"],\n'
        '  "supported_option": option letter (A-E) or null,\n'
        '  "unique_support": boolean (true only if it singles out ONE option),\n'
        '  "reason_code": one of '
        '["directly_answers_question","defines_option_only","dimension_mismatch",'
        '"supports_multiple_options","irrelevant_to_question","insufficient_evidence"].\n'
        'Return a JSON array of these objects, in the same order as the candidates. '
        "No extra text."
    )


def build_recheck_prompt(question: str, choices: List[Dict[str, str]], fact: Dict[str, Any], option: str) -> str:
    return (
        f"Question: {question}\n"
        f"Options: {options_block(choices)}\n"
        f"Knowledge: {fact.get('fact', '')}\n"
        f"Claim: this knowledge DIRECTLY establishes that option {option} answers the "
        "question, and does so uniquely (better than every other option), rather than "
        "merely defining what that option is.\n"
        'Answer STRICT JSON: {"confirmed": true|false, "reason_code": one of '
        '["directly_answers_question","defines_option_only","dimension_mismatch",'
        '"supports_multiple_options","irrelevant_to_question","insufficient_evidence"]}'
    )


def extract_json(text: str) -> Optional[Any]:
    """Robustly pull the first JSON array/object out of model output."""
    if not text:
        return None
    fenced = re.search(r"```(?:json)?\s*(.+?)```", text, re.S)
    if fenced:
        text = fenced.group(1)
    for opener, closer in (("[", "]"), ("{", "}")):
        start = text.find(opener)
        end = text.rfind(closer)
        if start != -1 and end > start:
            try:
                return json.loads(text[start : end + 1])
            except json.JSONDecodeError:
                continue
    return None


def sanitize_label(raw: Dict[str, Any], fact_id: str, valid_options: set) -> Dict[str, Any]:
    relevance = raw.get("question_relevance")
    if relevance not in RELEVANCE_VALUES:
        relevance = "irrelevant"
    option = raw.get("supported_option")
    if isinstance(option, str):
        option = option.strip().upper()[:1]
    if option not in valid_options:
        option = None
    reason = raw.get("reason_code")
    if reason not in REASON_CODES:
        reason = "insufficient_evidence"
    unique = bool(raw.get("unique_support")) and option is not None
    if relevance != "direct":
        unique = False
    return {
        "fact_id": fact_id,
        "question_relevance": relevance,
        "supported_option": option,
        "unique_support": unique,
        "reason_code": reason,
    }


def _disable_flash_attention() -> None:
    """Avoid FlashAttention on pre-Ampere GPUs (T4/V100/2080 etc.)."""
    import torch

    if not torch.cuda.is_available():
        return
    # PyTorch SDPA may pick the flash kernel even when the GPU cannot run it.
    if hasattr(torch.backends, "cuda"):
        if hasattr(torch.backends.cuda, "enable_flash_sdp"):
            torch.backends.cuda.enable_flash_sdp(False)
        if hasattr(torch.backends.cuda, "enable_mem_efficient_sdp"):
            torch.backends.cuda.enable_mem_efficient_sdp(True)
        if hasattr(torch.backends.cuda, "enable_math_sdp"):
            torch.backends.cuda.enable_math_sdp(True)


def _load_causal_lm(model_path: str, dtype):
    from transformers import AutoModelForCausalLM

    _disable_flash_attention()
    load_kwargs = {"torch_dtype": dtype}
    # eager attention works on all CUDA generations; slightly slower but stable.
    try:
        return AutoModelForCausalLM.from_pretrained(
            model_path, attn_implementation="eager", **load_kwargs
        )
    except TypeError:
        return AutoModelForCausalLM.from_pretrained(model_path, **load_kwargs)


class LocalTeacher:
    """Thin transformers wrapper; greedy decoding for deterministic JSON output."""

    def __init__(self, model_path: str):
        import torch
        from transformers import AutoTokenizer

        self.torch = torch
        if torch.cuda.is_available():
            device_name = os.environ.get("CSQA_TEACHER_CUDA", "cuda:0")
            self.device = torch.device(device_name)
            dtype = torch.float16
        else:
            self.device = torch.device("cpu")
            dtype = torch.float32

        self.tokenizer = AutoTokenizer.from_pretrained(model_path)
        self.model = _load_causal_lm(model_path, dtype)
        self.model.to(self.device)
        self.model.eval()
        if self.tokenizer.pad_token_id is None:
            self.tokenizer.pad_token_id = self.tokenizer.eos_token_id

    def chat(self, system: str, user: str, max_new_tokens: int = 512) -> str:
        messages = [{"role": "system", "content": system}, {"role": "user", "content": user}]
        inputs = self.tokenizer.apply_chat_template(
            messages, add_generation_prompt=True, return_tensors="pt"
        ).to(self.device)
        with self.torch.no_grad():
            output = self.model.generate(
                inputs,
                max_new_tokens=max_new_tokens,
                do_sample=False,
                pad_token_id=self.tokenizer.pad_token_id,
            )
        return self.tokenizer.decode(output[0, inputs.shape[1] :], skip_special_tokens=True)


class DeepSeekTeacher:
    """DeepSeek API teacher; same .chat() interface as LocalTeacher (no GPU needed)."""

    # 固定单文件累计记账, 避免目录随运行次数膨胀
    TOKENS_PATH = os.path.join(BASE_DIR, "Tokens", "teacher_token_usage.json")

    def __init__(self, model: str = DEFAULT_API_MODEL):
        from openai import OpenAI

        api_key = _load_api_key()
        self.client = OpenAI(base_url=DEEPSEEK_BASE_URL, api_key=api_key)
        self.model = model
        sys.path.insert(0, os.path.abspath(os.path.join(BASE_DIR, "..")))
        from utils import record_usage  # 复用主仓的真实 token 记账(含缓存命中)

        self._record_usage = record_usage
        os.makedirs(os.path.dirname(self.TOKENS_PATH), exist_ok=True)
        if not os.path.exists(self.TOKENS_PATH):
            with open(self.TOKENS_PATH, "w") as f:
                json.dump({}, f)

    def chat(self, system: str, user: str, max_new_tokens: int = 10000) -> str:
        response = self.client.chat.completions.create(
            model=self.model,
            messages=[
                {"role": "system", "content": system},
                {"role": "user", "content": user},
            ],
            temperature=1,
            max_tokens=max_new_tokens,
            extra_body={"thinking": {"type": "enabled"}},
        )
        self._record_usage(self.model, response.usage, self.TOKENS_PATH)
        return (response.choices[0].message.content or "").strip()


def build_teacher(backend: str):
    if backend == "api":
        return DeepSeekTeacher()
    if backend == "local":
        return LocalTeacher(DEFAULT_MODEL)
    raise ValueError(f"Unknown teacher backend: {backend}")


def label_question(
    teacher: LocalTeacher,
    question: str,
    choices: List[Dict[str, str]],
    facts: List[Dict[str, Any]],
) -> List[Dict[str, Any]]:
    valid_options = {c["label"] for c in choices}
    raw_out = teacher.chat(LABEL_SYSTEM, build_label_prompt(question, choices, facts))
    parsed = extract_json(raw_out)
    by_id: Dict[str, Dict[str, Any]] = {}
    if isinstance(parsed, list):
        for item in parsed:
            if isinstance(item, dict) and item.get("fact_id"):
                by_id[str(item["fact_id"])] = item

    labels: List[Dict[str, Any]] = []
    for fact in facts:
        raw = by_id.get(fact["fact_id"], {})
        label = sanitize_label(raw, fact["fact_id"], valid_options)
        label["recheck"] = None
        label["confirmed_direct"] = False

        if label["question_relevance"] == "direct" and label["unique_support"]:
            recheck_out = teacher.chat(
                RECHECK_SYSTEM,
                build_recheck_prompt(question, choices, fact, label["supported_option"]),
                max_new_tokens=10000,
            )
            rc = extract_json(recheck_out) or {}
            confirmed = bool(rc.get("confirmed"))
            recheck_reason = rc.get("reason_code")
            if recheck_reason not in REASON_CODES:
                recheck_reason = "insufficient_evidence"
            label["recheck"] = {"confirmed": confirmed, "reason_code": recheck_reason}
            if confirmed:
                label["confirmed_direct"] = True
            else:
                # Two passes disagree -> demote, keep as negative evidence.
                label["question_relevance"] = "partial"
                label["unique_support"] = False
                label["reason_code"] = recheck_reason
        labels.append(label)
    return labels


def load_done_ids(path: str) -> set:
    done = set()
    if os.path.exists(path):
        with open(path, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if line:
                    try:
                        done.add(json.loads(line)["question_id"])
                    except (json.JSONDecodeError, KeyError):
                        continue
    return done


def main() -> None:
    parser = argparse.ArgumentParser(description="Offline CSQA teacher labeling")
    parser.add_argument("--limit", type=int, default=100, help="Number of questions to label")
    parser.add_argument(
        "--teacher",
        choices=["api", "local"],
        default="api",
        help="Teacher backend: 'api' = DeepSeek API (default), 'local' = local Llama",
    )
    args = parser.parse_args()

    os.makedirs(OUT_DIR, exist_ok=True)
    questions = load_questions(os.path.abspath(DATA_PATH))
    retriever = CSQAKBRetriever()
    done_ids = load_done_ids(OUT_PATH)

    target_ids = [qid for qid in range(min(args.limit, len(questions))) if qid not in done_ids]
    if not target_ids:
        print(f"All {min(args.limit, len(questions))} questions already labeled -> {OUT_PATH}")
        return

    teacher = build_teacher(args.teacher)
    written = 0
    with open(OUT_PATH, "a", encoding="utf-8") as out:
        for qid in target_ids:
            entry = questions[qid]
            stem = entry["question"]["stem"]
            choices = [{"label": c["label"], "text": c["text"]} for c in entry["question"]["choices"]]
            facts = retriever.retrieve(stem, choices)[:MAX_FACTS_PER_QUESTION]
            labels = label_question(teacher, stem, choices, facts) if facts else []
            record = {
                "question_id": qid,
                "question": stem,
                "options": choices,
                "candidates": facts,
                "labels": labels,
            }
            out.write(json.dumps(record, ensure_ascii=False) + "\n")
            out.flush()
            written += 1
            print(f"[{written}/{len(target_ids)}] qid={qid} facts={len(facts)} "
                  f"confirmed={sum(1 for l in labels if l['confirmed_direct'])}")

    print(f"Done. Labeled {written} new questions ({args.teacher} teacher) -> {OUT_PATH}")


if __name__ == "__main__":
    main()
