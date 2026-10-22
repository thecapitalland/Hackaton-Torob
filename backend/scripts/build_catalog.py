"""Build the slim SQLite catalog used by the Torobche backend.

Usage:
    python backend/scripts/build_catalog.py --src <dir with shops.csv/products.csv/offers.csv> \
        --out data/catalog.db

The raw dataset is ~280 MB of CSV. This script cleans it and stores only what
the agent actually needs:

* offers outside ``[10_000, 2_000_000_000]`` toman are dropped
* per product, offers outside ``[0.33, 3] x median`` are dropped when the
  product has at least 4 offers (removes the R50i 22,950,000 outlier)
* one offer per (product, shop) pair is kept - the cheapest one
* ``offers.description``, ``shops.contacts`` and ``shops.instagram`` are never
  stored (the dataset phone numbers are fake and must never leak to the UI)
"""

from __future__ import annotations

import argparse
import json
import re
import sqlite3
import sys
import time
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

try:  # the windows console defaults to cp1256 which can not print Persian
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:  # pragma: no cover
    pass

from app.normalize import (  # noqa: E402
    TEHRAN_BBOX,
    build_search_text,
    normalize_display,
    normalize_mall_name,
)

MALL_RE = re.compile(r"((?:پاساژ|مجتمع|مرکز خرید|بازار|برج)\s+[^،,\-]+)")
FLOOR_RE = re.compile(r"طبقه\s*([\-‑]?\d+|[^\s،,]+)")
UNIT_RE = re.compile(r"واحد\s*(\d+)")
PLAQUE_RE = re.compile(r"پلاک\s*(\d+)")

PRICE_MIN = 10_000
PRICE_MAX = 2_000_000_000
OUTLIER_LO = 0.33
OUTLIER_HI = 3.0

# Categories that must survive any slimming pass (used by the demo).
DEMO_CATEGORIES = [
    "هدفون، هدست و هندزفری",
    "گوشی موبایل",
    "کتانی و کفش اسپرت",
    "لپ تاپ و نوت بوک",
    "تیشرت و پولوشرت",
    "لوستر و چراغ تزئینی",
    "لامپ LED و کم مصرف",
    "چراغ پنلی و سقفی",
    "گیتار",
    "فرش دستبافت",
    "فرش ماشینی",
    "انواع پارچه",
    "شمش طلا",
]


def log(msg: str) -> None:
    print(f"[build_catalog] {msg}", flush=True)


def find_csvs(src: Path) -> dict[str, Path]:
    """Locate the three CSV files, ignoring ``__MACOSX`` and nested folders."""
    found: dict[str, Path] = {}
    for name in ("shops.csv", "products.csv", "offers.csv"):
        candidates = [p for p in src.rglob(name) if "__MACOSX" not in p.parts]
        if not candidates:
            raise SystemExit(f"could not find {name} under {src}")
        found[name] = candidates[0]
    return found


def read_csv(path: Path, usecols: list[str] | None = None) -> pd.DataFrame:
    log(f"reading {path.name} ...")
    df = pd.read_csv(path, dtype=str, keep_default_na=False, usecols=usecols)
    df = df.replace({"null": None, "": None, "NULL": None, "None": None})
    return df


def extract_mall(address: str | None) -> str | None:
    if not address:
        return None
    match = MALL_RE.search(address)
    if not match:
        return None
    name = normalize_mall_name(match.group(1))
    return name or None


def extract_floor(address: str | None) -> str | None:
    if not address:
        return None
    match = FLOOR_RE.search(address)
    if not match:
        return None
    floor = match.group(1).strip()
    floor = re.sub(r"^[،,\s]+|[،,\s]+$", "", floor)
    return floor or None


def extract_unit(address: str | None) -> str | None:
    if not address:
        return None
    match = UNIT_RE.search(address)
    return match.group(1) if match else None


def extract_plaque(address: str | None) -> str | None:
    if not address:
        return None
    match = PLAQUE_RE.search(address)
    return match.group(1) if match else None


def hours_declared(weekly_hours: str | None) -> bool:
    if not weekly_hours:
        return False
    try:
        data = json.loads(weekly_hours)
    except (ValueError, TypeError):
        return False
    if not isinstance(data, dict):
        return False
    for day in data.values():
        if isinstance(day, dict) and day.get("status") == "declared":
            return True
    return False


