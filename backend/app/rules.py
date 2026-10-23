"""Deterministic fallbacks used when the LLM is off or unavailable.

These rules keep the whole product flow working with ``LLM_MODE=off``:
slot extraction, clarifying questions, seller reply parsing and the seller
message draft.
"""

from __future__ import annotations

import re

from .normalize import (
    BRAND_ALIASES,
    CATEGORY_SYNONYMS,
    NEIGHBORHOODS,
    fa_digits,
    geocode_neighbourhood,
    normalize,
    tokenize,
)

BUDGET_RE = re.compile(
    r"(\d+(?:[\.,٫]\d+)?)\s*(میلیون|میلیون\s+تومان|تومن|تومان|هزار|م|m)\b",
    re.IGNORECASE,
)
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
    "m": 1_000_000,
}

# Colloquial amounts: «هفت» = 7, «هفتصد» = 700, then «هزار» / «میلیون».
_NUMBER_ONES = {
    "صفر": 0, "یک": 1, "یه": 1, "دو": 2, "سه": 3, "چهار": 4, "پنج": 5,
    "شش": 6, "شیش": 6, "هفت": 7, "هشت": 8, "نه": 9, "ده": 10,
    "یازده": 11, "دوازده": 12, "سیزده": 13, "چهارده": 14, "پانزده": 15,
    "شانزده": 16, "هفده": 17, "هجده": 18, "نوزده": 19, "بیست": 20,
    "سی": 30, "چهل": 40, "پنجاه": 50, "شصت": 60, "هفتاد": 70,
    "هشتاد": 80, "نود": 90, "صد": 100, "یکصد": 100, "دویست": 200,
    "سیصد": 300, "چهارصد": 400, "پانصد": 500, "ششصد": 600, "هفتصد": 700,
    "هشتصد": 800, "نهصد": 900,
}
_NUMBER_SCALES = {"هزار": 1_000, "میلیون": 1_000_000, "میلیارد": 1_000_000_000}
_MONEY_SUFFIXES = {"تومان", "تومن", "تومانه"}
CHEAPER_WORDS = ("ارزون‌تر", "ارزونتر", "ارزان‌تر", "ارزانتر", "ارزون تر")
VAGUE_PHRASES = ("یه چیزی", "یک چیزی", "چیزی میخوام", "چیزی می خواهم")
SMALLTALK_PHRASES = ("سلام", "درود", "صبح بخیر", "عصر بخیر", "مرسی", "ممنون")

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


def _words_to_number(tokens: list[str]) -> int | None:
    """Parse a pure Persian amount such as «هفت میلیون» or «هفتصد هزار»."""
    if not tokens:
        return None
    total = 0
    current = 0
    seen = False
    for token in tokens:
        if token in _NUMBER_ONES:
            current += _NUMBER_ONES[token]
            seen = True
            continue
        if token in _NUMBER_SCALES:
            current = (current or 1) * _NUMBER_SCALES[token]
            total += current
            current = 0
            seen = True
            continue
        if token in _MONEY_SUFFIXES:
            if 0 < current < 1000:
                current *= 1_000_000
            seen = True
            continue
        return None
    if not seen:
        return None
    return total + current


def _persian_amount(normalized: str) -> int | None:
    tokens = normalized.split()
    best: int | None = None
    for start in range(len(tokens)):
        for end in range(start + 1, min(len(tokens), start + 6) + 1):
            span = tokens[start:end]
            if not any(token in _NUMBER_ONES or token in _NUMBER_SCALES for token in span):
                continue
            value = _words_to_number(span)
            if value is None:
                continue
            has_scale = any(token in _NUMBER_SCALES or token in _MONEY_SUFFIXES for token in span)
            if not has_scale:
                continue
            if best is None or value > best:
                best = value
    return best


def _apply_amount(normalized: str, amount: int) -> tuple[int | None, int | None]:
    if "بیشتر" in normalized or "بالای" in normalized or "حداقل" in normalized:
        return None, amount
    return amount, None


