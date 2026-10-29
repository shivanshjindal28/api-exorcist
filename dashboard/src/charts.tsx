/* Charts drawn as plain SVG and CSS. A charting library would bring inline
 * styles the CSP refuses and a dependency to audit; these few shapes need
 * neither. Colour comes from classes (tone-*), so both themes apply without
 * code. Motion (motion.ts) is off for reduced-motion viewers and in tests. */

import { useCallback, useEffect, useRef, useState } from "react";
import type { ReactNode } from "react";
import { motionOK, useCountUp, useEntered, useTilt } from "./motion";

export interface Slice {
  key: string;
  label: string;
  value: number;
  /** A tone from the severity scale: crit, high, med, low, ok, info, pend. */
  tone: string;
}

/** A number that counts up to its value; anything else is shown as it is. */
export function CountUp({ value }: { value: number | string }) {
  return typeof value === "number" ? <CountUpNumber value={value} /> : <>{value}</>;
}

function CountUpNumber({ value }: { value: number }) {
  return <>{useCountUp(value).toLocaleString()}</>;
}

const R = 52;
const C = 2 * Math.PI * R;
/** The ring is drawn this many times, one under the other, to give it depth. */
const DEPTH = 7;

/**
 * The estate as a ring, tilted back in perspective with real depth, turning
 * slowly. It draws itself in, tilts toward the pointer, and a slice (or its
 * legend row) under the pointer lifts out and puts its own count in the centre.
 */
export function Donut({ slices, centre, caption }: { slices: Slice[]; centre: ReactNode; caption: string }) {
  const total = slices.reduce((n, s) => n + s.value, 0);
  const entered = useEntered();
  const [active, setActiveNow] = useState<string | null>(null);
  // Moving from one slice to the next crosses a hairline gap; clearing the
  // highlight there made it flicker. A slice takes it at once, and it is let
  // go only if the pointer has not reached another slice a moment later.
  const clearing = useRef<number | undefined>(undefined);
  const setActive = useCallback((key: string | null) => {
    window.clearTimeout(clearing.current);
    if (key === null) clearing.current = window.setTimeout(() => setActiveNow(null), 140);
    else setActiveNow(key);
  }, []);
  useEffect(() => () => window.clearTimeout(clearing.current), []);
  const tilt = useTilt<HTMLDivElement>(10);
  const live = slices.filter((s) => s.value > 0);
  const on = live.find((s) => s.key === active) ?? null;

  let offset = 0;
  const arcs = live.map((s, i) => {
    const len = (s.value / total) * C;
    const gap = s.value === total ? 0 : Math.min(2, len / 2);
    const arc = { s, i, len: Math.max(len - gap, 0.01), offset };
    offset += len;
    return arc;
  });

  const ring = (layer: number) => (
    <svg
      key={layer}
      className={`donut-layer ${layer === 0 ? "is-top" : "is-depth"}`}
      viewBox="0 0 140 140"
      aria-hidden={layer !== 0}
      // Each layer sits a little further back; the stack reads as the ring's edge.
      style={{ transform: `translateZ(${-layer * 2}px)` }}
    >
      {layer === 0 && <circle className="donut-track" cx="70" cy="70" r={R} />}
      {total > 0 &&
        arcs.map(({ s, i, len, offset: o }) => (
          <circle
            key={s.key}
            className={`donut-seg tone-${s.tone} ${on ? (on.key === s.key ? "is-active" : "is-dim") : ""}`}
            cx="70"
            cy="70"
            r={R}
            strokeDasharray={`${entered ? len : 0} ${C}`}
            strokeDashoffset={-o}
            transform="rotate(-90 70 70)"
            style={{ transitionDelay: `${i * 0.12}s` }}
            onMouseEnter={layer === 0 ? () => setActive(s.key) : undefined}
            onMouseLeave={layer === 0 ? () => setActive(null) : undefined}
          />
        ))}
    </svg>
  );

  return (
    <div className="donut">
      <div
        className={`donut-stage ${on ? "is-hovered" : ""}`}
        role="img"
        aria-label={caption}
        ref={tilt.ref}
        onMouseMove={tilt.onMouseMove}
        onMouseLeave={() => {
          tilt.onMouseLeave();
          setActive(null);
        }}
      >
        <div className={`donut-3d ${motionOK() ? "is-turning" : ""}`}>
          {Array.from({ length: DEPTH }, (_, layer) => ring(DEPTH - 1 - layer))}
        </div>
        <div className="donut-centre" aria-live="polite">
          {on ? (
            <>
              <strong className={`tone-text tone-${on.tone}`}>{on.value}</strong>
              <span>{on.label}</span>
            </>
          ) : (
            centre
          )}
        </div>
      </div>
      <ul className="donut-legend">
        {slices.map((s) => (
          <li
            key={s.key}
            className={on ? (on.key === s.key ? "is-active" : "is-dim") : ""}
            onMouseEnter={() => s.value > 0 && setActive(s.key)}
            onMouseLeave={() => setActive(null)}
          >
            <span className={`swatch tone-${s.tone}`} aria-hidden="true" />
            <span className="donut-label">{s.label}</span>
            <span className="donut-value num">
              <CountUp value={s.value} />
            </span>
            <span className="donut-pct num muted">{total ? `${Math.round((s.value / total) * 100)}%` : "-"}</span>
          </li>
        ))}
      </ul>
    </div>
  );
}

