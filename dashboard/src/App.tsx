import { useCallback, useEffect, useMemo, useState } from "react";
import { ApiClient, session } from "./api";
import { SessionContext } from "./common";
import type { Principal } from "./types";
import { Audit } from "./views/Audit";
import { Benchmark } from "./views/Benchmark";
import { Endpoints } from "./views/Endpoints";
import { Login } from "./views/Login";
import { Overview } from "./views/Overview";
import { SafeKill } from "./views/SafeKill";

const VIEWS = {
  overview: { title: "Overview", render: () => <Overview /> },
  endpoints: { title: "Endpoints", render: () => <Endpoints /> },
  safekill: { title: "Safe Kill", render: () => <SafeKill /> },
  audit: { title: "Audit log", render: () => <Audit /> },
  benchmark: { title: "Benchmark", render: () => <Benchmark /> },
} as const;

type ViewKey = keyof typeof VIEWS;

function viewFromHash(): ViewKey {
  const h = window.location.hash.replace(/^#\/?/, "");
  return h in VIEWS ? (h as ViewKey) : "overview";
}

export function App() {
  const [token, setToken] = useState<string | null>(() => session.load());
  const [principal, setPrincipal] = useState<Principal | null>(null);
  const [checked, setChecked] = useState(false);
  const [view, setView] = useState<ViewKey>(viewFromHash);

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
    const onHash = () => setView(viewFromHash());
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

  return (
    <SessionContext.Provider value={{ api, principal, signOut }}>
      <header className="topbar">
        <span className="brand">API Exorcist</span>
        <nav aria-label="Sections">
          {(Object.keys(VIEWS) as ViewKey[]).map((k) => (
            <a key={k} href={`#${k}`} aria-current={k === view ? "page" : undefined}>
              {VIEWS[k].title}
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
      <div className="simulated" role="note">
        Simulated estate behind a simulated gateway. Nothing real is touched.
      </div>
      <main className="content">
        <h1>{VIEWS[view].title}</h1>
        {VIEWS[view].render()}
      </main>
    </SessionContext.Provider>
  );
}
