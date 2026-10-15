"""
Scans started from the browser, run in the background.

A GitHub scan takes from ten seconds to a few minutes, most of it downloading,
so the request that starts one returns at once with a job id and the browser
polls it. Each job keeps a running list of what it is doing, which is what the
progress view shows.

Finished reports are written to `<data>/scans/<id>.json`, so a restart keeps
the history. Two scans run at a time; more wait their turn, and past a short
queue a new scan is refused rather than piling up work nobody is watching.
"""

from __future__ import annotations

import builtins
import copy
import hashlib
import json
import logging
import re
import tempfile
import threading
import time
import uuid
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from urllib.parse import urlsplit

from apix.live.repo import RepoError
from apix.live.scan import scan_repository
from apix.safekill.audit import AuditLog
from apix.scanning.compare import changes
from apix.scanning.report import OK, PARTIAL, check, repository_report
from apix.scanning.sensitivity import enrich
from apix.scanning.upload import SavedUpload
from apix.traffic.logs import ParsedLogs, iter_requests
from apix.traffic.usage import analyse

log = logging.getLogger("apix.scans")

MAX_WAITING = 6

#: What a person can decide about an endpoint found by a scan. A project scan
#: has no traffic and no gateway, so removal itself is out of reach; what is
#: in reach is triage, recorded under the reviewer's name in the scan's audit log.
DECISIONS: dict[str, str] = {
    "keep": "Keep: in use and intended",
    "document": "Needs documentation",
    "assign-owner": "Needs an owner",
    "investigate": "Investigate for removal",
}
SCAN_SUBJECT = "(scan)"


class NotReviewable(ValueError):
    """The scan or endpoint cannot take a review decision; the message says why."""
_SLUG = re.compile(r"^[A-Za-z0-9](?:[A-Za-z0-9-]{0,38})/[A-Za-z0-9._-]{1,100}$")


class ScanRefused(ValueError):
    """The scan was not started; the message says why."""


def parse_github(raw: str) -> str:
    """`owner/name` from anything a person might paste, or ScanRefused."""
    text = raw.strip()
    if not text:
        raise ScanRefused("paste a GitHub repository link, "
                          "for example https://github.com/fastapi/fastapi")
    if "://" not in text and not text.lower().startswith(("github.com/", "www.github.com/")):
        candidate = text
    else:
        parts = urlsplit(text if "://" in text else "https://" + text)
        host = (parts.hostname or "").lower()
        if host not in ("github.com", "www.github.com"):
            raise ScanRefused(
                f"{host or text} is not GitHub. Only github.com repositories can be "
                "scanned by link; for anything else, upload the project folder"
            )
        bits = [b for b in parts.path.split("/") if b]
        if len(bits) < 2:
            raise ScanRefused("that link names no repository; it should look like "
                              "https://github.com/owner/name")
        candidate = f"{bits[0]}/{bits[1]}"
    candidate = re.sub(r"\.git$", "", candidate.strip("/"))
    if not _SLUG.fullmatch(candidate):
        raise ScanRefused(f"{raw.strip()!r} is not a GitHub repository link")
    return candidate


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


@dataclass
class ScanJob:
    id: str
    kind: str                     # "github" | "folder"
    target: str
    requested_by: str
    status: str = "queued"        # queued | running | done | failed
    created_at: str = field(default_factory=_now)
    started_at: str | None = None
    finished_at: str | None = None
    duration_s: float | None = None
    progress: list[dict[str, str]] = field(default_factory=list)
    error: str | None = None
    report: dict[str, Any] | None = None
    #: Usage evidence from imported access logs, kept apart from the report so
    #: the report (whose hash is in the audit chain) never changes.
    traffic: dict[str, Any] | None = None

    def say(self, message: str) -> None:
        self.progress.append({"at": _now(), "message": message})

    def to_dict(self, *, full: bool = True) -> dict[str, Any]:
        d: dict[str, Any] = {
            "id": self.id, "kind": self.kind, "target": self.target,
            "requested_by": self.requested_by, "status": self.status,
            "created_at": self.created_at, "started_at": self.started_at,
            "finished_at": self.finished_at, "duration_s": self.duration_s,
            "error": self.error,
            "progress": self.progress if full else self.progress[-1:],
        }
        if self.report is not None:
            d["summary"] = self.report.get("summary", [])
            if full:
                d["report"] = self.report
        if self.traffic is not None:
            d["traffic_summary"] = {
                "imported_at": self.traffic.get("imported_at"),
                "window_days": (self.traffic.get("window") or {}).get("days"),
                "lifecycle": self.traffic.get("lifecycle", {}),
            }
            if full:
                d["traffic"] = self.traffic
        return d


