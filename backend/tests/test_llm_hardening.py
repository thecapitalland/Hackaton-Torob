"""P0-2 bounded LLM attempts and deterministic rule precedence."""

from __future__ import annotations

from types import SimpleNamespace

from app import graph
from app.llm import LLMClient
from app import llm as llm_module


class FakeCompletions:
    def __init__(self, callback):
        self.callback = callback
        self.calls: list[dict] = []

    def create(self, **kwargs):
        self.calls.append(kwargs)
        return self.callback(**kwargs)


def _fake_client(callback) -> tuple[LLMClient, FakeCompletions]:
    client = LLMClient()
    client.api_key = "test-key"
    client.model = "primary-model"
    client.fallback_model = "fallback-model"
    client.timeout = 0.05
    completions = FakeCompletions(callback)
    client._client = SimpleNamespace(
        chat=SimpleNamespace(completions=completions)
    )
    return client, completions


def _ok_response(**_kwargs):
    return SimpleNamespace(
        choices=[SimpleNamespace(message=SimpleNamespace(content='{"ok":true}'))]
    )


def test_llm_deadline_is_shared_by_primary_and_fallback(monkeypatch):
    monkeypatch.setattr(llm_module, "llm_mode", lambda: "on")
    clock = [0.0]
    monkeypatch.setattr(llm_module.time, "monotonic", lambda: clock[0])

    def timeout_after_budget(timeout, **_kwargs):
        clock[0] += timeout * 0.75
        raise TimeoutError("simulated timeout")

    client, completions = _fake_client(timeout_after_budget)
    started = clock[0]
    assert client.chat_json([{"role": "user", "content": "test"}]) is None
    elapsed = clock[0] - started

    assert elapsed <= client.timeout + 0.03
    assert len(completions.calls) <= 2
    assert all(0 < call["timeout"] <= client.timeout + 1e-6 for call in completions.calls), completions.calls


def test_429_tries_fallback_once_and_does_not_cache_failure(monkeypatch):
    monkeypatch.setattr(llm_module, "llm_mode", lambda: "on")

    class RateLimitError(Exception):
        status_code = 429

    client, completions = _fake_client(lambda **_kwargs: (_ for _ in ()).throw(RateLimitError("429")))
    messages = [{"role": "user", "content": "test"}]
    assert client.chat_json(messages) is None
    assert [call["model"] for call in completions.calls] == ["primary-model", "fallback-model"]
    assert not client._cache

    assert client.chat_json(messages) is None
    assert len(completions.calls) == 4, "a later call should retry after an uncached failure"


def test_response_format_variant_is_used_only_for_its_400_error(monkeypatch):
    monkeypatch.setattr(llm_module, "llm_mode", lambda: "on")

    class BadRequest(Exception):
        status_code = 400

    def reject_format_then_succeed(**kwargs):
        if "response_format" in kwargs:
            raise BadRequest("response_format is not supported")
        return _ok_response(**kwargs)

    client, completions = _fake_client(reject_format_then_succeed)
    assert client.chat_json([{"role": "user", "content": "test"}]) == {"ok": True}
    assert len(completions.calls) == 2
    assert "response_format" in completions.calls[0]
    assert "response_format" not in completions.calls[1]


def test_clarify_chips_always_come_from_rules(monkeypatch):
    class FakeClient:
        def chat_json(self, _messages):
            return {"text": "محله‌ات را بنویس", "chips": ["تهران", "اصفهان", "ساری"]}

    monkeypatch.setattr(graph, "get_client", lambda: FakeClient())
    result = graph._llm_clarify(["location"])
    assert result["text"] == "محله‌ات را بنویس"
    assert result["chips"] == graph.rules.clarify_fallback(["location"])["chips"]
    assert "تهران" not in result["chips"] and "اصفهان" not in result["chips"]


def test_rule_category_and_budget_override_llm_extraction(monkeypatch):
    monkeypatch.setattr(
        graph,
        "_llm_extract",
        lambda *_args, **_kwargs: {
            "category": "گوشی موبایل",
            "keywords": ["سامسونگ"],
            "budget_max": 999_000_000,
            "budget_min": None,
            "in_torob": True,
        },
    )
    state = graph.understand({"text": "هدفون تا ۳ میلیون"})
    assert state["slots"]["category"] == "هدفون، هدست و هندزفری"
    assert state["slots"]["budget_max"] == 3_000_000


def test_rules_keep_saffron_out_of_catalog_despite_llm_claim(monkeypatch):
    monkeypatch.setattr(
        graph,
        "_llm_extract",
        lambda *_args, **_kwargs: {"in_torob": True, "keywords": ["زعفران"]},
    )
    understood = graph.understand({"text": "زعفران"})
    state = {**understood, "text": "زعفران", "asked": 1}
    state.update(graph.search(state))
    assert state["slots"]["in_torob"] is False
    assert graph.route_after_search(state) == "out_of_catalog"


def test_invented_compare_number_falls_back_to_computed_template(monkeypatch):
    class FakeClient:
        def chat_json(self, _messages):
            return {
                "verdict": "گزینهٔ هدفون با ۹۹۹٬۰۰۰ تومان ارزان‌تر است.",
                "checklist": ["فاکتور رسمی", "گارانتی را بررسی کن", "کالا را تست کن"],
            }

    monkeypatch.setattr(graph, "get_client", lambda: FakeClient())
    result = graph.compare({"slots": {"compare": ["هدفون", "هندزفری"]}})["compare"]
    assert "۹۹۹٬۰۰۰" not in result["verdict"]
    assert result["verdict"] == graph._compare_verdict_template(
        graph._compare_side_data("هدفون", {}), graph._compare_side_data("هندزفری", {})
    )


def test_unsupported_warranty_or_quality_claim_falls_back(monkeypatch):
    class FakeClient:
        def chat_json(self, _messages):
            return {
                "verdict": "این مدل کیفیت بهتری دارد و گارانتی اصلی دارد.",
                "checklist": ["فاکتور رسمی", "ضمانت را بررسی کن", "کالا را تست کن"],
            }

    monkeypatch.setattr(graph, "get_client", lambda: FakeClient())
    result = graph.compare({"slots": {"compare": ["هدفون", "هندزفری"]}})["compare"]
    assert "گارانتی" not in result["verdict"]
    assert "کیفیت" not in result["verdict"]
