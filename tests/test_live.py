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


def _variable_mount(project: dict[str, str]) -> tuple[list, SemgrepExtractor]:
    """Parse a mount by settings.API_V1_STR inside a throwaway project.

    The project is a temporary directory on purpose: run against this
    repository, the resolver found the API_V1_STR assignment in a demo clone
    that exists only on one laptop, so the test passed or failed by machine.
    """
    import tempfile

    with tempfile.TemporaryDirectory() as d:
        root = Path(d)
        for rel, text in project.items():
            (root / rel).parent.mkdir(parents=True, exist_ok=True)
            (root / rel).write_text(text, encoding="utf-8")
        ex = SemgrepExtractor()
        data = {"results": [
            _result("apix-py-include-router", "", "main.py",
                    message="APIXMOUNT|prefix=settings.API_V1_STR"),
            _result("apix-py-fastapi-get", '"/users"', "api/u.py", 5),
        ]}
        return ex._parse(data, root), ex


def test_a_prefix_set_by_a_variable_marks_routes_unresolved() -> None:
    """`prefix=settings.API_V1_STR` whose value the project never spells out.

    It used to be dropped silently, which left every route looking resolved:
    the web report showed /users where the deployed path is /api/v1/users.
    """
    routes, ex = _variable_mount({"app/main.py": "API_V1_STR = os.environ['X']\n"})
    check(
        "test_a_prefix_set_by_a_variable_marks_routes_unresolved",
        len(routes) == 1
        and routes[0].path == "/users"
        and not routes[0].prefix_resolved
        and ex.variable_mounts == ["settings.API_V1_STR"],
        f"got {[(r.path, r.prefix_resolved) for r in routes]}, {ex.variable_mounts}",
    )


def test_a_variable_prefix_the_project_spells_out_is_applied() -> None:
    """FastAPI's template: API_V1_STR: str = "/api/v1" in its settings class."""
    routes, ex = _variable_mount({
        "app/core/config.py": 'class Settings:\n    API_V1_STR: str = "/api/v1"\n'})
    check(
        "test_a_variable_prefix_the_project_spells_out_is_applied",
        [(r.path, r.prefix_resolved) for r in routes] == [("/api/v1/users", True)]
        and ex.resolved_mounts == {"settings.API_V1_STR": "/api/v1"},
        f"got {[(r.path, r.prefix_resolved) for r in routes]}, {ex.resolved_mounts}",
    )


def test_flask_methods_are_read_from_the_decorator() -> None:
    """Methods come from the source file, because Semgrep now redacts it.

    This test used to hand the parser a payload whose `extra.lines` held the
    decorator. Real Semgrep returns "requires login" there unless signed in to
    its cloud platform, so the test passed while every real Flask route was
    extracted as GET. The payload below is shaped like real output: redacted
    lines, and a line span pointing at an actual file.
    """
    import tempfile

    ex = SemgrepExtractor()
    with tempfile.TemporaryDirectory() as d:
        root = Path(d)
        (root / "app.py").write_text(
            "from flask import Flask\napp = Flask(__name__)\n\n"
            '@app.route("/submit", methods=["POST", "PUT"])\n'
            "def submit():\n    return ''\n",
            encoding="utf-8",
        )
        data = {
            "results": [{
                "check_id": "rules.apix-py-flask-route",
                "path": str(root / "app.py"),
                "start": {"line": 4},
                "end": {"line": 6},
                "extra": {
                    "message": 'APIX|path="/submit"|func=submit',
                    "lines": "requires login",
                },
            }]
        }
        routes = ex._parse(data, root)
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


def test_specs_under_docs_are_found() -> None:
    """`docs/openapi.yaml` is a common home for a spec; it used to be skipped."""
    import tempfile

    from apix.live.repo import RepoScan

    with tempfile.TemporaryDirectory() as d:
        root = Path(d)
        for folder in ("docs", "api"):
            (root / folder).mkdir()
            (root / folder / "openapi.yaml").write_text("openapi: 3.0.0\npaths: {}\n")
        (root / "node_modules").mkdir()
        (root / "node_modules" / "openapi.yaml").write_text("openapi: 3.0.0\n")
        found = sorted(RepoScan.from_path(root).rel(p) for p in RepoScan.from_path(root).spec_files)
    check("test_specs_under_docs_are_found",
          found == ["api/openapi.yaml", "docs/openapi.yaml"],
          f"found {found}; docs/ must be searched, node_modules/ must not")


