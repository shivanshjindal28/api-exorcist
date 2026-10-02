"""
Generate submittable Word versions of the project documents.

Why a converter rather than hand-authored .docx
------------------------------------------------
The Markdown files under docs/ are the single source of truth. Maintaining a
separate hand-built Word copy guarantees the two drift apart, and the version a
reviewer reads would slowly stop matching the version the repository documents.
This script regenerates the .docx from the Markdown, so there is exactly one
place to edit.

The converter handles only the subset of Markdown these documents actually use;
it is not a general-purpose implementation and does not try to be.

Usage:
    python docs/build_docx.py                 # build every document
    python docs/build_docx.py literature      # build one

Requires: python-docx. Mermaid diagrams are embedded as images when
docs/diagrams/<name>.png exists (see render_diagrams.py); otherwise a labelled
placeholder is written so the omission is visible rather than silent.
"""

from __future__ import annotations

import re
import sys
from dataclasses import dataclass
from pathlib import Path

from docx import Document
from docx.enum.section import WD_SECTION
from docx.enum.table import WD_TABLE_ALIGNMENT
from docx.enum.text import WD_ALIGN_PARAGRAPH, WD_BREAK, WD_TAB_ALIGNMENT
from docx.oxml import OxmlElement
from docx.oxml.ns import qn
from docx.shared import Inches, Pt, RGBColor

DOCS = Path(__file__).resolve().parent
DIAGRAMS = DOCS / "diagrams"

BODY_FONT = "Times New Roman"
MONO_FONT = "Consolas"
INK = RGBColor(0x1C, 0x1F, 0x26)
MUTED = RGBColor(0x5A, 0x5E, 0x66)
ACCENT = RGBColor(0x8A, 0x4B, 0x12)


# ---------------------------------------------------------------------------
# Document metadata
# ---------------------------------------------------------------------------
@dataclass(frozen=True)
class Style:
    """Type sizes for one document kind, in points.

    The two reference documents use an 11pt body because they are read on
    screen. The interim report uses the sizes the NMIMS report format
    mandates (Annexure A.8): body 12, chapter title 18, section 14,
    subsection 12, figure and table captions 10.
    """

    body: int = 11
    h2: float = 15          # "## " is a chapter title in a report
    h3: float = 12.5        # "### " is a section title
    h4: float = 11.5        # "#### " is a subsection title
    caption: int = 9
    line_spacing: float = 1.15
    chapter_page_break: bool = False


DEFAULT_STYLE = Style()

#: Mandated by the guidelines: Times New Roman, 1.5 spacing, 18/14/12 headings,
#: 12pt body, 10pt figure and table captions, every chapter starting a new page.
REPORT_STYLE = Style(
    body=12,
    h2=18,
    h3=14,
    h4=12,
    caption=10,
    line_spacing=1.5,
    chapter_page_break=True,
)

#: Diagram captions for the design document, in the order the mermaid fences
#: appear. Positional, and must stay in step with NAMES in render_diagrams.py.
#: The interim report does not use this list; it names each figure inline with
#: an explicit `![figure](diagrams/<name>.png "Caption")` directive, which is
#: why inserting a section there cannot silently shift its captions.
DESIGN_CAPTIONS = [
    ("component", "Component diagram: the five architectural layers"),
    ("classes", "Class diagram: core domain model"),
    ("deployment", "Deployment diagram: self-hosted, single tenant"),
    ("sequence-scan", "Sequence diagram: a discovery scan"),
    ("state-lifecycle", "State machine: endpoint lifecycle"),
    ("decision-tree", "Classification decision logic"),
    ("hybrid-veto", "The learned layer as a veto over rule-derived removals"),
    ("state-safekill", "State machine: Safe Kill Simulation"),
    ("dfd", "Data flow diagram: level 1"),
    ("url-tiers", "Two-tier URL scanner"),
]


@dataclass(frozen=True)
class DocSpec:
    key: str
    source: str
    output: str
    title: str
    subtitle: str
    #: "document" -> plain title page + TOC field.
    #: "report"   -> the NMIMS front matter required by Annexure A.8.
    kind: str = "document"
    style: Style = DEFAULT_STYLE
    #: (appendix title, source Markdown, positional captions) appended after
    #: the body, with figure and table numbering continuing across the join.
    appendices: tuple[tuple[str, str, str], ...] = ()


