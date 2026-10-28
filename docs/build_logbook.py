"""
Generate the capstone log book in the NMIMS format (guidelines, Annexure A.7).

    python docs/build_logbook.py      ->  docs/Group_4_Capstone_Log_Book.docx

The weekly entries record the work carried out, dated from the project's own
history (commit dates, document dates and review milestones). Faculty remarks,
signatures and grades are left blank on purpose: the log book is submitted
scanned and signed by the faculty mentor, who fills those in by hand.
"""

from __future__ import annotations

from datetime import date, timedelta
from pathlib import Path

from docx import Document
from docx.enum.table import WD_TABLE_ALIGNMENT
from docx.enum.text import WD_ALIGN_PARAGRAPH, WD_BREAK
from docx.oxml import OxmlElement
from docx.oxml.ns import qn
from docx.shared import Inches, Pt

DOCS = Path(__file__).resolve().parent
OUTPUT = DOCS / "Group_4_Capstone_Log_Book.docx"
FONT = "Times New Roman"

SCHOOL = "Mukesh Patel School of Technology Management & Engineering"
DEPARTMENT = "Computer Science & Engineering (Cyber Security)"
PROGRAM = "B.Tech. Computer Science and Engineering (Cyber Security)"
SEMESTER = "VII"
ACADEMIC_YEAR = "2026–2027"
TITLE = ("API Exorcist: Autonomous Discovery and Safe Elimination of Zombie, "
         "Shadow and Orphaned APIs")
MENTOR = "Dr. Pintu R Shah, Head of Department, Computer Science & Engineering (Cyber Security)"

#: (name, roll no., SAP ID, contact)
STUDENTS = [
    ("Nakul Hintya", "K026", "70102300049", "hintyanakul14@gmail.com"),
    ("Shivansh Rohit Jindal", "K029", "70102300028", "shivanshjindal2005@gmail.com"),
    ("Dhyey Kharayat", "K031", "70102300012", "dhyeykharayat@gmail.com"),
]

WEEK_1 = date(2026, 8, 4)

