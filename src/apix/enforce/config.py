"""
Enforcement policy: which rules apply, how severely, and what is exempt.

Read from `.apix.yml` at the repository root. With no file, every rule runs at
its default severity, so adopting enforcement needs no configuration at all.

    enforce:
      rules:
        new-endpoint-undocumented: error     # error | warn | off
        new-endpoint-unowned: error
        spec-removed-handler-kept: error
        spec-without-handler: warn
      allow:
        - endpoint: "GET /health*"
          reason: "liveness probe; infrastructure, not an API"

Every exemption must carry a reason. An allow-list entry with no reason is a
configuration error, because "someone silenced the check" is exactly the kind
of decision an auditor later needs explained.
"""

from __future__ import annotations

import fnmatch
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

UNDOCUMENTED = "new-endpoint-undocumented"
UNOWNED = "new-endpoint-unowned"
HANDLER_KEPT = "spec-removed-handler-kept"
SPEC_WITHOUT_HANDLER = "spec-without-handler"

#: Defaults. The last is a warning because route extraction can miss a
#: framework, and a check that fails on its own blind spot gets switched off.
DEFAULT_SEVERITY: dict[str, str] = {
    UNDOCUMENTED: "error",
    UNOWNED: "error",
    HANDLER_KEPT: "error",
    SPEC_WITHOUT_HANDLER: "warn",
}
SEVERITIES = ("error", "warn", "off")
CONFIG_FILE = ".apix.yml"


class EnforceConfigError(ValueError):
    """The configuration is malformed. Reported before anything is checked."""


@dataclass(frozen=True)
class AllowRule:
    pattern: str
    reason: str

    def matches(self, endpoint_id: str) -> bool:
        return fnmatch.fnmatchcase(endpoint_id, self.pattern)


@dataclass(frozen=True)
class EnforceConfig:
    severity: dict[str, str] = field(default_factory=lambda: dict(DEFAULT_SEVERITY))
    allow: tuple[AllowRule, ...] = ()
    source: str = "defaults"

    def allowed_by(self, endpoint_id: str) -> AllowRule | None:
        return next((a for a in self.allow if a.matches(endpoint_id)), None)

    @classmethod
    def load(cls, repo_root: Path, path: Path | None = None) -> EnforceConfig:
        cfg_path = path or (repo_root / CONFIG_FILE)
        if not cfg_path.exists():
            if path is not None:
                raise EnforceConfigError(f"no configuration file at {cfg_path}")
            return cls()
        try:
            import yaml
        except ImportError:
            raise EnforceConfigError(
                f'{cfg_path.name} needs PyYAML: pip install -e ".[live]"'
            ) from None
        try:
            doc = yaml.safe_load(cfg_path.read_text(encoding="utf-8")) or {}
        except yaml.YAMLError as exc:
            raise EnforceConfigError(f"{cfg_path.name} is not valid YAML: {exc}") from None
        return cls.from_dict(doc, source=str(cfg_path))

    @classmethod
    def from_dict(cls, doc: Any, *, source: str = "inline") -> EnforceConfig:
        if not isinstance(doc, dict):
            raise EnforceConfigError("configuration must be a mapping")
        section = doc.get("enforce") or {}
        if not isinstance(section, dict):
            raise EnforceConfigError("'enforce' must be a mapping")
        unknown = set(section) - {"rules", "allow"}
        if unknown:
            raise EnforceConfigError(f"unknown 'enforce' keys: {sorted(unknown)}")

        severity = dict(DEFAULT_SEVERITY)
        for rule, level in (section.get("rules") or {}).items():
            if rule not in DEFAULT_SEVERITY:
                raise EnforceConfigError(
                    f"unknown rule {rule!r}; known rules: {sorted(DEFAULT_SEVERITY)}"
                )
            if level not in SEVERITIES:
                raise EnforceConfigError(
                    f"{rule}: severity must be one of {SEVERITIES}, got {level!r}"
                )
            severity[rule] = level

        allow: list[AllowRule] = []
        for i, entry in enumerate(section.get("allow") or []):
            if not isinstance(entry, dict):
                raise EnforceConfigError(f"allow[{i}] must be a mapping")
            pattern = str(entry.get("endpoint") or "").strip()
            reason = str(entry.get("reason") or "").strip()
            if not pattern:
                raise EnforceConfigError(f"allow[{i}] needs an 'endpoint' pattern")
            if not reason:
                raise EnforceConfigError(
                    f"allow[{i}] ({pattern}) needs a 'reason': every exemption "
                    "must say why"
                )
            allow.append(AllowRule(pattern, reason))
        return cls(severity=severity, allow=tuple(allow), source=source)
