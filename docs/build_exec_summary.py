"""
Generate the executive summary required with the final submission:
Group_4_Capstone_exe_summary.docx, with the four sections the guidelines ask
for (introduction and problem statement, methodology, key findings and results,
project value and impact).

Every figure is one the final report states and docs/verify_claims.py checks
against the code. Usage:

    python docs/build_exec_summary.py
"""

from __future__ import annotations

from pathlib import Path

from docx import Document
from docx.enum.table import WD_TABLE_ALIGNMENT
from docx.enum.text import WD_ALIGN_PARAGRAPH
from docx.shared import Cm, Pt, RGBColor
from PIL import Image

DOCS = Path(__file__).resolve().parent
OUT_DIR = DOCS / "deliverables"
OUTPUT = OUT_DIR / "Group_4_Capstone_exe_summary.docx"
LOGO = DOCS / "assets" / "logo.png"
TEMPLATE = DOCS / "assets" / "mpstme-template.jpg"

RED = RGBColor(0xBC, 0x31, 0x2C)
INK = RGBColor(0x1C, 0x1F, 0x26)
MUTED = RGBColor(0x55, 0x59, 0x61)
FONT = "Calibri"

TEAM = [("Nakul Hintya", "K026"), ("Shivansh Rohit Jindal", "K029"), ("Dhyey Kharayat", "K031")]
MENTOR = "Dr. Pintu R Shah, Head of Department, Computer Science & Engineering (Cyber Security)"


def _institution_mark() -> Path:
    """The MPSTME / NMIMS box from the department's own template, cropped."""
    target = OUT_DIR / "_mpstme_mark.png"
    with Image.open(TEMPLATE) as im:
        im.crop((0, 0, 442, 178)).save(target)
    return target


def _run(par, text, *, size=11, bold=False, italic=False, colour=INK):
    r = par.add_run(text)
    r.font.name = FONT
    r.font.size = Pt(size)
    r.bold = bold
    r.italic = italic
    r.font.color.rgb = colour
    return r


def _para(doc, text="", *, size=11, bold=False, italic=False, colour=INK, align=None,
          after=6, before=0):
    p = doc.add_paragraph()
    if text:
        _rich(p, text, size=size, bold=bold, italic=italic, colour=colour)
    if align is not None:
        p.alignment = align
    p.paragraph_format.space_after = Pt(after)
    p.paragraph_format.space_before = Pt(before)
    p.paragraph_format.line_spacing = 1.12
    return p


def _rich(p, text, *, size=11, bold=False, italic=False, colour=INK):
    """`**bold**` spans inside a paragraph."""
    for i, part in enumerate(text.split("**")):
        if part:
            _run(p, part, size=size, bold=bold or i % 2 == 1, italic=italic, colour=colour)


def _heading(doc, number, title):
    p = doc.add_paragraph()
    _run(p, f"{number}. {title}", size=14, bold=True, colour=RED)
    p.paragraph_format.space_before = Pt(10)
    p.paragraph_format.space_after = Pt(4)
    p.paragraph_format.keep_with_next = True


def _bullets(doc, items):
    for item in items:
        p = doc.add_paragraph(style="List Bullet")
        _rich(p, item, size=10.5)
        p.paragraph_format.space_after = Pt(2)
        p.paragraph_format.line_spacing = 1.1


def _table(doc, rows, widths):
    t = doc.add_table(rows=len(rows), cols=len(rows[0]))
    t.style = "Table Grid"
    t.alignment = WD_TABLE_ALIGNMENT.CENTER
    for r, row in enumerate(rows):
        for c, text in enumerate(row):
            cell = t.rows[r].cells[c]
            cell.width = Cm(widths[c])
            cell.text = ""
            _rich(cell.paragraphs[0], text, size=9.5, bold=r == 0,
                  colour=RGBColor(0xFF, 0xFF, 0xFF) if r == 0 else INK)
            if r == 0:
                shade = cell._tc.get_or_add_tcPr()
                from docx.oxml import OxmlElement
                from docx.oxml.ns import qn
                fill = OxmlElement("w:shd")
                fill.set(qn("w:val"), "clear")
                fill.set(qn("w:color"), "auto")
                fill.set(qn("w:fill"), "BC312C")
                shade.append(fill)
    doc.add_paragraph().paragraph_format.space_after = Pt(2)


