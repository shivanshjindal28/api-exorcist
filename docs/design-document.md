# Design Document

**API Exorcist — autonomous discovery and safe elimination of zombie, shadow and orphaned APIs**

B.Tech CSE (Cyber Security), MPSTME, NMIMS · 2026–2027

> **Status key used throughout.** ✅ implemented and tested · 🔵 in progress ·
> ⬜ designed, not yet built. The distinction is stated on every diagram, because a
> design document that hides which parts are real is worthless as an engineering
> artefact.

---

## 1. Design principles

Five principles constrain every decision that follows. They are listed first because
each later choice is traceable to one of them.

| # | Principle | Consequence |
|---|---|---|
| P1 | **No source is trusted alone.** Every connector is a partial, imperfect witness. | Six connectors; disagreement between them is treated as signal, not noise. |
| P2 | **Absence is evidence.** A zombie is identified by what *fails* to see it. | The inventory records which sources did *not* observe each endpoint. |
| P3 | **Observed beats declared.** What happened on the wire outranks what a config claims. | `_reconcile()` prefers traffic-observed auth over gateway-declared auth. |
| P4 | **Every verdict carries its reasons.** | Classification returns a `Verdict` with an evidence set, never a bare label. |
| P5 | **Nothing is destroyed without a reversible path.** | Safe Kill is canary-and-rollback, never immediate deletion. |

P1 and P2 come from the dead-code and architecture-recovery literature [1][3]; P4 from
the explainability literature [8][9]; P5 is a requirement of the regulated deployment
target rather than a research finding.

---

## 2. Structural view

### 2.1 Component diagram — five layers

```mermaid
flowchart TB
    subgraph L1["Layer 1 · Data Sources"]
        direction LR
        GW["API Gateway<br/>Kong / Apigee"]
        SPEC["OpenAPI<br/>Specification"]
        TRAF["Network Traffic<br/>Zeek"]
        CODE["Source Repos<br/>Semgrep"]
        DNS["DNS / Service Mesh"]
        CICD["CI/CD<br/>GitHub Actions"]
    end

    subgraph L2["Layer 2 · Ingestion and Streaming"]
        CONN["Connector Framework<br/>uniform DiscoverySignal contract"]
        BUS["Event Bus<br/>LocalBus / Kafka"]
        SINK["Search Index<br/>Elasticsearch"]
    end

    subgraph L3["Layer 3 · Analysis and Intelligence"]
        CORR["Correlation Engine<br/>unified inventory + 15 flags"]
        FEAT["Feature Extraction<br/>16 observable features"]
        RULES["Rule Classifier<br/>deterministic, auditable"]
        ML["ML Classifier<br/>gradient boosting"]
        XAI["Explanation Layer<br/>rules + SHAP"]
        GRAPH["Dependency Graph<br/>Neo4j"]
    end

    subgraph L4["Layer 4 · Decision and Enforcement"]
        BLAST["Blast Radius<br/>graph traversal"]
        GATE["Policy Decision Gate<br/>human approval"]
        KILL["Safe Kill Simulation<br/>canary + rollback"]
        AUDIT["Audit Log<br/>hash-chained, append-only"]
        ENF["CI/CD Enforcement<br/>GitHub Action"]
    end

    subgraph L5["Layer 5 · Presentation"]
        API["REST API<br/>FastAPI"]
        UI["Dashboard<br/>React + TypeScript"]
        CLI["CLI<br/>apix"]
    end

    GW & SPEC & TRAF & CODE & DNS & CICD --> CONN
    CONN --> BUS --> CORR
    CORR --> SINK
    CORR --> FEAT --> RULES --> XAI
    FEAT --> ML --> XAI
    CORR --> GRAPH --> BLAST
    XAI --> GATE
    BLAST --> GATE
    GATE --> KILL --> AUDIT
    XAI --> ENF
    XAI & BLAST & AUDIT --> API
    API --> UI
    CORR --> CLI

    classDef done fill:#dff0e8,stroke:#2F6B63,color:#123
    classDef wip  fill:#fdf0dc,stroke:#A9631B,color:#123
    classDef todo fill:#eeeeee,stroke:#999,color:#333,stroke-dasharray:4 3
    class GW,SPEC,TRAF,CODE,DNS,CICD,CONN,BUS,SINK,CORR,FEAT,CLI done
    class RULES,ML,XAI wip
    class GRAPH,BLAST,GATE,KILL,AUDIT,ENF,API,UI todo
```

