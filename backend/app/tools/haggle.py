"""Data-backed haggling.

Everything here is pure and deterministic: prices, quartiles, the target
price, the ceiling, and the cheaper shop used as leverage all come from the
same-product offers.  The LLM (when enabled) may only *phrase* the two or
three haggling lines; every number it writes must already exist in the
payload, otherwise the deterministic rules template is returned instead.
"""

from __future__ import annotations

import re
from statistics import median as _median, quantiles

from .. import rules
from ..normalize import fa_digits, normalize, to_ascii_digits
from .geo import haversine_m

TARGET_STEP = 10_000
COUNTER_STEP = 50_000

# A number in an LLM line, optionally followed by a known unit.  Grouping
# separators are allowed inside the number («۳٬۱۵۰٬۰۰۰»).
NUMBER_RE = re.compile(
    r"(\d+(?:\.\d+)?)\s*(میلیون|هزار|تومان|تومن|متر|کیلومتر|درصد|٪)?"
)
UNIT_FACTORS = {
    "میلیون": 1_000_000,
    "هزار": 1_000,
    "کیلومتر": 1_000,
    "متر": 1,
    "تومان": 1,
    "تومن": 1,
    "درصد": 1,
    "٪": 1,
}


def _price(item: dict | None) -> int:
    """Offer or option price in toman (0 when missing/invalid)."""
    if not isinstance(item, dict):
        return 0
    raw = item.get("price_toman")
    if raw is None:
        raw = item.get("price")
    try:
        return max(0, int(raw or 0))
    except (TypeError, ValueError):
        return 0


def _unique_prices(offers: list[dict] | None) -> list[int]:
    """Same-product prices, deduped per shop, ignoring null/zero rows."""
    by_shop: dict[str, int] = {}
    for index, offer in enumerate(offers or []):
        if not isinstance(offer, dict):
            continue
        price = _price(offer)
        if price <= 0:
            continue
        shop_id = str(offer.get("shop_id") or offer.get("offer_id") or index)
        if shop_id not in by_shop or price < by_shop[shop_id]:
            by_shop[shop_id] = price
    return sorted(by_shop.values())


def price_stats(offers: list[dict] | None) -> dict:
    """Median/Q1/min/max over the real same-product offers."""
    prices = _unique_prices(offers)
    if not prices:
        return {"median": 0, "q1": 0, "min": 0, "max": 0, "n_shops": 0}
    median = int(round(_median(prices)))
    if len(prices) >= 2:
        q1 = int(round(quantiles(prices, n=4, method="inclusive")[0]))
    else:
        q1 = prices[0]
    return {
        "median": median,
        "q1": max(prices[0], q1),
        "min": prices[0],
        "max": prices[-1],
        "n_shops": len(prices),
    }


def fairness(price: int, stats: dict) -> str:
    """expensive / normal / good / single for one shop's price."""
    if int(stats.get("n_shops") or 0) < 2:
        return "single"
    price = int(price or 0)
    median = int(stats.get("median") or 0)
    q1 = int(stats.get("q1") or 0)
    if median and price > median * 1.10:
        return "expensive"
    if q1 and price <= q1:
        return "good"
    return "normal"


