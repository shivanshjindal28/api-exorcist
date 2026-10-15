"""
Zombie candidates from code evidence: the conclusion a repository scan can
honestly reach.

A repository has no traffic, so it cannot prove an endpoint is dead. It can
still hold strong evidence that one is, and a scan that only listed routes
left all of it unread. Scanned against real projects, the evidence that
mattered was:

    superseded      a newer version of the same operation exists (OWASP crAPI:
                    POST .../v2/check-otp beside .../v3/check-otp)
    unused          the project's own clients call its neighbours but not it
                    (crAPI's web app calls v3/check-otp, never v2; the FastAPI
                    template's front end never calls readItem)
    deprecated      marked so in the spec, or in the code (@Deprecated,
                    deprecated=True), and still served
    debug or test   a debug or test endpoint shipped in the API (VAmPI's
                    /users/v1/_debug, /createdb)
    shadow          undocumented while the spec documents its neighbours
    internal        an internal endpoint a public gateway route also matches
    frozen          unchanged for over a year while the project is active

Each signal carries a weight and a sentence. Use by a client or another
service counts against. A candidate scores 2 or more; a "likely zombie" scores
4 or more with at least one strong signal. Everything here is labelled as
suspected from code: confirming it takes usage data, which is what the demo
bank's traffic and Safe Kill's shadow window supply.
"""

from __future__ import annotations

import re
from collections import defaultdict
from dataclasses import dataclass, field
from typing import Any

_VERSION = re.compile(r"^v(\d+(?:\.\d+)?)$", re.I)
_DEBUG = re.compile(
    r"(^|[_\-.])(debug|test|tests|testing|demo|sample|dummy|mock|fake|sandbox|playground|"
    r"createdb|populate|seed|reset-test-users|oops|fail|failing|crash|_debug)([_\-.]|$)", re.I)
_DEBUG_FN = re.compile(r"debug|test_|_test|populate|seed|createdb|failing|oops", re.I)
_INTERNAL = re.compile(r"^(internal|private|admin|_internal|management|ops)$", re.I)
#: Probes are called by load balancers and monitors, not by clients, so "no
#: client calls it" says nothing about them.
_INFRA = re.compile(
    r"^(health|healthz|health-check|healthcheck|ping|ready|readyz|readiness|live|livez|"
    r"liveness|metrics|status|version|info|actuator|favicon\.ico|robots\.txt|"
    # Token-verification keys and discovery documents are fetched by other
    # services' auth libraries, not by any client code (crAPI's jwks.json).
    r"jwks|jwks\.json|\.well-known|openid-configuration|"
    # Documentation and the root redirect (petclinic's "/" -> swagger-ui).
    r"swagger|swagger-ui|swagger-ui\.html|api-docs|docs|redoc|openapi\.json|openapi\.yaml)$",
    re.I)
_CODE_DEPRECATED = re.compile(
    r"@Deprecated\b|deprecated\s*=\s*True|@deprecated\b|\bDEPRECATED\b|:deprecated:|"
    r"#\s*deprecated|//\s*deprecated|\*\s*@deprecated", re.I)

STRONG = {"superseded", "deprecated", "unused"}


@dataclass
class Signal:
    key: str
    weight: int
    text: str


@dataclass
class Candidate:
    endpoint_id: str
    score: int
    label: str
    signals: list[Signal] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "endpoint_id": self.endpoint_id, "score": self.score, "label": self.label,
            "signals": [{"key": s.key, "weight": s.weight, "text": s.text}
                        for s in self.signals],
        }


def code_markers(source: str, line: int) -> list[str]:
    """Deprecation markers on or just above a handler's declaration."""
    lines = source.splitlines()
    lo, hi = max(0, line - 9), min(len(lines), line + 2)
    found = []
    for i in range(lo, hi):
        m = _CODE_DEPRECATED.search(lines[i])
        if m:
            found.append(f"{m.group(0).strip()} at line {i + 1}")
    return found


def _segments(path: str) -> list[str]:
    return [s for s in path.strip("/").split("/") if s]


def version_key(path: str) -> tuple[str, float] | None:
    """(the path with its version segment taken out, the version number)."""
    segs = _segments(path)
    for i, s in enumerate(segs):
        m = _VERSION.match(s)
        if m:
            return "/" + "/".join(segs[:i] + segs[i + 1:]), float(m.group(1))
    return None


def _is_infra(path: str) -> bool:
    segs = _segments(path)
    return not segs or any(_INFRA.match(s) for s in segs[-2:])


