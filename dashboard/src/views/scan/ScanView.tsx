import { useCallback, useEffect, useState } from "react";
import { ApiError } from "../../api";
import { Card, ErrorBox, Loading, canApprove, useSession } from "../../common";
import type { Review, ScanJob } from "../../types";
import { Audit as DemoAudit } from "../Audit";
import { Benchmark as DemoBenchmark } from "../Benchmark";
import { Endpoints as DemoEndpoints } from "../Endpoints";
import { Overview as DemoOverview } from "../Overview";
import { SafeKill as DemoSafeKill } from "../SafeKill";
import { KIND_LABEL, ScanStatusBadge } from "../ScanResults";
import { ScanAuditTab } from "./Audit";
import { ScanBenchmarkTab } from "./Benchmark";
import { ScanEndpointsTab } from "./Endpoints";
import { ScanOverviewTab } from "./Overview";
import { ScanSafeKillTab } from "./SafeKill";
import { when } from "./shared";

export const TABS = [
  ["overview", "Overview"],
  ["endpoints", "Endpoints"],
  ["safekill", "Safe Kill"],
  ["audit", "Audit log"],
  ["benchmark", "Benchmark"],
] as const;
export type Tab = (typeof TABS)[number][0];

export const DEMO_ID = "demo";
const POLL_MS = 1000;

export function parseScanParam(param: string): { id: string; tab: Tab } {
  const [id = "", tab = "overview"] = param.split("/");
  const known = TABS.some(([k]) => k === tab);
  return { id, tab: (known ? tab : "overview") as Tab };
}

function Tabs({ id, tab, label }: { id: string; tab: Tab; label: string }) {
  return (
    <nav className="tabs" aria-label={label}>
      {TABS.map(([key, title]) => (
        <a key={key} href={`#results/${id}/${key}`} aria-current={key === tab ? "page" : undefined}>
          {title}
        </a>
      ))}
    </nav>
  );
}

/** One scan, or the demo bank, with the same five views. */
export function ScanView({ param }: { param: string }) {
  const { id, tab } = parseScanParam(param);
  return id === DEMO_ID ? <DemoView tab={tab} /> : <RealScanView id={id} tab={tab} />;
}

// ---------------------------------------------------------------------------
function DemoView({ tab }: { tab: Tab }) {
  const body = {
    overview: <DemoOverview />,
    endpoints: <DemoEndpoints />,
    safekill: <DemoSafeKill />,
    audit: <DemoAudit />,
    benchmark: <DemoBenchmark />,
  }[tab];
  return (
    <div className="stack">
      <p>
        <a href="#results">All scans</a>
      </p>
      <div className="scan-head">
        <h2>Demo bank</h2>
        <span className="scan-status scan-demo">simulated</span>
      </div>
      <div className="simulated" role="note">
        A simulated bank of 25 endpoints behind a simulated gateway, with traffic, DNS and
        a known answer key. It shows what the full engine does when all six sources exist:
        lifecycle classification, the removal gate, and Safe Kill. Nothing real is touched.
      </div>
      <Tabs id={DEMO_ID} tab={tab} label="Demo bank views" />
      {body}
    </div>
  );
}

// ---------------------------------------------------------------------------
function RealScanView({ id, tab }: { id: string; tab: Tab }) {
  const { api, signOut } = useSession();
  const [job, setJob] = useState<ScanJob | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let live = true;
    let timer: number | undefined;
    const tick = () => {
      api
        .scan(id)
        .then((j) => {
          if (!live) return;
          setJob(j);
          setError(null);
          if (j.status === "queued" || j.status === "running") {
            timer = window.setTimeout(tick, POLL_MS);
          }
        })
        .catch((e: unknown) => {
          if (!live) return;
          if (e instanceof ApiError && e.unauthorised) return signOut();
          setError(e instanceof Error ? e.message : String(e));
        });
    };
    tick();
    return () => {
      live = false;
      window.clearTimeout(timer);
    };
  }, [api, id, signOut]);

  const onReviewed = useCallback(
    (reviews: Record<string, Review>) => setJob((j) => (j ? { ...j, reviews } : j)),
    [],
  );

  if (error) return <ErrorBox message={error} />;
  if (!job) return <Loading what="scan" />;
  const running = job.status === "queued" || job.status === "running";

  return (
    <div className="stack">
      <p>
        <a href="#results">All scans</a>
      </p>
      <div className="scan-head">
        <h2>
          <code>{job.target}</code>
        </h2>
        <ScanStatusBadge status={job.status} />
        <span className="muted small">
          {KIND_LABEL[job.kind]} scan by {job.requested_by}, {when(job.created_at)}
          {job.duration_s != null ? `, took ${job.duration_s}s` : ""}
          {job.report?.details.commit ? `, commit ${job.report.details.commit}` : ""}
        </span>
      </div>

      {running && (
        <Card title="Scanning">
          <ol className="progress-steps" aria-live="polite">
            {job.progress.map((p, i) => (
              <li key={`${p.at}-${i}`} className={i === job.progress.length - 1 ? "current" : "done"}>
                {p.message}
              </li>
            ))}
          </ol>
        </Card>
      )}
      {job.status === "failed" && (
        <div className="error" role="alert">
          <strong>The scan could not finish.</strong> {job.error}
        </div>
      )}

      {job.status === "done" && job.report && (
        <>
          <Tabs id={id} tab={tab} label="Scan views" />
          {tab === "overview" && <ScanOverviewTab job={job} />}
          {tab === "endpoints" && <ScanEndpointsTab job={job} onReviewed={onReviewed} />}
          {tab === "safekill" && <ScanSafeKillTab job={job} onReviewed={onReviewed} />}
          {tab === "audit" && <ScanAuditTab id={id} />}
          {tab === "benchmark" && <ScanBenchmarkTab job={job} />}
        </>
      )}
    </div>
  );
}

/** "Open the demo": re-runs it for an approver, then shows it like any scan. */
export function DemoButton() {
  const { api, principal } = useSession();
  const [busy, setBusy] = useState(false);

  async function open() {
    setBusy(true);
    try {
      if (canApprove(principal)) await api.rescan();
    } catch {
      // The demo was scanned at start-up; showing that is fine.
    } finally {
      setBusy(false);
      window.location.hash = `#results/${DEMO_ID}/overview`;
    }
  }

  return (
    <button onClick={open} disabled={busy}>
      {busy ? "Running the demo..." : "Run the demo"}
    </button>
  );
}
