"""Transparency score - "how complete is the information about this offer".

There is no review dataset, so instead of a fake rating we show *evidence*:
declared opening hours, in-person payment, warranty, fresh price, and how many
shops sell the same product.  The score is never a seller rating.
"""

from __future__ import annotations

import json
from typing import Any

from ..normalize import fa_digits

SIGNAL_HOURS = "ساعت کاری اعلام‌شده"
SIGNAL_PAYMENT = "پرداخت حضوری"
SIGNAL_WARRANTY = "گارانتی/تضمین"
SIGNAL_FRESH_PRICE = "قیمت تازه"
SIGNAL_POPULAR = "عرضه در چند فروشگاه"
SIGNAL_VERIFIED = "تأیید موجودی با پیام ✓"

DISCLAIMER = "این امتیاز اعتبار فروشنده نیست؛ کامل‌بودن اطلاعات است"


def parse_payment_options(raw: str | None) -> list[dict]:
    if not raw:
        return []
    try:
        parsed = json.loads(raw)
    except (ValueError, TypeError):
        return []
    return parsed if isinstance(parsed, list) else []


def in_person_providers(shop: dict) -> list[str]:
    """Payment providers that support paying in person."""
    providers: list[str] = []
    for option in parse_payment_options(shop.get("payment_options")):
        if not isinstance(option, dict):
            continue
        channel = str(option.get("channel") or "").lower()
        if channel == "in_person":
            name = option.get("provider_name")
            if name and name not in providers:
                providers.append(str(name))
    return providers


def parse_warranty(raw: str | None) -> dict | None:
    if not raw:
        return None
    try:
        parsed = json.loads(raw)
    except (ValueError, TypeError):
        return None
    if isinstance(parsed, dict):
        return parsed
    if isinstance(parsed, list) and parsed:
        return parsed[0] if isinstance(parsed[0], dict) else None
    return None


def warranty_text(warranty: dict | None) -> str | None:
    if not warranty:
        return None
    provider = warranty.get("provider")
    months = warranty.get("period_months")
    if provider and months:
        return f"{provider} · {fa_digits(str(months))} ماهه"
    if provider:
        return str(provider)
    return None


def transparency(
    offer: dict,
    shop: dict,
    n_shops: int,
    price_age_days: int | None = None,
    verified: bool = False,
) -> dict:
    """Return ``{"score": 0..5, "chips": [...], "signals": {...}}``."""
    signals: dict[str, bool] = {
        SIGNAL_HOURS: bool(shop.get("hours_declared")),
        SIGNAL_PAYMENT: bool(in_person_providers(shop)),
        SIGNAL_WARRANTY: bool(parse_warranty(offer.get("warranty"))),
        SIGNAL_FRESH_PRICE: price_age_days is not None and price_age_days < 14,
        SIGNAL_POPULAR: (n_shops or 0) >= 5,
    }
    if verified:
        signals[SIGNAL_VERIFIED] = True

    chips: list[str] = []
    if signals[SIGNAL_HOURS]:
        chips.append(SIGNAL_HOURS)
    providers = in_person_providers(shop)
    if providers:
        chips.append(f"{fa_digits(str(len(providers)))} روش پرداخت حضوری")
    warranty = warranty_text(parse_warranty(offer.get("warranty")))
    if warranty:
        chips.append(f"{SIGNAL_WARRANTY}: {warranty}")
    if signals[SIGNAL_FRESH_PRICE] and price_age_days is not None:
        chips.append(f"قیمت {fa_digits(str(price_age_days))} روز پیش به‌روز شده")
    if signals[SIGNAL_POPULAR]:
        chips.append(f"در {fa_digits(str(n_shops))} فروشگاه عرضه می‌شود")
    if verified:
        chips.append(SIGNAL_VERIFIED)

    score = sum(1 for value in signals.values() if value)
    score = min(5, score)
    return {"score": score, "chips": chips, "signals": signals, "disclaimer": DISCLAIMER}


def grade(score: int) -> str:
    if score >= 4:
        return "شفافیت بالا"
    if score >= 3:
        return "شفافیت متوسط"
    if score >= 1:
        return "شفافیت کم"
    return "اطلاعات ناقص"


def warranty_summary(warranty: Any) -> str | None:
    if isinstance(warranty, str):
        warranty = parse_warranty(warranty)
    return warranty_text(warranty if isinstance(warranty, dict) else None)
