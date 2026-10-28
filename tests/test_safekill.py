"""
Tests for Safe Kill (Phase 4).

Run:  python tests/test_safekill.py

Most of these construct a situation the simulated estate never produces on its
own. Every zombie in the demo estate is genuinely dead, so on a normal run the
rejection and rollback paths never fire. Untested, a broken rollback would look
exactly like a working one. Each safety path is therefore forced with a scripted
backend and asserted directly, the same reasoning as test_graph.py's
`test_zombie_with_a_caller_is_blocked`.
"""

from __future__ import annotations

import contextlib
import dataclasses
import math
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from apix.graph import assess_removals, build_graph  # noqa: E402
from apix.graph.build import RemovalAssessment  # noqa: E402
from apix.graph.model import BlastRadius  # noqa: E402
from apix.pipeline import run_classification, run_discovery, sources_of  # noqa: E402
from apix.safekill import (  # noqa: E402
    AuditLog,
    IllegalTransition,
    KillState,
    NamedApprover,
    NoApprover,
    PolicyApprover,
    SafeKillController,
    SafeKillPolicy,
    WindowObservation,
    verify_file,
)
from apix.safekill.audit import ChainCheck, verify_entries  # noqa: E402
from apix.safekill.states import TERMINAL, TRANSITIONS, check_transition  # noqa: E402
from apix.simulated_env.enforcement import SimulatedEnforcement  # noqa: E402
from apix.simulated_env.estate import ESTATE  # noqa: E402

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


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------
def _demo_assessments() -> list[RemovalAssessment]:
    records = run_discovery(verbose=False, persist=False)
    verdicts = run_classification(records, consulted=sources_of())
    return assess_removals(verdicts, build_graph(records))


def _cleared() -> RemovalAssessment:
    """One real, gate-cleared removal candidate from the demo estate."""
    return next(a for a in _demo_assessments() if a.may_proceed)


def _clean(days: float, fraction: float = 0.0, shadow: bool = False) -> WindowObservation:
    return WindowObservation(days=days, refuse_fraction=fraction, shadow=shadow, requests=0)


@dataclasses.dataclass
class ScriptedBackend:
    """Returns the observations it is given, in order, and records every call."""

    script: list[WindowObservation]
    name: str = "scripted"
    calls: list[tuple[str, float, bool]] = dataclasses.field(default_factory=list)
    restored: list[str] = dataclasses.field(default_factory=list)
    retired: list[str] = dataclasses.field(default_factory=list)

    def observe(
        self, endpoint_id: str, *, days: float, refuse_fraction: float, shadow: bool
    ) -> WindowObservation:
        self.calls.append(("observe", refuse_fraction, shadow))
        obs = self.script.pop(0)
        return dataclasses.replace(
            obs, days=days, refuse_fraction=refuse_fraction, shadow=shadow
        )

    def restore(self, endpoint_id: str) -> None:
        self.restored.append(endpoint_id)

    def retire(self, endpoint_id: str) -> None:
        self.retired.append(endpoint_id)


def _run(script: list[WindowObservation], approver: object = None):  # type: ignore[no-untyped-def]
    backend = ScriptedBackend(script=script)
    audit = AuditLog()
    ctl = SafeKillController(
        backend=backend,
        audit=audit,
        approver=approver or NamedApprover("test-operator"),  # type: ignore[arg-type]
    )
    return ctl.run(_cleared()), backend, audit


# ---------------------------------------------------------------------------
# The state machine
# ---------------------------------------------------------------------------
def test_terminal_states_are_exactly_the_designs() -> None:
    expected = {
        KillState.BLOCKED, KillState.REJECTED, KillState.DENIED,
        KillState.ROLLED_BACK, KillState.RETIRED,
    }
    check("test_terminal_states_are_exactly_the_designs", set(TERMINAL) == expected,
          f"terminal states are {sorted(s.value for s in TERMINAL)}")


def test_illegal_transition_is_refused() -> None:
    """Skipping approval, or retiring straight from shadow, must be impossible."""
    refused = 0
    for src, dst in (
        (KillState.SHADOW, KillState.CANARY_5),         # skips approval
        (KillState.AWAITING_APPROVAL, KillState.RETIRED),
        (KillState.CANARY_5, KillState.RETIRED),        # skips 25% and soak
        (KillState.RETIRED, KillState.CANARY_5),        # resurrects a terminal
    ):
        try:
            check_transition(src, dst)
        except IllegalTransition:
            refused += 1
    check("test_illegal_transition_is_refused", refused == 4,
          f"only {refused} of 4 illegal moves were refused")


