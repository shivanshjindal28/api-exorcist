import { Card } from "../../common";
import type { ScanJob } from "../../types";
import { ALL_SOURCES, consultedSources, sourceName } from "./shared";

/**
 * The real-project version of the demo's benchmark: what a conventional,
 * documentation-based inventory would know, against what this scan found.
 * There is no answer key for a real project, so this measures coverage, not
 * accuracy, and says so.
 */
export function ScanBenchmarkTab({ job }: { job: ScanJob }) {
  const eps = job.report!.endpoints;
  const total = eps.length;
  const inSpec = eps.filter((e) => e.seen_by.includes("OPENAPI")).length;
  const inCode = eps.filter((e) => e.seen_by.includes("CODE")).length;
  const codeOnly = eps.filter((e) => e.seen_by.includes("CODE") && !e.seen_by.includes("OPENAPI")).length;
  const specOnly = eps.filter((e) => e.seen_by.includes("OPENAPI") && !e.seen_by.includes("CODE")).length;
  const consulted = consultedSources(job);
  const pct = (n: number) => (total ? Math.round((n / total) * 100) : 0);

  return (
    <div className="stack">
      <Card title="A conventional inventory, against this scan">
        <p className="lead">
          {inSpec === 0 ? (
            <>
              This project publishes no API specification, so an inventory built from
              documentation would list <strong>none</strong> of the <strong>{total}</strong>{" "}
              endpoints this scan found.
            </>
          ) : (
            <>
              An inventory built from the API specification would list{" "}
              <strong>
                {inSpec} of {total}
              </strong>{" "}
              endpoints. The other <strong>{codeOnly}</strong> exist only in code: shadow
              APIs nobody documented.
            </>
          )}
        </p>
        <div className="compare">
          <Bar label="Documentation only (conventional)" n={inSpec} total={total} tone="neutral" />
          <Bar label="Code, specification and CI/CD, correlated (this scan)" n={total} total={total} tone="good" />
        </div>
        <div className="tiles">
          <Tile value={total} label="endpoints found" />
          <Tile value={`${inSpec} (${pct(inSpec)}%)`} label="documented in the specification" />
          <Tile value={codeOnly} label="only in code: undocumented" />
          <Tile value={specOnly} label="only in the specification: no handler found" />
        </div>
      </Card>

      <Card title="What each source saw">
        <div className="table-wrap">
          <table>
            <thead>
              <tr>
                <th>Source</th>
                <th>Consulted</th>
                <th>Endpoints it saw</th>
              </tr>
            </thead>
            <tbody>
              {ALL_SOURCES.map((s) => {
                const asked = consulted.includes(s);
                const n = eps.filter((e) => e.seen_by.includes(s)).length;
                return (
                  <tr key={s}>
                    <td>{sourceName(s)}</td>
                    <td>{asked ? "yes" : <span className="muted">no: not in a project's files</span>}</td>
                    <td>{asked ? `${n} of ${total}` : <span className="muted">n/a</span>}</td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
        <p className="muted small">
          Code saw {inCode} endpoint(s). No single source sees everything, which is why the
          engine correlates them; the demo bank shows the same effect with all six sources.
        </p>
      </Card>

      <Card title="Why there is no accuracy figure here">
        <p className="muted">
          The demo bank's benchmark scores the engine against an answer key: the true state of
          every endpoint is known, because the estate was built that way. A real project has
          no answer key, so this page measures coverage, not accuracy. See the{" "}
          <a href="#results/demo/benchmark">demo benchmark</a> for the accuracy study.
        </p>
      </Card>
    </div>
  );
}

function Bar({ label, n, total, tone }: { label: string; n: number; total: number; tone: string }) {
  const width = total ? (n / total) * 100 : 0;
  return (
    <div className="compare-row">
      <span className="compare-label">{label}</span>
      <span className="bar-track" aria-hidden="true">
        <span className={`bar ${tone === "good" ? "pos" : "neutral"}`} style={{ width: `${width}%` }} />
      </span>
      <span className="compare-value">
        {n} of {total}
      </span>
    </div>
  );
}

function Tile({ value, label }: { value: number | string; label: string }) {
  return (
    <div className="tile">
      <div className="tile-value">{value}</div>
      <div className="tile-label">{label}</div>
    </div>
  );
}
