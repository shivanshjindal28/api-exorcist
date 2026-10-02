"""
Does Safe Kill make removal safer? Measured, across generated estates.

The question is narrow and the comparison is like-for-like. Both arms receive
exactly the same removal candidates: every endpoint the classifier calls ZOMBIE
and the dependency graph finds isolated, i.e. everything the existing removal
gate clears.

    gate only     remove every cleared candidate immediately
    Safe Kill     shadow window, named approval, progressive canary,
                  automatic rollback

The gate's own error is the population that matters. On generated estates the
rules call some live, low-traffic endpoints ZOMBIE, and the graph cannot block
them because they carry too little traffic for a caller edge to be recorded.
Under "gate only" each of those is an outage. The harness counts how many Safe
Kill stops, at which stage, and how many genuine requests were refused on the
way. It also counts the cost in the other direction: genuinely dead endpoints
that Safe Kill declines or rolls back, which leave attack surface in place.

"Live" is the world's fact, from simulated_env/enforcement.py: a genuine caller
still exists. This module, like metrics.py, is evaluation code and may consult
the world; the controller it drives never does. The label is cross-checked
against it and any disagreement is reported rather than hidden.
"""

from __future__ import annotations

from collections import Counter
from dataclasses import dataclass, field
from typing import Any

from apix.engine.rules import RuleClassifier
from apix.graph import assess_removals, build_graph
from apix.pipeline import run_discovery
from apix.safekill.audit import AuditLog
from apix.safekill.controller import PolicyApprover, SafeKillController
from apix.safekill.policy import SafeKillPolicy
from apix.safekill.states import KillState
from apix.simulated_env.enforcement import SimulatedEnforcement
from apix.simulated_env.generator import generate_many


@dataclass
class Arm:
    """Outcomes for one population (live or dead) under Safe Kill."""

    n: int = 0
    states: Counter[str] = field(default_factory=Counter)
    genuine_refused: int = 0
    #: What triggered each rollback: "identified" or "anonymous".
    rollback_by: Counter[str] = field(default_factory=Counter)

    def count(self, state: KillState) -> int:
        return self.states.get(state.value, 0)


@dataclass
class SafeKillReport:
    estates: int
    policy: SafeKillPolicy
    accept_unidentified: bool
    live: Arm = field(default_factory=Arm)
    dead: Arm = field(default_factory=Arm)
    #: Live endpoints whose label is ZOMBIE, or dead ones whose label is not.
    label_disagreements: int = 0
    #: Sum over live candidates of exp(-rate * shadow_days): how many the
    #: statistics say the shadow window should miss.
    predicted_shadow_misses: float = 0.0
    audit_entries: int = 0
    audit_chains_ok: bool = True

    # -- the comparison ---------------------------------------------------
    @property
    def gate_only_outages(self) -> int:
        """Every live candidate the gate clears is removed, and breaks."""
        return self.live.n

    @property
    def safekill_outages(self) -> int:
        """Live endpoints Safe Kill still retired."""
        return self.live.count(KillState.RETIRED)

    @property
    def caught_without_harm(self) -> int:
        return self.live.count(KillState.REJECTED) + self.live.count(KillState.DENIED)

    @property
    def caught_by_rollback(self) -> int:
        return self.live.count(KillState.ROLLED_BACK)

    @property
    def measured_shadow_misses(self) -> int:
        """Live candidates the shadow window let through to approval."""
        return self.live.n - self.live.count(KillState.REJECTED)

    def to_dict(self) -> dict[str, Any]:
        return {
            "estates": self.estates,
            "shadow_days": self.policy.shadow_days,
            "canary_days": list(self.policy.canary_days),
            "accept_unidentified": self.accept_unidentified,
            "live_candidates": self.live.n,
            "dead_candidates": self.dead.n,
            "gate_only_outages": self.gate_only_outages,
            "safekill_outages": self.safekill_outages,
            "caught_without_harm": self.caught_without_harm,
            "caught_by_rollback": self.caught_by_rollback,
            "genuine_requests_refused": self.live.genuine_refused,
            "live_rollback_by": dict(self.live.rollback_by),
            "dead_rollback_by": dict(self.dead.rollback_by),
            "live_states": dict(self.live.states),
            "dead_states": dict(self.dead.states),
            "label_disagreements": self.label_disagreements,
            "predicted_shadow_misses": round(self.predicted_shadow_misses, 3),
            "measured_shadow_misses": self.measured_shadow_misses,
            "audit_entries": self.audit_entries,
            "audit_chains_ok": self.audit_chains_ok,
        }


def evaluate(
    n_estates: int = 120,
    *,
    policy: SafeKillPolicy | None = None,
    accept_unidentified: bool = True,
    use_model: bool = False,
) -> SafeKillReport:
    policy = policy or SafeKillPolicy()
    report = SafeKillReport(
        estates=n_estates, policy=policy, accept_unidentified=accept_unidentified
    )

    classifier: Any = RuleClassifier()
    if use_model:
        from apix.engine.model import HybridClassifier

        classifier = HybridClassifier(rules=classifier)

    for seed, estate in generate_many(n_estates):
        records = run_discovery(verbose=False, persist=False, estate=estate)
        # Classified directly, not through pipeline.run_classification, which
        # persists data/verdicts.json and would overwrite the demo scan's
        # verdicts with whichever generated estate happened to run last.
        verdicts = classifier.classify_all(records)
        cleared = [
            a for a in assess_removals(verdicts, build_graph(records)) if a.may_proceed
        ]

        backend = SimulatedEnforcement(estate, seed=seed)
        audit = AuditLog()
        controller = SafeKillController(
            backend=backend,
            audit=audit,
            policy=policy,
            approver=PolicyApprover(accept_unidentified=accept_unidentified),
        )
        truth = {e.endpoint_id: e for e in estate}

        for assessment in cleared:
            ep = assessment.verdict.endpoint_id
            traffic = backend.traffic(ep)
            live = traffic.has_live_caller
            if live:
                report.predicted_shadow_misses += policy.miss_probability(
                    traffic.genuine_per_day, policy.shadow_days
                )
            labelled_dead = truth[ep].true_label.value == "ZOMBIE"
            if live == labelled_dead:
                report.label_disagreements += 1

            outcome = controller.run(assessment)
            arm = report.live if live else report.dead
            arm.n += 1
            arm.states[outcome.state.value] += 1
            if outcome.breach_kind:
                arm.rollback_by[outcome.breach_kind] += 1

        report.live.genuine_refused += backend.harm.total_genuine_refused
        report.audit_entries += len(audit.entries)
        report.audit_chains_ok &= audit.verify().ok

    return report


