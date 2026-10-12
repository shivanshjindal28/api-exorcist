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

#: docs/interim-report.md is deliberately absent. It is the Review 2 submission,
#: a dated snapshot of the system at the 50% mark ("85 tests", Safe Kill out of
#: scope), and updating its figures would make it disagree with itself and with
#: the copy the panel holds. Phase 4 onward belongs in the final report.
DOCS = [
    ROOT / "README.md",
    ROOT / "CLAUDE.md",
    ROOT / "docs" / "design-document.md",
    ROOT / "docs" / "literature-review.md",
    ROOT / "demo" / "DEMO.md",
]


#: Prose spells small numbers out. A claim written "nine services" is exactly
#: as much a claim as "9 services", and an unmatched pattern is an unchecked
#: figure -- which is how three of the drifts above survived review.
WORD_NUMBERS = {
    w: n for n, w in enumerate(
        ["zero", "one", "two", "three", "four", "five", "six", "seven", "eight", "nine", "ten", "eleven", "twelve", "thirteen", "fourteen", "fifteen", "sixteen", "seventeen", "eighteen", "nineteen", "twenty"]
    )
}
NUM = r"(\d+|" + "|".join(WORD_NUMBERS) + r")"


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
            value = WORD_NUMBERS.get(raw.lower())
            out.append((m.group(0).strip(),
                        float(value if value is not None else float(raw))))
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
    blast = _blast_radius_of("GET /v2/accounts/{id}")
    return {
        "blast_services": blast[0],
        "blast_hops": blast[1],
        "blast_callers": blast[2],
        "blast_endpoints": blast[3],
        "endpoints": float(len(ESTATE)),
        "rules": float(len(RULES)),
        "flags": float(n_flags),
        "features": float(len(FEATURE_NAMES)),
        "zombies": float(counts.get("ZOMBIE", 0)),
        "deprecated": float(counts.get("DEPRECATED", 0)),
        "connectors": 6.0,
        "tests": float(_count_tests()),
        "vitest": float(_count_vitest()),
        **_safekill_figures(),
    }


def _safekill_figures() -> dict[str, float]:
    """The Safe Kill numbers the README and design document quote.

    Two evaluations: the default policy, and the canary-only design as
    originally drawn, whose costs are the argument for the shadow stage.
    """
    from apix.evaluation.safekill_eval import evaluate
    from apix.safekill import KillState, SafeKillPolicy

    default = evaluate(120)
    canary_only = evaluate(120, policy=SafeKillPolicy(shadow_days_override=0))
    return {
        "sk_live": float(default.live.n),
        "sk_outages": float(default.safekill_outages),
        "sk_canary_dead_kept": float(canary_only.dead.count(KillState.ROLLED_BACK)),
        "sk_canary_refused": float(canary_only.live.genuine_refused),
        "sk_canary_noise": float(canary_only.live.rollback_by.get("anonymous", 0)),
    }


def _blast_radius_of(endpoint_id: str) -> tuple[float, float, float, float]:
    """(services, hops, direct callers, endpoints) for one endpoint.

    Every document narrates this same endpoint as the worked example of why a
    single-hop inventory is not enough, so the four numbers are claims about
    the system and are checked like any other.
    """
    from apix.graph import build_graph
    from apix.pipeline import run_discovery

    records = run_discovery(verbose=False)
    radius = build_graph(records).blast_radius(endpoint_id)
    services = set(radius.direct_services) | set(radius.indirect_services)
    return (
        float(len(services)),
        float(radius.depth_reached),
        float(len(radius.direct_services)),
        float(len(radius.affected_endpoints)),
    )