def test_every_state_is_reachable() -> None:
    reached = {KillState.NOMINATED}
    frontier = [KillState.NOMINATED]
    while frontier:
        for nxt in TRANSITIONS[frontier.pop()]:
            if nxt not in reached:
                reached.add(nxt)
                frontier.append(nxt)
    check("test_every_state_is_reachable", reached == set(KillState),
          f"unreachable: {sorted(s.value for s in set(KillState) - reached)}")


# ---------------------------------------------------------------------------
# The audit log
# ---------------------------------------------------------------------------
def _three_entry_log() -> AuditLog:
    log = AuditLog()
    for i, state in enumerate(("NOMINATED", "BLAST_RADIUS", "BLOCKED")):
        log.append(at=f"2026-10-01T09:00:0{i}", endpoint_id="GET /x",
                   from_state=None, to_state=state, reason="r", actor="t")
    return log


def test_audit_chain_verifies() -> None:
    check("test_audit_chain_verifies", _three_entry_log().verify().ok)


def test_audit_detects_edited_entry() -> None:
    log = _three_entry_log()
    forged = dataclasses.replace(log.entries[1], actor="someone-who-never-saw-it")
    entries = [log.entries[0], forged, log.entries[2]]
    result = verify_entries(entries)
    check("test_audit_detects_edited_entry",
          not result.ok and result.broken_at == 1, str(result))


def test_audit_detects_deleted_entry() -> None:
    log = _three_entry_log()
    result = verify_entries([log.entries[0], log.entries[2]])
    check("test_audit_detects_deleted_entry", not result.ok, str(result))


def test_audit_file_round_trip_and_tamper() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        path = Path(tmp) / "audit.jsonl"
        log = AuditLog(path=path)
        for i in range(3):
            log.append(at=f"t{i}", endpoint_id="GET /x", from_state=None,
                       to_state="S", reason="r", actor="a")
        intact = verify_file(path).ok
        lines = path.read_text(encoding="utf-8").splitlines()
        lines[1] = lines[1].replace('"actor": "a"', '"actor": "b"')
        path.write_text("\n".join(lines) + "\n", encoding="utf-8")
        tampered = verify_file(path)
    check("test_audit_file_round_trip_and_tamper",
          intact and not tampered.ok and tampered.broken_at == 1,
          f"intact={intact}, tampered={tampered}")


def test_audit_survives_two_writers_taking_turns() -> None:
    """The CLI and the REST API share one log; neither may link to a stale head."""
    with tempfile.TemporaryDirectory() as tmp:
        path = Path(tmp) / "audit.jsonl"
        api, cli = AuditLog(path=path), AuditLog(path=path)
        api.append(at="t0", endpoint_id="E", from_state=None, to_state="S",
                   reason="r", actor="api")
        cli.append(at="t1", endpoint_id="E", from_state=None, to_state="S",
                   reason="r", actor="cli")
        api.append(at="t2", endpoint_id="E", from_state=None, to_state="S",
                   reason="r", actor="api")
        result = verify_file(path)
    check("test_audit_survives_two_writers_taking_turns",
          result.ok and result.entries == 3, str(result))


_WRITER = """
import sys, time
from pathlib import Path
from apix.safekill.audit import AuditLog
path, go, name, n = Path(sys.argv[1]), Path(sys.argv[2]), sys.argv[3], int(sys.argv[4])
log = AuditLog(path=path)
while not go.exists():
    time.sleep(0.005)
for i in range(n):
    log.append(at=str(i), endpoint_id="E", from_state=None, to_state="S",
               reason="r", actor=name)
"""


def test_audit_survives_concurrent_writers() -> None:
    """Separate processes appending at the same instant must not fork the chain.

    Without a lock, two writers read the same head, both link to it, and the
    chain breaks at the second of the pair; or their lines interleave and the
    file stops parsing. Processes, not threads: the deployment case is the CLI
    and the API server, or two API replicas, sharing one file.
    """
    import os
    import subprocess

    writers, each = 4, 25
    with tempfile.TemporaryDirectory() as tmp:
        path, go = Path(tmp) / "audit.jsonl", Path(tmp) / "go"
        env = {**os.environ, "PYTHONPATH": str(Path(__file__).parents[1] / "src")}
        procs = [
            subprocess.Popen(
                [sys.executable, "-c", _WRITER, str(path), str(go), f"w{k}", str(each)],
                env=env, stderr=subprocess.PIPE, text=True,
            )
            for k in range(writers)
        ]
        go.touch()
        errors = [p.communicate(timeout=120)[1] for p in procs]
        try:
            result = verify_file(path)
        except ValueError as exc:     # interleaved, unparseable lines
            result = ChainCheck(False, 0, None, f"unparseable: {exc}")
    check("test_audit_survives_concurrent_writers",
          result.ok and result.entries == writers * each
          and all(p.returncode == 0 for p in procs),
          f"{result}; stderr: {[e[-200:] for e in errors if e]}")


