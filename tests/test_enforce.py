"""
Tests for CI/CD enforcement (Phase 6).

Run:  python tests/test_enforce.py

Real git, real temporary repositories, real merge bases. Route extraction is
done by a small fake for most tests, because CI installs only `.[dev]` and has
no Semgrep: the logic under test is the comparison, not Semgrep. One test runs
the real extractor end to end and skips, saying so, where Semgrep is absent.
"""

from __future__ import annotations

import contextlib
import re
import shutil
import subprocess
import sys
import tempfile
from collections.abc import Iterator
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from apix.enforce import (  # noqa: E402
    EnforceConfig,
    EnforceConfigError,
    EnforceError,
    run_enforcement,
)
from apix.enforce.config import (  # noqa: E402
    HANDLER_KEPT,
    SPEC_WITHOUT_HANDLER,
    UNDOCUMENTED,
    UNOWNED,
)
from apix.enforce.report import as_github, as_json  # noqa: E402
from apix.extractors.base import ExtractedRoute, normalise_path  # noqa: E402

_PASS = 0
_FAIL = 0
_SKIP = 0


def check(name: str, condition: bool, detail: str = "") -> None:
    global _PASS, _FAIL
    if condition:
        _PASS += 1
        print(f"  PASS  {name}")
        return
    _FAIL += 1
    print(f"  FAIL  {name}" + (f"\n          {detail}" if detail else ""))
    raise AssertionError(f"{name}: {detail}" if detail else name)


def skip(name: str, why: str) -> None:
    global _SKIP
    _SKIP += 1
    print(f"  SKIP  {name}  ({why})")
    with contextlib.suppress(ImportError):
        import pytest

        pytest.skip(why)


# ---------------------------------------------------------------------------
# A fake extractor for Flask decorators: enough to test the comparison in CI.
# ---------------------------------------------------------------------------
_ROUTE = re.compile(
    r'@app\.route\("(?P<path>[^"]+)"(?:,\s*methods=\[(?P<methods>[^\]]*)\])?\)'
)


class FakeExtractor:
    name = "fake-flask"

    def available(self) -> bool:
        return True

    def extract(self, repo_root: Path) -> list[ExtractedRoute]:
        out: list[ExtractedRoute] = []
        for f in sorted(repo_root.rglob("*.py")):
            if ".git" in f.parts:
                continue
            rel = str(f.relative_to(repo_root)).replace("\\", "/")
            for i, line in enumerate(f.read_text(encoding="utf-8").splitlines(), 1):
                m = _ROUTE.search(line)
                if not m:
                    continue
                methods = [t.strip().strip("\"'").upper()
                           for t in (m.group("methods") or '"GET"').split(",") if t.strip()]
                for meth in methods:
                    out.append(ExtractedRoute(meth, normalise_path(m.group("path")),
                                              rel, i, framework="flask"))
        return out


# ---------------------------------------------------------------------------
# Repositories
# ---------------------------------------------------------------------------
def _git(root: Path, *args: str) -> str:
    return subprocess.run(["git", "-C", str(root), *args], check=True,
                          capture_output=True, text=True).stdout.strip()


def _route(path: str, method: str = "GET", fn: str = "h") -> str:
    return f'@app.route("{path}", methods=["{method}"])\ndef {fn}():\n    return ""\n\n'


def _spec(*entries: tuple[str, str], extra: str = "") -> str:
    lines = ['openapi: 3.0.0', 'info: {title: t, version: "1"}', "paths:"]
    by_path: dict[str, list[str]] = {}
    for method, path in entries:
        by_path.setdefault(path, []).append(method.lower())
    for path, methods in by_path.items():
        lines.append(f"  {path}:")
        for m in methods:
            lines.append(f"    {m}: {{summary: x{extra}}}")
    return "\n".join(lines) + "\n"


@contextlib.contextmanager
def repo(base: dict[str, str], head: dict[str, str | None]) -> Iterator[Path]:
    """A repository whose `main` holds `base` and whose `feature` applies `head`.

    `head` maps paths to new content, or to None to delete the file.
    """
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp) / "r"
        root.mkdir()
        _git(root, "init", "-q")
        _git(root, "checkout", "-q", "-b", "main")
        _git(root, "config", "user.email", "t@example.test")
        _git(root, "config", "user.name", "t")
        for rel, text in base.items():
            (root / rel).parent.mkdir(parents=True, exist_ok=True)
            (root / rel).write_text(text, encoding="utf-8")
        _git(root, "add", "-A")
        _git(root, "commit", "-q", "-m", "base", "--allow-empty")
        _git(root, "checkout", "-q", "-b", "feature")
        for rel, text in head.items():
            target = root / rel
            if text is None:
                target.unlink()
                continue
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text(text, encoding="utf-8")
        _git(root, "add", "-A")
        _git(root, "commit", "-q", "-m", "feature", "--allow-empty")
        yield root