SPECS = [
    DocSpec(
        key="literature",
        source="literature-review.md",
        output="API_Exorcist_Literature_Review.docx",
        title="Literature Review",
        subtitle=(
            "API Exorcist: Autonomous Discovery and Safe Elimination of "
            "Zombie, Shadow and Orphaned APIs"
        ),
    ),
    DocSpec(
        key="design",
        source="design-document.md",
        output="API_Exorcist_Design_Document.docx",
        title="Design Document",
        subtitle=(
            "API Exorcist: Autonomous Discovery and Safe Elimination of "
            "Zombie, Shadow and Orphaned APIs"
        ),
    ),
    DocSpec(
        key="interim",
        source="interim-report.md",
        output="API_Exorcist_Interim_Report.docx",
        title=(
            "API Exorcist: Autonomous Discovery and Safe Elimination of "
            "Zombie, Shadow and Orphaned APIs"
        ),
        subtitle="Interim Report: Chapters 1 to 3",
        kind="report",
        style=REPORT_STYLE,
        # The guidelines ask for the design document to be prepared separately
        # and then included in the report. It is both: its own .docx, and this
        # appendix, built from the same Markdown so they cannot diverge.
        appendices=(
            ("Appendix A: Design Document", "design-document.md", "design"),
        ),
    ),
]

#: Left blank deliberately rather than guessed. Fill these in before printing.
TEAM = [
    ("Shivansh Jindal", "________", "________"),
    ("Jal Bafana", "________", "________"),
    ("Arjun Mehta", "________", "________"),
    ("Tejas Sahoo", "________", "________"),
]
MENTOR = "________________________"
ACADEMIC_YEAR = "2026–2027"
PROGRAM = "B.Tech. Computer Science and Engineering"
STREAM = "Cyber Security"


# ---------------------------------------------------------------------------
# Low-level helpers
# ---------------------------------------------------------------------------
def _set_cell_background(cell, hex_colour: str) -> None:
    shd = OxmlElement("w:shd")
    shd.set(qn("w:val"), "clear")          # never "solid", which renders black
    shd.set(qn("w:color"), "auto")
    shd.set(qn("w:fill"), hex_colour)
    cell._tc.get_or_add_tcPr().append(shd)


def _add_field(paragraph, instruction: str) -> None:
    """Insert a Word field code (used for the TOC and page numbers)."""
    run = paragraph.add_run()
    begin = OxmlElement("w:fldChar")
    begin.set(qn("w:fldCharType"), "begin")
    instr = OxmlElement("w:instrText")
    instr.set(qn("xml:space"), "preserve")
    instr.text = instruction
    sep = OxmlElement("w:fldChar")
    sep.set(qn("w:fldCharType"), "separate")
    placeholder = OxmlElement("w:t")
    placeholder.text = "Right-click and select Update Field"
    end = OxmlElement("w:fldChar")
    end.set(qn("w:fldCharType"), "end")
    for el in (begin, instr, sep, placeholder, end):
        run._r.append(el)


#: Page furniture for the document currently being built. A module-level
#: setting because `_set_orientation` creates sections deep inside diagram
#: rendering, and those sections need the same header and footer as the rest.
PAGE_FURNITURE: dict[str, object] = {
    "footer_align": WD_ALIGN_PARAGRAPH.CENTER,
    "header_left": "",
    "header_right": "",
}


def _add_page_numbers(section) -> None:
    footer = section.footer.paragraphs[0]
    footer.alignment = PAGE_FURNITURE["footer_align"]
    _add_field(footer, "PAGE")
    for run in footer.runs:
        run.font.name = BODY_FONT
        run.font.size = Pt(9)
        run.font.color.rgb = MUTED

    left = str(PAGE_FURNITURE["header_left"])
    right = str(PAGE_FURNITURE["header_right"])
    if not (left or right):
        return

    # One centred tab stop is not enough: the format asks for the title hard
    # left and the academic year hard right, which needs a right-aligned tab
    # at the right margin.
    header = section.header.paragraphs[0]
    header.text = ""
    usable = section.page_width - section.left_margin - section.right_margin
    fmt = header.paragraph_format
    fmt.tab_stops.clear_all()
    fmt.tab_stops.add_tab_stop(usable, WD_TAB_ALIGNMENT.RIGHT)
    run = header.add_run(f"{left}\t{right}")
    run.font.name = BODY_FONT
    run.font.size = Pt(9)
    run.font.color.rgb = MUTED


def _set_page_numbering(section, fmt: str, start: int | None = None) -> None:
    """Set the numeral format for a section ('decimal', 'lowerRoman')."""
    pg = OxmlElement("w:pgNumType")
    pg.set(qn("w:fmt"), fmt)
    if start is not None:
        pg.set(qn("w:start"), str(start))
    section._sectPr.append(pg)


# ---------------------------------------------------------------------------
# Inline formatting
# ---------------------------------------------------------------------------
_INLINE = re.compile(
    r"(\*\*.+?\*\*"        # bold
    r"|\*[^*\n]+?\*"       # italic
    r"|`[^`\n]+?`"         # code
    r"|\[[^\]]+?\]\([^)]+?\))"  # link
)


