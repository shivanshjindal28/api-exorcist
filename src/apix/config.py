"""
Runtime configuration, resolved from the environment with sane defaults.

Why this module exists
---------------------
Before packaging, three modules each computed their output directory from
``Path(__file__).parent``. That works for a script run from its own checkout and
is wrong for an installed package: it writes into site-packages, which may be
read-only and is certainly not where a user expects their scan results.

Output now resolves against the *working directory*, which is what a CLI tool
should do, and every value is overridable by environment variable so a container
deployment configures itself without a code change.

No secrets belong here. Credentials for live connectors are read at the point of
use so they never sit in a process-wide singleton.
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path


def _env_path(name: str, default: Path) -> Path:
    raw = os.environ.get(name)
    return Path(raw).expanduser().resolve() if raw else default


def _env_int(name: str, default: int) -> int:
    raw = os.environ.get(name)
    if raw is None:
        return default
    try:
        return int(raw)
    except ValueError:
        raise ValueError(
            f"{name} must be an integer, got {raw!r}"
        ) from None


@dataclass(frozen=True)
class Settings:
    """Resolved configuration for one process."""

    data_dir: Path
    bus_backend: str
    kafka_bootstrap: str
    elastic_url: str
    traffic_window_days: int
    meaningful_traffic_threshold: int

    def ensure_data_dir(self) -> Path:
        self.data_dir.mkdir(parents=True, exist_ok=True)
        return self.data_dir


def load() -> Settings:
    """Read settings from the environment.

    Called at use sites rather than cached at import, so tests and embedded
    callers can change the environment and see it take effect.
    """
    return Settings(
        # Relative to CWD: `apix scan` writes ./data/ where the user is standing.
        data_dir=_env_path("APIX_DATA_DIR", Path.cwd() / "data"),
        bus_backend=os.environ.get("APIX_BUS", "local").lower(),
        kafka_bootstrap=os.environ.get("KAFKA_BOOTSTRAP", "localhost:9092"),
        elastic_url=os.environ.get("ELASTIC_URL", "http://localhost:9200"),
        # The capture window the traffic connector reports over. A genuinely
        # quarterly batch endpoint can look silent inside 30 days; that ambiguity
        # is resolved at the Safe Kill approval gate, not by widening this.
        traffic_window_days=_env_int("APIX_TRAFFIC_WINDOW_DAYS", 30),
        # Calls/day below which an endpoint is not in meaningful use.
        meaningful_traffic_threshold=_env_int("APIX_TRAFFIC_THRESHOLD", 10),
    )
