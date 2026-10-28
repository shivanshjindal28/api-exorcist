/**
 * Explanations of how the system reaches its conclusions, shown beside the
 * conclusions themselves: the arithmetic of a classification, the steps of a
 * Safe Kill removal, the stages of a repository scan, and what makes an
 * endpoint found in code a real one.
 */
import type { SafeKillState, ScanEndpoint, ScanJob, ScoreRow, Verdict } from "../types";

const CLASSES = ["ACTIVE", "DEPRECATED", "ORPHANED", "ZOMBIE"] as const;

const TEMPERATURE = 3;

function signed(x: number): string {
  if (x === 0) return "";
  return `${x > 0 ? "+" : "−"}${Math.abs(x).toFixed(1)}`;
}

/** Softmax confidence of `label`, as the engine computes it (temperature 3). */
export function softmaxConfidence(scores: Record<string, number>, label: string): number {
  const exps = CLASSES.map((c) => Math.exp((scores[c] ?? 0) / TEMPERATURE));
  const sum = exps.reduce((a, b) => a + b, 0);
  return Math.exp((scores[label] ?? 0) / TEMPERATURE) / sum;
}

/** The complete arithmetic behind a rule-decided verdict. */
export function ScoreTable({ verdict: v }: { verdict: Verdict }) {
  const rows: ScoreRow[] = v.score_table ?? [];
  if (!v.score_table) {
    return (
      <p className="muted small">
        This server does not report the score table; the evidence above lists what bore on
        the label.
      </p>
    );
  }
  if (rows.length === 0) {
    return (
      <p className="muted small">
        {v.decided_by === "model"
          ? "Decided by the learned model, whose reasons are the SHAP contributions above; the rule score table does not apply."
          : "No rule could be evaluated, so no score was computed: the label is indeterminate, not a conclusion."}
      </p>
    );
  }
  const totals = Object.fromEntries(
    CLASSES.map((c) => [c, rows.reduce((s, r) => s + (r.weights[c] ?? 0), 0)]),
  ) as Record<string, number>;
  const conf = softmaxConfidence(totals, v.label);
  const label = v.label as string;

  return (
    <div className="score-table">
      <p className="small">
        Every rule whose sources were consulted and whose condition holds adds its signed
        weight to <em>all four</em> classes. The highest total wins.
      </p>
      <div className="table-wrap">
        <table>
          <thead>
            <tr>
              <th>Rule that fired</th>
              {CLASSES.map((c) => (
                <th key={c} className={c === label ? "num winner" : "num"}>
                  {c.toLowerCase()}
                </th>
              ))}
            </tr>
          </thead>
          <tbody>
            {rows.map((r) => (
              <tr key={r.key}>
                <td>
                  {r.statement} <span className="muted small">({r.source})</span>
                </td>
                {CLASSES.map((c) => (
                  <td
                    key={c}
                    className={`num ${c === label ? "winner" : ""} ${
                      (r.weights[c] ?? 0) > 0 ? "pos" : (r.weights[c] ?? 0) < 0 ? "neg" : ""
                    }`}
                  >
                    {signed(r.weights[c] ?? 0)}
                  </td>
                ))}
              </tr>
            ))}
          </tbody>
          <tfoot>
            <tr>
              <th>Total</th>
              {CLASSES.map((c) => (
                <th key={c} className={c === label ? "num winner" : "num"}>
                  {signed(totals[c] ?? 0) || "0.0"}
                </th>
              ))}
            </tr>
          </tfoot>
        </table>
      </div>
      <p className="small">
        <strong>{label.toLowerCase()}</strong> has the highest total. Confidence is the
        softmax of the four totals at temperature {TEMPERATURE}: e<sup>{(totals[label] ?? 0).toFixed(1)}/
        {TEMPERATURE}</sup> divided by the sum of e<sup>total/{TEMPERATURE}</sup> over all four
        classes = <strong>{(conf * 100).toFixed(1)}%</strong>. A close second makes it low, which
        is the signal that the evidence does not settle the case.
      </p>
      {(v.abstained ?? []).length > 0 && (
        <p className="muted small">
          Not evaluated, because a source they need was never consulted:{" "}
          {(v.abstained ?? []).map((k) => k.toLowerCase().replace(/_/g, " ")).join(", ")}. An
          unconsulted source is not evidence of absence.
        </p>
      )}
    </div>
  );
}

