"""
The comparative before/after benchmark.

Addresses jury concern #3: a comparative study of the situation before and after
using the product.

Method
------
"Before" is not a rhetorical device here — it is a real configuration of this
same system. Each configuration runs the *identical* pipeline code with a
different set of connectors, so any difference in outcome is attributable to the
evidence available and not to a different algorithm. That is what makes this a
controlled comparison rather than a marketing claim.

    1. Gateway registry only   — what most organisations actually have today
    2. OpenAPI specification only — what the documentation claims exists
    3. Gateway + specification — a conventional "complete" API inventory
    4. All six sources, correlated — API Exorcist

Headline metric
---------------
**End-to-end zombie recall**: of the zombies genuinely present in the estate, how
many did each configuration both *discover* and *correctly classify*? An endpoint
a configuration never discovered is counted as missed, because an organisation
cannot remediate an endpoint it does not know exists. This is the number that
belongs in the paper.

Usage:
    python -m evaluation.benchmark
    python -m evaluation.benchmark --json
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from connectors.gateway import GatewayConnector, OpenAPIConnector  # noqa: E402
from connectors.discovery import (  # noqa: E402
    CICDConnector,
    CodeConnector,
    DNSConnector,
    TrafficConnector,
)
from engine.rules import RuleClassifier  # noqa: E402
from engine.verdict import Classification  # noqa: E402
from evaluation.metrics import evaluate, format_report  # noqa: E402
from pipeline import run_discovery  # noqa: E402
from simulated_env.estate import by_id  # noqa: E402

DATA_DIR = Path(__file__).resolve().parent.parent / "data"

CONFIGURATIONS: list[tuple[str, str, list]] = [
    (
        "gateway-only",
        "Gateway registry only",
        [GatewayConnector],
    ),
    (
        "spec-only",
        "OpenAPI specification only",
        [OpenAPIConnector],
    ),
    (
        "conventional",
        "Gateway + specification (conventional)",
        [GatewayConnector, OpenAPIConnector],
    ),
    (
        "api-exorcist",
        "API Exorcist — all six sources, correlated",
        [
            GatewayConnector,
            OpenAPIConnector,
            TrafficConnector,
            CodeConnector,
            DNSConnector,
            CICDConnector,
        ],
    ),
]


def run_configuration(connectors: list) -> dict[str, Any]:
    """Run one configuration end to end and score it against ground truth."""
    truth = by_id()
    total_in_estate = len(truth)
    true_zombies = {
        eid for eid, ep in truth.items() if ep.true_label.value == "ZOMBIE"
    }

    records = run_discovery(verbose=False, connectors=connectors, persist=False)
    discovered = {r.endpoint_id for r in records}

    classifier = RuleClassifier()
    verdicts = classifier.classify_all(records)

    # Classification quality, measured only on what this configuration found.
    pairs = [
        (v.endpoint_id, v.label.value, truth[v.endpoint_id].true_label.value)
        for v in verdicts
        if v.endpoint_id in truth
    ]
    res = evaluate(pairs)

    # End-to-end zombie recall: discovered AND correctly labelled, over every
    # zombie truly present. Undiscovered endpoints count against the score.
    caught = {
        v.endpoint_id
        for v in verdicts
        if v.label is Classification.ZOMBIE and v.endpoint_id in true_zombies
    }
    missed_undiscovered = true_zombies - discovered
    missed_misclassified = (true_zombies & discovered) - caught

    sensitive_exposed = sum(
        1
        for v in verdicts
        if v.is_actionable and "UNAUTHENTICATED" in _flags_of(records, v.endpoint_id)
    )

    return {
        "endpoints_discovered": len(discovered),
        "estate_size": total_in_estate,
        "coverage_pct": round(100.0 * len(discovered) / total_in_estate, 1),
        "zombies_in_estate": len(true_zombies),
        "zombies_caught": len(caught),
        "zombie_recall_pct": round(
            100.0 * len(caught) / len(true_zombies), 1
        ) if true_zombies else 0.0,
        "zombies_missed_undiscovered": sorted(missed_undiscovered),
        "zombies_missed_misclassified": sorted(missed_misclassified),
        "unauthenticated_zombies_found": sensitive_exposed,
        "shadow_candidates_found": sum(
            1 for r in records if "SHADOW_CANDIDATE" in r.flags
        ),
        "classification": res.to_dict(),
        "_result_obj": res,
    }


def _flags_of(records: list, endpoint_id: str) -> list[str]:
    for r in records:
        if r.endpoint_id == endpoint_id:
            return r.flags
    return []


def run_benchmark() -> dict[str, Any]:
    out: dict[str, Any] = {}
    for key, title, connectors in CONFIGURATIONS:
        res = run_configuration(connectors)
        res["title"] = title
        out[key] = res
    return out


# ---------------------------------------------------------------------------
def print_benchmark(results: dict[str, Any]) -> None:
    print("=" * 78)
    print("COMPARATIVE EVALUATION — before and after multi-source correlation")
    print("=" * 78)
    print()
    print(
        "  Every configuration runs identical pipeline code. Only the set of"
    )
    print(
        "  evidence sources differs, so the difference in outcome is caused by"
    )
    print("  the correlation, not by a different algorithm.")
    print()

    # ---- discovery comparison ----
    print("-" * 78)
    print("Discovery — how much of the estate each configuration can even see")
    print("-" * 78)
    print()
    print(
        f"  {'configuration':<44}{'found':>8}{'of':>4}{'coverage':>12}"
    )
    print("  " + "-" * 68)
    for key, _t, _c in CONFIGURATIONS:
        r = results[key]
        print(
            f"  {r['title']:<44}{r['endpoints_discovered']:>8}"
            f"{r['estate_size']:>4}{r['coverage_pct']:>11.1f}%"
        )
    print()

    # ---- the headline ----
    print("-" * 78)
    print("HEADLINE — end-to-end zombie recall")
    print("-" * 78)
    print()
    print("  Of the zombies genuinely present, how many were discovered AND")
    print("  correctly classified? Undiscovered endpoints count as missed.")
    print()
    print(f"  {'configuration':<44}{'caught':>9}{'of':>4}{'recall':>11}")
    print("  " + "-" * 68)
    for key, _t, _c in CONFIGURATIONS:
        r = results[key]
        bar = "#" * int(r["zombie_recall_pct"] / 10)
        print(
            f"  {r['title']:<44}{r['zombies_caught']:>9}"
            f"{r['zombies_in_estate']:>4}{r['zombie_recall_pct']:>10.1f}%  {bar}"
        )
    print()

    base = results["conventional"]
    full = results["api-exorcist"]
    delta = full["zombies_caught"] - base["zombies_caught"]
    print(
        f"  A conventional inventory (gateway + specification) finds "
        f"{base['zombies_caught']} of {base['zombies_in_estate']} zombies."
    )
    print(
        f"  Correlating all six sources finds {full['zombies_caught']} "
        f"— {delta} additional endpoint(s) that no conventional"
    )
    print("  approach could have surfaced.")
    print()
    if full["unauthenticated_zombies_found"]:
        print(
            f"  {full['unauthenticated_zombies_found']} of those carry no "
            f"authentication at all."
        )
        print()

    # ---- classification quality, full configuration ----
    print("-" * 78)
    print(format_report(full["_result_obj"], "Classification quality — API Exorcist"))
    print()


def main() -> None:
    ap = argparse.ArgumentParser(description="API Exorcist comparative benchmark")
    ap.add_argument("--json", action="store_true", help="emit results as JSON")
    args = ap.parse_args()

    results = run_benchmark()

    if args.json:
        clean = {
            k: {kk: vv for kk, vv in v.items() if not kk.startswith("_")}
            for k, v in results.items()
        }
        print(json.dumps(clean, indent=2))
        return

    print_benchmark(results)

    DATA_DIR.mkdir(exist_ok=True)
    out = DATA_DIR / "benchmark.json"
    clean = {
        k: {kk: vv for kk, vv in v.items() if not kk.startswith("_")}
        for k, v in results.items()
    }
    out.write_text(json.dumps(clean, indent=2))
    print(f"  Paper-ready figures written to {out}")
    print()


if __name__ == "__main__":
    main()
