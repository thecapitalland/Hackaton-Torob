"""FIX5 state handling: fresh searches, typed clarify answers, and slot acks."""

from __future__ import annotations

from fastapi.testclient import TestClient

from app.main import app


def _new_session(client: TestClient) -> str:
    return client.post("/api/session").json()["session_id"]


def _chat(client: TestClient, session_id: str, text: str) -> dict:
    response = client.post(
        "/api/chat", json={"session_id": session_id, "text": text}
    )
    assert response.status_code == 200, response.text
    return response.json()


def test_fresh_product_queries_replace_previous_search_state():
    with TestClient(app) as client:
        session_id = _new_session(client)

        first = _chat(client, session_id, "هدفون تا ۳ میلیون")
        assert first["pending"]["id"] == "q_location"
        located = client.post(
            "/api/resume", json={"session_id": session_id, "value": "جمهوری"}
        ).json()
        assert located["cards"]

        fridge = _chat(client, session_id, "یخچال ساید تا ۱۰۰ میلیون")
        assert fridge.get("mode") != "out_of_catalog"
        assert fridge["cards"], "a fresh fridge request must not reuse headphone keywords"
        assert "یخچال" in fridge["slots"]["query"]
        assert fridge["slots"]["budget_max"] == 100_000_000
        assert "هدفون" not in " ".join(fridge["slots"].get("keywords") or [])

        phone = _chat(client, session_id, "گوشی سامسونگ تا ۶۰ میلیون")
        assert phone.get("mode") != "out_of_catalog"
        assert phone["cards"]
        assert "گوشی" in phone["slots"]["query"]
        assert "یخچال" not in " ".join(phone["slots"].get("keywords") or [])

        query_before_refinement = phone["slots"]["query"]
        cheaper = _chat(client, session_id, "ارزون‌تر")
        assert cheaper["slots"]["query"] == query_before_refinement
        assert cheaper["cards"]


def test_product_message_is_not_consumed_as_location_answer():
    with TestClient(app) as client:
        session_id = _new_session(client)
        _chat(client, session_id, "هدفون تا ۳ میلیون")

        result = _chat(client, session_id, "هدفون سونی میخوام فردوسی")

        assert result.get("mode") != "out_of_catalog"
        assert result["cards"], result
        assert result["slots"]["location"]["label"] in {"فردوسی", "میدان فردوسی"}


def test_product_message_updates_budget_while_budget_question_is_pending():
    with TestClient(app) as client:
        session_id = _new_session(client)
        pending = _chat(client, session_id, "گوشی شیائومی")
        assert pending["pending"]["id"] == "q_budget"

        result = _chat(client, session_id, "گوشی شیائومی تا ۲۰ میلیون")

        assert result["slots"]["budget_max"] == 20_000_000
        assert result["pending"]["id"] == "q_location"
        assert result["slots"]["query"] == "گوشی شیائومی تا ۲۰ میلیون"


def test_bare_typed_budget_and_location_still_answer_pending_questions():
    with TestClient(app) as client:
        budget_session = _new_session(client)
        budget_question = _chat(client, budget_session, "گوشی سامسونگ")
        assert budget_question["pending"]["id"] == "q_budget"
        budget_answer = _chat(client, budget_session, "۵ میلیون")
        assert budget_answer["slots"]["budget_max"] == 5_000_000
        assert budget_answer["pending"]["id"] == "q_location"

        location_session = _new_session(client)
        location_question = _chat(client, location_session, "هدفون تا ۳ میلیون")
        assert location_question["pending"]["id"] == "q_location"
        location_answer = _chat(client, location_session, "جمهوری")
        assert location_answer["slots"]["location"]["label"] == "جمهوری"
        assert location_answer["cards"]


def test_other_bare_slot_answer_is_acknowledged_and_open_question_repeats():
    with TestClient(app) as client:
        session_id = _new_session(client)
        pending = _chat(client, session_id, "هدفون تا ۳ میلیون")
        assert pending["pending"]["id"] == "q_location"

        result = _chat(client, session_id, "نقدی")

        assert result["slots"]["installment"] is False
        assert result["pending"]["id"] == "q_location"
        assert any("پرداخت ثبت شد" in message["content"] for message in result["messages"])
