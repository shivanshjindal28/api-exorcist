import { useEffect, useState } from "react";
import { ApiError } from "../../api";
import { Card, ErrorBox, LifecycleBadge, Loading, MethodPath, useSession } from "../../common";
import type { RetirementPlan, Review, ScanJob } from "../../types";
import { CandidateBadge } from "./Candidates";
import { ReviewBadge, ReviewControls, ago } from "./shared";

/** What Safe Kill needs before it may remove anything, and whether this scan has it. */
type Status = "ok" | "partial" | "unavailable";
const STATUS_TEXT: Record<Status, string> = { ok: "have it", partial: "partly", unavailable: "missing" };

function prerequisites(job: ScanJob): { step: string; status: Status; why: string }[] {
  const consulted = job.report?.sources?.consulted ?? [];
  const found = (job.report?.endpoints.length ?? 0) > 0;
  const graph = job.report?.graph;
  const imported = job.traffic ?? null;
  const days = imported?.window.days ?? 0;
  const traffic = consulted.includes("TRAFFIC");
  const usage: { status: Status; why: string } = traffic
    ? { status: "ok", why: "observed traffic" }
    : imported
      ? days >= 90
        ? { status: "ok", why: `${imported.requests.toLocaleString()} requests over ${days} days of imported access logs` }
        : {
            status: "partial",
            why: `${days} days of access logs imported; 90 give 95% confidence of catching a caller that calls once a month`,
          }
      : {
          status: "unavailable",
          why: "needs traffic logs from a gateway or a network sensor; a project's files have none. Import access logs on the Usage view",
        };
  return [
    {
      step: "An inventory of the endpoints",
      status: found ? "ok" : "unavailable",
      why: found ? "this scan found them in the code" : "this scan found no endpoints",
    },
    {
      step: "Usage data, to classify an endpoint as a zombie",
      status: usage.status,
      why: usage.why,
    },
    {
      step: "A dependency graph, to prove nothing calls it",
      status: traffic ? "ok" : graph ? "partial" : "unavailable",
      why: traffic
        ? "built from observed calls between services"
        : graph
          ? `drawn from the code (${graph.stats.calls ?? 0} call(s) between services): it shows what the code can call, but not callers outside the repository, so "nothing calls it" is not proven`
          : "built from observed calls between services, which come from traffic",
    },
    {
      step: "Control of the gateway, to shadow, canary and roll back",
      status: consulted.includes("GATEWAY") ? "ok" : imported ? "partial" : "unavailable",
      why: imported
        ? "no gateway is connected, so each retirement plan below gives the exact gateway change to apply, and to reverse, by hand"
        : "Safe Kill acts through the gateway in front of the API; none is connected",
    },
  ];
}

export function ScanSafeKillTab({
  job,
  onReviewed,
}: {
  job: ScanJob;
  onReviewed: (reviews: Record<string, Review>) => void;
}) {
  const report = job.report!;
  const reviews = job.reviews ?? {};
  const steps = prerequisites(job);
  const [open, setOpen] = useState<string | null>(null);

  // Unreviewed first, then the strongest zombie candidates: the queue a
  // reviewer works down.
  const queue = [...report.endpoints].sort(
    (a, b) =>
      Number(Boolean(reviews[a.id])) - Number(Boolean(reviews[b.id])) ||
      (b.candidate?.score ?? 0) - (a.candidate?.score ?? 0) ||
      b.findings.length - a.findings.length ||
      b.risk - a.risk ||
      a.id.localeCompare(b.id),
  );

  return (
    <div className="stack">
      <Card title={job.traffic ? "What removal needs, and what this scan has" : "Why nothing is removed from a project scan"}>
        <p>
          Safe Kill removes an endpoint only after four things hold.{" "}
          {job.traffic
            ? "Imported access logs supply the usage evidence; the gateway changes are applied by your team from the plans below."
            : "A project scan provides the first and part of the third; the rest need the running system."}
        </p>
        <ul className="checks">
          {steps.map((s) => (
            <li key={s.step} className={`check check-${s.status}`}>
              <span className="check-status">{STATUS_TEXT[s.status]}</span>
              <span className="check-name">{s.step}</span>
              <span className="check-detail">{s.why}</span>
            </li>
          ))}
        </ul>
        <p className="muted small">
          Removing an endpoint on the strength of its code alone is how outages happen: the
          code cannot show a month-end batch job that still calls it. See Safe Kill working
          end to end in the <a href="#results/demo/safekill">demo bank</a>, where traffic and
          a gateway exist.
        </p>
      </Card>

      <RetirementPlans job={job} />

      <Card title={`Review queue (${Object.keys(reviews).length} of ${report.endpoints.length} decided)`}>
        <p className="muted small">
          What can be done now is triage. Each decision is recorded under your name in this
          scan's <a href={`#results/${job.id}/audit`}>audit log</a>. "Investigate for removal"
          marks the endpoints to watch once usage data is connected.
        </p>
        <div className="table-wrap">
          <table>
            <thead>
              <tr>
                <th>Endpoint</th>
                <th>Candidate</th>
                <th>Findings</th>
                <th>Last changed</th>
                <th>Decision</th>
              </tr>
            </thead>
            <tbody>
              {queue.map((e) => (
                <QueueRow
                  key={e.id}
                  open={open === e.id}
                  toggle={() => setOpen(open === e.id ? null : e.id)}
                  e={e}
                  job={job}
                  review={reviews[e.id]}
                  onReviewed={onReviewed}
                  shared={report.repository_findings.length}
                />
              ))}
            </tbody>
          </table>
        </div>
      </Card>
    </div>
  );
}

