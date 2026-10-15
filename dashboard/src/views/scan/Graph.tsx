import { useEffect, useMemo, useRef, useState } from "react";
import { Card, ErrorBox, LabelBadge, Loading, useLoad, useSession } from "../../common";
import { HEADER_H, ROW_H, anchor, curve, layout, nodeOf } from "../../graphLayout";
import type { GraphEdge, GraphView } from "../../types";

type Selection = { kind: "endpoint" | "service"; id: string } | null;

const EDGE_TEXT: Record<GraphEdge["kind"], string> = {
  calls: "calls",
  routes: "routes",
  publishes: "publishes to",
  consumes: "consumed by",
};

/** The demo bank's graph, fetched; it is computed from observed traffic. */
export function DemoGraphTab() {
  const { api } = useSession();
  const { data, error, loading } = useLoad(() => api.demoGraph());
  if (error) return <ErrorBox message={error} />;
  if (loading && !data) return <Loading what="dependency graph" />;
  return data ? <GraphPanel view={data} /> : null;
}

export function GraphPanel({
  view,
  candidates = {},
}: {
  view: GraphView;
  /** endpoint id -> candidate label, drawn in red. */
  candidates?: Record<string, string>;
}) {
  const [selected, setSelected] = useState<Selection>(null);
  const [expanded, setExpanded] = useState<Set<string>>(new Set());
  const lay = useMemo(() => layout(view, expanded), [view, expanded]);
  const canvas = useRef<HTMLDivElement>(null);
  const [zoom, setZoom] = useState(1);
  // Open fitted to the available width, never enlarged past 100%.
  const fit = () => {
    const w = canvas.current?.clientWidth ?? 0;
    setZoom(w > 0 ? Math.max(0.4, Math.min(1, (w - 4) / lay.width)) : 1);
  };
  useEffect(fit, [lay.width]);

  // What the selection lights up: an endpoint's blast radius, or a service's edges.
  const lit = useMemo(() => {
    const services = new Set<string>();
    const endpoints = new Set<string>();
    const edges = new Set<number>();
    if (!selected) return null;
    if (selected.kind === "endpoint") {
      const r = view.radius[selected.id];
      endpoints.add(selected.id);
      services.add(nodeOf(view, selected.id));
      r?.direct_services.forEach((s) => services.add(s));
      r?.indirect_services.forEach((s) => services.add(s));
      r?.affected_endpoints.forEach((a) => endpoints.add(a.endpoint_id));
      view.edges.forEach((e, i) => {
        if (endpoints.has(e.to) && services.has(nodeOf(view, e.from))) edges.add(i);
      });
    } else {
      services.add(selected.id);
      view.edges.forEach((e, i) => {
        const a = nodeOf(view, e.from);
        const b = nodeOf(view, e.to);
        if (a === selected.id || b === selected.id) {
          edges.add(i);
          services.add(a);
          services.add(b);
        }
      });
    }
    return { services, endpoints, edges };
  }, [selected, view]);

  const ep = (id: string) => view.endpoints.find((e) => e.id === id);
  const toggle = (id: string) =>
    setExpanded((prev) => {
      const next = new Set(prev);
      if (next.has(id)) next.delete(id);
      else next.add(id);
      return next;
    });

  if (view.services.length === 0) {
    return (
      <Card title="Dependency graph">
        <p className="muted">Nothing to draw: no services or endpoints were found.</p>
      </Card>
    );
  }

  return (
    <div className="graph-layout">
      <Card title="Dependency graph">
        <p className="muted small graph-basis">
          {view.basis === "traffic"
            ? "Drawn from calls observed in traffic: what does call each endpoint."
            : "Drawn from the code: calls between services, gateway routes and message topics. What can call each endpoint, not proof of what does."}{" "}
          Click an endpoint to see its blast radius, or a service to see its connections.
        </p>
        <div className="graph-toolbar">
          <button className="small secondary" onClick={() => setZoom((z) => Math.min(2, z + 0.2))}
            aria-label="Zoom in">+</button>
          <button className="small secondary" onClick={() => setZoom((z) => Math.max(0.4, z - 0.2))}
            aria-label="Zoom out">-</button>
          <button className="small secondary" onClick={fit}>Fit to width</button>
          <button className="small secondary" onClick={() => setZoom(1)}>Actual size</button>
          {selected && (
            <button className="small secondary" onClick={() => setSelected(null)}>Clear selection</button>
          )}
          <Legend basis={view.basis} />
        </div>
        <div className="graph-canvas" ref={canvas}>
          <svg
            width={lay.width * zoom}
            height={lay.height * zoom}
            viewBox={`0 0 ${lay.width} ${lay.height}`}
            role="img"
            aria-label={`Dependency graph: ${view.stats.services ?? 0} services, ${view.edges.length} connections`}
          >
            <defs>
              {["calls", "routes", "topic", "lit", "dim"].map((k) => (
                <marker key={k} id={`arrow-${k}`} viewBox="0 0 10 10" refX="9" refY="5"
                  markerWidth="7" markerHeight="7" orient="auto-start-reverse">
                  <path d="M 0 0 L 10 5 L 0 10 z" className={`arrowhead arrowhead-${k}`} />
                </marker>
              ))}
            </defs>

            {view.edges.map((e, i) => {
              const p = anchor(view, lay, e);
              if (!p) return null;
              const on = lit?.edges.has(i);
              const dim = lit && !on;
              const kindClass = e.kind === "calls" ? "calls" : e.kind === "routes" ? "routes" : "topic";
              const marker = on ? "lit" : dim ? "dim" : kindClass;
              return (
                <g key={i} className={`edge edge-${kindClass}${on ? " is-lit" : ""}${dim ? " is-dim" : ""}${e.certain === false ? " is-inferred" : ""}`}>
                  <path d={curve(p)} markerEnd={`url(#arrow-${marker})`}>
                    <title>{`${e.from} ${EDGE_TEXT[e.kind]} ${e.to}${e.label ? ` (${e.label})` : ""}\n${e.evidence}`}</title>
                  </path>
                  {e.kind === "routes" && e.label && (
                    <text x={(p.x1 + p.x2) / 2} y={(p.y1 + p.y2) / 2 - 5} className="edge-label">
                      {e.label}
                    </text>
                  )}
                </g>
              );
            })}

            {[...lay.boxes.values()].map((b) => {
              const s = b.service;
              const on = lit?.services.has(s.id);
              const dim = lit && !on;
              const isSel = selected?.kind === "service" && selected.id === s.id;
              return (
                <g key={s.id} className={`gbox gbox-${s.kind}${dim ? " is-dim" : ""}${on ? " is-lit" : ""}${isSel ? " is-selected" : ""}`}>
                  <rect x={b.x} y={b.y} width={b.w} height={b.h} rx={8} className="gbox-body" />
                  <g
                    className="gbox-head"
                    role="button"
                    tabIndex={0}
                    aria-label={`Service ${s.id}`}
                    onClick={() => setSelected({ kind: "service", id: s.id })}
                    onKeyDown={(ev) => {
                      if (ev.key === "Enter" || ev.key === " ") setSelected({ kind: "service", id: s.id });
                    }}
                  >
                    <rect x={b.x} y={b.y} width={b.w} height={HEADER_H} rx={8} className="gbox-header" />
                    <text x={b.x + 12} y={b.y + 22} className="gbox-title">
                      {s.kind === "gateway" ? "gateway: " : ""}
                      {s.id.length > 34 ? `${s.id.slice(0, 33)}...` : s.id}
                    </text>
                  </g>
                  {b.rows.map((id, i) => {
                    const e = ep(id);
                    const y = b.y + HEADER_H + 4 + i * ROW_H;
                    const isSel = selected?.kind === "endpoint" && selected.id === id;
                    const hit = lit?.endpoints.has(id);
                    const label = e ? `${e.method} ${e.path}` : id;
                    return (
                      <g
                        key={id}
                        className={`grow${isSel ? " is-selected" : ""}${hit && !isSel ? " is-hit" : ""}`}
                        role="button"
                        tabIndex={0}
                        aria-label={`Endpoint ${id}`}
                        onClick={() => setSelected({ kind: "endpoint", id })}
                        onKeyDown={(ev) => {
                          if (ev.key === "Enter" || ev.key === " ") setSelected({ kind: "endpoint", id });
                        }}
                      >
                        <rect x={b.x + 4} y={y} width={b.w - 8} height={ROW_H - 2} rx={4} className="grow-bg" />
                        <circle cx={b.x + 14} cy={y + ROW_H / 2 - 1} r={4}
                          className={`dot dot-${(e?.label ?? (candidates[id] ? "candidate" : e?.isolated ? "isolated" : "depended")).toLowerCase()}`} />
                        <text x={b.x + 24} y={y + 15} className="grow-text">
                          <title>{label}</title>
                          {label.length > 36 ? `${label.slice(0, 35)}...` : label}
                        </text>
                      </g>
                    );
                  })}
                  {b.toggle && (
                    <text
                      x={b.x + 12}
                      y={b.y + HEADER_H + 4 + b.rows.length * ROW_H + 15}
                      className="gbox-more"
                      role="button"
                      tabIndex={0}
                      onClick={() => toggle(s.id)}
                      onKeyDown={(ev) => {
                        if (ev.key === "Enter") toggle(s.id);
                      }}
                    >
                      {b.hidden > 0 ? `+ ${b.hidden} more endpoint(s)` : "show fewer"}
                    </text>
                  )}
                </g>
              );
            })}
          </svg>
        </div>
      </Card>

      <Card title={selected ? (selected.kind === "endpoint" ? "Blast radius" : "Service") : "About this graph"}>
        {!selected && <About view={view} />}
        {selected?.kind === "endpoint" && <EndpointDetail view={view} id={selected.id} />}
        {selected?.kind === "service" && <ServiceDetail view={view} id={selected.id} />}
      </Card>
    </div>
  );
}