**Layer boundaries are enforced by dependency direction.** Layer 1 knows nothing of
Layer 2; connectors emit `DiscoverySignal` and never classify. Layer 3 never reaches
back to a data source. This is what makes the simulated estate swappable for live
sources without touching anything downstream — the single most important structural
property of the system.

### 2.2 Class diagram — core domain model

```mermaid
classDiagram
    class Source {
        <<enumeration>>
        GATEWAY
        OPENAPI
        TRAFFIC
        CODE
        DNS
        CICD
    }

    class DiscoverySignal {
        +Source source
        +str endpoint_id
        +str service
        +str method
        +str path
        +str version
        +datetime observed_at
        +dict attributes
        +to_dict() dict
    }

    class Connector {
        <<abstract>>
        +Source source
        +str name
        +collect() Iterator~DiscoverySignal~
        +run() list~DiscoverySignal~
    }

    class GatewayConnector
    class OpenAPIConnector
    class TrafficConnector
    class CodeConnector
    class DNSConnector
    class CICDConnector

    class InventoryRecord {
        +str endpoint_id
        +set~str~ seen_by
        +dict evidence
        +bool in_openapi_spec
        +bool in_gateway_registry
        +bool observed_on_wire
        +bool handler_exists_in_code
        +bool dns_resolvable
        +bool deployed_via_pipeline
        +int daily_calls
        +int last_seen_days_ago
        +str owner_team
        +str auth_scheme
        +bool spec_deprecated
        +list~str~ flags
    }

    class Correlator {
        -dict _records
        +ingest(signals)
        +finalise() list~InventoryRecord~
        -_reconcile(rec)
        -_derive_flags(rec)
        +coverage_report(records)$ dict
    }

    class Classification {
        <<enumeration>>
        ACTIVE
        DEPRECATED
        ORPHANED
        ZOMBIE
    }

    class Verdict {
        +str endpoint_id
        +Classification label
        +float confidence
        +list~Reason~ reasons
        +str decided_by
        +to_dict() dict
    }

    class Reason {
        +str flag
        +str statement
        +float weight
        +str evidence_source
    }

    class Classifier {
        <<abstract>>
        +classify(rec) Verdict
    }

    class RuleClassifier {
        +classify(rec) Verdict
        -_score(rec) dict
    }

    class MLClassifier {
        +classify(rec) Verdict
        -_explain_shap(features) list~Reason~
    }

    Connector <|-- GatewayConnector
    Connector <|-- OpenAPIConnector
    Connector <|-- TrafficConnector
    Connector <|-- CodeConnector
    Connector <|-- DNSConnector
    Connector <|-- CICDConnector
    Connector ..> DiscoverySignal : emits
    Connector ..> Source : tagged with
    Correlator ..> DiscoverySignal : ingests
    Correlator --> InventoryRecord : produces
    Classifier ..> InventoryRecord : consumes
    Classifier --> Verdict : produces
    Classifier <|-- RuleClassifier
    Classifier <|-- MLClassifier
    Verdict --> Classification
    Verdict o-- Reason
```

Implemented: `Source`, `DiscoverySignal`, `Connector` and its six subclasses,
`InventoryRecord`, `Correlator`. ✅
In progress: `Classification`, `Verdict`, `Reason`, `Classifier`, `RuleClassifier`. 🔵
Designed: `MLClassifier`. ⬜

**Why `Verdict` composes `Reason` rather than carrying a string.** P4 requires that
every decision be auditable. A `list[Reason]`, each naming the flag, a
human-readable statement, its weight, and the source that observed it, serialises
directly into the audit log and renders directly in the dashboard. A formatted string
would have to be parsed back apart for either purpose.

### 2.3 Deployment diagram

