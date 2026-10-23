"""Deterministic fallbacks used when the LLM is off or unavailable.

These rules keep the whole product flow working with ``LLM_MODE=off``:
slot extraction, clarifying questions, seller reply parsing and the seller
message draft.
"""

from __future__ import annotations

import re

from .normalize import CATEGORY_SYNONYMS, NEIGHBORHOODS, fa_digits, normalize

BUDGET_RE = re.compile(r"(\d+(?:[\.,٫]\d+)?)\s*(میلیون|میلیون\s+تومان|تومن|تومان|هزار|م)\b")
RIALS_RE = re.compile(r"(\d+(?:[\.,٫]\d+)?)\s*ریال")
NUMBER_RE = re.compile(r"(\d+(?:[\.,٫]\d+)?)")

INSTALLMENT_WORDS = ("قسطی", "اقساط", "اقساطی", "ترب پی", "ترب‌پی", "چک", "بن‌پی", "خیلی")
CASH_WORDS = ("نقد", "ک cash", "پرداخت نقدی")
TODAY_WORDS = ("امروز", "همین حالا", "همین امروز", "الان", "فوری", "امروزه")
TOMORROW_WORDS = ("فردا", "پس فردا")
NOT_IN_TOROB_WORDS = (
    "دست دوم",
    "دست‌دوم",
    "دستدوم",
    "عتیقه",
    "فله",
    "دستباف دست",
    "کار دست",
    "ادویه",
    "زعفران",
    "زعفرون",
    "عطاری",
)

AVAILABLE_WORDS = ("موجود", "موجوده", "داریم", "هست", "داره", "available")
UNAVAILABLE_WORDS = ("تموم", "ناموجود", "نداریم", "نداره", "نیست", "sold out")
UNCLEAR_WORDS = ("چک میکنم", "چک می کنم", "می پرسم", "بعدا", "بعداً", "یه لحظه", "بررسی میکنم")

# FIX5: refinement wording extends the *current* search («ارزون‌تر», «هم
# بگرد»); it must never rebuild the query into those words.
REFINEMENT_WORDS = (
    "ارزون‌تر",
    "ارزونتر",
    "ارزان‌تر",
    "گرانتر",
    "گرون‌تر",
    "نزدیک‌تر",
    "دورتر",
    "هم بگرد",
    "بگرد",
)

# yes-style tokens (post-normalize) used to read bare confirmations
# («آره» -> «اره» after normalization)
YES_ANSWER_TOKENS = frozenset({"اره", "بله", "باشه", "اوکی", "حله", "تایید"})


def is_yes_answer(text: str) -> bool:
    tokens = set(re.findall(r"[^\W_]+", normalize(text), flags=re.UNICODE))
    return bool(tokens & YES_ANSWER_TOKENS)

UNIT_MULTIPLIERS = {
    "میلیون": 1_000_000,
    "میلیون تومان": 1_000_000,
    "تومن": 1,
    "تومان": 1,
    "هزار": 1_000,
    "م": 1_000_000,
}

# words that are question/shopping filler, never a product term
_COMPARE_FILLERS = {
    "میخوام",
    "می خواهم",
    "میخواهم",
    "بخرم",
    "بخر",
    "خرید",
    "کدوم",
    "کدام",
    "بهتره",
    "بهتر است",
    "بهتر",
    "دیگه",
    "دیگر",
    "چی",
    "چیه",
    "چه",
    "هر",
    "یک",
    "یه",
    "برای",
    "من",
    "رو",
    "تو",
    "حتما",
    "لطفا",
    "قیمت",
    "قیمتش",
    "دو",
    "با",
    "و",
    "از",
    "در",
    "است",
    "هست",
    "هس",
    "؟",
}

# hints (normalized) that a listing may be a replica / «درجه یک» copy
_REPLICA_HINTS = (
    "کپی",
    "ریپلیکا",
    "کی دی",
    "replica",
    "فیک",
    "درجه",
)


def _number(value: str) -> float:
    return float(value.replace(",", "").replace("٫", ".").replace("٬", ""))


