"""
Tests for the synthetic estate generator.

Run:  python tests/test_generator.py

The most important test here is `test_in_service_classes_are_not_separable`. An
early version of the generator drew traffic, recency and code age from a
different distribution for each lifecycle story, which made the classes almost
linearly separable on raw features. A gradient-boosted model then scored 0.968
F1 on DEPRECATED while barely using `spec_deprecated` at all — it had learned the
generator's parameters, not the concept.

A generated dataset is only worth training on if it is honestly hard. These
tests encode that, so the artifact cannot quietly return.
"""

from __future__ import annotations

import contextlib
import statistics
import sys
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from apix.simulated_env.estate import Label  # noqa: E402
from apix.simulated_env.generator import (  # noqa: E402
    EstateProfile,
    generate_estate,
    generate_many,
)

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
def test_generation_is_deterministic() -> None:
    """A reported result must be reproducible from its seed alone."""
    a = generate_estate(7)
    b = generate_estate(7)
    same = len(a) == len(b) and all(
        x.endpoint_id == y.endpoint_id
        and x.true_label == y.true_label
        and x.daily_calls == y.daily_calls
        for x, y in zip(a, b, strict=True)
    )
    check("test_generation_is_deterministic", same)


def test_different_seeds_give_different_estates() -> None:
    a, b = generate_estate(1), generate_estate(2)
    check(
        "test_different_seeds_give_different_estates",
        {e.endpoint_id for e in a} != {e.endpoint_id for e in b},
    )


def test_all_four_classes_appear_at_scale() -> None:
    counts: Counter[str] = Counter()
    for _seed, est in generate_many(40):
        counts.update(e.true_label.value for e in est)
    missing = {"ACTIVE", "DEPRECATED", "ORPHANED", "ZOMBIE"} - set(counts)
    check(
        "test_all_four_classes_appear_at_scale",
        not missing and min(counts.values()) >= 30,
        f"counts={dict(counts)} missing={missing}",
    )


def test_scale_is_sufficient_to_train() -> None:
    """The whole point: enough of the rarest class to learn anything."""
    counts: Counter[str] = Counter()
    for _seed, est in generate_many(120):
        counts.update(e.true_label.value for e in est)
    check(
        "test_scale_is_sufficient_to_train",
        sum(counts.values()) > 2000 and counts["ORPHANED"] > 150,
        f"total={sum(counts.values())} orphaned={counts['ORPHANED']}",
    )


# ---------------------------------------------------------------------------
# The anti-artifact tests
# ---------------------------------------------------------------------------
def _medians(n: int = 60) -> dict[str, dict[str, float]]:
    buckets: dict[str, dict[str, list[float]]] = {}
    for _seed, est in generate_many(n):
        for e in est:
            b = buckets.setdefault(
                e.true_label.value, {"calls": [], "use": []}
            )
            b["calls"].append(float(e.daily_calls))
            b["use"].append(float(e.last_meaningful_use_days_ago))
    return {
        k: {m: statistics.median(v) for m, v in vals.items()}
        for k, vals in buckets.items()
    }


def test_in_service_classes_are_not_separable() -> None:
    """ACTIVE, DEPRECATED and ORPHANED must look alike on usage features.

    In a real estate a deprecated endpoint can be busy — a partner still calling
    it is often *why* the retirement stalled — and an active admin endpoint can
    be nearly idle. If the generator separates them, a model can score well
    without learning anything transferable.
    """
    med = _medians()
    calls = [med[k]["calls"] for k in ("ACTIVE", "DEPRECATED", "ORPHANED")]
    ratio = max(calls) / max(1.0, min(calls))
    check(
        "test_in_service_classes_are_not_separable",
        ratio < 2.0,
        f"median daily_calls differ by {ratio:.1f}x — too separable: {calls}",
    )


