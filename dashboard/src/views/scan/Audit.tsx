import { Card, ErrorBox, Loading, useLoad, useSession } from "../../common";

const STATE_LABEL: Record<string, string> = {
  STARTED: "scan started",
  FINISHED: "scan finished",
  FAILED: "scan failed",
  keep: "keep",
  document: "needs documentation",
  "assign-owner": "needs an owner",
  investigate: "investigate for removal",
};

const label = (s: string | null) => (s == null ? "" : STATE_LABEL[s] ?? s);

export function ScanAuditTab({ id }: { id: string }) {
  const { api } = useSession();
  const { data, error, loading, reload } = useLoad(() => api.scanAudit(id), [id]);

  if (error) return <ErrorBox message={error} />;
  if (loading && !data) return <Loading what="audit log" />;
  if (!data) return null;

  const { chain } = data;
  return (
    <div className="stack">
      <Card title="This scan's audit chain">
        <p>
          {chain.entries} entries: who started the scan, a fingerprint of the report it
          produced, and every decision since. Each entry carries the SHA-256 of its content
          and of the entry before it, so editing, deleting or reordering any of them breaks
          every hash after it.
        </p>
        <p className="mono small">head {data.head}</p>
        <div className="buttons">
          <button onClick={reload} disabled={loading}>
            {loading ? "Recomputing..." : "Verify the whole chain"}
          </button>
          <span className={chain.ok ? "good-text" : "bad-text"} role="status">
            {chain.ok
              ? `Verified: ${chain.entries} entries, no break.`
              : `BROKEN at entry ${chain.broken_at}: ${chain.problem}`}
          </span>
        </div>
      </Card>
      <Card title="Entries">
        <div className="table-wrap">
          <table>
            <thead>
              <tr>
                <th>#</th>
                <th>When</th>
                <th>Subject</th>
                <th>Transition</th>
                <th>By</th>
                <th>Detail</th>
                <th>Hash</th>
              </tr>
            </thead>
            <tbody>
              {[...data.entries].reverse().map((e) => {
                const note = typeof e.evidence.note === "string" ? e.evidence.note : "";
                const digest =
                  typeof e.evidence.report_sha256 === "string" ? e.evidence.report_sha256 : "";
                return (
                  <tr key={e.seq}>
                    <td>{e.seq}</td>
                    <td className="small">{new Date(e.at).toLocaleString()}</td>
                    <td>{e.endpoint_id === "(scan)" ? <em>the scan</em> : <code>{e.endpoint_id}</code>}</td>
                    <td>
                      {e.from_state ? `${label(e.from_state)} → ` : ""}
                      <strong>{label(e.to_state)}</strong>
                    </td>
                    <td>{e.actor}</td>
                    <td className="small">
                      {e.reason}
                      {note && <div className="muted">"{note}"</div>}
                      {digest && <div className="mono muted">report sha256 {digest.slice(0, 16)}...</div>}
                    </td>
                    <td className="mono small">{e.hash.slice(0, 10)}</td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
      </Card>
    </div>
  );
}
