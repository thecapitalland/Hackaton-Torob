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
    "کفش ورزشی": "کتانی و کفش اسپرت",
    "اسنیکر": "کتانی و کفش اسپرت",
    "سنتی": "کتانی و کفش اسپرت",
    "لپ تاپ": "لپ تاپ و نوت بوک",
    "لپتاپ": "لپ تاپ و نوت بوک",
    "لپ تپ": "لپ تاپ و نوت بوک",
    "نوت بوک": "لپ تاپ و نوت بوک",
    "نوتبوک": "لپ تاپ و نوت بوک",
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

# Neighbourhood coordinates used when the user picks a chip or when the LLM
# extracts a location label. (lat, lon)
NEIGHBORHOODS: dict[str, tuple[float, float]] = {
    "فردوسی": (35.7010, 51.4187),
    "میدان فردوسی": (35.7010, 51.4187),
    "جمهوری": (35.6925, 51.4105),
    "خیابان جمهوری": (35.6925, 51.4105),
    "ولیعصر": (35.7000, 51.4060),
    "تیرجار": (35.7000, 51.4060),
    "تجریش": (35.8040, 51.4330),
    "انقلاب": (35.7010, 51.3910),
    "لاله زار": (35.6923, 51.4229),
    "لاله‌زار": (35.6923, 51.4229),
    "بهارستان": (35.6925, 51.4310),
    "میدان بهارستان": (35.6925, 51.4310),
    "علاالدین": (35.6947, 51.4112),
    "علاءالدین": (35.6947, 51.4112),
    "حافظ": (35.6950, 51.4115),
    "بازار رضا": (36.3180, 59.6067),  # Mashhad - never used, kept out of Tehran flow
}

# Tehran bounding box used for the `in_bbox` flag.
TEHRAN_BBOX = {"lat_min": 35.55, "lat_max": 35.85, "lon_min": 51.10, "lon_max": 51.65}
