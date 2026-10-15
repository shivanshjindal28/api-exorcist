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

// ---------------------------------------------------------------------------
// Scans a person starts: an uploaded folder or a GitHub link.

export type CheckStatus = "ok" | "partial" | "unavailable" | "failed";

export interface ScanCheck {
  name: string;
  status: CheckStatus;
  detail: string;
}

export interface SummaryItem {
  label: string;
  value: number | string;
}

export interface ScanEndpoint {
  id: string;
  method: string;
  path: string;
  file: string | null;
  line: number | null;
  framework: string | null;
  owner: string | null;
  last_change_days: number | null;
  documented: boolean;
  deprecated_in_spec: boolean;
  seen_by: string[];
  flags: string[];
  findings: string[];
  risk: number;
  /** Absent in reports saved before candidates were computed. */
  candidate?: Candidate | null;
  referenced_by?: string[];
  service?: string;
}

export interface CandidateSignal {
  key: string;
  weight: number;
  text: string;
}

export interface Candidate {
  endpoint_id: string;
  score: number;
  label: string;
  signals: CandidateSignal[];
}

export interface ScanReport {
  summary: SummaryItem[];
  checks: ScanCheck[];
  endpoints: ScanEndpoint[];
  repository_findings: string[];
  candidates?: Candidate[];
  /** Absent (or null) in reports saved before the graph was built from code. */
  graph?: GraphView | null;
  /** Absent from reports saved before sources were recorded. */
  sources?: { consulted: string[]; unavailable: string[] };
  lifecycle: { available: boolean; why: string };
  details: { commit: string | null; specifications: string[]; mount_prefixes: string[] };
}

export type ScanKind = "github" | "folder";
export type ScanStatus = "queued" | "running" | "done" | "failed";

export interface ScanJob {
  id: string;
  kind: ScanKind;
  target: string;
  requested_by: string;
  status: ScanStatus;
  created_at: string;
  started_at: string | null;
  finished_at: string | null;
  duration_s: number | null;
  error: string | null;
  progress: { at: string; message: string }[];
  summary?: SummaryItem[];
  report?: ScanReport;
  reviews?: Record<string, Review>;
}

export type Decision = "keep" | "document" | "assign-owner" | "investigate";

export interface Review {
  decision: Decision;
  label: string;
  by: string;
  at: string;
  note: string;
}

export interface ScanAudit {
  head: string;
  chain: { ok: boolean; entries: number; broken_at: number | null; problem: string };
  entries: AuditEntry[];
}

export interface InputOption {
  available: boolean;
  warning?: string | null;
  reason?: string | null;
}

export interface Capabilities {
  folder: InputOption;
  github: InputOption;
  website: InputOption;
}

// ---------------------------------------------------------------------------
// The dependency graph (apix/graph/view.py), the same shape for the demo bank
// (basis "traffic") and for a project scan (basis "code").

export type GraphServiceKind = "service" | "gateway" | "topic" | "external";
export type GraphEdgeKind = "calls" | "routes" | "publishes" | "consumes";

export interface GraphService {
  id: string;
  kind: GraphServiceKind;
  endpoints: string[];
  broker?: string;
}

export interface GraphEndpoint {
  id: string;
  service: string;
  method: string;
  path: string;
  label: string | null;
  findings?: number;
  daily_calls?: number;
  exposed_via: string[];
  callers: string[];
  isolated: boolean;
}

export interface GraphEdge {
  kind: GraphEdgeKind;
  from: string;
  to: string;
  evidence: string;
  label?: string;
  count?: number;
  certain?: boolean;
  file?: string;
  line?: number;
}

export interface GraphView {
  basis: "traffic" | "code";
  services: GraphService[];
  endpoints: GraphEndpoint[];
  edges: GraphEdge[];
  radius: Record<string, BlastRadius>;
  notes: string[];
  stats: Record<string, number>;
}
