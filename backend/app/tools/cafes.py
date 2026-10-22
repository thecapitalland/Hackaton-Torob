"""Cafe suggestions for the trip plan - graceful fallback chain (Update #1):

1. Neshan ``nearby`` (only with ``NESHAN_API_KEY``);
2. OpenStreetMap Overpass (``amenity=cafe``);
3. static local list (``data/mock_cafes.json``, labelled «پیشنهاد نمونه»).

The chosen source is always visible in the UI, so the transparency rule holds.
"""

from __future__ import annotations

from ..data_static import load_cafes
from ..services import neshan, overpass
from .geo import haversine_m

LOCAL_LABEL = "پیشنهاد نمونه"
NESHAN_LABEL = "پیشنهاد نشان"
OSM_LABEL = "پیشنهاد نقشهٔ آزاد (OSM)"


def all_cafes() -> list[dict]:
    return load_cafes()


def _attach_distance(item: dict, lat: float | None, lon: float | None) -> dict:
    result = dict(item)
    if lat is not None and lon is not None:
        result["distance_m"] = haversine_m(lat, lon, result.get("lat"), result.get("lon"))
    return result


def nearest_local(lat: float | None = None, lon: float | None = None) -> dict | None:
    """Closest static mock cafe (always labelled «پیشنهاد نمونه»)."""
    cafes = all_cafes()
    if not cafes:
        return None
    if lat is None or lon is None:
        best = dict(cafes[0])
        best["distance_m"] = None
    else:
        ranked = [
            (haversine_m(lat, lon, cafe.get("lat"), cafe.get("lon")), cafe)
            for cafe in cafes
        ]
        ranked = [(d, c) for d, c in ranked if d is not None]
        if ranked:
            best = dict(min(ranked, key=lambda pair: pair[0])[1])
            best["distance_m"] = min(pair[0] for pair in ranked)
        else:
            best = dict(cafes[0])
            best["distance_m"] = None
    best["mock"] = True
    best["label"] = LOCAL_LABEL
    return best


def nearby(lat: float | None, lon: float | None, radius_m: int = 500) -> dict:
    """Full chain -> ``{"source": neshan|osm|local, "cafes": [...]}``.

    Each cafe carries ``source`` + ``label`` so the UI can show where the
    suggestion came from. The list is sorted by (rough) distance.
    """
    if lat is not None and lon is not None:
        for fetch, source, label in (
            (neshan.nearby_cafes, "neshan", NESHAN_LABEL),
            (overpass.cafes_near, "osm", OSM_LABEL),
        ):
            try:
                found = fetch(lat, lon, radius_m)
            except Exception:
                found = None
            if found:
                cafes = sorted(
                    (_attach_distance(item, lat, lon) for item in found),
                    key=lambda item: item.get("distance_m") or 0,
                )
                for cafe in cafes:
                    cafe["label"] = label
                return {"source": source, "cafes": cafes}
    # static list (also used when no coordinates are known)
    single = nearest_local(lat, lon)
    return {"source": "local", "cafes": [single] if single else []}


def nearest_cafe(lat: float | None, lon: float | None) -> dict | None:
    """Back-compat helper used by ``build_trip``: the top cafe of the chain."""
    cafes = nearby(lat, lon).get("cafes") or []
    return cafes[0] if cafes else None
