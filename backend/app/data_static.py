"""Static data loading (mock seller replies, mock cafes, markets) and path helpers."""

from __future__ import annotations

import json
import logging
import os
import sqlite3
import subprocess
import sys
import threading
from functools import lru_cache
from pathlib import Path

APP_DIR = Path(__file__).resolve().parent
BACKEND_DIR = APP_DIR.parent
PROJECT_ROOT = BACKEND_DIR.parent

DATA_DIR = Path(os.environ.get("DATA_DIR", PROJECT_ROOT / "data"))
logger = logging.getLogger("torobche.catalog")
_CATALOG_LOCK = threading.Lock()
_VALIDATED_CATALOGS: set[Path] = set()


def catalog_path() -> Path:
    return Path(os.environ.get("CATALOG_PATH", DATA_DIR / "catalog.db"))


def _catalog_is_usable(path: Path) -> bool:
    if not path.is_file() or path.stat().st_size <= 0:
        return False
    conn: sqlite3.Connection | None = None
    try:
        uri = f"file:{path.resolve().as_posix()}?mode=ro"
        conn = sqlite3.connect(uri, uri=True, timeout=5)
        check = conn.execute("PRAGMA quick_check").fetchone()
        if not check or check[0] != "ok":
            return False
        tables = {
            row[0]
            for row in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")
        }
        if not {"products", "offers", "shops", "categories"}.issubset(tables):
            return False
        products = int(conn.execute("SELECT COUNT(*) FROM products").fetchone()[0])
        offers = int(conn.execute("SELECT COUNT(*) FROM offers").fetchone()[0])
        shops = int(conn.execute("SELECT COUNT(*) FROM shops").fetchone()[0])
        return products > 0 and offers > 0 and shops > 0
    except (OSError, sqlite3.Error, ValueError):
        return False
    finally:
        if conn is not None:
            conn.close()


def _raw_dataset_dir() -> Path | None:
    configured = os.environ.get("TOROB_DATASET_DIR", "").strip()
    candidates = [Path(configured)] if configured else []
    candidates.extend(
        [
            PROJECT_ROOT / "dataset",
            PROJECT_ROOT / "torob-dataset",
            PROJECT_ROOT / "data" / "raw",
        ]
    )
    for candidate in candidates:
        if all((candidate / name).is_file() for name in ("shops.csv", "products.csv", "offers.csv")):
            return candidate
    return None


def ensure_catalog() -> Path:
    """Validate the catalog, rebuild it from configured raw CSVs if possible.

    A missing/unhydrated LFS object is a clear startup error unless a raw data
    directory is configured. Invalid catalogs are never treated as empty data.
    """
    path = catalog_path().resolve()
    if path in _VALIDATED_CATALOGS:
        return path
    with _CATALOG_LOCK:
        if path in _VALIDATED_CATALOGS:
            return path
        if _catalog_is_usable(path):
            _VALIDATED_CATALOGS.add(path)
            return path

        raw_dir = _raw_dataset_dir()
        if raw_dir is not None:
            build_script = BACKEND_DIR / "scripts" / "build_catalog.py"
            temporary = path.with_name(f"{path.stem}.building{path.suffix}")
            path.parent.mkdir(parents=True, exist_ok=True)
            temporary.unlink(missing_ok=True)
            logger.warning(
                "Catalog %s is missing/invalid; building it from raw CSVs at %s",
                path,
                raw_dir,
            )
            try:
                subprocess.run(
                    [sys.executable, str(build_script), "--src", str(raw_dir), "--out", str(temporary)],
                    check=True,
                    cwd=str(PROJECT_ROOT),
                )
                if not _catalog_is_usable(temporary):
                    raise RuntimeError("catalog builder produced a missing, empty, or invalid SQLite catalog")
                os.replace(temporary, path)
            except Exception as exc:
                temporary.unlink(missing_ok=True)
                raise RuntimeError(
                    f"Torob catalog could not be built at {path}. Check the three raw CSV files "
                    "(shops.csv, products.csv, offers.csv) and TOROB_DATASET_DIR."
                ) from exc
            logger.info("Catalog is ready: %s (%d bytes)", path, path.stat().st_size)
            _VALIDATED_CATALOGS.add(path)
            return path

        size = path.stat().st_size if path.exists() else 0
        raise RuntimeError(
            f"Torob catalog is unavailable or invalid: {path} ({size} bytes). "
            "For a fresh clone run `git lfs pull` to fetch data/catalog.db, or set "
            "TOROB_DATASET_DIR to a directory containing shops.csv, products.csv, and offers.csv. "
            "The application will not start with an empty catalog."
        )


def markets_path() -> Path:
    return Path(os.environ.get("MARKETS_PATH", DATA_DIR / "markets.json"))


def seller_replies_path() -> Path:
    return Path(os.environ.get("SELLER_REPLIES_PATH", DATA_DIR / "mock_seller_replies.json"))


def cafes_path() -> Path:
    return Path(os.environ.get("CAFES_PATH", DATA_DIR / "mock_cafes.json"))


def checkpoint_path() -> str:
    return os.environ.get("CHECKPOINT_PATH", str(DATA_DIR / "checkpoints.db"))


def _read_json(path: Path, default):
    try:
        with path.open("r", encoding="utf-8") as handle:
            return json.load(handle)
    except (OSError, ValueError):
        return default


@lru_cache(maxsize=1)
def load_seller_replies() -> dict:
    return _read_json(seller_replies_path(), {"templates": {}, "demo_script_assignment": {}})


@lru_cache(maxsize=1)
def load_cafes() -> list[dict]:
    data = _read_json(cafes_path(), {})
    if isinstance(data, dict):
        return data.get("cafes", [])
    return data


@lru_cache(maxsize=1)
def load_markets() -> dict:
    return _read_json(markets_path(), {"markets": [], "external_markets": []})


def llm_mode() -> str:
    return os.environ.get("LLM_MODE", "off").strip().lower()


def demo_mode() -> bool:
    return os.environ.get("DEMO_MODE", "0").strip().lower() in {"1", "true", "yes"}


def demo_now() -> str | None:
    return os.environ.get("DEMO_NOW") or None
