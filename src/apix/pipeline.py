"""
API Exorcist — discovery pipeline (Weeks 4–5, the 50% deliverable).

Runs the full discovery half of the system end to end:

    connectors  ->  message bus  ->  correlation  ->  unified inventory

What this stage does NOT do, by design: it does not classify endpoints
(week 7), does not explain decisions (week 8), and does not act on
anything (week 9). It answers exactly one question — "what APIs exist
in this environment, and what does each source know about them?" —
which is the prerequisite for everything that follows.

Usage:
    python pipeline.py                 # run and print a summary
    python pipeline.py --json          # emit the inventory as JSON
    python pipeline.py --coverage      # show per-source coverage only
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import TYPE_CHECKING

from apix.config import load as load_settings
from apix.connectors.base import Connector, DiscoverySignal, Source

if TYPE_CHECKING:
    from apix.engine.verdict import Verdict
    from apix.ingestion.bus import MessageBus
from apix.connectors.discovery import (
    CICDConnector,
    CodeConnector,
    DNSConnector,
    TrafficConnector,
)
from apix.connectors.gateway import GatewayConnector, OpenAPIConnector
from apix.ingestion.bus import (
    TOPIC_INVENTORY,
    TOPIC_RAW_SIGNALS,
    ElasticSink,
    get_bus,
)
from apix.inventory.correlator import Correlator, InventoryRecord

CONNECTORS = [
    GatewayConnector,
    OpenAPIConnector,
    TrafficConnector,
    CodeConnector,
    DNSConnector,
    CICDConnector,
]



def run_discovery(
    verbose: bool = True,
    connectors: list[type[Connector]] | None = None,
    persist: bool = True,
) -> list[InventoryRecord]:
    """Execute the discovery pipeline and return the inventory.

    `connectors` defaults to all six. Passing a subset is how the comparative
    benchmark reproduces a conventional single-source approach: it runs the
    identical code path with fewer witnesses, so any difference in the result is
    attributable to the sources rather than to a different algorithm.

    `persist` is disabled by benchmark runs so a baseline configuration cannot
    overwrite the full pipeline's inventory on disk.
    """
    bus = get_bus()
    active_connectors = connectors if connectors is not None else CONNECTORS

    # ---- stage 1: collect from every source -------------------------
    total_signals = 0
    per_connector: dict[str, int] = {}
    for cls in active_connectors:
        conn = cls()
        signals: list[DiscoverySignal] = conn.run()
        per_connector[conn.name] = len(signals)
        for sig in signals:
            bus.publish(TOPIC_RAW_SIGNALS, sig.to_dict())
        total_signals += len(signals)
    bus.flush()

    if verbose:
        print("Stage 1 — collection")
        for name, n in per_connector.items():
            print(f"  {name:<18} {n:>3} signals")
        print(f"  {'TOTAL':<18} {total_signals:>3} signals\n")

    # ---- stage 2: correlate ------------------------------------------
    # Re-hydrate from the bus rather than reusing in-memory objects, so
    # the code path is identical whether transport is local or Kafka.
    correlator = Correlator()
    correlator.ingest(_rehydrate(bus))
    records = correlator.finalise()

    # ---- stage 3: publish inventory ----------------------------------
    for rec in records:
        bus.publish(TOPIC_INVENTORY, rec.to_dict())
    bus.flush()

    # Persist for the dashboard / downstream weeks
    out = load_settings().data_dir / "inventory.json"
    indexed = 0
    sink = ElasticSink()
    if persist:
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(json.dumps([r.to_dict() for r in records], indent=2))
        indexed = sink.index_records(r.to_dict() for r in records)

    if verbose:
        print("Stage 2 — correlation")
        print(f"  unified endpoints : {len(records)}")
        if persist:
            print(f"  written to        : {_display_path(out)}")
        if sink.available:
            print(f"  indexed to ES     : {indexed}")
        else:
            print("  Elasticsearch     : not available (file output used)")
        print()

    return records


def _display_path(p: Path) -> str:
    """Show a path relative to the user's location when that is shorter."""
    try:
        return str(p.relative_to(Path.cwd()))
    except ValueError:
        return str(p)