def test_spec_only_endpoints_belong_to_the_service_their_path_names() -> None:
    """crAPI documents its Django and Go services in one spec under openapi-spec/,
    and every one of their endpoints was drawn as a service of that name."""
    import json
    import tempfile

    from apix.live.connectors import RepoOpenAPIConnector
    from apix.live.repo import RepoScan

    with tempfile.TemporaryDirectory() as d:
        root = Path(d)
        (root / "services" / "workshop").mkdir(parents=True)
        (root / "openapi-spec").mkdir()
        spec = {"openapi": "3.0.0", "paths": {
            "/workshop/api/shop/products": {"get": {}},
            "/elsewhere/api/x": {"get": {}},
        }}
        (root / "openapi-spec" / "openapi.json").write_text(json.dumps(spec))
        services = {s.endpoint_id: s.service
                    for s in RepoOpenAPIConnector(RepoScan.from_path(root)).collect()}
    check("test_spec_only_endpoints_belong_to_the_service_their_path_names",
          services == {"GET /workshop/api/shop/products": "workshop",
                       "GET /elsewhere/api/x": "openapi-spec"},
          str(services))


# ---------------------------------------------------------------------------
# Express: template literals, optional parameters, mounts through require()
# ---------------------------------------------------------------------------
#: A small Express project in the shapes idurar/idurar-erp-crm uses, which an
#: October 2026 scan of it reported as having no API at all: chained
#: router.route(...).get(...), PATCH, CRUD routes built from a template literal
#: in a loop, routers mounted from app.js through require() with middleware in
#: between, and one level of nesting.
_EXPRESS_PROJECT = {
    "src/app.js": (
        "const express = require('express');\n"
        "const api = require('./routes');\n"
        "const files = require('./routes/files.js');\n"
        "const app = express();\n"
        "app.use('/api', auth, api);\n"
        "app.use('/download', files);\n"
        "app.use(config.prefix, require('./routes/legacy'));\n"
        "app.get('/health', (req, res) => res.send('ok'));\n"
    ),
    "src/routes/index.js": (
        "const router = require('express').Router();\n"
        "const crud = require('./crud');\n"
        "router.use('/v1', crud);\n"
        "router.route('/login').post(login);\n"
        "module.exports = router;\n"
    ),
    "src/routes/crud.js": (
        "const router = require('express').Router();\n"
        "['invoice', 'quote'].forEach((entity) => {\n"
        "  router.route(`/${entity}/read/:id`).get(catchErrors(read));\n"
        "  router.route(`/${entity}/update/:id`).patch(catchErrors(update));\n"
        "});\n"
        "router\n  .route('/setting/:key?')\n  .get(h)\n  .delete(h2);\n"
        "module.exports = router;\n"
    ),
    "src/routes/files.js": (
        "const router = require('express').Router();\n"
        "router.route('/:directory/:file').get(download);\n"
        "module.exports = router;\n"
    ),
    "src/routes/orphan.js": (
        "const router = require('express').Router();\n"
        "router.get('/stray', h);\n"
        "module.exports = router;\n"
    ),
}

#: What a person reading _EXPRESS_PROJECT would say it serves.
_EXPRESS_EXPECTED = {
    ("GET", "/health", True),
    ("POST", "/api/login", True),
    ("GET", "/api/v1/{entity}/read/{id}", True),
    ("PATCH", "/api/v1/{entity}/update/{id}", True),
    ("GET", "/api/v1/setting/{key}", True),
    ("DELETE", "/api/v1/setting/{key}", True),
    ("GET", "/download/{directory}/{file}", True),
    # Mounted nowhere the scan can follow: the path is relative, and says so.
    ("GET", "/stray", False),
}


def _express_project(root: Path) -> None:
    for rel, text in _EXPRESS_PROJECT.items():
        (root / rel).parent.mkdir(parents=True, exist_ok=True)
        (root / rel).write_text(text, encoding="utf-8")


