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
    DocSpec(
        key="final",
        source="final-report.md",
        # The submission instructions fix the name: groupNo_Capstone_final_report.
        output="",          # filled from GROUP_NO in final_output()
        title=(
            "API Exorcist: Autonomous Discovery and Safe Elimination of "
            "Zombie, Shadow and Orphaned APIs"
        ),
        subtitle="Capstone Project Final Report",
        kind="report",
        style=REPORT_STYLE,
        # Its appendices are chapters of final-report.md itself (A to D, in the
        # order the guidelines' table of contents gives), not separate files.
    ),
]

#: The interim report was built before the team details were confirmed, and
#: is frozen; it keeps these blanks.
INTERIM_TEAM = [
    ("Shivansh Jindal", "________", "________"),
    ("Jal Bafana", "________", "________"),
    ("Arjun Mehta", "________", "________"),
    ("Tejas Sahoo", "________", "________"),
]
INTERIM_MENTOR = "________________________"
INTERIM_MENTOR_DESIGNATION = "(Designation, Department, MPSTME)"

#: The final report: (name, roll no., SAP ID), as confirmed by the team.
GROUP_NO = "Group_4"
TEAM = [
    ("Nakul Hintya", "K026", "70102300049"),
    ("Shivansh Rohit Jindal", "K029", "70102300028"),
    ("Dhyey Kharayat", "K031", "70102300012"),
]
MENTOR = "Dr. Pintu R Shah"
MENTOR_DESIGNATION = (
    "(Head of Department, Computer Science & Engineering (Cyber Security), MPSTME)"
)
SCHOOL = "Mukesh Patel School of Technology Management & Engineering (Mumbai Campus)"
DEPARTMENT = "Computer Science & Engineering (Cyber Security) Department"


def final_output() -> str:
    return f"{GROUP_NO}_Capstone_final_report.docx"
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
    # Page geometry in inches. None keeps the original behaviour (US Letter,
    # 1" sides on diagram sections) that the interim report was built with;
    # the final report sets A4 and keeps the 1.5" binding margin on every page.
    "page": None,
}

#: A4, with the margins the guidelines mandate: 1.5" on the binding edge,
#: 1" elsewhere. On a landscape page the binding edge is the top.
A4_REPORT = {"w": 8.27, "h": 11.69, "binding": 1.5, "other": 1.0}


def _add_page_numbers(section) -> None:
    # A new section's footer is linked to the previous one, so this paragraph
    # is usually the same shared paragraph every earlier call wrote into.
    # Clearing it first is what keeps one PAGE field: without it, every
    # landscape diagram added another, and the printed report showed each page
    # number eighteen times over ("2222222...").
    if PAGE_FURNITURE["page"] is not None:
        # Linked, every section shares the first section's header, whose
        # right tab is sized for a portrait column: on a landscape page the
        # year printed mid-page. Each section gets its own, sized to itself.
        section.header.is_linked_to_previous = False
        section.footer.is_linked_to_previous = False
    footer = section.footer.paragraphs[0]
    footer.text = ""
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
    if PAGE_FURNITURE["page"] is not None:
        # The Header style carries its own stops (centre 3.25", right 6.5"),
        # which clear_all() does not touch: the tab landed on the centre stop
        # and the year printed mid-page. Clear them explicitly.
        fmt.tab_stops.add_tab_stop(Inches(3.25), WD_TAB_ALIGNMENT.CLEAR)
        fmt.tab_stops.add_tab_stop(Inches(6.5), WD_TAB_ALIGNMENT.CLEAR)
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

    if PAGE_FURNITURE["page"] is not None:
        _size_columns(doc, table, rows)
        _keep_table_together(table)
    doc.add_paragraph()


