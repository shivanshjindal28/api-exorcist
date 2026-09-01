"""
Multi-source correlation: turning disagreeing signals into an inventory.

This is the analytical core of the discovery layer. Each connector is a
partial witness; this module reconciles them into one record per
endpoint and — critically — records *which sources failed to see it*.

The central insight of the project lives here. A zombie API is not
identified by any single positive observation. It is identified by a
pattern of absence:

    present in CODE                (the handler still exists)
  + present in DNS                 (it is still reachable)
  + absent from OPENAPI            (nobody documented it)
  + absent from GATEWAY            (nobody registered it)
  + absent/negligible in TRAFFIC   (nobody actually uses it)

No connector can conclude that on its own. Only the join can. This is
why the architecture aggregates six sources rather than relying on a
single scanner, and it is the concrete reason the project is not simply
"run a scanner and read the output".

The output of this module is the unified inventory: the input to the
classifier (`apix.engine`) and to the dependency graph (`apix.graph`).
"""

from __future__ import annotations

from collections import defaultdict
from collections.abc import Iterable
from dataclasses import asdict, dataclass, field
from typing import Any

from apix.connectors.base import DiscoverySignal, Source

# Below this many calls/day an endpoint is "effectively silent" even if
# traffic technically witnessed it. Catches endpoints kept alive only by
# health checks, crawlers or the occasional stray probe.
EFFECTIVELY_SILENT_THRESHOLD = 10


@dataclass
class InventoryRecord:
    """One endpoint, reconciled across every source that saw it."""

    endpoint_id: str
    service: str
    method: str
    path: str
    version: str

    # Which sources observed this endpoint
    seen_by: set[str] = field(default_factory=set)
    # Merged attributes, namespaced by source to preserve provenance
    evidence: dict[str, dict[str, Any]] = field(default_factory=dict)

    # ---- reconciled observable facts (populated by finalise()) ----
    in_openapi_spec: bool = False
    in_gateway_registry: bool = False
    observed_on_wire: bool = False
    handler_exists_in_code: bool = False
    dns_resolvable: bool = False
    deployed_via_pipeline: bool = False

    daily_calls: int = 0
    last_seen_days_ago: int | None = None
    distinct_callers: int = 0
    caller_services: list[str] = field(default_factory=list)
    owner_team: str | None = None
    auth_scheme: str | None = None
    data_classification: str | None = None
    spec_deprecated: bool = False
    days_since_last_commit: int | None = None
    first_deployed: str | None = None

    # ---- derived discrepancy flags: the actual detection signals ----
    flags: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        d = asdict(self)
        d["seen_by"] = sorted(self.seen_by)
        return d


