"""
Generate the final (jury) presentation.

The slot is 30 minutes in all: presentation, live demonstration and questions.
The deck is planned to that budget, and every slide carries speaker notes with
its time and what to say:

    0:00 - 10:30   slides 1-14   problem, literature, design, algorithms
    10:30 - 19:30  slide 15      live demonstration (9 minutes)
    19:30 - 23:30  slides 16-22  results, comparison, limitations, future
    23:30 - 30:00               questions; backup slides after "Thank you"

Layout primitives and the MPSTME template come from build_pptx.py (the Review 2
deck), so both decks look the same. Figures are the ones the final report
states and docs/verify_claims.py checks against the code.

Usage:
    python docs/build_final_pptx.py
"""

from __future__ import annotations

import sys
from pathlib import Path

from pptx import Presentation
from pptx.enum.text import MSO_ANCHOR, PP_ALIGN
from pptx.util import Emu, Inches, Pt

sys.path.insert(0, str(Path(__file__).resolve().parent))

from build_pptx import (
    CONTENT_W,
    DOCS,
    EMU_PER_IN,
    GOOD,
    INK,
    MARGIN,
    MUTED,
    RED,
    SAFE_TOP,
    SHADE,
    SLIDE_H,
    SLIDE_W,
    TEMPLATE,
    WHITE,
    _blank,
    _height_of,
    _line,
    _text,
    bullets,
    callout,
    code,
    footnote,
    heading,
    picture,
    table,
    two_columns,
)

OUTPUT = DOCS / "Group_4_Final_Presentation.pptx"
LOGO = DOCS / "assets" / "logo.png"

TITLE = "API Exorcist"
SUBTITLE = ("Autonomous Discovery and Safe Elimination of "
            "Zombie, Shadow and Orphaned APIs")
TEAM = [
    ("Nakul Hintya", "K026"),
    ("Shivansh Rohit Jindal", "K029"),
    ("Dhyey Kharayat", "K031"),
]
MENTOR = "Dr. Pintu R Shah"


def notes(slide, text: str) -> None:
    """Speaker notes: the time budget first, then what to say."""
    slide.notes_slide.notes_text_frame.text = text


def boxes(slide, top, items, *, height=Inches(2.35), size=11):
    """A left-to-right flow of numbered boxes: (title, body, stop). Returns y."""
    n = len(items)
    gap = Inches(0.12)
    w = int((CONTENT_W - gap * (n - 1)) / n)
    for i, (title, body, stop) in enumerate(items):
        left = MARGIN + i * (w + gap)
        box = slide.shapes.add_shape(1, left, top, w, height)
        box.fill.solid()
        box.fill.fore_color.rgb = SHADE
        box.line.color.rgb = RED if i == n - 1 else MUTED
        box.line.width = Pt(0.75)
        box.shadow.inherit = False
        tf = _text(slide, left + Inches(0.08), top + Inches(0.08),
                   w - Inches(0.16), height - Inches(0.16))
        _line(tf, f"{i + 1}  {title}", size=size + 2, bold=True, colour=RED,
              first=True, space_after=4)
        _line(tf, body, size=size, colour=INK, space_after=6)
        if stop:
            _line(tf, f"Stops here: {stop}", size=size - 1, italic=True,
                  colour=MUTED, space_after=0)
    return top + height


def layers(slide, top, rows, *, row_h=Inches(0.72), size=11):
    """Architecture as stacked layers: (label, [components]). Returns y."""
    label_w = Inches(1.75)
    gap = Inches(0.1)
    y = top
    for n, (label, parts) in enumerate(rows):
        band = slide.shapes.add_shape(1, MARGIN, y, CONTENT_W, row_h)
        band.fill.solid()
        band.fill.fore_color.rgb = SHADE
        band.line.fill.background()
        band.shadow.inherit = False
        tf = _text(slide, MARGIN + Inches(0.1), y, label_w - Inches(0.1), row_h,
                   anchor=MSO_ANCHOR.MIDDLE)
        _line(tf, f"{n + 1}  {label}", size=size + 1.5, bold=True, colour=RED,
              first=True, space_after=0)
        avail = CONTENT_W - label_w - Inches(0.1)
        w = int((avail - gap * (len(parts) - 1)) / len(parts))
        for i, part in enumerate(parts):
            left = MARGIN + label_w + i * (w + gap)
            chip = slide.shapes.add_shape(1, left, y + Inches(0.1), w,
                                          row_h - Inches(0.2))
            chip.fill.solid()
            chip.fill.fore_color.rgb = WHITE
            chip.line.color.rgb = MUTED
            chip.line.width = Pt(0.75)
            chip.shadow.inherit = False
            tf = chip.text_frame
            tf.word_wrap = True
            tf.margin_left = tf.margin_right = Inches(0.05)
            tf.vertical_anchor = MSO_ANCHOR.MIDDLE
            # "Name|detail": the name on its own line, the detail beneath.
            name, _, detail = part.partition("|")
            _line(tf, name, size=size, bold=bool(detail), colour=INK,
                  first=True, space_after=0, align=PP_ALIGN.CENTER)
            if detail:
                _line(tf, detail, size=size - 1, colour=MUTED, space_after=0,
                      align=PP_ALIGN.CENTER)
        y += row_h
        if n < len(rows) - 1:
            arrow = _text(slide, MARGIN, y, CONTENT_W, Inches(0.2),
                          align=PP_ALIGN.CENTER)
            _line(arrow, "▼", size=10, colour=RED, first=True,
                  space_after=0, align=PP_ALIGN.CENTER)
            y += Inches(0.2)
    return y


# ---------------------------------------------------------------------------
# 0:00 - 10:30   Introduction to algorithms
# ---------------------------------------------------------------------------
def logo(slide, top, size):
    """The project logo, centred. Returns the y below it."""
    if LOGO.exists():
        slide.shapes.add_picture(str(LOGO), int((SLIDE_W - size) / 2), top,
                                 size, size)
    return top + size


