"""
Parameterised generation of synthetic API estates.

Why this exists
---------------
The hand-written estate has 25 endpoints and two `ORPHANED` examples. That is
enough to demonstrate that correlation works; it is nowhere near enough to train
a model or to cross-validate one. This module generates many estates so there is
something to train on.

The trap this module is built to avoid
--------------------------------------
The obvious objection to training on generated data is devastating and correct:

    "If you generate the data with rules and then train a model on it, hasn't the
     model just learned your generator?"

Naive generation fails that objection outright. Three properties are designed in
to answer it:

**1. Generation is by mechanism, not by label rule.** Nothing here says "if
traffic is zero then label ZOMBIE". Instead an endpoint is put through a
*lifecycle story* — a product is discontinued, a team is dissolved, a migration
stalls halfway, a debug route is added during an incident and never removed — and
the observable features are consequences of that story. The label records which
story ran. Features and labels therefore share a cause rather than the label
being a function of the features.

**2. Observation is lossy and biased, per estate.** Real sensors miss things.
Each generated estate draws its own connector reliability: one organisation's
OpenAPI spec is well maintained, another's is two years stale; one has a
disciplined gateway registry, another does not. A model that memorises one
estate's observation pattern will not generalise to the next.

**3. Estates are the unit of holdout.** `evaluation/train.py` splits by estate,
never by endpoint, so a model is always tested on organisations it has never
seen. Splitting by endpoint would leak an estate's idiosyncrasies across the
split and inflate every score.

What this still does not fix
----------------------------
The decay mechanisms are the ones documented in the literature and the ones we
thought of. A real estate will contain mechanisms we did not model, and no amount
of generation reveals those. The honest claim remains: *the engine recovers known
decay patterns from partial, disagreeing evidence.* Not: *the engine is validated
on production data.*
"""

from __future__ import annotations

import random
from dataclasses import dataclass
from datetime import date, timedelta
from typing import Any

from apix.simulated_env.estate import Auth, Endpoint, Label, Sensitivity

#: The observable consequences of one lifecycle story. Loosely typed on
#: purpose: each story reports only the facts its mechanism determines.
StoryFacts = dict[str, Any]

# ---------------------------------------------------------------------------
# Vocabulary. Deliberately banking-flavoured so generated estates resemble the
# hand-written one in character, not just in shape.
# ---------------------------------------------------------------------------
_DOMAINS: list[tuple[str, list[str], Sensitivity]] = [
    ("accounts", ["balance", "statement", "summary", "limits", "nominee"], Sensitivity.FINANCIAL),
    ("payments", ["transfer", "upi/pay", "upi/collect", "mandate", "refund"], Sensitivity.FINANCIAL),
    ("cards", ["block", "replace", "pin", "rewards", "limits"], Sensitivity.FINANCIAL),
    ("kyc", ["verify", "documents", "aadhaar", "pan", "video"], Sensitivity.PII),
    ("loans", ["apply", "schedule", "eligibility", "foreclose", "scorecard"], Sensitivity.FINANCIAL),
    ("notify", ["push", "sms", "email", "templates", "preferences"], Sensitivity.INTERNAL),
    ("profile", ["address", "contact", "preferences", "consent"], Sensitivity.PII),
    ("support", ["tickets", "chat", "callback", "faq"], Sensitivity.INTERNAL),
]

_TEAMS = [
    "core-banking", "payments-platform", "cards-eng", "identity", "lending",
    "engagement", "channels", "risk-eng", "customer-platform",
]

_CALLERS = [
    "mobile-bff", "web-bff", "partner-gateway", "merchant-gateway",
    "batch-scheduler", "fraud-service", "reporting-etl", "branch-terminal",
]


