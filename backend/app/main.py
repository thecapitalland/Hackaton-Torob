"""FastAPI application for Torobche.

Every response carries ``session_id``, ``phase``, ``messages``, ``pending`` and
``trace`` so the frontend can render the conversation, the pending human
approval and the "how did we get here" drawer.
"""

from __future__ import annotations

import os
import secrets
import sqlite3
from pathlib import Path
from typing import Any

from dotenv import load_dotenv
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles
from langgraph.checkpoint.sqlite import SqliteSaver
from langgraph.types import Command
from pydantic import BaseModel, Field
from starlette.concurrency import run_in_threadpool

load_dotenv()

from .data_static import (  # noqa: E402
    checkpoint_path,
    demo_mode,
    llm_mode,
    load_markets,
)
from .graph import build_graph  # noqa: E402
from . import rules  # noqa: E402
from . import normalize as normalize_utils  # noqa: E402
from .llm import get_client  # noqa: E402
from .services import neshan as neshan_service  # noqa: E402
from .tools import cafes as cafes_tool  # noqa: E402
from .tools import catalog, markets  # noqa: E402
from .tools.geo import haversine_m  # noqa: E402
from .tools.hours import now_tehran  # noqa: E402

def _default_static_dir() -> Path:
    """Where the SPA build lives.

    ``npm run build`` now writes to ``static/`` (vite outDir ../static), but a
    fresh clone that only ran an older build may still have ``frontend/dist``.
    Prefer the documented path and fall back to dist only when it is missing.
    """
    root = Path(__file__).resolve().parents[2]
    static = root / "static"
    if static.exists():
        return static
    dist = root / "frontend" / "dist"
    return dist if dist.exists() else static


STATIC_DIR = (
    Path(os.environ["STATIC_DIR"])
    if os.environ.get("STATIC_DIR")
    else _default_static_dir()
)

