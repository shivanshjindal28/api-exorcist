"""
Usage evidence from access logs, and what is built on it: lifecycle labels on
real code, retirement plans, exports, drift between scans and the portfolio.

The rules under test are the ones that keep a false ZOMBIE (an outage) from
being produced: absence counts only where the logs cover the service, only
over a long enough window, and failed requests are never use.
"""

from __future__ import annotations

import csv
import gzip
import io
import json
from datetime import date
from typing import Any

import pytest

from apix.scanning.compare import changes
from apix.scanning.exports import inventory_csv, openapi_stubs, sarif
from apix.scanning.retire import plan
from apix.scanning.sensitivity import classify, enrich
from apix.traffic import analyse, parse_files
from apix.traffic.logs import clean_path, parse_time


def _ep(method: str, path: str, service: str = "shop", **kw: Any) -> dict[str, Any]:
    return {"id": f"{method} {path}", "method": method, "path": path, "service": service,
            "owner": kw.pop("owner", "payments-team"), "documented": kw.pop("documented", True),
            **kw}


def _combined(day: int, method: str, target: str, status: int = 200,
              ip: str = "10.0.0.1") -> str:
    return (f'{ip} - - [{day:02d}/Oct/2026:10:00:00 +0000] "{method} {target} HTTP/1.1" '
            f'{status} 10 "-" "curl/8"')


def _run(endpoints: list[dict[str, Any]], lines: list[str]) -> dict[str, Any]:
    _, requests = parse_files([("access.log", "\n".join(lines).encode())])
    return analyse(endpoints, requests)


# ---------------------------------------------------------------------------
# Reading logs
# ---------------------------------------------------------------------------
def test_three_log_formats_are_read() -> None:
    text = "\n".join([
        _combined(1, "GET", "/v1/orders"),
        'http 2026-10-02T10:00:00.000Z app/lb 9.9.9.9:443 10.0.0.1:80 0.1 0.1 0.1 200 200 1 1 '
        '"GET https://bank.example:443/v1/orders/7 HTTP/1.1" "ua"',
        json.dumps({"request": {"method": "POST", "uri": "/v1/orders"},
                    "response": {"status": 201}, "client_ip": "1.2.3.4",
                    "started_at": 1791800000000}),
        json.dumps({"httpMethod": "GET", "resourcePath": "/v1/orders/{id}", "status": "200",
                    "requestTime": "03/Oct/2026:10:00:00 +0000", "ip": "5.6.7.8"}),
        "this is not a log line",
    ])
    parsed, reqs = parse_files([("mixed.log", text.encode())])
    assert [(r.method, r.path, r.status) for r in reqs] == [
        ("GET", "/v1/orders", 200), ("GET", "/v1/orders/7", 200),
        ("POST", "/v1/orders", 201), ("GET", "/v1/orders/{id}", 200)]
    assert all(r.at is not None for r in reqs)
    summary = parsed.files[0]
    assert (summary.lines, summary.parsed) == (5, 4)


def test_query_strings_and_addresses_never_survive_parsing() -> None:
    line = _combined(1, "GET", "/v1/login?otp=123456&token=secret", ip="203.0.113.7")
    _, reqs = parse_files([("a.log", line.encode())])
    r = reqs[0]
    assert r.path == "/v1/login"
    assert "203.0.113.7" not in repr(r) and len(r.client) == 16
    # A fresh, unstored salt per import: the same address hashes differently.
    _, again = parse_files([("a.log", line.encode())])
    assert again[0].client != r.client


def test_gzip_rotated_logs_are_read() -> None:
    data = gzip.compress((_combined(1, "GET", "/v1/orders") + "\n").encode())
    parsed, reqs = parse_files([("access.log.2.gz", data)])
    assert len(reqs) == 1 and parsed.files[0].format == "combined (gzip)"


def test_an_unrecognised_file_says_so() -> None:
    parsed, reqs = parse_files([("notes.txt", b"hello\nworld\n")])
    assert not reqs and "no line was recognised" in parsed.files[0].note


@pytest.mark.parametrize(("raw", "path"), [
    ("https://h:443/a/b?x=1", "/a/b"), ("//a//b/", "/a/b"), ("/a%20b", "/a b"), ("", "/")])
