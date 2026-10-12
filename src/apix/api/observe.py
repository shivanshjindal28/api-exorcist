"""
Observability: Prometheus metrics and structured logs for the API.

Metrics are written in the Prometheus text exposition format by hand rather
than through prometheus_client. The format is small and stable, and one less
dependency is one less thing a bank's software review has to clear.

Two decisions worth stating:

- **Requests are labelled by route template, never by raw path.** Endpoint ids
  appear in URLs (`/v1/verdicts/GET%20/v1/cards/...`), and anyone can send any
  path. Labelling by raw path would let an unauthenticated client create a new
  time series per request until the process runs out of memory. Dashboard
  files and unknown paths share one label, "other".
- **`/metrics` needs a token like everything else.** A scrape shows how many
  zombies an estate has and whether its audit chain holds, which is exactly the
  map an attacker wants. Prometheus sends a bearer token natively
  (`authorization: {credentials_file: ...}` in the scrape config).

Logs are one JSON object per line when `APIX_LOG_FORMAT=json`, the shape a SIEM
ingests without a parser. They name the principal, never the token, and never
log request bodies, which can carry an approver's free-text note.
"""

from __future__ import annotations

import json
import logging
import threading
import time
from collections import defaultdict
from dataclasses import dataclass, field
from typing import Any

from apix import __version__

# Seconds. Scans take hundreds of milliseconds; the benchmark several seconds.
BUCKETS = (0.005, 0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 1.0, 2.5, 5.0, 10.0)

log = logging.getLogger("apix.api")


@dataclass
class Metrics:
    """Request counters and latency histograms, safe across worker threads."""

    started: float = field(default_factory=time.time)
    _lock: threading.Lock = field(default_factory=threading.Lock, repr=False)
    _requests: dict[tuple[str, str, str], int] = field(
        default_factory=lambda: defaultdict(int))
    _latency: dict[tuple[str, str], list[int]] = field(
        default_factory=lambda: defaultdict(lambda: [0] * (len(BUCKETS) + 1)))
    _latency_sum: dict[tuple[str, str], float] = field(
        default_factory=lambda: defaultdict(float))
    _auth_failures: dict[str, int] = field(default_factory=lambda: defaultdict(int))
    _actions: dict[tuple[str, str], int] = field(default_factory=lambda: defaultdict(int))

    def observe(self, method: str, route: str, status: int, seconds: float) -> None:
        with self._lock:
            self._requests[(method, route, str(status))] += 1
            counts = self._latency[(method, route)]
            for i, bound in enumerate(BUCKETS):
                if seconds <= bound:
                    counts[i] += 1
                    break
            else:
                counts[-1] += 1
            self._latency_sum[(method, route)] += seconds

    def auth_failure(self, reason: str) -> None:
        with self._lock:
            self._auth_failures[reason] += 1

    def action(self, kind: str, result: str) -> None:
        with self._lock:
            self._actions[(kind, result)] += 1

    def render(self, state: dict[str, Any]) -> str:
        """The exposition text. `state` carries the estate gauges."""
        out: list[str] = []

        def family(name: str, kind: str, help_: str) -> None:
            out.append(f"# HELP {name} {help_}")
            out.append(f"# TYPE {name} {kind}")

        family("apix_build_info", "gauge", "Version of API Exorcist serving this.")
        out.append(f'apix_build_info{{version="{_label(__version__)}"}} 1')
        family("apix_process_start_time_seconds", "gauge", "Unix time the process started.")
        out.append(f"apix_process_start_time_seconds {self.started:.3f}")

        with self._lock:
            requests = dict(self._requests)
            latency = {k: list(v) for k, v in self._latency.items()}
            sums = dict(self._latency_sum)
            failures = dict(self._auth_failures)
            actions = dict(self._actions)

        family("apix_http_requests_total", "counter",
               "Requests by method, route template and status.")
        for (method, route, status), n in sorted(requests.items()):
            out.append(
                f'apix_http_requests_total{{method="{_label(method)}",'
                f'route="{_label(route)}",status="{status}"}} {n}'
            )

        family("apix_http_request_duration_seconds", "histogram",
               "Request latency by method and route template.")
        for (method, route), counts in sorted(latency.items()):
            labels = f'method="{_label(method)}",route="{_label(route)}"'
            running = 0
            for bound, n in zip(BUCKETS, counts, strict=False):
                running += n
                out.append(
                    f'apix_http_request_duration_seconds_bucket{{{labels},le="{bound}"}} '
                    f"{running}"
                )
            running += counts[-1]
            out.append(
                f'apix_http_request_duration_seconds_bucket{{{labels},le="+Inf"}} {running}'
            )
            out.append(f"apix_http_request_duration_seconds_sum{{{labels}}} "
                       f"{sums[(method, route)]:.6f}")
            out.append(f"apix_http_request_duration_seconds_count{{{labels}}} {running}")

        family("apix_auth_failures_total", "counter",
               "Rejected credentials by reason. A rising rate is someone guessing.")
        for reason in ("missing", "unrecognised", "forbidden"):
            out.append(
                f'apix_auth_failures_total{{reason="{reason}"}} {failures.get(reason, 0)}'
            )

        family("apix_safekill_actions_total", "counter",
               "Safe Kill actions taken through the API, by kind and result.")
        for (kind, result), n in sorted(actions.items()):
            out.append(
                f'apix_safekill_actions_total{{kind="{_label(kind)}",'
                f'result="{_label(result)}"}} {n}'
            )

        family("apix_endpoints", "gauge", "Endpoints in the inventory, by verdict label.")
        for label, n in sorted(state.get("labels", {}).items()):
            out.append(f'apix_endpoints{{label="{_label(label)}"}} {n}')
        gauges = [
            ("apix_removal_candidates", "Endpoints proposed for removal.",
             "removal_candidates"),
            ("apix_cleared_by_gate", "Candidates the dependency gate let through.",
             "cleared_by_gate"),
            ("apix_safekill_awaiting_approval", "Removals waiting for a named approver.",
             "awaiting_approval"),
            ("apix_audit_entries", "Entries in the Safe Kill audit log.", "audit_entries"),
            ("apix_audit_chain_ok",
             "1 if every audit entry's hash and link verify, 0 if the chain is broken.",
             "audit_chain_ok"),
            ("apix_last_scan_timestamp_seconds", "Unix time of the last completed scan.",
             "scanned_at_unix"),
        ]
        for name, help_, key in gauges:
            if key in state:
                family(name, "gauge", help_)
                out.append(f"{name} {state[key]}")
        return "\n".join(out) + "\n"


