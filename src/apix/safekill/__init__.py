"""
Safe Kill: the remediation half of API Exorcist (Phase 4).

Detection ends with a removal candidate that two independent systems agree is
dead: the classifier and the dependency graph. Safe Kill is everything after
that, and it exists because that agreement is still not proof. A caller that
was silent while traffic was being captured is invisible to both.

    states.py      the design's state machine, with illegal moves refused
    policy.py      how long to watch (derived, not chosen) and what a breach is
    backend.py     the enforcement interface a gateway plugin implements
    controller.py  walks a candidate through shadow, approval and canary
    audit.py       append-only, hash-chained record of every transition
"""

from apix.safekill.audit import AuditLog, ChainCheck, verify_file
from apix.safekill.backend import EnforcementBackend, WindowObservation
from apix.safekill.controller import (
    ApprovalRequest,
    Approver,
    Decision,
    KillOutcome,
    NamedApprover,
    NoApprover,
    PolicyApprover,
    SafeKillController,
)
from apix.safekill.policy import SafeKillPolicy
from apix.safekill.states import IllegalTransition, KillState

__all__ = [
    "ApprovalRequest",
    "Approver",
    "AuditLog",
    "ChainCheck",
    "Decision",
    "EnforcementBackend",
    "IllegalTransition",
    "KillOutcome",
    "KillState",
    "NamedApprover",
    "NoApprover",
    "PolicyApprover",
    "SafeKillController",
    "SafeKillPolicy",
    "WindowObservation",
    "verify_file",
]
