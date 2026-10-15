"""
A retirement plan for one endpoint: how to turn it off without an outage.

Removing an endpoint is a sequence, not a delete. The plan follows the same
stages Safe Kill runs on the demo bank, written out as changes a team applies
to its own gateway and code:

    1. announce     Deprecation and Sunset response headers (RFC 9745, RFC 8594),
                    so any caller still out there is told, in-band, with a date
    2. observe      keep watching the access logs through the shadow window;
                    any successful call stops the plan
    3. brownout     answer 410 Gone at the gateway, reversibly, for a short
                    window, then for good
    4. remove       delete the handler, the route and the specification entry

Nothing here touches a system. The plan is text a person reviews and applies,
and the gate it depends on is stated in the plan itself.
"""

from __future__ import annotations

import math
import re
from datetime import date, timedelta
from typing import Any

SHADOW_DAYS = 90


def _nginx_location(path: str) -> str:
    if "{" not in path:
        return f"location = {path}"
    pattern = re.sub(r"\\\{[^}]*\\\}", "[^/]+", re.escape(path)).replace("\\/", "/")
    return f"location ~ ^{pattern}$"


def _monthly_window(per_day: float) -> int:
    """Days of silence needed to be 95% sure of seeing a caller at this rate."""
    return math.ceil(math.log(20) / per_day)


def plan(endpoint: dict[str, Any], usage: dict[str, Any] | None,
         today: date | None = None) -> dict[str, Any]:
    today = today or date.today()
    method, path = endpoint["method"], endpoint["path"]
    lifecycle = (usage or {}).get("lifecycle")
    sunset = today + timedelta(days=SHADOW_DAYS)
    http_date = sunset.strftime("%a, %d %b %Y 00:00:00 GMT")

    blockers: list[str] = []
    if usage is None:
        blockers.append("No usage evidence. Import access logs covering at least "
                        f"{SHADOW_DAYS} days before removal; until then this plan stops at "
                        "step 2.")
    elif lifecycle in ("ACTIVE", "ORPHANED", "DEPRECATED"):
        blockers.append(f"The logs show this endpoint in use ({usage.get('ok', 0):,} "
                        "successful requests). Do not remove it"
                        + ("; migrate its callers first." if lifecycle == "DEPRECATED"
                           else "."))
    elif lifecycle == "INDETERMINATE":
        blockers.append(f"The logs cannot decide: {usage.get('reason')}.")
    if not endpoint.get("owner"):
        blockers.append("No owning team is recorded; someone must own the decision "
                        "and the rollback.")

    loc = _nginx_location(path)
    steps = [
        {
            "title": "Announce the retirement in every response",
            "detail": "Callers that read headers learn the date without anyone finding "
                      "them. RFC 9745 (Deprecation) and RFC 8594 (Sunset).",
            "snippet_label": "nginx",
            "snippet": (f"{loc} {{\n"
                        f"    if ($request_method = {method}) {{\n"
                        f"        add_header Deprecation \"@{int(_epoch(today))}\" always;\n"
                        f"        add_header Sunset \"{http_date}\" always;\n"
                        f"    }}\n"
                        f"    proxy_pass http://upstream;\n}}"),
        },
        {
            "title": f"Watch for {SHADOW_DAYS} days",
            "detail": f"Import fresh logs into this scan. {SHADOW_DAYS} silent days give 95% "
                      f"confidence of catching a caller that calls once a month "
                      f"(ln 20 / rate = {_monthly_window(1 / 30)} days). Any successful "
                      "call stops the plan: find that caller first.",
        },
        {
            "title": "Brownout: answer 410 Gone, reversibly",
            "detail": "First for an hour, then a day, then for good. Reverting is one "
                      "line, which is the point: the handler is still deployed.",
            "snippet_label": "nginx",
            "snippet": (f"{loc} {{\n"
                        f"    if ($request_method = {method}) {{\n"
                        f"        return 410 '{{\"error\":\"retired\",\"sunset\":\"{sunset.isoformat()}\"}}';\n"
                        f"    }}\n    proxy_pass http://upstream;\n}}"),
        },
        {
            "title": "Remove the code and the documentation",
            "detail": "Delete the handler and its route, then the specification entry, in "
                      "one change, so CI enforcement (apix enforce) sees neither left behind.",
            "where": ([f"{endpoint['file']}:{endpoint.get('line') or 1}"]
                      if endpoint.get("file") else []),
        },
    ]
    return {
        "endpoint_id": endpoint["id"],
        "ready": not blockers,
        "blockers": blockers,
        "sunset": sunset.isoformat(),
        "steps": steps,
    }


def _epoch(d: date) -> float:
    from datetime import datetime, timezone

    return datetime(d.year, d.month, d.day, tzinfo=timezone.utc).timestamp()