def to_float(value) -> float | None:
    if value is None or value == "":
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def main() -> int:
    parser = argparse.ArgumentParser(description="Build the Torobche catalog.db")
    parser.add_argument("--src", required=True, help="folder containing the raw CSV files")
    parser.add_argument("--out", required=True, help="output sqlite path")
    parser.add_argument("--max-mb", type=float, default=150.0, help="target size in MB")
    parser.add_argument(
        "--keep-single-shop",
        action="store_true",
        help="keep products that only have one shop (bigger database)",
    )
    args = parser.parse_args()

    started = time.time()
    src = Path(args.src)
    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    if out.exists():
        out.unlink()

    csvs = find_csvs(src)
    for key, path in csvs.items():
        log(f"{key}: {path}")

    # ------------------------------------------------------------------ shops
    shops = read_csv(
        csvs["shops.csv"],
        usecols=[
            "address",
            "category_names",
            "lat",
            "lon",
            "location_label",
            "name",
            "payment_options",
            "shop_id",
            "supports_fast_delivery",
            "website_url",
            "weekly_hours",
        ],
    )
    log(f"shops raw: {len(shops)}")
    shops["lat"] = shops["lat"].map(to_float)
    shops["lon"] = shops["lon"].map(to_float)

    # ----------------------------------------------------------------- offers
    offers = read_csv(
        csvs["offers.csv"],
        usecols=[
            "last_price_changed_at",
            "offer_id",
            "price_toman",
            "product_id",
            "seller_title",
            "shop_id",
            "warranty",
        ],
    )
    log(f"offers raw: {len(offers)}")
    offers["price_toman"] = pd.to_numeric(offers["price_toman"], errors="coerce")
    in_range = offers["price_toman"].between(PRICE_MIN, PRICE_MAX)
    dropped_range = int((~in_range).sum())
    offers = offers[in_range].copy()
    log(f"offers after price range [{PRICE_MIN}, {PRICE_MAX}]: {len(offers)} (dropped {dropped_range})")

    # per-product median based outlier removal
    grouped = offers.groupby("product_id")["price_toman"]
    median = grouped.transform("median")
    count = grouped.transform("count")
    lo = median * OUTLIER_LO
    hi = median * OUTLIER_HI
    keep = (count < 4) | (offers["price_toman"] >= lo) & (offers["price_toman"] <= hi)
    dropped_outliers = int((~keep).sum())
    offers = offers[keep].copy()
    log(f"offers after outlier rule: {len(offers)} (dropped {dropped_outliers})")

    # one offer per (product, shop): keep the cheapest
    offers = offers.sort_values(["product_id", "shop_id", "price_toman"])
    before = len(offers)
    offers = offers.drop_duplicates(subset=["product_id", "shop_id"], keep="first")
    log(f"offers after (product, shop) dedupe: {len(offers)} (dropped {before - len(offers)})")

    kept_product_ids = set(offers["product_id"].tolist())
    kept_shop_ids = set(offers["shop_id"].tolist())
    log(f"products referenced by kept offers: {len(kept_product_ids)}")
    log(f"shops referenced by kept offers: {len(kept_shop_ids)}")

    # --------------------------------------------------------------- products
    products = read_csv(
        csvs["products.csv"],
        usecols=[
            "brand_name",
            "category_name",
            "image_urls",
            "model",
            "persian_title",
            "product_id",
            "specs",
        ],
    )
    log(f"products raw: {len(products)}")
    products = products[products["product_id"].isin(kept_product_ids)].copy()
    log(f"products kept: {len(products)}")

    products["search_text"] = [
        build_search_text(title, brand, model)
        for title, brand, model in zip(
            products["persian_title"], products["brand_name"], products["model"]
        )
    ]
    products["image_first"] = products["image_urls"].map(first_image)

    # product level statistics derived from the cleaned offers
    stats = (
        offers.groupby("product_id")["price_toman"]
        .agg(
            n_shops=lambda s: int(offers.loc[s.index, "shop_id"].nunique()),
            min_price="min",
            median_price="median",
        )
    )
    products["n_shops"] = products["product_id"].map(stats["n_shops"]).fillna(0).astype(int)
    products["min_price"] = products["product_id"].map(stats["min_price"]).astype("int64")
    products["median_price"] = products["product_id"].map(stats["median_price"]).astype("int64")

    # ------------------------------------------------------------------ shops
    shops = shops[shops["shop_id"].isin(kept_shop_ids)].copy()
    shops["has_ll"] = [
        1
        if (lat is not None and lon is not None and lat != 0 and lon != 0)
        else 0
        for lat, lon in zip(shops["lat"], shops["lon"])
    ]
    shops["in_bbox"] = [
        1
        if (
            lat is not None
            and lon is not None
            and TEHRAN_BBOX["lat_min"] <= lat <= TEHRAN_BBOX["lat_max"]
            and TEHRAN_BBOX["lon_min"] <= lon <= TEHRAN_BBOX["lon_max"]
        )
        else 0
        for lat, lon in zip(shops["lat"], shops["lon"])
    ]
    shops["mall"] = shops["address"].map(extract_mall)
    shops["floor"] = shops["address"].map(extract_floor)
    shops["unit"] = shops["address"].map(extract_unit)
    shops["plaque"] = shops["address"].map(extract_plaque)
    shops["hours_declared"] = shops["weekly_hours"].map(lambda h: 1 if hours_declared(h) else 0)

    # --------------------------------------------------------------- write db
    conn = sqlite3.connect(out)
    cur = conn.cursor()
    cur.executescript(
        """
        PRAGMA journal_mode = OFF;
        PRAGMA synchronous = OFF;
        PRAGMA temp_store = MEMORY;
        CREATE TABLE shops (
            shop_id TEXT PRIMARY KEY,
            name TEXT,
            address TEXT,
            location_label TEXT,
            category_names TEXT,
            lat REAL,
            lon REAL,
            has_ll INTEGER,
            in_bbox INTEGER,
            mall TEXT,
            floor TEXT,
            unit TEXT,
            plaque TEXT,
            payment_options TEXT,
            supports_fast_delivery TEXT,
            website_url TEXT,
            weekly_hours TEXT,
            hours_declared INTEGER
        );
        CREATE TABLE products (
            product_id TEXT PRIMARY KEY,
            persian_title TEXT,
            brand_name TEXT,
            model TEXT,
            category_name TEXT,
            image_urls TEXT,
            image_first TEXT,
            specs TEXT,
            search_text TEXT,
            n_shops INTEGER DEFAULT 0,
            min_price INTEGER,
            median_price INTEGER
        );        CREATE TABLE offers (
            offer_id TEXT PRIMARY KEY,
            product_id TEXT,
            shop_id TEXT,
            price_toman INTEGER,
            last_price_changed_at TEXT,
            seller_title TEXT,
            warranty TEXT
        );
        """
    )

    log("writing shops ...")
    cur.executemany(
        "INSERT INTO shops VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
        shops[
            [
                "shop_id",
                "name",
                "address",
                "location_label",
                "category_names",
                "lat",
                "lon",
                "has_ll",
                "in_bbox",
                "mall",
                "floor",
                "unit",
                "plaque",
                "payment_options",
                "supports_fast_delivery",
                "website_url",
                "weekly_hours",
                "hours_declared",
            ]
        ].itertuples(index=False, name=None),
    )

    log("writing products ...")
    cur.executemany(
        "INSERT INTO products (product_id, persian_title, brand_name, model, category_name,"
        " image_urls, image_first, specs, search_text, n_shops, min_price, median_price)"
        " VALUES (?,?,?,?,?,?,?,?,?,?,?,?)",
        products[
            [
                "product_id",
                "persian_title",
                "brand_name",
                "model",
                "category_name",
                "image_urls",
                "image_first",
                "specs",
                "search_text",
                "n_shops",
                "min_price",
                "median_price",
            ]
        ].itertuples(index=False, name=None),
    )

    log("writing offers ...")
    offers_out = offers[
        ["offer_id", "product_id", "shop_id", "price_toman", "last_price_changed_at", "seller_title", "warranty"]
    ].copy()
    offers_out["price_toman"] = offers_out["price_toman"].astype("int64")
    cur.executemany(
        "INSERT INTO offers VALUES (?,?,?,?,?,?,?)",
        offers_out.itertuples(index=False, name=None),
    )
    conn.commit()

    size_mb = out.stat().st_size / (1024 * 1024)
    log(f"database size before slimming: {size_mb:.1f} MB")

    # -------------------------------------------------------------- slimming
    if size_mb > args.max_mb and not args.keep_single_shop:
        log(f"database is larger than {args.max_mb} MB - slimming (drop single-shop products)")
        demo_marks = ",".join("?" for _ in DEMO_CATEGORIES)

        # indexes first: the deletes below scan the offers table
        log("creating temporary indexes for the slimming pass ...")
        conn.executescript(
            """
            CREATE INDEX IF NOT EXISTS idx_offers_product ON offers(product_id);
            CREATE INDEX IF NOT EXISTS idx_offers_shop ON offers(shop_id);
            CREATE INDEX IF NOT EXISTS idx_offers_price ON offers(price_toman);
            CREATE INDEX IF NOT EXISTS idx_products_category ON products(category_name);
            CREATE INDEX IF NOT EXISTS idx_products_brand ON products(brand_name);
            CREATE INDEX IF NOT EXISTS idx_products_nshops ON products(n_shops);
            CREATE INDEX IF NOT EXISTS idx_shops_location ON shops(location_label);
            CREATE INDEX IF NOT EXISTS idx_shops_mall ON shops(mall);
            """
        )
        conn.commit()

        log("dropping single-shop products ...")
        conn.execute(
            f"""
            DELETE FROM offers WHERE product_id IN (
                SELECT product_id FROM products
                WHERE n_shops < 2 AND (category_name IS NULL OR category_name NOT IN ({demo_marks}))
            )
            """,
            DEMO_CATEGORIES,
        )
        conn.execute(
            f"""
            DELETE FROM products WHERE n_shops < 2
            AND (category_name IS NULL OR category_name NOT IN ({demo_marks}))
            """,
            DEMO_CATEGORIES,
        )
        log("dropping shops without offers ...")
        conn.execute("CREATE TEMP TABLE tmp_shop_ids AS SELECT DISTINCT shop_id FROM offers")
        conn.execute("DELETE FROM shops WHERE shop_id NOT IN (SELECT shop_id FROM tmp_shop_ids)")
        conn.execute("DROP TABLE tmp_shop_ids")
        conn.execute(
            """
            UPDATE products SET
                n_shops = (SELECT COUNT(DISTINCT o.shop_id) FROM offers o WHERE o.product_id = products.product_id),
                min_price = (SELECT MIN(o.price_toman) FROM offers o WHERE o.product_id = products.product_id)
            """
        )
        conn.commit()
        size_mb = out.stat().st_size / (1024 * 1024)
        log(f"database size after slimming: {size_mb:.1f} MB")

    # --------------------------------------------------------------- categories
    log("building categories table ...")
    conn.execute(
        "CREATE TABLE categories (name TEXT PRIMARY KEY, n_products INTEGER, n_offers INTEGER)"
    )
    conn.execute(
        """
        INSERT INTO categories (name, n_products, n_offers)
        SELECT p.category_name, COUNT(DISTINCT p.product_id), COUNT(o.offer_id)
        FROM products p LEFT JOIN offers o ON o.product_id = p.product_id
        WHERE p.category_name IS NOT NULL AND p.category_name <> ''
        GROUP BY p.category_name
        """
    )
    conn.commit()

    # ---------------------------------------------------------------- indexes
    log("creating indexes ...")
    conn.executescript(
        """
        CREATE INDEX IF NOT EXISTS idx_offers_product ON offers(product_id);
        CREATE INDEX IF NOT EXISTS idx_offers_shop ON offers(shop_id);
        CREATE INDEX IF NOT EXISTS idx_offers_price ON offers(price_toman);
        CREATE INDEX IF NOT EXISTS idx_products_category ON products(category_name);
        CREATE INDEX IF NOT EXISTS idx_products_brand ON products(brand_name);
        CREATE INDEX IF NOT EXISTS idx_products_nshops ON products(n_shops);
        CREATE INDEX IF NOT EXISTS idx_products_min_price ON products(min_price);
        CREATE INDEX IF NOT EXISTS idx_shops_location ON shops(location_label);
        CREATE INDEX IF NOT EXISTS idx_shops_mall ON shops(mall);
        CREATE VIEW IF NOT EXISTS v_offers AS
        SELECT o.offer_id, o.product_id, o.shop_id, o.price_toman, o.last_price_changed_at,
               o.seller_title, o.warranty,
               p.persian_title, p.brand_name, p.model, p.category_name, p.image_first, p.image_urls, p.specs,
               s.name AS shop_name, s.address, s.mall, s.floor, s.unit, s.plaque,
               s.lat, s.lon, s.location_label, s.payment_options, s.weekly_hours, s.hours_declared
        FROM offers o
        JOIN products p ON p.product_id = o.product_id
        JOIN shops s ON s.shop_id = o.shop_id;
        """
    )
    conn.commit()
    log("vacuuming ...")
    conn.execute("VACUUM")
    conn.commit()

    # ----------------------------------------------------------------- report
    stats = {
        "products": conn.execute("SELECT COUNT(*) FROM products").fetchone()[0],
        "offers": conn.execute("SELECT COUNT(*) FROM offers").fetchone()[0],
        "shops": conn.execute("SELECT COUNT(*) FROM shops").fetchone()[0],
        "categories": conn.execute("SELECT COUNT(*) FROM categories").fetchone()[0],
        "products_with_2plus_shops": conn.execute(
            "SELECT COUNT(*) FROM products WHERE n_shops >= 2"
        ).fetchone()[0],
        "size_mb": round(out.stat().st_size / (1024 * 1024), 1),
    }
    conn.close()

    print()
    print("=" * 60)
    print("catalog.db built")
    for key, value in stats.items():
        print(f"  {key:28s}: {value}")
    print(f"  {'elapsed_sec':28s}: {round(time.time() - started, 1)}")
    print("=" * 60)
    return 0


def first_image(value) -> str | None:
    if not value:
        return None
    try:
        parsed = json.loads(value)
    except (ValueError, TypeError):
        return None
    if isinstance(parsed, list) and parsed:
        return parsed[0]
    return None


if __name__ == "__main__":
    raise SystemExit(main())