def slide_title(prs):
    slide = _blank(prs)
    y = logo(slide, SAFE_TOP - Inches(0.1), Inches(1.35)) + Inches(0.05)
    tf = _text(slide, MARGIN, y, CONTENT_W, Inches(0.75), align=PP_ALIGN.CENTER)
    _line(tf, TITLE, size=42, bold=True, colour=RED, first=True,
          align=PP_ALIGN.CENTER, space_after=0)
    y += Inches(0.85)
    h = _height_of(SUBTITLE, 19, CONTENT_W / EMU_PER_IN, 0)
    tf = _text(slide, MARGIN, y, CONTENT_W, Emu(h), align=PP_ALIGN.CENTER)
    _line(tf, SUBTITLE, size=19, colour=INK, first=True,
          align=PP_ALIGN.CENTER, space_after=0)
    y += Emu(h) + Inches(0.3)
    tf = _text(slide, MARGIN, y, CONTENT_W, Inches(0.34), align=PP_ALIGN.CENTER)
    _line(tf, "Capstone Project - Final Presentation", size=15, bold=True,
          colour=RED, first=True, align=PP_ALIGN.CENTER, space_after=0)
    y += Inches(0.55)
    tf = _text(slide, MARGIN, y, CONTENT_W, Inches(0.4), align=PP_ALIGN.CENTER)
    _line(tf, "Group 4", size=16, bold=True, colour=INK, first=True,
          align=PP_ALIGN.CENTER, space_after=6)
    for name, roll in TEAM:
        _line(tf, f"{name}   {roll}", size=15.5, colour=INK,
              align=PP_ALIGN.CENTER, space_after=3)
    y += Inches(1.45)
    tf = _text(slide, MARGIN, y, CONTENT_W, Inches(0.9), align=PP_ALIGN.CENTER)
    _line(tf, f"Faculty Mentor: {MENTOR}", size=15, colour=INK, first=True,
          align=PP_ALIGN.CENTER, space_after=10)
    _line(tf, "B.Tech. Computer Science and Engineering (Cyber Security)   |   "
              "MPSTME, NMIMS   |   2026-2027", size=12.5, colour=MUTED,
          align=PP_ALIGN.CENTER, space_after=0)
    notes(slide, "[0:00, 20 s] Names, project title, mentor. One sentence: "
                 "we find APIs a bank has forgotten about, and remove them "
                 "without causing an outage.")


def slide_contents(prs):
    slide = _blank(prs)
    y = heading(slide, "Table of Contents")
    items = [
        "Introduction", "Literature Survey and Research Gap",
        "Problem Statement", "Objectives and Scope",
        "Tools and Technologies Used", "Market Research",
        "Design", "Algorithms", "Implementation (live)",
        "Results and Comparative Analysis", "Limitations",
        "Conclusion and Future Extensions", "References",
    ]
    col_w = (CONTENT_W - Inches(0.45)) / 2
    half = (len(items) + 1) // 2
    for offset, chunk, start in (
        (MARGIN, items[:half], 1),
        (MARGIN + col_w + Inches(0.45), items[half:], half + 1),
    ):
        tf = _text(slide, offset, y + Inches(0.2), col_w, Inches(4.5))
        for n, item in enumerate(chunk):
            _line(tf, f"{start + n}.   {item}", size=15.5, colour=INK,
                  space_after=13, first=(n == 0))
    notes(slide, "[0:20, 10 s] Do not read it. 'About ten minutes of slides, "
                 "nine of live demo, then results and your questions.'")


def slide_intro(prs):
    slide = _blank(prs)
    y = heading(slide, "Introduction",
                "Endpoints are created quickly and retired slowly, or never")
    y = bullets(slide, y, [
        ("A bank exposes hundreds of HTTP endpoints: mobile and internet "
         "banking, payments, KYC, partner integrations. Every feature adds more.",
         14.5, False, INK),
        ("Removing one needs someone to be sure nothing still uses it. That is "
         "expensive to decide and cheap to postpone, so it is postponed.",
         14.5, False, INK),
        ("ZOMBIE API: still deployed and reachable, used and maintained by "
         "nobody.   SHADOW API: running, documented nowhere.", 14.5, True, INK),
    ], gap=12)
    y = callout(slide, y + Inches(0.12),
                "OWASP API Security Top 10, API9:2023 Improper Inventory "
                "Management.   RBI's Cyber Security Framework requires a "
                "maintained asset inventory.", size=13.5)
    bullets(slide, y + Inches(0.18), [
        ("An endpoint nobody knows about is never patched, never monitored and "
         "never audited, yet it keeps its credentials and its access to "
         "production data.", 15, True, RED),
    ])
    notes(slide, "[0:30, 50 s] Define zombie and shadow plainly. Stress: "
                 "finding endpoints is easy; knowing which are dead, and "
                 "removing them without an outage, is the hard part.")


def slide_four_states(prs):
    slide = _blank(prs)
    y = heading(slide, "Four states, not one problem",
                "Every one of them is defined by USE, which drives the "
                "architecture")
    y = table(slide, y, [
        ["State", "Definition", "Correct action"],
        ["ACTIVE", "Documented, owned, in genuine use", "Leave alone"],
        ["DEPRECATED", "Announced as retiring, still responding",
         "Confirm a removal date exists"],
        ["ORPHANED", "Still genuinely used, but nobody owns it",
         "Assign an owner - never remove"],
        ["ZOMBIE", "No meaningful use, largely invisible",
         "Candidate for Safe Kill"],
    ], [0.19, 0.47, 0.34], size=13)
    y = callout(slide, y + Inches(0.22),
                "ORPHANED and ZOMBIE are both unowned. Only one is unused.",
                size=15.5)
    bullets(slide, y + Inches(0.16), [
        ("Removing an orphaned endpoint is an outage. A tool that cannot tell "
         "the two apart cannot be used in a bank.", 14.5, True, RED),
    ])
    notes(slide, "[1:20, 40 s] The key distinction is orphaned vs zombie. "
                 "Because the states are defined by use, a tool that only "
                 "reads code cannot honestly label any of them.")


