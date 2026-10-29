import { cleanup, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it } from "vitest";
import type { SafeKillState, ScanEndpoint, ScanJob, Verdict } from "../types";
import {
  RealApiEvidence,
  SafeKillSteps,
  ScoreTable,
  TrustCard,
  WhatWouldChange,
  softmaxConfidence,
} from "../views/explain";

afterEach(cleanup);

// The rules that fire for GET /v1/kyc/documents/{id}/raw on the demo estate,
// with the weights the engine holds (apix/engine/rules.py). Real output, not a
// shape invented for the test.
const w = (a: number, d: number, o: number, z: number) => ({
  ACTIVE: a, DEPRECATED: d, ORPHANED: o, ZOMBIE: z,
});
const KYC_RAW: Verdict = {
  endpoint_id: "GET /v1/kyc/documents/{id}/raw",
  label: "ZOMBIE",
  confidence: 0.9902,
  decided_by: "rules",
  risk_score: 5,
  all_class_scores: { ACTIVE: -11.6, DEPRECATED: -1.5, ORPHANED: -4.0, ZOMBIE: 13.5 },
  evidence: [],
  recommended_action: "Candidate for Safe Kill.",
  actionable: true,
  abstained: [],
  score_table: [
    { key: "NO_MEANINGFUL_TRAFFIC", statement: "no meaningful traffic in the capture window", source: "TRAFFIC", weights: w(-3, 0.5, -2.5, 3.5) },
    { key: "SHADOW", statement: "absent from both the OpenAPI spec and the gateway registry", source: "OPENAPI+GATEWAY", weights: w(-2, -1.5, 0, 2.5) },
    { key: "STALE_6M", statement: "no meaningful use for over six months", source: "TRAFFIC", weights: w(-2, 0, -1.5, 2) },
    { key: "REACHABLE_BUT_UNUSED", statement: "still resolvable via DNS despite no observed traffic", source: "DNS+TRAFFIC", weights: w(0, 0, 0, 1.5) },
    { key: "NO_PIPELINE_RECORD", statement: "no CI/CD pipeline record", source: "CICD", weights: w(-0.8, 0, 0, 1.2) },
    { key: "UNDOCUMENTED", statement: "handler exists in code but the endpoint is not documented", source: "CODE+OPENAPI", weights: w(-1, -1, 0, 1) },
    { key: "CODE_UNTOUCHED_1Y", statement: "no commit touching this handler in over a year", source: "CODE", weights: w(-0.8, 0.5, 0, 1) },
    { key: "NO_OWNER", statement: "no owning team could be determined", source: "OPENAPI+CICD+CODE", weights: w(-2, 0, 0, 0.8) },
  ],
};

describe("ScoreTable", () => {
  it("shows every rule and totals that reproduce the engine's scores and confidence", () => {
    render(<ScoreTable verdict={KYC_RAW} />);
    expect(screen.getAllByRole("row")).toHaveLength(1 + 8 + 1);
    const totals = screen.getAllByRole("row").at(-1)!;
    expect(totals.textContent).toContain("+13.5");
    expect(totals.textContent).toContain("−11.6");
    expect(screen.getByText("99.0%")).toBeTruthy();
    expect(softmaxConfidence(KYC_RAW.all_class_scores, "ZOMBIE")).toBeCloseTo(0.9902, 3);
  });

  it("names the rules that could not be evaluated, as not evidence", () => {
    render(<ScoreTable verdict={{ ...KYC_RAW, abstained: ["NO_MEANINGFUL_TRAFFIC"] }} />);
    expect(screen.getByText(/no meaningful traffic\. An unconsulted source/)).toBeTruthy();
  });

  it("says plainly when the model, not the rules, decided", () => {
    render(<ScoreTable verdict={{ ...KYC_RAW, decided_by: "model", score_table: [] }} />);
    expect(screen.getByText(/Decided by the learned model/)).toBeTruthy();
  });
});

