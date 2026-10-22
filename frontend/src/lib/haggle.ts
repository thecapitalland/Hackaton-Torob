import { copy } from "../copy.fa";
import { faDigits, formatDistance, formatPrice } from "../format";
import type { Fairness, Haggle } from "../types";

export type FairnessTone = "danger" | "muted" | "success" | "neutral";

/** Persian badge for a fairness label. */
export function fairnessLabel(label?: Fairness | string | null): {
  text: string;
  tone: FairnessTone;
} {
  switch (label) {
    case "expensive":
      return { text: copy.haggle.expensive, tone: "danger" };
    case "good":
      return { text: copy.haggle.good, tone: "success" };
    case "single":
      return { text: copy.haggle.single, tone: "neutral" };
    default:
      return { text: copy.haggle.normal, tone: "muted" };
  }
}

/** «میانه ۲۷ فروشگاه: ۲٬۹۹۰٬۰۰۰» (or the honest single-offer note). */
export function medianLine(haggle?: Haggle | null): string {
  if (!haggle) return "";
  if (haggle.label === "single" || haggle.n_shops < 2) {
    return copy.haggle.singleNote;
  }
  return `${copy.haggle.median} ${faDigits(haggle.n_shops)} ${copy.haggle.shops}: ${formatPrice(
    haggle.median,
  )}`;
}

/** «۲۰۰ متر اون‌ورتر «X» ۲۵۰٬۰۰۰ تومان ارزون‌تره» */
export function cheaperAlert(haggle?: Haggle | null): string | null {
  const leverage = haggle?.leverage;
  if (!leverage) return null;
  const saving = leverage.saving ?? 0;
  if (saving <= 0) return null;
  const distance = leverage.delta_m ?? leverage.distance_m;
  const parts: string[] = [];
  if (distance !== null && distance !== undefined) {
    parts.push(`${formatDistance(distance)} ${copy.haggle.overThere}`);
  }
  parts.push(`«${leverage.name}»`);
  parts.push(`${formatPrice(saving)} ${copy.haggle.toman} ${copy.haggle.cheaper}`);
  return parts.join(" ");
}

export function targetLine(haggle: Haggle): string {
  return `${copy.haggle.target}: ${formatPrice(haggle.target)} ${copy.haggle.toman}`;
}

export function ceilingLine(haggle: Haggle): string {
  return `${copy.haggle.ceiling}: ${formatPrice(haggle.ceiling)} ${copy.haggle.toman}`;
}

export function savingLine(haggle: Haggle): string {
  return `${copy.haggle.saving} ${faDigits(Math.round(haggle.saving_pct))}٪`;
}

/** Copy-to-clipboard with a graceful fallback for non-secure origins. */
export async function copyText(text: string): Promise<boolean> {
  try {
    if (navigator.clipboard?.writeText) {
      await navigator.clipboard.writeText(text);
      return true;
    }
  } catch {
    return false;
  }
  return false;
}
