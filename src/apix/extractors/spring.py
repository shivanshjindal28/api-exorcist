"""
Spring MVC routes: the path a mapped method actually serves.

Semgrep finds every method carrying a mapping annotation; this module reads the
annotation text and works out the full path, because the structural pattern
alone got two things wrong on a real Spring Boot repository:

- **The class-level prefix was ignored.** A controller annotated
  `@RequestMapping("/api/customers")` serves its `@GetMapping("/{id}")` at
  `/api/customers/{id}`. Without the prefix every service's `GET /{id}` looked
  the same, and identical method-level paths in different controllers merged
  into one endpoint.
- **Routes with no path of their own were missed.** A bare `@PostMapping`, the
  usual "create" endpoint, serves the class prefix itself.

Also handled: `value =` and `path =` forms, arrays of paths, `@PatchMapping`,
and method-level `@RequestMapping(method = RequestMethod.X)`. A prefix given as
a constant (`@RequestMapping(ApiPaths.BASE)`) is not resolved, because its value
lives in other code, which a scanner reads but never evaluates; the route is
returned relative to it and flagged.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

_ANNOTATION = re.compile(r"@(Get|Post|Put|Delete|Patch|Request)Mapping\b")
_CLASS_DECL = re.compile(r"\b(class|interface|record)\s+[A-Za-z_]\w*")
_LITERAL = re.compile(r'"((?:[^"\\]|\\.)*)"')
_NAMED_PATH = re.compile(r"\b(value|path)\s*=\s*(\{[^}]*\}|\"(?:[^\"\\]|\\.)*\"|[\w.]+)")
_METHODS = re.compile(r"RequestMethod\s*\.\s*(GET|POST|PUT|DELETE|PATCH|HEAD|OPTIONS)")

_VERB = {"Get": "GET", "Post": "POST", "Put": "PUT", "Delete": "DELETE", "Patch": "PATCH"}


@dataclass(frozen=True)
class Mapping:
    paths: list[str]                 # [""] when the annotation names no path
    methods: list[str]               # empty: every method (bare @RequestMapping)
    unresolved: str | None = None    # a constant used as the path, if any


@dataclass(frozen=True)
class SpringRoute:
    method: str
    path: str
    resolved: bool
    expression: str | None = None


def _balanced(text: str, start: int) -> str:
    """The text between the parenthesis at `start` and its partner."""
    depth, i, quoted = 0, start, False
    while i < len(text):
        c = text[i]
        if quoted:
            if c == "\\":
                i += 1
            elif c == '"':
                quoted = False
        elif c == '"':
            quoted = True
        elif c == "(":
            depth += 1
        elif c == ")":
            depth -= 1
            if depth == 0:
                return text[start + 1 : i]
        i += 1
    return text[start + 1 :]


def parse_mapping(args: str) -> Mapping:
    """What a mapping annotation's argument list says."""
    args = args.strip()
    methods = sorted(set(_METHODS.findall(args)))
    if not args:
        return Mapping([""], methods)
    named = _NAMED_PATH.search(args)
    if named:
        target = named.group(2)
    else:
        # Positional: the first argument, if it is not a named one.
        first = args.split(",", 1)[0].strip() if not args.startswith("{") \
            else args[: args.find("}") + 1]
        target = "" if "=" in first else first
    if not target:
        return Mapping([""], methods)
    literals = _LITERAL.findall(target)
    if literals:
        return Mapping(literals, methods)
    return Mapping([""], methods, unresolved=target.strip())


def _annotation_at(text: str, pos: int) -> tuple[str, str] | None:
    """(kind, argument text) of the mapping annotation found from `pos`."""
    m = _ANNOTATION.search(text, pos)
    if not m:
        return None
    rest = text[m.end():]
    stripped = rest.lstrip()
    if stripped.startswith("("):
        open_at = m.end() + (len(rest) - len(stripped))
        return m.group(1), _balanced(text, open_at)
    return m.group(1), ""


def class_prefix(lines: list[str], method_line: int) -> Mapping:
    """The @RequestMapping on the class that encloses `method_line` (0-based)."""
    decl = None
    for i in range(min(method_line, len(lines) - 1), -1, -1):
        code = lines[i].split("//", 1)[0]
        if _CLASS_DECL.search(code) and "new " not in code:
            decl = i
            break
    if decl is None:
        return Mapping([""], [])
    # The annotations sit directly above the declaration, possibly with
    # blank lines, comments and other annotations in between.
    top = decl
    for i in range(decl - 1, max(-1, decl - 40), -1):
        s = lines[i].strip()
        if s == "" or s.startswith(("@", "//", "/*", "*", "*/", ")", '"', "}")) \
                or s.endswith((",", "(")):
            top = i
            continue
        break
    block = "\n".join(lines[top : decl + 1])
    m = re.search(r"@RequestMapping\b", block)
    if not m:
        return Mapping([""], [])
    found = _annotation_at(block, m.start())
    return parse_mapping(found[1]) if found else Mapping([""], [])


def _join(prefix: str, path: str) -> str:
    joined = "/" + "/".join(p.strip("/") for p in (prefix, path) if p.strip("/"))
    return joined


def routes_for(source: str, start_line: int) -> list[SpringRoute]:
    """Every (method, full path) a mapped method serves.

    `start_line` is the 1-based line where Semgrep's match begins, which is the
    method's first annotation.
    """
    lines = source.splitlines()
    if not 0 < start_line <= len(lines):
        return []
    offset = sum(len(line) + 1 for line in lines[: start_line - 1])
    found = _annotation_at(source, offset)
    if not found:
        return []
    kind, args = found
    own = parse_mapping(args)
    cls = class_prefix(lines, start_line - 1)

    # A method-level @RequestMapping with no method= serves every method,
    # reported as ANY.
    methods = [_VERB[kind]] if kind in _VERB else (own.methods or ["ANY"])

    unresolved = own.unresolved or cls.unresolved
    out: list[SpringRoute] = []
    for prefix in cls.paths:
        for path in own.paths:
            full = _join(prefix, path)
            for method in methods:
                out.append(SpringRoute(method, full, unresolved is None, unresolved))
    return out
