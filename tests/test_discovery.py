"""
Tests for the discovery layer.

The most important test in this file is test_no_ground_truth_leakage.
If a connector or the feature extractor ever reads `true_label`, every
accuracy number the project reports becomes meaningless. That failure
would be silent and would not show up as a crash, so it is asserted
explicitly.
"""

from __future__ import annotations

import inspect
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import apix.connectors.discovery as discovery_mod
import apix.connectors.gateway as gateway_mod
import apix.inventory.correlator as correlator_mod
from apix.dataset.build import FEATURE_NAMES, build, extract_features
from apix.pipeline import run_discovery
from apix.simulated_env.estate import ESTATE, Label, by_id

# --------------------------------------------------------------------
# Integrity
# --------------------------------------------------------------------

def test_no_ground_truth_leakage():
    """No connector, correlator, or feature may reference ground truth.

    `true_label` and `decay_story` exist only for evaluation. Any read of
    them inside the detection path would inflate accuracy artificially.
    """
    forbidden = ("true_label", "decay_story")
    for mod in (gateway_mod, discovery_mod, correlator_mod):
        src = inspect.getsource(mod)
        for token in forbidden:
            assert token not in src, (
                f"GROUND TRUTH LEAK: '{token}' referenced in {mod.__name__}. "
                "Detection code must never read the answer key."
            )

    # The feature extractor must also stay clean.
    feat_src = inspect.getsource(extract_features)
    for token in forbidden:
        assert token not in feat_src, f"GROUND TRUTH LEAK in extract_features: {token}"


def test_features_are_purely_numeric():
    """Every feature must be numeric, for model compatibility."""
    records = run_discovery(verbose=False)
    for rec in records:
        feats = extract_features(rec)
        assert set(feats) == set(FEATURE_NAMES), "feature set drifted from FEATURE_NAMES"
        for k, v in feats.items():
            assert isinstance(v, float), f"feature {k} is {type(v)}, expected float"


# --------------------------------------------------------------------
# Coverage / correlation behaviour
# --------------------------------------------------------------------

def test_every_endpoint_is_discovered():
    """Correlation must recover the full estate.

    Code scanning sees every endpoint, so the union across sources should
    equal the estate exactly. Losing one here means a correlation bug.
    """
    records = run_discovery(verbose=False)
    assert len(records) == len(ESTATE)
    assert {r.endpoint_id for r in records} == {e.endpoint_id for e in ESTATE}


def test_no_single_source_sees_everything_except_code():
    """The premise of the project: authoritative sources have blind spots.

    If the gateway or the spec saw 100% of the estate, multi-source
    correlation would be unnecessary and the project's core argument
    would collapse.
    """
    records = run_discovery(verbose=False)
    total = len(records)

    def seen(src: str) -> int:
        return sum(1 for r in records if src in r.seen_by)

    assert seen("GATEWAY") < total, "gateway should not see the whole estate"
    assert seen("OPENAPI") < total, "spec should not see the whole estate"
    assert seen("TRAFFIC") < total, "silent endpoints must be invisible to traffic"
    # Code is the one source that sees every handler, by construction.
    assert seen("CODE") == total


def test_shadow_endpoints_are_flagged():
    """Endpoints in neither the spec nor the gateway must be flagged."""
    records = run_discovery(verbose=False)
    truth = by_id()
    for r in records:
        gt = truth[r.endpoint_id]
        if not gt.in_openapi_spec and not gt.in_gateway_registry:
            assert "SHADOW_CANDIDATE" in r.flags, f"{r.endpoint_id} not flagged as shadow"


def test_unauthenticated_endpoints_are_flagged():
    records = run_discovery(verbose=False)
    truth = by_id()
    for r in records:
        if truth[r.endpoint_id].auth.value == "NONE":
            assert "UNAUTHENTICATED" in r.flags, f"{r.endpoint_id} missing UNAUTHENTICATED"


def test_active_endpoints_are_not_shadow_flagged():
    """Guard against false positives on healthy, high-traffic endpoints.

    Flagging an ACTIVE endpoint as a shadow candidate is the failure mode
    that would make the tool untrustworthy in production.
    """
    records = run_discovery(verbose=False)
    truth = by_id()
    for r in records:
        if truth[r.endpoint_id].true_label is Label.ACTIVE:
            assert "SHADOW_CANDIDATE" not in r.flags, (
                f"false positive: ACTIVE endpoint {r.endpoint_id} flagged as shadow"
            )
            assert "NO_TRAFFIC_IN_WINDOW" not in r.flags


def test_deprecated_but_used_endpoints_still_show_traffic():
    """Deprecated-but-still-needed endpoints must not look dead.

    These are the endpoints that must NOT be killed (e.g. the PSP partner
    still on payments v2). If discovery reported them as silent, the
    Safe Kill stage in week 9 could take down a live integration.
    """
    records = run_discovery(verbose=False)
    truth = by_id()
    for r in records:
        if truth[r.endpoint_id].true_label is Label.DEPRECATED:
            assert r.observed_on_wire, f"{r.endpoint_id} should show live traffic"
            assert "NO_TRAFFIC_IN_WINDOW" not in r.flags


# --------------------------------------------------------------------
# Dataset
# --------------------------------------------------------------------

def test_dataset_is_labelled_and_complete():
    records = run_discovery(verbose=False)
    rows = build(records)
    assert len(rows) == len(ESTATE)
    for row in rows:
        assert row["label"] in {"ACTIVE", "DEPRECATED", "ORPHANED", "ZOMBIE"}


def test_dataset_contains_all_four_classes():
    """A single-class dataset would be useless for training."""
    records = run_discovery(verbose=False)
    rows = build(records)
    present = {r["label"] for r in rows}
    assert present == {"ACTIVE", "DEPRECATED", "ORPHANED", "ZOMBIE"}


def test_spec_deprecated_flag_is_imperfect():
    """The deprecated flag must not trivially equal the label.

    If every DEPRECATED endpoint carried the flag, the classifier could
    learn a one-feature shortcut and report meaningless accuracy.
    """
    deprecated = [e for e in ESTATE if e.true_label is Label.DEPRECATED]
    flagged = [e for e in deprecated if e.spec_deprecated_flag]
    assert 0 < len(flagged) < len(deprecated), (
        "spec_deprecated_flag must be an imperfect proxy for the label"
    )


if __name__ == "__main__":
    import traceback

    tests = [v for k, v in sorted(globals().items()) if k.startswith("test_")]
    passed = failed = 0
    for t in tests:
        try:
            t()
            print(f"  PASS  {t.__name__}")
            passed += 1
        except AssertionError as e:
            print(f"  FAIL  {t.__name__}\n        {e}")
            failed += 1
        except Exception:
            print(f"  ERROR {t.__name__}")
            traceback.print_exc()
            failed += 1
    print(f"\n{passed} passed, {failed} failed")
    sys.exit(1 if failed else 0)