interface Step {
  title: string;
  does: string;
  stops: string;
  /** Candidate statuses that sit at, or ended at, this step. */
  here: string[];
}

function safeKillSteps(policy: SafeKillState["policy"]): Step[] {
  const [c5, c25, c100] = policy.canary_days;
  return [
    {
      title: "Removal gate",
      does:
        "The classifier must call it ZOMBIE with usage evidence, and the dependency graph must find nothing calling it.",
      stops: "Any observed caller, an indeterminate verdict, or the learned model's veto blocks it.",
      here: ["BLOCKED", "NOT_STARTED"],
    },
    {
      title: `Shadow, ${policy.shadow_days} days`,
      does:
        `Nothing is refused; every request that would have been is recorded with its caller. The length catches a caller who calls once a month with ${Math.round(policy.confidence * 100)}% confidence.`,
      stops: "Any identified caller rejects the removal and names the caller.",
      here: ["SHADOW", "REJECTED"],
    },
    {
      title: "Named approval",
      does:
        "A person holding an approver token sees the evidence and the shadow's result, and approves or declines. Their name comes from the token.",
      stops:
        "A decline. Traffic whose callers cannot be identified means it can never be approved: add authentication and shadow it again.",
      here: ["AWAITING_APPROVAL", "DENIED"],
    },
    {
      title: "Canary",
      does: `410 Gone to 5%, then 25%, then 100% of requests, for ${c5} / ${c25} / ${c100} days.`,
      stops:
        "A refused request from an identified caller, or anonymous refusals above the shadow's baseline, rolls it back automatically.",
      here: ["CANARY_5", "CANARY_25", "CANARY_100", "ROLLED_BACK"],
    },
    {
      title: "Retired",
      does: "Removed. Every transition, the failures included, is in the hash-chained audit log.",
      stops: "",
      here: ["RETIRED"],
    },
  ];
}

/** The five steps of a removal, and how many candidates are at each. */
export function SafeKillSteps({ state }: { state: SafeKillState }) {
  const statuses = state.candidates.map((c) => c.status);
  return (
    <ol className="steps" aria-label="How a removal is made safe">
      {safeKillSteps(state.policy).map((s, i) => {
        const count = statuses.filter((x) => s.here.includes(x)).length;
        return (
          <li key={s.title} className="step">
            <div className="step-head">
              <span className="step-no">{i + 1}</span>
              <strong>{s.title}</strong>
              {count > 0 && <span className="step-count">{count} here</span>}
            </div>
            <p className="small">{s.does}</p>
            {s.stops && (
              <p className="small muted">
                <strong>Stops here:</strong> {s.stops}
              </p>
            )}
          </li>
        );
      })}
    </ol>
  );
}

/** Why this endpoint can be believed to be a real one, from what the scan recorded. */
export function RealApiEvidence({ e }: { e: ScanEndpoint }) {
  const inCode = e.seen_by.includes("CODE");
  const documented = e.seen_by.includes("OPENAPI");
  const usedBy = e.referenced_by ?? [];
  const items: { ok: boolean; text: string }[] = [];
  if (inCode) {
    items.push({
      ok: true,
      text:
        e.framework && e.framework.startsWith("operationId")
          ? `A handler with the name the specification gives this operation exists at ${e.file}:${e.line}: the framework routes requests to it by that name.`
          : `Declared in code at ${e.file}${e.line ? `:${e.line}` : ""}${
              e.declared_path ? ` as "${e.declared_path}"` : ""
            }, found by matching the ${e.framework ?? "framework"} route declaration in the syntax tree. A route written in a comment or a string is not counted.`,
    });
    if (e.prefix_resolved === false) {
      items.push({
        ok: false,
        text: "The prefix in front of the declared path could not be determined (it is set at run time or mounted where the scan could not follow), so the full path may be longer than shown.",
      });
    }
  } else {
    items.push({
      ok: false,
      text: "No handler was found in code. Either it is served by code the scanner does not read (Django and Go routes are not extracted yet), or the specification documents something that is not implemented.",
    });
  }
  if (documented) {
    items.push({ ok: true, text: "Also documented in the project's API specification: a second, independent witness." });
  }
  if (usedBy.length > 0) {
    items.push({
      ok: true,
      text: `Also called by the project's own client code (${usedBy[0]}${usedBy.length > 1 ? ` and ${usedBy.length - 1} more` : ""}).`,
    });
  }
  if (inCode && !documented && usedBy.length === 0) {
    items.push({
      ok: false,
      text: "Nothing else in the repository mentions it. That makes it a real declaration with no second witness: what a shadow endpoint looks like.",
    });
  }
  return (
    <ul className="evidence-list">
      {items.map((it) => (
        <li key={it.text} className={it.ok ? "ok" : "caution"}>
          <span aria-hidden="true">{it.ok ? "✓" : "!"}</span> {it.text}
        </li>
      ))}
    </ul>
  );
}