@dataclass(frozen=True)
class EstateProfile:
    """How disciplined a given organisation is.

    Drawn per estate. This is what stops a model from learning one fixed
    observation pattern and calling it understanding.
    """

    spec_discipline: float       # P(a live endpoint is actually documented)
    gateway_discipline: float    # P(a live endpoint is actually registered)
    deprecation_hygiene: float   # P(a deprecated endpoint is flagged as such)
    dns_cleanup: float           # P(DNS is removed when an endpoint dies)
    pipeline_coverage: float     # P(a deployment left a CI/CD record)
    zombie_rate: float           # share of endpoints that have decayed
    orphan_rate: float

    @classmethod
    def draw(cls, rng: random.Random) -> EstateProfile:
        return cls(
            spec_discipline=rng.uniform(0.55, 0.98),
            gateway_discipline=rng.uniform(0.60, 0.99),
            # Deliberately never 1.0. Teams forget, which is the behaviour
            # Cassieri et al. documented and the reason our own single
            # misclassification exists.
            deprecation_hygiene=rng.uniform(0.30, 0.85),
            dns_cleanup=rng.uniform(0.05, 0.45),
            pipeline_coverage=rng.uniform(0.50, 0.95),
            zombie_rate=rng.uniform(0.10, 0.35),
            orphan_rate=rng.uniform(0.04, 0.15),
        )


# ---------------------------------------------------------------------------
# Lifecycle stories. Each returns the observable consequences of a mechanism.
# None of them reads or writes a feature threshold directly.
# ---------------------------------------------------------------------------
def _in_service_profile(rng: random.Random) -> StoryFacts:
    """Traffic, recency and code age for an endpoint that is still in service.

    **Shared deliberately** by ACTIVE, DEPRECATED and ORPHANED.

    An earlier version gave each of those stories its own distribution — active
    endpoints busy and freshly committed, deprecated ones quieter and staler.
    A gradient-boosted model then reached 0.968 F1 on DEPRECATED while relying
    almost entirely on `days_since_last_use` and `days_since_last_commit`, and
    barely at all on `spec_deprecated`. It had not learned to detect deprecation;
    it had learned the parameters of the generator.

    That is not how real estates behave. A deprecated endpoint can be busy —
    a partner integration still hammering it is *why* the retirement stalled.
    An active admin endpoint can be called twice a day. Drawing all three from
    one distribution means the only thing separating ACTIVE from DEPRECATED is
    the deprecation flag, and the only thing separating ACTIVE from ORPHANED is
    ownership — which is exactly the real-world situation the project exists to
    handle, and the reason Cassieri et al.'s finding matters.
    """
    return {
        # Wide and heavily overlapping: from a twice-a-day admin route to a
        # core payments path.
        "daily_calls": max(1, int(rng.lognormvariate(6.8, 2.6))),
        "last_use": rng.choice([0, 0, 1, 1, 2, 3, 5, 8, 14, 21]),
        "commit_age": int(rng.triangular(10, 900, 200)),
        "dns": True,
    }


def _story_healthy(rng: random.Random, p: EstateProfile) -> StoryFacts:
    """In active service and maintained."""
    return {
        **_in_service_profile(rng),
        "label": Label.ACTIVE,
        "documented": rng.random() < p.spec_discipline,
        "registered": rng.random() < p.gateway_discipline,
        "owned": True,
        "deprecated_flag": False,
        "story": "in active service",
    }


def _story_announced_retirement(rng: random.Random, p: EstateProfile) -> StoryFacts:
    """A successor shipped; this one still answers because a caller remains.

    Observationally identical to a healthy endpoint **except** for the
    deprecation flag — and that flag is present only `deprecation_hygiene` of
    the time. The recall ceiling this creates is the finding, not a defect.
    """
    return {
        **_in_service_profile(rng),
        "label": Label.DEPRECATED,
        "documented": rng.random() < min(0.95, p.spec_discipline + 0.10),
        "registered": rng.random() < p.gateway_discipline,
        "owned": True,
        "deprecated_flag": rng.random() < p.deprecation_hygiene,
        "story": "superseded by a newer version; retirement never completed",
    }


def _story_team_dissolved(rng: random.Random, p: EstateProfile) -> StoryFacts:
    """The owning team was reorganised away. Traffic continues regardless.

    Also observationally identical to a healthy endpoint except for ownership.
    """
    return {
        **_in_service_profile(rng),
        "label": Label.ORPHANED,
        "documented": rng.random() < p.spec_discipline,
        "registered": rng.random() < p.gateway_discipline,
        "owned": False,
        "deprecated_flag": False,
        "story": "owning team dissolved in a reorganisation; still in use",
    }


