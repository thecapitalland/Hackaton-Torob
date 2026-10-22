"""The Torobche LangGraph agent.

One ``StateGraph`` handles the whole journey:

    START -> route_action
      chat           -> understand -> (missing?) clarify -> understand -> search
                    -> recommend | out_of_catalog
      select_product -> find_stores
      verify         -> plan_contact -> approve_contact (interrupt)
                    -> send_messages -> collect_replies -> parse_replies -> rerank
      trip           -> build_trip

The LLM is only used for language (slot extraction, explanations, message
drafting, reply parsing, tips).  All data - products, shops, prices, opening
hours, distances - comes from the catalog through the tools.
"""

from __future__ import annotations

import json
import time
from datetime import datetime
from typing import Any

from langgraph.graph import END, START, StateGraph
from langgraph.types import interrupt
from pydantic import BaseModel, Field, ValidationError

from . import prompts, rules
from .llm import get_client
from .normalize import (
    ACCESSORY_CATEGORIES,
    CATEGORY_SYNONYMS,
    NEIGHBORHOODS,
    fa_digits,
    normalize,
)
from .state import AgentState
from .tools import catalog, haggle, markets, ooc, ranking, seller_sim
from .tools.cafes import nearest_cafe
from .tools.hours import now_tehran
from .tools.markets import (
    balad_link,
    get_specialty_market,
    google_link,
    market_hours_text,
    neshan_link,
)

OOC_THRESHOLD = 0.35
MAX_QUESTIONS = 3

PRICE_FORMAT = {
    "warning_low": "قیمت برای این برند غیرعادی پایین است؛ اصالت را حضوری بررسی کن",
    "no_shops": "فقط در یک فروشگاه عرضه می‌شود؛ مقایسهٔ قیمت ممکن نیست",
}


# --------------------------------------------------------------------------
# pydantic models for the LLM output
# --------------------------------------------------------------------------


class UnderstandOut(BaseModel):
    category: str | None = None
    keywords: list[str] = Field(default_factory=list)
    budget_max: int | None = None
    budget_min: int | None = None
    location_label: str | None = None
    payment_in_person: bool | None = None
    installment: bool | None = None
    today: bool | None = None
    in_torob: bool | None = None


class ClarifyOut(BaseModel):
    text: str = ""
    chips: list[str] = Field(default_factory=list)


class RecommendOut(BaseModel):
    cards: list[dict] = Field(default_factory=list)
    market_line: str | None = None


class PlanContactOut(BaseModel):
    message: str = ""


class ParseReplyOut(BaseModel):
    availability: str = "unclear"
    price_toman: int | None = None
    price_changed: bool = False
    hours_text: str | None = None
    alternative: str | None = None
    installment: bool | None = None
    confidence: float = 0.5
    offer_status: str = "none"
    counter_price: int | None = None


class TripOut(BaseModel):
    summary: str = ""


class OocOut(BaseModel):
    message_fa: str = ""
    tips: list[str] = Field(default_factory=list)


class HaggleOut(BaseModel):
    lines: list[str] = Field(default_factory=list)


# --------------------------------------------------------------------------
# helpers
# --------------------------------------------------------------------------


def _trace(node: str, summary: str, started: float) -> dict:
    return {"node": node, "summary": summary, "ms": int((time.time() - started) * 1000)}


def _price_fa(value: int | None) -> str:
    if not value:
        return ""
    return fa_digits(f"{int(value):,}".replace(",", "٬"))


def _short(value: str, limit: int = 42) -> str:
    value = " ".join(str(value).split())
    if len(value) > limit:
        return value[: limit - 1] + "…"
    return value


def _known_categories() -> list[str]:
    return catalog.list_categories(limit=80)


def _resolve_location(label: str | None) -> dict | None:
    if not label:
        return None
    normalized = normalize(label)
    for name, (lat, lon) in NEIGHBORHOODS.items():
        if name == "بازار رضا":
            continue
        if normalize(name) in normalized or normalized in normalize(name):
            return {"label": name, "lat": lat, "lon": lon}
    return None


def _merge_slots(current: dict, extracted: dict) -> dict:
    """Merge a fresh extraction into the known slots (never erase a value)."""
    slots = dict(current or {})
    for key in (
        "category",
        "budget_max",
        "budget_min",
        "keywords",
        "payment_in_person",
        "installment",
        "today",
        "in_torob",
    ):
        value = extracted.get(key)
        if value in (None, [], ""):
            continue
        if key == "keywords":
            merged = list(slots.get("keywords") or [])
            for keyword in value:
                if keyword and keyword not in merged:
                    merged.append(keyword)
            slots["keywords"] = merged[:6]
            continue
        slots[key] = value

    location = extracted.get("location")
    if location:
        slots["location"] = location
    return slots


def _compute_missing(slots: dict, asked: int) -> list[str]:
    """Which slots are still missing.

    Only ``budget`` and ``location`` are mandatory.  The optional
    ``payment`` question is asked once (it is the first question of the demo
    script) and only when the user did not mention payment at all.

    When the product is clearly out of scope for the dataset (spices, antiques,
    second hand goods ...) we do not ask anything - the honest "not in the
    dataset" answer is more useful than a budget question.
    """
    if slots.get("in_torob") is False:
        return []
    missing: list[str] = []
    if (
        not slots.get("budget_max")
        and not slots.get("budget_min")
        and not slots.get("budget_skipped")
    ):
        missing.append("budget")
    if not slots.get("location") and not slots.get("location_skipped"):
        missing.append("location")
    if not missing and asked < 1:
        if slots.get("installment") is None and slots.get("payment_in_person") is None:
            missing.append("payment")
    return missing