def parse_budget(text: str, *, budget_context: bool = False) -> tuple[int | None, int | None]:
    """Return ``(budget_max, budget_min)`` in toman.

    A bare number below 1000 counts as millions only when it answers a budget
    question. «۷ تومن», «7m» and «زیر ۷» are colloquial millions anywhere.
    """
    if not text:
        return None, None
    normalized = normalize(text)
    normalized = re.sub(r"(?<=\d)[,٬](?=\d)", "", normalized)
    budget_max: int | None = None
    budget_min: int | None = None

    rials = RIALS_RE.search(normalized)
    if rials:
        amount = int(_number(rials.group(1)) / 10)
        budget_max, budget_min = _apply_amount(normalized, amount)

    match = BUDGET_RE.search(normalized)
    if match:
        unit = match.group(2).strip().lower()
        amount = int(_number(match.group(1)) * UNIT_MULTIPLIERS.get(unit, 1))
        if unit in _MONEY_SUFFIXES and amount < 1000:
            amount *= 1_000_000
        budget_max, budget_min = _apply_amount(normalized, amount)

    if budget_max is None and budget_min is None:
        words = _persian_amount(normalized)
        if words is not None:
            budget_max, budget_min = _apply_amount(normalized, words)

    if budget_max is None and budget_min is None:
        small = re.fullmatch(r"(?:زیر|تا)\s*(\d+)", normalized)
        if small:
            amount = int(small.group(1))
            if amount < 1000:
                amount *= 1_000_000
            budget_max = amount

    if budget_max is None and budget_min is None:
        bare = re.fullmatch(r"\d+(?:[\.,]\d+)?", normalized)
        if bare:
            amount = int(_number(bare.group(0)))
            if amount < 1000:
                if budget_context:
                    budget_max = amount * 1_000_000
            else:
                budget_max = amount
        elif budget_context:
            lone = _words_to_number(normalized.split())
            if lone is not None and lone < 1000:
                budget_max = lone * 1_000_000
    return budget_max, budget_min


def is_budget_only(text: str) -> bool:
    """True when the message states a price and no product."""
    budget_max, budget_min = parse_budget(text, budget_context=True)
    if budget_max is None and budget_min is None:
        return False
    return core_noun(text, None) is None and detect_category(text) is None


def is_cheaper_request(text: str) -> bool:
    normalized = normalize(text)
    return any(normalize(word) in normalized for word in CHEAPER_WORDS)


def _known_category(category: str, known_categories: list[str] | None) -> str | None:
    if not known_categories:
        return category
    if category in known_categories:
        return category
    target = normalize(category)
    for item in known_categories:
        if normalize(item) == target:
            return item
    return None


def detect_category(text: str, known_categories: list[str] | None = None) -> str | None:
    """Map free text to a dataset category.

    A product head noun beats a brand. «هدفون سامسونگ» stays headphones,
    not «گوشی موبایل».
    """
    if not text:
        return None
    noun = core_noun(text, None)
    if noun:
        preferred = category_for_core_noun(noun, text, known_categories)
        if preferred:
            return preferred
    normalized = normalize(text)
    brand_keys = {normalize(key) for key in BRAND_ALIASES}
    best: tuple[int, str] | None = None
    for synonym, category in CATEGORY_SYNONYMS.items():
        key = normalize(synonym)
        if not key or key not in normalized:
            continue
        if noun and key in brand_keys:
            continue
        accepted = _known_category(category, known_categories)
        if known_categories and accepted is None:
            continue
        score = len(key)
        chosen = accepted or category
        if best is None or score > best[0]:
            best = (score, chosen)
    if best:
        return best[1]
    if known_categories:
        for category in sorted(known_categories, key=lambda item: len(normalize(item)), reverse=True):
            key = normalize(category)
            if key and key in normalized:
                return category
    return None


_CORE_NOUN_MARKERS: tuple[tuple[str, str], ...] = (
    ("ماشین لباسشویی", "ماشین لباسشویی"),
    ("تلویزیون", "تلویزیون"),
    ("مانیتور", "مانیتور"),
    ("شارژر", "شارژر"),
    ("استابلایزر", "استابلایزر"),
    ("رگولاتور", "رگولاتور"),
    ("محافظ", "محافظ"),
    ("ترانس", "ترانس"),
    ("فیلتر", "فیلتر"),
    ("کابل", "کابل"),
    ("براکت", "براکت"),
    ("کولر", "کولر"),
    ("لپ تاپ", "لپ تاپ"),
    ("لپتاپ", "لپ تاپ"),
    ("نوت بوک", "لپ تاپ"),
    ("یخچال", "یخچال"),
    ("کفش ورزشی", "کفش ورزشی"),
    ("کتونی", "کتونی"),
    ("کتانی", "کتونی"),
    ("هندزفری", "هدفون"),
    ("ایربادز", "هدفون"),
    ("ایرپاد", "هدفون"),
    ("هدفون", "هدفون"),
    ("هدست", "هدفون"),
    ("موبایل", "گوشی"),
    ("گوشی", "گوشی"),
    ("آیفون", "گوشی"),
    ("کفش", "کفش"),
    ("قاب گوشی", "قاب"),
    ("کاور گوشی", "قاب"),
    ("قاب", "قاب"),
    ("کاور", "قاب"),
)

