import type { ApiResponse, CafesNearby, GeoAddress, RouteInfo } from "./types";

const BASE = import.meta.env.VITE_API_BASE ?? "";

export class ApiError extends Error {
  code: string;
  constructor(code: string, message: string) {
    super(message);
    this.code = code;
  }
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  let response: Response;
  try {
    response = await fetch(`${BASE}${path}`, {
      headers: { "Content-Type": "application/json" },
      ...init,
    });
  } catch {
    throw new ApiError("NETWORK", "اتصال قطع شد، دوباره امتحان کن");
  }
  let data: any = null;
  try {
    data = await response.json();
  } catch {
    throw new ApiError("BAD_RESPONSE", "پاسخ سرور قابل خواندن نبود");
  }
  if (!response.ok || data?.error) {
    throw new ApiError(
      data?.error?.code ?? "ERROR",
      data?.error?.message_fa ?? "خطایی پیش آمد، دوباره امتحان کن",
    );
  }
  return data as T;
}

export const api = {
  health: () => request<{ ok: boolean; llm_mode: string }>("/api/health"),

  createSession: () => request<{ session_id: string }>("/api/session", { method: "POST" }),

  chat: (sessionId: string, text: string, location?: { lat: number; lon: number }) =>
    request<ApiResponse>("/api/chat", {
      method: "POST",
      body: JSON.stringify({ session_id: sessionId, text, location }),
    }),

  resume: (sessionId: string, value: unknown) =>
    request<ApiResponse>("/api/resume", {
      method: "POST",
      body: JSON.stringify({ session_id: sessionId, value }),
    }),

  selectProduct: (sessionId: string, productId: string, sort = "recommended") =>
    request<ApiResponse>("/api/select_product", {
      method: "POST",
      body: JSON.stringify({ session_id: sessionId, product_id: productId, sort }),
    }),

  verify: (sessionId: string, shopIds: string[]) =>
    request<ApiResponse>("/api/verify", {
      method: "POST",
      body: JSON.stringify({ session_id: sessionId, shop_ids: shopIds }),
    }),

  trip: (sessionId: string, shopIds: string[]) =>
    request<ApiResponse>("/api/trip", {
      method: "POST",
      body: JSON.stringify({ session_id: sessionId, shop_ids: shopIds }),
    }),

  specialtyMarket: (category: string, lat?: number, lon?: number) => {
    const params = new URLSearchParams({ category });
    if (lat !== undefined && lon !== undefined) {
      params.set("lat", String(lat));
      params.set("lon", String(lon));
    }
    return request<{ market: ApiResponse["specialty_market"] }>(
      `/api/specialty_market?${params.toString()}`,
    );
  },

  /* ------------------------------------------------------------- geo (Update #1) */

  /** Reverse geocode a GPS coordinate (Neshan, with server-side fallback). */
  geoReverse: (lat: number, lon: number) =>
    request<GeoAddress>(
      `/api/geo/reverse?${new URLSearchParams({ lat: String(lat), lon: String(lon) })}`,
    ),

  /**
   * Walking/driving distance + ETA for up to 10 destinations.
   * Destinations without coordinates produce a null entry (aligned by index).
   */
  geoRoutes: (
    origin: { lat: number; lon: number },
    destinations: { lat?: number | null; lon?: number | null }[],
    mode: "pedestrian" | "car" = "pedestrian",
  ) =>
    request<{ results: (RouteInfo | null)[]; mode: string }>("/api/geo/routes", {
      method: "POST",
      body: JSON.stringify({ origin, destinations, mode }),
    }),

  /** Cafe suggestions: Neshan -> OSM -> local list, always labelled. */
  cafesNearby: (lat: number, lon: number, radius = 500) =>
    request<CafesNearby>(
      `/api/cafes/nearby?${new URLSearchParams({
        lat: String(lat),
        lon: String(lon),
        radius: String(radius),
      })}`,
    ),
};
