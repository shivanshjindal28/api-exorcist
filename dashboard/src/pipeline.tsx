/* Safe Kill drawn as a pipeline: five stages in a row, the ones passed in green,
 * the current one pulsing, and the one that stopped a removal marked where it
 * stopped, the way a CI run shows its jobs. */

import { IconCheck, IconX } from "./icons";
import type { KillState, Observation } from "./types";

const STAGES = ["Removal gate", "Shadow", "Named approval", "Canary", "Retired"];

/** Which of the five stages a controller state belongs to. */
export function stageOf(state: KillState | string): number {
  switch (state) {
    case "NOMINATED":
    case "BLAST_RADIUS":
    case "BLOCKED":
      return 0;
    case "SHADOW":
    case "REJECTED":
      return 1;
    case "AWAITING_APPROVAL":
    case "DENIED":
      return 2;
    case "CANARY_5":
    case "CANARY_25":
    case "CANARY_100":
    case "ROLLED_BACK":
      return 3;
    case "RETIRED":
      return 4;
    default:
      return 0;
  }
}

const STOPS = new Set(["BLOCKED", "REJECTED", "DENIED", "ROLLED_BACK"]);

export function Pipeline({
  state,
  notes = {},
}: {
  state: KillState | string;
  /** A short line under a stage, by index: "90 days", "by ann". */
  notes?: Partial<Record<number, string>>;
}) {
  const at = stageOf(state);
  const stopped = STOPS.has(state);
  const retired = state === "RETIRED";
  return (
    <ol className="pipeline" aria-label={`Safe Kill: ${state.replace(/_/g, " ").toLowerCase()}`}>
      {STAGES.map((name, i) => {
        const status =
          retired || i < at ? "done" : i === at ? (stopped ? "stopped" : "current") : "todo";
        return (
          <li key={name} className={`stage stage-${status}`}>
            <span className="stage-dot" aria-hidden="true">
              {status === "done" ? <IconCheck size={14} /> : status === "stopped" ? <IconX size={14} /> : i + 1}
            </span>
            <span className="stage-name">{name}</span>
            {notes[i] && <span className="stage-note">{notes[i]}</span>}
            <span className="visually-hidden">: {status === "todo" ? "not reached" : status}</span>
          </li>
        );
      })}
    </ol>
  );
}

/** The canary's three steps, filled as each one passes; red where it rolled back. */
export function CanaryMeter({ canary, rolledBack }: { canary: Observation[]; rolledBack: boolean }) {
  const steps = [0.05, 0.25, 1];
  return (
    <div className="canary-meter" aria-hidden="true">
      {steps.map((f, i) => {
        const reached = i < canary.length;
        const failed = rolledBack && i === canary.length - 1;
        return (
          <span key={f} className={`canary-step ${failed ? "is-failed" : reached ? "is-done" : ""}`}>
            <span className="canary-fill" />
            <span className="canary-label">{Math.round(f * 100)}%</span>
          </span>
        );
      })}
    </div>
  );
}
