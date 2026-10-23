"""Typed, guarded action decisions for each user chat turn.

Jev selects an action only; catalog/rules remain responsible for values and
all LLM-produced fields are normalized and validated before reaching graph state.
"""

from __future__ import annotations

import json
import logging
import os
import time
from contextvars import copy_context
from concurrent.futures import ThreadPoolExecutor
from typing import Annotated, Any, Literal, Union

import httpx
from pydantic import BaseModel, ConfigDict, Field, TypeAdapter, ValidationError

from . import prompts, rules
from .data_static import llm_mode
from .llm import current_call_budget, get_client, llm_node
from .llm_cost import record_call
from .normalize import geocode_neighbourhood, normalize
from .tools import catalog

logger = logging.getLogger("torobche.decision")

ActionName = Literal[
    "new_search", "refine", "change_radius", "change_location",
    "compare", "haggle", "ooc", "chitchat",
]


class _Base(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)
    confidence: float = Field(ge=0, le=1)


class NewSearch(_Base):
    action: Literal["new_search"]
    query: str = Field(min_length=1, max_length=80)
    category: str | None = None
    brand: str | None = None
    budget_min: int | None = Field(default=None, ge=0)
    budget_max: int | None = Field(default=None, ge=0)
    area: str | None = None
    radius_km: Literal[2, 5, 10] | None = None


class Refine(_Base):
    action: Literal["refine"]
    budget_min: int | None = None
    budget_max: int | None = None
    clear_budget_max: bool = False
    brand: str | None = None
    category: str | None = None
    # F6 can update a brand and location on the existing product query.
    area: str | None = None


class ChangeRadius(_Base):
    action: Literal["change_radius"]
    radius_km: Literal[2, 5, 10] | None


class ChangeLocation(_Base):
    action: Literal["change_location"]
    area: str = Field(min_length=2)


class Compare(_Base):
    action: Literal["compare"]
    sides: list[str] = Field(min_length=2, max_length=2)


class Haggle(_Base):
    action: Literal["haggle"]
    target_price: int | None = None


class Ooc(_Base):
    action: Literal["ooc"]
    query: str = Field(min_length=1, max_length=80)


class Chitchat(_Base):
    action: Literal["chitchat"]


Intent = Annotated[
    Union[NewSearch, Refine, ChangeRadius, ChangeLocation, Compare, Haggle, Ooc, Chitchat],
    Field(discriminator="action"),
]
IntentAdapter = TypeAdapter(Intent)


class Decision(BaseModel):
    model_config = ConfigDict(extra="forbid")
    intent: Intent
    source: Literal["llm", "rule", "llm+guard"]
    rejected_fields: list[str] = Field(default_factory=list)
    accessory_request: bool = False


class IntentWire(BaseModel):
    """Flat schema for providers that do not reliably emit discriminated unions."""
    model_config = ConfigDict(extra="forbid", strict=True)
    action: ActionName
    confidence: float = Field(ge=0, le=1)
    query: str | None = None
    category: str | None = None
    brand: str | None = None
    budget_min: int | None = None
    budget_max: int | None = None
    clear_budget_max: bool | None = None
    area: str | None = None
    radius_km: int | None = None
    sides: list[str] | None = None
    target_price: int | None = None


class JevChoiceAnswer(BaseModel):
    model_config = ConfigDict(extra="ignore")
    type: Literal["choice"]
    choice: ActionName
    confidence: float | None = None
    probabilities: dict[str, float] = Field(default_factory=dict)


class JevNoulAnswer(BaseModel):
    model_config = ConfigDict(extra="ignore")
    type: Literal["noul"]
    noul: float = 0


class JevScoreAnswer(BaseModel):
    model_config = ConfigDict(extra="ignore")
    type: Literal["score"]
    score: float
    confidence: float | None = None


JevAnswer = Annotated[
    Union[JevChoiceAnswer, JevNoulAnswer, JevScoreAnswer],
    Field(discriminator="type"),
]


class JevResponse(BaseModel):
    model_config = ConfigDict(extra="ignore")
    answers: dict[str, JevAnswer]
    usage: dict[str, Any] | None = None


def _rule_decision(text: str, state: dict, known_categories: list[str], known_brands: list[str]) -> Decision:
    raw = rules.rule_intent(
        text,
        state,
        known_categories=known_categories,
        known_brands=known_brands,
    )
    return _decision_from_rule_raw(raw)


def _decision_from_rule_raw(raw: dict) -> Decision:
    try:
        intent = _intent_from_mapping(raw)
    except (ValidationError, ValueError, TypeError):
        intent = Chitchat(action="chitchat", confidence=1.0)
    return Decision(intent=intent, source="rule")


