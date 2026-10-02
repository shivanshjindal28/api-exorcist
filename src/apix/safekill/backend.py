"""
The enforcement interface: everything Safe Kill can do to, and learn from, a
running endpoint.

The controller depends on this protocol and on nothing else in the outside
world. In simulation the implementation is simulated_env/enforcement.py; in a
deployment it is a gateway or service-mesh plugin (a Kong or Envoy filter that
answers 410 Gone for a share of requests and reports what it refused). The
controller code is identical either way, which is the same seam the message bus
and the graph store already use.

What a backend reports is deliberately limited to what a real gateway can know:

  * how many requests arrived, and how many were (or in shadow mode would have
    been) refused;
  * for each refused request, the caller's **authenticated identity** if the
    endpoint authenticates (a JWT subject, an mTLS principal, an API key id);
  * otherwise, only that an unidentified request was refused.

It never reports whether a caller "really needed" the endpoint, because no
gateway can know that. The controller has to reason from identity and volume,
and that limit is real, not a simplification: on an unauthenticated endpoint a
forgotten partner integration and an attacker's scanner are indistinguishable
on the wire. Policy is written around that fact rather than pretending it away.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Protocol


@dataclass(frozen=True)
class WindowObservation:
    """What one observation window showed."""

    days: float
    refuse_fraction: float                      # 0.0 in shadow mode
    shadow: bool
    requests: int
    #: Refused (or, in shadow, would-be-refused) requests per identified caller.
    identified: dict[str, int] = field(default_factory=dict)
    #: Refused (or would-be-refused) requests with no authenticated identity.
    unidentified: int = 0

    @property
    def identified_total(self) -> int:
        return sum(self.identified.values())

    @property
    def refused_total(self) -> int:
        return self.identified_total + self.unidentified


class EnforcementBackend(Protocol):
    """A gateway-like control point in front of one estate."""

    name: str

    def observe(
        self, endpoint_id: str, *, days: float, refuse_fraction: float, shadow: bool
    ) -> WindowObservation:
        """Run one window. In shadow mode nothing is refused, only recorded."""
        ...

    def restore(self, endpoint_id: str) -> None:
        """Stop refusing anything. Called on rollback."""
        ...

    def retire(self, endpoint_id: str) -> None:
        """Remove the route permanently. Called only on RETIRED."""
        ...