class Correlator:
    """Merges DiscoverySignals into a unified inventory."""

    def __init__(self) -> None:
        self._records: dict[str, InventoryRecord] = {}

    def ingest(self, signals: Iterable[DiscoverySignal]) -> None:
        for s in signals:
            rec = self._records.get(s.endpoint_id)
            if rec is None:
                rec = InventoryRecord(
                    endpoint_id=s.endpoint_id,
                    service=s.service,
                    method=s.method,
                    path=s.path,
                    version=s.version,
                )
                self._records[s.endpoint_id] = rec
            rec.seen_by.add(s.source.value)
            # Preserve provenance rather than blindly overwriting, so we can
            # later explain *why* the system believes something.
            rec.evidence[s.source.value] = s.attributes

    def finalise(self) -> list[InventoryRecord]:
        for rec in self._records.values():
            self._reconcile(rec)
            self._derive_flags(rec)
        return sorted(self._records.values(), key=lambda r: (r.service, r.endpoint_id))

    # ------------------------------------------------------------------
    def _reconcile(self, rec: InventoryRecord) -> None:
        """Fold per-source attributes into a single view.

        Where sources conflict we prefer the observed over the declared:
        traffic beats gateway config for auth, because what actually
        happened on the wire is more trustworthy than what a config file
        claims. This matters — a gateway may declare OAuth2 on a route
        that the service also exposes directly without auth.
        """
        ev = rec.evidence
        gw = ev.get(Source.GATEWAY.value, {})
        spec = ev.get(Source.OPENAPI.value, {})
        traf = ev.get(Source.TRAFFIC.value, {})
        code = ev.get(Source.CODE.value, {})
        dns = ev.get(Source.DNS.value, {})
        cicd = ev.get(Source.CICD.value, {})

        rec.in_gateway_registry = bool(gw.get("registered", False))
        rec.in_openapi_spec = bool(spec.get("documented", False))
        rec.observed_on_wire = bool(traf.get("observed_on_wire", False))
        rec.handler_exists_in_code = bool(code.get("handler_exists_in_code", False))
        rec.dns_resolvable = bool(dns.get("dns_resolvable", False))
        rec.deployed_via_pipeline = bool(cicd.get("deployed_via_pipeline", False))

        # Usage: traffic is authoritative; fall back to gateway counters.
        rec.daily_calls = int(traf.get("daily_calls", gw.get("daily_calls", 0)) or 0)
        rec.last_seen_days_ago = traf.get("last_seen_days_ago")
        rec.distinct_callers = int(traf.get("distinct_callers", 0) or 0)
        rec.caller_services = list(traf.get("caller_services", []) or [])

        # Ownership: spec metadata first, then pipeline metadata.
        rec.owner_team = spec.get("owner_team") or cicd.get("pipeline_owner_team")

        # Auth: prefer what was observed on the wire over what was declared.
        rec.auth_scheme = (
            traf.get("observed_auth_scheme")
            or gw.get("auth_scheme")
            or spec.get("declared_auth")
            or code.get("declared_auth_in_code")
        )

        rec.data_classification = spec.get("data_classification")
        rec.spec_deprecated = bool(spec.get("spec_deprecated", False))
        rec.days_since_last_commit = code.get("days_since_last_commit")
        rec.first_deployed = cicd.get("first_deployed")

    # ------------------------------------------------------------------
    def _derive_flags(self, rec: InventoryRecord) -> None:
        """Derive the discrepancy flags that drive classification.

        These are deliberately *observations*, not verdicts. The classifier
        in `apix.engine.rules` consumes them, and `apix.engine.explain`
        surfaces them to the analyst as human-readable reasons.
        """
        f = rec.flags

        # --- documentation / registration gaps ---
        if rec.handler_exists_in_code and not rec.in_openapi_spec:
            f.append("UNDOCUMENTED")           # exists but not in the spec
        if rec.handler_exists_in_code and not rec.in_gateway_registry:
            f.append("UNREGISTERED")           # bypasses the gateway
        if not rec.in_openapi_spec and not rec.in_gateway_registry:
            f.append("SHADOW_CANDIDATE")       # invisible to both authorities

        # --- usage gaps ---
        if not rec.observed_on_wire:
            f.append("NO_TRAFFIC_IN_WINDOW")
        elif rec.daily_calls < EFFECTIVELY_SILENT_THRESHOLD:
            f.append("EFFECTIVELY_SILENT")
        if rec.last_seen_days_ago is None or (rec.last_seen_days_ago or 0) > 180:
            f.append("STALE_6M")

        # --- ownership gaps ---
        if rec.owner_team is None:
            f.append("NO_OWNER")

        # --- reachability: a dead endpoint that is still reachable is
        #     the dangerous combination ---
        if rec.dns_resolvable and not rec.observed_on_wire:
            f.append("REACHABLE_BUT_UNUSED")

        # --- security posture ---
        if rec.auth_scheme == "NONE":
            f.append("UNAUTHENTICATED")
        if rec.auth_scheme == "API_KEY":
            f.append("LEGACY_AUTH")
        if rec.data_classification in ("PII", "FINANCIAL"):
            f.append("SENSITIVE_DATA")

        # --- lifecycle ---
        if rec.spec_deprecated:
            f.append("MARKED_DEPRECATED")
        if (rec.days_since_last_commit or 0) > 365:
            f.append("CODE_UNTOUCHED_1Y")

        # --- deployment provenance ---
        if rec.handler_exists_in_code and not rec.deployed_via_pipeline:
            f.append("NO_PIPELINE_RECORD")

    # ------------------------------------------------------------------
    @staticmethod
    def coverage_report(records: list[InventoryRecord]) -> dict[str, Any]:
        """How much of the estate each source actually saw.

        This is a headline result for the report: it quantifies why
        single-source discovery is insufficient.
        """
        total = len(records)
        per_source: dict[str, int] = defaultdict(int)
        for r in records:
            for s in r.seen_by:
                per_source[s] += 1
        return {
            "total_endpoints": total,
            "per_source": {
                s: {"seen": n, "coverage_pct": round(100.0 * n / total, 1)}
                for s, n in sorted(per_source.items())
            },
            "only_found_by_correlation": sum(
                1 for r in records
                if "SHADOW_CANDIDATE" in r.flags
            ),
        }