/** What a scan's results rest on, and what they cannot show. */
export function TrustCard({ job }: { job: ScanJob }) {
  const r = job.report!;
  const eps = r.endpoints;
  const code = eps.filter((e) => e.seen_by.includes("CODE"));
  const traced = code.filter((e) => e.file && e.line);
  const second = code.filter(
    (e) => e.seen_by.includes("OPENAPI") || (e.referenced_by ?? []).length > 0,
  );
  const specOnly = eps.filter((e) => !e.seen_by.includes("CODE") && e.seen_by.includes("OPENAPI"));
  const unresolved = code.filter((e) => e.prefix_resolved === false);
  const cands = r.candidates ?? [];
  return (
    <div className="trust">
      <h3>Are these real APIs?</h3>
      <ul className="evidence-list">
        <li className="ok">
          <span aria-hidden="true">{"✓"}</span> <strong>{code.length}</strong> endpoint(s) were found in the code,
          each a route declaration matched in the syntax tree, and {traced.length} of them name the file and
          line that declares them. Open any endpoint to check it against the source.
        </li>
        <li className={second.length === code.length ? "ok" : "caution"}>
          <span aria-hidden="true">{second.length === code.length ? "✓" : "!"}</span>{" "}
          <strong>{second.length}</strong> of those are confirmed by a second, independent source: the
          specification documents them, or the project&apos;s own client calls them.{" "}
          {code.length - second.length > 0 &&
            `${code.length - second.length} are seen in code only: real declarations that nothing else in the repository mentions.`}
        </li>
        {specOnly.length > 0 && (
          <li className="caution">
            <span aria-hidden="true">!</span> <strong>{specOnly.length}</strong> documented endpoint(s) have no
            handler found in code: served by code the scanner does not read, or documented and not
            implemented.
          </li>
        )}
        {unresolved.length > 0 && (
          <li className="caution">
            <span aria-hidden="true">!</span> <strong>{unresolved.length}</strong> route(s) sit under a prefix
            that could not be determined, so their full paths may be longer than shown.
          </li>
        )}
      </ul>
      <h3>Are the zombie candidates really zombies?</h3>
      <p className="small">
        {cands.length === 0
          ? "No endpoint is suspected. "
          : `${cands.length} endpoint(s) are suspected. Every reason given is a fact that can be checked in the code, and is shown with its candidate. `}
        None of that proves an endpoint is unused: a caller outside the repository, such as a partner
        or a monthly batch job, cannot be seen in code.{" "}
        {job.traffic ? (
          <>The labels on the <a href={`#results/${job.id}/usage`}>Usage</a> tab come from real requests in the imported access logs.</>
        ) : (
          <>
            Import the gateway&apos;s access logs on the <a href={`#results/${job.id}/usage`}>Usage</a> tab to prove or
            clear each one.
          </>
        )}
      </p>
    </div>
  );
}

/** The stages of a repository scan, in order, as an introduction to its checks. */
export function ScanStages() {
  const stages = [
    "Download the repository with its history, or copy the uploaded folder. Nothing from the project is ever run.",
    "Find route declarations in the code by matching the syntax tree (FastAPI, Flask, Express, Spring), skipping dependencies, builds and tests.",
    "Work out each route's full path: router prefixes and mounts are followed; a prefix that cannot be known is marked, not guessed.",
    "Read the API specification, the commit history, the owners file and the CI/CD workflows.",
    "Find what the project's own clients call, and the calls between its services.",
    "Join it all into one record per endpoint, noting which sources saw it and which did not.",
    "Rank zombie candidates from that evidence, each with its reasons, and draw the dependency graph.",
  ];
  return (
    <ol className="stages small">
      {stages.map((s) => (
        <li key={s}>{s}</li>
      ))}
    </ol>
  );
}
