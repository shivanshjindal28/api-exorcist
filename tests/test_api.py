"""
Tests for the REST API (Phase 5).

Run:  python tests/test_api.py

These run in CI, unlike the ML tests: FastAPI and httpx are in the `dev` extra.
An authentication layer whose security tests are skipped in CI has not been
tested. If FastAPI is absent anyway, every test here skips and says so.

The most important test is `test_every_route_except_health_requires_a_token`.
It reads the routes from the application itself rather than from a list in this
file, so a route added later without authentication fails the build the moment
it exists, instead of whenever someone remembers to add it here.
"""

from __future__ import annotations

import contextlib
import sys
import tempfile
from collections.abc import Iterator
from pathlib import Path
from typing import Any
from urllib.parse import quote

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

try:
    from fastapi.routing import APIRoute
    from fastapi.testclient import TestClient

    HAVE_API = True
except ImportError:  # pragma: no cover - only without the dev extras
    HAVE_API = False

from apix.api.auth import (  # noqa: E402
    Role,
    TokenConfigError,
    TokenStore,
    hash_token,
    new_token,
)

_PASS = 0
_FAIL = 0

APPROVER, VIEWER = "shivansh", "jal"
PIN = "GET /v1/cards/{id}/pin"
DEBUG = "POST /v1/debug/payments/replay"


def check(name: str, condition: bool, detail: str = "") -> None:
    global _PASS, _FAIL
    if condition:
        _PASS += 1
        print(f"  PASS  {name}")
        return
    _FAIL += 1
    print(f"  FAIL  {name}" + (f"\n          {detail}" if detail else ""))
    raise AssertionError(f"{name}: {detail}" if detail else name)


def _skip_without_api(name: str) -> None:
    if HAVE_API:
        return
    print(f"  SKIP  {name}  (FastAPI not installed)")
    with contextlib.suppress(ImportError):
        import pytest

        pytest.skip("FastAPI not installed")


@contextlib.contextmanager
def _client() -> Iterator[tuple[Any, dict[str, str], dict[str, str]]]:
    """A fresh app with its own audit log, and approver and viewer headers."""
    from apix.api.app import default_app

    approver_token, viewer_token = new_token(), new_token()
    store = TokenStore.parse(
        f"{APPROVER}:approver:{hash_token(approver_token)};"
        f"{VIEWER}:viewer:{hash_token(viewer_token)}"
    )
    with tempfile.TemporaryDirectory() as tmp:
        client = TestClient(default_app(Path(tmp) / "audit.jsonl", store))
        yield (
            client,
            {"Authorization": f"Bearer {approver_token}"},
            {"Authorization": f"Bearer {viewer_token}"},
        )


def _routes(client: Any) -> list[tuple[str, str]]:
    out = []
    for route in client.app.routes:
        if isinstance(route, APIRoute):
            for method in route.methods:
                out.append((method, route.path))
    return out


def _call(client: Any, method: str, path: str, headers: dict[str, str] | None = None) -> Any:
    url = path.replace("{endpoint_id:path}", quote(PIN, safe="")).replace(
        "{endpoint_id}", quote(PIN, safe="")
    ).replace("{job_id}", "0123456789ab")       # well formed; no such scan exists
    if method == "POST":
        return client.post(url, json={"endpoint_id": PIN, "approve": False},
                           headers=headers or {})
    return client.get(url, headers=headers or {})


# ---------------------------------------------------------------------------
# Tokens
# ---------------------------------------------------------------------------
def test_token_config_rejects_bad_entries() -> None:
    bad = [
        "alice:approver",                                   # missing digest
        f"alice:admin:{hash_token('x')}",                   # unknown role
        f"alice:viewer:{new_token()}",                      # raw token, not a hash
        f"a:viewer:{hash_token('x')};a:viewer:{hash_token('y')}",  # duplicate name
    ]
    rejected = 0
    for spec in bad:
        try:
            TokenStore.parse(spec)
        except TokenConfigError:
            rejected += 1
    check("test_token_config_rejects_bad_entries", rejected == len(bad),
          f"{rejected} of {len(bad)} malformed configurations rejected")


def test_token_store_authenticates_only_the_right_token() -> None:
    token = new_token()
    store = TokenStore.single("alice", Role.VIEWER, token)
    who = store.authenticate(token)
    check("test_token_store_authenticates_only_the_right_token",
          who is not None and who.name == "alice"
          and store.authenticate(token + "x") is None
          and store.authenticate("") is None
          and token not in store.config_line(),
          "the stored line must contain the hash, never the token")