#: Work carried out, week by week. An empty list leaves ruled lines to write on.
WEEKS: list[list[str]] = [
    # Week 1
    [
        "Finalised the project idea: discovery and safe removal of zombie, shadow "
        "and orphaned APIs, focused on retail banking.",
        "Defined the four lifecycle states (active, deprecated, orphaned, zombie) "
        "and the problem of determining them from partial evidence.",
        "Began the literature survey on dead code, API deprecation and "
        "microservice architecture recovery.",
    ],
    # Week 2
    [
        "Continued the literature survey: dependency graphs, security smells, "
        "explainable AI (SHAP) and passive discovery.",
        "Prepared the synopsis and the Review 1 presentation: objectives, scope, "
        "five-layer architecture, tools and technology, timeline.",
        "Review 1 (topic approval and feasibility). Panel asks noted: identify the "
        "dataset for the ML engine, focus on one application, add explainable AI.",
    ],
    # Week 3
    [
        "Acted on the Review 1 comments: chose a synthetic retail-banking estate as "
        "the dataset (no public labelled corpus exists), and SHAP for explainability.",
        "Verified every reference against DBLP and Crossref; collected the papers.",
        "Planned implementation in phases, with the discovery layer as the first "
        "milestone.",
    ],
    # Week 4
    [
        "Built the discovery layer: six connectors (code, DNS, gateway, CI/CD, "
        "traffic, OpenAPI) and correlation into one inventory with 14 flags.",
        "Built the 25-endpoint simulated banking estate with a known answer key.",
        "Wrote the literature review with a traceability matrix, and the design "
        "document (component, class, sequence, state and data-flow diagrams).",
    ],
    # Week 5
    [
        "Classification engine: 15 weighted evidence rules that abstain when a "
        "source was not consulted; per-verdict explanations; comparative benchmark.",
        "Real GitHub repository scanning with Semgrep, git history and CODEOWNERS.",
        "Dependency graph with blast radius and the removal gate (Phase 2).",
        "Estate generator, trained model and SHAP attribution, with the model used "
        "as a veto over removals (Phase 3). Packaging, tests and CI set up.",
    ],
    # Week 6
    [
        "Wrote the interim report (Chapters 1 to 3) in the prescribed format, with "
        "measured results: 0.960 accuracy, 8 of 8 zombies found against 2 of 8 for a "
        "conventional inventory.",
        "Full-text verification of the key references; corrected a claim one paper "
        "did not support.",
    ],
    # Week 7
    [
        "Review 2 (midterm review): presented progress, design and results; "
        "submitted the interim report.",
        "Started the design of Safe Kill: shadow observation, approval, canary and "
        "rollback.",
    ],
    # Week 8
    [
        "Safe Kill: measured that a percentage canary cannot see rarely used "
        "endpoints; replaced the first stage with a shadow window sized by the rule "
        "of three (90 days for a monthly caller).",
        "Implemented the Safe Kill state machine and the hash-chained audit log.",
    ],
    # Week 9
    [
        "Completed and evaluated Safe Kill on 120 generated estates: removal on the "
        "gate alone would cause 49 outages; with Safe Kill, none (Phase 4).",
        "Found and fixed a generator defect (doubled version in endpoint paths) and "
        "re-measured all results.",
    ],
    # Week 10
    [
        "REST API with hashed tokens and roles; React and TypeScript dashboard "
        "(Phase 5).",
        "CI/CD enforcement action that blocks new undocumented, unowned and "
        "zombie-in-the-making endpoints (Phase 6).",
        "Container image, metrics, logs and a security review (Phases 7 and 8).",
        "Browser scans of an uploaded folder or a GitHub link (Phase 9).",
    ],
    # Week 11
    [
        "Zombie candidates from code evidence, tested on real public repositories "
        "(OWASP crAPI, VAmPI, Spring Petclinic and others) (Phase 10).",
        "Usage evidence from gateway access logs, retirement plans, exports and "
        "drift between scans (Phase 11).",
        "Fixed Express route extraction found failing on a real repository.",
        "Prepared the final report (black book), the research paper draft and "
        "the capstone log book in the prescribed format.",
    ],
    # Week 12
    [
        "Discussed the final report with the faculty mentor. Points to address: "
        "a comparative analysis of the benefits of the system and the limitations "
        "without it; how classification and the Safe Kill simulation work, in the "
        "report and in the application; validation that the APIs found in a "
        "repository are real and that the flagged zombies are zombies, with the "
        "scanning process explained; a later redesign of the user interface; and "
        "scanning of live websites by loading their pages over HTTPS.",
    ],
    # Week 13
    [
        "Validation study on six public repositories: endpoints found in code "
        "checked against independently built route lists (126 of 127 agree; all "
        "167 traced to the line that declares them), and all 25 reasons given for "
        "17 zombie candidates checked against the projects' source.",
        "Fixed two extraction defects the validation found: Express routers "
        "mounted through a router built in the same file, and routes read from "
        "end-to-end test files.",
        "Added to the final report: how a repository scan works (with a "
        "flowchart), a worked classification with real numbers, a Safe Kill "
        "walkthrough with screenshots, the validation study, and a comparative "
        "analysis with and without the system.",
        "Added the same explanations to the application: the score table behind "
        "each classification, the five steps of a Safe Kill removal, and, for each "
        "scan, whether its results can be trusted and why each endpoint is real.",
    ],
]


# ---------------------------------------------------------------------------
def _run(par, text, size=12, bold=False, italic=False):
    r = par.add_run(text)
    r.font.name = FONT
    r.font.size = Pt(size)
    r.bold = bold
    r.italic = italic
    return r


def _para(doc_or_cell, text="", size=12, bold=False, align=None, after=4):
    p = doc_or_cell.add_paragraph()
    if text:
        _run(p, text, size, bold)
    if align is not None:
        p.alignment = align
    p.paragraph_format.space_after = Pt(after)
    return p


def _cell(cell, text, size=11, bold=False):
    cell.text = ""
    _run(cell.paragraphs[0], text, size, bold)


def _table(doc, rows, widths, header=True):
    t = doc.add_table(rows=len(rows), cols=len(rows[0]))
    t.style = "Table Grid"
    t.alignment = WD_TABLE_ALIGNMENT.CENTER
    for i, row in enumerate(rows):
        for j, text in enumerate(row):
            _cell(t.rows[i].cells[j], text, bold=header and i == 0)
            t.rows[i].cells[j].width = Inches(widths[j])
    return t


def _min_height(row, inches):
    tr_pr = row._tr.get_or_add_trPr()
    h = OxmlElement("w:trHeight")
    h.set(qn("w:val"), str(int(inches * 1440)))
    h.set(qn("w:hRule"), "atLeast")
    tr_pr.append(h)