# --------------------------------------------------------------------------
# node: understand
# --------------------------------------------------------------------------


def _rule_extract(text: str) -> dict:
    categories = _known_categories()
    budget_max, budget_min = rules.parse_budget(text)
    category = rules.detect_category(text, categories)
    location = rules.detect_location(text)
    stop_words = [location["label"]] if location else []
    keywords = rules.extract_keywords(text, category, stop_words)
    return {
        "category": category,
        "keywords": keywords,
        "budget_max": budget_max,
        "budget_min": budget_min,
        "location": location,
        "installment": rules.detect_installment(text),
        "today": rules.detect_today(text),
        "in_torob": rules.detect_in_torob(text),
    }


def _clean_keywords(keywords: list[str] | None, location: dict | None) -> list[str]:
    """Drop neighbourhood names and other non product words from the keywords."""
    if not keywords:
        return []
    location_words: set[str] = set()
    if location and location.get("label"):
        location_words.update(normalize(location["label"]).split())
    for name in NEIGHBORHOODS:
        if name == "بازار رضا":
            continue
        location_words.update(normalize(name).split())
    cleaned: list[str] = []
    for keyword in keywords:
        token = normalize(keyword)
        if not token:
            continue
        if token in location_words:
            continue
        if any(token in word or word in token for word in location_words if len(word) > 3):
            continue
        if token not in cleaned:
            cleaned.append(token)
    return cleaned[:6]


def _llm_extract(text: str, history: list[dict], current_slots: dict, last_question: str | None = None) -> dict:
    client = get_client()
    payload = {
        "message": text,
        "history": [
            {"role": m.get("role"), "content": m.get("content")}
            for m in history[-4:]
            if m.get("role") in {"user", "assistant"} and m.get("content")
        ],
        "last_question": last_question,
        "current_slots": current_slots,
    }
    raw = client.chat_json(prompts.understand_messages(payload))
    if not raw:
        return {}
    try:
        parsed = UnderstandOut(**raw)
    except ValidationError:
        return {}
    data = parsed.model_dump()
    if data.get("category") and data["category"] not in _known_categories():
        # keep only categories that really exist in the dataset
        category = rules.detect_category(data["category"], _known_categories())
        data["category"] = category
    location = _resolve_location(data.get("location_label"))
    if location:
        data["location"] = location
    else:
        data.pop("location", None)
        data["location_label"] = None
    return data


def understand(state: AgentState) -> dict:
    started = time.time()
    text = state.get("text") or ""
    history = state.get("messages") or []
    current = state.get("slots") or {}

    extracted = _llm_extract(text, history, current, state.get("last_question"))
    if not extracted:
        extracted = _rule_extract(text)
    slots = _merge_slots(current, extracted)

    # Update #1: a GPS position from the client fills an empty location slot,
    # but an explicit text location above always wins.
    user_location = state.get("user_location") or {}
    if (
        not slots.get("location")
        and user_location.get("lat") is not None
        and user_location.get("lon") is not None
    ):
        slots["location"] = {
            "label": user_location.get("label") or "موقعیت فعلی شما",
            "lat": user_location["lat"],
            "lon": user_location["lon"],
        }

    if not slots.get("query"):
        slots["query"] = text
    if slots.get("category") and slots["category"] in ACCESSORY_CATEGORIES:
        slots["category"] = None
    slots["keywords"] = _clean_keywords(slots.get("keywords"), slots.get("location"))

    asked = int(state.get("asked") or 0)
    missing = _compute_missing(slots, asked)

    summary_parts = []
    if slots.get("category"):
        summary_parts.append(slots["category"])
    if slots.get("budget_max"):
        summary_parts.append(f"بودجه {_price_fa(slots['budget_max'])}")
    if slots.get("location"):
        summary_parts.append(slots["location"].get("label", ""))
    if slots.get("installment"):
        summary_parts.append("قسطی")
    summary = "، ".join(part for part in summary_parts if part) or "نیاز ثبت شد"

    return {
        "slots": slots,
        "missing": missing,
        "trace": [_trace("understand", summary, started)],
    }


# --------------------------------------------------------------------------
# node: clarify (interrupt)
# --------------------------------------------------------------------------


def _llm_clarify(missing: list[str]) -> dict:
    client = get_client()
    payload = {"missing": missing, "missing_text": " و ".join(missing)}
    raw = client.chat_json(prompts.clarify_messages(payload))
    if not raw:
        return rules.clarify_fallback(missing)
    try:
        parsed = ClarifyOut(**raw)
    except ValidationError:
        return rules.clarify_fallback(missing)
    chips = [str(chip) for chip in parsed.chips if str(chip).strip()][:3]
    if not chips:
        return rules.clarify_fallback(missing)
    if chips[-1] != "مهم نیست":
        chips[-1] = "مهم نیست"
    text = parsed.text.strip() or rules.clarify_fallback(missing)["text"]
    return {"text": text, "chips": chips}


