import { useState } from "react";
import { Contributions } from "../../charts";
import { Card } from "../../common";
import { WhatWouldChange } from "../explain";
import type { Candidate, ScanJob } from "../../types";

const LABEL_CLASS: Record<string, string> = {
  "Likely zombie": "cand-likely",
  "Superseded version": "cand-superseded",
  "Deprecated but served": "cand-deprecated",
  "Debug or test endpoint": "cand-debug",
  "Not used by this project's clients": "cand-unused",
  "Undocumented (shadow)": "cand-shadow",
};

export function CandidateBadge({ label }: { label: string }) {
  return <span className={`cand ${LABEL_CLASS[label] ?? "cand-other"}`}>{label}</span>;
}

/** What evidence a scan looked for, and which this repository lacked. */
function evidenceAbsent(job: ScanJob): string[] {
  const r = job.report!;
  const out: string[] = [];
  const versioned = r.endpoints.some((e) => /\/v\d+(\.\d+)?(\/|$)/i.test(e.path));
  if (!versioned) out.push("no versioned paths (v1, v2...), so nothing can be superseded");
  if (!r.endpoints.some((e) => e.documented)) {
    out.push("no API specification, so nothing can be undocumented among documented neighbours or marked deprecated in one");
  }
  const clients = r.checks.find((c) => c.name === "This project's own clients");
  if (!clients || clients.status !== "ok") {
    out.push("no front end, SDK or other client in the repository, so use by clients cannot be judged");
  }
  return out;
}

export function CandidatesCard({ job }: { job: ScanJob }) {
  const r = job.report!;
  const candidates: Candidate[] = r.candidates ?? [];
  const [open, setOpen] = useState<string | null>(candidates[0]?.endpoint_id ?? null);

  if (!r.candidates) {
    return (
      <Card title="Zombie candidates">
        <p className="muted">
          This scan was made before zombie candidates were computed. Scan the project again.
        </p>
      </Card>
    );
  }

  if (candidates.length === 0) {
    const absent = evidenceAbsent(job);
    return (
      <Card title="Zombie candidates: none">
        <p>
          Nothing in this repository marks any of its {r.endpoints.length} endpoint(s) as likely
          dead or dangerous.
        </p>
        {absent.length > 0 && (
          <>
            <p className="muted small">The evidence a repository can hold, and what this one lacks:</p>
            <ul className="small">
              {absent.map((a) => (
                <li key={a}>{a}</li>
              ))}
            </ul>
          </>
        )}
        <p className="muted small">
          That is a property of the repository, not a failure of the scan. Traffic would settle
          it; the <a href="#results/demo/overview">demo bank</a> shows the classification with it.
        </p>
      </Card>
    );
  }

  const max = Math.max(...candidates.map((c) => c.score), 1);
  return (
    <Card title={`Zombie candidates (${candidates.length})`}>
      <p className="muted small">
        Ranked by the code evidence against each endpoint. Suspected, not proven: confirming one
        takes usage data, which Safe Kill's shadow window collects before anything is removed.
      </p>
      <ol className="candidates">
        {candidates.map((c) => {
          const isOpen = open === c.endpoint_id;
          const [method, ...rest] = c.endpoint_id.split(" ");
          return (
            <li key={c.endpoint_id} className={isOpen ? "open" : undefined}>
              <button
                className="link cand-row"
                onClick={() => setOpen(isOpen ? null : c.endpoint_id)}
                aria-expanded={isOpen}
                aria-label={`Evidence for ${c.endpoint_id}`}
              >
                <CandidateBadge label={c.label} />
                <code>
                  <span className={`method m-${method}`}>{method}</span> {rest.join(" ")}
                </code>
                <span className="cand-score" aria-label={`score ${c.score}`}>
                  <span className="bar-track">
                    <span className="bar neg" style={{ width: `${(c.score / max) * 100}%` }} />
                  </span>
                  {c.score}
                </span>
              </button>
              {isOpen && (
                <div className="cand-open">
                  <Contributions items={c.signals} total={c.score} />
                  <WhatWouldChange
                    current={c.label.toLowerCase()}
                    items={c.counterfactuals?.map((f) => ({
                      if: f.if,
                      to: f.label === "not a candidate" ? <strong>not a candidate</strong> : <CandidateBadge label={f.label} />,
                      note: `(score ${f.score})`,
                    }))}
                  />
                </div>
              )}
            </li>
          );
        })}
      </ol>
    </Card>
  );
}
