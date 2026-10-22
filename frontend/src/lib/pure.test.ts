import { describe, expect, it } from "vitest";

import { faHours, formatPrice } from "../format";
import type { Followup, Market, Shop, Trip } from "../types";
import { categoryIcon } from "./category";
import { bestConfirmedName } from "./followups";
import { isShopInMarket, shopsInMarket } from "./market";
import { buildTripLine } from "./trip";

function makeShop(overrides: Partial<Shop> = {}): Shop {
  return {
    shop_id: "shop_1",
    offer_id: "offer_1",
    name: "فروشگاه نمونه",
    price: 3_150_000,
    lat: 35.695,
    lon: 51.4115,
    open_status: "open",
    open_text: "باز است تا ۲۰:۳۰",
    in_person_providers: [],
    transparency: { score: 3, chips: [] },
    score: 1,
    why: "",
    ...overrides,
  };
}

function makeFollowup(overrides: Partial<Followup> = {}): Followup {
  return {
    shop_id: "shop_1",
    name: "فروشگاه نمونه",
    message: "سلام",
    status: "replied",
    simulated: true,
    delay_ms: 2500,
    parsed: null,
    ...overrides,
  };
}

const MARKET: Market = {
  market_id: "jomhouri_hafez",
  name_fa: "بورس جمهوری–حافظ",
  center: [35.695, 51.4115],
  radius_m: 350,
};

describe("formatPrice (P2.8)", () => {
  it("groups prices with Persian digits and the fa-IR separator", () => {
    expect(formatPrice(3_150_000)).toBe("۳٬۱۵۰٬۰۰۰");
    expect(formatPrice(0)).toBe("۰");
    expect(formatPrice(null)).toBe("");
  });
});

describe("faHours (P2.9)", () => {
  it("translates English hours and uses Persian digits", () => {
    const text = faHours("Sat–Thu 09:00-21:00; Fri ~11:00-16/18 (sources differ)");
    expect(text).toContain("شنبه تا پنجشنبه");
    expect(text).toContain("جمعه");
    expect(text).not.toMatch(/[A-Za-z0-9]/);
  });

  it("leaves an empty value empty", () => {
    expect(faHours(undefined)).toBe("");
  });
});

describe("categoryIcon (P2.10)", () => {
  it("picks the pill icon from the category", () => {
    expect(categoryIcon("گوشی موبایل")).toBe("📱");
    expect(categoryIcon("لپ تاپ و نوت بوک")).toBe("💻");
    expect(categoryIcon("هدفون، هدست و هندزفری")).toBe("🎧");
    expect(categoryIcon("لوستر و چراغ تزئینی")).toBe("🛍️");
    expect(categoryIcon(null)).toBe("🛍️");
  });
});

describe("bestConfirmedName (P1.5)", () => {
  it("returns the first shop that confirmed availability", () => {
    const followups = [
      makeFollowup({
        shop_id: "a",
        name: "اولی",
        parsed: { availability: "unclear", confidence: 0.4 },
      }),
      makeFollowup({
        shop_id: "b",
        name: "مهریسا نوین",
        parsed: { availability: "available", confidence: 0.9 },
      }),
      makeFollowup({
        shop_id: "c",
        name: "سومی",
        parsed: { availability: "available", confidence: 0.9 },
      }),
    ];
    expect(bestConfirmedName(followups)).toBe("مهریسا نوین");
  });

  it("returns null when nobody confirmed", () => {
    expect(bestConfirmedName([makeFollowup()])).toBeNull();
  });
});

describe("market filtering (P1.6)", () => {
  it("keeps shops inside the market radius", () => {
    expect(isShopInMarket(makeShop(), MARKET)).toBe(true);
    expect(isShopInMarket(makeShop({ lat: 35.75, lon: 51.45 }), MARKET)).toBe(false);
  });

  it("rejects shops without coordinates", () => {
    expect(isShopInMarket(makeShop({ lat: null, lon: null }), MARKET)).toBe(false);
  });

  it("filters the list only when a market is active", () => {
    const inside = makeShop({ shop_id: "inside" });
    const outside = makeShop({ shop_id: "outside", lat: 35.75, lon: 51.45 });
    expect(shopsInMarket([inside, outside], MARKET).map((shop) => shop.shop_id)).toEqual([
      "inside",
    ]);
    expect(shopsInMarket([inside, outside], null)).toHaveLength(2);
  });
});

describe("trip fallback line (P1.7)", () => {
  const trip: Trip = {
    summary: "برنامه",
    checklist: [],
    links: {},
    stops: [
      { order: 1, shop_id: "s1", name: "مغازه", lat: 35.696, lon: 51.412, verified: true },
      { order: 2, shop_id: "s2", name: "مغازه دوم", lat: 35.697, lon: 51.413, verified: false },
    ],
    start: { label: "شروع", lat: 35.695, lon: 51.411 },
    cafe: { id: "c1", name: "کافه", lat: 35.698, lon: 51.414 },
  };

  it("draws start -> shop -> cafe when there is no polyline", () => {
    expect(buildTripLine(trip)).toEqual([
      [35.695, 51.411],
      [35.696, 51.412],
      [35.697, 51.413],
      [35.698, 51.414],
    ]);
  });

  it("skips missing coordinates", () => {
    const sparse: Trip = {
      ...trip,
      start: { label: "بدون موقعیت" },
      stops: [{ order: 1, shop_id: "s1", name: "مغازه", lat: null, lon: null, verified: false }],
    };
    expect(buildTripLine(sparse)).toEqual([[35.698, 51.414]]);
  });
});
