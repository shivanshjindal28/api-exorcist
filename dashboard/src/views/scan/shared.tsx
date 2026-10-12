import { useState } from "react";
import { ApiError } from "../../api";
import { ErrorBox, canApprove, useSession } from "../../common";
import type { Decision, Review, ScanCheck, ScanEndpoint, ScanJob } from "../../types";

export const CHECK_TEXT: Record<ScanCheck["status"], string> = {
  ok: "worked",
  partial: "partly",
  unavailable: "not available",
  failed: "failed",
};

export const DECISIONS: { key: Decision; label: string }[] = [
  { key: "keep", label: "Keep" },
  { key: "document", label: "Needs documentation" },
  { key: "assign-owner", label: "Needs an owner" },
  { key: "investigate", label: "Investigate for removal" },
];

/**
 * The six sources the engine knows, spelled exactly as the server sends them
 * (apix.connectors.base.Source). A project scan consults three. The first
 * version of these views used lower case, its tests used the same wrong
 * spelling, and every source showed as "not consulted" on a real report.
 */
export const ALL_SOURCES = ["GATEWAY", "OPENAPI", "TRAFFIC", "CODE", "DNS", "CICD"];

const SOURCE_NAME: Record<string, string> = {
  GATEWAY: "Gateway",
  OPENAPI: "API spec",
  TRAFFIC: "Traffic",
  CODE: "Code",
  DNS: "DNS",
  CICD: "CI/CD",
};

export function sourceName(s: string): string {
  return SOURCE_NAME[s] ?? s;
}

export function consultedSources(job: ScanJob): string[] {
  return job.report?.sources?.consulted ?? ["CICD", "CODE", "OPENAPI"];
}

export function ago(days: number | null): string {
  if (days == null) return "unknown";
  if (days < 1) return "today";
  if (days < 60) return `${days} days ago`;
  if (days < 730) return `${Math.round(days / 30)} months ago`;
  return `${(days / 365).toFixed(1)} years ago`;
}

export function when(iso: string | null): string {
  if (!iso) return "";
  const d = new Date(iso);
  return Number.isNaN(d.getTime()) ? iso : d.toLocaleString();
}

/** Which of the six sources saw an endpoint, which did not, which were never asked. */
export function SourceChips({ e, consulted }: { e: ScanEndpoint; consulted: string[] }) {
  return (
    <ul className="chips" aria-label="Sources">
      {ALL_SOURCES.map((s) => {
        const asked = consulted.includes(s);
        const saw = e.seen_by.includes(s);
        const state = !asked ? "not consulted" : saw ? "saw it" : "did not see it";
        return (
          <li
            key={s}
            className={`chip ${!asked ? "unasked" : saw ? "on" : "off"}`}
            title={`${sourceName(s)}: ${state}`}
          >
            {sourceName(s)}
            <span className="visually-hidden">: {state}</span>
          </li>
        );
      })}
    </ul>
  );
}

export function ReviewBadge({ review }: { review: Review | undefined }) {
  if (!review) return <span className="muted small">not reviewed</span>;
  return <span className={`review review-${review.decision}`}>{review.label}</span>;
}

/** Record a decision about an endpoint. The reviewer is the signed-in person. */
export function ReviewControls({
  jobId,
  e,
  review,
  onReviewed,
}: {
  jobId: string;
  e: ScanEndpoint;
  review: Review | undefined;
  onReviewed: (reviews: Record<string, Review>) => void;
}) {
  const { api, principal } = useSession();
  const [note, setNote] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  if (!canApprove(principal)) {
    return (
      <p className="muted small">
        Decision: <ReviewBadge review={review} />. Recording one needs an approver.
      </p>
    );
  }

  async function decide(decision: Decision) {
    setBusy(true);
    setError(null);
    try {
      const r = await api.review(jobId, e.id, decision, note.trim());
      onReviewed(r.reviews);
      setNote("");
    } catch (err) {
      setError(err instanceof ApiError ? err.message : String(err));
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="review-controls">
      <p className="small">
        Decision: <ReviewBadge review={review} />
        {review && (
          <span className="muted">
            {" "}
            by {review.by}, {when(review.at)}
            {review.note ? `: "${review.note}"` : ""}
          </span>
        )}
      </p>
      <div className="buttons">
        {DECISIONS.map((d) => (
          <button
            key={d.key}
            className={`small ${review?.decision === d.key ? "" : "secondary"}`}
            disabled={busy}
            aria-pressed={review?.decision === d.key}
            aria-label={`${d.label}: ${e.id}`}
            onClick={() => decide(d.key)}
          >
            {d.label}
          </button>
        ))}
      </div>
      <input
        type="search"
        className="review-note"
        placeholder="Note for the audit log (optional)"
        aria-label={`Note for ${e.id}`}
        maxLength={1000}
        value={note}
        onChange={(ev) => setNote(ev.target.value)}
      />
      {error && <ErrorBox message={error} />}
    </div>
  );
}
