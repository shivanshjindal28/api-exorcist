"""
Acceptance tests against real public repositories, with known answers.

Run:  APIX_REALWORLD=1 python -m pytest tests/test_realworld.py -v

Every other test here uses fixtures written by the people who wrote the
scanner, and fixtures shaped like the code they test kept passing while real
projects broke: Windows refused crAPI's long paths, Connexion and API-first
Spring handlers went unseen, OpenAPI tags were read as owners, and crAPI's two
real zombie endpoints came out as ordinary rows. These tests download real
projects and assert what a person who knows them would expect, including what
must NOT be flagged. They need the network and take a few minutes, so they are
skipped unless APIX_REALWORLD=1.

The answers come from the projects themselves, not from the scanner:
  - OWASP crAPI keeps /v2/check-otp, which its own code comments call the
    non-secure version (no attempt limit), beside /v3/check-otp (locks after
    10 tries); its web app calls only v3, and only v4.0 of login-with-token,
    never v2.7.
  - VAmPI documents a debug endpoint, /users/v1/_debug, and /createdb.
  - spring-petclinic-rest serves GET /owners beside its paged v2.
  - The FastAPI template's React app never calls readItem, testEmail or the
    private createUser; it does call readItems.
"""

from __future__ import annotations

import os
from functools import cache
from typing import Any

import pytest

pytestmark = pytest.mark.skipif(
    os.environ.get("APIX_REALWORLD") != "1",
    reason="downloads real repositories; set APIX_REALWORLD=1",
)


@cache
def report(slug: str) -> dict[str, Any]:
    from apix.live.scan import scan_repository
    from apix.scanning.report import check, repository_report

    result = scan_repository(slug, verbose=False)
    return repository_report(result, has_history=True,
                             acquired=check("Project downloaded", "ok", slug))


def candidates(slug: str) -> dict[str, dict[str, Any]]:
    return {c["endpoint_id"]: c for c in report(slug)["candidates"]}


def ids(slug: str) -> set[str]:
    return {e["id"] for e in report(slug)["endpoints"]}


def test_crapi_old_otp_and_login_versions_are_likely_zombies() -> None:
    c = candidates("OWASP/crAPI")
    for old in ("POST /identity/api/auth/v2/check-otp",
                "POST /identity/api/auth/v2.7/user/login-with-token"):
        assert old in c, f"{old} not flagged; candidates: {sorted(c)[:12]}"
        assert c[old]["label"] == "Likely zombie", c[old]
    for current in ("POST /identity/api/auth/v3/check-otp",
                    "POST /identity/api/auth/v4.0/user/login-with-token"):
        assert current in ids("OWASP/crAPI")
        assert current not in c, f"{current} wrongly flagged: {c.get(current)}"


def test_crapi_spec_only_endpoints_sit_in_their_own_services() -> None:
    """Django (workshop) and Go (community) routes are known only from the spec;
    they once formed a service named after the spec's folder."""
    graph = report("OWASP/crAPI")["graph"]
    drawn = {s["id"] for s in graph["services"]}
    assert "openapi-spec" not in drawn, drawn
    by_id = {e["id"]: e["service"] for e in graph["endpoints"]}
    assert by_id["GET /workshop/api/shop/products"] == "workshop"


def test_vampi_debug_endpoints_are_flagged_and_handlers_found() -> None:
    rep = report("erev0s/VAmPI")
    c = candidates("erev0s/VAmPI")
    assert "GET /users/v1/_debug" in c and "GET /createdb" in c, sorted(c)
    # Connexion: every documented operation has its handler found.
    assert all(e["file"] for e in rep["endpoints"]), \
        [e["id"] for e in rep["endpoints"] if not e["file"]]
    # Tags are not owners: VAmPI names no owner anywhere.
    assert all(e["owner"] is None for e in rep["endpoints"])


def test_petclinic_v1_owner_listing_is_superseded_by_v2() -> None:
    rep = report("spring-petclinic/spring-petclinic-rest")
    c = candidates("spring-petclinic/spring-petclinic-rest")
    assert "GET /petclinic/api/owners" in c, sorted(c)
    assert any(s["key"] == "superseded" for s in c["GET /petclinic/api/owners"]["signals"])
    assert "GET /petclinic/api/v2/owners" not in c
    found = sum(1 for e in rep["endpoints"] if e["file"])
    assert found >= 35, f"API-first handlers found: {found} of {len(rep['endpoints'])}"