def add_inline(paragraph, text: str, *, size: int = 11, bold_all: bool = False):
    """Write text into a paragraph, honouring inline Markdown."""
    for part in _INLINE.split(text):
        if not part:
            continue
        run = paragraph.add_run()
        run.font.size = Pt(size)
        run.font.color.rgb = INK
        run.bold = bold_all

        if part.startswith("**") and part.endswith("**"):
            run.text = part[2:-2]
            run.bold = True
            run.font.name = BODY_FONT
        elif part.startswith("`") and part.endswith("`"):
            run.text = part[1:-1]
            run.font.name = MONO_FONT
            run.font.size = Pt(size - 1)
            run.font.color.rgb = ACCENT
        elif part.startswith("*") and part.endswith("*"):
            run.text = part[1:-1]
            run.italic = True
            run.font.name = BODY_FONT
        elif part.startswith("["):
            m = re.match(r"\[([^\]]+?)\]\(([^)]+?)\)", part)
            run.text = m.group(1) if m else part
            run.font.name = BODY_FONT
            run.underline = True
            run.font.color.rgb = ACCENT
        else:
            run.text = part
            run.font.name = BODY_FONT
    return paragraph


# ---------------------------------------------------------------------------
# Block-level rendering
# ---------------------------------------------------------------------------
def add_table(doc, rows: list[list[str]]) -> None:
    if not rows:
        return
    header, *body = rows
    table = doc.add_table(rows=1, cols=len(header))
    table.style = "Table Grid"
    table.alignment = WD_TABLE_ALIGNMENT.CENTER

    for i, text in enumerate(header):
        cell = table.rows[0].cells[i]
        cell.text = ""
        para = cell.paragraphs[0]
        add_inline(para, text, size=10, bold_all=True)
        _set_cell_background(cell, "EFEDE7")

    for row in body:
        cells = table.add_row().cells
        for i, text in enumerate(row[: len(header)]):
            cells[i].text = ""
            add_inline(cells[i].paragraphs[0], text, size=10)

    doc.add_paragraph()


def add_code_block(doc, lines: list[str], language: str = "") -> None:
    para = doc.add_paragraph()
    para.paragraph_format.left_indent = Inches(0.3)
    para.paragraph_format.space_before = Pt(6)
    para.paragraph_format.space_after = Pt(10)
    for i, line in enumerate(lines):
        run = para.add_run(line)
        run.font.name = MONO_FONT
        run.font.size = Pt(9)
        run.font.color.rgb = INK
        if i < len(lines) - 1:
            run.add_break()

    borders = OxmlElement("w:pBdr")
    left = OxmlElement("w:left")
    left.set(qn("w:val"), "single")
    left.set(qn("w:sz"), "18")
    left.set(qn("w:color"), "A9631B")
    borders.append(left)
    para._p.get_or_add_pPr().append(borders)


#: Usable area inside the page margins, portrait and landscape.
PORTRAIT_W, PORTRAIT_H = 6.3, 8.4
LANDSCAPE_W, LANDSCAPE_H = 9.0, 5.9

#: Above this width-to-height ratio a diagram is too wide to stay legible in a
#: portrait column, and gets its own landscape page instead.
WIDE_RATIO = 1.35


def _continue_page_numbering(section) -> None:
    """Drop any inherited page-numbering restart from a new section.

    `add_section` copies the previous section's properties, and the body
    section carries `<w:pgNumType w:start="1"/>` so Chapter 1 begins at page 1.
    Inherited, that restarts the count at every landscape diagram: the finished
    report had page 1 appearing a dozen times and a table of contents that
    pointed at all of them. Removing the element means "carry on".
    """
    sectPr = section._sectPr
    for el in sectPr.findall(qn("w:pgNumType")):
        sectPr.remove(el)


def _set_orientation(doc, landscape: bool) -> None:
    """Start a new section with the given page orientation."""
    from docx.enum.section import WD_ORIENT

    section = doc.add_section(WD_SECTION.NEW_PAGE)
    _continue_page_numbering(section)
    portrait_w, portrait_h = Inches(8.5), Inches(11)
    if landscape:
        section.orientation = WD_ORIENT.LANDSCAPE
        section.page_width, section.page_height = portrait_h, portrait_w
    else:
        section.orientation = WD_ORIENT.PORTRAIT
        section.page_width, section.page_height = portrait_w, portrait_h
    section.top_margin = section.bottom_margin = Inches(0.8)
    section.left_margin = section.right_margin = Inches(1.0)
    _add_page_numbers(section)


def _fit(img_w: int, img_h: int, box_w: float, box_h: float) -> Inches:
    """Largest width that keeps the whole image inside the box."""
    scale = min(box_w / img_w, box_h / img_h)
    return Inches(img_w * scale)


