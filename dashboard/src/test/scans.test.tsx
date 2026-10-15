import { cleanup, render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, describe, expect, it, vi } from "vitest";
import type { ApiClient } from "../api";
import { route, takeSigninToken } from "../App";
import { SessionContext } from "../common";
import { selectFiles } from "../folder";
import type { Capabilities, Principal, ScanJob } from "../types";
import { NewScan } from "../views/NewScan";
import { ScanView } from "../views/scan/ScanView";

afterEach(() => {
  cleanup();
  window.location.hash = "";
});

function file(path: string, size = 10) {
  return { file: new Blob(["x".repeat(size)]) as Blob & { name: string; size: number }, path };
}

describe("choosing what to upload from a folder", () => {
  it("leaves out dependencies, binaries and huge files, and counts them", () => {
    const sel = selectFiles([
      file("shop/app/main.py"),
      file("shop/docs/openapi.yaml"),
      file("shop/node_modules/express/index.js"),
      file("shop/.git/HEAD"),
      file("shop/logo.png"),
      file("shop/dist/bundle.js", 3 * 1024 * 1024),
      file("shop/big.json", 3 * 1024 * 1024),
    ]);
    expect(sel.upload.map((f) => f.path)).toEqual(["shop/app/main.py", "shop/docs/openapi.yaml"]);
    expect(sel.skipped).toEqual({ dependencies: 3, binary: 1, tooLarge: 1 });
    expect(sel.root).toBe("shop");
  });
});

describe("routing and sign-in", () => {
  it("opens a scan's report from its link, and the dashboard by default", () => {
    expect(route("#results/abc123def456")).toEqual({ view: "results", param: "abc123def456" });
    expect(route("#scan")).toEqual({ view: "scan", param: null });
    expect(route("#report/abc123def456")).toEqual({ view: "report", param: "abc123def456" });
    expect(route("#nonsense")).toEqual({ view: "dashboard", param: null });
    // Links from before every scan had the five views still reach the demo.
    expect(route("#safekill")).toEqual({ view: "results", param: "demo/safekill" });
    expect(route("")).toEqual({ view: "dashboard", param: null });
  });

  it("takes a sign-in token from the fragment and erases it from the address bar", () => {
    window.history.replaceState(null, "", "/#signin=apx_abc-DEF_123");
    expect(takeSigninToken()).toBe("apx_abc-DEF_123");
    expect(window.location.href).not.toContain("apx_");
    expect(window.location.hash).toBe("#dashboard");
    // Anything else in the fragment is not a token.
    window.history.replaceState(null, "", "/#signin=<script>");
    expect(takeSigninToken()).toBeNull();
  });
});

const CAPS: Capabilities = {
  folder: { available: true, warning: null },
  github: { available: true, warning: null, reason: null },
  website: { available: false, reason: "Scanning a live website is not available in this version." },
};

function renderNewScan(role: Principal["role"], api: Partial<ApiClient>) {
  render(
    <SessionContext.Provider
      value={{
        api: { capabilities: vi.fn(async () => CAPS), ...api } as unknown as ApiClient,
        principal: { name: "ann", role },
        signOut: vi.fn(),
      }}
    >
      <NewScan />
    </SessionContext.Provider>,
  );
}

describe("New scan", () => {
  it("offers three inputs and says why the website one is unavailable", async () => {
    renderNewScan("approver", {});
    expect(await screen.findByText(/not available in this version/)).toBeTruthy();
    expect((screen.getByLabelText("Website address") as HTMLInputElement).disabled).toBe(true);
    expect((screen.getByRole("button", { name: "Not available" }) as HTMLButtonElement).disabled).toBe(true);
    expect(screen.getByLabelText("Choose a project folder")).toBeTruthy();
    expect(screen.getByLabelText("Repository link")).toBeTruthy();
  });

  it("starts a GitHub scan and goes to its progress page", async () => {
    const user = userEvent.setup();
    const scanGithub = vi.fn(async () => ({ id: "0123456789ab" }) as ScanJob);
    renderNewScan("approver", { scanGithub });
    await user.type(screen.getByLabelText("Repository link"), "https://github.com/a/b");
    await user.click(screen.getByRole("button", { name: "Scan repository" }));
    expect(scanGithub).toHaveBeenCalledWith("https://github.com/a/b");
    await waitFor(() => expect(window.location.hash).toBe("#results/0123456789ab/overview"));
  });

  it("lets a viewer look but not start a scan", async () => {
    renderNewScan("viewer", {});
    expect(await screen.findByText(/signed in as a viewer/)).toBeTruthy();
    expect((screen.getByLabelText("Repository link") as HTMLInputElement).disabled).toBe(true);
  });
});