def _round_to(value: int, step: int) -> int:
    """Nearest step, half up (works for positive toman amounts)."""
    value = max(0, int(value or 0))
    return ((value + step // 2) // step) * step


def target_price(stats: dict, price: int) -> dict:
    """Negotiation target and walk-away ceiling.

    The target is Q1 rounded to 10,000 toman, clamped to ``[min, price]``;
    the ceiling is the median rounded to 10,000 (never below the target).
    """
    price = max(0, int(price or 0))
    min_price = int(stats.get("min") or 0)
    n_shops = int(stats.get("n_shops") or 0)
    if price <= 0 or n_shops < 2:
        return {"target": price, "ceiling": price, "saving_pct": 0}

    target = _round_to(int(stats.get("q1") or 0), TARGET_STEP)
    if min_price:
        target = max(min_price, target)
    target = min(price, target)

    ceiling = _round_to(int(stats.get("median") or 0), TARGET_STEP)
    ceiling = max(target, ceiling)

    saving = max(0, price - target)
    saving_pct = round(saving / price * 100, 1) if price else 0
    return {"target": target, "ceiling": ceiling, "saving_pct": saving_pct}


def _coords(item: dict) -> tuple[float, float] | None:
    lat = item.get("lat")
    lon = item.get("lon")
    if lat is None or lon is None:
        return None
    try:
        return float(lat), float(lon)
    except (TypeError, ValueError):
        return None


def leverage_shop(option: dict, all_options: list[dict] | None) -> dict | None:
    """A cheaper real shop to mention at the counter.

    Cheapest qualifying shop wins; a shop in the same mall is preferred even
    when it is a little more expensive than a shop elsewhere, and distance is
    the final tie-breaker.
    """
    price = _price(option)
    if price <= 0:
        return None
    option_mall = normalize(option.get("mall") or "")
    option_coords = _coords(option)

    all_prices = sorted(p for p in (_price(other) for other in all_options or []) if p > 0)
    if all_prices:
        mid = len(all_prices) // 2
        median_price = (
            all_prices[mid]
            if len(all_prices) % 2
            else (all_prices[mid - 1] + all_prices[mid]) / 2
        )
    else:
        median_price = 0
    # an offer far below the market median is usually a data outlier and is a
    # poor leverage shop (پیشنهاد زیر ۵۰٪ میانه بیشتر شبیه خطای داده است)
    floor_price = median_price * 0.5 if median_price else 0

    candidates: list[dict] = []
    for other in all_options or []:
        if other is option or not isinstance(other, dict):
            continue
        if str(other.get("shop_id")) == str(option.get("shop_id")):
            continue
        other_price = _price(other)
        if other_price <= 0 or other_price >= price:
            continue
        if floor_price and other_price < floor_price:
            continue
        other_mall = normalize(other.get("mall") or "")
        same_mall = bool(option_mall) and other_mall == option_mall
        other_coords = _coords(other)
        delta_m = None
        if option_coords and other_coords:
            delta_m = haversine_m(*option_coords, *other_coords)
        distance = other.get("distance_m")
        try:
            distance = int(distance) if distance is not None else None
        except (TypeError, ValueError):
            distance = None
        candidates.append(
            {
                "shop_id": other.get("shop_id"),
                "name": other.get("name"),
                "price": other_price,
                "distance_m": distance,
                "delta_m": delta_m,
                "same_mall": same_mall,
                "saving": price - other_price,
            }
        )

    if not candidates:
        return None

    def sort_key(item: dict) -> tuple:
        distance = item.get("distance_m")
        return (
            0 if item["same_mall"] else 1,
            item["price"],
            distance if distance is not None else 10**12,
        )

    best = sorted(candidates, key=sort_key)[0]
    return {
        "shop_id": best["shop_id"],
        "name": best["name"],
        "price": best["price"],
        "distance_m": best["distance_m"],
        "delta_m": best["delta_m"],
        "same_mall": best["same_mall"],
        "saving": best["saving"],
    }


def allowed_numbers(
    option: dict,
    stats: dict,
    leverage: dict | None,
    target: int,
    ceiling: int,
) -> set[float]:
    """Every numeric value the LLM may legitimately cite."""
    values: set[float] = {
        float(_price(option)),
        float(stats.get("median") or 0),
        float(stats.get("q1") or 0),
        float(stats.get("min") or 0),
        float(stats.get("max") or 0),
        float(stats.get("n_shops") or 0),
        float(target),
        float(ceiling),
    }
    if leverage:
        for key in ("price", "distance_m", "delta_m", "saving"):
            value = leverage.get(key)
            if value is not None:
                try:
                    values.add(float(value))
                except (TypeError, ValueError):
                    pass
    price = _price(option)
    saving = max(0, price - target)
    values.add(float(saving))
    if price:
        pct = round(saving / price * 100, 1)
        # the UI rounds the percentage for display («۲۹٪»), so both the exact
        # and the rounded value are legitimate for an LLM line
        values.add(float(pct))
        values.add(float(round(pct)))
    values.discard(0.0)
    return values


def numbers_in_text(text: str) -> set[float]:
    """Find every number in an LLM line, expanding million/thousand units."""
    normalized = to_ascii_digits(text or "").replace("٬", "").replace(",", "")
    found: set[float] = set()
    for match in NUMBER_RE.finditer(normalized):
        try:
            value = float(match.group(1))
        except ValueError:
            continue
        factor = UNIT_FACTORS.get(match.group(2) or "", 1)
        found.add(round(value * factor, 1))
    return found


def _llm_payload(
    option: dict,
    stats: dict,
    leverage: dict | None,
    target: int,
    ceiling: int,
    lines_target: dict,
) -> dict:
    def price_text(value) -> str:
        return rules.price_fa(value)

    return {
        "shop": {
            "name": option.get("name"),
            "price": _price(option),
            "price_text": price_text(_price(option)),
        },
        "stats": {
            "median": stats.get("median"),
            "median_text": price_text(stats.get("median")),
            "q1": stats.get("q1"),
            "q1_text": price_text(stats.get("q1")),
            "min": stats.get("min"),
            "n_shops": stats.get("n_shops"),
        },
        "target": target,
        "target_text": price_text(target),
        "ceiling": ceiling,
        "ceiling_text": price_text(ceiling),
        "saving_pct": lines_target.get("saving_pct", 0),
        "leverage": (
            {
                **leverage,
                "price_text": price_text(leverage.get("price")),
                "distance_text": rules.distance_fa(
                    leverage.get("delta_m") or leverage.get("distance_m")
                ),
            }
            if leverage
            else None
        ),
        "instruction": "۲ یا ۳ جملهٔ کوتاه فارسی؛ فقط اعداد و نام‌های همین payload.",
    }


def haggle_lines(
    option: dict,
    stats: dict,
    leverage: dict | None,
    llm_on: bool = False,
    llm_fn=None,
) -> list[str]:
    """Two or three short Persian haggling lines.

    ``llm_fn(payload) -> list[str] | None`` is injected by graph.py so this
    module stays pure in tests.  Any invented number (or a missing real shop
    name in the leverage line) rejects the whole LLM answer.
    """
    price = _price(option)
    target_info = target_price(stats, price)
    target = target_info["target"]
    ceiling = target_info["ceiling"]
    fallback = rules.haggle_lines(option, stats, leverage, target, ceiling)
    if not llm_on or llm_fn is None:
        return fallback

    payload = _llm_payload(option, stats, leverage, target, ceiling, target_info)
    try:
        candidate = llm_fn(payload)
    except Exception:  # noqa: BLE001 - the LLM must never break the flow
        return fallback
    if isinstance(candidate, dict):
        candidate = candidate.get("lines")
    lines = [str(line).strip() for line in (candidate or []) if str(line).strip()]
    lines = lines[:3]
    if len(lines) < 2:
        return fallback
    text = " ".join(lines)
    allowed = allowed_numbers(option, stats, leverage, target, ceiling)
    if numbers_in_text(text) - allowed:
        return fallback
    if leverage and normalize(leverage.get("name")) not in normalize(text):
        return fallback
    return lines


def build_haggle(
    option: dict,
    offers: list[dict] | None,
    all_options: list[dict] | None,
    llm_on: bool = False,
    llm_fn=None,
) -> dict:
    """The ``ShopOption.haggle`` payload consumed by the UI."""
    stats = price_stats(offers)
    price = _price(option)
    target_info = target_price(stats, price)
    leverage = leverage_shop(option, all_options)
    return {
        "label": fairness(price, stats),
        "median": stats["median"],
        "q1": stats["q1"],
        "min": stats["min"],
        "n_shops": stats["n_shops"],
        "target": target_info["target"],
        "ceiling": target_info["ceiling"],
        "saving_pct": target_info["saving_pct"],
        "leverage": leverage,
        "lines": haggle_lines(option, stats, leverage, llm_on=llm_on, llm_fn=llm_fn),
    }
