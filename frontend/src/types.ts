import type { Decision } from "./types/api.gen";

export type Phase =
  | "discover"
  | "recommend"
  | "compare"
  | "stores"
  | "verify"
  | "trip"
  | "done"
  | "out_of_catalog";

export interface SlotLocation {
  label: string;
  lat: number;
  lon: number;
}

export interface Slots {
  query?: string;
  category?: string | null;
  brand?: string | null;
  keywords?: string[];
  budget_max?: number | null;
  budget_min?: number | null;
  location?: SlotLocation | null;
  radius_km?: 2 | 5 | 10 | null;
  accessory_request?: boolean;
  payment_in_person?: boolean;
  installment?: boolean;
  today?: boolean;
  in_torob?: boolean;
}

export interface Message {
  role: "user" | "assistant";
  content: string;
}

export interface TraceEntry {
  node: string;
  summary: string;
  ms: number;
}

export interface PendingQuestion {
  type: "question";
  id?: string;
  text: string;
  chips: string[];
  missing?: string[];
}

export interface PendingApproval {
  type: "approval";
  channel: string;
  targets: {
    shop_id: string;
    name: string;
    price?: number;
    target_price?: number | null;
    message?: string;
  }[];
  message: string;
  privacy_note?: string;
}

export type Pending = PendingQuestion | PendingApproval | null;

export interface ProductCard {
  kind: "best" | "budget" | "premium";
  product_id: string;
  title: string;
  brand: string;
  image?: string | null;
  min_price: number;
  median_price: number;
  n_shops: number;
  highlights: string[];
  why: string;
  warnings: string[];
}

export interface MoreItem {
  product_id: string;
  title: string;
  brand?: string;
  image?: string | null;
  min_price: number;
  n_shops: number;
}

export interface Transparency {
  score: number;
  chips: string[];
  signals?: Record<string, boolean>;
  disclaimer?: string;
}

export type Fairness = "expensive" | "normal" | "good" | "single";

export interface HaggleLeverage {
  shop_id: string;
  name: string;
  price: number;
  distance_m?: number | null;
  delta_m?: number | null;
  same_mall?: boolean;
  saving?: number;
}

export interface Haggle {
  label: Fairness;
  median: number;
  q1: number;
  min: number;
  n_shops: number;
  target: number;
  ceiling: number;
  saving_pct: number;
  leverage?: HaggleLeverage | null;
  lines: string[];
}

export interface Shop {
  shop_id: string;
  offer_id: string;
  name: string;
  price: number;
  address?: string;
  mall?: string | null;
  floor?: string | null;
  unit?: string | null;
  lat?: number | null;
  lon?: number | null;
  distance_m?: number | null;
  walk_min_est?: number | null;
  open_status: "open" | "closed" | "unknown";
  open_text: string;
  in_person_providers: string[];
  warranty?: { provider?: string; period_months?: number } | null;
  warranty_text?: string | null;
  price_age_days?: number | null;
  transparency: Transparency;
  score: number;
  why: string;
  verify?: ParsedReply | null;
  haggle?: Haggle | null;
  negotiated_price?: number | null;
  offer_status?: "accepted" | "countered" | "none" | null;
}

export interface ParsedReply {
  availability: "available" | "unavailable" | "unclear";
  price_toman?: number | null;
  price_changed?: boolean;
  hours_text?: string | null;
  alternative?: string | null;
  installment?: boolean | null;
  confidence: number;
  offer_status?: "accepted" | "countered" | "none";
  counter_price?: number | null;
}

/* ---------------------------------------------------------------- geo (Update #1) */

export interface GeoAddress {
  formatted_address: string;
  neighbourhood?: string | null;
  label?: string | null;
  source: "neshan" | "fallback";
}

export interface GeoSuggestion {
  name_fa: string;
  lat: number;
  lon: number;
  source: "neshan" | "fallback";
}

export interface RouteInfo {
  distance_m: number;
  duration_min: number;
  /** true = straight-line x1.3 estimate («فاصلهٔ تقریبی») */
  estimated: boolean;
  source: "neshan" | "estimate";
  polyline?: [number, number][] | null;
}