def parse_budget(text: str) -> tuple[int | None, int | None]:
    """Return ``(budget_max, budget_min)`` in toman."""
    if not text:
        return None, None
    normalized = normalize(text)
    budget_max: int | None = None
    budget_min: int | None = None

    rials = RIALS_RE.search(normalized)
    if rials:
        amount = int(_number(rials.group(1)) / 10)
        if "بیشتر" in normalized or "بالای" in normalized or "حداقل" in normalized:
            budget_min = amount
        else:
            budget_max = amount

    match = BUDGET_RE.search(normalized)
    if match:
        amount = int(_number(match.group(1)) * UNIT_MULTIPLIERS.get(match.group(2).strip(), 1))
        if "بیشتر" in normalized or "بالای" in normalized or "حداقل" in normalized:
            budget_min = amount
        else:
            budget_max = amount
    return budget_max, budget_min


def detect_category(text: str, known_categories: list[str] | None = None) -> str | None:
    """Map free text to a dataset category."""
    if not text:
        return None
    normalized = normalize(text)
    best: tuple[int, str] | None = None
    for synonym, category in CATEGORY_SYNONYMS.items():
        key = normalize(synonym)
        if key and key in normalized:
            score = len(key)
            if best is None or score > best[0]:
                best = (score, category)
    if best:
        return best[1]
    if known_categories:
        for category in known_categories:
            key = normalize(category)
            if key and key in normalized:
                return category
    return None


def detect_location(text: str) -> dict | None:
    """Find a known Tehran neighbourhood in the text."""
    if not text:
        return None
    normalized = normalize(text)
    for label, (lat, lon) in NEIGHBORHOODS.items():
        if label == "بازار رضا":
            continue  # Mashhad - never part of the Tehran flow
        key = normalize(label)
        if key and key in normalized:
            return {"label": label, "lat": lat, "lon": lon}
    return None


def detect_installment(text: str) -> bool | None:
    normalized = normalize(text)
    for word in INSTALLMENT_WORDS:
        if normalize(word) in normalized:
            return True
    for word in CASH_WORDS:
        if normalize(word) in normalized:
            return False
    return None


def detect_today(text: str) -> bool | None:
    normalized = normalize(text)
    for word in TODAY_WORDS:
        if normalize(word) in normalized:
            return True
    for word in TOMORROW_WORDS:
        if normalize(word) in normalized:
            return False
    return None


def detect_in_torob(text: str) -> bool:
    normalized = normalize(text)
    for word in NOT_IN_TOROB_WORDS:
        if normalize(word) in normalized:
            return False
    return True


def _strip_slot_words(text: str) -> str:
    """Normalized text without location, payment and skip wording.

    These words describe *where/how* the user shops, never *what* they buy;
    leaking them into keywords (or the D2 residual check) breaks searches.
    """
    normalized = normalize(text)
    for label in NEIGHBORHOODS:
        if label == "بازار رضا":
            continue
        normalized = normalized.replace(normalize(label), " ")
    for word in (*INSTALLMENT_WORDS, *CASH_WORDS, *SKIP_ANSWER_WORDS):
        cleaned = normalize(word)
        if cleaned:
            normalized = normalized.replace(cleaned, " ")
    for token in ("محله", "پرداخت", "نقدی"):
        normalized = normalized.replace(token, " ")
    return normalized



# words that never become search terms / D2 residual tokens
_KEYWORD_STOP_WORDS: frozenset[str] = frozenset({
    "میخوام",
    "میخواهم",
    "میخواهیم",
    "میخواستم",
    "بخرم",
    "بخریم",
    "خرید",
    "پیدا",
    "کن",
    "کنید",
    "کنم",
    "لطفا",
    "لطفاً",
    "امروز",
    "حضوری",
    "نزدیک",
    "به",
    "از",
    "در",
    "با",
    "و",
    "یا",
    "یک",
    "یه",
    "که",
    "برای",
    "من",
    "خوب",
    "بهترین",
    "عالی",
    "خانم",
    "آقا",
    "قیمت",
    "ارزان",
    "گرون",
    "ارزون",
    "میلیون",
    "تومان",
    "تومن",
    "میلیونی",
    "تا",
    "زیر",
    "حدود",
    "بودجه",
    "دست",
    "دوم",
    "زنانه",
    "مردانه",
    "میخوام بخرم",
    # intent / usage words: they describe *why* the product is bought,
    # not *which* product it is, so they must never become search terms
    "برنامه",
    "برنامه نویسی",
    "برنامهنویسی",
    "نویسی",
    "گیمینگ",
    "گیم",
    "بازی",
    "دانشجویی",
    "دانشجو",
    "دانشگاهی",
    "استفاده",
    "مصرف",
    "روزمره",
    "مناسب",
    "کیفیت",
    "کاربری",
    # generic product nouns: the detected category already covers them.
    # Keeping them would split «لپ تاپ» into «تاپ» and break the AND
    # search, so they are removed before tokenization.
    "لپ تاپ",
    "لپتاپ",
    "لپ تپ",
    "لپ",
    "تاپ",
    "نوت بوک",
    "نوتبوک",
    "نوت",
    "بوک",
})


