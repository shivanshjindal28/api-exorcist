"""
Dependencies read from code: who calls what, what is routed where, which
services talk through which topics.

The dependency graph in the demo bank is built from observed traffic. A
repository has no traffic, but its code says a good deal about how its services
depend on one another, and this module reads three kinds of it:

    HTTP calls       a service's client code calling another's endpoint
                     (Spring RestClient / WebClient / RestTemplate / Feign,
                     fetch and axios, Python requests and httpx)
    gateway routes   a gateway configuration sending a path pattern to a service
                     (Spring Cloud Gateway, in YAML)
    message topics   a service publishing to or consuming from a topic
                     (Kafka, RabbitMQ)

Only HTTP calls feed the blast radius, because only they make one endpoint's
removal break another service. A gateway route exposes endpoints; it does not
depend on any single one. A topic connects services, not endpoints.

What this cannot see, and the graph page says: callers outside the repository
(a mobile app, another team's service), calls whose URL is built at run time
from values the code does not spell out, and anything the code could call but
production never does. It is a graph of what the code *can* call. Nothing is
executed to find it: every file is read as text.
"""

from __future__ import annotations

import re
from collections.abc import Iterator
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from apix.extractors.spring import routes_for
from apix.live.repo import RepoScan

_CODE_SUFFIXES = {".java", ".kt", ".py", ".js", ".jsx", ".ts", ".tsx", ".mjs", ".cjs"}
_CONFIG_SUFFIXES = {".yml", ".yaml"}
_MAX_FILE_BYTES = 1_000_000
_TEST_PATH = re.compile(
    r"(^|/)(test|tests|__tests__|spec|e2e|testing)(/|$)|"
    r"(Test|Tests|IT)\.(java|kt)$|(^|/)test_[^/]*\.py$|_test\.py$|\.(test|spec)\.[jt]sx?$",
)

# -- HTTP -----------------------------------------------------------------
_VERBS = "get|post|put|delete|patch"
# A literal that looks like a URL or an absolute path.
_URLISH = r"""(?:https?://[^"'`\s]+|/[^"'`\s]*)"""
# Java/Kotlin fluent clients: restClient.post().uri("/x"), webClient.get().uri(...)
_FLUENT_URI = re.compile(r"""\.uri\(\s*["']([^"']+)["']""")
_FLUENT_VERB = re.compile(rf"\.({_VERBS})\(\s*\)|\.method\(\s*HttpMethod\.([A-Z]+)", re.I)
# RestTemplate
_REST_TEMPLATE = re.compile(
    r"\b\w*[Rr]est[Tt]emplate\.(getForObject|getForEntity|postForObject|postForEntity|"
    r"postForLocation|put|delete|patchForObject|exchange)\s*\(([^;]{0,300})",
)
_RT_VERB = {"getForObject": "GET", "getForEntity": "GET", "postForObject": "POST",
            "postForEntity": "POST", "postForLocation": "POST", "put": "PUT",
            "delete": "DELETE", "patchForObject": "PATCH"}
_HTTP_METHOD = re.compile(r"HttpMethod\.([A-Z]+)")
# fetch("/x", { method: "POST" }) / fetch(`${base}/x`)
_FETCH = re.compile(r"""\bfetch\(\s*([`"'])((?:(?!\1).){1,300})\1([^)]{0,200})""")
_JS_METHOD = re.compile(r"""method\s*:\s*["'`]([A-Za-z]+)["'`]""")
# client.get("/x") style: axios, requests, httpx, sessions, Angular HttpClient
_CLIENT_CALL = re.compile(
    rf"""\b([\w.$]+)\.({_VERBS})\(\s*(f?)(["'`])((?:(?!\4).){{1,300}})\4(\s*,\s*[^)]*)?""",
    re.I,
)
# Receivers that register routes rather than call them (Express, Flask, FastAPI).
_ROUTE_RECEIVERS = {"app", "router", "server", "route", "routes", "api_router",
                    "bp", "blueprint", "r", "fastify"}
