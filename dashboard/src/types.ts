// Response shapes of the API Exorcist REST API, taken from what the server
// actually returns (src/apix/api/app.py), not from the design document.

export type Label = "ACTIVE" | "DEPRECATED" | "ORPHANED" | "ZOMBIE" | "INDETERMINATE";
export type Role = "viewer" | "approver";

export interface Principal {
  name: string;
  role: Role;
}

export interface Summary {
  mode: string;
  note: string;
  scanned_at: string;
  endpoints: number;
  labels: Record<string, number>;
  removal_candidates: number;
  cleared_by_gate: number;
  awaiting_approval: number;
  decided: number;
  model_veto: boolean;
}

export interface Evidence {
  key: string;
  statement: string;
  source: string;
  contribution: number;
}

export interface Verdict {
  endpoint_id: string;
  label: Label;
  confidence: number;
  decided_by: string;
  risk_score: number;
  all_class_scores: Record<string, number>;
  evidence: Evidence[];
  recommended_action: string;
  actionable: boolean;
}

export interface VerdictDetail extends Verdict {
  explanation: string;
}

export interface InventoryRecord {
  endpoint_id: string;
  service: string;
  seen_by: string[];
  auth_scheme: string | null;
  data_classification: string | null;
  owner_team: string | null;
  daily_calls: number | null;
  last_seen_days_ago: number | null;
  flags: string[];
}

export interface BlastRadius {
  endpoint_id: string;
  direct_services: string[];
  indirect_services: string[];
  affected_endpoints: { endpoint_id: string; hop: number }[];
  depth_reached: number;
  truncated: boolean;
  isolated: boolean;
  severity: string;
}

export interface Observation {
  days: number;
  refuse_fraction: number;
  shadow: boolean;
  requests: number;
  identified: Record<string, number>;
  unidentified: number;
}

export type KillState =
  | "NOMINATED"
  | "BLAST_RADIUS"
  | "BLOCKED"
  | "SHADOW"
  | "REJECTED"
  | "AWAITING_APPROVAL"
  | "DENIED"
  | "CANARY_5"
  | "CANARY_25"
  | "CANARY_100"
  | "ROLLED_BACK"
  | "RETIRED";

export interface KillOutcome {
  endpoint_id: string;
  state: KillState;
  path: KillState[];
  reason: string;
  days: number;
  approver: string | null;
  breach_kind: string | null;
  shadow: Observation | null;
  canary: Observation[];
}

export interface PendingApproval {
  endpoint_id: string;
  confidence: number;
  reasons: string[];
  warnings: string[];
  baseline_per_day: number;
  outcome: KillOutcome | null;
}

export interface SafeKillState {
  policy: { shadow_days: number; canary_days: number[]; confidence: number };
  candidates: {
    endpoint_id: string;
    may_proceed: boolean;
    blocked_by: string | null;
    status: string;
  }[];
  pending: PendingApproval[];
  decided: KillOutcome[];
}

export interface AuditEntry {
  seq: number;
  at: string;
  endpoint_id: string;
  from_state: string | null;
  to_state: string;
  reason: string;
  actor: string;
  evidence: Record<string, unknown>;
  prev_hash: string;
  hash: string;
}

export interface AuditPage {
  path: string;
  total: number;
  head: string;
  chain_ok: boolean;
  entries: AuditEntry[];
}

export interface ChainCheck {
  ok: boolean;
  entries: number;
  broken_at: number | null;
  problem: string;
}

export interface BenchmarkRow {
  title: string;
  coverage_pct: number;
  rules_evaluable: number;
  rules_total: number;
  zombies_caught: number;
  zombies_in_estate: number;
  zombie_recall_pct: number;
  unauthenticated_zombies_found: number;
  indeterminate_verdicts: number;
}

export type Benchmark = Record<string, BenchmarkRow>;