def _keyword_stop_words(category: str | None = None, extra: list[str] | None = None) -> set[str]:
    stop = set(_KEYWORD_STOP_WORDS)
    for word in extra or []:
        cleaned = normalize(word)
        if cleaned:
            stop.add(cleaned)
            for part in cleaned.split():
                if len(part) > 3:
                    stop.add(part)
    if category:
        stop.add(normalize(category))
        # every part of the category name (even short ones like «لپ»/«تاپ»)
        stop.update(normalize(category).split())
    return stop


def extract_keywords(text: str, category: str | None = None, extra_stop_words: list[str] | None = None) -> list[str]:
    """Very small keyword extractor: keep the product-ish words of the query."""
    if not text:
        return []
    stop_words = _keyword_stop_words(category, extra_stop_words)
    normalized_text = _strip_slot_words(text)
    # remove multi-word category nouns *before* tokenizing so «لپ تاپ» can
    # never leak a bare «تاپ» into the keyword list
    for phrase in ("لپ تاپ", "لپ تپ", "نوت بوک"):
        normalized_text = normalized_text.replace(phrase, " ")
    tokens = re.findall(r"[^\W_]+", normalized_text, flags=re.UNICODE)
    keywords: list[str] = []
    for token in tokens:
        if len(token) < 3 or token in stop_words:
            continue
        if token.isdigit():
            continue
        keywords.append(token)
    return keywords[:5]


# --------------------------------------------------------------------------
# FIX5 D1/D2: fresh queries vs. bare slot answers
# --------------------------------------------------------------------------


def residual_tokens(text: str) -> list[str]:
    """Tokens left after stripping locations, budgets, payments and fillers.

    The D2 decision in ``main`` is judged on these: if a typed message still
    contains product words it is a real message, not the answer to the
    pending question.
    """
    if not text:
        return []
    stripped = _strip_slot_words(text)
    for phrase in ("لپ تاپ", "لپ تپ", "نوت بوک"):
        stripped = stripped.replace(phrase, " ")
    leftovers: list[str] = []
    for token in re.findall(r"[^\W_]+", stripped, flags=re.UNICODE):
        if token.isdigit():
            continue
        if len(token) < 3:
            continue
        leftovers.append(token)
    return leftovers


def is_refinement_text(text: str) -> bool:
    """True for «ارزون‌تر» / «تو جمهوری هم بگرد» - wording that extends the
    current search instead of starting a new one."""
    if not text:
        return False
    normalized = normalize(text)
    return any(normalize(word) in normalized for word in REFINEMENT_WORDS)


def slot_ack(text: str) -> str | None:
    """Short acknowledgment for a bare slot answer («نقدی ثبت شد»)."""
    parts: list[str] = []
    budget_max, budget_min = parse_budget(text)
    if budget_max is not None or budget_min is not None:
        parts.append("بودجه")
    if detect_location(text) is not None:
        parts.append("محله")
    if detect_installment(text) is not None or is_yes_answer(text):
        parts.append("نحوهٔ پرداخت")
    if is_skip_answer(text):
        return "ثبت شد ✓"
    if not parts:
        return None
    return " و ".join(parts) + " ثبت شد ✓"


# --------------------------------------------------------------------------
# clarifying questions
# --------------------------------------------------------------------------

