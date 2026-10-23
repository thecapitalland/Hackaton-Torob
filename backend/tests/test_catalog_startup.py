"""Catalog startup must rebuild when possible or fail loudly when unavailable."""

from __future__ import annotations

import sqlite3

import pytest

from app import data_static


def _write_valid_catalog(path):
    path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(path)
    try:
        conn.executescript(
            """
            CREATE TABLE products (product_id TEXT);
            CREATE TABLE offers (offer_id TEXT);
            CREATE TABLE shops (shop_id TEXT);
            CREATE TABLE categories (name TEXT);
            INSERT INTO products VALUES ('p1');
            INSERT INTO offers VALUES ('o1');
            INSERT INTO shops VALUES ('s1');
            INSERT INTO categories VALUES ('sample');
            """
        )
    finally:
        conn.close()


def test_missing_or_zero_catalog_fails_with_actionable_message(monkeypatch, tmp_path):
    catalog_file = tmp_path / "data" / "catalog.db"
    catalog_file.parent.mkdir(parents=True)
    catalog_file.write_bytes(b"")
    monkeypatch.setenv("CATALOG_PATH", str(catalog_file))
    monkeypatch.delenv("TOROB_DATASET_DIR", raising=False)
    monkeypatch.setattr(data_static, "_raw_dataset_dir", lambda: None)

    with pytest.raises(RuntimeError, match="git lfs pull"):
        data_static.ensure_catalog()


def test_invalid_catalog_is_rebuilt_from_configured_csv_directory(monkeypatch, tmp_path):
    catalog_file = tmp_path / "data" / "catalog.db"
    catalog_file.parent.mkdir(parents=True)
    catalog_file.write_bytes(b"")
    raw_dir = tmp_path / "torob-dataset"
    raw_dir.mkdir()
    for name in ("shops.csv", "products.csv", "offers.csv"):
        (raw_dir / name).write_text("placeholder", encoding="utf-8")
    monkeypatch.setenv("CATALOG_PATH", str(catalog_file))
    monkeypatch.setenv("TOROB_DATASET_DIR", str(raw_dir))

    def fake_build(command, **_kwargs):
        output = command[command.index("--out") + 1]
        _write_valid_catalog(__import__("pathlib").Path(output))

    monkeypatch.setattr(data_static.subprocess, "run", fake_build)
    result = data_static.ensure_catalog()
    assert result == catalog_file.resolve()
    assert result.stat().st_size > 0
    assert data_static._catalog_is_usable(result)