def _rehydrate(bus: MessageBus) -> list[DiscoverySignal]:
    """Rebuild DiscoverySignal objects from bus messages."""
    from datetime import datetime

    from apix.connectors.base import Source

    out: list[DiscoverySignal] = []
    for msg in bus.consume(TOPIC_RAW_SIGNALS):
        out.append(
            DiscoverySignal(
                source=Source(msg["source"]),
                endpoint_id=msg["endpoint_id"],
                service=msg["service"],
                method=msg["method"],
                path=msg["path"],
                version=msg["version"],
                observed_at=datetime.fromisoformat(msg["observed_at"]),
                attributes=msg["attributes"],
            )
        )
    return out


def print_coverage(records: list[InventoryRecord]) -> None:
    rep = Correlator.coverage_report(records)
    print("Per-source coverage of the estate")
    print(f"  total endpoints in unified inventory: {rep['total_endpoints']}\n")
    print(f"  {'source':<10}{'seen':>6}{'coverage':>11}")
    print("  " + "-" * 27)
    for src, d in rep["per_source"].items():
        print(f"  {src:<10}{d['seen']:>6}{d['coverage_pct']:>10}%")
    print()
    print(
        f"  endpoints invisible to BOTH authoritative sources "
        f"(gateway + spec): {rep['only_found_by_correlation']}"
    )
    print(
        "  -> these are the shadow/zombie candidates that no single\n"
        "     source could have surfaced alone."
    )
    print()


def print_findings(records: list[InventoryRecord]) -> None:
    """Highlight the endpoints a security team would care about."""
    suspicious = [
        r for r in records
        if "SHADOW_CANDIDATE" in r.flags or "REACHABLE_BUT_UNUSED" in r.flags
    ]
    print(f"Discovery findings — {len(suspicious)} endpoint(s) needing review\n")
    for r in sorted(suspicious, key=lambda x: (-_risk(x), x.endpoint_id)):
        risk = _risk(r)
        bar = "#" * risk + "." * (5 - risk)
        print(f"  [{bar}] {r.endpoint_id}")
        print(f"           service : {r.service}")
        print(f"           seen by : {', '.join(sorted(r.seen_by))}")
        print(f"           flags   : {', '.join(r.flags)}")
        print()


def _risk(r: InventoryRecord) -> int:
    """Crude 0-5 triage score for display ordering only.

    NOT the classifier — that arrives in week 7. This just orders the
    discovery output so the demo surfaces the scary things first.
    """
    score = 0
    if "SHADOW_CANDIDATE" in r.flags:
        score += 2
    if "UNAUTHENTICATED" in r.flags:
        score += 2
    if "SENSITIVE_DATA" in r.flags:
        score += 1
    if "NO_OWNER" in r.flags:
        score += 1
    return min(score, 5)


def sources_of(connectors: list[type[Connector]] | None = None) -> frozenset[Source]:
    """Which discovery sources a given connector set actually consults."""
    return frozenset(c.source for c in (connectors or CONNECTORS))


def run_classification(
    records: list[InventoryRecord],
    consulted: frozenset[Source] | None = None,
) -> list[Verdict]:
    """Classify the inventory and persist the explained verdicts.

    `consulted` must name the sources that actually ran. Passing None means all
    six, which is only true for a full scan of the simulated estate.
    """
    from apix.engine.explain import audit_entry
    from apix.engine.rules import RuleClassifier

    verdicts = RuleClassifier(consulted=consulted).classify_all(records)

    data_dir = load_settings().ensure_data_dir()
    (data_dir / "verdicts.json").write_text(
        json.dumps([audit_entry(v) for v in verdicts], indent=2)
    )
    return verdicts


def print_classification(
    verdicts: list[Verdict], explain_all: bool = False
) -> None:
    """Print the classification summary and per-verdict explanations."""
    from apix.engine.explain import explain, summarise

    print(summarise(verdicts))
    print()

    shown = verdicts if explain_all else [v for v in verdicts if v.risk_score > 0]
    shown = sorted(shown, key=lambda v: (-v.risk_score, -v.confidence, v.endpoint_id))

    heading = (
        "Every endpoint, explained"
        if explain_all
        else f"Endpoints requiring attention ({len(shown)})"
    )
    print(heading)
    print()
    for v in shown:
        print(explain(v))
        print()


# Argument parsing lives in apix.cli, which is the single entry point. This
# module stays importable as a library so the benchmark, the tests and any future
# API server can drive the pipeline without going through a command line.
if __name__ == "__main__":
    from apix.cli import main

    raise SystemExit(main(["scan", *__import__("sys").argv[1:]]))
