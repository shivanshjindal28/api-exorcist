"""Live scanning of real systems, as opposed to the simulated estate.

Currently: GitHub repositories. The connectors here emit the same
`DiscoverySignal` contract as the simulated ones, so everything downstream —
correlation, classification, explanation — runs unchanged.
"""

from apix.live.repo import RepoError, RepoScan
from apix.live.scan import RepoScanResult, scan_repository

__all__ = ["RepoError", "RepoScan", "RepoScanResult", "scan_repository"]
