"""
Tests for the dependency graph and the removal gate.

Run:  python tests/test_graph.py

The most important test here is `test_zombie_with_a_caller_is_blocked`. No zombie
in the simulated estate has a caller, so the blocking path never fires during a
normal run — which means without a constructed case it could be broken and
nothing would say so. A safety mechanism that is never exercised is not a safety
mechanism.
"""

from __future__ import annotations

import contextlib
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from apix.engine.verdict import Classification, Verdict  # noqa: E402
from apix.graph import InMemoryGraph, assess_removals, build_graph  # noqa: E402
from apix.pipeline import run_classification, run_discovery, sources_of  # noqa: E402
from apix.simulated_env.estate import Label, by_id  # noqa: E402

_PASS = 0
_FAIL = 0


def check(name: str, condition: bool, detail: str = "") -> None:
    global _PASS, _FAIL
    if condition:
        _PASS += 1
        print(f"  PASS  {name}")
        return
    _FAIL += 1
    print(f"  FAIL  {name}" + (f"\n          {detail}" if detail else ""))
    raise AssertionError(f"{name}: {detail}" if detail else name)


def _zombie(endpoint_id: str, consulted: frozenset[str] | None = None) -> Verdict:
    """A ZOMBIE verdict that would be actionable on its own."""
    return Verdict(
        endpoint_id=endpoint_id,
        label=Classification.ZOMBIE,
        confidence=0.95,
        rules_fired=4,
        sources_consulted=consulted or frozenset({"TRAFFIC", "CODE", "OPENAPI"}),
    )


# ---------------------------------------------------------------------------
# Traversal
# ---------------------------------------------------------------------------
def test_isolated_endpoint_has_empty_radius() -> None:
    g = InMemoryGraph()
    g.add_endpoint("GET /a", "svc-a")
    r = g.blast_radius("GET /a")
    check(
        "test_isolated_endpoint_has_empty_radius",
        r.is_isolated and r.severity == "isolated",
        f"{r.to_dict()}",
    )


def test_direct_caller_is_reported() -> None:
    g = InMemoryGraph()
    g.add_endpoint("GET /a", "svc-a")
    g.add_call("svc-b", "GET /a")
    r = g.blast_radius("GET /a")
    check(
        "test_direct_caller_is_reported",
        r.direct_services == ["svc-b"] and not r.is_isolated,
        f"{r.to_dict()}",
    )


def test_traversal_is_transitive() -> None:
    """Killing /a breaks svc-b, so svc-b's own endpoints degrade, so svc-c is hit.

    A single-hop CALLS traversal would report one affected service and miss the
    rest — which is the whole reason the walk alternates CALLS and OWNS.
    """
    g = InMemoryGraph()
    g.add_endpoint("GET /a", "svc-a")
    g.add_endpoint("GET /b", "svc-b")
    g.add_call("svc-b", "GET /a")     # svc-b depends on /a
    g.add_call("svc-c", "GET /b")     # svc-c depends on svc-b's endpoint

    r = g.blast_radius("GET /a")
    check(
        "test_traversal_is_transitive",
        r.direct_services == ["svc-b"]
        and "svc-c" in r.indirect_services
        and ("GET /b", 2) in r.affected_endpoints,
        f"{r.to_dict()}",
    )


def test_self_calls_are_not_dependencies() -> None:
    """A service calling its own endpoint would make everything self-dependent."""
    g = InMemoryGraph()
    g.add_endpoint("GET /a", "svc-a")
    g.add_call("svc-a", "GET /a")
    r = g.blast_radius("GET /a")
    check("test_self_calls_are_not_dependencies", r.is_isolated, f"{r.to_dict()}")


def test_depth_limit_is_respected() -> None:
    g = InMemoryGraph()
    for i in range(6):
        g.add_endpoint(f"GET /e{i}", f"svc{i}")
    for i in range(5):
        g.add_call(f"svc{i + 1}", f"GET /e{i}")

    shallow = g.blast_radius("GET /e0", max_depth=1)
    deep = g.blast_radius("GET /e0", max_depth=6)
    check(
        "test_depth_limit_is_respected",
        len(shallow.all_services) < len(deep.all_services) and shallow.truncated,
        f"shallow={shallow.all_services} deep={deep.all_services}",
    )


def test_severity_scales_with_reach() -> None:
    g = InMemoryGraph()
    g.add_endpoint("GET /a", "svc-a")
    for i in range(7):
        g.add_call(f"caller{i}", "GET /a")
    check(
        "test_severity_scales_with_reach",
        g.blast_radius("GET /a").severity == "severe",
    )


# ---------------------------------------------------------------------------
# The removal gate
# ---------------------------------------------------------------------------
def test_zombie_with_a_caller_is_blocked() -> None:
    """The safety property the estate never exercises on its own.

    An endpoint can look completely dead — undocumented, unowned, silent — and
    still have something calling it. The graph is the check that catches that,
    and removing it is how this product would cause an outage.
    """
    g = InMemoryGraph()
    g.add_endpoint("GET /looks-dead", "svc-a")
    g.add_call("svc-still-calling", "GET /looks-dead")

    a = assess_removals([_zombie("GET /looks-dead")], g)[0]
    check(
        "test_zombie_with_a_caller_is_blocked",
        not a.may_proceed and "svc-still-calling" in (a.blocked_by or ""),
        f"may_proceed={a.may_proceed} blocked_by={a.blocked_by}",
    )


