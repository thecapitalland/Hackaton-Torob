"""Typed action contract, rule fallbacks, and backend radius action."""

from __future__ import annotations

from types import SimpleNamespace

from fastapi.testclient import TestClient

from app import decision, llm, llm_cost
from app.main import app
from app.decision import IntentWire
from app.llm import LLMClient


def test_intent_discriminated_union_accepts_all_actions():
    examples = [
        {"action": "new_search", "query": "هدفون", "confidence": 0.9},
        {"action": "refine", "budget_min": 10_000_000, "clear_budget_max": True, "confidence": 0.9},
        {"action": "change_radius", "radius_km": 5, "confidence": 0.9},
        {"action": "change_location", "area": "فردوسی", "confidence": 0.9},
        {"action": "compare", "sides": ["هدفون", "هندزفری"], "confidence": 0.9},
        {"action": "haggle", "target_price": 2_000_000, "confidence": 0.9},
        {"action": "ooc", "query": "زعفران", "confidence": 0.9},
        {"action": "chitchat", "confidence": 0.9},
    ]
    parsed = [decision.IntentAdapter.validate_python(item) for item in examples]
    assert [intent.action for intent in parsed] == [item["action"] for item in examples]


def test_jev_confidence_and_ooc_guardrails(monkeypatch):
    monkeypatch.setattr(decision, "llm_mode", lambda: "on")
    monkeypatch.setenv("BOXAPI_API_KEY", "test-only")
    monkeypatch.setenv("DECIDER_MODEL", "test-router")
    monkeypatch.setenv("LLM_ROUTER_BACKEND", "jev")
    categories = ["گوشی موبایل", "هدفون، هدست و هندزفری"]

    monkeypatch.setattr(decision, "_jev_action", lambda *_args: ("refine", 0.3, False))
    low_conf = decision.decide("بالای ۱۰ میلیون هم بگرد", {"slots": {"query": "هدفون"}}, categories, [])
    assert low_conf.source == "rule"
    assert low_conf.intent.action == "refine"

    monkeypatch.setattr(decision, "_jev_action", lambda *_args: ("ooc", 0.99, False))
    phone = decision.decide("گوشی سامسونگ", {"slots": {}}, categories, ["سامسونگ"])
    assert phone.intent.action == "new_search"
    assert phone.source == "rule"


def test_jev_systemone_request_is_typed_and_costed_without_logging_key(monkeypatch, caplog):
    monkeypatch.setenv("BOXAPI_API_KEY", "jev-test-secret")
    monkeypatch.setenv("BOXAPI_BASE_URL", "https://configured.example/v1")
    monkeypatch.setenv("DECIDER_MODEL", "typesafe/jev-1.14")
    caplog.set_level("INFO", logger="torobche.llm")
    calls = []

    class Response:
        status_code = 200

        def json(self):
            return {
                "answers": {
                    "action": {
                        "type": "choice",
                        "choice": "refine",
                        "confidence": 0.94,
                        "probabilities": {"refine": 0.94},
                    },
                    "is_accessory_request": {"type": "noul", "noul": 0.1},
                },
                "usage": {"prompt_tokens": 1000, "completion_tokens": 100},
            }

    def fake_post(url, **kwargs):
        calls.append((url, kwargs))
        return Response()

    monkeypatch.setattr(decision.httpx, "post", fake_post)
    llm_cost.reset_stats()
    result = decision._jev_action("بالای ۱۰ میلیون هم بگرد", {"slots": {"query": "هدفون"}}, 2)
    assert result == ("refine", 0.94, False)
    assert calls[0][0] == "https://configured.example/v1/systemone"
    assert isinstance(calls[0][1]["json"]["questions"]["action"]["criteria"], dict)
    assert "jev-test-secret" not in caplog.text
    assert llm_cost.stats()["total"]["cost_usd"] == 0.000042


def test_router_guard_rejects_unknown_category_and_brand(monkeypatch):
    monkeypatch.setattr(decision, "llm_mode", lambda: "on")
    monkeypatch.setenv("BOXAPI_API_KEY", "test-only")
    monkeypatch.setenv("LLM_ROUTER_BACKEND", "chat")

    class FakeClient:
        def chat_json(self, _messages, **_kwargs):
            return {
                "action": "new_search",
                "query": "هدفون ناشناخته",
                "category": "دستهٔ خیالی",
                "brand": "برند خیالی",
                "confidence": 0.95,
            }

    monkeypatch.setattr(decision, "get_client", lambda: FakeClient())
    result = decision.decide("چیز نامشخص", {"slots": {}}, ["هدفون، هدست و هندزفری"], ["سونی"])
    assert result.intent.action == "new_search"
    assert result.intent.category is None
    assert result.intent.brand is None
    assert {"category", "brand"} <= set(result.rejected_fields)


def test_chat_json_applies_strict_router_validator_and_does_not_cache_invalid_output(monkeypatch):
    monkeypatch.setattr(llm, "llm_mode", lambda: "on")
    client = LLMClient()
    client.api_key = "test-key"
    client.model = "gpt-4.1-mini"
    client.fallback_model = ""
    response = SimpleNamespace(
        choices=[SimpleNamespace(message=SimpleNamespace(content='{"action":"chitchat","confidence":0.9,"extra":"x"}'))],
        usage={"prompt_tokens": 10, "completion_tokens": 8},
    )

    class Completions:
        def create(self, **_kwargs):
            return response

    client._client = SimpleNamespace(chat=SimpleNamespace(completions=Completions()))
    llm_cost.reset_stats()
    assert client.chat_json(
        [{"role": "user", "content": "hello"}],
        response_schema=IntentWire.model_json_schema(),
        response_validator=IntentWire.model_validate,
    ) is None
    assert not client._cache
    assert llm_cost.stats()["total"]["failed"] == 1


def test_llm_stats_endpoint_is_debug_only(monkeypatch):
    with TestClient(app) as client:
        monkeypatch.delenv("DEBUG", raising=False)
        assert client.get("/api/debug/llm-stats").status_code == 404
        monkeypatch.setenv("DEBUG", "1")
        response = client.get("/api/debug/llm-stats")
        assert response.status_code == 200
        assert "total" in response.json() and "by_node" in response.json()

