"""Text normalization utilities shared by the catalog builder and the query layer.

Persian/Arabic text needs aggressive folding before it can be matched with SQL
``LIKE`` queries or compared with Python dictionaries:

* Arabic yeh/kaf -> Persian yeh/kaf
* Arabic & Persian digits -> ASCII digits
* ZWNJ (U+200C), tatweel (U+0640) and harakat removed
* alef variants folded, hamza removed for market names
* latin text lower-cased, whitespace collapsed

``normalize()`` is used for *search* (ZWNJ is dropped so that «لپ‌تاپ» and
«لپتاپ» match). ``normalize_display()`` keeps ZWNJ because it is used for
values we show to the user.
"""

from __future__ import annotations

import re
import unicodedata
import json
from pathlib import Path

AR_DIGITS = "٠١٢٣٤٥٦٧٨٩"
FA_DIGITS = "۰۱۲۳۴۵۶۷۸۹"

_DIGIT_TABLE = {ord(ch): str(i) for i, ch in enumerate(AR_DIGITS)}
_DIGIT_TABLE.update({ord(ch): str(i) for i, ch in enumerate(FA_DIGITS)})

ZWNJ = "‌"
TATWEEL = "ـ"

_DIACRITICS = re.compile(r"[ً-ْٰـ]")
_WS = re.compile(r"\s+")

# Characters that are folded to their plain counterparts.
_LETTER_FOLD = str.maketrans(
    {
        "ي": "ی",  # ARABIC YEH -> FARSI YEH
        "ى": "ی",  # ALEF MAKSURA -> FARSI YEH
        "ك": "ک",  # ARABIC KAF -> KEHEH
        "ؤ": "و",  # WAW WITH HAMZA -> WAW
        "أ": "ا",  # ALEF WITH HAMZA ABOVE -> ALEF
        "إ": "ا",  # ALEF WITH HAMZA BELOW -> ALEF
        "آ": "ا",  # ALEF WITH MADDA -> ALEF
        "ة": "ه",  # TEH MARBUTA -> HEH
        "ـ": "",  # tatweel
    }
)


def to_ascii_digits(text: str) -> str:
    """Convert Arabic/Persian digits to ASCII digits."""
    if not text:
        return ""
    return text.translate(_DIGIT_TABLE)


def fa_digits(text: str) -> str:
    """Convert ASCII digits to Persian digits (for UI copy)."""
    if not text:
        return ""
    return "".join(FA_DIGITS[int(c)] if c.isdigit() else c for c in text)


def normalize(text: str | None) -> str:
    """Fold text for searching: digits -> ASCII, letters folded, ZWNJ removed."""
    if not text:
        return ""
    text = unicodedata.normalize("NFKC", str(text))
    text = text.translate(_DIGIT_TABLE)
    text = text.translate(_LETTER_FOLD)
    text = _DIACRITICS.sub("", text)
    text = text.replace(ZWNJ, "").replace(TATWEEL, "")
    text = text.lower()
    text = _WS.sub(" ", text).strip()
    return text


def normalize_display(text: str | None) -> str:
    """Fold text but keep ZWNJ (used for values that are displayed)."""
    if not text:
        return ""
    text = unicodedata.normalize("NFKC", str(text))
    text = text.translate(_DIGIT_TABLE)
    text = text.translate(_LETTER_FOLD)
    text = _DIACRITICS.sub("", text)
    text = text.replace(TATWEEL, "")
    text = _WS.sub(" ", text).strip()
    return text


def strip_hamza(text: str | None) -> str:
    """Remove the hamza carrier so that «علاءالدین» == «علاالدین»."""
    if not text:
        return ""
    return text.replace("ء", "")


def strip_digits_spacing(text: str | None) -> str:
    """Remove digits and collapse spacing (used while cleaning market names)."""
    if not text:
        return ""
    text = re.sub(r"[0-9۰-۹٠-٩]+", " ", text)
    return _WS.sub(" ", text).strip()


def normalize_mall_name(name: str | None) -> str:
    """Canonical form of a mall / market name."""
    if not name:
        return ""
    name = strip_digits_spacing(strip_hamza(normalize_display(name)))
    name = re.sub(r"\s+", " ", name).strip(" -،,")
    return name


def build_search_text(*parts: str | None) -> str:
    """Concatenate and normalize product searchable text."""
    joined = " ".join(p for p in parts if p)
    return normalize(joined)


def tokenize(text: str | None) -> list[str]:
    """Split normalized text into tokens (latin words and persian runs)."""
    if not text:
        return []
    normalized = normalize(text)
    return [t for t in re.split(r"[^\w]+", normalized, flags=re.UNICODE) if t]


def trigrams(text: str | None) -> set[str]:
    """Character trigrams of a normalized string (used for fuzzy matching)."""
    normalized = normalize(text)
    if len(normalized) < 3:
        return {normalized} if normalized else set()
    return {normalized[i : i + 3] for i in range(len(normalized) - 2)}


def jaccard(a: set[str], b: set[str]) -> float:
    """Jaccard similarity of two sets."""
    if not a or not b:
        return 0.0
    return len(a & b) / len(a | b)


