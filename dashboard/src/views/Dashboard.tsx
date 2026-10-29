import type { ReactNode } from "react";
import { BarList, CountUp, Delta, Donut } from "../charts";
import {
  Card,
  Empty,
  ErrorBox,
  LevelBadge,
  Loading,
  Page,
  PageHead,
  Priority,
  Sparkline,
  useLoad,
  useSession,
} from "../common";
import { IconActivity, IconAlert, IconEndpoint, IconGhost, IconLock, IconProjects, IconScan } from "../icons";
import { useTilt } from "../motion";
import type { Portfolio } from "../types";
import { GetStarted } from "./GetStarted";
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
            icon={<IconScan size={26} />}
            title="No projects scanned yet"
            action={<GetStarted />}
          >
            API Exorcist finds every endpoint in the code, checks it against the specification
            and history, and ranks the ones that look abandoned. Three steps to the first answer:
          </Empty>
        </section>
      </Page>
    );
  }

  const prev = data.previous ?? null;
  const tiles: { label: string; value: number; note?: string; tone?: string; icon: ReactNode; delta?: ReactNode }[] = [
    { label: "Projects", value: t.projects, icon: <IconProjects />, note: "latest scan of each" },
    {
      label: "Endpoints",
      value: t.endpoints,
      icon: <IconEndpoint />,
      delta: prev ? <Delta now={t.endpoints} before={prev.endpoints} worseWhenUp={false} /> : undefined,
    },
    {
      label: "Undocumented (shadow)",
      value: t.undocumented,
      icon: <IconGhost />,
      note: t.endpoints ? `${Math.round((t.undocumented / t.endpoints) * 100)}% of the estate` : undefined,
      delta: prev ? <Delta now={t.undocumented} before={prev.undocumented} /> : undefined,
    },
    {
      label: "Zombie candidates",
      value: t.candidates,
      note: `${t.likely} likely`,
      tone: "tile-bad",
      icon: <IconAlert />,
      delta: prev ? <Delta now={t.candidates} before={prev.candidates} /> : undefined,
    },
    {
      label: "Proven zombies",
      value: t.zombies,
      note: "no traffic in the imported logs",
      tone: t.zombies ? "tile-bad" : undefined,
      icon: <IconActivity />,
    },
    { label: "Sensitive endpoints", value: t.high_sensitivity, note: "auth, payments, cards, KYC, admin", icon: <IconLock /> },
  ];
  const comp = data.composition;
  const cats = data.by_category ?? [];

  return (
    <Page head={head}>
      <div className="stack">
        <div className="tiles">
          {tiles.map((x) => (
            <TiltTile className={`tile ${x.tone ?? ""}`} key={x.label}>
              <div className="tile-top">
                <span className="tile-icon">{x.icon}</span>
              </div>
              <div className="tile-label">{x.label}</div>
              <div className="tile-value"><CountUp value={x.value} /></div>
              {x.note && <div className="tile-note">{x.note}</div>}
              {x.delta && <div className="tile-delta">{x.delta}</div>}
            </TiltTile>
          ))}
        </div>

        {comp && (
          <div className="charts">
            <Card title="The estate at a glance">
              <Donut
                caption="Endpoints by the worst thing known about each"
                centre={
                  <>
                    <strong>{t.endpoints}</strong>
                    <span>endpoints</span>
                  </>
                }
                slices={[
                  { key: "zombie", label: "Proven zombie", value: comp.zombie, tone: "crit" },
                  { key: "likely", label: "Likely zombie", value: comp.likely, tone: "high" },
                  { key: "candidate", label: "Other candidate", value: comp.candidate, tone: "med" },
                  { key: "undocumented", label: "Undocumented only", value: comp.undocumented, tone: "low" },
                  { key: "clean", label: "Documented, no finding", value: comp.clean, tone: "ok" },
                ]}
              />
            </Card>
            <Card title="Exposure by what endpoints handle">
              <BarList
                partLabel="zombie candidates"
                wholeLabel="all endpoints"
                bars={cats.slice(0, 7).map((c) => ({
                  key: c.category,
                  label: <LevelBadge level={c.level} category={c.category} />,
                  value: c.endpoints,
                  part: c.flagged,
                }))}
              />
            </Card>
          </div>
        )}

        <Card title="Needs attention" flush>
          {data.top_risks.length === 0 ? (
            <Empty icon={<IconAlert size={26} />} title="Nothing needs attention">
              No zombie candidates across the estate.
            </Empty>
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
                  <th>Candidates over time</th>
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
                      {(p.history?.length ?? 0) > 1 ? (
                        <Sparkline points={p.history!.map((h) => h.candidates)} width={96} height={24} />
                      ) : (
                        <span className="muted small">one scan</span>
                      )}
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

/** A metric card that tilts toward the pointer, with a soft glare where it points. */
function TiltTile({ className, children }: { className: string; children: ReactNode }) {
  const tilt = useTilt<HTMLDivElement>(6);
  return (
    <div className={`${className} tilt`} ref={tilt.ref} onMouseMove={tilt.onMouseMove} onMouseLeave={tilt.onMouseLeave}>
      {children}
    </div>
  );
}
