// Laying out a dependency graph for drawing, with no layout library: React is
// the dashboard's only runtime dependency, and a layered layout of a few dozen
// boxes does not need one.
//
// Services are placed in columns by dependency depth: anything that calls,
// routes to or publishes for another node sits to its left, so arrows mostly
// run left to right and the column a service sits in says how far upstream it
// is. Within a column, boxes are ordered by where their neighbours sit (one
// barycentric pass), which removes most crossings on graphs this size.

import type { GraphEdge, GraphService, GraphView } from "./types";

export const BOX_W = 280;
export const TOPIC_W = 230;
export const HEADER_H = 34;
export const ROW_H = 22;
export const GAP_X = 150;
export const GAP_Y = 26;
export const MARGIN = 24;
export const MAX_ROWS = 10;

export interface Box {
  service: GraphService;
  x: number;
  y: number;
  w: number;
  h: number;
  layer: number;
  rows: string[];            // endpoint ids shown, in order
  hidden: number;            // endpoints not shown (collapsed)
  toggle: boolean;           // a "+ n more" / "show fewer" row is drawn
}

export interface Layout {
  boxes: Map<string, Box>;
  width: number;
  height: number;
}

/** The service an edge's endpoint belongs to, or the node itself. */
export function nodeOf(view: GraphView, id: string): string {
  return view.endpoints.find((e) => e.id === id)?.service ?? id;
}

/** Service-level arrows: caller -> owning service, gateway -> service, and so on. */
export function serviceEdges(view: GraphView): [string, string][] {
  const out = new Set<string>();
  for (const e of view.edges) {
    const a = nodeOf(view, e.from);
    const b = nodeOf(view, e.to);
    if (a !== b) out.add(`${a}\u0000${b}`);
  }
  return [...out].map((k) => k.split("\u0000") as [string, string]);
}

/** Longest-path layering, cycle-safe: relaxation stops after n passes. */
export function layers(ids: string[], edges: [string, string][]): Map<string, number> {
  const layer = new Map(ids.map((id) => [id, 0]));
  for (let pass = 0; pass < ids.length; pass++) {
    let changed = false;
    for (const [a, b] of edges) {
      const want = (layer.get(a) ?? 0) + 1;
      if ((layer.get(b) ?? 0) < want && want < ids.length) {
        layer.set(b, want);
        changed = true;
      }
    }
    if (!changed) break;
  }
  return layer;
}

function rowsFor(view: GraphView, s: GraphService, expanded: boolean): [string[], number] {
  const linked = new Set(view.edges.flatMap((e) => [e.from, e.to]));
  const ids = [...s.endpoints].sort(
    (a, b) => Number(linked.has(b)) - Number(linked.has(a)) || a.localeCompare(b),
  );
  if (expanded || ids.length <= MAX_ROWS) return [ids, 0];
  return [ids.slice(0, MAX_ROWS), ids.length - MAX_ROWS];
}

export function layout(view: GraphView, expanded: Set<string> = new Set()): Layout {
  const ids = view.services.map((s) => s.id);
  const edges = serviceEdges(view);
  const layer = layers(ids, edges);
  const columns = new Map<number, GraphService[]>();
  for (const s of view.services) {
    const l = layer.get(s.id) ?? 0;
    columns.set(l, [...(columns.get(l) ?? []), s]);
  }

  const boxes = new Map<string, Box>();
  let height = 0;
  const xs: number[] = [];
  let x = MARGIN;
  const order = [...columns.keys()].sort((a, b) => a - b);
  for (const l of order) {
    xs[l] = x;
    const widest = Math.max(...(columns.get(l) ?? []).map((s) => (s.kind === "topic" ? TOPIC_W : BOX_W)));
    x += widest + GAP_X;
  }

  for (const l of order) {
    let col = columns.get(l) ?? [];
    // Barycentre: sit near the boxes you are connected to in earlier columns.
    const centre = (id: string) => {
      const ys = edges
        .filter(([a, b]) => b === id && boxes.has(a))
        .map(([a]) => {
          const box = boxes.get(a)!;
          return box.y + box.h / 2;
        });
      return ys.length ? ys.reduce((p, q) => p + q, 0) / ys.length : Number.MAX_SAFE_INTEGER;
    };
    col = [...col].sort((a, b) => centre(a.id) - centre(b.id) || a.id.localeCompare(b.id));
    let y = MARGIN;
    for (const s of col) {
      const [rows, hidden] = rowsFor(view, s, expanded.has(s.id));
      const toggle = s.endpoints.length > MAX_ROWS;
      const h = HEADER_H + (rows.length + (toggle ? 1 : 0)) * ROW_H + (rows.length ? 8 : 0);
      const w = s.kind === "topic" ? TOPIC_W : BOX_W;
      boxes.set(s.id, { service: s, x: xs[l]!, y, w, h, layer: l, rows, hidden, toggle });
      y += h + GAP_Y;
    }
    height = Math.max(height, y);
  }
  return { boxes, width: x - GAP_X + MARGIN, height: height + MARGIN };
}

/** Where an edge leaves its source and lands on its target. */
export function anchor(
  view: GraphView,
  lay: Layout,
  e: GraphEdge,
): { x1: number; y1: number; x2: number; y2: number } | null {
  const src = lay.boxes.get(nodeOf(view, e.from));
  const dst = lay.boxes.get(nodeOf(view, e.to));
  if (!src || !dst) return null;
  const rowY = (box: Box, id: string) => {
    const i = box.rows.indexOf(id);
    return i < 0 ? box.y + HEADER_H / 2 : box.y + HEADER_H + i * ROW_H + ROW_H / 2 + 4;
  };
  const forward = dst.x >= src.x + src.w;
  return {
    x1: forward ? src.x + src.w : src.x,
    y1: rowY(src, e.from),
    x2: forward ? dst.x : dst.x + dst.w,
    y2: rowY(dst, e.to),
  };
}

export function curve(p: { x1: number; y1: number; x2: number; y2: number }): string {
  const dx = Math.max(60, Math.abs(p.x2 - p.x1) / 2);
  const dir = p.x2 >= p.x1 ? 1 : -1;
  return `M ${p.x1} ${p.y1} C ${p.x1 + dx * dir} ${p.y1}, ${p.x2 - dx * dir} ${p.y2}, ${p.x2} ${p.y2}`;
}