def format_report(r: SafeKillReport) -> str:
    p = r.policy
    lines = [
        "",
        "=" * 74,
        "SAFE KILL EVALUATION: does it make removal safer?",
        "=" * 74,
        "",
        f"  estates            : {r.estates} generated, the same seeds as training",
        f"  shadow window      : {p.shadow_days:g} days (catches a 1-in-"
        f"{1 / p.min_detectable_rate:g}-day caller with {p.confidence:.0%} confidence)",
        f"  canary             : 5% / 25% / 100% for "
        f"{' / '.join(f'{d:g}' for d in p.canary_days)} days",
        "  approval           : evaluation harness, recorded as non-human; "
        + ("accepts" if r.accept_unidentified else "declines")
        + " unidentified traffic",
        "",
        "  Every candidate below was cleared by the existing removal gate:",
        "  classified ZOMBIE, actionable, and isolated in the dependency graph.",
        "",
        f"  live endpoints cleared by mistake : {r.live.n}",
        f"  dead endpoints cleared correctly  : {r.dead.n}",
        "",
        "-" * 74,
        "Live endpoints: would removing them have caused an outage?",
        "-" * 74,
        "",
        f"    gate only, remove at once        {r.gate_only_outages:>4} outages",
        f"    Safe Kill                        {r.safekill_outages:>4} outages",
        "",
        f"    stopped in shadow, nothing refused   {r.live.count(KillState.REJECTED):>4}",
        f"    declined at approval                 {r.live.count(KillState.DENIED):>4}",
        f"    rolled back automatically            {r.caught_by_rollback:>4}",
        f"    retired anyway (slipped through)     {r.safekill_outages:>4}",
        "",
        f"    genuine requests refused in total    {r.live.genuine_refused:>4}",
        "",
        "-" * 74,
        "Dead endpoints: the cost of caution",
        "-" * 74,
        "",
        f"    retired, as they should be           {r.dead.count(KillState.RETIRED):>4}",
        f"    declined at approval                 {r.dead.count(KillState.DENIED):>4}",
        f"    rolled back (false alarm)            {r.dead.count(KillState.ROLLED_BACK):>4}",
        f"    rejected in shadow                   {r.dead.count(KillState.REJECTED):>4}",
        "",
        "  A dead endpoint left running is attack surface that stays open; it",
        "  is a cost, just a smaller one than an outage.",
        "",
        "-" * 74,
        f"  audit: {r.audit_entries} entries, every per-estate chain "
        + ("verifies" if r.audit_chains_ok else "DOES NOT VERIFY"),
        f"  world model vs labels: {r.label_disagreements} disagreement(s)",
        "",
    ]
    return "\n".join(lines)


def sweep(
    windows: tuple[float, ...] = (0, 3, 7, 30, 90),
    n_estates: int = 120,
    *,
    accept_unidentified: bool = True,
) -> list[SafeKillReport]:
    """Repeat the evaluation at several shadow lengths.

    Zero is the design as originally drawn, a canary with no shadow, so the
    first row measures what adding the shadow stage changed.
    """
    return [
        evaluate(
            n_estates,
            policy=SafeKillPolicy(shadow_days_override=w),
            accept_unidentified=accept_unidentified,
        )
        for w in windows
    ]


def format_sweep(reports: list[SafeKillReport]) -> str:
    if not reports:
        return ""
    r0 = reports[0]
    lines = [
        "",
        "=" * 74,
        "WHAT IS THE SHADOW STAGE WORTH?",
        "=" * 74,
        "",
        f"  {r0.live.n} live and {r0.dead.n} dead endpoints, all cleared by the "
        f"removal gate,",
        f"  across {r0.estates} estates. Gate only: {r0.gate_only_outages} outages.",
        "",
        "  shadow   live endpoints                      genuine    dead endpoints",
        "   days    shadow  rollback  outage  missed*   refused    retired  false",
        "          caught                    pred/meas            rollback",
        "  " + "-" * 70,
    ]
    for r in reports:
        lines.append(
            f"  {r.policy.shadow_days:>5g}    {r.live.count(KillState.REJECTED):>5}"
            f"  {r.caught_by_rollback:>8}  {r.safekill_outages:>6}"
            f"  {r.predicted_shadow_misses:>5.1f}/{r.measured_shadow_misses:<3}"
            f"  {r.live.genuine_refused:>8}"
            f"  {r.dead.count(KillState.RETIRED):>8}"
            f"  {r.dead.count(KillState.ROLLED_BACK):>6}"
        )
    lines += [
        "",
        "  * missed = live endpoints the shadow window let through to approval:",
        "    predicted by exp(-rate x days), then measured. Agreement means the",
        "    result follows from the statistics, not from a world built to fit.",
        "",
    ]
    return "\n".join(lines)
