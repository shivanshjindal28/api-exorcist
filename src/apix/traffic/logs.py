"""
Read access logs into requests: method, path, status, time, client.

Three shapes cover most of what a bank's estate writes:

    combined    nginx and Apache "combined" or "common" format
    alb         AWS Application Load Balancer access logs
    json        one JSON object per line: Kong, AWS API Gateway, Envoy,
                Traefik, or any gateway whose field names are recognisable

Two things are dropped as each line is read, because a log is the most
sensitive file anyone will hand this tool:

    query strings   they carry tokens, account numbers and OTPs
    client address  replaced by a salted hash used only to count distinct
                    clients; the salt is random per import and never stored,
                    so even this tool cannot link a hash back to an address

Gzip-rotated files (access.log.2.gz) are read directly, with a cap on how far
any one file may decompress.
"""

from __future__ import annotations

import gzip
import hashlib
import io
import json
import re
import secrets
from collections import Counter
from collections.abc import Iterable, Iterator
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any
from urllib.parse import unquote, urlsplit

#: Lines read per import, across all files. Ten million lines is weeks of a
#: busy gateway; past it the import stops and says so rather than running on.
MAX_LINES = 10_000_000
#: How far one gzip file may expand. A small file that inflates without limit
#: is a classic way to exhaust a server's memory.
MAX_DECOMPRESSED = 2 * 1024 ** 3

_METHODS = {"GET", "POST", "PUT", "PATCH", "DELETE", "HEAD", "OPTIONS"}

_COMBINED = re.compile(
    r'^(?P<ip>\S+) \S+ \S+ \[(?P<time>[^\]]+)\] '
    r'"(?P<method>[A-Z]+) (?P<target>\S+)(?: [^"]*)?" (?P<status>\d{3}) \S+'
    r'(?: "[^"]*" "(?P<ua>[^"]*)")?')
_ALB = re.compile(
    r'^(?:https?|h2|wss?|grpcs) (?P<time>\S+) \S+ (?P<ip>[^\s:]+|\[[^\]]+\]):\d+ \S+ '
    r'\S+ \S+ \S+ (?P<status>\d{3}|-) \S+ \d+ \d+ "(?P<method>[A-Z]+) (?P<target>\S+)[^"]*"')

# Field names gateways use, lower-cased and flattened with dots.
_JSON_METHOD = ("method", "request_method", "httpmethod", "request.method", "http.method",
                "requestmethod", "http.request.method", "verb")
_JSON_PATH = ("path", "uri", "request_uri", "requestpath", "request.uri", "request.path",
              "request.url", "url", "url.path", "http.target", "http.url", "resourcepath",
              "request_path", "requesturi")
_JSON_STATUS = ("status", "status_code", "statuscode", "response.status",
                "downstreamstatus", "http.status_code", "http.response.status_code",
                "response_code", "elb_status_code", "responsestatus")
_JSON_TIME = ("time", "timestamp", "@timestamp", "time_local", "time_iso8601",
              "requesttime", "requesttimeepoch", "started_at", "startutc", "ts", "date",
              "start_time")
_JSON_CLIENT = ("remote_addr", "client_ip", "clientip", "ip", "sourceip", "client",
                "clienthost", "client.ip", "source.ip", "identity.sourceip",
                "x_forwarded_for", "downstream_remote_address")


@dataclass(frozen=True)
class Request:
    method: str
    path: str                  # no query string, no fragment
    status: int | None
    at: datetime | None
    client: str                # salted hash; "" when the log had no address


@dataclass
class FileSummary:
    name: str
    lines: int = 0
    parsed: int = 0
    format: str = "unrecognised"
    note: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {"name": self.name, "lines": self.lines, "parsed": self.parsed,
                "format": self.format, "note": self.note}


@dataclass
class ParsedLogs:
    """What was read: one summary per file. The requests themselves stream
    through `iter_requests` and are never all held in memory at once."""
    files: list[FileSummary] = field(default_factory=list)
    truncated: bool = False


def clean_path(target: str) -> str:
    """The path of a request target, with the query and fragment removed."""
    if "://" in target:
        target = urlsplit(target).path or "/"
    target = target.split("?", 1)[0].split("#", 1)[0]
    path = re.sub(r"/{2,}", "/", unquote(target))
    if not path.startswith("/"):
        path = "/" + path
    return path.rstrip("/") or "/"


def parse_time(raw: Any) -> datetime | None:
    if raw is None or raw == "":
        return None
    if isinstance(raw, int | float) or (isinstance(raw, str) and raw.replace(".", "", 1).isdigit()):
        value = float(raw)
        if value > 1e14:        # microseconds
            value /= 1e6
        elif value > 1e11:      # milliseconds
            value /= 1e3
        try:
            return datetime.fromtimestamp(value, tz=timezone.utc)
        except (OverflowError, OSError, ValueError):
            return None
    text = str(raw).strip()
    for fmt in ("%d/%b/%Y:%H:%M:%S %z", "%d/%b/%Y:%H:%M:%S"):
        try:
            t = datetime.strptime(text, fmt)
            return t if t.tzinfo else t.replace(tzinfo=timezone.utc)
        except ValueError:
            pass
    try:
        t = datetime.fromisoformat(text.replace("Z", "+00:00"))
    except ValueError:
        return None
    return t if t.tzinfo else t.replace(tzinfo=timezone.utc)


