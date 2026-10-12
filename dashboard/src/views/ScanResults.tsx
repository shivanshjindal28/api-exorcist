import { Card, ErrorBox, Loading, useLoad, useSession } from "../common";
import type { ScanJob } from "../types";

export function when(iso: string | null): string {
  if (!iso) return "";
  const d = new Date(iso);
  return Number.isNaN(d.getTime()) ? iso : d.toLocaleString();
}

export function ScanStatusBadge({ status }: { status: ScanJob["status"] }) {
  const text = { queued: "queued", running: "scanning", done: "finished", failed: "failed" }[
    status
  ];
  return <span className={`scan-status scan-${status}`}>{text}</span>;
}

export const KIND_LABEL: Record<ScanJob["kind"], string> = {
  github: "GitHub",
  folder: "Folder",
};

export function ScanResults() {
  const { api } = useSession();
  const { data, error, loading } = useLoad(() => api.scans());

  if (error) return <ErrorBox message={error} />;
  if (loading && !data) return <Loading what="scans" />;
  if (!data) return null;

  return (
    <Card title={`Scans (${data.length})`}>
      {data.length === 0 && (
        <p>
          No scans yet. Start one from <a href="#scan">New scan</a>: upload a project folder
          or paste a GitHub link.
        </p>
      )}
      <div className="table-wrap">
        <table>
          <thead>
            <tr>
              <th>What</th>
              <th>Source</th>
              <th>Status</th>
              <th>Endpoints</th>
              <th>Undocumented</th>
              <th>Started</th>
              <th>Took</th>
            </tr>
          </thead>
          <tbody>
            <tr className="demo-row">
              <td>
                <a href="#results/demo/overview">Demo bank</a>
              </td>
              <td>Simulated</td>
              <td>
                <span className="scan-status scan-demo">always available</span>
              </td>
              <td>25</td>
              <td colSpan={3} className="small muted">
                All six sources, with traffic: the full engine, on a known answer key
              </td>
            </tr>
            {data.map((s) => {
              const n = (label: string) => s.summary?.find((x) => x.label === label)?.value ?? "";
              return (
                <tr key={s.id}>
                  <td>
                    <a href={`#results/${s.id}/overview`}>
                      <code>{s.target}</code>
                    </a>
                  </td>
                  <td>{KIND_LABEL[s.kind]}</td>
                  <td>
                    <ScanStatusBadge status={s.status} />
                  </td>
                  <td>{n("Endpoints found")}</td>
                  <td>{n("Undocumented")}</td>
                  <td className="small">{when(s.created_at)}</td>
                  <td className="small">{s.duration_s != null ? `${s.duration_s}s` : ""}</td>
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>
    </Card>
  );
}