def _findings(root: Path, config: EnforceConfig | None = None) -> set[tuple[str, str]]:
    r = run_enforcement(root, "main", FakeExtractor(), config)
    return {(f.rule, f.endpoint_id) for f in r.comparison.findings}


BASE = {
    "api/app.py": _route("/v1/users", fn="a") + _route("/v1/legacy/export", fn="b"),
    "docs/openapi.yaml": _spec(("GET", "/v1/users"), ("GET", "/v1/legacy/export")),
    "CODEOWNERS": "api/ @payments-team\n",
}


# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------
def test_every_exemption_needs_a_reason() -> None:
    bad = [
        {"enforce": {"allow": [{"endpoint": "GET /x"}]}},
        {"enforce": {"rules": {"made-up-rule": "error"}}},
        {"enforce": {"rules": {UNOWNED: "fatal"}}},
        {"enforce": {"surprise": True}},
    ]
    rejected = 0
    for doc in bad:
        try:
            EnforceConfig.from_dict(doc)
        except EnforceConfigError:
            rejected += 1
    check("test_every_exemption_needs_a_reason", rejected == len(bad),
          f"{rejected} of {len(bad)} malformed configurations rejected")


def test_no_configuration_means_defaults() -> None:
    with tempfile.TemporaryDirectory() as d:
        cfg = EnforceConfig.load(Path(d))
    check("test_no_configuration_means_defaults",
          cfg.source == "defaults" and cfg.severity[UNDOCUMENTED] == "error"
          and cfg.severity[SPEC_WITHOUT_HANDLER] == "warn")


# ---------------------------------------------------------------------------
# The four rules
# ---------------------------------------------------------------------------
def test_each_rule_fires_on_what_it_describes() -> None:
    head: dict[str, str | None] = {
        "api/app.py": BASE["api/app.py"] + _route("/v1/users/<int:i>", "DELETE", "c"),
        "internal/debug.py": _route("/v1/debug/replay", "POST", "d"),
        "docs/openapi.yaml": _spec(("GET", "/v1/users"), ("GET", "/v1/reports")),
    }
    with repo(BASE, head) as root:
        found = _findings(root)
    expected = {
        (UNDOCUMENTED, "DELETE /v1/users/{i}"),
        (UNDOCUMENTED, "POST /v1/debug/replay"),
        (UNOWNED, "POST /v1/debug/replay"),
        (HANDLER_KEPT, "GET /v1/legacy/export"),
        (SPEC_WITHOUT_HANDLER, "GET /v1/reports"),
    }
    check("test_each_rule_fires_on_what_it_describes", found == expected,
          f"missing {expected - found}, unexpected {found - expected}")


def test_a_documented_owned_endpoint_passes() -> None:
    head: dict[str, str | None] = {
        "api/app.py": BASE["api/app.py"] + _route("/v1/accounts", fn="c"),
        "docs/openapi.yaml": _spec(("GET", "/v1/users"), ("GET", "/v1/legacy/export"),
                                   ("GET", "/v1/accounts")),
    }
    with repo(BASE, head) as root:
        r = run_enforcement(root, "main", FakeExtractor())
    check("test_a_documented_owned_endpoint_passes",
          r.comparison.passed and not r.comparison.findings
          and r.comparison.added == ["GET /v1/accounts"],
          str([f.to_dict() for f in r.comparison.findings]))


def test_existing_debt_is_never_held_against_a_change() -> None:
    """An undocumented, unowned endpoint already on main must not fail the PR."""
    base = {"legacy/old.py": _route("/v0/forgotten", fn="z")}
    with repo(base, {"README.md": "docs only\n"}) as root:
        r = run_enforcement(root, "main", FakeExtractor())
    check("test_existing_debt_is_never_held_against_a_change",
          r.comparison.passed and not r.comparison.findings,
          str([f.to_dict() for f in r.comparison.findings]))


def test_openapi_tags_are_not_owners() -> None:
    head: dict[str, str | None] = {
        "svc/app.py": _route("/v1/items", fn="c"),
        "docs/openapi.yaml": BASE["docs/openapi.yaml"]
        + "  /v1/items:\n    get: {summary: items, tags: [items]}\n",
    }
    with repo(BASE, head) as root:
        found = _findings(root)
    check("test_openapi_tags_are_not_owners",
          (UNOWNED, "GET /v1/items") in found, str(found))