# A generic `.get("/x")` is only a call when the receiver looks like an HTTP
# client. Without this, `settings.get("/a/b")` and `cache.get("/key")` became
# dependencies; the fixture in tests/test_deps.py holds the case.
_CLIENT_RECEIVER = re.compile(r"axios|http|client|api|session|requests?|httpx|^ky$|^got$|fetch", re.I)
_HANDLER_ARG = re.compile(r"^\s*,\s*(async\s+)?(function\b|\(|\w+\s*=>|[A-Za-z_$][\w$]*\s*\))")

# -- messaging --------------------------------------------------------------
_KAFKA_LISTENER = re.compile(r"@KafkaListener\s*\(([^)]*)\)", re.S)
_RABBIT_LISTENER = re.compile(r"@RabbitListener\s*\(([^)]*)\)", re.S)
_TOPICS_ARG = re.compile(r"\b(topics|queues)\s*=\s*(\{[^}]*\}|[^,)]+)")
_KAFKA_SEND = re.compile(r"\b\w*[Kk]afka[Tt]emplate\.send\(\s*([^,)]+)")
_RABBIT_SEND = re.compile(r"\b\w*[Rr]abbit[Tt]emplate\.convertAndSend\(\s*([^,)]+)")
_JS_SEND = re.compile(r"""\.send\(\s*\{\s*topic\s*:\s*([^,}]+)""")
_JS_SUBSCRIBE = re.compile(r"""\.subscribe\(\s*\{\s*topics?\s*:\s*(\[[^\]]*\]|[^,}]+)""")
_PY_PRODUCE = re.compile(r"""\b\w*producer\.(?:send|produce)\(\s*([^,)]+)""", re.I)
_PY_SUBSCRIBE = re.compile(r"""\bsubscribe\(\s*(\[[^\]]*\]|[^,)]+)""")
_STRING_CONST = re.compile(r"""\b(?:static\s+final\s+)?String\s+([A-Z][A-Z0-9_]*)\s*=\s*"([^"]+)"\s*;""")
_VALUE_FIELD = re.compile(
    r"""@Value\(\s*"\$\{[^:}]+:([^}]+)\}"\s*\)\s*(?:private|protected|public)?\s*(?:final\s+)?String\s+(\w+)""",
)
_TEMPLATE_EXPR = re.compile(r"\$\{[^}]*\}|\{[^}]*\}")


@dataclass(frozen=True)
class CodeCall:
    caller_service: str
    method: str                 # GET... or ANY when the code does not say
    path: str                   # normalised; parameters as {param}
    file: str
    line: int
    client: str
    target_host: str | None = None


@dataclass(frozen=True)
class GatewayRoute:
    gateway_service: str
    pattern: str                # e.g. /api/accounts/**
    target: str                 # the uri as written
    file: str
    line: int


@dataclass(frozen=True)
class TopicUse:
    service: str
    topic: str
    role: str                   # "publishes" | "consumes"
    broker: str                 # "kafka" | "rabbitmq"
    file: str
    line: int
    certain: bool = True        # False: inferred from a declared topic name


@dataclass
class CodeDependencies:
    calls: list[CodeCall] = field(default_factory=list)
    routes: list[GatewayRoute] = field(default_factory=list)
    topics: list[TopicUse] = field(default_factory=list)
    files_read: int = 0
    test_files_skipped: int = 0


def service_of(rel_path: str) -> str:
    parts = [p for p in rel_path.split("/") if p]
    return parts[0] if len(parts) > 1 else "root"


def _line_of(text: str, pos: int) -> int:
    return text.count("\n", 0, pos) + 1


def clean_call_path(raw: str) -> tuple[str | None, str | None]:
    """(host, path) from a URL or path literal as written in code."""
    raw = raw.strip()
    host = None
    m = re.match(r"^https?://([^/:?#]+)(?::\d+)?(/[^?#]*)?", raw)
    if m:
        host = m.group(1).lower()
        raw = m.group(2) or "/"
    # A base-URL expression in front: `${BASE}/api/x`, `{base}/api/x`.
    raw = re.sub(r"^(\$\{[^}]*\}|\{[^}]*\})+", "", raw)
    if not raw.startswith("/"):
        return host, None
    raw = raw.split("?", 1)[0].split("#", 1)[0]
    path = _TEMPLATE_EXPR.sub("{param}", raw)
    if path.endswith("/") and len(path) > 1:
        # "/api/accounts/" + id: the concatenated value is one more segment.
        path += "{param}"
    path = re.sub(r"/{2,}", "/", path)
    if len(path) > 200 or re.search(r"\.(js|css|png|svg|html?|json)$", path):
        return host, None
    return host, path


