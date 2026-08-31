"""
Classification metrics, implemented from definitions.

No scikit-learn dependency here. Two reasons: the discovery pipeline runs on the
standard library alone and that property is worth keeping, and a team that has to
defend these numbers to a jury should be able to point at the arithmetic that
produced them.

Definitions used throughout, per class c:

    TP = predicted c, actually c
    FP = predicted c, actually something else
    FN = predicted something else, actually c

    precision = TP / (TP + FP)      "when it says c, how often is it right"
    recall    = TP / (TP + FN)      "of the real c's, how many did it find"
    F1        = 2PR / (P + R)       harmonic mean

Macro-averaging is reported alongside accuracy because the estate is imbalanced
(12 ACTIVE against 2 ORPHANED). Accuracy alone would let a classifier that never
predicts ORPHANED still look respectable; macro-F1 does not.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from engine.verdict import CLASS_ORDER, Classification


@dataclass
class ClassMetrics:
    label: str
    support: int = 0          # how many truly belong to this class
    tp: int = 0
    fp: int = 0
    fn: int = 0

    @property
    def precision(self) -> float:
        denom = self.tp + self.fp
        return self.tp / denom if denom else 0.0

    @property
    def recall(self) -> float:
        denom = self.tp + self.fn
        return self.tp / denom if denom else 0.0

    @property
    def f1(self) -> float:
        p, r = self.precision, self.recall
        return 2 * p * r / (p + r) if (p + r) else 0.0

    def to_dict(self) -> dict[str, Any]:
        return {
            "label": self.label,
            "support": self.support,
            "tp": self.tp,
            "fp": self.fp,
            "fn": self.fn,
            "precision": round(self.precision, 4),
            "recall": round(self.recall, 4),
            "f1": round(self.f1, 4),
        }


@dataclass
class EvaluationResult:
    per_class: dict[str, ClassMetrics] = field(default_factory=dict)
    confusion: dict[str, dict[str, int]] = field(default_factory=dict)
    errors: list[dict[str, str]] = field(default_factory=list)
    total: int = 0
    correct: int = 0

    @property
    def accuracy(self) -> float:
        return self.correct / self.total if self.total else 0.0

    @property
    def macro_f1(self) -> float:
        if not self.per_class:
            return 0.0
        return sum(m.f1 for m in self.per_class.values()) / len(self.per_class)

    @property
    def macro_precision(self) -> float:
        if not self.per_class:
            return 0.0
        return sum(m.precision for m in self.per_class.values()) / len(self.per_class)

    @property
    def macro_recall(self) -> float:
        if not self.per_class:
            return 0.0
        return sum(m.recall for m in self.per_class.values()) / len(self.per_class)

    def to_dict(self) -> dict[str, Any]:
        return {
            "total": self.total,
            "correct": self.correct,
            "accuracy": round(self.accuracy, 4),
            "macro_precision": round(self.macro_precision, 4),
            "macro_recall": round(self.macro_recall, 4),
            "macro_f1": round(self.macro_f1, 4),
            "per_class": {k: v.to_dict() for k, v in self.per_class.items()},
            "confusion": self.confusion,
            "errors": self.errors,
        }


def evaluate(pairs: list[tuple[str, str, str]]) -> EvaluationResult:
    """Score predictions against ground truth.

    `pairs` is a list of (endpoint_id, predicted_label, true_label).
    """
    names = [c.value for c in CLASS_ORDER]
    res = EvaluationResult(
        per_class={n: ClassMetrics(label=n) for n in names},
        confusion={t: {p: 0 for p in names} for t in names},
    )

    for endpoint_id, pred, truth in pairs:
        res.total += 1
        if truth in res.confusion and pred in res.confusion[truth]:
            res.confusion[truth][pred] += 1
        if truth in res.per_class:
            res.per_class[truth].support += 1

        if pred == truth:
            res.correct += 1
            if truth in res.per_class:
                res.per_class[truth].tp += 1
        else:
            if pred in res.per_class:
                res.per_class[pred].fp += 1
            if truth in res.per_class:
                res.per_class[truth].fn += 1
            res.errors.append(
                {"endpoint_id": endpoint_id, "predicted": pred, "actual": truth}
            )

    return res


# ---------------------------------------------------------------------------
# Rendering
# ---------------------------------------------------------------------------
def format_confusion(res: EvaluationResult) -> str:
    names = [c.value for c in CLASS_ORDER]
    w = max(len(n) for n in names) + 1

    lines = ["Confusion matrix  (rows = actual, columns = predicted)", ""]
    header = " " * (w + 2) + "".join(f"{n[:4]:>7}" for n in names) + "   total"
    lines.append(header)
    lines.append(" " * (w + 2) + "-" * (7 * len(names) + 8))

    for t in names:
        row = res.confusion.get(t, {})
        total = sum(row.values())
        cells = ""
        for p in names:
            n = row.get(p, 0)
            # Mark the diagonal so correct predictions are readable at a glance
            cells += f"{(str(n) + '*') if (p == t and n) else str(n):>7}"
        lines.append(f"  {t:<{w}}{cells}{total:>8}")

    lines.append("")
    lines.append("  * = correct predictions (diagonal)")
    return "\n".join(lines)


def format_report(res: EvaluationResult, title: str = "Classification report") -> str:
    lines = [title, ""]
    lines.append(
        f"  {'class':<12}{'precision':>11}{'recall':>9}{'f1':>8}{'support':>9}"
    )
    lines.append("  " + "-" * 49)
    for c in CLASS_ORDER:
        m = res.per_class[c.value]
        lines.append(
            f"  {m.label:<12}{m.precision:>11.3f}{m.recall:>9.3f}"
            f"{m.f1:>8.3f}{m.support:>9}"
        )
    lines.append("  " + "-" * 49)
    lines.append(
        f"  {'macro avg':<12}{res.macro_precision:>11.3f}"
        f"{res.macro_recall:>9.3f}{res.macro_f1:>8.3f}{res.total:>9}"
    )
    lines.append("")
    lines.append(
        f"  accuracy: {res.accuracy:.3f}  ({res.correct}/{res.total} correct)"
    )
    return "\n".join(lines)


def format_errors(res: EvaluationResult) -> str:
    if not res.errors:
        return "No misclassifications."
    lines = [f"Misclassifications ({len(res.errors)})", ""]
    for e in res.errors:
        lines.append(
            f"  {e['endpoint_id']}\n"
            f"      predicted {e['predicted']}, actually {e['actual']}"
        )
    return "\n".join(lines)