def _flatten(obj: dict[str, Any], prefix: str = "", depth: int = 0) -> dict[str, Any]:
    out: dict[str, Any] = {}
    for k, v in obj.items():
        key = f"{prefix}{str(k).lower()}"
        if isinstance(v, dict) and depth < 2:
            out.update(_flatten(v, key + ".", depth + 1))
        else:
            out[key] = v
    return out


def _first(flat: dict[str, Any], names: tuple[str, ...]) -> Any:
    for n in names:
        v = flat.get(n)
        if v not in (None, "", "-"):
            return v
    return None


class _Hasher:
    def __init__(self) -> None:
        self._salt = secrets.token_bytes(16)    # never stored, never logged

    def __call__(self, address: str | None) -> str:
        if not address or address == "-":
            return ""
        first = address.split(",")[0].strip().strip("[]")
        return hashlib.sha256(self._salt + first.encode()).hexdigest()[:16]


def _status(raw: Any) -> int | None:
    try:
        s = int(str(raw).strip())
    except (TypeError, ValueError):
        return None
    return s if 100 <= s <= 599 else None


def _parse_line(line: str, hasher: _Hasher) -> tuple[str, Request] | None:
    line = line.strip()
    if not line:
        return None
    if line.startswith("{"):
        try:
            obj = json.loads(line)
        except ValueError:
            return None
        if not isinstance(obj, dict):
            return None
        flat = _flatten(obj)
        method = str(_first(flat, _JSON_METHOD) or "").upper()
        target = _first(flat, _JSON_PATH)
        if method not in _METHODS or not isinstance(target, str):
            # Some gateways log the request line as one field ("GET /x HTTP/1.1").
            req = _first(flat, ("request", "request_line", "requestline"))
            if isinstance(req, str) and " " in req:
                bits = req.split(" ")
                method, target = bits[0].upper(), bits[1]
        if method not in _METHODS or not isinstance(target, str):
            return None
        return "json", Request(method, clean_path(target), _status(_first(flat, _JSON_STATUS)),
                               parse_time(_first(flat, _JSON_TIME)),
                               hasher(str(_first(flat, _JSON_CLIENT) or "")))
    m = _ALB.match(line)
    if m:
        return "alb", Request(m["method"], clean_path(m["target"]), _status(m["status"]),
                              parse_time(m["time"]), hasher(m["ip"]))
    m = _COMBINED.match(line)
    if m and m["method"] in _METHODS:
        return "combined", Request(m["method"], clean_path(m["target"]), _status(m["status"]),
                                   parse_time(m["time"]), hasher(m["ip"]))
    return None


def _lines(name: str, data: bytes) -> tuple[Iterator[str], str]:
    if name.lower().endswith(".gz") or data[:2] == b"\x1f\x8b":
        raw = gzip.GzipFile(fileobj=io.BytesIO(data))
        return _capped(raw), "gzip"
    return iter(io.TextIOWrapper(io.BytesIO(data), encoding="utf-8", errors="replace")), ""


def _capped(raw: gzip.GzipFile) -> Iterator[str]:
    total = 0
    for chunk in io.TextIOWrapper(raw, encoding="utf-8", errors="replace"):
        total += len(chunk)
        if total > MAX_DECOMPRESSED:
            raise ValueError("decompresses past the 2 GB limit")
        yield chunk


def iter_requests(files: Iterable[tuple[str, bytes]], into: ParsedLogs) -> Iterator[Request]:
    """Yield every recognised request; unrecognised lines are counted, never
    guessed at. Per-file summaries are filled into `into` as files are read."""
    hasher = _Hasher()
    seen = 0
    for name, data in files:
        summary = FileSummary(name=name or "log")
        into.files.append(summary)
        formats: Counter[str] = Counter()
        packing = ""
        try:
            lines, packing = _lines(summary.name, data)
            for line in lines:
                if seen >= MAX_LINES:
                    into.truncated = True
                    summary.note = f"stopped at the {MAX_LINES:,}-line limit for one import"
                    break
                seen += 1
                summary.lines += 1
                got = _parse_line(line, hasher)
                if got:
                    formats[got[0]] += 1
                    yield got[1]
        except (OSError, EOFError, ValueError) as exc:
            summary.note = f"could not be read to the end: {exc}"
        summary.parsed = sum(formats.values())
        if formats:
            summary.format = formats.most_common(1)[0][0] + (" (gzip)" if packing else "")
        elif not summary.note:
            summary.note = ("no line was recognised as an access log entry (supported: "
                            "nginx/Apache combined, AWS ALB, JSON lines)")


def parse_files(files: Iterable[tuple[str, bytes]]) -> tuple[ParsedLogs, list[Request]]:
    """Every request in memory at once: for tests and small files only."""
    parsed = ParsedLogs()
    return parsed, list(iter_requests(files, parsed))