# ---------------------------------------------------------------------------
def _source_files(scan: RepoScan, deps: CodeDependencies) -> Iterator[tuple[str, Path]]:
    for p in scan._walk():
        if p.suffix.lower() not in _CODE_SUFFIXES | _CONFIG_SUFFIXES:
            continue
        rel = scan.rel(p)
        if _TEST_PATH.search(rel):
            deps.test_files_skipped += 1
            continue
        try:
            if p.stat().st_size > _MAX_FILE_BYTES:
                continue
        except OSError:
            continue
        yield rel, p


def extract_dependencies(scan: RepoScan) -> CodeDependencies:
    deps = CodeDependencies()
    texts: dict[str, str] = {}
    for rel, p in _source_files(scan, deps):
        try:
            texts[rel] = p.read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue
    deps.files_read = len(texts)

    constants: dict[str, str] = {}
    for text in texts.values():
        for name, value in _STRING_CONST.findall(text):
            constants.setdefault(name, value)

    for rel, text in texts.items():
        suffix = Path(rel).suffix.lower()
        service = service_of(rel)
        if suffix in _CONFIG_SUFFIXES:
            deps.routes += _gateway_routes(rel, text, service)
            continue
        deps.calls += _http_calls(rel, text, service, suffix)
        deps.topics += _topic_uses(rel, text, service, constants)

    _infer_publishers(deps, texts, constants)
    deps.calls = _dedupe(deps.calls)
    return deps


def _dedupe(calls: list[CodeCall]) -> list[CodeCall]:
    seen: set[tuple[str, str, str, str]] = set()
    out: list[CodeCall] = []
    for c in calls:
        key = (c.caller_service, c.method, c.path, c.file)
        if key not in seen:
            seen.add(key)
            out.append(c)
    return out


def _http_calls(rel: str, text: str, service: str, suffix: str) -> list[CodeCall]:
    out: list[CodeCall] = []

    def add(method: str, raw: str, pos: int, client: str) -> None:
        host, path = clean_call_path(raw)
        if path and path != "/":
            out.append(CodeCall(service, method.upper(), path, rel, _line_of(text, pos),
                                client, host))

    if suffix in (".java", ".kt"):
        for m in _FLUENT_URI.finditer(text):
            window = text[max(0, m.start() - 400): m.start()]
            # The nearest verb before .uri(...) in the same statement.
            stmt = window.rsplit(";", 1)[-1]
            verbs = list(_FLUENT_VERB.finditer(stmt))
            if not verbs:
                continue
            v = verbs[-1]
            add((v.group(1) or v.group(2) or "ANY"), m.group(1), m.start(), "RestClient/WebClient")
        for m in _REST_TEMPLATE.finditer(text):
            fn, args = m.group(1), m.group(2)
            lit = re.search(rf"""["']({_URLISH})["']""", args)
            if not lit:
                continue
            method = _RT_VERB.get(fn)
            if method is None:
                hm = _HTTP_METHOD.search(args)
                method = hm.group(1) if hm else "ANY"
            add(method, lit.group(1), m.start(), "RestTemplate")
        if "@FeignClient" in text:
            for m in re.finditer(r"@(Get|Post|Put|Delete|Patch|Request)Mapping\b", text):
                # The interface's own @RequestMapping is its prefix, not a call.
                ahead = re.split(r"[;{]", text[m.end():], maxsplit=1)[0]
                if re.search(r"\b(interface|class)\s", ahead):
                    continue
                line = _line_of(text, m.start())
                for r in routes_for(text, line):
                    out.append(CodeCall(service, r.method, r.path, rel, line, "Feign",
                                        _feign_target(text)))
        return out

    if suffix in (".js", ".jsx", ".ts", ".tsx", ".mjs", ".cjs"):
        for m in _FETCH.finditer(text):
            jm = _JS_METHOD.search(m.group(3) or "")
            add(jm.group(1) if jm else "GET", m.group(2), m.start(), "fetch")
    for m in _CLIENT_CALL.finditer(text):
        receiver = m.group(1).split(".")[-1].lower()
        if receiver in _ROUTE_RECEIVERS or (m.group(6) and _HANDLER_ARG.match(m.group(6))):
            continue
        if not _CLIENT_RECEIVER.search(receiver):
            continue
        literal = m.group(5)
        if not re.match(_URLISH, literal) and not literal.startswith(("${", "{")):
            continue
        client = "axios/HttpClient" if suffix != ".py" else "requests/httpx"
        add(m.group(2), literal, m.start(), client)
    return out


