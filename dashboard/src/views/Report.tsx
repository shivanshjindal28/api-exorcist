import { ErrorBox, LevelBadge, Loading, Page, PageHead, useLoad, useSession } from "../common";
import { IconReport } from "../icons";
import type { ScanAudit, ScanEndpoint, ScanJob } from "../types";
import { CHECK_TEXT, when } from "./scan/shared";

/** One recommended next step per endpoint, from the strongest evidence it has. */
export function recommend(e: ScanEndpoint, lifecycle: string | undefined): string {
  const label = e.candidate?.label ?? "";
  if (lifecycle === "ZOMBIE") return "Retire: announce a sunset, watch 90 days, then 410 Gone";
  if (lifecycle === "DEPRECATED") return "Migrate the remaining callers, then retire";
  if (label === "Debug or test endpoint" && lifecycle) {
    return "A debug route in use: find its callers, then remove it from production";
  }
  if (lifecycle === "ORPHANED") {
    return e.documented ? "Assign an owning team; do not remove" : "Assign an owner and document it; do not remove";
  }
  if (label === "Likely zombie") return "Import usage logs to confirm, then retire";
  if (label === "Debug or test endpoint") return "Remove from production builds";
  if (label === "Superseded version") return "Confirm no client uses it, then retire";
  if (label === "Deprecated but served") return "Set a removal date";
  if (!e.documented) return "Document it, or retire it";
  if (label) return "Review";
  return "No action";
}

