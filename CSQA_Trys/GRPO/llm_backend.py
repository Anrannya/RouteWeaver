# -*- coding: utf-8 -*-
"""Unified LLM backend with on-disk caching.

Two backends:
  * real : the project's native askLLM (sub-questions -> local ollama llama3-8b,
           final summary -> DeepSeek). Needs DEEPSEEK_API_KEY in env + a running
           ollama server, exactly like CSQA_dotrun_step2.py.
  * mock : deterministic stub for plumbing tests only (NO scientific meaning).

Caching is keyed by (model, temperature, messages). With temperature=0 the env is
deterministic, so the cache becomes a reusable offline reward table for GRPO.
"""

from __future__ import annotations

import hashlib
import json
import os
import re
from typing import Any, Dict, List, Optional

CSQA_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
DOT_ROOT = os.path.abspath(os.path.join(CSQA_DIR, ".."))
CACHE_DIR = os.path.join(os.path.dirname(__file__), "cache")


def _key(model: str, temperature: float, messages: List[Dict[str, str]]) -> str:
    blob = json.dumps({"m": model, "t": temperature, "msg": messages}, ensure_ascii=False, sort_keys=True)
    return hashlib.sha1(blob.encode("utf-8")).hexdigest()


class LLMBackend:
    def __init__(self, backend: str = "real", cache_name: Optional[str] = None, temperature: float = 0.0):
        self.backend = backend
        self.temperature = temperature
        os.makedirs(CACHE_DIR, exist_ok=True)
        # Separate cache per backend so a mock self-test can never contaminate a real run.
        cache_name = cache_name or f"llm_cache_{backend}.json"
        self.cache_path = os.path.join(CACHE_DIR, cache_name)
        self.cache: Dict[str, str] = {}
        if os.path.exists(self.cache_path):
            try:
                self.cache = json.load(open(self.cache_path, encoding="utf-8"))
            except json.JSONDecodeError:
                self.cache = {}
        self._dirty = 0
        self._clients = None
        self._tokens_path = None
        self._askLLM = None

    # ---- real backend lazy init (mirrors CSQA_dotrun_step2.py) ----
    def _ensure_real(self):
        if self._clients is not None:
            return
        import sys
        sys.path.insert(0, DOT_ROOT)
        from utils import askLLM, setOpenAi, setLocal  # noqa
        self._askLLM = askLLM
        openai_client = setOpenAi(keyid=0)
        llama_client = setLocal()
        self._clients = {"gpt": openai_client, "llama": llama_client}
        tok_dir = os.path.join(os.path.dirname(__file__), "Tokens")
        os.makedirs(tok_dir, exist_ok=True)
        self._tokens_path = os.path.join(tok_dir, "grpo_token_usage.json")
        if not os.path.exists(self._tokens_path):
            json.dump({}, open(self._tokens_path, "w"))

    def chat(self, messages: List[Dict[str, str]], model: str, max_tokens: int = 300) -> str:
        k = _key(model, self.temperature, messages)
        if k in self.cache:
            return self.cache[k]
        if self.backend == "mock":
            out = self._mock(messages, model)
        else:
            self._ensure_real()
            out = self._askLLM(
                self._clients, messages, tokens_path=self._tokens_path,
                model=model, temperature=self.temperature, max_tokens=max_tokens,
            )
        out = (out or "").strip()
        self.cache[k] = out
        self._dirty += 1
        if self._dirty >= 20:
            self.flush()
        return out

    def flush(self):
        json.dump(self.cache, open(self.cache_path, "w", encoding="utf-8"), ensure_ascii=False)
        self._dirty = 0

    # ---- deterministic mock (plumbing only) ----
    @staticmethod
    def _mock(messages: List[Dict[str, str]], model: str) -> str:
        text = " ".join(m.get("content", "") for m in messages)
        is_final = "which answer do you ultimately choose" in text.lower()
        if is_final:
            # If an injected evidence hint is present, follow it; else deterministic pseudo-pick.
            m = re.search(r"points to option ([A-E])", text)
            if m:
                return m.group(1)
            h = int(hashlib.sha1(text.encode()).hexdigest(), 16)
            return "ABCDE"[h % 5]
        # sub-question: short canned answer (carry evidence forward if injected)
        m = re.search(r"points to option ([A-E])", text)
        if m:
            return f"Based on the knowledge, option {m.group(1)} fits best."
        return "A concise reasoning answer for this sub-question."
