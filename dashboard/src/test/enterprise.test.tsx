// The views built on usage evidence: the portfolio dashboard, the Usage view,
// retirement plans, exports, drift and the executive report.

import { cleanup, render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import type { ReactElement } from "react";
import { afterEach, describe, expect, it, vi } from "vitest";
import type { ApiClient } from "../api";
import { SessionContext } from "../common";
import type { Portfolio, Principal, ScanEndpoint, ScanJob, Traffic } from "../types";
import { Dashboard } from "../views/Dashboard";
import { recommend } from "../views/Report";
import { ScanView } from "../views/scan/ScanView";

afterEach(() => {
  cleanup();
  window.location.hash = "";
});

function withSession(node: ReactElement, api: Partial<ApiClient>, role: Principal["role"] = "approver") {
  render(
    <SessionContext.Provider
      value={{ api: api as unknown as ApiClient, principal: { name: "ann", role }, signOut: vi.fn() }}
    >
      {node}
    </SessionContext.Provider>,
  );
}

const EP = (id: string, extra: Partial<ScanEndpoint> = {}): ScanEndpoint => {
  const [method = "GET", path = "/"] = id.split(" ");
  return {
    id, method, path, file: "app.py", line: 3, framework: "flask", owner: null,
    last_change_days: 400, documented: true, deprecated_in_spec: false, seen_by: ["CODE"],
    flags: [], findings: [], risk: 1, priority: 1,
    sensitivity: { category: "General", level: "low", because: "no sensitive word" }, ...extra,
  };
};

const TRAFFIC: Traffic = {
  window: { start: "2026-09-01T00:00:00+00:00", end: "2026-10-15T00:00:00+00:00", days: 44 },
  requests: 120, matched: 110, preflight: 0, unmatched: 10, gateway_prefixes: ["/api"],
  lifecycle: { ZOMBIE: 1, ORPHANED: 1 },
  endpoints: {
    "POST /v2/check-otp": {
      requests: 30, ok: 0, failed: 30, server_errors: 0, clients: 1, clients_capped: false,
      first_seen: null, last_seen: null, last_success: null, daily: [["2026-10-01", 30]],
      lifecycle: "ZOMBIE", reason: "no successful request in 44 days. Only failed requests (30): someone probing it.",
    },
    "GET /v1/orders": {
      requests: 80, ok: 80, failed: 0, server_errors: 0, clients: 9, clients_capped: false,
      first_seen: null, last_seen: null, last_success: "2026-10-14T00:00:00+00:00",
      daily: [["2026-10-01", 40], ["2026-10-02", 40]], lifecycle: "ORPHANED",
      reason: "80 successful request(s) from 9 client(s), and no owning team is recorded",
    },
  },
  shadow_routes: [{ method: "GET", path: "/legacy/export", requests: 10, ok: 10, failed: 0, clients: 2, last_seen: null }],
  shadow_routes_total: 1, probing: [], probing_total: 0, uncovered_services: [],
  files: [{ name: "access.log", lines: 121, parsed: 120, format: "combined", note: "" }],
  truncated: false, imported_at: "2026-10-15T00:00:00+00:00", imported_by: "ann",
};

const JOB: ScanJob = {
  id: "0123456789ab", kind: "github", target: "github.com/acme/bank", requested_by: "ann",
  status: "done", created_at: "2026-10-15T00:00:00+00:00", started_at: null, finished_at: null,
  duration_s: 9, error: null, progress: [],
  report: {
    summary: [{ label: "Endpoints found", value: 2 }],
    checks: [],
    endpoints: [
      EP("POST /v2/check-otp", {
        priority: 15, sensitivity: { category: "Authentication", level: "high", because: "the word 'otp'" },
        candidate: { endpoint_id: "POST /v2/check-otp", score: 8, label: "Likely zombie", signals: [] },
      }),
      EP("GET /v1/orders"),
    ],
    repository_findings: [],
    candidates: [{ endpoint_id: "POST /v2/check-otp", score: 8, label: "Likely zombie", signals: [] }],
    lifecycle: { available: false, why: "" },
    details: { commit: "abc1234", specifications: [], mount_prefixes: [] },
  },
  traffic: TRAFFIC,
  changes: {
    previous: { id: "ba9876543210", finished_at: null, commit: "abc1234" }, same_commit: true,
    added: ["POST /v2/check-otp"], added_undocumented: [], removed: [], became_undocumented: [],
    became_documented: [], new_candidates: [], resolved_candidates: [], unchanged: 1,
  },
};

describe("Dashboard", () => {
  it("ranks the riskiest endpoints across every project", async () => {
    const folio: Portfolio = {
      totals: { projects: 1, endpoints: 2, undocumented: 1, candidates: 1, likely: 1, zombies: 1, high_sensitivity: 1, reviewed: 0 },
      projects: [{ id: JOB.id, target: JOB.target, kind: "github", scanned_at: JOB.created_at, endpoints: 2,
        undocumented: 1, candidates: 1, likely: 1, zombies: 1, high_sensitivity: 1, reviewed: 0, traffic: true, risk: 15 }],
      top_risks: [{ scan: JOB.id, target: JOB.target, id: "POST /v2/check-otp", priority: 15,
        sensitivity: "Authentication", level: "high", label: "Zombie (no traffic)", documented: true }],
    };
    withSession(<Dashboard />, { portfolio: vi.fn(async () => folio) });
    expect(await screen.findByText("Needs attention")).toBeTruthy();
    expect(screen.getByText("POST /v2/check-otp").closest("a")?.getAttribute("href")).toBe(`#results/${JOB.id}/endpoints`);
    expect(screen.getByText("Zombie (no traffic)")).toBeTruthy();
    expect(screen.getByText("logs imported")).toBeTruthy();
  });

  it("offers a first scan and the demo when nothing is scanned", async () => {
    const empty: Portfolio = {
      totals: { projects: 0, endpoints: 0, undocumented: 0, candidates: 0, likely: 0, zombies: 0, high_sensitivity: 0, reviewed: 0 },
      projects: [], top_risks: [],
    };
    withSession(<Dashboard />, { portfolio: vi.fn(async () => empty) });
    expect(await screen.findByText("No projects scanned yet")).toBeTruthy();
    expect(screen.getByText("Explore the demo bank")).toBeTruthy();
  });
});

describe("Usage view", () => {
  it("shows proven zombies with the reason, and traffic the code does not explain", async () => {
    withSession(<ScanView param={`${JOB.id}/usage`} />, { scan: vi.fn(async () => JOB) });
    expect(await screen.findByText("Lifecycle, from real usage")).toBeTruthy();
    expect(screen.getByText(/someone probing it/)).toBeTruthy();
    expect(screen.getByText("/legacy/export")).toBeTruthy();
    expect(screen.getByText(/repository records no owners/)).toBeTruthy();
  });

  it("imports log files and shows the result", async () => {
    const user = userEvent.setup();
    const importTraffic = vi.fn(async () => JOB);
    withSession(<ScanView param={`${JOB.id}/usage`} />, {
      scan: vi.fn(async () => ({ ...JOB, traffic: null })), importTraffic,
    });
    const input = (await screen.findByLabelText("Choose access log files")) as HTMLInputElement;
    await user.upload(input, new File(["127.0.0.1 - - x"], "access.log", { type: "text/plain" }));
    await user.click(screen.getByRole("button", { name: "Import and classify" }));
    expect(importTraffic).toHaveBeenCalledWith(JOB.id, [expect.any(File)], expect.any(Function));
    expect(await screen.findByText("Lifecycle, from real usage")).toBeTruthy();
  });

  it("lets a viewer read usage but not import it", async () => {
    withSession(<ScanView param={`${JOB.id}/usage`} />, { scan: vi.fn(async () => ({ ...JOB, traffic: null })) }, "viewer");
    expect(await screen.findByText(/Importing them needs an approver/)).toBeTruthy();
    expect(screen.queryByLabelText("Choose access log files")).toBeNull();
  });
});

describe("Retirement plans", () => {
  it("drafts a plan for each proven zombie and shows what blocks it", async () => {
    const plan = vi.fn(async () => ({
      endpoint_id: "POST /v2/check-otp", ready: false, sunset: "2027-01-13",
      blockers: ["No owning team is recorded; someone must own the decision and the rollback."],
      steps: [{ title: "Announce the retirement in every response", detail: "RFC 9745", snippet: "location = /v2/check-otp {}", snippet_label: "nginx" }],
    }));
    withSession(<ScanView param={`${JOB.id}/safekill`} />, { scan: vi.fn(async () => JOB), plan });
    expect(await screen.findByText("Retirement plans (1)")).toBeTruthy();
    expect(await screen.findByText(/No owning team is recorded/)).toBeTruthy();
    expect(screen.getByText("location = /v2/check-otp {}")).toBeTruthy();
    expect(plan).toHaveBeenCalledWith(JOB.id, "POST /v2/check-otp");
    // Imported logs count as usage evidence: partly, since 44 days is under 90.
    expect(screen.getByText(/44 days of access logs imported/)).toBeTruthy();
  });
});

describe("Scan actions", () => {
  it("exports through the API client, never a link carrying the token", async () => {
    const user = userEvent.setup();
    const download = vi.fn(async () => undefined);
    withSession(<ScanView param={`${JOB.id}/overview`} />, { scan: vi.fn(async () => JOB), download });
    await user.click(await screen.findByRole("button", { name: "Export" }));
    await user.click(screen.getByRole("menuitem", { name: /SARIF/ }));
    expect(download).toHaveBeenCalledWith(JOB.id, "sarif");
  });

  it("says when drift between two scans of one commit is the scanner's, not the code's", async () => {
    withSession(<ScanView param={`${JOB.id}/overview`} />, { scan: vi.fn(async () => JOB) });
    expect(await screen.findByText(/Both scans read the same commit/)).toBeTruthy();
  });
});

describe("Executive report recommendations", () => {
  it("follows the strongest evidence, and never says remove for an endpoint in use", () => {
    const e = EP("GET /x");
    expect(recommend(e, "ZOMBIE")).toMatch(/^Retire/);
    expect(recommend(e, "ORPHANED")).toMatch(/do not remove/);
    expect(recommend({ ...e, candidate: { endpoint_id: "GET /x", score: 2, label: "Debug or test endpoint", signals: [] } }, "ORPHANED"))
      .toMatch(/find its callers/);
    expect(recommend({ ...e, documented: false }, undefined)).toBe("Document it, or retire it");
    expect(recommend(e, "ACTIVE")).toBe("No action");
  });
});
