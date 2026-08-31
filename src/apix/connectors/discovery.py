"""
Runtime and static discovery connectors: traffic, code, DNS/mesh.

These are the sources that find what the authoritative registries miss.
Each has a complementary blind spot, and the combination is what makes
the system work:

  TRAFFIC  sees what actually moved on the wire, including endpoints
           nobody registered. Cannot see endpoints that are deployed but
           silent during the capture window - which is exactly the
           profile of a zombie. So traffic alone under-reports zombies.

  CODE     sees every route defined in the repository, including silent
           ones. Cannot tell whether a route is actually deployed or
           reachable, and will report routes that were never shipped.
           So code alone over-reports.

  DNS      sees what is still resolvable and routable. Coarse (service
           level, not endpoint level) but proves reachability.

Traffic finds the loud unknowns; code finds the silent ones; DNS proves
they are still reachable. A zombie is typically visible to CODE, absent
from GATEWAY and OPENAPI, and either absent from TRAFFIC or present with
negligible volume. That disagreement pattern is the detection signal.
"""

from __future__ import annotations

import hashlib
from collections.abc import Iterator

from apix.connectors.base import Connector, DiscoverySignal, Source
from apix.simulated_env.estate import ESTATE, Endpoint

# Capture window for the passive sensor, in days. An endpoint that
# received no calls in this window simply does not appear in traffic.
TRAFFIC_CAPTURE_WINDOW_DAYS = 30


class TrafficConnector(Connector):
    """Passive network traffic analysis (Zeek).

    Real implementation: parse Zeek's http.log / conn.log from a SPAN or
    TAP port, extract method + URI + host, and normalise dynamic path
    segments (numeric ids, UUIDs) back into templates like /accounts/{id}
    so that millions of distinct URIs collapse to one endpoint.

    Why Zeek rather than Suricata: Suricata is signature-based and
    optimised for matching known attack patterns. We are not hunting
    known attacks; we need complete, protocol-aware visibility of all
    traffic in order to build an inventory. Zeek is purpose-built for
    that passive, high-fidelity logging, and being passive it requires no
    change to production systems - essential in a bank.

    Blind spot: an endpoint with zero calls in the window is invisible.
    """

    source = Source.TRAFFIC
    name = "zeek-sensor"

    def collect(self) -> Iterator[DiscoverySignal]:
        for e in ESTATE:
            # Traffic can only witness endpoints that were actually called
            # within the capture window.
            seen_in_window = (
                e.daily_calls > 0
                or e.last_meaningful_use_days_ago <= TRAFFIC_CAPTURE_WINDOW_DAYS
            )
            if not seen_in_window:
                continue

            yield DiscoverySignal(
                source=self.source,
                endpoint_id=e.endpoint_id,
                service=e.service,
                method=e.method,
                path=e.path,
                version=e.version,
                attributes={
                    "observed_on_wire": True,
                    "daily_calls": e.daily_calls,
                    "last_seen_days_ago": e.last_meaningful_use_days_ago,
                    # Zeek can observe whether an Authorization header was
                    # present, which reveals unauthenticated endpoints even
                    # when the gateway claims otherwise.
                    "auth_header_present": e.auth.value != "NONE",
                    "observed_auth_scheme": e.auth.value,
                    # Distinct client identities seen calling it
                    "distinct_callers": len(e.internal_callers),
                    "caller_services": list(e.internal_callers),
                    "capture_window_days": TRAFFIC_CAPTURE_WINDOW_DAYS,
                },
            )


