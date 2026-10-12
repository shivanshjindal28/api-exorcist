import { Card, ErrorBox, Loading, useLoad, useSession } from "../common";

const ORDER = ["gateway-only", "spec-only", "conventional", "api-exorcist"];

export function Benchmark() {
  const { api } = useSession();
  const { data, error, loading } = useLoad(() => api.benchmark());

  if (error) return <ErrorBox message={error} />;
  if (loading && !data) return <Loading what="benchmark (runs four configurations)" />;
  if (!data) return null;

  const rows = ORDER.filter((k) => data[k]).map((k) => ({ key: k, ...data[k]! }));
  return (
    <Card title="Before and after: identical pipeline, only the sources differ">
      <div className="table-wrap">
        <table>
          <thead>
            <tr>
              <th>Configuration</th>
              <th>Coverage</th>
              <th>Rules usable</th>
              <th>Zombies caught</th>
              <th>Recall</th>
            </tr>
          </thead>
          <tbody>
            {rows.map((r) => (
              <tr key={r.key} className={r.key === "api-exorcist" ? "highlight" : undefined}>
                <td>{r.title}</td>
                <td>{r.coverage_pct.toFixed(1)}%</td>
                <td>
                  {r.rules_evaluable} / {r.rules_total}
                </td>
                <td>
                  {r.zombies_caught} / {r.zombies_in_estate}
                </td>
                <td>
                  <span className="recall">
                    <span className="bar-track">
                      <span className="bar pos" style={{ width: `${r.zombie_recall_pct}%` }} />
                    </span>
                    {r.zombie_recall_pct.toFixed(0)}%
                  </span>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      <p className="muted">
        A conventional inventory, a gateway registry plus a specification, is what most banks
        actually have. A source that was never consulted is not evidence of absence: rules
        that depend on it abstain, which is why the gateway alone classifies nothing at all.
      </p>
    </Card>
  );
}
