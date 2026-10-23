"""Smoke configured GapGPT chat routing or the optional Jev action endpoint.

Only ``BOXAPI_BASE_URL`` is ever contacted. No key or raw prompt/response is
printed. Use ``--jev`` to exercise the action-only ``/systemone`` endpoint.
"""

from __future__ import annotations

import argparse
import os
import sys
import time
from pathlib import Path

from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "backend"))
load_dotenv(ROOT / ".env")

from app import decision, llm_cost, prompts  # noqa: E402
from app.data_static import llm_mode  # noqa: E402
from app.decision import IntentWire  # noqa: E402
from app.llm import get_client, llm_node  # noqa: E402
from app.tools import catalog  # noqa: E402

SCENARIOS = [
    (
        "F3",
        "بالای ۱۰ میلیون هم بگرد",
        {"slots": {"query": "هدفون", "category": "هدفون، هدست و هندزفری", "budget_max": 3_000_000}},
    ),
    (
        "F5",
        "۵ کیلومتر",
        {"slots": {"query": "هدفون", "category": "هدفون، هدست و هندزفری"}},
    ),
    (
        "F6",
        "هدفون سونی می‌خوام فردوسی",
        {"slots": {"query": "هدفون", "category": "هدفون، هدست و هندزفری"}},
    ),
]


def _usage_delta(before: dict, after: dict) -> tuple[int, int, float]:
    old, new = before.get("total", {}), after.get("total", {})
    return (
        int(new.get("prompt_tokens", 0)) - int(old.get("prompt_tokens", 0)),
        int(new.get("completion_tokens", 0)) - int(old.get("completion_tokens", 0)),
        float(new.get("cost_usd", 0.0)) - float(old.get("cost_usd", 0.0)),
    )


def _chat_smoke() -> int:
    client = get_client()
    models = list(dict.fromkeys([client.model, client.fallback_model]))
    if not all(models):
        print("LLM_MODEL and LLM_MODEL_FALLBACK must be configured.")
        return 1
    categories = catalog.all_category_names()
    brands = catalog.all_brands()
    for model in models:
        for case, text, state in SCENARIOS:
            before = llm_cost.stats()
            started = time.perf_counter()
            with llm_node("smoke_router"):
                raw = client.chat_json(
                    prompts.router_messages(text, state),
                    model=model,
                    response_schema=IntentWire.model_json_schema(),
                    schema_name="intent",
                    response_validator=IntentWire.model_validate,
                    max_output_tokens=200,
                    token_parameter="max_tokens",
                )
            latency_ms = int((time.perf_counter() - started) * 1_000)
            after = llm_cost.stats()
            prompt_tokens, completion_tokens, cost = _usage_delta(before, after)
            action = "none"
            if raw:
                try:
                    action = IntentWire.model_validate(raw).action
                except Exception:
                    action = "validation-failed"
            print(
                f"{case} model={model} action={action} latency_ms={latency_ms} "
                f"prompt_tokens={prompt_tokens} completion_tokens={completion_tokens} "
                f"cost_usd={cost:.8f} format={client._format_support.get(model, 'unknown')}"
            )
    return 0


def _jev_smoke() -> int:
    for case, text, state in SCENARIOS:
        before = llm_cost.stats()
        started = time.perf_counter()
        result = decision._jev_action(
            text,
            state,
            min(
                float(os.environ.get("LLM_ROUTER_TIMEOUT", "5")),
                float(os.environ.get("DECIDER_TIMEOUT", "4")),
            ),
        )
        latency_ms = int((time.perf_counter() - started) * 1_000)
        after = llm_cost.stats()
        prompt_tokens, completion_tokens, cost = _usage_delta(before, after)
        action, confidence = (result[0], result[1]) if result else ("rule-fallback", 0.0)
        print(
            f"{case} backend=jev action={action} confidence={confidence:.2f} "
            f"latency_ms={latency_ms} prompt_tokens={prompt_tokens} "
            f"completion_tokens={completion_tokens} cost_usd={cost:.8f}"
        )
    return 0


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--jev", action="store_true", help="smoke the Jev /systemone action decider")
    args = parser.parse_args()
    base_url = os.environ.get("BOXAPI_BASE_URL", "").strip()
    if not base_url:
        print("BOXAPI_BASE_URL is not set; refusing to probe any host.")
        return 1
    if not os.environ.get("BOXAPI_API_KEY", "").strip():
        print("BOXAPI_API_KEY is not set - nothing to test.")
        return 1
    if llm_mode() in {"off", "0", "false"}:
        print("Set LLM_MODE=on to run the smoke test.")
        return 1

    client = get_client()
    try:
        model_page = client._get_client().models.list()
        available = [str(getattr(item, "id", "")) for item in getattr(model_page, "data", [])]
        print(
            f"models.list count={len(available)} "
            f"configured_primary_present={client.model in available}"
        )
    except Exception as exc:
        print(f"models.list failed: {type(exc).__name__}; configured_host_only=true")
    return _jev_smoke() if args.jev else _chat_smoke()


if __name__ == "__main__":
    raise SystemExit(main())
