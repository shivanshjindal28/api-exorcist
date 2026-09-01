"""
Labelled dataset construction for the ML classification engine.

Addresses jury ask #1: "identify the dataset for the ML engine."

Why the dataset is synthetic
----------------------------
No public dataset of zombie / shadow / orphaned APIs exists. Real API
inventories are among the most sensitive artefacts an organisation
holds — publishing one would be publishing a map of the attack surface —
so no bank has released one, and the academic literature contains no
labelled corpus. Public API collections (APIs.guru, RapidAPI) list
*documented, live* APIs only, which is precisely the class we do not
need to detect.

We therefore generate a labelled corpus from the simulated estate, whose
decay patterns are modelled on the mechanisms documented in the
literature (incomplete version migrations, decommissioned products left
running, dissolved teams, debug routes never removed, gateway/DNS rules
outliving the code they point to).

This is a legitimate and standard approach when ground truth is
unobtainable, but it must be stated as a limitation: the classifier is
validated against decay patterns we ourselves modelled. The honest claim
is "the engine correctly recovers known decay patterns from partial,
disagreeing evidence" — not "the engine is validated on production bank
data." The paper's evaluation section must say exactly that.

Feature design
--------------
Features are derived ONLY from the correlated inventory — that is, only
from what the connectors could observe. Ground-truth labels are attached
afterwards, by endpoint id, and are never available as an input feature.
This separation is what makes the accuracy figure meaningful.
"""

from __future__ import annotations

import csv
import json
from pathlib import Path
from typing import Any

from apix.config import load as load_settings
from apix.inventory.correlator import InventoryRecord
from apix.simulated_env.estate import by_id

# Feature order is fixed and explicit. Stability matters because the
# explainability layer reports feature importances by name.
FEATURE_NAMES: list[str] = [
    # --- visibility / documentation ---
    "in_openapi_spec",
    "in_gateway_registry",
    "handler_exists_in_code",
    "deployed_via_pipeline",
    "source_count",             # how many of the 6 sources saw it
    # --- reachability ---
    "dns_resolvable",
    # --- usage ---
    "observed_on_wire",
    "log_daily_calls",          # log1p-scaled: call volumes span 0..3.1M
    "days_since_last_use",
    "distinct_callers",
    # --- ownership ---
    "has_owner",
    # --- lifecycle ---
    "spec_deprecated",
    "days_since_last_commit",
    # --- security posture ---
    "is_unauthenticated",
    "is_legacy_auth",
    "handles_sensitive_data",
]

LABELS = ["ACTIVE", "DEPRECATED", "ORPHANED", "ZOMBIE"]

# Sentinel for "no usage ever observed". Chosen well above the 6-month
# staleness threshold so tree models can split on it cleanly.
NEVER_USED_DAYS = 3650


def extract_features(rec: InventoryRecord) -> dict[str, float]:
    """Turn one inventory record into a numeric feature vector.

    Every value here is observable. Nothing reads ground truth.
    """
    import math

    last_use = rec.last_seen_days_ago
    if last_use is None:
        last_use = NEVER_USED_DAYS

    return {
        "in_openapi_spec": float(rec.in_openapi_spec),
        "in_gateway_registry": float(rec.in_gateway_registry),
        "handler_exists_in_code": float(rec.handler_exists_in_code),
        "deployed_via_pipeline": float(rec.deployed_via_pipeline),
        "source_count": float(len(rec.seen_by)),
        "dns_resolvable": float(rec.dns_resolvable),
        "observed_on_wire": float(rec.observed_on_wire),
        # log1p compresses a 0..3,100,000 range into ~0..15 so that no
        # single high-traffic endpoint dominates distance-based models.
        "log_daily_calls": float(math.log1p(max(rec.daily_calls, 0))),
        "days_since_last_use": float(last_use),
        "distinct_callers": float(rec.distinct_callers),
        "has_owner": float(rec.owner_team is not None),
        "spec_deprecated": float(rec.spec_deprecated),
        "days_since_last_commit": float(rec.days_since_last_commit or 0),
        "is_unauthenticated": float(rec.auth_scheme == "NONE"),
        "is_legacy_auth": float(rec.auth_scheme == "API_KEY"),
        "handles_sensitive_data": float(
            rec.data_classification in ("PII", "FINANCIAL")
        ),
    }


def build(records: list[InventoryRecord]) -> list[dict[str, Any]]:
    """Build labelled rows: features + ground-truth label."""
    truth = by_id()
    rows: list[dict[str, Any]] = []
    for rec in records:
        gt = truth.get(rec.endpoint_id)
        if gt is None:
            # Discovered something not in the estate — impossible here,
            # but in production this is an unlabelled sample.
            continue
        row: dict[str, Any] = {"endpoint_id": rec.endpoint_id, "service": rec.service}
        row.update(extract_features(rec))
        row["label"] = gt.true_label.value
        rows.append(row)
    return rows


def class_balance(rows: list[dict[str, Any]]) -> dict[str, int]:
    out: dict[str, int] = {}
    for r in rows:
        out[r["label"]] = out.get(r["label"], 0) + 1
    return out


def write_csv(rows: list[dict[str, Any]], path: Path) -> None:
    cols = ["endpoint_id", "service", *FEATURE_NAMES, "label"]
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=cols)
        w.writeheader()
        w.writerows(rows)


def main() -> None:
    from apix.pipeline import run_discovery

    records = run_discovery(verbose=False)
    rows = build(records)

    out_dir = load_settings().ensure_data_dir()
    write_csv(rows, out_dir / "dataset.csv")
    (out_dir / "dataset.json").write_text(json.dumps(rows, indent=2))

    bal = class_balance(rows)
    print("Labelled dataset for the ML engine")
    print(f"  samples  : {len(rows)}")
    print(f"  features : {len(FEATURE_NAMES)}")
    print(f"  classes  : {len(LABELS)}")
    print()
    print("  class balance:")
    for lbl in LABELS:
        n = bal.get(lbl, 0)
        pct = 100.0 * n / len(rows) if rows else 0
        print(f"    {lbl:<11} {n:>3}  ({pct:4.1f}%)  {'#' * n}")
    print()
    print(f"  written to: {out_dir/'dataset.csv'}")
    print()
    print("  NOTE: 25 samples cannot train a model — ORPHANED has two.")
    print("  What is settled here is the schema, the provenance and the")
    print("  labelling method. Volume is Phase 3: parameterised generation")
    print("  of many estates, held out whole so a model must generalise")
    print("  across environments rather than memorise one.")


if __name__ == "__main__":
    main()
