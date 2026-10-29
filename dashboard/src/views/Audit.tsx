import { useState } from "react";
import { Card, ErrorBox, Loading, useLoad, useSession, useToast } from "../common";
import type { ChainCheck } from "../types";

export function Audit() {
  const { api } = useSession();
  const [endpoint, setEndpoint] = useState("");
  const [applied, setApplied] = useState("");
  const { data, error, loading } = useLoad(() => api.audit(applied || undefined), [applied]);
  const [check, setCheck] = useState<ChainCheck | null>(null);
  const [checking, setChecking] = useState(false);
  const notify = useToast();

  async function verify() {
    setChecking(true);
    try {
      const result = await api.verifyAudit();
      setCheck(result);
      notify(result.ok ? "Audit chain verified" : "Audit chain is broken", {
        tone: result.ok ? "ok" : "error",
        detail: result.ok ? "Every hash recomputed and matched." : undefined,
      });
    } finally {
      setChecking(false);
    }
  }

  if (error) return <ErrorBox message={error} />;
  if (loading && !data) return <Loading what="audit log" />;
  if (!data) return null;

  return (
    <div className="stack">
      <Card title="Audit chain">
        <p>
          {data.total} entries. Each carries the SHA-256 of its own content and of the entry
          before it, so editing, deleting or reordering any entry breaks every hash after it.
        </p>
        <p className="mono small">head {data.head}</p>
        <div className="buttons">
          <button onClick={verify} disabled={checking}>
            {checking ? "Recomputing..." : "Verify the whole chain"}
          </button>
          {check && (
            <span className={check.ok ? "good-text" : "bad-text"} role="status">
              {check.ok
                ? `Verified: ${check.entries} entries, no break.`
                : `BROKEN at entry ${check.broken_at}: ${check.problem}`}
            </span>
          )}
        </div>
      </Card>

      <Card title="Entries">
        <form
          className="filters"
          onSubmit={(e) => {
            e.preventDefault();
            setApplied(endpoint.trim());
          }}
        >
          <input
            type="search"
            placeholder="Filter by endpoint id"
            aria-label="Filter by endpoint id"
            value={endpoint}
            onChange={(e) => setEndpoint(e.target.value)}
          />
          <button type="submit" className="small">
            Filter
          </button>
        </form>
        <div className="table-wrap">
          <table>
            <thead>
              <tr>
                <th>#</th>
                <th>When (simulated)</th>
                <th>Endpoint</th>
                <th>Transition</th>
                <th>Actor</th>
                <th>Reason</th>
                <th>Hash</th>
              </tr>
            </thead>
            <tbody>
              {[...data.entries].reverse().map((e) => (
                <tr key={e.seq}>
                  <td>{e.seq}</td>
                  <td className="small">{e.at.replace("T", " ")}</td>
                  <td>
                    <code>{e.endpoint_id}</code>
                  </td>
                  <td className="small">
                    {e.from_state ? `${e.from_state.toLowerCase()} -> ` : ""}
                    <strong>{e.to_state.toLowerCase()}</strong>
                  </td>
                  <td>{e.actor}</td>
                  <td className="small">{e.reason}</td>
                  <td className="mono small" title={e.hash}>
                    {e.hash.slice(0, 10)}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </Card>
    </div>
  );
}