const DONE: ScanJob = {
  id: "0123456789ab",
  kind: "folder",
  target: "shop",
  requested_by: "ann",
  status: "done",
  created_at: "2026-10-12T10:00:00+00:00",
  started_at: null,
  finished_at: null,
  duration_s: 3.2,
  error: null,
  progress: [],
  report: {
    summary: [{ label: "Endpoints found", value: 1 }],
    checks: [
      { name: "API routes in the code", status: "ok", detail: "1 route" },
      { name: "Change history", status: "unavailable", detail: "an uploaded folder does not include git history" },
    ],
    endpoints: [
      {
        id: "DELETE /v1/orders/{id}", method: "DELETE", path: "/v1/orders/{id}", file: "api.py",
        line: 9, framework: "flask", owner: null, last_change_days: null, documented: false,
        deprecated_in_spec: false, seen_by: ["CODE"], flags: [], risk: 2,
        findings: ["handler exists in code but the endpoint is not documented"],
      },
    ],
    repository_findings: [],
    // Spelled as real reports spell them: upper case, as apix.connectors.base.Source.
    sources: { consulted: ["CICD", "CODE", "OPENAPI"], unavailable: ["DNS", "GATEWAY", "TRAFFIC"] },
    lifecycle: { available: false, why: "No usage data." },
    details: { commit: null, specifications: [], mount_prefixes: [] },
  },
};

function renderReport(job: ScanJob, tab = "overview", extra: Partial<ApiClient> = {}) {
  render(
    <SessionContext.Provider
      value={{
        api: { scan: vi.fn(async () => job), ...extra } as unknown as ApiClient,
        principal: { name: "ann", role: "approver" },
        signOut: vi.fn(),
      }}
    >
      <ScanView param={`${job.id}/${tab}`} />
    </SessionContext.Provider>,
  );
}

describe("Scan report", () => {
  it("says what could not be checked, and why", async () => {
    renderReport(DONE);
    expect(await screen.findByText("Change history")).toBeTruthy();
    expect(screen.getByText(/does not include git history/)).toBeTruthy();
    expect(screen.getByText("not available")).toBeTruthy();
    expect(screen.getByText(/Why no endpoint is called a zombie/)).toBeTruthy();
  });

  it("has the demo bank's six views, plus Usage for imported access logs", async () => {
    renderReport(DONE);
    const tabs = await screen.findByRole("navigation", { name: "Scan views" });
    const names = Array.from(tabs.querySelectorAll("a")).map((a) => a.childNodes[0]?.textContent);
    expect(names).toEqual([
      "Overview", "Endpoints", "Usage", "Dependency graph", "Safe Kill", "Audit log", "Benchmark",
    ]);
  });

  it("shows an endpoint's sources and findings on the Endpoints view", async () => {
    renderReport(DONE, "endpoints");
    expect(await screen.findByText("handler exists in code but the endpoint is not documented")).toBeTruthy();
    expect(screen.getByTitle("Traffic: not consulted")).toBeTruthy();
    expect(screen.getByTitle("Code: saw it")).toBeTruthy();
  });

  it("records a review decision, without sending a reviewer name", async () => {
    const user = userEvent.setup();
    const review = vi.fn(async () => ({
      reviews: { "DELETE /v1/orders/{id}": { decision: "investigate", label: "Investigate for removal", by: "ann", at: "2026-10-12T10:00:00+00:00", note: "" } },
    }));
    renderReport(DONE, "endpoints", { review } as Partial<ApiClient>);
    await user.click(await screen.findByRole("button", { name: "Investigate for removal: DELETE /v1/orders/{id}" }));
    expect(review).toHaveBeenCalledWith("0123456789ab", "DELETE /v1/orders/{id}", "investigate", "");
    expect((await screen.findAllByText("Investigate for removal")).length).toBeGreaterThan(0);
  });

  it("says on the Safe Kill view what removal still needs", async () => {
    renderReport(DONE, "safekill");
    expect(await screen.findByText(/Why nothing is removed/)).toBeTruthy();
    expect(screen.getByText("Usage data, to classify an endpoint as a zombie")).toBeTruthy();
    expect(screen.getAllByText("missing").length).toBe(3);
  });

  it("benchmarks against a documentation-only inventory, and says when there is none", async () => {
    renderReport(DONE, "benchmark");
    expect(await screen.findByText(/publishes no API specification/)).toBeTruthy();
    expect(screen.getByText(/coverage, not accuracy/)).toBeTruthy();
  });

  it("explains a failed scan instead of showing an empty report", async () => {
    renderReport({
      ...DONE, status: "failed", report: undefined,
      error: "could not download a/b: the repository does not exist, or it is private",
    });
    expect(await screen.findByText(/could not finish/)).toBeTruthy();
    expect(screen.getByText(/it is private/)).toBeTruthy();
  });
});


