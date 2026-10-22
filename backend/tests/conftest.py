"""Shared pytest fixtures."""

from __future__ import annotations

import os
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

os.environ.setdefault("LLM_MODE", "off")
os.environ.setdefault("DEMO_MODE", "1")
os.environ.setdefault("DEMO_NOW", "2026-10-22T15:00:00+03:30")
os.environ.setdefault("CATALOG_PATH", str(ROOT.parent / "data" / "catalog.db"))
os.environ.setdefault("MARKETS_PATH", str(ROOT.parent / "data" / "markets.json"))
os.environ.setdefault("SELLER_REPLIES_PATH", str(ROOT.parent / "data" / "mock_seller_replies.json"))
os.environ.setdefault("CAFES_PATH", str(ROOT.parent / "data" / "mock_cafes.json"))

try:  # the windows console defaults to cp1256 which can not print Persian
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:  # pragma: no cover
    pass


@pytest.fixture(scope="session")
def catalog_path() -> Path:
    path = Path(os.environ["CATALOG_PATH"])
    if not path.exists():
        pytest.skip(f"catalog.db is missing at {path}")
    return path


@pytest.fixture(scope="session")
def demo_now():
    from app.tools.hours import now_tehran

    return now_tehran()
