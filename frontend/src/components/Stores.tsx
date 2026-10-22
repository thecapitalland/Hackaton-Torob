import { useMemo, useState } from "react";
import { motion } from "framer-motion";
import { copy } from "../copy.fa";
import { faDigits, formatDistance, formatPrice } from "../format";
import type { Shop } from "../types";
import { Chip, Sheet } from "./ui";
import { MapView } from "./MapView";
import { DirectionsLinks } from "./DirectionsLinks";
import { useBreakpoint } from "../hooks";
import type { Market, RouteInfo, SlotLocation } from "../types";

export type SortKey = "recommended" | "cheapest" | "nearest" | "open";

const SORTS: { key: SortKey; label: string }[] = [
  { key: "recommended", label: copy.stores.sortRecommended },
  { key: "cheapest", label: copy.stores.sortCheapest },
  { key: "nearest", label: copy.stores.sortNearest },
  { key: "open", label: copy.stores.sortOpen },
];

function OpenBadge({ shop }: { shop: Shop }) {
  if (shop.open_status === "open") {
    return (
      <span className="rounded-full bg-brand-green/10 px-2 py-0.5 text-[11px] font-bold text-brand-green">
        ● {shop.open_text}
      </span>
    );
  }
  if (shop.open_status === "closed") {
    return (
      <span className="rounded-full bg-brand-red/10 px-2 py-0.5 text-[11px] font-bold text-brand-red">
        ● {copy.stores.closed}
      </span>
    );
  }
  return (
    <span className="rounded-full bg-brand-gray/15 px-2 py-0.5 text-[11px] font-medium text-brand-gray">
      ● {copy.stores.unknown}
    </span>
  );
}

function TransparencyDots({ score }: { score: number }) {
  return (
    <span className="inline-flex items-center gap-0.5" aria-label={`شفافیت ${score} از ۵`}>
      {[0, 1, 2, 3, 4].map((index) => (
        <span
          key={index}
          className={`h-1.5 w-1.5 rounded-full ${
            index < score ? "bg-brand-green" : "bg-brand-border"
          }`}
        />
      ))}
    </span>
  );
}

export function StoreCard({
  shop,
  cheapest,
  selected,
  route,
  onToggle,
  onOpenTransparency,
}: {
  shop: Shop;
  cheapest: boolean;
  selected: boolean;
  route?: RouteInfo | null;
  onToggle: () => void;
  onOpenTransparency: () => void;
}) {
  return (
    <motion.div
      layout
      className={`rounded-card border bg-white p-3 shadow-card ${
        selected ? "border-brand-red" : "border-brand-border"
      }`}
    >
      <div className="flex items-start gap-2">
        <button
          onClick={onToggle}
          aria-label="انتخاب فروشگاه"
          className={`mt-0.5 flex h-6 w-6 shrink-0 items-center justify-center rounded-md border ${
            selected ? "border-brand-red bg-brand-red text-white" : "border-brand-border"
          }`}
        >
          {selected ? "✓" : ""}
        </button>
        <div className="min-w-0 flex-1">
          <div className="flex items-center justify-between gap-2">
            <h4 className="truncate text-[14px] font-bold">{shop.name}</h4>
            <div className="shrink-0 text-left">
              <p className="text-[13.5px] font-bold text-brand-red">
                {formatPrice(shop.price)} تومان
              </p>
              {cheapest ? (
                <p className="text-[10.5px] font-bold text-brand-green">{copy.stores.cheapest}</p>
              ) : null}
            </div>
          </div>

          <div className="mt-1.5 flex flex-wrap items-center gap-1.5">
            <OpenBadge shop={shop} />
            {route ? (
              <span className="text-[11px] text-brand-muted">
                📍 {formatDistance(route.distance_m)} · {faDigits(route.duration_min)}{" "}
                {copy.stores.walkTime}
                {route.estimated ? ` (${copy.stores.estimateDistance})` : ` (${copy.stores.realRoute})`}
              </span>
            ) : shop.distance_m !== null && shop.distance_m !== undefined ? (
              <span className="text-[11px] text-brand-muted">
                📍 {formatDistance(shop.distance_m)} ({copy.stores.estimateDistance})
              </span>
            ) : null}
            {shop.mall || shop.floor ? (
              <span className="text-[11px] text-brand-muted">
                🏬 {shop.mall ?? ""}
                {shop.floor ? ` · طبقه ${shop.floor}` : ""}
              </span>
            ) : null}
          </div>

          {shop.in_person_providers?.length ? (
            <div className="mt-1.5 flex flex-wrap gap-1">
              {shop.in_person_providers.slice(0, 4).map((provider) => (
                <span
                  key={provider}
                  className="rounded-full bg-brand-bg px-2 py-0.5 text-[10.5px] text-brand-muted"
                >
                  💳 {provider}
                </span>
              ))}
            </div>
          ) : null}

          <div className="mt-2 flex items-center justify-between">
            <button
              onClick={onOpenTransparency}
              className="flex items-center gap-1.5 text-[11.5px] text-brand-muted"
            >
              <TransparencyDots score={shop.transparency?.score ?? 0} />
              {copy.stores.transparency} {faDigits(shop.transparency?.score ?? 0)} از ۵
            </button>
            {shop.why ? (
              <span className="text-[11px] text-brand-gray">⚖️ {shop.why}</span>
            ) : null}
          </div>

          <div className="mt-2 border-t border-dashed border-brand-border pt-2">
            <DirectionsLinks lat={shop.lat} lon={shop.lon} />
          </div>
        </div>
      </div>
    </motion.div>
  );
}