def test_app_refuses_to_start_without_tokens() -> None:
    _skip_without_api("test_app_refuses_to_start_without_tokens")
    from apix.api.app import create_app
    from apix.api.workspace import Workspace

    with tempfile.TemporaryDirectory() as tmp:
        try:
            create_app(Workspace(Path(tmp) / "a.jsonl"), TokenStore(()))
            started = True
        except ValueError:
            started = False
    check("test_app_refuses_to_start_without_tokens", not started)


# ---------------------------------------------------------------------------
# Authentication and authorisation, over every route
# ---------------------------------------------------------------------------
def test_every_route_except_health_requires_a_token() -> None:
    _skip_without_api("test_every_route_except_health_requires_a_token")
    with _client() as (client, _, _):
        open_routes, checked = [], 0
        for method, path in _routes(client):
            if path == "/v1/health":
                continue
            checked += 1
            if _call(client, method, path).status_code != 401:
                open_routes.append(f"{method} {path}")
    check("test_every_route_except_health_requires_a_token",
          checked >= 14 and not open_routes,
          f"reachable without a token: {open_routes}" if open_routes
          else f"only {checked} routes checked")


def test_unrecognised_token_is_rejected() -> None:
    _skip_without_api("test_unrecognised_token_is_rejected")
    with _client() as (client, _, _):
        r = client.get("/v1/summary", headers={"Authorization": f"Bearer {new_token()}"})
    check("test_unrecognised_token_is_rejected",
          r.status_code == 401 and r.headers.get("www-authenticate") == "Bearer",
          f"{r.status_code} {dict(r.headers)}")


def test_viewer_can_read_but_not_act() -> None:
    _skip_without_api("test_viewer_can_read_but_not_act")
    with _client() as (client, _, viewer):
        reads = {p: _call(client, m, p, viewer).status_code
                 for m, p in _routes(client) if m == "GET"}
        acts = {p: _call(client, m, p, viewer).status_code
                for m, p in _routes(client) if m == "POST"}
    check("test_viewer_can_read_but_not_act",
          acts and all(c == 403 for c in acts.values())
          # A scan id that does not exist is a 404, and a missing required
          # query (a plan names its endpoint) a 422: both still answers given
          # to the viewer, not a refusal of them.
          and all(c == 200 or (c in (404, 422) and "{job_id}" in p) for p, c in reads.items()),
          f"reads {reads}, acts {acts}")


def test_responses_are_never_cached() -> None:
    _skip_without_api("test_responses_are_never_cached")
    with _client() as (client, _, viewer):
        ok = client.get("/v1/inventory", headers=viewer)
        denied = client.get("/v1/inventory")
    check("test_responses_are_never_cached",
          all(r.headers.get("cache-control") == "no-store"
              and r.headers.get("x-content-type-options") == "nosniff"
              for r in (ok, denied)),
          f"{ok.headers} / {denied.headers}")


# ---------------------------------------------------------------------------
# Reads
# ---------------------------------------------------------------------------
def test_summary_states_it_is_simulated() -> None:
    _skip_without_api("test_summary_states_it_is_simulated")
    with _client() as (client, _, viewer):
        s = client.get("/v1/summary", headers=viewer).json()
    check("test_summary_states_it_is_simulated",
          s["mode"] == "simulated" and "nothing real is touched" in s["note"]
          and s["endpoints"] == 25 and s["labels"].get("ZOMBIE") == 8,
          str(s))


def test_endpoint_ids_round_trip_through_urls() -> None:
    _skip_without_api("test_endpoint_ids_round_trip_through_urls")
    with _client() as (client, _, viewer):
        v = client.get("/v1/verdicts/" + quote(PIN, safe=""), headers=viewer)
        missing = client.get("/v1/verdicts/" + quote("GET /nope", safe=""), headers=viewer)
        zombies = client.get("/v1/verdicts?label=ZOMBIE", headers=viewer).json()
    check("test_endpoint_ids_round_trip_through_urls",
          v.status_code == 200 and v.json()["endpoint_id"] == PIN
          and "explanation" in v.json()
          and missing.status_code == 404
          and len(zombies) == 8 and all(z["label"] == "ZOMBIE" for z in zombies),
          f"{v.status_code}, missing {missing.status_code}, zombies {len(zombies)}")