def _count_vitest() -> int:
    """Dashboard tests, counted from source: every `it(` in a test file.

    Counted rather than run, so this script needs no Node. The README and
    CLAUDE.md quote it, and a count that was only ever typed in by hand drifts.
    """
    total = 0
    for path in (ROOT / "dashboard" / "src").rglob("*.test.ts*"):
        total += len(re.findall(r"^\s*it\(", path.read_text(encoding="utf-8"), re.M))
    return total


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
        Claim("discrepancy flags", r"(\d+) (?:discrepancy )?flags", live["flags"]),
        Claim("observable features", r"(\d+) (?:observable )?features", live["features"]),
        Claim("estate size", r"(\d+)-endpoint estate", live["endpoints"]),
        Claim("zombie count", r"(?:all )?(\d+) zombies are isolated", live["zombies"]),
        Claim("zombies of total", r"\d+ of (\d+) zombies", live["zombies"]),
        Claim("deprecated count", r"all (\d+) deprecated endpoints", live["deprecated"]),
        # The worked blast-radius example, spelled in digits or in words.
        Claim("blast services", NUM + r"\**,? services\**,? (?:across|affected)",
              live["blast_services"]),
        Claim("blast hops", NUM + r" hops? deep", live["blast_hops"]),
        Claim("blast hops (across)", NUM + r"\**\s*hops\b", live["blast_hops"]),
        Claim("blast callers", NUM + r" direct callers", live["blast_callers"]),
        # The demo script wraps this claim across a blockquote line break, so
        # the pattern has to tolerate a newline and a "> " continuation.
        Claim("blast endpoints", NUM + r"\**\s+endpoints[\s>]*degraded",
              live["blast_endpoints"]),
        # Two digits or more: a single-digit "6 Tests" is a step number in the
        # demo timing table, not a claim about the suite.
        Claim("test count", r"(\d{2,}) tests\b", live["tests"]),
        Claim("dashboard test count", r"(\d+) Vitest\s+tests", live["vitest"]),
        # Safe Kill. The gate's mistakes, and what the canary-only design costs.
        Claim("safekill live candidates", r"(\d+) live endpoints", live["sk_live"]),
        Claim("canary-only dead kept", r"keeps (\d+) dead endpoints",
              live["sk_canary_dead_kept"]),
        Claim("canary-only real requests refused", r"refuses (\d+) real\s+requests",
              live["sk_canary_refused"]),
        Claim("canary-only noise catches", r"(\d+) of its \d+ catches",
              live["sk_canary_noise"]),
        # Every live candidate is a canary-only catch: no shadow, nothing missed.
        Claim("canary-only catches", r"\d+ of its (\d+) catches", live["sk_live"]),
    ]


#: Capability -> (file that exists iff it is built, phrases that describe it).
#:
#: Checked in BOTH directions. If the module exists, no document may mark that
#: capability as not-built; if it does not exist, no document may mark it done.
#: The first version of this script checked only numbers, and a README table
#: sat on the repository landing page saying "SHAP over a trained model ⬜"
#: after SHAP had shipped — the most visible line in the project, and the
#: numeric checks could not see it.
CAPABILITIES: dict[str, tuple[str, list[str]]] = {
    "SHAP / model layer": (
        "src/apix/engine/model.py",
        [r"SHAP", r"trained model", r"learned model", r"model layer"],
    ),
    "dependency graph": (
        "src/apix/graph/build.py",
        [r"dependency graph", r"blast radius", r"removal gate"],
    ),
    "live repository scanning": (
        "src/apix/live/scan.py",
        [r"GitHub repository scanning", r"Semgrep AST", r"repository scanning"],
    ),
    "estate generator": (
        "src/apix/simulated_env/generator.py",
        [r"estate generator", r"parameterised generation", r"generated estates"],
    ),
    "Safe Kill": (
        "src/apix/safekill/__init__.py",
        [r"Safe Kill Simulation"],
    ),
    # Split in Phase 5: the API shipped before the dashboard, and one entry
    # for both would have demanded the unbuilt half be marked done.
    "REST API": (
        "src/apix/api/app.py",
        [r"\bREST API\b(?! and dashboard)"],
    ),
    "dashboard": (
        "src/apix/api/dashboard/index.html",
        [r"\bdashboard\b"],
    ),
    "CI/CD enforcement": (
        "src/apix/enforce/__init__.py",
        [r"CI/CD enforcement"],
    ),
    "container image": (
        "Dockerfile",
        [r"container image"],
    ),
    "observability": (
        "src/apix/api/observe.py",
        [r"\bobservability\b"],
    ),
    "browser scans": (
        "src/apix/scanning/jobs.py",
        [r"Browser scans"],
    ),
    # Shown in the app as unavailable. If this module ever exists, documents
    # marking it unbuilt fail; until then, any marking it done fails.
    "live website scanning": (
        "src/apix/webscan/__init__.py",
        [r"Live website scanning"],
    ),
}

_NOT_BUILT = ("⬜", "🔵")
_BUILT = "✅"


def check_patterns_are_live(claims: list[Claim]) -> list[str]:
    """Every claim and every capability phrase must match something.

    A pattern that matches no document line reports "consistent" forever,
    because there is nothing for it to disagree with. That is how three
    patterns ran for weeks checking nothing: a shell had turned their `\\b`
    into a literal backspace byte (0x08), invisible in an editor, and the
    script kept printing "all consistent". This check makes a dead pattern a
    failure, and refuses control characters in this file outright.
    """
    problems: list[str] = []
    own = Path(__file__).read_text(encoding="utf-8")
    for lineno, line in enumerate(own.splitlines(), 1):
        if any(ord(c) < 32 and c != "\t" for c in line):
            problems.append(f"verify_claims.py:{lineno}: control character in source")

    texts = [d.read_text(encoding="utf-8") for d in DOCS if d.exists()]
    for claim in claims:
        if not any(claim.matches(t) for t in texts):
            problems.append(f"claim {claim.name!r} matches no document: dead pattern")
    for label, (_, phrases) in CAPABILITIES.items():
        for phrase in phrases:
            if not any(re.search(phrase, t, re.I) for t in texts):
                problems.append(
                    f"capability {label!r}: phrase {phrase!r} matches no document"
                )
    return problems