function Legend({ basis }: { basis: GraphView["basis"] }) {
  return (
    <ul className="graph-legend" aria-label="Legend">
      <li><span className="lg lg-calls" /> calls</li>
      {basis === "code" && <li><span className="lg lg-routes" /> gateway route</li>}
      {basis === "code" && <li><span className="lg lg-topic" /> message topic</li>}
      <li><span className="dot-inline dot-depended" /> something depends on it</li>
      <li><span className="dot-inline dot-isolated" /> nothing found depending on it</li>
      {basis === "code" && <li><span className="dot-inline dot-candidate" /> zombie candidate</li>}
    </ul>
  );
}

function About({ view }: { view: GraphView }) {
  const s = view.stats;
  return (
    <div className="stack">
      <dl className="facts">
        <dt>Services</dt><dd>{s.services ?? 0}</dd>
        <dt>Endpoints</dt><dd>{s.endpoints ?? 0}</dd>
        <dt>Calls between services</dt><dd>{s.calls ?? 0}</dd>
        {view.basis === "code" && (<><dt>Gateway routes</dt><dd>{s.routes ?? 0}</dd>
          <dt>Message topics</dt><dd>{s.topics ?? 0}</dd></>)}
        <dt>Nothing depends on</dt><dd>{s.isolated ?? 0} endpoint(s)</dd>
      </dl>
      {view.notes.map((n) => (
        <p key={n} className="small">{n}</p>
      ))}
    </div>
  );
}

