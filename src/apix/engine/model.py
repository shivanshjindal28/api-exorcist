"""
The learned classifier, and SHAP attribution for its decisions.

How this fits with the rule layer
---------------------------------
The rule classifier explains a verdict as *additive signed evidence
contributions*. SHAP explains a model prediction as *additive signed feature
contributions*. That correspondence is not a coincidence — it is why additive
scoring was chosen for the rules in the first place, and it means both layers
emit the same `Reason` objects and render through one code path. Nothing in
`explain.py`, the audit log or the dashboard needs to know which layer decided.

Why exact SHAP is affordable here
---------------------------------
Gaspar et al. [9] report SHAP as too expensive for a real-time intrusion
detection system, and choose LIME partly on that basis. Our workload is not
real-time: classification runs per scan, over an inventory of thousands, not per
packet at line rate. `TreeExplainer` computes exact Shapley values for tree
ensembles, and we can pay for them where an IDS cannot. That is the one place
this project benefits from being slower than the systems it borrows from.

The safety asymmetry
--------------------
The model may **veto** a removal, never authorise one. Measured on held-out
estates it produces zero false zombies where the rules produce seventeen — so it
is trustworthy at saying "this is not dead". It is not thereby trustworthy at
saying "this is dead", and the consequences of the two errors are not
comparable: a missed zombie is an exposure that stays on a report, a false zombie
is an outage. `HybridClassifier` encodes that asymmetry rather than averaging the
two opinions.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from apix.dataset.build import FEATURE_NAMES, extract_features
from apix.engine.rules import RuleClassifier
from apix.engine.verdict import CLASS_ORDER, Classification, Reason, Verdict
from apix.inventory.correlator import InventoryRecord

#: Statements for the boolean features, keyed by the value that was *observed*.
#:
#: Selecting the wording from the SHAP sign instead of the observed value is a
#: mistake worth naming: a positive contribution means "this observation pushed
#: toward the predicted class", not "this feature is true". An unowned endpoint
#: pushed toward ZOMBIE by its *lack* of an owner would then be reported as "an
#: owning team is recorded" — the exact opposite of the truth, on the endpoint
#: the operator is about to act on.
_BOOLEAN_PHRASING: dict[str, tuple[str, str]] = {
    # feature: (statement when observed true, statement when observed false)
    "in_openapi_spec": ("documented in the OpenAPI specification", "not documented in the OpenAPI specification"),
    "in_gateway_registry": ("registered with the API gateway", "absent from the gateway registry"),
    "handler_exists_in_code": ("a handler exists in source", "no handler found in source"),
    "deployed_via_pipeline": ("shipped through a deployment pipeline", "no deployment pipeline record"),
    "dns_resolvable": ("still resolvable via DNS", "no DNS record"),
    "observed_on_wire": ("observed carrying traffic", "never observed on the wire"),
    "has_owner": ("an owning team is recorded", "no owning team recorded"),
    "spec_deprecated": ("marked deprecated in the specification", "not marked deprecated"),
    "is_unauthenticated": ("no authentication enforced", "authentication is enforced"),
    "is_legacy_auth": ("legacy API-key authentication", "not using legacy authentication"),
    "handles_sensitive_data": ("handles sensitive data", "does not handle sensitive data"),
}

#: Numeric features, rendered with the observed value because the number is the
#: point: "last used 3650 days ago" says something "time since last use" cannot.
_NUMERIC_PHRASING: dict[str, str] = {
    "source_count": "seen by {v:.0f} of 6 discovery sources",
    "log_daily_calls": "{calls} calls/day",
    "days_since_last_use": "last used {v:.0f} days ago",
    "distinct_callers": "{v:.0f} distinct caller(s)",
    "days_since_last_commit": "handler last committed {v:.0f} days ago",
}

DEFAULT_MODEL_PATH = Path("models") / "classifier.joblib"


class ModelUnavailable(RuntimeError):
    """Raised when the model or its dependencies cannot be loaded."""


class MLClassifier:
    """Gradient-boosted classifier with exact SHAP attribution."""

    name = "model"

    def __init__(
        self,
        model_path: Path | None = None,
        *,
        max_reasons: int = 6,
    ) -> None:
        self.model_path = Path(model_path or DEFAULT_MODEL_PATH)
        self.max_reasons = max_reasons
        self._model: Any = None
        self._explainer: Any = None
        self._classes: list[str] = []

    # ------------------------------------------------------------------
    def load(self) -> None:
        if self._model is not None:
            return
        try:
            import joblib
            import shap
        except ImportError as exc:
            raise ModelUnavailable(
                'the ML layer needs scikit-learn and shap. Run: pip install -e ".[ml]"'
            ) from exc

        if not self.model_path.exists():
            raise ModelUnavailable(
                f"no trained model at {self.model_path}. Run: apix train --save"
            )

        bundle = joblib.load(self.model_path)
        self._model = bundle["model"]
        self._classes = list(bundle["classes"])
        if list(bundle.get("features", [])) != FEATURE_NAMES:
            raise ModelUnavailable(
                "the saved model was trained on a different feature set. "
                "Retrain with: apix train --save"
            )
        # Exact Shapley values for tree ensembles. Affordable because this is a
        # per-scan batch workload, not a per-packet one.
        self._explainer = shap.TreeExplainer(self._model)

    @property
    def available(self) -> bool:
        try:
            self.load()
            return True
        except ModelUnavailable:
            return False

    # ------------------------------------------------------------------
    def classify(self, rec: InventoryRecord) -> Verdict:
        return self.classify_all([rec])[0]

    def classify_all(self, records: list[InventoryRecord]) -> list[Verdict]:
        """Classify in one batch — SHAP is far cheaper vectorised."""
        self.load()
        import numpy as np

        if not records:
            return []

        rows: list[list[float]] = []
        for rec in records:
            feats = extract_features(rec)
            rows.append([feats[name] for name in FEATURE_NAMES])
        X: Any = np.asarray(rows, dtype=float)

        probabilities = self._model.predict_proba(X)
        shap_values = np.asarray(self._explainer.shap_values(X))

        verdicts: list[Verdict] = []
        for i, rec in enumerate(records):
            probs = probabilities[i]
            best = int(np.argmax(probs))
            label = Classification(self._classes[best])

            contributions = _contributions_for(shap_values, i, best)
            reasons = self._reasons(X[i], contributions)

            verdicts.append(
                Verdict(
                    endpoint_id=rec.endpoint_id,
                    label=label,
                    confidence=float(probs[best]),
                    reasons=reasons,
                    scores={
                        cls: float(probs[self._classes.index(cls)])
                        if cls in self._classes else 0.0
                        for cls in (c.value for c in CLASS_ORDER)
                    },
                    decided_by=self.name,
                    risk_score=_risk_of(rec, label),
                    sources_consulted=frozenset(rec.seen_by),
                    rules_fired=len(reasons),
                )
            )
        return verdicts

    # ------------------------------------------------------------------
    def _reasons(self, row: Any, contributions: Any) -> list[Reason]:
        """Turn SHAP values into the same Reason objects the rules emit.

        The statement describes what was *observed*; the signed contribution
        says how strongly that observation pushed toward the predicted class.
        Those are two different things and conflating them produces
        explanations that state the opposite of the facts.
        """
        import math

        pairs = sorted(
            zip(FEATURE_NAMES, contributions, strict=True),
            key=lambda p: -abs(float(p[1])),
        )
        reasons: list[Reason] = []
        for name, value in pairs[: self.max_reasons]:
            contribution = float(value)
            if abs(contribution) < 1e-6:
                continue

            observed = float(row[FEATURE_NAMES.index(name)])

            if name in _BOOLEAN_PHRASING:
                when_true, when_false = _BOOLEAN_PHRASING[name]
                statement = when_true if observed > 0.5 else when_false
            elif name in _NUMERIC_PHRASING:
                # `calls` is only meaningful for the log-scaled traffic feature.
                # Computing it unconditionally overflows: expm1 of a 3650-day
                # staleness value is not a number of requests.
                fields: dict[str, Any] = {"v": observed}
                if name == "log_daily_calls":
                    fields["calls"] = f"{math.expm1(min(observed, 30.0)):,.0f}"
                statement = _NUMERIC_PHRASING[name].format(**fields)
            else:  # pragma: no cover - a new feature without phrasing
                statement = f"{name} = {observed:g}"

            reasons.append(
                Reason(
                    key=name.upper(),
                    statement=statement,
                    evidence_source="MODEL/SHAP",
                    contribution=round(contribution, 4),
                )
            )
        return reasons


# ---------------------------------------------------------------------------
class HybridClassifier:
    """Rules decide; the model may veto a removal but never authorise one.

    This is the arrangement the training comparison actually supports. The rules
    work with no training data, which is what lets a new deployment function on
    day one, and they are auditable line by line. The model is measurably better
    at *not* calling live endpoints dead, so it is given exactly that job.
    """

    name = "rules+model"

    def __init__(
        self,
        rules: RuleClassifier | None = None,
        model: MLClassifier | None = None,
    ) -> None:
        self.rules = rules or RuleClassifier()
        self.model = model or MLClassifier()

    def classify_all(self, records: list[InventoryRecord]) -> list[Verdict]:
        verdicts = self.rules.classify_all(records)
        if not self.model.available:
            return verdicts

        model_verdicts = {
            v.endpoint_id: v for v in self.model.classify_all(records)
        }

        for v in verdicts:
            if v.label is not Classification.ZOMBIE:
                continue
            mv = model_verdicts.get(v.endpoint_id)
            if mv is None or mv.label is Classification.ZOMBIE:
                continue

            # The model disagrees with a removal candidate. Downgrade it to a
            # finding and record why, rather than silently overwriting either
            # opinion — an auditor must be able to see that both ran.
            v.decided_by = "rules+model"
            v.vetoed_by_model = True
            v.model_label = mv.label.value
            v.model_confidence = round(mv.confidence, 4)
            v.reasons = [
                *v.reasons,
                Reason(
                    key="MODEL_VETO",
                    statement=(
                        f"the learned model disagrees, classifying this as "
                        f"{mv.label.value} at {mv.confidence:.0%} confidence"
                    ),
                    evidence_source="MODEL/SHAP",
                    contribution=-abs(mv.confidence),
                ),
                *mv.reasons[:3],
            ]
        return verdicts


# ---------------------------------------------------------------------------
def _contributions_for(shap_values: Any, row: int, class_index: int) -> Any:
    """Extract this row's per-feature contributions for the predicted class.

    SHAP's output shape varies by version and problem: multiclass tree models
    give (n_samples, n_features, n_classes) in recent releases and a list of
    per-class arrays in older ones. Handling both keeps the integration from
    breaking on a routine upgrade.
    """
    arr = shap_values
    if arr.ndim == 3:
        return arr[row, :, class_index]
    if arr.ndim == 2:
        return arr[row]
    return arr[class_index][row]


def _risk_of(rec: InventoryRecord, label: Classification) -> int:
    from apix.engine.rules import _risk_score

    return _risk_score(rec, label)