def slide_literature(prs):
    slide = _blank(prs)
    y = heading(slide, "Literature Survey",
                "Six themes, 12 peer-reviewed papers - what each gave the "
                "implementation")
    y = table(slide, y, [
        ["Theme", "Papers", "Finding", "Use in the project"],
        ["Dead and deprecated code", "[1] Caivano 2023\n[2] Cassieri 2023\n"
         "[11] Brito 2018",
         "Decay is slow; deprecation flags are applied inconsistently",
         "Staleness as evidence; a missing flag is never read as evidence"],
        ["Architecture recovery", "[3] Bushong 2021\n[12] Gortney 2022",
         "Source analysis recovers structure but no usage",
         "Code-only scans make no lifecycle claim"],
        ["Dependency graphs", "[4] Ma 2019\n[5] Abdelfattah 2023",
         "Service dependency is measurable, graph-shaped",
         "Blast radius computed before any removal"],
        ["Security smells", "[6] Dell'Immagine 2023\n[7] Ponce Mella 2024",
         "Research stops at detection and triage",
         "The gap: Safe Kill acts on it"],
        ["Explainability", "[8] Lundberg 2017\n[9] Gaspar 2024",
         "Additive per-decision attribution (SHAP)",
         "Every verdict carries signed reasons"],
        ["Passive discovery", "[10] Scheitle 2018",
         "CT logs expose hostnames",
         "Active probing only with DNS ownership proof"],
    ], [0.19, 0.22, 0.29, 0.30], size=10.5)
    footnote(slide, "All 12 validated against DBLP or Crossref; five checked "
                    "against full text, and one claim the paper did not make "
                    "was removed.")
    notes(slide, "[2:00, 50 s] Do not read rows. Say: the literature can "
                 "detect dead code, recover architecture and model "
                 "dependencies - and every line of it stops at detection.")


def slide_gap(prs):
    slide = _blank(prs)
    y = heading(slide, "The Research Gap",
                "Each piece exists separately. No surveyed work combines them.")
    y = bullets(slide, y, [
        ("No single source can establish an endpoint's true state - dead code "
         "is single-source, declared deprecation is unreliable, and source "
         "recovery has no usage data.   [1][2][3][11][12]", 14, False, INK),
        ("...yet every surveyed tool is single-source.", 14, True, RED),
        ("The machinery to predict removal impact exists.   [4][5][6][7]",
         14, False, INK),
        ("...yet no tool acts on it: detection is where the research stops.",
         14, True, RED),
        ("Automated decisions can be made auditable.   [8][9]",
         14, False, INK),
        ("...yet no tool needs it, because none acts.", 14, True, RED),
    ], gap=9)
    callout(slide, y + Inches(0.2),
            "Our contribution: multi-source correlation, consequence "
            "prediction, and a safe, explained, audited removal.", size=14.5)
    notes(slide, "[2:50, 30 s] The gap is the composition, and the step after "
                 "detection: removing safely.")


def slide_problem(prs):
    slide = _blank(prs)
    y = heading(slide, "Problem Statement")
    y = callout(
        slide, y,
        "Determine each endpoint's lifecycle state from sources that "
        "disagree, predict what removing it would break, remove it without "
        "an outage, and explain every decision well enough to defend in an "
        "audit.", size=15.5)
    bullets(slide, y + Inches(0.26), [
        ("1.  Partial evidence - tell \"this source says no\" from \"this "
         "source was never asked\".", 14.5, False, INK),
        ("2.  Consequence - know what transitively calls an endpoint before "
         "clearing it.", 14.5, False, INK),
        ("3.  Safe action - catch the caller nobody knew about before it "
         "becomes an outage.", 14.5, False, INK),
        ("4.  Auditability - every verdict and every removal carries its "
         "complete evidence and a named decision-maker.", 14.5, False, INK),
    ], gap=12)
    notes(slide, "[3:20, 30 s] Four sub-problems; each maps to one part of "
                 "the system shown next.")


def slide_objectives(prs):
    slide = _blank(prs)
    y = heading(slide, "Objectives and Scope", "Every objective delivered")
    y = table(slide, y, [
        ["Objective", "Delivered"],
        ["Correlate six independent sources into one inventory",
         "Done - 14 discrepancy flags"],
        ["Classify ACTIVE / DEPRECATED / ORPHANED / ZOMBIE, abstaining when "
         "a source is absent", "Done - 15 evidence rules"],
        ["Explain every verdict", "Done - signed reasons, shown in the app"],
        ["Predict blast radius before any removal",
         "Done - dependency graph and removal gate"],
        ["Remove safely", "Done - Safe Kill: shadow, approval, canary, "
         "rollback, audit"],
        ["Work on real code", "Done - eight public repositories, access-log "
         "import"],
        ["Stop new zombies being created", "Done - pull-request enforcement"],
    ], [0.62, 0.38], size=12)
    footnote(slide, "Out of scope: unauthorised external scanning. The "
                    "architecture is real code; the banking estate it is "
                    "measured on is synthetic, with a known answer key.",
             colour=RED)
    notes(slide, "[3:50, 40 s] All objectives met. State the honesty "
                 "boundary now, before anyone asks: real code is scanned for "
                 "real; the bank estate is simulated because no bank "
                 "publishes its inventory.")