export function StoresSection({
  shops,
  market,
  marketFilter,
  onClearMarketFilter,
  userLocation,
  selected,
  routes,
  onToggle,
  onAsk,
  onSort,
  sort,
}: {
  shops: Shop[];
  market?: Market | null;
  marketFilter?: Market | null;
  onClearMarketFilter?: () => void;
  userLocation?: SlotLocation | null;
  selected: string[];
  routes?: Record<string, RouteInfo>;
  onToggle: (shopId: string) => void;
  onAsk: () => void;
  onSort: (sort: SortKey) => void;
  sort: SortKey;
}) {
  const [tab, setTab] = useState<"list" | "map">("list");
  const [onlyOpen, setOnlyOpen] = useState(false);
  const [onlyInPerson, setOnlyInPerson] = useState(false);
  const [transparencyShop, setTransparencyShop] = useState<Shop | null>(null);
  const [mapSheetOpen, setMapSheetOpen] = useState(false);
  const { isMobile, isWide } = useBreakpoint();

  const filtered = useMemo(() => {
    let list = shops;
    if (onlyOpen) list = list.filter((shop) => shop.open_status === "open");
    if (onlyInPerson)
      list = list.filter((shop) => (shop.in_person_providers?.length ?? 0) > 0);
    return list;
  }, [shops, onlyOpen, onlyInPerson]);

  const cheapestId = useMemo(() => {
    if (!filtered.length) return null;
    return filtered.reduce((best, shop) => (shop.price < best.price ? shop : best)).shop_id;
  }, [filtered]);

  const center = useMemo(() => {
    const points = filtered.filter((shop) => shop.lat !== null && shop.lon !== null);
    if (!points.length) return null;
    return [
      points.reduce((sum, shop) => sum + (shop.lat ?? 0), 0) / points.length,
      points.reduce((sum, shop) => sum + (shop.lon ?? 0), 0) / points.length,
    ] as [number, number];
  }, [filtered]);

  return (
    <section className="space-y-3">
      <div className="flex items-center justify-between px-1">
        <h2 className="text-[16px] font-bold">{copy.stores.title}</h2>
        {/* list/map toggle is unnecessary from 1280px up: the side pane is always visible.
            It stays visible below 768px too: there it opens the map bottom sheet. */}
        <div className="flex rounded-full border border-brand-border bg-white p-1 xl:hidden">
          {(["list", "map"] as const).map((key) => (
            <button
              key={key}
              onClick={() => {
                if (key === "map" && isMobile) {
                  setMapSheetOpen(true);
                  return;
                }
                // on very wide screens the big left pane already shows the map
                if (key === "map" && isWide) return;
                setTab(key);
              }}
              className={`rounded-full px-4 py-1.5 text-[12.5px] font-medium ${
                tab === key ? "bg-brand-red text-white" : "text-brand-muted"
              }`}
            >
              {key === "list" ? copy.stores.list : copy.stores.map}
            </button>
          ))}
        </div>
      </div>

      <div className="no-scrollbar flex gap-2 overflow-x-auto px-1">
        {marketFilter ? (
          <Chip size="sm" tone="success" onClick={onClearMarketFilter}>
            🏬 فقط {marketFilter.name_fa} ✕
          </Chip>
        ) : null}
        {SORTS.map((item) => (
          <Chip key={item.key} active={sort === item.key} onClick={() => onSort(item.key)} size="sm">
            {item.label}
          </Chip>
        ))}
        <span className="w-px shrink-0 bg-brand-border" />
        <Chip
          size="sm"
          active={onlyInPerson}
          tone={onlyInPerson ? "success" : "default"}
          onClick={() => setOnlyInPerson((value) => !value)}
        >
          {copy.stores.filterInPerson}
        </Chip>
        <Chip
          size="sm"
          active={onlyOpen}
          tone={onlyOpen ? "success" : "default"}
          onClick={() => setOnlyOpen((value) => !value)}
        >
          {copy.stores.filterOpen}
        </Chip>
      </div>

      {tab === "list" ? (
        filtered.length ? (
          <div className="space-y-2">
            {filtered.map((shop) => (
              <StoreCard
                key={shop.shop_id}
                shop={shop}
                cheapest={shop.shop_id === cheapestId}
                selected={selected.includes(shop.shop_id)}
                route={routes?.[shop.shop_id] ?? null}
                onToggle={() => onToggle(shop.shop_id)}
                onOpenTransparency={() => setTransparencyShop(shop)}
              />
            ))}
          </div>
        ) : (
          <p className="rounded-card border border-brand-border bg-white p-4 text-[13px] text-brand-muted">
            {marketFilter ? copy.stores.emptyInMarket : copy.stores.empty}
          </p>
        )
      ) : (
        /* 768px+: the map is a collapsible panel inside the page.
           At >=1280px the big left pane already shows it - avoid a duplicate. */
        <div className="hidden md:block xl:hidden">
          <MapView
            shops={filtered}
            market={market}
            userLocation={userLocation}
            center={center}
            className="h-[380px]"
          />
          <p className="mt-1.5 text-[11px] text-brand-gray">
            🟢 باز · ⚪️ ساعت اعلام نشده · 🔴 بسته · 🏬 بورس کالا
          </p>
        </div>
      )}

      {/* below 768px the map opens as a bottom sheet */}
      <Sheet open={mapSheetOpen} onClose={() => setMapSheetOpen(false)} title={copy.stores.map}>
        <MapView
          shops={filtered}
          market={market}
          userLocation={userLocation}
          center={center}
          className="h-[60vh]"
        />
        <p className="mt-2 text-[11px] text-brand-gray">
          🟢 باز · ⚪️ ساعت اعلام نشده · 🔴 بسته · 🏬 بورس کالا
        </p>
      </Sheet>

      <Sheet
        open={Boolean(transparencyShop)}
        onClose={() => setTransparencyShop(null)}
        title={`${copy.stores.transparency} ${faDigits(transparencyShop?.transparency?.score ?? 0)} از ۵`}
      >
        {transparencyShop ? (
          <div className="space-y-3">
            <div className="flex items-center gap-2">
              <TransparencyDots score={transparencyShop.transparency?.score ?? 0} />
              <span className="text-[13px] font-bold">{transparencyShop.name}</span>
            </div>
            <ul className="space-y-1.5 text-[13px] text-brand-muted">
              {(transparencyShop.transparency?.chips ?? []).map((chip) => (
                <li key={chip}>✓ {chip}</li>
              ))}
              {!(transparencyShop.transparency?.chips ?? []).length ? (
                <li>✗ هیچ سیگنالی ثبت نشده</li>
              ) : null}
            </ul>
            {transparencyShop.price_age_days !== null &&
            transparencyShop.price_age_days !== undefined ? (
              <p className="text-[12px] text-brand-gray">
                به‌روزرسانی قیمت: {faDigits(transparencyShop.price_age_days)} روز پیش (مربوط به قیمت،
                نه موجودی)
              </p>
            ) : null}
            <p className="rounded-xl bg-brand-bg p-2.5 text-[11.5px] text-brand-muted">
              {transparencyShop.transparency?.disclaimer ??
                "این امتیاز اعتبار فروشنده نیست؛ کامل‌بودن اطلاعات است"}
            </p>
          </div>
        ) : null}
      </Sheet>

      {selected.length ? (
        <div className="sticky bottom-20 z-20">
          <button
            onClick={onAsk}
            className="w-full rounded-2xl bg-brand-red py-3.5 text-[14px] font-bold text-white shadow-card"
          >
            📨 {copy.stores.askShops} {faDigits(selected.length)} {copy.stores.shopsAsk}
          </button>
        </div>
      ) : null}
    </section>
  );
}