def _keep_table_together(table) -> None:
    """A header row is never left alone at the foot of a page.

    The header keeps with the first data row, repeats at the top of every page
    a long table runs onto, and no row splits across a page. Without this a
    table starting low on a page left its header stranded there.
    """
    for r, row in enumerate(table.rows):
        tr_pr = row._tr.get_or_add_trPr()
        tr_pr.append(OxmlElement("w:cantSplit"))
        if r == 0:
            tr_pr.append(OxmlElement("w:tblHeader"))
            for cell in row.cells:
                for p in cell.paragraphs:
                    p.paragraph_format.keep_with_next = True


def _size_columns(doc, table, rows: list[list[str]]) -> None:
    """Give each column room in proportion to what it holds.

    Equal columns broke short headers mid-word ("Repositor / y") while long
    prose columns ran to a dozen lines. A column needs at least its longest
    word, and beyond that space in proportion to how much text it carries.
    """
    ncols = len(rows[0])

    def plain(s: str) -> str:
        return re.sub(r"[*`]|\[([^\]]*)\]\([^)]*\)", r"\1", s)

    # Each column first gets its longest word (capped, so one long name such
    # as a repository slug cannot starve the rest), then the remaining width
    # is shared in proportion to how much text the column carries.
    char_in = 0.085                          # one bold 10pt character, roughly
    minimum, share = [], []
    for j in range(ncols):
        col = [plain(r[j]) for r in rows if j < len(r)]
        longest_word = max((len(w) for c in col for w in c.split()), default=4)
        minimum.append(min(longest_word, 14) * char_in + 0.15)
        share.append(sum(len(c) for c in col) / max(len(col), 1))
    s = doc.sections[-1]
    usable = (s.page_width - s.left_margin - s.right_margin) / 914400
    if sum(minimum) > usable:
        # Many columns: never wider than the text block. Take the excess from
        # the wide columns only (long names and prose wrap well); a short
        # header such as "Truth" broken mid-word is unreadable.
        floor = 0.8
        excess = sum(minimum) - usable
        room = sum(max(m - floor, 0) for m in minimum) or 1
        minimum = [m - excess * max(m - floor, 0) / room for m in minimum]
    spare = max(usable - sum(minimum), 0)
    total = sum(share) or 1
    table.autofit = False
    for j in range(ncols):
        width = Inches(minimum[j] + spare * share[j] / total)
        for row in table.rows:
            row.cells[j].width = width


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
    page = PAGE_FURNITURE["page"]
    if isinstance(page, dict):
        _apply_page(section, page, landscape=landscape)
        _add_page_numbers(section)
        return
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


def _apply_page(section, page: dict, *, landscape: bool = False) -> None:
    """Size and margins for one section of a report with fixed page geometry."""
    from docx.enum.section import WD_ORIENT

    w, h = Inches(page["w"]), Inches(page["h"])
    bind, other = Inches(page["binding"]), Inches(page["other"])
    if landscape:
        section.orientation = WD_ORIENT.LANDSCAPE
        section.page_width, section.page_height = h, w
        # Turned to read, the bound edge of a landscape page is its top.
        section.top_margin = bind
        section.bottom_margin = section.left_margin = section.right_margin = other
    else:
        section.orientation = WD_ORIENT.PORTRAIT
        section.page_width, section.page_height = w, h
        section.left_margin = bind
        section.top_margin = section.bottom_margin = section.right_margin = other


