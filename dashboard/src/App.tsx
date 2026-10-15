import { useCallback, useEffect, useMemo, useState } from "react";
import type { ReactNode } from "react";
import { ApiClient, session } from "./api";
import { Menu, SessionContext } from "./common";
import type { Principal } from "./types";
import { Dashboard } from "./views/Dashboard";
import { Login } from "./views/Login";
import { NewScan } from "./views/NewScan";
import { ExecutiveReport } from "./views/Report";
import { ScanResults } from "./views/ScanResults";
import { ScanView } from "./views/scan/ScanView";

interface View {
  title: string;
  render: (param: string | null) => ReactNode;
}

const VIEWS: Record<string, View> = {
  dashboard: { title: "Dashboard", render: () => <Dashboard /> },
  results: {
    title: "Projects",
    // A scan id (or "demo") opens that scan's views; without one, the list.
    render: (param) => (param ? <ScanView key={param.split("/")[0]} param={param} /> : <ScanResults />),
  },
  scan: { title: "New scan", render: () => <NewScan /> },
  report: { title: "Report", render: (param) => <ExecutiveReport id={param ?? ""} /> },
};

const HOME = "dashboard";

/** Where the demo bank's views used to live, before every scan had them. */
const LEGACY_DEMO = new Set(["overview", "endpoints", "safekill", "audit", "benchmark"]);

export function route(hash: string): { view: string; param: string | null } {
  const [view, ...rest] = hash.replace(/^#\/?/, "").split("/");
  if (view && view in VIEWS) return { view, param: rest.length ? rest.join("/") : null };
  if (view && LEGACY_DEMO.has(view)) return { view: "results", param: `demo/${view}` };
  return { view: HOME, param: null };
}

/**
 * A token handed over in the URL fragment by `apix serve` (#signin=apx_...).
 *
 * A fragment is never sent to a server and never appears in a Referer header.
 * It is read once and erased from the address bar and the history entry at
 * once, so it cannot be bookmarked or shared by accident.
 */
export function takeSigninToken(): string | null {
  const m = /^#signin=(apx_[A-Za-z0-9_-]+)$/.exec(window.location.hash);
  if (!m) return null;
  window.history.replaceState(null, "", `${window.location.pathname}#${HOME}`);
  return m[1] ?? null;
}

// The theme is a per-viewer convenience, so browser storage is enough; it is
// read defensively because storage can be unavailable.
type Theme = "light" | "dark";
const THEME_KEY = "apix.theme";

function storedTheme(): Theme | null {
  try {
    const t = localStorage.getItem(THEME_KEY);
    return t === "light" || t === "dark" ? t : null;
  } catch {
    return null;
  }
}

function systemTheme(): Theme {
  return window.matchMedia?.("(prefers-color-scheme: dark)").matches ? "dark" : "light";
}

function useTheme(): [Theme, () => void] {
  const [theme, setTheme] = useState<Theme>(() => storedTheme() ?? systemTheme());
  useEffect(() => {
    document.documentElement.dataset.theme = theme;
  }, [theme]);
  const toggle = useCallback(() => {
    setTheme((t) => {
      const next = t === "dark" ? "light" : "dark";
      try {
        localStorage.setItem(THEME_KEY, next);
      } catch {
        // Not remembered; it still applies for this visit.
      }
      return next;
    });
  }, []);
  return [theme, toggle];
}

const NAV: { href: string; label: string; match: (v: string, p: string | null) => boolean }[] = [
  { href: "#dashboard", label: "Overview", match: (v) => v === "dashboard" },
  {
    href: "#results",
    label: "Projects",
    match: (v, p) => (v === "results" && !(p ?? "").startsWith("demo")) || v === "report" || v === "scan",
  },
  { href: "#results/demo/overview", label: "Demo bank", match: (v, p) => v === "results" && (p ?? "").startsWith("demo") },
];

export function App() {
  const [token, setToken] = useState<string | null>(() => {
    const handed = takeSigninToken();
    if (handed) session.save(handed);
    return handed ?? session.load();
  });
  const [principal, setPrincipal] = useState<Principal | null>(null);
  const [checked, setChecked] = useState(false);
  const [where, setWhere] = useState(() => route(window.location.hash));
  const [theme, toggleTheme] = useTheme();

  const api = useMemo(() => (token ? new ApiClient(token) : null), [token]);

  const signOut = useCallback(() => {
    session.clear();
    setToken(null);
    setPrincipal(null);
  }, []);

  // A token restored from this tab's session is re-checked, never trusted.
  useEffect(() => {
    if (!api || principal) {
      setChecked(true);
      return;
    }
    api
      .whoami()
      .then(setPrincipal)
      .catch(signOut)
      .finally(() => setChecked(true));
  }, [api, principal, signOut]);

  useEffect(() => {
    const onHash = () => {
      setWhere(route(window.location.hash));
      window.scrollTo(0, 0);
    };
    window.addEventListener("hashchange", onHash);
    return () => window.removeEventListener("hashchange", onHash);
  }, []);

  const view = VIEWS[where.view] ?? VIEWS[HOME]!;
  useEffect(() => {
    document.title = `${view.title} - API Exorcist`;
  }, [view]);

  if (!checked) return null;
  if (!api || !principal) {
    return (
      <Login
        onSignIn={(t, who) => {
          session.save(t);
          setToken(t);
          setPrincipal(who);
        }}
      />
    );
  }

  return (
    <SessionContext.Provider value={{ api, principal, signOut }}>
      <div className="shell">
        <header className="topnav">
          <div className="topnav-inner">
          <a className="wordmark" href="#dashboard">
            API Exorcist
          </a>
          <nav aria-label="Sections">
            {NAV.map((n) => (
              <a key={n.href} href={n.href} aria-current={n.match(where.view, where.param) ? "page" : undefined}>
                {n.label}
              </a>
            ))}
          </nav>
          <div className="topnav-right">
            {where.view !== "scan" && (
              <a className="btn small" href="#scan">
                New scan
              </a>
            )}
            <Menu
              label={principal.name}
              buttonClass="user-btn"
              header={
                <div className="menu-who">
                  <strong>{principal.name}</strong>
                  {principal.role === "approver" ? "Approver: can scan and decide" : "Viewer: read only"}
                </div>
              }
              items={[
                { label: theme === "dark" ? "Light theme" : "Dark theme", onSelect: toggleTheme },
                { label: "Sign out", onSelect: signOut },
              ]}
            />
          </div>
          </div>
        </header>
        <main className="main">{view.render(where.param)}</main>
      </div>
    </SessionContext.Provider>
  );
}
