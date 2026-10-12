import { useCallback, useEffect, useMemo, useState } from "react";
import type { ReactNode } from "react";
import { ApiClient, session } from "./api";
import { SessionContext } from "./common";
import type { Principal } from "./types";
import { Login } from "./views/Login";
import { NewScan } from "./views/NewScan";
import { ScanResults } from "./views/ScanResults";
import { ScanView } from "./views/scan/ScanView";

interface View {
  title: string;
  render: (param: string | null) => ReactNode;
}

const VIEWS: Record<string, View> = {
  scan: { title: "New scan", render: () => <NewScan /> },
  results: {
    title: "Scan results",
    // A scan id (or "demo") opens that scan's five views; without one, the list.
    render: (param) => (param ? <ScanView key={param.split("/")[0]} param={param} /> : <ScanResults />),
  },
};

const HOME = "scan";

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

export function App() {
  const [token, setToken] = useState<string | null>(() => {
    const handed = takeSigninToken();
    if (handed) session.save(handed);
    return handed ?? session.load();
  });
  const [principal, setPrincipal] = useState<Principal | null>(null);
  const [checked, setChecked] = useState(false);
  const [where, setWhere] = useState(() => route(window.location.hash));

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
    const onHash = () => setWhere(route(window.location.hash));
    window.addEventListener("hashchange", onHash);
    return () => window.removeEventListener("hashchange", onHash);
  }, []);

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

  const view = VIEWS[where.view] ?? VIEWS[HOME]!;

  return (
    <SessionContext.Provider value={{ api, principal, signOut }}>
      <header className="topbar">
        <span className="brand">API Exorcist</span>
        <nav aria-label="Sections">
          {Object.keys(VIEWS).map((k) => (
            <a key={k} href={`#${k}`} aria-current={k === where.view ? "page" : undefined}>
              {VIEWS[k]!.title}
            </a>
          ))}
        </nav>
        <span className="who">
          {principal.name} <span className="role">{principal.role}</span>
          <button className="link" onClick={signOut}>
            Sign out
          </button>
        </span>
      </header>
      <main className="content">
        <h1>{view.title}</h1>
        {view.render(where.param)}
      </main>
    </SessionContext.Provider>
  );
}
