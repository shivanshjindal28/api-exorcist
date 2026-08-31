"""
Tests for the classification and explanation engine.

Run:  python tests/test_engine.py

The most important test in this file is `test_engine_never_imports_ground_truth`.
An earlier version of the OpenAPI connector derived a feature from `true_label`,
which would have silently inflated accuracy and invalidated every number in the
paper. The guard in tests/test_discovery.py covers the discovery layer; this one
extends the same protection to the engine.
"""

from __future__ import annotations

import ast
import contextlib
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from apix.connectors.base import Source  # noqa: E402
from apix.engine.explain import audit_entry, explain, one_line, summarise  # noqa: E402
from apix.engine.rules import (  # noqa: E402
    MEANINGFUL_TRAFFIC_THRESHOLD,
    RULES,
    RuleClassifier,
)
from apix.engine.verdict import CLASS_ORDER, Classification  # noqa: E402
from apix.evaluation.metrics import evaluate  # noqa: E402
from apix.inventory.correlator import InventoryRecord  # noqa: E402
from apix.pipeline import run_discovery  # noqa: E402
from apix.simulated_env.estate import Label, by_id  # noqa: E402

_PASS = 0
_FAIL = 0


def check(name: str, condition: bool, detail: str = "") -> None:
    """Record a check, and raise if it failed.

    Raising matters: these functions are named `test_*`, so pytest collects them.
    A helper that only *recorded* failures would let pytest report the whole file
    green while checks inside it were failing — a silently passing test suite is
    worse than no suite. The script runner in `main()` catches the exception so
    it can still report every check rather than stopping at the first failure.
    """
    global _PASS, _FAIL
    if condition:
        _PASS += 1
        print(f"  PASS  {name}")
        return
    _FAIL += 1
    print(f"  FAIL  {name}" + (f"\n          {detail}" if detail else ""))
    raise AssertionError(f"{name}: {detail}" if detail else name)


# ---------------------------------------------------------------------------
# Boundary: the engine must never see the answer key
# ---------------------------------------------------------------------------
#: Any import path that would reach the answer key. Both spellings are checked
#: because the package migration changed `simulated_env` to `apix.simulated_env`,
#: and a guard that only knows the old name passes silently while protecting
#: nothing — which is worse than having no guard at all.
_GROUND_TRUTH_MODULES = ("simulated_env", "apix.simulated_env")

#: Two different guarantees are needed, because the packages differ in what they
#: legitimately need.
#:
#: STRUCTURAL isolation — must not import the estate at all. These packages
#: reason over the correlated inventory and have no business knowing that a
#: simulated environment even exists. Enforced at the AST level.
_STRUCTURALLY_ISOLATED = ("engine", "inventory")
#:
#: TOKEN isolation — may import the estate, because in simulation mode it IS
#: their data source, but must never read the answer-key fields. Connectors read
#: observable attributes; dataset/build.py attaches labels only after feature
#: extraction has finished. Enforced by token scan (and again in
#: tests/test_discovery.py against the imported modules).
_TOKEN_ISOLATED = ("connectors", "dataset")

_ANSWER_KEY_FIELDS = ("true_label", "decay_story")


def _reaches_ground_truth(name: str | None) -> bool:
    return bool(name) and name.startswith(_GROUND_TRUTH_MODULES)  # type: ignore[union-attr]


def test_engine_never_imports_ground_truth() -> None:
    """`engine` and `inventory` must not import the estate at any depth."""
    offenders: list[str] = []
    scanned = 0
    for pkg in _STRUCTURALLY_ISOLATED:
        for path in (ROOT / "src" / "apix" / pkg).rglob("*.py"):
            scanned += 1
            tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
            for node in ast.walk(tree):
                if isinstance(node, ast.Import):
                    for alias in node.names:
                        if _reaches_ground_truth(alias.name):
                            offenders.append(f"{pkg}/{path.name}: import {alias.name}")
                elif isinstance(node, ast.ImportFrom) and _reaches_ground_truth(
                    node.module
                ):
                    offenders.append(f"{pkg}/{path.name}: from {node.module}")

    check(
        "test_engine_never_imports_ground_truth",
        not offenders and scanned > 0,
        f"leakage: {offenders}" if offenders else "guard scanned zero files",
    )


