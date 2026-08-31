"""
The deterministic rule classifier.

How it works
------------
Each rule is a predicate over an `InventoryRecord` paired with a signed weight
per class. Every rule whose predicate holds contributes its weights; the class
with the highest total wins, and confidence is the softmax margin over the four
totals.

Why additive scoring rather than a decision tree
------------------------------------------------
The original design sketched a decision tree. Additive scoring was chosen instead
for three reasons, all of which matter downstream:

1. **It degrades gracefully.** A tree commits at the first branch. Real evidence
   conflicts — an endpoint can be documented, owned, and yet completely silent —
   and scoring weighs that conflict instead of letting whichever test happens to
   run first decide the outcome.

2. **Confidence falls out of the margin.** A tree gives a label with no native
   notion of how close the call was. The gap between the top two scores is
   exactly the signal needed to decide when to consult the ML layer (Phase 3).

3. **It matches the shape of SHAP.** SHAP explains a prediction as additive
   feature contributions summing to the output. This rule layer explains a
   verdict as additive evidence contributions summing to a score. The two layers
   therefore produce explanations in the same form, and the dashboard and audit
   log need only one renderer. A tree's path-based explanation would need a
   second.

Determinism and auditability are unchanged: the same input always yields the same
output, and every contributing weight is reported.

The weights encode the taxonomy's semantics, not the answer key
---------------------------------------------------------------
Weights were set from the definitions of the four classes, before measuring
accuracy. They were deliberately NOT tuned against ground truth afterwards —
hand-fitting them to the 25-endpoint estate would produce a number that means
nothing. Whatever the evaluation reports is what these semantics yield.
"""

from __future__ import annotations

import math
from collections.abc import Callable
from dataclasses import dataclass

from apix.connectors.base import Source
from apix.engine.verdict import CLASS_ORDER, Classification, Reason, Verdict
from apix.inventory.correlator import InventoryRecord

#: Calls/day below which an endpoint is not in *meaningful* use. Matches the
#: correlator's EFFECTIVELY_SILENT_THRESHOLD: health checks, crawlers and stray
#: probes keep a dead endpoint technically "observed on the wire" without anyone
#: actually depending on it. The ground-truth taxonomy turns on meaningful use,
#: so the classifier must too.
MEANINGFUL_TRAFFIC_THRESHOLD = 10

#: Softmax temperature. Above 1.0 to damp confidence — with fourteen rules the
#: raw score spread is wide, and a classifier that reports 0.99 on a
#: 25-endpoint synthetic estate would be lying about how much it knows.
_TEMPERATURE = 3.0

A = Classification.ACTIVE
D = Classification.DEPRECATED
ORPH = Classification.ORPHANED
Z = Classification.ZOMBIE


@dataclass(frozen=True)
class EvidenceRule:
    """One observable condition and what it argues for or against."""

    key: str
    statement: str
    evidence_source: str
    predicate: Callable[[InventoryRecord], bool]
    weights: dict[Classification, float]
    #: Sources whose data this rule's predicate reads. **All** must have been
    #: consulted for the rule to be evaluated at all.
    #:
    #: This is the distinction between "the source said no" and "nobody asked".
    #: A scan of a source repository has no traffic capture, so every endpoint
    #: has `observed_on_wire == False` — not because they are silent, but
    #: because silence was never measured. Without this field the classifier
    #: would read that as overwhelming evidence and label a healthy production
    #: API a zombie, with high confidence. Absence of evidence is not evidence
    #: of absence, and the engine has to encode that rather than assume it.
    requires: frozenset[Source] = frozenset()
    #: Sources of which **at least one** must have been consulted. Used where a
    #: fact is derivable from several places: ownership comes from the OpenAPI
    #: spec, from CI/CD metadata, or from a repository CODEOWNERS file, and any
    #: one of them is enough to make "no owner recorded" a real observation.
    requires_any: frozenset[Source] = frozenset()

    def evaluable_with(self, consulted: frozenset[Source]) -> bool:
        if not self.requires <= consulted:
            return False
        return not self.requires_any or bool(self.requires_any & consulted)


def _has_meaningful_traffic(r: InventoryRecord) -> bool:
    return r.observed_on_wire and r.daily_calls >= MEANINGFUL_TRAFFIC_THRESHOLD