# Answers that mean "this slot does not matter to me".  They must mark the
# slot as skipped so the clarify loop never asks the same question again.
SKIP_ANSWER_WORDS = (
    "مهم نیست",
    "مهم نيست",
    "فرقی نداره",
    "فرقی نمیکنه",
    "فرقی نمی‌کنه",
    "فرق نداره",
    "فرق نمیکنه",
    "فرق نمی‌کنه",
    "هر جایی",
    "هرجایی",
    "هرجا",
    "هرچی",
    "هر جور",
    "هرجور",
    "بدون محدودیت",
    "محدودیت ندارم",
    "نمی‌دونم",
    "نمیدونم",
    "اهمیتی نداره",
)


def is_skip_answer(text: str) -> bool:
    """True when the user says the pending question does not matter."""
    normalized = normalize(text)
    if not normalized:
        return False
    return any(normalize(word) in normalized for word in SKIP_ANSWER_WORDS)


CLARIFY_QUESTIONS = {
    "budget": {
        "text": "چند تومن بودجه‌ات توی ذهنته؟",
        "chips": ["تا ۵ میلیون", "تا ۱۰ میلیون", "مهم نیست"],
    },
    "location": {
        "text": "کدوم محله برات نزدیک‌تره؟",
        # FIX5: no fake fixed hoods — the user types, shares GPS, or picks
        # on the map; keeping only the skip answer as a chip
        "chips": ["مهم نیست"],
    },
    "payment": {
        "text": "پرداخت قسطی/ترب‌پی برات مهمه؟",
        "chips": ["آره، قسطی", "نقد می‌خرم", "مهم نیست"],
    },
}


def clarify_fallback(missing: list[str]) -> dict:
    """Deterministic clarifying question (always ends with «مهم نیست»)."""
    for kind in ("budget", "location", "payment"):
        if kind in missing:
            return dict(CLARIFY_QUESTIONS[kind])
    return dict(CLARIFY_QUESTIONS["budget"])


# --------------------------------------------------------------------------
# seller reply parsing
# --------------------------------------------------------------------------

PRICE_PATTERNS = [
    # «۳ میلیون و ۱۵۰» (the way it is said in a shop) = 3,150,000
    re.compile(r"(\d+(?:[\.,٫]\d+)?)\s*میلیون\s*و\s*(\d+)(?:\s*هزار)?"),
    re.compile(r"(\d+(?:[\.,٫]\d+)?)\s*میلیون"),
    re.compile(r"(\d+(?:[\.,٫]\d+)?)\s*هزار"),
    re.compile(r"(\d+(?:[\.,٫]\d+)?)\s*(?:تومن|تومان)"),
]


def parse_price(text: str) -> int | None:
    """«۳ میلیون و ۱۵۰ تومنه» -> 3150000."""
    normalized = normalize(text)
    match = PRICE_PATTERNS[0].search(normalized)
    if match:
        millions = int(_number(match.group(1)))
        thousands = int(match.group(2))
        return millions * 1_000_000 + thousands * 1_000
    match = PRICE_PATTERNS[1].search(normalized)
    if match:
        return int(_number(match.group(1)) * 1_000_000)
    match = PRICE_PATTERNS[2].search(normalized)
    if match:
        return int(_number(match.group(1)) * 1_000)
    match = PRICE_PATTERNS[3].search(normalized)
    if match:
        return int(_number(match.group(1)))
    return None


def parse_prices(text: str) -> list[int]:
    """All prices in a reply (needed for accept/counter messages).

    A counter reply contains both the buyer's target and the seller's number,
    so taking the first price would report the target as the negotiated price.
    """
    normalized = normalize(text)
    values: list[int] = []
    for match in re.finditer(
        r"(\d+(?:[\.,٫]\d+)?)\s*میلیون(?:\s*و\s*(\d+)(?:\s*هزار)?)?", normalized
    ):
        value = int(_number(match.group(1)) * 1_000_000)
        if match.group(2):
            value += int(match.group(2)) * 1_000
        values.append(value)
    for match in re.finditer(r"(\d+(?:[\.,٫]\d+)?)\s*هزار", normalized):
        values.append(int(_number(match.group(1)) * 1_000))
    for match in re.finditer(r"(\d{6,})\s*(?:تومن|تومان)?", normalized):
        values.append(int(match.group(1)))
    # keep the original order, remove duplicates
    return list(dict.fromkeys(value for value in values if value > 0))