describe("SafeKillSteps", () => {
  const STATE: SafeKillState = {
    policy: { shadow_days: 90, canary_days: [7, 7, 14], confidence: 0.95 },
    candidates: [
      { endpoint_id: "a", may_proceed: true, blocked_by: null, status: "NOT_STARTED" },
      { endpoint_id: "b", may_proceed: true, blocked_by: null, status: "AWAITING_APPROVAL" },
      { endpoint_id: "c", may_proceed: true, blocked_by: null, status: "RETIRED" },
    ],
    pending: [],
    decided: [],
  };

  it("lists the five steps with the policy's own numbers and where each candidate is", () => {
    render(<SafeKillSteps state={STATE} />);
    expect(screen.getAllByRole("listitem")).toHaveLength(5);
    expect(screen.getByText("Shadow, 90 days")).toBeTruthy();
    expect(screen.getByText(/7 \/ 7 \/ 14 days/)).toBeTruthy();
    expect(screen.getAllByText("1 here")).toHaveLength(3);
  });
});

const EP: ScanEndpoint = {
  id: "GET /api/tags",
  method: "GET",
  path: "/api/tags",
  file: "src/app/routes/tag/tag.controller.ts",
  line: 13,
  framework: "express",
  declared_path: "/tags",
  prefix_resolved: true,
  owner: null,
  last_change_days: null,
  documented: false,
  deprecated_in_spec: false,
  seen_by: ["CODE"],
  flags: [],
  findings: [],
  risk: 1,
  referenced_by: [],
};

describe("RealApiEvidence", () => {
  it("traces a code endpoint to its declaration, and calls a lone one what it is", () => {
    render(<RealApiEvidence e={EP} />);
    expect(screen.getByText(/tag\.controller\.ts:13 as "\/tags"/)).toBeTruthy();
    expect(screen.getByText(/what a shadow endpoint looks like/)).toBeTruthy();
  });

  it("counts the specification and the project's clients as second witnesses", () => {
    render(
      <RealApiEvidence
        e={{ ...EP, documented: true, seen_by: ["CODE", "OPENAPI"], referenced_by: ["web/src/api.ts:12"] }}
      />,
    );
    expect(screen.getByText(/second, independent witness/)).toBeTruthy();
    expect(screen.getByText(/web\/src\/api\.ts:12/)).toBeTruthy();
    expect(screen.queryByText(/shadow endpoint/)).toBeNull();
  });

  it("is honest about a missing handler and an unknown prefix", () => {
    const { unmount } = render(
      <RealApiEvidence e={{ ...EP, seen_by: ["OPENAPI"], file: null, line: null }} />,
    );
    expect(screen.getByText(/No handler was found in code/)).toBeTruthy();
    unmount();
    render(<RealApiEvidence e={{ ...EP, prefix_resolved: false }} />);
    expect(screen.getByText(/could not be determined/)).toBeTruthy();
  });
});

describe("TrustCard", () => {
  it("summarises what the results rest on and what they cannot show", () => {
    const job = {
      id: "abc",
      report: {
        endpoints: [
          EP,
          { ...EP, id: "GET /api/user", seen_by: ["CODE", "OPENAPI"] },
          { ...EP, id: "GET /api/old", seen_by: ["OPENAPI"], file: null, line: null },
        ],
        candidates: [],
      },
    } as unknown as ScanJob;
    render(<TrustCard job={job} />);
    const text = document.body.textContent ?? "";
    expect(text).toContain("2 endpoint(s) were found in the code");
    expect(text).toContain("1 of those are confirmed by a second");
    expect(text).toContain("1 documented endpoint(s) have no handler");
    expect(text).toMatch(/cannot be seen in code/);
  });
});

describe("WhatWouldChange", () => {
  it("states each change and the answer it would give", () => {
    render(
      <WhatWouldChange
        current="zombie"
        items={[{ if: "it carried 10 or more calls a day, recently", to: "ORPHANED", note: "(78% confidence)" }]}
      />,
    );
    const list = screen.getByRole("list", { name: "What would change this" });
    expect(list.textContent).toContain("If it carried 10 or more calls a day, recently,");
    expect(list.textContent).toContain("it would be ORPHANED");
  });

  it("shows nothing when they were not computed, rather than claim firmness", () => {
    const { container } = render(<WhatWouldChange current="zombie" items={undefined} title="What would change it" />);
    expect(container.textContent).toBe("");
  });

  it("says a conclusion is firm when no single change moves it", () => {
    render(<WhatWouldChange current="active" items={[]} />);
    expect(screen.getByText(/No single change to the evidence would move this from active/)).toBeTruthy();
  });
});
