import { useEffect, useLayoutEffect, useRef, useState } from "react";

/**
 * Sets a CSS custom property on an element. Dynamic geometry (the split
 * position, a step's fill) goes through custom properties so the
 * stylesheets keep every other value in tokens and no element carries a
 * style attribute.
 */
export function useCssVar<T extends HTMLElement>(name: string, value: string) {
  const ref = useRef<T>(null);
  useLayoutEffect(() => {
    ref.current?.style.setProperty(name, value);
  }, [name, value]);
  return ref;
}

export function useMediaQuery(query: string): boolean {
  const [matches, setMatches] = useState(() => window.matchMedia(query).matches);
  useEffect(() => {
    const mq = window.matchMedia(query);
    const onChange = () => setMatches(mq.matches);
    mq.addEventListener("change", onChange);
    onChange();
    return () => mq.removeEventListener("change", onChange);
  }, [query]);
  return matches;
}

export function formatDate(unix: number): string {
  const d = new Date(unix * 1000);
  if (d.toDateString() === new Date().toDateString()) {
    return d.toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" });
  }
  return d.toLocaleDateString([], { year: "numeric", month: "short", day: "numeric" });
}