def _feign_target(text: str) -> str | None:
    m = re.search(r"@FeignClient\s*\(([^)]*)\)", text)
    if not m:
        return None
    named = re.search(r"""(?:name|value)\s*=\s*"([^"]+)"|^\s*"([^"]+)\"""", m.group(1))
    return (named.group(1) or named.group(2)).lower() if named else None


def _resolve(expr: str, constants: dict[str, str], fields: dict[str, str]) -> list[str]:
    """Topic names an annotation argument or send() argument stands for."""
    expr = expr.strip().strip("{}").strip()
    out: list[str] = []
    for part in re.split(r"\s*,\s*", expr):
        part = part.strip()
        if not part:
            continue
        lit = re.fullmatch(r"""["'](.+?)["']""", part)
        if lit:
            value = lit.group(1)
            prop = re.fullmatch(r"\$\{[^:}]+:([^}]+)\}", value)
            out.append(prop.group(1) if prop else value)
            continue
        name = part.split(".")[-1].strip("()")
        if name in constants:
            out.append(constants[name])
        elif name in fields:
            out.append(fields[name])
    return out


def _topic_uses(rel: str, text: str, service: str,
                constants: dict[str, str]) -> list[TopicUse]:
    fields = {name: value for value, name in _VALUE_FIELD.findall(text)}
    out: list[TopicUse] = []
    for pattern, broker in ((_KAFKA_LISTENER, "kafka"), (_RABBIT_LISTENER, "rabbitmq")):
        for m in pattern.finditer(text):
            arg = _TOPICS_ARG.search(m.group(1))
            if arg:
                for topic in _resolve(arg.group(2), constants, fields):
                    out.append(TopicUse(service, topic, "consumes", broker, rel,
                                        _line_of(text, m.start())))
    for pattern, broker, role in (
        (_KAFKA_SEND, "kafka", "publishes"), (_RABBIT_SEND, "rabbitmq", "publishes"),
        (_JS_SEND, "kafka", "publishes"), (_PY_PRODUCE, "kafka", "publishes"),
        (_JS_SUBSCRIBE, "kafka", "consumes"), (_PY_SUBSCRIBE, "kafka", "consumes"),
    ):
        for m in pattern.finditer(text):
            for topic in _resolve(m.group(1).strip("[]"), constants, fields):
                out.append(TopicUse(service, topic, role, broker, rel,
                                    _line_of(text, m.start())))
    return out