def _intent_from_mapping(raw: dict) -> Intent:
    data = dict(raw)
    if data.get("action") == "compare" and isinstance(data.get("sides"), tuple):
        data["sides"] = list(data["sides"])
    if data.get("action") in {"new_search", "ooc"}:
        data["query"] = str(data.get("query") or "").strip()
    return IntentAdapter.validate_python(data)


def _wire_to_mapping(wire: IntentWire) -> dict:
    data = wire.model_dump(exclude_none=True)
    # Providers may encode absent numeric slots as zero or strings as empty.
    for key in ("budget_min", "budget_max", "target_price", "radius_km"):
        if data.get(key) == 0:
            data[key] = None
    for key in ("query", "category", "brand", "area"):
        if isinstance(data.get(key), str) and not data[key].strip():
            data[key] = None
    if data.get("action") == "compare" and data.get("sides") is not None:
        data["sides"] = list(data["sides"])
    return data


def _guard_intent(
    proposed: Intent,
    text: str,
    state: dict,
    rule_raw: dict,
    known_categories: list[str],
    known_brands: list[str],
) -> tuple[Intent | None, list[str]]:
    data = proposed.model_dump()
    action = data["action"]
    rejected: list[str] = []

    if action == "ooc" and rules.detect_in_torob(text):
        return None, ["action"]
    if action == "ooc" and rule_raw.get("action") == "ooc":
        data["query"] = rule_raw["query"]
    if action == "haggle" and not (
        state.get("selected_product_id")
        or (state.get("slots") or {}).get("selected_product_id")
        or (state.get("product") or {}).get("product_id")
    ):
        return None, ["action"]

    if "category" in data:
        if data.get("category") is not None and data["category"] not in known_categories:
            data["category"] = None
            rejected.append("category")
        if rule_raw.get("category") is not None:
            data["category"] = rule_raw["category"]

    if "brand" in data:
        brand_category = data.get("category") or rule_raw.get("category")
        valid_brands = catalog.brands_in_category(brand_category) if brand_category else known_brands
        if data.get("brand") is not None:
            canonical = rules.detect_brand(data["brand"], valid_brands)
            if canonical is None:
                data["brand"] = None
                rejected.append("brand")
            else:
                data["brand"] = canonical
        if rule_raw.get("brand") is not None:
            rule_brand = rules.detect_brand(rule_raw["brand"], valid_brands)
            if rule_brand is not None:
                data["brand"] = rule_brand
            else:
                data["brand"] = None
                if "brand" not in rejected:
                    rejected.append("brand")

    if "area" in data:
        if data.get("area") is not None:
            location = geocode_neighbourhood(data["area"])
            if location is None:
                data["area"] = None
                rejected.append("area")
            else:
                data["area"] = location["label"]
        if rule_raw.get("area") is not None:
            data["area"] = rule_raw["area"]

    if "budget_min" in data or "budget_max" in data:
        for key in ("budget_min", "budget_max"):
            value = data.get(key)
            if value is not None and not (0 < value < 10**11):
                data[key] = None
                rejected.append(key)
        has_rule_budget = rule_raw.get("budget_min") is not None or rule_raw.get("budget_max") is not None
        if rule_raw.get("budget_min") is not None:
            data["budget_min"] = rule_raw["budget_min"]
        if rule_raw.get("budget_max") is not None:
            data["budget_max"] = rule_raw["budget_max"]
        if not has_rule_budget:
            data["budget_min"] = None
            data["budget_max"] = None
        if "clear_budget_max" in data:
            data["clear_budget_max"] = bool(rule_raw.get("clear_budget_max"))
        if data.get("budget_min") is not None and data.get("budget_max") is not None:
            if data["budget_min"] > data["budget_max"]:
                data["budget_min"] = None
                data["budget_max"] = None
                rejected.extend(["budget_min", "budget_max"])

    if action == "change_radius" and rule_raw.get("action") == "change_radius":
        data["radius_km"] = rule_raw.get("radius_km")

    if action == "haggle" and rule_raw.get("action") == "haggle":
        data["target_price"] = rule_raw.get("target_price")

    if action == "new_search" and rule_raw.get("action") == "new_search":
        data["query"] = rule_raw.get("query") or data.get("query")

    if action == "compare":
        sides = data.get("sides") or ()
        if len(sides) != 2 or not all(str(side).strip() for side in sides):
            return None, [*rejected, "sides"]
        if rule_raw.get("action") == "compare":
            data["sides"] = list(rule_raw["sides"])
        elif not all(_text_contains_phrase(text, str(side)) for side in sides):
            return None, [*rejected, "sides"]

    try:
        return _intent_from_mapping(data), rejected
    except (ValidationError, ValueError, TypeError):
        return None, [*rejected, "validation"]


