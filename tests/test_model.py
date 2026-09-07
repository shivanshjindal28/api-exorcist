"""
Tests for the learned classifier and its SHAP attribution.

Run:  python tests/test_model.py

These skip cleanly when the ML extras or a trained model are absent, because CI
installs only `.[dev]`. A skipped test says so; it never passes silently.

The test that matters most is `test_statements_describe_observed_values`. SHAP
gives a signed contribution — how strongly an observation pushed toward the
predicted class — and it is tempting to phrase the explanation from that sign.
Doing so reports an unowned endpoint as "an owning team is recorded", which is
the opposite of the truth on the endpoint an operator is about to disable.
"""

from __future__ import annotations

import contextlib
import sys
import warnings
from pathlib import Path

warnings.filterwarnings("ignore")

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from apix.dataset.build import FEATURE_NAMES  # noqa: E402
from apix.engine.model import (  # noqa: E402
    HybridClassifier,
    MLClassifier,
    ModelUnavailable,
)
from apix.engine.rules import RuleClassifier  # noqa: E402
from apix.engine.verdict import Classification, Verdict  # noqa: E402
from apix.pipeline import run_discovery, sources_of  # noqa: E402

_PASS = 0
_FAIL = 0
_SKIP = 0


def check(name: str, condition: bool, detail: str = "") -> None:
    global _PASS, _FAIL
    if condition:
        _PASS += 1
        print(f"  PASS  {name}")
        return
    _FAIL += 1
    print(f"  FAIL  {name}" + (f"\n          {detail}" if detail else ""))
    raise AssertionError(f"{name}: {detail}" if detail else name)


def skip(name: str, why: str) -> None:
    global _SKIP
    _SKIP += 1
    print(f"  SKIP  {name}  ({why})")


def _model_or_none() -> MLClassifier | None:
    m = MLClassifier()
    try:
        m.load()
    except ModelUnavailable:
        return None
    return m


# ---------------------------------------------------------------------------
def test_missing_model_fails_loudly() -> None:
    """A missing model must raise, never silently classify everything ACTIVE."""
    m = MLClassifier(model_path=Path("does-not-exist.joblib"))
    try:
        m.load()
        ok, detail = False, "load() succeeded with no model file"
    except ModelUnavailable as exc:
        ok, detail = "apix train" in str(exc), str(exc)
    check("test_missing_model_fails_loudly", ok, detail)


def test_model_classifies_the_estate() -> None:
    m = _model_or_none()
    if m is None:
        skip("test_model_classifies_the_estate", "no trained model")
        return
    records = run_discovery(verbose=False, persist=False)
    verdicts = m.classify_all(records)
    check(
        "test_model_classifies_the_estate",
        len(verdicts) == len(records)
        and all(isinstance(v, Verdict) for v in verdicts),
        f"{len(verdicts)} verdicts from {len(records)} records",
    )


def test_every_model_verdict_carries_reasons() -> None:
    m = _model_or_none()
    if m is None:
        skip("test_every_model_verdict_carries_reasons", "no trained model")
        return
    records = run_discovery(verbose=False, persist=False)
    bare = [v.endpoint_id for v in m.classify_all(records) if not v.reasons]
    check(
        "test_every_model_verdict_carries_reasons", not bare, f"bare: {bare[:3]}"
    )


def test_reasons_reference_real_features() -> None:
    """Explanations must cite features that exist, not invented text."""
    m = _model_or_none()
    if m is None:
        skip("test_reasons_reference_real_features", "no trained model")
        return
    valid = {f.upper() for f in FEATURE_NAMES}
    records = run_discovery(verbose=False, persist=False)
    bad = [
        r.key
        for v in m.classify_all(records)
        for r in v.reasons
        if r.key not in valid
    ]
    check("test_reasons_reference_real_features", not bad, f"unknown: {set(bad)}")


def test_statements_describe_observed_values() -> None:
    """The bug this test exists for.

    An endpoint with no owner must never be described as having one, regardless
    of which way its SHAP value pointed.
    """
    m = _model_or_none()
    if m is None:
        skip("test_statements_describe_observed_values", "no trained model")
        return

    records = {r.endpoint_id: r for r in run_discovery(verbose=False, persist=False)}
    wrong: list[str] = []
    for v in m.classify_all(list(records.values())):
        rec = records[v.endpoint_id]
        for r in v.reasons:
            if r.key != "HAS_OWNER":
                continue
            claims_owner = "an owning team is recorded" in r.statement
            actually_owned = rec.owner_team is not None
            if claims_owner != actually_owned:
                wrong.append(
                    f"{v.endpoint_id}: says {r.statement!r}, "
                    f"owner={rec.owner_team!r}"
                )
    check(
        "test_statements_describe_observed_values",
        not wrong,
        f"{len(wrong)} contradiction(s): {wrong[:2]}",
    )


