"""
The state the REST API serves: one scan, its verdicts, its removal gate, and a
Safe Kill controller that persists across requests.

Kept free of any web framework so it can be tested directly and so the HTTP
layer stays a thin translation. Every mutation takes the lock: FastAPI runs
synchronous endpoints on a thread pool, and a re-scan racing a Safe Kill
decision would otherwise act on a half-replaced inventory.

What persists, and what does not
--------------------------------
The audit log is on disk and shared with the CLI, so its chain survives a
restart and continues across both. A Safe Kill candidate waiting for approval
is held in memory: restarting the API forgets it, and its shadow window has to
run again. That is the conservative failure, since a forgotten approval can
only delay a removal, never cause one.
"""

from __future__ import annotations

import threading
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from apix.engine.counterfactual import counterfactuals
from apix.engine.explain import audit_entry, explain
from apix.engine.rules import RuleClassifier
from apix.engine.verdict import Verdict
from apix.graph import assess_removals, build_graph
from apix.graph.build import RemovalAssessment
from apix.graph.model import BlastRadius
from apix.inventory.correlator import InventoryRecord
from apix.pipeline import run_discovery, sources_of
from apix.safekill import (
    AuditLog,
    Decision,
    KillOutcome,
    SafeKillController,
    SafeKillPolicy,
)
from apix.safekill.controller import NotAwaitingApproval
from apix.simulated_env.enforcement import SimulatedEnforcement
from apix.simulated_env.estate import ESTATE

MODE_NOTE = "simulated estate behind a simulated gateway; nothing real is touched"


class UnknownEndpoint(LookupError):
    pass


class NotACandidate(LookupError):
    pass