def test_isolated_zombie_may_proceed() -> None:
    g = InMemoryGraph()
    g.add_endpoint("GET /truly-dead", "svc-a")
    a = assess_removals([_zombie("GET /truly-dead")], g)[0]
    check(
        "test_isolated_zombie_may_proceed",
        a.may_proceed and a.blocked_by is None,
        f"may_proceed={a.may_proceed} blocked_by={a.blocked_by}",
    )


def test_both_signals_are_required() -> None:
    """Graph isolation alone must not authorise a removal.

    An endpoint nobody calls is not thereby dead — it may be new, or called only
    by clients outside the observed estate. The classifier must also say ZOMBIE,
    and it can only say that when a usage source was consulted.
    """
    g = InMemoryGraph()
    g.add_endpoint("GET /nobody-calls-me", "svc-a")
    no_traffic = _zombie(
        "GET /nobody-calls-me", consulted=frozenset({"CODE", "OPENAPI"})
    )
    a = assess_removals([no_traffic], g)[0]
    check(
        "test_both_signals_are_required",
        not a.may_proceed and "TRAFFIC" in (a.blocked_by or ""),
        f"may_proceed={a.may_proceed} blocked_by={a.blocked_by}",
    )


def test_only_zombies_are_assessed() -> None:
    g = InMemoryGraph()
    g.add_endpoint("GET /a", "svc-a")
    healthy = Verdict(
        endpoint_id="GET /a",
        label=Classification.ACTIVE,
        confidence=0.9,
        rules_fired=5,
        sources_consulted=frozenset({"TRAFFIC"}),
    )
    check("test_only_zombies_are_assessed", assess_removals([healthy], g) == [])


# ---------------------------------------------------------------------------
# Against the real estate
# ---------------------------------------------------------------------------
def test_every_estate_zombie_is_isolated() -> None:
    """A zombie with dependents would mean the taxonomy is inconsistent."""
    records = run_discovery(verbose=False, persist=False)
    graph = build_graph(records, InMemoryGraph())
    truth = by_id()
    bad = [
        eid for eid, ep in truth.items()
        if ep.true_label is Label.ZOMBIE
        and not graph.blast_radius(eid).is_isolated
    ]
    check("test_every_estate_zombie_is_isolated", not bad, f"have callers: {bad}")


def test_no_live_endpoint_is_cleared_for_removal() -> None:
    """The outage test, end to end through discovery, classification and graph."""
    records = run_discovery(verbose=False, persist=False)
    verdicts = run_classification(records, consulted=sources_of())
    graph = build_graph(records, InMemoryGraph())
    truth = by_id()

    fatal = [
        a.verdict.endpoint_id
        for a in assess_removals(verdicts, graph)
        if a.may_proceed
        and truth[a.verdict.endpoint_id].true_label
        in (Label.ACTIVE, Label.ORPHANED, Label.DEPRECATED)
    ]
    check(
        "test_no_live_endpoint_is_cleared_for_removal",
        not fatal,
        f"would have been removed: {fatal}",
    )


def test_deprecated_endpoints_all_have_callers() -> None:
    """The hard case: deprecated but still depended upon.

    All three deprecated endpoints in the estate still carry callers, so even if
    the classifier called one a zombie the graph would block it. That layering
    is the point — neither signal is trusted alone.
    """
    records = run_discovery(verbose=False, persist=False)
    graph = build_graph(records, InMemoryGraph())
    truth = by_id()
    unprotected = [
        eid for eid, ep in truth.items()
        if ep.true_label is Label.DEPRECATED
        and graph.blast_radius(eid).is_isolated
    ]
    check(
        "test_deprecated_endpoints_all_have_callers",
        not unprotected,
        f"no graph protection for: {unprotected}",
    )


def test_graph_stats_are_consistent() -> None:
    records = run_discovery(verbose=False, persist=False)
    graph = build_graph(records, InMemoryGraph())
    s = graph.stats()
    check(
        "test_graph_stats_are_consistent",
        s["endpoints"] == len(records)
        and s["call_edges"] == sum(len(r.caller_services) for r in records)
        and s["isolated_endpoints"] == 8,
        f"{s}",
    )


def main() -> None:
    print("Dependency graph tests\n")
    for fn in [
        test_isolated_endpoint_has_empty_radius,
        test_direct_caller_is_reported,
        test_traversal_is_transitive,
        test_self_calls_are_not_dependencies,
        test_depth_limit_is_respected,
        test_severity_scales_with_reach,
        test_zombie_with_a_caller_is_blocked,
        test_isolated_zombie_may_proceed,
        test_both_signals_are_required,
        test_only_zombies_are_assessed,
        test_every_estate_zombie_is_isolated,
        test_no_live_endpoint_is_cleared_for_removal,
        test_deprecated_endpoints_all_have_callers,
        test_graph_stats_are_consistent,
    ]:
        with contextlib.suppress(AssertionError):
            fn()

    print(f"\n{_PASS} passed, {_FAIL} failed")
    sys.exit(1 if _FAIL else 0)


if __name__ == "__main__":
    main()