app = FastAPI(title="Torobche", version="1.0.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)

# --------------------------------------------------------------------------
# graph + checkpointer
# --------------------------------------------------------------------------

_checkpointer: SqliteSaver | None = None
_graph: Any = None


def get_graph() -> Any:
    global _checkpointer, _graph
    if _graph is None:
        path = checkpoint_path()
        Path(path).parent.mkdir(parents=True, exist_ok=True)
        connection = sqlite3.connect(path, check_same_thread=False)
        _checkpointer = SqliteSaver(connection)
        _graph = build_graph(_checkpointer)
    return _graph


# --------------------------------------------------------------------------
# request models
# --------------------------------------------------------------------------


class ChatIn(BaseModel):
    session_id: str
    text: str = ""
    # optional GPS position from the client (Update #1), never required
    location: GeoOrigin | None = None


class ResumeIn(BaseModel):
    session_id: str
    value: Any = None


class SelectProductIn(BaseModel):
    session_id: str
    product_id: str
    sort: str = "recommended"


class VerifyIn(BaseModel):
    session_id: str
    shop_ids: list[str] = Field(default_factory=list)


class TripIn(BaseModel):
    session_id: str
    shop_ids: list[str] = Field(default_factory=list)


class GeoOrigin(BaseModel):
    lat: float
    lon: float


class LocationIn(BaseModel):
    session_id: str
    label: str = "موقعیت فعلی شما"
    lat: float
    lon: float


class GeoDestination(BaseModel):
    lat: float
    lon: float


class GeoRoutesIn(BaseModel):
    origin: GeoOrigin
    destinations: list[GeoDestination] = Field(max_length=50)
    mode: str = "pedestrian"  # pedestrian | car


# --------------------------------------------------------------------------
# helpers
# --------------------------------------------------------------------------


def config_for(session_id: str) -> dict:
    return {"configurable": {"thread_id": session_id}}


def _state_snapshot(session_id: str) -> dict:
    graph = get_graph()
    try:
        snapshot = graph.get_state(config_for(session_id))
        values = snapshot.values or {}
    except Exception:
        values = {}
    return {
        "messages": len(values.get("messages") or []),
        "trace": len(values.get("trace") or []),
        "values": values,
    }


def _error(code: str, message_fa: str, status: int = 400) -> JSONResponse:
    return JSONResponse(status_code=status, content={"error": {"code": code, "message_fa": message_fa}})


def _base_payload(session_id: str, values: dict, before: dict, pending: dict | None) -> dict:
    messages = values.get("messages") or []
    trace = values.get("trace") or []
    # the user messages are rendered optimistically by the client, so the API
    # only returns the assistant side of the conversation
    new_messages = [m for m in messages[before.get("messages", 0) :] if m.get("role") != "user"]
    return {
        "session_id": session_id,
        "phase": values.get("phase") or "discover",
        "messages": new_messages,
        "pending": pending,
        "trace": trace[before.get("trace", 0) :],
        "slots": values.get("slots") or {},
    }


def _extract_pending(result: Any) -> dict | None:
    interrupts = (result or {}).get("__interrupt__") if isinstance(result, dict) else None
    if not interrupts:
        return None
    first = interrupts[0]
    payload = getattr(first, "value", None)
    if payload is None and isinstance(first, dict):
        payload = first.get("value")
    return payload


def _pending_question(session_id: str) -> dict | None:
    """The clarify question currently waiting for an answer, if any."""
    graph = get_graph()
    try:
        snapshot = graph.get_state(config_for(session_id))
    except Exception:
        return None
    for task in getattr(snapshot, "tasks", None) or []:
        for invocation in getattr(task, "interrupts", None) or []:
            value = getattr(invocation, "value", None)
            if isinstance(value, dict) and value.get("type") == "question":
                return value
    return None


def _chat_answers_question(question: dict, text: str) -> bool:
    """Does the typed message look like an answer to the pending question?

    FIX5-D2: only *bare* answers count.  A message carrying product words
    (its own category, more than two residual tokens after removing
    neighbourhood/budget/payment words) is a real request and must go the
    normal chat path - the slots it mentions are filled by ``understand``.
    """
    # a genuine shopping request always wins over a pending question
    if rules.detect_category(text) is not None:
        return False
    if rules.is_skip_answer(text):
        return True
    if len(rules.residual_tokens(text)) > 2:
        return False
    identifier = str(question.get("id") or "")
    slot = identifier[2:] if identifier.startswith("q_") else ""
    if not slot:
        missing = question.get("missing") or []
        slot = str(missing[0]) if missing else ""
    if slot == "location":
        return rules.detect_location(text) is not None
    if slot == "budget":
        budget_max, budget_min = rules.parse_budget(text)
        return budget_max is not None or budget_min is not None
    if slot == "payment":
        return rules.detect_installment(text) is not None or rules.is_yes_answer(text)
    return False


async def _invoke(session_id: str, payload: dict) -> Any:
    graph = get_graph()
    return await run_in_threadpool(graph.invoke, payload, config_for(session_id))


async def _resume(session_id: str, value: Any) -> Any:
    graph = get_graph()
    return await run_in_threadpool(
        graph.invoke, Command(resume=value), config_for(session_id)
    )


# --------------------------------------------------------------------------
# endpoints
# --------------------------------------------------------------------------


@app.get("/api/health")
async def health() -> dict:
    counts = {"products": 0, "offers": 0, "shops": 0}
    try:
        conn = catalog.get_conn()
        for table in ("products", "offers", "shops"):
            counts[table] = conn.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]
    except Exception:
        pass
    client = get_client()
    return {
        "ok": True,
        "catalog_rows": counts,
        "llm_mode": llm_mode(),
        "model": client.model,
        "tz": "Asia/Tehran",
        "demo_mode": demo_mode(),
        "now": now_tehran().isoformat(),
        "markets": len(load_markets().get("markets") or []),
    }


@app.get("/health")
async def health_alias() -> dict:
    """Alias for external pings that hit /health instead of /api/health."""
    return await health()


@app.get("/api/geo/reverse")
async def geo_reverse(lat: float, lon: float) -> dict:
    """Reverse geocoding: Neshan first, nearest known neighbourhood as fallback."""
    address = neshan_service.reverse_geocode(lat, lon)
    if address:
        return address
    return _nearest_neighbourhood(lat, lon)


@app.get("/api/geo/search")
async def geo_search(q: str = "") -> dict:
    """Search Neshan when configured, then merge deterministic local hoods."""
    query = q.strip()
    if len(query) < 2:
        return {"results": []}
    candidates = list(neshan_service.search(query) or [])
    candidates.extend(normalize_utils.search_neighbourhoods(query, limit=8))
    results: list[dict] = []
    seen: set[str] = set()
    for item in candidates:
        label = str(item.get("name_fa") or item.get("label") or "").strip()
        if not label or item.get("lat") is None or item.get("lon") is None:
            continue
        key = normalize_utils.normalize(label)
        if key in seen:
            continue
        seen.add(key)
        results.append({
            "name_fa": label,
            "lat": float(item["lat"]),
            "lon": float(item["lon"]),
            "source": item.get("source") or "fallback",
        })
        if len(results) == 8:
            break
    return {"results": results}


