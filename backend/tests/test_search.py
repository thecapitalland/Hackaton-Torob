"""Search / ranking tests against the real catalog."""

from __future__ import annotations

import pytest

from app import rules
from app.graph import _search_with_fallback
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


def test_laptop_keywords_never_leak_usage_words(catalog_path):
    text = "لپ تاپ ایسوس برای برنامه نویسی تا ۵۰ میلیون"
    category = rules.detect_category(text, catalog.all_category_names())
    assert category == "لپ تاپ و نوت بوک"
    keywords = rules.extract_keywords(text, category)
    assert "تاپ" not in keywords
    assert "لپ" not in keywords
    for usage_word in ("برای", "برنامه", "نویسی", "میخوام"):
        assert usage_word not in keywords
    assert "ایسوس" in keywords


def test_laptop_query_returns_an_asus_card(catalog_path):
    text = "لپ تاپ ایسوس برای برنامه نویسی تا ۵۰ میلیون"
    category = rules.detect_category(text, catalog.all_category_names())
    budget_max, budget_min = rules.parse_budget(text)
    slots = {
        "category": category,
        "keywords": rules.extract_keywords(text, category),
        "budget_max": budget_max,
        "budget_min": budget_min,
    }
    candidates, _ = _search_with_fallback(slots)
    assert candidates, "the laptop query must not fall through to out_of_catalog"
    cards = catalog.pick_cards(candidates, budget_max)
    assert cards
    asus = [
        card
        for card in cards
        if "ایسوس" in f"{card.get('persian_title', '')} {card.get('brand_name', '')}"
    ]
    assert asus, [card.get("persian_title") for card in cards]


def test_three_laptop_candidates_produce_three_cards(catalog_path):
    candidates = catalog.search_products(
        [], "لپ تاپ و نوت بوک", budget_max=500_000_000, limit=30, min_shops=1
    )
    assert len(candidates) >= 3
    cards = catalog.pick_cards(candidates, 500_000_000)
    assert len(cards) == 3
    assert [card["kind"] for card in cards] == ["best", "budget", "premium"]


# --------------------------------------------------------------------------
# B3: honest ranking «why»
# --------------------------------------------------------------------------


def test_why_labels_only_the_real_cheapest(catalog_path):
    """B3: «ارزان‌ترین قیمت» must appear only on the actual cheapest shop."""
    from app.tools import ranking

    offers = catalog.get_offers_for_product(R50I)
    slots = {"location": {"lat": 35.7, "lon": 51.42, "label": "آزمون"}}
    options = ranking.build_shop_options(offers, slots, ranking_hours_now(), 27)
    options = ranking.rank_shops(options, slots, ranking_hours_now())
    prices = [option["price"] for option in options if option.get("price")]
    cheapest = min(prices)
    labelled = [
        option for option in options if "ارزان‌ترین قیمت" in (option.get("why") or "")
    ]
    assert labelled
    for option in labelled:
        assert option["price"] == cheapest, (
            option["name"],
            option["price"],
            option["why"],
        )
    others = [option for option in options if option["price"] != cheapest]
    for option in others:
        if option.get("haggle", {}).get("label") == "good":
            continue
        assert "ارزان‌ترین قیمت" not in (option.get("why") or ""), option["why"]


def ranking_hours_now():
    from app.tools.hours import now_tehran

    return now_tehran()


# --------------------------------------------------------------------------
# B5: trip backup must not repeat a real stop
# --------------------------------------------------------------------------


def test_trip_backup_is_never_a_chosen_stop(catalog_path):
    from app import graph

    state = graph.find_stores(
        {"product_id": R50I, "slots": {"installment": False, "today": True}}
    )
    shops = state.get("shops") or []
    assert len(shops) >= 3
    state["shop_ids"] = [shops[0]["shop_id"], shops[1]["shop_id"]]
    result = graph.build_trip(state)
    trip = result["trip"]
    stop_ids = [stop["shop_id"] for stop in trip["stops"]]
    if trip["backup"]:
        assert trip["backup"]["shop_id"] not in stop_ids


def test_trip_backup_prefers_a_verified_shop(catalog_path):
    from app import graph

    state = graph.find_stores(
        {"product_id": R50I, "slots": {"installment": False, "today": True}}
    )
    shops = state.get("shops") or []
    chosen = shops[0]
    verified = next(shop for shop in shops[1:] if shop["price"])
    state["shop_ids"] = [chosen["shop_id"]]
    state["followups"] = [
        {
            "shop_id": verified["shop_id"],
            "parsed": {"availability": "available", "offer_status": "confirmed"},
        }
    ]
    result = graph.build_trip(state)
    backup = result["trip"]["backup"]
    assert backup, "expected a backup shop"
    assert backup["shop_id"] == verified["shop_id"]
