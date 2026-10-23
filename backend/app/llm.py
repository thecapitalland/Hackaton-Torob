"""Thin OpenAI-compatible client for BoxAPI.

The agent must keep working when the LLM is unavailable (``LLM_MODE=off`` or a
network error), therefore every method returns ``None`` instead of raising and
the caller falls back to deterministic rules.

The provider/model are configured by environment variables; no credentials or
model identifiers are sent to alternate hosts.
"""

from __future__ import annotations

import hashlib
import json
import os
import threading
import time
from contextlib import contextmanager
from contextvars import ContextVar
from dataclasses import dataclass
from typing import Any, Callable

from .data_static import llm_mode
from .llm_cost import record_call

_CURRENT_NODE: ContextVar[str] = ContextVar("llm_node", default="unknown")


@dataclass
class CallBudget:
    remaining: int
    deadline: float
    used: int = 0
    blocked: bool = False

    def consume(self) -> int | None:
        if self.blocked or self.remaining <= 0 or time.monotonic() >= self.deadline:
            return None
        self.remaining -= 1
        self.used += 1
        return self.used


_CURRENT_BUDGET: ContextVar[CallBudget | None] = ContextVar("llm_call_budget", default=None)


def current_call_budget() -> CallBudget | None:
    return _CURRENT_BUDGET.get()


@contextmanager
def llm_node(node: str):
    token = _CURRENT_NODE.set(node or "unknown")
    try:
        yield
    finally:
        _CURRENT_NODE.reset(token)


@contextmanager
def llm_budget(max_calls: int = 2, timeout_s: float = 8.0):
    budget = CallBudget(max(0, int(max_calls)), time.monotonic() + max(0.0, timeout_s))
    token = _CURRENT_BUDGET.set(budget)
    try:
        yield budget
    finally:
        _CURRENT_BUDGET.reset(token)


