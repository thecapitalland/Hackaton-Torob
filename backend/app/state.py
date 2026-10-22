"""LangGraph state definitions for the Torobche agent."""

from __future__ import annotations

import operator
from typing import Annotated, Literal, Optional, TypedDict

Phase = Literal["discover", "recommend", "stores", "verify", "trip", "done", "out_of_catalog"]
Action = Literal["chat", "select_product", "verify", "trip"]


class Slots(TypedDict, total=False):
    """Everything the agent knows about the user's request."""

    query: str
    category: Optional[str]
    keywords: list[str]
    budget_max: Optional[int]
    budget_min: Optional[int]
    location: Optional[dict]  # {"label": "میدان فردوسی", "lat": 35.7010, "lon": 51.4187}
    location_skipped: bool
    budget_skipped: bool
    payment_in_person: bool
    installment: bool
    today: bool
    in_torob: bool


class Card(TypedDict, total=False):
    kind: Literal["best", "budget", "premium"]
    product_id: str
    title: str
    brand: str
    image: Optional[str]
    min_price: int
    median_price: int
    n_shops: int
    highlights: list[str]
    why: str
    warnings: list[str]


class ShopOption(TypedDict, total=False):
    shop_id: str
    offer_id: str
    name: str
    price: int
    address: str
    mall: Optional[str]
    floor: Optional[str]
    lat: Optional[float]
    lon: Optional[float]
    distance_m: Optional[int]
    open_status: Literal["open", "closed", "unknown"]
    open_text: str
    in_person_providers: list[str]
    warranty: Optional[dict]
    price_age_days: Optional[int]
    transparency: dict
    score: float
    why: str
    verify: Optional[dict]
    haggle: Optional[dict]
    negotiated_price: Optional[int]
    offer_status: Optional[str]


class Followup(TypedDict, total=False):
    shop_id: str
    name: str
    message: str
    status: Literal["draft", "approved", "sent", "replied", "no_response", "rejected"]
    raw_reply: Optional[str]
    parsed: Optional[dict]
    simulated: bool
    delay_ms: int
    call_transcript: Optional[str]
    target_price: Optional[int]
    offer_status: Optional[str]
    counter_price: Optional[int]


class AgentState(TypedDict, total=False):
    """The full graph state. ``messages`` and ``trace`` use additive reducers."""

    messages: Annotated[list[dict], operator.add]
    slots: Slots
    missing: list[str]
    asked: int
    last_question: Optional[str]
    # GPS position passed straight from the client (Update #1); consumed by
    # ``understand`` and never stored as a message.
    user_location: Optional[dict]
    candidates: list[dict]
    top_search_score: float
    cards: list[Card]
    more: list[dict]
    selected_product_id: Optional[str]
    product: Optional[dict]
    shops: list[ShopOption]
    followups: list[Followup]
    approval: Optional[dict]
    draft_message: Optional[str]
    draft_targets: list[dict]
    specialty_market: Optional[dict]
    ooc: Optional[dict]
    trip: Optional[dict]
    trace: Annotated[list[dict], operator.add]
    phase: Phase
    # per-request input fields (overwritten on every invocation)
    action: Action
    text: str
    product_id: Optional[str]
    shop_ids: list[str]
    sort: str
    location: Optional[dict]
