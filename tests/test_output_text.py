"""
Tests for text a person reads at runtime: CLI output, API messages, the
dashboard's explanations.

Run:  python tests/test_output_text.py

No em dash may appear in a runtime string. Two reasons, both found in practice:
a Windows console renders it as a replacement character, so `Do NOT schedule
removal — this endpoint...` printed as `removal ? this endpoint`; and the
reports and demo deliberately avoid it, and these messages appear on screen in
the same review. Docstrings and comments are exempt: nobody sees them run.
"""

from __future__ import annotations

import ast
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
EM_DASH = "—"


def _docstring_nodes(tree: ast.AST) -> set[int]:
    out: set[int] = set()
    for node in ast.walk(tree):
        if isinstance(node, (ast.Module, ast.ClassDef, ast.FunctionDef, ast.AsyncFunctionDef)):
            body = node.body
            if body and isinstance(body[0], ast.Expr) and isinstance(body[0].value, ast.Constant):
                out.add(id(body[0].value))
    return out


def test_no_em_dash_in_runtime_strings() -> None:
    offenders: list[str] = []
    scanned = 0
    for path in (ROOT / "src" / "apix").rglob("*.py"):
        scanned += 1
        tree = ast.parse(path.read_text(encoding="utf-8"))
        docs = _docstring_nodes(tree)
        for node in ast.walk(tree):
            if (
                isinstance(node, ast.Constant)
                and isinstance(node.value, str)
                and EM_DASH in node.value
                and id(node) not in docs
            ):
                rel = path.relative_to(ROOT)
                offenders.append(f"{rel}:{node.lineno}: {node.value.strip()[:60]!r}")
    assert scanned > 0, "scanned no source files"
    assert not offenders, "em dash in runtime text:\n" + "\n".join(offenders)


def test_no_em_dash_in_dashboard_text() -> None:
    src = ROOT / "dashboard" / "src"
    offenders = [
        str(p.relative_to(ROOT))
        for p in src.rglob("*")
        if p.suffix in (".ts", ".tsx") and EM_DASH in p.read_text(encoding="utf-8")
    ]
    assert not offenders, f"em dash in dashboard source: {offenders}"


if __name__ == "__main__":
    for t in (test_no_em_dash_in_runtime_strings, test_no_em_dash_in_dashboard_text):
        t()
        print(f"  PASS  {t.__name__}")
    sys.exit(0)