def slide_tools(prs):
    slide = _blank(prs)
    y = heading(slide, "Tools and Technologies Used",
                "Each choice defended against the alternative it beat")
    table(slide, y, [
        ["Component", "Technology", "Why"],
        ["Route extraction", "Semgrep (AST)",
         "A route is a structure; regex breaks on formatting"],
        ["Backend and API", "Python 3.10 / 3.12, FastAPI",
         "Typed, async, hashed bearer tokens and roles"],
        ["Dashboard", "React + TypeScript",
         "One runtime dependency, strict CSP, same origin"],
        ["Dependency graph", "In-process graph / Neo4j",
         "Blast radius is a multi-hop traversal"],
        ["Classification", "Weighted rules + gradient boosting veto",
         "Rules work with zero training data; the model may only block"],
        ["Explainability", "Signed reasons + SHAP",
         "Additive, per-decision attribution"],
        ["Usage evidence", "nginx, ALB, Kong, Envoy, Traefik logs",
         "Logs every bank already keeps; no agent"],
        ["Quality and delivery", "pytest, Vitest, mypy strict, ruff, "
         "GitHub Actions, Docker", "307 + 51 tests; hardened container"],
    ], [0.21, 0.36, 0.43], size=11)
    notes(slide, "[4:30, 30 s] Highlight two: Semgrep reads structure not "
                 "text; rules decide and the model may only veto.")


def slide_market(prs):
    slide = _blank(prs)
    y = heading(slide, "Market Research",
                "Detection is a crowded market. Safe remediation is not.")
    table(slide, y, [
        ["Capability", "API gateways", "API security platforms",
         "Static analysers", "API Exorcist"],
        ["Finds what the gateway and spec miss", "No", "From traffic",
         "From code", "*Six sources*"],
        ["Tells orphaned (in use) from zombie", "No", "Partly", "No",
         "*Yes*"],
        ["Says what it cannot determine", "No", "No", "No", "*Yes*"],
        ["Predicts what a removal breaks", "No", "No", "No", "*Yes*"],
        ["Removes safely, with rollback", "No", "No", "No", "*Yes*"],
        ["Stops new zombies at the pull request", "No", "No", "Partly",
         "*Yes*"],
    ], [0.30, 0.15, 0.19, 0.17, 0.19], size=11.5)
    footnote(slide, "Buyers: regulated banks, which need an inventory for "
                    "security (OWASP API9) and for audit (RBI CSF). Product "
                    "shape: self-hosted; nothing leaves the bank's network.")
    notes(slide, "[5:00, 40 s] Gateways list what is registered; security "
                 "platforms detect and report; static tools list routes. "
                 "Nobody predicts impact or removes safely.")


def slide_design(prs):
    slide = _blank(prs)
    y = heading(slide, "Design - System Architecture",
                "Five layers, dependencies pointing one way")
    layers(slide, y, [
        ("Sources", ["Code|Semgrep AST", "OpenAPI|specification",
                     "CI/CD|workflows", "API gateway|route registry",
                     "Traffic|access logs", "DNS|service mesh"]),
        ("Ingestion", ["Connectors|emit observations, never verdicts",
                       "Event bus|LocalBus / Kafka"]),
        ("Analysis", ["Correlation|14 flags", "Rule classifier|15 rules",
                      "Learned model|veto + SHAP",
                      "Dependency graph|blast radius"]),
        ("Decision", ["Removal gate|classifier + graph",
                      "Safe Kill|shadow, canary, rollback",
                      "Audit log|hash-chained",
                      "Enforcement|on pull requests"]),
        ("Presentation", ["Browser app|React + TypeScript",
                          "REST API|FastAPI, tokens, roles", "CLI|apix"]),
    ], size=10.5)
    footnote(slide, "Dependencies point one way: the engine never reaches back "
                    "to a data source, so the simulated estate swaps for live "
                    "sources with nothing downstream changing.")
    notes(slide, "[5:40, 50 s] Walk top to bottom: six sources -> correlation "
                 "-> rules, model, graph -> gate, Safe Kill, audit -> API and "
                 "dashboard. Full design document is in the report.")


def slide_scan_flow(prs):
    slide = _blank(prs)
    y = heading(slide, "Design - How a repository scan works",
                "Nothing from the scanned project is ever executed")
    y = boxes(slide, y, [
        ("Acquire", "Clone the GitHub repository with its history, or take an "
         "uploaded folder.", ""),
        ("Read", "Semgrep routes, OpenAPI specs, git history, CODEOWNERS, "
         "workflows, the project's own client calls.", ""),
        ("Correlate", "One record per METHOD /path; which sources saw it, "
         "which were consulted.", ""),
        ("Rank", "Zombie-candidate evidence, data sensitivity, dependency "
         "graph from code.", ""),
        ("Report", "Candidates with reasons, every endpoint traced to file "
         "and line, what could not be checked.", ""),
    ], height=Inches(1.6), size=11.5)
    y = callout(slide, y + Inches(0.2),
                "Code, specifications and history are read as data. What "
                "cannot be checked is reported as such - never assumed.",
                size=13.5)
    picture(slide, y + Inches(0.15), "screen-candidates")
    notes(slide, "[6:30, 30 s] This is what runs in the demo on crAPI. The "
                 "screenshot is its result: candidates ranked, the top one's "
                 "evidence on the right.")