def _story_product_discontinued(rng: random.Random, p: EstateProfile) -> StoryFacts:
    """The business line closed. The route was never removed."""
    return {
        "label": Label.ZOMBIE,
        "daily_calls": 0,
        "last_use": rng.randint(200, 1100),
        "documented": rng.random() < p.spec_discipline * 0.3,
        "registered": rng.random() < p.gateway_discipline * 0.5,
        "owned": False,
        "dns": rng.random() > p.dns_cleanup,
        "deprecated_flag": rng.random() < p.deprecation_hygiene * 0.4,
        "commit_age": rng.randint(400, 1600),
        "story": "product discontinued; the endpoint was never decommissioned",
    }


def _story_incident_debug_route(rng: random.Random, p: EstateProfile) -> StoryFacts:
    """Added under pressure during an outage, never cleaned up.

    Stillborn: it was never in real use from the moment it was written, which is
    the dominant pattern Caivano et al. found for dead code.
    """
    return {
        "label": Label.ZOMBIE,
        "daily_calls": rng.choice([0, 0, 0, rng.randint(1, 8)]),
        "last_use": rng.randint(90, 900),
        "documented": False,
        "registered": rng.random() < 0.15,
        "owned": False,
        "dns": rng.random() > p.dns_cleanup * 0.5,
        "deprecated_flag": False,
        "commit_age": rng.randint(300, 1400),
        # Debug routes skip review, which is why they are so often unauthenticated.
        "force_auth_none": rng.random() < 0.55,
        "story": "debug route added during an incident and never removed",
    }


def _story_concluded_experiment(rng: random.Random, p: EstateProfile) -> StoryFacts:
    """An A/B test that finished. Nobody owns the losing variant."""
    return {
        "label": Label.ZOMBIE,
        "daily_calls": 0,
        "last_use": rng.randint(150, 800),
        "documented": False,
        "registered": rng.random() < 0.25,
        "owned": rng.random() < 0.3,
        "dns": rng.random() > p.dns_cleanup,
        "deprecated_flag": False,
        "commit_age": rng.randint(200, 900),
        "story": "A/B experiment concluded; the variant endpoint remained",
    }


def _story_stalled_migration(rng: random.Random, p: EstateProfile) -> StoryFacts:
    """v2 shipped, the old version was meant to follow, and never did."""
    return {
        "label": Label.ZOMBIE,
        "daily_calls": rng.choice([0, 0, rng.randint(1, 9)]),
        "last_use": rng.randint(180, 1000),
        "documented": rng.random() < p.spec_discipline * 0.4,
        "registered": rng.random() < p.gateway_discipline * 0.6,
        "owned": rng.random() < 0.35,
        "dns": rng.random() > p.dns_cleanup,
        "deprecated_flag": rng.random() < p.deprecation_hygiene * 0.5,
        "commit_age": rng.randint(400, 1500),
        "story": "migration to a newer version stalled; the old route survived",
    }


_ZOMBIE_STORIES = [
    _story_product_discontinued,
    _story_incident_debug_route,
    _story_concluded_experiment,
    _story_stalled_migration,
]


# ---------------------------------------------------------------------------
def generate_estate(
    seed: int,
    *,
    n_services: int | None = None,
    endpoints_per_service: tuple[int, int] = (3, 7),
    profile: EstateProfile | None = None,
) -> list[Endpoint]:
    """Generate one synthetic estate.

    Deterministic in `seed`: the same seed always produces the same estate, so a
    result someone reports can be reproduced exactly.
    """
    rng = random.Random(seed)
    p = profile or EstateProfile.draw(rng)

    n_services = n_services or rng.randint(4, 8)
    domains = rng.sample(_DOMAINS, min(n_services, len(_DOMAINS)))
    today = date(2026, 9, 1)

    endpoints: list[Endpoint] = []
    for domain, resources, sensitivity in domains:
        service = f"{domain}-service"
        team = rng.choice(_TEAMS)
        n = rng.randint(*endpoints_per_service)

        for _ in range(n):
            resource = rng.choice(resources)
            version = rng.choice(["v1", "v1", "v2", "v2", "v3"])
            method = rng.choice(["GET", "GET", "POST", "PUT", "DELETE"])
            suffix = rng.choice(["", "", "/{id}", "/{id}", "/status"])
            path = f"/{version}/{domain}/{resource}{suffix}"
            endpoint_id = f"{method} {path}"
            if any(e.endpoint_id == endpoint_id for e in endpoints):
                continue

            roll = rng.random()
            if roll < p.zombie_rate:
                facts = rng.choice(_ZOMBIE_STORIES)(rng, p)
            elif roll < p.zombie_rate + p.orphan_rate:
                facts = _story_team_dissolved(rng, p)
            elif roll < p.zombie_rate + p.orphan_rate + 0.12:
                facts = _story_announced_retirement(rng, p)
            else:
                facts = _story_healthy(rng, p)

            endpoints.append(
                _materialise(rng, p, facts, service, team, method, path,
                             version, sensitivity, today)
            )

    _wire_callers(rng, endpoints)
    return endpoints


