"""
Generate the capstone poster: A1 portrait (594 x 841 mm), one slide, exported
to PDF and PNG by PowerPoint. Title, group and mentor, abstract, problem
statement, methodology, results and future work, with diagrams drawn as shapes,
charts from docs/poster_figures.py, and real screenshots of the console.

    python docs/poster_figures.py
    python docs/build_poster.py
"""

from __future__ import annotations

from pathlib import Path

from PIL import Image
from pptx import Presentation
from pptx.dml.color import RGBColor
from pptx.enum.shapes import MSO_SHAPE
from pptx.enum.text import MSO_ANCHOR, PP_ALIGN
from pptx.util import Emu, Inches, Pt

DOCS = Path(__file__).resolve().parent
OUT_DIR = DOCS / "deliverables"
FIG = OUT_DIR / "poster"
OUTPUT = OUT_DIR / "Group_4_Capstone_Poster.pptx"
LOGO = DOCS / "assets" / "logo.png"
TEMPLATE = DOCS / "assets" / "mpstme-template.jpg"
SCREENS = DOCS / "diagrams"

W, H = 23.39, 33.11            # inches: A1 portrait
M, GUT = 0.8, 0.6
COL_W = (W - 2 * M - 2 * GUT) / 3
TOP = 5.25                     # columns start below the header and the team strip
BOTTOM = H - 1.05

RED = RGBColor(0xBC, 0x31, 0x2C)
DARK = RGBColor(0x8E, 0x1F, 0x1B)
INK = RGBColor(0x1C, 0x1F, 0x26)
MUTED = RGBColor(0x55, 0x59, 0x61)
PALE = RGBColor(0xF7, 0xE9, 0xE8)
SHADE = RGBColor(0xF4, 0xF5, 0xF7)
LINE = RGBColor(0xE3, 0xE6, 0xEB)
WHITE = RGBColor(0xFF, 0xFF, 0xFF)
GREEN = RGBColor(0x08, 0x74, 0x4A)
GREEN_BG = RGBColor(0xEC, 0xFD, 0xF3)
RED_BG = RGBColor(0xFE, 0xF1, 0xF0)
FONT = "Calibri"
EMU = 914400


def col_x(i: int) -> float:
    return M + i * (COL_W + GUT)


def box(slide, x, y, w, h, fill=None, line=None, shape=MSO_SHAPE.RECTANGLE, weight=1.0):
    s = slide.shapes.add_shape(shape, Inches(x), Inches(y), Inches(w), Inches(h))
    if fill is None:
        s.fill.background()
    else:
        s.fill.solid()
        s.fill.fore_color.rgb = fill
    if line is None:
        s.line.fill.background()
    else:
        s.line.color.rgb = line
        s.line.width = Pt(weight)
    s.shadow.inherit = False
    return s


def text(slide, x, y, w, h, parts, *, size=20, colour=INK, bold=False, align=PP_ALIGN.LEFT,
         anchor=MSO_ANCHOR.TOP, spacing=1.12, after=6):
    """`parts` is a string, or a list of paragraphs; `**bold**` spans are honoured."""
    tb = slide.shapes.add_textbox(Inches(x), Inches(y), Inches(w), Inches(h))
    tf = tb.text_frame
    tf.word_wrap = True
    tf.vertical_anchor = anchor
    tf.margin_left = tf.margin_right = tf.margin_top = tf.margin_bottom = 0
    paras = [parts] if isinstance(parts, str) else parts
    for n, para in enumerate(paras):
        p = tf.paragraphs[0] if n == 0 else tf.add_paragraph()
        p.alignment = align
        p.line_spacing = spacing
        p.space_after = Pt(after)
        for i, chunk in enumerate(para.split("**")):
            if not chunk:
                continue
            r = p.add_run()
            r.text = chunk
            r.font.name = FONT
            r.font.size = Pt(size)
            r.font.bold = bold or i % 2 == 1
            r.font.color.rgb = colour
    return tb