def test_zombies_remain_genuinely_distinguishable() -> None:
    """The converse guard: zombies really are different, and must stay so.

    Overlapping everything would make the dataset impossible rather than
    honest. Absence of use is a real property of a real zombie.
    """
    med = _medians()
    check(
        "test_zombies_remain_genuinely_distinguishable",
        med["ZOMBIE"]["calls"] < 1 and med["ZOMBIE"]["use"] > 100,
        f"zombie medians={med['ZOMBIE']}",
    )


def test_deprecation_flag_is_never_reliable() -> None:
    """The observability ceiling has to be present, and below 1.0.

    If every deprecated endpoint carried the flag, the class would be trivially
    detectable and the evaluation would be measuring nothing. Cassieri et al.
    found real teams forget; the generator must too.
    """
    flagged = total = 0
    for _seed, est in generate_many(60):
        for e in est:
            if e.true_label is Label.DEPRECATED:
                total += 1
                flagged += bool(e.spec_deprecated_flag)
    rate = flagged / total if total else 0.0
    check(
        "test_deprecation_flag_is_never_reliable",
        0.30 < rate < 0.85,
        f"flag rate {rate:.3f} — outside the plausible band",
    )


def test_auth_does_not_encode_the_label() -> None:
    """Auth scheme must follow endpoint age, not lifecycle state.

    Keying auth off the label made API-key authentication impossible for an
    ACTIVE endpoint, handing the model a free "not active" signal. Real
    production endpoints authenticate with API keys all the time.
    """
    legacy_by_label: Counter[str] = Counter()
    total_by_label: Counter[str] = Counter()
    for _seed, est in generate_many(60):
        for e in est:
            total_by_label[e.true_label.value] += 1
            if e.auth.value == "API_KEY":
                legacy_by_label[e.true_label.value] += 1
    active_rate = legacy_by_label["ACTIVE"] / max(1, total_by_label["ACTIVE"])
    check(
        "test_auth_does_not_encode_the_label",
        active_rate > 0.05,
        f"only {active_rate:.3f} of ACTIVE endpoints use API_KEY — "
        "auth is leaking the label",
    )


def test_dependencies_follow_usage() -> None:
    """Callers are a consequence of being used, not an independent draw."""
    bad = []
    for _seed, est in generate_many(30):
        for e in est:
            if e.daily_calls == 0 and e.internal_callers:
                bad.append(e.endpoint_id)
    check(
        "test_dependencies_follow_usage",
        not bad,
        f"{len(bad)} silent endpoint(s) have callers, e.g. {bad[:3]}",
    )


def test_profiles_vary_between_estates() -> None:
    """Each organisation has its own observation discipline."""
    import random

    profiles = [EstateProfile.draw(random.Random(s)) for s in range(30)]
    spread = max(p.spec_discipline for p in profiles) - min(
        p.spec_discipline for p in profiles
    )
    check(
        "test_profiles_vary_between_estates",
        spread > 0.2,
        f"spec_discipline spread only {spread:.3f}",
    )


def test_generated_estate_runs_through_the_pipeline() -> None:
    """The generator's output must work with the unmodified connectors."""
    from apix.pipeline import run_discovery

    est = generate_estate(99)
    records = run_discovery(verbose=False, persist=False, estate=est)
    check(
        "test_generated_estate_runs_through_the_pipeline",
        len(records) == len(est) and all(r.flags is not None for r in records),
        f"{len(records)} records from {len(est)} endpoints",
    )


def main() -> None:
    print("Estate generator tests\n")
    for fn in [
        test_generation_is_deterministic,
        test_different_seeds_give_different_estates,
        test_all_four_classes_appear_at_scale,
        test_scale_is_sufficient_to_train,
        test_in_service_classes_are_not_separable,
        test_zombies_remain_genuinely_distinguishable,
        test_deprecation_flag_is_never_reliable,
        test_auth_does_not_encode_the_label,
        test_dependencies_follow_usage,
        test_profiles_vary_between_estates,
        test_generated_estate_runs_through_the_pipeline,
    ]:
        with contextlib.suppress(AssertionError):
            fn()

    print(f"\n{_PASS} passed, {_FAIL} failed")
    sys.exit(1 if _FAIL else 0)


if __name__ == "__main__":
    main()