# ---------------------------------------------------------------------------
# Safe Kill through the API
# ---------------------------------------------------------------------------
def test_identity_comes_from_the_token_not_the_body() -> None:
    _skip_without_api("test_identity_comes_from_the_token_not_the_body")
    with _client() as (client, approver, viewer):
        client.post("/v1/safekill/shadow", json={"endpoint_id": PIN}, headers=approver)
        forged = client.post(
            "/v1/safekill/decision",
            json={"endpoint_id": PIN, "approve": True, "approver": "mallory"},
            headers=approver,
        )
        real = client.post("/v1/safekill/decision",
                           json={"endpoint_id": PIN, "approve": True}, headers=approver)
        audit = client.get("/v1/audit", headers=viewer).json()
    approvals = [e for e in audit["entries"] if e["to_state"] == "CANARY_5"]
    check("test_identity_comes_from_the_token_not_the_body",
          forged.status_code == 422
          and real.status_code == 200 and real.json()["state"] == "RETIRED"
          and [e["actor"] for e in approvals] == [APPROVER]
          and audit["chain_ok"],
          f"forged {forged.status_code}, approvals {approvals}")


def test_decision_before_shadow_is_refused() -> None:
    _skip_without_api("test_decision_before_shadow_is_refused")
    with _client() as (client, approver, _):
        r = client.post("/v1/safekill/decision",
                        json={"endpoint_id": PIN, "approve": True}, headers=approver)
    check("test_decision_before_shadow_is_refused", r.status_code == 409,
          f"{r.status_code} {r.text}")


def test_unidentified_traffic_can_never_be_approved() -> None:
    """409 with the advice, the decision stays open, and there is no override.

    Asking to accept the risk is rejected as an unknown field, and declining
    still works: the one decision that can be made.
    """
    _skip_without_api("test_unidentified_traffic_can_never_be_approved")
    with _client() as (client, approver, viewer):
        client.post("/v1/safekill/shadow", json={"endpoint_id": DEBUG}, headers=approver)
        refused = client.post("/v1/safekill/decision",
                              json={"endpoint_id": DEBUG, "approve": True},
                              headers=approver)
        still_pending = [p["endpoint_id"] for p in
                         client.get("/v1/safekill", headers=viewer).json()["pending"]]
        override = client.post(
            "/v1/safekill/decision",
            json={"endpoint_id": DEBUG, "approve": True, "accept_unidentified": True},
            headers=approver,
        )
        declined = client.post("/v1/safekill/decision",
                               json={"endpoint_id": DEBUG, "approve": False},
                               headers=approver)
    check("test_unidentified_traffic_can_never_be_approved",
          refused.status_code == 409 and "authentication" in refused.text
          and DEBUG in still_pending
          and override.status_code == 422
          and declined.status_code == 200 and declined.json()["state"] == "DENIED",
          f"refused {refused.status_code}, pending {still_pending}, "
          f"override {override.status_code}, declined {declined.status_code} "
          f"{declined.text[:120]}")


def test_shadow_is_idempotent() -> None:
    _skip_without_api("test_shadow_is_idempotent")
    with _client() as (client, approver, viewer):
        first = client.post("/v1/safekill/shadow", json={"endpoint_id": PIN},
                            headers=approver).json()
        after_first = client.get("/v1/audit", headers=viewer).json()["total"]
        second = client.post("/v1/safekill/shadow", json={"endpoint_id": PIN},
                             headers=approver).json()
        after_second = client.get("/v1/audit", headers=viewer).json()["total"]
    check("test_shadow_is_idempotent",
          first["state"] == second["state"] == "AWAITING_APPROVAL"
          and after_first == after_second,
          f"audit grew {after_first} -> {after_second}")


def test_non_candidate_cannot_be_shadowed() -> None:
    _skip_without_api("test_non_candidate_cannot_be_shadowed")
    with _client() as (client, approver, _):
        r = client.post("/v1/safekill/shadow",
                        json={"endpoint_id": "GET /v2/accounts/{id}"}, headers=approver)
    check("test_non_candidate_cannot_be_shadowed", r.status_code == 404,
          f"{r.status_code} {r.text}")


def test_audit_chain_verifies_through_the_api() -> None:
    _skip_without_api("test_audit_chain_verifies_through_the_api")
    with _client() as (client, approver, viewer):
        client.post("/v1/safekill/shadow", json={"endpoint_id": PIN}, headers=approver)
        v = client.get("/v1/audit/verify", headers=viewer).json()
    check("test_audit_chain_verifies_through_the_api",
          v["ok"] and v["entries"] > 0, str(v))


# ---------------------------------------------------------------------------
# Phase 7: observability and hardening
# ---------------------------------------------------------------------------
def _metric(text: str, name: str) -> float | None:
    for line in text.splitlines():
        if line.rsplit(" ", 1)[0] == name:
            return float(line.rsplit(" ", 1)[1])
    return None