def _label(value: str) -> str:
    """Escape a label value as the exposition format requires."""
    return value.replace("\\", "\\\\").replace('"', '\\"').replace("\n", "\\n")


# ---------------------------------------------------------------------------
# Logs
# ---------------------------------------------------------------------------
class JsonFormatter(logging.Formatter):
    """One JSON object per line; structured fields come from `extra={"fields":...}`."""

    def format(self, record: logging.LogRecord) -> str:
        doc: dict[str, Any] = {
            "ts": time.strftime("%Y-%m-%dT%H:%M:%S", time.gmtime(record.created))
            + f".{int(record.msecs):03d}Z",
            "level": record.levelname.lower(),
            "logger": record.name,
            "event": record.getMessage(),
        }
        fields = getattr(record, "fields", None)
        if isinstance(fields, dict):
            doc.update(fields)
        if record.exc_info:
            doc["exception"] = self.formatException(record.exc_info)
        return json.dumps(doc, ensure_ascii=False, default=str)


class TextFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        fields = getattr(record, "fields", None)
        tail = ""
        if isinstance(fields, dict):
            tail = " " + " ".join(f"{k}={v}" for k, v in fields.items())
        return f"{record.levelname:<7} {record.getMessage()}{tail}"


def configure_logging(fmt: str) -> dict[str, Any]:
    """Configure apix and uvicorn loggers; returns uvicorn's log_config.

    uvicorn's own access log is switched off: the API writes a richer access
    line itself (principal, route template, request id), and two lines per
    request would double a SIEM's ingest for nothing.
    """
    formatter = "apix.api.observe.JsonFormatter" if fmt == "json" \
        else "apix.api.observe.TextFormatter"
    return {
        "version": 1,
        "disable_existing_loggers": False,
        "formatters": {"apix": {"()": formatter}},
        "handlers": {
            "stdout": {"class": "logging.StreamHandler", "formatter": "apix",
                       "stream": "ext://sys.stdout"},
        },
        "loggers": {
            "apix": {"handlers": ["stdout"], "level": "INFO", "propagate": False},
            "uvicorn.error": {"handlers": ["stdout"], "level": "INFO",
                              "propagate": False},
            "uvicorn.access": {"handlers": [], "level": "WARNING", "propagate": False},
        },
    }