# ---------------------------------------------------------------------------
# Policy
# ---------------------------------------------------------------------------
def test_shadow_window_is_the_rule_of_three() -> None:
    p = SafeKillPolicy()
    miss = p.miss_probability(p.min_detectable_rate, p.shadow_days)
    check("test_shadow_window_is_the_rule_of_three",
          p.shadow_days == 90 and miss <= 0.05 and math.isclose(miss, math.exp(-3), rel_tol=0.01),
          f"window {p.shadow_days} days, miss probability {miss:.4f}")


# ---------------------------------------------------------------------------
# The safety paths, each forced
# ---------------------------------------------------------------------------
def test_no_approver_removes_nothing() -> None:
    backend = SimulatedEnforcement(ESTATE, seed=1)
    ctl = SafeKillController(backend=backend, approver=NoApprover())
    outcomes = ctl.run_all([a for a in _demo_assessments() if a.may_proceed])
    check("test_no_approver_removes_nothing",
          outcomes
          and all(o.state is KillState.AWAITING_APPROVAL for o in outcomes)
          and not backend.harm.retired
          and backend.harm.total_genuine_refused == 0
          and all(not o.canary for o in outcomes),
          f"states: {[o.state.value for o in outcomes]}")


def test_gate_refusal_is_blocked_without_touching_traffic() -> None:
    a = _cleared()
    blocked = dataclasses.replace(
        a, radius=BlastRadius(a.verdict.endpoint_id, direct_services=["payments-service"])
    )
    backend = ScriptedBackend(script=[])
    out = SafeKillController(backend=backend, approver=NamedApprover("op")).run(blocked)
    check("test_gate_refusal_is_blocked_without_touching_traffic",
          out.state is KillState.BLOCKED and not backend.calls,
          f"state {out.state.value}, backend calls {backend.calls}")


def test_identified_caller_in_shadow_rejects_and_refuses_nobody() -> None:
    caller = dataclasses.replace(_clean(90, shadow=True), requests=2,
                                 identified={"month-end-recon": 2})
    out, backend, _ = _run([caller])
    check("test_identified_caller_in_shadow_rejects_and_refuses_nobody",
          out.state is KillState.REJECTED
          and all(shadow for _, _, shadow in backend.calls)
          and not backend.retired and not backend.restored
          and "month-end-recon" in out.reason,
          f"state {out.state.value}, calls {backend.calls}")


def test_operator_decline_is_denied() -> None:
    noisy = dataclasses.replace(_clean(90, shadow=True), requests=270, unidentified=270)
    out, backend, _ = _run([noisy], approver=NamedApprover("op"))
    check("test_operator_decline_is_denied",
          out.state is KillState.DENIED and len(backend.calls) == 1
          and "authentication" in out.reason,
          f"state {out.state.value}: {out.reason}")


def test_canary_breach_rolls_back_automatically() -> None:
    breach = dataclasses.replace(_clean(7, 0.25), requests=1, identified={"partner-x": 1})
    out, backend, audit = _run([_clean(90, shadow=True), _clean(7, 0.05), breach])
    last = audit.for_endpoint(out.endpoint_id)[-1]
    check("test_canary_breach_rolls_back_automatically",
          out.state is KillState.ROLLED_BACK
          and backend.restored == [out.endpoint_id]
          and not backend.retired
          and out.breach_kind == "identified"
          and last.actor == "safekill-controller",
          f"state {out.state.value}, restored {backend.restored}, actor {last.actor}")


def test_clean_walk_retires_with_approver_on_record() -> None:
    out, backend, audit = _run(
        [_clean(90, shadow=True), _clean(7, 0.05), _clean(7, 0.25), _clean(14, 1.0)]
    )
    approval = next(e for e in audit.entries if e.to_state == "CANARY_5")
    check("test_clean_walk_retires_with_approver_on_record",
          out.state is KillState.RETIRED
          and backend.retired == [out.endpoint_id]
          and approval.actor == "test-operator"
          and approval.evidence.get("human") is True,
          f"state {out.state.value}, approval actor {approval.actor}")


