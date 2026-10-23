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
    assert result["verdict_label"] == "تصمیم با تو"
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
    assert compare["verdict_label"] == "تصمیم با تو"
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
