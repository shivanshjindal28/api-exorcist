import { describe, expect, it, vi } from "vitest";
import { ApiClient, ApiError } from "../api";

function fakeFetch(status = 200, body: unknown = {}) {
  return vi.fn(async (_input: RequestInfo | URL, _init?: RequestInit) => {
    return new Response(JSON.stringify(body), {
      status,
      headers: { "Content-Type": "application/json" },
    });
  });
}

const TOKEN = "apx_test_token_value";

describe("ApiClient", () => {
  it("sends the token only in the Authorization header, never in the URL", async () => {
    const f = fakeFetch(200, { name: "a", role: "viewer" });
    await new ApiClient(TOKEN, f).whoami();
    const [url, init] = f.mock.calls[0]!;
    expect(String(url)).not.toContain(TOKEN);
    expect((init?.headers as Record<string, string>).Authorization).toBe(`Bearer ${TOKEN}`);
    expect(init?.credentials).toBe("omit");
    expect(init?.cache).toBe("no-store");
  });

  it("percent-encodes endpoint ids in paths", async () => {
    const f = fakeFetch(200, {});
    await new ApiClient(TOKEN, f).verdict("GET /v1/cards/{id}/pin");
    expect(String(f.mock.calls[0]![0])).toBe("/v1/verdicts/GET%20%2Fv1%2Fcards%2F%7Bid%7D%2Fpin");
  });

  it("never sends an approver name: identity comes from the token", async () => {
    const f = fakeFetch(200, {});
    await new ApiClient(TOKEN, f).decide("GET /x", true, "looks dead");
    const body = JSON.parse(String(f.mock.calls[0]![1]?.body)) as Record<string, unknown>;
    expect(body).toEqual({
      endpoint_id: "GET /x",
      approve: true,
      note: "looks dead",
    });
    expect(body).not.toHaveProperty("approver");
    expect(body).not.toHaveProperty("accept_unidentified");
  });

  it("raises an ApiError that knows a 401 means sign in again", async () => {
    const f = fakeFetch(401, { detail: "token not recognised" });
    const err = await new ApiClient(TOKEN, f).summary().catch((e: unknown) => e);
    expect(err).toBeInstanceOf(ApiError);
    expect((err as ApiError).unauthorised).toBe(true);
    expect((err as ApiError).message).toBe("token not recognised");
  });

  it("surfaces the server's explanation for a refused decision", async () => {
    const f = fakeFetch(409, { detail: "266 unidentified request(s)..." });
    const err = await new ApiClient(TOKEN, f).decide("POST /d", true, "").catch((e: unknown) => e);
    expect((err as ApiError).status).toBe(409);
    expect((err as ApiError).unauthorised).toBe(false);
    expect((err as ApiError).message).toContain("unidentified");
  });
});
