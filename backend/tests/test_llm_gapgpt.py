"""GapGPT configuration, redacted per-call costs, and diagnostics endpoint."""

from __future__ import annotations

import logging
from types import SimpleNamespace

from app import llm as llm_module, llm_cost
from app.llm import LLMClient, llm_budget, llm_node


def test_gapgpt_defaults_and_models_are_environment_driven(monkeypatch):
    monkeypatch.delenv("BOXAPI_BASE_URL", raising=False)
    monkeypatch.delenv("LLM_MODEL", raising=False)
    monkeypatch.delenv("LLM_MODEL_FALLBACK", raising=False)
    client = LLMClient()
    assert client.base_url == "https://api.gapgpt.app/v1"
    assert client.model == ""
    assert client.fallback_model == ""


def test_cost_formula_and_unknown_model():
    assert llm_cost.estimate_cost("gpt-4.1-mini", 1000, 100) == 0.00056
    assert llm_cost.estimate_cost("unknown/provider-model", 1000, 100) is None


def test_successful_call_logs_redacted_cost_and_updates_stats(monkeypatch, caplog):
    monkeypatch.setattr(llm_module, "llm_mode", lambda: "on")
    monkeypatch.setenv("BOXAPI_API_KEY", "do-not-log-this-secret")
    client = LLMClient()
    client.model = "gpt-4.1-mini"
    client.fallback_model = ""

    response = SimpleNamespace(
        choices=[SimpleNamespace(message=SimpleNamespace(content='{"ok":true}'))],
        usage={"prompt_tokens": 1000, "completion_tokens": 100},
    )

    class Completions:
        def create(self, **_kwargs):
            return response

    client._client = SimpleNamespace(chat=SimpleNamespace(completions=Completions()))
    llm_cost.reset_stats()
    caplog.set_level(logging.INFO, logger="torobche.llm")
    with llm_node("test-node"):
        assert client.chat_json([{"role": "user", "content": "safe test"}]) == {"ok": True}

    assert "llm_call" in caplog.text
    assert "0.00056" in caplog.text
    assert "do-not-log-this-secret" not in caplog.text
    stats = llm_cost.stats()
    assert stats["total"]["calls"] == 1
    assert stats["by_node"]["test-node"]["calls"] == 1
    assert stats["total"]["cost_usd"] == 0.00056


def test_schema_capability_is_cached_after_response_format_400(monkeypatch):
    monkeypatch.setattr(llm_module, "llm_mode", lambda: "on")
    monkeypatch.setenv("LLM_STRUCTURED", "auto")
    client = LLMClient()
    client.api_key = "test-key"
    client.model = "gpt-4.1-mini"
    client.fallback_model = ""

    class BadRequest(Exception):
        status_code = 400

    def callback(**kwargs):
        if kwargs.get("response_format", {}).get("type") == "json_schema":
            raise BadRequest("response_format json_schema is not supported")
        return SimpleNamespace(
            choices=[SimpleNamespace(message=SimpleNamespace(content='{"ok":true}'))]
        )

    completions = type("Completions", (), {"create": lambda self, **kw: callback(**kw)})()
    client._client = SimpleNamespace(chat=SimpleNamespace(completions=completions))
    schema = {"type": "object", "properties": {"ok": {"type": "boolean"}}}
    assert client.chat_json([{"role": "user", "content": "one"}], response_schema=schema) == {"ok": True}
    assert client._format_support[client.model] == "json_object"
    assert client.chat_json([{"role": "user", "content": "two"}], response_schema=schema) == {"ok": True}


def test_ambiguous_provider_400_falls_back_to_no_response_format(monkeypatch):
    monkeypatch.setattr(llm_module, "llm_mode", lambda: "on")
    monkeypatch.setenv("LLM_STRUCTURED", "json_object")
    client = LLMClient()
    client.api_key = "test-key"
    client.model = "gpt-4.1-mini"
    client.fallback_model = ""

    class BadRequest(Exception):
        status_code = 400

    def reject_format_then_succeed(**kwargs):
        if "response_format" in kwargs:
            raise BadRequest("Provider returned error")
        return SimpleNamespace(choices=[SimpleNamespace(message=SimpleNamespace(content='{"ok":true}'))])

    completions = type("Completions", (), {"create": lambda self, **kw: reject_format_then_succeed(**kw)})()
    client._client = SimpleNamespace(chat=SimpleNamespace(completions=completions))
    assert client.chat_json([{"role": "user", "content": "first"}]) == {"ok": True}
    assert client._format_support[client.model] == "off"
    assert client.chat_json([{"role": "user", "content": "second"}]) == {"ok": True}


def test_message_budget_is_shared_across_router_and_text_calls(monkeypatch):
    monkeypatch.setattr(llm_module, "llm_mode", lambda: "on")
    client = LLMClient()
    client.api_key = "test-key"
    client.model = "primary-model"
    client.fallback_model = "fallback-model"
    class Completions:
        calls: list[dict] = []

        def create(self, **kwargs):
            self.calls.append(kwargs)
            raise TimeoutError("simulated timeout")

    completions = Completions()
    client._client = SimpleNamespace(chat=SimpleNamespace(completions=completions))
    with llm_budget(max_calls=2, timeout_s=1) as budget:
        assert budget.consume() == 1  # action router consumed one request
        assert client.chat_json([{"role": "user", "content": "text response"}]) is None
        assert budget.blocked is True
        assert client.chat_json([{"role": "user", "content": "another node"}]) is None
    assert len(completions.calls) == 1

