"""
From requests to lifecycle: which scanned endpoints are really used.

Every request is matched to the endpoint whose route template it fits (the
most literal template wins: /users/me before /users/{id}). Then each endpoint
is classified by the definitions the whole project uses:

    ACTIVE        used, owned, not deprecated
    DEPRECATED    marked deprecated and still used: migrate its callers first
    ORPHANED      used, but no owning team is recorded: assign one, never remove
    ZOMBIE        no successful request in the whole window
    INDETERMINATE the logs cannot decide, and the reason says why

Three rules keep "no traffic" from being over-read, because a false ZOMBIE is
an outage:

1. Absence only counts where the logs cover the service. If a service has no
   requests at all, the logs are from somewhere else; nothing in it is called
   unused.
2. The window must be long enough. Below MIN_WINDOW_DAYS nothing is called a
   zombie; above it, the rule of three bounds what was missed: seeing no call
   in W days means, at 95% confidence, fewer than one call every W/3 days.
3. Failed requests are not use. Only 401, 403 or 404 responses is someone
   probing, which is the attack surface, not a customer.

Requests that fit no scanned endpoint are reported too: a route the gateway
serves that the code does not show is a shadow API by definition.
"""

from __future__ import annotations

import re
from collections import Counter, defaultdict
from collections.abc import Iterable
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any

from apix.live.evidence import _is_infra
from apix.traffic.logs import Request

MIN_WINDOW_DAYS = 7
#: Distinct clients are counted exactly up to this many per endpoint.
CLIENT_CAP = 10_000
#: Unmatched routes reported, busiest first.
UNMATCHED_SHOWN = 40

_ID_SEGMENT = re.compile(
    r"^(\d+|[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}|[0-9a-f]{16,}"
    r"|[A-Za-z0-9_\-]{24,}|[^@/]+@[^@/]+)$", re.I)


@dataclass
class _Template:
    endpoint_id: str
    method: str
    regex: re.Pattern[str]
    literal: int            # literal segments: more literal is more specific
    segments: int


def _compile(method: str, path: str, endpoint_id: str) -> _Template:
    segs = [s for s in path.strip("/").split("/") if s]
    parts = []
    literal = 0
    for s in segs:
        if re.fullmatch(r"\{[^}]*\}", s):
            parts.append("[^/]+")
        elif "{" in s:
            parts.append(re.sub(r"\\\{[^}]*\\\}", "[^/]+", re.escape(s)))
        else:
            parts.append(re.escape(s))
            literal += 1
    pattern = "^/" + "/".join(parts) + "$" if parts else "^/$"
    return _Template(endpoint_id, method.upper(), re.compile(pattern, re.I), literal, len(segs))


class Matcher:
    """Request -> endpoint id, by method and route template."""

    def __init__(self, endpoints: Iterable[dict[str, Any]]) -> None:
        self._by_method: dict[str, list[_Template]] = defaultdict(list)
        for e in endpoints:
            t = _compile(e["method"], e["path"], e["id"])
            self._by_method[t.method].append(t)
        for ts in self._by_method.values():
            ts.sort(key=lambda t: (-t.literal, -t.segments))
        self.prefix_hits: Counter[str] = Counter()

    def _find(self, method: str, path: str) -> str | None:
        for t in self._by_method.get(method, ()):
            if t.regex.match(path):
                return t.endpoint_id
        return None

    def match(self, method: str, path: str) -> str | None:
        m = "GET" if method == "HEAD" else method
        hit = self._find(m, path)
        if hit:
            return hit
        # A gateway often serves the API under a prefix the code never sees
        # (/api, /identity). Try without one or two leading segments.
        segs = path.strip("/").split("/")
        for n in (1, 2):
            if len(segs) > n:
                hit = self._find(m, "/" + "/".join(segs[n:]))
                if hit:
                    self.prefix_hits["/" + "/".join(segs[:n])] += 1
                    return hit
        return None


@dataclass
class _Usage:
    requests: int = 0
    ok: int = 0
    failed: int = 0
    server_errors: int = 0
    first: datetime | None = None
    last: datetime | None = None
    last_ok: datetime | None = None
    clients: set[str] = field(default_factory=set)
    days: Counter[str] = field(default_factory=Counter)

    def add(self, r: Request) -> None:
        self.requests += 1
        if r.status is None or r.status < 400:
            self.ok += 1
            if r.at and (self.last_ok is None or r.at > self.last_ok):
                self.last_ok = r.at
        elif r.status >= 500:
            self.server_errors += 1
        else:
            self.failed += 1
        if r.at:
            if self.first is None or r.at < self.first:
                self.first = r.at
            if self.last is None or r.at > self.last:
                self.last = r.at
            self.days[r.at.date().isoformat()] += 1
        if r.client and len(self.clients) < CLIENT_CAP:
            self.clients.add(r.client)