class CodeConnector(Connector):
    """Static analysis of service source code (Semgrep).

    Real implementation: run Semgrep rules per framework that match route
    declarations - @app.get(...) / @RestController / router.post(...) -
    across every service repository, and emit one finding per route.

    Why Semgrep rather than regex or manual review: Semgrep parses code
    into an abstract syntax tree, so it matches on structure rather than
    text. That means it reliably finds route declarations across
    languages and formatting styles, without the false matches a regex
    over source text would produce. Manual review does not scale to
    hundreds of repositories.

    Blind spot: source code proves a route was *written*, not that it is
    deployed and reachable. Code findings must be corroborated by DNS or
    traffic before acting on them.
    """

    source = Source.CODE
    name = "semgrep-scan"

    def collect(self) -> Iterator[DiscoverySignal]:
        for e in ESTATE:
            # Every endpoint in the estate exists as a handler in code -
            # that is precisely why zombies keep responding.
            repo = f"examplebank/{e.service}"
            # Deterministic fake commit so runs are reproducible
            commit = hashlib.sha1(e.endpoint_id.encode()).hexdigest()[:10]
            yield DiscoverySignal(
                source=self.source,
                endpoint_id=e.endpoint_id,
                service=e.service,
                method=e.method,
                path=e.path,
                version=e.version,
                attributes={
                    "handler_exists_in_code": True,
                    "repository": repo,
                    "last_commit_sha": commit,
                    # How long since anyone touched this handler. Code that
                    # has not been modified in years, in a repo that is
                    # otherwise active, is a strong staleness signal.
                    "days_since_last_commit": _days_since_commit(e),
                    "declared_auth_in_code": e.auth.value,
                },
            )


class DNSConnector(Connector):
    """DNS records and service-mesh registry.

    Real implementation: zone transfer / DNS enumeration for the internal
    domain, plus the service mesh registry (Istio/Consul), to establish
    which services are still resolvable and routable.

    This is deliberately coarse - DNS resolves a service host, not an
    individual endpoint - so it contributes reachability evidence at the
    service level. It matters because a common reason zombies survive is
    that a DNS record or load-balancer rule still points at them long
    after the code was "retired".

    Blind spot: endpoints reachable only from inside the cluster, with no
    DNS entry of their own, are invisible here.
    """

    source = Source.DNS
    name = "dns-mesh"

    def collect(self) -> Iterator[DiscoverySignal]:
        for e in ESTATE:
            if not e.dns_record:
                continue
            yield DiscoverySignal(
                source=self.source,
                endpoint_id=e.endpoint_id,
                service=e.service,
                method=e.method,
                path=e.path,
                version=e.version,
                attributes={
                    "dns_resolvable": True,
                    "fqdn": e.fqdn,
                    "mesh_registered": True,
                },
            )


class CICDConnector(Connector):
    """CI/CD deployment history (GitHub Actions).

    Real implementation: query the Actions API for deployment workflow
    runs per service, and map which endpoints were introduced or last
    shipped by which run.

    This gives us deployment recency and ownership evidence, and in the
    enforcement phase (week 10) this is the same integration point where
    we will *block* undocumented endpoints from shipping.

    Blind spot: endpoints deployed manually, outside the pipeline, have
    no record here - and those are disproportionately the shadow ones.
    """

    source = Source.CICD
    name = "github-actions"

    def collect(self) -> Iterator[DiscoverySignal]:
        for e in ESTATE:
            # Anything registered with the gateway went through the
            # pipeline. Manually-deployed shadow endpoints did not.
            if not e.in_gateway_registry:
                continue
            yield DiscoverySignal(
                source=self.source,
                endpoint_id=e.endpoint_id,
                service=e.service,
                method=e.method,
                path=e.path,
                version=e.version,
                attributes={
                    "deployed_via_pipeline": True,
                    "first_deployed": e.deployed_on.isoformat(),
                    "pipeline_owner_team": e.owner_team,
                },
            )


def _days_since_commit(e: Endpoint) -> int:
    """Approximate code staleness.

    Endpoints still in genuine use tend to be touched occasionally;
    forgotten ones are not. We approximate this from how long the
    endpoint has been unused, which is what a real repo history would
    reflect anyway.
    """
    if e.daily_calls > 100_000:
        return 14
    if e.daily_calls > 0:
        return 90
    # Silent endpoints: code has been untouched roughly as long as
    # it has been unused.
    return max(180, int(e.last_meaningful_use_days_ago))


ALL_CONNECTORS = [
    "GatewayConnector",
    "OpenAPIConnector",
    "TrafficConnector",
    "CodeConnector",
    "DNSConnector",
    "CICDConnector",
]