CORE_NOUN_ALIASES: dict[str, tuple[str, ...]] = {
    "ماشین لباسشویی": ("ماشین لباسشویی", "لباسشویی"),
    "تلویزیون": ("تلویزیون",),
    "مانیتور": ("مانیتور",),
    "شارژر": ("شارژر",),
    "استابلایزر": ("استابلایزر", "استابلایزر برق"),
    "رگولاتور": ("رگولاتور",),
    "محافظ": ("محافظ",),
    "ترانس": ("ترانس",),
    "فیلتر": ("فیلتر",),
    "کابل": ("کابل",),
    "براکت": ("براکت",),
    "کولر": ("کولر",),
    "لپ تاپ": ("لپ تاپ", "لپتاپ", "نوت بوک", "نوتبوک"),
    "یخچال": ("یخچال",),
    "کتونی": ("کتونی", "کتانی"),
    "کفش ورزشی": ("کفش ورزشی", "کتونی", "کتانی"),
    "کفش": ("کفش",),
    "هدفون": ("هدفون", "هدست", "هندزفری", "ایرپاد", "ایربادز"),
    "گوشی": ("گوشی", "موبایل", "آیفون"),
    "قاب": ("قاب", "کاور", "درب"),
}

_CATEGORY_CORE_NOUNS = {
    "ماشین لباسشویی": "ماشین لباسشویی",
    "مانیتور": "مانیتور",
    "تلویزیون": "تلویزیون",
    "لپ تاپ و نوت بوک": "لپ تاپ",
    "یخچال فریزر بالاپایین": "یخچال",
    "یخچال فریزر در فرانسوی": "یخچال",
    "یخچال فریزر دوقلو": "یخچال",
    "یخچال فریزر ساید بای ساید": "یخچال",
    "کتانی و کفش اسپرت": "کفش ورزشی",
    "هدفون، هدست و هندزفری": "هدفون",
    "گوشی موبایل": "گوشی",
}


def core_noun(text: str, category: str | None = None) -> str | None:
    """Return the primary product noun for relevance-preserving search.

    More specific terms win («کفش کتونی» -> «کتونی»); a recognized dataset
    category supplies a noun when the user used only a synonym/brand.
    """
    normalized = normalize(text)
    tokens = set(re.findall(r"[^\W_]+", normalized, flags=re.UNICODE))
    first = " ".join(tokenize(normalized)[:2])
    # In phrases such as «شارژر لپ‌تاپ» or «فیلتر یخچال», the first noun is
    # the requested accessory; the trailing device is a compatibility qualifier.
    for noun in ("قاب", "کاور", "شارژر", "استابلایزر", "رگولاتور", "محافظ", "ترانس", "فیلتر", "کابل", "براکت"):
        if first == normalize(noun) or first.startswith(normalize(noun) + " "):
            return noun
    matches: list[tuple[int, str]] = []
    for marker, noun in _CORE_NOUN_MARKERS:
        marker_tokens = normalize(marker).split()
        if marker_tokens and all(token in tokens for token in marker_tokens):
            # Use contiguous phrase matching so «کفش» does not match inside a
            # longer unrelated token.
            phrase = " ".join(marker_tokens)
            if re.search(rf"(?<!\w){re.escape(phrase)}(?!\w)", normalized):
                matches.append((len(phrase), noun))
    if matches:
        return max(matches, key=lambda item: item[0])[1]
    return _CATEGORY_CORE_NOUNS.get(category or "")


def core_noun_aliases(noun: str | None) -> tuple[str, ...]:
    return CORE_NOUN_ALIASES.get(noun or "", (noun,) if noun else ())


