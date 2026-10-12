"""
CI/CD enforcement (Phase 6): the prevention half.

Detection and Safe Kill deal with zombies that already exist. Enforcement stops
new ones being made: it runs on a pull request and fails it if the change adds
an endpoint that is undocumented or unowned, or removes an endpoint from the
specification while leaving its handler in place, which is exactly how a zombie
is born.

    config.py    rules, severities and reasoned exemptions, from .apix.yml
    snapshot.py  one commit's API surface: routes, spec entries, owners
    check.py     the four rules, applied only to what the change touches
    runner.py    merge base, temporary worktree, the two snapshots
    report.py    text, JSON, and GitHub annotations with a run summary

Run as `apix enforce --base origin/main`, or through the composite action in
`action.yml` at the repository root.
"""

from apix.enforce.check import Comparison, Finding, compare
from apix.enforce.config import EnforceConfig, EnforceConfigError
from apix.enforce.runner import EnforceError, EnforceResult, run_enforcement
from apix.enforce.snapshot import Snapshot, take_snapshot

__all__ = [
    "Comparison",
    "EnforceConfig",
    "EnforceConfigError",
    "EnforceError",
    "EnforceResult",
    "Finding",
    "Snapshot",
    "compare",
    "run_enforcement",
    "take_snapshot",
]
