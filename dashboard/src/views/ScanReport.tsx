import { useEffect, useMemo, useState } from "react";
import { ApiError } from "../api";
import { Card, ErrorBox, Loading, useSession } from "../common";
import type { ScanCheck, ScanEndpoint, ScanJob, ScanReport as Report } from "../types";
import { KIND_LABEL, ScanStatusBadge, when } from "./ScanResults";

const POLL_MS = 1000;

/** One scan: its progress while it runs, then its report. */
export function ScanReport({ id }: { id: string }) {
  const { api, signOut } = useSession();
  const [job, setJob] = useState<ScanJob | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let live = true;
    let timer: number | undefined;
    const tick = () => {
      api
        .scan(id)
        .then((j) => {
          if (!live) return;
          setJob(j);
          setError(null);
          if (j.status === "queued" || j.status === "running") {
            timer = window.setTimeout(tick, POLL_MS);
          }
        })
        .catch((e: unknown) => {
          if (!live) return;
          if (e instanceof ApiError && e.unauthorised) return signOut();
          setError(e instanceof Error ? e.message : String(e));
        });
    };
    tick();
    return () => {
      live = false;
      window.clearTimeout(timer);
    };
  }, [api, id, signOut]);

  if (error) return <ErrorBox message={error} />;
  if (!job) return <Loading what="scan" />;

  return (
    <div className="stack">
      <p>
        <a href="#results">All scans</a>
      </p>
      <Card title={job.target}>
        <dl className="facts">
          <dt>Source</dt>
          <dd>{KIND_LABEL[job.kind]}</dd>
          <dt>Status</dt>
          <dd>
            <ScanStatusBadge status={job.status} />
            {job.duration_s != null && <span className="muted small"> in {job.duration_s}s</span>}
          </dd>
          <dt>Started</dt>
          <dd>
            {when(job.created_at)} by {job.requested_by}
          </dd>
          {job.report?.details.commit && (
            <>
              <dt>Commit</dt>
              <dd>
                <code>{job.report.details.commit}</code>
              </dd>
            </>
          )}
        </dl>
        {(job.status === "queued" || job.status === "running") && <Progress job={job} />}
        {job.status === "failed" && (
          <div className="error" role="alert">
            <strong>The scan could not finish.</strong> {job.error}
          </div>
        )}
      </Card>
      {job.report && <ReportBody report={job.report} job={job} />}
    </div>
  );
}

function Progress({ job }: { job: ScanJob }) {
  return (
    <ol className="progress-steps" aria-live="polite">
      {job.progress.map((p, i) => (
        <li key={`${p.at}-${i}`} className={i === job.progress.length - 1 ? "current" : "done"}>
          {p.message}
        </li>
      ))}
    </ol>
  );
}

// ---------------------------------------------------------------------------
const CHECK_TEXT: Record<ScanCheck["status"], string> = {
  ok: "worked",
  partial: "partly",
  unavailable: "not available",
  failed: "failed",
};

