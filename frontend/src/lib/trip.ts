import type { Trip } from "../types";

/**
 * Straight-line fallback for the trip map: start -> shop(s) -> cafe.
 * Used only when Neshan did not return a walking polyline.
 */
export function buildTripLine(trip: Trip): [number, number][] {
  const points: [number, number][] = [];
  const start = trip.start;
  if (start?.lat !== null && start?.lat !== undefined && start?.lon !== null && start?.lon !== undefined) {
    points.push([start.lat, start.lon]);
  }
  for (const stop of trip.stops ?? []) {
    if (stop.lat !== null && stop.lat !== undefined && stop.lon !== null && stop.lon !== undefined) {
      points.push([stop.lat, stop.lon]);
    }
  }
  const cafe = trip.cafe;
  if (cafe?.lat !== null && cafe?.lat !== undefined && cafe?.lon !== null && cafe?.lon !== undefined) {
    points.push([cafe.lat, cafe.lon]);
  }
  return points;
}
