"""Read-only access to the SQLite catalog.

Every product / shop / price that reaches the UI comes from here - the LLM is
never allowed to invent an id.
"""

from __future__ import annotations

import json
import math
import sqlite3
import threading
from functools import lru_cache
from typing import Any, Iterable

from ..data_static import catalog_path
from ..normalize import normalize

_CONN: sqlite3.Connection | None = None
_LOCK = threading.Lock()


def get_conn() -> sqlite3.Connection:
    """Lazily open the (read only) catalog connection."""
    global _CONN
    if _CONN is None:
        with _LOCK:
            if _CONN is None:
                conn = sqlite3.connect(str(catalog_path()), check_same_thread=False)
                conn.row_factory = sqlite3.Row
                conn.execute("PRAGMA query_only = ON")
                _CONN = conn
    return _CONN


def reset_conn() -> None:
    global _CONN
    with _LOCK:
        if _CONN is not None:
            _CONN.close()
        _CONN = None


def _rows(cursor: sqlite3.Cursor) -> list[dict]:
    return [dict(row) for row in cursor.fetchall()]


# --------------------------------------------------------------------------
# categories
# --------------------------------------------------------------------------


def list_categories(limit: int = 60) -> list[str]:
    """Category names ordered by how many products they contain."""
    sql = "SELECT name FROM categories ORDER BY n_products DESC"
    params: tuple = ()
    if limit:
        sql += " LIMIT ?"
        params = (limit,)
    try:
        rows = get_conn().execute(sql, params).fetchall()
    except sqlite3.Error:
        return []
    return [row["name"] for row in rows]


def all_category_names() -> list[str]:
    try:
        rows = get_conn().execute("SELECT name FROM categories").fetchall()
    except sqlite3.Error:
        return []
    return [row["name"] for row in rows]


def category_stats() -> list[dict]:
    try:
        return _rows(get_conn().execute("SELECT * FROM categories ORDER BY n_products DESC"))
    except sqlite3.Error:
        return []


# --------------------------------------------------------------------------
# search
# --------------------------------------------------------------------------

BASE_SELECT = """
SELECT p.product_id, p.persian_title, p.brand_name, p.model, p.category_name,
       p.image_urls, p.image_first, p.specs, p.search_text,
       COUNT(DISTINCT o.shop_id) AS n_shops,
       MIN(o.price_toman) AS min_price,
       MAX(o.price_toman) AS max_price
FROM products p JOIN offers o ON o.product_id = p.product_id
"""


def search_products(
    keywords: Iterable[str] | None = None,
    category: str | None = None,
    budget_max: int | None = None,
    budget_min: int | None = None,
    limit: int = 30,
    min_shops: int = 2,
    match_mode: str = "all",
) -> list[dict]:
    """Find products in the catalog.

    ``min_shops`` defaults to 2 because only ~35k products are sold by more
    than one shop - recommending from those gives a much better store
    comparison.  ``match_mode="any"`` relaxes the keyword filter (used as a
    fallback when the strict AND-search returns nothing useful).
    """
    keywords = [k for k in (keywords or []) if k and k.strip()]
    where = ["p.n_shops >= :min_shops"]
    params: dict[str, Any] = {"min_shops": min_shops, "limit": limit}

    if category:
        where.append("p.category_name = :category")
        params["category"] = category

    if keywords:
        clauses = []
        for index, keyword in enumerate(keywords):
            key = f"kw{index}"
            params[key] = f"%{normalize(keyword)}%"
            clauses.append(f"p.search_text LIKE :{key}")
        joiner = " OR " if match_mode == "any" else " AND "
        where.append("(" + joiner.join(clauses) + ")")

    having = []
    if budget_max is not None:
        having.append("MIN(o.price_toman) <= :budget_max")
        params["budget_max"] = budget_max
    if budget_min is not None:
        having.append("MAX(o.price_toman) >= :budget_min")
        params["budget_min"] = budget_min

    sql = BASE_SELECT
    sql += " WHERE " + " AND ".join(where)
    sql += " GROUP BY p.product_id"
    if having:
        sql += " HAVING " + " AND ".join(having)
    sql += " ORDER BY n_shops DESC, min_price ASC LIMIT :limit"

    try:
        rows = _rows(get_conn().execute(sql, params))
    except sqlite3.Error:
        return []
    for row in rows:
        row["spec_count"] = count_specs(row.get("specs"))
        row["median_price"] = median_price_for(row["product_id"], row["min_price"], row["max_price"])
    return rows


def median_price_for(product_id: str, fallback_min: int | None, fallback_max: int | None) -> int:
    try:
        row = get_conn().execute(
            "SELECT median_price FROM products WHERE product_id = ?", (product_id,)
        ).fetchone()
    except sqlite3.Error:
        row = None
    if row and row["median_price"]:
        return int(row["median_price"])
    if fallback_min and fallback_max:
        return int((fallback_min + fallback_max) / 2)
    return int(fallback_min or 0)


