import { useMemo, useRef, useState } from "react";
import { Contributions } from "../../charts";
import {
  Card,
  LevelBadge,
  LifecycleBadge,
  MethodPath,
  Priority,
  SortTh,
  Sparkline,
  useSort,
} from "../../common";
import { IconX } from "../../icons";
import type { Review, ScanEndpoint, ScanJob } from "../../types";
import { RealApiEvidence } from "../explain";
import { CandidateBadge } from "./Candidates";
import { ReviewBadge, ReviewControls, SourceChips, ago, consultedSources, when } from "./shared";

type Filter = "all" | "candidates" | "findings" | "undocumented" | "unreviewed" | "sensitive" | "zombie";
type SortKey = "priority" | "endpoint" | "handles" | "status";

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
  const [sort, onSort] = useSort<SortKey>({ key: "priority", dir: "desc" });
  // Open on the strongest candidate, the endpoint a reviewer wants first.
  const [selected, setSelected] = useState<string | null>(
    report.candidates?.[0]?.endpoint_id ?? report.endpoints[0]?.id ?? null,
  );

  const filters: { key: Filter; label: string; test: (e: ScanEndpoint) => boolean }[] = [
    { key: "all", label: "All", test: () => true },
    { key: "candidates", label: "Zombie candidates", test: (e) => !!e.candidate },
    ...(usage ? [{ key: "zombie" as const, label: "Proven zombies", test: (e: ScanEndpoint) => usage[e.id]?.lifecycle === "ZOMBIE" }] : []),
    { key: "undocumented", label: "Undocumented", test: (e) => !e.documented },
    { key: "sensitive", label: "Sensitive", test: (e) => e.sensitivity?.level === "high" },
    { key: "findings", label: "With findings", test: (e) => e.findings.length > 0 },
    { key: "unreviewed", label: "Not reviewed", test: (e) => !reviews[e.id] },
  ];
  const active = filters.find((f) => f.key === filter) ?? filters[0]!;

  const shown = useMemo(() => {
    const q = query.trim().toLowerCase();
    const rows = report.endpoints.filter(
      (e) => active.test(e) && (!q || `${e.id} ${e.file ?? ""} ${e.sensitivity?.category ?? ""}`.toLowerCase().includes(q)),
    );
    const status = (e: ScanEndpoint) => usage?.[e.id]?.lifecycle ?? e.candidate?.label ?? "";
    const value = (e: ScanEndpoint): string | number =>
      sort.key === "priority" ? e.priority ?? 0
        : sort.key === "endpoint" ? e.path
          : sort.key === "handles" ? e.sensitivity?.category ?? ""
            : status(e);
    const dir = sort.dir === "asc" ? 1 : -1;
    return rows.sort((a, b) => {
      const va = value(a);
      const vb = value(b);
      const c = typeof va === "number" && typeof vb === "number" ? va - vb : String(va).localeCompare(String(vb));
      return c * dir || a.id.localeCompare(b.id);
    });
  }, [report, active, query, sort, usage]);

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
    <div className={e ? "split" : "stack"}>
      <Card title={`Endpoints (${shown.length} of ${report.endpoints.length})`}>
        <div className="filter-chips" role="group" aria-label="Which endpoints">
          {filters.map((f) => (
            <button
              key={f.key}
              className={`fchip ${filter === f.key ? "is-on" : ""}`}
              aria-pressed={filter === f.key}
              onClick={() => setFilter(f.key)}
            >
              {f.label}
              <span className="fchip-count">{report.endpoints.filter(f.test).length}</span>
            </button>
          ))}
        </div>
        <div className="filters">
          <input type="search" placeholder="Filter by path, file or category" value={query}
            onChange={(ev) => setQuery(ev.target.value)} aria-label="Filter endpoints" />
        </div>
        <div className="table-wrap">
          <table>
            <thead>
              <tr>
                <SortTh label="Priority" k="priority" sort={sort} onSort={onSort} />
                <SortTh label="Endpoint" k="endpoint" sort={sort} onSort={onSort} />
                <SortTh label="Handles" k="handles" sort={sort} onSort={onSort} />
                <SortTh label={usage ? "Usage" : "Candidate"} k="status" sort={sort} onSort={onSort} />
                {/* With the inspector open, it shows these; the table keeps the width. */}
                {!e && <th>Spec</th>}
                {!e && <th>Decision</th>}
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
                    {e && !x.documented && <span className="tag">undocumented</span>}
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
                  {!e && <td>{x.documented ? "yes" : <span className="warn-text">no</span>}</td>}
                  {!e && (
                    <td>
                      <ReviewBadge review={reviews[x.id]} />
                    </td>
                  )}
                </tr>
              ))}
            </tbody>
          </table>
          {shown.length === 0 && <p className="muted table-empty">No endpoint matches this filter.</p>}
        </div>
      </Card>

      {e && (
        <Inspector
          e={e}
          job={job}
          review={reviews[e.id]}
          consulted={consulted}
          onReviewed={onReviewed}
          onClose={() => setSelected(null)}
        />
      )}
    </div>
  );
}

