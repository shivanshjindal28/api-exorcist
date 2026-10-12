"""
Tests for scans started from the browser: an uploaded folder or a GitHub link.

Run:  python -m pytest tests/test_scans.py

No test here touches the network. The GitHub path is exercised up to the
download, which is replaced, so CI checks the parsing, the job lifecycle and
the failure reporting without depending on github.com. Semgrep is absent in CI;
the upload test accepts either outcome for route extraction, but if it could
not run, the report must say so and say why.
"""

from __future__ import annotations

import contextlib
import tempfile
import time
from collections.abc import Iterator
from pathlib import Path
from typing import Any

import pytest

from apix.scanning import (
    JobManager,
    ScanRefused,
    UploadRejected,
    parse_github,
    save_files,
)
from apix.scanning import upload as upload_mod
from apix.scanning.upload import safe_relative

fastapi = pytest.importorskip("fastapi")
from fastapi.testclient import TestClient  # noqa: E402

from apix.api.app import create_app  # noqa: E402
from apix.api.auth import TokenStore, hash_token, new_token  # noqa: E402
from apix.api.workspace import Workspace  # noqa: E402

SPEC = b"""openapi: 3.0.0
info: {title: shop, version: "1"}
paths:
  /v1/orders:
    get: {summary: list orders}
  /v1/orders/{id}:
    delete: {summary: cancel, deprecated: true}
"""


# ---------------------------------------------------------------------------
# GitHub links
# ---------------------------------------------------------------------------
@pytest.mark.parametrize("raw", [
    "https://github.com/fastapi/fastapi",
    "https://github.com/fastapi/fastapi.git",
    "https://github.com/fastapi/fastapi/tree/master/docs",
    "http://www.github.com/fastapi/fastapi/",
    "github.com/fastapi/fastapi",
    "fastapi/fastapi",
    "  https://github.com/fastapi/fastapi  ",
])
def test_github_links_in_every_common_form(raw: str) -> None:
    assert parse_github(raw) == "fastapi/fastapi"


@pytest.mark.parametrize("raw,why", [
    ("https://gitlab.com/a/b", "not GitHub"),
    ("https://github.com/onlyowner", "names no repository"),
    ("", "paste a GitHub"),
    ("https://github.com/a b/c", "not a GitHub repository"),
    ("file:///etc/passwd", "not GitHub"),
    ("https://github.com.evil.example/a/b", "not GitHub"),
])
def test_anything_else_is_refused_with_a_reason(raw: str, why: str) -> None:
    with pytest.raises(ScanRefused, match=why):
        parse_github(raw)


# ---------------------------------------------------------------------------
# Upload safety
# ---------------------------------------------------------------------------
@pytest.mark.parametrize("name", [
    "../evil.py", "proj/../../evil.py", "/etc/passwd", "C:/Windows/x.dll",
    "C:\\Windows\\x.dll", "proj/\x00.py", "proj/~/x", "proj/a:b.py", "", ".",
])
def test_names_that_could_escape_are_refused(name: str) -> None:
    assert safe_relative(name) is None


def test_saving_never_writes_outside_the_destination() -> None:
    with tempfile.TemporaryDirectory() as outer:
        dest = Path(outer) / "upload"
        dest.mkdir()
        saved = save_files(dest, [
            ("proj/app.py", b"x"),
            ("proj/../../escaped.py", b"bad"),
            ("proj\\..\\..\\escaped2.py", b"bad"),
            ("proj/docs/openapi.yaml", SPEC),
        ])
        outside = [p.name for p in Path(outer).iterdir() if p.name != "upload"]
        written = sorted(str(p.relative_to(dest)).replace("\\", "/")
                         for p in dest.rglob("*") if p.is_file())
    assert outside == []
    assert written == ["app.py", "docs/openapi.yaml"]     # the folder name is stripped
    assert saved.name == "proj" and saved.files == 2 and len(saved.skipped) == 2


