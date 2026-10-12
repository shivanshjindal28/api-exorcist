"""
Spring MVC route paths (apix/extractors/spring.py).

These run without Semgrep: they test the part that reads annotations, which is
where a real Spring Boot repository exposed two gaps. Scanned from the browser,
github.com/Mehandihasan2023/digital-banking-platform reported 20 routes with no
class prefixes (`GET /{id}` for three different services) and missed every bare
`@PostMapping`; it has 27, all under /api/....
"""

from __future__ import annotations

import tempfile
from pathlib import Path

import pytest

from apix.extractors.semgrep_extractor import SemgrepExtractor
from apix.extractors.spring import parse_mapping, routes_for

CONTROLLER = '''package com.bank;

@RestController
@RequestMapping("/api/customers")
@RequiredArgsConstructor
public class CustomerController {

    @PostMapping
    public ResponseEntity<C> create(@RequestBody C c) { return null; }

    @GetMapping("/{id}")
    public C get(@PathVariable Long id) { return null; }

    @GetMapping(value = "/number/{n}", produces = "application/json")
    public C byNumber(String n) { return null; }

    @RequestMapping(path = {"/a", "/b"}, method = {RequestMethod.GET, RequestMethod.HEAD})
    public C multi() { return null; }

    @PreAuthorize("hasRole('ADMIN')")
    @DeleteMapping(path = "/{id}")
    public void del(Long id) { }

    @RequestMapping("/any")
    public void any() { }
}

@RequestMapping(ApiPaths.ADMIN)
class AdminController {
    @PatchMapping("/flags")
    public void flags() { }
}
'''


def _at(prefix: str) -> int:
    """1-based line of the first line starting with `prefix`."""
    for i, line in enumerate(CONTROLLER.splitlines(), 1):
        if line.strip().startswith(prefix):
            return i
    raise AssertionError(prefix)


def _routes(prefix: str) -> list[tuple[str, str, bool]]:
    return [(r.method, r.path, r.resolved) for r in routes_for(CONTROLLER, _at(prefix))]


@pytest.mark.parametrize("args,paths,methods,unresolved", [
    ("", [""], [], None),
    ('"/x"', ["/x"], [], None),
    ('value = "/x", produces = "a/b"', ["/x"], [], None),
    ('path = {"/a", "/b"}', ["/a", "/b"], [], None),
    ('{"/a", "/b"}', ["/a", "/b"], [], None),
    ('produces = "application/json"', [""], [], None),
    ('method = RequestMethod.POST', [""], ["POST"], None),
    ("ApiPaths.BASE", [""], [], "ApiPaths.BASE"),
])
def test_mapping_arguments(args: str, paths: list[str], methods: list[str],
                           unresolved: str | None) -> None:
    m = parse_mapping(args)
    assert (m.paths, m.methods, m.unresolved) == (paths, methods, unresolved)


def test_the_class_prefix_is_applied() -> None:
    assert _routes("@GetMapping(\"/{id}\")") == [("GET", "/api/customers/{id}", True)]


def test_a_bare_mapping_serves_the_class_prefix_itself() -> None:
    assert _routes("@PostMapping") == [("POST", "/api/customers", True)]


def test_named_paths_arrays_and_request_methods() -> None:
    assert _routes("@GetMapping(value") == [("GET", "/api/customers/number/{n}", True)]
    assert _routes("@RequestMapping(path") == [
        ("GET", "/api/customers/a", True), ("HEAD", "/api/customers/a", True),
        ("GET", "/api/customers/b", True), ("HEAD", "/api/customers/b", True),
    ]
    assert _routes('@RequestMapping("/any")') == [("ANY", "/api/customers/any", True)]


def test_other_annotations_before_the_mapping_are_skipped() -> None:
    assert _routes("@PreAuthorize") == [("DELETE", "/api/customers/{id}", True)]


def test_a_constant_prefix_is_flagged_not_guessed() -> None:
    routes = routes_for(CONTROLLER, _at("@PatchMapping"))
    assert [(r.method, r.path, r.resolved, r.expression) for r in routes] == [
        ("PATCH", "/flags", False, "ApiPaths.ADMIN")]


def test_the_extractor_uses_the_source_not_the_match_text() -> None:
    """Semgrep's message carries no path for Spring; the file is read instead.

    Two controllers with the same method-level path must stay two endpoints.
    """
    other = CONTROLLER.replace("/api/customers", "/api/accounts")
    with tempfile.TemporaryDirectory() as d:
        root = Path(d)
        (root / "Customers.java").write_text(CONTROLLER, encoding="utf-8")
        (root / "Accounts.java").write_text(other, encoding="utf-8")
        line = _at('@GetMapping("/{id}")')

        def hit(file: str) -> dict[str, object]:
            return {"check_id": "rules.apix-java-spring-get", "path": str(root / file),
                    "start": {"line": line},
                    "extra": {"message": "APIX|path=|func=get", "lines": "requires login"}}

        routes = SemgrepExtractor()._parse(
            {"results": [hit("Customers.java"), hit("Accounts.java")]}, root)
    assert sorted((r.method, r.path, r.file) for r in routes) == [
        ("GET", "/api/accounts/{id}", "Accounts.java"),
        ("GET", "/api/customers/{id}", "Customers.java"),
    ]