def build() -> Path:
    OUT_DIR.mkdir(exist_ok=True)
    doc = Document()
    for s in doc.sections:
        s.page_width, s.page_height = Cm(21), Cm(29.7)
        s.left_margin = s.right_margin = Cm(2)
        s.top_margin, s.bottom_margin = Cm(1.6), Cm(1.6)

    # Header: institution on the left, the project's mark on the right.
    head = doc.add_table(rows=1, cols=2)
    left, right = head.rows[0].cells
    left.paragraphs[0].add_run().add_picture(str(_institution_mark()), width=Cm(6.2))
    rp = right.paragraphs[0]
    rp.alignment = WD_ALIGN_PARAGRAPH.RIGHT
    rp.add_run().add_picture(str(LOGO), width=Cm(2.4))

    _para(doc, "EXECUTIVE SUMMARY", size=10, bold=True, colour=RED, align=WD_ALIGN_PARAGRAPH.CENTER,
          after=2, before=6)
    _para(doc, "API Exorcist", size=24, bold=True, colour=INK, align=WD_ALIGN_PARAGRAPH.CENTER, after=0)
    _para(doc, "Autonomous Discovery and Safe Elimination of Zombie, Shadow and Orphaned APIs",
          size=12.5, colour=MUTED, align=WD_ALIGN_PARAGRAPH.CENTER, after=6)
    _para(doc, "Capstone Project · Group 4 · B.Tech. Computer Science and Engineering (Cyber Security) "
               "· MPSTME, SVKM's NMIMS, Mumbai · 2026–2027",
          size=9.5, colour=MUTED, align=WD_ALIGN_PARAGRAPH.CENTER, after=2)
    _para(doc, "  ·  ".join(f"{n} ({r})" for n, r in TEAM), size=10, bold=True,
          align=WD_ALIGN_PARAGRAPH.CENTER, after=0)
    _para(doc, f"Faculty Mentor: {MENTOR}", size=9.5, colour=MUTED,
          align=WD_ALIGN_PARAGRAPH.CENTER, after=10)

    # ---- 1 ----------------------------------------------------------------------------
    _heading(doc, 1, "Introduction and problem statement")
    _para(doc, "A bank exposes hundreds of HTTP endpoints across mobile and internet banking, "
               "payments, KYC and partner integrations, and every new feature adds more. Removing "
               "one requires someone to be sure nothing still uses it, a decision that is expensive "
               "to make and cheap to postpone, so it is postponed. The endpoint keeps its "
               "credentials, its network route and its access to production data while it "
               "disappears from the organisation's inventory. A **zombie API** is still deployed "
               "and reachable but used and maintained by no one; a **shadow API** runs but is "
               "documented nowhere. OWASP ranks this as API9:2023, Improper Inventory Management, "
               "and the RBI's Cyber Security Framework requires banks to maintain an asset inventory.")
    _para(doc, "Existing tools either list endpoints from a single source (a gateway registry, a "
               "specification, a code scanner) or detect anomalies and stop at a report. None tells "
               "an **orphaned** endpoint (unowned but still in use, where removal is an outage) from "
               "a **zombie**, none predicts what a removal would break, and none removes one safely.")
    _para(doc, "**Problem statement.** Determine each endpoint's lifecycle state from sources that "
               "disagree, telling \"this source says no\" from \"this source was never asked\"; "
               "predict what removing it would break; remove it without an outage; and explain every "
               "decision well enough to defend in an audit.")

    # ---- 2 ----------------------------------------------------------------------------
    _heading(doc, 2, "Methodology")
    _bullets(doc, [
        "**Six-source correlation.** Code (Semgrep syntax-tree rules for FastAPI, Flask, Express "
        "and Spring), the OpenAPI specification, CI/CD, the API gateway, traffic and DNS each see "
        "part of the estate. Their observations are joined into one inventory with 14 discrepancy "
        "flags. **Absence is evidence**: a zombie is present in code and DNS, absent from the "
        "gateway and the specification, and silent in traffic.",
        "**Explainable classification.** Fifteen rules with signed weights classify every endpoint "
        "as ACTIVE, DEPRECATED, ORPHANED or ZOMBIE. A rule whose source was never consulted "
        "abstains, so a scan without traffic never labels anything a zombie. Every verdict carries "
        "its signed reasons, the full score table, and counterfactuals: the smallest change to the "
        "evidence that would change it.",
        "**A learned veto.** A gradient-boosting model, explained with SHAP, may block a removal "
        "the rules propose and may never create one.",
        "**Removal gate and blast radius.** A dependency graph must find nothing calling an "
        "endpoint before it is cleared; blast radius is computed to any depth.",
        "**Safe Kill.** A ninety-day shadow (the rule of three: 95% confidence of seeing a caller "
        "who calls once a month), a named approval, a canary answering 410 Gone to 5%, 25% and "
        "100% of requests with automatic rollback, and a hash-chained audit log. Traffic whose "
        "callers cannot be identified can never be approved.",
        "**Real projects and real usage.** Repository scans rank zombie candidates from code "
        "evidence; imported gateway and load-balancer logs then prove them. A GitHub Action fails "
        "pull requests that add undocumented, unowned or zombie-in-the-making endpoints.",
        "**Evaluation.** A comparative benchmark on a 25-endpoint simulated bank with a known "
        "answer key, 120 generated estates for the model and Safe Kill, and an independent "
        "validation on public repositories. The bank estate is synthetic and says so; the code "
        "scans are real.",
    ])

    # ---- 3 ----------------------------------------------------------------------------
    _heading(doc, 3, "Key findings and results")
    _table(doc, [
        ["Measure", "Result"],
        ["Zombies found on the simulated bank", "**8 of 8** by correlating six sources; **2 of 8** by a "
         "conventional gateway-plus-specification inventory"],
        ["Classification quality", "Accuracy **0.960**, macro-F1 **0.940**, zombie recall **1.000**, "
         "**zero** live endpoints marked for removal"],
        ["Learned model on 36 unseen estates", "**0** false zombies, against the rules' 14: hence a veto, "
         "not a replacement"],
        ["Safe Kill across 120 generated estates", "The gate alone would remove **49** live endpoints "
         "(49 outages); with Safe Kill, **0** outages, and all **793** dead endpoints still retired"],
        ["Endpoints found in real code", "**126 of 127** agree with independent truth lists; **167 of 167** "
         "trace to the line that declares them; **25 of 25** candidate reasons true in the source"],
        ["Blast radius (demo estate)", "Removing one account-read endpoint would reach **9 services, 5 hops "
         "deep**; a one-hop check would miss six"],
        ["Engineering", "307 Python and 51 dashboard tests, strict typing, a check that every documented "
         "figure matches the code, and CI on every push"],
    ], [5.2, 11.8])
    _para(doc, "On real code, the scan of OWASP crAPI ranks first the two insecure old versions the "
               "project keeps beside their fixes: v2/check-otp accepts any number of wrong one-time "
               "passwords where v3 locks after ten, and the project's own web application calls "
               "only v3. On VAmPI it flags the debug endpoints _debug and createdb shipped in "
               "the API.", size=10.5)
    _para(doc, "The one misclassification on the simulated bank is a deprecated endpoint whose team "
               "never set the specification's deprecation flag. It is reported rather than tuned "
               "away, and the system's own counterfactual names the missing evidence: it would be "
               "DEPRECATED if the specification marked it.", size=10.5)

    # ---- 4 ----------------------------------------------------------------------------
    _heading(doc, 4, "Project value and impact")
    _bullets(doc, [
        "**Smaller attack surface.** It finds the endpoints an inventory misses: six of the eight "
        "zombies were invisible to the gateway and the specification, and four of those had no "
        "authentication at all.",
        "**Removal without outages.** Telling orphaned from zombie, and shadowing before refusing "
        "anything, turns removal from a judgement call into a measured, reversible process.",
        "**Compliance and audit.** Every verdict carries its reasons and every decision a named "
        "person, in a tamper-evident log: evidence for OWASP API9 and the RBI's inventory "
        "requirement.",
        "**Prevention.** Pull-request enforcement stops new zombies at the commit that creates "
        "them, and judges only the change, so a bank with existing debt can adopt it at once.",
        "**Deployable.** A browser console, REST API with hashed tokens and roles, a hardened "
        "container, and metrics; it reads the logs and repositories a bank already has.",
        "**Academic contribution.** A six-page research paper and an open-source repository; the "
        "project qualified for the inter-capstone competition.",
    ])
    _para(doc, "**Limitations and next steps.** The banking estate is synthetic; the next step is a "
               "pilot on a real organisation's logs, with gateway plugins so the shadow and canary act "
               "on real traffic, calendar-aware windows for quarterly jobs, and wider framework "
               "coverage (Django, Go, ASP.NET).", size=10.5, before=4)
    _para(doc, "Source code: github.com/shivanshjindal28/api-exorcist", size=9.5, colour=MUTED,
          align=WD_ALIGN_PARAGRAPH.CENTER, before=6)

    doc.save(OUTPUT)
    return OUTPUT


if __name__ == "__main__":
    print(f"  built {build().name}")
