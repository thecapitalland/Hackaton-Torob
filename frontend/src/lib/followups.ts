import type { Followup } from "../types";

/** Name of the first shop that confirmed availability (best verified shop). */
export function bestConfirmedName(followups: Followup[]): string | null {
  const best = followups.find(
    (followup) => followup.parsed?.availability === "available",
  );
  return best?.name ?? null;
}