@app.post("/api/location")
async def update_location(body: LocationIn) -> dict:
    """Change the origin in the current session and re-rank its selected model."""
    before = _state_snapshot(body.session_id)
    values_before = before.get("values") or {}
    product_id = values_before.get("selected_product_id") or (values_before.get("product") or {}).get("product_id")
    result = await _invoke(
        body.session_id,
        {
            "action": "set_location",
            "location_update": {"label": body.label, "lat": body.lat, "lon": body.lon},
            "product_id": product_id,
        },
    )
    values = (result or {}).get("values") or _state_snapshot(body.session_id)["values"]
    payload = _base_payload(body.session_id, values, before, None)
    payload["product"] = values.get("product")
    payload["shops"] = values.get("shops") or []
    payload["map_center"] = _map_center(payload["shops"])
    payload["specialty_market"] = values.get("specialty_market")
    return payload


@app.post("/api/geo/routes")
async def geo_routes(body: GeoRoutesIn) -> dict:
    """Route + ETA per destination; estimate from straight line when Neshan is off.

    A destination with no coordinates is answered with a null entry so the
    caller can align results by index.
    """
    mode = "pedestrian" if body.mode != "car" else "car"
    results: list[dict | None] = []
    for destination in body.destinations[:10]:
        results.append(_one_route(body.origin, destination, mode))
    return {"results": results, "mode": mode}


@app.get("/api/cafes/nearby")
async def cafes_nearby(lat: float, lon: float, radius: int = 500) -> dict:
    """Cafe suggestions: Neshan -> OSM -> local static list (always labelled)."""
    payload = cafes_tool.nearby(lat, lon, min(max(radius, 100), 1000))
    payload["neshan_available"] = neshan_service._is_available()
    return payload


def _nearest_neighbourhood(lat: float, lon: float) -> dict:
    from .normalize import NEIGHBORHOODS

    best_label: str | None = None
    best_distance: int | None = None
    for label, (nlat, nlon) in NEIGHBORHOODS.items():
        distance = haversine_m(lat, lon, nlat, nlon)
        if distance is None:
            continue
        if best_distance is None or distance < best_distance:
            best_distance = distance
            best_label = label
    label = best_label or "تهران"
    return {
        "formatted_address": f"حوالی {label} (موقعیت تخمینی)",
        "neighbourhood": label,
        "source": "fallback",
    }


def _one_route(origin: GeoOrigin, destination: GeoDestination, mode: str) -> dict | None:
    if destination.lat is None or destination.lon is None:
        return None
    route = neshan_service.direction(
        origin.lat, origin.lon, destination.lat, destination.lon, mode
    )
    if route:
        return {**route, "estimated": False}
    # graceful fallback: 1.3x straight line, labelled «تقریبی» in the UI
    straight = haversine_m(origin.lat, origin.lon, destination.lat, destination.lon)
    if straight is None:
        return None
    distance_m = int(straight * 1.3)
    speed = 80 if mode == "pedestrian" else 450  # ~4.8 km/h walk / ~27 km/h car
    return {
        "distance_m": distance_m,
        "duration_min": max(1, round(distance_m / speed)),
        "polyline": None,
        "source": "estimate",
        "estimated": True,
    }


@app.post("/api/session")
async def new_session() -> dict:
    return {"session_id": "s_" + secrets.token_hex(2)}


@app.post("/api/chat")
async def chat(body: ChatIn) -> Any:
    if not body.text.strip():
        return _error("BAD_REQUEST", "پیام خالی است.")
    # FIX4-P1: a typed answer to the pending clarify question resolves it
    # (same flow as the chip buttons) instead of being dropped silently.
    question = _pending_question(body.session_id)
    if question and _chat_answers_question(question, body.text):
        return await _resume_and_respond(body.session_id, body.text)
    before = _state_snapshot(body.session_id)
    payload: dict[str, Any] = {
        "action": "chat",
        "text": body.text,
        "messages": [{"role": "user", "content": body.text}],
    }
    if question:
        # The user chose to continue with a regular message rather than
        # answer the open question. The interrupted clarify node has not
        # returned yet, so count that question as asked before rebuilding the
        # turn; otherwise the optional payment question can unexpectedly pop
        # up after the user's complete product/location request.
        payload["asked"] = max(int((before.get("values") or {}).get("asked") or 0), 1)
    if body.location:
        payload["user_location"] = body.location.model_dump()
    result = await _invoke(body.session_id, payload)
    pending = _extract_pending(result)
    values = (result or {}).get("values") or {}
    if not values:
        values = _state_snapshot(body.session_id)["values"]
    payload = _base_payload(body.session_id, values, before, pending)
    payload["cards"] = values.get("cards") or []
    payload["more"] = values.get("more") or []
    payload["specialty_market"] = values.get("specialty_market")
    if values.get("phase") == "out_of_catalog":
        payload["mode"] = "out_of_catalog"
        payload["ooc"] = values.get("ooc") or {}
    if values.get("phase") == "compare":
        payload["mode"] = "compare"
        payload["compare"] = values.get("compare") or {}
    return payload


