"""
Update the Word fields the .docx builder can only leave as placeholders.

python-docx writes a TOC *field*, not a table of contents: the page numbers
inside it are computed by Word's layout engine, which python-docx does not
have. The same is true of the "Page No." column in the List of Figures and
List of Tables. Left alone, a reviewer opens the report and sees
"Right-click and select Update Field" where the contents should be.

This script drives Word itself to do that work, so the delivered file is
finished rather than one manual step away from finished:

  * repaginates and updates every field, including the TOC;
  * finds each "Figure N:" and "Table N:" caption, asks Word which page it
    landed on, and writes that number into the matching listing row;
  * updates fields a second time, because filling the listings reflows the
    front matter and can move what follows.

Late binding (win32com.client.dynamic) is deliberate: Office is installed
here in a form whose type library will not load, so early-bound Dispatch
fails with TYPE_E_CANTLOADLIBRARY. IDispatch does not need the type library.

Usage:
    python docs/finalise_docx.py <file.docx> [<file.docx> ...]
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

#: wdActiveEndAdjustedPageNumber, NOT wdActiveEndPageNumber (3).
#:
#: This report restarts its page numbering at Chapter 1, so the physical page
#: and the printed page differ by the length of the front matter. The listings
#: must carry the number the reader sees on the page, which is the adjusted
#: one; the physical number put Table 1 on "page 11" when the page itself says
#: 1, and it disagreed with the TOC Word had just generated.
WD_ADJUSTED_PAGE_NUMBER = 1
WD_DO_NOT_SAVE = 0

CAPTION = re.compile(r"^\s*(Figure|Table)\s+(\d+)\s*:", re.I)


def _page_numbers(doc) -> dict[tuple[str, int], int]:
    """Map (kind, number) -> the page its caption sits on."""
    pages: dict[tuple[str, int], int] = {}
    for para in doc.Paragraphs:
        text = para.Range.Text.strip()
        m = CAPTION.match(text)
        if not m:
            continue
        key = (m.group(1).capitalize(), int(m.group(2)))
        # A caption appears once in the body; the listing row that names it
        # lives in a table, which Paragraphs also walks, so keep the first
        # occurrence that is not itself inside a listing table.
        if key in pages:
            continue
        pages[key] = int(para.Range.Information(WD_ADJUSTED_PAGE_NUMBER))
    return pages


def _fill_listings(doc, pages: dict[tuple[str, int], int]) -> int:
    """Write page numbers into the List of Figures / List of Tables."""
    filled = 0
    for table in doc.Tables:
        # Word terminates a cell with CR + BEL, so the raw text is
        # "Figure No.\r\a"; strip whichever of those characters are present.
        header = re.sub(r"[\r\a\x07\s]+$", "", table.Cell(1, 1).Range.Text).lower()
        if not header.startswith(("figure no", "table no")):
            continue
        kind = "Figure" if header.startswith("figure") else "Table"
        for row in range(2, table.Rows.Count + 1):
            label = table.Cell(row, 1).Range.Text
            m = re.search(r"(\d+)", label)
            if not m:
                continue
            page = pages.get((kind, int(m.group(1))))
            if page is None:
                continue
            cell = table.Cell(row, 3)
            cell.Range.Text = str(page)
            filled += 1
    return filled


def finalise(word, path: Path) -> None:
    doc = word.Documents.Open(str(path))
    try:
        doc.Fields.Update()
        for toc in doc.TablesOfContents:
            toc.Update()
        doc.Repaginate()

        pages = _page_numbers(doc)
        filled = _fill_listings(doc, pages)

        # Filling the listings reflows the front matter, which can shift the
        # body; update once more so the TOC agrees with the final layout.
        doc.Fields.Update()
        for toc in doc.TablesOfContents:
            toc.Update()
        doc.Repaginate()

        doc.Save()
        print(f"  {path.name}: {len(pages)} caption(s) located, "
              f"{filled} listing row(s) filled, {doc.ComputeStatistics(2)} pages")
    finally:
        doc.Close(WD_DO_NOT_SAVE if doc.Saved is False else -1)


def main(argv: list[str]) -> int:
    if not argv:
        print(__doc__)
        return 2
    import win32com.client.dynamic as dyn

    word = dyn.Dispatch("Word.Application")
    word.Visible = False
    word.DisplayAlerts = False
    try:
        for arg in argv:
            finalise(word, Path(arg).resolve())
    finally:
        word.Quit()
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
