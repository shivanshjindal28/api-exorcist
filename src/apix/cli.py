"""
The `apix` command-line interface.

Subcommands rather than flags on a single script, because the tool does several
genuinely different jobs and a user should be able to discover them with
``apix --help`` rather than by reading source.

    apix scan                  discover, classify and explain
    apix scan --github O/R     scan a real GitHub repository
    apix impact                dependency graph, blast radius, removal gate
    apix safekill              shadow, approval, canary and rollback (Phase 4)
    apix serve                 the REST API (Phase 5)
    apix token NAME            mint an API token for a named principal
    apix enforce --base REF    fail a change that adds an undocumented,
                               unowned or orphaned endpoint (Phase 6)
    apix benchmark             the comparative before/after evaluation
    apix train                 train the model and compare it against the rules
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
import os
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

    verdicts = run_classification(records, use_model=args.model)
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
    print(f"REAL SCAN: {result.slug} @ {result.head_commit}")
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

    lifecycle_ok = any(v.supports_lifecycle_claim for v in result.verdicts)
    if lifecycle_ok:
        counts = Counter(v.label.value for v in result.verdicts)
        print("  Classification:")
        for label, n in counts.most_common():
            print(f"    {label:<11} {n:>4}")
    else:
        # Every lifecycle class is defined in terms of use, and this scan has no
        # usage data. Reporting a class histogram here would be inventing one.
        print("  Lifecycle classification: NOT AVAILABLE")
        print("    Every class (active / deprecated / orphaned / zombie) is")
        print("    defined by usage, and no traffic source was consulted.")
    print()

    total = len(result.verdicts)
    finding_counts: Counter[str] = Counter()
    for v in result.verdicts:
        finding_counts.update(v.findings)

    # A finding that holds for every endpoint is a fact about the repository,
    # not about any endpoint in it. Repeating "no CODEOWNERS file" once per
    # route buries the findings that actually differ, which is the opposite of
    # triage. Separate them.
    universal = {s for s, n in finding_counts.items() if n == total and total}
    if universal:
        print("  Repository-level: true of all "
              f"{total} endpoint(s), so it distinguishes none of them:")
        for statement in sorted(universal):
            print(f"    · {statement}")
        print()

    distinguishing = {
        s: n for s, n in finding_counts.items() if s not in universal
    }
    if distinguishing:
        print("  Endpoint-level: these differ between endpoints:")
        for statement, n in Counter(distinguishing).most_common(10):
            print(f"    {n:>4}/{total}  {statement}")
    else:
        print("  Endpoint-level: none. Every endpoint carries exactly the same")
        print("  findings, so this scan cannot rank them against each other.")
        print("  Connect a traffic source, or add CODEOWNERS and a published")
        print("  specification, to get signal that varies per endpoint.")
    print()

    if result.total_commits < 20:
        print(f"  NOTE: only {result.total_commits} commit(s) of history. Staleness")
        print("  signals are computed from commit dates and mean little here.")
        print()

    # Only worth listing individually when an endpoint has something the others
    # do not. Otherwise the list is the same paragraph repeated.
    candidates = [
        v for v in result.verdicts
        if args.explain_all or (v.risk_score > 0 and (set(v.findings) - universal))
    ]
    flagged = sorted(
        candidates, key=lambda v: (-v.risk_score, v.endpoint_id)
    )[: args.limit if args.limit else None]

    if flagged:
        print(f"  Endpoints worth review (showing {len(flagged)}):")
        print()
        for v in flagged:
            print(explain(v, indent="  "))
            if v.blocked_reason:
                print(f"          note    : {v.blocked_reason}")
            print()
    elif universal:
        print(f"  No endpoint stands out: all {total} share the same findings.")
        print("  Listing them individually would repeat one paragraph "
              f"{total} times.")
        print("  Use --explain-all to see them anyway.")
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


def _cmd_impact(args: argparse.Namespace) -> int:
    """Dependency graph and blast-radius analysis."""
    from apix.graph import assess_removals, build_graph
    from apix.pipeline import run_classification, run_discovery, sources_of

    records = run_discovery(verbose=False)
    verdicts = run_classification(records, consulted=sources_of())
    graph = build_graph(records)
    stats = graph.stats()

    try:
        if args.endpoint:
            radius = graph.blast_radius(args.endpoint, args.depth)
            if args.json:
                print(json.dumps(radius.to_dict(), indent=2))
                return EXIT_OK
            _print_radius(radius)
            return EXIT_OK

        assessments = assess_removals(verdicts, graph, args.depth)
        if args.json:
            print(json.dumps(
                {
                    "graph": stats,
                    "assessments": [a.to_dict() for a in assessments],
                },
                indent=2,
            ))
            return EXIT_OK

        print()
        print("=" * 74)
        print("DEPENDENCY GRAPH: what would break")
        print("=" * 74)
        print()
        print(f"  backend            : {graph.name}")
        print(f"  endpoints          : {stats['endpoints']}")
        print(f"  services           : {stats['services']}")
        print(f"  observed call edges: {stats['call_edges']}")
        print(f"  isolated endpoints : {stats['isolated_endpoints']}")
        print()
        print("  An endpoint nothing calls is a removal candidate. One that")
        print("  something still calls is blocked, however dead it looks.")
        print()

        clear = [a for a in assessments if a.may_proceed]
        blocked = [a for a in assessments if not a.may_proceed]

        print(f"  CLEARED FOR SAFE KILL: {len(clear)}")
        for a in clear:
            print(f"    [ok]      {a.verdict.endpoint_id}")
            print("              nothing observed depends on it")
        print()
        print(f"  BLOCKED: {len(blocked)}")
        for a in blocked:
            print(f"    [blocked] {a.verdict.endpoint_id}")
            print(f"              {a.blocked_by}")
        print()
        return EXIT_OK
    finally:
        graph.close()


def _print_radius(radius: object) -> None:
    r = radius  # typed loosely; BlastRadius is a frozen dataclass
    print()
    print(f"Blast radius: {r.endpoint_id}")  # type: ignore[attr-defined]
    print("-" * 74)
    if r.is_isolated:  # type: ignore[attr-defined]
        print("  isolated: nothing observed calls this endpoint.")
        print("  Note: a caller silent during the capture window is invisible")
        print("  here, which is why approval and canary rollout still apply.")
        print()
        return
    print(f"  severity         : {r.severity}")            # type: ignore[attr-defined]
    print(f"  depth reached    : {r.depth_reached} hop(s)")  # type: ignore[attr-defined]
    print(f"  direct callers   : {', '.join(r.direct_services) or 'none'}")  # type: ignore[attr-defined]
    if r.indirect_services:  # type: ignore[attr-defined]
        print(f"  reached onward   : {', '.join(r.indirect_services)}")  # type: ignore[attr-defined]
    if r.affected_endpoints:  # type: ignore[attr-defined]
        affected = r.affected_endpoints  # type: ignore[attr-defined]
        print(f"  endpoints degraded: {len(affected)}")
        shown = 12
        for ep, hop in affected[:shown]:
            print(f"      hop {hop}  {ep}")
        if len(affected) > shown:
            # A truncated list that does not say it is truncated is how the
            # demo script came to report 12 when the real figure was 13.
            print(f"      ... and {len(affected) - shown} more")
    print()


def _cmd_safekill(args: argparse.Namespace) -> int:
    """Safe Kill: walk every removal candidate through shadow, approval, canary."""
    from pathlib import Path

    from apix.safekill import (
        AuditLog,
        NamedApprover,
        NoApprover,
        SafeKillController,
        SafeKillPolicy,
        verify_file,
    )

    if args.verify:
        check = verify_file(Path(args.verify))
        if check.ok:
            print(f"  chain verifies: {check.entries} entries, no break")
            return EXIT_OK
        print(f"  CHAIN BROKEN at entry {check.broken_at}: {check.problem}")
        return EXIT_FINDINGS

    if args.evaluate:
        return _safekill_evaluate(args.evaluate, args.json)

    from apix.graph import assess_removals, build_graph
    from apix.pipeline import run_classification, run_discovery, sources_of
    from apix.simulated_env.enforcement import HIDDEN_CALLER, SimulatedEnforcement
    from apix.simulated_env.estate import ESTATE

    policy = SafeKillPolicy(min_detectable_rate=1 / args.slowest_caller_days)
    records = run_discovery(verbose=False)
    verdicts = run_classification(records, consulted=sources_of(), use_model=args.model)
    graph = build_graph(records)
    try:
        assessments = assess_removals(verdicts, graph)
    finally:
        graph.close()
    if args.endpoint:
        assessments = [a for a in assessments if a.verdict.endpoint_id == args.endpoint]
        if not assessments:
            print(f"  {args.endpoint} is not a removal candidate (not classified ZOMBIE)")
            return EXIT_ERROR

    audit_path = Path(args.audit) if args.audit else (
        load_settings().ensure_data_dir() / "safekill-audit.jsonl"
    )
    audit = AuditLog(path=audit_path)
    before = len(audit.entries)
    approver = (
        NamedApprover(args.approve_as, accept_unidentified=args.accept_unidentified)
        if args.approve_as else NoApprover()
    )
    hidden = {ep: HIDDEN_CALLER for ep in (args.hidden_caller or [])}
    backend = SimulatedEnforcement(ESTATE, seed=args.seed, hidden_callers=hidden)
    controller = SafeKillController(
        backend=backend,
        audit=audit,
        policy=policy,
        approver=approver,
    )
    outcomes = controller.run_all(assessments)
    chain = audit.verify()

    if args.json:
        print(json.dumps({
            "policy": {"shadow_days": policy.shadow_days,
                       "canary_days": list(policy.canary_days)},
            "approver": args.approve_as,
            "outcomes": [o.to_dict() for o in outcomes],
            "audit": {"path": str(audit_path), "entries": len(audit.entries),
                      "appended": len(audit.entries) - before,
                      "chain_ok": chain.ok, "head": audit.head},
        }, indent=2))
        return EXIT_OK if chain.ok else EXIT_FINDINGS

    print()
    print("=" * 74)
    print("SAFE KILL")
    print("=" * 74)
    print()
    print("  simulated gateway over the simulated estate: nothing real is touched")
    print()
    print(f"  shadow   : {policy.shadow_days:g} days, nothing refused, every request "
          f"recorded")
    print(f"             (catches a 1-in-{args.slowest_caller_days:g}-day caller with "
          f"{policy.confidence:.0%} confidence)")
    print("  canary   : 5% / 25% / 100% for "
          + " / ".join(f"{d:g}" for d in policy.canary_days)
          + " days, rolled back automatically on a breach")
    for ep in hidden:
        name, every = HIDDEN_CALLER
        print(f"  WHAT-IF  : {ep} has a hidden caller, {name},")
        print(f"             calling every {every:g} days. The traffic capture never")
        print("             saw it, so classifier and graph both cleared this endpoint.")
    if hidden:
        print()
    if args.approve_as:
        extra = ", including unidentified traffic" if args.accept_unidentified else ""
        print(f"  approver : {args.approve_as}{extra}")
    else:
        print("  approver : none. Nothing will be removed; re-run with --approve-as NAME")
    print()

    for o in outcomes:
        state = o.state.value.lower().replace("_", " ")
        print(f"  {o.endpoint_id:<42} {state:<18} {o.days:>4g} days")
        if o.shadow is not None:
            sh = o.shadow
            who = (", ".join(f"{c} ({n})" for c, n in sorted(sh.identified.items()))
                   or "no identified caller")
            print(f"      shadow : {sh.requests} request(s); {who}; "
                  f"{sh.unidentified} unidentified")
        if o.canary and not o.breach_kind and all(not c.refused_total for c in o.canary):
            print("      canary : clean at 5% / 25% / 100%")
        else:
            for i, c in enumerate(o.canary):
                print(f"      canary {c.refuse_fraction:>4.0%}: {c.refused_total} refused "
                      f"of {c.requests}")
                if i == len(o.canary) - 1 and o.breach_kind:
                    print(f"      -> rolled back automatically ({o.breach_kind} breach)")
        if o.state.value in ("BLOCKED", "REJECTED", "DENIED", "ROLLED_BACK"):
            print(f"      {o.reason}")
        print()

    # What actually happened to the hidden caller. A real controller cannot
    # know this, and this one does not: it is read from the simulated world's
    # harm ledger, after the run, purely so a what-if can show its consequence.
    for ep in hidden:
        name, _ = HIDDEN_CALLER
        refused = backend.harm.genuine_refused.get(ep, 0)
        print("  CONSEQUENCE (visible only because this is a simulation):")
        if ep in backend.harm.retired_with_live_caller:
            print(f"    {ep} was RETIRED while {name} still depends on it.")
            print("    Its next month-end run fails. This is the outage Safe Kill exists")
            print("    to prevent, and the shadow window was too short to catch it.")
        elif refused:
            print(f"    {refused} real request(s) from {name} were refused before the")
            print("    automatic rollback restored the endpoint. Caught, at a cost.")
        else:
            print(f"    {name} was never refused. Caught with no harm at all.")
        print()

    counts: dict[str, int] = {}
    for o in outcomes:
        counts[o.state.value] = counts.get(o.state.value, 0) + 1
    print("  " + "  ".join(f"{k.lower().replace('_', ' ')}: {v}"
                           for k, v in sorted(counts.items())))
    print()
    print(f"  audit    : {len(audit.entries) - before} entries appended to {audit_path}")
    print(f"             {len(audit.entries)} in total; chain "
          + ("verifies" if chain.ok else f"BROKEN at entry {chain.broken_at}"))
    print(f"             head {audit.head[:16]}...")
    print()
    return EXIT_OK if chain.ok else EXIT_FINDINGS


def _safekill_evaluate(n_estates: int, as_json: bool) -> int:
    from apix.evaluation.safekill_eval import (
        evaluate,
        format_report,
        format_sweep,
        sweep,
    )

    report = evaluate(n_estates)
    reports = sweep(n_estates=n_estates)
    data = {"default": report.to_dict(), "sweep": [r.to_dict() for r in reports]}
    out = load_settings().ensure_data_dir() / "safekill-eval.json"
    out.write_text(json.dumps(data, indent=2))
    if as_json:
        print(json.dumps(data, indent=2))
        return EXIT_OK
    print(format_report(report))
    print(format_sweep(reports))
    print(f"  Figures written to {out}")
    print()
    return EXIT_OK


def _cmd_serve(args: argparse.Namespace) -> int:
    """Run the REST API."""
    import getpass
    import ipaddress
    import os
    from pathlib import Path

    from apix.api.auth import Role, TokenConfigError, TokenStore, new_token

    try:
        loopback = ipaddress.ip_address(args.host).is_loopback
    except ValueError:
        loopback = args.host == "localhost"
    if not loopback and not args.allow_remote:
        print(f"  refusing to bind {args.host}: bearer tokens over plain HTTP travel")
        print("  in cleartext. Put the API behind TLS termination, then pass")
        print("  --allow-remote to confirm.")
        return EXIT_ERROR

    spec = os.environ.get("APIX_API_TOKENS", "")
    session_token = None
    try:
        tokens = TokenStore.parse(spec)
    except TokenConfigError as exc:
        print(f"  APIX_API_TOKENS is malformed: {exc}")
        return EXIT_ERROR
    if not tokens and not loopback:
        # A one-time token is printed to stdout. On a laptop that is a terminal;
        # in a container it is a log pipeline, retained and readable by whoever
        # reads logs. A served deployment must be given its principals.
        print("  refusing to mint a one-time token for a non-loopback bind: it would")
        print("  be written to stdout, which in a deployment is retained log storage.")
        print("  Set APIX_API_TOKENS; `apix token NAME --role approver` makes an entry.")
        return EXIT_ERROR
    # The port is settled before anything else starts. Found the hard way: a
    # previous `apix serve` still holding 8600 made the new one fail to bind
    # *after* it had already sent the browser to the old server, with a token
    # the old server had never seen.
    chosen = _choose_port(args.host, args.port)
    if chosen is None:
        print(f"  port {args.port} on {args.host} is already in use, probably by another")
        print("  API Exorcist that is still running. Close that one, or choose a free")
        print("  port with --port.")
        return EXIT_ERROR
    if args.port is None and chosen != DEFAULT_PORT:
        print(f"  port {DEFAULT_PORT} is in use (another API Exorcist still running?);")
        print(f"  using {chosen} instead.")
    args.port = chosen

    # Configuration is checked first: it is the more useful error.
    try:
        import uvicorn

        from apix.api.app import default_app
    except ImportError as exc:
        # Name the module. "Needs its extra" alone hid that the missing piece
        # was PyYAML, not the API extra, when the container failed to start.
        print(f"  cannot start the API: {exc}.")
        print('  Install it with: pip install -e ".[api]"')
        return EXIT_ERROR

    from apix.api.observe import configure_logging, log

    if not tokens:
        # No configured principals: mint one for this process only, the way
        # Jupyter does, rather than starting an unauthenticated server.
        session_token = new_token()
        tokens = TokenStore.single(args.as_name or getpass.getuser(),
                                   Role.APPROVER, session_token)

    audit_path = Path(args.audit) if args.audit else (
        load_settings().ensure_data_dir() / "safekill-audit.jsonl"
    )
    app = default_app(audit_path, tokens, seed=args.seed, use_model=args.model,
                      docs=not args.no_docs)
    log_config = configure_logging(args.log_format)

    if args.log_format == "json":
        # Plain banner lines would break a JSON log pipeline; one event instead.
        import logging.config

        logging.config.dictConfig(log_config)
        log.info("serve.start", extra={"fields": {
            "listening": f"http://{args.host}:{args.port}",
            "audit_log": str(audit_path),
            "estate": "simulated",
            "principals": len(tokens.entries),
            "docs": not args.no_docs,
        }})
        uvicorn.run(app, host=args.host, port=args.port, log_config=log_config,
                    server_header=False)
        return EXIT_OK

    print()
    print("=" * 74)
    print("API EXORCIST REST API")
    print("=" * 74)
    print()
    print(f"  listening : http://{args.host}:{args.port}")
    print(f"  docs      : http://{args.host}:{args.port}/docs"
          + ("  (disabled)" if args.no_docs else ""))
    print(f"  metrics   : http://{args.host}:{args.port}/metrics  (needs a token)")
    print(f"  audit log : {audit_path}")
    print("  estate    : simulated; nothing real is touched")
    if session_token:
        who = tokens.entries[0][1].name
        print()
        print(f"  No APIX_API_TOKENS set. A one-time approver token for {who!r},")
        print("  valid only while this process runs (shown once, never stored):")
        print()
        print(f"      {session_token}")
        print()
        print("  Send it as:  Authorization: Bearer <token>")
    else:
        print(f"  principals: {len(tokens.entries)} from APIX_API_TOKENS")
    print()
    if not args.no_browser:
        _open_dashboard_when_ready(args.host, args.port, session_token)
        print("  Opening the dashboard in your browser. Leave this terminal open;")
        print("  closing it (or Ctrl+C) stops API Exorcist.")
        print()
    uvicorn.run(app, host=args.host, port=args.port, log_config=log_config,
                server_header=False)
    return EXIT_OK


DEFAULT_PORT = 8600


def _port_free(host: str, port: int) -> bool:
    import socket

    family = socket.AF_INET6 if ":" in host else socket.AF_INET
    with socket.socket(family, socket.SOCK_STREAM) as sock:
        # No SO_REUSEADDR: on Windows it would let this test succeed on a port
        # another process is actively listening on.
        try:
            sock.bind((host, port))
        except OSError:
            return False
    return True


def _choose_port(host: str, requested: int | None) -> int | None:
    """The port to serve on: as asked, or the first free one from the default.

    An explicit --port is honoured or refused, never silently changed, because
    whoever chose it may have something else pointed at it.
    """
    if requested is not None:
        return requested if _port_free(host, requested) else None
    for port in range(DEFAULT_PORT, DEFAULT_PORT + 20):
        if _port_free(host, port):
            return port
    return None


def _open_dashboard_when_ready(host: str, port: int, token: str | None) -> None:
    """Open the dashboard once the server answers, signed in if we minted a token.

    The one-time token travels in the URL *fragment* (`#signin=`). Browsers
    never send a fragment to any server, nor put it in a Referer header, so it
    reaches no log; the page reads it, signs in and erases it from the address
    bar and history at once. It is only done for a loopback bind and a token
    this process minted, which is the "run it on my own machine" case.
    """
    import threading
    import time
    import urllib.request
    import webbrowser

    shown = "127.0.0.1" if host in ("0.0.0.0", "::") else host
    base = f"http://{shown}:{port}/"
    url = base + (f"#signin={token}" if token else "")

    def wait_then_open() -> None:
        for _ in range(120):
            try:
                with urllib.request.urlopen(base + "v1/health", timeout=1):
                    break
            except OSError:
                time.sleep(0.5)
        webbrowser.open(url)

    threading.Thread(target=wait_then_open, daemon=True).start()


def _cmd_token(args: argparse.Namespace) -> int:
    """Mint a token and print the configuration line that grants it."""
    from apix.api.auth import Role, TokenStore, new_token

    token = new_token()
    store = TokenStore.single(args.name, Role(args.role), token)
    print()
    print(f"  token for {args.name} ({args.role}). Shown once; it is not stored:")
    print()
    print(f"      {token}")
    print()
    print("  Add this entry to APIX_API_TOKENS (';' separates entries). It holds")
    print("  only the SHA-256 of the token, so the configuration is not a secret:")
    print()
    print(f"      {store.config_line()}")
    print()
    return EXIT_OK


def _cmd_enforce(args: argparse.Namespace) -> int:
    """Judge what this change does to the API surface (Phase 6)."""
    from pathlib import Path

    from apix.enforce import EnforceConfig, EnforceConfigError, EnforceError
    from apix.enforce.report import as_github, as_json, as_text
    from apix.enforce.runner import run_enforcement
    from apix.extractors.semgrep_extractor import SemgrepExtractor

    repo = Path(args.repo)
    try:
        config = EnforceConfig.load(repo, Path(args.config)) if args.config else None
        result = run_enforcement(repo, args.base, SemgrepExtractor(), config)
    except (EnforceConfigError, EnforceError) as exc:
        print(f"apix enforce: {exc}", file=sys.stderr)
        return EXIT_ERROR

    render = {"text": as_text, "json": as_json, "github": as_github}[args.format]
    print(render(result))
    return EXIT_OK if result.comparison.passed else EXIT_FINDINGS


def _cmd_train(args: argparse.Namespace) -> int:
    """Train the ML classifier and compare it honestly against the rules."""
    from apix.engine.model import DEFAULT_MODEL_PATH
    from apix.evaluation.train import (
        format_comparison,
        save_report,
        train_and_compare,
        verdict_line,
    )

    report = train_and_compare(
        args.estates,
        seed=args.seed,
        verbose=not args.json,
        save_to=DEFAULT_MODEL_PATH if args.save else None,
    )
    if report.error:
        print(f"apix: {report.error}", file=sys.stderr)
        return EXIT_ERROR

    if args.json:
        print(json.dumps(report.to_dict(), indent=2))
        return EXIT_OK

    print()
    print(format_comparison(report))
    print()
    print(verdict_line(report))
    print()

    out = load_settings().ensure_data_dir() / "training-report.json"
    save_report(report, out)
    print(f"  Full report written to {out}")
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
            "API Exorcist: discover, classify and safely eliminate zombie, "
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
    scan.add_argument(
        "--model",
        action="store_true",
        help="add the learned layer as a veto over removal candidates "
             "(needs: apix train --save)",
    )
    scan.set_defaults(func=_cmd_scan)

    bench = sub.add_parser(
        "benchmark", help="comparative before/after evaluation"
    )
    bench.add_argument("--json", action="store_true", help="emit results as JSON")
    bench.set_defaults(func=_cmd_benchmark)

    imp = sub.add_parser(
        "impact", help="dependency graph and blast-radius analysis"
    )
    imp.add_argument(
        "endpoint",
        nargs="?",
        help='a single endpoint, e.g. "GET /v2/accounts/{id}"',
    )
    imp.add_argument(
        "--depth", type=int, default=4, help="max traversal hops (default 4)"
    )
    imp.add_argument("--json", action="store_true", help="emit as JSON")
    imp.set_defaults(func=_cmd_impact)

    sk = sub.add_parser(
        "safekill",
        help="shadow, approval, canary and automatic rollback (Phase 4)",
    )
    sk.add_argument(
        "endpoint", nargs="?",
        help='walk one candidate only, e.g. "GET /v1/cards/{id}/pin"',
    )
    sk.add_argument(
        "--approve-as", metavar="NAME",
        help="approve clean candidates under this name; without it nothing is removed",
    )
    sk.add_argument(
        "--accept-unidentified", action="store_true",
        help="also approve candidates whose shadow saw traffic with no caller identity",
    )
    sk.add_argument(
        "--slowest-caller-days", type=float, default=30.0, metavar="DAYS",
        help="slowest recurring caller the shadow must catch "
             "(default 30, which gives a 90-day shadow)",
    )
    sk.add_argument(
        "--model", action="store_true",
        help="add the learned layer's veto before Safe Kill (needs: apix train --save)",
    )
    sk.add_argument(
        "--hidden-caller", metavar="ENDPOINT", action="append",
        help="what-if: give ENDPOINT a month-end batch caller the capture never saw",
    )
    sk.add_argument("--audit", metavar="PATH", help="audit log path (JSON Lines)")
    sk.add_argument("--verify", metavar="PATH", help="verify an audit log's hash chain")
    sk.add_argument(
        "--evaluate", type=int, metavar="N", nargs="?", const=120,
        help="measure Safe Kill across N generated estates (default 120)",
    )
    sk.add_argument("--seed", type=int, default=7, help="simulated traffic seed")
    sk.add_argument("--json", action="store_true", help="emit as JSON")
    sk.set_defaults(func=_cmd_safekill)

    srv = sub.add_parser("serve", help="run the REST API (Phase 5)")
    srv.add_argument("--host", default="127.0.0.1", help="bind address (default 127.0.0.1)")
    srv.add_argument(
        "--port", type=int, default=None,
        help=f"port (default {DEFAULT_PORT}, or the next free one if that is taken)",
    )
    srv.add_argument(
        "--allow-remote", action="store_true",
        help="permit a non-loopback bind; only behind TLS termination",
    )
    srv.add_argument(
        "--as", dest="as_name", metavar="NAME",
        help="name for the one-time session token when APIX_API_TOKENS is unset",
    )
    srv.add_argument("--audit", metavar="PATH", help="audit log path (JSON Lines)")
    srv.add_argument("--model", action="store_true", help="add the learned layer's veto")
    srv.add_argument("--seed", type=int, default=7, help="simulated traffic seed")
    srv.add_argument(
        "--log-format", choices=["text", "json"],
        default=os.environ.get("APIX_LOG_FORMAT", "text"),
        help="json: one object per line, for a SIEM (env APIX_LOG_FORMAT)",
    )
    srv.add_argument(
        "--no-docs", action="store_true",
        help="disable /docs and /redoc, which load Swagger UI from a CDN",
    )
    srv.add_argument(
        "--no-browser", action="store_true",
        help="do not open the dashboard in a browser on start",
    )
    srv.set_defaults(func=_cmd_serve)

    tok = sub.add_parser("token", help="mint an API token for a named principal")
    tok.add_argument("name", help="who the token belongs to; written to the audit log")
    tok.add_argument(
        "--role", choices=["viewer", "approver"], default="viewer",
        help="viewer reads; approver also shadows, approves and re-scans",
    )
    tok.set_defaults(func=_cmd_token)

    enf = sub.add_parser(
        "enforce",
        help="fail a change that adds an undocumented, unowned or orphaned endpoint",
    )
    enf.add_argument(
        "--base", required=True, metavar="REF",
        help="the branch the change will merge into, e.g. origin/main",
    )
    enf.add_argument("--repo", default=".", metavar="PATH", help="repository (default .)")
    enf.add_argument(
        "--config", metavar="PATH", help="policy file (default: .apix.yml in the repo)"
    )
    enf.add_argument(
        "--format", choices=["text", "json", "github"], default="text",
        help="github writes annotations and a run summary",
    )
    enf.set_defaults(func=_cmd_enforce)

    tr = sub.add_parser(
        "train", help="train the ML classifier and compare it against the rules"
    )
    tr.add_argument(
        "--estates", type=int, default=120, help="how many estates to generate"
    )
    tr.add_argument("--seed", type=int, default=42, help="split/model seed")
    tr.add_argument(
        "--save", action="store_true", help="persist the fitted model for scans"
    )
    tr.add_argument("--json", action="store_true", help="emit the report as JSON")
    tr.set_defaults(func=_cmd_train)

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