def _box(doc, landscape: bool) -> tuple[float, float]:
    """Room for a figure, in inches, inside the current section's margins."""
    if PAGE_FURNITURE["page"] is None:
        return (LANDSCAPE_W, LANDSCAPE_H) if landscape else (PORTRAIT_W, PORTRAIT_H)
    s = doc.sections[-1]
    emu = 914400
    w = (s.page_width - s.left_margin - s.right_margin) / emu
    h = (s.page_height - s.top_margin - s.bottom_margin) / emu
    # Leave room for the caption under the figure.
    return w, h - 0.8


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
            width = _fit(w, h, *_box(doc, landscape=True))
        else:
            width = _fit(w, h, *_box(doc, landscape=False))

        para = doc.add_paragraph()
        para.alignment = WD_ALIGN_PARAGRAPH.CENTER
        # A figure and its caption are one unit: never split across a page.
        para.paragraph_format.keep_with_next = True
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
            cap.paragraph_format.keep_with_next = True   # never orphaned above its table
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
            text = bullet.group(2) if bullet else number.group(3)
            # An item continues on the indented lines that follow it. Read as
            # separate paragraphs, they printed as a stray, oddly indented
            # block under a one-line item.
            i += 1
            while i < len(lines):
                nxt = lines[i].rstrip()
                if (not nxt.strip() or not nxt.startswith(" ")
                        or re.match(r"^\s*([-*]|\d+\.)\s+", nxt)):
                    break
                text += " " + strip_status_markers(nxt.strip())
                i += 1
            if bullet:
                # Not `style`: that name is the Style parameter of this function.
                para = doc.add_paragraph(style="List Bullet")
            else:
                # The number is written, not left to Word's "List Number"
                # style, which counts across the whole document: the second
                # list in the report began at 30.
                para = doc.add_paragraph()
                para.paragraph_format.left_indent = Inches(0.35)
                para.paragraph_format.first_line_indent = Inches(-0.3)
                para.add_run(f"{number.group(2)}.\t").font.size = Pt(style.body)
                para.paragraph_format.tab_stops.add_tab_stop(Inches(0.35))
            para.paragraph_format.space_after = Pt(3)
            para.paragraph_format.line_spacing = style.line_spacing
            add_inline(para, text, size=style.body)
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
    final = spec.key == "final"
    team = TEAM if final else INTERIM_TEAM
    mentor = MENTOR if final else INTERIM_MENTOR
    designation = MENTOR_DESIGNATION if final else INTERIM_MENTOR_DESIGNATION
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
    for name, roll, _sap in team:
        _centred(doc, f"{name}  ({roll})", 12, space_after=2)
    doc.add_paragraph()
    _centred(doc, "Under the supervision of", 12)
    _centred(doc, mentor, 12, bold=True)
    _centred(doc, designation, 10, colour=MUTED, space_after=18)
    if final:
        _centred(doc, SCHOOL, 12, bold=True)
        _centred(doc, DEPARTMENT.upper(), 11)
    else:
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
    if final:
        _centred(doc, DEPARTMENT.upper(), 11, space_after=2)
    _centred(doc, "Vile Parle (W), Mumbai-56", 11, colour=MUTED)
    _centred(doc, f"({ACADEMIC_YEAR})", 11, colour=MUTED, space_after=18)
    _centred(doc, "CERTIFICATE", 16, bold=True, space_after=18)

    body = doc.add_paragraph()
    body.alignment = WD_ALIGN_PARAGRAPH.JUSTIFY
    body.paragraph_format.line_spacing = 1.5
    names = ", ".join(n for n, _r, _s in team)
    if final and len(team) > 1:
        names = ", ".join(n for n, _r, _s in team[:-1]) + " and " + team[-1][0]
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
            [f"\n\n{mentor}\nSignature" if final else "\n\nName and Signature",
             "\n\nName and Signature"],
            ["Date:", "Date:"],
            ["Place: Mumbai",
             f"Head of Department\n\n\n{mentor}\nSignature" if final
             else "Head of Department"],
        ],
    )
    _page_break(doc)

    # ---- acknowledgement ----
    _centred(doc, "ACKNOWLEDGEMENT", 16, bold=True, space_after=14)
    ack = doc.add_paragraph()
    ack.alignment = WD_ALIGN_PARAGRAPH.JUSTIFY
    ack.paragraph_format.line_spacing = 1.5
    add_inline(ack, ACKNOWLEDGEMENTS.get(spec.key, ACKNOWLEDGEMENTS["interim"]),
               size=12)
    doc.add_paragraph()
    add_table(
        doc,
        [["NAME", "ROLL NO.", "SAP ID"], *(list(m) for m in team)],
    )
    _page_break(doc)

    # ---- abstract ----
    _centred(doc, "ABSTRACT", 16, bold=True, space_after=14)
    for para_text in ABSTRACTS.get(spec.key, ABSTRACT):
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
    add_table(doc, [["Abbreviation", "Expansion"],
                    *ABBREVIATION_SETS.get(spec.key, ABBREVIATIONS)])


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