def test_express_template_literal_paths_become_parameters() -> None:
    """Semgrep hands back `/${entity}/create with no closing backtick."""
    ex = SemgrepExtractor()
    data = {"results": [
        _result("apix-js-express-post", "`/${entity}/create", "r.js", 1),
        _result("apix-js-express-get", "`/${cfg.kind}/list`", "r.js", 2),
        # The slot is a prefix here, not a segment: reporting /{base}/x would
        # invent a path. It is rejected instead.
        _result("apix-js-express-get", "`${base}/x", "r.js", 3),
    ]}
    routes = ex._parse(data, ROOT)
    check("test_express_template_literal_paths_become_parameters",
          [(r.method, r.path) for r in routes]
          == [("POST", "/{entity}/create"), ("GET", "/{kind}/list")]
          and ex.rejected == ["`${base}/x"],
          f"got {[(r.method, r.path) for r in routes]}, rejected {ex.rejected}")


def test_express_optional_parameter_normalises() -> None:
    check("test_express_optional_parameter_normalises",
          normalise_path("/setting/upload/:settingKey?") == "/setting/upload/{settingKey}",
          normalise_path("/setting/upload/:settingKey?"))


def test_express_mounts_are_followed_through_require() -> None:
    """Mounts compose across files; an unfollowable one is marked, not guessed."""
    import tempfile

    with tempfile.TemporaryDirectory() as d:
        root = Path(d)
        _express_project(root)

        def r(rule: str, path: str, file: str) -> dict:
            return {"check_id": f"rules.{rule}", "path": str(root / file),
                    "start": {"line": 1},
                    "extra": {"message": f"APIX|path={path}|func=anonymous"}}

        def mount(prefix: str, router: str, file: str) -> dict:
            return {"check_id": "rules.apix-js-express-mount", "path": str(root / file),
                    "start": {"line": 1},
                    "extra": {"message": f"APIXJSMOUNT|prefix={prefix}|router={router}"}}

        data = {"results": [
            mount("'/api'", "api", "src/app.js"),
            mount("'/download'", "files", "src/app.js"),
            mount("config.prefix", "require('./routes/legacy')", "src/app.js"),
            mount("'/v1'", "crud", "src/routes/index.js"),
            r("apix-js-express-get", "'/health'", "src/app.js"),
            r("apix-js-express-post", "'/login'", "src/routes/index.js"),
            r("apix-js-express-get", "`/${entity}/read/:id", "src/routes/crud.js"),
            r("apix-js-express-patch", "`/${entity}/update/:id", "src/routes/crud.js"),
            r("apix-js-express-get", "'/setting/:key?'", "src/routes/crud.js"),
            r("apix-js-express-delete", "'/setting/:key?'", "src/routes/crud.js"),
            r("apix-js-express-get", "'/:directory/:file'", "src/routes/files.js"),
            r("apix-js-express-get", "'/stray'", "src/routes/orphan.js"),
        ]}
        ex = SemgrepExtractor()
        got = {(x.method, x.path, x.prefix_resolved) for x in ex._parse(data, root)}
    check("test_express_mounts_are_followed_through_require",
          got == _EXPRESS_EXPECTED
          and ex.mount_prefixes == ["/api", "/api/v1", "/download"],
          f"missing {_EXPRESS_EXPECTED - got}, extra {got - _EXPRESS_EXPECTED}, "
          f"mounts {ex.mount_prefixes}")


def test_real_semgrep_finds_every_express_form() -> None:
    """The rule file itself, run by real Semgrep on the same project.

    The tests above hand the parser canned output, so they cannot notice a rule
    that stopped matching. This one can, and is skipped only where Semgrep is
    not installed.
    """
    import tempfile

    ex = SemgrepExtractor()
    if not ex.available():
        print("  SKIP  test_real_semgrep_finds_every_express_form (Semgrep not installed)")
        return
    with tempfile.TemporaryDirectory() as d:
        root = Path(d)
        _express_project(root)
        got = {(x.method, x.path, x.prefix_resolved) for x in ex.extract(root)}
    check("test_real_semgrep_finds_every_express_form",
          got == _EXPRESS_EXPECTED,
          f"missing {_EXPRESS_EXPECTED - got}, extra {got - _EXPRESS_EXPECTED}; "
          f"error {ex.last_error}")