def test_fastapi_template_endpoints_its_frontend_never_calls() -> None:
    rep = report("fastapi/full-stack-fastapi-template")
    c = candidates("fastapi/full-stack-fastapi-template")
    # The variable prefix is resolved: full paths.
    assert "GET /api/v1/items" in ids("fastapi/full-stack-fastapi-template")
    for unused in ("GET /api/v1/items/{id}", "POST /api/v1/utils/test-email/",
                   "POST /api/v1/private/users/"):
        hit = next((k for k in c if k.rstrip("/") == unused.rstrip("/")), None)
        assert hit, f"{unused} not flagged; candidates: {sorted(c)}"
    for used in ("GET /api/v1/items", "POST /api/v1/login/access-token"):
        assert not any(k.rstrip("/") == used for k in c), f"{used} wrongly flagged"
    assert not any("health-check" in k for k in c), "a health probe is not a zombie"
    assert rep["graph"]["stats"]["calls"] >= 10, rep["graph"]["stats"]


def test_no_report_lists_positive_evidence_as_a_finding() -> None:
    for slug in ("erev0s/VAmPI", "OWASP/crAPI"):
        for e in report(slug)["endpoints"]:
            assert "an owning team is recorded" not in e["findings"], (slug, e["id"])


def test_crapi_flags_few_and_never_what_the_web_app_calls() -> None:
    """Precision guard: an early version flagged 13 crAPI endpoints, including
    video and vehicle endpoints its web app does call (as <videoId>, and under a
    parameter the spec names differently)."""
    c = candidates("OWASP/crAPI")
    assert len(c) <= 8, sorted(c)
    for used in ("GET /identity/api/v2/vehicle/{carId}/location",
                 "GET /identity/api/v2/user/videos/{video_id}",
                 "GET /identity/api/auth/jwks.json"):
        assert used not in c, f"{used} wrongly flagged: {c.get(used)}"


def test_idurar_express_routes_are_all_found_under_their_mounts() -> None:
    """idurar declares every route as router.route(...).get(...), builds its CRUD
    routes from a template literal in a loop, and mounts routers from app.js.
    A scan of it once found no API at all. Its 33 routes, counted by hand in
    backend/src/routes, sit under /api, /download and /public.
    """
    found = ids("idurar/idurar-erp-crm")
    for expected in ("POST /api/login",
                     "PATCH /api/admin/password-update/{id}",
                     "PATCH /api/{entity}/update/{id}",
                     "POST /api/{entity}/mail",
                     "PATCH /api/setting/upload/{settingKey}",
                     "GET /download/{directory}/{file}",
                     "GET /public/{subPath}/{directory}/{file}"):
        assert expected in found, (expected, sorted(found))
    assert len(found) == 33, sorted(found)
    # Commented out in coreApi.js: present in the text, absent from the AST.
    assert "DELETE /api/setting/delete/{id}" not in found


def test_express_reference_app_routes_carry_their_mount_prefix() -> None:
    """Accusing nothing must not be the result of seeing nothing, or of
    seeing the wrong paths.

    The reference app mounts every router under /api through a router built
    in routes.ts, and a validation against its route files found every path
    reported without /api, plus `GET /` taken from an end-to-end test. Its 20
    routes, read by hand: 19 under /api and the status route `GET /` in
    main.ts.
    """
    found = ids("gothinkster/node-express-realworld-example-app")
    assert len(found) == 20, sorted(found)
    for expected in ("GET /api/articles", "POST /api/users/login", "GET /api/tags",
                     "DELETE /api/articles/{slug}/comments/{id}", "GET /"):
        assert expected in found, (expected, sorted(found))
    assert not any(e.startswith(("GET /articles", "POST /users")) for e in found)


def test_repositories_without_distinguishing_evidence_accuse_nothing() -> None:
    """No spec, no client, no versions: the honest answer is no candidates."""
    for slug in ("gothinkster/node-express-realworld-example-app",
                 "Mehandihasan2023/digital-banking-platform"):
        assert candidates(slug) == {}, (slug, sorted(candidates(slug)))
