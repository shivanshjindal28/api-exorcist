import { createContext, useCallback, useContext, useEffect, useState } from "react";
import type { ReactNode } from "react";
import { ApiError } from "./api";
import type { ApiClient } from "./api";
import type { Principal } from "./types";

interface Session {
  api: ApiClient;
  principal: Principal;
  /** Called on any 401: the token is no longer valid, so sign out. */
  signOut: () => void;
}

export const SessionContext = createContext<Session | null>(null);

export function useSession(): Session {
  const s = useContext(SessionContext);
  if (!s) throw new Error("useSession outside a signed-in session");
  return s;
}

export function canApprove(p: Principal): boolean {
  return p.role === "approver";
}

interface Loaded<T> {
  data: T | null;
  error: string | null;
  loading: boolean;
  reload: () => void;
}

/** Fetch on mount and on `reload()`. A 401 signs the user out. */
export function useLoad<T>(fetcher: () => Promise<T>, deps: unknown[] = []): Loaded<T> {
  const { signOut } = useSession();
  const [data, setData] = useState<T | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);
  const [tick, setTick] = useState(0);

  useEffect(() => {
    let live = true;
    setLoading(true);
    fetcher()
      .then((d) => {
        if (!live) return;
        setData(d);
        setError(null);
      })
      .catch((e: unknown) => {
        if (!live) return;
        if (e instanceof ApiError && e.unauthorised) {
          signOut();
          return;
        }
        setError(e instanceof Error ? e.message : String(e));
      })
      .finally(() => {
        if (live) setLoading(false);
      });
    return () => {
      live = false;
    };
    // `fetcher` is a fresh closure every render; re-fetching on identity would
    // loop. Callers list what it depends on in `deps` instead.
  }, [tick, ...deps]);

  const reload = useCallback(() => setTick((t) => t + 1), []);
  return { data, error, loading, reload };
}

export function ErrorBox({ message }: { message: string }) {
  return (
    <div className="error" role="alert">
      {message}
    </div>
  );
}

export function Loading({ what }: { what: string }) {
  return (
    <p className="muted" aria-live="polite">
      Loading {what}...
    </p>
  );
}

export function LabelBadge({ label }: { label: string }) {
  return <span className={`badge badge-${label.toLowerCase()}`}>{label}</span>;
}

const STATE_TONE: Record<string, string> = {
  RETIRED: "good",
  REJECTED: "info",
  BLOCKED: "info",
  DENIED: "warn",
  ROLLED_BACK: "bad",
  AWAITING_APPROVAL: "pending",
  NOT_STARTED: "neutral",
};

export function StateBadge({ state }: { state: string }) {
  const tone = STATE_TONE[state] ?? "neutral";
  return <span className={`state state-${tone}`}>{state.replace(/_/g, " ").toLowerCase()}</span>;
}

export function pct(x: number, digits = 0): string {
  return `${(x * 100).toFixed(digits)}%`;
}

export function Card({ title, children }: { title: string; children: ReactNode }) {
  return (
    <section className="card">
      <h2>{title}</h2>
      {children}
    </section>
  );
}
