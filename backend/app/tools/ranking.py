"""Explainable ranking of the shops that sell a product.

score = 0.35 * price_rank + 0.25 * proximity + 0.20 * open + 0.10 * in_person + 0.10 * transparency

When the user did not share a location the proximity term is dropped and the
remaining weights are re-normalised.  ``why`` lists the two strongest
contributors in Persian so the ranking can be explained in the UI.
"""

from __future__ import annotations

from ..normalize import fa_digits
from .geo import haversine_m, walk_minutes
from .hours import open_status, price_age_days
from .transparency import in_person_providers, parse_warranty, transparency, warranty_summary

WEIGHTS = {
    "price": 0.35,
    "proximity": 0.25,
    "open": 0.20,
    "payment": 0.10,
    "transparency": 0.10,
}

LABELS = {
    "price": "ارزان‌ترین قیمت",
    "proximity": "نزدیک‌ترین",
    "open": "الان باز",
    "payment": "پرداخت حضوری",
    "transparency": "شفافیت بالا",
}


def build_shop_options(
    offers: list[dict],
    slots: dict | None = None,
    now=None,
    n_shops: int = 0,
    verified: bool = False,
) -> list[dict]:
    """Turn raw offer rows into the shop cards the API returns."""
    slots = slots or {}
    location = slots.get("location") or {}
    user_lat = location.get("lat")
    user_lon = location.get("lon")

    options: list[dict] = []
    for offer in offers:
        status, text = open_status(offer.get("weekly_hours"), now)
        age = price_age_days(offer.get("last_price_changed_at"), now)
        providers = in_person_providers(offer)
        distance = None
        if user_lat is not None and user_lon is not None:
            distance = haversine_m(user_lat, user_lon, offer.get("lat"), offer.get("lon"))
        warranty = parse_warranty(offer.get("warranty"))
        trans = transparency(offer, offer, n_shops or 1, price_age_days=age, verified=verified)
        options.append(
            {
                "shop_id": offer.get("shop_id"),
                "offer_id": offer.get("offer_id"),
                "name": offer.get("name"),
                "price": int(offer.get("price_toman") or 0),
                "address": offer.get("address"),
                "mall": offer.get("mall"),
                # floors are data ("2", "5", "منفی یک"); the UI must never
                # show Latin digits next to a Persian shop card
                "floor": fa_digits(str(offer.get("floor")).strip())
                if offer.get("floor")
                else offer.get("floor"),
                "unit": offer.get("unit"),
                "plaque": offer.get("plaque"),
                "lat": offer.get("lat"),
                "lon": offer.get("lon"),
                "distance_m": distance,
                "walk_min_est": walk_minutes(distance),
                "open_status": status,
                "open_text": text,
                "in_person_providers": providers,
                "warranty": warranty,
                "warranty_text": warranty_summary(warranty),
                "price_age_days": age,
                "transparency": trans,
                "seller_title": offer.get("seller_title"),
            }
        )
    return options


def rank_shops(options: list[dict], slots: dict | None = None, now=None) -> list[dict]:
    """Sort shop options by the explainable score."""
    slots = slots or {}
    location = slots.get("location") or {}
    has_location = location.get("lat") is not None and location.get("lon") is not None

    if not options:
        return []

    prices = [option["price"] for option in options if option.get("price")]
    min_price = min(prices) if prices else 0
    max_price = max(prices) if prices else 0
    distances = [
        option["distance_m"] for option in options if option.get("distance_m") is not None
    ]
    max_distance = max(distances) if distances else 0

    weights = dict(WEIGHTS)
    if not has_location:
        total = weights["price"] + weights["open"] + weights["payment"] + weights["transparency"]
        weights = {key: value / total for key, value in weights.items()}
        weights["proximity"] = 0.0

    for option in options:
        parts: dict[str, float] = {}

        price = option.get("price") or 0
        if max_price > min_price:
            parts["price"] = 1 - (price - min_price) / (max_price - min_price)
        else:
            parts["price"] = 1.0

        if has_location:
            distance = option.get("distance_m")
            if distance is None:
                parts["proximity"] = 0.0
            elif max_distance > 0:
                parts["proximity"] = 1 - min(1.0, distance / max_distance)
            else:
                parts["proximity"] = 1.0
        else:
            parts["proximity"] = 0.0

        parts["open"] = {"open": 1.0, "unknown": 0.5, "closed": 0.0}.get(
            option.get("open_status", "unknown"), 0.0
        )
        parts["payment"] = 1.0 if option.get("in_person_providers") else 0.0
        parts["transparency"] = (option.get("transparency") or {}).get("score", 0) / 5

        score = sum(weights[key] * value for key, value in parts.items())
        option["score"] = round(min(1.0, max(0.0, score)), 3)
        # B3: «ارزان‌ترین قیمت» only makes sense on the actual cheapest shop
        is_cheapest = option.get("price") == min_price
        good_price = (option.get("haggle") or {}).get("label") == "good"
        contributions = sorted(
            (
                (weights[key] * value, key)
                for key, value in parts.items()
                if weights[key] * value > 0
            ),
            reverse=True,
        )
        labels = [
            LABELS[key] if key != "price" else ("ارزان‌ترین قیمت" if is_cheapest or good_price else "قیمت مناسب")
            for _, key in contributions[:2]
        ]
        option["why"] = " + ".join(labels) or "تنها گزینهٔ موجود"

    options.sort(key=lambda option: (-option["score"], option.get("price") or 0))
    return options


def rerank_after_replies(
    options: list[dict],
    parsed_by_shop: dict[str, dict],
    now=None,
) -> list[dict]:
    """Re-score the shops after the seller replies came back."""
    for option in options:
        parsed = parsed_by_shop.get(option["shop_id"])
        option["verify"] = parsed
        if not parsed:
            option["score"] = round(max(0.0, option.get("score", 0) - 0.1), 3)
            continue
        availability = parsed.get("availability")
        if availability == "available":
            option["score"] = round(min(1.0, option.get("score", 0) + 0.3), 3)
            new_price = parsed.get("price_toman")
            if new_price:
                option["negotiated_price"] = int(new_price)
                option["price"] = int(new_price)
            if parsed.get("offer_status"):
                option["offer_status"] = parsed.get("offer_status")
        elif availability == "unavailable":
            option["score"] = round(max(0.0, option.get("score", 0) - 0.6), 3)
        else:
            option["score"] = round(max(0.0, option.get("score", 0) - 0.1), 3)
    options.sort(key=lambda option: (-option["score"], option.get("price") or 0))
    return options