def lines_of(s: str, size: float, width_in: float) -> int:
    per_line = max(1, int(width_in * 72 / (size * 0.5)))
    return max(1, -(-len(s.replace("**", "")) // per_line))


def para_height(paras, size, width_in, after=6, spacing=1.12) -> float:
    return sum(lines_of(p, size, width_in) * size * spacing / 72 + after / 72 for p in paras)


def picture(slide, path, x, y, w=None, h=None):
    with Image.open(path) as im:
        iw, ih = im.size
    if w is not None and h is None:
        h = w * ih / iw
    elif h is not None and w is None:
        w = h * iw / ih
    slide.shapes.add_picture(str(path), Inches(x), Inches(y), Inches(w), Inches(h))
    return y + h


def section(slide, i_col, y, number, title):
    """A numbered section heading with a rule. Returns the y below it."""
    x = col_x(i_col)
    dot = box(slide, x, y, 0.62, 0.62, fill=RED, shape=MSO_SHAPE.OVAL)
    tf = dot.text_frame
    tf.margin_left = tf.margin_right = tf.margin_top = tf.margin_bottom = 0
    tf.vertical_anchor = MSO_ANCHOR.MIDDLE
    p = tf.paragraphs[0]
    p.alignment = PP_ALIGN.CENTER
    r = p.add_run()
    r.text = str(number)
    r.font.name, r.font.size, r.font.bold, r.font.color.rgb = FONT, Pt(22), True, WHITE
    text(slide, x + 0.8, y - 0.02, COL_W - 0.8, 0.7, title, size=34, colour=RED, bold=True,
         anchor=MSO_ANCHOR.MIDDLE)
    box(slide, x, y + 0.82, COL_W, 0.035, fill=RED)
    return y + 1.08


def body(slide, i_col, y, paras, size=20, after=8):
    h = para_height(paras, size, COL_W, after)
    text(slide, col_x(i_col), y, COL_W, h, paras, size=size, after=after)
    return y + h


def callout(slide, i_col, y, paras, size=20, fill=PALE, edge=RED):
    h = para_height(paras, size, COL_W - 0.6, 4) + 0.36
    box(slide, col_x(i_col), y, COL_W, h, fill=fill)
    box(slide, col_x(i_col), y, 0.09, h, fill=edge)
    text(slide, col_x(i_col) + 0.3, y + 0.18, COL_W - 0.5, h - 0.3, paras, size=size, after=4)
    return y + h


# ---------------------------------------------------------------------------------------
def header(slide):
    box(slide, 0, 0, W, 4.05, fill=RED)
    box(slide, 0, 3.85, W, 0.2, fill=DARK)
    # The institution's mark, from the department's template, on its white card.
    mark = OUT_DIR / "_mpstme_mark_poster.png"
    with Image.open(TEMPLATE) as im:
        im.crop((6, 24, 430, 170)).save(mark)
    box(slide, M, 0.75, 6.1, 2.35, fill=WHITE, shape=MSO_SHAPE.ROUNDED_RECTANGLE)
    picture(slide, mark, M + 0.25, 0.92, w=5.6)
    # The project's mark on the right.
    box(slide, W - M - 2.75, 0.62, 2.75, 2.75, fill=WHITE, shape=MSO_SHAPE.ROUNDED_RECTANGLE)
    picture(slide, LOGO, W - M - 2.6, 0.77, w=2.45)
    cx, cw = M + 6.5, W - 2 * M - 6.5 - 3.15
    text(slide, cx, 0.55, cw, 1.6, "API Exorcist", size=104, colour=WHITE, bold=True,
         align=PP_ALIGN.CENTER, anchor=MSO_ANCHOR.MIDDLE, spacing=0.9)
    text(slide, cx, 2.15, cw, 1.2,
         "Autonomous Discovery and Safe Elimination of Zombie, Shadow and Orphaned APIs",
         size=32, colour=WHITE, align=PP_ALIGN.CENTER, anchor=MSO_ANCHOR.MIDDLE)

    box(slide, 0, 4.05, W, 0.95, fill=SHADE)
    text(slide, M, 4.17, W - 2 * M, 0.75, [
        "**Group 4:** Nakul Hintya (K026)  ·  Shivansh Rohit Jindal (K029)  ·  Dhyey Kharayat (K031)"
        "        **Faculty Mentor:** Dr. Pintu R Shah, Head of Department, CSE (Cyber Security)",
        "B.Tech. Computer Science and Engineering (Cyber Security)  ·  Mukesh Patel School of "
        "Technology Management & Engineering, SVKM's NMIMS, Mumbai  ·  2026–2027",
    ], size=19, align=PP_ALIGN.CENTER, after=2)


def column_one(slide):
    y = section(slide, 0, TOP, 1, "Abstract")
    y = body(slide, 0, y, [
        "Banks expose hundreds of APIs and retire them slowly, or never. Forgotten "
        "**zombie** endpoints stay reachable, unpatched and unmonitored; undocumented "
        "**shadow** endpoints run with no one aware of them. API Exorcist correlates six "
        "independent sources to find them, classifies every endpoint with an explainable "
        "rule engine that abstains when evidence is missing, predicts what a removal would "
        "break, and removes zombies through a shadow window, a named approval and a canary "
        "with automatic rollback, recording every decision in a hash-chained audit log.",
    ]) + 0.3

    y = section(slide, 0, y, 2, "Problem statement")
    y = body(slide, 0, y, [
        "OWASP ranks **Improper Inventory Management** in its API Security Top 10 (API9:2023), "
        "and the RBI's Cyber Security Framework requires an asset inventory. Yet existing tools "
        "read a single source, stop at detection, and cannot tell the four states apart:",
    ]) + 0.1
    rows = [
        ("ACTIVE", "documented, owned, in use", "leave alone", GREEN_BG, GREEN),
        ("DEPRECATED", "announced as retiring", "confirm a date", RGBColor(0xEF, 0xF6, 0xFF),
         RGBColor(0x1D, 0x5F, 0xC4)),
        ("ORPHANED", "in use, but nobody owns it", "assign an owner", RGBColor(0xFF, 0xF4, 0xEC),
         RGBColor(0xC2, 0x41, 0x0C)),
        ("ZOMBIE", "no meaningful use, invisible", "remove safely", RED_BG, RED),
    ]
    for state, meaning, action, bg, fg in rows:
        box(slide, col_x(0), y, COL_W, 0.68, fill=bg)
        text(slide, col_x(0) + 0.2, y, 2.0, 0.68, state, size=19, colour=fg, bold=True,
             anchor=MSO_ANCHOR.MIDDLE)
        text(slide, col_x(0) + 2.2, y, 2.9, 0.68, meaning, size=17, anchor=MSO_ANCHOR.MIDDLE)
        text(slide, col_x(0) + 5.1, y, COL_W - 5.2, 0.68, action, size=17, colour=MUTED,
             anchor=MSO_ANCHOR.MIDDLE)
        y += 0.76
    y = callout(slide, 0, y + 0.2, [
        "**Orphaned and zombie are both unowned; only one is unused.** Removing an orphaned "
        "endpoint is an outage. The task: decide each state from sources that disagree, "
        "predict what a removal breaks, remove without an outage, and explain every decision.",
    ], size=19) + 0.4

    y = section(slide, 0, y, 3, "Key idea: absence is evidence")
    y = body(slide, 0, y, [
        "No single source can find a zombie. It is found where the sources **disagree**. An "
        "endpoint serving raw KYC documents, unauthenticated, on the demo bank:",
    ], size=19) + 0.1
    sources = [("Code", True), ("DNS", True), ("Gateway", False), ("OpenAPI spec", False),
               ("Traffic", False), ("CI/CD", False)]
    tw, th = (COL_W - 0.3) / 3, 0.92
    for n, (name, saw) in enumerate(sources):
        cx, cy = col_x(0) + (n % 3) * (tw + 0.15), y + (n // 3) * (th + 0.15)
        box(slide, cx, cy, tw, th, fill=GREEN_BG if saw else RED_BG,
            line=GREEN if saw else RED, shape=MSO_SHAPE.ROUNDED_RECTANGLE)
        text(slide, cx, cy + 0.08, tw, 0.42, name, size=19, bold=True, align=PP_ALIGN.CENTER)
        text(slide, cx, cy + 0.48, tw, 0.4, "saw it" if saw else "absent", size=16,
             colour=GREEN if saw else RED, bold=True, align=PP_ALIGN.CENTER)
    y += 2 * th + 0.35
    y = callout(slide, 0, y, [
        "Reachable, yet documented, registered, deployed and used **nowhere**: classified "
        "**ZOMBIE**. Its counterfactual: it would be ORPHANED if it carried ten calls a day.",
    ], size=18) + 0.4

    y = section(slide, 0, y, 4, "Built and engineered")
    body(slide, 0, y, [
        "• A browser console, a REST API with hashed tokens and roles, a CLI and a GitHub Action",
        "• Semgrep syntax-tree route extraction: FastAPI, Flask, Express, Spring",
        "• Access-log import: nginx, AWS ALB, Kong, Envoy, Traefik",
        "• 307 Python and 51 dashboard tests, strict typing, CI on every push",
        "• A hardened, read-only container; Prometheus metrics",
    ], size=18, after=6)


def column_two(slide):
    y = section(slide, 1, TOP, 5, "Methodology")
    layers = [
        ("Sources", ["Code", "OpenAPI", "CI/CD", "Gateway", "Traffic", "DNS"]),
        ("Correlate", ["One inventory, 14 discrepancy flags"]),
        ("Decide", ["15 rules,\nabstaining", "Model veto\n+ SHAP", "Dependency\ngraph"]),
        ("Act", ["Removal\ngate", "Safe Kill", "Audit\nchain"]),
        ("Present", ["Console", "REST API", "CI action"]),
    ]
    label_w, row_h = 1.55, 0.98
    for n, (label, parts) in enumerate(layers):
        box(slide, col_x(1), y, COL_W, row_h, fill=SHADE)
        text(slide, col_x(1) + 0.12, y, label_w, row_h, label, size=17, colour=RED, bold=True,
             anchor=MSO_ANCHOR.MIDDLE)
        avail = COL_W - label_w - 0.12
        cw = (avail - 0.08 * (len(parts) - 1)) / len(parts)
        for i, part in enumerate(parts):
            bx = col_x(1) + label_w + i * (cw + 0.08)
            b = box(slide, bx, y + 0.12, cw, row_h - 0.24, fill=WHITE, line=LINE)
            tf = b.text_frame
            tf.margin_left = tf.margin_right = Inches(0.03)
            tf.vertical_anchor = MSO_ANCHOR.MIDDLE
            for k, ln in enumerate(part.split("\n")):
                p = tf.paragraphs[0] if k == 0 else tf.add_paragraph()
                p.alignment = PP_ALIGN.CENTER
                r = p.add_run()
                r.text = ln
                r.font.name, r.font.size, r.font.color.rgb = FONT, Pt(14.5), INK
                r.font.bold = k == 0
        y += row_h
        if n < len(layers) - 1:
            text(slide, col_x(1), y - 0.02, COL_W, 0.24, "▼", size=12, colour=RED,
                 align=PP_ALIGN.CENTER)
            y += 0.22
    y = body(slide, 1, y + 0.25, [
        "Each source is a partial witness; connectors emit observations, never verdicts. "
        "Rules with signed weights decide; a rule whose source was not consulted **abstains**, "
        "so a scan of code alone never labels anything a zombie. A gradient-boosting model "
        "may **veto** a removal, never create one. Every verdict carries its signed reasons, "
        "its full score table, and its **counterfactuals**: what would change it.",
    ], size=18) + 0.35

    y = section(slide, 1, y, 6, "Safe Kill")
    stages = [("Gate", "zombie, and\nnothing calls it"), ("Shadow", "90 days,\nnothing refused"),
              ("Approval", "a named\nperson"), ("Canary", "410 Gone to\n5, 25, 100%"),
              ("Retired", "every step\naudited")]
    sw = COL_W / 5
    for i, (name, note) in enumerate(stages):
        cx = col_x(1) + i * sw + sw / 2
        if i < 4:
            box(slide, cx + 0.32, y + 0.33, sw - 0.64, 0.06, fill=GREEN)
        box(slide, cx - 0.36, y, 0.72, 0.72, fill=GREEN, shape=MSO_SHAPE.OVAL)
        text(slide, cx - 0.36, y, 0.72, 0.72, str(i + 1), size=22, colour=WHITE, bold=True,
             align=PP_ALIGN.CENTER, anchor=MSO_ANCHOR.MIDDLE)
        text(slide, cx - sw / 2, y + 0.82, sw, 0.4, name, size=17, bold=True, align=PP_ALIGN.CENTER)
        text(slide, cx - sw / 2, y + 1.22, sw, 0.8, note, size=13.5, colour=MUTED,
             align=PP_ALIGN.CENTER, spacing=1.0)
    y += 2.15
    y = callout(slide, 1, y, [
        "**Why 90 days:** to be 95% sure of seeing a caller who calls once a month, watch "
        "ln(20) × 30 ≈ 90 days (the rule of three). Traffic whose callers cannot be "
        "identified can **never** be approved: a forgotten partner and an attacker's scanner "
        "look the same on the wire.",
    ], size=17) + 0.4

    y = section(slide, 1, y, 7, "The console")
    shot = SCREENS / "screen-endpoints.png"
    y = picture(slide, shot, col_x(1), y, w=COL_W)
    box(slide, col_x(1), y - (COL_W * 1006 / 1440), COL_W, COL_W * 1006 / 1440, line=LINE)
    y = body(slide, 1, y + 0.12, [
        "A live scan of OWASP crAPI: zombie candidates ranked, the top one's evidence in the "
        "inspector beside the list."], size=15) + 0.25
    y = picture(slide, FIG / "pipelines.png", col_x(1), y, w=COL_W)
    body(slide, 1, y + 0.12, [
        "Safe Kill in the console: a debug endpoint whose callers cannot be identified stops at "
        "approval and can never be approved; a KYC zombie retires through all five stages."],
        size=15)


def column_three(slide):
    y = section(slide, 2, TOP, 8, "Results")
    y = body(slide, 2, y, ["**Zombies found** on a simulated bank with a known answer key:"],
             size=18) + 0.05
    y = picture(slide, FIG / "chart_zombies.png", col_x(2), y, w=COL_W) + 0.15
    stats = [("0.960", "accuracy"), ("1.000", "zombie recall"), ("0", "live endpoints\nmarked for removal")]
    tw = (COL_W - 0.3) / 3
    for i, (v, lab) in enumerate(stats):
        bx = col_x(2) + i * (tw + 0.15)
        box(slide, bx, y, tw, 1.45, fill=SHADE, shape=MSO_SHAPE.ROUNDED_RECTANGLE)
        text(slide, bx, y + 0.1, tw, 0.7, v, size=38, colour=RED, bold=True, align=PP_ALIGN.CENTER)
        text(slide, bx, y + 0.82, tw, 0.6, lab, size=14, colour=MUTED, align=PP_ALIGN.CENTER,
             spacing=1.0)
    y += 1.75
    y = body(slide, 2, y, ["**Safe Kill across 120 generated estates:** the gate alone removes "
                           "49 live endpoints; Safe Kill removes none, and still retires all 793 "
                           "dead ones."], size=18) + 0.05
    y = picture(slide, FIG / "chart_safekill.png", col_x(2), y, w=COL_W) + 0.25

    y = section(slide, 2, y, 9, "Validated on real code")
    stats = [("126/127", "endpoints agree with\nindependent truth lists"),
             ("167/167", "traced to the line\nthat declares them"),
             ("25/25", "candidate reasons\ntrue in the source")]
    for i, (v, lab) in enumerate(stats):
        bx = col_x(2) + i * (tw + 0.15)
        box(slide, bx, y, tw, 1.55, fill=PALE, shape=MSO_SHAPE.ROUNDED_RECTANGLE)
        text(slide, bx, y + 0.1, tw, 0.7, v, size=32, colour=RED, bold=True, align=PP_ALIGN.CENTER)
        text(slide, bx, y + 0.8, tw, 0.7, lab, size=13, colour=MUTED, align=PP_ALIGN.CENTER,
             spacing=1.0)
    y += 1.85
    y = callout(slide, 2, y, [
        "On **OWASP crAPI** the scan ranks first an old OTP check, v2, that accepts any number "
        "of wrong codes, left running beside its fixed v3 that locks after ten; the project's "
        "own web app calls only v3.",
    ], size=17) + 0.4

    y = section(slide, 2, y, 10, "Future work")
    y = body(slide, 2, y, [
        "• A pilot on a real organisation's gateway logs and repositories",
        "• Gateway plugins so the shadow and canary act on live traffic",
        "• Calendar-aware shadow windows for quarterly and annual jobs",
        "• Route extraction for Django, Go, ASP.NET and NestJS",
    ], size=18, after=5) + 0.25

    qr = 2.35
    picture(slide, FIG / "qr_repo.png", col_x(2), y, w=qr)
    text(slide, col_x(2) + qr + 0.3, y + 0.2, COL_W - qr - 0.3, 2.0, [
        "**Source code and documentation**",
        "github.com/shivanshjindal28/api-exorcist",
        "Final report, research paper and design document in the repository.",
    ], size=16, after=6)


def footer(slide):
    box(slide, 0, H - 0.75, W, 0.75, fill=RED)
    text(slide, M, H - 0.75, W - 2 * M, 0.75,
         "The architecture is real code and the repository scans are of real projects; the banking "
         "estate used to measure accuracy is synthetic, with a known answer key.",
         size=16, colour=WHITE, align=PP_ALIGN.CENTER, anchor=MSO_ANCHOR.MIDDLE)


def build() -> Path:
    OUT_DIR.mkdir(exist_ok=True)
    prs = Presentation()
    prs.slide_width, prs.slide_height = Emu(int(W * EMU)), Emu(int(H * EMU))
    slide = prs.slides.add_slide(prs.slide_layouts[6])
    header(slide)
    column_one(slide)
    column_two(slide)
    column_three(slide)
    footer(slide)
    prs.save(OUTPUT)
    return OUTPUT


if __name__ == "__main__":
    print(f"  built {build().name}")
