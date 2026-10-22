"""Static data loading (mock seller replies, mock cafes, markets) and path helpers."""

from __future__ import annotations

import json
import os
from functools import lru_cache
from pathlib import Path

APP_DIR = Path(__file__).resolve().parent
BACKEND_DIR = APP_DIR.parent
PROJECT_ROOT = BACKEND_DIR.parent

DATA_DIR = Path(os.environ.get("DATA_DIR", PROJECT_ROOT / "data"))


def catalog_path() -> Path:
    return Path(os.environ.get("CATALOG_PATH", DATA_DIR / "catalog.db"))


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
