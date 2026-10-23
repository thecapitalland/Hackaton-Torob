import { describe, expect, it } from "vitest";

import { faFloor, faHours, formatPrice } from "../format";
import type { Followup, Market, Shop, Trip } from "../types";
import { categoryIcon } from "./category";
import { bestConfirmedName, tripPlanningReachable } from "./followups";
import { cheaperAlert, fairnessLabel, medianLine } from "./haggle";
import { isShopInMarket, shopsInMarket } from "./market";
import { filterByRadius, shopLocationLine, toggleCompare } from "./shop";
import { buildTripLine } from "./trip";
import type { Haggle } from "../types";
import { decisionActionName } from "./decision";

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

describe("formatPrice (P2.8)", () => {  it("groups prices with Persian digits and the fa-IR separator", () => {
    expect(formatPrice(3_150_000)).toBe("۳٬۱۵۰٬۰۰۰");
    expect(formatPrice(0)).toBe("۰");
    expect(formatPrice(null)).toBe("");
  });
});

describe("faFloor (QA2)", () => {
  it("renders floor numbers with Persian digits", () => {
    expect(faFloor("2")).toBe("۲");
    expect(faFloor(5)).toBe("۵");
  });

  it("keeps non-numeric floor labels and empty values", () => {
    expect(faFloor("زیرهمکف")).toBe("زیرهمکف");
    expect(faFloor(null)).toBe("");
    expect(faFloor(undefined)).toBe("");
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

  it("prefers the cheapest negotiated confirmed price", () => {
    const followups = [
      makeFollowup({
        shop_id: "countered",
        name: "گران‌تر",
        parsed: { availability: "available", confidence: 0.9, price_toman: 3_300_000 },
      }),
      makeFollowup({
        shop_id: "accepted",
        name: "ارزان‌تر",
        parsed: { availability: "available", confidence: 0.9, price_toman: 2_740_000 },
      }),
    ];
    expect(bestConfirmedName(followups)).toBe("ارزان‌تر");
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

describe("haggle badges and alert (Phase 2)", () => {
  const haggle: Haggle = {
    label: "expensive",
    median: 2_990_000,
    q1: 2_740_000,
    min: 1_390_000,
    n_shops: 27,
    target: 2_740_000,
    ceiling: 2_990_000,
    saving_pct: 28.8,
    leverage: {
      shop_id: "shop_cheap",
      name: "نیکینا رووش",
      price: 2_680_000,
      delta_m: 180,
      distance_m: 320,
      same_mall: true,
      saving: 1_170_000,
    },
    lines: ["خط اول", "خط دوم"],
  };

  it("maps fairness labels to Persian badges", () => {
    expect(fairnessLabel("expensive")).toEqual({ text: "گران", tone: "danger" });
    expect(fairnessLabel("normal")).toEqual({ text: "معمولی", tone: "muted" });
    expect(fairnessLabel("good")).toEqual({ text: "خوب قیمت", tone: "success" });
    expect(fairnessLabel("single")).toEqual({ text: "بدون مقایسه", tone: "neutral" });
  });

  it("formats the median line with Persian digits", () => {
    expect(medianLine(haggle)).toBe("میانه ۲۷ فروشگاه: ۲٬۹۹۰٬۰۰۰");
    expect(medianLine({ ...haggle, label: "single", n_shops: 1 })).toContain(
      "فقط یک فروشگاه",
    );
  });

  it("formats the cheaper-nearby alert with real name, distance and saving", () => {
    const alert = cheaperAlert(haggle);
    expect(alert).toContain("۱۸۰ متر");
    expect(alert).toContain("نیکینا رووش");
    expect(alert).toContain("۱٬۱۷۰٬۰۰۰");
    expect(alert).toContain("قیمت پایین‌تر");
    expect(alert).not.toMatch(/[0-9]/);
  });

  it("returns no alert without a cheaper shop", () => {
    expect(cheaperAlert({ ...haggle, leverage: null })).toBeNull();
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

describe("trip planning reachable (QA3 B2)", () => {
  it("stays reachable when no shop confirms but picks were added", () => {
    expect(tripPlanningReachable(0, 0)).toBe(false);
    expect(tripPlanningReachable(2, 0)).toBe(true);
    expect(tripPlanningReachable(0, 3)).toBe(true);
    expect(tripPlanningReachable(1, 2)).toBe(true);
  });
});

describe("shop location line (QA3 B4)", () => {
  it("joins only the non-empty parts with « · »", () => {
    expect(shopLocationLine("پاساژ علاالدین", "2")).toBe("پاساژ علاالدین · طبقه ۲");
    expect(shopLocationLine(null, "2")).toBe("طبقه ۲");
    expect(shopLocationLine("بورس جمهوری", null)).toBe("بورس جمهوری");
    expect(shopLocationLine("", "")).toBe("");
  });

  it("never renders a dangling separator for a mall-less shop", () => {
    const line = shopLocationLine("", "3");
    expect(line).toBe("طبقه ۳");
    expect(line.startsWith("·") || line.endsWith("·")).toBe(false);
  });
});

describe("radius and compare selection (UX)", () => {
  it("filters by straight-line radius and leaves whole-city results untouched", () => {
    const near = makeShop({ shop_id: "near", lat: 35.696, lon: 51.412 });
    const far = makeShop({ shop_id: "far", lat: 35.8, lon: 51.5 });
    const noPoint = makeShop({ shop_id: "no-point", lat: null, lon: null });
    const origin = { label: "مبدأ", lat: 35.695, lon: 51.4115 };
    expect(filterByRadius([near, far, noPoint], origin, 2).map((shop) => shop.shop_id)).toEqual([
      "near",
    ]);
    expect(filterByRadius([near, far, noPoint], origin, null)).toHaveLength(3);
  });

  it("adds/removes selected products and stops at the maximum", () => {
    expect(toggleCompare([], "a")).toEqual(["a"]);
    expect(toggleCompare(["a", "b"], "a")).toEqual(["b"]);
    expect(toggleCompare(["a", "b", "c", "d"], "e")).toEqual(["a", "b", "c", "d"]);
  });
});

describe("generated decision action union", () => {
  it("maps every discriminated action", () => {
    const actions = [
      "new_search", "refine", "change_radius", "change_location",
      "compare", "haggle", "ooc", "chitchat",
    ] as const;
    for (const action of actions) expect(decisionActionName(action)).toBeTruthy();
  });
});