def test_confidence_is_a_probability() -> None:
    m = _model_or_none()
    if m is None:
        skip("test_confidence_is_a_probability", "no trained model")
        return
    records = run_discovery(verbose=False, persist=False)
    bad = [
        (v.endpoint_id, v.confidence)
        for v in m.classify_all(records)
        if not 0.0 <= v.confidence <= 1.0
    ]
    check("test_confidence_is_a_probability", not bad, f"{bad[:3]}")


# ---------------------------------------------------------------------------
# The hybrid safety asymmetry
# ---------------------------------------------------------------------------
def test_model_can_veto_but_never_promote() -> None:
    """The model may block a removal; it may not create one.

    Measured on held-out estates the model produces zero false zombies where the
    rules produce seventeen, so it is trusted to say "not dead". It is not
    thereby trusted to say "dead" — the two errors have different consequences.
    """
    m = _model_or_none()
    if m is None:
        skip("test_model_can_veto_but_never_promote", "no trained model")
        return

    records = run_discovery(verbose=False, persist=False)
    rule_verdicts = {
        v.endpoint_id: v
        for v in RuleClassifier(consulted=sources_of()).classify_all(records)
    }
    hybrid = {
        v.endpoint_id: v
        for v in HybridClassifier(
            rules=RuleClassifier(consulted=sources_of()), model=m
        ).classify_all(records)
    }

    promoted = [
        eid
        for eid, v in hybrid.items()
        if v.label is Classification.ZOMBIE
        and rule_verdicts[eid].label is not Classification.ZOMBIE
    ]
    check(
        "test_model_can_veto_but_never_promote",
        not promoted,
        f"model promoted to ZOMBIE: {promoted}",
    )


def test_veto_makes_a_candidate_unactionable() -> None:
    """A vetoed removal candidate must not reach the Safe Kill queue."""
    v = Verdict(
        endpoint_id="GET /v1/looks-dead",
        label=Classification.ZOMBIE,
        confidence=0.9,
        rules_fired=4,
        sources_consulted=frozenset({"TRAFFIC", "CODE", "OPENAPI"}),
    )
    before = v.is_actionable
    v.vetoed_by_model = True
    v.model_label = "ACTIVE"
    v.model_confidence = 0.94
    check(
        "test_veto_makes_a_candidate_unactionable",
        before and not v.is_actionable and "vetoed" in (v.blocked_reason or ""),
        f"before={before} after={v.is_actionable} reason={v.blocked_reason}",
    )


def test_veto_retains_both_opinions() -> None:
    """An auditor must see that the rules proposed removal and the model objected."""
    v = Verdict(
        endpoint_id="GET /v1/x",
        label=Classification.ZOMBIE,
        confidence=0.9,
        rules_fired=3,
        sources_consulted=frozenset({"TRAFFIC"}),
    )
    v.vetoed_by_model = True
    v.model_label = "ORPHANED"
    v.model_confidence = 0.88
    d = v.to_dict()
    check(
        "test_veto_retains_both_opinions",
        d["label"] == "ZOMBIE" and d["blocked_reason"] and "ORPHANED" in d["blocked_reason"],
        f"{d.get('blocked_reason')}",
    )


def test_hybrid_works_without_a_model() -> None:
    """No model installed must degrade to the rules, not crash."""
    hybrid = HybridClassifier(
        rules=RuleClassifier(consulted=sources_of()),
        model=MLClassifier(model_path=Path("does-not-exist.joblib")),
    )
    records = run_discovery(verbose=False, persist=False)
    try:
        verdicts = hybrid.classify_all(records)
        ok = len(verdicts) == len(records)
        detail = ""
    except Exception as exc:
        ok, detail = False, repr(exc)
    check("test_hybrid_works_without_a_model", ok, detail)


def main() -> None:
    print("Model and SHAP tests\n")
    for fn in [
        test_missing_model_fails_loudly,
        test_model_classifies_the_estate,
        test_every_model_verdict_carries_reasons,
        test_reasons_reference_real_features,
        test_statements_describe_observed_values,
        test_confidence_is_a_probability,
        test_model_can_veto_but_never_promote,
        test_veto_makes_a_candidate_unactionable,
        test_veto_retains_both_opinions,
        test_hybrid_works_without_a_model,
    ]:
        with contextlib.suppress(AssertionError):
            fn()

    print(f"\n{_PASS} passed, {_FAIL} failed, {_SKIP} skipped")
    sys.exit(1 if _FAIL else 0)


if __name__ == "__main__":
    main()