function QueueRow({
  e,
  job,
  review,
  open,
  toggle,
  onReviewed,
  shared,
}: {
  e: NonNullable<ScanJob["report"]>["endpoints"][number];
  job: ScanJob;
  review: Review | undefined;
  open: boolean;
  toggle: () => void;
  onReviewed: (reviews: Record<string, Review>) => void;
  shared: number;
}) {
  return (
    <>
      <tr className={open ? "selected" : undefined}>
        <td>
          <button className="link" onClick={toggle} aria-expanded={open}
            aria-label={`Review ${e.id}`}>
            <code>
              <span className="method">{e.method}</span> {e.path}
            </code>
          </button>
        </td>
        <td>
          {e.candidate ? <CandidateBadge label={e.candidate.label} /> : <span className="muted">no</span>}
        </td>
        <td>{e.findings.length + shared}</td>
        <td className="small">{ago(e.last_change_days)}</td>
        <td>
          <ReviewBadge review={review} />
        </td>
      </tr>
      {open && (
        <tr className="detail-row">
          <td colSpan={5}>
            {e.candidate && (
              <ul className="signals">
                {e.candidate.signals.map((s) => (
                  <li key={s.text} className={s.weight < 0 ? "sig-against" : undefined}>
                    <span className="sig-weight">{s.weight > 0 ? `+${s.weight}` : s.weight}</span>
                    {s.text}
                  </li>
                ))}
              </ul>
            )}
            {e.findings.length > 0 && (
              <ul className="findings">
                {e.findings.map((f) => (
                  <li key={f}>{f}</li>
                ))}
              </ul>
            )}
            <ReviewControls jobId={job.id} e={e} review={review} onReviewed={onReviewed} />
          </td>
        </tr>
      )}
    </>
  );
}

/** Step-by-step retirement for the endpoints the evidence points at. */
function RetirementPlans({ job }: { job: ScanJob }) {
  const report = job.report!;
  const usage = job.traffic?.endpoints ?? null;
  const targets = usage
    ? report.endpoints.filter((e) => usage[e.id]?.lifecycle === "ZOMBIE")
    : report.endpoints.filter((e) => e.candidate?.label === "Likely zombie");
  const ordered = [...targets].sort((a, b) => (b.priority ?? 0) - (a.priority ?? 0));
  const [chosen, setChosen] = useState<string | null>(ordered[0]?.id ?? null);

  return (
    <Card title={`Retirement plans (${ordered.length})`}>
      {ordered.length === 0 ? (
        <p className="muted small" style={{ margin: 0 }}>
          {usage
            ? "The imported logs show no endpoint unused for the whole window, so nothing is ready to retire."
            : "No likely zombie in this scan. Plans are drafted for likely zombies, and for every endpoint the imported access logs prove unused."}
        </p>
      ) : (
        <div className="split">
          <div className="table-wrap">
            <table>
              <thead>
                <tr>
                  <th>Endpoint</th>
                  <th>{usage ? "Usage" : "Evidence"}</th>
                </tr>
              </thead>
              <tbody>
                {ordered.map((e) => (
                  <tr key={e.id} className={chosen === e.id ? "selected" : undefined}>
                    <td>
                      <button className="link" onClick={() => setChosen(e.id)} aria-pressed={chosen === e.id}
                        aria-label={`Retirement plan for ${e.id}`}>
                        <MethodPath method={e.method} path={e.path} />
                      </button>
                    </td>
                    <td>
                      {usage?.[e.id] ? <LifecycleBadge label={usage[e.id]!.lifecycle} /> : (
                        <span className="small">{e.candidate?.label}</span>
                      )}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
          {chosen && <PlanView jobId={job.id} endpointId={chosen} />}
        </div>
      )}
    </Card>
  );
}

function PlanView({ jobId, endpointId }: { jobId: string; endpointId: string }) {
  const { api } = useSession();
  const [plan, setPlan] = useState<RetirementPlan | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let live = true;
    setPlan(null);
    setError(null);
    api
      .plan(jobId, endpointId)
      .then((p) => live && setPlan(p))
      .catch((e: unknown) => live && setError(e instanceof ApiError ? e.message : String(e)));
    return () => {
      live = false;
    };
  }, [api, jobId, endpointId]);

  if (error) return <ErrorBox message={error} />;
  if (!plan) return <Loading what="the plan" />;
  return (
    <div className="plan">
      <div className="buttons">
        {plan.ready ? (
          <span className="state state-good">ready to start</span>
        ) : (
          <span className="state state-warn">blocked</span>
        )}
        <span className="muted small">Proposed sunset {plan.sunset}</span>
      </div>
      {plan.blockers.length > 0 && (
        <ul className="blockers small">
          {plan.blockers.map((b) => (
            <li key={b}>{b}</li>
          ))}
        </ul>
      )}
      <ol className="plan-steps">
        {plan.steps.map((st) => (
          <li key={st.title}>
            <h4>{st.title}</h4>
            <p className="small">{st.detail}</p>
            {st.snippet && (
              <>
                <div className="snippet-label">{st.snippet_label}</div>
                <pre className="snippet">{st.snippet}</pre>
              </>
            )}
            {st.where && st.where.length > 0 && (
              <p className="small">
                Handler: <code>{st.where.join(", ")}</code>
              </p>
            )}
          </li>
        ))}
      </ol>
    </div>
  );
}
