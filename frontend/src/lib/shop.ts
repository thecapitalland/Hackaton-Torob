import { faFloor } from "../format";
import type { Shop, SlotLocation } from "../types";

/**
 * «پاساژ علاالدین · طبقه ۲» — B4: empty parts never leave a trailing « · ».
 */
export function shopLocationLine(
  mall: string | null | undefined,
  floor: string | null | undefined,
): string {
  return [mall ?? "", floor ? `طبقه ${faFloor(floor)}` : ""]
    .filter(Boolean)
    .join(" · ");
}

export function filterByRadius(
  shops: Shop[],
  location: SlotLocation | null | undefined,
  radiusKm: number | null,
): Shop[] {
  if (radiusKm === null || !location) return shops;
  const radiusM = radiusKm * 1000;
  return shops.filter((shop) => {
    if (shop.lat == null || shop.lon == null) return false;
    const toRad = (value: number) => (value * Math.PI) / 180;
    const dLat = toRad(shop.lat - location.lat);
    const dLon = toRad(shop.lon - location.lon);
    const lat1 = toRad(location.lat);
    const lat2 = toRad(shop.lat);
    const a = Math.sin(dLat / 2) ** 2 + Math.cos(lat1) * Math.cos(lat2) * Math.sin(dLon / 2) ** 2;
    const distanceM = 6_371_000 * 2 * Math.atan2(Math.sqrt(a), Math.sqrt(1 - a));
    return distanceM <= radiusM;
  });
}

export function toggleCompare(selected: string[], productId: string, max = 4): string[] {
  if (selected.includes(productId)) return selected.filter((id) => id !== productId);
  if (selected.length >= max) return selected;
  return [...selected, productId];
}