def add_diagram(
    doc, name: str, caption: str, index: int, *, style: Style | None = None
) -> None:
    """Embed a rendered Mermaid diagram, or flag its absence visibly."""
    png = DIAGRAMS / f"{name}.png"
    if png.exists():
        from PIL import Image

        with Image.open(png) as im:
            w, h = im.size
        wide = (w / h) > WIDE_RATIO

        if wide:
            # A wide diagram squeezed into a portrait column renders its labels
            # at roughly 4pt. Give it a landscape page of its own instead.
            _set_orientation(doc, landscape=True)
            width = _fit(w, h, LANDSCAPE_W, LANDSCAPE_H)
        else:
            width = _fit(w, h, PORTRAIT_W, PORTRAIT_H)

        para = doc.add_paragraph()
        para.alignment = WD_ALIGN_PARAGRAPH.CENTER
        para.add_run().add_picture(str(png), width=width)
    else:
        wide = False
        para = doc.add_paragraph()
        para.alignment = WD_ALIGN_PARAGRAPH.CENTER
        run = para.add_run(f"[ Diagram not rendered: {name}.png missing ]")
        run.font.name = MONO_FONT
        run.font.size = Pt(9)
        run.font.color.rgb = RGBColor(0x9B, 0x3B, 0x2E)

    cap = doc.add_paragraph()
    cap.alignment = WD_ALIGN_PARAGRAPH.CENTER
    run = cap.add_run(f"Figure {index}: {caption}")
    run.font.name = BODY_FONT
    run.font.size = Pt((style or DEFAULT_STYLE).caption)
    run.italic = True
    run.font.color.rgb = MUTED

    # Return to portrait so the prose that follows is not stranded sideways.
    if wide:
        _set_orientation(doc, landscape=False)
    else:
        doc.add_paragraph()


# ---------------------------------------------------------------------------
# Markdown parsing
# ---------------------------------------------------------------------------
def strip_status_markers(text: str) -> str:
    """Replace status emoji with words; emoji render inconsistently in Word."""
    return (
        text.replace("✅", "[implemented]")
        .replace("🔵", "[in progress]")
        .replace("⬜", "[designed]")
    )


#: `![figure](diagrams/component.png "Component diagram")` is an explicitly named
#: figure. Preferred over the positional caption list: a section inserted above
#: one of these cannot shift its caption onto a different picture.
_FIGURE = re.compile(r'^!\[[^\]]*\]\(\s*(?:diagrams/)?([\w.-]+?)(?:\.png)?\s*"([^"]*)"\s*\)$')