def test_metrics_need_a_token_and_describe_the_estate() -> None:
    _skip_without_api("test_metrics_need_a_token_and_describe_the_estate")
    with _client() as (client, approver, viewer):
        anonymous = client.get("/metrics")
        client.post("/v1/safekill/shadow", json={"endpoint_id": PIN}, headers=approver)
        r = client.get("/metrics", headers=viewer)
    text = r.text
    check("test_metrics_need_a_token_and_describe_the_estate",
          anonymous.status_code == 401 and r.status_code == 200
          and r.headers["content-type"].startswith("text/plain; version=0.0.4")
          and _metric(text, 'apix_endpoints{label="ZOMBIE"}') == 8
          and _metric(text, "apix_audit_chain_ok") == 1
          and _metric(text, "apix_safekill_awaiting_approval") == 1
          and (_metric(text, "apix_audit_entries") or 0) > 0
          and 'apix_safekill_actions_total{kind="shadow",result="started"} 1' in text,
          f"anonymous={anonymous.status_code}\n{text[:1500]}")


def test_metric_labels_stay_bounded_whatever_path_is_sent() -> None:
    """Labels come from route templates. A raw-path label would let anyone mint
    a new time series per request until the process ran out of memory."""
    import secrets

    _skip_without_api("test_metric_labels_stay_bounded_whatever_path_is_sent")
    sent: list[str] = []
    with _client() as (client, _, viewer):
        for _ in range(30):
            junk = secrets.token_hex(8)
            sent.append(junk)
            client.get(f"/v1/verdicts/GET%20/{junk}", headers=viewer)
            client.get(f"/nowhere/{junk}")
        text = client.get("/metrics", headers=viewer).text
    routes = {
        line.split('route="', 1)[1].split('"', 1)[0]
        for line in text.splitlines() if line.startswith("apix_http_requests_total{")
    }
    check("test_metric_labels_stay_bounded_whatever_path_is_sent",
          not any(j in text for j in sent) and len(routes) <= 4,
          f"route labels: {sorted(routes)}")


def test_auth_failures_are_counted_by_reason() -> None:
    _skip_without_api("test_auth_failures_are_counted_by_reason")
    with _client() as (client, _, viewer):
        client.get("/v1/summary")
        client.get("/v1/summary", headers={"Authorization": "Bearer apx_wrong"})
        client.post("/v1/demo/rescan", headers=viewer)
        text = client.get("/metrics", headers=viewer).text
    got = {r: _metric(text, f'apix_auth_failures_total{{reason="{r}"}}')
           for r in ("missing", "unrecognised", "forbidden")}
    check("test_auth_failures_are_counted_by_reason",
          got == {"missing": 1, "unrecognised": 1, "forbidden": 1}, str(got))


def test_request_ids_are_echoed_only_when_well_formed() -> None:
    _skip_without_api("test_request_ids_are_echoed_only_when_well_formed")
    with _client() as (client, _, _viewer):
        good = client.get("/v1/health", headers={"X-Request-ID": "trace-123.a_b"})
        long = client.get("/v1/health", headers={"X-Request-ID": "x" * 200})
        none = client.get("/v1/health")
    check("test_request_ids_are_echoed_only_when_well_formed",
          good.headers["x-request-id"] == "trace-123.a_b"
          and len(long.headers["x-request-id"]) == 32
          and len(none.headers["x-request-id"]) == 32,
          f"{good.headers.get('x-request-id')} {long.headers.get('x-request-id')}")


def test_oversized_and_unsized_bodies_are_refused() -> None:
    _skip_without_api("test_oversized_and_unsized_bodies_are_refused")

    def chunks() -> Iterator[bytes]:
        yield b'{"endpoint_id": "x"}'

    with _client() as (client, approver, _):
        big = client.post("/v1/safekill/decision", headers=approver,
                          content=b"{" + b" " * 70_000 + b"}")
        unsized = client.post("/v1/safekill/shadow", headers=approver, content=chunks())
        normal = client.post("/v1/safekill/shadow", headers=approver,
                             json={"endpoint_id": PIN})
    check("test_oversized_and_unsized_bodies_are_refused",
          (big.status_code, unsized.status_code, normal.status_code) == (413, 411, 200),
          f"{big.status_code} {unsized.status_code} {normal.status_code}")


def test_swagger_pages_can_be_switched_off() -> None:
    """They load Swagger UI from a CDN; a locked-down deployment turns them off."""
    from apix.api.app import default_app

    _skip_without_api("test_swagger_pages_can_be_switched_off")
    token = new_token()
    store = TokenStore.single("ops", Role.VIEWER, token)
    with tempfile.TemporaryDirectory() as tmp:
        on = TestClient(default_app(Path(tmp) / "a.jsonl", store))
        off = TestClient(default_app(Path(tmp) / "b.jsonl", store, docs=False))
        codes = (on.get("/docs").status_code, off.get("/docs").status_code,
                 off.get("/redoc").status_code)
    check("test_swagger_pages_can_be_switched_off", codes == (200, 404, 404), str(codes))