def count_specs(specs_json: str | None) -> int:
    if not specs_json:
        return 0
    try:
        parsed = json.loads(specs_json)
    except (ValueError, TypeError):
        return 0
    return len(parsed) if isinstance(parsed, list) else 0


def parse_specs(specs_json: str | None) -> list[dict]:
    if not specs_json:
        return []
    try:
        parsed = json.loads(specs_json)
    except (ValueError, TypeError):
        return []
    return parsed if isinstance(parsed, list) else []


def first_image(product: dict) -> str | None:
    if product.get("image_first"):
        return product["image_first"]
    raw = product.get("image_urls")
    if not raw:
        return None
    try:
        parsed = json.loads(raw)
    except (ValueError, TypeError):
        return None
    if isinstance(parsed, list) and parsed:
        return parsed[0]
    return None


# --------------------------------------------------------------------------
# single product / offers
# --------------------------------------------------------------------------


def get_product(product_id: str) -> dict | None:
    try:
        row = get_conn().execute(
            "SELECT * FROM products WHERE product_id = ?", (product_id,)
        ).fetchone()
    except sqlite3.Error:
        return None
    if not row:
        return None
    product = dict(row)
    product["spec_count"] = count_specs(product.get("specs"))
    product["image_first"] = first_image(product)
    return product


def get_offers_for_product(product_id: str) -> list[dict]:
    """All offers of a product, one per shop (cheapest), with shop details."""
    sql = """
    SELECT o.offer_id, o.price_toman, o.last_price_changed_at, o.warranty, o.seller_title,
           s.shop_id, s.name, s.address, s.mall, s.floor, s.unit, s.plaque, s.lat, s.lon,
           s.weekly_hours, s.payment_options, s.location_label, s.hours_declared
    FROM offers o JOIN shops s ON s.shop_id = o.shop_id
    WHERE o.product_id = ?
    ORDER BY o.price_toman ASC
    """
    try:
        rows = _rows(get_conn().execute(sql, (product_id,)))
    except sqlite3.Error:
        return []
    best_per_shop: dict[str, dict] = {}
    for row in rows:
        current = best_per_shop.get(row["shop_id"])
        if current is None or row["price_toman"] < current["price_toman"]:
            best_per_shop[row["shop_id"]] = row
    return list(best_per_shop.values())


def get_shops(shop_ids: Iterable[str]) -> list[dict]:
    ids = [s for s in shop_ids if s]
    if not ids:
        return []
    placeholders = ",".join("?" for _ in ids)
    try:
        return _rows(
            get_conn().execute(f"SELECT * FROM shops WHERE shop_id IN ({placeholders})", ids)
        )
    except sqlite3.Error:
        return []


def get_offer(offer_id: str) -> dict | None:
    try:
        row = get_conn().execute(
            """
            SELECT o.*, s.name, s.address, s.mall, s.floor, s.lat, s.lon, s.weekly_hours,
                   s.payment_options, s.location_label
            FROM offers o JOIN shops s ON s.shop_id = o.shop_id
            WHERE o.offer_id = ?
            """,
            (offer_id,),
        ).fetchone()
    except sqlite3.Error:
        return None
    return dict(row) if row else None


def shop_by_id(shop_id: str) -> dict | None:
    try:
        row = get_conn().execute("SELECT * FROM shops WHERE shop_id = ?", (shop_id,)).fetchone()
    except sqlite3.Error:
        return None
    return dict(row) if row else None


def products_in_category(category: str, limit: int = 20) -> list[dict]:
    try:
        rows = _rows(
            get_conn().execute(
                """
                SELECT product_id, persian_title, brand_name, category_name, image_first, image_urls,
                       n_shops, min_price, median_price
                FROM products WHERE category_name = ?
                ORDER BY n_shops DESC, min_price ASC LIMIT ?
                """,
                (category, limit),
            )
        )
    except sqlite3.Error:
        return []
    return rows


def distinct_brands(category: str, limit: int = 10) -> list[str]:
    try:
        rows = get_conn().execute(
            """
            SELECT brand_name, COUNT(*) AS n FROM products
            WHERE category_name = ? AND brand_name IS NOT NULL AND brand_name <> ''
            GROUP BY brand_name ORDER BY n DESC LIMIT ?
            """,
            (category, limit),
        ).fetchall()
    except sqlite3.Error:
        return []
    return [row["brand_name"] for row in rows]


# --------------------------------------------------------------------------
# ranking helpers
# --------------------------------------------------------------------------


def _log_popularity(n_shops: int, max_shops: int) -> float:
    if max_shops <= 1:
        return 0.0
    return math.log1p(n_shops) / math.log1p(max_shops)


def budget_fit(min_price: int | None, budget_max: int | None) -> float:
    if not budget_max:
        return 0.75
    if min_price is None:
        return 0.0
    if min_price > budget_max:
        return 0.0
    return 0.5 + 0.5 * max(0.0, 1 - (min_price / budget_max))


def spec_richness(spec_count: int) -> float:
    return min(1.0, spec_count / 15.0)


