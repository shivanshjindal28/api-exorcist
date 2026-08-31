# API Exorcist

Autonomous discovery and safe elimination of zombie, shadow, and orphaned APIs.

Capstone project — B.Tech CSE (Cyber Security), MPSTME, NMIMS University.

---

## Status: the 50% checkpoint

The system runs a complete vertical slice of its core loop:

**discover → correlate → classify → explain → measure**

| Capability | State |
|---|---|
| Six-source discovery with deliberate blind spots | ✅ |
| Multi-source correlation into a unified inventory (15 flags) | ✅ |
| Four-class rule classifier, deterministic and auditable | ✅ |
| Per-verdict explanations with signed evidence contributions | ✅ |
| Evaluation harness — per-class P/R/F1, confusion matrix | ✅ |
| Comparative before/after benchmark | ✅ |
| Labelled dataset for the ML engine | ✅ |
| 31 tests, including two ground-truth leakage guards | ✅ |
| Dependency graph (Neo4j), SHAP over a trained model | ⬜ |
| Safe Kill Simulation, CI/CD enforcement, dashboard | ⬜ |

### Headline results

**Classification** — accuracy 0.960 (24/25), macro-F1 0.940.
**Zombie recall 1.000, with zero live endpoints marked for removal.**

**Comparative evaluation** — identical pipeline code, only the evidence sources differ:

| Configuration | Coverage | Rules usable | Zombie recall |
|---|---|---|---|
| Gateway registry only | 76.0% | 0 / 14 | 0.0% |
| OpenAPI specification only | 68.0% | 3 / 14 | 0.0% |
| Gateway + spec (conventional) | 76.0% | 5 / 14 | 0.0% |
| **All six, correlated** | **100%** | **14 / 14** | **100%** |

A conventional API inventory finds **none** of the 8 zombies. Correlation finds all
8 — and four of them are unauthenticated. A gateway registry on its own cannot
evaluate a single classification rule: it enumerates endpoints without being able to
say anything about them.

---

## Quick start

Python 3.10+. The pipeline, classifier and evaluation run on the standard
library alone — no infrastructure, no services, no network.

```bash
pip install -e .
```

```bash
apix scan
```

That's the whole demo: six sources collected, correlated, classified and
explained.

### Commands

### Scanning a real repository

```bash
pip install -e ".[live]"
```

```bash
apix scan --github fastapi/full-stack-fastapi-template
```

This clones the repository, extracts route declarations with **Semgrep** (AST
matching, so a route written in a comment or a string literal is not counted),
reads per-file staleness from the real commit history, takes ownership from
CODEOWNERS, and parses any committed OpenAPI specification.

**A repository scan is deliberately partial.** It has no gateway registry, no
traffic capture and no DNS. Rules depending on those abstain rather than firing,
so nothing found this way is ever a removal candidate — you cannot conclude an
endpoint is unused when usage was never measured. The scan says so explicitly.

### Commands

| Command | What it does |
|---|---|
| `apix scan` | Discover, classify and explain (simulated estate) |
| `apix scan --github OWNER/REPO` | Scan a real GitHub repository |
| `apix scan --local PATH` | Scan an already-cloned repository |
| `apix scan --coverage` | Per-source coverage table only |
| `apix scan --classify-only` | Verdicts and explanations, no coverage table |
| `apix scan --explain-all` | Explain every endpoint, not only risky ones |
| `apix scan --findings` | Raw discovery flags, before classification |
| `apix scan --json` | Machine-readable inventory |
| `apix benchmark` | The comparative before/after study |
| `apix dataset` | Build the labelled dataset for the ML engine |
| `apix version` | Version and resolved configuration |

`apix scan` **exits 1 when zombies are found** and 0 when clean, so it drops
into a CI pipeline as a gate.

### Development

```bash
pip install -e ".[dev]" && pre-commit install
```

```bash
pytest && ruff check . && mypy
```

32 tests, ruff clean, mypy `--strict` clean. Optional extras: `.[stream]` for
Kafka and Elasticsearch, `.[ml]` for the Phase 3 model layer and SHAP.

Outputs land in `./data/`: `inventory.json`, `verdicts.json` (audit-shaped),
`benchmark.json` (paper-ready figures), `dataset.csv`.

For the production transport path:

```bash
docker compose up -d
APIX_BUS=kafka python pipeline.py
```

---

## What it does right now

Six independent connectors observe the environment, each with genuine blind
spots. A correlation engine reconciles their disagreements into one inventory
per endpoint, and records *which sources failed to see each endpoint* — because
that pattern of absence is what identifies a zombie.

Current result against the simulated estate (25 endpoints, 6 services):

| Source | Coverage | Blind spot |
|---|---|---|
| CODE (Semgrep) | 100% | Cannot tell if a route is actually deployed |
| DNS / mesh | 96% | Misses in-cluster-only endpoints |
| GATEWAY (Kong) | 76% | Misses anything bypassing the gateway |
| CICD | 76% | Misses manually-deployed endpoints |
| TRAFFIC (Zeek) | 72% | Cannot see endpoints that are silent |
| OPENAPI | 68% | Only sees what someone documented |

**6 endpoints are invisible to both authoritative sources** (gateway + spec).
Those are the shadow/zombie candidates that no single tool could surface —
which is the empirical justification for the multi-source architecture.

---

## The core idea, in one paragraph

A zombie API is not found by any single positive observation. It is found by a
*pattern of absence*: present in code, still reachable via DNS, absent from the
OpenAPI spec, absent from the gateway registry, and silent or near-silent in
traffic. No connector can conclude that alone. Only the correlation can. This
is the concrete reason the project is not "run a scanner and read the output."

