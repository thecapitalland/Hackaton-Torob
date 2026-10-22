"""Compute the specialty-market statistics from the catalog.

    python backend/scripts/build_markets.py --catalog data/catalog.db \
        --out data/markets.json

The curated market definitions (names, centres, radius, external opening
hours and their sources) are defined in ``MARKET_DEFINITIONS`` below; the
numbers (how many shops / offers / prices) are always computed from the
catalog itself so the UI can honestly say "N of the M shops of this category
are inside this market".
"""

from __future__ import annotations

import argparse
import json
import math
import statistics as st
import sqlite3
import sys
from pathlib import Path

try:  # the windows console defaults to cp1256 which can not print Persian
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:  # pragma: no cover
    pass

MARKET_DEFINITIONS: list[dict] = [
    {
        "market_id": "paytakht",
        "name_fa": "مجتمع کامپیوتر پایتخت (ولیعصر، ابتدای میرداماد)",
        "categories": ["لپ تاپ و نوت بوک"],
        "center": [35.7603, 51.4096],
        "radius_m": 300,
        "keywords": ["مجتمع کامپیوتر پایتخت", "ابتدای میرداماد"],
        "hours_external": {
            "sat_thu": "09:30-21:30",
            "fri": "closed (open Fridays of Esfand)",
            "source": [
                "https://cccenter.ir/تماس/",
                "https://mahalema.com/place/paytakht_computer_complex/",
            ],
        },
        "alt": "jomhouri_hafez",
    },
    {
        "market_id": "jomhouri_hafez",
        "name_fa": "بورس جمهوری–حافظ (علاءالدین و چارسو)",
        "categories": [
            "گوشی موبایل",
            "هدفون، هدست و هندزفری",
            "لپ تاپ و نوت بوک",
            "کیف و کاور گوشی",
        ],
        "center": [35.6950, 51.4115],
        "radius_m": 350,
        "keywords": ["علاالدین", "علاءالدین", "چارسو"],
        "hours_external": {
            "alaeddin": "Sat–Thu 09:00-21:00; Fri ~11:00-16/18 (sources differ)",
            "charsou": "daily ~10:00-22:00",
            "source": [
                "https://alaedingroup.ir/alaedin-commercial-complexes/",
                "https://tehranmoble.ir/blog/aladdin-mobile-market/",
                "https://hihotel.ir/blog/tehran-charsou-mall/",
            ],
        },
    },
    {
        "market_id": "kuwaitiha_istanbul",
        "name_fa": "پاساژ کویتی‌ها و چهارراه استانبول",
        "categories": ["کتانی و کفش اسپرت", "تیشرت و پولوشرت"],
        "center": [35.6947, 51.4204],
        "radius_m": 300,
        "keywords": ["کویتی", "چهارراه استانبول"],
        "hours_external": {
            "sat_thu": "08:00-21:00",
            "fri": "closed",
            "source": [
                "https://balad.ir/p/پاساژ-کویتی-ها-tehran-nei-bazar_shopping-mall-3VwTZrEMhSoLw9",
                "https://letsgotrip.ir/kuwaiti-passage/",
            ],
        },
    },
    {
        "market_id": "lalehzar",
        "name_fa": "خیابان لاله‌زار (بورس لوستر و روشنایی/الکتریکی)",
        "categories": ["لوستر و چراغ تزئینی", "لامپ LED و کم مصرف", "چراغ پنلی و سقفی"],
        "center": [35.6923, 51.4229],
        "radius_m": 400,
        "keywords": ["لاله زار", "لاله‌زار", "لالهزار"],
        "hours_external": {
            "typical": "~10/11:00-20:00, Fridays shorter (shop-dependent)",
            "source": [
                "https://sheralight.ir/لوستر-فروشی-های-تهران/",
                "https://khoobo.com/buy-chandeliers-and-lighting/",
            ],
        },
    },
]