def product_score(candidate: dict, budget_max: int | None, max_shops: int) -> float:
    """0.45 popularity + 0.35 budget fit + 0.20 spec richness."""
    popularity = _log_popularity(int(candidate.get("n_shops") or 0), max_shops)
    fit = budget_fit(candidate.get("min_price"), budget_max)
    richness = spec_richness(int(candidate.get("spec_count") or 0))
    return 0.45 * popularity + 0.35 * fit + 0.20 * richness


def search_score(keywords: Iterable[str], candidate: dict, category: str | None) -> float:
    """Fraction of the query keywords that match, scaled by the category match."""
    keywords = [normalize(k) for k in keywords if k and k.strip()]
    if not keywords:
        base = 1.0
    else:
        haystack = candidate.get("search_text") or normalize(
            " ".join(
                filter(
                    None,
                    [
                        candidate.get("persian_title"),
                        candidate.get("brand_name"),
                        candidate.get("model"),
                    ],
                )
            )
        )
        hits = sum(1 for keyword in keywords if keyword and keyword in haystack)
        base = hits / len(keywords)
    if category and candidate.get("category_name") == category:
        return base
    return base * 0.6


def pick_cards(candidates: list[dict], budget_max: int | None) -> list[dict]:
    """Pick the best / budget / premium cards out of the candidates.

    * ``best``    - the highest product score inside the budget
    * ``budget``  - the cheapest option that is still comparable to the best
      one (a real amount of sellers, not an outlier listing)
    * ``premium`` - the most expensive option that still fits into 1.5x the
      budget and is above the price of the best card
    """
    if not candidates:
        return []
    max_shops = max(int(c.get("n_shops") or 0) for c in candidates) or 1
    scored = []
    for candidate in candidates:
        item = dict(candidate)
        item["score"] = product_score(candidate, budget_max, max_shops)
        item["median"] = int(candidate.get("median_price") or candidate.get("min_price") or 0)
        scored.append(item)
    scored.sort(key=lambda item: (-item["score"], item["median"]))

    chosen: list[dict] = []
    used: set[str] = set()

    def take(predicate, pool: list[dict] | None = None) -> dict | None:
        for item in pool if pool is not None else scored:
            if item["product_id"] in used:
                continue
            if predicate(item):
                used.add(item["product_id"])
                return item
        return None

    # --- best: highest score that fits into the budget
    best = take(lambda item: budget_max is None or int(item.get("min_price") or 0) <= budget_max)
    if best is None:
        best = take(lambda item: True)
    if best:
        best["kind"] = "best"
        chosen.append(best)

    best_shops = int((best or {}).get("n_shops") or 0)
    best_median = int((best or {}).get("median") or 0)

    # --- budget: cheapest comparable option (enough sellers, sane price)
    min_shops_budget = max(3, round(best_shops * 0.4))
    budget_pool = [
        item
        for item in scored
        if int(item.get("n_shops") or 0) >= min_shops_budget
        and (not best_median or item["median"] >= best_median * 0.5)
    ]
    if not budget_pool:
        budget_pool = [item for item in scored if int(item.get("n_shops") or 0) >= 3]
    if not budget_pool:
        budget_pool = scored
    budget = take(lambda item: True, pool=sorted(budget_pool, key=lambda item: (item["median"], -(item.get("n_shops") or 0))))
    if budget:
        budget["kind"] = "budget"
        chosen.append(budget)

    # --- premium: the most expensive option that still fits the budget
    def premium_ok(item: dict) -> bool:
        if budget_max and item["median"] > budget_max * 1.5:
            return False
        if best_median and item["median"] < best_median:
            return False
        return item["median"] > 0

    min_shops_premium = max(3, round(best_shops * 0.3))
    premium_pool = [
        item
        for item in scored
        if premium_ok(item) and int(item.get("n_shops") or 0) >= min_shops_premium
    ]
    if not premium_pool:
        premium_pool = [item for item in scored if premium_ok(item)]
    if not premium_pool:
        premium_pool = sorted(scored, key=lambda item: -item["median"])
    premium = take(lambda item: True, pool=sorted(premium_pool, key=lambda item: -item["median"]))
    if premium and (not best or premium["product_id"] != best["product_id"]):
        premium["kind"] = "premium"
        chosen.append(premium)

    # keep the requested order: best, budget, premium
    order = {"best": 0, "budget": 1, "premium": 2}
    chosen.sort(key=lambda item: order.get(item.get("kind", "best"), 3))
    return chosen


def cheap_budget_card(candidates: list[dict], exclude: set[str] | None = None) -> dict | None:
    """Lowest median price among products sold by at least 3 shops."""
    exclude = exclude or set()
    pool = [
        c
        for c in candidates
        if c["product_id"] not in exclude and int(c.get("n_shops") or 0) >= 3
    ]
    if not pool:
        pool = [c for c in candidates if c["product_id"] not in exclude]
    if not pool:
        return None
    return min(pool, key=lambda c: (int(c.get("median_price") or c.get("min_price") or 0)))
