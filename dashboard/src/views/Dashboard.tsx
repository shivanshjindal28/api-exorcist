import {
  Card,
  Empty,
  ErrorBox,
  LevelBadge,
  Loading,
  Page,
  PageHead,
  Priority,
  useLoad,
  useSession,
} from "../common";
import type { Portfolio } from "../types";
import { when } from "./scan/shared";

/** Every project's latest scan, and what across all of them needs attention first. */
export function Dashboard() {
  const { api } = useSession();
  const { data, error, loading } = useLoad<Portfolio>(() => api.portfolio());

  const head = (
    <PageHead title="Overview" sub="The latest scan of every project, and the endpoints to look at first." />
  );

  if (error) return <Page head={head}><ErrorBox message={error} /></Page>;
  if (loading && !data) return <Page head={head}><Loading what="the estate" /></Page>;
  if (!data) return null;

  const t = data.totals;
  if (t.projects === 0) {
    return (
      <Page head={head}>
        <section className="card">
          <Empty
            title="No projects scanned yet"
            action={
              <div className="buttons">
                <a className="btn" href="#scan">
                  Scan a project
                </a>
                <a className="btn secondary" href="#results/demo/overview">
                  Explore the demo bank
                </a>
              </div>
            }
          >
            Scan a repository or upload a project folder. API Exorcist finds every endpoint in
            the code, checks it against the specification and history, and ranks the ones that
            look abandoned. Add access logs and it proves which are.
          </Empty>
        </section>
      </Page>
    );
  }

  const tiles: { label: string; value: number; note?: string; tone?: string }[] = [
    { label: "Projects", value: t.projects },
    { label: "Endpoints", value: t.endpoints },
    {
      label: "Undocumented (shadow)",
      value: t.undocumented,
      note: t.endpoints ? `${Math.round((t.undocumented / t.endpoints) * 100)}% of the estate` : undefined,
    },
    { label: "Zombie candidates", value: t.candidates, note: `${t.likely} likely`, tone: "tile-bad" },
    {
      label: "Proven zombies",
      value: t.zombies,
      note: "no traffic in the imported logs",
      tone: t.zombies ? "tile-bad" : undefined,
    },
    { label: "Sensitive endpoints", value: t.high_sensitivity, note: "auth, payments, cards, KYC, admin" },
  ];

  return (
    <Page head={head}>
      <div className="stack">
        <div className="tiles">
          {tiles.map((x) => (
            <div className={`tile ${x.tone ?? ""}`} key={x.label}>
              <div className="tile-label">{x.label}</div>
              <div className="tile-value">{x.value.toLocaleString()}</div>
              {x.note && <div className="tile-note">{x.note}</div>}
            </div>
          ))}
        </div>

        <Card title="Needs attention" flush>
          {data.top_risks.length === 0 ? (
            <p className="muted" style={{ padding: "0 1.25rem 1rem" }}>
              No zombie candidates across the estate.
            </p>
          ) : (
            <div className="table-wrap">
              <table>
                <thead>
                  <tr>
                    <th>Priority</th>
                    <th>Endpoint</th>
                    <th>Project</th>
                    <th>Handles</th>
                    <th>Why</th>
                  </tr>
                </thead>
                <tbody>
                  {data.top_risks.map((r) => (
                    <tr key={`${r.scan}-${r.id}`}>
                      <td>
                        <Priority value={r.priority} />
                      </td>
                      <td>
                        <a href={`#results/${r.scan}/endpoints`}>
                          <code>{r.id}</code>
                        </a>
                        {!r.documented && <span className="tag">undocumented</span>}
                      </td>
                      <td className="small">{r.target.replace(/^github\.com\//, "")}</td>
                      <td>
                        <LevelBadge level={r.level} category={r.sensitivity} />
                      </td>
                      <td className="small">{r.label}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </Card>

        <Card title="Projects" flush actions={<a href="#results" className="small">All scans</a>}>
          <div className="table-wrap">
            <table>
              <thead>
                <tr>
                  <th>Project</th>
                  <th className="r">Endpoints</th>
                  <th className="r">Undocumented</th>
                  <th className="r">Candidates</th>
                  <th className="r">Proven zombies</th>
                  <th className="r">Reviewed</th>
                  <th>Usage data</th>
                  <th>Last scanned</th>
                </tr>
              </thead>
              <tbody>
                {data.projects.map((p) => (
                  <tr key={p.id}>
                    <td>
                      <a href={`#results/${p.id}/overview`}>
                        <code>{p.target}</code>
                      </a>
                    </td>
                    <td className="r num">{p.endpoints}</td>
                    <td className="r num">{p.undocumented}</td>
                    <td className="r num">
                      {p.candidates}
                      {p.likely > 0 && <span className="bad-text small"> ({p.likely} likely)</span>}
                    </td>
                    <td className="r num">{p.traffic ? p.zombies : <span className="muted">-</span>}</td>
                    <td className="r num">
                      {p.reviewed}/{p.endpoints}
                    </td>
                    <td>
                      {p.traffic ? (
                        <span className="state state-good">logs imported</span>
                      ) : (
                        <a className="small" href={`#results/${p.id}/usage`}>
                          Import logs
                        </a>
                      )}
                    </td>
                    <td className="small muted">{when(p.scanned_at)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </Card>
      </div>
    </Page>
  );
}