def test_paths_are_cleaned(raw: str, path: str) -> None:
    assert clean_path(raw) == path


def test_times_in_every_common_shape() -> None:
    for raw in ("01/Oct/2026:10:00:00 +0000", "2026-10-01T10:00:00Z", 1790848800,
                "1790848800000"):
        t = parse_time(raw)
        assert t is not None and t.year == 2026


# ---------------------------------------------------------------------------
# Matching and classifying
# ---------------------------------------------------------------------------
def test_the_most_literal_route_wins() -> None:
    eps = [_ep("GET", "/users/{id}"), _ep("GET", "/users/me")]
    r = _run(eps, [_combined(1, "GET", "/users/me"), _combined(9, "GET", "/users/42")])
    assert r["endpoints"]["GET /users/me"]["requests"] == 1
    assert r["endpoints"]["GET /users/{id}"]["requests"] == 1


def test_a_gateway_prefix_is_found_and_reported() -> None:
    r = _run([_ep("GET", "/v1/orders")], [_combined(1, "GET", "/api/v1/orders")])
    assert r["endpoints"]["GET /v1/orders"]["requests"] == 1
    assert r["gateway_prefixes"] == ["/api"]


def test_the_four_lifecycle_labels() -> None:
    eps = [
        _ep("GET", "/v1/orders"),
        _ep("GET", "/v1/refunds", owner=None),
        _ep("DELETE", "/v1/orders/{id}", deprecated_in_spec=True),
        _ep("POST", "/v1/legacy/export"),
    ]
    r = _run(eps, [
        _combined(1, "GET", "/v1/orders"), _combined(20, "GET", "/v1/orders", ip="10.0.0.2"),
        _combined(5, "GET", "/v1/refunds"),
        _combined(6, "DELETE", "/v1/orders/9"),
    ])
    labels = {k: v["lifecycle"] for k, v in r["endpoints"].items()}
    assert labels == {"GET /v1/orders": "ACTIVE", "GET /v1/refunds": "ORPHANED",
                      "DELETE /v1/orders/{id}": "DEPRECATED",
                      "POST /v1/legacy/export": "ZOMBIE"}
    assert r["endpoints"]["GET /v1/orders"]["clients"] == 2
    # The rule of three, stated: 19 silent days bound the rate below 1 per ~6 days.
    assert "19 days" in r["endpoints"]["POST /v1/legacy/export"]["reason"]


def test_failed_requests_are_probing_not_use() -> None:
    eps = [_ep("GET", "/v1/orders"), _ep("GET", "/v1/debug/dump")]
    r = _run(eps, [_combined(1, "GET", "/v1/orders"), _combined(20, "GET", "/v1/orders"),
                   _combined(9, "GET", "/v1/debug/dump", status=401)])
    dump = r["endpoints"]["GET /v1/debug/dump"]
    assert dump["lifecycle"] == "ZOMBIE" and dump["failed"] == 1
    assert "probing" in dump["reason"]


def test_absence_counts_only_where_the_logs_cover_the_service() -> None:
    eps = [_ep("GET", "/v1/orders"), _ep("GET", "/billing/invoices", service="billing")]
    r = _run(eps, [_combined(1, "GET", "/v1/orders"), _combined(20, "GET", "/v1/orders")])
    row = r["endpoints"]["GET /billing/invoices"]
    assert row["lifecycle"] == "INDETERMINATE" and "do not cover it" in row["reason"]
    assert r["uncovered_services"] == ["billing"]


def test_a_short_window_never_produces_a_zombie() -> None:
    eps = [_ep("GET", "/v1/orders"), _ep("GET", "/v1/old")]
    r = _run(eps, [_combined(1, "GET", "/v1/orders"), _combined(3, "GET", "/v1/orders")])
    assert r["endpoints"]["GET /v1/old"]["lifecycle"] == "INDETERMINATE"
    assert "at least 7" in r["endpoints"]["GET /v1/old"]["reason"]


def test_probes_and_preflights_are_not_judged() -> None:
    eps = [_ep("GET", "/v1/orders"), _ep("GET", "/health")]
    r = _run(eps, [_combined(1, "GET", "/v1/orders"), _combined(20, "OPTIONS", "/v1/orders")])
    assert r["endpoints"]["GET /health"]["lifecycle"] == "INDETERMINATE"
    assert r["preflight"] == 1 and r["endpoints"]["GET /v1/orders"]["requests"] == 1


