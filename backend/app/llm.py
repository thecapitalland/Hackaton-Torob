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
import time
from typing import Any

from .data_static import llm_mode


class LLMClient:
    """Small cached wrapper around the OpenAI SDK."""

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._cache: dict[str, dict] = {}
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

        deadline = time.monotonic() + max(0.0, self.timeout)
        models = [model]
        if self.fallback_model and self.fallback_model != model:
            models.append(self.fallback_model)

        attempts = 0
        result: dict | None = None
        for candidate_model in models:
            if attempts >= 2 or time.monotonic() >= deadline:
                break
            result, used = self._call(
                messages,
                candidate_model,
                deadline=deadline,
                attempts_left=2 - attempts,
            )
            attempts += used
            if result is not None:
                # Only successful JSON responses are cacheable. In particular,
                # 429/timeouts must be retried on a later request.
                with self._lock:
                    self._cache[key] = result
                return result
        return None

    @staticmethod
    def _is_response_format_error(exc: Exception) -> bool:
        if getattr(exc, "status_code", None) != 400:
            return False
        details = " ".join(
            str(value or "") for value in (exc, getattr(exc, "body", None), getattr(exc, "message", None))
        ).lower()
        return "response_format" in details or "response format" in details

    def _call(
        self,
        messages: list[dict],
        model: str,
        *,
        deadline: float,
        attempts_left: int,
    ) -> tuple[dict | None, int]:
        """Make one request, retrying without response_format only on its 400.

        The caller owns the shared two-request budget across primary/fallback.
        """
        client = self._get_client()
        attempts = 0
        variants: list[dict[str, Any]] = [
            {"max_completion_tokens": 700, "response_format": {"type": "json_object"}}
        ]
        while variants and attempts < attempts_left:
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                break
            variant = variants.pop(0)
            attempts += 1
            try:
                response = client.chat.completions.create(
                    model=model,
                    messages=messages,
                    timeout=remaining,
                    **variant,
                )
            except Exception as exc:  # noqa: BLE001 - deterministic fallback below
                if attempts == 1 and attempts_left >= 2 and self._is_response_format_error(exc):
                    variants.append({"max_tokens": 700})
                    continue
                return None, attempts
            try:
                text = response.choices[0].message.content or ""
            except Exception:  # noqa: BLE001
                return None, attempts
            parsed = parse_json_object(text)
            if parsed is not None:
                return parsed, attempts
            # Malformed content is a failed model attempt; the caller may use
            # the fallback model if the global deadline/budget allows it.
            return None, attempts
        return None, attempts


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