export function ExecutiveReport({ id }: { id: string }) {
  const { api } = useSession();
  const scan = useLoad<ScanJob>(() => api.scan(id), [id]);
  const audit = useLoad<ScanAudit>(() => api.scanAudit(id), [id]);

  const crumbs = [
    { label: "Projects", href: "#results" },
    { label: scan.data?.target ?? id, href: `#results/${id}/overview` },
    { label: "Executive report" },
  ];
  const head = <PageHead title="Executive report" crumbs={crumbs} />;
  if (scan.error) return <Page head={head}><ErrorBox message={scan.error} /></Page>;
  if (!scan.data) return <Page head={head}><Loading what="the report" /></Page>;
  const job = scan.data;
  if (!job.report) {
    return <Page head={head}><ErrorBox message="This scan has not finished, so there is nothing to report yet." /></Page>;
  }

  const r = job.report;
  const usage = job.traffic?.endpoints ?? {};
  const eps = [...r.endpoints].sort((a, b) => (b.priority ?? 0) - (a.priority ?? 0));
  const undocumented = eps.filter((e) => !e.documented).length;
  const cands = r.candidates ?? [];
  const likely = cands.filter((c) => c.label === "Likely zombie").length;
  const zombies = Object.values(usage).filter((u) => u.lifecycle === "ZOMBIE").length;
  const sensitive = eps.filter((e) => e.sensitivity?.level === "high").length;
  const flaggedSensitive = eps.filter(
    (e) => e.sensitivity?.level === "high" && (e.candidate || !e.documented || usage[e.id]?.lifecycle === "ZOMBIE"),
  ).length;
  const actions = eps
    .filter((e) => recommend(e, usage[e.id]?.lifecycle) !== "No action")
    .slice(0, 12);
  const reviewed = Object.keys(job.reviews ?? {}).length;
  const pct = (n: number) => (eps.length ? Math.round((n / eps.length) * 100) : 0);

  return (
    <Page head={head}>
      <div className="report-tools no-print">
        <a className="btn secondary" href={`#results/${id}/overview`}>
          Back to the scan
        </a>
        <button onClick={() => window.print()}>
          <IconReport />
          Print or save as PDF
        </button>
      </div>
      <article className="report">
        <div className="muted small">API Exorcist · API inventory and retirement report</div>
        <h1>{job.target}</h1>
        <p className="report-meta">
          Scanned {when(job.finished_at ?? job.created_at)} by {job.requested_by}
          {r.details.commit ? `, at commit ${r.details.commit}` : ""}. Report generated {new Date().toLocaleString()}.
        </p>

        <h2>Summary</h2>
        <p>
          The scan found <strong>{eps.length}</strong> API endpoints. <strong>{undocumented}</strong> ({pct(undocumented)}%)
          are not in the API specification, which makes them shadow APIs: nobody outside the code
          knows they exist. <strong>{cands.length}</strong> look abandoned from code evidence
          {likely ? <>, <strong>{likely}</strong> of them strongly</> : null}.{" "}
          {job.traffic ? (
            <>
              Access logs covering {job.traffic.window.days} days prove <strong>{zombies}</strong> endpoint(s)
              received no successful request in that time.
            </>
          ) : (
            <>No usage logs were imported, so no endpoint is proven unused yet.</>
          )}{" "}
          {sensitive > 0 && (
            <>
              <strong>{flaggedSensitive}</strong> of the {sensitive} endpoints handling authentication, payments,
              cards, identity or administration carry at least one of these findings.
            </>
          )}
        </p>

        <div className="tiles">
          <div className="tile"><div className="tile-label">Endpoints</div><div className="tile-value">{eps.length}</div></div>
          <div className="tile tile-warn"><div className="tile-label">Undocumented</div><div className="tile-value">{undocumented}</div></div>
          <div className="tile tile-bad"><div className="tile-label">Zombie candidates</div><div className="tile-value">{cands.length}</div><div className="tile-note">{likely} likely</div></div>
          <div className="tile tile-bad"><div className="tile-label">Proven unused</div><div className="tile-value">{job.traffic ? zombies : "-"}</div><div className="tile-note">{job.traffic ? `${job.traffic.window.days} days of logs` : "no logs imported"}</div></div>
        </div>

        <h2>Priority actions</h2>
        {actions.length === 0 ? (
          <p>No endpoint needs action.</p>
        ) : (
          <table>
            <thead>
              <tr>
                <th>Endpoint</th>
                <th>Handles</th>
                <th>Evidence</th>
                <th>Recommended action</th>
              </tr>
            </thead>
            <tbody>
              {actions.map((e) => (
                <tr key={e.id}>
                  <td><code>{e.id}</code></td>
                  <td>{e.sensitivity && <LevelBadge level={e.sensitivity.level} category={e.sensitivity.category} />}</td>
                  <td className="small">
                    {usage[e.id]?.lifecycle === "ZOMBIE"
                      ? "No successful request in the logged window"
                      : e.candidate?.label ??
                        (!e.documented ? "Undocumented" : usage[e.id]?.lifecycle === "ORPHANED" ? "In use, no owner recorded" : "")}
                  </td>
                  <td className="small">{recommend(e, usage[e.id]?.lifecycle)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        )}

        <h2>Coverage: what was checked</h2>
        <table>
          <tbody>
            {r.checks.map((c) => (
              <tr key={c.name}>
                <td style={{ width: "9rem" }} className={`check-${c.status}`}>
                  <span className="check-status">{CHECK_TEXT[c.status]}</span>
                </td>
                <td style={{ width: "14rem" }}><strong>{c.name}</strong></td>
                <td className="small">{c.detail}</td>
              </tr>
            ))}
          </tbody>
        </table>

        <h2>Governance</h2>
        <p>
          {reviewed} of {eps.length} endpoints have a recorded review decision. Every decision, the scan itself and
          any usage import are written to a hash-chained audit log, so an edited entry is detectable.{" "}
          {audit.data && (
            <>
              At the time of this report the chain holds {audit.data.chain.entries} entries and{" "}
              {audit.data.chain.ok ? <strong>verifies intact</strong> : <strong className="bad-text">does not verify</strong>}; its head is{" "}
              <code>{audit.data.head.slice(0, 16)}</code>.
            </>
          )}
        </p>

        <h2>Method and limits</h2>
        <p className="small">
          Endpoints are read from source code by AST analysis and from the API specification; nothing from the
          project is executed. Zombie candidates are suspected from code evidence (a newer version of the same
          operation, deprecation markers, what the project's own clients call, debug routes, change history) and
          are labelled suspected, not proven. An endpoint is called unused only from imported access logs, only
          where the logs cover its service, and only over at least seven days; failed requests never count as
          use. Data categories are inferred from path words and order the work; they never decide a removal.
        </p>
        <div className="report-foot">
          Generated by API Exorcist. Scan {job.id}. This report describes the code and logs supplied; it is not a
          penetration test.
        </div>
      </article>
    </Page>
  );
}