def category_for_core_noun(
    noun: str | None,
    text: str,
    known_categories: list[str] | None = None,
) -> str | None:
    """Category implied by the head noun, never by a brand mention."""
    if not noun:
        return None
    normalized = normalize(text)
    if noun == "شارژر" and any(token in normalized for token in ("لپتاپ", "لپ تاپ", "نوت بوک")):
        return _known_category("شارژر لپ تاپ", known_categories)
    if noun == "شارژر" and "گوشی" in normalized:
        return _known_category("شارژر گوشی", known_categories)
    if noun in {"قاب", "یخچال"}:
        return None
    mapped = {
        "هدفون": "هدفون، هدست و هندزفری",
        "گوشی": "گوشی موبایل",
        "لپ تاپ": "لپ تاپ و نوت بوک",
        "کفش ورزشی": "کتانی و کفش اسپرت",
    }.get(noun)
    if mapped:
        return _known_category(mapped, known_categories)
    for synonym, category in CATEGORY_SYNONYMS.items():
        if normalize(synonym) == normalize(noun):
            return _known_category(category, known_categories)
    return None


def _without_radius_words(text: str) -> str:
    cleaned = RADIUS_RE.sub(" ", normalize(text))
    for token in ("شعاع", "کیلومتر"):
        cleaned = cleaned.replace(token, " ")
    return " ".join(cleaned.split())


def detect_brand(text: str, known_brands: list[str] | None = None) -> str | None:
    """Find the longest explicit catalog brand name or configured alias."""
    normalized = _without_radius_words(text)
    if not normalized:
        return None
    brands = sorted(known_brands or [], key=lambda item: len(normalize(item)), reverse=True)
    for brand in brands:
        candidate = normalize(brand)
        if candidate and not candidate.isdigit() and re.search(rf"(?<!\w){re.escape(candidate)}(?!\w)", normalized):
            return brand
    tokens = set(tokenize(normalized))
    for marker, aliases in BRAND_ALIASES.items():
        if marker not in tokens:
            continue
        for brand in brands:
            if normalize(brand) in {normalize(alias) for alias in aliases}:
                return brand
    return None


RADIUS_RE = re.compile(r"(?<!\d)(\d{1,2})\s*(?:کیلومتر|km)\b", re.IGNORECASE)
RADIUS_VALUES = {2, 5, 10}


def detect_radius(text: str) -> tuple[bool, int | None]:
    """Return (was-mentioned, radius); None radius explicitly means all Tehran."""
    normalized = normalize(text)
    if any(phrase in normalized for phrase in ("کل تهران", "همه تهران", "تمام تهران")):
        return True, None
    match = RADIUS_RE.search(normalized)
    if not match:
        return False, None
    value = int(match.group(1))
    return (True, value) if value in RADIUS_VALUES else (False, None)


def detect_location(text: str) -> dict | None:
    """Find a known Tehran neighbourhood in the text.

    An exact name wins, so «ونک» is not resolved to «پونک».
    """
    if not text:
        return None
    normalized = normalize(text)
    squashed = normalized.replace(" ", "")
    exact: list[tuple[int, str, tuple[float, float]]] = []
    partial: list[tuple[int, str, tuple[float, float]]] = []
    for label, coords in NEIGHBORHOODS.items():
        if label == "بازار رضا":
            continue
        key = normalize(label)
        if not key:
            continue
        key_squashed = key.replace(" ", "")
        if key == normalized or key_squashed == squashed or f" {key} " in f" {normalized} ":
            exact.append((len(key_squashed), label, coords))
        elif key in normalized or (len(key_squashed) >= 5 and key_squashed in squashed):
            partial.append((len(key_squashed), label, coords))
    pool = exact or partial
    if not pool:
        return None
    _, label, (lat, lon) = max(pool, key=lambda item: item[0])
    resolved = geocode_neighbourhood(label)
    if resolved:
        return {"label": resolved["label"], "lat": resolved["lat"], "lon": resolved["lon"]}
    return {"label": label, "lat": lat, "lon": lon}


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
    for token in ("محله", "پرداخت", "نقدی", "کیلومتر", "شعاع", "km", "کل تهران"):
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
    "میلیون",
    "هزار",
    "تومان",
    "تومن",
    "هفت",
    "هفتصد",
    "ده",
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
    "کیلومتر",
    "شعاع",
    "تومان",
    "تومن",
    "میلیونی",
    "بالای",
    "بیشتر",
    "کمتر",
    "هم",
    "بگرد",
    "بگردم",
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


