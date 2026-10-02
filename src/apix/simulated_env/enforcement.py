"""
A simulated gateway in front of a simulated estate, for Safe Kill.

This is the world's side of the EnforcementBackend protocol. It generates the
requests an endpoint would really receive during a window, refuses the share
Safe Kill asks it to, and reports exactly what a real gateway could report:
request counts, and the authenticated identity of each refused caller where the
endpoint authenticates at all.

The world model, stated as assumptions
--------------------------------------
The estate records traffic volume (`daily_calls`) and recency
(`last_meaningful_use_days_ago`) but not, as a separate fact, whether a genuine
caller still exists. The simulation derives it, and the derivation is a
modelling choice, so it is written down rather than buried:

1. **A genuine caller still exists if one called within the last 30 days.**
   Thirty days is "monthly": the slowest recurring caller worth modelling is a
   month-end batch job. In the estates as generated, in-service stories draw
   recency from 0-21 days and every decay story from 90 days or more (the
   hand-written demo estate's most recent zombie is 41 days), so the boundary
   sits in a gap of the data rather than splitting a population.
2. **A genuine caller's rate follows its recency.** Last used today or
   yesterday: all of `daily_calls` is genuine. Last used `L` days ago: genuine
   calls arrive about once every `L + 1` days, and the rest of `daily_calls`
   is background (scanners, health checks, stray crawlers).
3. **Identity follows authentication.** On an endpoint that authenticates, a
   genuine caller presents a credential the gateway can name. On an
   unauthenticated endpoint nobody is identified. Background traffic is never
   identified.

None of this reads the answer key. Behaviour is derived from the same physical
facts the estate already records, so a different labelling of the same world
would produce the same requests.

The harm ledger
---------------
Alongside what it reports, the backend privately records harm: genuine requests
that were actually refused, and endpoints retired while a genuine caller still
existed. The controller never sees this ledger. The evaluation harness reads
it, in the same way metrics.py reads ground truth to score the classifier.
"""

from __future__ import annotations

import hashlib
import math
import random
from dataclasses import dataclass, field

from apix.safekill.backend import WindowObservation
from apix.simulated_env.estate import Auth, Endpoint

#: Assumption 1 above.
LIVE_CALLER_HORIZON_DAYS = 30


@dataclass(frozen=True)
class Traffic:
    """The world's true request process for one endpoint."""

    genuine_per_day: float
    background_per_day: float
    callers: tuple[str, ...]
    identifiable: bool

    @property
    def has_live_caller(self) -> bool:
        return self.genuine_per_day > 0


def traffic_of(e: Endpoint) -> Traffic:
    """Apply the world model to one endpoint. Pure and deterministic."""
    recency = e.last_meaningful_use_days_ago
    if recency > LIVE_CALLER_HORIZON_DAYS:
        genuine = 0.0
        background = float(e.daily_calls)
    elif recency <= 1:
        genuine = float(max(e.daily_calls, 1))
        background = 0.0
    else:
        genuine = 1.0 / (recency + 1)
        background = float(e.daily_calls)

    callers = e.internal_callers or (_client_principal(e.endpoint_id),)
    return Traffic(
        genuine_per_day=genuine,
        background_per_day=background,
        callers=tuple(callers),
        identifiable=e.auth is not Auth.NONE,
    )


def _client_principal(endpoint_id: str) -> str:
    """A stable name for the external client behind a low-traffic endpoint."""
    return "client-" + hashlib.sha256(endpoint_id.encode()).hexdigest()[:6]


# ---------------------------------------------------------------------------
@dataclass
class Harm:
    """What actually went wrong. Visible to the evaluation, never the controller."""

    genuine_refused: dict[str, int] = field(default_factory=dict)
    retired_with_live_caller: set[str] = field(default_factory=set)
    retired: set[str] = field(default_factory=set)
    restored: set[str] = field(default_factory=set)

    @property
    def total_genuine_refused(self) -> int:
        return sum(self.genuine_refused.values())


