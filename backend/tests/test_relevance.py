"""P0-1 search relevance checks against the real slim catalog."""

from __future__ import annotations

from app import graph, rules
from app.normalize import ACCESSORY_WORDS, normalize, tokenize


def _recommend(query: str) -> tuple[list[dict], list[dict]]:
    extracted = graph._rule_extract(query)
    slots = {**extracted, "query": query}
    candidates, _ = graph._search_with_fallback(slots)
    result = graph.recommend({"slots": slots, "candidates": candidates})
    return candidates, result["cards"]


def _has_unrequested_accessory(title: str, query: str) -> bool:
    title_tokens = set(tokenize(title))
    query_tokens = set(tokenize(query))
    return any(word not in query_tokens and word in title_tokens for word in ACCESSORY_WORDS)


def test_core_noun_and_spelling_aliases():
    assert rules.core_noun("کفش کتونی") == "کتونی"
    assert rules.core_noun("کتونی نایک تا ۵ میلیون") == "کتونی"
    assert rules.core_noun("هدفون تا ۳ میلیون") == "هدفون"
    assert rules.core_noun("گوشی سامسونگ") == "گوشی"
    assert rules.core_noun("گوشی موبایل", "گوشی موبایل") == "گوشی"
    assert rules.core_noun("شارژر لپتاپ") == "شارژر"
    assert rules.core_noun("یخچال ساید") == "یخچال"
    assert rules.core_noun("مانیتور") == "مانیتور"
    assert rules.detect_category("شارژر لپتاپ ایسوس", ["شارژر لپ تاپ"]) == "شارژر لپ تاپ"


def test_kafsh_ketooni_returns_three_relevant_shoe_cards(catalog_path):
    candidates, cards = _recommend("کفش کتونی")
    assert len(candidates) >= 3
    assert len(cards) >= 3
    by_id = {item["product_id"]: item for item in candidates}
    for item in candidates:
        assert item["category_name"] == "کتانی و کفش اسپرت"
    for card in cards:
        item = by_id[card["product_id"]]
        assert item["category_name"] == "کتانی و کفش اسپرت"
        assert not _has_unrequested_accessory(card["title"], "کفش کتونی")


def test_nike_sneaker_search_keeps_brand_and_budget(catalog_path):
    query = "کتونی نایک تا ۵ میلیون"
    candidates, cards = _recommend(query)
    assert len(cards) >= 2
    by_id = {item["product_id"]: item for item in candidates}
    for item in candidates:
        brand_and_title = normalize(
            f"{item.get('brand_name') or item.get('brand') or ''} "
            f"{item.get('persian_title') or item.get('title') or ''}"
        )
        assert any(alias in brand_and_title for alias in ("نایک", "نایکی", "nike"))
        assert int(item.get("min_price") or 0) <= 5_000_000
        assert not _has_unrequested_accessory(item.get("persian_title") or item.get("title") or "", query)
    for card in cards:
        item = by_id[card["product_id"]]
        assert any(alias in normalize(f"{item.get('brand_name') or ''} {card['title']}") for alias in ("نایک", "نایکی", "nike"))
        assert card["min_price"] <= 5_000_000
        assert not _has_unrequested_accessory(card["title"], query)


def test_generic_shoe_query_excludes_wax_and_cover_accessories(catalog_path):
    candidates, cards = _recommend("کفش")
    assert cards
    for item in candidates:
        assert not _has_unrequested_accessory(item.get("persian_title") or item.get("title") or "", "کفش")
    for card in cards:
        assert not _has_unrequested_accessory(card["title"], "کفش")


def test_headphones_and_samsung_phones_remain_relevant(catalog_path):
    for query, expected_category, expected_brand in (
        ("هدفون تا ۳ میلیون", "هدفون، هدست و هندزفری", None),
        ("گوشی سامسونگ", "گوشی موبایل", "سامسونگ"),
    ):
        candidates, cards = _recommend(query)
        assert cards
        by_id = {item["product_id"]: item for item in candidates}
        for item in candidates:
            assert item["category_name"] == expected_category
            if expected_brand:
                assert expected_brand in normalize(
                    f"{item.get('brand_name') or ''} {item.get('persian_title') or item.get('title') or ''}"
                )
            assert not _has_unrequested_accessory(
                item.get("persian_title") or item.get("title") or "", query
            )
        for card in cards:
            item = by_id[card["product_id"]]
            assert item["category_name"] == expected_category
            if expected_brand:
                assert expected_brand in normalize(f"{item.get('brand_name') or ''} {card['title']}")
            assert not _has_unrequested_accessory(card["title"], query)


def test_refrigerator_search_excludes_filters_stabilizers_and_protectors(catalog_path):
    candidates, cards = _recommend("یخچال")
    assert cards
    forbidden = {"فیلتر", "استابلایزر", "ترانس", "رگولاتور", "محافظ"}
    for item in [*candidates, *cards]:
        title = item.get("persian_title") or item.get("title") or ""
        assert not (forbidden & set(tokenize(title)))


def test_laptop_charger_keeps_charger_as_core_noun(catalog_path):
    candidates, cards = _recommend("شارژر لپتاپ")
    assert cards
    assert all(item["category_name"] == "شارژر لپ تاپ" for item in candidates)
    slots = {**graph._rule_extract("شارژر لپتاپ"), "query": "شارژر لپتاپ"}
    state = {"slots": slots, "text": "شارژر لپتاپ"}
    state.update(graph.search(state))
    assert graph.route_after_search(state) == "recommend"


def test_plain_monitor_defaults_to_computer_monitor_category(catalog_path):
    candidates, cards = _recommend("مانیتور")
    assert cards
    assert all(item["category_name"] == "مانیتور" for item in candidates)


def test_headphone_candidates_have_no_normalized_duplicate_titles(catalog_path):
    candidates, _cards = _recommend("هدفون بلوتوثی")
    keys = [graph._normalized_title_key(item) for item in candidates]
    assert len(keys) == len(set(keys))