def render_markdown(
    doc,
    md: str,
    *,
    captions: list[tuple[str, str]] | None = None,
    style: Style = DEFAULT_STYLE,
    figures: list[tuple[int, str]] | None = None,
    tables: list[tuple[int, str]] | None = None,
    figure_start: int = 0,
    table_start: int = 0,
) -> tuple[int, int]:
    """Render Markdown into `doc`.

    `figures` and `tables`, when given, collect (number, caption) pairs for the
    List of Figures and List of Tables. `figure_start` and `table_start`
    continue the numbering of a document appended after another one; the
    running counts are returned so the next append can carry on.
    """
    lines = md.splitlines()
    i = 0
    figure_index = figure_start
    table_index = table_start
    seen_h2 = False
    # Positional captions are indexed by how many mermaid fences this call
    # has seen, not by figure number, which may start above zero.
    mermaid_seen = 0
    captions = captions if captions is not None else DESIGN_CAPTIONS

    while i < len(lines):
        line = strip_status_markers(lines[i].rstrip())

        # --- HTML comment block (editorial notes, never rendered) -----------
        if line.startswith("<!--"):
            while i < len(lines) and "-->" not in lines[i]:
                i += 1
            i += 1
            continue

        # --- table caption --------------------------------------------------
        # `Table: <name>` on its own line, immediately above the table. The
        # format requires the table name *above* the table at 10pt, and this
        # is also what populates the List of Tables.
        if line.startswith("Table: "):
            table_index += 1
            cap = doc.add_paragraph()
            cap.paragraph_format.space_before = Pt(10)
            cap.paragraph_format.space_after = Pt(2)
            caption_text = line[len("Table: "):].strip()
            run = cap.add_run(f"Table {table_index}: {caption_text}")
            run.font.name = BODY_FONT
            run.font.size = Pt(style.caption)
            run.italic = True
            run.font.color.rgb = MUTED
            if tables is not None:
                tables.append((table_index, caption_text))
            i += 1
            continue

        # --- explicitly named figure ---------------------------------------
        fig = _FIGURE.match(line)
        if fig:
            figure_index += 1
            add_diagram(doc, fig.group(1), fig.group(2), figure_index, style=style)
            if figures is not None:
                figures.append((figure_index, fig.group(2)))
            i += 1
            continue

        # --- fenced blocks -------------------------------------------------
        if line.startswith("```"):
            lang = line[3:].strip()
            i += 1
            block: list[str] = []
            while i < len(lines) and not lines[i].startswith("```"):
                block.append(lines[i].rstrip())
                i += 1
            i += 1
            if lang == "mermaid":
                if mermaid_seen < len(captions):
                    name, caption = captions[mermaid_seen]
                else:
                    name, caption = f"diagram-{mermaid_seen}", "Diagram"
                mermaid_seen += 1
                figure_index += 1
                add_diagram(doc, name, caption, figure_index, style=style)
                if figures is not None:
                    figures.append((figure_index, caption))
            else:
                add_code_block(doc, block, lang)
            continue

        # --- tables --------------------------------------------------------
        if line.startswith("|") and i + 1 < len(lines) and set(
            lines[i + 1].replace("|", "").replace(" ", "")
        ) <= {"-", ":"} and lines[i + 1].strip():
            rows: list[list[str]] = []
            while i < len(lines) and lines[i].strip().startswith("|"):
                raw = strip_status_markers(lines[i].strip())
                cells = [c.strip() for c in raw.strip("|").split("|")]
                if set("".join(cells).replace(" ", "")) <= {"-", ":"}:
                    i += 1
                    continue
                rows.append(cells)
                i += 1
            add_table(doc, rows)
            continue

        # --- headings ------------------------------------------------------
        if line.startswith("#"):
            level = len(line) - len(line.lstrip("#"))
            text = line.lstrip("#").strip()
            if level == 1:
                i += 1
                continue  # document title handled by the title page
            if level == 2:
                # The body already starts on a fresh section, so only
                # chapters after the first need a break of their own.
                if style.chapter_page_break and seen_h2:
                    doc.add_paragraph().add_run().add_break(WD_BREAK.PAGE)
                seen_h2 = True
            heading = doc.add_heading(level=min(level - 1, 4))
            heading.paragraph_format.space_before = Pt(14 if level == 2 else 10)
            heading.paragraph_format.space_after = Pt(6)
            for run in heading.runs:
                run.text = ""
            size = {2: style.h2, 3: style.h3}.get(level, style.h4)
            add_inline(heading, text, size=size, bold_all=True)
            for run in heading.runs:
                run.font.color.rgb = INK
            i += 1
            continue

        # --- horizontal rule ------------------------------------------------
        if line.strip() in ("---", "***", "___"):
            i += 1
            continue

        # --- blockquote -----------------------------------------------------
        if line.startswith(">"):
            quote_lines = []
            while i < len(lines) and lines[i].startswith(">"):
                quote_lines.append(strip_status_markers(lines[i].lstrip("> ").rstrip()))
                i += 1
            para = doc.add_paragraph()
            para.paragraph_format.left_indent = Inches(0.4)
            para.paragraph_format.space_before = Pt(6)
            para.paragraph_format.space_after = Pt(8)
            para.paragraph_format.line_spacing = style.line_spacing
            add_inline(para, " ".join(quote_lines), size=style.body)
            for run in para.runs:
                run.italic = True
            continue

        # --- lists ----------------------------------------------------------
        bullet = re.match(r"^(\s*)[-*]\s+(.*)", line)
        number = re.match(r"^(\s*)(\d+)\.\s+(.*)", line)
        if bullet or number:
            # Not `style`: that name is the Style parameter of this function.
            list_style = "List Bullet" if bullet else "List Number"
            text = bullet.group(2) if bullet else number.group(3)
            para = doc.add_paragraph(style=list_style)
            para.paragraph_format.space_after = Pt(3)
            para.paragraph_format.line_spacing = style.line_spacing
            add_inline(para, text, size=style.body)
            i += 1
            continue

        # --- blank ----------------------------------------------------------
        if not line.strip():
            i += 1
            continue

        # --- paragraph (join continuation lines) ------------------------------
        buf = [line]
        i += 1
        while i < len(lines):
            nxt = lines[i].rstrip()
            if (
                not nxt.strip()
                or nxt.startswith(("#", "|", ">", "```", "---"))
                or re.match(r"^(\s*)([-*]|\d+\.)\s+", nxt)
            ):
                break
            buf.append(strip_status_markers(nxt))
            i += 1
        para = doc.add_paragraph()
        para.alignment = WD_ALIGN_PARAGRAPH.JUSTIFY
        para.paragraph_format.space_after = Pt(8)
        para.paragraph_format.line_spacing = style.line_spacing
        add_inline(para, " ".join(buf), size=style.body)

    return figure_index, table_index


# ---------------------------------------------------------------------------
# Report front matter (NMIMS Annexure A.8)
# ---------------------------------------------------------------------------
def _centred(doc, text: str, size: int, *, bold: bool = False,
             colour=INK, italic: bool = False, space_after: int = 6):
    para = doc.add_paragraph()
    para.alignment = WD_ALIGN_PARAGRAPH.CENTER
    para.paragraph_format.space_after = Pt(space_after)
    run = para.add_run(text)
    run.font.name = BODY_FONT
    run.font.size = Pt(size)
    run.bold = bold
    run.italic = italic
    run.font.color.rgb = colour
    return para


def _page_break(doc) -> None:
    doc.add_paragraph().add_run().add_break(WD_BREAK.PAGE)


