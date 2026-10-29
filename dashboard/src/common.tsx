import { createContext, useCallback, useContext, useEffect, useState } from "react";
import type { ReactNode } from "react";
import { ApiError } from "./api";
import type { ApiClient } from "./api";
import { IconAlert, IconCheckCircle, IconInfo, IconX } from "./icons";
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
      <IconAlert size={17} />
      <span>{message}</span>
    </div>
  );
}

/** The shape of the page while it loads; the words are there for screen readers. */
export function Loading({ what }: { what: string }) {
  return (
    <div className="skeleton-block" aria-live="polite" aria-busy="true">
      <span className="visually-hidden">Loading {what}...</span>
      <div className="skeleton-row" aria-hidden="true">
        <span className="skeleton tile-shape" />
        <span className="skeleton tile-shape" />
        <span className="skeleton tile-shape" />
        <span className="skeleton tile-shape" />
      </div>
      <span className="skeleton panel" aria-hidden="true" />
      <span className="skeleton line" aria-hidden="true" />
      <span className="skeleton line short" aria-hidden="true" />
    </div>
  );
}

// ---------------------------------------------------------------------------
// Toasts: a short confirmation that an action happened, or why it did not.

type ToastTone = "ok" | "error" | "info";
interface Toast {
  id: number;
  tone: ToastTone;
  title: string;
  detail?: string;
}
type Notify = (title: string, opts?: { detail?: string; tone?: ToastTone }) => void;

export const ToastContext = createContext<Notify>(() => {});

/** Show a toast. Outside a provider (in tests of a single view) it does nothing. */
export function useToast(): Notify {
  return useContext(ToastContext);
}

export function ToastProvider({ children }: { children: ReactNode }) {
  const [toasts, setToasts] = useState<Toast[]>([]);
  const dismiss = useCallback((id: number) => setToasts((ts) => ts.filter((t) => t.id !== id)), []);
  const notify = useCallback<Notify>(
    (title, opts = {}) => {
      const id = Date.now() + Math.random();
      setToasts((ts) => [...ts.slice(-3), { id, title, detail: opts.detail, tone: opts.tone ?? "ok" }]);
      window.setTimeout(() => dismiss(id), opts.tone === "error" ? 8000 : 4500);
    },
    [dismiss],
  );
  return (
    <ToastContext.Provider value={notify}>
      {children}
      <div className="toasts" role="status" aria-live="polite">
        {toasts.map((t) => (
          <div key={t.id} className={`toast toast-${t.tone}`}>
            {t.tone === "error" ? <IconAlert /> : t.tone === "info" ? <IconInfo /> : <IconCheckCircle />}
            <div className="toast-text">
              <strong>{t.title}</strong>
              {t.detail && <span>{t.detail}</span>}
            </div>
            <button className="icon-btn" aria-label="Dismiss" onClick={() => dismiss(t.id)}>
              <IconX size={15} />
            </button>
          </div>
        ))}
      </div>
    </ToastContext.Provider>
  );
}

