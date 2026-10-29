import { useCallback, useEffect, useMemo, useState } from "react";
import type { ReactNode } from "react";
import { ApiClient, session } from "./api";
import { SessionContext, ToastProvider } from "./common";
import {
  IconBank,
  IconCollapse,
  IconExpand,
  IconLogOut,
  IconMoon,
  IconOverview,
  IconPlus,
  IconProjects,
  IconSun,
} from "./icons";
import type { Principal } from "./types";
import { Dashboard } from "./views/Dashboard";
import { Login } from "./views/Login";
import { NewScan } from "./views/NewScan";
import { ExecutiveReport } from "./views/Report";
import { ScanResults } from "./views/ScanResults";
import { ScanView } from "./views/scan/ScanView";
import { Splash, shouldShowSplash } from "./views/Splash";

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

const NAV: {
  href: string;
  label: string;
  icon: ReactNode;
  match: (v: string, p: string | null) => boolean;
}[] = [
  { href: "#dashboard", label: "Overview", icon: <IconOverview />, match: (v) => v === "dashboard" },
  {
    href: "#results",
    label: "Projects",
    icon: <IconProjects />,
    match: (v, p) => (v === "results" && !(p ?? "").startsWith("demo")) || v === "report" || v === "scan",
  },
  {
    href: "#results/demo/overview",
    label: "Demo bank",
    icon: <IconBank />,
    match: (v, p) => v === "results" && (p ?? "").startsWith("demo"),
  },
];

// Whether the sidebar is folded to icons: a per-viewer convenience, like the theme.
const COLLAPSE_KEY = "apix.sidebar";

function useCollapsed(): [boolean, () => void] {
  const [collapsed, setCollapsed] = useState(() => {
    try {
      return localStorage.getItem(COLLAPSE_KEY) === "collapsed";
    } catch {
      return false;
    }
  });
  const toggle = useCallback(() => {
    setCollapsed((c) => {
      try {
        localStorage.setItem(COLLAPSE_KEY, c ? "open" : "collapsed");
      } catch {
        // Not remembered; it still applies for this visit.
      }
      return !c;
    });
  }, []);
  return [collapsed, toggle];
}

function initials(name: string): string {
  const parts = name.trim().split(/[\s._-]+/).filter(Boolean);
  return ((parts[0]?.[0] ?? "?") + (parts[1]?.[0] ?? "")).toUpperCase();
}

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
  const [collapsed, toggleCollapsed] = useCollapsed();
  const [splash, setSplash] = useState(shouldShowSplash);
  const splashView = splash ? <Splash onClose={() => setSplash(false)} /> : null;

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
      <>
      {splashView}
      <Login
        onSignIn={(t, who) => {
          session.save(t);
          setToken(t);
          setPrincipal(who);
        }}
      />
      </>
    );
  }

  return (
    <SessionContext.Provider value={{ api, principal, signOut }}>
      {splashView}
      <ToastProvider>
        <div className={collapsed ? "shell is-collapsed" : "shell"}>
          <aside className="sidebar">
            <a className="wordmark" href="#dashboard" title="API Exorcist">
              <img src="/logo.png" alt="" width={40} height={40} />
              <span className="wordmark-text hide-collapsed">
                <span className="wordmark-name">API Exorcist</span>
                <span className="wordmark-tag">API inventory and safe retirement</span>
              </span>
            </a>
            {where.view !== "scan" && (
              <a className="btn new-scan" href="#scan" title="New scan">
                <IconPlus size={17} />
                <span className="hide-collapsed">New scan</span>
              </a>
            )}
            <div className="nav-label hide-collapsed">Workspace</div>
            <nav className="nav" aria-label="Sections">
              {NAV.map((n) => (
                <a
                  key={n.href}
                  href={n.href}
                  title={n.label}
                  aria-current={n.match(where.view, where.param) ? "page" : undefined}
                >
                  {n.icon}
                  <span className="hide-collapsed">{n.label}</span>
                </a>
              ))}
            </nav>
            <div className="sidebar-foot">
              <button className="side-btn" onClick={toggleTheme} title="Switch theme">
                {theme === "dark" ? <IconSun /> : <IconMoon />}
                <span className="side-label hide-collapsed">{theme === "dark" ? "Light theme" : "Dark theme"}</span>
              </button>
              <button className="side-btn collapse-btn" onClick={toggleCollapsed} title={collapsed ? "Expand sidebar" : "Collapse sidebar"}>
                {collapsed ? <IconExpand /> : <IconCollapse />}
                <span className="side-label hide-collapsed">Collapse</span>
              </button>
              <div className="user-card">
                <span className="avatar" aria-hidden="true">{initials(principal.name)}</span>
                <span className="user-meta hide-collapsed">
                  <strong>{principal.name}</strong>
                  <span>{principal.role === "approver" ? "Approver: can scan and decide" : "Viewer: read only"}</span>
                </span>
                <button className="icon-btn" onClick={signOut} aria-label="Sign out" title="Sign out">
                  <IconLogOut size={17} />
                </button>
              </div>
            </div>
          </aside>
          <main className="main">{view.render(where.param)}</main>
        </div>
      </ToastProvider>
    </SessionContext.Provider>
  );
}
