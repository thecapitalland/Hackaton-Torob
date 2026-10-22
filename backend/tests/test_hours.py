"""Opening hours rules (Asia/Tehran)."""

from __future__ import annotations

from datetime import datetime

from app.tools import catalog
from app.tools.hours import open_status

MEHRISA = "shop_13336f1a0d2ec0b16bbd60aa"  # مهریسا نوین - پاساژ علاالدین
AVAN = "shop_60e835a590a4a652ce0ad6d9"  # آوان آران - hours unknown

THURSDAY_1500 = datetime.fromisoformat("2026-10-22T15:00:00+03:30")
FRIDAY_1200 = datetime.fromisoformat("2026-10-23T12:00:00+03:30")


def test_mehrisa_is_open_on_thursday(catalog_path):
    shop = catalog.shop_by_id(MEHRISA)
    assert shop is not None
    status, text = open_status(shop["weekly_hours"], THURSDAY_1500)
    assert status == "open", text
    assert text.startswith("باز است تا")


def test_mehrisa_is_closed_on_friday(catalog_path):
    shop = catalog.shop_by_id(MEHRISA)
    status, text = open_status(shop["weekly_hours"], FRIDAY_1200)
    assert status == "closed"
    assert text == "الان بسته"


def test_avan_hours_are_unknown(catalog_path):
    shop = catalog.shop_by_id(AVAN)
    assert shop is not None
    status, text = open_status(shop["weekly_hours"], THURSDAY_1500)
    assert status == "unknown"
    assert text == "ساعت کاری اعلام نشده"


def test_zero_length_shift_is_ignored():
    hours = {
        "thu": {"status": "declared", "shifts": [{"start_time": "00:00:00", "end_time": "00:00:00"}]}
    }
    status, text = open_status(hours, THURSDAY_1500)
    assert status == "unknown"


def test_missing_hours_are_unknown():
    assert open_status(None, THURSDAY_1500)[0] == "unknown"
    assert open_status("{}", THURSDAY_1500)[0] == "unknown"


def test_unsupported_day_is_unknown():
    hours = {"thu": {"status": "unsupported", "shifts": []}}
    assert open_status(hours, THURSDAY_1500)[0] == "unknown"


def test_closed_day():
    hours = {"thu": {"status": "closed", "shifts": []}}
    status, text = open_status(hours, THURSDAY_1500)
    assert status == "closed"


def test_overnight_shift_spans_midnight():
    hours = {
        "thu": {"status": "declared", "shifts": [{"start_time": "20:00:00", "end_time": "02:00:00"}]}
    }
    night = datetime.fromisoformat("2026-10-22T23:30:00+03:30")
    status, text = open_status(hours, night)
    assert status == "open"
    assert "۰۲:۰۰" in text or "02:00" in text


def test_price_age_days():
    from app.tools.hours import price_age_days

    age = price_age_days("2026-09-14T08:57:27.401253+00:00", THURSDAY_1500)
    assert age is not None and age > 30
