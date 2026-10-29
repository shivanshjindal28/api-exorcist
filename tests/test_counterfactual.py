"""
Counterfactual explanations: what would change a verdict, computed by the
classifier that made it.

The property that matters is faithfulness. A counterfactual that claims a
label must produce that label when its change is applied, and it must never
rest on a source the scan did not consult, or it would explain a decision the
system cannot actually make.
"""

from __future__ import annotations

from apix.connectors.base import Source
from apix.engine.counterfactual import CHANGES, counterfactuals
from apix.engine.rules import RuleClassifier
from apix.live.evidence import Candidate, Signal, label_for
from apix.pipeline import run_discovery

KYC_RAW = "GET /v1/kyc/documents/{id}/raw"
EKYC = "POST /v1/kyc/aadhaar/ekyc"


def _records():
    return {r.endpoint_id: r for r in run_discovery(verbose=False, persist=False)}


def test_every_counterfactual_produces_the_label_it_claims() -> None:
    records = _records()
    clf = RuleClassifier()
    by_key = {c.key: c for c in CHANGES}
    checked = 0
    for rec in records.values():
        verdict = clf.classify(rec)
        for cf in counterfactuals(rec, verdict, clf.classify):
            changed = rec
            for key in cf["changes"]:
                changed = by_key[key].apply(changed)
            after = clf.classify(changed)
            assert after.label.value == cf["label"] != verdict.label.value, (rec.endpoint_id, cf)
            checked += 1
    assert checked > 0


def test_the_zombie_would_be_orphaned_with_real_traffic() -> None:
    rec = _records()[KYC_RAW]
    clf = RuleClassifier()
    verdict = clf.classify(rec)
    flips = counterfactuals(rec, verdict, clf.classify)
    assert verdict.label.value == "ZOMBIE"
    assert any(f["changes"] == ["real_traffic"] and f["label"] == "ORPHANED" for f in flips), flips


def test_the_known_misclassification_names_its_missing_evidence() -> None:
    """The one error on the demo estate: a deprecated endpoint whose team never
    set the specification flag. Its counterfactual should say exactly that."""
    rec = _records()[EKYC]
    clf = RuleClassifier()
    verdict = clf.classify(rec)
    flips = counterfactuals(rec, verdict, clf.classify)
    assert verdict.label.value == "ACTIVE"
    assert any(f["changes"] == ["marked_deprecated"] and f["label"] == "DEPRECATED" for f in flips)


def test_no_counterfactual_rests_on_a_source_that_was_not_consulted() -> None:
    """A repository scan has no traffic: changing traffic cannot move a verdict
    whose traffic rules abstained, so no counterfactual may claim it does."""
    clf = RuleClassifier(consulted=frozenset({Source.CODE, Source.OPENAPI, Source.CICD}))
    for rec in _records().values():
        verdict = clf.classify(rec)
        for f in counterfactuals(rec, verdict, clf.classify):
            assert not {"real_traffic", "went_silent", "has_caller"} & set(f["changes"]), f


def test_candidate_labels_are_unchanged_by_the_refactor() -> None:
    assert label_for(1, {"unused"}) is None
    assert label_for(2, {"unused"}) == "Not used by this project's clients"
    assert label_for(5, {"superseded", "unused"}) == "Likely zombie"
    assert label_for(4, {"unused", "frozen"}) == "Likely zombie"
    assert label_for(3, {"superseded"}) == "Superseded version"


def test_a_candidate_says_what_would_end_its_candidacy() -> None:
    weak = Candidate("GET /x", 2, "Not used by this project's clients", [Signal("unused", 2, "t")])
    flips = weak.to_dict()["counterfactuals"]
    assert flips == [{"if": "this project's own client code called it", "label": "not a candidate", "score": -2}]
    # A candidate already called by a client is not told "if a client called it".
    used = Candidate("GET /y", 3, "Superseded version",
                     [Signal("superseded", 3, "t"), Signal("debug", 2, "t"), Signal("used", -2, "t")])
    assert all("client" not in f["if"] for f in used.to_dict()["counterfactuals"])