def _week(doc, n: int, work: list[str]) -> None:
    start = WEEK_1 + timedelta(weeks=n - 1)
    end = start + timedelta(days=6)
    t = doc.add_table(rows=4, cols=1)
    t.style = "Table Grid"
    t.alignment = WD_TABLE_ALIGNMENT.CENTER

    head = t.rows[0].cells[0]
    head.text = ""
    p = head.paragraphs[0]
    _run(p, f"Week No: {n}", bold=True)
    p2 = head.add_paragraph()
    _run(p2, "Date of Reporting: ", bold=True)
    _run(p2, f"From {start:%d/%m/%Y} to {end:%d/%m/%Y}")

    body = t.rows[1].cells[0]
    body.text = ""
    _run(body.paragraphs[0], "Work carried out", bold=True)
    for item in work:
        bp = body.add_paragraph(style="List Bullet")
        _run(bp, item, size=11)
        bp.paragraph_format.space_after = Pt(1)
    _min_height(t.rows[1], 2.6)

    remark = t.rows[2].cells[0]
    remark.text = ""
    _run(remark.paragraphs[0], "Faculty Remark", bold=True)
    _min_height(t.rows[2], 0.9)

    sign = t.rows[3].cells[0]
    sign.text = ""
    _run(sign.paragraphs[0], "Faculty Signature with date", bold=True)
    _min_height(t.rows[3], 0.6)

    for row in t.rows:
        row.cells[0].width = Inches(6.0)
    doc.add_paragraph().paragraph_format.space_after = Pt(2)


def build() -> Path:
    doc = Document()
    normal = doc.styles["Normal"]
    normal.font.name = FONT
    normal.font.size = Pt(12)
    s = doc.sections[0]
    s.page_width, s.page_height = Inches(8.27), Inches(11.69)
    s.left_margin, s.right_margin = Inches(1.25), Inches(1.0)
    s.top_margin = s.bottom_margin = Inches(0.8)

    footer = s.footer.paragraphs[0]
    footer.alignment = WD_ALIGN_PARAGRAPH.RIGHT
    for tag, text in (("begin", None), (None, "PAGE"), ("end", None)):
        r = footer.add_run()
        if tag:
            fc = OxmlElement("w:fldChar")
            fc.set(qn("w:fldCharType"), tag)
            r._r.append(fc)
        else:
            it = OxmlElement("w:instrText")
            it.text = text
            r._r.append(it)

    # ---- cover ----
    c = WD_ALIGN_PARAGRAPH.CENTER
    _para(doc, SCHOOL, 16, True, c, 2)
    _para(doc, f"{DEPARTMENT} Department", 12, False, c, 14)
    _para(doc, "Log Book for Capstone Project", 18, True, c, 18)

    _table(doc, [
        ["Department", DEPARTMENT],
        ["Program", PROGRAM],
        ["Semester", SEMESTER],
        ["Academic Year", ACADEMIC_YEAR],
        ["Title of the Project", TITLE],
        ["Name of the Faculty Mentor", MENTOR],
    ], [2.0, 4.0], header=False)
    for row in doc.tables[-1].rows:
        row.cells[0].paragraphs[0].runs[0].bold = True

    _para(doc, "", after=8)
    _para(doc, "STUDENT DETAILS", 12, True, c, 6)
    _table(doc, [["", "NAME", "ROLL NO.", "CONTACT"]]
           + [[f"Student {i}", n, r, mail] for i, (n, r, _sap, mail) in enumerate(STUDENTS, 1)],
           [0.9, 1.9, 0.9, 2.3])

    _para(doc, "", after=8)
    _para(doc, "Name of group members:", 12, True, None, 6)
    t = _table(doc, [["Roll No.", "Name", "Sign (Students)", "Grades (By Faculty Mentor)"]]
               + [[r, n, "", ""] for n, r, _sap, _m in STUDENTS],
               [0.9, 2.0, 1.5, 1.6])
    for row in t.rows[1:]:
        _min_height(row, 0.45)

    doc.add_paragraph().add_run().add_break(WD_BREAK.PAGE)

    # ---- weekly entries, two to a page ----
    for i, work in enumerate(WEEKS, start=1):
        _week(doc, i, work)
        if i % 2 == 0 and i != len(WEEKS):
            doc.add_paragraph().add_run().add_break(WD_BREAK.PAGE)

    doc.save(OUTPUT)
    return OUTPUT


if __name__ == "__main__":
    out = build()
    print(f"  built {out.name}  ({out.stat().st_size // 1024} KB)")
