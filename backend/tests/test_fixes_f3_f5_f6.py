"""FIX6 backend cases covered by the GapGPT/decision integration layer."""

from __future__ import annotations

from fastapi.testclient import TestClient

from app import rules
from app.main import app


def test_rules_classify_budget_radius_and_brand_area_refinements():
    old = {"slots": {"query": "هدفون", "category": "هدفون، هدست و هندزفری", "budget_max": 3_000_000}}
    refine = rules.rule_intent("بالای ۱۰ میلیون هم بگرد", old)
    assert refine["action"] == "refine"
    assert refine["budget_min"] == 10_000_000
    assert refine["clear_budget_max"] is True

    radius = rules.rule_intent("۵ کیلومتر", old)
    assert radius == {"action": "change_radius", "radius_km": 5, "confidence": 1.0}

    f6 = rules.rule_intent(
        "هدفون سونی می‌خوام فردوسی",
        old,
        known_categories=["هدفون، هدست و هندزفری"],
        known_brands=["سونی"],
    )
    assert f6["action"] == "new_search"
    assert f6["brand"] == "سونی"
    assert f6["area"] == "فردوسی"
    assert f6["query"] == "هدفون سونی"


def test_set_radius_endpoint_repeats_search_without_changing_query():
    with TestClient(app) as client:
        session = client.post("/api/session").json()["session_id"]
        initial = client.post(
            "/api/chat",
            json={
                "session_id": session,
                "text": "هدفون تا ۳ میلیون",
                "location": {"lat": 35.6925, "lon": 51.4105},
            },
        ).json()
        if initial.get("pending"):
            initial = client.post("/api/resume", json={"session_id": session, "value": "مهم نیست"}).json()
        query = initial["slots"]["query"]
        changed = client.post("/api/radius", json={"session_id": session, "radius_km": 5})
        assert changed.status_code == 200, changed.text
        body = changed.json()
        assert body["slots"]["radius_km"] == 5
        assert body["slots"]["query"] == query
        assert body["cards"]


def test_f3_budget_refinement_clears_ceiling_and_keeps_headphones():
    with TestClient(app) as client:
        session = client.post("/api/session").json()["session_id"]
        first = client.post(
            "/api/chat",
            json={
                "session_id": session,
                "text": "هدفون تا ۳ میلیون",
                "location": {"lat": 35.6925, "lon": 51.4105},
            },
        ).json()
        if first.get("pending"):
            first = client.post("/api/resume", json={"session_id": session, "value": "مهم نیست"}).json()
        old_query = first["slots"]["query"]

        refined = client.post(
            "/api/chat", json={"session_id": session, "text": "بالای ۱۰ میلیون هم بگرد"}
        ).json()
        assert refined["decision"]["intent"]["action"] == "refine"
        assert refined["slots"]["query"] == old_query
        assert refined["slots"]["budget_min"] == 10_000_000
        assert refined["slots"]["budget_max"] is None
        assert refined["cards"]
        assert all(card["min_price"] >= 10_000_000 for card in refined["cards"])


def test_f6_typed_brand_and_area_win_on_open_clarify():
    with TestClient(app) as client:
        session = client.post("/api/session").json()["session_id"]
        pending = client.post(
            "/api/chat", json={"session_id": session, "text": "هدفون تا ۳ میلیون"}
        ).json()
        assert pending["pending"]["id"] == "q_location"

        result = client.post(
            "/api/chat",
            json={"session_id": session, "text": "هدفون سونی می‌خوام فردوسی"},
        ).json()
        assert result.get("mode") != "out_of_catalog"
        assert result["slots"]["brand"] == "سونی"
        assert result["slots"]["location"]["label"] in {"فردوسی", "میدان فردوسی"}
        assert result["decision"]["intent"]["action"] == "new_search"
        assert result["cards"]
        assert all("سونی" in card["title"] or card["brand"] == "سونی" for card in result["cards"])