```mermaid
flowchart TB
    subgraph CUST["Customer environment — read-only access"]
        direction LR
        C1["Kong Admin API"]
        C2["GitHub org<br/>repos + Actions"]
        C3["Zeek sensor<br/>span port"]
        C4["CoreDNS / mesh"]
    end

    subgraph HOST["API Exorcist — self-hosted, single tenant"]
        direction TB
        subgraph POD1["Scanner workload"]
            W1["Connector workers"]
            W2["Correlator"]
        end
        subgraph POD2["Analysis workload"]
            W3["Classifier + XAI"]
            W4["Safe Kill controller"]
        end
        subgraph DATA["Stateful services"]
            PG[("PostgreSQL<br/>inventory, scans, audit")]
            NEO[("Neo4j<br/>dependency graph")]
            ES[("Elasticsearch<br/>search")]
            KAF[["Kafka<br/>signal bus"]]
        end
        SRV["FastAPI server"]
        WEB["React dashboard"]
    end

    OP(["Security operator"])

    C1 & C2 & C3 & C4 -.->|"scoped read tokens<br/>TLS"| W1
    W1 --> KAF --> W2
    W2 --> PG & ES & NEO
    PG & NEO --> W3 --> W4
    W4 -.->|"canary control<br/>write-scoped"| C1
    PG & NEO & ES --> SRV --> WEB --> OP

    classDef ext fill:#eef2f6,stroke:#5A7184,color:#123
    classDef int fill:#dff0e8,stroke:#2F6B63,color:#123
    class C1,C2,C3,C4 ext
```

**The only write path into the customer's environment is the Safe Kill controller's
canary control, and it holds a separate, write-scoped credential from the read tokens
used for discovery.** A compromise of the scanner cannot disable an endpoint. This
separation is a hard requirement of the banking deployment target.

---

## 3. Behavioural view

### 3.1 Sequence diagram — a discovery scan ✅

```mermaid
sequenceDiagram
    actor OP as Operator
    participant CLI as apix CLI
    participant PIPE as Pipeline
    participant CN as Connectors (×6)
    participant BUS as Event Bus
    participant COR as Correlator
    participant ST as Store

    OP->>CLI: apix scan
    CLI->>PIPE: run()

    rect rgb(240,245,250)
        note over PIPE,CN: Stage 1 — collection (parallelisable, no shared state)
        PIPE->>CN: collect()
        loop each of 6 sources
            CN-->>BUS: DiscoverySignal ×N
        end
        note right of CN: 122 signals from 25 endpoints<br/>Sources disagree — that is the point
    end

    rect rgb(250,245,238)
        note over BUS,COR: Stage 2 — correlation
        BUS->>COR: ingest(signals)
        COR->>COR: group by endpoint_id
        COR->>COR: _reconcile() — observed beats declared
        COR->>COR: _derive_flags() — 15 discrepancy flags
        COR-->>ST: InventoryRecord ×25
    end

    rect rgb(240,248,244)
        note over PIPE,ST: Stage 3 — reporting
        PIPE->>ST: coverage_report()
        ST-->>CLI: no source exceeds 76%<br/>6 invisible to both authorities
        CLI-->>OP: ranked findings
    end
```

### 3.2 State machine — endpoint lifecycle

This is the taxonomy the project is named for, expressed as states rather than a
static quadrant. Transitions are what the classifier detects.

```mermaid
stateDiagram-v2
    [*] --> ACTIVE : deployed, documented, in use

    ACTIVE --> DEPRECATED : team marks obsolete<br/>(spec_deprecated = true)
    ACTIVE --> ORPHANED : owning team dissolves<br/>(NO_OWNER, traffic continues)
    ACTIVE --> ZOMBIE : traffic ceases silently<br/>(no one notices)

    DEPRECATED --> ZOMBIE : traffic ceases,<br/>removal never happens
    DEPRECATED --> RETIRED : planned removal executed
    ORPHANED --> ZOMBIE : traffic ceases

    ZOMBIE --> CANDIDATE : flagged for removal
    CANDIDATE --> ZOMBIE : approval denied<br/>or rollback triggered
    CANDIDATE --> RETIRED : Safe Kill completes

    RETIRED --> [*]

    note right of ZOMBIE
        The dangerous state.
        Reachable, unmonitored,
        unowned, undocumented.
    end note

    note right of ORPHANED
        Distinct from ZOMBIE:
        still carries traffic.
        Must NOT be killed.
    end note
```

