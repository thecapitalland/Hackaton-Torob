"""Data-backed haggling: statistics, thresholds, leverage and seller counters."""

from __future__ import annotations

import re

from app import graph, rules
from app.tools import catalog, haggle, seller_sim

R50I = "product_92ac53fa75e18e8e73f20b56"
MEHRISA = "shop_13336f1a0d2ec0b16bbd60aa"  # hash bucket -> accepted
AVAN = "shop_60e835a590a4a652ce0ad6d9"  # hash bucket -> countered
CHEAP = "shop_e5d5df8f0e8cc8d8da0d67d3"


def _option(**overrides) -> dict:
    base = {
        "shop_id": "shop_target",
        "name": "فروشگاه هدف",
        "price": 3_000_000,
        "mall": None,
        "lat": 35.695,
        "lon": 51.4115,
        "distance_m": 400,
    }
    base.update(overrides)
    return base


def _stats(**overrides) -> dict:
    base = {
        "median": 3_000_000,
        "q1": 2_500_000,
        "min": 1_900_000,
        "max": 3_600_000,
        "n_shops": 5,
    }
    base.update(overrides)
    return base


# --------------------------------------------------------------------------
# price_stats
# --------------------------------------------------------------------------


def test_price_stats_dedupes_shops_and_ignores_zero_prices():
    offers = [
        {"shop_id": "a", "price_toman": 1_000_000},
        {"shop_id": "a", "price_toman": 900_000},  # cheaper duplicate wins
        {"shop_id": "b", "price_toman": 2_000_000},
        {"shop_id": "c", "price_toman": 3_000_000},
        {"shop_id": "d", "price_toman": 4_000_000},
        {"shop_id": "e", "price_toman": 0},
        {"shop_id": "f", "price_toman": None},
    ]
    stats = haggle.price_stats(offers)
    assert stats["n_shops"] == 4
    assert stats["min"] == 900_000
    assert stats["max"] == 4_000_000
    assert stats["median"] == 2_500_000
    # inclusive quartile of [0.9, 2, 3, 4] is 1.725M -> rounded toman
    assert stats["q1"] == 1_725_000


def test_price_stats_handles_a_single_offer_and_empty_input():
    single = haggle.price_stats([{"shop_id": "a", "price_toman": 3_150_000}])
    assert single == {
        "median": 3_150_000,
        "q1": 3_150_000,
        "min": 3_150_000,
        "max": 3_150_000,
        "n_shops": 1,
    }
    assert haggle.price_stats([])["n_shops"] == 0


# --------------------------------------------------------------------------
# fairness thresholds
# --------------------------------------------------------------------------


def test_fairness_single_offer_has_no_comparison():
    assert haggle.fairness(3_000_000, _stats(n_shops=1)) == "single"


def test_fairness_thresholds_are_inclusive_at_the_boundaries():
    stats = _stats(median=3_000_000, q1=2_500_000)
    assert haggle.fairness(3_300_000, stats) == "normal"  # exactly median + 10%
    assert haggle.fairness(3_300_001, stats) == "expensive"
    assert haggle.fairness(2_500_000, stats) == "good"  # exactly Q1
    assert haggle.fairness(2_500_001, stats) == "normal"
    assert haggle.fairness(1_900_000, stats) == "good"


# --------------------------------------------------------------------------
# target / ceiling
# --------------------------------------------------------------------------


def test_target_is_q1_rounded_to_10k_and_clamped_to_min_and_price():
    info = haggle.target_price(_stats(q1=2_744_999, median=2_990_000), 3_850_000)
    assert info["target"] == 2_740_000
    assert info["ceiling"] == 2_990_000
    assert info["target"] <= 3_850_000
    assert info["target"] >= 1_900_000

    below_min = haggle.target_price(_stats(q1=500_000, min=1_500_000), 2_000_000)
    assert below_min["target"] == 1_500_000

    above_price = haggle.target_price(_stats(q1=3_500_000), 3_100_000)
    assert above_price["target"] == 3_100_000


def test_single_offer_target_is_the_offer_itself():
    info = haggle.target_price(_stats(median=3_000_000, q1=3_000_000, n_shops=1), 3_000_000)
    assert info == {"target": 3_000_000, "ceiling": 3_000_000, "saving_pct": 0}


