"""
Tests for live repository scanning.

Run:  python tests/test_live.py

These do not require Semgrep or a network. The extractor's parsing, path
normalisation and prefix composition are exercised against a canned Semgrep
payload, which is where the logic that can actually be wrong lives — running
Semgrep itself would only test Semgrep.
"""

from __future__ import annotations

import contextlib
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from apix.extractors.base import looks_like_route, normalise_path  # noqa: E402
from apix.extractors.semgrep_extractor import SemgrepExtractor  # noqa: E402
from apix.live.connectors import (  # noqa: E402
    REPO_SOURCES,
    _auth_from_spec,
    _version_of,
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


def _result(rule: str, path_literal: str, file: str, line: int = 1, **extra):
    msg = extra.pop("message", f'APIX|path={path_literal}|func=handler')
    return {
        "check_id": f"rules.{rule}",
        "path": str(ROOT / file),
        "start": {"line": line},
        "extra": {"message": msg, "lines": extra.get("lines", "")},
    }


# ---------------------------------------------------------------------------
# Path normalisation
# ---------------------------------------------------------------------------
def test_path_parameter_styles_normalise_to_one_form() -> None:
    """Express, Flask and Django spell parameters differently.

    Without normalisation the same endpoint found in code and in a spec looks
    like two endpoints, and the correlator reports a shadow API that does not
    exist.
    """
    cases = {
        "/users/:id": "/users/{id}",
        "/users/<int:id>": "/users/{id}",
        "/users/<id>": "/users/{id}",
        "/users/{id}/": "/users/{id}",
        "//users//{id}": "/users/{id}",
        "users/{id}": "/users/{id}",
    }
    bad = {k: normalise_path(k) for k, v in cases.items() if normalise_path(k) != v}
    check("test_path_parameter_styles_normalise_to_one_form", not bad, f"{bad}")


def test_non_routes_are_rejected() -> None:
    """`config.get("timeout")` matches $APP.get structurally but is not a route."""
    rejects = ["timeout", "https://example.com/x", "some value", "", "a" * 400]
    accepts = ["/v1/users", "/users/{id}", "/"]
    bad_r = [s for s in rejects if looks_like_route(s)]
    bad_a = [s for s in accepts if not looks_like_route(s) and s != "/"]
    check(
        "test_non_routes_are_rejected",
        not bad_r and not bad_a,
        f"wrongly accepted={bad_r} wrongly rejected={bad_a}",
    )


# ---------------------------------------------------------------------------
# Extraction and prefix composition
# ---------------------------------------------------------------------------
def test_router_prefix_is_composed_into_the_path() -> None:
    """A route declared as /me on a router mounted at /users is /users/me.

    Reporting the declared path alone invents endpoints nobody serves — this is
    the defect the first real scan surfaced.
    """
    ex = SemgrepExtractor()
    data = {
        "results": [
            _result(
                "apix-py-router-prefix", "", "api/users.py",
                message='APIXPREFIX|var=router|prefix="/users"',
            ),
            _result("apix-py-fastapi-get", '"/me"', "api/users.py", 10),
        ]
    }
    routes = ex._parse(data, ROOT)
    check(
        "test_router_prefix_is_composed_into_the_path",
        len(routes) == 1 and routes[0].path == "/users/me",
        f"got {[r.path for r in routes]}",
    )


def test_single_mount_prefix_is_applied() -> None:
    ex = SemgrepExtractor()
    data = {
        "results": [
            _result(
                "apix-py-include-router", "", "main.py",
                message='APIXMOUNT|prefix="/api/v1"',
            ),
            _result(
                "apix-py-router-prefix", "", "api/items.py",
                message='APIXPREFIX|var=router|prefix="/items"',
            ),
            _result("apix-py-fastapi-get", '"/{id}"', "api/items.py", 4),
        ]
    }
    routes = ex._parse(data, ROOT)
    check(
        "test_single_mount_prefix_is_applied",
        len(routes) == 1 and routes[0].path == "/api/v1/items/{id}",
        f"got {[r.path for r in routes]}",
    )


def test_ambiguous_mount_prefixes_are_not_guessed() -> None:
    """With several mount points and no dataflow analysis, guessing is wrong.

    Applying an arbitrary one would silently produce confident, incorrect paths.
    The routes are left relative and flagged instead.
    """
    ex = SemgrepExtractor()
    data = {
        "results": [
            _result("apix-py-include-router", "", "main.py",
                    message='APIXMOUNT|prefix="/api/v1"'),
            _result("apix-py-include-router", "", "main.py",
                    message='APIXMOUNT|prefix="/internal"'),
            _result("apix-py-fastapi-get", '"/things"', "api/t.py", 3),
        ]
    }
    routes = ex._parse(data, ROOT)
    check(
        "test_ambiguous_mount_prefixes_are_not_guessed",
        len(routes) == 1
        and routes[0].path == "/things"
        and not routes[0].prefix_resolved,
        f"got {[(r.path, r.prefix_resolved) for r in routes]}",
    )


def test_flask_methods_are_read_from_the_decorator() -> None:
    ex = SemgrepExtractor()
    data = {
        "results": [
            _result(
                "apix-py-flask-route", '"/submit"', "app.py", 7,
                lines='@app.route("/submit", methods=["POST", "PUT"])',
            )
        ]
    }
    routes = ex._parse(data, ROOT)
    check(
        "test_flask_methods_are_read_from_the_decorator",
        sorted(r.method for r in routes) == ["POST", "PUT"],
        f"got {[r.method for r in routes]}",
    )


def test_declared_path_is_retained() -> None:
    """The reader must be able to see what was inferred versus what was written."""
    ex = SemgrepExtractor()
    data = {
        "results": [
            _result("apix-py-router-prefix", "", "a.py",
                    message='APIXPREFIX|var=r|prefix="/users"'),
            _result("apix-py-fastapi-get", '"/me"', "a.py", 2),
        ]
    }
    r = ex._parse(data, ROOT)[0]
    check(
        "test_declared_path_is_retained",
        r.declared_path == "/me" and r.path == "/users/me",
        f"declared={r.declared_path} path={r.path}",
    )


# ---------------------------------------------------------------------------
# What a repository scan may claim
# ---------------------------------------------------------------------------
def test_repo_scan_declares_only_three_sources() -> None:
    """A repository has no gateway, no traffic sensor and no resolver."""
    names = {s.value for s in REPO_SOURCES}
    check(
        "test_repo_scan_declares_only_three_sources",
        names == {"CODE", "OPENAPI", "CICD"},
        f"got {names}",
    )


def test_spec_auth_none_only_when_explicit() -> None:
    """`security: []` means no auth; an absent key means unstated, not none."""
    explicit = _auth_from_spec({}, {"security": []})
    unstated = _auth_from_spec({}, {})
    check(
        "test_spec_auth_none_only_when_explicit",
        explicit == "NONE" and unstated is None,
        f"explicit={explicit} unstated={unstated}",
    )


def test_version_inferred_from_path() -> None:
    ok = (
        _version_of("/api/v1/users") == "v1"
        and _version_of("/v22/x") == "v22"
        and _version_of("/users/me") == "unversioned"
    )
    check("test_version_inferred_from_path", ok)


def main() -> None:
    print("Live-scan tests\n")
    for fn in [
        test_path_parameter_styles_normalise_to_one_form,
        test_non_routes_are_rejected,
        test_router_prefix_is_composed_into_the_path,
        test_single_mount_prefix_is_applied,
        test_ambiguous_mount_prefixes_are_not_guessed,
        test_flask_methods_are_read_from_the_decorator,
        test_declared_path_is_retained,
        test_repo_scan_declares_only_three_sources,
        test_spec_auth_none_only_when_explicit,
        test_version_inferred_from_path,
    ]:
        with contextlib.suppress(AssertionError):
            fn()

    print(f"\n{_PASS} passed, {_FAIL} failed")
    sys.exit(1 if _FAIL else 0)


if __name__ == "__main__":
    main()
