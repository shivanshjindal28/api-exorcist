"""
Gateway and OpenAPI specification connectors.

These are the two "authoritative" sources — the ones an organisation
believes describe its API estate. Their defining weakness is that they
are declarative: they describe what was *registered* or *documented*,
not what is actually running.

Every shadow API is by definition missing from at least one of these.
That absence is the single most useful signal in the whole system, which
is why we collect these first and treat gaps as findings.

In production these would call the real Kong / Apigee / AWS API Gateway
admin APIs and fetch the served OpenAPI document. Here they read the
simulated estate, honouring the `in_gateway_registry` and
`in_openapi_spec` flags so the blind spots are faithfully reproduced.
"""

from __future__ import annotations

from typing import Iterator

from connectors.base import Connector, DiscoverySignal, Source
from simulated_env.estate import ESTATE


class GatewayConnector(Connector):
    """Reads the API gateway's route registry.

    Real implementation: GET /routes and /services from the Kong admin
    API (or the Apigee/AWS equivalent), which returns every route the
    gateway will forward.

    Blind spot: endpoints deployed directly onto a service, bypassing
    the gateway, are invisible here. Those are true shadow APIs.
    """

    source = Source.GATEWAY
    name = "kong-gateway"

    def collect(self) -> Iterator[DiscoverySignal]:
        for e in ESTATE:
            if not e.in_gateway_registry:
                continue  # gateway genuinely does not know about it
            yield DiscoverySignal(
                source=self.source,
                endpoint_id=e.endpoint_id,
                service=e.service,
                method=e.method,
                path=e.path,
                version=e.version,
                attributes={
                    # The gateway enforces and therefore knows auth config
                    "auth_scheme": e.auth.value,
                    "upstream_host": e.fqdn,
                    "registered": True,
                    # Gateways keep request counters
                    "daily_calls": e.daily_calls,
                    "route_enabled": True,
                },
            )


class OpenAPIConnector(Connector):
    """Parses the published OpenAPI specification for each service.

    Real implementation: fetch /openapi.json (or the spec published to a
    developer portal) per service and walk paths -> methods.

    Blind spot: the spec is written by hand or generated at build time.
    Anything added later, or removed from the doc without being removed
    from the code, will not appear. This is how documented-but-dead and
    live-but-undocumented endpoints diverge.
    """

    source = Source.OPENAPI
    name = "openapi-spec"

    def collect(self) -> Iterator[DiscoverySignal]:
        for e in ESTATE:
            if not e.in_openapi_spec:
                continue  # not documented
            yield DiscoverySignal(
                source=self.source,
                endpoint_id=e.endpoint_id,
                service=e.service,
                method=e.method,
                path=e.path,
                version=e.version,
                attributes={
                    "documented": True,
                    # Specs commonly carry ownership and lifecycle metadata
                    "owner_team": e.owner_team,
                    "declared_auth": e.auth.value,
                    "data_classification": e.sensitivity.value,
                    # OpenAPI `deprecated: true` flag as actually published.
                    # Imperfect by design: teams forget to set it.
                    "spec_deprecated": e.spec_deprecated_flag,
                },
            )