def test_spec_x_owner_counts_as_an_owner() -> None:
    head: dict[str, str | None] = {
        "svc/app.py": _route("/v1/items", fn="c"),
        "docs/openapi.yaml": BASE["docs/openapi.yaml"]
        + "  /v1/items:\n    get: {summary: items, x-owner: lending-team}\n",
    }
    with repo(BASE, head) as root:
        found = _findings(root)
    check("test_spec_x_owner_counts_as_an_owner", not found, str(found))


def test_severity_controls_whether_a_change_fails() -> None:
    head: dict[str, str | None] = {"api/app.py": BASE["api/app.py"] + _route("/v1/new", fn="c")}
    warn = EnforceConfig.from_dict({"enforce": {"rules": {UNDOCUMENTED: "warn"}}})
    off = EnforceConfig.from_dict({"enforce": {"rules": {UNDOCUMENTED: "off"}}})
    with repo(BASE, head) as root:
        as_warning = run_enforcement(root, "main", FakeExtractor(), warn).comparison
        switched_off = run_enforcement(root, "main", FakeExtractor(), off).comparison
    check("test_severity_controls_whether_a_change_fails",
          as_warning.passed and len(as_warning.warnings) == 1
          and switched_off.passed and not switched_off.findings,
          f"warn: {as_warning.findings}; off: {switched_off.findings}")


def test_exemptions_are_reported_with_their_reason() -> None:
    cfg = EnforceConfig.from_dict({"enforce": {"allow": [
        {"endpoint": "GET /healthz", "reason": "load balancer probe"}]}})
    head: dict[str, str | None] = {"internal/h.py": _route("/healthz", fn="c")}
    with repo(BASE, head) as root:
        c = run_enforcement(root, "main", FakeExtractor(), cfg).comparison
    check("test_exemptions_are_reported_with_their_reason",
          c.passed and not c.findings
          and [(e, a.reason) for e, a in c.exempted] == [("GET /healthz", "load balancer probe")],
          str(c.exempted))


_SELF_EXEMPT = (
    'enforce:\n  allow:\n    - endpoint: "POST /v1/backdoor"\n'
    '      reason: "trust me"\n'
)


def test_a_change_cannot_exempt_itself() -> None:
    """The policy is read from the merge base, never from the change.

    Read from the head, a pull request could add an exemption for the very
    endpoint it introduces and pass its own check with one innocuous line.
    """
    head: dict[str, str | None] = {
        "internal/b.py": _route("/v1/backdoor", "POST", "b"),
        ".apix.yml": _SELF_EXEMPT,
    }
    with repo(BASE, head) as root:
        r = run_enforcement(root, "main", FakeExtractor())
    found = {(f.rule, f.endpoint_id) for f in r.comparison.findings}
    check("test_a_change_cannot_exempt_itself",
          not r.comparison.passed and (UNDOCUMENTED, "POST /v1/backdoor") in found
          and not r.comparison.exempted and r.policy_changed
          and "policy_changed" in as_json(r),
          f"passed={r.comparison.passed} policy_changed={r.policy_changed} {found}")


def test_policy_already_on_main_applies() -> None:
    base = {**BASE, ".apix.yml": _SELF_EXEMPT}
    with repo(base, {"internal/b.py": _route("/v1/backdoor", "POST", "b")}) as root:
        r = run_enforcement(root, "main", FakeExtractor())
    check("test_policy_already_on_main_applies",
          r.comparison.passed and not r.policy_changed
          and r.config.source == ".apix.yml at the merge base",
          f"{r.comparison.findings} source={r.config.source!r}")


# ---------------------------------------------------------------------------
# Git behaviour
# ---------------------------------------------------------------------------
def test_compares_with_the_merge_base_not_the_branch_tip() -> None:
    """Work merged to main after the branch was cut is not this change's."""
    with repo(BASE, {"README.md": "x\n"}) as root:
        _git(root, "checkout", "-q", "main")
        (root / "late").mkdir()
        (root / "late" / "x.py").write_text(_route("/v1/late", fn="l"), encoding="utf-8")
        _git(root, "add", "-A")
        _git(root, "commit", "-q", "-m", "landed on main later")
        _git(root, "checkout", "-q", "feature")
        r = run_enforcement(root, "main", FakeExtractor())
    check("test_compares_with_the_merge_base_not_the_branch_tip",
          r.comparison.passed and not r.comparison.added and not r.comparison.removed,
          f"added {r.comparison.added}, removed {r.comparison.removed}")


def test_temporary_worktree_is_removed() -> None:
    with repo(BASE, {"README.md": "x\n"}) as root:
        run_enforcement(root, "main", FakeExtractor())
        listing = _git(root, "worktree", "list")
    check("test_temporary_worktree_is_removed", len(listing.splitlines()) == 1, listing)