def slide_algo_classify(prs):
    slide = _blank(prs)
    y = heading(slide, "Algorithm 1 - Correlation and classification",
                "Absence is evidence; a source never consulted is not "
                "absence")
    y = code(slide, y, [
        "correlate(signals):",
        "  GROUP by normalised (method, path)  -- /users/:id = /users/{id}",
        "  RECORD sources that SAW it, and sources CONSULTED",
        "  DERIVE 14 flags  -- UNDOCUMENTED, SHADOW_CANDIDATE, NO_OWNER ...",
        "",
        "classify(record):",
        "  FOR each of 15 rules:",
        "    IF its source was not consulted:  ABSTAIN",
        "    IF it fires:  add signed weights, record the Reason",
        "  label = argmax;  confidence = softmax(scores, T = 3)",
    ], size=11.5)
    bullets(slide, y + Inches(0.2), [
        ("A zombie is found where the sources DISAGREE: in code and DNS, "
         "absent from the gateway and the spec, silent in traffic.",
         13.5, True, RED),
        ("Additive rules, not a decision tree: an abstaining rule removes its "
         "contribution instead of breaking a branch, and confidence comes "
         "from the margin.", 13.5, False, INK),
    ], gap=8)
    notes(slide, "[7:00, 60 s] The two ideas: absence is evidence, and "
                 "abstention. Without abstention a code-only scan would "
                 "call every endpoint a zombie, confidently and wrongly.")


def slide_algo_safekill(prs):
    slide = _blank(prs)
    y = heading(slide, "Algorithm 2 - Safe Kill",
                "Five steps; any of the first four can stop a removal")
    y = boxes(slide, y, [
        ("Gate", "ZOMBIE with usage evidence, and the dependency graph finds "
         "nothing calling it.", "a caller, an indeterminate verdict, or the "
         "model's veto"),
        ("Shadow, 90 days", "Nothing refused; every request that would have "
         "been is recorded with its caller.", "any identified caller"),
        ("Named approval", "A person with an approver token decides; the "
         "name comes from the token.", "a decline - or unidentified traffic, "
         "which can never be approved"),
        ("Canary", "410 Gone to 5%, 25%, 100% for 7 / 7 / 14 days.",
         "a refused identified caller: automatic rollback"),
        ("Retired", "Every transition is in a hash-chained audit log.", ""),
    ], height=Inches(2.25), size=11.5)
    callout(slide, y + Inches(0.2),
            "Why 90 days: to be 95% sure of seeing a caller who calls once a "
            "month, watch ln(20) x 30 = 90 days (the rule of three).",
            size=13.5)
    notes(slide, "[8:00, 60 s] Walk the five boxes. Then the design change "
                 "we made: unidentified traffic can never be approved, "
                 "because a forgotten partner and an attacker's scanner look "
                 "the same on the wire. The fix is to add authentication and "
                 "shadow again.")


def slide_algo_candidates(prs):
    slide = _blank(prs)
    y = heading(slide, "Algorithm 3 - Zombie candidates on real code",
                "A repository has no traffic, so it ranks suspects and never "
                "convicts")
    y = table(slide, y, [
        ["Evidence in the code", "Weight", "Real example"],
        ["A newer version of the same operation exists", "+3",
         "crAPI v2/check-otp beside v3"],
        ["...and the project's own client calls only the newer one", "+2",
         "crAPI's web app calls v3 only"],
        ["Marked deprecated in the spec or the code", "+3", ""],
        ["A debug or test endpoint shipped in the API", "+2",
         "VAmPI /users/v1/_debug"],
        ["Undocumented while its neighbours are documented", "+2",
         "crAPI admin/lockUser"],
        ["Unchanged for a year while the project changes", "+1", ""],
        ["Referenced by a client, or called by another service", "-2", ""],
    ], [0.53, 0.12, 0.35], size=11.5)
    callout(slide, y + Inches(0.18),
            "Score 2 = candidate; 4 with a newer version or a deprecation = "
            "likely zombie. Access logs then PROVE it, under three guards.",
            size=13)
    notes(slide, "[9:00, 50 s] This is what the demo shows first. Guards on "
                 "logs: absence only counts where logs cover the service; "
                 "under 7 days nothing is a zombie; a 401 is probing, not "
                 "use.")


def slide_contribution_map(prs):
    slide = _blank(prs)
    y = heading(slide, "Implementation - what was built",
                "One product: a browser app, a CLI, a REST API and a GitHub "
                "Action")
    two_columns(
        slide, y,
        "In the application", [
            "Scan an uploaded folder or a GitHub link; report what could not "
            "be checked and why",
            "Ranked zombie candidates with their reasons; every endpoint "
            "traced to its file and line",
            "Access-log import: real lifecycle labels from real usage",
            "Dependency graph, Safe Kill, hash-chained audit log",
            "Exports: SARIF, CSV, OpenAPI stubs, executive report",
            "A production-grade console: severity scale, charts, Safe Kill as a "
            "pipeline, the audit log as a chain, light and dark",
        ],
        "Around it", [
            "REST API with hashed tokens, viewer and approver roles",
            "GitHub Action: fails a PR that adds undocumented, unowned or "
            "zombie-in-the-making endpoints",
            "Hardened container: non-root, read-only, digest-pinned",
            "Prometheus metrics, JSON logs",
            "CI: 307 Python + 51 dashboard tests, strict types, and a check "
            "that every figure in the documents matches the code",
        ],
        size=12.5)
    notes(slide, "[9:50, 40 s] Hand over to the demo: 'Rather than describe "
                 "it, let us show it.' Switch to the browser.")


# ---------------------------------------------------------------------------
# 10:30 - 19:30  Live demonstration
# ---------------------------------------------------------------------------
def slide_demo(prs):
    slide = _blank(prs)
    y = heading(slide, "Implementation (live)", "Nine minutes, in the browser")
    y = table(slide, y, [
        ["Time", "What we show", "What it proves"],
        ["2:00", "Scan OWASP crAPI from its GitHub link",
         "Real code: 62 endpoints, the two insecure old versions ranked "
         "first, with reasons"],
        ["1:30", "Import its access log (synthetic, labelled so)",
         "Candidates become proven zombies; probing is not use"],
        ["1:00", "Dependency graph", "What a removal would break"],
        ["3:00", "Demo bank: Endpoints, Benchmark, Safe Kill",
         "2 of 8 vs 8 of 8 zombies; shadow and approval; unidentified "
         "traffic cannot be approved"],
        ["1:30", "Audit log: verify the whole chain",
         "Every decision named and tamper-evident"],
    ], [0.10, 0.40, 0.50], size=11.5)
    footnote(slide, "Fallback: every repository is pre-scanned under Projects. "
                    "If the network fails, open the saved report; if anything "
                    "errors, switch to the demo bank.", colour=RED)
    notes(slide, "[10:30 - 19:30] Follow demo/DEMO.md, section '30-minute "
                 "version'. Start the crAPI scan first and talk while it "
                 "runs (about 60 s). Keep this slide visible if the "
                 "projector must switch.")