function EndpointDetail({ view, id }: { view: GraphView; id: string }) {
  const e = view.endpoints.find((x) => x.id === id);
  const r = view.radius[id];
  if (!e || !r) return <p className="muted">Unknown endpoint.</p>;
  const incoming = view.edges.filter((x) => x.to === id);
  const byHop = new Map<number, string[]>();
  r.affected_endpoints.forEach((a) => byHop.set(a.hop, [...(byHop.get(a.hop) ?? []), a.endpoint_id]));

  return (
    <div className="stack">
      <p>
        <code>
          <span className="method">{e.method}</span> {e.path}
        </code>{" "}
        {e.label && <LabelBadge label={e.label} />}
      </p>
      <p className="small muted">served by {e.service}</p>
      {r.isolated ? (
        <p className="good-text">
          Isolated: nothing {view.basis === "traffic" ? "observed" : "in this code"} depends on
          it. {view.basis === "code"
            ? "Callers outside the repository would not show here."
            : "A caller silent during the capture window would not show here."}
        </p>
      ) : (
        <p>
          <strong className={r.severity === "severe" || r.severity === "broad" ? "bad-text" : "warn-text"}>
            {r.severity}
          </strong>
          : removing it breaks {r.direct_services.length} service(s) directly
          {r.indirect_services.length ? ` and ${r.indirect_services.length} more further out` : ""}, and{" "}
          {r.affected_endpoints.length} endpoint(s) of theirs degrade
          {r.depth_reached ? `, ${r.depth_reached} hop(s) deep` : ""}.
        </p>
      )}
      {incoming.length > 0 && (
        <div>
          <h3>Called by</h3>
          <ul className="evidence-list">
            {incoming.map((x, i) => (
              <li key={i}>
                <strong>{x.from}</strong>
                <div className="small muted">{x.evidence}</div>
              </li>
            ))}
          </ul>
        </div>
      )}
      {r.indirect_services.length > 0 && (
        <div>
          <h3>Further out</h3>
          <p className="small">{r.indirect_services.join(", ")}</p>
        </div>
      )}
      {byHop.size > 0 && (
        <div>
          <h3>Endpoints that degrade</h3>
          {[...byHop.entries()].sort((a, b) => a[0] - b[0]).map(([hop, ids]) => (
            <div key={hop}>
              <p className="small muted">hop {hop}</p>
              <ul className="findings">
                {ids.map((x) => (
                  <li key={x}><code>{x}</code></li>
                ))}
              </ul>
            </div>
          ))}
        </div>
      )}
      {e.exposed_via.length > 0 && (
        <div>
          <h3>Exposed through</h3>
          <ul className="findings">
            {e.exposed_via.map((x) => (
              <li key={x}><code>{x}</code></li>
            ))}
          </ul>
        </div>
      )}
    </div>
  );
}