def test_ceiling_follows_the_median_not_the_offer():
    info = haggle.target_price(_stats(median=2_996_000, q1=2_500_000), 2_700_000)
    assert info["ceiling"] == 3_000_000
    assert info["target"] == 2_500_000


# --------------------------------------------------------------------------
# leverage
# --------------------------------------------------------------------------


def test_leverage_prefers_the_same_mall_even_over_a_cheaper_shop_elsewhere():
    option = _option(price=3_000_000, mall="پاساژ علاالدین")
    same_mall = _option(
        shop_id="same",
        name="همان پاساژ",
        price=2_900_000,
        mall="پاساژ علاالدین",
        lat=35.6952,
        lon=51.4117,
        distance_m=80,
    )
    other = _option(
        shop_id="far",
        name="جای دیگر",
        price=2_000_000,
        mall=None,
        lat=35.75,
        lon=51.45,
        distance_m=100,
    )
    result = haggle.leverage_shop(option, [option, same_mall, other])
    assert result is not None
    assert result["shop_id"] == "same"
    assert result["same_mall"] is True
    assert result["saving"] == 100_000


def test_leverage_uses_distance_to_break_a_price_tie():
    option = _option(price=3_000_000, mall=None)
    near = _option(shop_id="near", name="نزدیک", price=2_500_000, lat=35.696, lon=51.412, distance_m=100)
    far = _option(shop_id="far", name="دور", price=2_500_000, lat=35.75, lon=51.45, distance_m=5000)
    near["delta_m"] = 100
    result = haggle.leverage_shop(option, [option, far, near])
    assert result is not None
    assert result["shop_id"] == "near"
    assert result["delta_m"] is not None


def test_leverage_returns_none_when_no_shop_is_cheaper():
    option = _option(price=2_000_000)
    other = _option(shop_id="higher", price=2_100_000)
    assert haggle.leverage_shop(option, [option, other]) is None


# --------------------------------------------------------------------------
# deterministic lines and LLM guard
# --------------------------------------------------------------------------


def test_template_lines_cite_the_real_shop_price_and_distance():
    option = _option(price=3_000_000)
    leverage = {
        "shop_id": "cheap",
        "name": "فروشگاه ارزان",
        "price": 2_500_000,
        "distance_m": 300,
        "delta_m": 180,
        "same_mall": False,
        "saving": 500_000,
    }
    lines = haggle.haggle_lines(option, _stats(), leverage, llm_on=False)
    assert 2 <= len(lines) <= 3
    text = " ".join(lines)
    assert leverage["name"] in text
    assert rules.price_fa(leverage["price"]) in text
    assert rules.distance_fa(leverage["delta_m"]) in text
    assert not re.search(r"[0-9]", text)


def test_invented_llm_number_is_rejected_and_rules_template_wins():
    option = _option(price=3_000_000)
    leverage = {
        "shop_id": "cheap",
        "name": "فروشگاه ارزان",
        "price": 2_500_000,
        "distance_m": 300,
        "delta_m": 180,
        "same_mall": False,
        "saving": 500_000,
    }

    def invented(_payload):
        return [
            "فروشگاه ارزان ۱٬۲۳۴٬۵۶۷ می‌ده، ۱۸۰ متر اون‌طرف‌تر.",
            "با ۲٬۵۰۰٬۰۰۰ حضوری می‌دید؟",
        ]

    lines = haggle.haggle_lines(
        option, _stats(), leverage, llm_on=True, llm_fn=invented
    )
    assert rules.price_fa(2_500_000) in " ".join(lines)
    assert "۱٬۲۳۴٬۵۶۷" not in " ".join(lines)


def test_valid_llm_lines_are_kept():
    option = _option(price=3_000_000)
    leverage = {
        "shop_id": "cheap",
        "name": "فروشگاه ارزان",
        "price": 2_500_000,
        "distance_m": 300,
        "delta_m": 180,
        "same_mall": False,
        "saving": 500_000,
    }
    template = rules.haggle_lines(option, _stats(), leverage, 2_500_000, 3_000_000)
    lines = haggle.haggle_lines(
        option, _stats(), leverage, llm_on=True, llm_fn=lambda _payload: template
    )
    assert lines == template


