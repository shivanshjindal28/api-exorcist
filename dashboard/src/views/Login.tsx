import { useState } from "react";
import type { FormEvent } from "react";
import { ApiClient, ApiError } from "../api";
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
      <form className="card login-card" onSubmit={submit}>
        <h1>API Exorcist</h1>
        <p className="muted">
          Sign in with an API token. <code>apix serve</code> prints a one-time token when none
          are configured; <code>apix token NAME</code> mints a named one.
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
