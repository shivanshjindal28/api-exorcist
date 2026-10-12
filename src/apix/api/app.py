"""
The REST API: FastAPI over a Workspace.

    GET  /v1/health                        open; says nothing about the estate
    GET  /v1/whoami                        the principal behind the token
    GET  /v1/summary                       counts, scan time, simulated-mode notice
    GET  /v1/inventory                     correlated inventory, every source's view
    GET  /v1/verdicts[?label=ZOMBIE]       verdicts with signed reasons
    GET  /v1/verdicts/{endpoint}           one verdict and its explanation
    GET  /v1/impact                        the removal gate for every candidate
    GET  /v1/impact/{endpoint}             one blast radius
    GET  /v1/benchmark                     the comparative before/after study
    GET  /v1/safekill                      candidates, pending approvals, outcomes
    GET  /v1/audit[?endpoint=&limit=]      audit entries and the chain head
    GET  /v1/audit/verify                  recompute the whole chain
    GET  /metrics                          Prometheus text format (needs a token)

    POST /v1/demo/rescan                   approver: re-run discovery on the demo bank

    GET  /v1/capabilities                  which scan inputs work on this machine
    POST /v1/scans/github                  approver: scan a public GitHub repository
    POST /v1/scans/upload                  approver: scan an uploaded project folder
    GET  /v1/scans                         every scan, newest first
    GET  /v1/scans/{id}                    one scan: progress while running, then its report
    POST /v1/safekill/shadow               approver: gate + shadow window
    POST /v1/safekill/decision             approver: approve or decline

`{endpoint}` is an endpoint id such as `GET /v1/cards/{id}/pin`, percent-encoded
in the URL. Actions carry the endpoint in the JSON body instead, so nothing
destructive depends on how a client happens to encode a path.

Every response carries `Cache-Control: no-store`: what this API returns is a
map of an estate's weakest points, and no proxy or browser should keep a copy.

Every response also carries an `X-Request-ID`, echoed from the client when it
is well formed and generated otherwise, and the same id is in the access log
line, so one failed approval can be traced from the browser to the audit entry.
Request bodies are capped at 64 KiB: the largest legitimate one is a decision
with a 1000-character note.
"""

from __future__ import annotations

import re
import shutil
import tempfile
import time
import uuid
from collections.abc import Awaitable, Callable
from pathlib import Path
from typing import Annotated, Any

from fastapi import Depends, FastAPI, HTTPException, Query, Request, Response
from fastapi import Path as PathParam
from fastapi.concurrency import run_in_threadpool
from fastapi.responses import JSONResponse, PlainTextResponse
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, ConfigDict, Field

from apix import __version__
from apix.api.auth import Principal, Role, TokenStore
from apix.api.observe import Metrics, log
from apix.api.workspace import (
    NeedsAcknowledgement,
    NotACandidate,
    UnknownEndpoint,
    Workspace,
)
from apix.engine.explain import audit_entry
from apix.safekill.controller import NotAwaitingApproval
from apix.scanning import JobManager, ScanRefused, UploadRejected, save_files
from apix.scanning.upload import MAX_FILES, MAX_TOTAL_BYTES

_bearer = HTTPBearer(auto_error=False)
MAX_BODY_BYTES = 64 * 1024
#: The one route that takes a large body: a project folder. Its own cap, set by
#: the upload module, plus room for the multipart framing around the files.
UPLOAD_PATH = "/v1/scans/upload"
MAX_UPLOAD_BODY = MAX_TOTAL_BYTES + 16 * 1024 * 1024
_REQUEST_ID = re.compile(r"^[A-Za-z0-9._-]{1,64}$")


# ---------------------------------------------------------------------------
# Request bodies. extra="forbid": an unknown field is a 422, so there is no
# way to smuggle an "approver" name in alongside the real fields.
# ---------------------------------------------------------------------------
class ShadowRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    endpoint_id: str = Field(min_length=1, max_length=512)


class GithubScanRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    url: str = Field(min_length=1, max_length=500)


class DecisionRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    endpoint_id: str = Field(min_length=1, max_length=512)
    approve: bool
    accept_unidentified: bool = False
    note: str = Field(default="", max_length=1000)