export function LabelBadge({ label }: { label: string }) {
  const word = label.charAt(0) + label.slice(1).toLowerCase();
  return <span className={`badge badge-${label.toLowerCase()}`}>{word}</span>;
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

export function Card({
  title,
  children,
  actions,
  flush = false,
}: {
  title: string;
  children: ReactNode;
  actions?: ReactNode;
  /** Tables run edge to edge. */
  flush?: boolean;
}) {
  return (
    <section className={flush ? "card card-flush" : "card"}>
      {actions ? (
        <div className="card-head">
          <h2>{title}</h2>
          {actions}
        </div>
      ) : (
        <h2>{title}</h2>
      )}
      {children}
    </section>
  );
}

// ---------------------------------------------------------------------------
// Page furniture shared by every view.

export interface Crumb {
  label: string;
  href?: string;
}

/** The header of a page: where you are, what it is, what you can do here. */
export function PageHead({
  title,
  crumbs = [],
  sub,
  actions,
  badge,
  tabs,
}: {
  title: ReactNode;
  crumbs?: Crumb[];
  sub?: ReactNode;
  actions?: ReactNode;
  badge?: ReactNode;
  /** A page's own navigation, drawn on the header's bottom edge. */
  tabs?: ReactNode;
}) {
  return (
    <header className={tabs ? "pagehead has-tabs" : "pagehead"}>
      <div className="pagehead-inner">
      {crumbs.length > 0 && (
        <nav className="crumbs" aria-label="Breadcrumb">
          {crumbs.map((c, i) => (
            <span key={`${c.label}-${i}`}>
              {i > 0 && <span className="sep"> / </span>}
              {c.href ? <a href={c.href}>{c.label}</a> : c.label}
            </span>
          ))}
        </nav>
      )}
      <div className="pagehead-row">
        <h1>{title}</h1>
        {badge}
        {actions && <div className="buttons">{actions}</div>}
      </div>
      {sub && <div className="sub">{sub}</div>}
      {tabs}
      </div>
    </header>
  );
}

export function Page({
  head,
  children,
}: {
  head: ReactNode;
  children: ReactNode;
}) {
  return (
    <>
      {head}
      <div className="content">{children}</div>
    </>
  );
}

export function Empty({
  icon,
  title,
  children,
  action,
}: {
  icon?: ReactNode;
  title: string;
  children?: ReactNode;
  action?: ReactNode;
}) {
  return (
    <div className="empty">
      {icon && <div className="empty-icon">{icon}</div>}
      <h2>{title}</h2>
      {children && <p>{children}</p>}
      {action}
    </div>
  );
}

export function MethodPath({ method, path }: { method: string; path: string }) {
  return (
    <code>
      <span className={`method m-${method}`}>{method}</span> {path}
    </code>
  );
}

export function LifecycleBadge({ label }: { label: string }) {
  return <span className={`lc lc-${label}`}>{label.toLowerCase()}</span>;
}

export function LevelBadge({ level, category }: { level: string; category: string }) {
  return (
    <span className={`level level-${level}`} title={`${level} sensitivity`}>
      {category}
    </span>
  );
}

/** Priority as a severity: the word says how urgent, the number is the score. */
export function priorityLevel(v: number): "critical" | "high" | "medium" | "low" | "none" {
  return v >= 8 ? "critical" : v >= 5 ? "high" : v >= 3 ? "medium" : v >= 1 ? "low" : "none";
}

export function Priority({ value }: { value: number | undefined }) {
  const v = value ?? 0;
  const level = priorityLevel(v);
  const word = level === "none" ? "None" : level.charAt(0).toUpperCase() + level.slice(1);
  return (
    <span className={`prio prio-${level}`} title="Priority: evidence against the endpoint, weighted by what it handles">
      {word} <span className="prio-score">{v}</span>
    </span>
  );
}

/** A small line of daily request counts. */
export function Sparkline({ points, width = 120, height = 28 }: { points: number[]; width?: number; height?: number }) {
  if (points.length < 2) return <span className="muted small">{points[0] ?? 0}</span>;
  const max = Math.max(...points, 1);
  const step = width / (points.length - 1);
  const xy = points.map((p, i) => [i * step, height - 2 - (p / max) * (height - 4)] as const);
  const line = xy.map(([x, y], i) => `${i ? "L" : "M"}${x.toFixed(1)},${y.toFixed(1)}`).join(" ");
  const area = `${line} L${width},${height} L0,${height} Z`;
  return (
    <svg className="spark" width={width} height={height} viewBox={`0 0 ${width} ${height}`} aria-hidden="true">
      <path className="spark-area" d={area} />
      <path d={line} />
    </svg>
  );
}

/** A button that opens a short list of actions. */
export function Menu({
  label,
  icon,
  items,
  header,
  buttonClass = "secondary",
}: {
  label: string;
  icon?: ReactNode;
  items: { label: string; hint?: string; onSelect: () => void; disabled?: boolean }[];
  header?: ReactNode;
  buttonClass?: string;
}) {
  const [open, setOpen] = useState(false);
  useEffect(() => {
    if (!open) return;
    const close = (e: KeyboardEvent | MouseEvent) => {
      if (e instanceof KeyboardEvent && e.key !== "Escape") return;
      setOpen(false);
    };
    const t = window.setTimeout(() => window.addEventListener("click", close), 0);
    window.addEventListener("keydown", close);
    return () => {
      window.clearTimeout(t);
      window.removeEventListener("click", close);
      window.removeEventListener("keydown", close);
    };
  }, [open]);
  return (
    <div className="menu">
      <button className={buttonClass} aria-haspopup="menu" aria-expanded={open} onClick={() => setOpen((o) => !o)}>
        {icon}
        {label}
        <span aria-hidden="true" className="muted">&#9662;</span>
      </button>
      {open && (
        <ul className="menu-list" role="menu">
          {header && (
            <li role="none">
              {header}
              <div className="menu-sep" />
            </li>
          )}
          {items.map((it) => (
            <li key={it.label} role="none">
              <button
                role="menuitem"
                disabled={it.disabled}
                onClick={() => {
                  setOpen(false);
                  it.onSelect();
                }}
              >
                <span className="menu-text">
                  {it.label}
                  {it.hint && <small>{it.hint}</small>}
                </span>
              </button>
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}