COUNTER_WORDS = ("کمه", "آخرین قیمت", "نمی‌تونم", "نمی تونم", "بیشتر از", "تخفیف بیشتر")
ACCEPT_WORDS = ("اوکیه", "قبوله", "قبول", "موافقم", "حله")


def parse_reply(text: str, offer_price: int | None = None) -> dict:
    """Rule based seller reply parsing."""
    normalized = normalize(text or "")
    availability = "unclear"
    for word in UNAVAILABLE_WORDS:
        if normalize(word) in normalized:
            availability = "unavailable"
            break
    if availability != "unavailable":
        for word in AVAILABLE_WORDS:
            if normalize(word) in normalized:
                availability = "available"
                break
    if availability == "unclear":
        for word in UNCLEAR_WORDS:
            if normalize(word) in normalized:
                availability = "unclear"
                break

    prices = parse_prices(text)
    offer_status = "none"
    counter = None
    if any(normalize(word) in normalized for word in COUNTER_WORDS):
        offer_status = "countered"
        # target + counter are both in the sentence; the seller's number is
        # the highest one
        price = max(prices) if prices else parse_price(text)
        counter = price
    elif any(normalize(word) in normalized for word in ACCEPT_WORDS):
        offer_status = "accepted"
        price = max(prices) if prices else parse_price(text)
    else:
        price = parse_price(text)

    price_changed = False
    if price and offer_price:
        price_changed = abs(price - offer_price) / offer_price > 0.02

    hours_text = None
    hours_match = re.search(r"(?:تا|تا\s+ساعت)\s*(\d{1,2})\s*(?::(\d{2}))?\s*(و\s*نیم|:\d{2})?", normalized)
    if hours_match:
        hour = int(hours_match.group(1))
        minute = int(hours_match.group(2)) if hours_match.group(2) else 0
        if "و نیم" in hours_match.group(0):
            minute = 30
        if "شب" in normalized and hour < 12:
            hour += 12
        elif ("ظهر" in normalized or "عصر" in normalized or "بعدازظهر" in normalized) and hour < 12:
            hour += 12
        hours_text = f"تا {fa_digits(f'{hour:02d}:{minute:02d}')}"

    return {
        "availability": availability,
        "price_toman": price,
        "price_changed": price_changed,
        "hours_text": hours_text,
        "alternative": None,
        "installment": None,
        "confidence": 0.8 if availability != "unclear" else 0.45,
        "offer_status": offer_status,
        "counter_price": counter,
    }


# --------------------------------------------------------------------------
# money / distance formatting (shared with haggle fallbacks)
# --------------------------------------------------------------------------


def price_fa(value) -> str:
    """3150000 -> «۳٬۱۵۰٬۰۰۰» (never Latin digits)."""
    if value in (None, ""):
        return ""
    try:
        number = int(value)
    except (TypeError, ValueError):
        return ""
    return fa_digits(f"{number:,}".replace(",", "٬"))


def distance_fa(value) -> str:
    """200 -> «۲۰۰ متر», 1250 -> «۱٫۲ کیلومتر»."""
    if value in (None, ""):
        return ""
    try:
        meters = int(round(float(value)))
    except (TypeError, ValueError):
        return ""
    if meters < 1000:
        return f"{fa_digits(str(meters))} متر"
    text = f"{meters / 1000:.1f}".replace(".", "٫")
    return f"{fa_digits(text)} کیلومتر"


# --------------------------------------------------------------------------
# haggle lines (deterministic)
# --------------------------------------------------------------------------


