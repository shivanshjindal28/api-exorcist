"""
Shared contract for all discovery connectors.

Design principle
----------------
Every connector is a partial, imperfect witness. The gateway knows only
what was registered with it. The OpenAPI spec knows only what was
documented. Traffic capture sees only what actually moved on the wire
during the capture window. Code scanning sees what is written in the
repository, including things that were never deployed.

No single source is sufficient, and that is the point: shadow and zombie
endpoints are precisely the ones that are missing from the authoritative
sources. Correlating disagreeing sources is what surfaces them, so the
inventory layer treats a *disagreement between sources* as signal, not
as noise.

Connectors therefore emit `DiscoverySignal` objects rather than verdicts.
They never read ground truth and never classify.
"""

from __future__ import annotations

from collections.abc import Iterator
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any


class Source(str, Enum):
    """Which discovery mechanism produced a signal."""

    GATEWAY = "GATEWAY"        # API gateway registry / config
    OPENAPI = "OPENAPI"        # published OpenAPI specification
    TRAFFIC = "TRAFFIC"        # passive network capture (Zeek)
    CODE = "CODE"              # static analysis of source (Semgrep)
    DNS = "DNS"                # DNS records / service mesh registry
    CICD = "CICD"              # CI/CD deployment events


@dataclass
class DiscoverySignal:
    """One observation about one endpoint, from one source.

    `attributes` carries whatever that particular source happens to know.
    Different sources populate different keys, and the inventory layer
    merges them. Absence of a key means "this source cannot tell",
    which is deliberately distinct from a value of False.
    """

    source: Source
    endpoint_id: str                 # "GET /v2/accounts/{id}"
    service: str
    method: str
    path: str
    version: str
    observed_at: datetime = field(
        default_factory=lambda: datetime.now(timezone.utc)
    )
    attributes: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        d = asdict(self)
        d["source"] = self.source.value
        d["observed_at"] = self.observed_at.isoformat()
        return d

    def __repr__(self) -> str:  # pragma: no cover - debugging aid
        return f"<Signal {self.source.value}: {self.endpoint_id}>"


class Connector:
    """Base class for a discovery connector.

    Subclasses implement `collect()` and yield DiscoverySignal objects.
    Keeping this interface uniform is what lets the ingestion layer treat
    all six sources identically and run them in parallel.
    """

    source: Source = None  # type: ignore[assignment]
    name: str = "connector"

    def collect(self) -> Iterator[DiscoverySignal]:
        raise NotImplementedError

    def run(self) -> list[DiscoverySignal]:
        """Collect all signals eagerly, for batch/offline mode."""
        return list(self.collect())


def split_endpoint_id(endpoint_id: str) -> tuple[str, str, str]:
    """'GET /v2/accounts/{id}' -> ('GET', 'v2', '/accounts/{id}')."""
    method, full_path = endpoint_id.split(" ", 1)
    parts = full_path.lstrip("/").split("/", 1)
    version = parts[0]
    path = "/" + parts[1] if len(parts) > 1 else "/"
    return method, version, path