# ---------------------------------------------------------------------------
# 19:30 - 23:30  Results, comparison, close
# ---------------------------------------------------------------------------
def slide_results_benchmark(prs):
    slide = _blank(prs)
    y = heading(slide, "Results - classification and the comparison",
                "Simulated 25-endpoint bank with a known answer key; identical "
                "code, only the sources differ")
    y = table(slide, y, [
        ["Configuration", "Coverage", "Rules usable", "Zombies caught"],
        ["Gateway registry only", "76.0%", "0 / 15", "0 / 8"],
        ["OpenAPI specification only", "68.0%", "3 / 15", "0 / 8"],
        ["Gateway + spec (conventional)", "76.0%", "5 / 15", "2 / 8"],
        ["*All six, correlated*", "*100%*", "*15 / 15*", "*8 / 8*"],
    ], [0.40, 0.18, 0.20, 0.22], size=12.5, highlight_last=True)
    y = callout(slide, y + Inches(0.18),
                "Accuracy 0.960 (24/25), macro-F1 0.940, zombie recall 1.000, "
                "zero live endpoints marked for removal.", size=13.5)
    bullets(slide, y + Inches(0.16), [
        ("The conventional inventory finds 2 of 8. The other six are invisible "
         "to both the gateway and the spec - and four of them have no "
         "authentication at all.", 13.5, True, GOOD),
        ("The one error: an endpoint whose team never set the deprecation "
         "flag, exactly what Cassieri [2] observed. Reported, not tuned "
         "away - and its counterfactual names the gap: \"it would be "
         "DEPRECATED if the spec marked it deprecated\".", 13, False, MUTED),
    ], gap=8)
    notes(slide, "[19:30, 50 s] Already seen in the demo - be quick. Weights "
                 "were fixed before accuracy was measured.")


def slide_results_real(prs):
    slide = _blank(prs)
    y = heading(slide, "Results - validation on real code",
                "Are the APIs real, and are the zombies zombies? Checked "
                "independently of the scanner")
    y = table(slide, y, [
        ["Check", "Result"],
        ["Endpoints found in code vs independent truth lists, five "
         "repositories", "*126 of 127 agree (0.992)*"],
        ["Every endpoint traced to the line that declares it",
         "*167 of 167*"],
        ["Every reason given for every zombie candidate, checked in the "
         "source", "*25 of 25 true*"],
    ], [0.66, 0.34], size=12.5)
    y = table(slide, y + Inches(0.2), [
        ["Repository", "Top of the list"],
        ["OWASP crAPI", "v2/check-otp (no attempt limit; v3 locks after 10) "
         "and v2.7 login-with-token"],
        ["VAmPI", "/users/v1/_debug and /createdb - debug endpoints shipped"],
        ["spring-petclinic-rest", "GET /owners, GET /pets - superseded by v2"],
    ], [0.30, 0.70], size=11.5)
    footnote(slide, "The first validation run scored 107 of 127 and exposed two "
                    "extractor defects. Both were fixed and are covered by "
                    "tests that scan the real repositories.")
    notes(slide, "[20:20, 50 s] This answers the mentor's question directly. "
                 "The one disagreement is petclinic, where the truth list "
                 "itself is wrong.")


def slide_results_safekill(prs):
    slide = _blank(prs)
    y = heading(slide, "Results - does Safe Kill make removal safer?",
                "120 generated estates; the gate wrongly clears 49 live "
                "endpoints that call too rarely to be seen")
    y = table(slide, y, [
        ["Shadow length", "Caught in shadow", "Rolled back", "Outages",
         "Real requests refused"],
        ["None (gate only)", "-", "-", "49", "-"],
        ["0 days (canary only)", "0", "49", "0", "67"],
        ["3 days", "26", "20", "3", "43"],
        ["30 days", "45", "0", "4", "0"],
        ["*90 days*", "*48*", "*1*", "*0*", "*1*"],
    ], [0.26, 0.20, 0.17, 0.15, 0.22], size=12, highlight_last=True)
    callout(slide, y + Inches(0.18),
            "49 outages become 0, while all 793 genuinely dead endpoints are "
            "still retired.", size=14)
    footnote(slide, "A canary alone avoids outages only by luck: it refuses 67 "
                    "real requests and wrongly keeps 118 dead endpoints. "
                    "Measured misses match exp(-rate x days).")
    notes(slide, "[21:10, 50 s] Simulated estates - say so. The shadow is the "
                 "defence; the canary is the backstop that caught the one "
                 "slow caller.")


def slide_comparison(prs):
    slide = _blank(prs)
    y = heading(slide, "Comparative analysis - with and without API Exorcist")
    two_columns(
        slide, y,
        "Without it", [
            "6 of 8 zombies stay invisible to the inventory a bank has",
            "crAPI's brute-forceable v2 OTP check stays reachable beside "
            "its fix",
            "Debug endpoints (VAmPI _debug, createdb) ship and stay",
            "Removal on judgement: 49 outages on the gate's word",
            "Nothing stops the next zombie being created",
        ],
        "With it", [
            "8 of 8 found, each with signed reasons",
            "Ranked first, with the evidence and a retirement plan",
            "Flagged, traced to file and line",
            "0 outages: shadow, named approval, canary, rollback",
            "A pull request adding an undocumented, unowned endpoint fails",
        ],
        size=13)
    notes(slide, "[22:00, 40 s] The mentor's comparative ask. Each line was "
                 "measured or observed, not projected.")