class LLMClient:
    """Small cached wrapper around the OpenAI SDK."""

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._cache: dict[str, dict] = {}
        self._client = None
        self.api_key = os.environ.get("BOXAPI_API_KEY", "")
        self.base_url = os.environ.get("BOXAPI_BASE_URL", "https://api.gapgpt.app/v1")
        # Model identifiers are configuration, never embedded in application
        # behavior. An unset value disables LLM calls rather than guessing.
        self.model = os.environ.get("LLM_MODEL", "").strip()
        self.fallback_model = os.environ.get("LLM_MODEL_FALLBACK", "").strip()
        self.timeout = float(os.environ.get("LLM_TIMEOUT", "6"))
        self.structured_mode = os.environ.get("LLM_STRUCTURED", "auto").strip().lower()
        self._format_support: dict[str, str] = {}

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
    def chat_json(
        self,
        messages: list[dict],
        model: str | None = None,
        *,
        response_schema: dict | None = None,
        schema_name: str = "response",
        response_validator: Callable[[dict], Any] | None = None,
        timeout: float | None = None,
        max_output_tokens: int = 700,
        token_parameter: str = "max_completion_tokens",
    ) -> dict | None:
        """Return a parsed JSON object, or ``None`` when the LLM cannot help."""
        if not self.enabled or not (model or self.model):
            return None
        model = model or self.model
        key = hashlib.sha1(
            json.dumps([model, messages], ensure_ascii=False, sort_keys=True).encode("utf-8")
        ).hexdigest()
        with self._lock:
            if key in self._cache:
                return self._cache[key]

        budget = _CURRENT_BUDGET.get()
        if budget is None:
            budget = CallBudget(2, time.monotonic() + max(0.0, self.timeout))
        timeout_s = self.timeout if timeout is None else min(self.timeout, max(0.0, timeout))
        deadline = min(time.monotonic() + max(0.0, timeout_s), budget.deadline)
        models = [model]
        if self.fallback_model and self.fallback_model != model:
            models.append(self.fallback_model)

        result: dict | None = None
        for candidate_model in models:
            if budget.remaining <= 0 or time.monotonic() >= deadline:
                break
            result, _used = self._call(
                messages,
                candidate_model,
                deadline=deadline,
                attempts_left=budget.remaining,
                budget=budget,
                node=_CURRENT_NODE.get(),
                response_schema=response_schema,
                schema_name=schema_name,
                response_validator=response_validator,
                max_output_tokens=max_output_tokens,
                token_parameter=token_parameter,
            )
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
        return (
            "response_format" in details
            or "response format" in details
            or "provider returned error" in details
        )

    def _call(
        self,
        messages: list[dict],
        model: str,
        *,
        deadline: float,
        attempts_left: int,
        budget: CallBudget,
        node: str = "unknown",
        response_schema: dict | None = None,
        schema_name: str = "response",
        response_validator: Callable[[dict], Any] | None = None,
        max_output_tokens: int = 700,
        token_parameter: str = "max_completion_tokens",
    ) -> tuple[dict | None, int]:
        """Make one request, retrying without response_format only on its 400.

        The caller owns the shared two-request budget across primary/fallback.
        """
        client = self._get_client()
        attempts = 0
        format_mode = self._initial_format(model, response_schema)
        variants: list[tuple[str, dict[str, Any]]] = [
            (format_mode, self._format_kwargs(format_mode, response_schema, schema_name, max_output_tokens, token_parameter))
        ]
        while variants and attempts < attempts_left:
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                break
            attempted_format, variant = variants.pop(0)
            request_attempt = budget.consume()
            if request_attempt is None:
                break
            attempts += 1
            call_started = time.monotonic()
            try:
                response = client.chat.completions.create(
                    model=model,
                    messages=messages,
                    timeout=remaining,
                    **variant,
                )
            except Exception as exc:  # noqa: BLE001 - deterministic fallback below
                error_kind = _error_kind(exc)
                if error_kind == "timeout":
                    budget.blocked = True
                record_call(
                    node=node,
                    model=model,
                    attempt=request_attempt,
                    latency_ms=int((time.monotonic() - call_started) * 1_000),
                    prompt_tokens=None,
                    completion_tokens=None,
                    ok=False,
                    error_kind=error_kind,
                )
                if self._is_response_format_error(exc) and attempted_format != "off":
                    fallback_format = "json_object" if attempted_format == "json_schema" else "off"
                    self._format_support[model] = fallback_format
                    if attempts < attempts_left:
                        variants.append(
                            (
                                fallback_format,
                                self._format_kwargs(fallback_format, response_schema, schema_name, max_output_tokens, token_parameter),
                            )
                        )
                    continue
                return None, attempts
            if attempted_format != "off":
                self._format_support.setdefault(model, attempted_format)
            usage = getattr(response, "usage", None)
            if isinstance(usage, dict):
                prompt_tokens = usage.get("prompt_tokens")
                completion_tokens = usage.get("completion_tokens")
            else:
                prompt_tokens = getattr(usage, "prompt_tokens", None)
                completion_tokens = getattr(usage, "completion_tokens", None)
            try:
                text = response.choices[0].message.content or ""
            except Exception:  # noqa: BLE001
                record_call(
                    node=node,
                    model=model,
                    attempt=request_attempt,
                    latency_ms=int((time.monotonic() - call_started) * 1_000),
                    prompt_tokens=prompt_tokens,
                    completion_tokens=completion_tokens,
                    ok=False,
                    error_kind="parse",
                )
                return None, attempts
            parsed = parse_json_object(text)
            validation_error = False
            if parsed is not None and response_validator is not None:
                try:
                    response_validator(parsed)
                except Exception:  # noqa: BLE001 - schema failures use deterministic rules
                    validation_error = True
            record_call(
                node=node,
                model=model,
                attempt=request_attempt,
                latency_ms=int((time.monotonic() - call_started) * 1_000),
                prompt_tokens=prompt_tokens,
                completion_tokens=completion_tokens,
                ok=parsed is not None and not validation_error,
                error_kind=(
                    "validation" if validation_error
                    else None if parsed is not None
                    else "parse"
                ),
            )
            if validation_error:
                return None, attempts
            if parsed is not None:
                return parsed, attempts
            # Malformed content is a failed model attempt; the caller may use
            # the fallback model if the global deadline/budget allows it.
            return None, attempts
        return None, attempts

    def _initial_format(self, model: str, response_schema: dict | None) -> str:
        if self.structured_mode == "off":
            return "off"
        supported = self._format_support.get(model)
        if supported == "off":
            return "off"
        if supported == "json_object":
            return "json_object"
        if supported == "json_schema" and response_schema is not None:
            return "json_schema"
        if self.structured_mode == "json_schema" and response_schema is not None:
            return "json_schema"
        if self.structured_mode == "auto" and response_schema is not None:
            return "json_schema"
        return "json_object"

    @staticmethod
    def _format_kwargs(
        mode: str,
        schema: dict | None,
        name: str,
        max_output_tokens: int,
        token_parameter: str = "max_completion_tokens",
    ) -> dict[str, Any]:
        kwargs: dict[str, Any] = {token_parameter: max_output_tokens}
        if mode == "json_schema" and schema is not None:
            kwargs["response_format"] = {
                "type": "json_schema",
                "json_schema": {"name": name, "strict": True, "schema": schema},
            }
        elif mode == "json_object":
            kwargs["response_format"] = {"type": "json_object"}
        return kwargs


def _error_kind(exc: Exception) -> str:
    if LLMClient._is_response_format_error(exc):
        return "400_format"
    if getattr(exc, "status_code", None) == 429:
        return "429"
    name = type(exc).__name__.lower()
    message = str(exc).lower()
    if "timeout" in name or "timeout" in message:
        return "timeout"
    return "other"


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