EXTERNAL_MARKETS: list[dict] = [
    {
        "market_id": "gb_carpet",
        "name_fa": "بازار فرش دستباف (خیابان خیام، ساختمان بازار فرش ایران، فراشباشی)",
        "keywords_fa": ["فرش دستباف", "گلیم", "گبه"],
        "center": [35.6735, 51.417],
        "hours_external": {
            "sat_wed": "08:30-17:00 (street-front passages ~20:00)",
            "thu": "inner ~14:00",
            "fri": "closed",
            "source": [
                "https://tehranica.info/shopping-center/ساختمان-بازار-فرش-ایران-بازار/",
                "https://tehranica.info/lists/بورس-های-بازار-تهران/",
                "https://www.digikala.com/mag/tehran-grand-bazaar/",
            ],
        },
        "related_dataset_categories": ["فرش دستبافت", "فرش ماشینی"],
    },
    {
        "market_id": "gb_fabric",
        "name_fa": "بازار پارچه (بازار امیر/بزازها، حمام‌چال، عباس‌آباد)",
        "keywords_fa": ["پارچه", "منسوجات"],
        "center": [35.6745, 51.4205],
        "hours_external": {
            "sat_wed": "08:30-17:00 (street-front passages ~20:00)",
            "thu": "inner ~14:00",
            "fri": "closed",
            "source": [
                "https://tehranica.info/lists/بورس-های-بازار-تهران/",
                "https://www.digikala.com/mag/tehran-grand-bazaar/",
            ],
        },
        "related_dataset_categories": ["انواع پارچه"],
    },
    {
        "market_id": "gb_gold",
        "name_fa": "بازار زرگرها (سبزه‌میدان، ۱۵ خرداد)",
        "keywords_fa": ["طلا", "جواهر", "سکه طلا"],
        "center": [35.6765, 51.42],
        "hours_external": {
            "sat_wed": "08:30-17:00 (street-front passages ~20:00)",
            "thu": "inner ~14:00",
            "fri": "closed",
            "source": ["https://tehranica.info/lists/بورس-های-بازار-تهران/"],
        },
        "related_dataset_categories": ["شمش طلا"],
    },
    {
        "market_id": "gb_spice",
        "name_fa": "بورس عطاری و ادویه (بازار سید اسماعیل، پله‌نوروزخان، کوچه احمدی/مولوی)",
        "keywords_fa": ["زعفران", "زعفرون", "ادویه", "گیاهان دارویی", "عطاری", "خشکبار عمده"],
        "center": [35.6725, 51.4235],
        "hours_external": {
            "sat_wed": "08:30-17:00 (street-front passages ~20:00)",
            "thu": "inner ~14:00",
            "fri": "closed",
            "source": ["https://tehranica.info/lists/بورس-های-بازار-تهران/"],
        },
        "related_dataset_categories": [],
    },
    {
        "market_id": "gb_stationery",
        "name_fa": "بازار بین‌الحرمین/مسجد جامع (لوازم‌التحریر)",
        "keywords_fa": ["لوازم تحریر", "نوشت‌افزار", "لوازم نقاشی"],
        "center": [35.674, 51.4245],
        "hours_external": {
            "sat_wed": "08:30-17:00 (street-front passages ~20:00)",
            "thu": "inner ~14:00",
            "fri": "closed",
            "source": [
                "https://tehranica.info/lists/بورس-های-بازار-تهران/",
                "https://www.digikala.com/mag/tehran-grand-bazaar/",
            ],
        },
        "related_dataset_categories": [],
    },
    {
        "market_id": "gb_womens",
        "name_fa": "بازار جعفری و سرای ملی (شال، روسری، پوشاک زنانه)",
        "keywords_fa": ["شال و روسری", "پوشاک زنانه"],
        "center": [35.6755, 51.4225],
        "hours_external": {
            "sat_wed": "08:30-17:00 (street-front passages ~20:00)",
            "thu": "inner ~14:00",
            "fri": "closed",
            "source": ["https://www.digikala.com/mag/tehran-grand-bazaar/"],
        },
        "related_dataset_categories": [],
    },
    {
        "market_id": "manouchehri",
        "name_fa": "خیابان منوچهری و پاساژ چهلستون (عتیقه، آرایشی، کیف و چمدان)",
        "keywords_fa": ["عتیقه", "سکه قدیمی", "کلکسیون", "لوازم آرایشی عمده", "چمدان"],
        "center": [35.6935, 51.4245],
        "hours_external": {
            "typical": "~10:00-22:00",
            "source": ["https://tehranica.info/attractions/localities/road/خیابان-منوچهری-تهران/"],
        },
        "related_dataset_categories": ["عطر و ادکلن"],
    },
    {
        "market_id": "baharestan_music",
        "name_fa": "راستهٔ ساز میدان بهارستان (و جمهوری تا چهارراه استانبول)",
        "keywords_fa": ["ساز", "آلات موسیقی", "تار", "سه‌تار", "ویولن"],
        "center": [35.6925, 51.431],
        "hours_external": {
            "typical": "daily 08:00-20:00",
            "price_hint_external": "ساز از ~۵۰۰ هزار تا بیش از ۷۰ میلیون تومان (همشهری)",
            "source": ["https://www.hamshahrionline.ir/news/834068/"],
        },
        "related_dataset_categories": ["گیتار"],
    },
    {
        "market_id": "hasanabad_tools",
        "name_fa": "بورس ابزار و یراق (امام خمینی، چهارراه حسن‌آباد تا ولیعصر، شیخ هادی)",
        "keywords_fa": ["ابزار", "یراق", "دریل", "ابزار دستی"],
        "center": [35.687, 51.408],
        "hours_external": {
            "typical": "shop-dependent (unverified)",
            "source": ["https://balad.ir/blog/places-to-shop-in-tehran/"],
        },
        "related_dataset_categories": [
            "دریل و پیچ گوشتی برقی و شارژی",
            "سایر ابزار دستی و تجهیزات کارگاهی",
        ],
    },
    {
        "market_id": "aminhozour",
        "name_fa": "سه‌راه امین حضور / خیابان امیرکبیر (لوازم خانگی برقی)",
        "keywords_fa": ["لوازم خانگی", "یخچال", "لباسشویی"],
        "center": [35.689, 51.4275],
        "hours_external": {
            "typical": "shop-dependent (unverified)",
            "source": ["https://balad.ir/blog/places-to-shop-in-tehran/"],
        },
        "related_dataset_categories": ["یخچال فریزر ساید بای ساید", "یخچال فریزر بالاپایین"],
    },
    {
        "market_id": "haft_tir_carpet",
        "name_fa": "میدان هفت‌تیر (فرش ماشینی و گلیم)",
        "keywords_fa": ["فرش ماشینی", "موکت"],
        "center": [35.715, 51.426],
        "hours_external": {
            "typical": "shop-dependent (unverified)",
            "source": ["https://balad.ir/blog/places-to-shop-in-tehran/"],
        },
        "related_dataset_categories": ["فرش ماشینی"],
    },
    {
        "market_id": "parvaneh_friday",
        "name_fa": "جمعه‌بازار پروانه (باغ هنر، اتوبان حقانی)",
        "keywords_fa": ["دست دوم", "عتیقه", "صنایع دستی", "کلکسیون"],
        "center": [35.756, 51.433],
        "hours_external": {
            "fri": "08:00-16/17:00 only Fridays",
            "note": "used clothing reportedly banned at new site",
            "source": ["https://bazarparvane.com/", "https://pinorest.com/mag/parvaneh-friday-bazar/"],
        },
        "related_dataset_categories": [],
    },
    {
        "market_id": "jomhouri_wedding",
        "name_fa": "خیابان جمهوری/کوچه مهران (لباس عروس اقتصادی)",
        "keywords_fa": ["لباس عروس", "کت و شلوار داماد"],
        "center": [35.6955, 51.405],
        "hours_external": {
            "typical": "shop-dependent (unverified)",
            "source": ["https://balad.ir/blog/places-to-shop-in-tehran/"],
        },
        "related_dataset_categories": ["لباس عروس"],
    },
]