def test_remote_bind_needs_configured_tokens() -> None:
    """No one-time token on a served bind: stdout there is retained log storage."""
    import io
    import os

    from apix.cli import main

    _skip_without_api("test_remote_bind_needs_configured_tokens")
    saved = os.environ.pop("APIX_API_TOKENS", None)
    out = io.StringIO()
    try:
        with contextlib.redirect_stdout(out):
            code = main(["serve", "--host", "0.0.0.0", "--allow-remote"])
    finally:
        if saved is not None:
            os.environ["APIX_API_TOKENS"] = saved
    check("test_remote_bind_needs_configured_tokens",
          code == 2 and "refusing to mint" in out.getvalue() and "apx_" not in out.getvalue(),
          f"exit {code}: {out.getvalue()}")


def test_a_busy_default_port_moves_on_and_a_busy_chosen_one_is_refused() -> None:
    """A previous `apix serve` left running must not strand the new one.

    It used to bind-fail only after sending the browser to the old server, with a
    token the old server had never seen.
    """
    import socket

    from apix import cli

    holder = socket.socket()
    holder.bind(("127.0.0.1", 0))
    holder.listen()
    busy = holder.getsockname()[1]
    saved = cli.DEFAULT_PORT
    cli.DEFAULT_PORT = busy
    try:
        fallback = cli._choose_port("127.0.0.1", None)
        refused = cli._choose_port("127.0.0.1", busy)
    finally:
        cli.DEFAULT_PORT = saved
        holder.close()
    check("test_a_busy_default_port_moves_on_and_a_busy_chosen_one_is_refused",
          fallback is not None and fallback != busy and refused is None,
          f"fallback={fallback} refused={refused} busy={busy}")


def test_logs_name_the_principal_never_the_token() -> None:
    import io
    import logging

    from apix.api.observe import JsonFormatter

    _skip_without_api("test_logs_name_the_principal_never_the_token")
    stream = io.StringIO()
    handler = logging.StreamHandler(stream)
    handler.setFormatter(JsonFormatter())
    logger = logging.getLogger("apix.api")
    logger.addHandler(handler)
    old_level = logger.level
    logger.setLevel(logging.INFO)
    try:
        with _client() as (client, approver, _):
            client.post("/v1/safekill/shadow", json={"endpoint_id": PIN},
                        headers=approver)
            client.post("/v1/safekill/decision", headers=approver, json={
                "endpoint_id": PIN, "approve": False, "note": "secret-note-text"})
            token = approver["Authorization"].split()[1]
    finally:
        logger.removeHandler(handler)
        logger.setLevel(old_level)
    import json as _json

    lines = [_json.loads(x) for x in stream.getvalue().splitlines() if x]
    events = {d["event"] for d in lines}
    decided = [d for d in lines if d["event"] == "safekill.decision"]
    raw = stream.getvalue()
    check("test_logs_name_the_principal_never_the_token",
          token not in raw and "secret-note-text" not in raw
          and {"request", "safekill.shadow", "safekill.decision"} <= events
          and decided and decided[0]["principal"] == APPROVER
          and isinstance(decided[0]["state"], str)
          and all("request_id" in d for d in lines if d["event"] == "request"),
          raw[:1200])


# ---------------------------------------------------------------------------
if __name__ == "__main__":
    tests = [v for k, v in sorted(globals().items()) if k.startswith("test_")]
    for t in tests:
        with contextlib.suppress(AssertionError):
            t()
    print(f"\n{_PASS} passed, {_FAIL} failed")
    sys.exit(1 if _FAIL else 0)


def test_the_api_imports_without_the_scanning_extras() -> None:
    """The container installs only the api extra. A top-level `import yaml`
    reached through the scanning code stopped it starting; CI's container job
    caught that, and this catches it without Docker."""
    import subprocess

    _skip_without_api("test_the_api_imports_without_the_scanning_extras")
    code = ("import sys; sys.modules['yaml'] = None; sys.modules['semgrep'] = None; "
            "import apix.api.app; print('ok')")
    proc = subprocess.run([sys.executable, "-c", code], capture_output=True, text=True,
                          cwd=str(ROOT), env={**__import__("os").environ,
                                              "PYTHONPATH": str(ROOT / "src")})
    check("test_the_api_imports_without_the_scanning_extras",
          proc.returncode == 0 and "ok" in proc.stdout, proc.stderr[-500:])
