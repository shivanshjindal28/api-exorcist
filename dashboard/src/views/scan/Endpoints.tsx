import { useMemo, useState } from "react";
import { Card, LevelBadge, LifecycleBadge, MethodPath, Priority, Sparkline } from "../../common";
import type { Review, ScanJob } from "../../types";
import { CandidateBadge } from "./Candidates";
import { ReviewBadge, ReviewControls, SourceChips, ago, consultedSources, when } from "./shared";

type Filter = "all" | "candidates" | "findings" | "undocumented" | "unreviewed" | "sensitive" | "zombie";

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
  const usage = job.traffic?.endpoints ?? null;
  const [filter, setFilter] = useState<Filter>(
    report.endpoints.some((e) => e.candidate) ? "candidates" : "all",
  );
  const [query, setQuery] = useState("");
  // Open on the strongest candidate, the endpoint a reviewer wants first.
  const [selected, setSelected] = useState<string | null>(
    report.candidates?.[0]?.endpoint_id ?? report.endpoints[0]?.id ?? null,
  );

  const shown = useMemo(() => {
    const q = query.trim().toLowerCase();
    return report.endpoints.filter((e) => {
      if (filter === "candidates" && !e.candidate) return false;
      if (filter === "findings" && !e.findings.length) return false;
      if (filter === "undocumented" && e.documented) return false;
      if (filter === "unreviewed" && reviews[e.id]) return false;
      if (filter === "sensitive" && e.sensitivity?.level !== "high") return false;
      if (filter === "zombie" && usage?.[e.id]?.lifecycle !== "ZOMBIE") return false;
      return !q || `${e.id} ${e.file ?? ""} ${e.sensitivity?.category ?? ""}`.toLowerCase().includes(q);
    }).sort((a, b) => (b.priority ?? 0) - (a.priority ?? 0) || a.id.localeCompare(b.id));
  }, [report, filter, query, reviews, usage]);

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
            <option value="candidates">Zombie candidates</option>
            <option value="findings">With their own findings</option>
            <option value="undocumented">Undocumented</option>
            <option value="unreviewed">Not yet reviewed</option>
            <option value="sensitive">Sensitive (auth, payments, cards, KYC, admin)</option>
            {usage && <option value="zombie">Proven zombies (no traffic)</option>}
          </select>
          <input type="search" placeholder="Filter by path or file" value={query}
            onChange={(ev) => setQuery(ev.target.value)} aria-label="Filter endpoints" />
        </div>
        <div className="table-wrap">
          <table>
            <thead>
              <tr>
                <th title="Priority">Pri.</th>
                <th>Endpoint</th>
                <th>Handles</th>
                <th>{usage ? "Usage" : "Candidate"}</th>
                <th>Spec</th>
                <th>Decision</th>
              </tr>
            </thead>
            <tbody>
              {shown.map((x) => (
                <tr key={x.id} className={x.id === selected ? "selected" : undefined}>
                  <td>
                    <Priority value={x.priority} />
                  </td>
                  <td>
                    <button className="link" onClick={() => setSelected(x.id)}
                      aria-label={`Details for ${x.id}`} aria-pressed={x.id === selected}>
                      <MethodPath method={x.method} path={x.path} />
                    </button>
                  </td>
                  <td>
                    {x.sensitivity && <LevelBadge level={x.sensitivity.level} category={x.sensitivity.category} />}
                  </td>
                  <td>
                    {usage?.[x.id] ? (
                      <LifecycleBadge label={usage[x.id]!.lifecycle} />
                    ) : x.candidate ? (
                      <CandidateBadge label={x.candidate.label} />
                    ) : (
                      <span className="muted">no</span>
                    )}
                  </td>
                  <td>{x.documented ? "yes" : <span className="warn-text">no</span>}</td>
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
              <MethodPath method={e.method} path={e.path} />
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
              {e.sensitivity && (
                <>
                  <dt>Handles</dt>
                  <dd>
                    <LevelBadge level={e.sensitivity.level} category={e.sensitivity.category} />{" "}
                    <span className="muted small">from {e.sensitivity.because}</span>
                  </dd>
                </>
              )}
              <dt>Priority</dt>
              <dd>
                <Priority value={e.priority} />
              </dd>
            </dl>
            {usage?.[e.id] && (
              <div>
                <h3>
                  Usage <LifecycleBadge label={usage[e.id]!.lifecycle} />
                </h3>
                <p className="small" style={{ margin: "0 0 0.4rem" }}>{usage[e.id]!.reason}</p>
                <Sparkline points={usage[e.id]!.daily.map(([, n]) => n)} width={260} height={36} />
                <p className="muted small" style={{ margin: "0.3rem 0 0" }}>
                  {usage[e.id]!.requests.toLocaleString()} request(s), last success{" "}
                  {usage[e.id]!.last_success ? when(usage[e.id]!.last_success) : "never in the window"}
                </p>
              </div>
            )}
            {e.candidate && (
              <div className="cand-detail">
                <h3>
                  <CandidateBadge label={e.candidate.label} /> score {e.candidate.score}
                </h3>
                <ul className="signals">
                  {e.candidate.signals.map((s) => (
                    <li key={s.text} className={s.weight < 0 ? "sig-against" : undefined}>
                      <span className="sig-weight">{s.weight > 0 ? `+${s.weight}` : s.weight}</span>
                      {s.text}
                    </li>
                  ))}
                </ul>
              </div>
            )}
            {e.referenced_by && e.referenced_by.length > 0 && (
              <div>
                <h3>Used by this project&apos;s clients</h3>
                <ul className="findings small">
                  {e.referenced_by.map((r) => (
                    <li key={r}>
                      <code>{r}</code>
                    </li>
                  ))}
                </ul>
              </div>
            )}
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
