import type { Followup } from "../types";

/**
 * Name of the best shop that confirmed availability.
 *
 * When a shop accepted the target or countered, `parsed.price_toman` is the
 * negotiated price, so the cheapest confirmed shop wins (the first one when
 * prices are missing/equal).
 */
export function bestConfirmedName(followups: Followup[]): string | null {
  const available = followups.filter(
    (followup) => followup.parsed?.availability === "available",
  );
  if (!available.length) return null;
  const price = (followup: Followup) =>
    followup.parsed?.price_toman ?? Number.POSITIVE_INFINITY;
  return [...available].sort((a, b) => price(a) - price(b))[0].name;
}
