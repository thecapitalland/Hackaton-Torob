"""Out-of-catalog fallback: honest "not found" + real alternatives only."""

from __future__ import annotations

import re

from app.tools import ooc


def test_saffron_is_not_found_and_maps_to_spice_market():
    market = ooc.match_external_market("زعفران و ادویه")
    assert market is not None
    assert market["market_id"] == "gb_spice"


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
