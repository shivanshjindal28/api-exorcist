import { useMemo, useState } from "react";
import type { ChangeEvent, DragEvent } from "react";
import { ApiError } from "../../api";
import {
  Card,
  ErrorBox,
  LifecycleBadge,
  MethodPath,
  Priority,
  Sparkline,
  canApprove,
  useSession,
} from "../../common";
import { IconUpload } from "../../icons";
import type { Lifecycle, ScanJob, Traffic } from "../../types";
import { when } from "./shared";

const ORDER: Lifecycle[] = ["ZOMBIE", "ORPHANED", "DEPRECATED", "ACTIVE", "INDETERMINATE"];
const MEANING: Record<Lifecycle, string> = {
  ZOMBIE: "no successful request in the window",
  ORPHANED: "in use, no owning team",
  DEPRECATED: "deprecated, still called",
  ACTIVE: "in use and owned",
  INDETERMINATE: "the logs cannot decide",
};

/** Usage evidence: what turns a suspected zombie into a proven one. */
export function ScanUsageTab({ job, onImported }: { job: ScanJob; onImported: (j: ScanJob) => void }) {
  const { principal } = useSession();
  const traffic = job.traffic ?? null;
  return (
    <div className="stack">
      {traffic && <UsageReport job={job} traffic={traffic} />}
      {canApprove(principal) ? (
        <ImportCard job={job} onImported={onImported} replacing={Boolean(traffic)} />
      ) : (
        !traffic && (
          <Card title="Usage">
            <p className="muted">
              No access logs have been imported for this scan. Importing them needs an approver.
            </p>
          </Card>
        )
      )}
    </div>
  );
}

function ImportCard({
  job,
  onImported,
  replacing,
}: {
  job: ScanJob;
  onImported: (j: ScanJob) => void;
  replacing: boolean;
}) {
  const { api } = useSession();
  const [files, setFiles] = useState<File[]>([]);
  const [progress, setProgress] = useState<number | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [over, setOver] = useState(false);

  function pick(e: ChangeEvent<HTMLInputElement>) {
    setError(null);
    setFiles(Array.from(e.target.files ?? []));
  }
  function drop(e: DragEvent<HTMLDivElement>) {
    e.preventDefault();
    setOver(false);
    setError(null);
    setFiles(Array.from(e.dataTransfer.files ?? []));
  }

  async function upload() {
    if (!files.length) return;
    setError(null);
    setProgress(0);
    try {
      onImported(await api.importTraffic(job.id, files, setProgress));
      setFiles([]);
    } catch (err) {
      setError(err instanceof ApiError ? err.message : String(err));
    } finally {
      setProgress(null);
    }
  }

  const size = files.reduce((n, f) => n + f.size, 0);
  return (
    <Card title={replacing ? "Replace the usage evidence" : "Prove which endpoints are dead"}>
      <div
        className={`drop ${over ? "is-over" : ""}`}
        onDragOver={(e) => {
          e.preventDefault();
          setOver(true);
        }}
        onDragLeave={() => setOver(false)}
        onDrop={drop}
      >
        <p className="small" style={{ margin: 0 }}>
          Code shows what exists; only usage shows what is dead. Import the access logs your
          gateway or load balancer already writes, ideally 30 to 90 days of them, and every
          endpoint is classified by the four lifecycle definitions.
        </p>
        <div className="formats">
          {["nginx / Apache", "AWS ALB", "Kong", "AWS API Gateway", "Envoy", "Traefik", "JSON lines", ".gz rotated"].map((f) => (
            <span key={f} className="chip">
              {f}
            </span>
          ))}
        </div>
        <div className="buttons">
          <label className="file-pick">
            <IconUpload />
            {files.length ? `${files.length} file(s), ${(size / 1048576).toFixed(1)} MB` : "Choose log files"}
            <input
              className="visually-hidden"
              type="file"
              multiple
              aria-label="Choose access log files"
              onChange={pick}
              disabled={progress !== null}
            />
          </label>
          <button onClick={upload} disabled={!files.length || progress !== null}>
            {progress === null ? "Import and classify" : `Uploading ${Math.round(progress * 100)}%`}
          </button>
          <span className="muted small">or drop files here</span>
        </div>
        {progress !== null && (
          <div className="upload-progress" role="progressbar" aria-valuenow={Math.round(progress * 100)}
            aria-valuemin={0} aria-valuemax={100} aria-label="Upload progress">
            <span style={{ width: `${progress * 100}%` }} />
          </div>
        )}
        <p className="muted small" style={{ margin: 0 }}>
          Privacy: query strings (tokens, account numbers, OTPs) are dropped as each line is read,
          and client addresses become salted hashes used only to count distinct clients. Neither
          is stored. The import is recorded in this scan's audit log under your name.
        </p>
        {error && <ErrorBox message={error} />}
      </div>
    </Card>
  );
}

