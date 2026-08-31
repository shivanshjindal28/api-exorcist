"""
Classification outcomes and the evidence that produced them.

Design principle P4: every verdict carries its reasons. A bare label with a
confidence score is not auditable, and this system is intended for a regulated
environment where "why was this endpoint disabled?" must have a complete answer.

`Verdict` therefore composes a list of `Reason` objects rather than a formatted
string. Each Reason names the observation, states it in plain language, records
which source witnessed it, and carries the signed contribution it made to the
decision. That structure serialises directly into the audit log and renders
directly in the dashboard, with no parsing in either direction.

Boundary note
-------------
`Classification` is deliberately defined here rather than imported from
`simulated_env.estate.Label`. The engine must never import from the simulated
environment: that module holds the answer key. The two enums having identical
members is a property the evaluation harness asserts, not one the engine assumes.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from enum import Enum
from typing import Any, ClassVar


class Classification(str, Enum):
    """The four lifecycle states an endpoint can be assigned."""

    ACTIVE = "ACTIVE"          # documented, owned, in genuine use
    DEPRECATED = "DEPRECATED"  # announced as retiring, still responding
    ORPHANED = "ORPHANED"      # still used, but no owning team
    ZOMBIE = "ZOMBIE"          # forgotten, no meaningful use, often undocumented


#: Order used for reporting and for confusion-matrix axes.
CLASS_ORDER: list[Classification] = [
    Classification.ACTIVE,
    Classification.DEPRECATED,
    Classification.ORPHANED,
    Classification.ZOMBIE,
]


@dataclass(frozen=True)
class Reason:
    """One piece of evidence that contributed to a verdict.

    `contribution` is signed: positive values argued *for* the assigned label,
    negative values argued against it but were outweighed. Both are retained,
    because an explanation that hides the counter-evidence is not an explanation.
    """

    key: str                  # machine-readable, e.g. "NO_MEANINGFUL_TRAFFIC"
    statement: str            # human-readable sentence
    evidence_source: str      # which discovery source witnessed it
    contribution: float       # signed contribution to the assigned label

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class Verdict:
    """The engine's decision about one endpoint, with its full reasoning."""

    endpoint_id: str
    label: Classification
    confidence: float                       # 0.0–1.0, margin-based
    reasons: list[Reason] = field(default_factory=list)
    scores: dict[str, float] = field(default_factory=dict)  # every class's score
    decided_by: str = "rules"               # "rules" | "model" | "rules+model"
    risk_score: int = 0                     # 0–5, triage ordering only

    #: Which discovery sources were consulted in the scan that produced this
    #: verdict. Not which sources *saw* this endpoint — which ones ran at all.
    sources_consulted: frozenset[str] = frozenset()
    #: Rules that could not be evaluated because a source they depend on was
    #: never consulted. These are not evidence against anything; they are
    #: questions nobody asked.
    abstained: list[str] = field(default_factory=list)
    #: How many rules actually fired. Zero means no evidence was available at
    #: all, and `label` is then a tie-break artifact rather than a conclusion.
    rules_fired: int = 0

    @property
    def is_determinate(self) -> bool:
        """Whether any evidence at all supported this verdict.

        When every rule abstains, all four classes score zero and `max()`
        returns whichever comes first in the enum. That is not a decision, and
        reporting it as one would be the most dishonest thing this system could
        do — it would let a configuration that cannot see anything appear to
        classify everything as healthy. Confidence is 0.25 in that case, exactly
        uniform, which is the correct answer: no idea.
        """
        return self.rules_fired > 0

    @property
    def is_partial(self) -> bool:
        """Whether this verdict rests on incomplete evidence.

        A scan of a source repository has no traffic capture and no gateway
        registry, so it genuinely cannot tell a busy endpoint from a silent one.
        Saying so is the difference between a useful finding and a confident
        fabrication.
        """
        return bool(self.abstained)

    #: Sources without which a removal decision must never be made. An endpoint
    #: cannot be queued for shutdown on the strength of "we did not look".
    REMOVAL_REQUIRES: ClassVar[frozenset[str]] = frozenset({"TRAFFIC"})

    #: Sources without which no lifecycle label is supportable at all.
    LIFECYCLE_REQUIRES: ClassVar[frozenset[str]] = frozenset({"TRAFFIC"})

    @property
    def supports_lifecycle_claim(self) -> bool:
        """Whether a four-class label means anything for this verdict.

        Every class in the taxonomy is defined in terms of *use*: ACTIVE is in
        genuine use, DEPRECATED is still responding, ORPHANED is still used but
        unowned, ZOMBIE has no meaningful use. A scan with no traffic source
        cannot place an endpoint anywhere in that scheme, so it should report
        what it observed — undocumented, unowned, unmaintained — and stop short
        of a lifecycle verdict.

        The label is still computed and retained, because the evidence behind it
        is real and useful for ranking. It is simply not presented as a
        conclusion about the endpoint's place in its lifecycle.
        """
        return self.sources_consulted >= self.LIFECYCLE_REQUIRES

    @property
    def findings(self) -> list[str]:
        """The observations behind this verdict, as plain statements.

        What a scan can honestly report when it cannot classify.
        """
        return [r.statement for r in self.supporting_reasons]

    @property
    def is_actionable(self) -> bool:
        """Whether this verdict may enter the Safe Kill queue.

        Two conditions, and both matter.

        Only ZOMBIE is ever a removal candidate. ORPHANED endpoints still carry
        real traffic — removing one causes an outage, which is precisely the
        distinction that keeps this product from being dangerous.

        And traffic must actually have been observed. A repository scan can
        establish that an endpoint is undocumented, unowned and untouched for
        two years, and still be wrong to remove it, because nothing in a source
        repository reveals whether it served ten million requests yesterday.
        Findings from such a scan are reportable; they are not actionable.
        """
        if self.label is not Classification.ZOMBIE or not self.is_determinate:
            return False
        return self.sources_consulted >= self.REMOVAL_REQUIRES

    @property
    def blocked_reason(self) -> str | None:
        """Why a ZOMBIE verdict is not actionable, if it is not."""
        if self.label is not Classification.ZOMBIE:
            return None
        missing = self.REMOVAL_REQUIRES - self.sources_consulted
        if not missing:
            return None
        return (
            f"not actionable: {', '.join(sorted(missing))} was not consulted, "
            "so real usage was never measured"
        )

    @property
    def supporting_reasons(self) -> list[Reason]:
        return [r for r in self.reasons if r.contribution > 0]

    @property
    def opposing_reasons(self) -> list[Reason]:
        return [r for r in self.reasons if r.contribution < 0]

    def to_dict(self) -> dict[str, Any]:
        return {
            "endpoint_id": self.endpoint_id,
            "label": self.label.value,
            "confidence": round(self.confidence, 4),
            "decided_by": self.decided_by,
            "risk_score": self.risk_score,
            "scores": {k: round(v, 4) for k, v in self.scores.items()},
            "reasons": [r.to_dict() for r in self.reasons],
            "sources_consulted": sorted(self.sources_consulted),
            "abstained": self.abstained,
            "rules_fired": self.rules_fired,
            "determinate": self.is_determinate,
            "actionable": self.is_actionable,
            "blocked_reason": self.blocked_reason,
        }

    def __repr__(self) -> str:  # pragma: no cover - debugging aid
        return (
            f"<Verdict {self.endpoint_id}: {self.label.value} "
            f"@{self.confidence:.2f}>"
        )
