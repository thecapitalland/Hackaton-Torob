import { useEffect, useMemo, useState } from "react";
import {
  MapContainer,
  Marker,
  Polyline,
  Popup,
  TileLayer,
  Circle,
  useMap,
} from "react-leaflet";
import L from "leaflet";
import type { Market, Shop, SlotLocation } from "../types";
import { faDigits, formatDistance, formatPrice } from "../format";
import { FairnessBadge } from "./HagglePanel";
import { medianLine } from "../lib/haggle";

const OSM_URL = "https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png";
const OSM_ATTRIBUTION = '&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a>';
const FALLBACK_URL = "https://{s}.basemaps.cartocdn.com/light_all/{z}/{x}/{y}{r}.png";
const FALLBACK_ATTRIBUTION = '&copy; <a href="https://carto.com/attributions">CARTO</a> | OSM';

function divIcon(className: string, html: string) {
  return L.divIcon({
    className: "",
    html: `<div class="${className}">${html}</div>`,
    iconSize: [32, 32],
    iconAnchor: [16, 16],
  });
}

function Recenter({ center }: { center: [number, number] }) {
  const map = useMap();
  useEffect(() => {
    map.setView(center, 14);
  }, [center, map]);
  return null;
}

/**
 * Leaflet measures its container once on mount.  Inside a flex pane or a
 * bottom sheet that happens before the final layout, which used to leave the
 * desktop map at ~2px (blank tiles, no markers).  Re-measure after mount, on
 * window resize and whenever the container itself changes size.
 */
function MapResize() {
  const map = useMap();
  useEffect(() => {
    const invalidate = () => map.invalidateSize();
    const timer = window.setTimeout(invalidate, 0);
    window.addEventListener("resize", invalidate);
    let observer: ResizeObserver | null = null;
    const parent = map.getContainer().parentElement;
    if (typeof ResizeObserver !== "undefined" && parent) {
      observer = new ResizeObserver(invalidate);
      observer.observe(parent);
    }
    return () => {
      window.clearTimeout(timer);
      window.removeEventListener("resize", invalidate);
      observer?.disconnect();
    };
  }, [map]);
  return null;
}