def test_llm_may_cite_the_computed_saving_percentage():
    option = _option(price=3_000_000)
    leverage = {
        "shop_id": "cheap",
        "name": "فروشگاه ارزان",
        "price": 2_500_000,
        "distance_m": 300,
        "delta_m": 180,
        "same_mall": False,
        "saving": 500_000,
    }
    candidate = [
        f"همین مدل رو «{leverage['name']}» {rules.price_fa(leverage['price'])} می‌ده، "
        f"{rules.distance_fa(leverage['delta_m'])} اون‌طرف‌تر.",
        f"با {rules.price_fa(2_500_000)} حضوری می‌دید؟ صرفه‌جویی ۱۷٪.",
    ]
    lines = haggle.haggle_lines(
        option, _stats(), leverage, llm_on=True, llm_fn=lambda _payload: candidate
    )
    assert lines == candidate


# --------------------------------------------------------------------------
# seller simulation + parsing
# --------------------------------------------------------------------------


def test_demo_shops_accept_or_counter_the_target_deterministically():
    first = seller_sim.seller_reply_detail(
        MEHRISA, 3_150_000, 0, floor="۱", target_price=2_740_000
    )
    second = seller_sim.seller_reply_detail(
        MEHRISA, 3_150_000, 0, floor="۱", target_price=2_740_000
    )
    assert first == second
    assert first["offer_status"] == "accepted"
    assert first["counter_price"] is None
    assert "۲ میلیون و ۷۴۰" in first["text"]

    counter = seller_sim.seller_reply_detail(
        AVAN, 3_850_000, 0, floor="۲", target_price=2_740_000
    )
    assert counter["offer_status"] == "countered"
    assert 2_740_000 <= counter["counter_price"] <= 3_850_000
    assert counter["counter_price"] % 50_000 == 0
    assert "آخرین قیمت" in counter["text"]


def test_counter_reply_parses_to_the_counter_price_not_the_target():
    counter = seller_sim.seller_reply_detail(
        AVAN, 3_850_000, 0, floor="۲", target_price=2_740_000
    )
    parsed = rules.parse_reply(counter["text"], 3_850_000)
    assert parsed["availability"] == "available"
    assert parsed["offer_status"] == "countered"
    assert parsed["price_toman"] == counter["counter_price"]
    assert parsed["counter_price"] == counter["counter_price"]


def test_accepted_reply_parses_to_the_target_price():
    accepted = seller_sim.seller_reply_detail(
        MEHRISA, 3_150_000, 0, floor="۱", target_price=2_740_000
    )
    parsed = rules.parse_reply(accepted["text"], 3_150_000)
    assert parsed["offer_status"] == "accepted"
    assert parsed["price_toman"] == 2_740_000


def test_no_target_keeps_the_old_scripted_available_reply():
    detail = seller_sim.seller_reply_detail(MEHRISA, 3_150_000, 0, floor="۱")
    assert detail["offer_status"] == "none"
    assert detail["counter_price"] is None
    assert "قیمت امروز" in detail["text"]


# --------------------------------------------------------------------------
# graph wiring
# --------------------------------------------------------------------------


def test_find_stores_attaches_haggle_to_every_option_with_llm_off(catalog_path):
    state = graph.find_stores({"product_id": R50I, "slots": {}})
    shops = state["shops"]
    assert len(shops) == 27
    for shop in shops:
        analysis = shop["haggle"]
        assert analysis["n_shops"] == 27
        assert analysis["label"] in {"expensive", "normal", "good", "single"}
        assert analysis["min"] <= analysis["target"] <= shop["price"]
        assert analysis["ceiling"] >= analysis["target"]
        assert 2 <= len(analysis["lines"]) <= 3
        assert not re.search(r"[0-9]", " ".join(analysis["lines"]))

    labels = {shop["haggle"]["label"] for shop in shops}
    assert {"expensive", "good"} <= labels
    expensive = next(shop for shop in shops if shop["haggle"]["label"] == "expensive")
    assert expensive["haggle"]["leverage"] is not None


def test_plan_contact_asks_the_computed_target_price(catalog_path):
    state = graph.find_stores(
        {"product_id": R50I, "slots": {"installment": False, "today": True}}
    )
    state["shop_ids"] = [MEHRISA, AVAN, CHEAP]
    plan = graph.plan_contact(state)
    message = plan["draft_message"]
    assert "با ۲٬۷۴۰٬۰۰۰ حضوری می‌دید؟" in message
    assert all(target["target_price"] for target in plan["draft_targets"])