**The `ORPHANED → ZOMBIE` distinction is the one that matters operationally.** An
orphaned endpoint has no owner but real users; killing it causes an outage. A zombie
has neither. Conflating them is the failure mode that would make this product
dangerous, which is why they are separate classes rather than a single "abandoned"
label.

### 3.3 Classification decision logic 🔵

```mermaid
flowchart TD
    START([InventoryRecord]) --> Q1{"Traffic observed<br/>in window?"}

    Q1 -->|"Yes, above<br/>threshold"| Q2{"spec_deprecated<br/>set?"}
    Q1 -->|"No, or<br/>effectively silent"| Q3{"Documented<br/>or registered?"}

    Q2 -->|Yes| DEP["DEPRECATED<br/>declared obsolete,<br/>still serving"]
    Q2 -->|No| Q4{"Has an<br/>owner?"}

    Q4 -->|Yes| ACT["ACTIVE<br/>healthy"]
    Q4 -->|No| ORP["ORPHANED<br/>in use, unowned"]

    Q3 -->|Yes| Q5{"Marked<br/>deprecated?"}
    Q3 -->|"No — invisible<br/>to both authorities"| ZOM["ZOMBIE<br/>shadow + silent"]

    Q5 -->|Yes| DEP
    Q5 -->|No| Q6{"Reachable<br/>via DNS?"}

    Q6 -->|Yes| ZOM
    Q6 -->|No| Q7{"Handler still<br/>in code?"}

    Q7 -->|Yes| ORP
    Q7 -->|No| RET["RETIRED<br/>already gone"]

    ZOM --> RISK["Risk score:<br/>+ UNAUTHENTICATED<br/>+ SENSITIVE_DATA<br/>+ REACHABLE_BUT_UNUSED"]

    classDef zom fill:#f4e4e0,stroke:#9B3B2E,color:#123
    classDef act fill:#dff0e8,stroke:#2F6B63,color:#123
    classDef mid fill:#fdf0dc,stroke:#A9631B,color:#123
    class ZOM,RISK zom
    class ACT act
    class DEP,ORP mid
```

**Implementation note — the tree became additive scoring.** The diagram above is the
*semantics* of the four classes and remains accurate as a description of intent. The
implementation in `engine/rules.py` realises it as fourteen evidence rules, each with
a signed weight per class; the highest total wins. Three reasons drove the change, all
discovered while building:

1. **A tree commits at its first branch.** Real evidence conflicts — an endpoint can be
   documented, owned, *and* completely silent. Scoring weighs the conflict; a tree lets
   whichever test happens to run first decide.
2. **Confidence falls out of the margin.** A tree yields a label with no native measure
   of how close the call was. The gap between the top two scores is exactly the signal
   needed to decide when to consult the ML layer.
3. **It matches the shape of SHAP.** SHAP explains a prediction as additive feature
   contributions. This layer explains a verdict as additive evidence contributions.
   Both layers therefore emit the same explanation structure, and the dashboard and
   audit log need one renderer rather than two.

Determinism and auditability are unchanged, and the weights were fixed from the class
definitions *before* accuracy was measured — not tuned against the answer key
afterwards, which would make the reported figures meaningless.

The ML layer runs alongside and is consulted only where the margin is narrow. **Rules
decide; the model advises.** That ordering keeps the system explainable by
construction rather than by post-hoc attribution.

### 3.3.1 Measured performance ✅

Against the 25-endpoint estate, all four sources correlated:

| Class | Precision | Recall | F1 | Support |
|---|---|---|---|---|
| ACTIVE | 0.923 | 1.000 | 0.960 | 12 |
| DEPRECATED | 1.000 | 0.667 | 0.800 | 3 |
| ORPHANED | 1.000 | 1.000 | 1.000 | 2 |
| ZOMBIE | 1.000 | 1.000 | 1.000 | 8 |
| **macro avg** | **0.981** | **0.917** | **0.940** | 25 |

Accuracy 0.960 (24/25). **Zombie recall is 1.000 and no live endpoint was marked for
removal** — the two properties that matter operationally, since a missed zombie is an
unremediated exposure and a false zombie is an outage.

