"""
Render the design document's Mermaid diagrams to PNG for the Word build.

The Markdown design document is the source of truth: GitHub renders its ```mermaid
fences natively, so the .md needs nothing. Word does not, so the same fences are
extracted and rendered here rather than being redrawn by hand — redrawn diagrams
drift from the ones in the repository, and then two "authoritative" versions of
the architecture exist.

Requires mermaid-cli:
    npx -y @mermaid-js/mermaid-cli@11 -i in.mmd -o out.png

Usage:
    python docs/render_diagrams.py           # render any that are missing
    python docs/render_diagrams.py --force   # re-render everything
"""

from __future__ import annotations

import json
import re
import shutil
import subprocess
import sys
from pathlib import Path

DOCS = Path(__file__).resolve().parent
SOURCE = DOCS / "design-document.md"
OUT = DOCS / "diagrams"

#: Names in the order the fenced blocks appear in design-document.md.
#: build_docx.py pairs these with captions using the same ordering, so the two
#: lists must stay in step. A count mismatch is reported rather than guessed at.
NAMES = [
    "component",
    "classes",
    "deployment",
    "sequence-scan",
    "state-lifecycle",
    "decision-tree",
    "state-safekill",
    "dfd",
    "url-tiers",
]

#: Light background and generous scale: these are embedded in a printed
#: document, so they must stay legible at 6.2 inches wide on paper.
#:
#: fontSize is deliberately large. What determines legibility in print is not
#: the pixel size of the render but the ratio of text height to overall diagram
#: width, because the image is scaled to the page. A bigger font forces Mermaid
#: to allocate more space per node, which raises that ratio. At 15px the dense
#: component diagram came out at roughly 4pt on the page — unreadable.
MERMAID_CONFIG = {
    "theme": "neutral",
    "themeVariables": {
        "fontFamily": "Georgia, 'Times New Roman', serif",
        "fontSize": "20px",
        "primaryColor": "#EFEDE7",
        "primaryTextColor": "#1C1F26",
        "primaryBorderColor": "#8A8477",
        "lineColor": "#5A5E66",
        "secondaryColor": "#DFE8EC",
        "tertiaryColor": "#F7F6F3",
    },
    "flowchart": {"curve": "basis", "padding": 14},
    "sequence": {"actorMargin": 40},
}


def extract_blocks(md: str) -> list[str]:
    return re.findall(r"^```mermaid\n(.*?)^```", md, flags=re.M | re.S)


def find_mmdc() -> list[str] | None:
    """Locate mermaid-cli, preferring a local install over a fresh download."""
    direct = shutil.which("mmdc")
    if direct:
        return [direct]
    npx = shutil.which("npx") or shutil.which("npx.cmd")
    if npx:
        return [npx, "-y", "@mermaid-js/mermaid-cli@11"]
    return None


def main() -> int:
    force = "--force" in sys.argv

    if not SOURCE.exists():
        print(f"  source not found: {SOURCE}")
        return 1

    blocks = extract_blocks(SOURCE.read_text(encoding="utf-8"))
    print(f"  found {len(blocks)} mermaid block(s) in {SOURCE.name}")

    if len(blocks) != len(NAMES):
        print(
            f"  WARNING: {len(blocks)} blocks but {len(NAMES)} names are declared.\n"
            "  Update NAMES here and the captions list in build_docx.py together,\n"
            "  or figures and captions will be mismatched in the Word document."
        )

    OUT.mkdir(parents=True, exist_ok=True)
    cfg = OUT / "mermaid-config.json"
    cfg.write_text(json.dumps(MERMAID_CONFIG, indent=2), encoding="utf-8")

    mmdc = find_mmdc()
    if mmdc is None:
        print("  mermaid-cli not available and npx not found.")
        print("  Install Node.js, then re-run. The .md renders on GitHub regardless.")
        return 1

    rendered = failed = skipped = 0
    for i, block in enumerate(blocks):
        name = NAMES[i] if i < len(NAMES) else f"diagram-{i + 1}"
        png = OUT / f"{name}.png"
        mmd = OUT / f"{name}.mmd"
        mmd.write_text(block, encoding="utf-8")

        if png.exists() and not force:
            skipped += 1
            continue

        cmd = [
            *mmdc,
            "-i", str(mmd),
            "-o", str(png),
            "-c", str(cfg),
            "-b", "white",
            "-s", "3",            # 3x scale so text stays sharp in print
        ]
        try:
            proc = subprocess.run(
                cmd, capture_output=True, text=True, timeout=180
            )
        except subprocess.TimeoutExpired:
            print(f"  TIMEOUT  {name}")
            failed += 1
            continue

        if proc.returncode == 0 and png.exists():
            kb = round(png.stat().st_size / 1024, 1)
            print(f"  rendered {name}.png  ({kb} KB)")
            rendered += 1
        else:
            tail = (proc.stderr or proc.stdout or "").strip().splitlines()
            print(f"  FAILED   {name}: {tail[-1] if tail else 'unknown error'}")
            failed += 1

    print(f"\n  {rendered} rendered, {skipped} already present, {failed} failed")
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