def _listing(doc, heading: str, rows: list[tuple[int, str]], label: str) -> None:
    """List of Figures / List of Tables."""
    _centred(doc, heading, 16, bold=True, space_after=12)
    if not rows:
        _centred(doc, "(none)", 11, colour=MUTED)
        _page_break(doc)
        return
    add_table(
        doc,
        [
            [f"{label} No.", f"Name of the {label.lower()}", "Page No."],
            *([f"{label} {n}", caption, ""] for n, caption in rows),
        ],
    )
    _page_break(doc)


def _front_matter(doc, spec: DocSpec, figures, tables) -> None:
    # ---- title page ----
    for _ in range(3):
        doc.add_paragraph()
    _centred(doc, spec.title, 22, bold=True, space_after=18)
    _centred(doc, "Project Report submitted in the partial fulfilment", 12)
    _centred(doc, "of", 12)
    _centred(doc, PROGRAM, 12, bold=True)
    _centred(doc, "in", 12)
    _centred(doc, STREAM, 12, bold=True, space_after=18)
    _centred(doc, "by", 12, space_after=10)
    for name, roll, _sap in TEAM:
        _centred(doc, f"{name}  ({roll})", 12, space_after=2)
    doc.add_paragraph()
    _centred(doc, "Under the supervision of", 12)
    _centred(doc, MENTOR, 12, bold=True)
    _centred(doc, "(Designation, Department, MPSTME)", 10, colour=MUTED,
             space_after=18)
    _centred(doc, "Mukesh Patel School of Technology Management & Engineering",
             12, bold=True)
    _centred(doc, "SVKM's NMIMS University (Deemed-to-be University)", 11)
    _centred(doc, "Vile Parle (W), Mumbai - 400056", 11)
    _centred(doc, ACADEMIC_YEAR, 11, space_after=0)
    _page_break(doc)

    # ---- certificate ----
    _centred(doc, "SVKM's NMIMS University", 14, bold=True, space_after=2)
    _centred(doc, "(Deemed-to-be University)", 11, colour=MUTED)
    _centred(doc, "MUKESH PATEL SCHOOL OF TECHNOLOGY MANAGEMENT & ENGINEERING",
             12, bold=True, space_after=2)
    _centred(doc, "Vile Parle (W), Mumbai-56", 11, colour=MUTED)
    _centred(doc, f"({ACADEMIC_YEAR})", 11, colour=MUTED, space_after=18)
    _centred(doc, "CERTIFICATE", 16, bold=True, space_after=18)

    body = doc.add_paragraph()
    body.alignment = WD_ALIGN_PARAGRAPH.JUSTIFY
    body.paragraph_format.line_spacing = 1.5
    names = ", ".join(n for n, _r, _s in TEAM)
    add_inline(
        body,
        f'This is to certify that the project entitled "{spec.title}" has been '
        f"done by {names} under my guidance and supervision, and has been "
        f"submitted in partial fulfilment of the degree of {PROGRAM} in "
        f"{STREAM} of MPSTME, SVKM's NMIMS (Deemed-to-be University), Mumbai, "
        "India.",
        size=12,
    )
    for _ in range(4):
        doc.add_paragraph()
    add_table(
        doc,
        [
            ["Project mentor (Internal Guide)", "Examiner"],
            ["\n\nName and Signature", "\n\nName and Signature"],
            ["Date:", "Date:"],
            ["Place: Mumbai", "Head of Department"],
        ],
    )
    _page_break(doc)

    # ---- acknowledgement ----
    _centred(doc, "ACKNOWLEDGEMENT", 16, bold=True, space_after=14)
    ack = doc.add_paragraph()
    ack.alignment = WD_ALIGN_PARAGRAPH.JUSTIFY
    ack.paragraph_format.line_spacing = 1.5
    add_inline(
        ack,
        "We thank our faculty mentor for the guidance and for the critical "
        "questioning that shaped this work, and the review panel whose "
        "observations at the first review directed the dataset, explainability "
        "and comparative-evaluation strands of the project. We also thank the "
        "Department of Computer Engineering, MPSTME, for the resources made "
        "available to us.",
        size=12,
    )
    doc.add_paragraph()
    add_table(
        doc,
        [["NAME", "ROLL NO.", "SAP ID"], *(list(m) for m in TEAM)],
    )
    _page_break(doc)

    # ---- abstract ----
    _centred(doc, "ABSTRACT", 16, bold=True, space_after=14)
    for para_text in ABSTRACT:
        para = doc.add_paragraph()
        para.alignment = WD_ALIGN_PARAGRAPH.JUSTIFY
        para.paragraph_format.line_spacing = 1.5
        para.paragraph_format.space_after = Pt(8)
        add_inline(para, para_text, size=12)
    _page_break(doc)

    # ---- table of contents ----
    _centred(doc, "Table of Contents", 16, bold=True, space_after=12)
    _add_field(doc.add_paragraph(), r'TOC \o "1-3" \h \z \u')
    _page_break(doc)

    _listing(doc, "List of Figures", figures, "Figure")
    _listing(doc, "List of Tables", tables, "Table")

    _centred(doc, "Abbreviations", 16, bold=True, space_after=12)
    add_table(doc, [["Abbreviation", "Expansion"], *ABBREVIATIONS])