# ---------------------------------------------------------------------------
# Authentication. These live at module level for a reason that cost a bug:
# with `from __future__ import annotations`, FastAPI resolves type hints against
# the module's globals. Aliases defined inside create_app() were invisible to
# it, so `who: Viewer` was silently treated as a required query parameter and
# a missing token returned 422 instead of 401.
# ---------------------------------------------------------------------------
def _principal(
    request: Request,
    creds: Annotated[HTTPAuthorizationCredentials | None, Depends(_bearer)],
) -> Principal:
    tokens: TokenStore = request.app.state.tokens
    metrics: Metrics = request.app.state.metrics
    if creds is None or creds.scheme.lower() != "bearer":
        metrics.auth_failure("missing")
        raise HTTPException(
            401, "a bearer token is required", headers={"WWW-Authenticate": "Bearer"}
        )
    who = tokens.authenticate(creds.credentials)
    if who is None:
        metrics.auth_failure("unrecognised")
        raise HTTPException(
            401, "token not recognised", headers={"WWW-Authenticate": "Bearer"}
        )
    request.state.principal = who.name
    return who


def _approver(
    request: Request, who: Annotated[Principal, Depends(_principal)]
) -> Principal:
    if not who.role.allows(Role.APPROVER):
        request.app.state.metrics.auth_failure("forbidden")
        raise HTTPException(403, f"{who.name} is a viewer; this needs an approver")
    return who


Viewer = Annotated[Principal, Depends(_principal)]
Approver = Annotated[Principal, Depends(_approver)]


# ---------------------------------------------------------------------------
# The dashboard and its Content-Security-Policy.
#
# The dashboard (dashboard/, built into this package) is served from the same
# origin as the API, so there is no CORS to configure and nothing to get wrong.
# Its HTML and JavaScript are public code; every byte of data still needs a
# token. The CSP allows scripts, styles and connections to this origin only,
# with no inline script anywhere: the build contains none, which is what makes
# this policy possible. A stored token is only as safe as the page holding it,
# and this is what keeps a script injected from elsewhere from running at all.
#
# FastAPI's /docs and /redoc pages load Swagger UI from a CDN with an inline
# script, so they are exempt rather than broken. A deployment with no internet
# access should serve those assets locally or disable the pages.
# ---------------------------------------------------------------------------
DASHBOARD_DIR = Path(__file__).resolve().parent / "dashboard"
CSP = (
    "default-src 'self'; script-src 'self'; style-src 'self'; img-src 'self'; "
    "connect-src 'self'; font-src 'self'; object-src 'none'; base-uri 'none'; "
    "form-action 'self'; frame-ancestors 'none'"
)
_SWAGGER_PATHS = frozenset({"/docs", "/redoc", "/docs/oauth2-redirect"})


# ---------------------------------------------------------------------------
def _route_label(request: Request) -> str:
    """The route template, so labels stay bounded whatever path is sent.

    Dashboard files and unknown paths match no API route; they share "other".
    """
    route = request.scope.get("route")
    return getattr(route, "path", None) or "other"


