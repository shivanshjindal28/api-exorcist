/* Motion, in one place, and only where it helps read the data: numbers that
 * count up to their value, shapes that draw themselves in, a card that tilts
 * toward the pointer. All of it is off for anyone who asks the system for
 * reduced motion, and under the test runner, so what a test sees is final. */

import { useCallback, useEffect, useRef, useState } from "react";
import type { MouseEvent as ReactMouseEvent } from "react";

export function motionOK(): boolean {
  if (typeof window === "undefined") return false;
  if (/jsdom/i.test(window.navigator.userAgent)) return false;
  return !window.matchMedia?.("(prefers-reduced-motion: reduce)").matches;
}

/** A number that rises from 0 to `value` over `ms`, easing out. */
export function useCountUp(value: number, ms = 900): number {
  const [shown, setShown] = useState(() => (motionOK() ? 0 : value));
  useEffect(() => {
    if (!motionOK()) {
      setShown(value);
      return;
    }
    let raf = 0;
    const start = performance.now();
    const from = 0;
    const tick = (t: number) => {
      const p = Math.min(1, (t - start) / ms);
      const eased = 1 - Math.pow(1 - p, 3);
      setShown(Math.round(from + (value - from) * eased));
      if (p < 1) raf = requestAnimationFrame(tick);
    };
    raf = requestAnimationFrame(tick);
    return () => cancelAnimationFrame(raf);
  }, [value, ms]);
  return shown;
}

/** True one frame after mount: lets CSS transitions run from a starting state. */
export function useEntered(): boolean {
  const [entered, setEntered] = useState(() => !motionOK());
  useEffect(() => {
    if (entered) return;
    const raf = requestAnimationFrame(() => requestAnimationFrame(() => setEntered(true)));
    return () => cancelAnimationFrame(raf);
  }, [entered]);
  return entered;
}

/**
 * Tilt an element toward the pointer, up to `max` degrees, the way a physical
 * card would. Spread the returned props onto the element.
 */
export function useTilt<T extends HTMLElement>(max = 8) {
  const ref = useRef<T>(null);
  const onMouseMove = useCallback(
    (e: ReactMouseEvent<T>) => {
      const el = ref.current;
      if (!el || !motionOK()) return;
      const r = el.getBoundingClientRect();
      const x = (e.clientX - r.left) / r.width - 0.5;
      const y = (e.clientY - r.top) / r.height - 0.5;
      el.style.transform = `perspective(900px) rotateX(${(-y * max).toFixed(2)}deg) rotateY(${(x * max).toFixed(2)}deg)`;
      el.style.setProperty("--glare-x", `${((x + 0.5) * 100).toFixed(1)}%`);
      el.style.setProperty("--glare-y", `${((y + 0.5) * 100).toFixed(1)}%`);
    },
    [max],
  );
  const onMouseLeave = useCallback(() => {
    const el = ref.current;
    if (el) el.style.transform = "";
  }, []);
  return { ref, onMouseMove, onMouseLeave };
}