#: The wiring of Express's reference application (gothinkster's realworld app),
#: which a validation against its route files found reported without /api:
#: the routers are mounted into a router built in the same file, not imported.
_EXPRESS_LOCAL_ROUTER_PROJECT = {
    "src/main.ts": (
        "import express from 'express';\n"
        "import routes from './app/routes/routes';\n"
        "const app = express();\n"
        "app.use(cors());\n"
        "app.use(routes);\n"
        "app.get('/', (req, res) => res.json({ status: 'ok' }));\n"
    ),
    "src/app/routes/routes.ts": (
        "import { Router } from 'express';\n"
        "import tagsController from './tag/tag.controller';\n"
        "import authController from './auth/auth.controller';\n"
        "\n"
        "const api = Router()\n"
        "  .use(tagsController)\n"
        "  .use(authController);\n"
        "\n"
        "export default Router().use('/api', api);\n"
    ),
    "src/app/routes/tag/tag.controller.ts": (
        "import { Router } from 'express';\n"
        "const router = Router();\n"
        "router.get('/tags', async (req, res) => res.json([]));\n"
        "export default router;\n"
    ),
    "src/app/routes/auth/auth.controller.ts": (
        "import { Router } from 'express';\n"
        "const router = Router();\n"
        "router.post('/users/login', async (req, res) => res.json({}));\n"
        "export default router;\n"
    ),
    # A request the end-to-end tests make. Not a route the application serves.
    "e2e/src/server/server.spec.ts": (
        "import axios from 'axios';\n"
        "const app = axios.create();\n"
        "describe('GET /', () => { it('works', async () => { await app.get('/'); }); });\n"
    ),
    "src/app/routes/tag/tag.controller.spec.ts": (
        "router.get('/only-in-a-test', h);\n"
    ),
}


def test_real_semgrep_follows_routers_built_in_the_same_file() -> None:
    import tempfile

    ex = SemgrepExtractor()
    if not ex.available():
        print("  SKIP  test_real_semgrep_follows_routers_built_in_the_same_file "
              "(Semgrep not installed)")
        return
    with tempfile.TemporaryDirectory() as d:
        root = Path(d)
        for rel, text in _EXPRESS_LOCAL_ROUTER_PROJECT.items():
            (root / rel).parent.mkdir(parents=True, exist_ok=True)
            (root / rel).write_text(text, encoding="utf-8")
        got = {(x.method, x.path, x.prefix_resolved, x.file) for x in ex.extract(root)}
    expected = {
        ("GET", "/api/tags", True, "src/app/routes/tag/tag.controller.ts"),
        ("POST", "/api/users/login", True, "src/app/routes/auth/auth.controller.ts"),
        ("GET", "/", True, "src/main.ts"),
    }
    check("test_real_semgrep_follows_routers_built_in_the_same_file",
          got == expected,
          f"missing {expected - got}, extra {got - expected}; error {ex.last_error}")


def main() -> None:
    print("Live-scan tests\n")
    for fn in [
        test_path_parameter_styles_normalise_to_one_form,
        test_non_routes_are_rejected,
        test_router_prefix_is_composed_into_the_path,
        test_single_mount_prefix_is_applied,
        test_ambiguous_mount_prefixes_are_not_guessed,
        test_a_prefix_set_by_a_variable_marks_routes_unresolved,
        test_a_variable_prefix_the_project_spells_out_is_applied,
        test_flask_methods_are_read_from_the_decorator,
        test_declared_path_is_retained,
        test_repo_scan_declares_only_three_sources,
        test_spec_auth_none_only_when_explicit,
        test_version_inferred_from_path,
        test_specs_under_docs_are_found,
        test_express_template_literal_paths_become_parameters,
        test_express_optional_parameter_normalises,
        test_express_mounts_are_followed_through_require,
        test_real_semgrep_finds_every_express_form,
        test_real_semgrep_follows_routers_built_in_the_same_file,
    ]:
        with contextlib.suppress(AssertionError):
            fn()

    print(f"\n{_PASS} passed, {_FAIL} failed")
    sys.exit(1 if _FAIL else 0)


if __name__ == "__main__":
    main()