def create_app(workspace: Workspace, tokens: TokenStore, *, docs: bool = True,
               jobs: JobManager | None = None) -> FastAPI:
    """`docs=False` removes /docs and /redoc, which load Swagger UI from a CDN."""
    if not tokens:
        # Refuse to start rather than serve an unauthenticated inventory.
        raise ValueError("the API needs at least one token; see `apix token`")

    app = FastAPI(
        title="API Exorcist",
        version=__version__,
        description=(
            "Discovery, classification and Safe Kill for zombie, shadow and "
            "orphaned APIs. Simulated estate: nothing real is touched."
        ),
        docs_url="/docs" if docs else None,
        redoc_url="/redoc" if docs else None,
    )
    metrics = Metrics()
    app.state.metrics = metrics

    @app.middleware("http")
    async def harden_and_observe(
        request: Request, call_next: Callable[[Request], Awaitable[Response]]
    ) -> Response:
        started = time.perf_counter()
        incoming = request.headers.get("x-request-id", "")
        request_id = incoming if _REQUEST_ID.match(incoming) else uuid.uuid4().hex
        request.state.principal = None

        response: Response | None = None
        if request.method in {"POST", "PUT", "PATCH"}:
            length = request.headers.get("content-length")
            if length is None:
                response = JSONResponse({"detail": "Content-Length is required"}, 411)
            else:
                cap = MAX_UPLOAD_BODY if request.url.path == UPLOAD_PATH else MAX_BODY_BYTES
                if not length.isdigit() or int(length) > cap:
                    response = JSONResponse(
                        {"detail": f"request body over {cap // 1024} KiB"}, 413)
        status = 500
        try:
            if response is None:
                response = await call_next(request)
            status = response.status_code
        finally:
            elapsed = time.perf_counter() - started
            route = _route_label(request)
            metrics.observe(request.method, route, status, elapsed)
            log.info("request", extra={"fields": {
                "request_id": request_id,
                "method": request.method,
                "route": route,
                "status": status,
                "duration_ms": round(elapsed * 1000, 1),
                "principal": request.state.principal,
                "client": request.client.host if request.client else None,
            }})
        response.headers["X-Request-ID"] = request_id
        response.headers["Cache-Control"] = "no-store"
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["X-Frame-Options"] = "DENY"
        response.headers["Referrer-Policy"] = "no-referrer"
        if request.url.path not in _SWAGGER_PATHS:
            response.headers["Content-Security-Policy"] = CSP
        return response

    app.state.tokens = tokens

    # -- reads --------------------------------------------------------------
    @app.get("/v1/health")
    def health() -> dict[str, str]:
        return {"status": "ok", "version": __version__}

    @app.get("/v1/whoami")
    def whoami(who: Viewer) -> dict[str, str]:
        return {"name": who.name, "role": who.role.value}

    @app.get("/v1/summary")
    def summary(who: Viewer) -> dict[str, Any]:
        return workspace.summary()

    @app.get("/v1/inventory")
    def inventory(who: Viewer) -> list[dict[str, Any]]:
        return [r.to_dict() for r in workspace.records]

    @app.get("/v1/verdicts")
    def verdicts(
        who: Viewer,
        label: Annotated[str | None, Query(pattern="^[A-Z]+$")] = None,
    ) -> list[dict[str, Any]]:
        return [
            audit_entry(v) for v in workspace.verdicts
            if label is None or v.label.value == label
        ]

    @app.get("/v1/verdicts/{endpoint_id:path}")
    def verdict(endpoint_id: str, who: Viewer) -> dict[str, Any]:
        try:
            return workspace.verdict(endpoint_id)
        except UnknownEndpoint:
            raise HTTPException(404, f"no endpoint {endpoint_id!r}") from None

    @app.get("/v1/impact")
    def impact(who: Viewer) -> list[dict[str, Any]]:
        return [a.to_dict() for a in workspace.assessments]

    @app.get("/v1/impact/{endpoint_id:path}")
    def radius(endpoint_id: str, who: Viewer) -> dict[str, Any]:
        try:
            return workspace.radius(endpoint_id)
        except UnknownEndpoint:
            raise HTTPException(404, f"no endpoint {endpoint_id!r}") from None

    @app.get("/v1/benchmark")
    def benchmark(who: Viewer) -> dict[str, Any]:
        return workspace.benchmark()

    @app.get("/v1/safekill")
    def safekill(who: Viewer) -> dict[str, Any]:
        return workspace.safekill_state()

    @app.get("/v1/audit")
    def audit(
        who: Viewer,
        endpoint: str | None = None,
        limit: Annotated[int, Query(ge=1, le=5000)] = 200,
    ) -> dict[str, Any]:
        return workspace.audit(endpoint, limit)

    @app.get("/v1/audit/verify")
    def verify(who: Viewer) -> dict[str, Any]:
        return workspace.verify_audit()

    @app.get("/metrics", response_class=PlainTextResponse)
    def prometheus(who: Viewer) -> PlainTextResponse:
        return PlainTextResponse(
            metrics.render(workspace.metrics_state()),
            media_type="text/plain; version=0.0.4; charset=utf-8",
        )

    # -- actions ------------------------------------------------------------
    @app.post("/v1/demo/rescan")
    def rescan(who: Approver) -> dict[str, Any]:
        workspace.refresh()
        return workspace.summary()

    @app.post("/v1/safekill/shadow")
    def shadow(body: ShadowRequest, who: Approver) -> dict[str, Any]:
        try:
            result = workspace.start_shadow(body.endpoint_id).to_dict()
        except NotACandidate:
            metrics.action("shadow", "not_a_candidate")
            raise HTTPException(
                404, f"{body.endpoint_id!r} is not a removal candidate"
            ) from None
        metrics.action("shadow", "started")
        log.info("safekill.shadow", extra={"fields": {
            "endpoint_id": body.endpoint_id, "principal": who.name}})
        return result

    @app.post("/v1/safekill/decision")
    def decision(body: DecisionRequest, who: Approver) -> dict[str, Any]:
        try:
            outcome = workspace.decide(
                body.endpoint_id,
                approver=who.name,          # from the token, never the body
                approve=body.approve,
                accept_unidentified=body.accept_unidentified,
                note=body.note,
            )
        except NotAwaitingApproval:
            metrics.action("decision", "not_awaiting")
            raise HTTPException(
                409, f"{body.endpoint_id!r} is not awaiting approval; "
                "start its shadow window first"
            ) from None
        except NeedsAcknowledgement as warning:
            metrics.action("decision", "needs_acknowledgement")
            raise HTTPException(
                409,
                f"{warning}. Resend with accept_unidentified=true to accept that "
                "risk, or approve=false to decline.",
            ) from None
        result = outcome.to_dict()
        metrics.action("decision", "approved" if body.approve else "declined")
        log.info("safekill.decision", extra={"fields": {
            "endpoint_id": body.endpoint_id,
            "principal": who.name,
            "approve": body.approve,
            "state": result["state"],
        }})
        return result

    # -- scans a person starts: an uploaded folder or a GitHub link -----------
    scans = jobs or JobManager()
    app.state.jobs = scans

    @app.get("/v1/capabilities")
    def capabilities(who: Viewer) -> dict[str, Any]:
        """What works on this machine, so the page can say so before a scan."""
        semgrep = shutil.which("semgrep") is not None
        git = shutil.which("git") is not None
        code_note = None if semgrep else (
            "Semgrep is not installed here, so routes cannot be read from code. "
            "Install it with `pip install semgrep`, then restart.")
        return {
            "folder": {"available": True, "warning": code_note},
            "github": {
                "available": git,
                "warning": code_note if git else None,
                "reason": None if git else "git is not installed on this machine",
            },
            "website": {
                "available": False,
                "reason": (
                    "Scanning a live website is not available in this version. "
                    "Upload the project's folder, or give its GitHub link, to scan "
                    "the code behind the site instead."
                ),
            },
        }

    @app.post("/v1/scans/github", status_code=202)
    def scan_github(body: GithubScanRequest, who: Approver) -> dict[str, Any]:
        try:
            job = scans.submit_github(body.url, who.name)
        except ScanRefused as exc:
            raise HTTPException(422, str(exc)) from None
        metrics.action("scan_github", "started")
        log.info("scan.start", extra={"fields": {
            "job": job["id"], "kind": "github", "target": job["target"],
            "principal": who.name}})
        return job

    @app.post(UPLOAD_PATH, status_code=202)
    async def scan_upload(request: Request, who: Approver) -> dict[str, Any]:
        try:
            form = await request.form(max_files=MAX_FILES + 1, max_fields=20)
        except Exception as exc:  # any parse failure is the client's
            raise HTTPException(400, f"could not read the upload: {exc}") from None
        files: list[tuple[str, bytes]] = []
        try:
            for item in form.getlist("files"):
                if isinstance(item, str):
                    continue
                files.append((item.filename or "", await item.read()))
        finally:
            await form.close()
        workdir = tempfile.TemporaryDirectory(prefix="apix-upload-")
        try:
            saved = await run_in_threadpool(save_files, Path(workdir.name), files)
        except UploadRejected as exc:
            workdir.cleanup()
            raise HTTPException(422, str(exc)) from None
        try:
            job = scans.submit_folder(saved, workdir, who.name)
        except ScanRefused as exc:
            raise HTTPException(422, str(exc)) from None
        metrics.action("scan_folder", "started")
        log.info("scan.start", extra={"fields": {
            "job": job["id"], "kind": "folder", "files": saved.files,
            "principal": who.name}})
        return job

    @app.get("/v1/scans")
    def list_scans(who: Viewer) -> list[dict[str, Any]]:
        return scans.list()

    @app.get("/v1/scans/{job_id}")
    def get_scan(
        who: Viewer,
        job_id: Annotated[str, PathParam(pattern="^[0-9a-f]{12}$")],
    ) -> dict[str, Any]:
        job = scans.get(job_id)
        if job is None:
            raise HTTPException(404, f"no scan {job_id}")
        return job

    # Mounted last, so every /v1 route above takes precedence over it.
    if (DASHBOARD_DIR / "index.html").exists():
        app.mount("/", StaticFiles(directory=DASHBOARD_DIR, html=True), name="dashboard")

    return app


def default_app(audit_path: Path, tokens: TokenStore, *, seed: int = 7,
                use_model: bool = False, docs: bool = True) -> FastAPI:
    # Scan reports live beside the audit log, so one data directory holds both.
    return create_app(Workspace(audit_path, seed=seed, use_model=use_model), tokens,
                      docs=docs, jobs=JobManager(store=audit_path.parent / "scans"))
