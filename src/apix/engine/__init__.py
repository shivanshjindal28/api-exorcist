"""Classification and explanation engine.

Consumes the correlated inventory and produces explained verdicts.

This package must never import from `simulated_env` — that module holds the
ground-truth answer key. A test enforces the boundary.
"""

from apix.engine.rules import RuleClassifier
from apix.engine.verdict import CLASS_ORDER, Classification, Reason, Verdict

__all__ = [
    "CLASS_ORDER",
    "Classification",
    "Reason",
    "RuleClassifier",
    "Verdict",
]