#: The interim report is the frozen Review 2 submission, so its front matter
#: keeps the constants above unchanged; the final report has its own.
ACKNOWLEDGEMENTS = {
    "interim": (
        "We thank our faculty mentor for the guidance and for the critical "
        "questioning that shaped this work, and the review panel whose "
        "observations at the first review directed the dataset, explainability "
        "and comparative-evaluation strands of the project. We also thank the "
        "Department of Computer Engineering, MPSTME, for the resources made "
        "available to us."
    ),
    "final": (
        "We thank our faculty mentor for the guidance and for the critical "
        "questioning that shaped this work from the first review to the last. "
        "We thank the review panels, whose observations at the first review "
        "directed the dataset, explainability and comparative-evaluation strands "
        "of the project, and whose questions at the midterm review led to the "
        "testing on real repositories reported in Chapter 4. We thank the authors "
        "and maintainers of the open-source projects scanned in this work, in "
        "particular OWASP crAPI, for publishing code that made an honest "
        "evaluation possible. We also thank the Computer Science & Engineering "
        "(Cyber Security) Department, MPSTME, for the resources made available "
        "to us."
    ),
}

ABSTRACTS = {
    "final": [
        "Banking API estates accumulate endpoints that remain deployed and "
        "network-reachable long after they have ceased to serve any purpose. Such "
        "endpoints retain their database credentials, network routes and access to "
        "production data while disappearing from the organisation's inventory: the "
        "condition OWASP catalogues as API9:2023 Improper Inventory Management, and "
        "one the Reserve Bank of India's Cyber Security Framework in Banks makes a "
        "compliance concern. No single source of evidence can identify them. A "
        "gateway registry cannot see a service addressed directly, a specification "
        "cannot describe a route nobody documented, traffic capture cannot observe "
        "an endpoint nothing called during the window, and source code shows that "
        "an endpoint exists but never that anything calls it. And the tools that do "
        "detect such endpoints stop at detection, leaving removal as an unaided and "
        "risky human judgement.",

        "This report presents API Exorcist, a system that determines an endpoint's "
        "lifecycle state by correlating six deliberately imperfect discovery "
        "sources, and then removes it safely. Fifteen weighted evidence rules "
        "classify each endpoint as ACTIVE, DEPRECATED, ORPHANED or ZOMBIE; a rule "
        "whose source was never consulted abstains rather than firing, and every "
        "verdict carries the signed evidence that produced it. A dependency graph "
        "computes the blast radius of a removal, and an endpoint is cleared only "
        "when the classifier and the graph agree. A gradient-boosted model with "
        "SHAP attribution may veto a removal but never propose one. The Safe Kill "
        "controller then carries a cleared endpoint through a shadow window derived "
        "from the rule of three, a named approval, a staged canary with automatic "
        "rollback, and a hash-chained audit log. The system scans real projects "
        "from a browser, ranks suspected zombies from the evidence code holds, "
        "proves them from imported gateway access logs, and enforces in CI that new "
        "shadow and zombie endpoints are not merged.",

        "On a synthetic retail-banking estate with a known answer key, the "
        "classifier reaches 0.960 accuracy and 0.940 macro-F1 with perfect zombie "
        "recall and no live endpoint marked for removal; a conventional "
        "gateway-plus-specification inventory finds two of eight zombies where "
        "correlation finds all eight. On held-out generated estates the model "
        "produces no false zombies where the rules produce fourteen. Across 120 "
        "generated estates, removal on the gate's word alone would cause 49 "
        "outages; with Safe Kill there are none. Scanning eight public repositories, "
        "the system ranks first the endpoints the projects themselves show to be "
        "stale, including the two old authentication endpoints OWASP crAPI still "
        "serves beside the newer versions its own web application calls. "
        "Validated against route lists built independently of it, the endpoints "
        "it finds in code agree on 126 of 127, and every reason it gives for a "
        "suspected zombie is true in the project's source. "
        "The architecture and the analysis are real code and the repository scans "
        "are of real projects; the banking estate is synthetic, and the claim made "
        "is that the engine recovers known decay patterns from partial, disagreeing "
        "evidence, not that it has been validated on production bank traffic.",
    ],
}

