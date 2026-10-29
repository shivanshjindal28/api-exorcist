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

/** One rule that fired, with its weight for every class. */
export interface ScoreRow {
  key: string;
  statement: string;
  source: string;
  weights: Record<string, number>;
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
  /** Every rule that fired; its columns sum to all_class_scores. Absent from
   *  servers older than the explanation table, empty for model verdicts. */
  score_table?: ScoreRow[];
  /** Rules not evaluated because a source they need was never consulted. */
  abstained?: string[];
  sources_consulted?: string[];
}

export interface VerdictDetail extends Verdict {
  explanation: string;
  /** The smallest changes to the evidence that would change the label,
   *  computed by the classifier that decided. Absent from older servers. */
  counterfactuals?: { changes: string[]; if: string; label: Label; confidence: number }[];
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
  /** The path as written at the declaration, before any prefix. Absent from older reports. */
  declared_path?: string | null;
  /** False when the prefix in front of the declared path could not be determined. */
  prefix_resolved?: boolean | null;
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
  /** Added when a report is read (apix/scanning/sensitivity.py). */
  sensitivity?: Sensitivity;
  priority?: number;
}

export interface Sensitivity {
  category: string;
  level: "high" | "medium" | "low";
  because: string;
}

export type Lifecycle = "ACTIVE" | "DEPRECATED" | "ORPHANED" | "ZOMBIE" | "INDETERMINATE";

export interface EndpointUsage {
  requests: number;
  ok: number;
  failed: number;
  server_errors: number;
  clients: number;
  clients_capped: boolean;
  first_seen: string | null;
  last_seen: string | null;
  last_success: string | null;
  daily: [string, number][];
  lifecycle: Lifecycle;
  reason: string;
}

export interface UnmatchedRoute {
  method: string;
  path: string;
  requests: number;
  ok: number;
  failed: number;
  clients: number;
  last_seen: string | null;
}

export interface Traffic {
  window: { start: string | null; end: string | null; days: number | null };
  requests: number;
  matched: number;
  preflight: number;
  unmatched: number;
  gateway_prefixes: string[];
  lifecycle: Partial<Record<Lifecycle, number>>;
  endpoints: Record<string, EndpointUsage>;
  shadow_routes: UnmatchedRoute[];
  shadow_routes_total: number;
  probing: UnmatchedRoute[];
  probing_total: number;
  uncovered_services: string[];
  files: { name: string; lines: number; parsed: number; format: string; note: string }[];
  truncated: boolean;
  imported_at: string;
  imported_by: string;
}

export interface ScanChanges {
  previous: { id: string; finished_at: string | null; commit: string | null };
  same_commit?: boolean;
  added: string[];
  added_undocumented: string[];
  removed: string[];
  became_undocumented: string[];
  became_documented: string[];
  new_candidates: string[];
  resolved_candidates: string[];
  unchanged: number;
}

export interface PlanStep {
  title: string;
  detail: string;
  snippet?: string;
  snippet_label?: string;
  where?: string[];
}

export interface RetirementPlan {
  endpoint_id: string;
  ready: boolean;
  blockers: string[];
  sunset: string;
  steps: PlanStep[];
}

export interface PortfolioProject {
  id: string;
  target: string;
  kind: ScanKind;
  scanned_at: string;
  endpoints: number;
  undocumented: number;
  candidates: number;
  likely: number;
  zombies: number;
  high_sensitivity: number;
  reviewed: number;
  traffic: boolean;
  risk: number;
  /** This project's finished scans, oldest first (at most 12). */
  history?: ScanCounts[];
}

export interface ScanCounts {
  at: string;
  endpoints: number;
  undocumented: number;
  candidates: number;
  likely: number;
}

export interface PortfolioRisk {
  scan: string;
  target: string;
  id: string;
  priority: number;
  sensitivity: string;
  level: Sensitivity["level"];
  label: string;
  documented: boolean;
}

export interface Portfolio {
  totals: {
    projects: number;
    endpoints: number;
    undocumented: number;
    candidates: number;
    likely: number;
    zombies: number;
    high_sensitivity: number;
    reviewed: number;
  };
  projects: PortfolioProject[];
  top_risks: PortfolioRisk[];
  /** Each endpoint counted once, under the worst thing known about it. */
  composition?: { zombie: number; likely: number; candidate: number; undocumented: number; clean: number };
  by_category?: { category: string; level: Sensitivity["level"]; endpoints: number; flagged: number }[];
  /** The same totals at each project's previous scan; null when none was scanned twice. */
  previous?: { endpoints: number; undocumented: number; candidates: number; likely: number } | null;
  compared?: number;
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
  /** What would change its label or end its candidacy, by rescoring. */
  counterfactuals?: { if: string; label: string; score: number }[];
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
  traffic?: Traffic | null;
  traffic_summary?: {
    imported_at: string;
    window_days: number | null;
    lifecycle: Partial<Record<Lifecycle, number>>;
  };
  /** Against the previous finished scan of the same GitHub repository. */
  changes?: ScanChanges | null;
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