// ---------------------------------------------------------------------------
// The dependency graph
import { layers, layout, serviceEdges } from "../graphLayout";
import { GraphPanel } from "../views/scan/Graph";
import type { GraphView } from "../types";

const GRAPH: GraphView = {
  basis: "code",
  services: [
    { id: "api-gateway", kind: "gateway", endpoints: [] },
    { id: "account-service", kind: "service", endpoints: ["POST /api/accounts/internal/debit"] },
    { id: "transaction-service", kind: "service", endpoints: ["POST /api/transactions/transfer"] },
  ],
  endpoints: [
    { id: "POST /api/accounts/internal/debit", service: "account-service", method: "POST",
      path: "/api/accounts/internal/debit", label: null, exposed_via: ["api-gateway /api/accounts/**"],
      callers: ["transaction-service"], isolated: false },
    { id: "POST /api/transactions/transfer", service: "transaction-service", method: "POST",
      path: "/api/transactions/transfer", label: null, exposed_via: [], callers: [], isolated: true },
  ],
  edges: [
    { kind: "calls", from: "transaction-service", to: "POST /api/accounts/internal/debit",
      evidence: "RestClient/WebClient call in transaction-service/AccountClientImpl.java:70" },
    { kind: "routes", from: "api-gateway", to: "account-service", label: "/api/accounts/**",
      evidence: "route /api/accounts/** in api-gateway/application.yml:22" },
  ],
  radius: {
    "POST /api/accounts/internal/debit": {
      endpoint_id: "POST /api/accounts/internal/debit", direct_services: ["transaction-service"],
      indirect_services: [], affected_endpoints: [{ endpoint_id: "POST /api/transactions/transfer", hop: 2 }],
      depth_reached: 2, truncated: false, isolated: false, severity: "contained",
    },
    "POST /api/transactions/transfer": {
      endpoint_id: "POST /api/transactions/transfer", direct_services: [], indirect_services: [],
      affected_endpoints: [], depth_reached: 0, truncated: false, isolated: true, severity: "isolated",
    },
  },
  notes: ["Read from 146 source and config files."],
  stats: { services: 2, endpoints: 2, calls: 1, routes: 1, topics: 0, isolated: 1 },
};

describe("dependency graph layout", () => {
  it("puts callers to the left of what they call", () => {
    const lay = layout(GRAPH);
    const x = (id: string) => lay.boxes.get(id)!.x;
    expect(x("transaction-service")).toBeLessThan(x("account-service"));
    expect(x("api-gateway")).toBeLessThan(x("account-service"));
    expect(serviceEdges(GRAPH)).toContainEqual(["transaction-service", "account-service"]);
  });

  it("survives a cycle between services", () => {
    const l = layers(["a", "b", "c"], [["a", "b"], ["b", "c"], ["c", "a"]]);
    expect([...l.values()].every((n) => n >= 0 && n < 3)).toBe(true);
  });
});

