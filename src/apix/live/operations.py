"""
Handlers wired by the specification rather than by decorators.

Two widespread ways of building an API declare routes only in the OpenAPI
document and connect each operation to code by its `operationId`:

    Connexion (Python)      operationId: api_views.users.debug
                            -> def debug(...) in api_views/users.py
    API-first Spring        an interface generated from openapi.yml at build
    (openapi-generator)     time, implemented by a controller whose method is
                            named after the operationId (@Override, no mapping
                            annotation); the generated interface is not committed

A decorator-based extractor sees nothing in either. Scanning OWASP-adjacent
VAmPI (Connexion) and spring-petclinic-rest (API-first) reported their
handlers as missing, and every documented endpoint as "documented but not
implemented", which is false. This module finds the handler a spec operation
names, so those endpoints are seen by code like any other.

A match is evidence that a handler exists with that name, not proof the
framework wires it; the report says which endpoints were matched this way.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path

from apix.live.repo import RepoScan

_PY_DEF = r"^\s*(?:async\s+)?def\s+{name}\s*\("
_JAVA_METHOD = (
    r"^\s*(?:@\w+(?:\([^)]*\))?\s*)*(?:public|protected)\s+(?:static\s+)?"
    r"[\w<>\[\],.?\s]+?\s+{name}\s*\("
)
_JS_FN = r"(?:function\s+{name}\s*\(|\b{name}\s*[:=]\s*(?:async\s*)?(?:function|\())"
_CONTROLLERISH = re.compile(
    r"@(Rest)?Controller\b|\bimplements\s+[\w.,\s]*Api\b|class\s+\w*(Controller|Resource|Api)\b"
)


@dataclass(frozen=True)
class OperationHandler:
    operation_id: str
    file: str
    line: int
    language: str


def find_handlers(scan: RepoScan, operation_ids: set[str]) -> dict[str, OperationHandler]:
    """operationId -> the handler that implements it, where one can be found."""
    if not operation_ids:
        return {}
    texts: dict[str, tuple[Path, str]] = {}
    for p in scan._walk():
        suffix = p.suffix.lower()
        if suffix not in (".py", ".java", ".kt", ".js", ".ts", ".mjs"):
            continue
        rel = scan.rel(p)
        if re.search(r"(^|/)(test|tests|__tests__)(/|$)|Tests?\.(java|kt)$|(^|/)test_|"
                     r"(^|/)tests?\.py$", rel):
            continue
        try:
            texts[rel] = (p, p.read_text(encoding="utf-8", errors="replace"))
        except OSError:
            continue

    found: dict[str, OperationHandler] = {}
    for op in sorted(operation_ids):
        handler = _find(op, texts)
        if handler:
            found[op] = handler
    return found


def _line(text: str, pos: int) -> int:
    return text.count("\n", 0, pos) + 1


def _find(op: str, texts: dict[str, tuple[Path, str]]) -> OperationHandler | None:
    # Connexion: a dotted path names the module and the function.
    if "." in op:
        module, _, name = op.rpartition(".")
        if not re.fullmatch(r"\w+", name):
            return None
        wanted = module.replace(".", "/")
        for rel, (_, text) in texts.items():
            stem = rel.rsplit(".", 1)[0]
            if rel.endswith(".py") and (stem == wanted or stem.endswith("/" + wanted)
                                        or stem == wanted + "/__init__"):
                m = re.search(_PY_DEF.format(name=re.escape(name)), text, re.M)
                if m:
                    return OperationHandler(op, rel, _line(text, m.start()), "python")
        return None

    if not re.fullmatch(r"[A-Za-z_]\w*", op):
        return None
    # Java/Kotlin: a public method of that name in a controller or Api implementation.
    for rel, (_, text) in texts.items():
        if rel.endswith((".java", ".kt")) and _CONTROLLERISH.search(text):
            m = re.search(_JAVA_METHOD.format(name=re.escape(op)), text, re.M)
            if m:
                return OperationHandler(op, rel, _line(text, m.end()), "java")
    # Python and JavaScript, plain names (swagger-tools, oas-tools, Connexion
    # with a resolver): a function of that name in a controller-like module.
    for rel, (_, text) in texts.items():
        if not re.search(r"controller|handler|api|view|route", rel, re.I):
            continue
        if rel.endswith(".py"):
            m = re.search(_PY_DEF.format(name=re.escape(op)), text, re.M)
            if m:
                return OperationHandler(op, rel, _line(text, m.start()), "python")
        elif rel.endswith((".js", ".ts", ".mjs")):
            m = re.search(_JS_FN.format(name=re.escape(op)), text)
            if m:
                return OperationHandler(op, rel, _line(text, m.start()), "javascript")
    return None
