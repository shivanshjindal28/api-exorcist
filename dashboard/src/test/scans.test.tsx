import { cleanup, render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, describe, expect, it, vi } from "vitest";
import type { ApiClient } from "../api";
import { route, takeSigninToken } from "../App";
import { SessionContext } from "../common";
import { selectFiles } from "../folder";
import type { Capabilities, Principal, ScanJob } from "../types";
import { NewScan } from "../views/NewScan";
import { ScanReport } from "../views/ScanReport";

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
  it("opens a scan's report from its link, and New scan by default", () => {
    expect(route("#results/abc123def456")).toEqual({ view: "results", param: "abc123def456" });
    expect(route("#nonsense")).toEqual({ view: "scan", param: null });
    expect(route("")).toEqual({ view: "scan", param: null });
  });

  it("takes a sign-in token from the fragment and erases it from the address bar", () => {
    window.history.replaceState(null, "", "/#signin=apx_abc-DEF_123");
    expect(takeSigninToken()).toBe("apx_abc-DEF_123");
    expect(window.location.href).not.toContain("apx_");
    expect(window.location.hash).toBe("#scan");
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
    await waitFor(() => expect(window.location.hash).toBe("#results/0123456789ab"));
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
        deprecated_in_spec: false, seen_by: ["code"], flags: [], risk: 2,
        findings: ["handler exists in code but the endpoint is not documented"],
      },
    ],
    repository_findings: [],
    lifecycle: { available: false, why: "No usage data." },
    details: { commit: null, specifications: [], mount_prefixes: [] },
  },
};

function renderReport(job: ScanJob) {
  render(
    <SessionContext.Provider
      value={{
        api: { scan: vi.fn(async () => job) } as unknown as ApiClient,
        principal: { name: "ann", role: "approver" },
        signOut: vi.fn(),
      }}
    >
      <ScanReport id={job.id} />
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

  it("shows an endpoint's findings when its row is opened", async () => {
    const user = userEvent.setup();
    renderReport(DONE);
    await user.click(await screen.findByRole("button", { name: "Details for DELETE /v1/orders/{id}" }));
    expect(screen.getByText("handler exists in code but the endpoint is not documented")).toBeTruthy();
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
