"""Simulated seller replies must agree with the shop data."""

from __future__ import annotations

from app.tools import catalog, seller_sim

MEHRISA = "shop_13336f1a0d2ec0b16bbd60aa"  # available + floor "۱"
PRICE = 3_150_000


def test_floor_phrase_matches_the_shop_floor(catalog_path):
    shop = catalog.shop_by_id(MEHRISA)
    detail = seller_sim.seller_reply_detail(MEHRISA, PRICE, 0, floor=shop["floor"])
    assert detail["text"]
    assert "منفی یک" not in detail["text"]
    assert f"طبقه {shop['floor']}" in detail["text"]


def test_floor_phrase_is_removed_when_the_shop_has_no_floor(catalog_path):
    detail = seller_sim.seller_reply_detail(MEHRISA, PRICE, 0, floor=None)
    assert detail["text"]
    assert "طبقه" not in detail["text"]
