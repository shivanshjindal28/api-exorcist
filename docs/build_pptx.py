"""
Generate the Review 2 (50% / midterm) capstone presentation.

Why a generator rather than a hand-built .pptx
----------------------------------------------
The same reason docs/build_docx.py exists: every figure on these slides is a
claim about the running system, and a hand-edited deck drifts away from the
code within days. The numbers here are the ones docs/verify_claims.py checks,
and the diagrams are the ones docs/render_diagrams.py produces.

The template
------------
Slides are drawn on the MPSTME 4:3 template (docs/assets/mpstme-template.jpg),
taken from the department's own sample deck: red band top and bottom, NMIMS
shield and MPSTME wordmark in the white box at top left, NMIMS logo at top
right. It is applied as a full-bleed background on every slide, so the branding
cannot drift between slides. All content sits inside SAFE_TOP..SAFE_BOTTOM,
which clears the logo box and both red bands.

Slide order follows the department's sample deck:
    Title, Contents, Introduction, Literature Survey, Problem Statement,
    Objectives and Scope, Tools and Technologies, Market Research,
    Design Document, Implementation, Future Extensions, References.

It is expanded where the Review 2 rubric asks for more than the sample shows --
system-level representation, algorithms, results, individual contribution and
progress against plan.

Layout is a downward flow: every helper takes the current y and returns the
next one, so content cannot silently overlap or run off the bottom. Vertical
positions are never hard-coded.

Usage:
    python docs/build_pptx.py

Requires: python-pptx, Pillow. Diagram PNGs come from docs/diagrams/ (render
them with docs/render_diagrams.py first); a missing one leaves a visible
placeholder rather than a silently empty slide.
"""

from __future__ import annotations

from pathlib import Path

from PIL import Image
from pptx import Presentation
from pptx.dml.color import RGBColor
from pptx.enum.text import MSO_ANCHOR, PP_ALIGN
from pptx.util import Emu, Inches, Pt

DOCS = Path(__file__).resolve().parent
DIAGRAMS = DOCS / "diagrams"
TEMPLATE = DOCS / "assets" / "mpstme-template.jpg"
OUTPUT = DOCS / "API_Exorcist_Review2_Presentation.pptx"

# 4:3, matching the department's sample deck (768 x 576 pt = 10.667 x 8 in).
SLIDE_W = Inches(10.667)
SLIDE_H = Inches(8.0)

# Measured from the template image (1200 x 900 px at 112.5 px/in):
#   red band          0.00 - 0.76 in
#   white logo box    0.00 - 1.58 in, left edge out to 3.93 in
#   red band          7.87 - 8.00 in
SAFE_TOP = Inches(1.66)      # clears the logo box
SAFE_BOTTOM = Inches(7.74)   # clears the lower red band
MARGIN = Inches(0.62)
CONTENT_W = SLIDE_W - 2 * MARGIN

# NMIMS brand red, sampled from the template's top band.
RED = RGBColor(0xBC, 0x31, 0x2C)
INK = RGBColor(0x1C, 0x1F, 0x26)
MUTED = RGBColor(0x55, 0x59, 0x61)
PALE = RGBColor(0xF7, 0xE9, 0xE8)     # red tint, for emphasis bands
SHADE = RGBColor(0xF4, 0xF2, 0xEF)
GOOD = RGBColor(0x1B, 0x66, 0x36)
WHITE = RGBColor(0xFF, 0xFF, 0xFF)

SANS_FONT = "Calibri"
MONO_FONT = "Consolas"

EMU_PER_IN = 914400


# ---------------------------------------------------------------------------
# Primitives
# ---------------------------------------------------------------------------
def _blank(prs: Presentation):
    """A slide carrying the MPSTME template as a full-bleed background."""
    slide = prs.slides.add_slide(prs.slide_layouts[6])
    if TEMPLATE.exists():
        slide.shapes.add_picture(str(TEMPLATE), 0, 0, SLIDE_W, SLIDE_H)
    else:  # visible, not silent
        bg = slide.background.fill
        bg.solid()
        bg.fore_color.rgb = WHITE
    return slide


def _text(slide, left, top, width, height, *, align=PP_ALIGN.LEFT,
          anchor=MSO_ANCHOR.TOP):
    box = slide.shapes.add_textbox(left, top, width, height)
    tf = box.text_frame
    tf.word_wrap = True
    tf.vertical_anchor = anchor
    tf.margin_left = tf.margin_right = 0
    tf.margin_top = tf.margin_bottom = 0
    tf.paragraphs[0].alignment = align
    return tf


def _line(tf, text, *, size=15, bold=False, italic=False, colour=INK,
          font=SANS_FONT, space_after=6, first=False, align=None):
    para = tf.paragraphs[0] if first else tf.add_paragraph()
    para.space_before = Pt(0)
    para.space_after = Pt(space_after)
    if align is not None:
        para.alignment = align
    run = para.add_run()
    run.text = text
    run.font.size = Pt(size)
    run.font.bold = bold
    run.font.italic = italic
    run.font.color.rgb = colour
    run.font.name = font
    return para