def _apply_clarify_answer(slot: str, answer: str, slots: dict) -> dict:
    """Map the answer of an interrupt to the slot that was asked about.

    LangGraph resumes *inside* ``clarify`` and then re-runs ``understand`` with
    the original user text, so without this mapping the answer («جمهوری»,
    «مهم نیست», «تا ۵ میلیون») would be completely ignored and the same
    question would be asked forever.
    """
    updated = dict(slots or {})
    if not answer or not answer.strip():
        return updated

    if rules.is_skip_answer(answer):
        # remember that the user explicitly said this slot does not matter;
        # ``_compute_missing`` checks these flags and never asks again
        updated[f"{slot}_skipped"] = True
        return updated

    if slot == "budget":
        budget_max, budget_min = rules.parse_budget(answer)
        if budget_max:
            updated["budget_max"] = budget_max
            updated["budget_skipped"] = False
        if budget_min:
            updated["budget_min"] = budget_min
            updated["budget_skipped"] = False
    elif slot == "location":
        location = rules.detect_location(answer)
        if location:
            updated["location"] = location
            updated["location_skipped"] = False
    elif slot == "payment":
        installment = rules.detect_installment(answer)
        if installment is not None:
            updated["installment"] = installment
        else:
            normalized = normalize(answer)
            if any(word in normalized for word in ("اره", "بله", "باشه")):
                updated["installment"] = True
            elif any(word in normalized for word in ("نقد", "نه")):
                updated["installment"] = False
    return updated


def clarify(state: AgentState) -> dict:
    started = time.time()
    missing = state.get("missing") or ["budget"]
    payload = _llm_clarify(missing)
    question = interrupt(
        {
            "type": "question",
            "id": f"q_{missing[0]}",
            "text": payload["text"],
            "chips": payload["chips"],
            "missing": missing,
        }
    )
    answer = question if isinstance(question, str) else str(question or "")
    slots = _apply_clarify_answer(missing[0], answer, state.get("slots") or {})
    return {
        "asked": int(state.get("asked") or 0) + 1,
        "slots": slots,
        "last_question": payload["text"],
        "messages": [{"role": "user", "content": answer}],
        "trace": [_trace("clarify", f"سؤال: {payload['text']}", started)],
    }


# --------------------------------------------------------------------------
# node: search
# --------------------------------------------------------------------------


def _search_with_fallback(slots: dict) -> tuple[list[dict], str]:
    """Search the catalog, relaxing the keyword filter step by step.

    The strict AND-search is the most precise, but a query like «هدفون
    بلوتوثی» would drop a product whose title does not literally contain
    «بلوتوث» (for example the Anker R50i).  That is why the OR-search is
    always merged in and the ranking (not the SQL order) decides.
    """
    keywords = list(slots.get("keywords") or [])
    category = slots.get("category")
    budget_max = slots.get("budget_max")
    budget_min = slots.get("budget_min")

    def run(words: list[str], cat: str | None, min_shops: int, mode: str) -> list[dict]:
        return catalog.search_products(
            words,
            cat,
            budget_max,
            budget_min,
            limit=30,
            min_shops=min_shops,
            match_mode=mode,
        )

    merged: list[dict] = []
    seen: set[str] = set()

    def collect(results: list[dict]) -> None:
        for item in results:
            if item["product_id"] in seen:
                continue
            seen.add(item["product_id"])
            merged.append(item)

    if keywords and category:
        collect(run(keywords, category, 2, "all"))
        collect(run(keywords, category, 2, "any"))
    if merged:
        merged.sort(key=lambda item: (-int(item.get("n_shops") or 0), int(item.get("min_price") or 0)))
        return merged, f"{len(merged)} کالا در «{category}» پیدا شد"

    attempts = [
        (keywords, category, 2, "all"),
        (keywords, category, 1, "any"),
        (keywords[:1], category, 2, "all"),
        ([], category, 2, "all"),
        ([], category, 1, "all"),
        (keywords, None, 1, "any"),
        ([], None, 1, "all"),
    ]
    for words, cat, min_shops, mode in attempts:
        results = run(words, cat, min_shops, mode)
        if results:
            collect(results)
            merged.sort(
                key=lambda item: (-int(item.get("n_shops") or 0), int(item.get("min_price") or 0))
            )
            return merged, f"{len(merged)} کالا با {'/'.join(words) if words else cat or 'همه'} پیدا شد"
    return [], "نتیجه‌ای پیدا نشد"


def search(state: AgentState) -> dict:
    started = time.time()
    slots = state.get("slots") or {}
    candidates, summary = _search_with_fallback(slots)
    scores = [
        catalog.search_score(slots.get("keywords") or [], candidate, slots.get("category"))
        for candidate in candidates
    ]
    top_score = max(scores) if scores else 0.0
    return {
        "candidates": candidates,
        "top_search_score": round(top_score, 3),
        "trace": [_trace("search", summary, started)],
    }


def route_after_search(state: AgentState) -> str:
    candidates = state.get("candidates") or []
    slots = state.get("slots") or {}
    if slots.get("in_torob") is False:
        return "out_of_catalog"
    if not candidates:
        return "out_of_catalog"
    if not slots.get("category") and not slots.get("keywords"):
        return "out_of_catalog"
    if float(state.get("top_search_score") or 0) < OOC_THRESHOLD:
        return "out_of_catalog"
    return "recommend"


# --------------------------------------------------------------------------
# node: recommend
# --------------------------------------------------------------------------


