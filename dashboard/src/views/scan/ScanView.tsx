import { useCallback, useEffect, useState } from "react";
import { ApiError } from "../../api";
import { Card, ErrorBox, Loading, Menu, Page, PageHead, canApprove, useSession } from "../../common";
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
import { DemoGraphTab, GraphPanel } from "./Graph";
import { ScanOverviewTab } from "./Overview";
import { ScanSafeKillTab } from "./SafeKill";
import { ScanUsageTab } from "./Usage";
import { when } from "./shared";

export const TABS = [
  ["overview", "Overview"],
  ["endpoints", "Endpoints"],
  ["usage", "Usage"],
  ["graph", "Dependency graph"],
  ["safekill", "Safe Kill"],
  ["audit", "Audit log"],
  ["benchmark", "Benchmark"],
] as const;
export type Tab = (typeof TABS)[number][0];
/** The demo bank has traffic built in, so it has no Usage view to import into. */
const DEMO_TABS = TABS.filter(([k]) => k !== "usage");

export const DEMO_ID = "demo";
const POLL_MS = 1000;

export function parseScanParam(param: string): { id: string; tab: Tab } {
  const [id = "", tab = "overview"] = param.split("/");
  const known = TABS.some(([k]) => k === tab);
  return { id, tab: (known ? tab : "overview") as Tab };
}

function Tabs({
  id,
  tab,
  label,
  tabs = TABS,
  counts = {},
}: {
  id: string;
  tab: Tab;
  label: string;
  tabs?: readonly (readonly [Tab, string])[];
  counts?: Partial<Record<Tab, number>>;
}) {
  return (
    <nav className="tabs" aria-label={label}>
      {tabs.map(([key, title]) => (
        <a key={key} href={`#results/${id}/${key}`} aria-current={key === tab ? "page" : undefined}>
          {title}
          {counts[key] != null && <span className="tab-count">{counts[key]}</span>}
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
function DemoView({ tab: asked }: { tab: Tab }) {
  const tab = asked === "usage" ? "overview" : asked;
  const body = {
    overview: <DemoOverview />,
    endpoints: <DemoEndpoints />,
    graph: <DemoGraphTab />,
    safekill: <DemoSafeKill />,
    audit: <DemoAudit />,
    benchmark: <DemoBenchmark />,
    usage: null,
  }[tab];
  return (
    <Page
      head={
        <PageHead
          title="Demo bank"
          badge={<span className="scan-status scan-demo">simulated</span>}
          sub="25 endpoints behind a simulated gateway, with traffic, DNS and a known answer key: the full engine when all six evidence sources exist."
          tabs={<Tabs id={DEMO_ID} tab={tab} label="Demo bank views" tabs={DEMO_TABS} />}
        />
      }
    >
      <div className="stack">
        <div className="simulated" role="note">
          Simulated data. It shows lifecycle classification, the removal gate and Safe Kill
          working end to end. Nothing real is touched, and no figure here describes a real bank.
        </div>
        {body}
      </div>
    </Page>
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

  const crumbs = [{ label: "Projects", href: "#results" }, { label: job?.target ?? id }];
  if (error) {
    return (
      <Page head={<PageHead title="Scan" crumbs={crumbs} />}>
        <ErrorBox message={error} />
      </Page>
    );
  }
  if (!job) {
    return (
      <Page head={<PageHead title="Scan" crumbs={crumbs} />}>
        <Loading what="scan" />
      </Page>
    );
  }
  const running = job.status === "queued" || job.status === "running";
  const usage = job.traffic?.lifecycle;

  return (
    <Page
      head={
        <PageHead
          title={job.target.replace(/^github\.com\//, "")}
          crumbs={crumbs}
          badge={<ScanStatusBadge status={job.status} />}
          actions={job.status === "done" ? <ScanActions job={job} /> : undefined}
          tabs={
            job.status === "done" && job.report ? (
              <Tabs
                id={id}
                tab={tab}
                label="Scan views"
                counts={{
                  endpoints: job.report.endpoints.length,
                  usage: usage ? usage.ZOMBIE ?? 0 : undefined,
                }}
              />
            ) : undefined
          }
          sub={
            <div className="meta">
              <span>{KIND_LABEL[job.kind]} scan</span>
              <span>by {job.requested_by}</span>
              <span>{when(job.created_at)}</span>
              {job.duration_s != null && <span>took {job.duration_s}s</span>}
              {job.report?.details.commit && (
                <span>
                  commit <code>{job.report.details.commit}</code>
                </span>
              )}
              {job.traffic && (
                <span>
                  usage: {job.traffic.requests.toLocaleString()} requests over{" "}
                  {job.traffic.window.days ?? "?"} days
                </span>
              )}
            </div>
          }
        />
      }
    >
    <div className="stack">

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
          {tab === "overview" && <ScanOverviewTab job={job} />}
          {tab === "endpoints" && <ScanEndpointsTab job={job} onReviewed={onReviewed} />}
          {tab === "usage" && <ScanUsageTab job={job} onImported={setJob} />}
          {tab === "graph" &&
            (job.report.graph ? (
              <GraphPanel
                view={job.report.graph}
                candidates={Object.fromEntries(
                  (job.report.candidates ?? []).map((c) => [c.endpoint_id, c.label]),
                )}
              />
            ) : (
              <Card title="Dependency graph">
                <p className="muted">
                  This scan was made before dependency graphs were built from code. Scan
                  the project again to draw one.
                </p>
              </Card>
            ))}
          {tab === "safekill" && <ScanSafeKillTab job={job} onReviewed={onReviewed} />}
          {tab === "audit" && <ScanAuditTab id={id} />}
          {tab === "benchmark" && <ScanBenchmarkTab job={job} />}
        </>
      )}
    </div>
    </Page>
  );
}

/** What can be done with a finished scan: re-scan it, add usage, take it elsewhere. */
function ScanActions({ job }: { job: ScanJob }) {
  const { api, principal } = useSession();
  const [busy, setBusy] = useState(false);
  const [problem, setProblem] = useState<string | null>(null);
  const approver = canApprove(principal);

  async function rescan() {
    setBusy(true);
    setProblem(null);
    try {
      const next = await api.rescanProject(job.id);
      window.location.hash = `#results/${next.id}/overview`;
    } catch (e) {
      setProblem(e instanceof Error ? e.message : String(e));
    } finally {
      setBusy(false);
    }
  }

  function download(format: "sarif" | "csv" | "openapi") {
    setProblem(null);
    api.download(job.id, format).catch((e: unknown) =>
      setProblem(e instanceof Error ? e.message : String(e)),
    );
  }

  return (
    <>
      {problem && (
        <span className="bad-text small" role="alert">
          {problem}
        </span>
      )}
      {approver && job.kind === "github" && (
        <button className="secondary" onClick={rescan} disabled={busy}>
          {busy ? "Starting..." : "Re-scan"}
        </button>
      )}
      {approver && (
        <a className="btn secondary" href={`#results/${job.id}/usage`}>
          Import access logs
        </a>
      )}
      <Menu
        label="Export"
        items={[
          { label: "Executive report", hint: "printable summary, save as PDF", onSelect: () => { window.location.hash = `#report/${job.id}`; } },
          { label: "SARIF 2.1.0", hint: "GitHub code scanning, Azure DevOps", onSelect: () => download("sarif") },
          { label: "Inventory (CSV)", hint: "spreadsheet or GRC tool", onSelect: () => download("csv") },
          { label: "OpenAPI stubs", hint: "a draft spec for every undocumented endpoint", onSelect: () => download("openapi") },
        ]}
      />
    </>
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