class JobManager:
    def __init__(self, store: Path | None = None, workers: int = 2) -> None:
        self.store = store
        self._jobs: dict[str, ScanJob] = {}
        self._lock = threading.Lock()
        self._pool = ThreadPoolExecutor(max_workers=workers, thread_name_prefix="apix-scan")
        self._audits: dict[str, AuditLog] = {}
        self._load()

    # -- history -----------------------------------------------------------
    def _load(self) -> None:
        if self.store is None or not self.store.is_dir():
            return
        for f in sorted(self.store.glob("*.json")):
            try:
                d = json.loads(f.read_text(encoding="utf-8"))
                job = ScanJob(**{k: d[k] for k in ScanJob.__dataclass_fields__ if k in d})
                self._jobs[job.id] = job
            except (ValueError, TypeError, KeyError):
                log.warning("skipping unreadable scan record %s", f.name)

    def _save(self, job: ScanJob) -> None:
        if self.store is None:
            return
        self.store.mkdir(parents=True, exist_ok=True)
        payload = {k: getattr(job, k) for k in ScanJob.__dataclass_fields__}
        tmp = self.store / f"{job.id}.json.tmp"
        tmp.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
        tmp.replace(self.store / f"{job.id}.json")

    # -- reads ---------------------------------------------------------------
    def list(self) -> list[dict[str, Any]]:
        with self._lock:
            jobs = sorted(self._jobs.values(), key=lambda j: j.created_at, reverse=True)
            return [j.to_dict(full=False) for j in jobs]

    def get(self, job_id: str) -> dict[str, Any] | None:
        with self._lock:
            job = self._jobs.get(job_id)
            if job is None:
                return None
            d = copy.deepcopy(job.to_dict())
        d["reviews"] = self.reviews(job_id)
        if d.get("report") is not None:
            enrich(d["report"], d.get("traffic"))
            prev = self.previous(job_id)
            d["changes"] = changes(d, prev) if prev else None
        return d

    def previous(self, job_id: str) -> dict[str, Any] | None:
        """The latest finished scan of the same target before this one."""
        with self._lock:
            job = self._jobs.get(job_id)
            if job is None or job.kind != "github":
                return None
            earlier = [j for j in self._jobs.values()
                       if j.target == job.target and j.status == "done" and j.report
                       and j.created_at < job.created_at]
            if not earlier:
                return None
            best = max(earlier, key=lambda j: j.created_at)
            return copy.deepcopy(best.to_dict())

    def portfolio(self) -> dict[str, Any]:
        """Every project's latest finished scan, and the riskiest endpoints across them."""
        with self._lock:
            latest: dict[str, ScanJob] = {}
            for j in self._jobs.values():
                if j.status == "done" and j.report is not None:
                    cur = latest.get(j.target)
                    if cur is None or j.created_at > cur.created_at:
                        latest[j.target] = j
            snapshot = [copy.deepcopy(j.to_dict()) for j in latest.values()]
        projects: list[dict[str, Any]] = []
        risks: list[dict[str, Any]] = []
        totals = {"projects": 0, "endpoints": 0, "undocumented": 0, "candidates": 0,
                  "likely": 0, "zombies": 0, "high_sensitivity": 0, "reviewed": 0}
        for d in sorted(snapshot, key=lambda x: x["created_at"], reverse=True):
            report = d["report"]
            enrich(report, d.get("traffic"))
            usage = (d.get("traffic") or {}).get("endpoints") or {}
            eps = report["endpoints"]
            cands = report.get("candidates", [])
            row: dict[str, Any] = {
                "id": d["id"], "target": d["target"], "kind": d["kind"],
                "scanned_at": d["finished_at"] or d["created_at"],
                "endpoints": len(eps),
                "undocumented": sum(1 for e in eps if not e.get("documented")),
                "candidates": len(cands),
                "likely": sum(1 for c in cands if c.get("label") == "Likely zombie"),
                "zombies": sum(1 for u in usage.values() if u.get("lifecycle") == "ZOMBIE"),
                "high_sensitivity": sum(1 for e in eps if e["sensitivity"]["level"] == "high"),
                "reviewed": len(self.reviews(d["id"])),
                "traffic": bool(d.get("traffic")),
                "risk": max((e["priority"] for e in eps), default=0),
            }
            projects.append(row)
            for k in totals:
                if k != "projects":
                    totals[k] += row[k]
            for e in eps:
                zombie = (usage.get(e["id"]) or {}).get("lifecycle") == "ZOMBIE"
                if e.get("candidate") or zombie:
                    risks.append({
                        "scan": d["id"], "target": d["target"], "id": e["id"],
                        "priority": e["priority"],
                        "sensitivity": e["sensitivity"]["category"],
                        "level": e["sensitivity"]["level"],
                        "label": "Zombie (no traffic)" if zombie
                        else (e.get("candidate") or {}).get("label"),
                        "documented": bool(e.get("documented")),
                    })
        totals["projects"] = len(projects)
        risks.sort(key=lambda r: (-r["priority"], r["target"], r["id"]))
        return {"totals": totals, "projects": projects, "top_risks": risks[:15]}

    # -- usage evidence from access logs ----------------------------------------
    def import_traffic(self, job_id: str, files: builtins.list[tuple[str, bytes]],
                       who: str) -> dict[str, Any]:
        with self._lock:
            job = self._jobs.get(job_id)
            if job is None:
                raise NotReviewable(f"no scan {job_id}")
            if job.status != "done" or job.report is None:
                raise NotReviewable("only a finished scan can take access logs")
            endpoints = copy.deepcopy(job.report["endpoints"])
        parsed = ParsedLogs()
        result = analyse(endpoints, iter_requests(files, parsed))
        if not result["requests"]:
            raise NotReviewable(
                "no access-log entries were recognised in "
                + (", ".join(f.name for f in parsed.files) or "the upload")
                + ". Supported: nginx or Apache combined format, AWS ALB logs, and JSON "
                "lines from gateways such as Kong, AWS API Gateway, Envoy or Traefik")
        result["files"] = [f.to_dict() for f in parsed.files]
        result["truncated"] = parsed.truncated
        result["imported_at"] = _now()
        result["imported_by"] = who
        with self._lock:
            replaced = job.traffic is not None
            job.traffic = result
        self._save(job)
        digest = hashlib.sha256(json.dumps(result, sort_keys=True).encode()).hexdigest()
        days = (result.get("window") or {}).get("days")
        self._record(job_id, "USAGE_IMPORTED",
                     f"{result['requests']:,} request(s)"
                     + (f" over {days:g} day(s)" if days is not None else "")
                     + f" from {len(parsed.files)} file(s)"
                     + (", replacing the earlier import" if replaced else ""),
                     who, {"usage_sha256": digest, "lifecycle": result["lifecycle"],
                           "files": [f.name for f in parsed.files]})
        return self.get(job_id) or {}

    def rescan(self, job_id: str, who: str) -> dict[str, Any]:
        with self._lock:
            job = self._jobs.get(job_id)
        if job is None:
            raise ScanRefused(f"no scan {job_id}")
        if job.kind != "github":
            raise ScanRefused("an uploaded folder cannot be re-scanned; upload it again")
        return self.submit_github(job.target, who)

    # -- the scan's own audit log: who started it, what it found, decisions ----
    def audit_log(self, job_id: str) -> AuditLog:
        with self._lock:
            log = self._audits.get(job_id)
            if log is None:
                path = self.store / f"{job_id}.audit.jsonl" if self.store else None
                log = AuditLog(path=path)
                self._audits[job_id] = log
            return log

    def _record(self, job_id: str, to_state: str, reason: str, actor: str,
                evidence: dict[str, Any] | None = None, *,
                subject: str = SCAN_SUBJECT, from_state: str | None = None) -> None:
        self.audit_log(job_id).append(
            at=_now(), endpoint_id=subject, from_state=from_state, to_state=to_state,
            reason=reason, actor=actor, evidence=evidence or {},
        )

    def audit(self, job_id: str) -> dict[str, Any] | None:
        if job_id not in self._jobs:
            return None
        log = self.audit_log(job_id)
        check = log.verify()
        return {
            "head": log.head,
            "chain": {"ok": check.ok, "entries": check.entries,
                      "broken_at": check.broken_at, "problem": check.problem},
            "entries": [e.to_dict() for e in log.entries],
        }

    def reviews(self, job_id: str) -> dict[str, dict[str, Any]]:
        """The latest decision per endpoint, read back from the audit log."""
        if job_id not in self._jobs:
            return {}
        out: dict[str, dict[str, Any]] = {}
        for e in self.audit_log(job_id).entries:
            if e.endpoint_id != SCAN_SUBJECT and e.to_state in DECISIONS:
                out[e.endpoint_id] = {
                    "decision": e.to_state, "label": DECISIONS[e.to_state],
                    "by": e.actor, "at": e.at, "note": e.evidence.get("note", ""),
                }
        return out

    def review(self, job_id: str, endpoint_id: str, decision: str, note: str,
               who: str) -> dict[str, dict[str, Any]]:
        with self._lock:
            job = self._jobs.get(job_id)
            if job is None:
                raise NotReviewable(f"no scan {job_id}")
            if job.status != "done" or job.report is None:
                raise NotReviewable("only a finished scan can be reviewed")
            known = {e["id"] for e in job.report.get("endpoints", [])}
        if endpoint_id not in known:
            raise NotReviewable(f"{endpoint_id!r} is not an endpoint this scan found")
        if decision not in DECISIONS:
            raise NotReviewable(f"unknown decision {decision!r}")
        previous = self.reviews(job_id).get(endpoint_id, {}).get("decision")
        self._record(job_id, decision, DECISIONS[decision], who,
                     {"note": note} if note else {}, subject=endpoint_id,
                     from_state=previous)
        return self.reviews(job_id)

    # -- starting scans ---------------------------------------------------------
    def _new(self, kind: str, target: str, who: str) -> ScanJob:
        with self._lock:
            waiting = sum(1 for j in self._jobs.values() if j.status in ("queued", "running"))
            if waiting >= MAX_WAITING:
                raise ScanRefused(
                    f"{waiting} scans are already queued or running; wait for one to finish"
                )
            job = ScanJob(id=uuid.uuid4().hex[:12], kind=kind, target=target,
                          requested_by=who)
            job.say("Queued")
            self._jobs[job.id] = job
        self._record(job.id, "STARTED", f"{kind} scan of {target}", who,
                     {"kind": kind, "target": target})
        return job

    def submit_github(self, raw: str, who: str) -> dict[str, Any]:
        slug = parse_github(raw)
        job = self._new("github", f"github.com/{slug}", who)
        self._pool.submit(self._run, job, lambda: self._github(job, slug))
        return job.to_dict()

    def submit_folder(self, saved: SavedUpload, workdir: tempfile.TemporaryDirectory[str],
                      who: str) -> dict[str, Any]:
        try:
            job = self._new("folder", saved.name, who)
        except ScanRefused:
            workdir.cleanup()
            raise
        self._pool.submit(self._run, job, lambda: self._folder(job, saved, workdir))
        return job.to_dict()

    # -- running ----------------------------------------------------------------
    def _run(self, job: ScanJob, work: Any) -> None:
        started = time.monotonic()
        with self._lock:
            job.status, job.started_at = "running", _now()
        try:
            report = work()
            with self._lock:
                job.report, job.status = report, "done"
                job.say("Finished")
        except RepoError as exc:
            with self._lock:
                job.status, job.error = "failed", str(exc)
                job.say(f"Stopped: {exc}")
        except Exception as exc:  # a scan must never take the server down
            log.exception("scan %s failed", job.id)
            with self._lock:
                job.status = "failed"
                job.error = f"the scan stopped unexpectedly ({type(exc).__name__}: {exc})"
                job.say("Stopped unexpectedly")
        finally:
            with self._lock:
                job.finished_at = _now()
                job.duration_s = round(time.monotonic() - started, 1)
                snapshot = job
            self._save(snapshot)
            if job.status == "done" and job.report is not None:
                # The report's fingerprint goes into the chain, so a report
                # edited on disk later no longer matches what was recorded.
                digest = hashlib.sha256(json.dumps(
                    job.report, sort_keys=True, ensure_ascii=False).encode()).hexdigest()
                self._record(job.id, "FINISHED",
                             f"{len(job.report.get('endpoints', []))} endpoint(s) found",
                             "apix-scanner",
                             {"report_sha256": digest, "duration_s": job.duration_s})
            else:
                self._record(job.id, "FAILED", job.error or "the scan did not finish",
                             "apix-scanner")
            log.info("scan.finished", extra={"fields": {
                "job": job.id, "kind": job.kind, "status": job.status,
                "duration_s": job.duration_s}})

    def _github(self, job: ScanJob, slug: str) -> dict[str, Any]:
        result = scan_repository(slug, verbose=False, progress=job.say)
        acquired = check(
            "Project downloaded", OK,
            f"github.com/{slug}, default branch at commit {result.head_commit}",
        )
        return repository_report(result, has_history=True, acquired=acquired)

    def _folder(self, job: ScanJob, saved: SavedUpload,
                workdir: tempfile.TemporaryDirectory[str]) -> dict[str, Any]:
        try:
            result = scan_repository(saved.name, local_path=saved.root, verbose=False,
                                     progress=job.say)
            detail = (f"{saved.files} file(s), "
                      f"{saved.bytes / (1024 * 1024):.1f} MB received")
            status = OK
            if saved.skipped:
                status = PARTIAL
                detail += (f"; {len(saved.skipped)} file(s) refused because their names "
                           "could point outside the upload")
            return repository_report(
                result, has_history=(saved.root / ".git").is_dir(),
                acquired=check("Project uploaded", status, detail),
            )
        finally:
            workdir.cleanup()

    def shutdown(self) -> None:
        self._pool.shutdown(wait=False, cancel_futures=True)
