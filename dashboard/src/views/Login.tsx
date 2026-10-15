import { useState } from "react";
import type { FormEvent } from "react";
import { ApiClient, ApiError } from "../api";
import { IconGhost } from "../icons";
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
        <h1>
          <span className="sb-logo">
            <IconGhost size={18} />
          </span>
          API Exorcist
        </h1>
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
