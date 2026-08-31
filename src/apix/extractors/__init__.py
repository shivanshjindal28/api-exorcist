"""Route extraction from source code.

Pluggable so the system is not hostage to one tool: Semgrep is the documented
choice and gives multi-language AST matching, but it is a heavy dependency that
not every environment can install. Extractors share one interface so a scan can
fall back without anything downstream noticing.
"""

from apix.extractors.base import ExtractedRoute, RouteExtractor, normalise_path
from apix.extractors.semgrep_extractor import SemgrepExtractor

__all__ = [
    "ExtractedRoute",
    "RouteExtractor",
    "SemgrepExtractor",
    "normalise_path",
]
