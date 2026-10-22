"""Simulated seller replies.

Nothing is ever sent: the dataset phone numbers are fake and must not be used.
Every reply is scripted, deterministic (so the demo video is reproducible) and
rendered in the UI with the «پاسخ شبیه‌سازی‌شده» label.
"""

from __future__ import annotations

import hashlib
import re

from ..data_static import load_seller_replies
from ..normalize import fa_digits

PRICE_CHANGE_FACTOR = 1.065
COUNTER_STEP = 50_000
BASE_DELAY_MS = 2500
DELAY_STEP_MS = 1700
# «... هستیم، طبقه منفی یک.» -> the floor part is replaced with the real one
FLOOR_RE = re.compile(r"[،,]\s*طبقه[^.!؟\n]*")


def price_to_words(value: int | None) -> str:
    """3150000 -> «۳ میلیون و ۱۵۰» (the way people say it in a shop)."""
    if value is None:
        return ""
    value = int(value)
    millions, rest = divmod(value, 1_000_000)
    thousands, remainder = divmod(rest, 1_000)
    parts: list[str] = []
    if millions:
        parts.append(f"{fa_digits(str(millions))} میلیون")
    if thousands:
        parts.append(f"{fa_digits(str(thousands))} هزار")
    if not parts:
        parts.append(fa_digits(str(value if remainder == 0 else value)))
    return " و ".join(parts)


def price_up(original: int) -> int:
    """The "new price" a seller quotes after a small increase."""
    return int(round(original * PRICE_CHANGE_FACTOR, -5))


def _stable_index(shop_id: str) -> int:
    digest = hashlib.sha1(shop_id.encode("utf-8")).hexdigest()
    return int(digest[:8], 16)


def assignment_for(shop_id: str) -> str:
    """The scripted outcome for a shop."""
    data = load_seller_replies()
    assignment = data.get("demo_script_assignment") or {}
    if shop_id in assignment:
        return str(assignment[shop_id])
    default = assignment.get("_default", "unavailable")
    # unassigned shops alternate between "no stock" and "no answer" so the
    # demo shows both branches - deterministically, based on the shop id.
    return "no_response" if _stable_index(shop_id) % 2 == 0 else default


def delay_for(index: int) -> int:
    return BASE_DELAY_MS + DELAY_STEP_MS * max(0, index)


def seller_reply(shop_id: str, offer_price: int, seed: int = 42) -> str | None:
    """The scripted reply text (or ``None`` when the seller stays silent)."""
    return seller_reply_detail(shop_id, offer_price, index=0)["text"]


def counter_price(target_price: int, offer_price: int) -> int:
    """A seller counter between the target and the listed price (50k steps)."""
    target = max(0, int(target_price or 0))
    offer = max(target, int(offer_price or 0))
    if offer <= target:
        return offer
    midpoint = (target + offer) // 2
    rounded = ((midpoint + COUNTER_STEP // 2) // COUNTER_STEP) * COUNTER_STEP
    return min(offer, max(target, rounded))


def negotiation_outcome(shop_id: str, offer_price: int, target_price: int | None) -> str:
    """Deterministic accept/counter for the demo.

    The two scripted headphone shops land in the two interesting buckets:
    مهریسا نوین accepts the target, آوان آران counters.  All other shops use
    the same stable hash, so the demo is reproducible.
    """
    if target_price is None:
        return "none"
    try:
        target = int(target_price)
        offer = int(offer_price)
    except (TypeError, ValueError):
        return "none"
    if target <= 0 or offer <= 0 or target >= offer:
        return "none"
    bucket = _stable_index(shop_id) % 4
    if bucket == 1:
        return "accepted"
    if bucket == 3:
        return "countered"
    return "none"


def seller_reply_detail(
    shop_id: str,
    offer_price: int,
    index: int = 0,
    floor: str | None = None,
    target_price: int | None = None,
) -> dict:
    """Full scripted answer: status, text and the UI typing delay.

    ``floor`` is the shop's real floor from the catalog; it replaces the
    hardcoded «طبقه منفی یک» of the template so the simulated seller never
    sends the user to a different floor than the shop card.  When the user
    approved a target price, some shops accept it and some counter it.
    """
    data = load_seller_replies()
    templates = data.get("templates") or {}
    outcome = assignment_for(shop_id)
    offer_status = "none"
    counter = None
    if outcome in {"available", "price_changed"}:
        offer_status = negotiation_outcome(shop_id, offer_price, target_price)
    if offer_status == "accepted":
        template = templates.get("negotiation_accepted")
        counter = None
    elif offer_status == "countered":
        template = templates.get("negotiation_countered")
        counter = counter_price(int(target_price or 0), offer_price)
    else:
        template = templates.get(outcome)

    text = template
    if isinstance(text, str):
        text = (
            text.replace("{price}", price_to_words(offer_price))
            .replace("{price_up}", price_to_words(price_up(offer_price)))
            .replace("{target}", price_to_words(target_price))
            .replace("{counter}", price_to_words(counter))
        )
        replacement = f"، طبقه {fa_digits(str(floor).strip())}" if floor else ""
        text = FLOOR_RE.sub(replacement, text)
    else:
        text = None

    status = {
        "available": "replied",
        "price_changed": "replied",
        "unavailable": "replied",
        "unclear": "replied",
        "no_response": "no_response",
    }.get(outcome, "no_response")
    if offer_status != "none" and status == "replied":
        status = "replied"

    return {
        "shop_id": shop_id,
        "outcome": outcome,
        "status": status,
        "text": text,
        "delay_ms": delay_for(index),
        "simulated": True,
        "offer_status": offer_status,
        "counter_price": counter,
        "target_price": target_price,
    }


def call_transcript(shop_name: str) -> str:
    """Transcript of the simulated phone call used when nobody answers."""
    return (
        f"تماس شبیه‌سازی‌شده با {shop_name}: «سلام، فروشگاه {shop_name}؟ "
        "دنبال این مدل بودم، موجوده؟ ... متأسفم خطی نبود، بعداً پیام می‌دم.»"
    )