def rank(
    endpoints: list[dict[str, Any]],
    *,
    referenced: dict[str, list[str]],
    frontend_referenced: set[str],
    called_by_services: dict[str, list[str]],
    uncalled_generated: dict[str, str],
    exposed_via: dict[str, list[str]],
    markers: dict[str, list[str]],
    newest_change_days: int | None,
) -> list[Candidate]:
    """Score every endpoint; return the candidates, strongest first.

    `endpoints` are report rows (id, method, path, service, documented,
    deprecated_in_spec, last_change_days, file). `referenced` maps an endpoint
    to the client files that reference it; `called_by_services` to services
    whose code calls it; `uncalled_generated` to the generated-client function
    that exists for it but that no code calls.
    """
    service_of = {e["id"]: e.get("service") or "" for e in endpoints}

    # Versions of the same operation.
    families: dict[tuple[str, str, str], list[tuple[float, str]]] = defaultdict(list)
    for e in endpoints:
        vk = version_key(e["path"])
        if vk:
            families[(service_of[e["id"]], e["method"], vk[0])].append((vk[1], e["id"]))
    unversioned = {(service_of[e["id"]], e["method"], e["path"]): e["id"] for e in endpoints
                   if version_key(e["path"]) is None}
    newer: dict[str, str] = {}
    for (svc, method, base), members in families.items():
        # An unversioned path beside v2+ of the same operation is the implicit v1.
        if (svc, method, base) in unversioned and all(v >= 2 for v, _ in members):
            members = [*members, (1.0, unversioned[(svc, method, base)])]
        if len(members) < 2:
            continue
        members.sort()
        latest = members[-1][1]
        for _, eid in members[:-1]:
            newer[eid] = latest

    # "Unused" is only evidence where a front end or SDK covers the service:
    # it references at least three of its endpoints and at least 30% of them.
    # Backend-to-backend calls are use, never coverage: the banking repository's
    # public account endpoints are meant for outside users, and the services
    # calling a few internal ones say nothing about the rest. And partial
    # coverage must not accuse: a UI calling through a gateway that rewrites
    # paths may reach endpoints this cannot match.
    client_reach: dict[str, int] = defaultdict(int)
    for eid in frontend_referenced:
        client_reach[service_of.get(eid, "")] += 1
    service_size: dict[str, int] = defaultdict(int)
    for e in endpoints:
        service_size[service_of[e["id"]]] += 1

    def covered(svc: str) -> bool:
        reach = client_reach.get(svc, 0)
        return reach >= 3 and reach >= 0.3 * service_size.get(svc, 1)
    documented_share: dict[str, tuple[int, int]] = {}
    for svc in set(service_of.values()):
        rows = [e for e in endpoints if service_of[e["id"]] == svc]
        documented_share[svc] = (sum(1 for e in rows if e.get("documented")), len(rows))

    out: list[Candidate] = []
    for e in endpoints:
        eid, path, svc = e["id"], e["path"], service_of[e["id"]]
        segs = _segments(path)
        infra = _is_infra(path)
        sig: list[Signal] = []

        if eid in newer:
            sig.append(Signal("superseded", 3, f"a newer version of this operation exists: {newer[eid]}"))
            if newer[eid] in referenced and eid not in referenced:
                sig.append(Signal("superseded", 2,
                                  "this project's own client calls the newer version and "
                                  "never this one"))

        if e.get("deprecated_in_spec"):
            sig.append(Signal("deprecated", 3, "marked deprecated in the API specification, "
                              "and still served"))
        elif markers.get(eid):
            sig.append(Signal("deprecated", 3, f"marked deprecated in the code "
                              f"({markers[eid][0]}), and still served"))

        internal = any(_INTERNAL.match(s) for s in segs)
        if not infra and eid not in referenced and eid not in called_by_services:
            if eid in uncalled_generated:
                sig.append(Signal("unused", 2, f"the generated client has "
                                  f"{uncalled_generated[eid]}() for it, but no code calls it"))
            # Admin and internal endpoints are not for the front end, so its not
            # calling them says nothing (crAPI's management/admin/lockUser).
            elif covered(svc) and not internal:
                sig.append(Signal("unused", 2, f"this project's own clients call "
                                  f"{client_reach[svc]} other endpoint(s) of {svc}, but "
                                  "not this one"))

        fn = (e.get("function") or "")
        if any(_DEBUG.search(s) for s in segs) or _DEBUG_FN.search(fn):
            sig.append(Signal("debug", 2, "looks like a debug or test endpoint shipped in "
                              "the API"))

        documented, total = documented_share.get(svc, (0, 0))
        if (not infra and not e.get("documented") and total
                and documented >= max(2, total // 2)):
            sig.append(Signal("shadow", 2, f"undocumented, while the specification documents "
                              f"{documented} of {total} endpoints of {svc}"))

        if internal and exposed_via.get(eid):
            sig.append(Signal("internal", 1, f"an internal endpoint also matched by the "
                              f"public route {exposed_via[eid][0]}"))

        age = e.get("last_change_days")
        if (not infra and age is not None and age > 365 and newest_change_days is not None
                and newest_change_days < 120):
            sig.append(Signal("frozen", 1, f"unchanged for {age // 365} year(s) while the "
                              "project is still being changed"))

        if eid in referenced:
            sig.append(Signal("used", -2, f"referenced by this project's client code "
                              f"({referenced[eid][0]})"))
        if eid in called_by_services:
            sig.append(Signal("used", -2, "called by "
                              + ", ".join(called_by_services[eid][:3])))

        score = sum(s.weight for s in sig)
        if score < 2:
            continue
        keys = {s.key for s in sig if s.weight > 0}
        # "Likely zombie" is reserved for the strongest evidence: a newer version
        # or a deprecation, or no client use for an endpoint frozen for a year.
        if score >= 4 and ({"superseded", "deprecated"} & keys
                           or {"unused", "frozen"} <= keys):
            label = "Likely zombie"
        elif "superseded" in keys:
            label = "Superseded version"
        elif "deprecated" in keys:
            label = "Deprecated but served"
        elif "debug" in keys:
            label = "Debug or test endpoint"
        elif "unused" in keys:
            label = "Not used by this project's clients"
        elif "shadow" in keys:
            label = "Undocumented (shadow)"
        else:
            label = "Worth a look"
        out.append(Candidate(eid, score, label, sorted(sig, key=lambda s: -s.weight)))
    return sorted(out, key=lambda c: (-c.score, c.endpoint_id))