def _route_shape(path: str) -> str:
    segs = [("{id}" if _ID_SEGMENT.match(s) else s) for s in path.strip("/").split("/") if s]
    return "/" + "/".join(segs)


def _iso(t: datetime | None) -> str | None:
    return t.isoformat(timespec="seconds") if t else None


def analyse(endpoints: list[dict[str, Any]], requests: Iterable[Request]) -> dict[str, Any]:
    """Match, count and classify. `endpoints` are scan report rows."""
    matcher = Matcher(endpoints)
    usage: dict[str, _Usage] = defaultdict(_Usage)
    unmatched: dict[tuple[str, str], _Usage] = defaultdict(_Usage)
    total = matched = preflight = 0
    start: datetime | None = None
    end: datetime | None = None

    for r in requests:
        total += 1
        if r.at:
            start = r.at if start is None or r.at < start else start
            end = r.at if end is None or r.at > end else end
        if r.method == "OPTIONS":       # CORS preflight: a browser asking, not using
            preflight += 1
            continue
        eid = matcher.match(r.method, r.path)
        if eid:
            matched += 1
            usage[eid].add(r)
        else:
            unmatched[(r.method, _route_shape(r.path))].add(r)

    window_days = round((end - start).total_seconds() / 86400, 1) if start and end else None
    service_of = {e["id"]: e.get("service") or "" for e in endpoints}
    covered = {service_of[eid] for eid, u in usage.items() if u.requests}

    rows: dict[str, dict[str, Any]] = {}
    counts: Counter[str] = Counter()
    for e in endpoints:
        eid = e["id"]
        u = usage.get(eid, _Usage())
        label, reason = _classify(e, u, window_days, service_of[eid] in covered)
        counts[label] += 1
        rows[eid] = {
            "requests": u.requests, "ok": u.ok, "failed": u.failed,
            "server_errors": u.server_errors,
            "clients": len(u.clients), "clients_capped": len(u.clients) >= CLIENT_CAP,
            "first_seen": _iso(u.first), "last_seen": _iso(u.last),
            "last_success": _iso(u.last_ok),
            "daily": sorted(u.days.items())[-90:],
            "lifecycle": label, "reason": reason,
        }

    shadow: list[dict[str, Any]] = []
    noise: list[dict[str, Any]] = []
    for (method, shape), u in sorted(unmatched.items(), key=lambda kv: -kv[1].requests):
        row = {"method": method, "path": shape, "requests": u.requests, "ok": u.ok,
               "failed": u.failed, "clients": len(u.clients),
               "last_seen": _iso(u.last)}
        # Only failures: someone probing for routes that are not there.
        (shadow if u.ok else noise).append(row)

    uncovered = sorted({service_of[e["id"]] for e in endpoints} - covered - {""})
    return {
        "window": {"start": _iso(start), "end": _iso(end), "days": window_days},
        "requests": total, "matched": matched, "preflight": preflight,
        "unmatched": total - matched - preflight,
        "gateway_prefixes": [p for p, _ in matcher.prefix_hits.most_common(5)],
        "lifecycle": dict(counts),
        "endpoints": rows,
        "shadow_routes": shadow[:UNMATCHED_SHOWN],
        "shadow_routes_total": len(shadow),
        "probing": noise[:UNMATCHED_SHOWN],
        "probing_total": len(noise),
        "uncovered_services": uncovered,
    }


def _classify(e: dict[str, Any], u: _Usage, window: float | None,
              service_covered: bool) -> tuple[str, str]:
    deprecated = bool(e.get("deprecated_in_spec")) or any(
        s.get("key") == "deprecated" for s in ((e.get("candidate") or {}).get("signals") or []))
    if u.ok:
        who = f"{u.ok:,} successful request(s) from {len(u.clients):,} client(s)"
        if deprecated:
            return "DEPRECATED", f"{who}, but marked deprecated: migrate them before removal"
        if not e.get("owner"):
            return "ORPHANED", f"{who}, and no owning team is recorded: assign one, do not remove"
        return "ACTIVE", who
    if _is_infra(e["path"]):
        return "INDETERMINATE", ("a probe or documentation route; monitors call these, and "
                                 "monitor traffic is often not in access logs")
    if not service_covered:
        return "INDETERMINATE", (f"these logs hold no request to any endpoint of "
                                 f"{e.get('service') or 'this service'}, so they do not cover it")
    if window is None:
        return "INDETERMINATE", "the logs carry no timestamps, so the window is unknown"
    if window < MIN_WINDOW_DAYS:
        return "INDETERMINATE", (f"only {window:g} day(s) of logs; at least "
                                 f"{MIN_WINDOW_DAYS} are needed before calling anything unused")
    bound = window / 3
    probed = f" Only failed requests ({u.failed:,}): someone probing it." if u.failed else ""
    return "ZOMBIE", (f"no successful request in {window:g} days. At 95% confidence it is "
                      f"called less than once every {bound:.0f} days.{probed}")
