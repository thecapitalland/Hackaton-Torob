"""FIX9: typed budget, neighbourhood search, and relevance guards."""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.normalize import search_neighbourhoods
from app.rules import detect_brand, detect_category, parse_budget


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("7000000", 7_000_000),
        ("۷۰۰۰۰۰۰", 7_000_000),
        ("7,000,000", 7_000_000),
        ("هفت میلیون", 7_000_000),
        ("ده میلیون", 10_000_000),
        ("هفتصد هزار", 700_000),
        ("7m", 7_000_000),
        ("7M", 7_000_000),
        ("زیر ۷", 7_000_000),
        ("تا ۷", 7_000_000),
        ("۷ تومن", 7_000_000),
        ("۷۰۰ هزار", 700_000),
    ],
)
def test_parse_budget_accepts_colloquial_amounts(text, expected):
    budget_max, _budget_min = parse_budget(text, budget_context=True)
    assert budget_max == expected


def test_budget_words_do_not_become_a_product_query():
    from app.rules import dedupe_query_text, is_budget_only

    assert is_budget_only("هفت میلیون")
    assert dedupe_query_text("کفش ورزشی ورزشی") == "کفش ورزشی"
    assert dedupe_query_text("کفش نایک نایکی") == "کفش نایک"


def test_radius_phrase_is_not_a_brand():
    from app.tools import catalog

    assert detect_brand("شعاع ۵ کیلومتر", catalog.all_brands()) is None


def test_head_noun_beats_brand_category():
    from app.tools import catalog

    known = catalog.all_category_names()
    assert detect_category("هدفون سامسونگ", known) == "هدفون، هدست و هندزفری"


def test_neighbourhood_search_ranks_exact_name_first():
    names = [item["name_fa"] for item in search_neighbourhoods("ونک")]
    assert names[0] == "ونک"
    assert "پونک" in names
    assert names.index("ونک") < names.index("پونک")
    assert search_neighbourhoods("آجودانیه")[0]["name_fa"] == "آجودانیه"
    assert search_neighbourhoods("سید خندان")[0]["name_fa"] == "سیدخندان"
    assert search_neighbourhoods("پاسداران")[0]["name_fa"] == "پاسداران"


@pytest.fixture(scope="module")
def client():
    with TestClient(app) as test_client:
        yield test_client


def _cards_for(client: TestClient, text: str) -> dict:
    session_id = client.post("/api/session").json()["session_id"]
    response = client.post("/api/chat", json={"session_id": session_id, "text": text})
    assert response.status_code == 200
    body = response.json()
    if body.get("pending"):
        body = client.post(
            "/api/resume", json={"session_id": session_id, "value": "مهم نیست"}
        ).json()
        if body.get("pending"):
            body = client.post(
                "/api/resume", json={"session_id": session_id, "value": "مهم نیست"}
            ).json()
    return body


def test_typed_budget_after_product_shows_cards(client):
    session_id = client.post("/api/session").json()["session_id"]
    first = client.post("/api/chat", json={"session_id": session_id, "text": "کفش کتونی"}).json()
    assert first["pending"]["id"] == "q_budget"
    second = client.post("/api/chat", json={"session_id": session_id, "text": "7000000"}).json()
    if second.get("pending"):
        second = client.post(
            "/api/resume", json={"session_id": session_id, "value": "مهم نیست"}
        ).json()
    assert second["cards"]
    assert second["slots"]["budget_max"] == 7_000_000
    assert "7000000" not in (second["slots"].get("query") or "")
    assert "هفت" != (second["slots"].get("query") or "")


def test_relevance_queries(client):
    chargers = _cards_for(client, "شارژر لپتاپ")
    assert chargers["cards"]
    assert all("شارژر" in card["title"] for card in chargers["cards"])

    cases = _cards_for(client, "قاب گوشی سونی")
    if cases.get("mode") == "out_of_catalog":
        assert "پیدا نکردم" in (cases["messages"][-1]["content"] if cases["messages"] else "") or cases.get("ooc")
    else:
        assert cases["cards"]
        assert all("باتری" not in card["title"] for card in cases["cards"])
        assert any(token in card["title"] for card in cases["cards"] for token in ("قاب", "کاور", "درب"))

    fridges = _cards_for(client, "یخچال")
    assert fridges["cards"]
    blob = " ".join(f"{card['title']} {card.get('category_name', '')}" for card in fridges["cards"])
    assert "یخدان" not in blob
    assert "مسافرت" not in blob

    headphones = _cards_for(client, "هدفون سامسونگ")
    assert headphones["slots"]["category"] == "هدفون، هدست و هندزفری"
    assert headphones["cards"]
    assert all("گوشی" not in (card.get("category_name") or "") for card in headphones["cards"])


_VANAK = {"lat": 35.757, "lon": 51.41, "label": "ونک"}


def _finish(client: TestClient, session_id: str, body: dict) -> dict:
    response = client.post("/api/chat", json={"session_id": session_id, **body})
    assert response.status_code == 200
    payload = response.json()
    for _ in range(3):
        if not payload.get("pending"):
            break
        payload = client.post(
            "/api/resume", json={"session_id": session_id, "value": "مهم نیست"}
        ).json()
    return payload


def test_later_location_is_not_overwritten_by_previous_hood(client):
    session_id = client.post("/api/session").json()["session_id"]
    first = _finish(client, session_id, {"text": "کفش کتونی در ونک"})
    assert first["slots"]["location"]["label"] == "ونک"
    moved = client.post(
        "/api/chat",
        json={
            "session_id": session_id,
            "text": "در پاسداران بگرد",
            "location": _VANAK,
        },
    ).json()
    assert moved["slots"]["location"]["label"] == "پاسداران"
    edited = client.post(
        "/api/chat",
        json={
            "session_id": session_id,
            "edit": {"slot": "location", "text": "سید خندان"},
            "location": {"lat": 35.7708, "lon": 51.4622, "label": "پاسداران"},
        },
    ).json()
    assert edited["slots"]["location"]["label"] == "سیدخندان"
    typed = client.post(
        "/api/chat",
        json={
            "session_id": session_id,
            "text": "در پاسداران بگرد",
            "location": {"lat": 35.7575, "lon": 51.448, "label": "سیدخندان"},
        },
    ).json()
    assert typed["slots"]["location"]["label"] == "پاسداران"


def test_product_chip_replaces_search(client):
    session_id = client.post("/api/session").json()["session_id"]
    first = _finish(client, session_id, {"text": "کفش کتونی", "location": _VANAK})
    assert first["cards"]
    edited = _finish(
        client,
        session_id,
        {
            "edit": {"slot": "product", "text": "یخچال"},
            "location": _VANAK,
        },
    )
    assert "یخچال" in (edited["slots"].get("query") or "")
    assert "کفش" not in (edited["slots"].get("query") or "")
    assert edited["cards"]
    blob = " ".join(card["title"] for card in edited["cards"])
    assert "یخچال" in blob
    assert "یخدان" not in blob
    assert edited["slots"]["location"]["label"] == "ونک"
    typed = _finish(client, session_id, {"text": "هدفون", "location": _VANAK})
    assert "هدفون" in (typed["slots"].get("query") or "")
    assert "یخچال" not in (typed["slots"].get("query") or "")
    assert typed["cards"]
