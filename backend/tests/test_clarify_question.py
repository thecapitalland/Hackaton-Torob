"""Clarify questions stay about the product, even when the LLM is on."""

from __future__ import annotations

import os

import pytest
from fastapi.testclient import TestClient

from app import graph
from app.main import app
from app.prompts import clarify_messages


@pytest.fixture(scope="module")
def client():
    with TestClient(app) as test_client:
        yield test_client


def test_budget_and_payment_templates_ignore_the_model(monkeypatch):
    def boom(*_args, **_kwargs):
        raise AssertionError("budget and payment questions must not call the model")

    monkeypatch.setattr(graph, "get_client", boom)
    budget = graph._llm_clarify(["budget"], "کفش نایک")
    payment = graph._llm_clarify(["payment"], "هدفون")
    assert budget["text"] == "برای کفش نایک تا چه قیمتی در نظر داری؟"
    assert payment["text"] == "برای هدفون پرداخت قسطی یا ترب‌پی مهم است؟"
    assert "پروژه" not in budget["text"]
    assert "سرویس" not in payment["text"]


def test_location_prompt_names_the_product_and_rejects_drift(monkeypatch):
    seen: dict = {}

    class FakeClient:
        def chat_json(self, messages, **_kwargs):
            seen["messages"] = messages
            return {"text": "پرداخت این سرویس چگونه انجام می‌شود؟"}

    monkeypatch.setattr(graph, "get_client", lambda: FakeClient())
    result = graph._llm_clarify(["location"], "هدفون")
    prompt = clarify_messages({"missing_text": "location", "product": "هدفون"})
    assert "هدفون" in prompt[0]["content"]
    assert "هدفون" in seen["messages"][0]["content"]
    assert "سرویس" not in result["text"]
    assert "پروژه" not in result["text"]
    assert result["text"] == graph.rules.clarify_fallback(["location"], "هدفون")["text"]


def test_live_questions_do_not_mention_project_or_service(client, monkeypatch):
    monkeypatch.setenv("LLM_MODE", "on")
    if not os.environ.get("BOXAPI_API_KEY", "").strip():
        pytest.skip("BOXAPI_API_KEY is not set")
    for text in ("هدفون تا ۴ میلیون", "کفش نایک"):
        session_id = client.post("/api/session").json()["session_id"]
        response = client.post("/api/chat", json={"session_id": session_id, "text": text})
        assert response.status_code == 200, response.text
        body = response.json()
        pending = body.get("pending") or {}
        question = str(pending.get("text") or "")
        assert question, body
        assert "پروژه" not in question
        assert "سرویس" not in question
        if text == "کفش نایک":
            assert pending["id"] == "q_budget"
            assert "تا چه قیمتی" in question
            assert "کفش" in question
