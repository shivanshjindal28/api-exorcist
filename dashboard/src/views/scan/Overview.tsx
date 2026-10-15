import { Card } from "../../common";
import type { ScanJob } from "../../types";
import { CandidatesCard } from "./Candidates";
import { CHECK_TEXT, DECISIONS } from "./shared";

export function ScanOverviewTab({ job }: { job: ScanJob }) {
  const report = job.report!;
  const total = report.endpoints.length;

  // Every finding, counted across endpoints. Project-wide ones hold for all.
  const counts = new Map<string, number>();
  for (const f of report.repository_findings) counts.set(f, total);
  for (const e of report.endpoints) {
    for (const f of e.findings) counts.set(f, (counts.get(f) ?? 0) + 1);
  }
  const findings = [...counts.entries()].sort((a, b) => b[1] - a[1]);

  const reviews = job.reviews ?? {};
  const reviewed = Object.keys(reviews).length;

  return (
    <div className="stack">
      <div className="tiles">
        {report.summary.map((s) => (
          <div className="tile" key={s.label}>
            <div className="tile-value">{s.value}</div>
            <div className="tile-label">{s.label}</div>
          </div>
        ))}
      </div>

      <CandidatesCard job={job} />

      <div className="split split-even">
          <Card title="Findings">
            {findings.length === 0 ? (
              <p className="muted">No findings: every endpoint is documented, owned and current.</p>
            ) : (
              <ul className="finding-bars">
                {findings.map(([f, n]) => (
                  <li key={f}>
                    <span className="finding-text">{f}</span>
                    <span className="bar-track" aria-hidden="true">
                      <span className="bar neg" style={{ width: `${(n / Math.max(total, 1)) * 100}%` }} />
                    </span>
                    <span className="finding-count">
                      {n}/{total}
                    </span>
                  </li>
                ))}
              </ul>
            )}
          </Card>
          <Card title="Review progress">
            <p>
              {reviewed} of {total} endpoint(s) have a recorded decision.{" "}
              <a href={`#results/${job.id}/safekill`}>Open the review queue</a>.
            </p>
            {reviewed > 0 && (
              <ul className="legend">
                {DECISIONS.map((d) => {
                  const n = Object.values(reviews).filter((r) => r.decision === d.key).length;
                  return n ? (
                    <li key={d.key}>
                      <span className={`review review-${d.key}`}>{d.label}</span> {n}
                    </li>
                  ) : null;
                })}
              </ul>
            )}
          </Card>
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
              The <a href="#results/demo/overview">demo bank</a> shows the full classification,
              where usage data exists.
            </p>
          )}
      </Card>
    </div>
  );
}
