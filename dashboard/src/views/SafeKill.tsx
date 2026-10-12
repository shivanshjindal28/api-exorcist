import { useState } from "react";
import { ApiError } from "../api";
import {
  Card,
  ErrorBox,
  Loading,
  StateBadge,
  canApprove,
  pct,
  useLoad,
  useSession,
} from "../common";
import type { KillOutcome, Observation, PendingApproval } from "../types";

export function SafeKill() {
  const { api, principal } = useSession();
  const { data, error, loading, reload } = useLoad(() => api.safekill());
  const [busy, setBusy] = useState<string | null>(null);
  const [actionError, setActionError] = useState<string | null>(null);
  const approver = canApprove(principal);

  if (error) return <ErrorBox message={error} />;
  if (loading && !data) return <Loading what="Safe Kill state" />;
  if (!data) return null;

  async function act(endpointId: string, run: () => Promise<unknown>) {
    setBusy(endpointId);
    setActionError(null);
    try {
      await run();
      reload();
    } catch (e) {
      setActionError(e instanceof ApiError ? e.message : String(e));
    } finally {
      setBusy(null);
    }
  }

  const { policy } = data;
  return (
    <div className="stack">
      <Card title="How a removal is made safe">
        <p>
          Every candidate is <strong>shadowed for {policy.shadow_days} days</strong> first:
          nothing is refused, and every request that would have been is recorded with its
          caller. That window is derived, not chosen: it catches a caller who calls once a
          month with {pct(policy.confidence)} confidence. Only then can a named approver
          start the canary: 410 Gone to 5%, 25%, then 100% of requests for{" "}
          {policy.canary_days.join(" / ")} days, rolled back automatically on any breach.
        </p>
        {!approver && (
          <p className="muted">
            You are signed in as a viewer: you can see every decision but not make one.
          </p>
        )}
        {actionError && <ErrorBox message={actionError} />}
      </Card>

      <Card title={`Awaiting a decision (${data.pending.length})`}>
        {data.pending.length === 0 ? (
          <p className="muted">Nothing is waiting. Start a shadow window below.</p>
        ) : (
          data.pending.map((p) => (
            <PendingCard
              key={p.endpoint_id}
              pending={p}
              approver={approver}
              busy={busy === p.endpoint_id}
              onDecide={(approve, accept, note) =>
                act(p.endpoint_id, () => api.decide(p.endpoint_id, approve, accept, note))
              }
            />
          ))
        )}
      </Card>

      <Card title="Removal candidates">
        <div className="table-wrap">
          <table>
            <thead>
              <tr>
                <th>Endpoint</th>
                <th>Removal gate</th>
                <th>Status</th>
                <th aria-label="Actions" />
              </tr>
            </thead>
            <tbody>
              {data.candidates.map((c) => (
                <tr key={c.endpoint_id}>
                  <td>
                    <code>{c.endpoint_id}</code>
                  </td>
                  <td>{c.may_proceed ? "cleared" : <span className="muted">{c.blocked_by}</span>}</td>
                  <td>
                    <StateBadge state={c.status} />
                  </td>
                  <td>
                    {approver && c.may_proceed && c.status === "NOT_STARTED" && (
                      <button
                        className="small"
                        disabled={busy === c.endpoint_id}
                        aria-label={`Start shadow for ${c.endpoint_id}`}
                        onClick={() => act(c.endpoint_id, () => api.startShadow(c.endpoint_id))}
                      >
                        Start shadow
                      </button>
                    )}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </Card>

      {data.decided.length > 0 && (
        <Card title="Decided">
          {data.decided.map((o) => (
            <OutcomeView key={o.endpoint_id} outcome={o} />
          ))}
        </Card>
      )}
    </div>
  );
}

function PendingCard({
  pending: p,
  approver,
  busy,
  onDecide,
}: {
  pending: PendingApproval;
  approver: boolean;
  busy: boolean;
  onDecide: (approve: boolean, acceptUnidentified: boolean, note: string) => void;
}) {
  const [accept, setAccept] = useState(false);
  const [note, setNote] = useState("");
  const warned = p.warnings.length > 0;
  const shadow = p.outcome?.shadow ?? null;

  return (
    <article className="pending" aria-label={`Decision for ${p.endpoint_id}`}>
      <h3>
        <code>{p.endpoint_id}</code>
      </h3>
      <p className="muted small">classified ZOMBIE at {pct(p.confidence)} confidence</p>
      <ul className="reasons">
        {p.reasons.map((r) => (
          <li key={r}>{r}</li>
        ))}
      </ul>
      {shadow && <ShadowSummary obs={shadow} />}
      {warned && (
        <div className="warning" role="note">
          {p.warnings.map((w) => (
            <p key={w}>{w}</p>
          ))}
        </div>
      )}
      {approver && (
        <div className="decide">
          {warned && (
            <label className="check">
              <input type="checkbox" checked={accept} onChange={(e) => setAccept(e.target.checked)} />
              I accept that this traffic cannot be identified, and approve anyway
            </label>
          )}
          <label htmlFor={`note-${p.endpoint_id}`}>Note for the audit log</label>
          <textarea
            id={`note-${p.endpoint_id}`}
            maxLength={1000}
            value={note}
            onChange={(e) => setNote(e.target.value)}
          />
          <div className="buttons">
            <button
              disabled={busy || (warned && !accept)}
              aria-label={`Approve removal of ${p.endpoint_id}: start the canary`}
              onClick={() => onDecide(true, accept, note)}
            >
              Approve: start the canary
            </button>
            <button
              className="secondary"
              disabled={busy}
              aria-label={`Decline removal of ${p.endpoint_id}`}
              onClick={() => onDecide(false, false, note)}
            >
              Decline
            </button>
          </div>
          <p className="muted small">
            Your decision is recorded under the name bound to your token.
          </p>
        </div>
      )}
    </article>
  );
}

function ShadowSummary({ obs }: { obs: Observation }) {
  const named = Object.entries(obs.identified);
  return (
    <p className="shadow">
      Shadow, {obs.days} days: {obs.requests} request(s);{" "}
      {named.length === 0
        ? "no identified caller"
        : named.map(([c, n]) => `${c} (${n})`).join(", ")}
      ; {obs.unidentified} unidentified.
    </p>
  );
}

function refused(o: Observation): number {
  return Object.values(o.identified).reduce((a, b) => a + b, 0) + o.unidentified;
}

export function OutcomeView({ outcome: o }: { outcome: KillOutcome }) {
  return (
    <article className="outcome">
      <h3>
        <code>{o.endpoint_id}</code> <StateBadge state={o.state} />
      </h3>
      <ol className="path" aria-label="States passed through">
        {o.path.map((s, i) => (
          <li key={`${s}-${i}`}>{s.replace(/_/g, " ").toLowerCase()}</li>
        ))}
      </ol>
      <p>{o.reason}</p>
      <p className="muted small">
        {o.days} simulated days
        {o.approver ? `; decided by ${o.approver}` : ""}
        {o.breach_kind ? `; ${o.breach_kind} breach` : ""}
      </p>
      {o.canary.length > 0 && (
        <ul className="canary">
          {o.canary.map((c, i) => (
            <li key={i}>
              {pct(c.refuse_fraction)}: {refused(c)} refused of {c.requests}
            </li>
          ))}
        </ul>
      )}
    </article>
  );
}