**The single error is instructive and is not a tuning problem.**
`POST /v1/kyc/aadhaar/ekyc` is genuinely DEPRECATED but was classified ACTIVE. It is
the one deprecated endpoint in the estate whose team never set the OpenAPI
`deprecated` flag — precisely the behaviour Cassieri et al. [2] documented. Every
*observable* property of that endpoint is identical to a healthy one: documented,
registered, owned, carrying traffic.

Note the confidence: **0.803, the same as correctly-classified ACTIVE endpoints.** The
classifier is not hesitant here — it is confidently wrong, because the evidence
genuinely does not distinguish the two cases. No amount of model sophistication
resolves this; only a new signal would, such as `CODEOWNERS`, a changelog, or a pull
request referencing the migration. **That is a finding about the limits of
observation, and it belongs in the paper as one.**

### 3.4 State machine — Safe Kill Simulation ⬜

The centrepiece of the remediation half, and the project's actual research
contribution.

```mermaid
stateDiagram-v2
    [*] --> Nominated : classifier returns ZOMBIE

    Nominated --> BlastRadius : enqueue for removal
    BlastRadius --> Blocked : dependents found in graph
    BlastRadius --> Simulated : no dependents

    Blocked --> [*] : reported, not actioned

    Simulated --> Rejected : simulation shows impact
    Simulated --> AwaitingApproval : simulation clean

    Rejected --> [*] : logged with reasons

    AwaitingApproval --> Denied : operator declines
    AwaitingApproval --> Canary5 : operator approves

    Denied --> [*] : logged with approver identity

    Canary5 --> RolledBack : error rate breach
    Canary5 --> Canary25 : clean for observation window
    Canary25 --> RolledBack : error rate breach
    Canary25 --> Canary100 : clean
    Canary100 --> RolledBack : error rate breach
    Canary100 --> Retired : clean through soak period

    RolledBack --> [*] : endpoint restored, incident logged
    Retired --> [*] : removed, audit entry sealed

    note right of Canary5
        Progressive 410 Gone
        on 5% → 25% → 100%
        of requests.
        Reversible at every step.
    end note

    note right of RolledBack
        Automatic, not manual.
        Triggered by error-rate
        breach, no human in loop.
    end note
```

**Every terminal state writes to the audit log, including the failures.** `Blocked`,
`Rejected` and `Denied` are recorded with the same rigour as `Retired`, because an
auditor asking "why was this endpoint *not* removed" needs an answer as much as the
reverse. This is a compliance requirement under the RBI framework, not a
nice-to-have.

### 3.5 Data flow diagram — level 1 ✅🔵

```mermaid
flowchart LR
    subgraph EXT[" "]
        E1(["Customer<br/>environment"])
        E2(["Security<br/>operator"])
    end

    P1["1.0<br/>Collect<br/>signals"]
    P2["2.0<br/>Correlate<br/>into inventory"]
    P3["3.0<br/>Extract<br/>features"]
    P4["4.0<br/>Classify<br/>and explain"]
    P5["5.0<br/>Decide and<br/>enforce"]

    D1[("D1 · Raw signals")]
    D2[("D2 · Inventory")]
    D3[("D3 · Feature store")]
    D4[("D4 · Verdicts")]
    D5[("D5 · Audit log")]

    E1 -->|"observations"| P1
    P1 -->|"DiscoverySignal"| D1
    D1 --> P2
    P2 -->|"InventoryRecord<br/>+ flags"| D2
    D2 --> P3
    P3 -->|"16 features"| D3
    D3 --> P4
    D2 --> P4
    P4 -->|"Verdict + Reasons"| D4
    D4 --> P5
    P5 -->|"kill / block / defer"| D5
    P5 -->|"canary control"| E1
    D4 -->|"ranked findings"| E2
    E2 -->|"approve / deny"| P5
    D5 -->|"audit trail"| E2
```

---

## 4. Data model

### 4.1 The sixteen observable features

Every feature answers: *what real-world observation produces this?* If the answer were
"the ground-truth label," it would not be a feature. A test enforces this.