def test_every_terminal_state_is_audited() -> None:
    """The design: Blocked, Rejected and Denied are recorded like Retired."""
    a = _cleared()
    seen: dict[str, bool] = {}

    scenarios = {
        "BLOCKED": ([], dataclasses.replace(
            a, radius=BlastRadius(a.verdict.endpoint_id, direct_services=["s"]))),
        "REJECTED": ([dataclasses.replace(_clean(90, shadow=True), identified={"c": 1})], a),
        "DENIED": ([dataclasses.replace(_clean(90, shadow=True), unidentified=5)], a),
        "ROLLED_BACK": ([_clean(90, shadow=True),
                         dataclasses.replace(_clean(7, 0.05), identified={"c": 1})], a),
        "RETIRED": ([_clean(90, shadow=True), _clean(7), _clean(7), _clean(14)], a),
    }
    for expected, (script, assessment) in scenarios.items():
        audit = AuditLog()
        out = SafeKillController(
            backend=ScriptedBackend(script=list(script)),
            audit=audit, approver=NamedApprover("op"),
        ).run(assessment)
        last = audit.entries[-1]
        seen[expected] = (
            out.state.value == expected and last.to_state == expected
            and audit.verify().ok
        )
    check("test_every_terminal_state_is_audited", all(seen.values()), str(seen))


# ---------------------------------------------------------------------------
# End to end, on the real (simulated) world
# ---------------------------------------------------------------------------
def test_demo_estate_retires_dead_endpoints_and_harms_nobody() -> None:
    backend = SimulatedEnforcement(ESTATE, seed=7)
    audit = AuditLog()
    outcomes = SafeKillController(
        backend=backend, audit=audit, approver=NamedApprover("op")
    ).run_all([a for a in _demo_assessments() if a.may_proceed])
    by_state = {o.endpoint_id: o.state for o in outcomes}
    check("test_demo_estate_retires_dead_endpoints_and_harms_nobody",
          len(backend.harm.retired) == 7
          and by_state.get("POST /v1/debug/payments/replay") is KillState.DENIED
          and backend.harm.total_genuine_refused == 0
          and not backend.harm.retired_with_live_caller
          and audit.verify().ok,
          f"{ {k: v.value for k, v in by_state.items()} }")


def test_accepted_anonymous_traffic_does_not_false_alarm() -> None:
    """With a shadow baseline, 3 probes a day must not look like a dependency.

    Only the evaluation harness may approve past unidentified traffic, and only
    with the override switched on; this measures the canary's breach rule.
    """
    target = next(a for a in _demo_assessments()
                  if a.verdict.endpoint_id == "POST /v1/debug/payments/replay")
    out = SafeKillController(
        backend=SimulatedEnforcement(ESTATE, seed=7),
        approver=PolicyApprover(accept_unidentified=True),
        policy=SafeKillPolicy(allow_unidentified_override=True),
    ).run(target)
    check("test_accepted_anonymous_traffic_does_not_false_alarm",
          out.state is KillState.RETIRED, f"{out.state.value}: {out.reason}")


def test_no_person_can_approve_over_unidentified_traffic() -> None:
    """An endpoint whose callers cannot be identified is never removed.

    A person once ticked "accept" on POST /v1/debug/payments/replay, 266
    anonymous requests in its shadow, and it was retired. Now the approval is
    refused, the candidate stays pending, and declining still works.
    """
    from apix.safekill.controller import Decision, UnidentifiedTraffic

    ep = "POST /v1/debug/payments/replay"
    target = next(a for a in _demo_assessments() if a.verdict.endpoint_id == ep)
    controller = SafeKillController(backend=SimulatedEnforcement(ESTATE, seed=7))
    waiting = controller.begin(target).pending_approval   # read now: the outcome updates
    try:
        controller.resolve(ep, Decision(approved=True, approver="op", human=True))
        refused = False
    except UnidentifiedTraffic as e:
        refused = "authentication" in str(e)
    still_pending = ep in [r.endpoint_id for r in controller.pending()]
    declined = controller.resolve(ep, Decision(approved=False, approver="op", human=True))
    named = SafeKillController(
        backend=SimulatedEnforcement(ESTATE, seed=7), approver=NamedApprover("op"),
    ).run(target)
    check("test_no_person_can_approve_over_unidentified_traffic",
          waiting and refused and still_pending
          and declined.state is KillState.DENIED and named.state is KillState.DENIED,
          f"refused={refused} pending={still_pending} declined={declined.state.value} "
          f"named={named.state.value}")