async def _resume_and_respond(session_id: str, value: Any) -> Any:
    """Resume the interrupted clarify step and build the response payload."""
    before = _state_snapshot(session_id)
    result = await _resume(session_id, value)
    pending = _extract_pending(result)
    values = (result or {}).get("values") or {}
    if not values:
        values = _state_snapshot(session_id)["values"]
    payload = _base_payload(session_id, values, before, pending)
    payload["cards"] = values.get("cards") or []
    payload["more"] = values.get("more") or []
    payload["specialty_market"] = values.get("specialty_market")
    payload["shops"] = values.get("shops") or []
    payload["followups"] = values.get("followups") or []
    payload["product"] = values.get("product")
    payload["trip"] = values.get("trip")
    if values.get("phase") == "out_of_catalog":
        payload["mode"] = "out_of_catalog"
        payload["ooc"] = values.get("ooc") or {}
    if values.get("phase") == "compare":
        payload["mode"] = "compare"
        payload["compare"] = values.get("compare") or {}
    return payload


@app.post("/api/resume")
async def resume(body: ResumeIn) -> Any:
    return await _resume_and_respond(body.session_id, body.value)


@app.post("/api/select_product")
async def select_product(body: SelectProductIn) -> Any:
    before = _state_snapshot(body.session_id)
    result = await _invoke(
        body.session_id,
        {
            "action": "select_product",
            "product_id": body.product_id,
            "sort": body.sort,
        },
    )
    pending = _extract_pending(result)
    values = (result or {}).get("values") or {}
    if not values:
        values = _state_snapshot(body.session_id)["values"]
    payload = _base_payload(body.session_id, values, before, pending)
    payload["product"] = values.get("product")
    payload["shops"] = values.get("shops") or []
    payload["specialty_market"] = values.get("specialty_market")
    payload["map_center"] = _map_center(values.get("shops") or [])
    return payload


@app.post("/api/verify")
async def verify(body: VerifyIn) -> Any:
    before = _state_snapshot(body.session_id)
    result = await _invoke(
        body.session_id,
        {"action": "verify", "shop_ids": body.shop_ids},
    )
    pending = _extract_pending(result)
    values = (result or {}).get("values") or {}
    if not values:
        values = _state_snapshot(body.session_id)["values"]
    payload = _base_payload(body.session_id, values, before, pending)
    payload["followups"] = values.get("followups") or []
    payload["shops"] = values.get("shops") or []
    return payload


@app.post("/api/trip")
async def trip(body: TripIn) -> Any:
    before = _state_snapshot(body.session_id)
    result = await _invoke(
        body.session_id,
        {"action": "trip", "shop_ids": body.shop_ids},
    )
    pending = _extract_pending(result)
    values = (result or {}).get("values") or {}
    if not values:
        values = _state_snapshot(body.session_id)["values"]
    payload = _base_payload(body.session_id, values, before, pending)
    payload["trip"] = values.get("trip")
    payload["shops"] = values.get("shops") or []
    return payload


@app.get("/api/specialty_market")
async def specialty_market(category: str = "", lat: float | None = None, lon: float | None = None) -> dict:
    location = None
    if lat is not None and lon is not None:
        location = {"lat": lat, "lon": lon}
    market = markets.get_specialty_market(category, location)
    return {"market": market}


def _map_center(shops: list[dict]) -> dict | None:
    points = [
        (shop.get("lat"), shop.get("lon"))
        for shop in shops
        if shop.get("lat") is not None and shop.get("lon") is not None
    ]
    if not points:
        return None
    lat = sum(point[0] for point in points) / len(points)
    lon = sum(point[1] for point in points) / len(points)
    return {"lat": lat, "lon": lon}


# --------------------------------------------------------------------------
# static SPA (mounted after the API routes)
# --------------------------------------------------------------------------

if STATIC_DIR.exists():
    app.mount("/", StaticFiles(directory=str(STATIC_DIR), html=True), name="spa")