# --------------------------------------------------------------------------
# Categories
# --------------------------------------------------------------------------

CATEGORY_SYNONYMS: dict[str, str] = {
    "هدفون": "هدفون، هدست و هندزفری",
    "هدست": "هدفون، هدست و هندزفری",
    "هندزفری": "هدفون، هدست و هندزفری",
    "ایرپاد": "هدفون، هدست و هندزفری",
    "ایربادز": "هدفون، هدست و هندزفری",
    "ایرپادز": "هدفون، هدست و هندزفری",
    "بلوتوث": "هدفون، هدست و هندزفری",
    "گوشی": "گوشی موبایل",
    "موبایل": "گوشی موبایل",
    "آیفون": "گوشی موبایل",
    "اپل": "گوشی موبایل",
    "سامسونگ": "گوشی موبایل",
    "شیائومی": "گوشی موبایل",
    "کتونی": "کتانی و کفش اسپرت",
    "کفش": "کتانی و کفش اسپرت",
    "کفش ورزشی": "کتانی و کفش اسپرت",
    "اسنیکر": "کتانی و کفش اسپرت",
    "سنتی": "کتانی و کفش اسپرت",
    "لپ تاپ": "لپ تاپ و نوت بوک",
    "لپتاپ": "لپ تاپ و نوت بوک",
    "لپ تپ": "لپ تاپ و نوت بوک",
    "نوت بوک": "لپ تاپ و نوت بوک",
    "نوتبوک": "لپ تاپ و نوت بوک",
    "شارژر لپتاپ": "شارژر لپ تاپ",
    "شارژر لپ تاپ": "شارژر لپ تاپ",
    "لوستر": "لوستر و چراغ تزئینی",
    "لوستر و چراغ": "لوستر و چراغ تزئینی",
    "تیشرت": "تیشرت و پولوشرت",
    "پولوشرت": "تیشرت و پولوشرت",
    "فرش دستباف": "فرش دستبافت",
    "فرش دستبافت": "فرش دستبافت",
    "گلیم": "فرش دستبافت",
    "پارچه": "انواع پارچه",
    "منسوجات": "انواع پارچه",
    "گیتار": "گیتار",
    "ساز": "گیتار",
    "لامپ led": "لامپ LED و کم مصرف",
    "لامپ ال ای دی": "لامپ LED و کم مصرف",
    "چراغ پنلی": "چراغ پنلی و سقفی",
    "چراغ سقفی": "چراغ پنلی و سقفی",
    "کیف گوشی": "کیف و کاور گوشی",
    "قاب گوشی": "کیف و کاور گوشی",
    "محافظ صفحه": "محافظ صفحه",
    "تاچ ال سی دی": "تاچ و ال سی دی",
    "ال سی دی": "تاچ و ال سی دی",
    "باتری گوشی": "باتری گوشی موبایل",
}

# Categories that must never be returned when the user asks for a device.
ACCESSORY_CATEGORIES: set[str] = {
    "تاچ و ال سی دی",
    "کیف و کاور گوشی",
    "باتری گوشی موبایل",
    "محافظ صفحه",
}

# Search aliases are expanded as alternatives for one term; they are never
# combined as an AND requirement. The first two groups cover common user
# wording that differs from Torob's normalized catalog text.
SEARCH_ALIASES: dict[str, tuple[str, ...]] = {
    "کتونی": ("کتونی", "کتانی"),
    "کتانی": ("کتونی", "کتانی"),
    "نایک": ("نایک", "نایکی", "nike"),
    "نایکی": ("نایک", "نایکی", "nike"),
    "nike": ("نایک", "نایکی", "nike"),
    "سونی": ("سونی", "sony"),
    "sony": ("سونی", "sony"),
    "ایسوس": ("ایسوس", "asus"),
    "asus": ("ایسوس", "asus"),
    "سامسونگ": ("سامسونگ", "samsung"),
    "samsung": ("سامسونگ", "samsung"),
    "شیائومی": ("شیائومی", "xiaomi"),
    "xiaomi": ("شیائومی", "xiaomi"),
    "اپل": ("اپل", "apple"),
    "apple": ("اپل", "apple"),
    "انکر": ("انکر", "anker"),
    "anker": ("انکر", "anker"),
    "لنوو": ("لنوو", "lenovo"),
    "lenovo": ("لنوو", "lenovo"),
}

BRAND_ALIASES: dict[str, tuple[str, ...]] = {
    "نایک": ("نایک", "نایکی", "nike"),
    "نایکی": ("نایک", "نایکی", "nike"),
    "nike": ("نایک", "نایکی", "nike"),
    "سونی": ("سونی", "sony"),
    "sony": ("سونی", "sony"),
    "ایسوس": ("ایسوس", "asus"),
    "asus": ("ایسوس", "asus"),
    "سامسونگ": ("سامسونگ", "samsung"),
    "samsung": ("سامسونگ", "samsung"),
    "شیائومی": ("شیائومی", "xiaomi"),
    "xiaomi": ("شیائومی", "xiaomi"),
    "اپل": ("اپل", "apple"),
    "apple": ("اپل", "apple"),
    "انکر": ("انکر", "anker"),
    "anker": ("انکر", "anker"),
    "لنوو": ("لنوو", "lenovo"),
    "lenovo": ("لنوو", "lenovo"),
}