function ServiceDetail({ view, id }: { view: GraphView; id: string }) {
  const s = view.services.find((x) => x.id === id);
  if (!s) return <p className="muted">Unknown service.</p>;
  const out = view.edges.filter((e) => nodeOf(view, e.from) === id);
  const inc = view.edges.filter((e) => nodeOf(view, e.to) === id && nodeOf(view, e.from) !== id);
  const kind = { service: "service", gateway: "gateway", topic: `${s.broker ?? "message"} topic`, external: "outside the repository" }[s.kind];
  const list = (edges: GraphEdge[], dir: "out" | "in") =>
    edges.map((e, i) => (
      <li key={i}>
        {dir === "out" ? EDGE_TEXT[e.kind] : `${e.from} ${EDGE_TEXT[e.kind]}`}{" "}
        {dir === "out" && <code>{e.label ? `${e.to} (${e.label})` : e.to}</code>}
        {dir === "in" && e.to !== id && <code> {e.to}</code>}
        {e.certain === false && <span className="muted small"> (inferred)</span>}
        <div className="small muted">{e.evidence}</div>
      </li>
    ));
  return (
    <div className="stack">
      <p>
        <strong>{s.id}</strong> <span className="muted small">({kind})</span>
      </p>
      {s.endpoints.length > 0 && <p className="small">{s.endpoints.length} endpoint(s)</p>}
      {out.length > 0 && (<div><h3>Outgoing</h3><ul className="evidence-list">{list(out, "out")}</ul></div>)}
      {inc.length > 0 && (<div><h3>Incoming</h3><ul className="evidence-list">{list(inc, "in")}</ul></div>)}
      {!out.length && !inc.length && <p className="muted small">No connections found.</p>}
    </div>
  );
}