def dedupe_query_text(text: str) -> str:
    """Drop repeated tokens and brand-alias pairs («نایک نایکی», «ورزشی ورزشی»)."""
    if not text:
        return ""
    tokens = re.findall(r"[^\W_]+", text, flags=re.UNICODE)
    if not tokens:
        return text
    groups = [
        {normalize(alias) for alias in aliases}
        for aliases in BRAND_ALIASES.values()
    ]
    kept: list[str] = []
    for token in tokens:
        key = normalize(token)
        if any(key == normalize(previous) for previous in kept):
            continue
        if any(key in group and any(normalize(previous) in group for previous in kept) for group in groups):
            continue
        kept.append(token)
    if kept == tokens:
        return text
    return " ".join(kept)


def is_vague_request(text: str) -> bool:
    normalized = normalize(text)
    return any(normalize(phrase) in normalized for phrase in VAGUE_PHRASES)


def is_smalltalk(text: str) -> bool:
    normalized = normalize(text)
    return any(normalize(phrase) in normalized for phrase in SMALLTALK_PHRASES)


def is_card_followup(text: str) -> bool:
    normalized = normalize(text)
    if normalized in {"اولی", "اولین", "همون اولی", "همان اولی"}:
        return True
    return "کدوم" in normalized and "بهتر" in normalized


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


def rule_intent(
    text: str,
    state: dict | None = None,
    *,
    known_categories: list[str] | None = None,
    known_brands: list[str] | None = None,
) -> dict:
    """Deterministic action and slot proposal used when the router is off/unsafe."""
    state = state or {}
    slots = state.get("slots") or {}
    last_query = str(state.get("last_query") or slots.get("query") or "")
    category = detect_category(text, known_categories)
    brand = detect_brand(text, known_brands)
    location = detect_location(text)
    budget_max, budget_min = parse_budget(text)
    radius_mentioned, radius = detect_radius(text)
    pair = extract_compare(text)
    in_torob = detect_in_torob(text)

    if not in_torob:
        return {"action": "ooc", "query": product_term_for_intent(text), "confidence": 1.0}
    if is_vague_request(text):
        return {"action": "chitchat", "confidence": 1.0}
    if pair:
        return {"action": "compare", "sides": tuple(pair), "confidence": 1.0}
    core = core_noun(text, category)
    has_product = bool(category or core)
    if radius_mentioned and last_query and not has_product and not brand:
        return {"action": "change_radius", "radius_km": radius, "confidence": 1.0}
    explicit_slot_edit = bool(
        budget_max is not None
        or budget_min is not None
        or brand
        or location
        or detect_installment(text) is not None
        or is_yes_answer(text)
        or is_refinement_text(text)
    )

    selected_product = state.get("selected_product_id") or slots.get("selected_product_id")
    normalized = normalize(text)
    if selected_product and any(word in normalized for word in ("چانه", "تخفیف", "موجودی فروشگاه")):
        target, _ = parse_budget(text)
        return {"action": "haggle", "target_price": target, "confidence": 1.0}

    if last_query and location and not has_product and not brand and budget_max is None and budget_min is None:
        return {"action": "change_location", "area": location["label"], "confidence": 1.0}

    if last_query and explicit_slot_edit and not has_product:
        area = location["label"] if location else None
        return {
            "action": "refine",
            "budget_min": budget_min,
            "budget_max": budget_max,
            "clear_budget_max": budget_min is not None and slots.get("budget_max") is not None,
            "brand": brand,
            "category": category,
            "area": area,
            "confidence": 1.0,
        }

    if not has_product and (is_smalltalk(text) or is_card_followup(text) or is_vague_request(text)):
        return {"action": "chitchat", "confidence": 1.0}

    keywords = extract_keywords(text, category, [location["label"]] if location else None)
    query_terms: list[str] = []
    if core:
        query_terms.append(core)
    for keyword in keywords:
        if normalize(keyword) not in {normalize(part) for part in query_terms}:
            query_terms.append(keyword)
    if brand and normalize(brand) not in {normalize(term) for term in query_terms}:
        query_terms.append(brand)
    query = dedupe_query_text(" ".join(query_terms).strip() or normalize(text)[:80])

    if not has_product and not query_terms and not (budget_max or budget_min or location):
        return {"action": "chitchat", "confidence": 1.0}
    return {
        "action": "new_search",
        "query": query[:80],
        "category": category,
        "brand": brand,
        "budget_min": budget_min,
        "budget_max": budget_max,
        "area": location["label"] if location else None,
        "radius_km": radius if radius_mentioned else None,
        "confidence": 1.0,
    }


