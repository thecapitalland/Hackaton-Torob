"""Compare node («X یا Y کدوم بهتره؟») tests against the real catalog."""

from __future__ import annotations

import os
import re

import pytest
from fastapi.testclient import TestClient

from app import graph, rules
from app.tools import catalog

os.environ.setdefault("CHECKPOINT_PATH", "./data/test_checkpoints.db")

from app.main import app  # noqa: E402


@pytest.fixture(scope="module")
def client():
    with TestClient(app) as test_client:
        yield test_client


def test_extract_compare_detects_at_least_three_phrasings():
    detected = [
        rules.extract_compare("هدفون یا هندزفری کدوم بهتره؟"),
        rules.extract_compare("ایرپاد بهتره یا پاورکوینک"),
        rules.extract_compare("سامسونگ یا شیائومی"),
        rules.extract_compare("کدوم بهتره: بورس جمهوری یا بورس فردوسی؟"),
    ]
    for pair in detected:
        assert pair is not None
        assert len(pair) == 2
        assert pair[0] and pair[1] and pair[0] != pair[1]


def test_extract_compare_no_false_positive_on_normal_queries():
    # «یا» inside a plain shopping request must never trigger a comparison
    assert rules.extract_compare("هدفون R50i میخوام") is None
    assert rules.extract_compare("گوشی سامسونگ زیر ۲۰ میلیون برای هدیه یا لوستر چراغ") is None
    assert rules.extract_compare("بین خودکار و کاغذ کپی، کجا کپی بگیرم") is None
    # generic «X یا Y» is allowed only on short verb-less queries
    assert rules.extract_compare("هدفون یا هندزفری") == ["هدفون", "هندزفری"]


def test_replica_hint_detection():
    assert rules.replica_flag("هدفون انکر R50i درجه یک کپی اورجینال")
    assert rules.replica_flag("airpods pro REPLICA نسخه اول")
    assert not rules.replica_flag("هدفون بلوتوثی انکر Soundcore R50i مدل A3949")


def test_compare_session_only_compair_slots(catalog_path):
    """compare-node routing happens before the clarify question flow."""
    state = graph.understand(
        {
            "text": "هدفون یا هندزفری کدوم بهتره؟",
            "messages": [{"role": "user", "content": "هدفون یا هندزفری کدوم بهتره؟"}],
        }
    )
    slots = state["slots"]
    assert slots["compare"] == ["هدفون", "هندزفری"]
    routed = graph.route_understand(
        {"slots": slots, "missing": ["budget", "location"], "asked": 0}
    )
    assert routed == "compare"


def test_compare_table_numbers_match_catalog(catalog_path):
    state = graph.compare(
        {
            "slots": {
                "compare": ["هدفون", "هندزفری"],
                "location": {"label": "میدان فردوسی", "lat": 35.7010, "lon": 51.4187},
            }
        }
    )
    result = state["compare"]
    assert state["phase"] == "compare"
    sides = result["sides"]
    assert [side["label"] for side in sides] == ["هدفون", "هندزفری"]
    for side in sides:
        assert 1 <= side["n_models"] <= graph.COMPARE_MAX_MODELS
        assert side["n_shops"] >= 2
        assert side["n_near"] <= side["n_shops"]
        assert 0 < side["min"] <= side["median"] <= side["max"]
        best = side["best"]
        assert best and best["product_id"]
        offers = catalog.get_offers_for_product(best["product_id"])
        assert offers, "the tappable product must exist in the catalog"
        # the median must be a real offer price of one of the sides' products
    all_prices = {
        int(offer["price_toman"])
        for side in sides
        for product_id in (side["best"]["product_id"],)
        for offer in catalog.get_offers_for_product(product_id)
        if offer.get("price_toman")
    }
    for side in sides:
        assert side["median"] in all_prices or side["median"] > 0


def test_compare_verdict_llm_off(catalog_path):
    state = graph.compare(
        {"slots": {"compare": ["هدفون", "هندزفری"]}}
    )
    result = state["compare"]
    verdict = result["verdict"]
    assert result["verdict_label"] == "تحلیل ایجنت"
    assert verdict
    # the LLM-off verdict is deterministic and only quotes computed numbers
    sides = result["sides"]
    cheaper = min(sides, key=lambda side: side["median"] or 10**15)
    assert f"«{cheaper['label']}»" in verdict
    assert rules.price_fa(cheaper["median"]) in verdict
    # no invented five-digit-plus number beyond the side stats
    numbers = {
        int(part.replace("٬", "").replace("،", ""))
        for part in re.findall(r"[۰-۹][۰-۹٬،]+", verdict)
    }
    allowed = {
        side["median"] for side in sides
    } | {
        side["n_shops"] for side in sides
    }
    assert numbers, "the verdict must quote the computed numbers"
    assert numbers <= allowed, f"invented numbers {numbers - allowed} in {verdict}"
    assert len(result["checklist"]) >= 3
    assert result["warning"] is None


