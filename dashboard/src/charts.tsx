/* Charts drawn as plain SVG. A charting library would bring inline styles the
 * CSP refuses and a dependency to audit; these few shapes need neither. Colour
 * comes from classes (tone-*), so both themes apply without code. */

import type { ReactNode } from "react";

export interface Slice {
  key: string;
  label: string;
  value: number;
  /** A tone from the severity scale: crit, high, med, low, ok, info, pend. */
  tone: string;
}

/** A ring split into slices, with the total in the middle and a legend beside it. */
export function Donut({ slices, centre, caption }: { slices: Slice[]; centre: ReactNode; caption: string }) {
  const total = slices.reduce((n, s) => n + s.value, 0);
  const r = 52;
  const c = 2 * Math.PI * r;
  let offset = 0;
  return (
    <div className="donut">
      <svg viewBox="0 0 140 140" width="168" height="168" role="img" aria-label={caption}>
        <circle className="donut-track" cx="70" cy="70" r={r} />
        {total > 0 &&
          slices
            .filter((s) => s.value > 0)
            .map((s) => {
              const len = (s.value / total) * c;
              // A hairline gap between slices, unless a slice is the whole ring.
              const gap = s.value === total ? 0 : Math.min(2, len / 2);
              const seg = (
                <circle
                  key={s.key}
                  className={`donut-seg tone-${s.tone}`}
                  cx="70"
                  cy="70"
                  r={r}
                  strokeDasharray={`${Math.max(len - gap, 0.01)} ${c}`}
                  strokeDashoffset={-offset}
                  transform="rotate(-90 70 70)"
                />
              );
              offset += len;
              return seg;
            })}
        <foreignObject x="30" y="42" width="80" height="56">
          <div className="donut-centre">{centre}</div>
        </foreignObject>
      </svg>
      <ul className="donut-legend">
        {slices.map((s) => (
          <li key={s.key}>
            <span className={`swatch tone-${s.tone}`} aria-hidden="true" />
            <span className="donut-label">{s.label}</span>
            <span className="donut-value num">{s.value}</span>
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

/** Horizontal bars, each with its flagged share drawn over the whole. */
export function BarList({ bars, partLabel, wholeLabel }: { bars: Bar[]; partLabel: string; wholeLabel: string }) {
  const max = Math.max(1, ...bars.map((b) => b.value));
  return (
    <div className="barlist">
      <ul>
        {bars.map((b) => (
          <li key={b.key}>
            <span className="barlist-label">{b.label}</span>
            <span className="barlist-track" aria-hidden="true">
              <span className="barlist-whole" style={{ width: `${(b.value / max) * 100}%` }}>
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
  return (
    <div className="contrib">
      <ul>
        {items.map((i) => (
          <li key={i.text} className={i.weight < 0 ? "against" : "for"}>
            <span className="contrib-weight num">{i.weight > 0 ? `+${i.weight}` : i.weight}</span>
            <span className="contrib-bar" aria-hidden="true">
              <span className="contrib-fill" style={{ width: `${(Math.abs(i.weight) / max) * 100}%` }} />
            </span>
            <span className="contrib-text">{i.text}</span>
          </li>
        ))}
      </ul>
      <div className="contrib-total">
        <span>{totalLabel}</span>
        <strong className="num">{total}</strong>
      </div>
    </div>
  );
}
