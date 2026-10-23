import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { AnimatePresence, motion } from "framer-motion";
import { ApiError, api } from "./api";
import { copy } from "./copy.fa";
import { faDigits } from "./format";
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
import { TypingIndicator } from "./components/Chat";
import { ProductCards } from "./components/ProductCards";
import { MarketCard } from "./components/MarketCard";
import { OutOfCatalogCard } from "./components/OutOfCatalogCard";
import { CompareCard } from "./components/CompareCard";
import { StoresSection, type SortKey } from "./components/Stores";
import { PermissionSheet } from "./components/PermissionSheet";
import { Inbox } from "./components/Inbox";
import { TripPlan } from "./components/TripPlan";
import { TraceDrawer } from "./components/TraceDrawer";
import { Chip, Sheet } from "./components/ui";
import { MapView } from "./components/MapView";
import { LocationModal } from "./components/LocationModal";
import { SummaryBar } from "./components/SummaryBar";
import { filterByRadius } from "./lib/shop";

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
  const [locationOpen, setLocationOpen] = useState(false);
  const [mapOpen, setMapOpen] = useState(false);
  const [radiusKm, setRadiusKm] = useState<number | null>(null);
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
    if (response.slots) {
      setSlots(response.slots);
      if (response.slots.location) setLocation(response.slots.location);
    }
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

  const chooseLocation = async (next: SlotLocation) => {
    setLocation(next);
    setSlots((prev) => ({ ...prev, location: next }));
    setRoutes({});
    routesKeyRef.current = null;
    if (!started || !sessionId) return;
    try {
      const response = await api.updateLocation(sessionId, next);
      applyResponse(response);
    } catch (error) {
      handleError(error);
    }
  };

  const compareSelected = async (productIds: string[]) => {
    if (!sessionId || busy || productIds.length < 2) return;
    setBusy(true);
    try {
      applyResponse(await api.compareProducts(sessionId, productIds));
    } catch (error) {
      handleError(error);
    } finally {
      setBusy(false);
    }
  };

  // ------------------------------------------------------------- render
  const pendingQuestion = pending && pending.type === "question" ? pending : null;
  const pendingApproval = pending && pending.type === "approval" ? pending : null;
  // P1.6: the market filter applies to the list *and* the map at the same time
  const visibleShops = useMemo(
    () => filterByRadius(shopsInMarket(shops, marketFilter), location ?? slots.location, radiusKm),
    [shops, marketFilter, location, slots.location, radiusKm],
  );

  return (
    <div className="min-h-screen bg-brand-bg">
      <div className="flex min-h-screen w-full flex-col">
        {/* ---------------- chat column (right side in RTL, ~40%) ---------------- */}
        <div className="flex w-full flex-col xl:mx-auto xl:max-w-[960px] xl:border-x xl:border-brand-border/70">
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
            <div className="flex items-center gap-2">
              <button
                onClick={() => setLocationOpen(true)}
                className="max-w-[180px] truncate rounded-full border border-brand-border bg-white px-3 py-2 text-[11px] font-bold"
              >
                📍 {location?.label ?? slots.location?.label ?? copy.home.location} · {copy.home.changeLocation}
              </button>
              <button
                onClick={() => setTraceOpen(true)}
                className="flex h-10 w-10 items-center justify-center rounded-xl border border-brand-border bg-white text-[16px]"
                aria-label={copy.trace.title}
              >
                🧠
              </button>
            </div>
          </header>

          <main className="flex-1 space-y-4 px-4 pb-4 pt-2 xl:flex-none">
            {!started ? (
              <section className="space-y-4 pt-4">
                <p className="text-[13px] leading-6 text-brand-muted">{copy.home.greeting}</p>
                <div className="rounded-card border border-brand-border bg-white p-3 shadow-card">
                  <div className="mb-2 text-[14px] font-bold">{copy.home.location}</div>
                  <div className="grid grid-cols-1 gap-2 sm:grid-cols-3">
                    <button onClick={() => setLocationOpen(true)} className="rounded-xl bg-brand-bg p-3 text-[12px] font-bold">{copy.home.useGps}</button>
                    <button onClick={() => setLocationOpen(true)} className="rounded-xl bg-brand-bg p-3 text-[12px] font-bold">{copy.home.typeLocation}</button>
                    <button onClick={() => setLocationOpen(true)} className="rounded-xl bg-brand-bg p-3 text-[12px] font-bold">{copy.home.pickMap}</button>
                  </div>
                  {location ? <p className="mt-2 text-[11px] text-brand-muted">📍 {location.label}</p> : null}
                </div>
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

                {slots.query || cards.length ? (
                  <SummaryBar slots={slots} radiusKm={radiusKm} onEdit={sendMessage} />
                ) : null}

                {cards.length ? (
                  <ProductCards
                    cards={cards}
                    more={more}
                    onSelect={selectProduct}
                    onSelectMore={selectProduct}
                    onCompare={compareSelected}
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
                  <section className="space-y-3">
                    <div className="flex flex-wrap items-center gap-2 rounded-2xl border border-brand-border bg-white p-3">
                      <span className="w-full text-[12px] font-bold">{copy.home.radiusTitle}</span>
                      {[2, 5, 10, null].map((radius) => (
                        <Chip
                          key={radius ?? "all"}
                          active={radiusKm === radius}
                          size="sm"
                          onClick={() => setRadiusKm(radius)}
                        >
                          {radius === null ? copy.home.wholeCity : `${faDigits(radius)} ${copy.home.km}`}
                        </Chip>
                      ))}
                    </div>
                    {radiusKm !== null && !visibleShops.length ? (
                      <div className="rounded-2xl border border-brand-border bg-white p-3 text-[12px] text-brand-muted">
                        <p>{copy.home.radiusEmpty}</p>
                        <button
                          onClick={() => setRadiusKm(radiusKm === 2 ? 5 : radiusKm === 5 ? 10 : null)}
                          className="mt-2 rounded-full bg-brand-red px-3 py-1.5 font-bold text-white"
                        >
                          {copy.home.radiusNext}
                        </button>
                      </div>
                    ) : null}
                    <div
                      role="button"
                      tabIndex={0}
                      onClick={() => setMapOpen(true)}
                      onKeyDown={(event) => { if (event.key === "Enter") setMapOpen(true); }}
                      className="flex cursor-pointer items-center gap-3 rounded-2xl border border-brand-border bg-white p-2 shadow-card"
                    >
                      <div className="pointer-events-none h-32 w-32 shrink-0 overflow-hidden rounded-xl">
                        <MapView
                          shops={visibleShops}
                          market={market}
                          userLocation={location ?? slots.location ?? null}
                          radiusKm={radiusKm}
                          className="h-32 w-32"
                        />
                      </div>
                      <div className="text-right">
                        <p className="text-[13px] font-bold">🗺️ {copy.stores.map}</p>
                        <p className="mt-1 text-[11px] text-brand-muted">{faDigits(visibleShops.length)} {copy.stores.title}</p>
                      </div>
                    </div>
                  </section>
                ) : null}

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
            <div className="sticky bottom-0 z-30 border-t border-brand-border bg-brand-bg/95 px-4 py-3 backdrop-blur xl:static xl:z-auto xl:border-t-0 xl:bg-transparent xl:backdrop-blur-none">
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
                  placeholder={copy.home.placeholder}
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

      </div>

      <LocationModal open={locationOpen} onClose={() => setLocationOpen(false)} onChoose={chooseLocation} />
      <Sheet open={mapOpen} onClose={() => setMapOpen(false)} title={copy.stores.map} wide>
        <div className="h-[70vh] min-h-[360px]">
          <MapView
            shops={visibleShops}
            market={market}
            userLocation={location ?? slots.location ?? null}
            route={tripRoute?.polyline ?? null}
            radiusKm={radiusKm}
            className="h-full w-full"
          />
        </div>
      </Sheet>

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