def test_unknown_base_says_how_to_fix_it() -> None:
    with repo(BASE, {"README.md": "x\n"}) as root:
        try:
            run_enforcement(root, "origin/does-not-exist", FakeExtractor())
            ok, detail = False, "ran against a ref that does not exist"
        except EnforceError as exc:
            ok, detail = "fetch-depth" in str(exc), str(exc)
    check("test_unknown_base_says_how_to_fix_it", ok, detail)


# ---------------------------------------------------------------------------
# Output
# ---------------------------------------------------------------------------
def test_github_annotations_cannot_be_injected() -> None:
    """A newline in a message must not end the annotation and start a new command.

    Workflow commands are line-oriented: an unescaped newline followed by
    `::error::...` would be read by GitHub as a second, forged annotation, and
    a `,` or `:` in a file name would corrupt the properties. The finding below
    carries all three; the output must contain exactly one command.
    """
    from apix.enforce.check import Comparison, Finding
    from apix.enforce.runner import EnforceResult
    from apix.enforce.snapshot import Snapshot

    hostile = Finding(
        UNDOCUMENTED, "error", "GET /x",
        "first line\n::error::forged annotation\r\n100% sure",
        file="weird,name:v1.py", line=3,
    )
    snap = Snapshot(root=Path("."))
    result = EnforceResult("main", "0" * 40, EnforceConfig(), snap, snap,
                           Comparison(findings=[hostile]))
    commands = _commands_github_would_run(as_github(result))
    annotations = [c for c in commands if c.startswith(("::error", "::warning"))]
    check("test_github_annotations_cannot_be_injected",
          len(annotations) == 1
          and "%0A::error::forged" in annotations[0]
          and "100%25 sure" in annotations[0]
          and "file=weird%2Cname%3Av1.py" in annotations[0],
          "\n".join(commands))


def _commands_github_would_run(log: str) -> list[str]:
    """Model GitHub's log parsing: `::` lines are commands, except inside a
    `::stop-commands::TOKEN` ... `::TOKEN::` block."""
    out: list[str] = []
    paused_until: str | None = None
    for line in log.splitlines():
        if paused_until is not None:
            if line == paused_until:
                paused_until = None
            continue
        if line.startswith("::stop-commands::"):
            paused_until = f"::{line.split('::', 2)[2]}::"
            continue
        if line.startswith("::"):
            out.append(line)
    return out


def test_cli_exit_codes_follow_ci_convention() -> None:
    from apix.cli import main

    def run(root: Path, base: str) -> int:
        with contextlib.redirect_stdout(None), contextlib.redirect_stderr(None):
            return main(["enforce", "--repo", str(root), "--base", base])

    if shutil.which("semgrep") is None:
        skip("test_cli_exit_codes_follow_ci_convention", "Semgrep not installed")
        return
    with repo(BASE, {"README.md": "x\n"}) as clean:
        ok = run(clean, "main")
        bad_ref = run(clean, "nope")
    with repo(BASE, {"internal/d.py": _route("/v1/d", "POST", "c")}) as dirty:
        failing = run(dirty, "main")
    check("test_cli_exit_codes_follow_ci_convention",
          (ok, failing, bad_ref) == (0, 1, 2), f"got {(ok, failing, bad_ref)}")


def test_real_semgrep_end_to_end() -> None:
    from apix.extractors.semgrep_extractor import SemgrepExtractor

    ex = SemgrepExtractor()
    if not ex.available():
        skip("test_real_semgrep_end_to_end", "Semgrep not installed")
        return
    head: dict[str, str | None] = {
        "api/app.py": "from flask import Flask\napp = Flask(__name__)\n\n"
        + BASE["api/app.py"] + _route("/v1/users/<int:i>", "DELETE", "c"),
    }
    base = {**BASE, "api/app.py": "from flask import Flask\napp = Flask(__name__)\n\n"
            + BASE["api/app.py"]}
    with repo(base, head) as root:
        r = run_enforcement(root, "main", ex)
    found = {(f.rule, f.endpoint_id) for f in r.comparison.findings}
    check("test_real_semgrep_end_to_end",
          found == {(UNDOCUMENTED, "DELETE /v1/users/{i}")}, str(found))


if __name__ == "__main__":
    tests = [v for k, v in sorted(globals().items()) if k.startswith("test_")]
    for t in tests:
        with contextlib.suppress(AssertionError):
            t()
    print(f"\n{_PASS} passed, {_FAIL} failed, {_SKIP} skipped")
    sys.exit(1 if _FAIL else 0)