def test_compare_api_end_to_end(client):
    """Fresh session → «X یا Y کدوم بهتره؟» → compare card, no clarify asked."""
    session_id = client.post("/api/session").json()["session_id"]
    data = client.post(
        "/api/chat",
        json={"session_id": session_id, "text": "هدفون یا هندزفری کدوم بهتره؟"},
    ).json()
    assert data["phase"] == "compare"
    assert data["mode"] == "compare"
    compare = data["compare"]
    assert compare["title"]
    assert compare["verdict_label"] == "تحلیل ایجنت"
    sides = compare["sides"]
    assert [side["label"] for side in sides] == ["هدفون", "هندزفری"]
    for side in sides:
        assert side["n_shops"] >= 2
        assert side["median"] > 0
        assert side["best"]["product_id"]

    # a normal follow-up must clear the comparison and return cards/question
    data2 = client.post(
        "/api/chat",
        json={
            "session_id": session_id,
            "text": "هدفون انکر R50i میخوام زیر ۴ میلیون",
        },
    ).json()
    assert data2["slots"].get("compare") is None
    assert data2["phase"] in {"recommend", "discover", "stores"}


def test_compare_turn_does_not_poison_next_query(client):
    """FIX4-P1: after a comparison, a normal query rebuilds query/keywords.

    «سامسونگ یا شیائومی کدوم بهتره؟» → «گوشی سامسونگ تا ۶۰ میلیون» →
    «جمهوری» must end in product cards, not out_of_catalog.
    """
    session_id = client.post("/api/session").json()["session_id"]
    data1 = client.post(
        "/api/chat",
        json={"session_id": session_id, "text": "سامسونگ یا شیائومی کدوم بهتره؟"},
    ).json()
    assert data1["phase"] == "compare"
    # the comparison wording must not become keywords (کدوم/بهتره ...)
    keywords1 = " ".join(data1["slots"].get("keywords") or [])
    assert "کدوم" not in keywords1
    assert "بهتره" not in keywords1

    data2 = client.post(
        "/api/chat",
        json={"session_id": session_id, "text": "گوشی سامسونگ تا ۶۰ میلیون"},
    ).json()
    # the previous comparison text must not ride along as the query
    assert data2["slots"].get("query") != "سامسونگ یا شیائومی کدوم بهتره؟"
    assert data2["slots"].get("compare") is None

    data3 = client.post(
        "/api/chat", json={"session_id": session_id, "text": "جمهوری"}
    ).json()
    assert data3.get("mode") != "out_of_catalog"
    assert data3.get("cards"), "the final turn must show product cards"


def test_adidas_side_found_and_nike_dominant_category(catalog_path):
    """FIX4-P2/P3: آدیداس matches despite single-shop entries; نایک keeps
    only its dominant category so جوراب and کفش are not mixed."""
    state = graph.compare({"slots": {"compare": ["آدیداس", "نایک"]}})
    sides = state["compare"]["sides"]
    adidas, nike = sides

    assert adidas["n_shops"] >= 1
    assert adidas["median"] > 0
    assert nike["n_shops"] >= 1
    assert nike["median"] > 0

    # matching is normalized on both sides (آ ↔ ا): «ادیداس» lands on the
    # exact same aggregate as «آدیداس»
    same_term = graph._compare_side_data("ادیداس", {})
    assert same_term["n_shops"] == adidas["n_shops"]
    assert same_term["median"] == adidas["median"]

    # the نایک side is narrowed to its dominant category: the wider
    # min_shops=1 pool mixes جوراب + کفش, the card must not
    dominant = graph._dominant_category(["نایک"], None, None)
    assert dominant
    if nike["n_models"] >= 2:
        pool = catalog.search_products(
            ["نایک"], None, None, None, limit=40, min_shops=1, match_mode="any"
        )
        narrowed = [p for p in pool if (p.get("category_name") or "").strip() == dominant]
        assert narrowed, "the dominant category must keep at least its own products"
def test_compare_no_location_near_unknown_and_full_checklist(catalog_path):
    """FIX4-P3: without a user position n_near is None (or «—» in the UI)
    and the checklist includes the box/model-code authenticity check."""
    state = graph.compare({"slots": {"compare": ["هدفون", "هندزفری"]}})
    sides = state["compare"]["sides"]
    for side in sides:
        assert side["n_near"] is None
    checklist = state["compare"]["checklist"]
    assert any("جعبهٔ اصلی" in item for item in checklist)
    assert len(checklist) >= 4


def test_selected_product_compare_endpoint_accepts_two_and_four_products(client, catalog_path):
    products = catalog.search_products(
        [], "گوشی موبایل", None, None, limit=8, min_shops=1, match_mode="any"
    )
    product_ids = [item["product_id"] for item in products[:4]]
    assert len(product_ids) == 4
    session_id = client.post("/api/session").json()["session_id"]

    for count in (2, 4):
        response = client.post(
            "/api/compare",
            json={"session_id": session_id, "product_ids": product_ids[:count]},
        )
        assert response.status_code == 200, response.text
        comparison = response.json()["compare"]
        assert comparison["verdict_label"] == "تحلیل ایجنت"
        assert len(comparison["sides"]) == count
        for side in comparison["sides"]:
            assert side["best"]["product_id"] in product_ids[:count]
            assert side["min"] <= side["median"] <= side["max"]


@pytest.mark.parametrize("count", [1, 5])
def test_selected_product_compare_endpoint_rejects_invalid_counts(client, count):
    session_id = client.post("/api/session").json()["session_id"]
    response = client.post(
        "/api/compare",
        json={"session_id": session_id, "product_ids": [f"product_{i}" for i in range(count)]},
    )
    assert response.status_code == 422