# Product titles that describe accessories rather than the requested core
# product. A term explicitly present in the user's query is not excluded.
ACCESSORY_WORDS: set[str] = {
    "کیسه",
    "قاب",
    "کاور",
    "بند",
    "واکس",
    "کفی",
    "جاکفشی",
    "جالباسی",
    "محافظ",
    "گلس",
    "پد",
    "کیف",
    "روکش",
    "پایه",
    "پایه نگهدارنده",
    "لوازم جانبی",
    "دستگاه واکس",
    "نظم دهنده",
    "فیلتر",
    "استابلایزر",
    "ترانس",
    "رگولاتور",
    "براکت",
    "شارژر",
    "کابل",
    "بوگیر",
    "خشک کن",
}

# Tehran bounding box used for the `in_bbox` flag.
TEHRAN_BBOX = {"lat_min": 35.55, "lat_max": 35.85, "lon_min": 51.10, "lon_max": 51.65}


def _load_tehran_neighbourhoods() -> list[dict]:
    path = Path(__file__).with_name("data") / "tehran_neighbourhoods.json"
    with path.open(encoding="utf-8") as handle:
        entries = json.load(handle)
    result = []
    for entry in entries:
        lat, lon = float(entry["lat"]), float(entry["lon"])
        if (
            TEHRAN_BBOX["lat_min"] <= lat <= TEHRAN_BBOX["lat_max"]
            and TEHRAN_BBOX["lon_min"] <= lon <= TEHRAN_BBOX["lon_max"]
        ):
            result.append({
                "name_fa": str(entry["name_fa"]),
                "aliases": [str(alias) for alias in entry.get("aliases", [])],
                "lat": lat,
                "lon": lon,
            })
    return result


TEHRAN_NEIGHBOURHOODS = _load_tehran_neighbourhoods()

# All recognized labels (including aliases) map to the same approximate
# centroid. The separate JSON records retain the canonical display label.
NEIGHBORHOODS: dict[str, tuple[float, float]] = {}
for _entry in TEHRAN_NEIGHBOURHOODS:
    _coords = (_entry["lat"], _entry["lon"])
    for _label in (_entry["name_fa"], *_entry["aliases"]):
        NEIGHBORHOODS.setdefault(_label, _coords)


def _squash(text: str) -> str:
    return normalize(text).replace(" ", "")


def geocode_neighbourhood(query: str | None) -> dict | None:
    """Resolve a Tehran neighbourhood name or alias to its canonical point."""
    normalized = normalize(query or "")
    squashed = _squash(normalized)
    if not normalized:
        return None
    for entry in TEHRAN_NEIGHBOURHOODS:
        labels = (entry["name_fa"], *entry["aliases"])
        if any(normalize(label) == normalized or _squash(label) == squashed for label in labels):
            return {
                "label": entry["name_fa"],
                "lat": entry["lat"],
                "lon": entry["lon"],
                "source": "fallback",
            }
    matches = []
    for entry in TEHRAN_NEIGHBOURHOODS:
        for label in (entry["name_fa"], *entry["aliases"]):
            key = normalize(label)
            if len(key) >= 3 and (key in normalized or (len(_squash(label)) >= 5 and _squash(label) in squashed)):
                matches.append((len(_squash(label)), entry))
    if not matches:
        return None
    entry = max(matches, key=lambda item: item[0])[1]
    return {
        "label": entry["name_fa"],
        "lat": entry["lat"],
        "lon": entry["lon"],
        "source": "fallback",
    }


def search_neighbourhoods(query: str, limit: int = 8) -> list[dict]:
    """Deterministic local suggestions for a typed Tehran neighbourhood.

    Exact names rank first, so «ونک» is offered before «پونک».
    """
    normalized = normalize(query)
    squashed = _squash(normalized)
    if len(squashed) < 2:
        return []
    found: list[tuple[int, str, dict]] = []
    seen: set[str] = set()
    for entry in TEHRAN_NEIGHBOURHOODS:
        labels = (entry["name_fa"], *entry["aliases"])
        best_rank: int | None = None
        for label in labels:
            key = normalize(label)
            flat = _squash(label)
            if not key:
                continue
            if key == normalized or flat == squashed:
                rank = 0
            elif key.startswith(normalized) or flat.startswith(squashed):
                rank = 1
            elif normalized in key or (len(squashed) >= 3 and squashed in flat):
                rank = 2
            else:
                continue
            if best_rank is None or rank < best_rank:
                best_rank = rank
        if best_rank is None:
            continue
        identity = normalize(entry["name_fa"])
        if identity in seen:
            continue
        seen.add(identity)
        found.append((best_rank, identity, {
            "name_fa": entry["name_fa"],
            "lat": entry["lat"],
            "lon": entry["lon"],
            "source": "fallback",
        }))
    found.sort(key=lambda item: (item[0], item[1]))
    return [item[2] for item in found[: max(0, limit)]]