@dataclass
class Workspace:
    audit_path: Path
    seed: int = 7
    use_model: bool = False
    policy: SafeKillPolicy = field(default_factory=SafeKillPolicy)

    records: list[InventoryRecord] = field(default_factory=list, init=False)
    verdicts: list[Verdict] = field(default_factory=list, init=False)
    assessments: list[RemovalAssessment] = field(default_factory=list, init=False)
    radii: dict[str, BlastRadius] = field(default_factory=dict, init=False)
    scanned_at: str = field(default="", init=False)
    outcomes: dict[str, KillOutcome] = field(default_factory=dict, init=False)

    def __post_init__(self) -> None:
        self._lock = threading.RLock()
        self._benchmark: dict[str, Any] | None = None
        self._verified_head: str | None = None
        self._verified_ok = True
        self.controller = SafeKillController(
            backend=SimulatedEnforcement(ESTATE, seed=self.seed),
            audit=AuditLog(path=self.audit_path),
            policy=self.policy,
        )
        self.refresh()

    # -- scanning ---------------------------------------------------------------
    def refresh(self) -> None:
        """Re-run discovery, classification and the removal gate."""
        with self._lock:
            records = run_discovery(verbose=False, persist=False)
            classifier: Any = RuleClassifier(consulted=sources_of())
            if self.use_model:
                from apix.engine.model import HybridClassifier

                classifier = HybridClassifier(rules=classifier)
            verdicts = classifier.classify_all(records)
            graph = build_graph(records)
            try:
                self.assessments = assess_removals(verdicts, graph)
                self.radii = {r.endpoint_id: graph.blast_radius(r.endpoint_id)
                              for r in records}
            finally:
                graph.close()
            self.records, self.verdicts = records, verdicts
            # Kept so a counterfactual is judged by the classifier that decided.
            self.classifier = classifier
            self.scanned_at = datetime.now(timezone.utc).isoformat(timespec="seconds")

    def summary(self) -> dict[str, Any]:
        with self._lock:
            labels: dict[str, int] = {}
            for v in self.verdicts:
                labels[v.label.value] = labels.get(v.label.value, 0) + 1
            return {
                "mode": "simulated",
                "note": MODE_NOTE,
                "scanned_at": self.scanned_at,
                "endpoints": len(self.records),
                "labels": dict(sorted(labels.items())),
                "removal_candidates": len(self.assessments),
                "cleared_by_gate": sum(1 for a in self.assessments if a.may_proceed),
                "awaiting_approval": len(self.controller.pending()),
                "decided": len(self.outcomes),
                "model_veto": self.use_model,
            }

    # -- reads ------------------------------------------------------------------
    def verdict(self, endpoint_id: str) -> dict[str, Any]:
        with self._lock:
            v = next((x for x in self.verdicts if x.endpoint_id == endpoint_id), None)
            if v is None:
                raise UnknownEndpoint(endpoint_id)
            rec = next(r for r in self.records if r.endpoint_id == endpoint_id)
            classifier = self.classifier
            flips = counterfactuals(rec, v, lambda r: classifier.classify_all([r])[0])
            return {**audit_entry(v), "explanation": explain(v), "counterfactuals": flips}

    def radius(self, endpoint_id: str) -> dict[str, Any]:
        with self._lock:
            if endpoint_id not in self.radii:
                raise UnknownEndpoint(endpoint_id)
            return self.radii[endpoint_id].to_dict()

    def benchmark(self) -> dict[str, Any]:
        """Computed once per process; it does not depend on the live scan."""
        with self._lock:
            if self._benchmark is None:
                from apix.evaluation.benchmark import run_benchmark

                self._benchmark = {
                    k: {kk: vv for kk, vv in v.items() if not kk.startswith("_")}
                    for k, v in run_benchmark().items()
                }
            return self._benchmark

    # -- Safe Kill ----------------------------------------------------------------
    def safekill_state(self) -> dict[str, Any]:
        with self._lock:
            pending = []
            for req in self.controller.pending():
                outcome = self.controller.pending_outcome(req.endpoint_id)
                pending.append({
                    "endpoint_id": req.endpoint_id,
                    "confidence": round(req.confidence, 4),
                    "reasons": req.reasons,
                    "warnings": req.warnings,
                    "baseline_per_day": round(req.baseline_per_day, 4),
                    "outcome": outcome.to_dict() if outcome else None,
                })
            waiting = {p["endpoint_id"] for p in pending}
            return {
                "policy": {
                    "shadow_days": self.policy.shadow_days,
                    "canary_days": list(self.policy.canary_days),
                    "confidence": self.policy.confidence,
                },
                "candidates": [
                    {
                        "endpoint_id": a.verdict.endpoint_id,
                        "may_proceed": a.may_proceed,
                        "blocked_by": a.blocked_by,
                        "status": (
                            self.outcomes[a.verdict.endpoint_id].state.value
                            if a.verdict.endpoint_id in self.outcomes
                            else "AWAITING_APPROVAL"
                            if a.verdict.endpoint_id in waiting
                            else "NOT_STARTED"
                        ),
                    }
                    for a in self.assessments
                ],
                "pending": pending,
                "decided": [o.to_dict() for o in self.outcomes.values()],
            }

    def start_shadow(self, endpoint_id: str) -> KillOutcome:
        """Run the gate and the shadow window. Refuses nothing; needs no approval."""
        with self._lock:
            assessment = next(
                (a for a in self.assessments if a.verdict.endpoint_id == endpoint_id),
                None,
            )
            if assessment is None:
                raise NotACandidate(endpoint_id)
            if endpoint_id in self.outcomes:
                return self.outcomes[endpoint_id]
            outcome = self.controller.begin(assessment)
            if outcome.finished:
                self.outcomes[endpoint_id] = outcome
            return outcome

    def decide(
        self,
        endpoint_id: str,
        *,
        approver: str,
        approve: bool,
        note: str,
    ) -> KillOutcome:
        """Apply a named person's decision. `approver` comes from their token."""
        with self._lock:
            request = next(
                (r for r in self.controller.pending() if r.endpoint_id == endpoint_id),
                None,
            )
            if request is None:
                raise NotAwaitingApproval(f"{endpoint_id} is not awaiting approval")
            # An approval over unidentified traffic raises UnidentifiedTraffic
            # from the controller and leaves the candidate pending: the person
            # is told why, and can still decline.
            outcome = self.controller.resolve(
                endpoint_id,
                Decision(approved=approve, approver=approver, human=True, note=note),
            )
            self.outcomes[endpoint_id] = outcome
            return outcome

    # -- audit ------------------------------------------------------------------------
    def audit(self, endpoint_id: str | None, limit: int) -> dict[str, Any]:
        with self._lock:
            log = self.controller.audit
            head = log.head                  # syncs first: another process may write
            entries = log.for_endpoint(endpoint_id) if endpoint_id else log.entries
            check = log.verify()
            return {
                "path": str(self.audit_path),
                "total": len(log.entries),
                "head": head,
                "chain_ok": check.ok,
                "entries": [e.to_dict() for e in entries[-limit:]],
            }

    def graph_view(self) -> dict[str, Any]:
        """The demo bank's dependency graph, drawn from observed traffic."""
        from apix.graph.view import traffic_view

        with self._lock:
            labels = {v.endpoint_id: v.label.value for v in self.verdicts}
            return traffic_view(self.records, labels)

    def metrics_state(self) -> dict[str, Any]:
        """Gauges for /metrics. The chain is re-verified only when it has grown."""
        summary = self.summary()
        with self._lock:
            log = self.controller.audit
            head = log.head                  # syncs with the file first
            if self._verified_head != head:
                self._verified_ok = log.verify().ok
                self._verified_head = head
            scanned = datetime.fromisoformat(self.scanned_at).timestamp() \
                if self.scanned_at else 0
            return {
                **summary,
                "audit_entries": len(log.entries),
                "audit_chain_ok": int(self._verified_ok),
                "scanned_at_unix": int(scanned),
            }

    def verify_audit(self) -> dict[str, Any]:
        with self._lock:
            check = self.controller.audit.verify()
            return {
                "ok": check.ok,
                "entries": check.entries,
                "broken_at": check.broken_at,
                "problem": check.problem,
            }