def _card_highlights(product: dict, limit: int = 3) -> list[str]:
    specs = catalog.parse_specs(product.get("specs"))
    highlights: list[str] = []
    seen: set[str] = set()
    for spec in specs:
        if not isinstance(spec, dict):
            continue
        key = str(spec.get("key") or "").strip()
        value = str(spec.get("value") or "").strip()
        if not value or len(value) > 40:
            continue
        text = f"{key}: {value}" if key and len(key) < 22 else value
        if text in seen:
            continue
        seen.add(text)
        highlights.append(text)
        if len(highlights) >= limit:
            break
    if not highlights:
        shops = int(product.get("n_shops") or 0)
        highlights.append(f"در {fa_digits(str(shops))} فروشگاه عرضه می‌شود")
    return highlights[:limit]


def _card_warnings(product: dict) -> list[str]:
    """Warn about an unusually low price (a cheap listing is not always real).

    The cheapest offer of a product is compared with the median of all its
    offers: the AirPods Pro 2 is listed at 830,000 toman while the market
    price of the same product is 2,320,000 - that is worth a warning.
    """
    warnings: list[str] = []
    min_price = product.get("min_price")
    median = product.get("median_price")
    if min_price and median and min_price < 0.4 * median:
        warnings.append(PRICE_FORMAT["warning_low"])
    if int(product.get("n_shops") or 0) < 2:
        warnings.append(PRICE_FORMAT["no_shops"])
    return warnings


def _llm_recommend(cards: list[dict], specialty: dict | None) -> dict:
    client = get_client()
    payload = {
        "cards": [
            {
                "product_id": card["product_id"],
                "title": card["title"],
                "brand": card.get("brand"),
                "min_price": card.get("min_price"),
                "n_shops": card.get("n_shops"),
                "highlights": card.get("highlights"),
            }
            for card in cards
        ],
        "specialty_market": specialty,
    }
    raw = client.chat_json(prompts.recommend_messages(payload))
    if not raw:
        return {}
    try:
        return RecommendOut(**raw).model_dump()
    except ValidationError:
        return {}


def recommend(state: AgentState) -> dict:
    started = time.time()
    slots = state.get("slots") or {}
    candidates = state.get("candidates") or []
    picked = catalog.pick_cards(candidates, slots.get("budget_max"))

    cards: list[dict] = []
    for item in picked:
        product = catalog.get_product(item["product_id"]) or item
        cards.append(
            {
                "kind": item.get("kind", "best"),
                "product_id": product["product_id"],
                "title": product.get("persian_title") or "",
                "brand": product.get("brand_name") or "",
                "image": catalog.first_image(product),
                "min_price": int(product.get("min_price") or 0),
                "median_price": int(product.get("median_price") or 0),
                "n_shops": int(product.get("n_shops") or 0),
                "highlights": _card_highlights(product),
                "why": "",
                "warnings": _card_warnings(product),
            }
        )

    specialty = get_specialty_market(slots.get("category"), slots.get("location"))

    llm_out = _llm_recommend(cards, specialty)
    llm_cards = {
        str(item.get("product_id")): item
        for item in (llm_out.get("cards") or [])
        if isinstance(item, dict)
    }
    for card in cards:
        item = llm_cards.get(card["product_id"])
        if not item:
            continue
        why = str(item.get("why") or "").strip()
        if why:
            card["why"] = why
        highlights = [str(h) for h in (item.get("highlights") or []) if str(h).strip()]
        if highlights:
            card["highlights"] = highlights[:3]
        warning = item.get("warning")
        if warning and str(warning).strip() and str(warning) not in card["warnings"]:
            card["warnings"].append(str(warning))

    for card in cards:
        if not card["why"]:
            card["why"] = (
                f"پرعرضه‌ترین گزینهٔ {card['brand'] or 'این دسته'} با "
                f"{fa_digits(str(card['n_shops']))} فروشگاه عرضه می‌شود."
            )

    chosen = {card["product_id"] for card in cards}
    more: list[dict] = []
    for candidate in candidates:
        if candidate["product_id"] in chosen:
            continue
        more.append(
            {
                "product_id": candidate["product_id"],
                "title": candidate.get("persian_title"),
                "brand": candidate.get("brand_name"),
                "image": catalog.first_image(candidate),
                "min_price": int(candidate.get("min_price") or 0),
                "n_shops": int(candidate.get("n_shops") or 0),
            }
        )
        if len(more) >= 6:
            break

    market_line = llm_out.get("market_line")
    if specialty and specialty.get("data_backed") and specialty.get("shops_in_market"):
        default_line = (
            f"برای این دسته، بورس اصلی تهران {specialty['name_fa']} است؛ "
            f"{fa_digits(str(specialty['shops_in_market']))} فروشگاه در داده‌ها، ارزش سر زدن دارد."
        )
        market_line = market_line or default_line

    message = "چند گزینهٔ خوب برایت پیدا کردم 👇"
    if market_line:
        message = f"{message}\n{market_line}"

    return {
        "cards": cards,
        "more": more,
        "specialty_market": specialty,
        "phase": "recommend",
        "messages": [{"role": "assistant", "content": message}],
        "trace": [_trace("recommend", f"{len(cards)} کارت و {len(more)} گزینهٔ دیگر", started)],
    }


