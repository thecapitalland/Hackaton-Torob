"""Neshan Maps API client (Update #1, backend-only - the key never reaches the browser).

Design rules from ``UPDATE_PROMPT_neshan_ui.md``:

* every function returns ``None`` / ``[]`` whenever Neshan is unavailable, the
  key is missing, or Neshan rejects the request - the caller silently falls
  back to the previous behaviour (air distance, static cafe list, ...);
* 3s timeout, in-memory LRU cache (10 minutes), HTTP 480 (= invalid key) marks
  the client disabled for 10 minutes so we do not hammer the API;
* endpoints used:
    - ``GET /v5/reverse``      reverse geocoding
    - ``GET /v4/direction``    walking / driving route (encoded polyline)
    - ``GET /v1/nearby``       nearby cafes (may be ticket-locked)
"""

from __future__ import annotations

import os
import time
from collections import OrderedDict
from typing import Any

import httpx

BASE_URL = "https://api.neshan.org"
TIMEOUT_S = 3.0
CACHE_TTL_S = 600  # 10 minutes
CACHE_MAX = 200
INVALID_KEY_HTTP = 480
DISABLE_AFTER_INVALID_S = 600

_client = httpx.Client(timeout=TIMEOUT_S)
_cache: OrderedDict[str, tuple[float, Any]] = OrderedDict()
_invalid_key_until = 0.0


def _api_key() -> str:
    return (os.environ.get("NESHAN_API_KEY") or os.environ.get("NESHAN_KEY") or "").strip()


def _is_available() -> bool:
    """False while the key is missing or Neshan rejected it recently."""
    if not _api_key():
        return False
    return time.time() >= _invalid_key_until


def _cache_get(key: str) -> Any | None:
    hit = _cache.get(key)
    if not hit:
        return None
    expires, value = hit
    if expires < time.time():
        _cache.pop(key, None)
        return None
    _cache.move_to_end(key)
    return value


def _cache_set(key: str, value: Any) -> None:
    _cache[key] = (time.time() + CACHE_TTL_S, value)
    _cache.move_to_end(key)
    while len(_cache) > CACHE_MAX:
        _cache.popitem(last=False)


def _clear_cache() -> None:
    _cache.clear()


def _request(path: str, params: dict[str, Any]) -> dict | None:
    if not _is_available():
        return None
    key = path + "|" + str(sorted(params.items()))
    cached = _cache_get(key)
    if cached is not None:
        return cached
    global _invalid_key_until
    try:
        response = _client.get(
            BASE_URL + path,
            params=params,
            headers={"Api-Key": _api_key()},
            timeout=TIMEOUT_S,
        )
    except Exception:
        return None
    if response.status_code == INVALID_KEY_HTTP:
        # invalid key -> disable for a while, fall back everywhere
        _invalid_key_until = time.time() + DISABLE_AFTER_INVALID_S
        return None
    if response.status_code != 200:
        return None
    try:
        data = response.json()
    except Exception:
        return None
    if not isinstance(data, dict) or str(data.get("status", "ok")).lower() != "ok":
        return None
    _cache_set(key, data)
    return data


# --------------------------------------------------------------------------
# public helpers
# --------------------------------------------------------------------------


def reverse_geocode(lat: float, lon: float) -> dict | None:
    """``GET /v5/reverse`` -> ``{formatted_address, neighbourhood, source}``."""
    if lat is None or lon is None:
        return None
    data = _request("/v5/reverse", {"lat": lat, "lng": lon})
    if not data:
        return None
    address = str(data.get("formatted_address") or "").strip()
    neighbourhood = str(data.get("neighbourhood") or "").strip() or None
    if not address and not neighbourhood:
        return None
    return {
        "formatted_address": address or neighbourhood,
        "neighbourhood": neighbourhood,
        "source": "neshan",
    }


