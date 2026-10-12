"""
Dependencies read from code, and the graph drawn from them (apix/live/deps.py,
apix/graph/view.py).

These run without Semgrep: dependency extraction reads files as text. The
fixture is a small multi-service repository shaped like the Spring Boot banking
project that prompted the feature, plus Python and JavaScript clients, and the
route registrations a naive matcher would mistake for calls.
"""

from __future__ import annotations

import tempfile
from collections.abc import Iterator
from pathlib import Path

import pytest

from apix.graph.view import code_view
from apix.inventory.correlator import InventoryRecord
from apix.live.deps import (
    CodeCall,
    clean_call_path,
    extract_dependencies,
    match_endpoint,
    route_matches,
)
from apix.live.repo import RepoScan

FILES = {
    "transaction-service/src/main/java/t/client/AccountClient.java": """
class AccountClient {
    BalanceDto debit(String n) {
        return restClient.post()
                .uri("/api/accounts/internal/debit")
                .retrieve().body(BalanceDto.class);
    }
    AccountDto find(String n) {
        return restClient.get()
                .uri("/api/accounts/" + n)
                .retrieve().body(AccountDto.class);
    }
    void legacy() { restTemplate.postForObject("http://ledger.bank.example/v1/entries", x, Y.class); }
}
""",
    "transaction-service/src/main/java/t/client/CustomerClient.java": """
@FeignClient(name = "customer-service")
@RequestMapping("/api/customers")
public interface CustomerClient {
    @GetMapping("/{id}")
    CustomerDto get(@PathVariable Long id);
}
""",
    "transaction-service/src/main/java/t/publisher/Publisher.java": """
class Publisher {
    @Value("${kafka.topics.completed:bank.transaction.completed}")
    private String completedTopic;
    void publish(Event e) { kafkaTemplate.send(completedTopic, e); }
}
""",
    "transaction-service/src/test/java/t/AccountClientTest.java": """
class AccountClientTest { void t() { restClient.delete().uri("/api/accounts/1"); } }
""",
    "common/src/main/java/c/EventTopics.java": """
public final class EventTopics {
    public static final String TRANSACTION_COMPLETED = "bank.transaction.completed";
}
""",
    "audit-service/src/main/java/a/Consumer.java": """
class Consumer {
    @KafkaListener(topics = EventTopics.TRANSACTION_COMPLETED, groupId = "g")
    public void on(Event e) { }
}
""",
    "api-gateway/src/main/resources/application.yml": """
spring:
  cloud:
    gateway:
      mvc:
        routes:
          - id: accounts
            uri: ${ACCOUNT_SERVICE_URL:http://localhost:8083}
            predicates:
              - Path=/api/accounts/**
""",
    "web/src/api.ts": """
export const load = (id: string) => fetch(`${BASE}/api/customers/${id}`);
export const save = () => fetch("/api/customers", { method: "POST" });
export const bulk = () => axios.post("/api/transactions/transfer", body);
""",
    "web/src/server.js": """
app.get("/api/health", (req, res) => res.send("ok"));
router.post("/api/hooks", handler);
""",
    "reports/jobs.py": """
import requests
def run():
    requests.get(f"{BASE}/api/accounts/{acct}")
    settings.get("/not/a/call/at/all")
""",
}


@pytest.fixture(scope="module")
def deps() -> Iterator:
    with tempfile.TemporaryDirectory() as d:
        root = Path(d)
        for rel, text in FILES.items():
            (root / rel).parent.mkdir(parents=True, exist_ok=True)
            (root / rel).write_text(text, encoding="utf-8")
        yield extract_dependencies(RepoScan.from_path(root, slug="fixture"))


def _calls(deps) -> set[tuple[str, str, str]]:
    return {(c.caller_service, c.method, c.path) for c in deps.calls}


def test_spring_fluent_clients_and_rest_template(deps) -> None:
    calls = _calls(deps)
    assert ("transaction-service", "POST", "/api/accounts/internal/debit") in calls
    # "/api/accounts/" + n: the concatenated value is one more path segment.
    assert ("transaction-service", "GET", "/api/accounts/{param}") in calls
    assert ("transaction-service", "POST", "/v1/entries") in calls
    ledger = next(c for c in deps.calls if c.path == "/v1/entries")
    assert ledger.target_host == "ledger.bank.example"


def test_feign_clients_count_as_calls_to_the_named_service(deps) -> None:
    feign = [c for c in deps.calls if c.client == "Feign"]
    assert [(c.method, c.path, c.target_host) for c in feign] == [
        ("GET", "/api/customers/{id}", "customer-service")]


def test_javascript_and_python_clients(deps) -> None:
    calls = _calls(deps)
    assert ("web", "GET", "/api/customers/{param}") in calls
    assert ("web", "POST", "/api/customers") in calls
    assert ("web", "POST", "/api/transactions/transfer") in calls
    assert ("reports", "GET", "/api/accounts/{param}") in calls


def test_route_registrations_and_tests_are_not_calls(deps) -> None:
    paths = {c.path for c in deps.calls}
    assert "/api/health" not in paths and "/api/hooks" not in paths
    assert "/not/a/call/at/all" not in paths
    assert not any(c.file.endswith("AccountClientTest.java") for c in deps.calls)
    assert deps.test_files_skipped == 1


