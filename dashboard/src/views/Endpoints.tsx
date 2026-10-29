import { useMemo, useState } from "react";
import {
  Card,
  ErrorBox,
  LabelBadge,
  Loading,
  MethodPath,
  SortTh,
  pct,
  useLoad,
  useSession,
  useSort,
} from "../common";
import type { Evidence, InventoryRecord, Verdict } from "../types";
import { ScoreTable } from "./explain";
import { ALL_SOURCES, SourceChips } from "./scan/shared";

const LABELS = ["ALL", "ZOMBIE", "ORPHANED", "DEPRECATED", "ACTIVE", "INDETERMINATE"];

interface Row {
  verdict: Verdict;
  record: InventoryRecord | undefined;
}

export function Endpoints() {
  const { api } = useSession();
  const { data, error, loading } = useLoad(async () => {
    const [verdicts, inventory] = await Promise.all([api.verdicts(), api.inventory()]);
    const byId = new Map(inventory.map((r) => [r.endpoint_id, r]));
    return verdicts.map((v): Row => ({ verdict: v, record: byId.get(v.endpoint_id) }));
  });
  const [label, setLabel] = useState("ALL");
  const [query, setQuery] = useState("");
  const [selected, setSelected] = useState<string | null>(null);
  const [sort, onSort] = useSort<"endpoint" | "label" | "confidence" | "risk" | "seen">({ key: "risk", dir: "desc" });

  const rows = useMemo(() => {
    const q = query.trim().toLowerCase();
    const value = ({ verdict: v, record: r }: Row): string | number =>
      sort.key === "endpoint" ? v.endpoint_id
        : sort.key === "label" ? v.label
          : sort.key === "confidence" ? v.confidence
            : sort.key === "seen" ? r?.seen_by.length ?? 0
              : v.risk_score;
    const dir = sort.dir === "asc" ? 1 : -1;
    return (data ?? [])
      .filter((r) => label === "ALL" || r.verdict.label === label)
      .filter(
        (r) =>
          !q ||
          r.verdict.endpoint_id.toLowerCase().includes(q) ||
          (r.record?.service ?? "").toLowerCase().includes(q),
      )
      .sort((a, b) => {
        const va = value(a);
        const vb = value(b);
        const c = typeof va === "number" && typeof vb === "number" ? va - vb : String(va).localeCompare(String(vb));
        return c * dir || a.verdict.endpoint_id.localeCompare(b.verdict.endpoint_id);
      });
  }, [data, label, query, sort]);

  if (error) return <ErrorBox message={error} />;
  if (loading && !data) return <Loading what="endpoints" />;

  return (
    <div className="split">
      <Card title={`Endpoints (${rows.length})`}>
        <div className="filter-chips" role="group" aria-label="Label">
          {LABELS.map((l) => {
            const n = (data ?? []).filter((r) => l === "ALL" || r.verdict.label === l).length;
            if (l !== "ALL" && n === 0) return null;
            return (
              <button key={l} className={`fchip ${label === l ? "is-on" : ""}`} aria-pressed={label === l} onClick={() => setLabel(l)}>
                {l === "ALL" ? "All" : l.charAt(0) + l.slice(1).toLowerCase()}
                <span className="fchip-count">{n}</span>
              </button>
            );
          })}
        </div>
        <div className="filters">
          <input
            type="search"
            placeholder="Filter by path or service"
            aria-label="Filter by path or service"
            value={query}
            onChange={(e) => setQuery(e.target.value)}
          />
        </div>
        <div className="table-wrap">
          <table>
            <thead>
              <tr>
                <SortTh label="Endpoint" k="endpoint" sort={sort} onSort={onSort} />
                <SortTh label="Label" k="label" sort={sort} onSort={onSort} />
                {!selected && <SortTh label="Confidence" k="confidence" sort={sort} onSort={onSort} />}
                <SortTh label="Risk" k="risk" sort={sort} onSort={onSort} />
                <th>Auth</th>
                {!selected && <SortTh label="Seen by" k="seen" sort={sort} onSort={onSort} />}
              </tr>
            </thead>
            <tbody>
              {rows.map(({ verdict: v, record: r }) => (
                <tr
                  key={v.endpoint_id}
                  className={selected === v.endpoint_id ? "selected" : undefined}
                  onClick={() => setSelected(v.endpoint_id)}
                >
                  <td>
                    <button className="link" onClick={() => setSelected(v.endpoint_id)}>
                      <MethodPath method={v.endpoint_id.split(" ")[0] ?? ""} path={v.endpoint_id.split(" ").slice(1).join(" ")} />
                    </button>
                    <div className="muted small">{r?.service}</div>
                  </td>
                  <td>
                    <LabelBadge label={v.label} />
                  </td>
                  {!selected && <td>{pct(v.confidence)}</td>}
                  <td>
                    <span className={`risk risk-${v.risk_score}`}>{v.risk_score}</span>
                  </td>
                  <td>
                    {r?.auth_scheme === "NONE" ? (
                      <span className="warn-text">none</span>
                    ) : (
                      (r?.auth_scheme ?? "?").toLowerCase()
                    )}
                  </td>
                  {!selected && <td>{r ? `${r.seen_by.length} / 6` : "?"}</td>}
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </Card>
      {selected ? (
        <Detail key={selected} endpointId={selected} record={data?.find((r) => r.verdict.endpoint_id === selected)?.record} />
      ) : (
        <Card title="Details">
          <p className="muted">Select an endpoint to see why it was classified the way it was.</p>
        </Card>
      )}
    </div>
  );
}

function Detail({ endpointId, record }: { endpointId: string; record: InventoryRecord | undefined }) {
  const { api } = useSession();
  const { data, error } = useLoad(async () => {
    const [verdict, radius] = await Promise.all([
      api.verdict(endpointId),
      api.blastRadius(endpointId),
    ]);
    return { verdict, radius };
  }, [endpointId]);

  if (error) return <ErrorBox message={error} />;
  if (!data) return <Loading what="details" />;
  const { verdict: v, radius } = data;

  return (
    <Card title="Why" className="sticky-panel">
      <p>
        <code>{v.endpoint_id}</code> <LabelBadge label={v.label} /> at {pct(v.confidence)}{" "}
        confidence, decided by {v.decided_by}.
      </p>
      <p className="action">{v.recommended_action}</p>

      <h3>Evidence</h3>
      <EvidenceBars evidence={v.evidence} />

      <details className="explain">
        <summary>How the score was worked out</summary>
        <ScoreTable verdict={v} />
      </details>

      {record && (
        <>
          <h3>Sources</h3>
          <SourceChips e={record} consulted={ALL_SOURCES} />
          <p className="muted small">
            Absence is evidence: the sources that did <em>not</em> see an endpoint are what
            identify a zombie.
          </p>
          {record.flags.length > 0 && (
            <>
              <h3>Discrepancy flags</h3>
              <ul className="chips">
                {record.flags.map((f) => (
                  <li key={f} className="chip flag">
                    {f}
                  </li>
                ))}
              </ul>
            </>
          )}
        </>
      )}

      <h3>Blast radius</h3>
      {radius.isolated ? (
        <p>
          Isolated: nothing observed depends on it. <span className="muted">That means no
          dependency was observed, not that none exists, which is why Safe Kill shadows it
          before anything is refused.</span>
        </p>
      ) : (
        <p>
          <strong>{radius.severity}</strong>: {radius.direct_services.length} direct caller(s),{" "}
          {radius.direct_services.length + radius.indirect_services.length} service(s) over{" "}
          {radius.depth_reached} hop(s), {radius.affected_endpoints.length} endpoint(s) degraded.
        </p>
      )}
    </Card>
  );
}

export function EvidenceBars({ evidence }: { evidence: Evidence[] }) {
  const max = Math.max(...evidence.map((e) => Math.abs(e.contribution)), 0.0001);
  return (
    <ul className="evidence">
      {evidence.map((e) => (
        <li key={e.key + e.statement}>
          <span className={`contribution ${e.contribution >= 0 ? "pos" : "neg"}`}>
            {e.contribution >= 0 ? "+" : ""}
            {e.contribution.toFixed(2)}
          </span>
          <span className="bar-track">
            <span
              className={`bar ${e.contribution >= 0 ? "pos" : "neg"}`}
              style={{ width: `${(Math.abs(e.contribution) / max) * 100}%` }}
            />
          </span>
          <span className="statement">
            {e.statement} <span className="muted small">({e.source})</span>
          </span>
        </li>
      ))}
    </ul>
  );
}