| Feature | Type | Observed by | Rationale |
|---|---|---|---|
| `in_openapi_spec` | bool | OPENAPI | Documentation presence |
| `in_gateway_registry` | bool | GATEWAY | Registration presence |
| `observed_on_wire` | bool | TRAFFIC | Any real usage |
| `handler_exists_in_code` | bool | CODE | Implementation presence |
| `dns_resolvable` | bool | DNS | Reachability — the danger multiplier |
| `deployed_via_pipeline` | bool | CICD | Deployment provenance |
| `daily_calls` | int | TRAFFIC | Usage intensity |
| `last_seen_days_ago` | int | TRAFFIC | Recency of use |
| `distinct_callers` | int | TRAFFIC | Breadth of dependence |
| `days_since_last_commit` | int | CODE | Maintenance recency [1] |
| `spec_deprecated` | bool | OPENAPI | Declared lifecycle state [2] |
| `has_owner` | bool | OPENAPI, CICD | Accountability |
| `auth_is_none` | bool | TRAFFIC, GATEWAY | Security posture |
| `auth_is_legacy` | bool | TRAFFIC, GATEWAY | Weak posture |
| `is_sensitive_data` | bool | OPENAPI | Blast severity |
| `source_count` | int | derived | How many witnesses agree |

`source_count` is the operationalisation of P2: a low count with a live `dns_resolvable`
is the zombie signature.

### 4.2 The fifteen discrepancy flags ✅

Grouped by the security-smell category they instantiate [6][7].

| Group | Flags |
|---|---|
| Documentation gap | `UNDOCUMENTED`, `UNREGISTERED`, `SHADOW_CANDIDATE` |
| Usage gap | `NO_TRAFFIC_IN_WINDOW`, `EFFECTIVELY_SILENT`, `STALE_6M` |
| Ownership gap | `NO_OWNER` |
| Reachability | `REACHABLE_BUT_UNUSED` |
| Security posture | `UNAUTHENTICATED`, `LEGACY_AUTH`, `SENSITIVE_DATA` |
| Lifecycle | `MARKED_DEPRECATED`, `CODE_UNTOUCHED_1Y` |
| Provenance | `NO_PIPELINE_RECORD` |

---

## 5. Interface design — the two-tier URL scanner ⬜

A customer may onboard by connecting a repository or by supplying a URL. The URL path
is deliberately tiered, for the reasons established in [10].

```mermaid
flowchart TD
    U(["Customer supplies<br/>https://api.example.com"]) --> T1

    subgraph T1["Tier 1 — any URL, zero probing"]
        A1["Fetch published<br/>OpenAPI / Swagger"]
        A2["Mine Certificate<br/>Transparency logs"]
        A3["Passive DNS<br/>enumeration"]
        A4["Parse the site's own<br/>JS bundles for routes"]
    end

    T1 --> INV["Partial inventory<br/>documented surface only"]
    INV --> Q{"Domain ownership<br/>proven?"}

    Q -->|"No"| STOP["Report Tier 1 findings.<br/>Prompt for DNS TXT record."]
    Q -->|"Yes — DNS TXT<br/>record verified"| T2

    subgraph T2["Tier 2 — authorised active scanning"]
        B1["Active endpoint probing"]
        B2["Auth posture checks"]
        B3["Response fingerprinting"]
    end

    T2 --> FULL["Full external inventory"]

    classDef safe fill:#dff0e8,stroke:#2F6B63,color:#123
    classDef gated fill:#f4e4e0,stroke:#9B3B2E,color:#123
    class A1,A2,A3,A4,INV safe
    class B1,B2,B3,FULL gated
```

**Tier 1 makes no request to any customer endpoint.** It reads published
specifications, public CT logs, public DNS, and the customer's own served JavaScript.
Tier 2 unlocks only after a DNS TXT record proves domain control — the same pattern
used by Google Search Console and by commercial attack-surface platforms.

This is a design constraint, not a limitation to apologise for. Probing endpoints on
infrastructure one does not control is unauthorised access; against a bank it is a
criminal matter. A product that shipped without this gate could not be sold.

---

## 6. Traceability — requirements to design

