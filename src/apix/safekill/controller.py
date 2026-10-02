"""
The Safe Kill controller: walks one removal candidate through the state machine.

    NOMINATED -> BLAST_RADIUS -> BLOCKED                      gate refused
                              -> SHADOW -> REJECTED           a real caller seen
                                        -> AWAITING_APPROVAL -> DENIED
                                                             -> CANARY_5/25/100
                                                                -> ROLLED_BACK
                                                                -> RETIRED

Three properties are guaranteed by construction rather than by convention:

1. **No removal without a named decision.** Nothing passes AWAITING_APPROVAL
   unless an Approver returns a Decision. With no approver the walk stops there
   and the endpoint is left serving traffic. The approver's identity, and
   whether it was a human, is written into the audit entry for the approval.

2. **Rollback is automatic.** A breach during any canary stage restores the
   endpoint and records ROLLED_BACK with the controller as the actor. No human
   is asked first, which is what the design means by "automatic, not manual".

3. **Every transition is audited**, failures included, through one method that
   also refuses any move the design does not contain.

The controller knows nothing about the simulated estate: it is structurally
forbidden from importing it (tests/test_engine.py), and learns about traffic
only through the EnforcementBackend protocol, which a real gateway plugin would
implement in exactly the same way.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Any, Protocol

from apix.graph.build import RemovalAssessment
from apix.safekill.audit import AuditLog
from apix.safekill.backend import EnforcementBackend, WindowObservation
from apix.safekill.policy import SafeKillPolicy
from apix.safekill.states import (
    CANARY_FRACTION,
    CANARY_STAGES,
    TERMINAL,
    KillState,
    check_transition,
)

CONTROLLER = "safekill-controller"

#: A fixed epoch so simulated runs are reproducible to the second.
DEFAULT_START = datetime(2026, 10, 1, 9, 0, 0)


# ---------------------------------------------------------------------------
# Approval
# ---------------------------------------------------------------------------
@dataclass(frozen=True)
class ApprovalRequest:
    """What an approver is shown before deciding."""

    endpoint_id: str
    confidence: float
    reasons: list[str]
    shadow: WindowObservation
    baseline_per_day: float
    warnings: list[str]


@dataclass(frozen=True)
class Decision:
    approved: bool
    approver: str
    human: bool
    note: str = ""


class Approver(Protocol):
    def decide(self, request: ApprovalRequest) -> Decision | None:
        """A decision, or None if nobody has decided yet."""
        ...


class NoApprover:
    """The default. Nobody has approved anything, so nothing is removed."""

    def decide(self, request: ApprovalRequest) -> Decision | None:
        return None


@dataclass(frozen=True)
class NamedApprover:
    """A person who has put their name to approving clean candidates.

    Unidentified traffic during the shadow window is the one case the controller
    cannot resolve on its own: on the wire, a forgotten integration without
    credentials and a scanner look the same. Those candidates are declined
    unless the approver has explicitly accepted that risk too.
    """

    name: str
    accept_unidentified: bool = False

    def decide(self, request: ApprovalRequest) -> Decision:
        if request.warnings and not self.accept_unidentified:
            return Decision(
                approved=False,
                approver=self.name,
                human=True,
                note=(
                    "unidentified traffic during shadow, not acknowledged. "
                    "Put authentication in front of it and re-run the shadow "
                    "window: legitimate callers will then identify themselves"
                ),
            )
        return Decision(approved=True, approver=self.name, human=True)


@dataclass(frozen=True)
class PolicyApprover:
    """Non-human approval, for evaluation only. Recorded as such in the audit."""

    name: str = "evaluation-harness"
    accept_unidentified: bool = True

    def decide(self, request: ApprovalRequest) -> Decision:
        approved = self.accept_unidentified or not request.warnings
        return Decision(approved=approved, approver=self.name, human=False)


# ---------------------------------------------------------------------------
# Outcome
# ---------------------------------------------------------------------------
@dataclass
class KillOutcome:
    endpoint_id: str
    state: KillState
    path: list[KillState] = field(default_factory=list)
    reason: str = ""
    days: float = 0.0
    shadow: WindowObservation | None = None
    canary: list[WindowObservation] = field(default_factory=list)
    approver: str | None = None
    #: "identified" or "anonymous" when the walk ended in a rollback.
    breach_kind: str | None = None

    @property
    def finished(self) -> bool:
        return self.state in TERMINAL

    @property
    def pending_approval(self) -> bool:
        return self.state is KillState.AWAITING_APPROVAL

    def to_dict(self) -> dict[str, Any]:
        return {
            "endpoint_id": self.endpoint_id,
            "state": self.state.value,
            "path": [s.value for s in self.path],
            "reason": self.reason,
            "days": self.days,
            "approver": self.approver,
            "breach_kind": self.breach_kind,
            "shadow": _obs_dict(self.shadow) if self.shadow else None,
            "canary": [_obs_dict(o) for o in self.canary],
        }


def _obs_dict(o: WindowObservation) -> dict[str, Any]:
    return {
        "days": o.days,
        "refuse_fraction": o.refuse_fraction,
        "shadow": o.shadow,
        "requests": o.requests,
        "identified": dict(sorted(o.identified.items())),
        "unidentified": o.unidentified,
    }


# ---------------------------------------------------------------------------
# Controller
# ---------------------------------------------------------------------------
@dataclass
class SafeKillController:
    backend: EnforcementBackend
    audit: AuditLog = field(default_factory=AuditLog)
    policy: SafeKillPolicy = field(default_factory=SafeKillPolicy)
    approver: Approver = field(default_factory=NoApprover)
    start: datetime = DEFAULT_START

    def run(self, assessment: RemovalAssessment) -> KillOutcome:
        """Walk one candidate as far as the evidence and the approver allow."""
        verdict = assessment.verdict
        ep = verdict.endpoint_id
        walk = _Walk(self, KillOutcome(endpoint_id=ep, state=KillState.NOMINATED))

        walk.enter(
            KillState.NOMINATED,
            f"classified {verdict.label.value} at {verdict.confidence:.0%} confidence",
            evidence={
                "label": verdict.label.value,
                "confidence": round(verdict.confidence, 4),
                "decided_by": verdict.decided_by,
                "reasons": [r.statement for r in verdict.reasons[:5]],
            },
        )

        # -- the removal gate: classifier and graph must both agree --------
        walk.move(
            KillState.BLAST_RADIUS,
            "assessing the removal gate",
            evidence=assessment.radius.to_dict(),
        )
        if not assessment.may_proceed:
            return walk.finish(KillState.BLOCKED, assessment.blocked_by or "gate refused")

        # -- shadow kill: record who would be refused, refuse nobody -------
        days = self.policy.shadow_days
        walk.move(
            KillState.SHADOW,
            f"shadow kill for {days:g} days: nothing refused, every request recorded",
            evidence={
                "days": days,
                "min_detectable_rate_per_day": self.policy.min_detectable_rate,
                "confidence": self.policy.confidence,
            },
        )
        shadow = self.backend.observe(ep, days=days, refuse_fraction=0.0, shadow=True)
        walk.outcome.shadow = shadow
        walk.advance(days)

        if shadow.identified:
            callers = ", ".join(
                f"{c} ({n})" for c, n in sorted(shadow.identified.items())
            )
            return walk.finish(
                KillState.REJECTED,
                f"shadow observed identified caller(s) the graph did not see: {callers}",
                evidence=_obs_dict(shadow),
            )

        baseline = shadow.unidentified / days if days > 0 else 0.0
        warnings: list[str] = []
        if shadow.unidentified:
            warnings.append(
                f"{shadow.unidentified} unidentified request(s) in {days:g} days "
                f"({baseline:.2f}/day). Without caller credentials this cannot be "
                f"told apart from a legitimate integration."
            )

        walk.move(
            KillState.AWAITING_APPROVAL,
            "shadow clean of identified callers; a named decision is required",
            evidence={**_obs_dict(shadow), "warnings": warnings},
        )

        decision = self.approver.decide(
            ApprovalRequest(
                endpoint_id=ep,
                confidence=verdict.confidence,
                reasons=[r.statement for r in verdict.reasons[:5]],
                shadow=shadow,
                baseline_per_day=baseline,
                warnings=warnings,
            )
        )
        if decision is None:
            walk.outcome.reason = "awaiting a named approver; nothing has been removed"
            return walk.outcome

        walk.outcome.approver = decision.approver
        if not decision.approved:
            return walk.finish(
                KillState.DENIED,
                f"declined by {decision.approver}"
                + (f": {decision.note}" if decision.note else ""),
                actor=decision.approver,
                evidence={"human": decision.human},
            )

        # -- progressive canary, rolled back automatically on breach -------
        for i, stage in enumerate(CANARY_STAGES):
            fraction = CANARY_FRACTION[stage]
            stage_days = self.policy.canary_days[i]
            walk.move(
                stage,
                f"refusing {fraction:.0%} of requests with 410 Gone for {stage_days:g} days",
                actor=decision.approver if i == 0 else CONTROLLER,
                evidence={
                    "refuse_fraction": fraction,
                    "days": stage_days,
                    **({"approved_by": decision.approver, "human": decision.human}
                       if i == 0 else {}),
                },
            )
            obs = self.backend.observe(
                ep, days=stage_days, refuse_fraction=fraction, shadow=False
            )
            walk.outcome.canary.append(obs)
            walk.advance(stage_days)

            breach = self.policy.breach(baseline, obs)
            if breach:
                self.backend.restore(ep)
                walk.outcome.breach_kind = breach.kind
                return walk.finish(
                    KillState.ROLLED_BACK,
                    f"automatic rollback at {fraction:.0%}: {breach.message}",
                    evidence={**_obs_dict(obs), "breach_kind": breach.kind},
                )

        self.backend.retire(ep)
        return walk.finish(
            KillState.RETIRED,
            f"clean through {self.policy.total_days:g} days of shadow and canary; removed",
        )

    def run_all(self, assessments: list[RemovalAssessment]) -> list[KillOutcome]:
        return [self.run(a) for a in assessments]


@dataclass
class _Walk:
    """One endpoint's progress: the only code that writes to the audit log."""

    ctl: SafeKillController
    outcome: KillOutcome
    elapsed: float = 0.0

    @property
    def now(self) -> str:
        return (self.ctl.start + timedelta(days=self.elapsed)).isoformat()

    def advance(self, days: float) -> None:
        self.elapsed += days
        self.outcome.days = self.elapsed

    def enter(self, state: KillState, reason: str, *, evidence: dict[str, Any]) -> None:
        self.outcome.path.append(state)
        self.ctl.audit.append(
            at=self.now, endpoint_id=self.outcome.endpoint_id, from_state=None,
            to_state=state.value, reason=reason, actor=CONTROLLER, evidence=evidence,
        )

    def move(
        self,
        state: KillState,
        reason: str,
        *,
        actor: str = CONTROLLER,
        evidence: dict[str, Any] | None = None,
    ) -> None:
        check_transition(self.outcome.state, state)
        self.ctl.audit.append(
            at=self.now, endpoint_id=self.outcome.endpoint_id,
            from_state=self.outcome.state.value, to_state=state.value,
            reason=reason, actor=actor, evidence=evidence or {},
        )
        self.outcome.state = state
        self.outcome.path.append(state)

    def finish(
        self,
        state: KillState,
        reason: str,
        *,
        actor: str = CONTROLLER,
        evidence: dict[str, Any] | None = None,
    ) -> KillOutcome:
        self.move(state, reason, actor=actor, evidence=evidence)
        self.outcome.reason = reason
        return self.outcome