#: Roughly one page, as the format asks: the problem, the approach, the result.
ABSTRACT = [
    "Banking API estates accumulate endpoints that remain deployed and "
    "network-reachable long after they have ceased to serve any purpose. Such "
    "endpoints retain their database credentials, their network routes and "
    "their access to production data while disappearing from the "
    "organisation's inventory. This is the condition OWASP catalogues as API9:2023 "
    "Improper Inventory Management, and one that the Reserve Bank of India's "
    "Cyber Security Framework in Banks makes an explicit compliance concern. "
    "The difficulty is that no single source of evidence can identify them. A "
    "gateway registry cannot see a service addressed directly; an API "
    "specification cannot describe a route the team forgot to document; "
    "traffic capture cannot observe an endpoint that nothing called during the "
    "capture window; and static analysis of source code establishes that an "
    "endpoint exists but never that anything calls it.",

    "This report presents API Exorcist, a system that determines an endpoint's "
    "true lifecycle state by correlating six independent and deliberately "
    "imperfect discovery sources: source code, DNS, API gateway, CI/CD "
    "pipeline records, traffic capture and OpenAPI specifications. The central "
    "design principle is that a zombie endpoint is identified not by any one "
    "source but by a pattern of *disagreement* between them, and that the "
    "absence of an observation is itself evidence, provided the system can "
    "distinguish a source that saw nothing from a source that was never "
    "consulted. Fifteen weighted evidence rules classify each endpoint as "
    "ACTIVE, DEPRECATED, ORPHANED or ZOMBIE, and a rule whose required source "
    "was never consulted abstains rather than firing, so a partial deployment "
    "reports what it cannot determine instead of guessing. Every verdict "
    "carries the complete set of signed evidence contributions that produced "
    "it. A dependency graph computes the blast radius of a proposed removal, "
    "and an endpoint is cleared only when the classifier and the graph agree "
    "independently.",

    "On a generated twenty-five-endpoint retail-banking estate with a known "
    "answer key, the system achieves 0.960 accuracy and 0.940 macro-F1 with "
    "perfect zombie recall and no live endpoint marked for removal. Under the "
    "same pipeline restricted to a conventional gateway-plus-specification "
    "inventory, two of eight zombies are found; correlating all six sources "
    "finds all eight, four of which carry no authentication at all. A "
    "gradient-boosted model with exact SHAP attribution is layered over the "
    "rules as a veto, in that it may block a proposed removal and never create one, "
    "because on held-out estates it produces no false zombies where the rules "
    "produce seventeen. The architecture and the analysis are real code; the "
    "estate they are measured against is synthetic, and the claim made is that "
    "the engine recovers known decay patterns from partial and disagreeing "
    "evidence, not that it has been validated against production bank traffic.",
]

ABBREVIATIONS = [
    ["API", "Application Programming Interface"],
    ["AST", "Abstract Syntax Tree"],
    ["BFS", "Breadth-First Search"],
    ["CI/CD", "Continuous Integration / Continuous Deployment"],
    ["CT", "Certificate Transparency"],
    ["CTE", "Common Table Expression"],
    ["DFD", "Data Flow Diagram"],
    ["DNS", "Domain Name System"],
    ["F1", "Harmonic mean of precision and recall"],
    ["IDS", "Intrusion Detection System"],
    ["KYC", "Know Your Customer"],
    ["OWASP", "Open Worldwide Application Security Project"],
    ["RBI", "Reserve Bank of India"],
    ["REST", "Representational State Transfer"],
    ["SHAP", "SHapley Additive exPlanations"],
    ["TTL", "Time To Live"],
    ["XAI", "Explainable Artificial Intelligence"],
]


# ---------------------------------------------------------------------------
def _build_report(spec: DocSpec) -> Path:
    """The interim report: NMIMS front matter, roman-then-decimal paging."""
    md = (DOCS / spec.source).read_text(encoding="utf-8")

    PAGE_FURNITURE["footer_align"] = WD_ALIGN_PARAGRAPH.RIGHT
    PAGE_FURNITURE["header_left"] = "API Exorcist"
    PAGE_FURNITURE["header_right"] = ACADEMIC_YEAR

    doc = Document()
    normal = doc.styles["Normal"]
    normal.font.name = BODY_FONT
    normal.font.size = Pt(spec.style.body)

    front = doc.sections[0]
    front.top_margin = front.bottom_margin = front.right_margin = Inches(1)
    front.left_margin = Inches(1.5)          # the format asks for 1.5" here
    _add_page_numbers(front)
    _set_page_numbering(front, "lowerRoman", start=1)

    # Figures and tables are collected in a dry run so that the List of
    # Figures can be written before the body it describes.
    figures: list[tuple[int, str]] = []
    tables: list[tuple[int, str]] = []
    _render_all(Document(), spec, md, figures=figures, tables=tables)

    _front_matter(doc, spec, figures, tables)

    # Chapter 1 onward restarts at 1 in decimal, as the format requires.
    body = doc.add_section(WD_SECTION.NEW_PAGE)
    body.top_margin = body.bottom_margin = body.right_margin = Inches(1)
    body.left_margin = Inches(1.5)
    _add_page_numbers(body)
    _set_page_numbering(body, "decimal", start=1)

    _render_all(doc, spec, md)

    out = DOCS / spec.output
    doc.save(out)
    return out


