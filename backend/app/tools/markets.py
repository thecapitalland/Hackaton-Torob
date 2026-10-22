"""Specialty markets ("بورس" of a category in Tehran).

The curated definitions live in ``data/markets.json``; the statistics
(how many shops / offers / prices) are computed by
``backend/scripts/build_markets.py`` from the catalog itself, so the numbers
shown to the user always come from the dataset.

The opening hours are *external* facts collected from public sources - the UI
labels them «اطلاعات عمومی».
"""

from __future__ import annotations

from ..data_static import load_markets
from .geo import haversine_m


def _markets() -> list[dict]:
    return load_markets().get("markets") or []


def external_markets() -> list[dict]:
    return load_markets().get("external_markets") or []


def market_by_id(market_id: str) -> dict | None:
    for market in _markets() + external_markets():
        if market.get("market_id") == market_id:
            return market
    return None


def _stats_for(market: dict, category: str) -> dict:
    stats = market.get("stats") or {}
    return stats.get(category) or {}


def _center(market: dict) -> tuple[float, float] | None:
    centroid = (market.get("stats") or {}).get("_centroid")
    if isinstance(centroid, list) and len(centroid) == 2:
        return float(centroid[0]), float(centroid[1])
    center = market.get("center")
    if isinstance(center, list) and len(center) == 2:
        return float(center[0]), float(center[1])
    return None


def get_specialty_market(category: str, user_location: dict | None = None) -> dict | None:
    """The main market of ``category`` in Tehran (curated + data backed)."""
    if not category:
        return None

    candidates = [m for m in _markets() if category in (m.get("categories") or [])]
    if not candidates:
        return None

    def shops_in(market: dict) -> int:
        return int(_stats_for(market, category).get("shops_in_market") or 0)

    # the curated list is ordered by priority: the first market of a category is
    # "the" market of that category (e.g. Paytakht for laptops).  When the
    # dataset does not cover it we still return it, but flag it as not backed
    # by data and point to the closest market that *is* in the data.
    market = candidates[0]
    stats = _stats_for(market, category)
    data_backed = bool(stats.get("shops_in_market"))

    center = _center(market)
    distance_km = None
    if user_location and center:
        meters = haversine_m(
            user_location.get("lat"), user_location.get("lon"), center[0], center[1]
        )
        if meters is not None:
            distance_km = round(meters / 1000, 1)

    hours = market.get("hours_external") or {}
    alt = None
    if not data_backed:
        alt_market = next((m for m in candidates[1:] if shops_in(m) > 0), None)
        if alt_market is None and market.get("alt"):
            alt_market = market_by_id(market["alt"])
        if alt_market is not None:
            alt = {
                "market_id": alt_market.get("market_id"),
                "name_fa": alt_market.get("name_fa"),
                "center": alt_market.get("center"),
            }

    median_market = stats.get("price_median_market")
    median_city = stats.get("price_median_city")
    return {
        "market_id": market.get("market_id"),
        "name_fa": market.get("name_fa"),
        "center": market.get("center"),
        "centroid": stats.get("centroid"),
        "radius_m": market.get("radius_m"),
        "distance_km": distance_km,
        "shops_in_market": stats.get("shops_in_market"),
        "offers_in_market": stats.get("offers_in_market"),
        "shops_citywide": stats.get("shops_citywide"),
        "price_median_market": median_market,
        "price_median_city": median_city,
        "price_q1_market": (stats.get("price_q1_median_q3_market") or [None, None, None])[0],
        "price_q3_market": (stats.get("price_q1_median_q3_market") or [None, None, None])[2],
        "hours_external": hours,
        "hours_label": "اطلاعات عمومی، ممکن است تغییر کند",
        "sources": market.get("hours_external", {}).get("source")
        or market.get("sources")
        or [],
        "data_backed": data_backed,
        "alt": alt,
        "category": category,
    }


def market_hours_text(market: dict | None) -> str:
    """«معمولاً ۹:۳۰ تا ۲۱:۳۰ — جمعه: تعطیل»"""
    if not market:
        return ""
    hours = market.get("hours_external") or {}
    if not hours:
        return ""
    parts: list[str] = []
    for key in ("sat_thu", "typical", "alaeddin", "charsou", "sat_wed", "thu", "fri", "note"):
        value = hours.get(key)
        if not value:
            continue
        if key == "fri":
            parts.append(f"جمعه: {value}")
        elif key == "note":
            continue
        elif key == "sat_thu" or key == "sat_wed":
            parts.append(f"شنبه تا چهارشنبه: {value}")
        elif key == "thu":
            parts.append(f"پنجشنبه: {value}")
        elif key == "typical":
            parts.append(str(value))
        else:
            parts.append(f"{key}: {value}")
    return " — ".join(parts[:3])


def neshan_link(lat: float | None, lon: float | None, zoom: int = 16) -> str | None:
    """«مسیریابی در نشان» deep link (Update #1). The frontend swaps the href
    for the desktop web map when the user is not on a phone."""
    if lat is None or lon is None:
        return None
    return f"https://nshn.ir/?destination={lat},{lon}"


def balad_link(lat: float | None, lon: float | None) -> str | None:
    """«مسیریابی در بلد» deep link."""
    if lat is None or lon is None:
        return None
    return f"https://balad.ir/directions/driving?destination={lat},{lon}"


def google_link(lat: float | None, lon: float | None) -> str | None:
    if lat is None or lon is None:
        return None
    return f"https://www.google.com/maps/dir/?api=1&destination={lat},{lon}"
