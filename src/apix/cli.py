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
    if args.github or args.local:
        return _scan_repository(args)

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


def _scan_repository(args: argparse.Namespace) -> int:
    """Scan a real GitHub repository, or a local checkout."""
    from apix.engine.explain import audit_entry, explain
    from apix.live import RepoError, scan_repository

    target = args.github or str(args.local)
    try:
        result = scan_repository(
            target, local_path=args.local, verbose=not args.json
        )
    except RepoError as exc:
        print(f"apix: {exc}", file=sys.stderr)
        return EXIT_ERROR

    if args.json:
        print(json.dumps(
            {
                "repository": result.slug,
                "commit": result.head_commit,
                "sources_consulted": sorted(s.value for s in result.consulted),
                "sources_unavailable": sorted(s.value for s in result.unavailable),
                "routes_found": result.routes_found,
                "verdicts": [audit_entry(v) for v in result.verdicts],
            },
            indent=2,
        ))
        return EXIT_FINDINGS if result.actionable else EXIT_OK

    print()
    print("=" * 74)
    print(f"REAL SCAN — {result.slug} @ {result.head_commit}")
    print("=" * 74)
    print()
    print(f"  route declarations found : {result.routes_found}")
    print(f"  unified endpoints        : {len(result.records)}")
    print(f"  OpenAPI specs parsed     : {len(result.spec_files)}"
          + (f"  {result.spec_files}" if result.spec_files else ""))
    print(f"  CI/CD workflows          : {result.workflow_count}")
    print(f"  CODEOWNERS rules         : {result.codeowners_rules}")
    print(f"  commits walked           : {result.total_commits}")
    print(f"  extractor                : {result.extractor}")
    if result.extractor_error:
        print(f"  extractor error          : {result.extractor_error}")
    print()

    # Path composition is the part most likely to be subtly wrong, so say what
    # was and was not resolved rather than presenting every path as absolute.
    if result.mount_prefixes:
        print(f"  mount prefix applied     : {', '.join(result.mount_prefixes)}")
    else:
        print("  mount prefix             : none found as a literal")
        print("    -> paths are relative to the API root. A project that mounts")
        print("       with a variable (prefix=settings.API_V1_STR) needs")
        print("       cross-module constant resolution, which is not implemented.")
    print()

    # State plainly what this scan could not see. A repository has no traffic
    # sensor and no gateway; pretending otherwise is how a tool invents zombies.
    print("  sources consulted   : "
          + ", ".join(sorted(s.value for s in result.consulted)))
    print("  sources UNAVAILABLE : "
          + ", ".join(sorted(s.value for s in result.unavailable)))
    print("    -> rules depending on those abstain. Nothing here is a removal")
    print("       candidate, because real usage was never measured.")
    print()

    if not result.records:
        print("  No HTTP routes found. This repository may not serve an API,")
        print("  or may use a framework the extractor does not yet cover.")
        print()
        return EXIT_OK

    from collections import Counter

    counts = Counter(v.label.value for v in result.verdicts)
    print("  Classification (on partial evidence):")
    for label, n in counts.most_common():
        print(f"    {label:<11} {n:>4}")
    print()

    flagged = sorted(
        (v for v in result.verdicts if v.risk_score > 0),
        key=lambda v: (-v.risk_score, v.endpoint_id),
    )[: args.limit]
    if flagged:
        print(f"  Endpoints worth review (showing {len(flagged)}):")
        print()
        for v in flagged:
            print(explain(v, indent="  "))
            if v.blocked_reason:
                print(f"          note    : {v.blocked_reason}")
            print()

    return EXIT_FINDINGS if result.actionable else EXIT_OK


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
    scan.add_argument(
        "--github",
        metavar="OWNER/REPO",
        help="scan a real GitHub repository instead of the simulated estate",
    )
    scan.add_argument(
        "--local",
        metavar="PATH",
        help="scan an already-cloned repository on disk",
    )
    scan.add_argument(
        "--limit",
        type=int,
        default=15,
        help="how many flagged endpoints to explain (default 15)",
    )
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