---

## Layout

```
src/apix/
  cli.py                   The `apix` command-line entry point
  config.py                Settings from environment; defaults need no infra
  pipeline.py              Orchestrates discovery and classification
  connectors/
    base.py                Shared DiscoverySignal contract
    gateway.py             Gateway registry + OpenAPI spec (authoritative)
    discovery.py           Traffic, code, DNS, CI/CD (find what authorities miss)
  ingestion/bus.py         Transport: LocalBus (default) / Kafka / Elasticsearch
  inventory/correlator.py  Multi-source correlation -> inventory + 15 flags
  engine/
    verdict.py             Classification, Verdict, Reason
    rules.py               14 evidence rules with signed per-class weights
    explain.py             Natural-language explanations + audit-log shape
  evaluation/
    metrics.py             Precision, recall, F1, confusion matrix
    benchmark.py           The comparative before/after study
  dataset/build.py         Feature extraction + labelled dataset
  simulated_env/estate.py  The estate and its ground truth (the answer key)

tests/                     32 tests, including three ground-truth leakage guards
docs/                      Literature review, design document, source papers
```

**Dependency direction is one-way.** Connectors know nothing of ingestion, and
the engine never reaches back to a data source. That is what makes the simulated
estate swappable for live sources without touching anything downstream — and it
is enforced by tests, not convention.

---

## Design decisions (be ready to defend these)

**Zeek over Suricata for discovery.** Suricata is signature-based and optimised
for matching known attack patterns. We are not hunting known attacks — we need
complete, protocol-aware visibility of *all* traffic to build an inventory. Zeek
is purpose-built for that, and being passive it requires no change to production
systems, which is essential in a bank.

**Semgrep over regex or manual review.** Semgrep parses code into an abstract
syntax tree, so it matches route declarations on structure rather than text.
That works across languages and formatting styles without the false matches a
regex over source would produce. Manual review does not scale to hundreds of
repos.

**Kafka for ingestion.** API traffic is high-volume and bursty. Kafka decouples
fast producers (traffic sensors) from slower consumers (analysis) and buffers
spikes so nothing is dropped.

**Transport is abstracted.** `LocalBus` is the default so the pipeline runs and
tests anywhere with zero dependencies; `KafkaBus` is the deployment path. The
pipeline code is identical either way. This keeps the demo reproducible on a
laptop without making the production path fake.

**Observed beats declared.** Where sources conflict, the correlator prefers what
was seen on the wire over what a config file claims. A gateway may declare OAuth2
on a route that the service also exposes directly with no auth.

---

## Dataset (jury ask #1)

No public dataset of zombie/shadow/orphaned APIs exists — real API inventories
are effectively maps of an attack surface, so no organisation publishes them,
and public API collections list only documented, live APIs (precisely the class
we do not need to detect).

We therefore generate a labelled corpus from the simulated estate, whose decay
patterns are modelled on mechanisms documented in the literature: incomplete
version migrations, decommissioned products left running, dissolved teams, debug
routes never removed, and DNS/gateway rules outliving the code they point at.

16 observable features, 4 classes. Ground-truth labels are attached *after*
feature extraction and are never available as an input.

**Stated limitation for the paper:** the classifier is validated against decay
patterns we ourselves modelled. The honest claim is *"the engine recovers known
decay patterns from partial, disagreeing evidence"* — not *"validated on
production bank data."*

---

## Known limitations (state these; do not hide them)

1. **Ownership is unobservable for fully-shadow endpoints.** If an endpoint is
   in neither the spec nor CI/CD, the system cannot determine its owner, so a
   ZOMBIE with a living owner is indistinguishable from an ORPHANED one on that
   feature alone. Week 7 will need additional signals (e.g. repository
   CODEOWNERS) to separate these.
2. **The estate is small (25 endpoints).** Enough to prove correlation works,
   too small to train and cross-validate a model. Week 7 scales this via
   parameterised generation of many synthetic estates.
3. **Traffic capture window is fixed at 30 days.** A genuinely seasonal endpoint
   (quarterly or annual batch) could look silent. Mitigated later by the Safe
   Kill Simulation's approval gate rather than by discovery.

---

## The one misclassification, and why it is not a bug

`POST /v1/kyc/aadhaar/ekyc` is genuinely `DEPRECATED` and was classified `ACTIVE`.

It is the one deprecated endpoint in the estate whose team never set the OpenAPI
`deprecated` flag — exactly the behaviour Cassieri et al. documented in their study of
deprecated API usage. Every *observable* property of it is identical to a healthy
endpoint: documented, registered, owned, carrying traffic.

The confidence is the tell: **0.803, the same as correctly-classified ACTIVE
endpoints.** The classifier is not hesitant; it is confidently wrong, because the
evidence genuinely does not distinguish the two cases. No model improvement fixes
this. Only a new signal would — `CODEOWNERS`, a changelog, a pull request referencing
the migration.

That is a finding about the limits of observation, and it is stated in the paper as
one rather than tuned away.

---

## Next

Phase 2 — Neo4j dependency graph. Ingest the inventory as nodes and caller
relationships as edges so "what depends on this endpoint" becomes a traversal. This is
the prerequisite for blast-radius computation in the Safe Kill Simulation.

Full schedule: [`docs/design-document.md`](docs/design-document.md).
Research grounding: [`docs/literature-review.md`](docs/literature-review.md).
