"""
Training and honestly evaluating the ML classifier.

The question this module exists to answer
-----------------------------------------
Not "how accurate is the model?" but **"does a learned model beat the
deterministic rules we already have?"** — because if it does not, the correct
engineering decision for a security product in a regulated environment is to
ship the auditable one and say so.

That framing is why the rule baseline is scored on the *same held-out estates*
in the same run. A model number reported on its own means nothing.

Three design choices that make the result defensible
----------------------------------------------------
**Split by estate, never by endpoint.** Endpoints within one estate share that
organisation's observation biases — how well it documents, how disciplined its
gateway registry is. Splitting by endpoint would put those correlations on both
sides of the split and inflate every score. `GroupShuffleSplit` on the estate
seed means the model is always tested on organisations it has never seen.

**No ground truth reaches the features.** Features come only from the correlated
inventory, exactly as in production. The label is attached afterwards, by
endpoint id.

**The rule baseline runs on identical data.** Same estates, same split, same
records. Any difference is the model, not the pipeline.

Usage:
    apix train                 # 120 estates, held out by estate
    apix train --estates 300   # more data
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from apix.dataset.build import FEATURE_NAMES, extract_features
from apix.engine.rules import RuleClassifier
from apix.evaluation.metrics import EvaluationResult, evaluate
from apix.pipeline import run_discovery, sources_of
from apix.simulated_env.generator import generate_many

#: Fraction of estates held out for testing.
TEST_FRACTION = 0.30


@dataclass
class Sample:
    estate_seed: int
    endpoint_id: str
    features: list[float]
    label: str
    rule_prediction: str


@dataclass
class TrainingReport:
    n_estates: int = 0
    n_samples: int = 0
    n_train: int = 0
    n_test: int = 0
    train_estates: int = 0
    test_estates: int = 0
    model_name: str = ""
    model_result: EvaluationResult | None = None
    rule_result: EvaluationResult | None = None
    feature_importance: list[tuple[str, float]] = field(default_factory=list)
    label_counts: dict[str, int] = field(default_factory=dict)
    saved_to: str | None = None
    error: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "n_estates": self.n_estates,
            "n_samples": self.n_samples,
            "train_estates": self.train_estates,
            "test_estates": self.test_estates,
            "n_train": self.n_train,
            "n_test": self.n_test,
            "model": self.model_name,
            "saved_to": self.saved_to,
            "label_counts": self.label_counts,
            "model_result": self.model_result.to_dict() if self.model_result else None,
            "rule_result": self.rule_result.to_dict() if self.rule_result else None,
            "feature_importance": [
                {"feature": f, "importance": round(v, 5)}
                for f, v in self.feature_importance
            ],
        }


# ---------------------------------------------------------------------------
def build_samples(n_estates: int, *, verbose: bool = True) -> list[Sample]:
    """Run the full pipeline over many generated estates and collect samples.

    The rule classifier's prediction is recorded per endpoint at the same time,
    so the baseline is scored on exactly the same records the model sees.
    """
    samples: list[Sample] = []
    classifier = RuleClassifier(consulted=sources_of())

    for i, (seed, estate) in enumerate(generate_many(n_estates), start=1):
        if verbose and i % 25 == 0:
            print(f"    {i}/{n_estates} estates ...")
        truth = {e.endpoint_id: e.true_label.value for e in estate}
        records = run_discovery(verbose=False, persist=False, estate=estate)
        verdicts = {v.endpoint_id: v for v in classifier.classify_all(records)}

        for rec in records:
            if rec.endpoint_id not in truth:
                continue
            feats = extract_features(rec)
            samples.append(
                Sample(
                    estate_seed=seed,
                    endpoint_id=rec.endpoint_id,
                    features=[feats[name] for name in FEATURE_NAMES],
                    label=truth[rec.endpoint_id],
                    rule_prediction=verdicts[rec.endpoint_id].label.value,
                )
            )
    return samples


def train_and_compare(
    n_estates: int = 120,
    *,
    seed: int = 42,
    verbose: bool = True,
    save_to: Any = None,
) -> TrainingReport:
    """Train a model and score it against the rule baseline on held-out estates.

    `save_to` persists the fitted model together with the feature list it was
    trained on, so a later scan can refuse to use it if the features have since
    changed rather than silently scoring garbage.
    """
    report = TrainingReport(n_estates=n_estates)

    try:
        import numpy as np
        from sklearn.ensemble import HistGradientBoostingClassifier
        from sklearn.model_selection import GroupShuffleSplit
    except ImportError:
        report.error = (
            'scikit-learn is not installed. Run: pip install -e ".[ml]"'
        )
        return report

    if verbose:
        print(f"  Generating and scanning {n_estates} estates ...")
    samples = build_samples(n_estates, verbose=verbose)
    report.n_samples = len(samples)

    counts: dict[str, int] = {}
    for s in samples:
        counts[s.label] = counts.get(s.label, 0) + 1
    report.label_counts = counts

    X = np.array([s.features for s in samples], dtype=float)
    y = np.array([s.label for s in samples])
    groups = np.array([s.estate_seed for s in samples])

    # Group split: whole estates go to one side or the other, never split.
    splitter = GroupShuffleSplit(
        n_splits=1, test_size=TEST_FRACTION, random_state=seed
    )
    train_idx, test_idx = next(splitter.split(X, y, groups))

    report.n_train, report.n_test = len(train_idx), len(test_idx)
    report.train_estates = len(set(groups[train_idx]))
    report.test_estates = len(set(groups[test_idx]))

    if verbose:
        print(
            f"  Training on {report.train_estates} estates "
            f"({report.n_train} endpoints), testing on "
            f"{report.test_estates} unseen estates ({report.n_test})"
        )

    model = HistGradientBoostingClassifier(
        max_iter=300,
        learning_rate=0.08,
        max_depth=6,
        # The estate is imbalanced by construction, as a real one is. Balancing
        # class weights stops the model from ignoring ORPHANED, the rarest and
        # the one whose confusion with ZOMBIE would cause an outage.
        class_weight="balanced",
        random_state=seed,
    )
    model.fit(X[train_idx], y[train_idx])
    report.model_name = type(model).__name__

    predictions = model.predict(X[test_idx])
    report.model_result = evaluate(
        [
            (samples[i].endpoint_id, str(pred), samples[i].label)
            for i, pred in zip(test_idx, predictions, strict=True)
        ]
    )

    # The baseline, on exactly the same held-out endpoints.
    report.rule_result = evaluate(
        [
            (samples[i].endpoint_id, samples[i].rule_prediction, samples[i].label)
            for i in test_idx
        ]
    )

    report.feature_importance = _permutation_importance(
        model, X[test_idx], y[test_idx], seed=seed
    )

    if save_to is not None:
        import joblib

        save_to = Path(save_to)
        save_to.parent.mkdir(parents=True, exist_ok=True)
        joblib.dump(
            {
                "model": model,
                "classes": [str(c) for c in model.classes_],
                "features": list(FEATURE_NAMES),
                "n_estates": n_estates,
                "trained_on": report.n_train,
                "seed": seed,
            },
            save_to,
        )
        report.saved_to = str(save_to)
        if verbose:
            print(f"  Model saved to {save_to}")

    return report


def _permutation_importance(
    model: Any, X: Any, y: Any, *, seed: int
) -> list[tuple[str, float]]:
    """Which features the model actually relies on.

    Permutation importance rather than a built-in attribute: it measures the
    drop in accuracy when one feature is shuffled, which is a statement about
    this model on this data rather than about how the trees were grown.
    """
    try:
        from sklearn.inspection import permutation_importance
    except ImportError:  # pragma: no cover
        return []

    result = permutation_importance(
        model, X, y, n_repeats=5, random_state=seed, scoring="accuracy"
    )
    pairs = list(zip(FEATURE_NAMES, result.importances_mean, strict=True))
    return sorted(pairs, key=lambda p: -p[1])


# ---------------------------------------------------------------------------
def format_comparison(report: TrainingReport) -> str:
    """The honest side-by-side."""
    if report.error:
        return f"  {report.error}"
    assert report.model_result and report.rule_result
    m, r = report.model_result, report.rule_result

    lines = [
        "=" * 78,
        "MODEL vs RULES — scored on estates neither has seen",
        "=" * 78,
        "",
        f"  {report.n_estates} estates, {report.n_samples} endpoints",
        f"  train: {report.train_estates} estates / {report.n_train} endpoints",
        f"  test : {report.test_estates} estates / {report.n_test} endpoints",
        f"  model: {report.model_name}",
        "",
        "  Split is by ESTATE, not by endpoint. Endpoints within one estate",
        "  share that organisation's observation biases; splitting by endpoint",
        "  would put those correlations on both sides and inflate every score.",
        "",
        f"  {'metric':<22}{'rules':>10}{'model':>10}{'delta':>10}",
        "  " + "-" * 52,
    ]

    for name, rv, mv in [
        ("accuracy", r.accuracy, m.accuracy),
        ("macro precision", r.macro_precision, m.macro_precision),
        ("macro recall", r.macro_recall, m.macro_recall),
        ("macro F1", r.macro_f1, m.macro_f1),
    ]:
        delta = mv - rv
        mark = "+" if delta > 0.0005 else (" " if abs(delta) <= 0.0005 else "")
        lines.append(f"  {name:<22}{rv:>10.3f}{mv:>10.3f}{mark}{delta:>9.3f}")

    lines += ["", f"  {'per class F1':<22}{'rules':>10}{'model':>10}{'delta':>10}",
              "  " + "-" * 52]
    for cls in ("ACTIVE", "DEPRECATED", "ORPHANED", "ZOMBIE"):
        rf, mf = r.per_class[cls].f1, m.per_class[cls].f1
        d = mf - rf
        lines.append(f"  {cls:<22}{rf:>10.3f}{mf:>10.3f}{'+' if d > 0.0005 else ' '}{d:>9.3f}")

    # The safety property, stated separately because it is not negotiable.
    lines += ["", "  Safety — false ZOMBIE (would cause an outage):"]
    for label, res in (("rules", r), ("model", m)):
        fp = res.per_class["ZOMBIE"].fp
        prec = res.per_class["ZOMBIE"].precision
        lines.append(
            f"    {label:<8} {fp:>4} false zombie(s)   precision {prec:.3f}"
        )

    if report.feature_importance:
        lines += ["", "  What the model actually relies on (permutation importance):"]
        for feat, imp in report.feature_importance[:8]:
            bar = "#" * max(0, int(imp * 200))
            lines.append(f"    {feat:<26}{imp:>7.4f}  {bar}")

    return "\n".join(lines)


def verdict_line(report: TrainingReport) -> str:
    """What to actually do, weighing the safety-critical class separately.

    Macro-F1 averages all four classes equally, and that is the wrong weighting
    for this product. A false ZOMBIE is an outage; a missed DEPRECATED is a
    ticket nobody filed. A verdict driven by the average alone would hide a
    difference in the one class where errors are expensive.
    """
    if report.error or not (report.model_result and report.rule_result):
        return ""
    m, r = report.model_result, report.rule_result
    d = m.macro_f1 - r.macro_f1
    m_fp, r_fp = m.per_class["ZOMBIE"].fp, r.per_class["ZOMBIE"].fp
    m_zf, r_zf = m.per_class["ZOMBIE"].f1, r.per_class["ZOMBIE"].f1

    lines = ["  VERDICT"]

    if abs(d) <= 0.01:
        lines.append(
            f"  Overall the two are indistinguishable "
            f"(macro-F1 {m.macro_f1:.3f} vs {r.macro_f1:.3f})."
        )
    elif d > 0:
        lines.append(f"  The model leads on aggregate (macro-F1 +{d:.3f}).")
    else:
        lines.append(f"  The rules lead on aggregate (macro-F1 {d:+.3f}).")

    if m_fp < r_fp:
        lines.append(
            f"  But on the class that matters operationally it is not close:"
            f"\n  the model produces {m_fp} false zombie(s) against the rules'"
            f" {r_fp}"
            f"\n  (ZOMBIE F1 {m_zf:.3f} vs {r_zf:.3f}). Every false zombie is a"
            "\n  candidate outage, so this difference outweighs the average."
        )
        lines.append(
            "\n  RECOMMENDATION: keep the rules as the day-one classifier — they"
            "\n  need no training data and are auditable line by line — and use"
            "\n  the model to veto removal candidates the rules propose."
        )
    elif m_fp > r_fp:
        lines.append(
            f"  However the model produces {m_fp} false zombie(s) against the"
            f"\n  rules' {r_fp}. In this product that is an outage, so the"
            "\n  aggregate gain does not justify adopting it."
        )
        lines.append("\n  RECOMMENDATION: ship the rules.")
    else:
        lines.append(
            f"  Both produce {m_fp} false zombie(s), so neither is safer."
            "\n\n  RECOMMENDATION: ship the rules — equal accuracy, and they are"
            "\n  auditable and work with no training data."
        )

    dep_gap = m.per_class["DEPRECATED"].f1 - r.per_class["DEPRECATED"].f1
    if abs(dep_gap) > 0.02:
        worse = "model" if dep_gap < 0 else "rules"
        lines.append(
            f"\n  Note: DEPRECATED is the weakest class for both ({worse} weaker"
            f"\n  by {abs(dep_gap):.3f} F1). Neither can exceed the rate at which"
            "\n  teams actually set the deprecation flag — the ceiling is"
            "\n  observability, not the algorithm."
        )

    return "\n".join(lines)


def save_report(report: TrainingReport, path: Any) -> None:
    path.write_text(json.dumps(report.to_dict(), indent=2))