def slide_limitations(prs):
    slide = _blank(prs)
    y = heading(slide, "Limitations", "Stated, not hidden")
    bullets(slide, y, [
        ("The banking estate is synthetic. The engine is measured on known "
         "answers; it has not run on a real bank's traffic.", 14, False, INK),
        ("Safe Kill's guarantee is as strong as its window: callers rarer "
         "than monthly need a longer shadow.", 14, False, INK),
        ("Django, Go, ASP.NET routes are not extracted yet; they are seen "
         "through the specification only.", 14, False, INK),
        ("Pending approvals live in memory, so the API runs as one replica.",
         14, False, INK),
        ("Live website scanning is designed (two-tier, DNS-proof for active "
         "probing) but not shipped in this version.", 14, False, INK),
    ], gap=12)
    notes(slide, "[22:40, 30 s] Say these before they are asked.")


def slide_future(prs):
    slide = _blank(prs)
    y = heading(slide, "Conclusion and Future Extensions")
    y = callout(slide, y,
                "API Exorcist finds what a bank's inventory misses, says what "
                "it cannot know, and removes a zombie without an outage - "
                "every decision explained and audited.", size=14.5)
    bullets(slide, y + Inches(0.22), [
        ("1.  Pilot on a real estate's logs and repositories, with its "
         "engineers confirming each finding.", 13.5, False, INK),
        ("2.  Gateway plugins (Kong, Envoy) so the shadow and canary act on "
         "real traffic.", 13.5, False, INK),
        ("3.  Business-calendar-aware shadow windows for quarterly and annual "
         "jobs.", 13.5, False, INK),
        ("4.  Django, Go, ASP.NET and NestJS route extraction.", 13.5, False,
         INK),
        ("5.  Durable multi-replica operation; audit head anchored in "
         "write-once storage.", 13.5, False, INK),
        ("6.  Live website scanning, passive first, active only with "
         "ownership proof.", 13.5, False, INK),
    ], gap=9)
    notes(slide, "[23:10, 20 s] One-sentence conclusion, then hand to "
                 "questions.")


def slide_references(prs):
    slide = _blank(prs)
    y = heading(slide, "References")
    refs = [
        '[1] D. Caivano et al., "On the spread and evolution of dead methods '
        'in Java desktop applications," Empirical Software Engineering, '
        '28(3), 2023.',
        '[2] P. Cassieri et al., "On deprecated API usages: an exploratory '
        'study of top-starred projects on GitHub," PROFES, 2023.',
        '[3] V. Bushong et al., "Using static analysis to address microservice '
        'architecture reconstruction," ASE, 2021.',
        '[4] S.-P. Ma et al., "Graph-based and scenario-driven microservice '
        'analysis, retrieval, and testing," FGCS, 100, 2019.',
        '[5] A. S. Abdelfattah, T. Cerny, "The microservice dependency '
        'matrix," ESOCC, 2023.',
        '[6] G. Dell\'Immagine et al., "KubeHound: detecting microservices\' '
        'security smells in Kubernetes deployments," Future Internet, 15(7), '
        '2023.',
        '[7] F. L. Ponce Mella et al., "Beyond security: understanding the '
        'multiple impacts of security smells for microservices," CLEI '
        'Electronic Journal, 27(2), 2024.',
        '[8] S. M. Lundberg, S.-I. Lee, "A unified approach to interpreting '
        'model predictions," NIPS, 2017.',
        '[9] D. Gaspar et al., "Explainable AI for intrusion detection '
        'systems: LIME and SHAP applicability on multi-layer perceptron," '
        'IEEE Access, 12, 2024.',
        '[10] Q. Scheitle et al., "The rise of certificate transparency and '
        'its implications on the internet ecosystem," IMC, 2018.',
        '[11] G. Brito et al., "On the use of replacement messages in API '
        'deprecation: an empirical study," JSS, 137, 2018.',
        '[12] M. E. Gortney et al., "Visualizing microservice architecture in '
        'the dynamic perspective: a systematic mapping study," IEEE Access, '
        '10, 2022.',
        '[13] OWASP, "API9:2023 Improper Inventory Management," OWASP API '
        'Security Top 10, 2023.',
        '[14] Reserve Bank of India, "Cyber Security Framework in Banks," '
        '2016.   [15] NIST SP 800-95, "Guide to Secure Web Services," 2007.',
    ]
    total = sum(_height_of(r, 10, CONTENT_W / EMU_PER_IN, 3) for r in refs)
    tf = _text(slide, MARGIN, y, CONTENT_W, Emu(total))
    for n, ref in enumerate(refs):
        _line(tf, ref, size=10, colour=INK, space_after=3, first=(n == 0))
    notes(slide, "[23:30, 5 s] Skip past.")


def slide_thanks(prs):
    slide = _blank(prs)
    y = logo(slide, Inches(2.0), Inches(1.6)) + Inches(0.2)
    tf = _text(slide, MARGIN, y, CONTENT_W, Inches(1.8),
               align=PP_ALIGN.CENTER)
    _line(tf, "Thank You", size=42, bold=True, colour=RED, first=True,
          align=PP_ALIGN.CENTER, space_after=14)
    _line(tf, "Questions", size=20, colour=MUTED, align=PP_ALIGN.CENTER,
          space_after=18)
    _line(tf, "github.com/shivanshjindal28/api-exorcist", size=14,
          colour=INK, align=PP_ALIGN.CENTER, space_after=0)
    notes(slide, "[23:30 - 30:00] Questions. Backup slides follow this one; "
                 "jump to them by number. Likely questions and answers are in "
                 "demo/DEMO.md, section 3.")