def test_safekill_prevents_the_gates_outages() -> None:
    from apix.evaluation.safekill_eval import evaluate

    r = evaluate(30)
    # The shadow catches a caller with 95% confidence, not certainty, so a live
    # endpoint can occasionally reach the canary (seed 17 does). What must hold
    # is that the canary then rolls it back: real requests are refused only on
    # endpoints that end ROLLED_BACK, and none is ever retired.
    live_states = set(r.live.states)
    check("test_safekill_prevents_the_gates_outages",
          r.gate_only_outages > 0
          and r.safekill_outages == 0
          and live_states <= {"REJECTED", "ROLLED_BACK"}
          and (r.live.genuine_refused == 0 or "ROLLED_BACK" in live_states)
          and r.label_disagreements == 0
          and r.audit_chains_ok,
          str(r.to_dict()))


def test_canary_without_shadow_is_trigger_happy() -> None:
    """Pins the finding that justified adding the shadow stage.

    With no shadow there is no baseline for anonymous traffic, so scanner noise
    trips rollbacks on endpoints that are genuinely dead, and real requests are
    refused before live endpoints are caught. If a change makes this stop being
    true, the documentation's argument for the shadow stage needs revisiting.
    """
    from apix.evaluation.safekill_eval import evaluate

    r = evaluate(30, policy=SafeKillPolicy(shadow_days_override=0))
    check("test_canary_without_shadow_is_trigger_happy",
          r.dead.rollback_by.get("anonymous", 0) > 0 and r.live.genuine_refused > 0,
          str(r.to_dict()))


def _hidden_caller_run(slowest_caller_days: float, seed: int):  # type: ignore[no-untyped-def]
    from apix.simulated_env.enforcement import HIDDEN_CALLER

    ep = "GET /v1/cards/{id}/pin"
    target = next(a for a in _demo_assessments() if a.verdict.endpoint_id == ep)
    backend = SimulatedEnforcement(ESTATE, seed=seed, hidden_callers={ep: HIDDEN_CALLER})
    out = SafeKillController(
        backend=backend,
        approver=NamedApprover("op"),
        policy=SafeKillPolicy(min_detectable_rate=1 / slowest_caller_days),
    ).run(target)
    return out, backend


def test_hidden_month_end_caller_is_caught_by_the_default_shadow() -> None:
    """The scenario the design exists for: a caller the capture never saw."""
    out, backend = _hidden_caller_run(30, seed=7)
    check("test_hidden_month_end_caller_is_caught_by_the_default_shadow",
          out.state is KillState.REJECTED
          and "month-end-recon-batch" in out.reason
          and backend.harm.total_genuine_refused == 0,
          f"{out.state.value}: {out.reason}")


def test_demo_seeds_show_each_outcome() -> None:
    """Pins the seeds that show each Safe Kill branch (CLI: apix safekill --seed)."""
    rolled, b3 = _hidden_caller_run(3, seed=3)
    retired, b1 = _hidden_caller_run(3, seed=1)
    check("test_demo_seeds_show_each_outcome",
          rolled.state is KillState.ROLLED_BACK and rolled.breach_kind == "identified"
          and b3.harm.total_genuine_refused > 0
          and retired.state is KillState.RETIRED
          and "GET /v1/cards/{id}/pin" in b1.harm.retired_with_live_caller,
          f"seed 3 -> {rolled.state.value}, seed 1 -> {retired.state.value}")


def test_world_model_never_reads_the_answer_key() -> None:
    """enforcement.py claims its behaviour comes from physics, not labels."""
    src = (ROOT / "src" / "apix" / "simulated_env" / "enforcement.py").read_text(
        encoding="utf-8"
    )
    body = "".join(seg for i, seg in enumerate(src.split('"""')) if i % 2 == 0)
    leaks = [f for f in ("true_label", "decay_story", "Label.") if f in body]
    check("test_world_model_never_reads_the_answer_key", not leaks, f"reads {leaks}")


# ---------------------------------------------------------------------------
if __name__ == "__main__":
    tests = [v for k, v in sorted(globals().items()) if k.startswith("test_")]
    for t in tests:
        with contextlib.suppress(AssertionError):
            t()
    print(f"\n{_PASS} passed, {_FAIL} failed")
    sys.exit(1 if _FAIL else 0)