export interface Bar {
  key: string;
  label: ReactNode;
  value: number;
  /** The part of `value` that is flagged, drawn in the strong tone. */
  part: number;
}

/** Horizontal bars that grow in, each with its flagged share drawn over the whole. */
export function BarList({ bars, partLabel, wholeLabel }: { bars: Bar[]; partLabel: string; wholeLabel: string }) {
  const max = Math.max(1, ...bars.map((b) => b.value));
  const entered = useEntered();
  return (
    <div className="barlist">
      <ul>
        {bars.map((b, i) => (
          <li key={b.key} title={`${b.part} of ${b.value} flagged`}>
            <span className="barlist-label">{b.label}</span>
            <span className="barlist-track" aria-hidden="true">
              <span
                className="barlist-whole"
                style={{ width: entered ? `${(b.value / max) * 100}%` : "0%", transitionDelay: `${i * 0.07}s` }}
              >
                <span className="barlist-part" style={{ width: `${b.value ? (b.part / b.value) * 100 : 0}%` }} />
              </span>
            </span>
            <span className="barlist-value num">
              {b.part > 0 && <span className="bad-text">{b.part}</span>}
              {b.part > 0 && <span className="muted"> / </span>}
              {b.value}
            </span>
          </li>
        ))}
      </ul>
      <p className="barlist-key small muted">
        <span className="swatch tone-crit" aria-hidden="true" /> {partLabel}
        <span className="swatch tone-track" aria-hidden="true" /> {wholeLabel}
      </p>
    </div>
  );
}

/** How a figure moved since the previous scan. More of a bad thing is red. */
export function Delta({ now, before, worseWhenUp = true }: { now: number; before: number; worseWhenUp?: boolean }) {
  const d = now - before;
  if (d === 0) return <span className="delta delta-flat">no change</span>;
  const up = d > 0;
  const bad = up === worseWhenUp;
  return (
    <span className={`delta ${bad ? "delta-bad" : "delta-good"}`}>
      <span aria-hidden="true">{up ? "▲" : "▼"}</span> {Math.abs(d)}
      <span className="visually-hidden">{up ? " more" : " fewer"}</span> since last scan
    </span>
  );
}

/**
 * Signed reasons as bars: what pushes an endpoint towards removal grows to the
 * right in red, what holds it back grows left in green, and the sum is the score.
 */
export function Contributions({
  items,
  total,
  totalLabel = "score",
}: {
  items: { text: string; weight: number }[];
  total: number;
  totalLabel?: string;
}) {
  const max = Math.max(1, ...items.map((i) => Math.abs(i.weight)));
  const entered = useEntered();
  return (
    <div className="contrib">
      <ul>
        {items.map((i, n) => (
          <li key={i.text} className={i.weight < 0 ? "against" : "for"}>
            <span className="contrib-weight num">{i.weight > 0 ? `+${i.weight}` : i.weight}</span>
            <span className="contrib-bar" aria-hidden="true">
              <span
                className="contrib-fill"
                style={{ width: entered ? `${(Math.abs(i.weight) / max) * 100}%` : "0%", transitionDelay: `${n * 0.08}s` }}
              />
            </span>
            <span className="contrib-text">{i.text}</span>
          </li>
        ))}
      </ul>
      <div className="contrib-total">
        <span>{totalLabel}</span>
        <strong className="num">
          <CountUp value={total} />
        </strong>
      </div>
    </div>
  );
}