# ---------------------------------------------------------------------------
# Backup slides for questions (not presented)
# ---------------------------------------------------------------------------
def _backup_heading(slide, title, subtitle=""):
    return heading(slide, f"Backup - {title}", subtitle)


def backup_model(prs):
    slide = _blank(prs)
    y = _backup_heading(slide, "Why not just machine learning?",
                        "36 held-out generated estates, split by estate")
    y = table(slide, y, [
        ["Metric", "Rules", "Model"],
        ["Macro-F1", "0.843", "0.861"],
        ["ZOMBIE false positives", "14", "*0*"],
        ["DEPRECATED F1", "0.681", "0.587"],
    ], [0.50, 0.25, 0.25], size=13)
    bullets(slide, y + Inches(0.22), [
        ("A false zombie is an outage; a missed one is a line on a report. "
         "So the model is a veto: it may block a removal, never create one.",
         14, True, RED),
        ("Rules decide because a new deployment has zero labels on day one, "
         "and rules are auditable line by line.", 14, False, INK),
    ], gap=10)
    notes(slide, "Q: 'Why not ML?' / 'Is 96% too high?'")


def backup_gate(prs):
    slide = _blank(prs)
    y = _backup_heading(slide, "Blast radius",
                        "Removing GET /v2/accounts/{id} on the demo estate")
    y = table(slide, y, [
        ["Measure", "Value"],
        ["Direct callers", "3 (lending-service, mobile-bff, payments-service)"],
        ["Services affected in total", "9"],
        ["Depth reached", "5 hops"],
        ["Endpoints degraded", "13"],
    ], [0.45, 0.55], size=13)
    callout(slide, y + Inches(0.22),
            "A one-hop check would report three and miss six. Isolation means "
            "no dependency was OBSERVED - which is why Safe Kill follows the "
            "gate.", size=13.5)
    notes(slide, "Q: 'What if it deletes something important?'")


def backup_sources(prs):
    slide = _blank(prs)
    y = _backup_heading(slide, "What if the six sources are not all there?",
                        "Rules abstain, and the system says what it lost")
    table(slide, y, [
        ["Sources available", "Rules usable", "What the system may claim"],
        ["All six", "15 / 15", "Full lifecycle classification"],
        ["Repository only (code, spec, CI/CD)", "6 / 15",
         "Candidates, never a lifecycle label"],
        ["Repository + access logs", "-", "Lifecycle from real usage"],
        ["Gateway only", "0 / 15", "Lists endpoints, classifies nothing"],
    ], [0.40, 0.18, 0.42], size=12.5)
    notes(slide, "Q: 'Banks will not give you all six sources.' / 'A random "
                 "repo found 0 candidates.'")


def backup_identify(prs):
    slide = _blank(prs)
    y = _backup_heading(slide, "How endpoints are identified",
                        "Every source reduces what it sees to METHOD /path")
    table(slide, y, [
        ["Source", "How", "Blind spot"],
        ["Code", "Semgrep AST rules: FastAPI, Flask, Express, Spring; "
         "router and mount prefixes resolved", "Written is not deployed"],
        ["Specification", "OpenAPI / Swagger paths x methods, with the "
         "server prefix", "Whatever nobody documented"],
        ["CI/CD", "Workflow files: a pipeline that could ship the route",
         "Manual deployments"],
        ["Gateway", "Route registry (Kong / Apigee admin API)",
         "Services addressed directly"],
        ["Traffic", "Access logs matched to route templates; IDs become "
         "{id}", "Anything silent"],
        ["DNS", "Resolvable hosts, service mesh", "Cluster-internal only"],
    ], [0.17, 0.53, 0.30], size=11)
    notes(slide, "Q: 'How exactly do you find the endpoints?' On real scans "
                 "code, spec and CI/CD are real; gateway and DNS rules "
                 "abstain; traffic comes from imported logs.")


def backup_quality(prs):
    slide = _blank(prs)
    y = _backup_heading(slide, "Is it production-ready?")
    bullets(slide, y, [
        ("Tokens stored only as hashes; every route authenticated; viewer and "
         "approver roles; the approver's name comes from the token.",
         14, False, INK),
        ("Hash-chained audit log, safe under concurrent writers.", 14, False,
         INK),
        ("Container: non-root, read-only filesystem, no capabilities, "
         "digest-pinned base, no pip; refuses to start without tokens.",
         14, False, INK),
        ("307 Python and 51 dashboard tests, mypy strict, three ground-truth "
         "leakage guards; CI on every push.", 14, False, INK),
        ("Not yet: run on a real bank's traffic, multiple replicas, gateway "
         "plugins. Nothing here claims otherwise.", 14, True, RED),
    ], gap=12)
    notes(slide, "Q: 'Is it production-ready?' / 'Can it be deployed?' - "
                 "Docker image on any container host with a disk; not "
                 "serverless.")


BUILDERS = [
    slide_title, slide_contents, slide_intro, slide_four_states,
    slide_literature, slide_gap, slide_problem, slide_objectives, slide_tools,
    slide_market, slide_design, slide_scan_flow, slide_algo_classify,
    slide_algo_safekill, slide_algo_candidates, slide_contribution_map,
    slide_demo, slide_results_benchmark, slide_results_real,
    slide_results_safekill, slide_comparison, slide_limitations, slide_future,
    slide_references, slide_thanks,
    backup_identify, backup_sources, backup_model, backup_gate, backup_quality,
]


def main() -> int:
    prs = Presentation()
    prs.slide_width = SLIDE_W
    prs.slide_height = SLIDE_H
    for builder in BUILDERS:
        builder(prs)
    prs.save(OUTPUT)
    print(f"  built {OUTPUT.name}  ({len(prs.slides._sldIdLst)} slides)")
    if not TEMPLATE.exists():
        print("  WARNING: docs/assets/mpstme-template.jpg is missing.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
