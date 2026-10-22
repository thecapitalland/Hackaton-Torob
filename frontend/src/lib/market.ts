import type { Market, Shop } from "../types";

const EARTH_RADIUS_M = 6_371_000;

/** Great-circle distance in meters between two lat/lon points. */
export function distanceMeters(
  a: { lat: number; lon: number },
  b: { lat: number; lon: number },
): number {
  const dPhi = ((b.lat - a.lat) * Math.PI) / 180;
  const dLambda = ((b.lon - a.lon) * Math.PI) / 180;
  const lat1 = (a.lat * Math.PI) / 180;
  const lat2 = (b.lat * Math.PI) / 180;
  const h =
    Math.sin(dPhi / 2) ** 2 +
    Math.cos(lat1) * Math.cos(lat2) * Math.sin(dLambda / 2) ** 2;
  return EARTH_RADIUS_M * 2 * Math.asin(Math.min(1, Math.sqrt(h)));
}

/** Center used for the market circle: shop centroid when available. */
export function marketAnchor(market: Market): [number, number] | null {
  return market.centroid ?? market.center ?? null;
}

/**
 * A shop belongs to a market when it is inside the curated radius.
 * A tiny tolerance covers GPS/geocoding jitter of the dataset.
 */
export function isShopInMarket(shop: Shop, market: Market, tolerance = 1.15): boolean {
  const anchor = marketAnchor(market);
  if (!anchor || shop.lat === null || shop.lat === undefined) return false;
  if (shop.lon === null || shop.lon === undefined) return false;
  const radius = market.radius_m ?? 400;
  return (
    distanceMeters({ lat: shop.lat, lon: shop.lon }, { lat: anchor[0], lon: anchor[1] }) <=
    radius * tolerance
  );
}

/** The stores list filtered to the selected market (no-op without a filter). */
export function shopsInMarket(shops: Shop[], market: Market | null | undefined): Shop[] {
  if (!market) return shops;
  return shops.filter((shop) => isShopInMarket(shop, market));
}
