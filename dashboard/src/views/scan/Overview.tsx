import { Card, LevelBadge, LifecycleBadge } from "../../common";
import type { Lifecycle, ScanJob } from "../../types";
import { ScanStages, TrustCard } from "../explain";
import { CandidatesCard } from "./Candidates";
import { CHECK_TEXT, DECISIONS, when } from "./shared";

const TONE: Record<string, string> = {
  "Zombie candidates": "tile-bad",
  "Likely zombies": "tile-bad",
  Undocumented: "tile-warn",
  "No owner": "tile-warn",
  "Deprecated in spec": "tile-info",
};

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
          <div className={`tile ${TONE[s.label] ?? ""}`} key={s.label}>
            <div className="tile-label">{s.label}</div>
            <div className="tile-value">{s.value}</div>
          </div>
        ))}
      </div>

      {job.traffic && <UsageSummary job={job} />}

      <CandidatesCard job={job} />

      <Card title="Can these results be trusted?">
        <TrustCard job={job} />
      </Card>

      <div className="split split-even">
        <ExposureCard job={job} />
        <ChangesCard job={job} />
      </div>

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

      <Card title="How this scan was done">
          <ScanStages />
          <h3>What each stage found</h3>
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

function UsageSummary({ job }: { job: ScanJob }) {
  const t = job.traffic!;
  const order: Lifecycle[] = ["ZOMBIE", "ORPHANED", "DEPRECATED", "ACTIVE", "INDETERMINATE"];
  return (
    <Card
      title="Proven by usage"
      actions={<a className="small" href={`#results/${job.id}/usage`}>Open usage</a>}
    >
      <p className="small muted" style={{ marginTop: 0 }}>
        {t.requests.toLocaleString()} requests over {t.window.days ?? "?"} days of access logs,
        imported by {t.imported_by}.
      </p>
      <ul className="legend" style={{ marginTop: 0 }}>
        {order.map((k) => (
          <li key={k}>
            <LifecycleBadge label={k} /> <strong className="num">{t.lifecycle[k] ?? 0}</strong>
          </li>
        ))}
      </ul>
    </Card>
  );
}

/** What the endpoints handle, inferred from their paths: a bank triages by exposure. */
function ExposureCard({ job }: { job: ScanJob }) {
  const eps = job.report!.endpoints;
  const groups = new Map<string, { level: string; total: number; flagged: number }>();
  for (const e of eps) {
    const s = e.sensitivity;
    if (!s) continue;
    const g = groups.get(s.category) ?? { level: s.level, total: 0, flagged: 0 };
    g.total += 1;
    const zombie = job.traffic?.endpoints[e.id]?.lifecycle === "ZOMBIE";
    if (e.candidate || zombie || !e.documented) g.flagged += 1;
    groups.set(s.category, g);
  }
  const rank = { high: 0, medium: 1, low: 2 } as Record<string, number>;
  const rows = [...groups.entries()].sort(
    (a, b) => (rank[a[1].level] ?? 3) - (rank[b[1].level] ?? 3) || b[1].total - a[1].total,
  );
  return (
    <Card title="Exposure by data handled">
      {rows.length === 0 ? (
        <p className="muted">No endpoints.</p>
      ) : (
        <ul className="finding-bars">
          {rows.map(([cat, g]) => (
            <li key={cat}>
              <span>
                <LevelBadge level={g.level} category={cat} />
              </span>
              <span className="bar-track" aria-hidden="true">
                <span className="bar neg" style={{ width: `${(g.flagged / Math.max(g.total, 1)) * 100}%` }} />
              </span>
              <span className="finding-count" title="flagged / total">
                {g.flagged}/{g.total}
              </span>
            </li>
          ))}
        </ul>
      )}
      <p className="muted small" style={{ marginBottom: 0 }}>
        Flagged: undocumented, a zombie candidate, or unused in the logs. Categories are read from
        path words, a heuristic that orders the queue and never decides a removal.
      </p>
    </Card>
  );
}

function ChangesCard({ job }: { job: ScanJob }) {
  const c = job.changes;
  if (!c) {
    return (
      <Card title="Changes since the previous scan">
        <p className="muted small" style={{ margin: 0 }}>
          {job.kind === "github"
            ? "This is the first scan of this repository. Re-scan it later to see endpoints added, removed, or newly undocumented: the drift an auditor asks about."
            : "Drift is tracked for GitHub scans, which can be re-scanned. An uploaded folder is a one-off snapshot."}
        </p>
      </Card>
    );
  }
  const items: [string, string, string[]][] = [
    ["diff-add", "+", c.added_undocumented.map((x) => `${x} (new, undocumented)`)],
    ["diff-add", "+", c.new_candidates.filter((x) => !c.added_undocumented.includes(x)).map((x) => `${x} (new zombie candidate)`)],
    ["diff-mod", "~", c.became_undocumented.map((x) => `${x} (removed from the spec, still in code)`)],
    ["diff-add", "+", c.added.filter((x) => !c.added_undocumented.includes(x)).map((x) => `${x} (new)`)],
    ["diff-del", "-", c.removed.map((x) => `${x} (removed)`)],
    ["diff-del", "-", c.resolved_candidates.map((x) => `${x} (no longer a candidate)`)],
  ];
  const lines = items.flatMap(([cls, mark, xs]) => xs.map((x) => ({ cls, mark, x })));
  return (
    <Card title="Changes since the previous scan">
      <p className="muted small" style={{ marginTop: 0 }}>
        Against <a href={`#results/${c.previous.id}/overview`}>the scan of {when(c.previous.finished_at)}</a>
        {c.previous.commit ? <> at <code>{c.previous.commit}</code></> : null}; {c.unchanged} endpoint(s) unchanged.
      </p>
      {c.same_commit && lines.length > 0 && (
        <p className="warning small">
          Both scans read the same commit, so the code did not change: these differences come from a
          newer version of the scanner reading it better, not from drift in the project.
        </p>
      )}
      {lines.length === 0 ? (
        <p className="good-text small" style={{ margin: 0 }}>No change to the API surface.</p>
      ) : (
        <ul className="diff">
          {lines.slice(0, 14).map((l) => (
            <li key={l.x} className={l.cls}>
              <span className="diff-mark">{l.mark}</span>
              <code>{l.x}</code>
            </li>
          ))}
          {lines.length > 14 && <li className="muted small">and {lines.length - 14} more</li>}
        </ul>
      )}
    </Card>
  );
}
