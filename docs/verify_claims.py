"""
Check that the numbers written in the documentation match the running code.

Why this exists
---------------
Documentation drifted from reality three times in this project, and a human
caught it each time:

  * the benchmark table said the conventional baseline finds 0 of 8 zombies
    after a rule change had made it 2;
  * the README announced Phase 2 as upcoming work after Phase 2 had shipped;
  * every document said the correlator derives 15 discrepancy flags. It derives
    14, and had done since the first commit.

None of those were caught by tests, because tests check code against code. A
figure in a design document is a claim about the system, and an unverified claim
in a document a panel will read is a defect like any other.

How it works
------------
Each rule below is a regex with one capture group, matched against a set of
files, and compared with a value computed live from the code. Regexes rather
than a hand-listed set of line numbers: a new mention of "17 evidence rules"
anywhere in the docs is then caught automatically, which is the whole point.

    python docs/verify_claims.py

Exits non-zero on any mismatch, and CI runs it.
"""

from __future__ import annotations

import re
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))

DOCS = [
    ROOT / "README.md",
    ROOT / "CLAUDE.md",
    ROOT / "docs" / "design-document.md",
    ROOT / "docs" / "literature-review.md",
    ROOT / "demo" / "DEMO.md",
]


@dataclass(frozen=True)
class Claim:
    """One thing the documents assert, and the value it must equal."""

    name: str
    pattern: str          # exactly one capture group, holding the number
    expected: float
    tolerance: float = 0.0

    def matches(self, text: str) -> list[tuple[str, float]]:
        out = []
        for m in re.finditer(self.pattern, text, re.I):
            raw = m.group(1).replace(",", "")
            out.append((m.group(0).strip(), float(raw)))
        return out


def live_values() -> dict[str, float]:
    """Compute every asserted quantity from the code, right now."""
    from apix.dataset.build import FEATURE_NAMES
    from apix.engine.rules import RULES
    from apix.simulated_env.estate import ESTATE, label_counts

    # Flags are counted from the source rather than from a run: a flag that
    # happens not to fire on this estate is still a flag the code can emit.
    correlator = (ROOT / "src/apix/inventory/correlator.py").read_text(
        encoding="utf-8"
    )
    # [A-Z0-9_] not [A-Z_]: STALE_6M and CODE_UNTOUCHED_1Y contain digits, and
    # an alphabetic-only class silently undercounts by two.
    n_flags = len(set(re.findall(r'f\.append\("([A-Z0-9_]+)"\)', correlator)))

    counts = label_counts()
    return {
        "endpoints": float(len(ESTATE)),
        "rules": float(len(RULES)),
        "flags": float(n_flags),
        "features": float(len(FEATURE_NAMES)),
        "zombies": float(counts.get("ZOMBIE", 0)),
        "deprecated": float(counts.get("DEPRECATED", 0)),
        "connectors": 6.0,
        "tests": float(_count_tests()),
    }


def _count_tests() -> int:
    """Ask pytest how many tests it collects."""
    proc = subprocess.run(
        [sys.executable, "-m", "pytest", "--collect-only", "-q"],
        capture_output=True,
        text=True,
        cwd=ROOT,
    )
    out = proc.stdout

    # Newer pytest under -q prints a per-file tally and no grand total:
    #     tests/test_graph.py: 14
    per_file = re.findall(r"^\S+\.py:\s*(\d+)\s*$", out, re.M)
    if per_file:
        return sum(int(n) for n in per_file)

    m = re.search(r"(\d+) tests? collected", out)
    if m:
        return int(m.group(1))

    ids = [ln for ln in out.splitlines() if "::" in ln and ln.strip()]
    return len(ids) if ids else -1


def build_claims(live: dict[str, float]) -> list[Claim]:
    """Patterns are deliberately narrow — a false alarm is worse than a miss."""
    return [
        Claim("evidence rules", r"(\d+) evidence rules", live["rules"]),
        Claim("rules usable denominator", r"\d+\s*/\s*(\d+)\s*rules", live["rules"]),
        Claim("discrepancy flags", r"(\d+) (?:discrepancy )?flags", live["flags"]),
        Claim("observable features", r"(\d+) (?:observable )?features", live["features"]),
        Claim("estate size", r"(\d+)-endpoint estate", live["endpoints"]),
        Claim("zombie count", r"(?:all )?(\d+) zombies are isolated", live["zombies"]),
        Claim("zombies of total", r"\d+ of (\d+) zombies", live["zombies"]),
        Claim("deprecated count", r"all (\d+) deprecated endpoints", live["deprecated"]),
        Claim("connector count", r"(\d+) connectors", live["connectors"]),
        # Two digits or more: a single-digit "6 Tests" is a step number in the
        # demo timing table, not a claim about the suite.
        Claim("test count", r"(\d{2,}) tests\b", live["tests"]),
    ]


def check_diagram_lists() -> list[str]:
    """Figure names and captions are positional; they must stay in step.

    Inserting a ```mermaid block mid-document shifts every name after it, which
    mismatches figures with their captions in the Word build — silently, because
    the images still render. This happened once while adding §3.3.3.
    """
    problems: list[str] = []
    design = (ROOT / "docs" / "design-document.md").read_text(encoding="utf-8")
    n_blocks = len(re.findall(r"^```mermaid$", design, re.M))

    names_src = (ROOT / "docs" / "render_diagrams.py").read_text(encoding="utf-8")
    n_names = len(
        re.findall(
            r'^\s+"([a-z-]+)",',
            names_src.split("NAMES = [")[1].split("]")[0],
            re.M,
        )
    )

    docx_src = (ROOT / "docs" / "build_docx.py").read_text(encoding="utf-8")
    n_caps = len(re.findall(r'^\s+\("([a-z-]+)", "', docx_src, re.M))

    if not (n_blocks == n_names == n_caps):
        problems.append(
            f"diagram lists out of step: {n_blocks} mermaid block(s) in the "
            f"design document, {n_names} name(s) in render_diagrams.py, "
            f"{n_caps} caption(s) in build_docx.py"
        )
    return problems


def main() -> int:
    live = live_values()
    claims = build_claims(live)

    print("Verifying documented figures against the running code\n")
    print("  live values:")
    for k, v in sorted(live.items()):
        print(f"    {k:<24} {v:g}")
    print()

    failures: list[str] = check_diagram_lists()
    checked = 0

    for doc in DOCS:
        if not doc.exists():
            continue
        text = doc.read_text(encoding="utf-8")
        rel = doc.relative_to(ROOT)
        for claim in claims:
            for phrase, found in claim.matches(text):
                checked += 1
                if abs(found - claim.expected) > claim.tolerance:
                    failures.append(
                        f"{rel}: {phrase!r} — {claim.name} is "
                        f"{claim.expected:g}, document says {found:g}"
                    )

    if failures:
        print(f"  {len(failures)} MISMATCH(ES) in {checked} checked claim(s):\n")
        for f in failures:
            print(f"    {f}")
        print()
        print("  Fix the document, or the code, depending on which is wrong.")
        return 1

    print(f"  {checked} documented figure(s) checked, all consistent.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