function ReportBody({ report, job }: { report: Report; job: ScanJob }) {
  const [filter, setFilter] = useState<"all" | "issues" | "undocumented">("issues");
  const [query, setQuery] = useState("");
  const [open, setOpen] = useState<string | null>(null);

  const shown = useMemo(() => {
    const q = query.trim().toLowerCase();
    return report.endpoints.filter((e) => {
      if (filter === "issues" && e.findings.length === 0) return false;
      if (filter === "undocumented" && e.documented) return false;
      if (q && !`${e.id} ${e.file ?? ""}`.toLowerCase().includes(q)) return false;
      return true;
    });
  }, [report, filter, query]);

  function download() {
    const blob = new Blob([JSON.stringify({ scan: { ...job, report: undefined }, report }, null, 2)], {
      type: "application/json",
    });
    const a = document.createElement("a");
    a.href = URL.createObjectURL(blob);
    a.download = `apix-scan-${job.id}.json`;
    a.click();
    URL.revokeObjectURL(a.href);
  }

  const issues = report.endpoints.filter((e) => e.findings.length > 0).length;

  return (
    <>
      <div className="tiles">
        {report.summary.map((s) => (
          <div className="tile" key={s.label}>
            <div className="tile-value">{s.value}</div>
            <div className="tile-label">{s.label}</div>
          </div>
        ))}
      </div>

      <Card title="What was checked">
        <ul className="checks">
          {report.checks.map((c) => (
            <li key={c.name} className={`check check-${c.status}`}>
              <span className="check-status">{CHECK_TEXT[c.status]}</span>
              <span className="check-name">{c.name}</span>
              <span className="check-detail">{c.detail}</span>
            </li>
          ))}
        </ul>
        {!report.lifecycle.available && (
          <p className="muted small">
            <strong>Why no endpoint is called a zombie here:</strong> {report.lifecycle.why}{" "}
            The <a href="#overview">demo bank</a> shows the full classification, where usage
            data exists.
          </p>
        )}
      </Card>

      {report.repository_findings.length > 0 && (
        <Card title="True of the whole project">
          <p className="muted small">
            These hold for every endpoint, so they are listed once instead of on every row.
          </p>
          <ul>
            {report.repository_findings.map((f) => (
              <li key={f}>{f}</li>
            ))}
          </ul>
        </Card>
      )}

      <Card title={`Endpoints (${report.endpoints.length})`}>
        {report.endpoints.length === 0 ? (
          <p className="muted">No endpoints were found. "What was checked" above says why.</p>
        ) : (
          <>
            <div className="filters">
              <label>
                Show{" "}
                <select value={filter} onChange={(e) => setFilter(e.target.value as typeof filter)}>
                  <option value="issues">With findings ({issues})</option>
                  <option value="undocumented">Undocumented</option>
                  <option value="all">All ({report.endpoints.length})</option>
                </select>
              </label>
              <input
                type="search"
                placeholder="Filter by path or file"
                value={query}
                onChange={(e) => setQuery(e.target.value)}
                aria-label="Filter endpoints"
              />
              <button className="secondary small-btn" onClick={download}>
                Download report (JSON)
              </button>
            </div>
            <div className="table-wrap">
              <table>
                <thead>
                  <tr>
                    <th>Endpoint</th>
                    <th>Where</th>
                    <th>Documented</th>
                    <th>Owner</th>
                    <th>Last changed</th>
                    <th>Findings</th>
                  </tr>
                </thead>
                <tbody>
                  {shown.map((e) => (
                    <EndpointRow
                      key={e.id}
                      e={e}
                      open={open === e.id}
                      toggle={() => setOpen(open === e.id ? null : e.id)}
                    />
                  ))}
                </tbody>
              </table>
            </div>
            {shown.length === 0 && (
              <p className="muted">No endpoint matches. Choose "All" to see every one.</p>
            )}
          </>
        )}
      </Card>
    </>
  );
}

function EndpointRow({ e, open, toggle }: { e: ScanEndpoint; open: boolean; toggle: () => void }) {
  return (
    <>
      <tr className={open ? "selected" : undefined}>
        <td>
          <button
            className="link"
            onClick={toggle}
            aria-expanded={open}
            aria-label={`Details for ${e.id}`}
          >
            <code>
              <span className="method">{e.method}</span> {e.path}
            </code>
          </button>
          {e.deprecated_in_spec && <span className="tag">deprecated in spec</span>}
        </td>
        <td className="small">
          {e.file ? (
            <code>
              {e.file}
              {e.line ? `:${e.line}` : ""}
            </code>
          ) : (
            <span className="muted">spec only</span>
          )}
        </td>
        <td>{e.documented ? "yes" : <span className="warn-text">no</span>}</td>
        <td>{e.owner ?? <span className="muted">none</span>}</td>
        <td className="small">
          {e.last_change_days == null ? <span className="muted">unknown</span> : ago(e.last_change_days)}
        </td>
        <td>{e.findings.length}</td>
      </tr>
      {open && (
        <tr className="detail-row">
          <td colSpan={6}>
            {e.findings.length ? (
              <ul className="findings">
                {e.findings.map((f) => (
                  <li key={f}>{f}</li>
                ))}
              </ul>
            ) : (
              <p className="muted small">Nothing beyond what is true of the whole project.</p>
            )}
            <p className="muted small">
              Seen by: {e.seen_by.join(", ") || "none"}
              {e.framework ? ` · framework: ${e.framework}` : ""}
            </p>
          </td>
        </tr>
      )}
    </>
  );
}

function ago(days: number): string {
  if (days < 1) return "today";
  if (days < 60) return `${days} days ago`;
  if (days < 730) return `${Math.round(days / 30)} months ago`;
  return `${(days / 365).toFixed(1)} years ago`;
}
