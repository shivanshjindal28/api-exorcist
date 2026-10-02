"""
The Safe Kill state machine, exactly as drawn in design-document.md section 3.4.

The transition table below is the diagram made executable. A controller cannot
move an endpoint along an edge the design does not contain: an illegal move
raises rather than being silently recorded, because an audit trail that can
describe a path the process does not allow is not evidence of anything.

One state is renamed relative to the diagram, and the rename is the substance
of a design decision. The diagram's `Simulated` stage is implemented as a
**shadow kill**: requests are allowed through as normal, and every one that
*would* have been refused is recorded with its caller. It is a simulation in
the sense the diagram meant (it predicts the impact of removal), done in the
only way that harms nothing. See policy.py for why it has to come before any
percentage canary rather than being one.
"""

from __future__ import annotations

from enum import Enum


class KillState(str, Enum):
    NOMINATED = "NOMINATED"                  # classifier returned ZOMBIE
    BLAST_RADIUS = "BLAST_RADIUS"            # removal gate being assessed
    BLOCKED = "BLOCKED"                      # gate refused: dependents or verdict
    SHADOW = "SHADOW"                        # the design's "Simulated" stage
    REJECTED = "REJECTED"                    # shadow observed a real caller
    AWAITING_APPROVAL = "AWAITING_APPROVAL"  # a named human must decide
    DENIED = "DENIED"                        # the human declined
    CANARY_5 = "CANARY_5"                    # 410 Gone to 5% of requests
    CANARY_25 = "CANARY_25"
    CANARY_100 = "CANARY_100"                # every request refused; soak period
    ROLLED_BACK = "ROLLED_BACK"              # automatic restore after a breach
    RETIRED = "RETIRED"                      # removed; audit entry sealed


#: Every edge in the design diagram, and no others.
TRANSITIONS: dict[KillState, frozenset[KillState]] = {
    KillState.NOMINATED: frozenset({KillState.BLAST_RADIUS}),
    KillState.BLAST_RADIUS: frozenset({KillState.BLOCKED, KillState.SHADOW}),
    KillState.SHADOW: frozenset({KillState.REJECTED, KillState.AWAITING_APPROVAL}),
    KillState.AWAITING_APPROVAL: frozenset({KillState.DENIED, KillState.CANARY_5}),
    KillState.CANARY_5: frozenset({KillState.ROLLED_BACK, KillState.CANARY_25}),
    KillState.CANARY_25: frozenset({KillState.ROLLED_BACK, KillState.CANARY_100}),
    KillState.CANARY_100: frozenset({KillState.ROLLED_BACK, KillState.RETIRED}),
    KillState.BLOCKED: frozenset(),
    KillState.REJECTED: frozenset(),
    KillState.DENIED: frozenset(),
    KillState.ROLLED_BACK: frozenset(),
    KillState.RETIRED: frozenset(),
}

TERMINAL: frozenset[KillState] = frozenset(
    s for s, nxt in TRANSITIONS.items() if not nxt
)

#: Percentage of requests refused at each canary stage, from the design.
CANARY_FRACTION: dict[KillState, float] = {
    KillState.CANARY_5: 0.05,
    KillState.CANARY_25: 0.25,
    KillState.CANARY_100: 1.00,
}

#: The canary stages in the order they are walked.
CANARY_STAGES: tuple[KillState, ...] = (
    KillState.CANARY_5,
    KillState.CANARY_25,
    KillState.CANARY_100,
)


class IllegalTransition(RuntimeError):
    """A move the design does not allow. Always a bug, never a runtime path."""


def check_transition(src: KillState, dst: KillState) -> None:
    if dst not in TRANSITIONS[src]:
        allowed = ", ".join(s.value for s in sorted(TRANSITIONS[src])) or "none"
        raise IllegalTransition(
            f"{src.value} -> {dst.value} is not in the design "
            f"(allowed from {src.value}: {allowed})"
        )
