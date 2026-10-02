"""
How long to watch, and what counts as a breach.

Why a shadow window comes before any percentage canary
------------------------------------------------------
The design draws Safe Kill as 5% -> 25% -> 100%. On a busy endpoint that is
the right shape. On the endpoints Safe Kill actually receives it is blind.

Measured on 120 generated estates, the rule classifier wrongly calls 49 live
endpoints ZOMBIE, and **every one of the 49 passes the removal gate**: they
carry 1-9 calls a day, too few for the traffic sensor to record a caller edge,
so the dependency graph sees nothing depending on them. Those are exactly the
endpoints the canary exists to catch, and a 5% canary on a one-call-a-day
endpoint refuses an expected 0.05 requests a day. It will almost always see
nothing and wave the endpoint through.

So the design's "Simulated" stage is a *shadow kill*: nothing is refused, and
every request that would have been is recorded with its caller. It harms no
one, so it can run as long as the statistics require.

How long that is
----------------
Requests to a rarely-used endpoint arrive roughly as a Poisson process. If a
caller makes `r` requests a day, the chance a window of `W` days sees none is
exp(-r * W). To be `c` confident of seeing at least one,

    W >= ln(1 / (1 - c)) / r

At c = 0.95, ln(20) = 2.996, which is the "rule of three". The default minimum
rate is one call every 30 days, because the classic hidden dependency is a
month-end batch job, so the default shadow window is 90 days. That is long, and
it is meant to be: watching costs nothing, and removing an endpoint a month-end
reconciliation depends on costs a month-end incident.

What counts as a breach during the canary
-----------------------------------------
  * Any refused request from an **identified** caller. A named principal needed
    the endpoint; one is enough.
  * Unidentified refusals **above the shadow baseline**. The shadow window
    measures how much anonymous traffic (scanners, health checks) the endpoint
    already gets; the canary breaches only when refusals exceed what that
    baseline predicts by more than three standard deviations, plus one so a
    single stray request on a silent endpoint is not mistaken for a pattern.

A breach is evaluated at the end of each window, not on the first refused
request. A production gateway would roll back on the first refusal from a named
caller, within seconds. Counts of refused requests reported by the simulation
are therefore upper bounds on the harm a streaming detector would allow:
conservative, never flattering.
"""

from __future__ import annotations

import math
from dataclasses import dataclass

from apix.safekill.backend import WindowObservation


@dataclass(frozen=True)
class Breach:
    """Why a canary window must be rolled back.

    `kind` matters for evaluation and for the operator: an identified breach is
    a named caller that needed the endpoint, an anonymous breach is a rise in
    traffic nobody can attribute. They are different evidence and should never
    be summed into one number.
    """

    kind: str            # "identified" | "anonymous"
    message: str


@dataclass(frozen=True)
class SafeKillPolicy:
    #: Slowest caller (calls/day) the shadow window must reliably catch.
    min_detectable_rate: float = 1 / 30
    #: Probability of catching a caller at exactly that rate.
    confidence: float = 0.95
    #: Days at each canary stage. The 100% stage is the soak period.
    canary_days: tuple[float, float, float] = (7.0, 7.0, 14.0)
    #: Standard deviations above the anonymous baseline before a breach.
    sigma: float = 3.0
    #: Fix the shadow window instead of deriving it. 0 means no shadow at all,
    #: which is the design as originally drawn; the evaluation uses this to
    #: measure what the shadow stage is worth.
    shadow_days_override: float | None = None

    def __post_init__(self) -> None:
        if not 0 < self.confidence < 1:
            raise ValueError("confidence must be strictly between 0 and 1")
        if self.min_detectable_rate <= 0:
            raise ValueError("min_detectable_rate must be positive")

    @property
    def shadow_days(self) -> float:
        """The rule-of-three window, rounded up to a whole day."""
        if self.shadow_days_override is not None:
            return float(self.shadow_days_override)
        return float(
            math.ceil(math.log(1 / (1 - self.confidence)) / self.min_detectable_rate)
        )

    @property
    def total_days(self) -> float:
        return self.shadow_days + sum(self.canary_days)

    def miss_probability(self, rate: float, days: float) -> float:
        """Chance a window of `days` sees nothing from a caller at `rate`."""
        return math.exp(-rate * days)

    def anonymous_limit(self, baseline_per_day: float, obs: WindowObservation) -> float:
        """Most unidentified refusals the baseline explains in this window."""
        expected = baseline_per_day * obs.refuse_fraction * obs.days
        return expected + self.sigma * math.sqrt(expected) + 1.0

    def breach(
        self, baseline_per_day: float, obs: WindowObservation
    ) -> Breach | None:
        """Why this canary window must be rolled back, or None if it is clean."""
        if obs.identified:
            names = ", ".join(
                f"{caller} ({n})" for caller, n in sorted(obs.identified.items())
            )
            return Breach(
                "identified", f"refused requests from identified caller(s): {names}"
            )
        limit = self.anonymous_limit(baseline_per_day, obs)
        if obs.unidentified > limit:
            return Breach(
                "anonymous",
                f"{obs.unidentified} unidentified request(s) refused, above the "
                f"{limit:.1f} the shadow baseline of {baseline_per_day:.2f}/day "
                f"explains",
            )
        return None
