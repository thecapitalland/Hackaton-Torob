import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { AnimatePresence, motion } from "framer-motion";
import { ApiError, api } from "./api";
import { copy } from "./copy.fa";
import { faDigits, formatPrice } from "./format";
import { shopsInMarket } from "./lib/market";
import type {
  ApiResponse,
  Compare,
  Followup,
  Market,
  Message,
  MoreItem,
  Ooc,
  Pending,
  Product,
  ProductCard,
  RouteInfo,
  Shop,
  SlotLocation,
  TraceEntry,
  Trip,
} from "./types";
import { SlotPills, TypingIndicator } from "./components/Chat";
import { ProductCards } from "./components/ProductCards";
import { MarketCard } from "./components/MarketCard";
import { OutOfCatalogCard } from "./components/OutOfCatalogCard";
import { CompareCard } from "./components/CompareCard";
import { StoresSection, type SortKey } from "./components/Stores";
import { PermissionSheet } from "./components/PermissionSheet";
import { Inbox } from "./components/Inbox";
import { TripPlan } from "./components/TripPlan";
import { TraceDrawer } from "./components/TraceDrawer";
import { Chip } from "./components/ui";
import { MapView } from "./components/MapView";

const NEIGHBORHOODS: Record<string, SlotLocation> = {
  فردوسی: { label: "میدان فردوسی", lat: 35.701, lon: 51.4187 },
  جمهوری: { label: "خیابان جمهوری", lat: 35.6925, lon: 51.4105 },
  ولیعصر: { label: "خیابان ولیعصر", lat: 35.7, lon: 51.406 },
  تجریش: { label: "تجریش", lat: 35.804, lon: 51.433 },
};

