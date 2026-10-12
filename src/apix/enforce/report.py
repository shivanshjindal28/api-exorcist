"""
Enforcement output: for a person, for a machine, and for GitHub.

GitHub format writes workflow commands, so each finding appears as an
annotation on the exact line of the pull request that introduced it, and a
Markdown summary on the run's page. Messages are escaped as the workflow-command
syntax requires: an endpoint path containing a newline or a `%` must not be able
to end the annotation early and inject a command of its own.
"""

from __future__ import annotations

import json
import os
import secrets
from pathlib import Path

from apix.enforce.config import CONFIG_FILE
from apix.enforce.runner import EnforceResult

POLICY_NOTE = (
    "this change edits .apix.yml. The edit is not applied to this check: a "
    "change cannot exempt itself. It takes effect once merged."
)

_RULE_TITLE = {
    "new-endpoint-undocumented": "Undocumented endpoint",
    "new-endpoint-unowned": "Unowned endpoint",
    "spec-removed-handler-kept": "Zombie in the making",
    "spec-without-handler": "Documented, not implemented",
}


def as_text(r: EnforceResult) -> str:
    c = r.comparison
    lines = [
        "",
        "=" * 74,
        "API EXORCIST ENFORCEMENT: what this change does to the API surface",
        "=" * 74,
        "",
        f"  compared with   : {r.base_ref} (merge base {r.base_commit[:10]})",
        f"  configuration   : {r.config.source}",
        f"  specifications  : {', '.join(r.head.spec_files) or 'none found'}",
        f"  endpoints added : {len(c.added)}",
        f"  endpoints gone  : {len(c.removed)}",
        "",
        "  Only this change is judged. Endpoints that already existed are never",
        "  held against it, and no endpoint is called dead: a code change carries",
        "  no evidence about traffic.",
        "",
    ]
    for f in c.findings:
        where = f"{f.file}:{f.line}" if f.file and f.line else (f.file or "")
        lines.append(f"  [{f.severity.upper():<5}] {_RULE_TITLE.get(f.rule, f.rule)}")
        lines.append(f"          {f.message}")
        if where:
            lines.append(f"          at {where}")
        lines.append("")
    for eid, rule in c.exempted:
        lines.append(f"  [ALLOW] {eid}: {rule.reason}")
    if c.exempted:
        lines.append("")
    for err in r.head.spec_errors:
        lines.append(f"  [NOTE ] specification not parsed: {err}")
    if r.policy_changed:
        lines.append(f"  [NOTE ] {POLICY_NOTE}")
    verdict = (
        "PASS: nothing this change adds is undocumented, unowned, or orphaned."
        if c.passed and not c.warnings
        else f"PASS with {len(c.warnings)} warning(s)."
        if c.passed
        else f"FAIL: {len(c.errors)} error(s), {len(c.warnings)} warning(s)."
    )
    lines += [f"  {verdict}", ""]
    return "\n".join(lines)


def as_json(r: EnforceResult) -> str:
    c = r.comparison
    return json.dumps({
        "base_ref": r.base_ref,
        "base_commit": r.base_commit,
        "config": r.config.source,
        "policy_changed": r.policy_changed,
        "passed": c.passed,
        "added": c.added,
        "removed": c.removed,
        "findings": [f.to_dict() for f in c.findings],
        "exempted": [{"endpoint_id": e, "reason": a.reason} for e, a in c.exempted],
        "spec_files": r.head.spec_files,
        "spec_errors": r.head.spec_errors,
    }, indent=2)


def _escape_data(s: str) -> str:
    return s.replace("%", "%25").replace("\r", "%0D").replace("\n", "%0A")


def _escape_property(s: str) -> str:
    return _escape_data(s).replace(":", "%3A").replace(",", "%2C")


def as_github(r: EnforceResult) -> str:
    """Workflow commands, one annotation per finding; also writes the summary."""
    out = []
    for f in r.comparison.findings:
        level = "error" if f.severity == "error" else "warning"
        props = [f"title={_escape_property(_RULE_TITLE.get(f.rule, f.rule))}"]
        if f.file:
            props.insert(0, f"file={_escape_property(f.file)}")
            if f.line:
                props.insert(1, f"line={f.line}")
        out.append(f"::{level} {','.join(props)}::{_escape_data(f.message)}")
    if r.policy_changed:
        out.append(
            f"::notice file={CONFIG_FILE},title=Policy edit not applied::"
            f"{_escape_data(POLICY_NOTE)}"
        )
    summary_path = os.environ.get("GITHUB_STEP_SUMMARY")
    if summary_path:
        with Path(summary_path).open("a", encoding="utf-8") as fh:
            fh.write(as_markdown(r))
    # The readable report goes into the same log, and GitHub parses any log
    # line beginning with "::" as a workflow command. Route strings come from
    # the pull request, whose author is untrusted in CI, so a path containing
    # "\n::error::..." printed here would forge an annotation; this was found
    # by test_github_annotations_cannot_be_injected. stop-commands, with a
    # token the author cannot predict, disables command parsing for the block.
    token = secrets.token_hex(16)
    out.append(f"::stop-commands::{token}")
    out.append(as_text(r))
    out.append(f"::{token}::")
    return "\n".join(out)


def _md(s: str) -> str:
    """Keep untrusted text inside its table cell and code span."""
    return (
        s.replace("\r", " ").replace("\n", " ").replace("|", "\\|").replace("`", "'")
    )


def as_markdown(r: EnforceResult) -> str:
    c = r.comparison
    head = "Passed" if c.passed else "Failed"
    md = [
        f"## API Exorcist enforcement: {head}",
        "",
        f"Compared with `{r.base_ref}` (merge base `{r.base_commit[:10]}`): "
        f"{len(c.added)} endpoint(s) added, {len(c.removed)} removed.",
        "",
    ]
    if c.findings:
        md += ["| Severity | Rule | Endpoint | Where |", "|---|---|---|---|"]
        for f in c.findings:
            where = (
                f"`{_md(f.file)}:{f.line}`" if f.file and f.line
                else (f"`{_md(f.file)}`" if f.file else "")
            )
            md.append(
                f"| {f.severity} | {_RULE_TITLE.get(f.rule, f.rule)} | "
                f"`{_md(f.endpoint_id)}` | {where} |"
            )
        md.append("")
    if c.exempted:
        md += ["Exempt by configuration:", ""]
        md += [f"- `{_md(e)}`: {_md(a.reason)}" for e, a in c.exempted]
        md.append("")
    if r.policy_changed:
        md += [f"**Note:** {POLICY_NOTE}", ""]
    md.append("Only this change is judged; endpoints that already existed are not.")
    md.append("")
    return "\n".join(md)