def _height_of(text, size, width_in, space_after=6):
    """Rendered height of one wrapped paragraph, in EMU. Deliberately generous."""
    per_line = max(1, int(width_in * 72 / (size * 0.47)))
    lines = max(1, -(-len(text) // per_line))
    return int((lines * size * 1.22 + space_after) * EMU_PER_IN / 72)


def _band(slide, top, colour, height):
    shape = slide.shapes.add_shape(1, MARGIN, top, CONTENT_W, height)
    shape.fill.solid()
    shape.fill.fore_color.rgb = colour
    shape.line.fill.background()
    shape.shadow.inherit = False
    return shape


def heading(slide, title, subtitle=""):
    """Slide title, red rule beneath, optional subtitle. Returns the next y."""
    h = _height_of(title, 25, CONTENT_W / EMU_PER_IN, 0)
    tf = _text(slide, MARGIN, SAFE_TOP, CONTENT_W, Emu(h))
    _line(tf, title, size=25, bold=True, colour=RED, first=True, space_after=0)

    y = SAFE_TOP + Emu(h) + Inches(0.07)
    rule = slide.shapes.add_shape(1, MARGIN, y, CONTENT_W, Pt(1.6))
    rule.fill.solid()
    rule.fill.fore_color.rgb = RED
    rule.line.fill.background()
    rule.shadow.inherit = False
    y += Inches(0.13)

    if subtitle:
        sh = _height_of(subtitle, 12.5, CONTENT_W / EMU_PER_IN, 0)
        tf = _text(slide, MARGIN, y, CONTENT_W, Emu(sh))
        _line(tf, subtitle, size=12.5, italic=True, colour=MUTED, first=True,
              space_after=0)
        y += Emu(sh) + Inches(0.12)
    return y + Inches(0.06)


def footnote(slide, text, colour=MUTED):
    """Pinned just above the lower red band. Returns its top edge."""
    h = _height_of(text, 10.5, CONTENT_W / EMU_PER_IN, 0)
    top = SAFE_BOTTOM - Emu(h)
    tf = _text(slide, MARGIN, top, CONTENT_W, Emu(h))
    _line(tf, text, size=10.5, italic=True, colour=colour, first=True,
          space_after=0)
    return top


def bullets(slide, top, items, *, size=14.5, gap=8):
    """items: str, or (text, size, bold, colour). Returns the next y."""
    width_in = CONTENT_W / EMU_PER_IN
    prepared, total = [], 0
    for item in items:
        text, isize, bold, colour = (
            (item, size, False, INK) if isinstance(item, str) else item
        )
        prepared.append((text, isize, bold, colour))
        total += _height_of(text, isize, width_in, gap)

    tf = _text(slide, MARGIN, top, CONTENT_W, Emu(total))
    for n, (text, isize, bold, colour) in enumerate(prepared):
        _line(tf, text, size=isize, bold=bold, colour=colour,
              space_after=gap, first=(n == 0))
    return top + Emu(total)


def table(slide, top, rows, weights, *, size=12, min_lines=1,
          highlight_last=False):
    """`weights` are column width fractions of CONTENT_W. Returns the next y."""
    n_rows, n_cols = len(rows), len(rows[0])
    widths = [int(CONTENT_W * w) for w in weights]

    # A row must be tall enough for its tallest cell, or PowerPoint grows the
    # table at render time and it walks off the bottom of the slide.
    heights = []
    for r, row in enumerate(rows):
        need = 1
        for c, cell_text in enumerate(row):
            col_in = widths[c] / EMU_PER_IN - 0.16
            per_line = max(1, int(col_in * 72 / (size * 0.47)))
            for part in cell_text.strip("*").split("\n"):
                need = max(need, -(-len(part) // per_line))
        floor = 1 if r == 0 else min_lines
        heights.append(Inches(0.2 + 0.19 * max(need, floor)))

    shape = slide.shapes.add_table(
        n_rows, n_cols, MARGIN, top, Emu(sum(widths)), Emu(sum(heights))
    )
    tbl = shape.table
    tbl.first_row = True
    for i, w in enumerate(widths):
        tbl.columns[i].width = Emu(w)
    for r, h in enumerate(heights):
        tbl.rows[r].height = h

    for r, row in enumerate(rows):
        for c, cell_text in enumerate(row):
            cell = tbl.cell(r, c)
            cell.margin_left = cell.margin_right = Inches(0.07)
            cell.margin_top = cell.margin_bottom = Inches(0.02)
            cell.vertical_anchor = MSO_ANCHOR.MIDDLE
            cell.fill.solid()
            if r == 0:
                cell.fill.fore_color.rgb = RED
            elif highlight_last and r == n_rows - 1:
                cell.fill.fore_color.rgb = PALE
            else:
                cell.fill.fore_color.rgb = WHITE

            tf = cell.text_frame
            tf.word_wrap = True
            emphatic = cell_text.startswith("*") and cell_text.endswith("*")
            for i, part in enumerate(cell_text.strip("*").split("\n")):
                para = tf.paragraphs[0] if i == 0 else tf.add_paragraph()
                para.space_before = Pt(0)
                para.space_after = Pt(0)
                para.alignment = (
                    PP_ALIGN.CENTER if c and n_cols > 2 else PP_ALIGN.LEFT
                )
                run = para.add_run()
                run.text = part
                run.font.size = Pt(size)
                run.font.name = SANS_FONT
                if r == 0:
                    run.font.bold = True
                    run.font.color.rgb = WHITE
                else:
                    run.font.bold = emphatic or (
                        highlight_last and r == n_rows - 1
                    )
                    run.font.color.rgb = RED if emphatic else INK
    return top + Emu(sum(heights))


def picture(slide, top, name, *, bottom=None):
    """Fit a diagram between `top` and `bottom`. Returns the next y."""
    limit = bottom or SAFE_BOTTOM
    box_h = limit - top
    png = DIAGRAMS / f"{name}.png"
    if not png.exists():
        tf = _text(slide, MARGIN, top, CONTENT_W, Inches(0.4),
                   align=PP_ALIGN.CENTER)
        _line(tf, f"[ {name}.png not rendered - run docs/render_diagrams.py ]",
              size=13, colour=RED, font=MONO_FONT, first=True,
              align=PP_ALIGN.CENTER)
        return top + Inches(0.4)

    with Image.open(png) as im:
        w, h = im.size
    scale = min(CONTENT_W / w, box_h / h)
    width, height = int(w * scale), int(h * scale)
    slide.shapes.add_picture(
        str(png), Emu(int(MARGIN + (CONTENT_W - width) / 2)), top,
        Emu(width), Emu(height),
    )
    return top + Emu(height)


def code(slide, top, lines, *, size=11.5):
    """Monospaced panel with a red edge. Returns the next y."""
    line_h = Inches(0.183 * (size / 11.5))
    h = line_h * len(lines) + Inches(0.2)
    _band(slide, top, SHADE, h)
    edge = slide.shapes.add_shape(1, MARGIN, top, Pt(3), h)
    edge.fill.solid()
    edge.fill.fore_color.rgb = RED
    edge.line.fill.background()
    edge.shadow.inherit = False

    tf = _text(slide, MARGIN + Inches(0.16), top + Inches(0.1),
               CONTENT_W - Inches(0.28), h - Inches(0.18))
    for n, line in enumerate(lines):
        _line(tf, line or " ", size=size, font=MONO_FONT, colour=INK,
              space_after=0, first=(n == 0))
    return top + h


def callout(slide, top, text, *, size=14, colour=RED):
    """Emphasised band. Returns the next y."""
    h = Emu(_height_of(text, size, CONTENT_W / EMU_PER_IN - 0.55, 0)) + Inches(0.26)
    _band(slide, top, PALE, h)
    bar = slide.shapes.add_shape(1, MARGIN, top, Pt(4), h)
    bar.fill.solid()
    bar.fill.fore_color.rgb = colour
    bar.line.fill.background()
    bar.shadow.inherit = False
    tf = _text(slide, MARGIN + Inches(0.22), top + Inches(0.11),
               CONTENT_W - Inches(0.4), h - Inches(0.22))
    _line(tf, text, size=size, bold=True, colour=INK, first=True, space_after=0)
    return top + h


def two_columns(slide, top, left_title, left_items, right_title, right_items,
                *, size=13):
    col_w = (CONTENT_W - Inches(0.4)) / 2
    col_in = col_w / EMU_PER_IN
    lowest = top
    for offset, title, items in (
        (MARGIN, left_title, left_items),
        (MARGIN + col_w + Inches(0.4), right_title, right_items),
    ):
        tf = _text(slide, offset, top, col_w, Inches(0.32))
        _line(tf, title, size=15.5, bold=True, colour=RED, first=True,
              space_after=0)
        y = top + Inches(0.38)
        total = sum(_height_of(t, size, col_in, 8) for t in items)
        tf = _text(slide, offset, y, col_w, Emu(total))
        for n, item in enumerate(items):
            _line(tf, item, size=size, colour=INK, space_after=8,
                  first=(n == 0))
        lowest = max(lowest, y + Emu(total))
    return lowest


# ---------------------------------------------------------------------------
# Content
# ---------------------------------------------------------------------------
TEAM = ["Shivansh Jindal", "Jal Bafana", "Arjun Mehta", "Tejas Sahoo"]
TITLE = "API Exorcist"
SUBTITLE = ("Autonomous Discovery and Safe Elimination of "
            "Zombie, Shadow and Orphaned APIs")


def slide_title(prs):
    slide = _blank(prs)
    y = SAFE_TOP + Inches(0.35)
    tf = _text(slide, MARGIN, y, CONTENT_W, Inches(0.75), align=PP_ALIGN.CENTER)
    _line(tf, TITLE, size=40, bold=True, colour=RED, first=True,
          align=PP_ALIGN.CENTER, space_after=0)
    y += Inches(0.82)

    h = _height_of(SUBTITLE, 18, CONTENT_W / EMU_PER_IN, 0)
    tf = _text(slide, MARGIN, y, CONTENT_W, Emu(h), align=PP_ALIGN.CENTER)
    _line(tf, SUBTITLE, size=18, colour=INK, first=True,
          align=PP_ALIGN.CENTER, space_after=0)
    y += Emu(h) + Inches(0.32)

    tf = _text(slide, MARGIN, y, CONTENT_W, Inches(0.34), align=PP_ALIGN.CENTER)
    _line(tf, "Capstone Project - Review 2 (Midterm, 50% Implementation)",
          size=14.5, bold=True, colour=RED, first=True, align=PP_ALIGN.CENTER,
          space_after=0)
    y += Inches(0.6)

    tf = _text(slide, MARGIN, y, CONTENT_W, Inches(1.3), align=PP_ALIGN.CENTER)
    for n, member in enumerate(TEAM):
        _line(tf, member, size=15.5, colour=INK, first=(n == 0),
              align=PP_ALIGN.CENTER, space_after=3)
    y += Inches(1.3)

    tf = _text(slide, MARGIN, y, CONTENT_W, Inches(0.85), align=PP_ALIGN.CENTER)
    _line(tf, "Faculty Mentor: ____________________", size=14, colour=MUTED,
          first=True, align=PP_ALIGN.CENTER, space_after=10)
    _line(tf, "B.Tech. Computer Science and Engineering (Cyber Security)   |   "
              "2026-2027", size=12.5, colour=MUTED, align=PP_ALIGN.CENTER,
          space_after=0)


def slide_contents(prs):
    slide = _blank(prs)
    y = heading(slide, "Table of Contents")
    items = [
        "Introduction", "Problem Statement",
        "Literature Survey and Research Gap", "Objectives and Scope",
        "Tools and Technologies Used", "Market Research",
        "Design Document - structural and behavioural views", "Algorithms",
        "Implementation (live demo)", "Results and Analysis",
        "Interim Report and Deliverables",
        "Individual Contribution and Progress against Plan",
        "Future Extensions", "References",
    ]
    col_w = (CONTENT_W - Inches(0.45)) / 2
    half = (len(items) + 1) // 2
    for offset, chunk, start in (
        (MARGIN, items[:half], 1),
        (MARGIN + col_w + Inches(0.45), items[half:], half + 1),
    ):
        tf = _text(slide, offset, y + Inches(0.2), col_w, Inches(4.5))
        for n, item in enumerate(chunk):
            _line(tf, f"{start + n}.   {item}", size=15, colour=INK,
                  space_after=12, first=(n == 0))


def slide_intro_1(prs):
    slide = _blank(prs)
    y = heading(slide, "Introduction",
                "Endpoints are created quickly and retired slowly - or never")
    y = bullets(slide, y, [
        ("A single retail bank exposes hundreds of HTTP endpoints across "
         "mobile banking, internet banking, payments, KYC and partner "
         "integrations.", 14.5, False, INK),
        ("Decommissioning is the one lifecycle step that depends on a human "
         "deciding nothing needs the endpoint any more. That decision is "
         "expensive to make correctly and cheap to postpone.", 14.5, False, INK),
        ("So it is postponed. The endpoint keeps running - and keeps its "
         "database credentials, its network route and its access to production "
         "data - while disappearing from the organisation's inventory.",
         14.5, False, INK),
    ], gap=12)
    y = callout(slide, y + Inches(0.14),
                "OWASP API9:2023 - Improper Inventory Management.   RBI's "
                "Cyber Security Framework requires a maintained asset "
                "inventory.", size=13.5)
    bullets(slide, y + Inches(0.16), [
        ("An endpoint nobody knows about cannot be patched, cannot be "
         "monitored, and cannot be included in an audit.", 15, True, RED),
    ])


def slide_intro_2(prs):
    slide = _blank(prs)
    y = heading(slide, "Four states, not one problem",
                'Everything old gets called a "dead API". These four need '
                "different responses.")
    y = table(slide, y, [
        ["State", "Definition", "Correct action"],
        ["ACTIVE", "Documented, owned, carrying meaningful traffic",
         "Leave alone"],
        ["DEPRECATED", "Declared end-of-life but still serving real callers",
         "Managed sunset with notice"],
        ["ORPHANED", "Carrying real traffic but with no owning team",
         "Assign an owner - never remove"],
        ["ZOMBIE", "Reachable, unowned, undocumented, not meaningfully used",
         "Candidate for removal"],
    ], [0.19, 0.49, 0.32], size=12.5)
    y = callout(slide, y + Inches(0.2),
                "ORPHANED and ZOMBIE are both unowned. Only one is unused.",
                size=15)
    bullets(slide, y + Inches(0.16), [
        ("Removing an orphaned endpoint causes an outage - and because no team "
         "claims it, that outage is harder to diagnose, not easier.",
         14, False, INK),
        ("A tool that cannot separate these two is not usable in production.",
         14, True, RED),
    ])


def slide_problem(prs):
    slide = _blank(prs)
    y = heading(slide, "Problem Statement")
    y = callout(
        slide, y,
        "Determine an endpoint's true lifecycle state from sources that "
        "disagree, quantify the consequence of removing it, and make both "
        "decisions explainable enough to defend in a regulated audit.",
        size=15.5,
    )
    bullets(slide, y + Inches(0.26), [
        ("Three sub-problems:", 14.5, True, RED),
        ("1.  Determination under partial evidence - establish state from "
         "disagreeing sources, and distinguish \"this source says no\" from "
         "\"this source was never asked\".", 14, False, INK),
        ("2.  Consequence prediction - before clearing a removal, determine "
         "what transitively calls it, and refuse anything with dependants.",
         14, False, INK),
        ("3.  Auditability - every classification and every removal decision "
         "carries the complete evidence that produced it.", 14, False, INK),
        ("Existing tooling either misses these endpoints or, worse, flags live "
         "ones. And the tools that do detect stop at detection: the decision "
         "to decommission is left to unaided human judgement.",
         14, False, MUTED),
    ], gap=11)


def slide_why_hard(prs):
    slide = _blank(prs)
    y = heading(slide, "Why no single source can answer this",
                "Six sources, six independent questions, six systematic blind "
                "spots")
    y = table(slide, y, [
        ["Source", "Question it answers", "What it cannot see"],
        ["CODE", "Does this endpoint exist in the source?",
         "Whether anything calls it"],
        ["DNS", "Is it reachable on the network?", "Use, or ownership"],
        ["GATEWAY", "Is it registered with the proxy?",
         "Services addressed directly"],
        ["CICD", "Was it deployed by a known pipeline?",
         "Manual and legacy deployments"],
        ["TRAFFIC", "Was it actually called?",
         "Anything silent during the window"],
        ["OPENAPI", "Is it documented?",
         "Whatever the team forgot to document"],
    ], [0.16, 0.45, 0.39], size=12.5)
    callout(slide, y + Inches(0.22),
            "A zombie is not found by any one source. It is found where the "
            "six answers DISAGREE.", size=15)
    footnote(slide, "Code defines it  |  DNS resolves it  |  gateway, spec, "
                    "pipeline and traffic have never heard of it.")


def _lit_slide(prs, index, rows):
    slide = _blank(prs)
    y = heading(slide, f"Literature Survey ({index}/4)",
                "Paper - finding used - how it is used in our implementation")
    table(slide, y,
          [["Paper", "Finding used", "Use in the project"], *rows],
          [0.20, 0.40, 0.40], size=11.5)


def slide_literature(prs):
    _lit_slide(prs, 1, [
        ["[1] Caivano et al.\nEMSE 2023",
         "Dead code studied at commit level over 23 applications and 1,587 "
         "commits: decay is slow, most dead methods are stillborn, and dead "
         "methods are rarely revived.",
         "Temporal signals are first-class evidence (CODE_UNTOUCHED_1Y, "
         "STALE_6M). The low revival rate is what makes proposing removal "
         "defensible at all."],
        ["[2] Cassieri et al.\nPROFES 2023",
         "Deprecation markers are applied and acted upon inconsistently by "
         "real teams.",
         "DEPRECATED is a class distinct from ZOMBIE, and the declared flag is "
         "treated as unreliable evidence - only 2 of our 3 deprecated "
         "endpoints carry it."],
        ["[11] Brito et al.\nJSS 2018",
         "Across 622 Java and 229 C# systems, on the median only 66.7% / "
         "77.8% of API elements are deprecated with a replacement message, and "
         "message quality does not improve over time.",
         "The deprecation rule is asymmetric: MARKED_DEPRECATED fires on "
         "presence only. There is deliberately NO rule for a missing marker, "
         "because a third of real deprecations have none."],
    ])
    _lit_slide(prs, 2, [
        ["[3] Bushong et al.\nASE 2021",
         "Architecture must be recovered from source because documentation "
         "drifts - and source analysis returns no usage data.",
         "Semgrep AST matching instead of regex; and repository-only scans are "
         "architecturally forbidden from making a lifecycle claim."],
        ["[12] Gortney et al.\nIEEE Access 2022",
         "Systematic map of architecture reconstruction in the DYNAMIC "
         "perspective - log analysis, tracing, monitoring - as a practice "
         "distinct from static recovery.",
         "Static and dynamic sources are both consumed and neither subsumes "
         "the other. Their disagreement IS the zombie signal, and a "
         "static-only scan must abstain."],
        ["[4] Ma et al.\nFGCS 2019",
         "A Service Dependency Graph implemented in Neo4j, evaluated from ten "
         "to hundreds of microservices.",
         "Precedent for Neo4j and for a Cypher variable-length path. We "
         "repurpose the structure from comprehension to a removal safety "
         "gate."],
    ])
    _lit_slide(prs, 3, [
        ["[5] Abdelfattah & Cerny\nESOCC 2023",
         "Inter-service dependency is a measurable, first-class architectural "
         "property.",
         "Blast radius is computed and stored before any removal is cleared."],
        ["[6] Dell'Immagine et al.\nFuture Internet 2023",
         "\"Security smell\" is a valid construct - structural indicators of "
         "elevated risk, short of a vulnerability.",
         "Our 14 discrepancy flags are modelled as security smells, which "
         "gives them grounding rather than leaving them an ad hoc checklist."],
        ["[7] Ponce Mella et al.\nCLEIej 2024",
         "Survey of security-smell impact: the research programme terminates "
         "at detection and triage.",
         "This is our gap. Automated safe remediation - the Safe Kill "
         "Simulation - is what follows detection."],
    ])
    _lit_slide(prs, 4, [
        ["[8] Lundberg & Lee\nNIPS 2017",
         "SHAP gives additive, complete, per-prediction feature attribution.",
         "Why our rule layer is additive signed weights rather than a decision "
         "tree: SHAP values then emit as the same Reason objects the rules "
         "do."],
        ["[9] Gaspar et al.\nIEEE Access 2024",
         "SHAP applies to security decisions, but its cost constrains "
         "real-time use (stated qualitatively; no figure given).",
         "Exact TreeExplainer is affordable for us because this is a per-scan "
         "batch workload, not per-packet at line rate."],
        ["[10] Scheitle et al.\nIMC 2018",
         "CT logs publicly expose unintended hostnames, with privacy "
         "implications.",
         "Two-tier URL scanning: passive sources for any URL; active probing "
         "only after a DNS TXT record proves domain ownership."],
    ])


def slide_gap(prs):
    slide = _blank(prs)
    y = heading(slide, "The Research Gap",
                "Each statement is supported individually. No surveyed work "
                "combines them.")
    y = bullets(slide, y, [
        ("Statements 1-3   No single source can establish an endpoint's true "
         "status - dead code is single-source detectable, declared deprecation "
         "is unreliable, and source recovery yields no usage data.   "
         "[1][2][3][11][12]", 13.5, False, INK),
        ("...yet every surveyed tool is single-source.", 13.5, True, RED),
        ("Statements 4-5   The machinery to predict removal impact exists: "
         "dependency structure is graph-shaped and security smells can be "
         "triaged automatically.   [4][5][6][7]", 13.5, False, INK),
        ("...yet no tool acts on it.", 13.5, True, RED),
        ("Statement 6   Automated decisions can be made auditable with "
         "complete additive attribution.   [8][9]", 13.5, False, INK),
        ("...yet no tool needs it, because none acts.", 13.5, True, RED),
    ], gap=8)
    callout(slide, y + Inches(0.18),
            "Our contribution is the composition: multi-source correlation, "
            "dependency-aware consequence prediction, and complete "
            "per-decision explanation.", size=14)
    footnote(slide, "All 12 citations validated against DBLP or Crossref. Five "
                    "checked against full text - one was found carrying claims "
                    "it does not make, and those claims were removed.")


def slide_objectives(prs):
    slide = _blank(prs)
    y = heading(slide, "Objectives and Scope")
    two_columns(
        slide, y,
        "Objectives", [
            "Correlate six independent discovery sources into one inventory",
            "Classify every endpoint as ACTIVE / DEPRECATED / ORPHANED / "
            "ZOMBIE",
            "Treat absence of evidence as evidence - and abstain when a source "
            "was never consulted",
            "Explain every verdict with signed evidence contributions",
            "Predict blast radius before clearing any removal",
            "Simulate safe removal with canary and automatic rollback",
        ],
        "Scope", [
            "IN - discovery, correlation, classification, explanation, "
            "dependency graph, removal gate, evaluation  (Phases 0-3)",
            "IN - real GitHub repository scanning (Semgrep AST, git history, "
            "CODEOWNERS)",
            "NEXT - Safe Kill Simulation: canary, rollback, hash-chained audit "
            "log  (Phase 4)",
            "LATER - CI/CD enforcement plugin, REST API and dashboard, "
            "hardening and deployment",
            "OUT - no unauthorised external scanning; active probing requires "
            "DNS TXT ownership proof",
        ],
        size=12.5,
    )
    footnote(
        slide,
        "Honesty boundary: the architecture and analysis are real code; the "
        "banking estate they are measured against is synthetic, with a known "
        "answer key. No production bank data was used.",
        colour=RED,
    )


def slide_tools(prs):
    slide = _blank(prs)
    y = heading(slide, "Tools and Technologies Used",
                "Each choice defended against the alternative it beat")
    table(slide, y, [
        ["Component", "Technology", "Why this, not the alternative"],
        ["Route extraction", "Semgrep (AST)",
         "A route is a structural pattern; regex over source text breaks on "
         "formatting"],
        ["Dependency store", "Neo4j / Cypher",
         "Blast radius is a bounded multi-hop traversal - a variable-length "
         "path, not a recursive CTE"],
        ["Traffic observation", "Zeek",
         "Passive full visibility of what was called, not signature matching "
         "for what was an attack"],
        ["Streaming", "Kafka",
         "Traffic-derived signals are bursty; the bus must buffer rather than "
         "block the collector"],
        ["Classification", "Weighted rules + GBM veto",
         "Rules work day one with no training data and are auditable line by "
         "line"],
        ["Explainability", "SHAP TreeExplainer",
         "Exact additive per-prediction attribution, affordable for a per-scan "
         "batch workload"],
        ["Language / CI", "Python 3.10 & 3.12, mypy strict, ruff, pytest",
         "85 tests, three ground-truth leakage guards, CI on both versions"],
    ], [0.20, 0.26, 0.54], size=11.5)
    footnote(slide, "Default configuration needs no external infrastructure - "
                    "clone and reproduce every number with two commands.")


def slide_market(prs):
    slide = _blank(prs)
    y = heading(slide, "Market Research",
                "Who has this problem, what exists today, and where the space "
                "is open")
    two_columns(
        slide, y,
        "The demand", [
            "OWASP ranks Improper Inventory Management in the API Security Top "
            "10 (API9:2023) - the failure mode is recognised industry-wide.",
            "RBI's Cyber Security Framework in Banks makes a maintained asset "
            "inventory a compliance obligation, not an aspiration.",
            "NIST SP 800-95 sets the same expectation for secure web services.",
            "Regulated banks therefore have both a security reason and an "
            "audit reason to buy.",
        ],
        "The gap in what exists", [
            "API gateways (Kong, Apigee, AWS) list only what is registered "
            "with them - blind to anything addressed directly.",
            "API security platforms detect anomalous and undocumented "
            "endpoints, then produce a report.",
            "Static analysis tools list routes defined in a repository, with "
            "no usage evidence at all.",
            "None predict the consequence of removal, and none act. Detection "
            "is a crowded market; safe remediation is not.",
        ],
        size=12.5,
    )
    footnote(slide, "Product shape: connect your GitHub org, your gateway and "
                    "your CI/CD - self-hosted, single tenant, nothing leaves "
                    "the customer's network.")


def _diagram_slide(prs, title, subtitle, name, note):
    slide = _blank(prs)
    y = heading(slide, title, subtitle)
    note_top = footnote(slide, note)
    picture(slide, y, name, bottom=note_top - Inches(0.14))


def slide_design(prs):
    _diagram_slide(
        prs, "Design - System Architecture",
        "Five layers, with a strictly one-way dependency direction",
        "component",
        "Connectors know nothing of ingestion; the engine never reaches back "
        "to a data source. That is what lets the synthetic estate be swapped "
        "for live sources without touching anything downstream.")
    _diagram_slide(
        prs, "Design - Class Diagram (core domain model)", "",
        "classes",
        "Verdict composes a list of Reason objects with signed contributions - "
        "never a bare label. The same type serialises into the audit log and "
        "renders in the explanation output.")
    _diagram_slide(
        prs, "Design - Sequence of a Discovery Scan", "",
        "sequence-scan",
        "Connectors emit observations and never verdicts. Their common output "
        "is DiscoverySignal - eight fields stating what one source observed "
        "about one endpoint.")
    _diagram_slide(
        prs, "Design - Endpoint Lifecycle (state machine)", "",
        "state-lifecycle",
        "These are the transitions the classifier is detecting from evidence, "
        "not transitions the system performs.")


def slide_algo_correlate(prs):
    slide = _blank(prs)
    y = heading(slide, "Algorithm 1 - Multi-source correlation")
    y = code(slide, y, [
        "DEFINE correlate(signals):",
        "  GROUP signals BY (method, path) normalised across frameworks",
        "  FOR each endpoint group:",
        "    CREATE inventory record",
        "    RECORD which sources OBSERVED it       -- presence",
        "    RECORD which sources were CONSULTED    -- so absence can be",
        "                                           -- told from 'never asked'",
        "    MERGE attributes, preferring OBSERVED over DECLARED",
        "    DERIVE the 14 discrepancy flags",
        "  RETURN inventory",
    ])
    bullets(slide, y + Inches(0.22), [
        ("sources_consulted is the mechanism that makes the whole system "
         "honest - it separates \"traffic saw nothing\" from \"traffic was "
         "never collected\". Every downstream claim depends on that "
         "distinction.", 13.5, False, INK),
        ("Observed beats declared: traffic-observed authentication outranks "
         "gateway-declared authentication, because a gateway can claim OAuth2 "
         "on a route the service also exposes directly with none.",
         13.5, False, INK),
    ], gap=9)
    footnote(slide, "14 flags: UNDOCUMENTED, UNREGISTERED, SHADOW_CANDIDATE, "
                    "NO_TRAFFIC_IN_WINDOW, EFFECTIVELY_SILENT, STALE_6M, "
                    "NO_OWNER, REACHABLE_BUT_UNUSED, UNAUTHENTICATED, "
                    "LEGACY_AUTH, SENSITIVE_DATA, MARKED_DEPRECATED, "
                    "CODE_UNTOUCHED_1Y, NO_PIPELINE_RECORD")


def slide_algo_classify(prs):
    slide = _blank(prs)
    y = heading(slide, "Algorithm 2 - Evidence scoring with abstention",
                "15 rules, each a predicate, a source requirement, and a "
                "signed weight per class")
    y = code(slide, y, [
        "DEFINE classify(record, sources_consulted):",
        "  scores <- {ACTIVE: 0, DEPRECATED: 0, ORPHANED: 0, ZOMBIE: 0}",
        "  FOR each rule in RULES:                 -- 15 rules",
        "    IF NOT rule.evaluable_with(sources_consulted):",
        "      CONTINUE                            -- ABSTAIN: never asked",
        "    IF rule.predicate(record):",
        "      scores += rule.weights              -- signed, per class",
        "      APPEND Reason(rule.statement, contribution)",
        "  label      <- argmax(scores)",
        "  confidence <- softmax(scores, temperature = 3.0)[label]",
        "  RETURN Verdict(label, confidence, reasons, sources_consulted)",
    ])
    bullets(slide, y + Inches(0.2), [
        ("Additive, not a decision tree - two properties follow, and neither "
         "is available from a tree:", 13.5, True, RED),
        ("It degrades gracefully: an abstaining rule removes its contribution "
         "instead of breaking a branch.", 13.5, False, INK),
        ("Confidence comes from the margin between the top two classes, so "
         "ambiguous evidence reports low confidence rather than an arbitrary "
         "choice.", 13.5, False, INK),
    ], gap=7)


def slide_missing_sources(prs):
    slide = _blank(prs)
    y = heading(slide, "What if those six sources are not present?",
                "It degrades rule by rule and states what it lost - it does "
                "not just refuse to scan")
    y = table(slide, y, [
        ["Sources available", "Rules usable", "What the system may claim"],
        ["All six", "15 / 15", "Full lifecycle classification"],
        ["Repository only (CODE, OPENAPI, CICD)", "6 / 15",
         "Endpoints exist - no lifecycle claim"],
        ["Traffic only", "5 / 15", "Usage, but not documentation or ownership"],
        ["Code only", "3 / 15", "Existence only"],
        ["*Gateway only*", "*0 / 15*", "*Lists endpoints, classifies nothing*"],
    ], [0.36, 0.18, 0.46], size=12.5)
    y = callout(slide, y + Inches(0.2),
                "With zero evaluable rules it reports every endpoint as "
                "undetermined - it has not classified anything, it has failed "
                "to, and it says so.", size=14)
    bullets(slide, y + Inches(0.18), [
        ("Without this, a repository-only scan would label every endpoint in a "
         "live service a zombie - confidently, and wrong about all of them.",
         14, True, RED),
    ])


def slide_gate(prs):
    slide = _blank(prs)
    y = heading(slide, "Algorithm 3 - The removal gate",
                "Two independent systems must agree before anything is "
                "cleared")
    y = code(slide, y, [
        "DEFINE assess_removal(verdict, graph, endpoint):",
        "  IF verdict.label is not ZOMBIE:              RETURN blocked",
        "  IF NOT verdict.is_determinate:               RETURN blocked",
        "  IF verdict.vetoed_by_model:                  RETURN blocked",
        "  IF TRAFFIC not in verdict.sources_consulted: RETURN blocked",
        "",
        "  radius <- graph.blast_radius(endpoint)  -- BFS, CALLS | OWNS edges",
        "  IF NOT radius.is_isolated:                   RETURN blocked",
        "  RETURN may_proceed(radius)",
    ])
    note_top = footnote(
        slide,
        "The rules propose; the model may only object. Both opinions are kept "
        "on the verdict, so an auditor sees that the rules proposed removal "
        "and the model blocked it. A test asserts no live endpoint is ever "
        "cleared.")
    picture(slide, y + Inches(0.2), "hybrid-veto",
            bottom=note_top - Inches(0.16))


def slide_dataset(prs):
    slide = _blank(prs)
    y = heading(slide, "The dataset (the jury's first ask)",
                "No public corpus of labelled zombie APIs exists - so we state "
                "exactly what we built")
    y = bullets(slide, y, [
        ("Estates are generated by lifecycle MECHANISM, not by label rule. An "
         "endpoint is put through a story - a product is discontinued, a team "
         "dissolves, a migration stalls, a debug route outlives an incident - "
         "and its features are consequences of that story.", 14, False, INK),
        ("Each estate draws its own observation discipline, so one "
         "organisation's sensor biases cannot be memorised.", 14, False, INK),
        ("Split by estate, never by endpoint: endpoints inside one estate "
         "share its biases, and splitting by endpoint would put those "
         "correlations on both sides of the split.", 14, False, INK),
        ("Two guards enforce, at import level and token level, that true_label "
         "and decay_story never reach detection code.", 14, False, INK),
    ], gap=11)
    callout(slide, y + Inches(0.18),
            "Both guards were written after an early connector was caught "
            "deriving a feature from the answer key - which would have "
            "silently inflated every number in this deck.", size=13.5)
    footnote(slide, "The defensible claim is that the engine recovers known "
                    "decay patterns from partial, disagreeing evidence - never "
                    "that it is validated on production bank data.")


def slide_impl_status(prs):
    slide = _blank(prs)
    y = heading(slide, "Implementation - status against plan",
                "Phases 0-3 of 8 complete: the basis for the 50% claim")
    y = table(slide, y, [
        ["Phase", "Scope", "State"],
        ["0", "Packaging, CLI, CI, strict typing", "Complete"],
        ["1", "Real GitHub scanning - Semgrep AST, git history, CODEOWNERS",
         "Complete"],
        ["2", "Dependency graph, blast radius, removal gate", "Complete"],
        ["3", "Scaled dataset, trained model, SHAP attribution", "Complete"],
        ["4", "Safe Kill Simulation - canary, rollback, audit log", "Next"],
        ["5-6", "REST API and dashboard; CI/CD enforcement plugin", "Planned"],
        ["7-8", "Security hardening, deployment, observability", "Planned"],
    ], [0.10, 0.66, 0.24], size=12.5)
    y = callout(slide, y + Inches(0.18),
                "Phase 4's two preconditions - the dependency graph and the "
                "removal gate - are already in place.", size=14)
    bullets(slide, y + Inches(0.16), [
        ("85 tests  |  three ground-truth leakage guards  |  CI on Python 3.10 "
         "and 3.12  |  strict typing  |  a script that fails the build when a "
         "number in a document stops matching the code.", 13.5, False, INK),
    ])


def slide_demo(prs):
    slide = _blank(prs)
    y = heading(slide, "Implementation - live demo",
                "Everything below runs from a clean clone in under a minute")
    y = code(slide, y, [
        'pip install -e ".[dev,live,ml]"',
        "",
        "apix scan          # six sources -> correlate -> classify -> explain",
        "apix scan --model  # add the learned layer as a veto",
        "apix impact        # dependency graph, blast radius, removal gate",
        "apix benchmark     # the before/after comparative evaluation",
        "apix scan --repo <github-url>   # a real repository, live",
        "pytest             # 85 tests",
    ], size=12.5)
    bullets(slide, y + Inches(0.26), [
        ("Demo order: scan a single zombie end to end -> show its evidence -> "
         "run the benchmark -> restrict the sources and watch the rules "
         "abstain -> scan a real GitHub repository and watch it refuse to make "
         "a lifecycle claim.", 14, False, INK),
        ("Six sources collected, correlated, classified and explained in under "
         "a second.", 14, True, RED),
    ], gap=10)


def slide_results_quality(prs):
    slide = _blank(prs)
    y = heading(slide, "Results - classification quality",
                "25-endpoint synthetic retail-banking estate, known answer key")
    y = table(slide, y, [
        ["Class", "Precision", "Recall", "F1", "Support"],
        ["ACTIVE", "0.923", "1.000", "0.960", "12"],
        ["DEPRECATED", "1.000", "0.667", "0.800", "3"],
        ["ORPHANED", "1.000", "1.000", "1.000", "2"],
        ["ZOMBIE", "1.000", "1.000", "1.000", "8"],
        ["*Macro average*", "*0.981*", "*0.917*", "*0.940*", "*25*"],
    ], [0.28, 0.18, 0.18, 0.18, 0.18], size=13, highlight_last=True)
    y = callout(slide, y + Inches(0.18),
                "Accuracy 0.960 (24/25)   |   zombie recall 1.000   |   zero "
                "live endpoints marked for removal", size=14)
    bullets(slide, y + Inches(0.16), [
        ("The single error is a genuinely DEPRECATED endpoint called ACTIVE - "
         "the one whose team never set the specification flag, which is "
         "exactly what Cassieri [2] and Brito [11] observed in real projects.",
         13.5, False, INK),
        ("Its confidence is 0.803, identical to correct ACTIVEs: confidently "
         "wrong, because the observable evidence genuinely does not "
         "distinguish the cases. Reported as a finding, not tuned away.",
         13.5, False, MUTED),
    ], gap=8)


def slide_results_benchmark(prs):
    slide = _blank(prs)
    y = heading(slide, "Results - the before / after comparison",
                "Identical pipeline code. Only the evidence sources differ.")
    y = table(slide, y, [
        ["Configuration", "Coverage", "Rules usable", "Zombies caught",
         "Recall"],
        ["Gateway registry only", "76.0%", "0 / 15", "0 / 8", "0.0%"],
        ["OpenAPI specification only", "68.0%", "3 / 15", "0 / 8", "0.0%"],
        ["Gateway + spec (conventional)", "76.0%", "5 / 15", "2 / 8", "25.0%"],
        ["*All six, correlated*", "*100%*", "*15 / 15*", "*8 / 8*", "*100%*"],
    ], [0.34, 0.15, 0.17, 0.19, 0.15], size=12.5, highlight_last=True)
    y = callout(slide, y + Inches(0.18),
                "A conventional inventory - a gateway registry plus a "
                "specification, which is what most banks actually have - finds "
                "2 of 8.", size=14)
    bullets(slide, y + Inches(0.16), [
        ("Correlation finds all 8: six endpoints that no conventional approach "
         "could have surfaced.", 14, True, GOOD),
        ("Four of those six carry no authentication at all.", 14, True, RED),
        ("This is the comparative before/after evaluation the first review "
         "asked for, and the basis of the research paper.", 13, False, MUTED),
    ], gap=8)


def slide_results_xai(prs):
    slide = _blank(prs)
    y = heading(slide, "Results - explainability (the jury's third ask)",
                "SHAP values render through the SAME Reason objects the rules "
                "emit")
    y = code(slide, y, [
        "GET /v1/kyc/documents/{id}/raw   ->   ZOMBIE (100%)",
        "   +10.736   last used 3650 days ago",
        "   + 7.692   handler last committed 548 days ago",
        "   + 1.536   0 calls/day",
        "   + 0.136   no owning team recorded",
    ], size=13)
    bullets(slide, y + Inches(0.24), [
        ("This endpoint serves raw identity documents. It is unauthenticated, "
         "documented nowhere, registered nowhere, and has carried no traffic "
         "in six months - while DNS still resolves it.", 14, False, INK),
        ("No single source could have found it. Code alone says it exists but "
         "not that it is exposed. Traffic never saw it. The gateway and the "
         "spec have never heard of it. Only the disagreement identifies it.",
         14, True, RED),
        ("Rule-derived and model-derived reasoning share one type and one "
         "renderer, so a compliance reviewer reads both in the same format.",
         13.5, False, MUTED),
    ], gap=10)


def slide_results_model(prs):
    slide = _blank(prs)
    y = heading(slide, "Results - the learned model, used as a veto",
                "Trained on generated estates; split by estate, never by "
                "endpoint")
    y = table(slide, y, [
        ["On 36 held-out estates", "Rules", "Model"],
        ["Macro-F1", "0.843", "0.861"],
        ["ZOMBIE false positives", "14", "*0*"],
        ["DEPRECATED F1", "0.681", "0.587"],
    ], [0.50, 0.25, 0.25], size=13)
    y = callout(slide, y + Inches(0.18),
                "In aggregate, close. The aggregate hides what "
                "matters.", size=14)
    bullets(slide, y + Inches(0.16), [
        ("A false zombie is an outage. A missed one is a line on a report. So "
         "the model is a veto, not a replacement - it may block a removal, "
         "never create one.", 13.5, False, INK),
        ("The rules propose because they need no training data (day-one "
         "onboarding) and are auditable line by line.", 13.5, False, INK),
        ("The veto's cost is measured, not hidden: on the demo estate it "
         "wrongly blocks one genuine zombie - a debug route with 3 calls/day "
         "that the model reads as still in use. It keeps its ZOMBIE label and "
         "full evidence; it simply does not auto-clear.", 13.5, False, MUTED),
    ], gap=8)


def slide_deliverables(prs):
    slide = _blank(prs)
    y = heading(slide, "Interim Report and Deliverables")
    two_columns(
        slide, y,
        "Submitted for this review", [
            "Interim Report - Chapters 1-3, in the prescribed format",
            "Design Document - structural and behavioural views, prepared "
            "separately and included in the report as Appendix A",
            "Literature Review - 12 papers, all DBLP- or Crossref-validated, "
            "with a traceability matrix to the implementing modules",
            "Working code - repository, CI green, reproducible from a clean "
            "clone",
            "Live demo - scan, impact, benchmark, real repository scan",
        ],
        "Reproducibility", [
            "docs/verify_claims.py fails the build when a documented number "
            "stops matching the running code - 34 figures checked",
            "Every diagram is generated from source",
            "Both Word documents and this deck are generated from Markdown, so "
            "there is one place to edit and nothing can drift",
            "apix benchmark reproduces every result table in this deck",
        ],
        size=12.5,
    )
    footnote(slide, "Documentation drifted from the code three times during "
                    "this project and a human caught it each time. That is why "
                    "the check exists.")


def slide_contribution(prs):
    slide = _blank(prs)
    y = heading(slide, "Individual Contribution",
                "To be confirmed by the team before presenting")
    table(slide, y, [
        ["Member", "Contribution in this phase"],
        ["Shivansh Jindal",
         "Technical lead - architecture, correlation and rule engine, "
         "dependency graph, evaluation harness, repository scanning"],
        ["Jal Bafana", "____________________________________________"],
        ["Arjun Mehta", "____________________________________________"],
        ["Tejas Sahoo", "____________________________________________"],
    ], [0.26, 0.74], size=13, min_lines=2)
    footnote(slide, "Fill these in before the review - the panel evaluates "
                    "individual contribution separately.", colour=RED)


def slide_timeline(prs):
    slide = _blank(prs)
    y = heading(slide, "Progress against the plan",
                "Compared with the schedule submitted at Review 1")
    y = table(slide, y, [
        ["Period", "Planned", "Actual"],
        ["Weeks 1-3", "Ideation, literature survey, synopsis",
         "Done - synopsis and Review 1 deck delivered"],
        ["Weeks 4-5", "Discovery layer - connectors and correlation",
         "Done, and extended to real repository scanning"],
        ["Weeks 6-7", "Classification and evaluation",
         "Done - rules, explanations, comparative benchmark"],
        ["Weeks 8-9", "Dependency graph and removal gate",
         "Done - in-memory and Neo4j backends"],
        ["Weeks 10-11", "Dataset and ML engine",
         "Done - generator, trained model, SHAP"],
        ["Next", "Safe Kill Simulation (Phase 4)",
         "Preconditions in place; starting now"],
    ], [0.16, 0.40, 0.44], size=12)
    callout(slide, y + Inches(0.18),
            "Ahead of the Review 1 plan: real GitHub scanning and the SHAP "
            "layer were both pulled forward from the second half.", size=13.5)
    footnote(slide, "Core complete target: 26 October 2026, with one buffer "
                    "week to 2 November.")


def slide_future(prs):
    slide = _blank(prs)
    y = heading(slide, "Future Extensions")
    bullets(slide, y, [
        ("1.  Safe Kill Simulation (Phase 4, next) - progressive canary "
         "shutdown, automatic rollback on an error-rate breach, and a "
         "hash-chained append-only audit log. This is the step that closes the "
         "gap the literature leaves open.", 14, False, INK),
        ("2.  CI/CD enforcement plugin - block a merge that introduces an "
         "undocumented or unowned endpoint, so the estate stops growing new "
         "zombies.", 14, False, INK),
        ("3.  REST API and React dashboard - the estate, its verdicts and "
         "their evidence, for people who do not live in a terminal.",
         14, False, INK),
        ("4.  Two-tier URL scanner - passive tier (published spec, CT logs, "
         "public DNS) for any URL; active probing only after a DNS TXT record "
         "proves domain ownership.", 14, False, INK),
        ("5.  Comparative research paper - the before/after evaluation already "
         "produces the figures; the engine section is written from measured "
         "results.", 14, False, INK),
        ("6.  Decorator-argument extraction - read deprecated= and "
         "include_in_schema=False directly from the source.", 14, False, INK),
    ], gap=10)


def slide_references(prs):
    slide = _blank(prs)
    y = heading(slide, "References",
                "All validated against DBLP or Crossref; five checked against "
                "full text")
    refs = [
        '[1] D. Caivano, P. Cassieri, S. Romano, G. Scanniello, "On the spread '
        'and evolution of dead methods in Java desktop applications," '
        'Empirical Software Engineering, 28(3), 2023.',
        '[2] P. Cassieri, S. Romano, G. Scanniello, "On deprecated API usages: '
        'an exploratory study of top-starred projects on GitHub," PROFES, '
        '2023.',
        '[3] V. Bushong, D. Das, A. Al Maruf, T. Cerny, "Using static analysis '
        'to address microservice architecture reconstruction," ASE, 2021.',
        '[4] S.-P. Ma, C.-Y. Fan, Y. Chuang, I-H. Liu, C.-W. Lan, "Graph-based '
        'and scenario-driven microservice analysis, retrieval, and testing," '
        'Future Generation Computer Systems, 100, 2019.',
        '[5] A. S. Abdelfattah, T. Cerny, "The microservice dependency '
        'matrix," ESOCC, 2023.',
        '[6] G. Dell\'Immagine, J. Soldani, A. Brogi, "KubeHound: detecting '
        'microservices\' security smells in Kubernetes deployments," Future '
        'Internet, 15(7), 2023.',
        '[7] F. L. Ponce Mella, J. Soldani, C. Taramasco, H. Astudillo, A. '
        'Brogi, "Beyond security: understanding the multiple impacts of '
        'security smells for microservices," CLEI Electronic Journal, 27(2), '
        '2024.',
        '[8] S. M. Lundberg, S.-I. Lee, "A unified approach to interpreting '
        'model predictions," NIPS, 2017.',
        '[9] D. Gaspar, P. Silva, C. Silva, "Explainable AI for intrusion '
        'detection systems: LIME and SHAP applicability on multi-layer '
        'perceptron," IEEE Access, 12, 2024.',
        '[10] Q. Scheitle et al., "The rise of certificate transparency and '
        'its implications on the internet ecosystem," IMC, 2018.',
        '[11] G. Brito, A. Hora, M. T. Valente, R. Robbes, "On the use of '
        'replacement messages in API deprecation: an empirical study," Journal '
        'of Systems and Software, 137, pp. 306-321, 2018.',
        '[12] M. E. Gortney, P. E. Harris, T. Cerny, A. Al Maruf, M. Bures, D. '
        'Taibi, P. Tisnovsky, "Visualizing microservice architecture in the '
        'dynamic perspective: a systematic mapping study," IEEE Access, 10, '
        '2022.',
        '[13] OWASP, "API9:2023 Improper Inventory Management," OWASP API '
        'Security Top 10, 2023.',
        '[14] Reserve Bank of India, "Cyber Security Framework in Banks," '
        'DBS.CO/CSITE/BC.11/33.01.001/2015-16, 2016.',
        '[15] NIST, "Guide to Secure Web Services," SP 800-95, 2007.',
    ]
    total = sum(_height_of(r, 9.5, CONTENT_W / EMU_PER_IN, 3) for r in refs)
    tf = _text(slide, MARGIN, y, CONTENT_W, Emu(total))
    for n, ref in enumerate(refs):
        _line(tf, ref, size=9.5, colour=INK, space_after=3, first=(n == 0))


def slide_thanks(prs):
    slide = _blank(prs)
    tf = _text(slide, MARGIN, Inches(3.4), CONTENT_W, Inches(1.2),
               align=PP_ALIGN.CENTER)
    _line(tf, "Thank You", size=40, bold=True, colour=RED, first=True,
          align=PP_ALIGN.CENTER, space_after=14)
    _line(tf, "Questions", size=18, colour=MUTED, align=PP_ALIGN.CENTER,
          space_after=0)


BUILDERS = [
    slide_title, slide_contents, slide_intro_1, slide_intro_2, slide_problem,
    slide_why_hard, slide_literature, slide_gap, slide_objectives, slide_tools,
    slide_market, slide_design, slide_algo_correlate, slide_algo_classify,
    slide_missing_sources, slide_gate, slide_dataset, slide_impl_status,
    slide_demo, slide_results_quality, slide_results_benchmark,
    slide_results_xai, slide_results_model, slide_deliverables,
    slide_contribution, slide_timeline, slide_future, slide_references,
    slide_thanks,
]


def main() -> int:
    prs = Presentation()
    prs.slide_width = SLIDE_W
    prs.slide_height = SLIDE_H

    for builder in BUILDERS:
        builder(prs)

    prs.save(OUTPUT)
    count = len(prs.slides._sldIdLst)
    print(f"  built {OUTPUT.name}  ({count} slides, "
          f"{round(OUTPUT.stat().st_size / 1024, 1)} KB)")

    if not TEMPLATE.exists():
        print("\n  WARNING: docs/assets/mpstme-template.jpg is missing.")
        print("  Slides were drawn on plain white, without NMIMS branding.")
    if not DIAGRAMS.exists() or not any(DIAGRAMS.glob("*.png")):
        print("\n  NOTE: no rendered diagrams found in docs/diagrams/.")
        print("  Run `python docs/render_diagrams.py` first.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
