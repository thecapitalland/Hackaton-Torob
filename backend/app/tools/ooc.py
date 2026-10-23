"""Out-of-catalog fallback.

When the requested product is not in the dataset we must be honest: say that
we did not find it, show *real* alternatives from the catalog (if any) and give
general shopping tips - clearly labelled as «اطلاعات عمومی، نه از داده‌های ترب».
"""

from __future__ import annotations

import json
import re
from pathlib import Path

from ..normalize import ACCESSORY_WORDS, CATEGORY_SYNONYMS, jaccard, normalize, tokenize, trigrams
from .catalog import all_category_names, products_in_category
from .markets import external_markets

# Words that must never appear inside a tip (the LLM is not allowed to invent
# prices or phone numbers).
MONEY_RE = re.compile(r"\d[\d٬,،\.]*\s*(تومان|تومن|تومان\s|میلیون|هزار\s?تومان)")
PHONE_RE = re.compile(r"(?:\+?98|0098|0)?9\d{9}|\b0\d{2,3}[-\s]?\d{7,8}\b")

# Filler words must be removed before comparing the query with the dataset
# categories: «زعفران می‌خوام» and «زعفران» are the same request.
FILLER_WORDS = {
    "میخوام",
    "میخواهم",
    "میخواستم",
    "می‌خوام",
    "می‌خواهم",
    "یه",
    "یک",
    "چند",
    "برای",
    "من",
    "ما",
    "لطفا",
    "لطفاً",
    "دنبال",
    "هستم",
    "لازم",
    "دارم",
    "می‌خواستم",
    "میخواستم",
    "بخرم",
    "خرید",
    "کجا",
    "پیدا",
    "کنم",
    "کنید",
    "دارید",
    "داره",
    "دارن",
    "سلام",
    "میخوای",
    "قیمت",
    "چنده",
    "چقدر",
    "است",
    "هست",
}

# Minimum trigram similarity between the query and a dataset category.
# Without it, a saffron query used to return pagers or perfumes just because
# they shared a couple of trigrams.
MIN_CATEGORY_SIMILARITY = 0.25
_TOKEN_STOP_WORDS = FILLER_WORDS | {
    "و", "یا", "برای", "قیمت", "بودجه", "میلیون", "تومان", "تومن", "تا", "زیر",
}


def _tokens(text: str) -> set[str]:
    tokens = set()
    for token in normalize(text).split():
        if len(token) <= 1 or token in _TOKEN_STOP_WORDS or token.isdigit():
            continue
        tokens.add({"کتونی": "کتانی"}.get(token, token))
    return tokens


def tehran_market_whitelist() -> dict[str, dict]:
    path = Path(__file__).resolve().parents[1] / "data" / "tehran_markets.json"
    try:
        entries = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}
    return {
        str(item["market_id"]): item
        for item in entries
        if item.get("market_id") and item.get("name_fa") and item.get("center")
    }


def whitelisted_market(market_id: str | None) -> dict | None:
    if not market_id:
        return None
    for item in tehran_market_whitelist().values():
        if market_id == item["market_id"] or market_id in item.get("aliases", []):
            return dict(item)
    return None


def clean_query(query: str) -> str:
    """Normalize text and drop filler words (no trigrams yet)."""
    normalized = normalize(query)
    tokens = [token for token in normalized.split() if token and token not in FILLER_WORDS]
    return " ".join(tokens)


def product_term(query: str) -> str:
    """The clean product term shown in the OOC header.

    «زعفران می‌خوام», «یه زعفران لازم دارم» and «زعفران بخرم» all become
    «زعفران»; the raw sentence is never repeated in the header.
    """
    cleaned = clean_query(query)
    return " ".join(cleaned.split()) or normalize(query)


def match_external_market(query: str) -> dict | None:
    """Find the Tehran market that usually hosts this kind of product."""
    if not query:
        return None
    normalized = normalize(query)
    tokens = [t for t in normalized.split() if len(t) > 2 and t not in FILLER_WORDS]
    best: tuple[float, dict] | None = None
    for market in external_markets():
        score = 0.0
        for keyword in market.get("keywords_fa") or []:
            key = normalize(keyword)
            if not key:
                continue
            if key in normalized:
                score += 2.0
            elif any(token and token in key for token in tokens):
                score += 0.8
        if score <= 0:
            continue
        if best is None or score > best[0]:
            best = (score, market)
    if best is None:
        return None
    market = dict(best[1])
    market["external"] = True
    market["center_approx"] = True
    return market


def _category_candidates(query: str, market: dict | None) -> list[str]:
    """Dataset categories that are closest to the query (best match first).

    Curated ``related_dataset_categories`` of the matched market always win
    (e.g. «سه‌تار» -> گیتار); every other category has to pass
    ``MIN_CATEGORY_SIMILARITY`` or it is dropped. Returning an empty list is
    better than suggesting a pager to someone who asked for saffron.
    """
    related = list((market or {}).get("related_dataset_categories") or [])
    cleaned = clean_query(query)
    if not cleaned:
        return []
    query_tri = trigrams(cleaned)
    query_tokens = _tokens(cleaned)
    normalized_query = normalize(cleaned)
    preferred_category: str | None = None
    for synonym, category in sorted(CATEGORY_SYNONYMS.items(), key=lambda item: len(normalize(item[0])), reverse=True):
        if normalize(synonym) and normalize(synonym) in normalized_query:
            preferred_category = category
            break
    scored: list[tuple[float, str]] = []
    for category in all_category_names():
        category_tokens = _tokens(category)
        shared = query_tokens & category_tokens
        token_score = len(shared) / max(1, len(query_tokens))
        tri_score = jaccard(query_tri, trigrams(category))
        score = max(tri_score, token_score)
        if category == preferred_category:
            score += 2.0
        if category in related:
            # curated relation: keep it even when the words are different
            scored.append((1.0 + score, category))
        elif score >= MIN_CATEGORY_SIMILARITY or shared:
            # Product-title overlap catches colloquial terms and brand/model
            # phrasing that is absent from the dataset's category label.
            title_overlap = 0.0
            for product in products_in_category(category, limit=8):
                product_tokens = _tokens(str(product.get("persian_title") or ""))
                if query_tokens and product_tokens:
                    title_overlap = max(
                        title_overlap,
                        len(query_tokens & product_tokens) / len(query_tokens),
                    )
            combined = max(score, title_overlap * 0.85)
            if combined >= MIN_CATEGORY_SIMILARITY or shared:
                scored.append((combined, category))
    scored.sort(key=lambda item: (-item[0], item[1]))
    return [category for _, category in scored[:3]]


