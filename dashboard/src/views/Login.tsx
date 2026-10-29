import { useState } from "react";
import type { FormEvent } from "react";
import { ApiClient, ApiError } from "../api";
import { IconGhost, IconGraph, IconShield } from "../icons";
import type { Principal } from "../types";

interface Props {
  onSignIn: (token: string, principal: Principal) => void;
  makeClient?: (token: string) => ApiClient;
}

export function Login({ onSignIn, makeClient = (t) => new ApiClient(t) }: Props) {
  const [token, setToken] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  async function submit(e: FormEvent) {
    e.preventDefault();
    const t = token.trim();
    if (!t) return;
    setBusy(true);
    setError(null);
    try {
      const who = await makeClient(t).whoami();
      onSignIn(t, who);
    } catch (err) {
      setError(
        err instanceof ApiError && err.unauthorised
          ? "That token was not recognised."
          : "Could not reach the API. Is `apix serve` running?",
      );
    } finally {
      setBusy(false);
    }
  }

  return (
    <main className="login">
      <section className="login-brand" aria-label="About API Exorcist">
        <div className="login-brand-mark">
          <img src="/logo.png" alt="" width={56} height={56} />
          <span>API Exorcist</span>
        </div>
        <h2 className="login-pitch">Find the APIs your bank forgot. Retire them without an outage.</h2>
        <ul className="login-points">
          <li>
            <IconGhost size={20} />
            <span>
              <strong>Six sources, correlated.</strong> What the gateway and the specification
              miss, the code, traffic and DNS still show.
            </span>
          </li>
          <li>
            <IconGraph size={20} />
            <span>
              <strong>Every verdict explained.</strong> Signed reasons, and what could not be
              checked, for every endpoint.
            </span>
          </li>
          <li>
            <IconShield size={20} />
            <span>
              <strong>Safe Kill.</strong> A shadow window, a named approval, a canary and
              automatic rollback, all in a hash-chained audit log.
            </span>
          </li>
        </ul>
        <p className="login-foot">B.Tech CSE (Cyber Security) capstone · MPSTME, NMIMS</p>
      </section>
      <form className="login-card" onSubmit={submit}>
        <img className="login-logo" src="/logo.png" alt="API Exorcist logo" width={64} height={64} />
        <h1>Sign in to API Exorcist</h1>
        <p className="muted">
          Started from VS Code (F5) or with <code>apix serve</code>, API Exorcist opens this
          page already signed in. If you see this instead, paste the token printed in the
          terminal where it is running.
        </p>
        <label htmlFor="token">Token</label>
        <input
          id="token"
          type="password"
          autoComplete="off"
          spellCheck={false}
          value={token}
          onChange={(e) => setToken(e.target.value)}
          placeholder="apx_..."
        />
        {error && (
          <p className="error" role="alert">
            {error}
          </p>
        )}
        <button type="submit" disabled={busy || !token.trim()}>
          {busy ? "Checking..." : "Sign in"}
        </button>
        <p className="muted small">
          The token is kept for this browser tab only and is never put in a URL.
        </p>
      </form>
    </main>
  );
}