ABBREVIATION_SETS = {
    "final": [
        ["ALB", "Application Load Balancer (AWS)"],
        ["API", "Application Programming Interface"],
        ["AST", "Abstract Syntax Tree"],
        ["BFS", "Breadth-First Search"],
        ["CI/CD", "Continuous Integration / Continuous Deployment"],
        ["CLI", "Command-Line Interface"],
        ["CSP", "Content Security Policy"],
        ["CSV", "Comma-Separated Values"],
        ["CT", "Certificate Transparency"],
        ["CTE", "Common Table Expression"],
        ["DFD", "Data Flow Diagram"],
        ["DNS", "Domain Name System"],
        ["F1", "Harmonic mean of precision and recall"],
        ["GRC", "Governance, Risk and Compliance"],
        ["HTTP", "Hypertext Transfer Protocol"],
        ["IDS", "Intrusion Detection System"],
        ["JSON", "JavaScript Object Notation"],
        ["KYC", "Know Your Customer"],
        ["ML", "Machine Learning"],
        ["OWASP", "Open Worldwide Application Security Project"],
        ["RBI", "Reserve Bank of India"],
        ["REST", "Representational State Transfer"],
        ["RFC", "Request for Comments (IETF standards series)"],
        ["SARIF", "Static Analysis Results Interchange Format"],
        ["SHA", "Secure Hash Algorithm"],
        ["SHAP", "SHapley Additive exPlanations"],
        ["SIEM", "Security Information and Event Management"],
        ["TLS", "Transport Layer Security"],
        ["TTL", "Time To Live"],
        ["UI", "User Interface"],
        ["XAI", "Explainable Artificial Intelligence"],
    ],
}


# ---------------------------------------------------------------------------
def _build_report(spec: DocSpec) -> Path:
    """The interim report: NMIMS front matter, roman-then-decimal paging."""
    md = (DOCS / spec.source).read_text(encoding="utf-8")

    PAGE_FURNITURE["footer_align"] = WD_ALIGN_PARAGRAPH.RIGHT
    PAGE_FURNITURE["header_left"] = "API Exorcist"
    PAGE_FURNITURE["header_right"] = ACADEMIC_YEAR
    # The interim report keeps the geometry it was submitted with.
    page = A4_REPORT if spec.key == "final" else None
    PAGE_FURNITURE["page"] = page

    doc = Document()
    normal = doc.styles["Normal"]
    normal.font.name = BODY_FONT
    normal.font.size = Pt(spec.style.body)

    front = doc.sections[0]
    front.top_margin = front.bottom_margin = front.right_margin = Inches(1)
    front.left_margin = Inches(1.5)          # the format asks for 1.5" here
    if page:
        _apply_page(front, page)
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
    if page:
        _apply_page(body, page)
    _add_page_numbers(body)
    _set_page_numbering(body, "decimal", start=1)

    _render_all(doc, spec, md)

    out = DOCS / (spec.output or final_output())
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
    PAGE_FURNITURE["page"] = None

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
