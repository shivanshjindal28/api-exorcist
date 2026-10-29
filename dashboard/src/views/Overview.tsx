import { useState } from "react";
import { CountUp } from "../charts";
import { Card, ErrorBox, LabelBadge, Loading, canApprove, useLoad, useSession } from "../common";

const ORDER = ["ACTIVE", "DEPRECATED", "ORPHANED", "ZOMBIE", "INDETERMINATE"];

export function Overview() {
  const { api, principal } = useSession();
  const { data, error, loading, reload } = useLoad(() => api.summary());
  const [scanning, setScanning] = useState(false);

  if (error) return <ErrorBox message={error} />;
  if (loading && !data) return <Loading what="summary" />;
  if (!data) return null;

  const total = data.endpoints || 1;
  const labels = ORDER.filter((l) => data.labels[l]);

  async function rescan() {
    setScanning(true);
    try {
      await api.rescan();
      reload();
    } finally {
      setScanning(false);
    }
  }

  return (
    <div className="stack">
      <div className="tiles">
        <Tile value={data.endpoints} label="endpoints discovered" />
        <Tile value={data.labels.ZOMBIE ?? 0} label="zombies" tone="bad" />
        <Tile value={data.cleared_by_gate} label="cleared by the removal gate" />
        <Tile value={data.awaiting_approval} label="awaiting a named approver" tone="pending" />
        <Tile value={data.decided} label="Safe Kill decisions" />
      </div>

      <Card title="Classification">
        <div className="distribution" role="img" aria-label="Share of endpoints by label">
          {labels.map((l) => (
            <span
              key={l}
              className={`segment segment-${l.toLowerCase()}`}
              style={{ width: `${((data.labels[l] ?? 0) / total) * 100}%` }}
              title={`${l}: ${data.labels[l]}`}
            />
          ))}
        </div>
        <ul className="legend">
          {labels.map((l) => (
            <li key={l}>
              <LabelBadge label={l} /> {data.labels[l]}
            </li>
          ))}
        </ul>
      </Card>

      <Card title="This scan">
        <dl className="facts">
          <dt>Scanned</dt>
          <dd>{new Date(data.scanned_at).toLocaleString()}</dd>
          <dt>Removal candidates</dt>
          <dd>
            {data.removal_candidates} classified ZOMBIE, {data.cleared_by_gate} cleared by the
            classifier and the dependency graph together
          </dd>
          <dt>Learned-model veto</dt>
          <dd>{data.model_veto ? "on" : "off"}</dd>
        </dl>
        {canApprove(principal) && (
          <button onClick={rescan} disabled={scanning}>
            {scanning ? "Scanning..." : "Re-run discovery"}
          </button>
        )}
      </Card>
    </div>
  );
}

function Tile({ value, label, tone }: { value: number; label: string; tone?: string }) {
  return (
    <div className={`tile${tone ? ` tile-${tone}` : ""}`}>
      <span className="tile-value"><CountUp value={value} /></span>
      <span className="tile-label">{label}</span>
    </div>
  );
}
