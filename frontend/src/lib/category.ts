/** Category-specific pill icon (the UI used to always show 🎧). */
export function categoryIcon(category?: string | null): string {
  const value = category ?? "";
  if (value.includes("گوشی") || value.includes("موبایل")) return "📱";
  if (value.includes("لپ") || value.includes("نوت")) return "💻";
  if (value.includes("هدفون") || value.includes("هدست") || value.includes("هندزفری")) {
    return "🎧";
  }
  return "🛍️";
}