#: The what-if caller used by `apix safekill --hidden-caller`: a month-end
#: reconciliation job, the textbook dependency a short traffic capture misses.
HIDDEN_CALLER = ("month-end-recon-batch", 25.0)


@dataclass
class SimulatedEnforcement:
    """EnforcementBackend over one estate. Deterministic in `seed`.

    `hidden_callers` adds, for a demonstration, a genuine caller the estate
    does not record and the traffic sensor therefore never saw: endpoint id ->
    (caller name, days between calls). It changes the *world*, not anything the
    detection pipeline observed, so the controller still has to discover it.
    """

    estate: list[Endpoint]
    seed: int = 0
    name: str = "simulated-gateway"
    harm: Harm = field(default_factory=Harm)
    hidden_callers: dict[str, tuple[str, float]] = field(default_factory=dict)

    def __post_init__(self) -> None:
        self._rng = random.Random(self.seed)
        self._by_id = {e.endpoint_id: e for e in self.estate}

    def traffic(self, endpoint_id: str) -> Traffic:
        base = traffic_of(self._by_id[endpoint_id])
        if endpoint_id not in self.hidden_callers:
            return base
        caller, every_days = self.hidden_callers[endpoint_id]
        return Traffic(
            genuine_per_day=base.genuine_per_day + 1.0 / every_days,
            background_per_day=base.background_per_day,
            # Only the hidden caller is calling if nothing genuine was before.
            callers=(caller, *base.callers) if base.has_live_caller else (caller,),
            identifiable=base.identifiable,
        )

    # -- EnforcementBackend ----------------------------------------------
    def observe(
        self, endpoint_id: str, *, days: float, refuse_fraction: float, shadow: bool
    ) -> WindowObservation:
        t = self.traffic(endpoint_id)
        genuine = _poisson(self._rng, t.genuine_per_day * days)
        background = _poisson(self._rng, t.background_per_day * days)

        if shadow:
            # Nothing is refused; every request is what *would* have been.
            g_refused, b_refused = genuine, background
        else:
            g_refused = _binomial(self._rng, genuine, refuse_fraction)
            b_refused = _binomial(self._rng, background, refuse_fraction)
            if g_refused:
                self.harm.genuine_refused[endpoint_id] = (
                    self.harm.genuine_refused.get(endpoint_id, 0) + g_refused
                )

        identified: dict[str, int] = {}
        unidentified = b_refused
        if t.identifiable:
            for _ in range(g_refused):
                caller = self._rng.choice(t.callers)
                identified[caller] = identified.get(caller, 0) + 1
        else:
            unidentified += g_refused

        return WindowObservation(
            days=days,
            refuse_fraction=0.0 if shadow else refuse_fraction,
            shadow=shadow,
            requests=genuine + background,
            identified=identified,
            unidentified=unidentified,
        )

    def restore(self, endpoint_id: str) -> None:
        self.harm.restored.add(endpoint_id)

    def retire(self, endpoint_id: str) -> None:
        self.harm.retired.add(endpoint_id)
        if self.traffic(endpoint_id).has_live_caller:
            self.harm.retired_with_live_caller.add(endpoint_id)


# ---------------------------------------------------------------------------
# Small samplers. The standard library has neither, and these windows are tiny.
# ---------------------------------------------------------------------------
def _poisson(rng: random.Random, mean: float) -> int:
    if mean <= 0:
        return 0
    if mean > 50:
        return max(0, round(rng.gauss(mean, math.sqrt(mean))))
    # Knuth: exact, and fast at the low rates Safe Kill actually sees.
    limit, k, p = math.exp(-mean), 0, 1.0
    while True:
        p *= rng.random()
        if p <= limit:
            return k
        k += 1


def _binomial(rng: random.Random, n: int, p: float) -> int:
    if n <= 0 or p <= 0:
        return 0
    if p >= 1:
        return n
    if n > 1000:
        mean = n * p
        return min(n, max(0, round(rng.gauss(mean, math.sqrt(mean * (1 - p))))))
    return sum(1 for _ in range(n) if rng.random() < p)
