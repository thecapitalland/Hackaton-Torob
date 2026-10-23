"""Out-of-catalog fallback: honest "not found" + real alternatives only."""

from __future__ import annotations

import re

from app import graph
from app.tools import ooc


def test_saffron_is_not_found_and_maps_to_spice_market():
    market = ooc.match_external_market("زعفران و ادویه")
    assert market is not None
    assert market["market_id"] == "gb_spice"


def test_ooc_header_term_strips_fillers():
    assert ooc.product_term("زعفران میخوام") == "زعفران"
    assert ooc.product_term("زعفران می‌خوام") == "زعفران"
    assert ooc.product_term("یه زعفران لازم دارم") == "زعفران"
    assert ooc.product_term("میخوام زعفران بخرم") == "زعفران"
    assert ooc.product_term("زعفران و ادویه فله") == "زعفران و ادویه فله"


def test_saffron_alone_maps_to_spice_market_with_filler_words():
    market = ooc.match_external_market("زعفران می‌خوام لطفا")
    assert market is not None
    assert market["market_id"] == "gb_spice"
    assert ooc.clean_query("زعفران می‌خوام لطفا") == "زعفران"

    colloquial = ooc.match_external_market("زعفرون میخوام")
    assert colloquial is not None
    assert colloquial["market_id"] == "gb_spice"


def test_saffron_has_no_irrelevant_dataset_alternatives():
    market = ooc.match_external_market("زعفران")
    assert market is not None
    # no pager, perfume or phone-case may sneak in through low trigram overlap
    assert ooc.find_alternatives("زعفران", market) == []
    assert ooc._category_candidates("زعفران", market) == []


def test_three_tar_maps_to_music_market():
    market = ooc.match_external_market("سه‌تار")
    assert market is not None
    assert market["market_id"] == "baharestan_music"


def test_carpet_maps_to_carpet_market():
    market = ooc.match_external_market("فرش دستباف")
    assert market is not None
    assert market["market_id"] == "gb_carpet"


def test_alternatives_come_from_the_catalog():
    market = ooc.match_external_market("سه‌تار")
    alternatives = ooc.find_alternatives("سه‌تار", market)
    assert alternatives, "no alternative found for سه‌تار"
    for item in alternatives:
        assert item["product_id"].startswith("product_")
        assert item["persian_title"]
    categories = {item["category_name"] for item in alternatives}
    assert "گیتار" in categories


def test_carpet_alternatives_use_the_dataset_category():
    market = ooc.match_external_market("فرش دستباف")
    alternatives = ooc.find_alternatives("فرش دستباف", market)
    assert alternatives
    assert any(item["category_name"] == "فرش دستبافت" for item in alternatives)


def test_shoe_phrase_suggests_a_real_shoe_category():
    candidates = ooc._category_candidates("کفش کتونی", None)
    assert candidates
    assert "کتانی و کفش اسپرت" in candidates
    assert "کتانی و کفش اسپرت" in candidates
    alternatives = ooc.find_alternatives("کفش کتونی", None)
    assert alternatives
    assert any("کفش" in item["category_name"] or "کتانی" in item["category_name"] for item in alternatives)


def test_tips_guard_strips_prices_and_phone_numbers():
    tips = ooc.sanitize_tips(
        [
            "چند مغازه را مقایسه کن",
            "قیمت حدود ۳ میلیون تومان است",
            "با ۰۹۱۲۳۴۵۶۷۸۹ تماس بگیر",
            "فاکتور رسمی بگیر",
        ]
    )
    assert "چند مغازه را مقایسه کن" in tips
    assert "فاکتور رسمی بگیر" in tips
    for tip in tips:
        assert "تومان" not in tip
        assert not re.search(r"09\d{9}", tip)


def test_fallback_message_is_honest():
    message = ooc.fallback_message("زعفران", {"name_fa": "بورس عطاری"})
    assert "پیدا نکردم" in message
    assert "بورس عطاری" in message


def test_no_market_message():
    message = ooc.fallback_message("چیز کاملاً ناشناخته", None)
    assert "پیدا نکردم" in message


def test_ooc_guide_filters_untrusted_market_brand_and_number(monkeypatch, catalog_path):
    class FakeClient:
        def chat_json(self, _messages, **_kwargs):
            return {
                "category_guess": "دستهٔ خیالی",
                "tips": [
                    "این بسته را با قیمت ۵ میلیون بخر",
                    "از فروشگاه خیالی در خیابان نمونه خرید کن",
                    "پلمب و تاریخ محصول را پیش از خرید بررسی کن",
                ],
                "markets": ["fake-market"],
                "brands_generic": ["برند خیالی"],
            }

    monkeypatch.setattr(graph, "get_client", lambda: FakeClient())
    result = graph.out_of_catalog({"text": "زعفران", "slots": {"query": "زعفران"}})
    guide = result["ooc"]["guide"]
    assert result["ooc"]["message_fa"] == "این کالا رو نداریم."
    assert guide["category_guess"] is None
    assert guide["markets"] == ["molavi"]
    assert guide["brands_generic"] == []
    assert guide["tips"] == ["پلمب و تاریخ محصول را پیش از خرید بررسی کن"]
    assert result["ooc"]["market"]["market_id"] == "molavi"