function UsageReport({ job, traffic }: { job: ScanJob; traffic: Traffic }) {
  const [filter, setFilter] = useState<Lifecycle | "all">("all");
  const report = job.report!;
  const byId = useMemo(() => new Map(report.endpoints.map((e) => [e.id, e])), [report]);
  const rows = useMemo(
    () =>
      Object.entries(traffic.endpoints)
        .filter(([, u]) => filter === "all" || u.lifecycle === filter)
        .sort(
          ([a, x], [b, y]) =>
            ORDER.indexOf(x.lifecycle) - ORDER.indexOf(y.lifecycle) ||
            (byId.get(b)?.priority ?? 0) - (byId.get(a)?.priority ?? 0) ||
            y.requests - x.requests ||
            a.localeCompare(b),
        ),
    [traffic, filter, byId],
  );
  const total = Object.keys(traffic.endpoints).length || 1;
  const matchedPct = traffic.requests ? Math.round((traffic.matched / traffic.requests) * 100) : 0;
  const lc = traffic.lifecycle;

  return (
    <>
      <div className="tiles">
        <div className="tile">
          <div className="tile-label">Requests read</div>
          <div className="tile-value">{traffic.requests.toLocaleString()}</div>
          <div className="tile-note">{matchedPct}% matched to an endpoint</div>
        </div>
        <div className="tile">
          <div className="tile-label">Window</div>
          <div className="tile-value">{traffic.window.days ?? "?"}<span className="small muted"> days</span></div>
          <div className="tile-note">{when(traffic.window.start)} to {when(traffic.window.end)}</div>
        </div>
        <div className="tile tile-bad">
          <div className="tile-label">Proven zombies</div>
          <div className="tile-value">{lc.ZOMBIE ?? 0}</div>
          <div className="tile-note">no successful call in the window</div>
        </div>
        <div className="tile tile-warn">
          <div className="tile-label">Orphaned</div>
          <div className="tile-value">{lc.ORPHANED ?? 0}</div>
          <div className="tile-note">used, but no owner: never remove</div>
        </div>
        <div className="tile tile-warn">
          <div className="tile-label">Traffic the code does not explain</div>
          <div className="tile-value">{traffic.shadow_routes_total}</div>
          <div className="tile-note">route shapes served, found in no code</div>
        </div>
      </div>

      <Card title="Lifecycle, from real usage">
        <div className="distribution" role="img" aria-label="Lifecycle distribution">
          {ORDER.map((k) =>
            lc[k] ? (
              <span key={k} className={`segment segment-${k.toLowerCase()}`} style={{ width: `${((lc[k] ?? 0) / total) * 100}%` }} />
            ) : null,
          )}
        </div>
        <ul className="legend">
          {ORDER.map((k) => (
            <li key={k}>
              <LifecycleBadge label={k} /> {lc[k] ?? 0} <span className="muted small">{MEANING[k]}</span>
            </li>
          ))}
        </ul>
        {(traffic.uncovered_services.length > 0 || traffic.gateway_prefixes.length > 0 || traffic.truncated ||
          (lc.ORPHANED ?? 0) > 0) && (
          <ul className="small muted" style={{ margin: "0.75rem 0 0", paddingLeft: "1.2rem" }}>
            {traffic.uncovered_services.length > 0 && (
              <li>
                These logs hold no request for {traffic.uncovered_services.join(", ")}, so nothing in
                {traffic.uncovered_services.length > 1 ? " those services" : " that service"} is judged unused.
              </li>
            )}
            {traffic.gateway_prefixes.length > 0 && (
              <li>
                Requests arrive under the gateway prefix {traffic.gateway_prefixes.join(", ")}; matched
                after removing it.
              </li>
            )}
            {traffic.truncated && <li>The import stopped at its line limit; later lines were not read.</li>}
            {(lc.ORPHANED ?? 0) > 0 && !report.endpoints.some((e) => e.owner) && (
              <li>
                Every endpoint in use is orphaned because the repository records no owners. Add a
                CODEOWNERS file and re-scan: owned endpoints in use become active.
              </li>
            )}
          </ul>
        )}
      </Card>

      <Card
        title="Endpoints by usage"
        flush
        actions={
          <select value={filter} onChange={(e) => setFilter(e.target.value as Lifecycle | "all")} aria-label="Lifecycle filter">
            <option value="all">All lifecycles</option>
            {ORDER.map((k) => (
              <option key={k} value={k}>
                {k.toLowerCase()} ({lc[k] ?? 0})
              </option>
            ))}
          </select>
        }
      >
        <div className="table-wrap">
          <table>
            <thead>
              <tr>
                <th>Endpoint</th>
                <th>Lifecycle</th>
                <th className="r">Requests</th>
                <th className="r">Clients</th>
                <th>Trend</th>
                <th>Last success</th>
                <th>Why</th>
              </tr>
            </thead>
            <tbody>
              {rows.map(([id, u]) => {
                const e = byId.get(id);
                return (
                  <tr key={id}>
                    <td>
                      <Priority value={e?.priority} />{" "}
                      {e ? <MethodPath method={e.method} path={e.path} /> : <code>{id}</code>}
                    </td>
                    <td>
                      <LifecycleBadge label={u.lifecycle} />
                    </td>
                    <td className="r num">
                      {u.requests.toLocaleString()}
                      {u.failed > 0 && <div className="small bad-text">{u.failed.toLocaleString()} failed</div>}
                    </td>
                    <td className="r num">
                      {u.clients.toLocaleString()}
                      {u.clients_capped ? "+" : ""}
                    </td>
                    <td>
                      <Sparkline points={u.daily.map(([, n]) => n)} />
                    </td>
                    <td className="small">{u.last_success ? when(u.last_success) : <span className="muted">never</span>}</td>
                    <td className="small muted">{u.reason}</td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
      </Card>

      <div className="split split-even">
        <Card title={`Traffic the code does not explain (${traffic.shadow_routes_total})`} flush>
          <p className="muted small" style={{ padding: "0 1.25rem" }}>
            Successful requests to routes found in no scanned code: served by another system, a
            gateway rule, or code this scan could not read. Each is a shadow API until someone owns it.
          </p>
          <UnmatchedTable rows={traffic.shadow_routes} />
        </Card>
        <Card title={`Probing (${traffic.probing_total})`} flush>
          <p className="muted small" style={{ padding: "0 1.25rem" }}>
            Routes that only ever failed (401, 403, 404): someone looking for endpoints. Useful for
            the security team; never counted as use.
          </p>
          <UnmatchedTable rows={traffic.probing} />
        </Card>
      </div>

      <Card title="Files read" flush>
        <div className="table-wrap">
          <table>
            <thead>
              <tr>
                <th>File</th>
                <th>Format</th>
                <th className="r">Lines</th>
                <th className="r">Recognised</th>
                <th>Note</th>
              </tr>
            </thead>
            <tbody>
              {traffic.files.map((f) => (
                <tr key={f.name}>
                  <td>
                    <code>{f.name}</code>
                  </td>
                  <td>{f.format}</td>
                  <td className="r num">{f.lines.toLocaleString()}</td>
                  <td className="r num">{f.parsed.toLocaleString()}</td>
                  <td className="small muted">{f.note}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
        <p className="muted small" style={{ padding: "0.5rem 1.25rem 1rem", margin: 0 }}>
          Imported by {traffic.imported_by}, {when(traffic.imported_at)}. Recorded in the{" "}
          <a href={`#results/${job.id}/audit`}>audit log</a> with a fingerprint of the result.
        </p>
      </Card>
    </>
  );
}

function UnmatchedTable({ rows }: { rows: Traffic["shadow_routes"] }) {
  if (!rows.length) return <p className="muted small" style={{ padding: "0 1.25rem 1rem" }}>None.</p>;
  return (
    <div className="table-wrap">
      <table>
        <thead>
          <tr>
            <th>Route</th>
            <th className="r">Requests</th>
            <th className="r">Clients</th>
          </tr>
        </thead>
        <tbody>
          {rows.slice(0, 12).map((r) => (
            <tr key={`${r.method} ${r.path}`}>
              <td>
                <MethodPath method={r.method} path={r.path} />
              </td>
              <td className="r num">{r.requests.toLocaleString()}</td>
              <td className="r num">{r.clients.toLocaleString()}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