def test_detection_code_never_reads_answer_key_fields() -> None:
    """No module that may import the estate is allowed to read its labels."""
    offenders: list[str] = []
    scanned = 0
    for pkg in (*_STRUCTURALLY_ISOLATED, *_TOKEN_ISOLATED):
        for path in (ROOT / "src" / "apix" / pkg).rglob("*.py"):
            scanned += 1
            src = path.read_text(encoding="utf-8")
            # Strip docstrings, where these terms legitimately appear in prose
            # explaining why they must not be read.
            body = "".join(
                seg for i, seg in enumerate(src.split('"""')) if i % 2 == 0
            )
            for field in _ANSWER_KEY_FIELDS:
                if field in body:
                    offenders.append(f"{pkg}/{path.name}: reads {field}")

    # dataset/build.py attaches the label AFTER extract_features() has run; the
    # separation is asserted by test_discovery.test_no_ground_truth_leakage,
    # which scans extract_features itself.
    offenders = [o for o in offenders if not o.startswith("dataset/build.py")]

    check(
        "test_detection_code_never_reads_answer_key_fields",
        not offenders and scanned > 0,
        f"leakage: {offenders}" if offenders else "guard scanned zero files",
    )


def test_no_rule_references_true_label() -> None:
    """No rule predicate may mention true_label or decay_story."""
    src = (ROOT / "src" / "apix" / "engine" / "rules.py").read_text(encoding="utf-8")
    # Strip the module docstring, where these terms appear in prose.
    body = src.split('"""', 2)[-1]
    banned = [t for t in _ANSWER_KEY_FIELDS if t in body]
    check("test_no_rule_references_true_label", not banned, f"found {banned}")


# ---------------------------------------------------------------------------
# Classifier behaviour
# ---------------------------------------------------------------------------
def _record(**kw) -> InventoryRecord:
    """An inventory record with healthy-ACTIVE defaults, overridable."""
    base = dict(
        endpoint_id="GET /v1/test",
        service="test-service",
        method="GET",
        path="/test",
        version="v1",
        in_openapi_spec=True,
        in_gateway_registry=True,
        observed_on_wire=True,
        handler_exists_in_code=True,
        dns_resolvable=True,
        deployed_via_pipeline=True,
        daily_calls=5000,
        last_seen_days_ago=1,
        distinct_callers=3,
        owner_team="platform",
        days_since_last_commit=20,
    )
    base.update(kw)
    return InventoryRecord(**base)  # type: ignore[arg-type]


def test_healthy_endpoint_is_active() -> None:
    v = RuleClassifier().classify(_record())
    check(
        "test_healthy_endpoint_is_active",
        v.label is Classification.ACTIVE,
        f"got {v.label}",
    )


def test_silent_shadow_endpoint_is_zombie() -> None:
    v = RuleClassifier().classify(
        _record(
            in_openapi_spec=False,
            in_gateway_registry=False,
            observed_on_wire=False,
            daily_calls=0,
            last_seen_days_ago=400,
            distinct_callers=0,
            owner_team=None,
            deployed_via_pipeline=False,
            days_since_last_commit=800,
        )
    )
    check(
        "test_silent_shadow_endpoint_is_zombie",
        v.label is Classification.ZOMBIE,
        f"got {v.label}",
    )


def test_used_but_unowned_is_orphaned_not_zombie() -> None:
    """The distinction that stops this product causing outages."""
    v = RuleClassifier().classify(_record(owner_team=None))
    check(
        "test_used_but_unowned_is_orphaned_not_zombie",
        v.label is Classification.ORPHANED,
        f"got {v.label}",
    )


def test_orphaned_is_never_actionable() -> None:
    """ORPHANED endpoints carry real traffic and must never be kill candidates."""
    v = RuleClassifier().classify(_record(owner_team=None))
    check(
        "test_orphaned_is_never_actionable",
        v.label is Classification.ORPHANED and not v.is_actionable,
    )


def test_deprecation_flag_is_near_decisive() -> None:
    v = RuleClassifier().classify(_record(spec_deprecated=True))
    check(
        "test_deprecation_flag_is_near_decisive",
        v.label is Classification.DEPRECATED,
        f"got {v.label}",
    )


def test_effectively_silent_counts_as_no_meaningful_traffic() -> None:
    """A handful of calls a day is not use — it is health checks and crawlers."""
    v = RuleClassifier().classify(
        _record(
            daily_calls=MEANINGFUL_TRAFFIC_THRESHOLD - 1,
            in_openapi_spec=False,
            in_gateway_registry=False,
            owner_team=None,
            last_seen_days_ago=200,
        )
    )
    check(
        "test_effectively_silent_counts_as_no_meaningful_traffic",
        v.label is Classification.ZOMBIE,
        f"got {v.label}",
    )