def haggle_lines(
    option: dict,
    stats: dict,
    leverage: dict | None,
    target: int,
    ceiling: int,
) -> list[str]:
    """Two or three short negotiation lines using only real data."""
    price = int((option or {}).get("price") or 0)
    n_shops = int((stats or {}).get("n_shops") or 0)
    median = (stats or {}).get("median") or 0
    lines: list[str] = []

    if leverage:
        distance = leverage.get("delta_m") or leverage.get("distance_m")
        where = "توی همین پاساژ" if leverage.get("same_mall") else "همین نزدیکی"
        first = (
            f"همین مدل رو «{leverage.get('name')}» "
            f"{price_fa(leverage.get('price'))} می‌ده"
        )
        if distance:
            first += f"، {distance_fa(distance)} اون‌طرف‌تر"
        first += f" ({where})."
        lines.append(first)
    elif n_shops < 2:
        lines.append("مقایسه ممکن نیست؛ فقط یک فروشگاه این مدل را دارد.")

    if target and target < price:
        lines.append(f"«با {price_fa(target)} حضوری می‌دید؟»")
    elif n_shops >= 2:
        lines.append(
            f"قیمتت از میانهٔ {fa_digits(str(n_shops))} فروشگاه "
            f"({price_fa(median)}) پایین‌تره؛ روی گارانتی و فاکتور چانه بزن."
        )

    if ceiling and len(lines) < 3:
        lines.append(f"سقف خرید: {price_fa(ceiling)}؛ بالاتر نرو.")
    if not lines:
        lines.append("قیمت نهایی را قبل از پرداخت حضوری تأیید کن.")
    return lines[:3]


# --------------------------------------------------------------------------
# message draft
# --------------------------------------------------------------------------


def draft_message(
    product_title: str,
    shop_names: list[str],
    installment: bool = False,
    today: bool = False,
    target_price: int | None = None,
) -> str:
    """Fallback message the agent would send to the shop."""
    parts = [
        "سلام وقت بخیر 🌱",
        "از طرف یک خریدار با دستیار «تربچه» پیام می‌دم.",
        f"دربارهٔ {product_title}:",
    ]
    if today:
        parts.append("امروز موجوده؟")
    else:
        parts.append("موجوده؟")
    parts.append("قیمت نهایی برای خرید حضوری چنده؟")
    if target_price:
        parts.append(f"با {price_fa(target_price)} حضوری می‌دید؟")
    parts.append("تا چه ساعتی بازید؟")
    if installment:
        parts.append("اقساطی/ترب‌پی دارید؟")
    parts.append("ممنون")
    return " ".join(parts)


def ooc_message(query: str, market_name: str | None = None) -> str:
    if market_name:
        return (
            f"«{query}» را در داده‌های ترب پیدا نکردم. "
            f"معمولاً بورس این کالا در تهران «{market_name}» است؛ "
            "آنجا معمولاً چند فروشندهٔ تخصصی هست."
        )
    return f"«{query}» را در داده‌های ترب پیدا نکردم."


# --------------------------------------------------------------------------
# compare («X یا Y کدوم بهتره؟»)
# --------------------------------------------------------------------------


def _compare_side(term: str) -> str:
    tokens = re.findall(r"[^\W_]+", term, flags=re.UNICODE)
    words = [word for word in tokens if word not in _COMPARE_FILLERS]
    # keep the tail: «کدوم بهتره گوشی سامسونگ» -> «گوشی سامسونگ»
    return " ".join(words[:3]) if words else ""


def extract_compare(text: str) -> list[str] | None:
    """Detect «X یا Y کدوم بهتره», «X بهتره یا Y», «X یا Y» in one message.

    Returns ``[term_a, term_b]`` or ``None``.  The generic «X یا Y» only
    counts on short queries without shopping verbs, so normal («هدفون R50i
    میخوام») queries never false-positive on a random «یا».
    """
    if not text or "یا" not in text:
        return None
    normalized = normalize(f" {text} ").strip()
    if "یا" not in normalized:
        return None

    explicit = any(word in normalized for word in ("بهتر", "کدوم", "کدام", "فرق"))
    verb_hit = any(word in normalized for word in ("میخوام", "می خواهم", "بخرم", "قیمت", "چیه", "چی هست", "چیزی"))
    words = [w for w in re.findall(r"[^\W_]+", normalized, flags=re.UNICODE)]
    if not explicit and (verb_hit or len(words) > 6):
        return None

    parts = re.split(r"\s+یا\s+", normalized.strip(" ؟.!."))
    if len(parts) < 2:
        return None
    side_a = _compare_side(parts[0])
    side_b = _compare_side(parts[1])
    if not side_a or not side_b or side_a == side_b:
        return None
    return [side_a, side_b]


def replica_flag(text: str) -> bool:
    """True when a product title hints at a replica / «درجه یک» copy."""
    if not text:
        return False
    normalized = normalize(text)
    return any(hint in normalized for hint in _REPLICA_HINTS)
