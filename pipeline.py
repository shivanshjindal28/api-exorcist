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

import argparse
import json
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from connectors.base import DiscoverySignal  # noqa: E402
from connectors.gateway import GatewayConnector, OpenAPIConnector  # noqa: E402
from connectors.discovery import (  # noqa: E402
    CICDConnector,
    CodeConnector,
    DNSConnector,
    TrafficConnector,
)
from ingestion.bus import (  # noqa: E402
    TOPIC_INVENTORY,
    TOPIC_RAW_SIGNALS,
    ElasticSink,
    LocalBus,
    get_bus,
)
from inventory.correlator import Correlator, InventoryRecord  # noqa: E402

CONNECTORS = [
    GatewayConnector,
    OpenAPIConnector,
    TrafficConnector,
    CodeConnector,
    DNSConnector,
    CICDConnector,
]

DATA_DIR = Path(__file__).resolve().parent / "data"


def run_discovery(verbose: bool = True) -> list[InventoryRecord]:
    """Execute the full discovery pipeline and return the inventory."""
    bus = get_bus()

    # ---- stage 1: collect from every source -------------------------
    total_signals = 0
    per_connector: dict[str, int] = {}
    for cls in CONNECTORS:
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
    DATA_DIR.mkdir(exist_ok=True)
    out = DATA_DIR / "inventory.json"
    out.write_text(json.dumps([r.to_dict() for r in records], indent=2))

    sink = ElasticSink()
    indexed = sink.index_records(r.to_dict() for r in records)

    if verbose:
        print("Stage 2 — correlation")
        print(f"  unified endpoints : {len(records)}")
        print(f"  written to        : {out.relative_to(Path.cwd()) if out.is_relative_to(Path.cwd()) else out}")
        if sink.available:
            print(f"  indexed to ES     : {indexed}")
        else:
            print("  Elasticsearch     : not available (file output used)")
        print()

    return records


def _rehydrate(bus) -> list[DiscoverySignal]:
    """Rebuild DiscoverySignal objects from bus messages."""
    from datetime import datetime

    from connectors.base import Source

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


def main() -> None:
    ap = argparse.ArgumentParser(description="API Exorcist discovery pipeline")
    ap.add_argument("--json", action="store_true", help="emit inventory as JSON")
    ap.add_argument("--coverage", action="store_true", help="per-source coverage only")
    ap.add_argument("--findings", action="store_true", help="show suspicious endpoints")
    args = ap.parse_args()

    quiet = args.json
    records = run_discovery(verbose=not quiet)

    if args.json:
        print(json.dumps([r.to_dict() for r in records], indent=2))
        return
    if args.coverage:
        print_coverage(records)
        return
    if args.findings:
        print_findings(records)
        return

    print_coverage(records)
    print_findings(records)


if __name__ == "__main__":
    main()