def test_classifier_is_deterministic() -> None:
    rec = _record(owner_team=None, daily_calls=0, observed_on_wire=False)
    a = RuleClassifier().classify(rec)
    b = RuleClassifier().classify(rec)
    check(
        "test_classifier_is_deterministic",
        a.label == b.label and abs(a.confidence - b.confidence) < 1e-12,
    )


# ---------------------------------------------------------------------------
# Source availability: "nobody asked" is not "the answer was no"
# ---------------------------------------------------------------------------
def test_traffic_rules_abstain_without_traffic_source() -> None:
    """A repository scan has no traffic capture; silence must not be inferred."""
    repo_only = frozenset({Source.CODE, Source.OPENAPI, Source.CICD})
    v = RuleClassifier(consulted=repo_only).classify(
        _record(observed_on_wire=False, daily_calls=0, last_seen_days_ago=None)
    )
    traffic_rules = {"NO_MEANINGFUL_TRAFFIC", "STALE_6M", "RECENTLY_USED"}
    check(
        "test_traffic_rules_abstain_without_traffic_source",
        traffic_rules <= set(v.abstained),
        f"abstained={v.abstained}",
    )


def test_repo_only_scan_does_not_label_healthy_endpoint_zombie() -> None:
    """The bug this whole mechanism exists to prevent.

    A documented, owned, recently-committed endpoint with no traffic data must
    not be called a zombie just because a repository cannot see traffic.
    """
    repo_only = frozenset({Source.CODE, Source.OPENAPI, Source.CICD})
    v = RuleClassifier(consulted=repo_only).classify(
        _record(observed_on_wire=False, daily_calls=0, last_seen_days_ago=None)
    )
    check(
        "test_repo_only_scan_does_not_label_healthy_endpoint_zombie",
        v.label is not Classification.ZOMBIE,
        f"got {v.label} — traffic absence was treated as evidence",
    )


def test_zombie_without_traffic_evidence_is_not_actionable() -> None:
    """Never queue a removal when usage was never measured."""
    repo_only = frozenset({Source.CODE, Source.OPENAPI, Source.CICD})
    v = RuleClassifier(consulted=repo_only).classify(
        _record(
            in_openapi_spec=False,
            owner_team=None,
            deployed_via_pipeline=False,
            days_since_last_commit=900,
            observed_on_wire=False,
            daily_calls=0,
        )
    )
    ok = (not v.is_actionable) and (
        v.label is not Classification.ZOMBIE or v.blocked_reason is not None
    )
    check(
        "test_zombie_without_traffic_evidence_is_not_actionable",
        ok,
        f"label={v.label} actionable={v.is_actionable} blocked={v.blocked_reason}",
    )


def test_no_evidence_means_indeterminate_not_active() -> None:
    """A gateway registry alone can enumerate endpoints but classify none.

    Every rule abstains, all four classes score zero, and max() returns ACTIVE
    by tie-break. Reporting that as 'healthy' would be the most dangerous thing
    this system could do, so the verdict is marked indeterminate.
    """
    v = RuleClassifier(consulted=frozenset({Source.GATEWAY})).classify(_record())
    check(
        "test_no_evidence_means_indeterminate_not_active",
        v.rules_fired == 0
        and not v.is_determinate
        and not v.is_actionable
        and abs(v.confidence - 0.25) < 1e-9,
        f"fired={v.rules_fired} determinate={v.is_determinate} conf={v.confidence}",
    )


def test_unowned_without_traffic_is_not_orphaned() -> None:
    """Being unowned is not orphanhood.

    ORPHANED means "still genuinely used, but nobody owns it". A repository has
    no CODEOWNERS often enough that, before the NO_OWNER / UNOWNED_BUT_USED
    split, every endpoint in a real scan came back ORPHANED on the strength of a
    missing file. Use has to be demonstrated, not assumed.
    """
    repo_only = frozenset({Source.CODE, Source.OPENAPI, Source.CICD})
    v = RuleClassifier(consulted=repo_only).classify(
        _record(owner_team=None, observed_on_wire=False, daily_calls=0)
    )
    check(
        "test_unowned_without_traffic_is_not_orphaned",
        v.label is not Classification.ORPHANED,
        f"got {v.label} — ownership alone was treated as orphanhood",
    )


