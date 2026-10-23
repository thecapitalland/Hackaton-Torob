"""FIX10: fridge relevance, radius chips, and same-category budget."""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from app.graph import _llm_recommend
from app.main import app
from app.normalize import collapse_whitespace
from app.rules import detect_category, detect_radius, is_accessory_request
from app.tools.catalog import search_score


@pytest.fixture(scope="module")
def client():
    with TestClient(app) as test_client:
        yield test_client


def _finish(client: TestClient, session_id: str, body: dict) -> dict:
    response = client.post("/api/chat", json={"session_id": session_id, **body})
    assert response.status_code == 200, response.text
    payload = response.json()
    for _ in range(3):
        if not payload.get("pending"):
            break
        payload = client.post(
            "/api/resume", json={"session_id": session_id, "value": "مهم نیست"}
        ).json()
    return payload


def test_fridge_category_and_part_score():
    assert detect_category("یخچال") == "یخچال فریزر بالاپایین"
    assert is_accessory_request("لامپ یخچال")
    assert not is_accessory_request("یخچال")
    assert detect_radius("5", bare=True) == (True, 5)
    assert detect_radius("۵ کیلومتر") == (True, 5)
    assert detect_radius("کل تهران") == (True, None)
    assert collapse_whitespace("یخچال\n  فریزر") == "یخچال فریزر"
    fridge = search_score(
        ["یخچال"],
        {"persian_title": "یخچال فریزر", "category_name": "یخچال فریزر بالاپایین", "search_text": "یخچال فریزر"},
        "یخچال فریزر بالاپایین",
    )
    part = search_score(
        ["یخچال"],
        {"persian_title": "ترموسوئیچ یخچال", "category_name": "قطعات و لوازم جانبی یخچال و فریزر", "search_text": "ترموسوئیچ یخچال"},
        "یخچال فریزر بالاپایین",
    )
    assert part < fridge


def test_fridge_budget_returns_fridges_not_parts(client):
    session_id = client.post("/api/session").json()["session_id"]
    first = client.post("/api/chat", json={"session_id": session_id, "text": "یخچال"}).json()
    assert first["pending"]["id"] == "q_budget"
    body = _finish(client, session_id, {"text": "زیر ۳۰ میلیون"})
    assert body["cards"]
    top = body["cards"][:3]
    blob = " ".join(f"{card['title']} {card.get('category_name', '')}" for card in top)
    assert "ترموسوئیچ" not in blob
    assert "لامپ" not in blob
    assert "قطعه" not in blob
    assert "یدکی" not in blob
    assert all("یخچال" in f"{card['title']} {card.get('category_name', '')}" for card in top)


def test_radius_chip_edit_sets_radius(client):
    session_id = client.post("/api/session").json()["session_id"]
    ready = _finish(client, session_id, {"text": "کفش کتونی"})
    budget = ready["slots"].get("budget_max")
    query = ready["slots"]["query"]
    for text, expected in (("5", 5), ("۵ کیلومتر", 5), ("۲ کیلومتر", 2), ("کل تهران", None)):
        edited = client.post(
            "/api/chat",
            json={"session_id": session_id, "edit": {"slot": "radius", "text": text}},
        ).json()
        assert edited["slots"].get("radius_km") == expected
        assert edited["slots"]["query"] == query
        assert edited["slots"].get("budget_max") == budget


def test_same_category_refine_keeps_budget(client):
    session_id = client.post("/api/session").json()["session_id"]
    first = client.post("/api/chat", json={"session_id": session_id, "text": "کفش کتونی"}).json()
    assert first["pending"]["id"] == "q_budget"
    ready = _finish(client, session_id, {"text": "7000000"})
    assert ready["slots"]["budget_max"] == 7_000_000
    refined = _finish(client, session_id, {"text": "کفش ورزشی نایک"})
    assert refined["slots"]["budget_max"] == 7_000_000
    assert "نایک" in (refined["slots"].get("query") or "")
    chip = _finish(
        client,
        session_id,
        {"edit": {"slot": "product", "text": "کفش نایک"}},
    )
    assert chip["slots"]["budget_max"] == 7_000_000
    assert "کفش" in (chip["slots"].get("query") or "")
    changed = client.post("/api/chat", json={"session_id": session_id, "text": "هدفون"}).json()
    assert changed["slots"].get("budget_max") != 7_000_000


def test_sony_case_keeps_phone_word(client):
    session_id = client.post("/api/session").json()["session_id"]
    body = _finish(client, session_id, {"text": "قاب گوشی سونی"})
    assert "گوشی" in (body["slots"].get("query") or "")
    if body.get("mode") == "out_of_catalog":
        assert body["ooc"]["message_fa"].startswith("این کالا رو نداریم")
        assert body["ooc"]["alternatives"]
    else:
        assert body["cards"]
        assert all("باتری" not in card["title"] for card in body["cards"])
        assert any(token in card["title"] for card in body["cards"] for token in ("قاب", "کاور", "درب"))


def test_greeting_after_results_does_not_restart(client):
    session_id = client.post("/api/session").json()["session_id"]
    ready = _finish(client, session_id, {"text": "کفش کتونی"})
    query = ready["slots"]["query"]
    greeted = client.post("/api/chat", json={"session_id": session_id, "text": "سلام"}).json()
    message = greeted["messages"][-1]["content"]
    assert "سلام" in message
    assert "دقیق" in message
    assert "چه کالایی" not in message
    assert greeted["cards"]
    assert greeted["slots"]["query"] == query


def test_card_titles_have_no_newline(client):
    session_id = client.post("/api/session").json()["session_id"]
    ready = _finish(client, session_id, {"text": "هدفون"})
    assert ready["cards"]
    assert all("\n" not in card["title"] and "  " not in card["title"] for card in ready["cards"])


def test_refine_skips_recommend_llm(client, monkeypatch):
    session_id = client.post("/api/session").json()["session_id"]
    _finish(client, session_id, {"text": "هدفون تا ۳ میلیون"})

    def boom(*_args, **_kwargs):
        raise AssertionError("recommend llm should not run on a pure refine")

    monkeypatch.setattr("app.graph._llm_recommend", boom)
    refined = client.post("/api/chat", json={"session_id": session_id, "text": "ارزون‌تر"}).json()
    assert refined["cards"]
    assert _llm_recommend  # the real function remains importable
