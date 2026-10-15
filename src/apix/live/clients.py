"""
Which endpoints the project's own clients use.

A repository often ships the code that consumes its API: a web or mobile front
end, another service, a generated SDK. What that code references is the best
evidence of use a repository holds. An endpoint no bundled client references,
in a project whose clients reference its neighbours, is how a zombie looks
before anyone measures traffic.

Two kinds of reference:

    path literals      a client file names the endpoint's path: crAPI's web app
                       holds "api/auth/v3/check-otp" for the endpoint
                       /identity/api/auth/v3/check-otp, and never "v2/check-otp"
    generated clients  an SDK generated from the spec names every endpoint, so
                       its presence proves nothing. What counts is whether app
                       code calls the generated function: UsersService.readUsers(
                       in a component means GET /api/v1/users/ is used.

Matching is by the end of the path, because clients often leave out a prefix
the server or a gateway adds. It needs two or more segments to agree, so a
bare "/users" cannot claim every users endpoint in a monorepo. A reference
proves the code can call the endpoint, not that production does; nor does the
absence of one prove nothing outside the repository calls it. The report
words both that way.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

from apix.live.repo import RepoScan, service_of

_CLIENT_SUFFIXES = {".js", ".jsx", ".ts", ".tsx", ".mjs", ".vue", ".svelte", ".dart",
                    ".py", ".java", ".kt", ".swift", ".go"}
_TEST_PATH = re.compile(
    r"(^|/)(test|tests|__tests__|spec|e2e|cypress|playwright|__mocks__)(/|$)|"
    # tests.py is Django's convention (crAPI's workshop/crapi/merchant/tests.py).
    r"(Test|Tests|IT)\.(java|kt)$|(^|/)test_[^/]*\.py$|(^|/)tests?\.py$|_tests?\.(py|go)$|"
    r"\.(test|spec)\.[jt]sx?$",
)
_GENERATED_MARK = re.compile(
    r"auto-?generated|do not edit|@hey-api|openapi-typescript-codegen|openapi-generator|"
    r"orval|swagger-codegen|this file was generated", re.I)
_LITERAL = re.compile(
    # <...> is in the set: crAPI's web app writes "api/v2/user/videos/<videoId>".
    r"""["'`]((?:https?://[^"'`\s/]+)?/?[A-Za-z0-9_\-.{}$:<>]+(?:/[A-Za-z0-9_\-.{}$:<>]*)+)["'`]""")
_FUNC_START = re.compile(
    r"(?:public\s+static\s+(?:async\s+)?|export\s+const\s+|export\s+(?:async\s+)?function\s+"
    r"|^\s*(?:async\s+)?)(\w+)\s*(?:<[^>]*>)?\s*(?:=\s*(?:async\s*)?\(|\()", re.M)
_METHOD_IN_BODY = re.compile(r"""\.(get|post|put|patch|delete)\s*<|method\s*:\s*["'](\w+)["']""", re.I)
_SKIP_LINE = re.compile(r"^\s*(import\b|export\s+\*|from\s+\S+\s+import|#include|//|\*|<link|@import)|require\(")


#: A reference from these files is a front end or app talking to the API.
#: Anything else (Java, Python, Go) is one service calling another, which is
#: evidence of use but says nothing about which public endpoints a UI covers.
FRONTEND_SUFFIXES = {".js", ".jsx", ".ts", ".tsx", ".mjs", ".vue", ".svelte", ".dart",
                     ".swift"}


@dataclass(frozen=True)
class ClientRef:
    service: str          # the client's service, e.g. "web", "frontend"
    path: str             # as written, parameters as {param}
    method: str           # ANY unless a generated client says
    file: str
    line: int
    via: str              # human-readable: how the reference was found

    @property
    def frontend(self) -> bool:
        return any(self.file.lower().endswith(s) for s in FRONTEND_SUFFIXES)


@dataclass
class ClientRefs:
    refs: list[ClientRef] = field(default_factory=list)
    generated_files: list[str] = field(default_factory=list)
    #: generated function -> (method, path), for functions no code calls
    uncalled_generated: list[tuple[str, str, str]] = field(default_factory=list)
    client_files: int = 0


def _clean(raw: str, concatenated: bool = False) -> str | None:
    """A literal as a path, or None. `concatenated`: the code appends a value
    to it ("/api/accounts/" + id), so a trailing slash stands for one more
    segment. Otherwise a trailing slash is just how the path is spelled, as in
    FastAPI's "/api/v1/users/"."""
    raw = re.sub(r"^https?://[^/]+", "", raw.strip())
    if not concatenated:
        raw = raw.rstrip("/") or raw
    raw = raw.split("?", 1)[0].split("#", 1)[0]
    if raw.startswith(("./", "../", "@", "~")) or re.search(
            r"\.(js|jsx|ts|tsx|css|scss|png|svg|jpe?g|gif|ico|json|html?|md|vue|map|woff2?)$", raw):
        return None
    raw = re.sub(r"\$\{[^}]*\}|\{[^}]*\}|<[^>/]*>|:[A-Za-z_]\w*", "{param}", raw)
    if raw.endswith("/") and raw.count("/") > 1:
        raw = raw + "{param}"
    segs = [s for s in raw.split("/") if s]
    literal = [s for s in segs if s != "{param}"]
    if len(segs) < 2 or len(literal) < 2 or any(" " in s for s in segs):
        return None
    if all(re.fullmatch(r"[\d.]+", s) for s in literal):
        return None
    return "/" + "/".join(segs)


def _line(text: str, pos: int) -> int:
    return text.count("\n", 0, pos) + 1


def collect_client_refs(scan: RepoScan) -> ClientRefs:
    out = ClientRefs()
    plain: dict[str, str] = {}
    generated: dict[str, str] = {}
    for p in scan._walk():
        if p.suffix.lower() not in _CLIENT_SUFFIXES:
            continue
        rel = scan.rel(p)
        if _TEST_PATH.search(rel):
            continue
        try:
            text = p.read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue
        if len(text) > 2_000_000:
            continue
        head = text[:1500]
        if _GENERATED_MARK.search(head) or re.search(r"(\.gen\.|/generated/|/gen/)", rel):
            generated[rel] = text
        else:
            plain[rel] = text
    out.client_files = len(plain)
    out.generated_files = sorted(generated)

    # Path literals in hand-written code.
    for rel, text in plain.items():
        service = service_of(rel)
        for m in _LITERAL.finditer(text):
            line_start = text.rfind("\n", 0, m.start()) + 1
            line_text = text[line_start: text.find("\n", m.end()) if "\n" in text[m.end():] else len(text)]
            if _SKIP_LINE.search(line_text):
                continue
            path = _clean(m.group(1), concatenated=bool(re.match(r"\s*\+", text[m.end():m.end() + 8])))
            if path:
                out.refs.append(ClientRef(service, path, "ANY", rel, _line(text, m.start()),
                                          "path referenced in code"))

    # Generated clients: a function counts only if hand-written code calls it.
    called_text = "\n".join(plain.values())
    for text in generated.values():
        starts = [(m.start(), m.group(1)) for m in _FUNC_START.finditer(text)
                  if m.group(1) not in {"if", "for", "while", "switch", "return", "function",
                                        "catch", "constructor"}]
        for i, (pos, name) in enumerate(starts):
            body = text[pos: starts[i + 1][0] if i + 1 < len(starts) else len(text)]
            paths = [c for c in (_clean(lm.group(1)) for lm in _LITERAL.finditer(body)) if c]
            if not paths:
                continue
            mm = _METHOD_IN_BODY.search(body)
            method = (mm.group(1) or mm.group(2)).upper() if mm else "ANY"
            # A static method is called through its class: UsersService.createUser(
            # and PrivateService.createUser( are different endpoints.
            cls = None
            cls_m = list(re.finditer(r"\bclass\s+(\w+)", text[:pos]))
            if cls_m and "static" in text[pos: pos + 40]:
                cls = cls_m[-1].group(1)
            call_re = (rf"\b{re.escape(cls)}\s*\.\s*{re.escape(name)}\s*\(" if cls
                       else rf"\.{re.escape(name)}\s*\(|\b{re.escape(name)}\s*\(")
            caller = re.search(call_re, called_text)
            if caller is None:
                out.uncalled_generated.append((name, method, paths[0]))
                continue
            # Which file calls it, for the evidence line.
            for crel, ctext in plain.items():
                cm = re.search(call_re, ctext)
                if cm:
                    out.refs.append(ClientRef(service_of(crel), paths[0], method, crel,
                                              _line(ctext, cm.start()),
                                              f"calls generated client function {name}()"))
                    break
    return out


# ---------------------------------------------------------------------------
def _segs(path: str) -> list[str]:
    return [s for s in path.strip("/").split("/") if s]


def _param(s: str) -> bool:
    return s.startswith("{") and s.endswith("}")


def ref_score(ref_path: str, endpoint_path: str) -> int:
    """How many literal segments agree when the two are aligned at the end;
    0 when they disagree or too little agrees to mean anything."""
    r, e = _segs(ref_path), _segs(endpoint_path)
    n = min(len(r), len(e))
    if n < 2:
        return 0
    literal = structural = 0
    for a, b in zip(r[-n:], e[-n:], strict=True):
        if _param(a) and _param(b):
            structural += 1          # a parameter where the endpoint has one
            continue
        if _param(a) or _param(b):
            continue
        if a != b:
            return 0
        literal += 1
    # A shorter reference must agree on at least two literal segments, so
    # "/users" cannot claim every users endpoint. Literal agreement counts
    # double; a parameter lining up with a parameter breaks the tie between
    # /users/{user_id} and /users/me for a reference to /users/{param}, which
    # first counted as ambiguous and left the front end's deleteUser() unseen.
    return 2 * literal + structural if literal >= 2 else 0


def match_refs(refs: list[ClientRef], endpoints: list[tuple[str, str, str, str]]
               ) -> list[tuple[ClientRef, str]]:
    """(reference, endpoint id) pairs, from (id, method, path, service) tuples.

    A reference from the endpoint's own service is the server naming its own
    route (route tables, security config), not a client, and is ignored. Among
    paths that match equally well none is chosen: an ambiguous reference is not
    evidence for any of them.
    """
    out: list[tuple[ClientRef, str]] = []
    for ref in refs:
        scored: list[tuple[int, str, str, str]] = []
        for eid, method, path, service in endpoints:
            if service == ref.service:
                continue
            if ref.method not in ("ANY", method) and method != "ANY":
                continue
            s = ref_score(ref.path, path)
            if s:
                scored.append((s, path, eid, method))
        if not scored:
            continue
        best = max(s for s, *_ in scored)
        top = [x for x in scored if x[0] == best]
        if len({p for _, p, _, _ in top}) > 1:
            continue
        out.extend((ref, eid) for _, _, eid, _ in top)
    return out