def find_alternatives(query: str, market: dict | None = None, limit: int = 3) -> list[dict]:
    """Real products (from the catalog) that are close to the request.

    The closest category comes first - a hand-made carpet query should suggest
    hand-made carpets, not the most popular carpet category.
    """
    alternatives: list[dict] = []
    seen: set[str] = set()
    title_indexes: dict[str, int] = {}
    query_tokens = set(tokenize(query))
    for category in _category_candidates(query, market):
        products = sorted(
            products_in_category(category, limit=6),
            key=lambda item: (-(item.get("n_shops") or 0), item.get("min_price") or 0),
        )
        for product in products:
            title = str(product.get("persian_title") or "")
            title_tokens = set(tokenize(title))
            if any(
                not _phrase_in_tokens(query_tokens, word) and _phrase_in_tokens(title_tokens, word)
                for word in ACCESSORY_WORDS
            ):
                continue
            if product["product_id"] in seen:
                continue
            seen.add(product["product_id"])
            title_key = normalize(product.get("persian_title") or "")
            title_key = "".join(re.sub(r"\d+", "", token) for token in tokenize(title_key))
            title_key = f"{normalize(category)}|{title_key}"
            candidate = {
                "product_id": product["product_id"],
                "persian_title": product.get("persian_title"),
                "brand_name": product.get("brand_name"),
                "category_name": product.get("category_name"),
                "image": product.get("image_first"),
                "min_price": product.get("min_price"),
                "n_shops": product.get("n_shops"),
                "offers": product.get("n_shops") or 0,
            }
            duplicate_index = title_indexes.get(title_key)
            if duplicate_index is None:
                title_indexes[title_key] = len(alternatives)
                alternatives.append(candidate)
            elif (candidate.get("min_price") or 0) < (alternatives[duplicate_index].get("min_price") or 0):
                alternatives[duplicate_index] = candidate
    return alternatives[:limit]


def _phrase_in_tokens(tokens: set[str], phrase: str) -> bool:
    words = tokenize(phrase)
    return bool(words) and all(word in tokens for word in words)


GENERIC_TIPS = [
    "چند مغازه را با هم مقایسه کن",
    "فاکتور رسمی و ضمانت بگیر",
    "قبل از پرداخت، جنس را حضوری بررسی کن",
    "قیمت نهایی را قبل از پرداخت قطعی کن",
]


def sanitize_tips(tips: list[str]) -> list[str]:
    """Drop any tip that contains a price, a phone number or a shop name."""
    clean: list[str] = []
    for tip in tips:
        if not tip or not isinstance(tip, str):
            continue
        if MONEY_RE.search(tip) or PHONE_RE.search(tip):
            continue
        if re.search(r"\d", tip.replace("٫", "")):
            # digits are only allowed in non price contexts; be strict
            if MONEY_RE.search(tip):
                continue
        clean.append(tip.strip())
    return clean[:4]


def sanitize_guide_tips(tips: list[str], shop_names: list[str] | None = None) -> list[str]:
    """Conservative guardrail for generic OOC advice (no numbers/shops/addresses)."""
    known_shops = [normalize(name) for name in (shop_names or []) if len(normalize(name)) >= 3]
    market_terms = [
        normalize(name)
        for item in tehran_market_whitelist().values()
        for name in (item.get("name_fa"), *(item.get("aliases") or []))
        if name
    ]
    safe: list[str] = []
    for tip in tips:
        if not isinstance(tip, str) or not tip.strip():
            continue
        normalized = normalize(tip)
        if re.search(r"\d", normalize(tip)) or MONEY_RE.search(normalized) or PHONE_RE.search(normalized):
            continue
        if any(term in normalized for term in ("خیابان", "کوچه", "پلاک", "نشانی", "آدرس", "فروشگاه «", "مغازهٔ «")):
            continue
        if any(name in normalized for name in known_shops + market_terms):
            continue
        safe.append(tip.strip())
    return safe[:3]


def fallback_message(query: str, market: dict | None) -> str:
    if market and market.get("name_fa"):
        return (
            f"«{query}» را در داده‌های ترب پیدا نکردم. "
            f"معمولاً بورس این کالا در تهران «{market['name_fa']}» است؛ "
            "دستیارهای فروش آنجا معمولاً موجودی و قیمت را دقیق‌تر می‌گویند."
        )
    return f"«{query}» را در داده‌های ترب پیدا نکردم. بورس مشخصی برای این کالا نمی‌شناسم."


def market_tips(market: dict | None) -> list[str]:
    if not market:
        return []
    tips = []
    if market.get("name_fa"):
        tips.append(f"برای این کالا سراغ «{market['name_fa']}» در تهران برو")
    tips.append("قبل از خرید، قیمت نهایی را حضوری تأیید کن")
    return tips