describe("dependency graph view", () => {
  it("shows an endpoint's blast radius and the code behind each caller", async () => {
    const user = userEvent.setup();
    render(<GraphPanel view={GRAPH} />);
    expect(screen.getByText(/Drawn from the code/)).toBeTruthy();
    await user.click(screen.getByRole("button", { name: "Endpoint POST /api/accounts/internal/debit" }));
    expect(screen.getByText("contained")).toBeTruthy();
    // In the side panel, not only in the arrow's hover tooltip.
    const evidence = screen.getAllByText(/AccountClientImpl.java:70/);
    expect(evidence.some((el) => el.tagName.toLowerCase() !== "title")).toBe(true);
    // The side panel lists them in <code>; the drawing has its own copies.
    expect(screen.getByText("POST /api/transactions/transfer", { selector: "code" })).toBeTruthy();
    expect(screen.getByText("api-gateway /api/accounts/**", { selector: "code" })).toBeTruthy();
  });

  it("says an endpoint is isolated without claiming nothing outside could call it", async () => {
    const user = userEvent.setup();
    render(<GraphPanel view={GRAPH} />);
    await user.click(screen.getByRole("button", { name: "Endpoint POST /api/transactions/transfer" }));
    expect(screen.getByText(/Callers outside the repository would not show here/)).toBeTruthy();
  });
});


describe("Safe Kill with a graph drawn from code", () => {
  it("counts the dependency graph as partly there, and says why not fully", async () => {
    renderReport({ ...DONE, report: { ...DONE.report!, graph: GRAPH } }, "safekill");
    expect(await screen.findByText("partly")).toBeTruthy();
    expect(screen.getAllByText("missing").length).toBe(2);
    expect(screen.getByText(/not callers outside the repository/)).toBeTruthy();
  });
});


// ---------------------------------------------------------------------------
// Zombie candidates
import { CandidatesCard } from "../views/scan/Candidates";

describe("Zombie candidates card", () => {
  it("ranks candidates and shows the evidence behind the top one", () => {
    const job: ScanJob = {
      ...DONE,
      report: {
        ...DONE.report!,
        candidates: [
          {
            endpoint_id: "POST /identity/api/auth/v2/check-otp", score: 8, label: "Likely zombie",
            signals: [
              { key: "superseded", weight: 3, text: "a newer version of this operation exists: POST /identity/api/auth/v3/check-otp" },
              { key: "superseded", weight: 2, text: "this project's own client calls the newer version and never this one" },
            ],
          },
          { endpoint_id: "GET /users/v1/_debug", score: 2, label: "Debug or test endpoint", signals: [] },
        ],
      },
    };
    render(<CandidatesCard job={job} />);
    expect(screen.getByText("Zombie candidates (2)")).toBeTruthy();
    expect(screen.getByText("Likely zombie")).toBeTruthy();
    expect(screen.getByText(/calls the newer version and never this one/)).toBeTruthy();
  });

  it("explains an empty result by the evidence the repository lacks", () => {
    const job: ScanJob = { ...DONE, report: { ...DONE.report!, candidates: [] } };
    render(<CandidatesCard job={job} />);
    expect(screen.getByText("Zombie candidates: none")).toBeTruthy();
    // The fixture is versioned (/v1/...) but undocumented, with no client.
    expect(screen.queryByText(/no versioned paths/)).toBeNull();
    expect(screen.getByText(/no API specification/)).toBeTruthy();
    expect(screen.getByText(/no front end, SDK or other client/)).toBeTruthy();
    expect(screen.getByText(/property of the repository, not a failure/)).toBeTruthy();
  });

  it("asks for a rescan when the report predates candidates", () => {
    render(<CandidatesCard job={DONE} />);
    expect(screen.getByText(/made before zombie candidates were computed/)).toBeTruthy();
  });
});