def test_oversized_uploads_are_refused_before_anything_is_written(
        monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(upload_mod, "MAX_FILES", 3)
    with tempfile.TemporaryDirectory() as d:
        with pytest.raises(UploadRejected, match="node_modules"):
            save_files(Path(d), [(f"p/{i}.py", b"") for i in range(4)])
        assert not any(Path(d).iterdir())
        with pytest.raises(UploadRejected, match="no files"):
            save_files(Path(d), [])


# ---------------------------------------------------------------------------
# The API
# ---------------------------------------------------------------------------
@contextlib.contextmanager
def _client() -> Iterator[tuple[TestClient, dict[str, str], dict[str, str], Path]]:
    approver, viewer = new_token(), new_token()
    store = TokenStore.parse(f"ann:approver:{hash_token(approver)};"
                             f"vic:viewer:{hash_token(viewer)}")
    with tempfile.TemporaryDirectory() as tmp:
        jobs = JobManager(store=Path(tmp) / "scans")
        app = create_app(Workspace(Path(tmp) / "audit.jsonl"), store, jobs=jobs)
        yield (TestClient(app), {"Authorization": f"Bearer {approver}"},
               {"Authorization": f"Bearer {viewer}"}, Path(tmp))
        jobs.shutdown()


def _wait(client: TestClient, h: dict[str, str], job_id: str) -> dict[str, Any]:
    for _ in range(600):
        job: dict[str, Any] = client.get(f"/v1/scans/{job_id}", headers=h).json()
        if job["status"] in ("done", "failed"):
            return job
        time.sleep(0.1)
    raise AssertionError(f"scan {job_id} never finished")


def test_capabilities_say_what_works_and_why_not() -> None:
    with _client() as (client, approver, _, _):
        anonymous = client.get("/v1/capabilities")
        caps = client.get("/v1/capabilities", headers=approver).json()
    assert anonymous.status_code == 401
    assert caps["folder"]["available"] is True
    assert caps["website"]["available"] is False
    assert "not available" in caps["website"]["reason"]


def test_an_uploaded_folder_is_scanned_and_the_report_explains_itself() -> None:
    files = [
        ("files", ("shop/docs/openapi.yaml", SPEC, "text/yaml")),
        ("files", ("shop/README.md", b"# shop", "text/markdown")),
    ]
    with _client() as (client, approver, viewer, _):
        started = client.post("/v1/scans/upload", headers=approver, files=files)
        assert started.status_code == 202, started.text
        job = _wait(client, viewer, started.json()["id"])
    assert job["status"] == "done", job.get("error")
    report = job["report"]
    checks = {c["name"]: c for c in report["checks"]}

    assert checks["Project uploaded"]["status"] == "ok"
    assert checks["API specification"]["status"] == "ok"
    assert "docs/openapi.yaml" in checks["API specification"]["detail"]
    # An upload has no .git: staleness must be declared unknown, not zero.
    assert checks["Change history"]["status"] == "unavailable"
    assert "git history" in checks["Change history"]["detail"]
    assert checks["Traffic, gateway and DNS"]["status"] == "unavailable"
    routes = checks["API routes in the code"]
    if routes["status"] == "failed":                  # CI: no Semgrep
        assert "Semgrep" in routes["detail"]
    assert report["lifecycle"]["available"] is False

    ids = {e["id"] for e in report["endpoints"]}
    assert {"GET /v1/orders", "DELETE /v1/orders/{id}"} <= ids
    deleted = next(e for e in report["endpoints"] if e["id"] == "DELETE /v1/orders/{id}")
    assert deleted["documented"] and deleted["deprecated_in_spec"]
    summary = {s["label"]: s["value"] for s in report["summary"]}
    assert summary["Unchanged for over a year"] == "unknown"


def test_viewers_cannot_start_scans() -> None:
    with _client() as (client, _, viewer, _):
        upload = client.post("/v1/scans/upload", headers=viewer,
                             files=[("files", ("p/a.py", b"x", "text/plain"))])
        github = client.post("/v1/scans/github", headers=viewer,
                             json={"url": "fastapi/fastapi"})
    assert (upload.status_code, github.status_code) == (403, 403)


def test_bad_uploads_and_links_are_refused_with_reasons() -> None:
    with _client() as (client, approver, _, _):
        empty = client.post("/v1/scans/upload", headers=approver,
                            files=[("files", ("../../x.py", b"x", "text/plain"))])
        gitlab = client.post("/v1/scans/github", headers=approver,
                             json={"url": "https://gitlab.com/a/b"})
        extra = client.post("/v1/scans/github", headers=approver,
                            json={"url": "a/b", "approver": "someone else"})
        unknown = client.get("/v1/scans/0123456789ab", headers=approver)
        malformed = client.get("/v1/scans/../../etc", headers=approver)
    assert empty.status_code == 422 and "usable name" in empty.json()["detail"]
    assert gitlab.status_code == 422 and "not GitHub" in gitlab.json()["detail"]
    assert extra.status_code == 422                       # bodies reject unknown fields
    assert unknown.status_code == 404
    assert malformed.status_code in (404, 422)


def test_only_the_upload_route_takes_a_large_body() -> None:
    big = b"x" * (200 * 1024)
    with _client() as (client, approver, _, _):
        upload = client.post("/v1/scans/upload", headers=approver,
                             files=[("files", ("p/big.py", big, "text/plain"))])
        other = client.post("/v1/scans/github", headers={
            **approver, "Content-Type": "application/json"}, content=b'{"url":"' + big + b'"}')
    assert upload.status_code == 202
    assert other.status_code == 413


def test_a_failed_download_says_why(monkeypatch: pytest.MonkeyPatch) -> None:
    from apix.live import repo as repo_mod

    def refuse(cls: Any, slug: str, **_: Any) -> Any:
        raise repo_mod.RepoError(
            f"could not download {slug}: the repository does not exist, or it is private")

    monkeypatch.setattr(repo_mod.RepoScan, "clone", classmethod(refuse))
    with _client() as (client, approver, _, _):
        started = client.post("/v1/scans/github", headers=approver,
                              json={"url": "https://github.com/someone/private-thing"})
        job = _wait(client, approver, started.json()["id"])
    assert job["status"] == "failed"
    assert "private" in job["error"]
    assert job["progress"][-1]["message"].startswith("Stopped")


def test_finished_reports_survive_a_restart() -> None:
    with _client() as (client, approver, _, tmp):
        job_id = client.post("/v1/scans/upload", headers=approver, files=[
            ("files", ("p/docs/openapi.yaml", SPEC, "text/yaml"))]).json()["id"]
        _wait(client, approver, job_id)
        reloaded = JobManager(store=tmp / "scans")
        try:
            again = reloaded.get(job_id)
        finally:
            reloaded.shutdown()
    assert again is not None and again["status"] == "done" and again["report"]["endpoints"]