# --------------------------------------------------------------------------
# node: out_of_catalog
# --------------------------------------------------------------------------


def out_of_catalog(state: AgentState) -> dict:
    started = time.time()
    slots = state.get("slots") or {}
    raw_query = slots.get("query") or state.get("text") or ""
    # QA2: the header must show the product term («زعفران»), never the whole
    # sentence («زعفران می‌خوام»).  All downstream lookups use the clean term.
    query = ooc.product_term(raw_query)
    market = ooc.match_external_market(query)
    alternatives = ooc.find_alternatives(query, market)

    client = get_client()
    payload = {
        "query": query,
        "alternatives": [
            {
                "persian_title": item.get("persian_title"),
                "category_name": item.get("category_name"),
                "offers": item.get("offers"),
            }
            for item in alternatives
        ],
        "market": market,
    }
    raw = client.chat_json(prompts.out_of_catalog_messages(payload))
    message_fa = ""
    tips: list[str] = []
    if raw:
        try:
            parsed = OocOut(**raw)
            message_fa = parsed.message_fa.strip()
            tips = [str(tip) for tip in parsed.tips if str(tip).strip()]
        except ValidationError:
            message_fa = ""
            tips = []
    tips = ooc.sanitize_tips(tips)
    if not message_fa:
        message_fa = ooc.fallback_message(query, market)
    if len(tips) < 3:
        tips = (tips + ooc.market_tips(market) + ooc.GENERIC_TIPS)[:4]

    market_payload = None
    if market:
        center = market.get("center") or [None, None]
        market_payload = {
            "market_id": market.get("market_id"),
            "name_fa": market.get("name_fa"),
            "center": center,
            "center_approx": True,
            "hours_external": market.get("hours_external") or {},
            "hours_text": market_hours_text(market),
            "sources": (market.get("hours_external") or {}).get("source") or market.get("sources") or [],
            "external": True,
            "route_url": neshan_link(center[0], center[1], 16),
        }

    payload_out = {
        "not_found": True,
        "query": query,
        "message_fa": message_fa,
        "alternatives": alternatives,
        "tips": tips[:4],
        "tips_label": "اطلاعات عمومی، نه از داده‌های ترب",
        "market": market_payload,
    }
    return {
        "ooc": payload_out,
        "phase": "out_of_catalog",
        "messages": [{"role": "assistant", "content": message_fa}],
        "trace": [_trace("out_of_catalog", f"«{query}» در داده‌ها نبود", started)],
    }


# --------------------------------------------------------------------------
# node: find_stores
# --------------------------------------------------------------------------


def _sort_shops(options: list[dict], sort: str) -> list[dict]:
    if sort == "cheapest":
        return sorted(options, key=lambda o: (o.get("price") or 0))
    if sort == "nearest":
        return sorted(
            options,
            key=lambda o: (o.get("distance_m") is None, o.get("distance_m") or 0, o.get("price") or 0),
        )
    if sort == "open":
        return sorted(
            options,
            key=lambda o: (
                {"open": 0, "unknown": 1, "closed": 2}.get(o.get("open_status"), 3),
                -(o.get("score") or 0),
            ),
        )
    return options


def _llm_haggle_lines(payload: dict) -> list[str] | None:
    client = get_client()
    raw = client.chat_json(prompts.haggle_messages(payload))
    if not raw:
        return None
    try:
        return [str(line) for line in HaggleOut(**raw).lines if str(line).strip()]
    except ValidationError:
        return None


def find_stores(state: AgentState) -> dict:
    started = time.time()
    slots = state.get("slots") or {}
    product_id = state.get("product_id") or state.get("selected_product_id")
    if not product_id:
        return {"phase": "stores", "shops": [], "trace": [_trace("find_stores", "محصولی انتخاب نشده", started)]}

    product = catalog.get_product(product_id)
    offers = catalog.get_offers_for_product(product_id)
    options = ranking.build_shop_options(
        offers, slots, now_tehran(), n_shops=int((product or {}).get("n_shops") or 0)
    )
    options = ranking.rank_shops(options, slots, now_tehran())
    options = _sort_shops(options, state.get("sort") or "recommended")

    # Haggle analysis for every row.  The LLM may phrase the lines for the
    # first five visible shops only; later rows get the same deterministic
    # template, so the response stays fast and LLM_MODE=off is complete.
    llm_on = get_client().enabled
    stats = haggle.price_stats(offers)
    for index, option in enumerate(options):
        option["haggle"] = haggle.build_haggle(
            option,
            offers,
            options,
            llm_on=llm_on and index < 5,
            llm_fn=_llm_haggle_lines if llm_on else None,
        )
    # keep the shared stats in the trace summary below readable
    top_stats = stats

    specialty = get_specialty_market(
        (product or {}).get("category_name") or slots.get("category"), slots.get("location")
    )

    return {
        "selected_product_id": product_id,
        "product": product,
        "shops": options,
        "specialty_market": specialty,
        "phase": "stores",
        "messages": [
            {
                "role": "assistant",
                "content": f"{fa_digits(str(len(options)))} فروشگاه این مدل رو دارن. "
                "می‌خوای از چند تا ازشون بپرسم موجوده؟",
            }
        ],
        "trace": [
            _trace(
                "find_stores",
                f"{len(options)} فروشگاه · میانه {_price_fa(top_stats['median'])} تومان",
                started,
            )
        ],
    }


