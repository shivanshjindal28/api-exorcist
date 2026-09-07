# API Exorcist

**Autonomous discovery and safe elimination of zombie, shadow and orphaned APIs.**

Capstone project — B.Tech CSE (Cyber Security), MPSTME, NMIMS University · 2026–2027

---

## The problem

A bank's software estate is a building with thousands of doors. Every feature ships
another one. Teams reorganise, products are discontinued, people leave — and nobody
walks the corridors checking which doors are still needed. Years later there are doors
opening into rooms no one uses, that no one remembers building, and that are **still
unlocked**.

Those doors are API endpoints. OWASP lists *Improper Inventory Management* in its API
Security Top 10 for exactly this reason: an endpoint nobody knows about is an endpoint
nobody patches, monitors or audits.

Existing tools can *find* endpoints, and some can flag suspicious ones. **None can
safely turn one off.** That gap is this project's contribution.

### The four states

| | Definition | Action |
|---|---|---|
| **ACTIVE** | Documented, owned, in genuine use | Leave alone |
| **DEPRECATED** | Announced as retiring, still responding | Confirm a removal date exists |
| **ORPHANED** | Still genuinely used, but nobody owns it | Assign an owner — **do not remove** |
| **ZOMBIE** | No meaningful use, largely invisible | Candidate for Safe Kill |