def _action_override(rule_raw: dict, action: str, text: str, state: dict) -> dict | None:
    """Jev supplies action only; accept it only when rules can supply its data."""
    if rule_raw.get("action") == action:
        return rule_raw
    if action == "new_search" and rule_raw.get("action") == "refine":
        # A new search can only be built when this message itself has a core
        # product phrase; never turn a pure budget/area edit into a query.
        core = rules.core_noun(text, rule_raw.get("category"))
        if core:
            return {**rule_raw, "action": "new_search", "query": " ".join([core, rule_raw.get("brand") or ""]).strip()}
    return None


def _text_contains_phrase(text: str, phrase: str) -> bool:
    haystack = normalize(text).split()
    needle = normalize(phrase).split()
    return bool(needle) and any(
        haystack[index : index + len(needle)] == needle
        for index in range(len(haystack) - len(needle) + 1)
    )


def _chat_router_raw(text: str, state: dict, timeout: float) -> dict | None:
    with llm_node("decide"):
        return get_client().chat_json(
            prompts.router_messages(text, state),
            response_schema=IntentWire.model_json_schema(),
            schema_name="intent",
            response_validator=IntentWire.model_validate,
            timeout=timeout,
            max_output_tokens=200,
            token_parameter="max_tokens",
        )


def _jev_action(text: str, state: dict, timeout: float) -> tuple[str, float, bool] | None:
    key = os.environ.get("BOXAPI_API_KEY", "").strip()
    model = os.environ.get("DECIDER_MODEL", "").strip()
    base_url = os.environ.get("BOXAPI_BASE_URL", "https://api.gapgpt.app/v1").rstrip("/")
    if not key or not model:
        return None
    budget = current_call_budget()
    remaining = min(timeout, budget.deadline - time.monotonic()) if budget else timeout
    if remaining <= 0:
        return None
    if budget is not None and budget.consume() is None:
        return None
    attempt = budget.used if budget else 1
    started = time.monotonic()
    context = {
        "text": text,
        "slots": {
            key: (state.get("slots") or {}).get(key)
            for key in ("query", "category", "brand", "budget_min", "budget_max", "location", "radius_km")
            if (state.get("slots") or {}).get(key) is not None
        },
        "last_query": (state.get("slots") or {}).get("query") or state.get("last_query"),
        "summary_bar": state.get("summary_bar") or {},
        "history": [
            {"role": msg.get("role"), "content": str(msg.get("content") or "")[:200]}
            for msg in (state.get("messages") or [])[-4:]
        ],
    }
    body = {
        "model": model,
        "state": {"text": json.dumps(context, ensure_ascii=False)},
        "questions": {
            "action": {
                "type": "choice",
                "instructions": "What does the user want?",
                "criteria": {
                    "new_search": "a new product search",
                    "refine": "change budget/brand/area of previous search",
                    "change_radius": "change search distance",
                    "change_location": "user says where they are now",
                    "compare": "compare products or brands",
                    "haggle": "negotiate or ask for a discount",
                    "chitchat": "greeting or other conversation",
                    "ooc": "request is clearly outside the Torob catalog",
                },
            },
            "is_accessory_request": {
                "type": "noul",
                "instructions": "Is the user explicitly asking for an accessory or part rather than a main product?",
            },
        },
    }
    try:
        response = httpx.post(
            f"{base_url}/systemone",
            headers={"Authorization": f"Bearer {key}", "Content-Type": "application/json"},
            json=body,
            timeout=remaining,
        )
        usage = None
        try:
            payload = response.json()
        except Exception:
            payload = None
        usage = payload.get("usage") if isinstance(payload, dict) else None
        prompt_tokens = (usage or {}).get("prompt_tokens", (usage or {}).get("input_tokens"))
        completion_tokens = (usage or {}).get("completion_tokens", (usage or {}).get("output_tokens"))
        if response.status_code != 200:
            kind = "429" if response.status_code == 429 else "other"
            record_call(
                node="decide", model=model, attempt=attempt,
                latency_ms=int((time.monotonic() - started) * 1_000),
                prompt_tokens=prompt_tokens,
                completion_tokens=completion_tokens,
                ok=False, error_kind=kind,
            )
            return None
        try:
            parsed = JevResponse.model_validate(payload)
            action_answer = parsed.answers.get("action")
            if not isinstance(action_answer, JevChoiceAnswer):
                raise ValueError("Jev action answer is not a choice")
            accessory_answer = parsed.answers.get("is_accessory_request")
            if not isinstance(accessory_answer, JevNoulAnswer):
                accessory_answer = JevNoulAnswer(type="noul", noul=0)
            confidence = action_answer.confidence
            if confidence is None:
                confidence = float(action_answer.probabilities.get(action_answer.choice, 0))
        except (ValidationError, TypeError, AttributeError, ValueError):
            record_call(
                node="decide", model=model, attempt=attempt,
                latency_ms=int((time.monotonic() - started) * 1_000),
                prompt_tokens=prompt_tokens,
                completion_tokens=completion_tokens,
                ok=False, error_kind="validation",
            )
            return None
        record_call(
            node="decide", model=model, attempt=attempt,
            latency_ms=int((time.monotonic() - started) * 1_000),
            prompt_tokens=prompt_tokens,
            completion_tokens=completion_tokens,
            ok=True, error_kind=None,
        )
        return action_answer.choice, float(confidence), accessory_answer.noul > 0.5
    except httpx.TimeoutException:
        if budget is not None:
            budget.blocked = True
        record_call(node="decide", model=model, attempt=attempt,
                    latency_ms=int((time.monotonic() - started) * 1_000),
                    prompt_tokens=None, completion_tokens=None, ok=False, error_kind="timeout")
    except Exception:
        record_call(node="decide", model=model, attempt=attempt,
                    latency_ms=int((time.monotonic() - started) * 1_000),
                    prompt_tokens=None, completion_tokens=None, ok=False, error_kind="other")
    return None