export interface CafesNearby {
  source: "neshan" | "osm" | "local";
  neshan_available?: boolean;
  cafes: {
    name: string;
    lat: number;
    lon: number;
    distance_m?: number | null;
    source?: string;
    label?: string;
    mock?: boolean;
  }[];
}

export interface Followup {
  shop_id: string;
  name: string;
  message: string;
  status: "draft" | "approved" | "sent" | "replied" | "no_response" | "rejected";
  raw_reply?: string | null;
  parsed?: ParsedReply | null;
  simulated: boolean;
  delay_ms: number;
  call_transcript?: string | null;
  target_price?: number | null;
  offer_status?: "accepted" | "countered" | "none" | null;
  counter_price?: number | null;
}

export interface Market {
  market_id: string;
  name_fa: string;
  center?: [number, number];
  centroid?: [number, number] | null;
  radius_m?: number;
  distance_km?: number | null;
  shops_in_market?: number | null;
  offers_in_market?: number | null;
  shops_citywide?: number | null;
  price_median_market?: number | null;
  price_median_city?: number | null;
  hours_external?: Record<string, unknown>;
  hours_label?: string;
  sources?: string[];
  data_backed?: boolean;
  alt?: { market_id: string; name_fa: string; center?: [number, number] } | null;
  category?: string;
  hours_text?: string;
  center_approx?: boolean;
  external?: boolean;
  route_url?: string | null;
}

export interface OocAlternative {
  product_id: string;
  persian_title: string;
  brand_name?: string;
  category_name?: string;
  image?: string | null;
  min_price?: number;
  n_shops?: number;
  offers?: number;
}

export interface Ooc {
  not_found: boolean;
  query: string;
  message_fa: string;
  alternatives: OocAlternative[];
  tips: string[];
  tips_label: string;
  market?: Market | null;
  guide?: {
    category_guess?: string | null;
    tips: string[];
    markets: string[];
    brands_generic: string[];
  } | null;
}

export interface CompareSide {
  label: string;
  n_models: number;
  n_shops: number;
  n_near: number | null;
  min: number;
  max: number;
  median: number;
  replica: boolean;
  best?: {
    product_id: string;
    title?: string;
    min_price?: number;
    n_shops?: number;
  } | null;
}

export interface Compare {
  title: string;
  sides: CompareSide[];
  verdict: string;
  verdict_label: string;
  warning?: string | null;
  checklist: string[];
}

export interface Product {
  product_id: string;
  persian_title: string;
  brand_name?: string;
  category_name?: string;
  image_first?: string | null;
  image_urls?: string | null;
  specs?: string | null;
  n_shops?: number;
  min_price?: number;
  median_price?: number;
}

export interface TripStop {
  order: number;
  shop_id: string;
  name: string;
  address?: string;
  mall?: string | null;
  floor?: string | null;
  lat?: number | null;
  lon?: number | null;
  price?: number;
  arrive_hint?: string;
  walk_min_est?: number | null;
  verified: boolean;
  links?: { neshan?: string | null; balad?: string | null };
}

export interface Trip {
  stops: TripStop[];
  backup?: {
    shop_id: string;
    name: string;
    address?: string;
    lat?: number | null;
    lon?: number | null;
    price?: number;
  } | null;
  cafe?: {
    id: string;
    name: string;
    lat: number;
    lon: number;
    distance_m?: number;
    mock?: boolean;
    label?: string;
  } | null;
  checklist: string[];
  links: {
    neshan?: string | null;
    balad?: string | null;
    google?: string | null;
  };
  summary: string;
  start?: { label: string; lat?: number | null; lon?: number | null };
}

export interface ApiResponse {
  session_id: string;
  phase: Phase;
  messages: Message[];
  pending: Pending;
  trace: TraceEntry[];
  slots: Slots;
  decision?: Decision | null;
  cards?: ProductCard[];
  more?: MoreItem[];
  specialty_market?: Market | null;
  ooc?: Ooc;
  compare?: Compare | null;
  mode?: string;
  product?: Product | null;
  shops?: Shop[];
  followups?: Followup[];
  trip?: Trip | null;
  map_center?: { lat: number; lon: number } | null;
  error?: { code: string; message_fa: string };
}
