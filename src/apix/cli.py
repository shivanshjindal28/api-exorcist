"""
The `apix` command-line interface.

Subcommands rather than flags on a single script, because the tool does several
genuinely different jobs and a user should be able to discover them with
``apix --help`` rather than by reading source.

    apix scan                  discover, classify and explain
    apix benchmark             the comparative before/after evaluation
    apix dataset               build the labelled dataset for the ML engine
    apix version               version and resolved configuration

Exit codes follow the convention a CI pipeline expects:

    0   completed, nothing requiring action
    1   completed, action required (zombies found)
    2   usage or runtime error

That distinction is what lets `apix scan` be dropped into a pipeline as a gate.
"""

from __future__ import annotations

import argparse
import json
import sys

from apix import __version__
from apix.config import load as load_settings

EXIT_OK = 0
EXIT_FINDINGS = 1
EXIT_ERROR = 2


def _cmd_scan(args: argparse.Namespace) -> int:
    from apix.pipeline import (
        print_classification,
        print_coverage,
        print_findings,
        run_classification,
        run_discovery,
    )

    quiet = args.json
    records = run_discovery(verbose=not quiet)

    if args.json:
        print(json.dumps([r.to_dict() for r in records], indent=2))
        return EXIT_OK
    if args.coverage:
        print_coverage(records)
        return EXIT_OK
    if args.findings:
        print_findings(records)
        return EXIT_OK

    verdicts = run_classification(records)
    if not args.classify_only:
        print_coverage(records)
    print_classification(verdicts, explain_all=args.explain_all)

    return EXIT_FINDINGS if any(v.is_actionable for v in verdicts) else EXIT_OK


def _cmd_benchmark(args: argparse.Namespace) -> int:
    from apix.evaluation.benchmark import print_benchmark, run_benchmark

    results = run_benchmark()
    if args.json:
        clean = {
            k: {kk: vv for kk, vv in v.items() if not kk.startswith("_")}
            for k, v in results.items()
        }
        print(json.dumps(clean, indent=2))
        return EXIT_OK

    print_benchmark(results)
    out = load_settings().ensure_data_dir() / "benchmark.json"
    clean = {
        k: {kk: vv for kk, vv in v.items() if not kk.startswith("_")}
        for k, v in results.items()
    }
    out.write_text(json.dumps(clean, indent=2))
    print(f"  Paper-ready figures written to {out}")
    print()
    return EXIT_OK


def _cmd_dataset(args: argparse.Namespace) -> int:
    from apix.dataset.build import main as build_main

    build_main()
    return EXIT_OK


def _cmd_version(args: argparse.Namespace) -> int:
    s = load_settings()
    print(f"apix {__version__}")
    print()
    print("Resolved configuration:")
    print(f"  data directory      : {s.data_dir}")
    print(f"  message bus         : {s.bus_backend}")
    print(f"  traffic window      : {s.traffic_window_days} days")
    print(f"  traffic threshold   : {s.meaningful_traffic_threshold} calls/day")
    if s.bus_backend == "kafka":
        print(f"  kafka bootstrap     : {s.kafka_bootstrap}")
    return EXIT_OK


def build_parser() -> argparse.ArgumentParser:
    ap = argparse.ArgumentParser(
        prog="apix",
        description=(
            "API Exorcist — discover, classify and safely eliminate zombie, "
            "shadow and orphaned APIs."
        ),
    )
    ap.add_argument("--version", action="version", version=f"apix {__version__}")
    sub = ap.add_subparsers(dest="command", metavar="<command>")

    scan = sub.add_parser("scan", help="discover, classify and explain")
    scan.add_argument("--json", action="store_true", help="emit inventory as JSON")
    scan.add_argument("--coverage", action="store_true", help="per-source coverage only")
    scan.add_argument(
        "--findings", action="store_true", help="raw discovery flags, unclassified"
    )
    scan.add_argument(
        "--classify-only", action="store_true", help="skip the coverage table"
    )
    scan.add_argument(
        "--explain-all",
        action="store_true",
        help="explain every endpoint, not only those needing attention",
    )
    scan.set_defaults(func=_cmd_scan)

    bench = sub.add_parser(
        "benchmark", help="comparative before/after evaluation"
    )
    bench.add_argument("--json", action="store_true", help="emit results as JSON")
    bench.set_defaults(func=_cmd_benchmark)

    ds = sub.add_parser("dataset", help="build the labelled ML dataset")
    ds.set_defaults(func=_cmd_dataset)

    ver = sub.add_parser("version", help="version and resolved configuration")
    ver.set_defaults(func=_cmd_version)

    return ap


def main(argv: list[str] | None = None) -> int:
    ap = build_parser()
    args = ap.parse_args(argv)

    if not getattr(args, "func", None):
        ap.print_help()
        return EXIT_ERROR

    try:
        return int(args.func(args))
    except KeyboardInterrupt:
        print("\ninterrupted", file=sys.stderr)
        return EXIT_ERROR
    except Exception as exc:  # pragma: no cover - top-level safety net
        print(f"apix: {exc}", file=sys.stderr)
        return EXIT_ERROR


if __name__ == "__main__":
    sys.exit(main())