def decide(text: str, state: dict, known_categories: list[str], known_brands: list[str]) -> Decision:
    if llm_mode() in {"off", "0", "false"} or not os.environ.get("BOXAPI_API_KEY", "").strip():
        return _rule_decision(text, state, known_categories, known_brands)

    backend = os.environ.get("LLM_ROUTER_BACKEND", "jev").strip().lower()
    min_conf = float(os.environ.get("DECIDER_MIN_CONF", os.environ.get("LLM_ROUTER_MIN_CONFIDENCE", "0.7")))
    router_timeout = float(os.environ.get("LLM_ROUTER_TIMEOUT", "5"))
    if backend not in {"jev", "chat"}:
        return _rule_decision(text, state, known_categories, known_brands)

    # Keep local rule extraction concurrent with the single configured router
    # call. Copy the message budget context into the worker so both spend from
    # the same per-message call counter/deadline.
    with ThreadPoolExecutor(max_workers=2) as executor:
        rule_future = executor.submit(
            rules.rule_intent,
            text,
            state,
            known_categories=known_categories,
            known_brands=known_brands,
        )
        context = copy_context()
        if backend == "jev":
            router_timeout = min(router_timeout, float(os.environ.get("DECIDER_TIMEOUT", "4")))
            llm_future = executor.submit(context.run, _jev_action, text, state, router_timeout)
        else:
            llm_future = executor.submit(context.run, _chat_router_raw, text, state, router_timeout)
        try:
            rule_raw = rule_future.result()
        except Exception:
            rule_raw = {"action": "chitchat", "confidence": 1.0}
        fallback = _decision_from_rule_raw(rule_raw)
        try:
            llm_result = llm_future.result()
        except Exception:
            llm_result = None

    if backend == "jev":
        action = llm_result
        if action is None:
            return fallback
        action_name, confidence, accessory_request = action
        if confidence < min_conf:
            return fallback
        override = _action_override(rule_raw, action_name, text, state)
        if override is None:
            return fallback
        try:
            proposed = _intent_from_mapping(override)
        except (ValidationError, ValueError, TypeError):
            return fallback
        guarded, rejected = _guard_intent(
            proposed, text, state, rule_raw, known_categories, known_brands
        )
        if guarded is None:
            return fallback
        return Decision(
            intent=guarded,
            source="llm+guard",
            rejected_fields=rejected,
            accessory_request=accessory_request,
        )

    if llm_result is None:
        return fallback
    try:
        wire = IntentWire.model_validate(llm_result)
        if wire.confidence < min_conf:
            return fallback
        proposed = _intent_from_mapping(_wire_to_mapping(wire))
    except (ValidationError, ValueError, TypeError):
        return fallback
    if proposed.action != rule_raw.get("action"):
        override = _action_override(rule_raw, proposed.action, text, state)
        if override is None:
            return fallback
        try:
            proposed = _intent_from_mapping(override)
        except (ValidationError, ValueError, TypeError):
            return fallback
    guarded, rejected = _guard_intent(
        proposed, text, state, rule_raw, known_categories, known_brands
    )
    if guarded is None:
        return fallback
    return Decision(intent=guarded, source="llm+guard", rejected_fields=rejected)