def haversine_m(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    radius = 6_371_000
    d_phi = math.radians(lat2 - lat1)
    d_lambda = math.radians(lon2 - lon1)
    a = (
        math.sin(d_phi / 2) ** 2
        + math.cos(math.radians(lat1)) * math.cos(math.radians(lat2)) * math.sin(d_lambda / 2) ** 2
    )
    return radius * 2 * math.asin(math.sqrt(min(1.0, a)))


def quantile(values: list[float], fraction: float) -> int | None:
    if len(values) < 4:
        return None
    try:
        return int(st.quantiles(values, n=4)[fraction])
    except st.StatisticsError:
        return None


def main() -> int:
    parser = argparse.ArgumentParser(description="Build data/markets.json")
    parser.add_argument("--catalog", default="data/catalog.db")
    parser.add_argument("--out", default="data/markets.json")
    args = parser.parse_args()

    conn = sqlite3.connect(args.catalog)
    conn.row_factory = sqlite3.Row
    markets_out: list[dict] = []

    for definition in MARKET_DEFINITIONS:
        market = dict(definition)
        stats: dict[str, dict] = {}
        for category in market["categories"]:
            rows = conn.execute(
                """
                SELECT o.shop_id AS shop_id, s.address AS address, s.mall AS mall,
                       s.lat AS lat, s.lon AS lon, o.price_toman AS price_toman
                FROM offers o JOIN shops s ON s.shop_id = o.shop_id
                JOIN products p ON p.product_id = o.product_id
                WHERE p.category_name = ? AND o.price_toman > 0
                """,
                (category,),
            ).fetchall()

            def inside(row: sqlite3.Row) -> bool:
                text = f"{row['address'] or ''}{row['mall'] or ''}"
                for keyword in market["keywords"]:
                    if keyword in text:
                        return True
                if row["lat"] is not None and row["lon"] is not None:
                    distance = haversine_m(
                        market["center"][0], market["center"][1], row["lat"], row["lon"]
                    )
                    return distance <= market["radius_m"]
                return False

            inside_rows = [row for row in rows if inside(row)]
            market_prices = [row["price_toman"] for row in inside_rows]
            city_prices = [row["price_toman"] for row in rows]
            shops_in_market = {row["shop_id"] for row in inside_rows}
            shops_citywide = {row["shop_id"] for row in rows}
            coords = [
                (row["lat"], row["lon"]) for row in inside_rows if row["lat"] is not None
            ]
            centroid = None
            if coords:
                centroid = [
                    round(sum(c[0] for c in coords) / len(coords), 5),
                    round(sum(c[1] for c in coords) / len(coords), 5),
                ]
            stats[category] = {
                "shops_in_market": len(shops_in_market),
                "offers_in_market": len(inside_rows),
                "shops_citywide": len(shops_citywide),
                "offers_citywide": len(rows),
                "centroid": centroid,
                "price_q1_median_q3_market": [
                    quantile(market_prices, 0),
                    int(st.median(market_prices)) if market_prices else None,
                    quantile(market_prices, 2),
                ],
                "price_q1_median_q3_city": [
                    quantile(city_prices, 0),
                    int(st.median(city_prices)) if city_prices else None,
                    quantile(city_prices, 2),
                ],
            }
        market["stats"] = stats
        market["external_note"] = (
            "ساعت و نقش بازار از وب بیرونی است (تقریبی، بررسی‌شده در ۲۰۲۶-۱۰-۲۲)؛ "
            "تعداد فروشگاه و قیمت‌ها از داده‌های ترب محاسبه شده است."
        )
        markets_out.append(market)
        for category, values in stats.items():
            print(
                f"{market['market_id']:20s} {category:28s} "
                f"{values['shops_in_market']:5d} / {values['shops_citywide']:5d} shops"
            )

    payload = {
        "generated": "2026-10-22",
        "method": (
            "یک آفر از بازار است اگر نشانی/نام پاساژ شامل کلیدواژهٔ بازار باشد "
            "یا مختصات فروشگاه در شعاع بازار باشد؛ قیمت‌ها به تومان"
        ),
        "excluded": ["بازار رضا — مشهد است و در تهران نیست"],
        "markets": markets_out,
        "external_markets": EXTERNAL_MARKETS,
    }
    out_path = Path(args.out)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    with out_path.open("w", encoding="utf-8") as handle:
        json.dump(payload, handle, ensure_ascii=False, indent=1)
    print(f"\nwrote {out_path} ({out_path.stat().st_size / 1024:.1f} KB)")
    conn.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