def test_traffic_the_code_does_not_explain_is_reported() -> None:
    r = _run([_ep("GET", "/v1/orders")], [
        _combined(1, "GET", "/v1/orders"),
        _combined(2, "GET", "/v2/beta/accounts/12345", ip="10.0.0.5"),
        _combined(3, "GET", "/v2/beta/accounts/67890", ip="10.0.0.6"),
        _combined(4, "GET", "/wp-admin/setup.php", status=404),
    ])
    assert r["shadow_routes"] == [{"method": "GET", "path": "/v2/beta/accounts/{id}",
                                   "requests": 2, "ok": 2, "failed": 0, "clients": 2,
                                   "last_seen": "2026-10-03T10:00:00+00:00"}]
    assert [p["path"] for p in r["probing"]] == ["/wp-admin/setup.php"]


# ---------------------------------------------------------------------------
# Built on it
# ---------------------------------------------------------------------------
@pytest.mark.parametrize(("path", "category"), [
    ("/identity/api/auth/v2/check-otp", "Authentication"),
    ("/v1/payments/transfer", "Payments"), ("/v1/cards/{id}/pin", "Authentication"),
    ("/v1/kyc/documents/{id}/raw", "Identity and KYC"), ("/users/v1/_debug", "Administration"),
    ("/v1/accounts/{id}", "Accounts and customers"), ("/v1/products", "General")])
def test_sensitivity_is_read_from_the_path(path: str, category: str) -> None:
    assert classify(path)["category"] == category


def test_retirement_is_blocked_by_use_and_by_missing_evidence() -> None:
    ep = _ep("POST", "/v1/legacy/{id}/export", file="app/legacy.py", line=12)
    unused = {"lifecycle": "ZOMBIE", "ok": 0, "reason": "no successful request"}
    used = {"lifecycle": "ACTIVE", "ok": 40}
    ready = plan(ep, unused, today=date(2026, 10, 1))
    assert ready["ready"] and ready["sunset"] == "2026-12-30"
    assert "location ~ ^/v1/legacy/[^/]+/export$" in ready["steps"][0]["snippet"]
    assert ready["steps"][3]["where"] == ["app/legacy.py:12"]
    assert not plan(ep, used)["ready"] and "Do not remove" in plan(ep, used)["blockers"][0]
    assert not plan(ep, None)["ready"]
    assert not plan({**ep, "owner": None}, unused)["ready"]


def _job(endpoints: list[dict[str, Any]], job_id: str = "a" * 12) -> dict[str, Any]:
    return {"id": job_id, "kind": "github", "target": "github.com/acme/bank",
            "finished_at": "2026-10-15T00:00:00+00:00",
            "report": {"endpoints": endpoints, "details": {"commit": "abc123"},
                       "candidates": []}}


def test_exports() -> None:
    eps = [_ep("GET", "/v1/orders", file="app.py", line=3),
           _ep("POST", "/v1/debug", service="=HYPERLINK(1)", documented=False,
               candidate={"label": "Debug or test endpoint", "score": 2,
                          "signals": [{"key": "debug", "weight": 2, "text": "debug"}]})]
    job = _job(eps)
    enrich(job["report"])
    s = sarif(job, None)
    rules = [r["ruleId"] for r in s["runs"][0]["results"]]
    assert s["version"] == "2.1.0" and rules == ["ZombieCandidate", "ShadowEndpoint"]
    assert s["runs"][0]["versionControlProvenance"][0]["revisionId"] == "abc123"
    rows = list(csv.reader(io.StringIO(inventory_csv(job, None, {}))))
    # A value that starts like a formula is data in a spreadsheet, never a formula.
    assert any(cell == "'=HYPERLINK(1)" for row in rows for cell in row)
    stubs = openapi_stubs(job)
    assert list(stubs["paths"]) == ["/v1/debug"]
    assert stubs["paths"]["/v1/debug"]["post"]["x-apix-candidate"] == "Debug or test endpoint"