def _infer_publishers(deps: CodeDependencies, texts: dict[str, str],
                      constants: dict[str, str]) -> None:
    """A service that sends to Kafka but chooses the topic at run time.

    The transactional-outbox pattern stores the topic with the event and
    publishes it later, so no send() call names it. When a service both sends
    to Kafka and declares a topic name in its own code (an @Value default or a
    constant it uses), it is recorded as publishing that topic, marked as
    inferred rather than read.
    """
    known = {(t.service, t.topic, t.role) for t in deps.topics}
    senders = {service_of(rel) for rel, text in texts.items()
               if re.search(r"[Kk]afka[Tt]emplate", text) and ".send(" in text}
    for rel, text in texts.items():
        service = service_of(rel)
        if service not in senders:
            continue
        declared = [v for v, _ in _VALUE_FIELD.findall(text) if "topic" in text.lower()]
        declared += [constants[n] for n in re.findall(r"\b[A-Z]\w*\.([A-Z][A-Z0-9_]+)\b", text)
                     if n in constants and "TOPIC" in text.upper()]
        for topic in declared:
            if "." not in topic and "-" not in topic:
                continue
            # Dead-letter topics are written by error handlers, not by the
            # service's own publishing; counting them would invent edges.
            if re.search(r"[.\-_](DLT|dlt|dlq|DLQ)$", topic):
                continue
            if (service, topic, "publishes") not in known \
                    and (service, topic, "consumes") not in known:
                at = text.find(topic)
                deps.topics.append(TopicUse(service, topic, "publishes", "kafka", rel,
                                            _line_of(text, at) if at >= 0 else 1,
                                            certain=False))
                known.add((service, topic, "publishes"))


def _gateway_routes(rel: str, text: str, service: str) -> list[GatewayRoute]:
    if "routes" not in text or "predicates" not in text:
        return []
    try:
        import yaml

        docs = list(yaml.safe_load_all(text))
    except Exception:  # unparseable config is skipped, not fatal
        return []
    out: list[GatewayRoute] = []

    def walk(node: Any) -> None:
        if isinstance(node, dict):
            for key, value in node.items():
                if key == "routes" and isinstance(value, list):
                    for route in value:
                        out.extend(_route(route))
                else:
                    walk(value)
        elif isinstance(node, list):
            for item in node:
                walk(item)

    def _route(route: Any) -> list[GatewayRoute]:
        if not isinstance(route, dict) or "uri" not in route:
            return []
        found: list[GatewayRoute] = []
        for pred in route.get("predicates") or []:
            if isinstance(pred, str) and pred.startswith("Path="):
                for pattern in pred[5:].split(","):
                    line = _line_of(text, max(0, text.find(pattern.strip())))
                    found.append(GatewayRoute(service, pattern.strip(), str(route["uri"]),
                                              rel, line))
        return found

    for doc in docs:
        walk(doc)
    return out


# ---------------------------------------------------------------------------
def _segments(path: str) -> list[str]:
    return [s for s in path.strip("/").split("/") if s]


def _is_param(seg: str) -> bool:
    return seg.startswith("{") and seg.endswith("}")


def match_endpoint(call: CodeCall, endpoints: list[tuple[str, str, str, str]]
                   ) -> str | None:
    """The endpoint id a call reaches, from (id, method, path, service) tuples.

    Literal segments must agree; a parameter on either side matches any
    segment. Among several matches the most literal one wins, and one in the
    service the client names (Feign name, URL host) beats one elsewhere.
    """
    want = _segments(call.path)
    best: tuple[int, int, str] | None = None
    for eid, method, path, service in endpoints:
        if call.method not in ("ANY", method) and method != "ANY":
            continue
        have = _segments(path)
        if len(have) != len(want):
            continue
        literal = 0
        for a, b in zip(want, have, strict=True):
            if _is_param(a) or _is_param(b):
                continue
            if a != b:
                break
            literal += 1
        else:
            if service == call.caller_service:
                continue        # a service calling itself is not a dependency
            hinted = int(bool(call.target_host) and service.lower() in (call.target_host or ""))
            score = (hinted, literal, eid)
            if best is None or score[:2] > best[:2]:
                best = score
    return best[2] if best else None


def route_matches(pattern: str, path: str) -> bool:
    """Spring/Ant path pattern: ** any number of segments, * one, {x} one."""
    regex = ""
    for seg in pattern.strip("/").split("/"):
        if seg == "**":
            regex += "(/.*)?"
        elif seg:
            part = re.escape(seg).replace(r"\*", "[^/]*")
            part = re.sub(r"\\\{[^}]*\\\}", "[^/]+", part)
            regex += "/" + part
    return re.fullmatch(regex or "/", path.rstrip("/") or "/") is not None
