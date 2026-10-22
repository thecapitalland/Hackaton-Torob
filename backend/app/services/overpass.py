"""OpenStreetMap cafe fallback (``amenity=cafe`` via Overpass).

Layer 2 of the coffee lookup: Neshan nearby -> **Overpass** -> static list.
Returns ``None`` on any failure so the caller keeps falling back. Results are
cached in memory for 10 minutes to be gentle with the public Overpass API.
"""

from __future__ import annotations

import time
from collections import OrderedDict

import httpx

OVERPASS_URL = "https://overpass-api.de/api/interpreter"
TIMEOUT_S = 4.0
CACHE_TTL_S = 600
CACHE_MAX = 100

_cache: OrderedDict[str, tuple[float, list[dict] | None]] = OrderedDict()
_failed_until = 0.0  # simple breaker: skip Overpass for 5 minutes after an error
_FAIL_COOLDOWN_S = 300


def _cache_get(key: str) -> list[dict] | None:
    """``None`` = not cached (empty lists are never stored)."""
    hit = _cache.get(key)
    if not hit:
        return None
    expires, value = hit
    if expires < time.time():
        _cache.pop(key, None)
        return None
    _cache.move_to_end(key)
    return value


def cafes_near(lat: float, lon: float, radius_m: int = 500) -> list[dict] | None:
    """Cafes within ``radius_m`` -> ``[{name, lat, lon}]`` (``None`` = unusable)."""
    global _failed_until
    if lat is None or lon is None:
        return None
    if time.time() < _failed_until:
        return None
    key = f"{lat:.5f},{lon:.5f}@{radius_m}"
    cached = _cache_get(key)
    if cached is not None:
        return cached
    query = (
        f"[out:json][timeout:{int(TIMEOUT_S)}];"
        f'node["amenity"="cafe"](around:{int(radius_m)},{lat},{lon});out body 20;'
    )
    try:
        response = httpx.post(
            OVERPASS_URL,
            data={"data": query},
            timeout=TIMEOUT_S,
            headers={"User-Agent": "torobche/1.0 (hackathon demo)"},
        )
        response.raise_for_status()
        data = response.json()
    except Exception:
        _failed_until = time.time() + _FAIL_COOLDOWN_S
        return None
    elements = (data or {}).get("elements") or []
    cafes: list[dict] = []
    for element in elements:
        tags = element.get("tags") or {}
        item_lat, item_lon = element.get("lat"), element.get("lon")
        if item_lat is None or item_lon is None:
            continue
        cafes.append(
            {
                "name": str(tags.get("name") or "کافه"),
                "lat": float(item_lat),
                "lon": float(item_lon),
                "source": "osm",
            }
        )
    if not cafes:
        return None
    result = cafes[:20]
    _cache_set(key, result)
    return result
