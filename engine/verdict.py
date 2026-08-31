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

from dataclasses import dataclass, field, asdict
from enum import Enum
from typing import Any


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

    @property
    def is_actionable(self) -> bool:
        """Whether this verdict would enter the Safe Kill queue.

        Only ZOMBIE is ever a removal candidate. ORPHANED endpoints still carry
        real traffic — removing one causes an outage, which is precisely the
        distinction that keeps this product from being dangerous.
        """
        return self.label is Classification.ZOMBIE

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
        }

    def __repr__(self) -> str:  # pragma: no cover - debugging aid
        return (
            f"<Verdict {self.endpoint_id}: {self.label.value} "
            f"@{self.confidence:.2f}>"
        )
