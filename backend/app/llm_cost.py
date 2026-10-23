"""Cost accounting and redacted structured records for LLM requests."""

from __future__ import annotations

import json
import logging
import os
import threading
from collections import Counter

logger = logging.getLogger("torobche.llm")

# USD per million tokens: (input, output). Unknown models deliberately have
# no estimate; never pretend an unlisted model is free.
PRICES_USD_PER_M: dict[str, tuple[float, float]] = {
    "gpt-4o-mini": (0.15, 0.60),
    "gpt-4.1-mini": (0.40, 1.60),
    "gpt-5-mini": (0.25, 2.00),
    "gemini-2.5-flash": (0.30, 2.50),
    "gemini-2.5-flash-lite": (0.10, 0.40),
    "gpt-4.1-nano": (0.10, 0.40),
    "deepseek-v4-flash": (0.14, 0.28),
    "deepseek-v4.1-flash": (0.15, 0.60),
    "typesafe/jev-1.14": (0.042, 0.0),
}

_LOCK = threading.Lock()
_TOTALS = Counter()
_BY_NODE: dict[str, Counter] = {}
_BY_MODEL: dict[str, Counter] = {}


def estimate_cost(model: str, prompt_tokens: int | None, completion_tokens: int | None) -> float | None:
    prices = PRICES_USD_PER_M.get(model)
    if prices is None or prompt_tokens is None or completion_tokens is None:
        return None
    return round((prompt_tokens * prices[0] + completion_tokens * prices[1]) / 1_000_000, 10)


def record_call(
    *,
    node: str,
    model: str,
    attempt: int,
    latency_ms: int,
    prompt_tokens: int | None,
    completion_tokens: int | None,
    ok: bool,
    error_kind: str | None = None,
) -> dict:
    cost = estimate_cost(model, prompt_tokens, completion_tokens)
    record = {
        "event": "llm_call",
        "node": node,
        "model": model,
        "attempt": attempt,
        "latency_ms": max(0, int(latency_ms)),
        "prompt_tokens": prompt_tokens,
        "completion_tokens": completion_tokens,
        "cost_usd": cost,
        "ok": bool(ok),
        "error_kind": error_kind,
    }
    with _LOCK:
        _TOTALS["calls"] += 1
        _TOTALS["ok"] += int(bool(ok))
        _TOTALS["failed"] += int(not ok)
        if prompt_tokens is not None:
            _TOTALS["prompt_tokens"] += int(prompt_tokens)
        if completion_tokens is not None:
            _TOTALS["completion_tokens"] += int(completion_tokens)
        if cost is not None:
            _TOTALS["cost_usd"] += cost
        node_stats = _BY_NODE.setdefault(node, Counter())
        node_stats["calls"] += 1
        node_stats["ok"] += int(bool(ok))
        node_stats["failed"] += int(not ok)
        if cost is not None:
            node_stats["cost_usd"] += cost
        model_stats = _BY_MODEL.setdefault(model, Counter())
        model_stats["calls"] += 1
        model_stats["ok"] += int(bool(ok))
        model_stats["failed"] += int(not ok)
        if prompt_tokens is not None:
            model_stats["prompt_tokens"] += int(prompt_tokens)
        if completion_tokens is not None:
            model_stats["completion_tokens"] += int(completion_tokens)
        if cost is not None:
            model_stats["cost_usd"] += cost
    # Deliberately omit key, request body, prompts and response content.
    if os.environ.get("LLM_COST_LOG", "1").strip().lower() not in {"0", "off", "false"}:
        logger.info("llm_call %s", json.dumps(record, ensure_ascii=False, sort_keys=True))
    return record


def stats() -> dict:
    with _LOCK:
        total = dict(_TOTALS)
        by_node = {name: dict(values) for name, values in _BY_NODE.items()}
        by_model = {name: dict(values) for name, values in _BY_MODEL.items()}
    total["cost_usd"] = round(float(total.get("cost_usd", 0.0)), 10)
    return {"total": total, "by_node": by_node, "by_model": by_model}


def reset_stats() -> None:
    with _LOCK:
        _TOTALS.clear()
        _BY_NODE.clear()
        _BY_MODEL.clear()
