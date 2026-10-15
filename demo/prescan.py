"""Scan GitHub repositories ahead of the presentation, the same way the app does.

    python demo/prescan.py OWASP/crAPI erev0s/VAmPI

Each scan runs through the app's own JobManager and is stored in data/scans, so
it appears under "All scans" in the browser exactly as if it had been started
there. If the room's network fails, these finished reports are the fallback.
Nothing from a scanned repository is executed.
"""

from __future__ import annotations

import sys
import time
from pathlib import Path

from apix.config import load as load_settings
from apix.scanning.jobs import JobManager


def main(slugs: list[str]) -> int:
    store = load_settings().ensure_data_dir() / "scans"
    jobs = JobManager(store=Path(store))
    failed = 0
    try:
        for slug in slugs:
            job = jobs.submit_github(slug, "prepare")
            started = time.monotonic()
            while True:
                d = jobs.get(job["id"]) or {}
                if d.get("status") in ("done", "failed"):
                    break
                time.sleep(2)
            took = time.monotonic() - started
            if d["status"] == "failed":
                failed += 1
                print(f"  FAILED  {slug}: {d.get('error')}")
                continue
            report = d["report"]
            cands = report.get("candidates", [])
            likely = sum(1 for c in cands if c.get("label") == "Likely zombie")
            print(f"  done    {slug}: {len(report.get('endpoints', []))} endpoints, "
                  f"{len(cands)} candidates ({likely} likely), {took:.0f}s")
    finally:
        jobs.shutdown()
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:] or ["OWASP/crAPI"]))