def test_gateway_routes_and_topics_resolved_through_constants(deps) -> None:
    assert [(r.gateway_service, r.pattern) for r in deps.routes] == [
        ("api-gateway", "/api/accounts/**")]
    uses = {(t.service, t.role, t.topic) for t in deps.topics}
    assert ("audit-service", "consumes", "bank.transaction.completed") in uses
    assert ("transaction-service", "publishes", "bank.transaction.completed") in uses


@pytest.mark.parametrize("raw,host,path", [
    ("/api/x", None, "/api/x"),
    ("https://api.example.com:8443/v1/x?y=1", "api.example.com", "/v1/x"),
    ("${BASE}/api/x/${id}", None, "/api/x/{param}"),
    ("{base}/api/x/{acct}", None, "/api/x/{param}"),
    ("/api/accounts/", None, "/api/accounts/{param}"),
    ("relative/path", None, None),
    ("/static/app.js", None, None),
])
def test_call_paths_as_written(raw: str, host: str | None, path: str | None) -> None:
    assert clean_call_path(raw) == (host, path)


def test_matching_prefers_the_most_literal_endpoint_and_the_named_service() -> None:
    endpoints = [
        ("GET /api/accounts/{n}", "GET", "/api/accounts/{n}", "account-service"),
        ("GET /api/accounts/internal", "GET", "/api/accounts/internal", "account-service"),
        ("GET /api/{x}/{y}", "GET", "/api/{x}/{y}", "other-service"),
    ]
    call = CodeCall("web", "GET", "/api/accounts/internal", "f", 1, "fetch")
    assert match_endpoint(call, endpoints) == "GET /api/accounts/internal"
    hinted = CodeCall("web", "GET", "/api/{param}/{param}", "f", 1, "Feign", "other-service")
    assert match_endpoint(hinted, endpoints) == "GET /api/{x}/{y}"
    wrong_method = CodeCall("web", "DELETE", "/api/accounts/internal", "f", 1, "fetch")
    assert match_endpoint(wrong_method, endpoints) is None
    itself = CodeCall("account-service", "GET", "/api/accounts/internal", "f", 1, "x")
    assert match_endpoint(itself, endpoints[:2]) is None


@pytest.mark.parametrize("pattern,path,ok", [
    ("/api/accounts/**", "/api/accounts/internal/debit", True),
    ("/api/accounts/**", "/api/accounts", True),
    ("/api/accounts/**", "/api/accountsx/y", False),
    ("/api/*/status", "/api/a/status", True),
    ("/api/*/status", "/api/a/b/status", False),
])
def test_gateway_patterns(pattern: str, path: str, ok: bool) -> None:
    assert route_matches(pattern, path) is ok


def test_the_graph_from_code_has_a_real_blast_radius(deps) -> None:
    def rec(service: str, method: str, path: str) -> InventoryRecord:
        return InventoryRecord(endpoint_id=f"{method} {path}", service=service,
                               method=method, path=path, version="v1")

    records = [
        rec("account-service", "POST", "/api/accounts/internal/debit"),
        rec("account-service", "GET", "/api/accounts/{n}"),
        rec("transaction-service", "POST", "/api/transactions/transfer"),
        rec("customer-service", "GET", "/api/customers/{id}"),
    ]
    view = code_view(records, deps, {})
    debit = view["radius"]["POST /api/accounts/internal/debit"]
    assert debit["direct_services"] == ["transaction-service"]
    # transaction-service breaks, so its own endpoint degrades one hop out.
    assert {a["endpoint_id"] for a in debit["affected_endpoints"]} == {
        "POST /api/transactions/transfer"}
    assert view["radius"]["POST /api/transactions/transfer"]["direct_services"] == ["web"]
    kinds = {s["id"]: s["kind"] for s in view["services"]}
    assert kinds["api-gateway"] == "gateway"
    assert kinds["topic: bank.transaction.completed"] == "topic"
    assert kinds["outside: ledger.bank.example"] == "external"
    exposed = next(e for e in view["endpoints"]
                   if e["id"] == "POST /api/accounts/internal/debit")["exposed_via"]
    assert exposed == ["api-gateway /api/accounts/**"]
    assert any("internal, admin or debug" in n for n in view["notes"])


def test_the_demo_graph_comes_from_traffic_and_needs_a_token() -> None:
    pytest.importorskip("fastapi")
    from fastapi.testclient import TestClient

    from apix.api.app import create_app
    from apix.api.auth import Role, TokenStore, new_token
    from apix.api.workspace import Workspace

    token = new_token()
    with tempfile.TemporaryDirectory() as d:
        client = TestClient(create_app(Workspace(Path(d) / "a.jsonl"),
                                       TokenStore.single("v", Role.VIEWER, token)))
        anonymous = client.get("/v1/demo/graph")
        view = client.get("/v1/demo/graph",
                          headers={"Authorization": f"Bearer {token}"}).json()
    assert anonymous.status_code == 401
    assert view["basis"] == "traffic" and view["stats"]["endpoints"] == 25
    # The same blast radius the removal gate and `apix impact` report.
    assert view["radius"]["GET /v2/accounts/{id}"]["severity"] == "severe"
    # Paths as the endpoint id spells them: the estate keeps versions apart.
    v2 = next(e for e in view["endpoints"] if e["id"] == "GET /v2/accounts/{id}")
    assert v2["path"] == "/v2/accounts/{id}"
    zombies = [e for e in view["endpoints"] if e["label"] == "ZOMBIE"]
    assert zombies and all(e["isolated"] for e in zombies)
