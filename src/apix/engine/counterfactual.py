"""
Counterfactual explanations: what would have to be different for a verdict to
come out differently.

The signed reasons say why an endpoint got its label. An operator also needs
the other half: what would change it. "This would be ORPHANED, not ZOMBIE, if
it carried ten calls a day" tells them what evidence would settle a doubtful
case, and what would have to happen for a removal to be wrong.

Each counterfactual is computed, not written. A copy of the endpoint's record
is changed in one observable way (it is documented, it gains an owner, it
carries real traffic...) and classified again by the same classifier, with
the same sources consulted, so a rule whose source was never asked still
abstains and a counterfactual can never rest on evidence the scan could not
see. Only changes that move the label are reported, the smallest first: single
changes, and pairs only when no single change is enough.

Nothing here reads ground truth: it sees what the classifier sees.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, replace
from itertools import combinations
from typing import Any

from apix.engine.rules import MEANINGFUL_TRAFFIC_THRESHOLD
from apix.engine.verdict import Verdict
from apix.inventory.correlator import InventoryRecord


@dataclass(frozen=True)
class Change:
    """One observable way an endpoint's evidence could be different."""

    key: str
    #: Reads after "if": "it carried 10 or more calls a day".
    text: str
    applies: Callable[[InventoryRecord], bool]
    apply: Callable[[InventoryRecord], InventoryRecord]


#: The changes considered, each a fact a scan could actually observe.
CHANGES: list[Change] = [
    Change(
        "real_traffic",
        f"it carried {MEANINGFUL_TRAFFIC_THRESHOLD} or more calls a day, recently",
        lambda r: r.daily_calls < MEANINGFUL_TRAFFIC_THRESHOLD or not r.observed_on_wire,
        lambda r: replace(r, observed_on_wire=True,
                          daily_calls=max(r.daily_calls, MEANINGFUL_TRAFFIC_THRESHOLD),
                          last_seen_days_ago=1),
    ),
    Change(
        "went_silent",
        "it fell silent: no calls for over six months",
        lambda r: r.observed_on_wire or r.daily_calls > 0,
        lambda r: replace(r, observed_on_wire=False, daily_calls=0,
                          last_seen_days_ago=200, distinct_callers=0, caller_services=[]),
    ),
    Change(
        "gained_owner",
        "an owning team were recorded",
        lambda r: r.owner_team is None,
        lambda r: replace(r, owner_team="(a team)"),
    ),
    Change(
        "lost_owner",
        "its owning team were no longer recorded",
        lambda r: r.owner_team is not None,
        lambda r: replace(r, owner_team=None),
    ),
    Change(
        "documented",
        "it were documented in the specification and registered with the gateway",
        lambda r: not (r.in_openapi_spec and r.in_gateway_registry),
        lambda r: replace(r, in_openapi_spec=True, in_gateway_registry=True),
    ),
    Change(
        "marked_deprecated",
        "the specification marked it deprecated",
        lambda r: r.in_openapi_spec and not r.spec_deprecated,
        lambda r: replace(r, spec_deprecated=True),
    ),
    Change(
        "has_caller",
        "another service were observed calling it",
        lambda r: r.distinct_callers == 0,
        lambda r: replace(r, distinct_callers=1),
    ),
    Change(
        "pipeline",
        "a CI/CD pipeline deployed it",
        lambda r: r.handler_exists_in_code and not r.deployed_via_pipeline,
        lambda r: replace(r, deployed_via_pipeline=True),
    ),
    Change(
        "recent_commit",
        "its handler had been changed in the last year",
        lambda r: (r.days_since_last_commit or 0) > 365,
        lambda r: replace(r, days_since_last_commit=30),
    ),
]


def counterfactuals(
    rec: InventoryRecord,
    verdict: Verdict,
    classify: Callable[[InventoryRecord], Verdict],
    *,
    limit: int = 4,
) -> list[dict[str, Any]]:
    """The smallest changes to `rec` that would change `verdict`'s label.

    `classify` must be the classifier that produced `verdict`, configured with
    the same consulted sources. Each result names the change(s), the label it
    would get instead, and that label's confidence.
    """
    applicable = [c for c in CHANGES if c.applies(rec)]
    found: list[dict[str, Any]] = []

    def attempt(changes: tuple[Change, ...]) -> None:
        changed = rec
        for c in changes:
            changed = c.apply(changed)
        after = classify(changed)
        if after.label != verdict.label:
            found.append({
                "changes": [c.key for c in changes],
                "if": " and ".join(c.text for c in changes),
                "label": after.label.value,
                "confidence": round(after.confidence, 3),
            })

    for c in applicable:
        attempt((c,))
    if not found:
        for pair in combinations(applicable, 2):
            attempt(pair)
    # Most decisive first: the flip the classifier is surest of.
    found.sort(key=lambda f: (len(f["changes"]), -f["confidence"]))
    return found[:limit]