/** One endpoint, beside the list: what it is, the evidence, and the decision. */
function Inspector({
  e,
  job,
  review,
  consulted,
  onReviewed,
  onClose,
}: {
  e: ScanEndpoint;
  job: ScanJob;
  review: Review | undefined;
  consulted: string[];
  onReviewed: (reviews: Record<string, Review>) => void;
  onClose: () => void;
}) {
  const report = job.report!;
  const u = job.traffic?.endpoints?.[e.id];
  const panel = useRef<HTMLDivElement>(null);
  const sections = [
    { id: "evidence", label: "Evidence" },
    ...(u ? [{ id: "usage", label: "Usage" }] : []),
    { id: "sources", label: "Sources" },
    { id: "findings", label: "Findings" },
    { id: "decision", label: "Decision" },
  ];
  // In-panel navigation scrolls; it must not touch the hash, which is the route.
  const jump = (id: string) =>
    panel.current?.querySelector(`[data-section="${id}"]`)?.scrollIntoView({ behavior: "smooth", block: "start" });

  return (
    <aside className="card inspector" aria-label={`Details for ${e.id}`}>
      <div className="inspector-head">
        <div className="inspector-title">
          <span className="muted small">Details</span>
          <MethodPath method={e.method} path={e.path} />
          <div className="inspector-badges">
            <Priority value={e.priority} />
            {e.candidate && <CandidateBadge label={e.candidate.label} />}
            {u && <LifecycleBadge label={u.lifecycle} />}
            {e.deprecated_in_spec && <span className="tag">deprecated in spec</span>}
          </div>
        </div>
        <button className="icon-btn" onClick={onClose} aria-label="Close details" title="Close">
          <IconX size={17} />
        </button>
      </div>
      <nav className="inspector-nav" aria-label="Sections of the details">
        {sections.map((s) => (
          <button key={s.id} className="small secondary" onClick={() => jump(s.id)}>
            {s.label}
          </button>
        ))}
      </nav>
      <div className="inspector-body stack" ref={panel}>
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
        </dl>
        <section data-section="evidence">
          <h3>Is this a real API?</h3>
          <RealApiEvidence e={e} />
          {e.candidate && (
            <div className="cand-detail">
              <h3>
                Why it is a candidate <CandidateBadge label={e.candidate.label} />
              </h3>
              <Contributions items={e.candidate.signals} total={e.candidate.score} />
            </div>
          )}
          {e.referenced_by && e.referenced_by.length > 0 && (
            <>
              <h3>Used by this project&apos;s clients</h3>
              <ul className="findings small">
                {e.referenced_by.map((r) => (
                  <li key={r}>
                    <code>{r}</code>
                  </li>
                ))}
              </ul>
            </>
          )}
        </section>
        {u && (
          <section data-section="usage">
            <h3>
              Usage <LifecycleBadge label={u.lifecycle} />
            </h3>
            <p className="small">{u.reason}</p>
            <Sparkline points={u.daily.map(([, n]) => n)} width={300} height={40} />
            <p className="muted small">
              {u.requests.toLocaleString()} request(s), last success{" "}
              {u.last_success ? when(u.last_success) : "never in the window"}
            </p>
          </section>
        )}
        <section data-section="sources">
          <h3>Sources</h3>
          <SourceChips e={e} consulted={consulted} />
          <p className="muted small">
            Absent: consulted, and did not see this endpoint. That absence is evidence. Not
            asked: a project scan cannot consult that source.
          </p>
        </section>
        <section data-section="findings">
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
        </section>
        <section data-section="decision">
          <h3>Decision</h3>
          <ReviewControls jobId={job.id} e={e} review={review} onReviewed={onReviewed} />
        </section>
      </div>
    </aside>
  );
}
