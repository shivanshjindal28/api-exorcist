import { cleanup, render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, describe, expect, it, vi } from "vitest";
import { ApiClient, ApiError } from "../api";
import { SessionContext } from "../common";
import type { Principal, SafeKillState } from "../types";
import { Login } from "../views/Login";
import { SafeKill } from "../views/SafeKill";

afterEach(cleanup);

const STATE: SafeKillState = {
  policy: { shadow_days: 90, canary_days: [7, 7, 14], confidence: 0.95 },
  candidates: [
    { endpoint_id: "GET /v1/cards/{id}/pin", may_proceed: true, blocked_by: null, status: "NOT_STARTED" },
    { endpoint_id: "POST /v1/debug/payments/replay", may_proceed: true, blocked_by: null, status: "AWAITING_APPROVAL" },
  ],
  pending: [
    {
      endpoint_id: "POST /v1/debug/payments/replay",
      confidence: 0.95,
      reasons: ["no meaningful traffic in the capture window"],
      warnings: ["266 unidentified request(s) in 90 days (2.96/day)."],
      baseline_per_day: 2.96,
      outcome: null,
    },
  ],
  decided: [],
};

function renderSafeKill(role: Principal["role"], decide = vi.fn()) {
  const api = {
    safekill: vi.fn(async () => STATE),
    decide,
    startShadow: vi.fn(),
  } as unknown as ApiClient;
  render(
    <SessionContext.Provider value={{ api, principal: { name: "jal", role }, signOut: vi.fn() }}>
      <SafeKill />
    </SessionContext.Provider>,
  );
  return { decide };
}

describe("Safe Kill view", () => {
  it("shows a viewer every decision but no way to make one", async () => {
    renderSafeKill("viewer");
    await screen.findByText(/Awaiting a decision/);
    expect(screen.queryByRole("button", { name: /Approve/ })).toBeNull();
    expect(screen.queryByRole("button", { name: /Start shadow/ })).toBeNull();
    expect(screen.getByText(/signed in as a viewer/)).toBeTruthy();
  });

  it("never offers approval over unidentified traffic, and says what to do", async () => {
    renderSafeKill("approver", vi.fn(async () => ({})));
    const approve = await screen.findByRole("button", { name: /Approve/ });
    expect((approve as HTMLButtonElement).disabled).toBe(true);
    // No way to accept the risk: the override that once retired this endpoint is gone.
    expect(screen.queryByRole("checkbox")).toBeNull();
    expect(screen.getByText(/This removal cannot be approved/)).toBeTruthy();
    expect(screen.getByText(/Put authentication in front of the/)).toBeTruthy();
  });

  it("lets an approver decline without accepting anything", async () => {
    const user = userEvent.setup();
    const { decide } = renderSafeKill("approver", vi.fn(async () => ({})));
    // The accessible name carries the endpoint, so a screen reader (or a test)
    // can tell one row's Decline from another's.
    await user.click(
      await screen.findByRole("button", { name: "Decline removal of POST /v1/debug/payments/replay" }),
    );
    expect(decide).toHaveBeenCalledWith("POST /v1/debug/payments/replay", false, "");
  });
});

describe("Login", () => {
  it("rejects an unrecognised token without signing in", async () => {
    const user = userEvent.setup();
    const onSignIn = vi.fn();
    const client = { whoami: vi.fn(async () => Promise.reject(new ApiError(401, "no"))) } as unknown as ApiClient;
    render(<Login onSignIn={onSignIn} makeClient={() => client} />);
    await user.type(screen.getByLabelText("Token"), "apx_wrong");
    await user.click(screen.getByRole("button", { name: "Sign in" }));
    expect(await screen.findByRole("alert")).toHaveProperty("textContent", "That token was not recognised.");
    expect(onSignIn).not.toHaveBeenCalled();
  });

  it("signs in with the principal the server returns", async () => {
    const user = userEvent.setup();
    const onSignIn = vi.fn();
    const who = { name: "shivansh", role: "approver" as const };
    const client = { whoami: vi.fn(async () => who) } as unknown as ApiClient;
    render(<Login onSignIn={onSignIn} makeClient={() => client} />);
    const input = screen.getByLabelText("Token");
    expect(input.getAttribute("type")).toBe("password");
    await user.type(input, "apx_right");
    await user.click(screen.getByRole("button", { name: "Sign in" }));
    await waitFor(() => expect(onSignIn).toHaveBeenCalledWith("apx_right", who));
  });
});