def test_drift_between_two_scans() -> None:
    old = _job([_ep("GET", "/v1/orders"), _ep("GET", "/v1/old")], "b" * 12)
    new = _job([_ep("GET", "/v1/orders", documented=False), _ep("GET", "/v1/debug",
                documented=False, candidate={"label": "x", "score": 2, "signals": []})])
    c = changes(new, old)
    assert c["added"] == ["GET /v1/debug"] and c["added_undocumented"] == ["GET /v1/debug"]
    assert c["removed"] == ["GET /v1/old"]
    assert c["became_undocumented"] == ["GET /v1/orders"]
    assert c["new_candidates"] == ["GET /v1/debug"]
    # Both at commit abc123: whatever differs came from the scanner, and says so.
    assert c["same_commit"] is True


# ---------------------------------------------------------------------------
# Over HTTP
# ---------------------------------------------------------------------------
fastapi = pytest.importorskip("fastapi")

from tests.test_scans import SPEC, _client, _wait  # noqa: E402


def _scanned(client: Any, approver: dict[str, str]) -> str:
    job_id: str = client.post("/v1/scans/upload", headers=approver, files=[
        ("files", ("shop/docs/openapi.yaml", SPEC, "text/yaml"))]).json()["id"]
    assert _wait(client, approver, job_id)["status"] == "done"
    return job_id


def test_logs_are_imported_over_http_and_recorded_in_the_audit_chain() -> None:
    logs = "\n".join([_combined(1, "GET", "/v1/orders?account=123"),
                      _combined(15, "GET", "/v1/orders", ip="10.0.0.2")]).encode()
    with _client() as (client, approver, viewer, _):
        job_id = _scanned(client, approver)
        refused = client.post(f"/v1/scans/{job_id}/traffic", headers=viewer,
                              files=[("files", ("a.log", logs, "text/plain"))])
        junk = client.post(f"/v1/scans/{job_id}/traffic", headers=approver,
                           files=[("files", ("a.log", b"nope", "text/plain"))])
        done = client.post(f"/v1/scans/{job_id}/traffic", headers=approver,
                           files=[("files", ("access.log", logs, "text/plain"))])
        page = client.get(f"/v1/scans/{job_id}/audit", headers=viewer).json()
        stored = json.dumps(client.get(f"/v1/scans/{job_id}", headers=viewer).json())
    assert refused.status_code == 403
    assert junk.status_code == 422 and "Supported" in junk.json()["detail"]
    assert done.status_code == 200, done.text
    usage = done.json()["traffic"]["endpoints"]
    assert usage["GET /v1/orders"]["lifecycle"] in ("ACTIVE", "ORPHANED")
    assert usage["DELETE /v1/orders/{id}"]["lifecycle"] == "ZOMBIE"
    last = page["entries"][-1]
    assert (last["to_state"], last["actor"]) == ("USAGE_IMPORTED", "ann")
    assert len(last["evidence"]["usage_sha256"]) == 64 and page["chain"]["ok"]
    assert "account=123" not in stored and "10.0.0.2" not in stored


def test_plan_exports_and_portfolio_over_http() -> None:
    with _client() as (client, approver, viewer, _):
        job_id = _scanned(client, approver)
        p = client.get(f"/v1/scans/{job_id}/plan", headers=viewer,
                       params={"endpoint": "DELETE /v1/orders/{id}"})
        missing = client.get(f"/v1/scans/{job_id}/plan", headers=viewer,
                             params={"endpoint": "GET /nope"})
        out = {f: client.get(f"/v1/scans/{job_id}/export/{f}", headers=viewer)
               for f in ("sarif", "csv", "openapi", "pdf")}
        folio = client.get("/v1/portfolio", headers=viewer).json()
        again = client.post(f"/v1/scans/{job_id}/rescan", headers=approver)
    assert p.status_code == 200 and p.json()["ready"] is False   # no usage evidence yet
    assert missing.status_code == 404
    assert out["sarif"].json()["version"] == "2.1.0"
    assert "attachment" in out["sarif"].headers["content-disposition"]
    assert out["csv"].text.startswith("endpoint,method,path")
    assert out["openapi"].status_code == 200 and out["pdf"].status_code == 404
    assert folio["totals"]["projects"] == 1 and folio["projects"][0]["id"] == job_id
    assert again.status_code == 422 and "upload it again" in again.json()["detail"]