# --------------------------------------------------------------------------
# verify: plan_contact -> approve_contact -> send -> collect -> parse -> rerank
# --------------------------------------------------------------------------


def _pick_target_shops(state: AgentState) -> list[dict]:
    shops = state.get("shops") or []
    requested = state.get("shop_ids") or []
    by_id = {shop["shop_id"]: shop for shop in shops}
    targets: list[dict] = []
    for shop_id in requested:
        shop = by_id.get(shop_id)
        if shop:
            targets.append(shop)
    if targets:
        return targets[:3]

    def priority(shop: dict) -> tuple[int, float]:
        rank = {"open": 0, "unknown": 1, "closed": 2}.get(shop.get("open_status"), 3)
        return (rank, -(shop.get("score") or 0))

    return sorted(shops, key=priority)[:3]


def plan_contact(state: AgentState) -> dict:
    started = time.time()
    slots = state.get("slots") or {}
    product = state.get("product") or {}
    targets = _pick_target_shops(state)
    title = product.get("persian_title") or "این مدل"
    target_prices = [
        int((target.get("haggle") or {}).get("target") or 0) for target in targets
    ]
    target_price = next((value for value in target_prices if value), None)

    client = get_client()
    payload = {
        "product": title,
        "product_id": product.get("product_id"),
        "shops": [
            {
                "shop_id": target["shop_id"],
                "name": target.get("name"),
                "price": target.get("price"),
                "target_price": int((target.get("haggle") or {}).get("target") or 0) or None,
            }
            for target in targets
        ],
        "target_price": target_price,
        "target_price_text": _price_fa(target_price),
        "installment": bool(slots.get("installment")),
        "today": bool(slots.get("today")),
    }
    raw = client.chat_json(prompts.plan_contact_messages(payload))
    message = ""
    if raw:
        try:
            message = PlanContactOut(**raw).message.strip()
        except ValidationError:
            message = ""
    if not message:
        message = rules.draft_message(
            title,
            [t.get("name", "") for t in targets],
            installment=bool(slots.get("installment")),
            today=bool(slots.get("today")),
            target_price=target_price,
        )

    return {
        "draft_message": message,
        "draft_targets": [
            {
                "shop_id": target["shop_id"],
                "name": target.get("name"),
                "price": target.get("price"),
                "target_price": int((target.get("haggle") or {}).get("target") or 0) or None,
            }
            for target in targets
        ],
        "phase": "verify",
        "trace": [_trace("plan_contact", f"پیام برای {len(targets)} فروشگاه", started)],
    }


def approve_contact(state: AgentState) -> dict:
    approval = interrupt(
        {
            "type": "approval",
            "channel": "simulated_sms",
            "targets": state.get("draft_targets") or [],
            "message": state.get("draft_message") or "",
            "privacy_note": "شماره‌ات به فروشنده داده نمی‌شه. در این نسخهٔ نمایشی پیام‌ها شبیه‌سازی می‌شن.",
        }
    )
    if not isinstance(approval, dict):
        approval = {"approved": False}
    return {"approval": approval}


def route_after_approval(state: AgentState) -> str:
    approval = state.get("approval") or {}
    return "send_messages" if approval.get("approved") else "reject"


def send_messages(state: AgentState) -> dict:
    started = time.time()
    approval = state.get("approval") or {}
    message = approval.get("message") or state.get("draft_message") or ""
    targets = state.get("draft_targets") or []
    allowed = approval.get("shop_ids")
    followups: list[dict] = []
    for target in targets:
        if allowed and target["shop_id"] not in allowed:
            continue
        followups.append(
            {
                "shop_id": target["shop_id"],
                "name": target.get("name"),
                "message": message,
                "status": "sent",
                "simulated": True,
                "raw_reply": None,
                "parsed": None,
                "target_price": target.get("target_price"),
                "delay_ms": seller_sim.delay_for(len(followups)),
            }
        )
    return {
        "followups": followups,
        "phase": "verify",
        "trace": [_trace("send_messages", f"{len(followups)} پیام شبیه‌سازی‌شده", started)],
    }


def reject(state: AgentState) -> dict:
    return {
        "phase": "stores",
        "followups": [],
        "messages": [{"role": "assistant", "content": "باشه، پیامی ارسال نشد."}],
        "trace": [_trace("reject", "ارسال رد شد", time.time())],
    }


def collect_replies(state: AgentState) -> dict:
    started = time.time()
    followups = list(state.get("followups") or [])
    shops = {shop["shop_id"]: shop for shop in (state.get("shops") or [])}
    for index, followup in enumerate(followups):
        shop = shops.get(followup["shop_id"])
        price = int((shop or {}).get("price") or 0)
        target_price = followup.get("target_price") or (
            (shop or {}).get("haggle") or {}
        ).get("target")
        detail = seller_sim.seller_reply_detail(
            followup["shop_id"],
            price,
            index,
            floor=(shop or {}).get("floor"),
            target_price=target_price,
        )
        followup["raw_reply"] = detail["text"]
        followup["status"] = detail["status"]
        followup["delay_ms"] = detail["delay_ms"]
        followup["simulated"] = True
        followup["offer_status"] = detail.get("offer_status", "none")
        followup["counter_price"] = detail.get("counter_price")
        if detail["status"] == "no_response":
            followup["call_transcript"] = seller_sim.call_transcript(followup.get("name") or "فروشگاه")
    return {
        "followups": followups,
        "trace": [_trace("collect_replies", f"{len(followups)} پاسخ شبیه‌سازی‌شده", started)],
    }


