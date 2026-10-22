"""Search / ranking tests against the real catalog."""

from __future__ import annotations

import pytest

from app.tools import catalog

R50I = "product_92ac53fa75e18e8e73f20b56"
HEADPHONES = "هدفون، هدست و هندزفری"
PHONES = "گوشی موبایل"


def test_headphone_under_4m_contains_r50i(catalog_path):
    results = catalog.search_products(
        ["هدفون", "بلوتوث"], HEADPHONES, budget_max=4_000_000, limit=30
    )
    assert results, "no headphone found"
    ids = [item["product_id"] for item in results]
    assert R50I in ids[:3], f"R50i not in top 3: {ids[:5]}"
    assert results[0]["n_shops"] >= 2


def test_headphone_search_is_not_empty_without_budget(catalog_path):
    results = catalog.search_products(["هدفون"], HEADPHONES, limit=30)
    assert len(results) >= 3


def test_samsung_phone_under_60m(catalog_path):
    results = catalog.search_products(
        ["گوشی", "سامسونگ"], PHONES, budget_max=60_000_000, limit=30
    )
    titles = " ".join(item["persian_title"] or "" for item in results)
    assert "A07" in titles or "A17" in titles, titles[:400]


def test_a55_returns_phone_not_lcd(catalog_path):
    results = catalog.search_products(["A55"], PHONES, limit=30)
    assert results
    for item in results:
        assert item["category_name"] == PHONES
        assert "ال سی دی" not in (item["category_name"] or "")


def test_budget_filter_is_respected(catalog_path):
    results = catalog.search_products(["هدفون"], HEADPHONES, budget_max=1_000_000, limit=30)
    for item in results:
        assert item["min_price"] <= 1_000_000


def test_pick_cards_returns_distinct_kinds(catalog_path):
    results = catalog.search_products(["هدفون"], HEADPHONES, budget_max=4_000_000, limit=30)
    cards = catalog.pick_cards(results, 4_000_000)
    kinds = [card["kind"] for card in cards]
    assert kinds[0] == "best"
    assert len(set(card["product_id"] for card in cards)) == len(cards)
    assert "budget" in kinds
    assert "premium" in kinds


def test_offer_count_for_r50i(catalog_path):
    offers = catalog.get_offers_for_product(R50I)
    assert len(offers) >= 5
    prices = [offer["price_toman"] for offer in offers]
    assert max(prices) <= 3 * 3_150_000, "outlier price was not removed"


def test_search_score_category_factor(catalog_path):
    results = catalog.search_products(["هدفون"], HEADPHONES, limit=5)
    if not results:
        pytest.skip("catalog has no headphone")
    product = results[0]
    full = catalog.search_score(["هدفون"], product, HEADPHONES)
    partial = catalog.search_score(["هدفون"], product, None)
    assert full == pytest.approx(1.0)
    assert partial == pytest.approx(0.6)
