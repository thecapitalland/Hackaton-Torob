import { useEffect, useState } from "react";

/** Reactive media query hook (SSR safe). */
export function useMediaQuery(query: string): boolean {
  const [matches, setMatches] = useState(() => {
    if (typeof window === "undefined" || !window.matchMedia) return false;
    return window.matchMedia(query).matches;
  });

  useEffect(() => {
    if (typeof window === "undefined" || !window.matchMedia) return;
    const list = window.matchMedia(query);
    const handler = (event: MediaQueryListEvent) => setMatches(event.matches);
    setMatches(list.matches);
    list.addEventListener("change", handler);
    return () => list.removeEventListener("change", handler);
  }, [query]);

  return matches;
}

/** < 768px : one column · 768-1279 : chat + cards · >= 1280 : two panes */
export function useBreakpoint() {
  const isMobile = useMediaQuery("(max-width: 767px)");
  const isWide = useMediaQuery("(min-width: 1280px)");
  return { isMobile, isWide };
}
