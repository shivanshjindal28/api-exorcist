import { useCallback, useEffect, useMemo, useState } from "react";
import type { ReactNode } from "react";
import { ApiClient, session } from "./api";
import { SessionContext } from "./common";
import type { Principal } from "./types";
import { Audit } from "./views/Audit";
import { Benchmark } from "./views/Benchmark";
import { Endpoints } from "./views/Endpoints";
import { Login } from "./views/Login";
import { NewScan } from "./views/NewScan";
import { Overview } from "./views/Overview";
import { SafeKill } from "./views/SafeKill";
import { ScanReport } from "./views/ScanReport";
import { ScanResults } from "./views/ScanResults";

interface View {
  title: string;
  group: "scan" | "demo";
  render: (param: string | null) => ReactNode;
}

const VIEWS: Record<string, View> = {
  scan: { title: "New scan", group: "scan", render: () => <NewScan /> },
  results: {
    title: "Scan results",
    group: "scan",
    render: (id) => (id ? <ScanReport key={id} id={id} /> : <ScanResults />),
  },
  overview: { title: "Overview", group: "demo", render: () => <Overview /> },
  endpoints: { title: "Endpoints", group: "demo", render: () => <Endpoints /> },
  safekill: { title: "Safe Kill", group: "demo", render: () => <SafeKill /> },
  audit: { title: "Audit log", group: "demo", render: () => <Audit /> },
  benchmark: { title: "Benchmark", group: "demo", render: () => <Benchmark /> },
};

const HOME = "scan";

export function route(hash: string): { view: string; param: string | null } {
  const [view, ...rest] = hash.replace(/^#\/?/, "").split("/");
  if (view && view in VIEWS) return { view, param: rest.length ? rest.join("/") : null };
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
  const link = (k: string) => (
    <a key={k} href={`#${k}`} aria-current={k === where.view ? "page" : undefined}>
      {VIEWS[k]!.title}
    </a>
  );
  const keys = Object.keys(VIEWS);

  return (
    <SessionContext.Provider value={{ api, principal, signOut }}>
      <header className="topbar">
        <span className="brand">API Exorcist</span>
        <nav aria-label="Sections">
          {keys.filter((k) => VIEWS[k]!.group === "scan").map(link)}
          <span className="nav-group" aria-hidden="true">
            Demo bank
          </span>
          {keys.filter((k) => VIEWS[k]!.group === "demo").map(link)}
        </nav>
        <span className="who">
          {principal.name} <span className="role">{principal.role}</span>
          <button className="link" onClick={signOut}>
            Sign out
          </button>
        </span>
      </header>
      {view.group === "demo" && (
        <div className="simulated" role="note">
          Demo bank: a simulated estate behind a simulated gateway, used to show the full
          classification and Safe Kill. Nothing real is touched.
        </div>
      )}
      <main className="content">
        <h1>{view.group === "demo" ? `Demo bank: ${view.title}` : view.title}</h1>
        {view.render(where.param)}
      </main>
    </SessionContext.Provider>
  );
}
