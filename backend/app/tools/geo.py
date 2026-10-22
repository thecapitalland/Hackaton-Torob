"""Geo helpers: distance, walking estimate and address parsing."""

from __future__ import annotations

import math
import re

from ..normalize import normalize, normalize_mall_name

EARTH_RADIUS_M = 6_371_000
WALK_SPEED_M_PER_MIN = 80  # ~4.8 km/h, used for the "estimated" walk time

MALL_RE = re.compile(r"((?:پاساژ|مجتمع|مرکز خرید|بازار|برج)\s+[^،,\-]+)")
FLOOR_RE = re.compile(r"طبقه\s*([\-‑]?\d+|[^\s،,]+)")
UNIT_RE = re.compile(r"واحد\s*(\d+)")


def haversine_m(lat1: float | None, lon1: float | None, lat2: float | None, lon2: float | None) -> int | None:
    """Great-circle distance in meters (None when a coordinate is missing)."""
    if lat1 is None or lon1 is None or lat2 is None or lon2 is None:
        return None
    try:
        phi1, phi2 = math.radians(lat1), math.radians(lat2)
        dphi = math.radians(lat2 - lat1)
        dlambda = math.radians(lon2 - lon1)
    except TypeError:
        return None
    a = (
        math.sin(dphi / 2) ** 2
        + math.cos(phi1) * math.cos(phi2) * math.sin(dlambda / 2) ** 2
    )
    return int(EARTH_RADIUS_M * 2 * math.asin(math.sqrt(min(1.0, a))))


def walk_minutes(distance_m: int | None) -> int | None:
    """Very rough walking estimate - always shown as «تخمینی»."""
    if distance_m is None:
        return None
    return max(1, round(distance_m / WALK_SPEED_M_PER_MIN))


def parse_mall_floor(address: str | None) -> tuple[str | None, str | None]:
    """Extract ``(mall, floor)`` from a free text address."""
    if not address:
        return None, None
    mall_match = MALL_RE.search(address)
    mall = normalize_mall_name(mall_match.group(1)) if mall_match else None
    floor_match = FLOOR_RE.search(address)
    floor = floor_match.group(1).strip() if floor_match else None
    return mall or None, floor or None


def parse_unit(address: str | None) -> str | None:
    if not address:
        return None
    match = UNIT_RE.search(address)
    return match.group(1) if match else None


def format_distance(distance_m: int | None) -> str:
    """«۱٫۰ کیلومتر» / «۳۵۰ متر» with Persian digits."""
    from ..normalize import fa_digits

    if distance_m is None:
        return "نامشخص"
    if distance_m < 1000:
        return f"{fa_digits(str(distance_m))} متر"
    km = distance_m / 1000
    text = f"{km:.1f}".replace(".", "٫")
    return f"{fa_digits(text)} کیلومتر"


def normalized_address(address: str | None) -> str:
    return normalize(address)