def _materialise(
    rng: random.Random,
    p: EstateProfile,
    facts: StoryFacts,
    service: str,
    team: str,
    method: str,
    path: str,
    version: str,
    sensitivity: Sensitivity,
    today: date,
) -> Endpoint:
    """Turn a lifecycle story's consequences into an observable Endpoint."""
    age_days = facts["commit_age"] + rng.randint(0, 400)

    # Auth scheme is drawn from how OLD the endpoint is, not from its label.
    #
    # Keying it off the label was an artifact: it made API-key auth impossible
    # for an ACTIVE endpoint, so `is_legacy_auth` became a near-free signal for
    # "not active" and the model leaned on it. In reality plenty of live,
    # healthy production endpoints authenticate with an API key — what actually
    # predicts the scheme is when the endpoint was built, and age overlaps
    # heavily across all four classes.
    if facts.get("force_auth_none"):
        auth = Auth.NONE
    elif age_days > 900:
        auth = rng.choice(
            [Auth.API_KEY, Auth.API_KEY, Auth.API_KEY, Auth.OAUTH2, Auth.JWT]
        )
    elif age_days > 400:
        auth = rng.choice(
            [Auth.API_KEY, Auth.OAUTH2, Auth.OAUTH2, Auth.JWT, Auth.MTLS]
        )
    else:
        auth = rng.choice(
            [Auth.OAUTH2, Auth.OAUTH2, Auth.JWT, Auth.JWT, Auth.MTLS, Auth.API_KEY]
        )
    return Endpoint(
        service=service,
        method=method,
        path=path,
        version=version,
        auth=auth,
        sensitivity=sensitivity,
        deployed_on=today - timedelta(days=age_days),
        in_openapi_spec=bool(facts["documented"]),
        in_gateway_registry=bool(facts["registered"]),
        owner_team=team if facts["owned"] else None,
        dns_record=bool(facts["dns"]),
        daily_calls=int(facts["daily_calls"]),
        last_meaningful_use_days_ago=int(facts["last_use"]),
        spec_deprecated_flag=bool(facts["deprecated_flag"]),
        true_label=facts["label"],
        decay_story=facts["story"],
    )


def _wire_callers(rng: random.Random, endpoints: list[Endpoint]) -> None:
    """Attach caller services, consistently with each endpoint's story.

    Dependencies are a *consequence* of being used: an endpoint with traffic has
    callers, and one that decayed has none. Wiring them independently of the
    story would let a model learn a relationship the world does not contain.
    """
    services = sorted({e.service for e in endpoints})
    for i, e in enumerate(endpoints):
        if e.daily_calls >= 10:
            pool = [s for s in services if s != e.service] + _CALLERS
            k = rng.randint(1, min(3, len(pool)))
            callers = tuple(rng.sample(pool, k))
        else:
            callers = ()
        endpoints[i] = Endpoint(
            **{**e.__dict__, "internal_callers": callers}
        )


def generate_many(
    n_estates: int, *, start_seed: int = 0
) -> list[tuple[int, list[Endpoint]]]:
    """Generate `n_estates` estates, each tagged with its seed.

    The seed is the estate's identity, and the unit the train/test split holds
    out — so a model is always evaluated on organisations it has never seen.
    """
    return [
        (seed, generate_estate(seed))
        for seed in range(start_seed, start_seed + n_estates)
    ]