def _parse_one(raw: str, offer_price: int) -> dict:
    client = get_client()
    payload = {"raw_reply": raw, "offer_price": offer_price}
    parsed_raw = client.chat_json(prompts.parse_replies_messages(payload))
    if parsed_raw:
        try:
            parsed = ParseReplyOut(**parsed_raw).model_dump()
        except ValidationError:
            parsed = {}
        if parsed:
            if parsed.get("availability") not in {"available", "unavailable", "unclear"}:
                parsed["availability"] = "unclear"
            if parsed.get("offer_status") not in {"accepted", "countered", "none"}:
                parsed["offer_status"] = "none"
            if parsed["offer_status"] == "countered":
                counter = parsed.get("counter_price") or parsed.get("price_toman")
                parsed["counter_price"] = counter
                if counter:
                    parsed["price_toman"] = counter
            else:
                parsed["counter_price"] = None
            price = parsed.get("price_toman")
            if price is not None and offer_price:
                parsed["price_changed"] = abs(price - offer_price) / offer_price > 0.02
            return parsed
    return rules.parse_reply(raw, offer_price)


def parse_replies(state: AgentState) -> dict:
    started = time.time()
    followups = list(state.get("followups") or [])
    shops = {shop["shop_id"]: shop for shop in (state.get("shops") or [])}
    for followup in followups:
        if followup.get("status") == "no_response" or not followup.get("raw_reply"):
            followup["parsed"] = {
                "availability": "unclear",
                "price_toman": None,
                "price_changed": False,
                "hours_text": None,
                "confidence": 0.0,
                "offer_status": "none",
                "counter_price": None,
            }
            continue
        price = int((shops.get(followup["shop_id"]) or {}).get("price") or 0)
        followup["parsed"] = _parse_one(followup["raw_reply"], price)
    return {
        "followups": followups,
        "trace": [_trace("parse_replies", "پاسخ‌ها خوانده و ساختاریابی شد", started)],
    }


def rerank(state: AgentState) -> dict:
    started = time.time()
    shops = list(state.get("shops") or [])
    parsed_by_shop = {
        followup["shop_id"]: followup.get("parsed")
        for followup in (state.get("followups") or [])
        if followup.get("parsed")
    }
    shops = ranking.rerank_after_replies(shops, parsed_by_shop, now_tehran())

    confirmed = [
        shop
        for shop in shops
        if (parsed_by_shop.get(shop["shop_id"]) or {}).get("availability") == "available"
    ]
    # The inbox already renders «N فروشگاه تأیید کرد. پیشنهادم: <best shop>» +
    # the trip CTA, so the same summary must not be repeated as a chat bubble
    # above the cards. Only the "nobody confirmed" case needs a message.
    messages: list[dict] = []
    if shops and not confirmed:
        messages = [
            {"role": "assistant", "content": "متأسفانه تأییدی نگرفتیم؛ بهترین گزینه‌های فهرست همین‌هاست."}
        ]
    return {
        "shops": shops,
        "phase": "verify",
        "messages": messages,
        "trace": [_trace("rerank", "رتبه‌بندی با پاسخ‌ها به‌روز شد", started)],
    }


# --------------------------------------------------------------------------
# node: build_trip
# --------------------------------------------------------------------------


