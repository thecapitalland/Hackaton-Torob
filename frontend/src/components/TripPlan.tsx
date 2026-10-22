import { motion } from "framer-motion";
import { copy } from "../copy.fa";
import { faDigits, formatDistance, formatPrice } from "../format";
import { buildTripLine } from "../lib/trip";
import type { RouteInfo, Trip } from "../types";
import { MapView } from "./MapView";
import { DirectionsLinks } from "./DirectionsLinks";

export function TripPlan({ trip, route }: { trip: Trip; route?: RouteInfo | null }) {
  const first = trip.stops?.[0];
  const mapStops = (trip.stops ?? []).filter(
    (stop) =>
      stop.lat !== null && stop.lat !== undefined && stop.lon !== null && stop.lon !== undefined,
  );
  const startPoint: [number, number] | null =
    trip.start?.lat !== null &&
    trip.start?.lat !== undefined &&
    trip.start?.lon !== null &&
    trip.start?.lon !== undefined
      ? [trip.start.lat, trip.start.lon]
      : mapStops.length
        ? [mapStops[0].lat as number, mapStops[0].lon as number]
        : null;
  const shareText = encodeURIComponent(
    `برنامهٔ خرید من با تربچه: ${trip.stops
      .map((stop) => `${stop.order}. ${stop.name}`)
      .join(" | ")}${trip.cafe ? ` | کافه: ${trip.cafe.name}` : ""}`,
  );

  return (
    <motion.section
      initial={{ opacity: 0, y: 10 }}
      animate={{ opacity: 1, y: 0 }}
      className="space-y-3 rounded-card border border-brand-border bg-white p-4 shadow-card"
    >
      <h2 className="text-[16px] font-bold">🧭 {copy.trip.title}</h2>
      <p className="text-[13px] leading-6 text-brand-muted">{trip.summary}</p>

      <ol className="relative space-y-3 border-r-2 border-dashed border-brand-border pr-4">
        <li className="relative">
          <span className="absolute -right-[26px] top-0.5 h-3 w-3 rounded-full bg-brand-muted" />
          <p className="text-[13px] font-bold">{copy.trip.start}</p>
          <p className="text-[11.5px] text-brand-gray">{trip.start?.label}</p>
        </li>
        {trip.stops.map((stop) => (
          <li key={stop.shop_id} className="relative">
            <span className="absolute -right-[26px] top-0.5 h-3 w-3 rounded-full bg-brand-red" />
            <p className="text-[13px] font-bold">
              🛍️ {stop.name}{" "}
              {stop.verified ? (
                <span className="rounded-full bg-brand-green/10 px-1.5 py-0.5 text-[10.5px] text-brand-green">
                  تأییدشده
                </span>
              ) : null}
            </p>
            <p className="text-[11.5px] text-brand-gray">
              {stop.arrive_hint || stop.address}
              {stop.price ? ` · ${formatPrice(stop.price)} ${copy.haggle.toman}` : ""}
              {route && !route.estimated && stop === first
                ? ` · ${faDigits(route.duration_min)} دقیقه پیاده (${copy.stores.realRoute})`
                : stop.walk_min_est
                  ? ` · ${faDigits(stop.walk_min_est)} دقیقه پیاده (${copy.trip.estimate})`
                  : ""}
            </p>
          </li>
        ))}
        {trip.cafe ? (
          <li className="relative">
            <span className="absolute -right-[26px] top-0.5 h-3 w-3 rounded-full bg-brand-amber" />
            <p className="text-[13px] font-bold">
              ☕ {trip.cafe.name}
              {trip.cafe.label ? (
                <span className="ms-2 rounded-full bg-brand-amber/10 px-1.5 py-0.5 text-[10px] font-bold text-brand-amber">
                  {trip.cafe.label}
                </span>
              ) : null}
            </p>
            <p className="text-[11.5px] text-brand-gray">
              {copy.trip.cafeNote}
              {trip.cafe.distance_m ? ` · ${formatDistance(trip.cafe.distance_m)}` : ""}
            </p>
          </li>
        ) : null}
        {trip.backup ? (
          <li className="relative">
            <span className="absolute -right-[26px] top-0.5 h-3 w-3 rounded-full bg-brand-gray" />
            <p className="text-[13px] font-bold">
              🅱️ {copy.trip.backup}: {trip.backup.name}
              {trip.backup.price
                ? ` · ${formatPrice(trip.backup.price)} ${copy.haggle.toman}`
                : ""}
            </p>
          </li>
        ) : null}
      </ol>

      {startPoint ? (
        <MapView
          shops={mapStops.map((stop) => ({
            shop_id: stop.shop_id,
            offer_id: "",
            name: stop.name,
            price: stop.price ?? 0,
            lat: stop.lat,
            lon: stop.lon,
            open_status: "open",
            open_text: "",
            in_person_providers: [],
            transparency: { score: 0, chips: [] },
            score: 0,
            why: "",
          }))}
          center={startPoint}
          start={
            trip.start?.lat !== null &&
            trip.start?.lat !== undefined &&
            trip.start?.lon !== null &&
            trip.start?.lon !== undefined
              ? {
                  lat: trip.start.lat,
                  lon: trip.start.lon,
                  label: trip.start.label,
                }
              : null
          }
          cafe={trip.cafe ?? null}
          route={route?.polyline ?? null}
          fallbackRoute={buildTripLine(trip)}
        />
      ) : null}

      <div className="flex flex-wrap gap-2">
        {trip.links?.neshan ? (
          <a
            href={trip.links.neshan}
            target="_blank"
            rel="noreferrer"
            className="flex-1 rounded-xl bg-brand-green py-2.5 text-center text-[12.5px] font-bold text-white"
          >
            {copy.trip.neshan}
          </a>
        ) : null}
        {trip.links?.balad ? (
          <a
            href={trip.links.balad}
            target="_blank"
            rel="noreferrer"
            className="flex-1 rounded-xl border border-brand-border py-2.5 text-center text-[12.5px] font-bold"
          >
            {copy.trip.balad}
          </a>
        ) : null}
        <a
          href={`https://wa.me/?text=${shareText}`}
          target="_blank"
          rel="noreferrer"
          className="flex-1 rounded-xl border border-brand-border py-2.5 text-center text-[12.5px] font-bold"
        >
          {copy.trip.share}
        </a>
      </div>

      <div>
        <h3 className="mb-2 text-[13.5px] font-bold">✅ {copy.trip.checklist}</h3>
        <ul className="space-y-1.5">
          {trip.checklist.map((item) => (
            <li key={item} className="flex items-center gap-2 text-[12.5px] text-brand-muted">
              <span className="flex h-5 w-5 items-center justify-center rounded-md border border-brand-border">
                ☐
              </span>
              {item}
            </li>
          ))}
        </ul>
      </div>
    </motion.section>
  );
}
