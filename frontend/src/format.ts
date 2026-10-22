const FA_DIGITS = "۰۱۲۳۴۵۶۷۸۹";

export function faDigits(value: string | number): string {
  return String(value).replace(/\d/g, (digit) => FA_DIGITS[Number(digit)]);
}

/** 3150000 -> «۳٬۱۵۰٬۰۰۰» */
export function formatPrice(value?: number | null): string {
  if (!value && value !== 0) return "";
  return faDigits(value.toLocaleString("en-US")).replace(/,/g, "٬");
}

/** 3150000 -> «۳٫۱۵ میلیون» */
export function formatPriceShort(value?: number | null): string {
  if (!value && value !== 0) return "";
  if (value >= 1_000_000) {
    const millions = value / 1_000_000;
    const text = millions >= 100 ? millions.toFixed(0) : millions.toFixed(2).replace(/0$/, "");
    return `${faDigits(text.replace(".", "٫"))} میلیون`;
  }
  if (value >= 1000) {
    const thousands = value / 1000;
    const text = thousands >= 100 ? thousands.toFixed(0) : thousands.toFixed(1).replace(/\.0$/, "");
    return `${faDigits(text.replace(".", "٫"))} هزار`;
  }
  return faDigits(value);
}

export function priceWithUnit(value?: number | null): string {
  if (!value && value !== 0) return "";
  return `${formatPrice(value)} تومان`;
}

/** Translate the curated (English) opening-hours strings and localize digits. */
const HOURS_TRANSLATIONS: [string, string][] = [
  ["closed (open Fridays of Esfand)", "تعطیل (جمعه‌های اسفند باز)"],
  ["shop-dependent (unverified)", "بسته به فروشگاه (تأییدنشده)"],
  ["open Fridays of Esfand", "جمعه‌های اسفند باز"],
  ["Sat–Thu", "شنبه تا پنجشنبه"],
  ["Sat-Thu", "شنبه تا پنجشنبه"],
  ["Sat–Wed", "شنبه تا چهارشنبه"],
  ["Sat-Wed", "شنبه تا چهارشنبه"],
  ["Fridays shorter", "جمعه‌ها کوتاه‌تر"],
  ["only Fridays", "فقط جمعه‌ها"],
  ["street-front passages", "راسته‌های خیابانی"],
  ["sources differ", "منابع متفاوت"],
  ["shop-dependent", "بسته به فروشگاه"],
  ["unverified", "تأییدنشده"],
  ["inner", "داخل"],
  ["daily", "هر روز"],
  ["Fri", "جمعه"],
  ["Thu", "پنجشنبه"],
  ["Wed", "چهارشنبه"],
  ["Tue", "سه‌شنبه"],
  ["Mon", "دوشنبه"],
  ["Sun", "یکشنبه"],
  ["Sat", "شنبه"],
  ["closed", "تعطیل"],
];

export function faHours(value?: string | null): string {
  if (!value) return "";
  let text = String(value);
  for (const [english, persian] of HOURS_TRANSLATIONS) {
    text = text.split(english).join(persian);
  }
  return faDigits(text.replace(/~/g, "حدود ").replace(/\s+/g, " ")).trim();
}

export function formatDistance(distanceM?: number | null): string {
  if (distanceM === null || distanceM === undefined) return "نامشخص";
  if (distanceM < 1000) return `${faDigits(distanceM)} متر`;
  const km = distanceM / 1000;
  const text = km.toFixed(1).replace(".", "٫");
  return `${faDigits(text)} کیلومتر`;
}

export function formatDays(days?: number | null): string {
  if (days === null || days === undefined) return "";
  if (days === 0) return "امروز";
  if (days === 1) return "دیروز";
  return `${faDigits(days)} روز پیش`;
}

export function formatTime(ms?: number): string {
  if (!ms && ms !== 0) return "";
  if (ms < 1000) return `${faDigits(ms)} میلی‌ثانیه`;
  return `${faDigits((ms / 1000).toFixed(1))} ثانیه`;
}

export function parseSpecs(specs?: string | null): { key: string; value: string; section?: string }[] {
  if (!specs) return [];
  try {
    const parsed = JSON.parse(specs);
    if (!Array.isArray(parsed)) return [];
    return parsed
      .filter((item) => item && typeof item === "object")
      .map((item) => ({
        key: String(item.key ?? "").trim(),
        value: String(item.value ?? "").trim(),
        section: String(item.section ?? "").trim(),
      }))
      .filter((item) => item.value);
  } catch {
    return [];
  }
}

export function parseImageList(images?: string | null): string[] {
  if (!images) return [];
  try {
    const parsed = JSON.parse(images);
    return Array.isArray(parsed) ? parsed.filter(Boolean) : [];
  } catch {
    return [];
  }
}