| Requirement | Origin | Addressed by |
|---|---|---|
| Identify a dataset for the ML engine | Jury review | §4.1, synthetic labelled estate; `dataset/build.py` ✅ |
| Use explainable AI | Jury review | §2.2 `Verdict`/`Reason`; §3.3 rules-first; SHAP for the model layer 🔵 |
| Comparative before/after study | Jury review | §7 benchmark: single-source baseline vs. correlated full pipeline 🔵 |
| Focus on one application | Jury review | Simulated retail-banking mesh, 6 services, 25 endpoints ✅ |
| Enhance the engine section of the paper | Jury review | Written last, from measured results (Phase 9) ⬜ |
| Scan via GitHub repository | Product | Real Semgrep `CodeConnector` (Phase 1) ⬜ |
| Scan via URL | Product | §5 two-tier scanner ⬜ |
| Shippable, self-hosted | Product | §2.3 deployment; credential separation ⬜ |

---

## 7. The comparative evaluation design 🔵

The before/after paper requires a measurable baseline built into the product, not
assembled afterwards.

**Baseline mode** answers: *what would a conventional single-source approach have
found?* It runs the same estate through one authoritative source alone — the gateway
registry, as a bank would today.

**Full mode** runs the complete six-source correlated pipeline.

### 7.1 Measured results ✅

Produced by `python -m evaluation.benchmark`, which writes `data/benchmark.json`.

| Configuration | Estate coverage | Zombies caught | Zombie recall |
|---|---|---|---|
| Gateway registry only | 19 / 25 (76.0%) | 2 / 8 | 25.0% |
| OpenAPI specification only | 17 / 25 (68.0%) | 0 / 8 | 0.0% |
| Gateway + specification (conventional) | 19 / 25 (76.0%) | 2 / 8 | 25.0% |
| **API Exorcist — six sources, correlated** | **25 / 25 (100%)** | **8 / 8** | **100.0%** |

**End-to-end zombie recall is the headline metric**, not raw discovery coverage. It
counts an endpoint only if the configuration both *discovered* and *correctly
classified* it, because an organisation cannot remediate an endpoint it never knew
existed. A configuration that finds an endpoint and calls it healthy has not helped.

The six zombies a conventional inventory misses entirely are:

```
GET  /v1/kyc/documents/{id}/raw        unauthenticated, raw identity documents
GET  /v1/cards/{id}/pin                abandoned PIN-retrieval design
POST /v1/debug/payments/replay         unauthenticated payment replay
POST /v1/internal/accounts/reindex     2022 migration leftover
POST /v1/loans/scorecard/experiment    concluded A/B experiment
GET  /v1/notify/templates/preview      retired internal CMS tool
```

**Four of the eight carry no authentication at all.** Note that the OpenAPI-only
configuration scores 0% — documentation, on its own, is worse than useless for this
problem, because the endpoints that matter are precisely the ones nobody documented.

That every configuration runs identical pipeline code with only the connector set
varying is what makes this a controlled comparison rather than a marketing claim.

---

## 8. Known design limitations

Stated here rather than discovered by a reviewer.

1. **Ownership is unobservable for fully-shadow endpoints.** An endpoint absent from
   both the spec and CI/CD has no observable owner, so a `ZOMBIE` with a living owner
   is indistinguishable from an `ORPHANED` one on that feature alone. Mitigation:
   repository `CODEOWNERS` as a seventh signal.
2. **The estate is small.** 25 endpoints proves correlation works; it cannot
   cross-validate a model. Mitigation: parameterised generation of many estates.
3. **The traffic window is fixed at 30 days.** A genuinely quarterly batch endpoint
   looks silent. Mitigation is deliberately *not* in discovery — it is the Safe Kill
   approval gate, because the correct response to seasonal ambiguity is a human
   decision, not a smarter threshold.
4. **The estate is synthetic.** The defensible claim is that the engine recovers known
   decay patterns from partial, disagreeing evidence — never that it is validated on
   production bank data. No public zombie-API corpus exists, because a real API
   inventory is a map of an attack surface.

---

## 9. References

Full citations in [`literature-review.md`](literature-review.md) §11. Numbering matches.

[1] Caivano et al., EMSE 2023 · [2] Cassieri et al., PROFES 2023 ·
[3] Bushong et al., ASE 2021 · [4] Ma et al., FGCS 2019 ·
[5] Abdelfattah & Cerný, ESOCC 2023 · [6] Dell'Immagine et al., Future Internet 2023 ·
[7] Ponce et al., CLEIej 2024 · [8] Lundberg & Lee, NIPS 2017 ·
[9] Gaspar et al., IEEE Access 2024 · [10] Scheitle et al., IMC 2018