export default function App() {
  const [sessionId, setSessionId] = useState<string | null>(null);
  const [messages, setMessages] = useState<Message[]>([]);
  const [pending, setPending] = useState<Pending>(null);
  const [trace, setTrace] = useState<TraceEntry[]>([]);
  const [slots, setSlots] = useState<ApiResponse["slots"]>({});
  const [cards, setCards] = useState<ProductCard[]>([]);
  const [more, setMore] = useState<MoreItem[]>([]);
  const [market, setMarket] = useState<Market | null>(null);
  const [marketFilter, setMarketFilter] = useState<Market | null>(null);
  const [ooc, setOoc] = useState<Ooc | null>(null);
  const [compare, setCompare] = useState<Compare | null>(null);
  const [product, setProduct] = useState<Product | null>(null);
  const [shops, setShops] = useState<Shop[]>([]);
  const [followups, setFollowups] = useState<Followup[]>([]);
  const [trip, setTrip] = useState<Trip | null>(null);
  const [selectedShops, setSelectedShops] = useState<string[]>([]);
  const [tripPicks, setTripPicks] = useState<string[]>([]);
  const [sort, setSort] = useState<SortKey>("recommended");
  const [input, setInput] = useState("");
  const [busy, setBusy] = useState(false);
  const [started, setStarted] = useState(false);
  const [traceOpen, setTraceOpen] = useState(false);
  const [toast, setToast] = useState<string | null>(null);
  const [location, setLocation] = useState<SlotLocation | null>(null);
  const [routes, setRoutes] = useState<Record<string, RouteInfo>>({});
  const [tripRoute, setTripRoute] = useState<RouteInfo | null>(null);
  const routesKeyRef = useRef<string | null>(null);
  const tripRouteKeyRef = useRef<string | null>(null);
  const bottomRef = useRef<HTMLDivElement | null>(null);

  // ------------------------------------------------------------- session
  useEffect(() => {
    api
      .createSession()
      .then((data) => setSessionId(data.session_id))
      .catch(() => setToast(copy.chat.error));
  }, []);

  useEffect(() => {
    if (toast) {
      const timer = window.setTimeout(() => setToast(null), 3200);
      return () => window.clearTimeout(timer);
    }
  }, [toast]);

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: "smooth", block: "end" });
  }, [messages.length, cards.length, shops.length, followups.length, trip, ooc, compare]);

  const applyResponse = useCallback((response: ApiResponse) => {
    if (response.messages?.length) {
      setMessages((prev) => [...prev, ...response.messages]);
    }
    if (response.trace?.length) {
      setTrace((prev) => [...prev, ...response.trace]);
    }
    if (response.slots) setSlots(response.slots);
    setPending(response.pending ?? null);
    if (response.cards) setCards(response.cards);
    if (response.more) setMore(response.more);
    if (response.specialty_market !== undefined) setMarket(response.specialty_market ?? null);
    if (response.ooc) setOoc(response.ooc);
    if (response.mode === "out_of_catalog") {
      setCards([]);
      setMore([]);
    }
    if (response.phase === "compare") {
      setCompare(response.compare ?? null);
      // a comparison turn must not show a stale product feed or market banner
      setCards([]);
      setMore([]);
      setMarket(null);
    } else if (response.phase) {
      setCompare(null);
    }
    if (response.product !== undefined) setProduct(response.product ?? null);
    if (response.shops) setShops(response.shops);
    if (response.followups) setFollowups(response.followups);
    if (response.trip !== undefined) setTrip(response.trip ?? null);
  }, []);

  const handleError = useCallback((error: unknown) => {
    if (error instanceof ApiError) setToast(error.message);
    else setToast(copy.chat.error);
  }, []);

  // ------------------------------------------------ real routes (Update #1)
  const locationKey = (point: { lat?: number; lon?: number } | null | undefined) =>
    point?.lat !== undefined && point?.lon !== undefined
      ? `${point.lat.toFixed(4)},${point.lon.toFixed(4)}`
      : "none";

  useEffect(() => {
    if (!shops.length) return;
    const origin = slots.location;
    if (!origin?.lat || !origin?.lon) return;
    const destinations = shops
      .filter((shop) => shop.lat !== null && shop.lat !== undefined && shop.lon !== null && shop.lon !== undefined)
      .slice(0, 8);
    if (!destinations.length) return;
    const key = `${locationKey(origin)}|${product?.product_id ?? ""}|${shops.length}|${destinations[0].shop_id}`;
    if (key === routesKeyRef.current) return;
    routesKeyRef.current = key;
    let cancelled = false;
    api
      .geoRoutes(
        { lat: origin.lat, lon: origin.lon },
        destinations.map((shop) => ({ lat: shop.lat, lon: shop.lon })),
        "pedestrian",
      )
      .then((response) => {
        if (cancelled) return;
        const next: Record<string, RouteInfo> = {};
        destinations.forEach((shop, index) => {
          const route = response.results[index];
          if (route) next[shop.shop_id] = route;
        });
        setRoutes((prev) => ({ ...prev, ...next }));
      })
      .catch(() => undefined);
    return () => {
      cancelled = true;
    };
  }, [shops, slots.location, product?.product_id]);

  // polyline of the walk to the first trip stop
  useEffect(() => {
    const first = trip?.stops?.[0];
    const origin = slots.location;
    if (!first?.lat || !first?.lon || !origin?.lat || !origin?.lon) return;
    const key = `${locationKey(origin)}|${first.shop_id}`;
    if (key === tripRouteKeyRef.current) return;
    tripRouteKeyRef.current = key;
    let cancelled = false;
    api
      .geoRoutes({ lat: origin.lat, lon: origin.lon }, [{ lat: first.lat, lon: first.lon }])
      .then((response) => {
        if (cancelled) return;
        setTripRoute(response.results[0] ?? null);
      })
      .catch(() => undefined);
    return () => {
      cancelled = true;
    };
  }, [trip, slots.location]);

  // ------------------------------------------------------------- actions
  const sendMessage = useCallback(
    async (text: string) => {
      const value = text.trim();
      if (!value || busy || !sessionId) return;
      setBusy(true);
      setStarted(true);
      setMarketFilter(null);
      setMessages((prev) => [...prev, { role: "user", content: value }]);
      setInput("");
      try {
        const response = await api.chat(
          sessionId,
          value,
          slots.location?.lat !== undefined && slots.location?.lon !== undefined
            ? { lat: slots.location.lat, lon: slots.location.lon }
            : undefined,
        );
        applyResponse(response);
      } catch (error) {
        handleError(error);
      } finally {
        setBusy(false);
      }
    },
    [applyResponse, busy, handleError, sessionId, slots.location],
  );

  const answerQuestion = useCallback(
    async (answer: string) => {
      if (!sessionId || busy) return;
      setBusy(true);
      setMarketFilter(null);
      setMessages((prev) => [...prev, { role: "user", content: answer }]);
      try {
        const response = await api.resume(sessionId, answer);
        applyResponse(response);
      } catch (error) {
        handleError(error);
      } finally {
        setBusy(false);
      }
    },
    [applyResponse, busy, handleError, sessionId],
  );

  const selectProduct = useCallback(
    async (productId: string) => {
      if (!sessionId || busy) return;
      setBusy(true);
      setSelectedShops([]);
      if (productId !== product?.product_id) setTripPicks([]);
      setRoutes({});
      setTripRoute(null);
      routesKeyRef.current = null;
      tripRouteKeyRef.current = null;
      try {
        const response = await api.selectProduct(sessionId, productId, sort);
        applyResponse(response);
      } catch (error) {
        handleError(error);
      } finally {
        setBusy(false);
      }
    },
    [applyResponse, busy, handleError, product?.product_id, sessionId, sort],
  );

  const askShops = useCallback(async () => {
    if (!sessionId || !selectedShops.length) return;
    setBusy(true);
    try {
      const response = await api.verify(sessionId, selectedShops);
      applyResponse(response);
    } catch (error) {
      handleError(error);
    } finally {
      setBusy(false);
    }
  }, [applyResponse, busy, handleError, selectedShops, sessionId]);

  const approve = useCallback(
    async (value: {
      approved: boolean;
      shop_ids: string[];
      message: string;
      messages?: Record<string, string>;
      channel: string;
    }) => {
      if (!sessionId) return;
      setBusy(true);
      try {
        const response = await api.resume(sessionId, value);
        applyResponse(response);
      } catch (error) {
        handleError(error);
      } finally {
        setBusy(false);
      }
    },
    [applyResponse, handleError, sessionId],
  );

  const planTrip = useCallback(async () => {
    if (!sessionId) return;
    const confirmed = followups
      .filter((followup) => followup.parsed?.availability === "available")
      .map((followup) => followup.shop_id);
    const chosen = [...new Set([...confirmed, ...tripPicks])];
    const fallback = selectedShops.length ? selectedShops : shops.slice(0, 1).map((s) => s.shop_id);
    setBusy(true);
    try {
      const response = await api.trip(sessionId, chosen.length ? chosen : fallback);
      applyResponse(response);
    } catch (error) {
      handleError(error);
    } finally {
      setBusy(false);
    }
  }, [applyResponse, followups, handleError, selectedShops, sessionId, shops, tripPicks]);

  const toggleShop = (shopId: string) => {
    setSelectedShops((prev) =>
      prev.includes(shopId) ? prev.filter((id) => id !== shopId) : [...prev, shopId],
    );
  };

  // «اضافه به مسیر» from the cheaper-nearby alert: keep a separate list so a
  // shop can be on the trip even if it was never messaged.
  const addToTrip = (shopId: string) => {
    setTripPicks((prev) => (prev.includes(shopId) ? prev : [...prev, shopId]));
    setToast(copy.haggle.addedToRoute);
  };

  const useMyLocation = () => {
    if (!navigator.geolocation) {
      setToast("دسترسی به موقعیت در این مرورگر نیست");
      return;
    }
    navigator.geolocation.getCurrentPosition(
      (position) => {
        const current: SlotLocation = {
          label: "موقعیت فعلی شما",
          lat: position.coords.latitude,
          lon: position.coords.longitude,
        };
        setLocation(current);
        setSlots((prev) => ({ ...prev, location: current }));
        setMessages((prev) => [
          ...prev,
          { role: "user", content: "می‌خواهم نزدیک موقعیت فعلیم بخرم" },
        ]);
        // Update #1: tell the user WHERE they are (Neshan, server fallback)
        api
          .geoReverse(current.lat, current.lon)
          .then((address) => {
            const where = address.neighbourhood || address.formatted_address;
            if (!where) return;
            setMessages((prev) => [
              ...prev,
              {
                role: "assistant",
                content:
                  address.source === "fallback"
                    ? `📍 حوالی «${where}» هستید (موقعیت تخمینی).`
                    : `📍 شما نزدیک «${where}» هستید.`,
              },
            ]);
          })
          .catch(() => undefined);
      },
      () => setToast("اجازهٔ دسترسی به موقعیت داده نشد"),
    );
  };

  const chooseNeighborhood = (name: string) => {
    const place = NEIGHBORHOODS[name];
    if (!place) return;
    setLocation(place);
    setSlots((prev) => ({ ...prev, location: place }));
    setMessages((prev) => [...prev, { role: "user", content: `نزدیک ${name}` }]);
  };

  // ------------------------------------------------------------- render
  const pendingQuestion = pending && pending.type === "question" ? pending : null;
  const pendingApproval = pending && pending.type === "approval" ? pending : null;
  // P1.6: the market filter applies to the list *and* the map at the same time
  const visibleShops = useMemo(
    () => shopsInMarket(shops, marketFilter),
    [shops, marketFilter],
  );

  return (
    <div className="min-h-screen bg-brand-bg">
      <div className="flex min-h-screen w-full flex-col xl:flex-row">
        {/* ---------------- chat column (right side in RTL, ~40%) ---------------- */}
        <div className="flex w-full flex-col xl:w-[40%] xl:max-w-[760px] xl:border-l xl:border-brand-border/70">
          {/* header */}
          <header className="sticky top-0 z-30 flex items-center justify-between border-b border-brand-border bg-brand-bg/95 px-4 py-3 backdrop-blur">
            <div className="flex items-center gap-2">
              <span className="flex h-9 w-9 items-center justify-center rounded-xl bg-brand-red text-[18px]">
                🌱
              </span>
              <div>
                <p className="text-[15px] font-bold leading-5">{copy.brand}</p>
                <p className="text-[10.5px] text-brand-gray">{copy.tagline}</p>
              </div>
            </div>
            <button
              onClick={() => setTraceOpen(true)}
              className="flex h-10 w-10 items-center justify-center rounded-xl border border-brand-border bg-white text-[16px]"
              aria-label={copy.trace.title}
            >
              🧠
            </button>
          </header>

          <SlotPills slots={slots} />

          <main className="flex-1 space-y-4 px-4 pb-4 pt-2">
            {!started ? (
              <section className="space-y-4 pt-4">
                <h1 className="text-[22px] font-bold leading-8">{copy.home.headline}</h1>
                <div className="rounded-card border border-brand-border bg-white p-3 shadow-card">
                  <textarea
                    value={input}
                    onChange={(event) => setInput(event.target.value)}
                    onKeyDown={(event) => {
                      if (event.key === "Enter" && !event.shiftKey) {
                        event.preventDefault();
                        sendMessage(input);
                      }
                    }}
                    rows={3}
                    placeholder={copy.home.placeholder}
                    className="w-full resize-none bg-transparent text-[14px] leading-7 outline-none placeholder:text-brand-gray"
                  />
                  <button
                    onClick={() => sendMessage(input)}
                    disabled={busy}
                    className="mt-2 w-full rounded-2xl bg-brand-red py-3 text-[14px] font-bold text-white disabled:opacity-60"
                  >
                    {copy.home.cta}
                  </button>
                </div>

                <div className="flex flex-wrap gap-2">
                  {copy.home.examples.map((example) => (
                    <Chip key={example} onClick={() => sendMessage(example)}>
                      {example}
                    </Chip>
                  ))}
                </div>

                <div className="space-y-2">
                  <button
                    onClick={useMyLocation}
                    className="flex w-full items-center gap-2 rounded-2xl border border-brand-border bg-white px-4 py-3 text-[13px] font-medium shadow-card"
                  >
                    {copy.home.location}
                  </button>
                  <div className="flex flex-wrap gap-2">
                    {copy.home.neighborhoods.map((name) => (
                      <Chip key={name} size="sm" onClick={() => chooseNeighborhood(name)}>
                        📍 {name}
                      </Chip>
                    ))}
                  </div>
                </div>
              </section>
            ) : (
              <>
                {messages.map((message, index) => (
                  <div
                    key={`${message.role}-${index}`}
                    className={`flex ${message.role === "user" ? "justify-end" : "justify-start"}`}
                  >
                    <motion.div
                      initial={{ opacity: 0, y: 8 }}
                      animate={{ opacity: 1, y: 0 }}
                      className={`max-w-[80%] whitespace-pre-line rounded-2xl px-3.5 py-2.5 text-[13.5px] leading-6 ${
                        message.role === "user"
                          ? "rounded-br-sm bg-brand-red text-white"
                          : "rounded-tr-sm border border-brand-border bg-white text-brand-text shadow-card"
                      }`}
                    >
                      {message.content}
                    </motion.div>
                  </div>
                ))}

                {pendingQuestion ? (
                  <div className="flex justify-start">
                    <div className="max-w-[90%] rounded-2xl rounded-tr-sm border border-brand-border bg-white p-3 shadow-card">
                      <p className="text-[13.5px] font-medium">{pendingQuestion.text}</p>
                      <div className="mt-2 flex flex-wrap gap-2">
                        {pendingQuestion.chips.map((chip) => (
                          <Chip key={chip} onClick={() => answerQuestion(chip)}>
                            {chip}
                          </Chip>
                        ))}
                      </div>
                    </div>
                  </div>
                ) : null}

                {busy ? <TypingIndicator /> : null}

                {cards.length ? (
                  <ProductCards
                    cards={cards}
                    more={more}
                    onSelect={selectProduct}
                    onSelectMore={selectProduct}
                  />
                ) : null}

                {market && !ooc && !compare ? (
                  <MarketCard
                    market={market}
                    filterActive={marketFilter?.market_id === market.market_id}
                    onFilterMarket={(next) =>
                      setMarketFilter((prev) =>
                        prev?.market_id === next.market_id ? null : next,
                      )
                    }
                  />
                ) : null}

                {ooc ? <OutOfCatalogCard ooc={ooc} onPickAlternative={selectProduct} /> : null}

                {compare ? <CompareCard compare={compare} onPickSide={selectProduct} /> : null}

                {shops.length ? (
                  <StoresSection
                    shops={visibleShops}
                    market={market}
                    marketFilter={marketFilter}
                    onClearMarketFilter={() => setMarketFilter(null)}
                    userLocation={location ?? slots.location ?? null}
                    selected={selectedShops}
                    routes={routes}
                    onToggle={toggleShop}
                    onAsk={askShops}
                    onSort={(next) => {
                      setSort(next);
                      if (product?.product_id) selectProduct(product.product_id);
                    }}
                    sort={sort}
                    onAddToTrip={addToTrip}
                    onPlanTrip={planTrip}
                    tripPicks={tripPicks}
                  />
                ) : null}

                {followups.length ? (
                  <Inbox
                    followups={followups}
                    shops={shops}
                    onPlanTrip={planTrip}
                    tripPicks={tripPicks}
                  />
                ) : null}

                {trip ? <TripPlan trip={trip} route={tripRoute} /> : null}

                <div ref={bottomRef} />
              </>
            )}
          </main>

          {/* bottom input */}
          {started ? (
            <div className="sticky bottom-0 z-30 border-t border-brand-border bg-brand-bg/95 px-4 py-3 backdrop-blur">
              <div className="flex items-end gap-2">
                <textarea
                  value={input}
                  onChange={(event) => setInput(event.target.value)}
                  onKeyDown={(event) => {
                    if (event.key === "Enter" && !event.shiftKey) {
                      event.preventDefault();
                      sendMessage(input);
                    }
                  }}
                  rows={1}
                  placeholder="بگو چی می‌خوای…"
                  className="max-h-28 flex-1 resize-none rounded-2xl border border-brand-border bg-white px-3.5 py-2.5 text-[13.5px] leading-6 outline-none focus:border-brand-red"
                />
                <button
                  onClick={() => sendMessage(input)}
                  disabled={busy}
                  className="flex h-11 w-11 items-center justify-center rounded-2xl bg-brand-red text-[17px] text-white disabled:opacity-60"
                  aria-label="ارسال"
                >
                  ↑
                </button>
              </div>
            </div>
          ) : null}
        </div>

        {/* ---------------- map pane (left side, wide screens, ~60%) ---------------- */}
        <aside className="hidden xl:block xl:w-[60%] xl:shrink-0 xl:p-4">
          <div className="sticky top-4 flex h-[calc(100vh-2rem)] flex-col gap-3">
            <div className="flex items-center justify-between rounded-card border border-brand-border bg-white px-4 py-3 shadow-card">
              <div>
                <h2 className="text-[15px] font-bold">🗺️ نقشهٔ مغازه‌ها</h2>
                <p className="text-[11.5px] text-brand-gray">
                  {visibleShops.length
                    ? `${faDigits(visibleShops.length)} فروشگاه برای کالای انتخابی`
                    : "اول یک کالا انتخاب کن"}
                </p>
              </div>
              {market ? (
                <span className="rounded-full bg-brand-purple/10 px-2.5 py-1 text-[11px] font-bold text-brand-purple">
                  🏬 {market.name_fa}
                </span>
              ) : null}
            </div>

            <div className="flex-1 overflow-hidden rounded-card border border-brand-border shadow-card">
              <MapView
                shops={visibleShops}
                market={market}
                userLocation={location ?? slots.location ?? null}
                route={tripRoute?.polyline ?? null}
                className="h-full w-full"
              />
            </div>

            {visibleShops.length ? (
              <div className="max-h-[28vh] space-y-1.5 overflow-y-auto rounded-card border border-brand-border bg-white p-3 shadow-card">
                {visibleShops.slice(0, 12).map((shop) => (
                  <div
                    key={shop.shop_id}
                    className="flex items-center justify-between gap-2 rounded-xl border border-brand-border px-3 py-2 text-[12px]"
                  >
                    <span className="truncate">
                      {shop.open_status === "open" ? "🟢" : shop.open_status === "closed" ? "🔴" : "⚪️"}{" "}
                      {shop.name}
                    </span>
                    <span className="shrink-0 font-bold text-brand-red">
                      {formatPrice(shop.price)} تومان
                    </span>
                  </div>
                ))}
              </div>
            ) : null}
          </div>
        </aside>
      </div>

      <PermissionSheet
        pending={pendingApproval}
        onApprove={approve}
        onReject={() =>
          approve({
            approved: false,
            shop_ids: [],
            message: "",
            messages: {},
            channel: "simulated_sms",
          })
        }
      />

      <TraceDrawer open={traceOpen} onClose={() => setTraceOpen(false)} trace={trace} />

      <AnimatePresence>
        {toast ? (
          <motion.div
            initial={{ opacity: 0, y: 20 }}
            animate={{ opacity: 1, y: 0 }}
            exit={{ opacity: 0, y: 20 }}
            className="fixed bottom-6 left-1/2 z-[60] -translate-x-1/2 rounded-2xl bg-brand-text px-4 py-2.5 text-[13px] text-white shadow-card"
          >
            {toast}
          </motion.div>
        ) : null}
      </AnimatePresence>
    </div>
  );
}