# ---------------------------------------------------------------------------
# The evidence table.
#
# Read this as the specification of the four classes:
#   ACTIVE     = documented, owned, in genuine use
#   DEPRECATED = documented, announced as retiring, still responding
#   ORPHANED   = still genuinely used, but no owning team
#   ZOMBIE     = no meaningful use, typically undocumented
# ---------------------------------------------------------------------------
RULES: list[EvidenceRule] = [
    EvidenceRule(
        key="NO_MEANINGFUL_TRAFFIC",
        statement="no meaningful traffic in the capture window",
        evidence_source="TRAFFIC",
        predicate=lambda r: not _has_meaningful_traffic(r),
        # The primary discriminator. ORPHANED requires real use by definition,
        # so silence argues against it as strongly as it argues against ACTIVE.
        weights={Z: 3.5, D: 0.5, A: -3.0, ORPH: -2.5},
        requires=frozenset({Source.TRAFFIC}),
    ),
    EvidenceRule(
        key="MEANINGFUL_TRAFFIC",
        statement="serving real traffic above the significance threshold",
        evidence_source="TRAFFIC",
        predicate=_has_meaningful_traffic,
        weights={A: 2.0, ORPH: 1.5, D: 1.0, Z: -3.5},
        requires=frozenset({Source.TRAFFIC}),
    ),
    EvidenceRule(
        key="SHADOW",
        statement="absent from both the OpenAPI spec and the gateway registry",
        evidence_source="OPENAPI+GATEWAY",
        predicate=lambda r: not r.in_openapi_spec and not r.in_gateway_registry,
        weights={Z: 2.5, A: -2.0, D: -1.5},
        requires=frozenset({Source.OPENAPI, Source.GATEWAY}),
    ),
    EvidenceRule(
        key="UNDOCUMENTED",
        statement="handler exists in code but the endpoint is not documented",
        evidence_source="CODE+OPENAPI",
        predicate=lambda r: r.handler_exists_in_code and not r.in_openapi_spec,
        weights={Z: 1.0, A: -1.0, D: -1.0},
        requires=frozenset({Source.CODE, Source.OPENAPI}),
    ),
    EvidenceRule(
        key="DOCUMENTED_AND_REGISTERED",
        statement="present in both the OpenAPI spec and the gateway registry",
        evidence_source="OPENAPI+GATEWAY",
        predicate=lambda r: r.in_openapi_spec and r.in_gateway_registry,
        weights={A: 1.5, Z: -1.5},
        requires=frozenset({Source.OPENAPI, Source.GATEWAY}),
    ),
    EvidenceRule(
        key="MARKED_DEPRECATED",
        statement="explicitly marked deprecated in the OpenAPI specification",
        evidence_source="OPENAPI",
        predicate=lambda r: r.spec_deprecated,
        # Near-decisive when present: this is an explicit declaration of intent,
        # not an inference. Note the converse does NOT hold - absence of the flag
        # is not evidence against deprecation, because teams forget to set it.
        weights={D: 5.5, A: -2.5, Z: -0.5},
        requires=frozenset({Source.OPENAPI}),
    ),
    EvidenceRule(
        key="NO_OWNER",
        statement="no owning team could be determined",
        evidence_source="OPENAPI+CICD+CODE",
        predicate=lambda r: r.owner_team is None,
        # Deliberately contributes nothing to ORPHANED. Being unowned is not by
        # itself orphanhood: ORPHANED means "still genuinely used, but nobody
        # owns it", and use cannot be established from ownership metadata. The
        # ORPHANED case is carried by UNOWNED_BUT_USED below, which requires
        # traffic. Before this split, a scan with no ownership source labelled
        # every endpoint ORPHANED on the strength of a missing CODEOWNERS file.
        weights={Z: 0.8, A: -2.0},
        requires_any=frozenset({Source.OPENAPI, Source.CICD, Source.CODE}),
    ),
    EvidenceRule(
        key="UNOWNED_BUT_USED",
        statement="carrying real traffic while no team owns it",
        evidence_source="TRAFFIC+OPENAPI+CICD",
        predicate=lambda r: r.owner_team is None and _has_meaningful_traffic(r),
        # The actual definition of ORPHANED, and the reason it is a separate
        # class from ZOMBIE: something depends on this endpoint right now.
        weights={ORPH: 3.5, Z: -1.0},
        requires=frozenset({Source.TRAFFIC}),
        requires_any=frozenset({Source.OPENAPI, Source.CICD, Source.CODE}),
    ),
    EvidenceRule(
        key="HAS_OWNER",
        statement="an owning team is recorded",
        evidence_source="OPENAPI+CICD",
        predicate=lambda r: r.owner_team is not None,
        weights={A: 1.2, D: 0.5, ORPH: -3.0},
        requires_any=frozenset({Source.OPENAPI, Source.CICD, Source.CODE}),
    ),
    EvidenceRule(
        key="STALE_6M",
        statement="no meaningful use for over six months",
        evidence_source="TRAFFIC",
        predicate=lambda r: (
            r.last_seen_days_ago is None or r.last_seen_days_ago > 180
        ),
        weights={Z: 2.0, A: -2.0, ORPH: -1.5},
        requires=frozenset({Source.TRAFFIC}),
    ),
    EvidenceRule(
        key="RECENTLY_USED",
        statement="used within the last 30 days",
        evidence_source="TRAFFIC",
        predicate=lambda r: (
            r.last_seen_days_ago is not None and r.last_seen_days_ago <= 30
        ),
        weights={A: 1.5, ORPH: 1.0, Z: -2.0},
        requires=frozenset({Source.TRAFFIC}),
    ),
    EvidenceRule(
        key="REACHABLE_BUT_UNUSED",
        statement="still resolvable via DNS despite no observed traffic",
        evidence_source="DNS+TRAFFIC",
        predicate=lambda r: r.dns_resolvable and not r.observed_on_wire,
        # The dangerous combination: nobody uses it, but anybody can reach it.
        weights={Z: 1.5},
        requires=frozenset({Source.DNS, Source.TRAFFIC}),
    ),
    EvidenceRule(
        key="CODE_UNTOUCHED_1Y",
        statement="no commit touching this handler in over a year",
        evidence_source="CODE",
        predicate=lambda r: (r.days_since_last_commit or 0) > 365,
        weights={Z: 1.0, D: 0.5, A: -0.8},
        requires=frozenset({Source.CODE}),
    ),
    EvidenceRule(
        key="NO_PIPELINE_RECORD",
        statement="no CI/CD pipeline record for this endpoint's deployment",
        evidence_source="CICD",
        predicate=lambda r: (
            r.handler_exists_in_code and not r.deployed_via_pipeline
        ),
        weights={Z: 1.2, A: -0.8},
        requires=frozenset({Source.CODE, Source.CICD}),
    ),
    EvidenceRule(
        key="HAS_INTERNAL_CALLERS",
        statement="other services were observed calling this endpoint",
        evidence_source="TRAFFIC",
        predicate=lambda r: r.distinct_callers > 0,
        weights={A: 1.2, ORPH: 1.0, Z: -1.5},
        requires=frozenset({Source.TRAFFIC}),
    ),
]