def test_unowned_with_traffic_is_orphaned() -> None:
    """The converse still holds when usage is actually observed."""
    v = RuleClassifier().classify(_record(owner_team=None))
    check(
        "test_unowned_with_traffic_is_orphaned",
        v.label is Classification.ORPHANED,
        f"got {v.label}",
    )


def test_lifecycle_claim_requires_a_usage_source() -> None:
    """Without traffic, no four-class label is supportable at all."""
    repo_only = frozenset({Source.CODE, Source.OPENAPI, Source.CICD})
    partial = RuleClassifier(consulted=repo_only).classify(_record())
    full = RuleClassifier().classify(_record())
    check(
        "test_lifecycle_claim_requires_a_usage_source",
        not partial.supports_lifecycle_claim
        and full.supports_lifecycle_claim
        and partial.findings,
        f"partial={partial.supports_lifecycle_claim} "
        f"full={full.supports_lifecycle_claim} findings={partial.findings}",
    )


def test_full_scan_evaluates_every_rule() -> None:
    """With all six sources nothing abstains — the simulated path is unchanged."""
    v = RuleClassifier().classify(_record())
    check(
        "test_full_scan_evaluates_every_rule",
        not v.abstained,
        f"unexpectedly abstained: {v.abstained}",
    )


# ---------------------------------------------------------------------------
# Explainability — jury concern #2
# ---------------------------------------------------------------------------
def test_every_verdict_carries_reasons() -> None:
    records = run_discovery(verbose=False, persist=False)
    verdicts = RuleClassifier().classify_all(records)
    bare = [v.endpoint_id for v in verdicts if not v.reasons]
    check("test_every_verdict_carries_reasons", not bare, f"no reasons: {bare}")


def test_verdict_scores_every_class() -> None:
    v = RuleClassifier().classify(_record())
    check(
        "test_verdict_scores_every_class",
        set(v.scores) == {c.value for c in CLASS_ORDER},
        f"got {sorted(v.scores)}",
    )


def test_reasons_reference_real_evidence_keys() -> None:
    """Explanations must cite rules that exist, not invented text."""
    valid = {r.key for r in RULES}
    records = run_discovery(verbose=False, persist=False)
    bad: list[str] = []
    for v in RuleClassifier().classify_all(records):
        bad += [r.key for r in v.reasons if r.key not in valid]
    check("test_reasons_reference_real_evidence_keys", not bad, f"unknown: {set(bad)}")


def test_audit_entry_is_complete() -> None:
    """An auditor must be able to reconstruct the decision from the log alone."""
    v = RuleClassifier().classify(_record(owner_team=None))
    entry = audit_entry(v)
    required = {
        "endpoint_id", "label", "confidence", "decided_by", "risk_score",
        "all_class_scores", "evidence", "recommended_action", "actionable",
    }
    check(
        "test_audit_entry_is_complete",
        required <= set(entry),
        f"missing {required - set(entry)}",
    )


def test_explanations_render_without_error() -> None:
    records = run_discovery(verbose=False, persist=False)
    verdicts = RuleClassifier().classify_all(records)
    try:
        for v in verdicts:
            assert explain(v)
            assert one_line(v)
        assert summarise(verdicts)
        ok, detail = True, ""
    except Exception as exc:  # pragma: no cover
        ok, detail = False, repr(exc)
    check("test_explanations_render_without_error", ok, detail)


# ---------------------------------------------------------------------------
# Metrics arithmetic
# ---------------------------------------------------------------------------
def test_metrics_on_known_pairs() -> None:
    """Hand-computed case: 2 ACTIVE correct, 1 ZOMBIE called ACTIVE.

    ACTIVE: tp=2 fp=1 fn=0 -> precision 2/3, recall 1.0
    ZOMBIE: tp=0 fp=0 fn=1 -> precision 0,   recall 0
    """
    res = evaluate(
        [
            ("a", "ACTIVE", "ACTIVE"),
            ("b", "ACTIVE", "ACTIVE"),
            ("c", "ACTIVE", "ZOMBIE"),
        ]
    )
    a = res.per_class["ACTIVE"]
    z = res.per_class["ZOMBIE"]
    ok = (
        abs(a.precision - 2 / 3) < 1e-9
        and a.recall == 1.0
        and z.recall == 0.0
        and res.correct == 2
        and abs(res.accuracy - 2 / 3) < 1e-9
    )
    check(
        "test_metrics_on_known_pairs",
        ok,
        f"ACTIVE p={a.precision} r={a.recall}, acc={res.accuracy}",
    )