def build_trip(state: AgentState) -> dict:
    started = time.time()
    slots = state.get("slots") or {}
    shops = list(state.get("shops") or [])
    by_id = {shop["shop_id"]: shop for shop in shops}
    requested = state.get("shop_ids") or []
    parsed_by_shop = {
        followup["shop_id"]: followup.get("parsed")
        for followup in (state.get("followups") or [])
        if followup.get("parsed")
    }

    chosen: list[dict] = []
    for shop_id in requested:
        shop = by_id.get(shop_id)
        if shop:
            chosen.append(shop)
    if not chosen:
        confirmed = [
            shop
            for shop in shops
            if (parsed_by_shop.get(shop["shop_id"]) or {}).get("availability") == "available"
        ]
        chosen = confirmed[:1] or shops[:1]

    stop_shop = chosen[0] if chosen else None
    backup = chosen[1] if len(chosen) > 1 else None

    stops: list[dict] = []
    for index, shop in enumerate(chosen):
        distance = shop.get("distance_m")
        stops.append(
            {
                "order": index + 1,
                "shop_id": shop["shop_id"],
                "name": shop.get("name"),
                "address": shop.get("address"),
                "mall": shop.get("mall"),
                "floor": shop.get("floor"),
                "lat": shop.get("lat"),
                "lon": shop.get("lon"),
                "price": shop.get("price"),
                "arrive_hint": " · ".join(
                    part
                    for part in [
                        shop.get("mall") or "",
                        f"طبقه {shop.get('floor')}" if shop.get("floor") else "",
                        f"واحد {shop.get('unit')}" if shop.get("unit") else "",
                    ]
                    if part
                ),
                "walk_min_est": shop.get("walk_min_est")
                or (max(1, round((distance or 0) / 80)) if distance else None),
                "verified": (parsed_by_shop.get(shop["shop_id"]) or {}).get("availability")
                == "available",
                "links": {
                    "neshan": neshan_link(shop.get("lat"), shop.get("lon")),
                    "balad": balad_link(shop.get("lat"), shop.get("lon")),
                },
            }
        )

    cafe = None
    if stop_shop and stop_shop.get("lat") is not None:
        cafe = nearest_cafe(stop_shop.get("lat"), stop_shop.get("lon"))

    checklist = [
        "کارت ملی برای خرید قسطی",
        "تست صدا و اتصال قبل از پرداخت",
        "فاکتور و برچسب گارانتی",
        "قیمت نهایی را حضوری تأیید کن",
    ]

    client = get_client()
    payload = {
        "stops": [
            {"name": stop["name"], "verified": stop["verified"], "walk_min_est": stop["walk_min_est"]}
            for stop in stops
        ],
        "backup": backup.get("name") if backup else None,
        "cafe": cafe.get("name") if cafe else None,
    }
    raw = client.chat_json(prompts.build_trip_messages(payload))
    summary = ""
    if raw:
        try:
            summary = TripOut(**raw).summary.strip()
        except ValidationError:
            summary = ""
    if not summary:
        first = stops[0] if stops else None
        summary = (
            f"اول برو {first['name']}" if first else "برنامهٔ رفتن آماده نشد."
        )
        if first:
            summary += " (موجودیش تأیید شده)"
            if first.get("walk_min_est"):
                summary += f"؛ حدود {fa_digits(str(first['walk_min_est']))} دقیقه پیاده راه می‌فتهی (تخمینی)."
            if cafe:
                summary += f" بعدش کافهٔ «{cafe['name']}» برای یک استراحت کوتاه (پیشنهاد نمونه)."
            if backup:
                summary += f" پلن ب: {backup.get('name')}."

    lat = stop_shop.get("lat") if stop_shop else None
    lon = stop_shop.get("lon") if stop_shop else None
    trip = {
        "stops": stops,
        "backup": (
            {
                "shop_id": backup["shop_id"],
                "name": backup.get("name"),
                "address": backup.get("address"),
                "lat": backup.get("lat"),
                "lon": backup.get("lon"),
                "price": backup.get("price"),
            }
            if backup
            else None
        ),
        "cafe": cafe,
        "checklist": checklist,
        "links": {
            "neshan": neshan_link(lat, lon),
            "balad": balad_link(lat, lon),
            "google": google_link(lat, lon),
        },
        "summary": summary,
        "start": {
            "label": (slots.get("location") or {}).get("label") or "مبدأ: موقعیت شما",
            "lat": (slots.get("location") or {}).get("lat"),
            "lon": (slots.get("location") or {}).get("lon"),
        },
    }
    return {
        "trip": trip,
        "phase": "trip",
        "messages": [{"role": "assistant", "content": summary}],
        "trace": [_trace("build_trip", f"{len(stops)} توقف، پلن B و کافه", started)],
    }


# --------------------------------------------------------------------------
# routing
# --------------------------------------------------------------------------


def route_action(state: AgentState) -> str:
    action = state.get("action") or "chat"
    if action in {"select_product", "verify", "trip", "chat"}:
        return action
    return "chat"


def route_understand(state: AgentState) -> str:
    missing = state.get("missing") or []
    asked = int(state.get("asked") or 0)
    if missing and asked < MAX_QUESTIONS:
        return "clarify"
    return "search"


# --------------------------------------------------------------------------
# graph
# --------------------------------------------------------------------------


def build_graph(checkpointer=None) -> Any:
    graph = StateGraph(AgentState)

    graph.add_node("understand", understand)
    graph.add_node("clarify", clarify)
    graph.add_node("search", search)
    graph.add_node("recommend", recommend)
    graph.add_node("out_of_catalog", out_of_catalog)
    graph.add_node("find_stores", find_stores)
    graph.add_node("plan_contact", plan_contact)
    graph.add_node("approve_contact", approve_contact)
    graph.add_node("send_messages", send_messages)
    graph.add_node("collect_replies", collect_replies)
    graph.add_node("parse_replies", parse_replies)
    graph.add_node("rerank", rerank)
    graph.add_node("reject", reject)
    graph.add_node("build_trip", build_trip)

    graph.add_conditional_edges(
        START,
        route_action,
        {
            "chat": "understand",
            "select_product": "find_stores",
            "verify": "plan_contact",
            "trip": "build_trip",
        },
    )

    graph.add_conditional_edges(
        "understand",
        route_understand,
        {"clarify": "clarify", "search": "search"},
    )
    graph.add_edge("clarify", "understand")
    graph.add_conditional_edges(
        "search",
        route_after_search,
        {"recommend": "recommend", "out_of_catalog": "out_of_catalog"},
    )
    graph.add_edge("recommend", END)
    graph.add_edge("out_of_catalog", END)
    graph.add_edge("find_stores", END)

    graph.add_edge("plan_contact", "approve_contact")
    graph.add_conditional_edges(
        "approve_contact",
        route_after_approval,
        {"send_messages": "send_messages", "reject": "reject"},
    )
    graph.add_edge("send_messages", "collect_replies")
    graph.add_edge("collect_replies", "parse_replies")
    graph.add_edge("parse_replies", "rerank")
    graph.add_edge("rerank", END)
    graph.add_edge("reject", END)
    graph.add_edge("build_trip", END)

    return graph.compile(checkpointer=checkpointer)
