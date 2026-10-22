"""Thin OpenAI-compatible client for BoxAPI.

The agent must keep working when the LLM is unavailable (``LLM_MODE=off`` or a
network error), therefore every method returns ``None`` instead of raising and
the caller falls back to deterministic rules.

Notes about the gpt-5 family: it rejects ``temperature``/``max_tokens``, so we
send ``max_completion_tokens`` and transparently retry with the other variant.
"""

from __future__ import annotations

import hashlib
import json
import os
import threading
from typing import Any

from .data_static import llm_mode


class LLMClient:
    """Small cached wrapper around the OpenAI SDK."""

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._cache: dict[str, dict | None] = {}
        self._client = None
        self.api_key = os.environ.get("BOXAPI_API_KEY", "")
        self.base_url = os.environ.get("BOXAPI_BASE_URL", "https://ai.boxapi.ir/api/v1")
        self.model = os.environ.get("LLM_MODEL", "gpt-5-mini")
        self.fallback_model = os.environ.get("LLM_MODEL_FALLBACK", "gpt-5.4-mini")
        self.timeout = float(os.environ.get("LLM_TIMEOUT", "12"))

    # ------------------------------------------------------------------ setup
    @property
    def enabled(self) -> bool:
        return llm_mode() not in {"off", "0", "false"} and bool(self.api_key)

    @property
    def mode(self) -> str:
        return llm_mode()

    def _get_client(self):
        if self._client is None:
            from openai import OpenAI

            self._client = OpenAI(
                api_key=self.api_key,
                base_url=self.base_url,
                max_retries=0,
            )
        return self._client

    # ------------------------------------------------------------------ calls
    def chat_json(self, messages: list[dict], model: str | None = None) -> dict | None:
        """Return a parsed JSON object, or ``None`` when the LLM cannot help."""
        if not self.enabled:
            return None
        model = model or self.model
        key = hashlib.sha1(
            json.dumps([model, messages], ensure_ascii=False, sort_keys=True).encode("utf-8")
        ).hexdigest()
        with self._lock:
            if key in self._cache:
                return self._cache[key]

        result: dict | None = None
        try:
            result = self._call(messages, model)
        except Exception:
            result = None

        if result is None and self.fallback_model and self.fallback_model != model:
            try:
                result = self._call(messages, self.fallback_model)
            except Exception:
                result = None

        with self._lock:
            self._cache[key] = result
        return result

    def _call(self, messages: list[dict], model: str) -> dict | None:
        client = self._get_client()
        variants: list[dict[str, Any]] = [
            {"max_completion_tokens": 700, "response_format": {"type": "json_object"}},
            {"max_tokens": 700, "response_format": {"type": "json_object"}},
            {"max_completion_tokens": 700},
            {"max_tokens": 700},
        ]
        last_error: Exception | None = None
        for variant in variants:
            try:
                response = client.chat.completions.create(
                    model=model, messages=messages, timeout=self.timeout, **variant
                )
            except Exception as exc:  # noqa: BLE001 - try the next variant
                last_error = exc
                continue
            text = ""
            try:
                text = response.choices[0].message.content or ""
            except Exception:  # noqa: BLE001
                continue
            parsed = parse_json_object(text)
            if parsed is not None:
                return parsed
        if last_error:
            raise last_error
        return None


def parse_json_object(text: str) -> dict | None:
    """Extract the first JSON object from an LLM answer."""
    if not text:
        return None
    cleaned = text.strip()
    if cleaned.startswith("```"):
        cleaned = cleaned.strip("`")
        if cleaned.lower().startswith("json"):
            cleaned = cleaned[4:]
        cleaned = cleaned.strip()
    start = cleaned.find("{")
    end = cleaned.rfind("}")
    if start == -1 or end == -1 or end < start:
        return None
    candidate = cleaned[start : end + 1]
    try:
        parsed = json.loads(candidate)
    except ValueError:
        try:
            parsed = json.loads(candidate.replace("'", '"'))
        except ValueError:
            return None
    return parsed if isinstance(parsed, dict) else None


_client: LLMClient | None = None


def get_client() -> LLMClient:
    global _client
    if _client is None:
        _client = LLMClient()
    return _client