def search(term: str) -> list[dict] | None:
    """Search Neshan places and return normalized coordinate results.

    The client deliberately exposes only the small subset needed by the UI;
    the API key stays server-side and unavailable results fall back locally.
    """
    term = (term or "").strip()
    if len(term) < 2:
        return None
    data = _request("/v1/search", {"term": term, "lat": 35.7, "lng": 51.4})
    items = (data or {}).get("items") or []
    results: list[dict] = []
    for item in items:
        location = item.get("location") or {}
        if isinstance(location, dict):
            lat, lon = location.get("y"), location.get("x")
        elif isinstance(location, (list, tuple)) and len(location) >= 2:
            lon, lat = location[0], location[1]
        else:
            continue
        if lat is None or lon is None:
            continue
        results.append({
            "name_fa": str(item.get("title") or item.get("address") or term),
            "lat": float(lat),
            "lon": float(lon),
            "source": "neshan",
        })
    return results or None


def decode_polyline(encoded: str) -> list[list[float]]:
    """Decode Google-style encoded polyline to ``[[lat, lon], ...]``."""
    points: list[list[float]] = []
    index = lat = lng = 0
    length = len(encoded)
    while index < length:
        result = shift = 0
        while True:
            if index >= length:
                return points
            byte = ord(encoded[index]) - 63
            index += 1
            result |= (byte & 0x1F) << shift
            shift += 5
            if byte < 0x20:
                break
        lat += ~(result >> 1) if result & 1 else result >> 1
        result = shift = 0
        while True:
            if index >= length:
                return points
            byte = ord(encoded[index]) - 63
            index += 1
            result |= (byte & 0x1F) << shift
            shift += 5
            if byte < 0x20:
                break
        lng += ~(result >> 1) if result & 1 else result >> 1
        points.append([lat / 1e5, lng / 1e5])
    return points


def direction(
    origin_lat: float,
    origin_lon: float,
    dest_lat: float,
    dest_lon: float,
    mode: str = "pedestrian",
) -> dict | None:
    """``GET /v4/direction`` -> ``{distance_m, duration_min, polyline, source}``.

    ``mode="pedestrian"`` adds ``type=pedestrian``; ``mode="car"`` omits the
    parameter (Neshan's default is driving).
    """
    if None in (origin_lat, origin_lon, dest_lat, dest_lon):
        return None
    params: dict[str, Any] = {
        "origin": f"{origin_lat},{origin_lon}",
        "destination": f"{dest_lat},{dest_lon}",
    }
    if mode == "pedestrian":
        params["type"] = "pedestrian"
    data = _request("/v4/direction", params)
    if not data:
        return None
    routes = data.get("routes") or []
    if not routes:
        return None
    legs = (routes[0].get("legs") or [None])[0] or {}
    summary = legs.get("summary") or {}
    distance_m = summary.get("distance")
    duration_s = summary.get("duration")
    if distance_m is None or duration_s is None:
        return None
    geometry = (routes[0].get("geometry") or legs.get("geometry") or "") or ""
    polyline = decode_polyline(geometry) if geometry else None
    return {
        "distance_m": int(float(distance_m)),
        "duration_min": max(1, round(float(duration_s) / 60)),
        "polyline": polyline,
        "source": "neshan",
    }


def nearby_cafes(lat: float, lon: float, radius_m: int = 500) -> list[dict] | None:
    """``GET /v1/nearby`` cafes -> ``[{name, lat, lon, ...}]`` (None = unusable)."""
    if lat is None or lon is None:
        return None
    data = _request(
        "/v1/nearby",
        {"location": f"{lat},{lon}", "layer": "cafe", "searchRadius": radius_m},
    )
    items = data.get("items") if data else None
    if not items:
        return None
    cafes: list[dict] = []
    for item in items:
        location = item.get("location") or {}
        if isinstance(location, dict):
            item_lat, item_lon = location.get("y"), location.get("x")
        elif isinstance(location, (list, tuple)) and len(location) >= 2:
            item_lon, item_lat = location[0], location[1]
        else:
            continue
        if item_lat is None or item_lon is None:
            continue
        cafes.append(
            {
                "name": str(item.get("title") or "کافه"),
                "lat": float(item_lat),
                "lon": float(item_lon),
                "source": "neshan",
            }
        )
    return cafes or None
