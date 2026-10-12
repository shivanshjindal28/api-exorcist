// The only module that talks to the server.
//
// Two rules hold here and nowhere else needs to remember them:
//   * the token travels only in the Authorization header, never in a URL,
//     where it would land in server logs, history and Referer headers;
//   * an endpoint id like "GET /v1/cards/{id}/pin" is always percent-encoded
//     before it becomes part of a path.

import type {
  AuditPage,
  Benchmark,
  BlastRadius,
  Capabilities,
  ChainCheck,
  GraphView,
  InventoryRecord,
  KillOutcome,
  Decision,
  Principal,
  Review,
  SafeKillState,
  ScanAudit,
  ScanJob,
  Summary,
  Verdict,
  VerdictDetail,
} from "./types";

export class ApiError extends Error {
  readonly status: number;

  constructor(status: number, message: string) {
    super(message);
    this.name = "ApiError";
    this.status = status;
  }

  /** The token is missing, wrong or expired: the user must sign in again. */
  get unauthorised(): boolean {
    return this.status === 401;
  }
}

type Fetch = typeof fetch;

export class ApiClient {
  private readonly token: string;
  private readonly fetchImpl: Fetch;

  constructor(token: string, fetchImpl: Fetch = (...args) => fetch(...args)) {
    this.token = token;
    this.fetchImpl = fetchImpl;
  }

  private async request<T>(method: "GET" | "POST", path: string, body?: unknown): Promise<T> {
    const headers: Record<string, string> = { Authorization: `Bearer ${this.token}` };
    const init: RequestInit = { method, headers, cache: "no-store", credentials: "omit" };
    if (body !== undefined) {
      headers["Content-Type"] = "application/json";
      init.body = JSON.stringify(body);
    }
    const res = await this.fetchImpl(path, init);
    if (!res.ok) {
      let detail = res.statusText;
      try {
        const data: unknown = await res.json();
        if (data && typeof data === "object" && "detail" in data) {
          detail = String((data as { detail: unknown }).detail);
        }
      } catch {
        // Non-JSON error body: keep the status text.
      }
      throw new ApiError(res.status, detail);
    }
    return (await res.json()) as T;
  }

  whoami(): Promise<Principal> {
    return this.request("GET", "/v1/whoami");
  }

  summary(): Promise<Summary> {
    return this.request("GET", "/v1/summary");
  }

  inventory(): Promise<InventoryRecord[]> {
    return this.request("GET", "/v1/inventory");
  }

  verdicts(): Promise<Verdict[]> {
    return this.request("GET", "/v1/verdicts");
  }

  verdict(endpointId: string): Promise<VerdictDetail> {
    return this.request("GET", `/v1/verdicts/${encodeURIComponent(endpointId)}`);
  }

  blastRadius(endpointId: string): Promise<BlastRadius> {
    return this.request("GET", `/v1/impact/${encodeURIComponent(endpointId)}`);
  }

  benchmark(): Promise<Benchmark> {
    return this.request("GET", "/v1/benchmark");
  }

  safekill(): Promise<SafeKillState> {
    return this.request("GET", "/v1/safekill");
  }

  startShadow(endpointId: string): Promise<KillOutcome> {
    return this.request("POST", "/v1/safekill/shadow", { endpoint_id: endpointId });
  }

  decide(
    endpointId: string,
    approve: boolean,
    acceptUnidentified: boolean,
    note: string,
  ): Promise<KillOutcome> {
    // No approver field: the server takes the approver's name from the token,
    // and rejects any request body that tries to supply one.
    return this.request("POST", "/v1/safekill/decision", {
      endpoint_id: endpointId,
      approve,
      accept_unidentified: acceptUnidentified,
      note,
    });
  }

  audit(endpointId?: string, limit = 200): Promise<AuditPage> {
    const q = new URLSearchParams({ limit: String(limit) });
    if (endpointId) q.set("endpoint", endpointId);
    return this.request("GET", `/v1/audit?${q.toString()}`);
  }

  verifyAudit(): Promise<ChainCheck> {
    return this.request("GET", "/v1/audit/verify");
  }

  demoGraph(): Promise<GraphView> {
    return this.request("GET", "/v1/demo/graph");
  }

  rescan(): Promise<Summary> {
    return this.request("POST", "/v1/demo/rescan");
  }

  // -- scans a person starts -----------------------------------------------

  capabilities(): Promise<Capabilities> {
    return this.request("GET", "/v1/capabilities");
  }

  scans(): Promise<ScanJob[]> {
    return this.request("GET", "/v1/scans");
  }

  scan(id: string): Promise<ScanJob> {
    return this.request("GET", `/v1/scans/${encodeURIComponent(id)}`);
  }

  scanAudit(id: string): Promise<ScanAudit> {
    return this.request("GET", `/v1/scans/${encodeURIComponent(id)}/audit`);
  }

  review(
    id: string,
    endpointId: string,
    decision: Decision,
    note = "",
  ): Promise<{ reviews: Record<string, Review> }> {
    // As with Safe Kill decisions: no reviewer field. The server records the
    // token's principal.
    return this.request("POST", `/v1/scans/${encodeURIComponent(id)}/review`, {
      endpoint_id: endpointId,
      decision,
      note,
    });
  }

  scanGithub(url: string): Promise<ScanJob> {
    return this.request("POST", "/v1/scans/github", { url });
  }

  /**
   * Upload a project folder. XMLHttpRequest rather than fetch, because fetch
   * cannot report upload progress and a large folder takes long enough that a
   * progress bar matters. The token still travels only in the header.
   */
  uploadFolder(
    files: { file: Blob; path: string }[],
    onProgress?: (fraction: number) => void,
  ): Promise<ScanJob> {
    const form = new FormData();
    for (const f of files) form.append("files", f.file, f.path);
    return new Promise((resolve, reject) => {
      const xhr = new XMLHttpRequest();
      xhr.open("POST", "/v1/scans/upload");
      xhr.setRequestHeader("Authorization", `Bearer ${this.token}`);
      xhr.withCredentials = false;
      xhr.upload.onprogress = (e) => {
        if (e.lengthComputable && onProgress) onProgress(e.loaded / e.total);
      };
      xhr.onerror = () => reject(new ApiError(0, "the upload could not reach API Exorcist"));
      xhr.onload = () => {
        let data: unknown = null;
        try {
          data = JSON.parse(xhr.responseText);
        } catch {
          // Non-JSON body: fall through with the status text.
        }
        if (xhr.status >= 200 && xhr.status < 300) {
          resolve(data as ScanJob);
          return;
        }
        const detail =
          data && typeof data === "object" && "detail" in data
            ? String((data as { detail: unknown }).detail)
            : xhr.statusText || `HTTP ${xhr.status}`;
        reject(new ApiError(xhr.status, detail));
      };
      xhr.send(form);
    });
  }
}

// Session storage, not local storage: the token is gone when the tab closes,
// and it is never written anywhere that outlives the browsing session.
const KEY = "apix.token";

export const session = {
  load(): string | null {
    try {
      return sessionStorage.getItem(KEY);
    } catch {
      return null;
    }
  },
  save(token: string): void {
    try {
      sessionStorage.setItem(KEY, token);
    } catch {
      // Storage unavailable (private mode): the session lasts until reload.
    }
  },
  clear(): void {
    try {
      sessionStorage.removeItem(KEY);
    } catch {
      // Nothing to clear.
    }
  },
};
