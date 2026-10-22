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

UNIT_MULTIPLIERS = {
    "میلیون": 1_000_000,
    "میلیون تومان": 1_000_000,
    "تومن": 1,
    "تومان": 1,
    "هزار": 1_000,
    "م": 1_000_000,
}


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


def extract_keywords(text: str, category: str | None = None, extra_stop_words: list[str] | None = None) -> list[str]:
    """Very small keyword extractor: keep the product-ish words of the query."""
    if not text:
        return []
    stop_words = {
        normalize(word)
        for word in {
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
        }
    }
    for word in extra_stop_words or []:
        cleaned = normalize(word)
        if cleaned:
            stop_words.add(cleaned)
            for part in cleaned.split():
                if len(part) > 3:
                    stop_words.add(part)
    if category:
        stop_words.add(normalize(category))
        # every part of the category name (even short ones like «لپ»/«تاپ»)
        stop_words.update(normalize(category).split())
    normalized_text = normalize(text)
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
        "chips": ["فردوسی", "جمهوری", "مهم نیست"],
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
    re.compile(r"(\d+(?:[\.,٫]\d+)?)\s*میلیون\s*و\s*(\d+)\s*هزار"),
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
    }


# --------------------------------------------------------------------------
# message draft
# --------------------------------------------------------------------------


def draft_message(
    product_title: str,
    shop_names: list[str],
    installment: bool = False,
    today: bool = False,
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
