import { useMemo, useState } from "react";
import { Card } from "../../common";
import type { Review, ScanJob } from "../../types";
import { ReviewBadge, ReviewControls, SourceChips, ago, consultedSources } from "./shared";

type Filter = "all" | "findings" | "undocumented" | "unreviewed";

export function ScanEndpointsTab({
  job,
  onReviewed,
}: {
  job: ScanJob;
  onReviewed: (reviews: Record<string, Review>) => void;
}) {
  const report = job.report!;
  const reviews = job.reviews ?? {};
  const consulted = consultedSources(job);
  const [filter, setFilter] = useState<Filter>("all");
  const [query, setQuery] = useState("");
  const [selected, setSelected] = useState<string | null>(report.endpoints[0]?.id ?? null);

  const shown = useMemo(() => {
    const q = query.trim().toLowerCase();
    return report.endpoints.filter((e) => {
      if (filter === "findings" && !e.findings.length) return false;
      if (filter === "undocumented" && e.documented) return false;
      if (filter === "unreviewed" && reviews[e.id]) return false;
      return !q || `${e.id} ${e.file ?? ""}`.toLowerCase().includes(q);
    });
  }, [report, filter, query, reviews]);

  const e = report.endpoints.find((x) => x.id === selected) ?? null;

  if (!report.endpoints.length) {
    return (
      <Card title="Endpoints">
        <p className="muted">
          No endpoints were found. The Overview's "What was checked" says why.
        </p>
      </Card>
    );
  }

  return (
    <div className="split">
      <Card title={`Endpoints (${shown.length} of ${report.endpoints.length})`}>
        <div className="filters">
          <select value={filter} onChange={(ev) => setFilter(ev.target.value as Filter)}
            aria-label="Which endpoints">
            <option value="all">All</option>
            <option value="findings">With their own findings</option>
            <option value="undocumented">Undocumented</option>
            <option value="unreviewed">Not yet reviewed</option>
          </select>
          <input type="search" placeholder="Filter by path or file" value={query}
            onChange={(ev) => setQuery(ev.target.value)} aria-label="Filter endpoints" />
        </div>
        <div className="table-wrap">
          <table>
            <thead>
              <tr>
                <th>Endpoint</th>
                <th>Documented</th>
                <th>Owner</th>
                <th>Decision</th>
              </tr>
            </thead>
            <tbody>
              {shown.map((x) => (
                <tr key={x.id} className={x.id === selected ? "selected" : undefined}>
                  <td>
                    <button className="link" onClick={() => setSelected(x.id)}
                      aria-label={`Details for ${x.id}`} aria-pressed={x.id === selected}>
                      <code>
                        <span className="method">{x.method}</span> {x.path}
                      </code>
                    </button>
                  </td>
                  <td>{x.documented ? "yes" : <span className="warn-text">no</span>}</td>
                  <td>{x.owner ?? <span className="muted">none</span>}</td>
                  <td>
                    <ReviewBadge review={reviews[x.id]} />
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </Card>

      <Card title="Details">
        {!e ? (
          <p className="muted">Select an endpoint.</p>
        ) : (
          <div className="stack">
            <p>
              <code>
                <span className="method">{e.method}</span> {e.path}
              </code>
              {e.deprecated_in_spec && <span className="tag">deprecated in spec</span>}
            </p>
            <dl className="facts">
              <dt>Defined in</dt>
              <dd>
                {e.file ? (
                  <code>
                    {e.file}
                    {e.line ? `:${e.line}` : ""}
                  </code>
                ) : (
                  <span className="muted">the API specification only: no handler found in code</span>
                )}
              </dd>
              {e.framework && (
                <>
                  <dt>Framework</dt>
                  <dd>{e.framework}</dd>
                </>
              )}
              <dt>Owner</dt>
              <dd>{e.owner ?? <span className="muted">none known</span>}</dd>
              <dt>Code last changed</dt>
              <dd>{ago(e.last_change_days)}</dd>
            </dl>
            <div>
              <h3>Sources</h3>
              <SourceChips e={e} consulted={consulted} />
              <p className="muted small">
                Crossed out: consulted, and did not see this endpoint. Greyed: a project
                scan cannot consult it.
              </p>
            </div>
            <div>
              <h3>Findings</h3>
              {e.findings.length || report.repository_findings.length ? (
                <ul className="findings">
                  {e.findings.map((f) => (
                    <li key={f}>{f}</li>
                  ))}
                  {report.repository_findings.map((f) => (
                    <li key={f} className="muted">
                      {f} <span className="small">(true of every endpoint)</span>
                    </li>
                  ))}
                </ul>
              ) : (
                <p className="muted small">None.</p>
              )}
            </div>
            <div>
              <h3>Decision</h3>
              <ReviewControls jobId={job.id} e={e} review={reviews[e.id]} onReviewed={onReviewed} />
            </div>
          </div>
        )}
      </Card>
    </div>
  );
}