def test_confusion_matrix_totals_match() -> None:
    res = evaluate(
        [("a", "ACTIVE", "ACTIVE"), ("b", "ZOMBIE", "ACTIVE"), ("c", "ZOMBIE", "ZOMBIE")]
    )
    total = sum(sum(row.values()) for row in res.confusion.values())
    check("test_confusion_matrix_totals_match", total == res.total == 3)


# ---------------------------------------------------------------------------
# End-to-end against ground truth
# ---------------------------------------------------------------------------
def test_all_true_zombies_are_caught() -> None:
    """Zombie recall must be total: a missed zombie is an unremediated exposure."""
    truth = by_id()
    records = run_discovery(verbose=False, persist=False)
    verdicts = {v.endpoint_id: v for v in RuleClassifier().classify_all(records)}

    missed = [
        eid
        for eid, ep in truth.items()
        if ep.true_label is Label.ZOMBIE
        and (eid not in verdicts or verdicts[eid].label is not Classification.ZOMBIE)
    ]
    check("test_all_true_zombies_are_caught", not missed, f"missed: {missed}")


def test_no_active_endpoint_is_marked_for_death() -> None:
    """A false ZOMBIE on a live endpoint would cause an outage. Zero tolerance."""
    truth = by_id()
    records = run_discovery(verbose=False, persist=False)
    fatal = [
        v.endpoint_id
        for v in RuleClassifier().classify_all(records)
        if v.is_actionable
        and truth[v.endpoint_id].true_label in (Label.ACTIVE, Label.ORPHANED)
    ]
    check("test_no_active_endpoint_is_marked_for_death", not fatal, f"would kill: {fatal}")


def test_engine_and_estate_taxonomies_agree() -> None:
    """The engine defines its own enum; it must still line up with ground truth."""
    check(
        "test_engine_and_estate_taxonomies_agree",
        {c.value for c in Classification} == {l.value for l in Label},
    )


def test_correlation_beats_single_source() -> None:
    """The project's central claim, asserted as a test.

    If a single authoritative source ever matched the correlated pipeline on
    zombie recall, the entire thesis would be wrong and this must fail loudly.
    """
    from apix.evaluation.benchmark import run_benchmark

    r = run_benchmark()
    full = r["api-exorcist"]["zombies_caught"]
    conv = r["conventional"]["zombies_caught"]
    check(
        "test_correlation_beats_single_source",
        full > conv,
        f"correlated={full}, conventional={conv}",
    )


def main() -> None:
    print("Engine tests\n")
    for fn in [
        test_engine_never_imports_ground_truth,
        test_detection_code_never_reads_answer_key_fields,
        test_no_rule_references_true_label,
        test_healthy_endpoint_is_active,
        test_silent_shadow_endpoint_is_zombie,
        test_used_but_unowned_is_orphaned_not_zombie,
        test_orphaned_is_never_actionable,
        test_deprecation_flag_is_near_decisive,
        test_effectively_silent_counts_as_no_meaningful_traffic,
        test_classifier_is_deterministic,
        test_traffic_rules_abstain_without_traffic_source,
        test_repo_only_scan_does_not_label_healthy_endpoint_zombie,
        test_zombie_without_traffic_evidence_is_not_actionable,
        test_no_evidence_means_indeterminate_not_active,
        test_unowned_without_traffic_is_not_orphaned,
        test_unowned_with_traffic_is_orphaned,
        test_lifecycle_claim_requires_a_usage_source,
        test_full_scan_evaluates_every_rule,
        test_every_verdict_carries_reasons,
        test_verdict_scores_every_class,
        test_reasons_reference_real_evidence_keys,
        test_audit_entry_is_complete,
        test_explanations_render_without_error,
        test_metrics_on_known_pairs,
        test_confusion_matrix_totals_match,
        test_all_true_zombies_are_caught,
        test_no_active_endpoint_is_marked_for_death,
        test_engine_and_estate_taxonomies_agree,
        test_correlation_beats_single_source,
    ]:
        # Already reported by check(); suppressed so that one failure does not
        # hide the state of every test after it.
        with contextlib.suppress(AssertionError):
            fn()

    print(f"\n{_PASS} passed, {_FAIL} failed")
    sys.exit(1 if _FAIL else 0)


if __name__ == "__main__":
    main()