def product_term_for_intent(text: str) -> str:
    """Short OOC label used by the typed decision contract."""
    return " ".join(extract_keywords(text))[:80] or normalize(text)[:80]


def chitchat_reply(text: str, cards: list | None = None) -> str:
    normalized = normalize(text)
    shown = cards or []
    if shown and is_card_followup(text):
        title = str(shown[0].get("title") or shown[0].get("persian_title") or "کارت اول")
        if "کدوم" in normalized:
            return f"از همین کارت‌ها، «{title}» انتخاب بهتر است."
        return f"منظورت همین اولی است: «{title}»."
    if is_vague_request(text):
        return "چه کالایی می‌خوای بخری؟ اسم محصول را بنویس."
    if any(token in normalized for token in ("مرسی", "ممنون")):
        return "خواهش می‌کنم. اگر بخواهی روی همین نتایج دقیق‌تر می‌گردم."
    if any(token in normalized for token in ("سلام", "درود", "صبح بخیر", "عصر بخیر")):
        return "سلام! چه کالایی را برای خرید حضوری جست‌وجو می‌کنید؟"
    return "برای شروع، نام کالا یا نیازتان را بنویسید."


CLARIFY_QUESTIONS = {
    "budget": {
        "text": "بودجهٔ تقریبی شما چقدر است؟",
        "chips": ["تا ۵ میلیون", "تا ۱۰ میلیون", "مهم نیست"],
    },
    "location": {
        "text": "کدام محله برای خریدتان مناسب‌تر است؟",
        # FIX5: no fake fixed hoods — the user types, shares GPS, or picks
        # on the map; keeping only the skip answer as a chip
        "chips": ["مهم نیست"],
    },
    "payment": {
        "text": "پرداخت قسطی یا ترب‌پی برایتان مهم است؟",
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
        where = "در همین پاساژ" if leverage.get("same_mall") else "در همین نزدیکی"
        first = (
            f"این مدل در فروشگاه «{leverage.get('name')}» "
            f"با {price_fa(leverage.get('price'))} عرضه می‌کند"
        )
        if distance:
            first += f"، {distance_fa(distance)} اون‌طرف‌تر"
        first += f"؛ {where}."
        lines.append(first)
    elif n_shops < 2:
        lines.append("مقایسه ممکن نیست؛ فقط یک فروشگاه این مدل را دارد.")

    if target and target < price:
        lines.append(f"«با {price_fa(target)} حضوری می‌دید؟»")
    elif n_shops >= 2:
        lines.append(
            f"قیمت از میانهٔ {fa_digits(str(n_shops))} فروشگاه "
            f"({price_fa(median)}) پایین‌تر است؛ دربارهٔ ضمانت و فاکتور مذاکره کنید."
        )

    if ceiling and len(lines) < 3:
        lines.append(f"سقف خرید: {price_fa(ceiling)}؛ از آن بیشتر پرداخت نکنید.")
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
        "از طرف یک خریدار و با دستیار «ترب‌چه» پیام می‌دهم.",
        f"دربارهٔ {product_title}:",
    ]
    if today:
        parts.append("امروز موجود است؟")
    else:
        parts.append("موجود است؟")
    parts.append("قیمت نهایی خرید حضوری چقدر است؟")
    if target_price:
        parts.append(f"با {price_fa(target_price)} حضوری می‌دید؟")
        parts.append("تا چه ساعتی باز هستید؟")
    if installment:
        parts.append("پرداخت قسطی یا ترب‌پی دارید؟")
    parts.append("ممنون")
    return " ".join(parts)


def ooc_message(query: str, market_name: str | None = None) -> str:
    if market_name:
        return (
            f"«{query}» را در داده‌های ترب پیدا نکردم. "
            f"معمولاً بورس این کالا در تهران «{market_name}» است؛ "
            "آنجا معمولاً چند فروشندهٔ تخصصی فعالیت می‌کنند."
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