#: Every source. The default when a caller does not say what was consulted —
#: which is the case for the simulated estate, where all six connectors run.
ALL_SOURCES: frozenset[Source] = frozenset(Source)


class RuleClassifier:
    """Deterministic, fully auditable classification from observable evidence.

    `consulted` names the sources that actually ran in the scan being classified.
    Rules depending on a source that was never consulted abstain rather than
    firing, so a repository-only scan does not mistake "we have no traffic data"
    for "this endpoint receives no traffic".
    """

    name = "rules"

    def __init__(
        self,
        rules: list[EvidenceRule] | None = None,
        consulted: frozenset[Source] | None = None,
    ) -> None:
        self.rules = rules if rules is not None else RULES
        self.consulted = ALL_SOURCES if consulted is None else consulted

    # ------------------------------------------------------------------
    def classify(self, rec: InventoryRecord) -> Verdict:
        scores: dict[Classification, float] = {c: 0.0 for c in CLASS_ORDER}
        fired: list[EvidenceRule] = []
        abstained: list[str] = []

        for rule in self.rules:
            if not rule.evaluable_with(self.consulted):
                abstained.append(rule.key)
                continue
            if rule.predicate(rec):
                fired.append(rule)
                for cls, w in rule.weights.items():
                    scores[cls] += w

        label = max(CLASS_ORDER, key=lambda c: scores[c])

        # Reasons are reported relative to the *assigned* label, so the operator
        # sees what argued for it and what argued against it.
        reasons = [
            Reason(
                key=rule.key,
                statement=rule.statement,
                evidence_source=rule.evidence_source,
                contribution=rule.weights.get(label, 0.0),
            )
            for rule in fired
            if rule.weights.get(label, 0.0) != 0.0
        ]
        reasons.sort(key=lambda r: -abs(r.contribution))

        return Verdict(
            endpoint_id=rec.endpoint_id,
            label=label,
            confidence=_softmax_confidence(scores, label),
            reasons=reasons,
            scores={c.value: scores[c] for c in CLASS_ORDER},
            decided_by=self.name,
            risk_score=_risk_score(rec, label),
            sources_consulted=frozenset(s.value for s in self.consulted),
            abstained=abstained,
            rules_fired=len(fired),
        )

    def classify_all(self, records: list[InventoryRecord]) -> list[Verdict]:
        return [self.classify(r) for r in records]


# ---------------------------------------------------------------------------
def _softmax_confidence(
    scores: dict[Classification, float], label: Classification
) -> float:
    """Confidence as the softmax probability of the winning class.

    Temperature-damped: the raw score spread across fourteen rules is wide, and
    an undamped softmax would report near-certainty on almost every endpoint.
    The value that matters operationally is not the absolute number but the
    ordering - low-confidence verdicts are the ones the ML layer will arbitrate.
    """
    vals = [scores[c] / _TEMPERATURE for c in CLASS_ORDER]
    peak = max(vals)
    exps = [math.exp(v - peak) for v in vals]  # shift for numerical stability
    total = sum(exps)
    idx = CLASS_ORDER.index(label)
    return exps[idx] / total if total else 0.25


def _risk_score(rec: InventoryRecord, label: Classification) -> int:
    """0-5 triage severity, for ordering the operator's queue.

    Severity is about consequence, not confidence: a zombie serving raw identity
    documents without authentication outranks a silent internal helper even when
    the classifier is equally sure about both.
    """
    if label is Classification.ACTIVE:
        return 0
    score = 1
    if "SHADOW_CANDIDATE" in rec.flags:
        score += 1
    if "UNAUTHENTICATED" in rec.flags:
        score += 2
    elif "LEGACY_AUTH" in rec.flags:
        score += 1
    if "SENSITIVE_DATA" in rec.flags:
        score += 1
    if "REACHABLE_BUT_UNUSED" in rec.flags:
        score += 1
    return min(score, 5)