**Every one of those is defined in terms of *use*.** That single fact drives most of
the architecture, and explains the system's most important behaviour — see
[Repository scans abstain](#repository-scans-abstain-and-that-is-the-point).

---

## Contents

- [Quick start](#quick-start)
- [Progress](#progress)
- [Headline results](#headline-results)
- [How it works](#how-it-works)
- [Command reference](#command-reference)
- [Scanning a real repository](#scanning-a-real-repository)
- [The removal gate](#the-removal-gate)
- [The learned model](#the-learned-model-and-why-it-did-not-replace-the-rules)
- [Evaluation methodology](#evaluation-methodology)
- [Design decisions](#design-decisions)
- [Known limitations](#known-limitations)
- [Project layout](#project-layout)
- [Development](#development)
- [Documentation](#documentation)

---

## Quick start

Python 3.10+. The pipeline, classifier, graph and evaluation run on the **standard
library alone** — no infrastructure, no services, no network.

```bash
pip install -e .
```

```bash
apix scan
```

That is the whole demo: six sources collected, correlated, classified and explained,
in under a second.

---

## Progress

| Phase | | |
|---|---|---|
| 0 | Packaging, CLI, CI, strict typing | ✅ done |
| 1 | Real GitHub scanning — Semgrep AST, git history, CODEOWNERS | ✅ done |
| 2 | Dependency graph, blast radius, removal gate | ✅ done |
| 3 | Scaled dataset, trained model, SHAP attribution | ✅ done |
| 4 | Safe Kill Simulation — canary, rollback, audit log | ⬜ next |
| 5 | REST API and dashboard | ⬜ |
| 6 | CI/CD enforcement plugin | ⬜ |
| 7–8 | Security hardening, deployment, observability | ⬜ |

### What is built

| Capability | State |
|---|---|
| Six-source discovery, each connector with deliberate blind spots | ✅ |
| Multi-source correlation into a unified inventory (14 flags) | ✅ |
| Four-class rule classifier, deterministic and auditable (15 evidence rules) | ✅ |
| Per-verdict explanations with signed evidence contributions | ✅ |
| Source-availability handling — rules abstain, verdicts can be indeterminate | ✅ |
| Evaluation harness — per-class P/R/F1, confusion matrix | ✅ |
| Comparative before/after benchmark | ✅ |
| Real GitHub repository scanning (Semgrep AST, git history, CODEOWNERS) | ✅ |
| Dependency graph + blast radius, with a Neo4j backend | ✅ |
| Removal gate — classifier and graph must both agree | ✅ |
| Labelled dataset — schema, scaled by generated estates | ✅ |
| Trained model with SHAP attribution, used as a veto over removals | ✅ |
| 85 tests, three ground-truth leakage guards, CI on 3.10 and 3.12 | ✅ |
| Safe Kill Simulation — canary, rollback, audit log | ⬜ |
| CI/CD enforcement plugin, REST API, dashboard | ⬜ |

**Next: Phase 4 — Safe Kill.** Progressive canary rollout, automatic rollback on
error-rate breach, and a hash-chained append-only audit log. Its two preconditions —
the dependency graph and the removal gate — are already in place.

---

## Headline results

**Classification** on the 25-endpoint estate: accuracy **0.960** (24/25), macro-F1
**0.940**, **zombie recall 1.000 with zero live endpoints marked for removal**.

That figure is the *rule* classifier. The learned model is a separate layer, evaluated
separately — see [The learned model](#the-learned-model-and-why-it-did-not-replace-the-rules).

**Comparative evaluation** — identical pipeline code, only the evidence sources differ:

| Configuration | Coverage | Rules usable | Zombies caught | Recall |
|---|---|---|---|---|
| Gateway registry only | 76.0% | 0 / 15 | 0 / 8 | 0.0% |
| OpenAPI specification only | 68.0% | 3 / 15 | 0 / 8 | 0.0% |
| Gateway + spec (conventional) | 76.0% | 5 / 15 | 2 / 8 | 25.0% |
| **All six, correlated** | **100%** | **15 / 15** | **8 / 8** | **100%** |

A conventional API inventory finds **2 of 8** zombies. It classifies those two
correctly — it simply never *discovers* the other six, which are invisible to both the
gateway and the specification. Its failure is visibility, not judgement, and better
classification would not have helped it.

A gateway registry alone can evaluate **not a single** classification rule. It
enumerates endpoints without being able to say anything about them.

Reproduce with `apix benchmark`; figures are written to `data/benchmark.json` and
asserted by CI.

---

## How it works

### 1. Six partial witnesses

Each connector sees part of the estate and misses part of it. The blind spots are
deliberate and modelled on real tooling:

| Source | Coverage | Blind spot |
|---|---|---|
| CODE (Semgrep) | 100% | Cannot tell whether a route is actually deployed |
| DNS / service mesh | 96% | Misses in-cluster-only endpoints |
| GATEWAY (Kong) | 76% | Misses anything bypassing the gateway |
| CICD | 76% | Misses manually-deployed endpoints |
| TRAFFIC (Zeek) | 72% | Cannot see endpoints that are silent |
| OPENAPI | 68% | Only sees what someone documented |

**6 endpoints are invisible to both authoritative sources** (gateway + spec). Those
are the shadow candidates no single tool could surface — the empirical justification
for the whole architecture.

### 2. Correlation: absence is the signal

> A zombie API is not found by any single positive observation. It is found by a
> **pattern of absence** — present in code, still reachable via DNS, absent from the
> specification, absent from the gateway registry, and silent in traffic.

No connector can conclude that alone; only the join can. The correlator reconciles all
six into one record per endpoint and records *which sources failed to see it*, then
derives **14 discrepancy flags** (`SHADOW_CANDIDATE`, `REACHABLE_BUT_UNUSED`,
`UNAUTHENTICATED`, …). Those flags are security smells in the sense of Dell'Immagine
et al. — structural indicators of elevated risk, not vulnerabilities themselves.

### 3. Classification: additive evidence, not a decision tree

**15 evidence rules**, each a predicate paired with a signed weight per class. Every
rule whose predicate holds contributes; the highest total wins; confidence is the
softmax margin.

Additive scoring rather than a tree, for three reasons that all matter downstream:

1. **It degrades gracefully.** A tree commits at its first branch; real evidence
   conflicts, and scoring weighs the conflict.
2. **Confidence falls out of the margin** — the signal for when to consult the model.
3. **It matches the shape of SHAP**, so the rule layer and the model layer emit the
   same explanation structure and share one renderer.

### 4. Explanation: the reasons *are* the decision

```
[#####] GET /v1/kyc/documents/{id}/raw
        verdict : ZOMBIE (99% confidence)
        because :
          + no meaningful traffic in the capture window        [TRAFFIC, +3.5]
          + absent from both the spec and the gateway registry [OPENAPI+GATEWAY, +2.5]
          + no meaningful use for over six months              [TRAFFIC, +2.0]
          + still resolvable via DNS despite no traffic        [DNS+TRAFFIC, +1.5]
          + no CI/CD pipeline record                           [CICD, +1.2]
        action  : Candidate for Safe Kill. Blast radius must be computed and an
                  approval recorded before any shutdown begins.
```

There is no separate explanation step that could disagree with the verdict — the
arithmetic shown *is* the arithmetic that decided. Every verdict also serialises into
an audit-log shape carrying all four class scores, not only the winner.

### 5. Source availability: "nobody asked" is not "the answer was no"

Rules declare which sources they depend on and **abstain** when a source was never
consulted. Without this, a scan with no traffic sensor reads every endpoint as silent
and labels healthy production APIs as zombies, with high confidence.

Consequences, all enforced in code:

- A ZOMBIE verdict is **not actionable** unless a usage source was actually consulted.
- When every rule abstains, the verdict is **indeterminate** — not ACTIVE by enum
  tie-break, which would let a blind configuration appear to certify everything.
- Confidence in that case is exactly 0.25, uniform across four classes: no idea.

---

## Command reference

| Command | What it does |
|---|---|
| `apix scan` | Discover, classify and explain (simulated estate) |
| `apix scan --model` | Add the learned layer as a veto over removal candidates |
| `apix scan --github OWNER/REPO` | Scan a real GitHub repository |
| `apix scan --local PATH` | Scan an already-cloned repository |
| `apix scan --coverage` | Per-source coverage table only |
| `apix scan --classify-only` | Verdicts and explanations, no coverage table |
| `apix scan --explain-all` | Explain every endpoint, not only risky ones |
| `apix scan --findings` | Raw discovery flags, before classification |
| `apix scan --json` | Machine-readable inventory |
| `apix impact` | Dependency graph and the removal gate |
| `apix impact "GET /v2/accounts/{id}"` | Blast radius for one endpoint |
| `apix benchmark` | The comparative before/after study |
| `apix train --estates 120 --save` | Train the model and compare it against the rules |
| `apix dataset` | Build the labelled dataset |
| `apix version` | Version and resolved configuration |

**Exit codes follow CI convention:** `0` clean, `1` findings present, `2` error. That
is what lets `apix scan` be dropped into a pipeline as a gate.

Outputs land in `./data/` — `inventory.json`, `verdicts.json` (audit-shaped),
`benchmark.json` (paper-ready figures), `training-report.json`, `dataset.csv`.

---

## Scanning a real repository

```bash
pip install -e ".[live]"
```

```bash
apix scan --github fastapi/full-stack-fastapi-template
```

This clones the repository, extracts route declarations with **Semgrep** (AST
matching, so a route written inside a comment or a string literal is *not* counted —
which a regular expression cannot distinguish), reads per-file staleness from the real
commit history, takes ownership from `CODEOWNERS`, and parses any committed OpenAPI
specification.

Verified against that repository: **23 routes found, 1,497 commits walked, 15 workflow
files detected.**

### Repository scans abstain, and that is the point

A repository has no gateway registry, no traffic sensor and no DNS. Since all four
lifecycle classes are defined in terms of *use*, the system **refuses to classify**:

```
  sources consulted   : CICD, CODE, OPENAPI
  sources UNAVAILABLE : DNS, GATEWAY, TRAFFIC

  Lifecycle classification: NOT AVAILABLE
    Every class (active / deprecated / orphaned / zombie) is
    defined by usage, and no traffic source was consulted.

  Findings across 23 endpoint(s):
      23  handler exists in code but the endpoint is not documented
      23  no owning team could be determined
       3  no commit touching this handler in over a year
```

A naive tool would see zero observed traffic and call all 23 zombies — and be wrong
about every one, since this is a live template. **A tool that states what it cannot
know is a tool a bank can deploy.**

---

## The removal gate

A ZOMBIE verdict is a *hypothesis* that an endpoint is unused. The dependency graph is
the first thing that can falsify it, and **both signals are required**:

```bash
apix impact
```

```
  endpoints          : 25      services : 13
  observed call edges: 30      isolated : 8

  CLEARED FOR SAFE KILL — 8      BLOCKED — 0
```

All 8 zombies are isolated — nothing observed calls them. That is *why* they are safe,
and it is checked rather than assumed. All 3 deprecated endpoints retain live callers
and would be blocked even if the classifier misjudged one.

Blast radius alternates `CALLS` and `OWNS` edges, because killing an endpoint breaks
its callers, whose own endpoints then degrade, and whatever called *those* is affected
in turn:

```bash
apix impact "GET /v2/accounts/{id}"
```

```
  severity      : severe        depth reached : 5 hop(s)
  direct callers: lending-service, mobile-bff, payments-service
  reached onward: cards-service, kyc-service, marketing-batch,
                  merchant-gateway, notifications-service, partner-psp-adapter
```

Three direct callers, **nine services affected, five hops deep**. A single-hop
traversal would report three and miss six.

**That unbounded depth is the argument for a graph store**: in SQL it is a recursive
CTE whose cost grows per hop; in Cypher it is `(dep)-[:CALLS|OWNS*1..N]->(e)`. Runs
in-process by default; `APIX_GRAPH=neo4j` switches backends with no code change.

**Stated limitation:** isolation means no dependency was *observed*, not that none
exists. A caller silent during the capture window is invisible — which is why this is
a gate and not a proof, and why approval and canary rollout still follow it.

---

## The learned model, and why it did not replace the rules

25 endpoints cannot train anything, so `simulated_env/generator.py` produces many
estates — **by lifecycle mechanism, not by label rule**. An endpoint is put through a
story (a product is discontinued, a team dissolves, a migration stalls, a debug route
outlives an incident) and its features are consequences of that story. Each estate
also draws its own observation discipline, so one organisation's sensor biases cannot
be memorised.

```bash
pip install -e ".[ml]" && apix train --estates 120 --save
```

Split is **by estate, never by endpoint** — endpoints inside one estate share its
biases, and splitting by endpoint would put those correlations on both sides.

| On 36 held-out estates | Rules | Model |
|---|---|---|
| macro-F1 | 0.842 | 0.844 |
| ZOMBIE false positives | 17 | **0** |
| DEPRECATED F1 | 0.674 | 0.514 |

**Aggregate: indistinguishable.** But the average hides what matters — the rules
produce 17 false zombies on unseen estates and the model produces none. A false zombie
is an outage; a missed one is a line on a report. So the model is not a replacement,
it is a **veto**:

```bash
apix scan --model
```

The rules propose (they need no training data, which is what lets a new deployment
work on day one, and they are auditable line by line). The model may block, never
create. Both opinions are retained on the verdict so an auditor sees that the rules
proposed removal and the model objected.

SHAP renders through the *same* `Reason` objects the rules emit:

```
GET /v1/kyc/documents/{id}/raw  ->  ZOMBIE (100%)
   +10.736  last used 3650 days ago
   + 7.692  handler last committed 548 days ago
   + 1.536  0 calls/day
   + 0.136  no owning team recorded
```

Exact `TreeExplainer` values are affordable here for the reason Gaspar et al. identify
as prohibitive for an intrusion detection system: this is a **per-scan batch workload**,
not per-packet at line rate.

**The veto has a measured cost, and it is not hidden.** On the demo estate it wrongly
blocks one genuine zombie — an unauthenticated debug route with 3 calls/day, which the
model reads as still in use. That endpoint keeps its ZOMBIE label and full evidence; it
simply does not auto-clear.

### Two generator artifacts, found by disbelieving good results

A first run scored 0.968 F1 on DEPRECATED while permutation importance showed it
relying on staleness and almost ignoring `spec_deprecated`. Cause: each story drew its
own traffic distribution, so median daily calls ran 4807 / 146 / 1137 / 0 across the
four classes — nearly separable without any semantics. A second artifact gave ACTIVE
endpoints authentication schemes no other class could have.

Both are now guarded by tests. **A generated dataset is only worth training on if it
is honestly hard.**

---

## Evaluation methodology

### The one misclassification, and why it is not a bug

`POST /v1/kyc/aadhaar/ekyc` is genuinely DEPRECATED and was classified ACTIVE. It is
the one deprecated endpoint whose team never set the OpenAPI `deprecated` flag —
exactly the behaviour Cassieri et al. documented. Every *observable* property of it is
identical to a healthy endpoint.

The confidence is the tell: **0.803, the same as correctly-classified ACTIVE
endpoints.** The classifier is not hesitant; it is confidently wrong, because the
evidence genuinely does not distinguish the two cases. No model improvement fixes
that — only a new signal would.

At scale the same ceiling appears: across generated estates, DEPRECATED recall tracks
the rate at which teams set the flag (≈0.59). **The limit is observability, not the
algorithm.**

### The dataset

No public corpus of zombie APIs exists, and there is a structural reason it never
will: a real API inventory is a map of an attack surface, so no organisation publishes
one. Generating it is not a shortcut around an available dataset — it is the only way
to obtain ground-truth labels.

**16 observable features, 4 classes.** Labels are attached *after* feature extraction
and are never available as an input. Two AST-level guards and a token guard enforce
that no detection module can read `true_label` or `decay_story`.

**Stated limitation:** the classifier is validated against decay patterns we modelled.
The defensible claim is *"the engine recovers known decay patterns from partial,
disagreeing evidence"* — never *"validated on production bank data."*

---

## Design decisions

**Zeek over Suricata.** Suricata is signature-based and optimised for known attack
patterns. We are not hunting attacks; we need complete, protocol-aware visibility of
*all* traffic to build an inventory. Zeek is purpose-built for that, and being passive
it requires no change to production systems — essential in a bank.

**Semgrep over regex.** Semgrep parses code into an abstract syntax tree and matches
on structure, so it works across languages and formatting styles without the false
matches a regex over source produces. Demonstrated: it finds real routes and ignores
decoys planted in comments and string literals.

**Additive scoring over a decision tree.** Degrades gracefully on conflicting
evidence, yields confidence from the margin, and shares SHAP's explanation shape.

**Graph store for dependencies.** Blast radius is an unbounded-depth traversal, the
query relational stores handle worst. Ma et al. built their Service Dependency Graph
in Neo4j for the same reason.

**Rules decide, the model advises.** A new deployment has zero labels on day one; if
the product needed a trained model it could not onboard a single customer.

**Everything optional is optional.** `LocalBus` and `InMemoryGraph` are the defaults,
so the demo and the test suite need nothing running. `KafkaBus` and `Neo4jGraph` are
the deployment path through the same interfaces, and the calling code is identical.

**Observed beats declared.** Where sources conflict, traffic-observed auth outranks
gateway-declared auth — a gateway can claim OAuth2 on a route the service also exposes
directly with no auth.

---

## Known limitations

State these; do not hide them.

1. **Ownership is unobservable for fully-shadow endpoints.** If an endpoint is in
   neither the spec nor CI/CD, no owner can be determined. Partly addressed —
   repository scans read `CODEOWNERS` as a third ownership source.
2. **The hand-written estate is small.** 25 endpoints, two of them ORPHANED. Enough to
   show correlation works, too small to train on; that is what the generator exists
   for.
3. **Traffic capture window is fixed at 30 days.** A genuinely seasonal endpoint can
   look silent. Deliberately *not* mitigated in discovery — the right response to
   seasonal ambiguity is a human decision at the approval gate, not a wider window
   that hides it.
4. **Repository scans cannot make lifecycle claims.** Enforced, not advisory.
5. **Router mount prefixes resolve only when literal.** A project mounting with
   `prefix=settings.API_V1_STR` needs cross-module constant resolution, which is not
   implemented. Those paths are flagged `prefix_resolved=False` rather than presented
   as absolute.
6. **Graph isolation means no dependency was *observed*.** A caller silent during the
   capture window is invisible.
7. **The estate is synthetic.** The architecture is not — `apix scan --github` reads
   real repositories.

---

## Project layout

```
src/apix/
  cli.py                   The `apix` command-line entry point
  config.py                Settings from environment; defaults need no infra
  pipeline.py              Orchestrates discovery and classification
  connectors/
    base.py                DiscoverySignal contract; SimulatedConnector base
    gateway.py             Gateway registry + OpenAPI spec (authoritative)
    discovery.py           Traffic, code, DNS, CI/CD (find what authorities miss)
  ingestion/bus.py         Transport: LocalBus (default) / Kafka / Elasticsearch
  inventory/correlator.py  Multi-source correlation -> inventory + 14 flags
  engine/
    verdict.py             Classification, Verdict, Reason; actionability rules
    rules.py               15 evidence rules with signed per-class weights
    explain.py             Natural-language explanations + audit-log shape
    model.py               Learned classifier, SHAP attribution, veto hybrid
  graph/
    model.py               BlastRadius, the DependencyGraph interface
    memory.py              In-process graph (default; no infrastructure)
    neo4j_store.py         Neo4j backend, variable-length Cypher traversal
    build.py               Graph construction and the removal gate
  extractors/
    base.py                ExtractedRoute, path normalisation across frameworks
    semgrep_extractor.py   AST route extraction; router prefix composition
    rules/routes.yaml      Semgrep rules: FastAPI, Flask, Express, Spring
  live/
    repo.py                Clone a repository; git-history staleness, CODEOWNERS
    connectors.py          CODE / OPENAPI / CICD read from a real checkout
    scan.py                Orchestrates a repository scan
  evaluation/
    metrics.py             Precision, recall, F1, confusion matrix
    benchmark.py           The comparative before/after study
    train.py               Model training and the honest rules-vs-model report
  dataset/build.py         Feature extraction + labelled dataset
  simulated_env/
    estate.py              The estate and its ground truth (the answer key)
    generator.py           Parameterised estates, generated by mechanism

tests/                     85 tests, three ground-truth leakage guards
demo/                      Review runbook, paced demo runner, expected output
docs/                      Literature review, design document, source papers,
                           diagram renderer, Word builder, claims verifier
```

**Dependency direction is one-way.** Connectors know nothing of ingestion, and the
engine never reaches back to a data source. That is what makes the simulated estate
swappable for live sources without touching anything downstream — and it is enforced
by tests, not convention.

---

## Development

```bash
pip install -e ".[dev,live,ml]" && pre-commit install
```

```bash
pytest && ruff check . && mypy && python docs/verify_claims.py
```

**85 tests**, ruff clean, mypy `--strict` clean.

### Optional extras

| Extra | Adds | For |
|---|---|---|
| `.[live]` | semgrep, pyyaml | Scanning real repositories |
| `.[ml]` | scikit-learn, shap | The model layer and SHAP |
| `.[graph]` | neo4j | Neo4j dependency graph backend |
| `.[stream]` | kafka-python, elasticsearch | Production transport |
| `.[dev]` | pytest, ruff, mypy, pre-commit | Development |

### CI

Every push runs, on Python 3.10 and 3.12:

1. **ruff** — lint
2. **mypy --strict** — types
3. **pytest** — the suite
4. **`docs/verify_claims.py`** — documented figures and status markers against the code
5. **Published figures** — fails if zombie recall drops below 100%, accuracy below
   0.95, or correlation stops beating a conventional inventory
6. **The removal gate** — fails if any endpoint is ever cleared for removal while
   dependents exist

**CI installs only `.[dev]`.** A machine with the ML extras will pass things CI fails,
so reproduce it before pushing:

```bash
python -m venv .ci-venv && .ci-venv/bin/pip install -e ".[dev]"
.ci-venv/bin/python -m pytest && .ci-venv/bin/python docs/verify_claims.py
```

On Windows the interpreter is at `.ci-venv\Scripts\python.exe`.

### Why `verify_claims.py` exists

Documentation drifted from the code three times in this project. Tests check code
against code; a figure in a design document is a claim about the system and nothing
was checking it. The script compares every documented number and status marker against
values computed live from the source, in both directions — a capability marked done
whose module does not exist fails just as loudly as one marked pending after it
shipped.

### Production transport

```bash
docker compose up -d
APIX_BUS=kafka APIX_GRAPH=neo4j apix scan
```

---

## Documentation

| Document | What it covers |
|---|---|
| [`docs/literature-review.md`](docs/literature-review.md) | Nine peer-reviewed sources, each verified against DBLP, with a traceability matrix mapping every paper to the module it justifies |
| [`docs/design-document.md`](docs/design-document.md) | Structural and behavioural design — 10 diagrams, measured results, known design limitations |
| [`docs/papers/README.md`](docs/papers/README.md) | The source PDFs and their full-text verification status |
| [`demo/DEMO.md`](demo/DEMO.md) | Review runbook — setup, six-step walkthrough, anticipated questions |
| [`CLAUDE.md`](CLAUDE.md) | Working notes: the non-negotiable rules and environment gotchas |

Nine of the ten paper PDFs are present; four have been checked against their full
text. **That checking mattered:** one paper turned out not to contain a result the
review had attributed to it, and the claim was removed rather than softened.

---

## Licence

MIT — see [LICENSE](LICENSE).
