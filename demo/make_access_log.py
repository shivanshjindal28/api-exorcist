"""Write a SYNTHETIC nginx access log for a finished scan, to demonstrate usage import.

    python demo/make_access_log.py data/scans/<id>.json demo/synthetic-access.log
    python demo/make_access_log.py OWASP/crAPI demo/synthetic-crapi-access.log

The second form uses the latest finished scan of that repository in data/scans.

No public project publishes its production access logs, so the Usage view
cannot be shown on real traffic from a public repository. This writes one,
and says so three ways: the file name should say synthetic, the first line
is a comment no log format accepts (the import counts it as unrecognised),
and every client address is from 198.51.100.0/24, the range RFC 5737
reserves for documentation.

What it simulates, over 45 days:
    - ordinary use of every endpoint except the scan's likely zombies
    - the likely zombies: no successful request, but a burst of failed
      attempts from one address (someone brute-forcing an old OTP check)
    - a few routes the code does not have (shadow traffic) and scanner noise
"""

from __future__ import annotations

import json
import random
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

DAYS = 45
SEED = 7
_MONTHS = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"]


def _clf(t: datetime) -> str:
    return f"{t.day:02d}/{_MONTHS[t.month - 1]}/{t.year}:{t:%H:%M:%S} +0000"


def _fill(path: str, rng: random.Random) -> str:
    parts = []
    for seg in path.split("/"):
        if seg.startswith("{") and seg.endswith("}"):
            parts.append(str(rng.randint(1, 9999)))
        else:
            parts.append(seg)
    return "/".join(parts)


def _line(ip: str, t: datetime, method: str, target: str, status: int, ua: str) -> str:
    return f'{ip} - - [{_clf(t)}] "{method} {target} HTTP/1.1" {status} {random.randint(80, 4000)} "-" "{ua}"'


def _find(scan: str) -> Path:
    """A scan file, or the latest finished scan of a repository named owner/name."""
    if Path(scan).is_file():
        return Path(scan)
    target = "github.com/" + scan.strip("/")
    found = []
    for f in Path("data/scans").glob("*.json"):
        d = json.loads(f.read_text(encoding="utf-8"))
        if d.get("target", "").lower() == target.lower() and d.get("status") == "done":
            found.append((d["created_at"], f))
    if not found:
        raise SystemExit(f"no finished scan of {target} in data/scans; scan it first")
    return max(found)[1]


def main(scan: str, out: str) -> int:
    rng = random.Random(SEED)
    random.seed(SEED)
    job = json.loads(_find(scan).read_text(encoding="utf-8"))
    endpoints = job["report"]["endpoints"]
    dead = {c["endpoint_id"] for c in job["report"].get("candidates", [])
            if c.get("label") == "Likely zombie"}
    end = datetime.now(timezone.utc).replace(microsecond=0)
    start = end - timedelta(days=DAYS)
    clients = [f"198.51.100.{i}" for i in range(2, 200)]
    lines: list[tuple[datetime, str]] = []

    def at() -> datetime:
        return start + timedelta(seconds=rng.randint(0, DAYS * 86400))

    for e in endpoints:
        if e["id"] in dead:
            continue
        # A long tail: a few endpoints busy, most quiet but alive.
        n = rng.choice([3, 5, 8, 12, 20, 40, 80, 150])
        for _ in range(n):
            ok = 201 if e["method"] == "POST" else 200
            status = ok if rng.random() > 0.06 else rng.choice([400, 401, 404, 500])
            lines.append((t := at(), _line(rng.choice(clients), t, e["method"],
                                           _fill(e["path"], rng), status, "Mozilla/5.0")))
    attacker = "198.51.100.250"
    for eid in sorted(dead):
        method, path = eid.split(" ", 1)
        burst = at()
        for i in range(rng.randint(40, 120)):
            lines.append((t := burst + timedelta(seconds=i * 2),
                          _line(attacker, t, method, _fill(path, rng), 401, "python-requests/2.31")))
    for path, n in (("/api/v1/legacy/statements/export", 60), ("/internal/reports/daily", 25)):
        for _ in range(n):
            lines.append((t := at(), _line(rng.choice(clients[:6]), t, "GET", path, 200, "curl/8.4")))
    for path in ("/wp-login.php", "/.env", "/actuator/env", "/phpmyadmin/index.php"):
        for _ in range(rng.randint(3, 15)):
            lines.append((t := at(), _line("198.51.100.251", t, "GET", path, 404, "zgrab/0.x")))

    lines.sort()
    body = ["# SYNTHETIC access log written by demo/make_access_log.py for a demonstration. "
            "Not real traffic. Addresses are RFC 5737 documentation addresses."]
    body += [s for _, s in lines]
    Path(out).write_text("\n".join(body) + "\n", encoding="utf-8")
    print(f"wrote {len(lines):,} synthetic requests over {DAYS} days to {out}; "
          f"{len(dead)} endpoint(s) left without successful traffic: {', '.join(sorted(dead)) or 'none'}")
    return 0


if __name__ == "__main__":
    if len(sys.argv) != 3:
        print(__doc__)
        raise SystemExit(2)
    raise SystemExit(main(sys.argv[1], sys.argv[2]))