def check_status_markers() -> list[str]:
    """A status marker is a claim too, and drifts exactly like a number does."""
    problems: list[str] = []

    for label, (path, phrases) in CAPABILITIES.items():
        built = (ROOT / path).exists()
        combined = re.compile("|".join(phrases), re.I)

        for doc in DOCS:
            if not doc.exists():
                continue
            rel = doc.relative_to(ROOT)
            for lineno, line in enumerate(
                doc.read_text(encoding="utf-8").splitlines(), 1
            ):
                if not combined.search(line):
                    continue
                # Only table rows and headings carry a status marker; prose
                # mentioning a capability is not making a claim about it.
                if not (line.lstrip().startswith(("|", "#")) or "—" in line[:4]):
                    continue

                if built and any(m in line for m in _NOT_BUILT):
                    problems.append(
                        f"{rel}:{lineno}: {label} IS built ({path} exists) but "
                        f"this line marks it unbuilt — {line.strip()[:70]}"
                    )
                elif not built and _BUILT in line:
                    problems.append(
                        f"{rel}:{lineno}: {label} is NOT built ({path} missing) "
                        f"but this line marks it done — {line.strip()[:70]}"
                    )
    return problems


#: Architecture-diagram node -> the file that exists exactly when it is built.
#:
#: The component diagram colours each box done or todo with a mermaid `class`
#: line, and that diagram is the most-shown picture in the project: it is on a
#: review slide. After Phase 4 and Phase 5 shipped it still drew Safe Kill, the
#: audit log, the API and the dashboard as unbuilt, because every other check
#: here reads tables and headings, not diagram colours.
DIAGRAM_NODES: dict[str, str] = {
    "GRAPH": "src/apix/graph/build.py",
    "BLAST": "src/apix/graph/build.py",
    "ML": "src/apix/engine/model.py",
    "GATE": "src/apix/safekill/__init__.py",
    "KILL": "src/apix/safekill/__init__.py",
    "AUDIT": "src/apix/safekill/audit.py",
    "API": "src/apix/api/app.py",
    "UI": "src/apix/api/dashboard/index.html",
    "ENF": "src/apix/enforce/__init__.py",
}


def check_diagram_status() -> list[str]:
    """Diagram colours are status claims too; check them against the code."""
    design = (ROOT / "docs" / "design-document.md").read_text(encoding="utf-8")
    # Node ids are local to each diagram: the model-veto figure has its own
    # GATE, and reading the whole document let its status overwrite this one's.
    blocks = re.findall(r"^```mermaid\n(.*?)^```", design, re.M | re.S)
    component = next((b for b in blocks if "Layer 5" in b), "")
    if not component:
        return ["design-document.md: component diagram (Layer 5) not found"]
    status: dict[str, str] = {}
    for m in re.finditer(
        r"^\s*class ([A-Z0-9_,]+) (done|wip|todo)\s*$", component, re.M
    ):
        for node in m.group(1).split(","):
            status[node] = m.group(2)

    problems: list[str] = []
    for node, path in DIAGRAM_NODES.items():
        if node not in status:
            problems.append(f"design-document.md: diagram node {node} has no status class")
            continue
        built = (ROOT / path).exists()
        if built and status[node] != "done":
            problems.append(
                f"design-document.md: diagram draws {node} as {status[node]}, "
                f"but it is built ({path} exists)"
            )
        elif not built and status[node] == "done":
            problems.append(
                f"design-document.md: diagram draws {node} as done, "
                f"but {path} does not exist"
            )
    return problems


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
    # The failure report quotes document lines, and those carry status markers
    # such as ⬜. A Windows console defaults to cp1252, which cannot encode them,
    # so the script used to crash with UnicodeEncodeError at exactly the moment
    # it had a mismatch to report, and only ever completed when everything
    # passed. A check that dies on its own failure path is not a check.
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")

    live = live_values()
    claims = build_claims(live)

    print("Verifying documented figures against the running code\n")
    print("  live values:")
    for k, v in sorted(live.items()):
        print(f"    {k:<24} {v:g}")
    print()

    failures: list[str] = (
        check_patterns_are_live(claims)
        + check_diagram_status()
        + check_diagram_lists()
        + check_status_markers()
    )
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