export function MapView({
  shops,
  market,
  userLocation,
  start,
  cafe,
  center,
  onSelectShop,
  route,
  fallbackRoute,
  className = "h-[320px]",
}: {
  shops: Shop[];
  market?: Market | null;
  userLocation?: SlotLocation | null;
  /** trip start marker (🏁) */
  start?: { lat: number; lon: number; label?: string } | null;
  /** cafe stop marker (☕) */
  cafe?: { name: string; lat: number; lon: number; label?: string | null } | null;
  center?: [number, number] | null;
  onSelectShop?: (shop: Shop) => void;
  /** walking route polyline [[lat, lon], ...] - drawn when present */
  route?: [number, number][] | null;
  /** straight fallback line, drawn dashed only when there is no real route */
  fallbackRoute?: [number, number][] | null;
  className?: string;
}) {
  const [tileUrl, setTileUrl] = useState(OSM_URL);
  const [attribution, setAttribution] = useState(OSM_ATTRIBUTION);
  const [expandedMall, setExpandedMall] = useState<string | null>(null);

  const points = useMemo(
    () => shops.filter((shop) => shop.lat !== null && shop.lon !== null),
    [shops],
  );

  const malls = useMemo(() => {
    const groups = new Map<string, Shop[]>();
    points.forEach((shop) => {
      const key = shop.mall ?? "";
      if (!key) return;
      groups.set(key, [...(groups.get(key) ?? []), shop]);
    });
    return [...groups.entries()].filter(([, items]) => items.length >= 3);
  }, [points]);

  const mallNames = new Set(malls.map(([name]) => name));

  const visible = points.filter(
    (shop) => !shop.mall || !mallNames.has(shop.mall) || expandedMall === shop.mall,
  );

  const mapCenter: [number, number] =
    center ??
    (points.length
      ? [
          points.reduce((sum, shop) => sum + (shop.lat ?? 0), 0) / points.length,
          points.reduce((sum, shop) => sum + (shop.lon ?? 0), 0) / points.length,
        ]
      : [35.695, 51.4115]);

  const marketPoint =
    (market?.centroid as [number, number] | null | undefined) ??
    (market?.center as [number, number] | undefined) ??
    null;

  return (
    <div className={`relative w-full ${className}`}>
      <MapContainer
        center={mapCenter}
        zoom={14}
        scrollWheelZoom
        className="h-full w-full rounded-card border border-brand-border"
        style={{ zIndex: 0 }}
      >
      <MapResize />
      <Recenter center={mapCenter} />
      <TileLayer
        url={tileUrl}
        attribution={attribution}
        eventHandlers={{
          tileerror: () => {
            if (tileUrl !== FALLBACK_URL) {
              setTileUrl(FALLBACK_URL);
              setAttribution(FALLBACK_ATTRIBUTION);
            }
          },
        }}
      />

      {marketPoint ? (
        <>
          {market?.radius_m ? (
            <Circle
              center={marketPoint}
              radius={market.radius_m}
              pathOptions={{ color: "#8E4EC6", fillColor: "#8E4EC6", fillOpacity: 0.08 }}
            />
          ) : null}
          <Marker
            position={marketPoint}
            icon={divIcon("market-marker", "<span>🏬</span>")}
          >
            <Popup>{market?.name_fa}</Popup>
          </Marker>
        </>
      ) : null}

      {malls.map(([name, items]) => {
        if (expandedMall === name) return null;
        const lat = items.reduce((sum, shop) => sum + (shop.lat ?? 0), 0) / items.length;
        const lon = items.reduce((sum, shop) => sum + (shop.lon ?? 0), 0) / items.length;
        return (
          <Marker
            key={`cluster-${name}`}
            position={[lat, lon]}
            icon={divIcon(
              "market-marker",
              `<span style="font-size:11px;font-weight:700">${faDigits(items.length)}</span>`,
            )}
            eventHandlers={{ click: () => setExpandedMall(name) }}
          >
            <Popup>{`${faDigits(items.length)} فروشگاه در ${name}`}</Popup>
          </Marker>
        );
      })}

      {visible.map((shop) => (
        <Marker
          key={shop.shop_id}
          position={[shop.lat as number, shop.lon as number]}
          icon={divIcon(
            `shop-marker shop-marker--${shop.open_status}`,
            shop.open_status === "open" ? "✓" : shop.open_status === "closed" ? "✕" : "؟",
          )}
          eventHandlers={{
            click: () => onSelectShop?.(shop),
          }}
        >
          <Popup>
            <div className="text-right">
              <strong>{shop.name}</strong>
              <br />
              {formatPrice(shop.price)} تومان
              {shop.mall || shop.floor ? (
                <>
                  <br />
                  🏬 {shop.mall ?? ""}
                  {shop.floor ? ` · طبقه ${faDigits(shop.floor)}` : ""}
                </>
              ) : null}
              <br />
              {shop.open_text}
              {shop.haggle ? (
                <>
                  <br />
                  <FairnessBadge label={shop.haggle.label} className="mt-1" />
                  <br />
                  <span style={{ fontSize: 10.5, color: "#6F6E69" }}>
                    {medianLine(shop.haggle)}
                  </span>
                </>
              ) : null}
            </div>
          </Popup>
        </Marker>
      ))}

      {route && route.length >= 2 ? (
        <Polyline
          positions={route}
          pathOptions={{ color: "#E63946", weight: 3, opacity: 0.9 }}
          interactive={false}
        />
      ) : fallbackRoute && fallbackRoute.length >= 2 ? (
        <Polyline
          positions={fallbackRoute}
          pathOptions={{
            color: "#E63946",
            weight: 3,
            opacity: 0.85,
            dashArray: "8 10",
          }}
          interactive={false}
        />
      ) : null}

      {start ? (
        <Marker
          position={[start.lat, start.lon]}
          icon={divIcon("start-marker", "🏁")}
        >
          <Popup>{start.label ?? "شروع مسیر"}</Popup>
        </Marker>
      ) : null}

      {cafe ? (
        <Marker position={[cafe.lat, cafe.lon]} icon={divIcon("cafe-marker", "☕")}>
          <Popup>
            {cafe.name}
            {cafe.label ? ` · ${cafe.label}` : ""}
          </Popup>
        </Marker>
      ) : null}

      {userLocation ? (
        <Marker
          position={[userLocation.lat, userLocation.lon]}
          icon={divIcon("user-marker", "")}
        >
          <Popup>موقعیت شما</Popup>
        </Marker>
      ) : null}
      </MapContainer>
      {!route && fallbackRoute && fallbackRoute.length >= 2 ? (
        <span className="pointer-events-none absolute right-3 top-3 z-[1000] rounded-full bg-white/95 px-2.5 py-1 text-[11px] font-bold text-brand-amber shadow-card">
          خط مستقیم · فاصلهٔ تقریبی
        </span>
      ) : null}
    </div>
  );
}

export function distanceLabel(shop: Shop): string {
  return formatDistance(shop.distance_m);
}
