"""
What changed between two scans of the same project: the API surface's drift.

Zombies are made between scans: a route deleted from the specification while
its handler stays, a debug endpoint merged on a Friday. Comparing each scan
with the previous one of the same target shows those changes as they happen,
which is the evidence an auditor asks for ("show me the inventory is kept").
"""

from __future__ import annotations

from typing import Any


def changes(new: dict[str, Any], old: dict[str, Any]) -> dict[str, Any]:
    a = {e["id"]: e for e in old["report"]["endpoints"]}
    b = {e["id"]: e for e in new["report"]["endpoints"]}
    added = sorted(set(b) - set(a))
    removed = sorted(set(a) - set(b))
    became_undocumented = sorted(i for i in set(a) & set(b)
                                 if a[i].get("documented") and not b[i].get("documented"))
    became_documented = sorted(i for i in set(a) & set(b)
                               if not a[i].get("documented") and b[i].get("documented"))
    new_candidates = sorted(i for i in b if b[i].get("candidate")
                            and not (a.get(i) or {}).get("candidate"))
    resolved_candidates = sorted(i for i in a if a[i].get("candidate")
                                 and not (b.get(i) or {}).get("candidate"))
    was = (old["report"].get("details") or {})
    now = (new["report"].get("details") or {})
    return {
        "previous": {"id": old["id"], "finished_at": old.get("finished_at"),
                     "commit": was.get("commit")},
        # The same commit scanned twice: any difference is the scanner's, not the
        # code's, and must not be read as drift in the project.
        "same_commit": bool(was.get("commit")) and was.get("commit") == now.get("commit"),
        "scanner": {"before": was.get("scanner_version"), "now": now.get("scanner_version")},
        "added": added,
        "added_undocumented": [i for i in added if not b[i].get("documented")],
        "removed": removed,
        "became_undocumented": became_undocumented,
        "became_documented": became_documented,
        "new_candidates": new_candidates,
        "resolved_candidates": resolved_candidates,
        "unchanged": len(set(a) & set(b)),
    }