def _render_all(doc, spec: DocSpec, md: str, *, figures=None, tables=None) -> None:
    """The report body, then each appendix, with numbering carried across."""
    n_fig, n_tab = render_markdown(
        doc, md, captions=[], style=spec.style, figures=figures, tables=tables,
    )
    for title, source, caption_set in spec.appendices:
        doc.add_paragraph().add_run().add_break(WD_BREAK.PAGE)
        heading = doc.add_heading(level=1)
        for run in heading.runs:
            run.text = ""
        add_inline(heading, title, size=spec.style.h2, bold_all=True)
        for run in heading.runs:
            run.font.color.rgb = INK

        captions = DESIGN_CAPTIONS if caption_set == "design" else []
        n_fig, n_tab = render_markdown(
            doc,
            (DOCS / source).read_text(encoding="utf-8"),
            captions=captions,
            style=spec.style,
            figures=figures,
            tables=tables,
            figure_start=n_fig,
            table_start=n_tab,
        )


def build(spec: DocSpec) -> Path:
    if spec.kind == "report":
        return _build_report(spec)

    md = (DOCS / spec.source).read_text(encoding="utf-8")

    PAGE_FURNITURE["footer_align"] = WD_ALIGN_PARAGRAPH.CENTER
    PAGE_FURNITURE["header_left"] = ""
    PAGE_FURNITURE["header_right"] = ""

    doc = Document()
    style = doc.styles["Normal"]
    style.font.name = BODY_FONT
    style.font.size = Pt(11)

    section = doc.sections[0]
    section.top_margin = Inches(1)
    section.bottom_margin = Inches(1)
    section.left_margin = Inches(1.1)
    section.right_margin = Inches(1.1)
    _add_page_numbers(section)

    # ---- title page ----
    for _ in range(5):
        doc.add_paragraph()
    t = doc.add_paragraph()
    t.alignment = WD_ALIGN_PARAGRAPH.CENTER
    run = t.add_run(spec.title)
    run.font.name = BODY_FONT
    run.font.size = Pt(30)
    run.bold = True
    run.font.color.rgb = INK

    s = doc.add_paragraph()
    s.alignment = WD_ALIGN_PARAGRAPH.CENTER
    run = s.add_run(spec.subtitle)
    run.font.name = BODY_FONT
    run.font.size = Pt(13)
    run.font.color.rgb = MUTED

    doc.add_paragraph()
    meta = doc.add_paragraph()
    meta.alignment = WD_ALIGN_PARAGRAPH.CENTER
    run = meta.add_run(
        "B.Tech. Computer Science and Engineering (Cyber Security)\n"
        "Mukesh Patel School of Technology Management & Engineering\n"
        "NMIMS University\n\n"
        "2026–2027"
    )
    run.font.name = BODY_FONT
    run.font.size = Pt(11)
    run.font.color.rgb = INK

    doc.add_paragraph().add_run().add_break(WD_BREAK.PAGE)

    # ---- table of contents ----
    h = doc.add_paragraph()
    run = h.add_run("Table of Contents")
    run.font.name = BODY_FONT
    run.font.size = Pt(16)
    run.bold = True
    run.font.color.rgb = INK
    doc.add_paragraph()
    _add_field(doc.add_paragraph(), r'TOC \o "1-3" \h \z \u')
    doc.add_paragraph().add_run().add_break(WD_BREAK.PAGE)

    # ---- body ----
    render_markdown(doc, md)

    out = DOCS / spec.output
    doc.save(out)
    return out


def main() -> int:
    wanted = sys.argv[1:] or [s.key for s in SPECS]
    missing_diagrams = not DIAGRAMS.exists() or not any(DIAGRAMS.glob("*.png"))

    for spec in SPECS:
        if spec.key not in wanted:
            continue
        out = build(spec)
        size_kb = round(out.stat().st_size / 1024, 1)
        print(f"  built {out.name}  ({size_kb} KB)")

    if missing_diagrams:
        print()
        print("  NOTE: no rendered diagrams found in docs/diagrams/.")
        print("  Run `python docs/render_diagrams.py` first, or the design")
        print("  document will contain placeholders where figures belong.")
    print()
    print("  Open in Word and right-click the Table of Contents ->")
    print("  Update Field to populate page numbers.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
