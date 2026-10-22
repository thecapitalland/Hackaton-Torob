import { copy } from "../copy.fa";

/** True on phones/tablets - the Neshan app deep link works there. */
function isTouchDevice(): boolean {
  if (typeof window === "undefined" || typeof navigator === "undefined") return false;
  return "ontouchstart" in window || navigator.maxTouchPoints > 0;
}

/**
 * «مسیریابی در نشان» + «مسیریابی در بلد» deep links (Update #1).
 *
 * The backend sends the device-neural Neshan URL (`nshn.ir/?destination=`),
 * the desktop web map is picked here when the user is not on a phone.
 */
export function DirectionsLinks({
  lat,
  lon,
  variant = "chip",
}: {
  lat?: number | null;
  lon?: number | null;
  variant?: "chip" | "button";
}) {
  if (lat === null || lat === undefined || lon === null || lon === undefined) return null;
  const destination = `${lat},${lon}`;
  const neshanHref = isTouchDevice()
    ? `https://nshn.ir/?destination=${destination}`
    : `https://neshan.org/maps/share/${destination}`;
  const baladHref = `https://balad.ir/directions/driving?destination=${destination}`;

  if (variant === "button") {
    return (
      <div className="flex flex-wrap gap-2">
        <a
          href={neshanHref}
          target="_blank"
          rel="noreferrer"
          className="flex-1 rounded-xl bg-brand-green py-2.5 text-center text-[12.5px] font-bold text-white"
        >
          {copy.trip.neshan}
        </a>
        {baladHref ? (
          <a
            href={baladHref}
            target="_blank"
            rel="noreferrer"
            className="flex-1 rounded-xl border border-brand-border py-2.5 text-center text-[12.5px] font-bold"
          >
            {copy.trip.balad}
          </a>
        ) : null}
      </div>
    );
  }

  return (
    <div className="flex flex-wrap gap-1.5">
      <a
        href={neshanHref}
        target="_blank"
        rel="noreferrer"
        className="rounded-full border border-brand-border bg-brand-green/5 px-2.5 py-1 text-[10.5px] font-bold text-brand-green"
      >
        🧭 {copy.stores.directionsNeshan}
      </a>
      <a
        href={baladHref}
        target="_blank"
        rel="noreferrer"
        className="rounded-full border border-brand-border bg-brand-bg px-2.5 py-1 text-[10.5px] font-bold text-brand-muted"
      >
        🗺️ {copy.stores.directionsBalad}
      </a>
    </div>
  );
}
