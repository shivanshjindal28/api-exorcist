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
    )
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
          and all(c == 200 for c in reads.values()),
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


def test_unacknowledged_anonymous_traffic_leaves_the_decision_open() -> None:
    """409 rather than an irreversible DENIED, and accepting it then proceeds."""
    _skip_without_api("test_unacknowledged_anonymous_traffic_leaves_the_decision_open")
    with _client() as (client, approver, viewer):
        client.post("/v1/safekill/shadow", json={"endpoint_id": DEBUG}, headers=approver)
        refused = client.post("/v1/safekill/decision",
                              json={"endpoint_id": DEBUG, "approve": True},
                              headers=approver)
        still_pending = [p["endpoint_id"] for p in
                         client.get("/v1/safekill", headers=viewer).json()["pending"]]
        accepted = client.post(
            "/v1/safekill/decision",
            json={"endpoint_id": DEBUG, "approve": True, "accept_unidentified": True},
            headers=approver,
        )
    check("test_unacknowledged_anonymous_traffic_leaves_the_decision_open",
          refused.status_code == 409 and "unidentified" in refused.text
          and DEBUG in still_pending
          and accepted.status_code == 200 and accepted.json()["state"] == "RETIRED",
          f"refused {refused.status_code}, pending {still_pending}, "
          f"accepted {accepted.status_code} {accepted.text[:120]}")


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
if __name__ == "__main__":
    tests = [v for k, v in sorted(globals().items()) if k.startswith("test_")]
    for t in tests:
        with contextlib.suppress(AssertionError):
            t()
    print(f"\n{_PASS} passed, {_FAIL} failed")
    sys.exit(1 if _FAIL else 0)
