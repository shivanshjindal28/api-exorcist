<div align="center">

# API Exorcist

**Autonomous discovery and safe elimination of zombie, shadow and orphaned APIs.**

[![CI](https://github.com/shivanshjindal28/api-exorcist/actions/workflows/ci.yml/badge.svg?branch=main)](https://github.com/shivanshjindal28/api-exorcist/actions/workflows/ci.yml)
![Python 3.10 | 3.12](https://img.shields.io/badge/python-3.10%20%7C%203.12-3776ab)
![mypy strict](https://img.shields.io/badge/types-mypy%20strict-2a6db2)
![ruff](https://img.shields.io/badge/lint-ruff-d7ff64)
![React + TypeScript](https://img.shields.io/badge/dashboard-React%20%2B%20TypeScript-3178c6)
[![MIT licence](https://img.shields.io/badge/licence-MIT-green)](LICENSE)

Capstone project · B.Tech CSE (Cyber Security) · MPSTME, NMIMS University · 2026–2027

[Quick start](#quick-start) · [Screens](#screens) · [Headline results](#headline-results) · [How it works](#how-it-works) · [Safe Kill](#safe-kill) · [Team](#team)

</div>

<p align="center">
  <img src="docs/diagrams/screen-endpoints.png" alt="A scan of OWASP crAPI: its zombie candidates, ranked, with the evidence behind the top one" width="900">
  <br>
  <sub>A live scan of OWASP crAPI. The two insecure old versions it keeps beside their fixes come out on top, each with the evidence behind its score.</sub>
</p>

---

### At a glance

| | |
|---|---|
| **Finds** | Endpoints from six partial witnesses (code, specification, gateway, traffic, DNS, CI/CD), correlated so that what is *missing* from a source becomes evidence |
| **Judges** | ACTIVE, DEPRECATED, ORPHANED or ZOMBIE from 15 evidence rules, every verdict carrying its signed reasons; rules abstain when their source is absent |
| **Removes safely** | Removal gate, 90-day shadow, named approval, 5/25/100 canary, automatic rollback, hash-chained audit log |
| **Prevents** | A GitHub Action fails pull requests that add undocumented, unowned or zombie-in-the-making endpoints |
| **Measured on real code** | Public repositories, checked independently of the scanner: 126 of 127 endpoints agree with independent truth lists, 167 of 167 trace to the line that declares them, and all 25 reasons given for zombie candidates are true in the source |
| **Measured on simulated estates** | Correlation finds **8 of 8** zombies where a conventional inventory finds 2; across 120 generated estates, Safe Kill turns the gate's 49 would-be outages into **0**. The estates are synthetic; the engine is the same |

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
the architecture. With traffic (the demo bank), the engine classifies all four. On a
code repository, which holds no traffic, it never claims a label it cannot prove:
it ranks **zombie candidates** from the evidence the code does hold, labelled
suspected, not proven. Import the access logs the organisation already keeps and
it **proves** them: every endpoint gets one of the four labels from real usage. Scanned live, the two insecure old versions OWASP crAPI
deliberately leaves beside their fixes come out on top; see
[What a scan concludes on real code](#what-a-scan-concludes-on-real-code-zombie-candidates).

---

## Contents

- [Quick start](#quick-start)
- [Screens](#screens)
- [Scanning a project in the browser](#scanning-a-project-in-the-browser)
- [Progress](#progress)
- [Headline results](#headline-results)
- [How it works](#how-it-works)
- [Command reference](#command-reference)
- [Scanning a real repository](#scanning-a-real-repository)
- [The removal gate](#the-removal-gate)
- [Deployment and operations](#deployment-and-operations-phases-7-and-8)
- [The learned model](#the-learned-model-and-why-it-did-not-replace-the-rules)
- [Evaluation methodology](#evaluation-methodology)
- [Design decisions](#design-decisions)
- [Known limitations](#known-limitations)
- [Project layout](#project-layout)
- [Development](#development)
- [Documentation](#documentation)
- [Team](#team)

---

## Quick start

Python 3.10+, git, and Semgrep for reading routes out of code.

```bash
pip install -e ".[api,live]"
```

Then, in VS Code, press **F5** ("API Exorcist: open the app"), or run:

```bash
apix serve
```

Your browser opens on API Exorcist, already signed in. Everything from there is in
the browser: scan a project, read its report, and explore the demo bank. Stop it
with Shift+F5 in VS Code, or Ctrl+C in the terminal.

The command line is still there for scripting and CI (see the
[command reference](#command-reference)); nothing needs it.

Presenting it? [`demo/DEMO.md`](demo/DEMO.md) is the walkthrough, and
`demo\prepare.ps1` scans three real repositories ahead of time so their reports are
ready to open even without a network.

---

## Screens

| | |
|---|---|
| ![Dependency graph of OWASP crAPI](docs/diagrams/screen-graph.png) | ![Is this a real API? The evidence behind one endpoint](docs/diagrams/screen-real-api.png) |
| **Dependency graph**, read from the code: what calls each endpoint, and so what removing it would break | **Is this a real API?** The file and line that declare it, and which sources confirm it |
| ![How a verdict was reached: the full score table](docs/diagrams/screen-classify.png) | ![Safe Kill: unidentified traffic can never be approved](docs/diagrams/screen-sk-anonymous.png) |
| **How it was classified**: every rule, its contribution, and the rules that abstained | **Safe Kill**: the five steps, and an endpoint that can never be approved because its callers cannot be identified |

---

## Progress

| Phase | | |
|---|---|---|
| 0 | Packaging, CLI, CI, strict typing | ✅ done |
| 1 | Real GitHub scanning — Semgrep AST, git history, CODEOWNERS | ✅ done |
| 2 | Dependency graph, blast radius, removal gate | ✅ done |
| 3 | Scaled dataset, trained model, SHAP attribution | ✅ done |
| 4 | Safe Kill Simulation — shadow, canary, rollback, audit log | ✅ done |
| 5 | REST API: bearer tokens, roles, Safe Kill approval over HTTP | ✅ done |
| 5b | Dashboard: React + TypeScript, served by the API | ✅ done |
| 6 | CI/CD enforcement: GitHub Action, judges only what a PR changes | ✅ done |
| 7–8 | Deployment: container image, observability, security review | ✅ done |
| 9 | Browser scans: upload a project folder or paste a GitHub link | ✅ done |
| 10 | Zombie candidates from code evidence, tested on seven real repositories | ✅ done |
| 11 | Usage evidence from access logs, retirement plans, exports, drift, estate dashboard | ✅ done |
| 12 | Mentor review: classification and Safe Kill explained in the app, scans validated against independent truth, comparative analysis | ✅ done |
| — | Live website scanning | ⬜ not in this version |

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
| Safe Kill: rule-of-three shadow window, named approval, 5/25/100 canary | ✅ |
| Automatic rollback on breach, hash-chained append-only audit log | ✅ |
| 299 tests, three ground-truth leakage guards, CI on 3.10 and 3.12 | ✅ |
| REST API: hashed bearer tokens, viewer and approver roles, approval over HTTP | ✅ |
| Dashboard: React + TypeScript, same origin, strict CSP | ✅ |
| CI/CD enforcement: undocumented, unowned and zombie-in-the-making endpoints | ✅ |
| Container image: non-root, read-only filesystem, digest-pinned base, no pip | ✅ |
| Observability: Prometheus metrics, JSON logs, request ids | ✅ |
| Browser scans of an uploaded folder or a GitHub link, with a report of what could not be checked and why | ✅ |
| Zombie candidates on real code: superseded versions, client use, deprecation, debug endpoints, shadow | ✅ |
| Dependency graph drawn for every scan: calls, gateway routes and topics read from code | ✅ |
| Access-log import (nginx, ALB, Kong, API Gateway, Envoy, Traefik): real lifecycle labels on real code | ✅ |
| Retirement plans: Deprecation and Sunset headers, a 90-day watch, 410 brownout, code removal | ✅ |
| Exports: SARIF 2.1.0, inventory CSV, OpenAPI stubs for undocumented endpoints, executive report | ✅ |
| Estate dashboard, data-sensitivity priority, drift between scans of the same repository | ✅ |

**All eight phases are built, and the browser is now the way in.** Live
website scanning is shown in the app but is not available in this version. What
remains is outside this repository's
reach rather than unbuilt: a gateway plugin implementing `EnforcementBackend`
against a real gateway, an approval queue that outlives the process so the API
can run as more than one replica, and anchoring the audit chain's head in a
store the operator does not control. Each is listed under
[Known limitations](#known-limitations).

---

## Headline results

**On real code**, scanned straight from GitHub (`tests/test_realworld.py` asserts
these, and what must not be flagged):

| Repository | What the scan puts at the top |
|---|---|
| OWASP crAPI | `POST .../v2/check-otp` and `POST .../v2.7/user/login-with-token`, old versions crAPI deliberately leaves beside their fixes (the v2 OTP check has no attempt limit; v3 locks after 10), as **likely zombies**: a newer version exists and its own web app calls only that one |
| VAmPI | `/users/v1/_debug` and `/createdb`, debug endpoints shipped in the API |
| spring-petclinic-rest | `GET /owners` and `GET /pets`, superseded by their v2 |
| full-stack-fastapi-template | the six endpoints its generated client has and its front end never calls |

**Are those endpoints real, and are the zombies zombies?** Checked independently of
the scanner (final report, Section 4.8):

| Check | Result |
|---|---|
| Endpoints found in code against independent truth lists (generated clients, API-first specs, route files read by hand), five repositories | **126 of 127 agree** (precision and recall 0.992) |
| Every endpoint reported from code traced to the line that declares it, six repositories | **167 of 167** |
| Every reason given for every zombie candidate checked against the project's source | **25 of 25 true** |

The one disagreement is spring-petclinic-rest, where the truth list itself is wrong:
its spec documents a `GET /oops` with no handler, and omits a root route the code
serves. The first run of this check scored 107 of 127 and exposed two extractor
defects (routers built and mounted in the same file, and a route read from an
end-to-end test). Both were fixed and are covered by tests.

**On the simulated estate**, where traffic and ground truth exist:

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
| `apix safekill` | Shadow every removal candidate; stops at approval |
| `apix safekill --approve-as NAME` | Approve clean candidates; canary, rollback, retire |
| `apix safekill --hidden-caller EP` | What-if: a month-end caller the capture never saw |
| `apix safekill --evaluate` | Measure Safe Kill across 120 generated estates |
| `apix safekill --verify PATH` | Verify an audit log's hash chain |
| `apix serve` | The app: opens the browser signed in, on 127.0.0.1:8600 or the next free port |
| `apix serve --log-format json --no-docs` | As deployed: JSON logs, no Swagger pages |
| `apix token NAME --role approver` | Mint a token; prints it once, stores only its hash |
| `apix enforce --base origin/main` | Judge what this change does to the API surface |
| `apix benchmark` | The comparative before/after study |
| `apix train --estates 120 --save` | Train the model and compare it against the rules |
| `apix dataset` | Build the labelled dataset |
| `apix version` | Version and resolved configuration |

**Exit codes follow CI convention:** `0` clean, `1` findings present, `2` error. That
is what lets `apix scan` be dropped into a pipeline as a gate.

Outputs land in `./data/` — `inventory.json`, `verdicts.json` (audit-shaped),
`benchmark.json` (paper-ready figures), `training-report.json`, `dataset.csv`,
`safekill-audit.jsonl` (the hash-chained audit log), `safekill-eval.json`.

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

### Repository scans do not guess a lifecycle, and that is the point

A repository has no gateway registry, no traffic sensor and no DNS. Since all four
lifecycle classes are defined in terms of *use*, the system **refuses to put a
lifecycle label on any endpoint**:

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

What it does instead is rank **zombie candidates** from the evidence a repository
does hold (newer versions, the project's own clients, deprecation markers, debug
endpoints), each labelled suspected and each with the sentences behind its score;
see [What a scan concludes on real code](#what-a-scan-concludes-on-real-code-zombie-candidates).

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

## Safe Kill

The removal gate ends with a candidate two independent systems agree is dead. That
agreement is still not proof: a caller that was silent while traffic was captured is
invisible to both. Safe Kill is what happens next.

```
NOMINATED -> BLAST_RADIUS -> BLOCKED
                          -> SHADOW -> REJECTED
                                    -> AWAITING_APPROVAL -> DENIED
                                                         -> CANARY 5% -> 25% -> 100%
                                                               -> ROLLED_BACK
                                                               -> RETIRED
```

The transition table is the design document's state diagram made executable: a move
the design does not contain raises instead of being recorded. Every transition, the
failures included, is written to an append-only, hash-chained audit log.

### Why the gate is not enough, measured

Across 120 generated estates the rules wrongly call **49 live endpoints the gate
clears** ZOMBIE, and the graph blocks **none** of them. They carry 1 to 9 calls a day,
too few for the traffic sensor to record a caller edge, so the graph sees nothing
depending on them. Removed on the gate's word alone, every one is an outage.

### Why the design's canary became a shadow first

The design drew 5% -> 25% -> 100%. On a busy endpoint that is right. On the endpoints
Safe Kill actually receives it is blind: a 5% canary on a one-call-a-day endpoint
refuses an expected 0.05 requests a day and almost always sees nothing.

So the design's "Simulated" stage is a **shadow kill**: nothing is refused, every
request that *would* have been is recorded with its caller. It harms nobody, so it can
run as long as the statistics require, and that length is derived rather than chosen.
To be 95% sure of catching a caller that calls once every 30 days (the month-end batch
job, the textbook hidden dependency), watch for ln(20) x 30 = **90 days**: the rule of
three.

### What the shadow is worth

Same candidates, same estates, only the shadow length changes. Zero is the design as
originally drawn.

| Shadow | Live: caught in shadow | Live: rolled back | Live: outage | Real requests refused | Dead: wrongly kept |
|---:|---:|---:|---:|---:|---:|
| 0 days | 0 | 49 | 0 | 67 | 118 |
| 3 days | 26 | 20 | 3 | 43 | 15 |
| 7 days | 35 | 8 | 6 | 12 | 4 |
| 30 days | 45 | 0 | 4 | 0 | 0 |
| **90 days** | **48** | **1** | **0** | **1** | **0** |

Four things this table says, and one it does not:

- **The canary-only design is trigger-happy, not discriminating.** Its zero outages
  hide that 21 of its 49 catches were triggered by scanner noise rather than the real
  caller. With no shadow there is no baseline for anonymous traffic, and the same
  trigger wrongly keeps 118 dead endpoints running, which is 15% of the attack surface
  the tool exists to close.
- **A short shadow is worse than none on outages.** Three days is long enough to
  calibrate the noise baseline, which switches off the lucky trigger, and too short to
  catch slow callers.
- **The result follows from the statistics, not from a world built to fit.** The
  number of live endpoints each window should miss, predicted by exp(-rate x days),
  matches the number measured to within sampling noise: 49.0/49, 19.7/23, 11.2/14,
  1.9/4, 0.1/1.
- **90 days is not a guarantee of zero.** At 90 days one live endpoint in 49 still
  slipped past the shadow (0.1 expected). The 5% canary caught it and the
  controller rolled back automatically, after one real request had been refused. The
  shadow is the main defence; the canary is the backstop it was designed to be.
- It does **not** say Safe Kill catches callers rarer than monthly. A quarterly or
  annual job needs a longer window (`--slowest-caller-days 90` gives 270 days) or a
  business-calendar check. The guarantee is exactly as strong as that parameter.

```bash
apix safekill --evaluate     # reproduces this table
```

### See it decide

```bash
apix safekill                                   # shadows everything, removes nothing
apix safekill --approve-as shivansh             # 7 retired, 1 declined, 0 requests refused
apix safekill "GET /v1/cards/{id}/pin" --approve-as shivansh --hidden-caller "GET /v1/cards/{id}/pin"
```

The last one injects, on the world's side only, a month-end batch job the traffic
capture never saw. The controller has to discover it, and the 90-day shadow names it
three times and rejects the removal with nothing refused. Shorten the window with
`--slowest-caller-days 3` and the same scenario either rolls back automatically after
refusing a real request (`--seed 3`) or retires the endpoint into an outage
(`--seed 1`): at that window, 15 runs in 40.

### The one case automation cannot settle

`POST /v1/debug/payments/replay` is the most dangerous endpoint in the estate:
unauthenticated, able to replay financial transactions, and receiving three anonymous
requests a day. Safe Kill will never remove it. On an unauthenticated endpoint a
forgotten partner integration and an attacker's scanner are indistinguishable on the
wire, so no person can know what they would be accepting: approval is refused, by the
controller, the API and the dashboard alike, and the only decision left is to
decline. The way forward is the recommendation that comes with it: put
authentication in front of the endpoint and re-run the shadow, and legitimate callers
will identify themselves. (An earlier version let an approver tick "accept the risk",
and the endpoint was retired; that override is gone.)

### The audit log

Each entry carries the SHA-256 of its canonical content and of the entry before it.
Editing, deleting or reordering any entry breaks every hash after it.

```bash
apix safekill --verify data/safekill-audit.jsonl
```

This makes tampering detectable, not impossible: whoever can rewrite the whole file
can recompute the whole chain. The deployment answer is to anchor the latest hash
somewhere the operator cannot write (a WORM bucket, the bank's SIEM), and the chain is
what makes that one anchor vouch for every entry before it.

### Boundaries

The controller never sees the simulated world. It is forbidden from importing it, by
the same AST guard that protects the classifier, and learns about traffic only through
an `EnforcementBackend` protocol that a real gateway plugin (a Kong or Envoy filter
answering 410 Gone) would implement identically. The simulated gateway's world model is
stated as assumptions in `simulated_env/enforcement.py`, and a test asserts it never
reads the answer key. Breaches are evaluated at the end of each window, so refused
request counts are upper bounds on what a streaming detector would allow.

---

## REST API

```bash
pip install -e ".[api]"
apix serve                       # http://127.0.0.1:8600, docs at /docs
```

With no tokens configured, `apix serve` mints a one-time approver token for this
process and prints it once, the way Jupyter does, rather than starting open. For
named principals:

```bash
apix token alice --role approver   # prints the token once, and its config entry
export APIX_API_TOKENS="alice:approver:<sha256>;bob:viewer:<sha256>"
```

| Route | Role | What it returns |
|---|---|---|
| `GET /v1/health` | none | status and version, nothing about the estate |
| `GET /v1/summary` | viewer | counts, scan time, and the simulated-mode notice |
| `GET /v1/inventory`, `/v1/verdicts`, `/v1/impact`, `/v1/benchmark` | viewer | what the CLI prints, as JSON |
| `GET /v1/safekill`, `/v1/audit`, `/v1/audit/verify` | viewer | Safe Kill state, the audit chain, its verification |
| `POST /v1/safekill/shadow` | approver | run the gate and the shadow window for one candidate |
| `POST /v1/safekill/decision` | approver | approve or decline; the canary and rollback follow |
| `POST /v1/demo/rescan` | approver | re-run discovery on the demo bank |
| `GET /v1/capabilities` | viewer | which scan inputs work on this machine, and why not |
| `POST /v1/scans/upload`, `POST /v1/scans/github` | approver | start a scan of an uploaded folder or a GitHub link |
| `GET /v1/scans`, `GET /v1/scans/{id}` | viewer | every scan; one scan's progress, then its report and decisions |
| `GET /v1/scans/{id}/audit` | viewer | that scan's hash-chained audit log |
| `GET /v1/demo/graph` | viewer | the demo bank's dependency graph, from traffic (a scan's is in its report) |
| `POST /v1/scans/{id}/review` | approver | record a decision about an endpoint the scan found |
| `GET /metrics` | viewer | Prometheus text format: requests, latency, auth failures, estate gauges |

Four decisions, each made for a security reason:

- **Every route but `/v1/health` needs a token, reads included.** The inventory is
  a map of an estate's weakest points: which endpoints are unauthenticated, which
  nobody owns. A test reads the routes from the application itself, so a route
  added later without authentication fails the build the moment it exists.
- **The approver's name comes from their token, never the request.** Request
  bodies reject unknown fields, so there is no `approver` field to forge, and the
  audit log credits the person who actually holds the token.
- **Tokens are stored only as SHA-256 hashes**, so the configuration is not a
  secret. They are 256-bit random values, so no slow hash is needed.
- **Unidentified traffic can never be approved.** An approval over it returns 409
  with the advice, and the decision stays open so the person can decline; there is no
  field to accept the risk, and sending one is rejected.

`apix serve` binds to localhost and refuses any other address without
`--allow-remote`, because bearer tokens over plain HTTP travel in cleartext. Every
response carries `Cache-Control: no-store`.

The approval flow was the one change Safe Kill needed: in a real deployment the
shadow runs for weeks and a person decides afterwards, so the controller now
stops at the approval gate (`begin`) and continues later (`resolve`). The split
is behaviour-preserving: the same run writes a byte-identical audit chain.

---

## Enforcement in CI (Phase 6)

Detection and Safe Kill deal with zombies that already exist. Enforcement stops
new ones being made. It runs on a pull request and judges **only what that change
does** to the API surface:

| Rule | Fails when the change | Default |
|---|---|---|
| Undocumented endpoint | adds a route with no OpenAPI entry: a shadow API from its first commit | error |
| Unowned endpoint | adds a route no CODEOWNERS entry and no `x-owner` covers | error |
| Zombie in the making | removes an endpoint from the spec but leaves its handler in the code | error |
| Documented, not implemented | adds a spec entry with no handler behind it | warning |

The third rule is the one specific to this project. Every zombie in the simulated
estate was made the same way: the route was removed from the specification and the
handler was never deleted. Enforcement catches that at the commit that does it.

Four decisions make it adoptable, and hard to talk your way past:

- **Existing debt is never held against a change.** An estate with four hundred
  undocumented endpoints can turn this on today; from then on it cannot gain a
  four hundred and first.
- **The comparison is against the merge base**, not the tip of `main`, so work
  merged elsewhere after the branch was cut is not blamed on this pull request.
- **No endpoint is ever called dead.** A code change carries no evidence about
  traffic, so enforcement makes no lifecycle claim, for the same reason a
  repository scan abstains from one.
- **A change cannot exempt itself.** `.apix.yml` is read from the merge base,
  not from the pull request. Read from the head, one innocuous line in the same
  pull request would exempt the endpoint it adds. An edit to the policy is
  reported and applies once it has merged, reviewed like any other code.

OpenAPI tags are deliberately not read as owners: they name functional groups, and
treating them as teams would let nearly any tagged endpoint pass. Every exemption in
`.apix.yml` must carry a reason, because a silenced check is a decision an auditor
will later ask about.

```yaml
# .github/workflows/api-surface.yml in the repository being protected
on: pull_request                  # never pull_request_target: see below
permissions:
  contents: read                  # it reads code and writes annotations, nothing else
jobs:
  api-surface:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
        with: { fetch-depth: 0 }      # the merge base must be present
      - uses: shivanshjindal28/api-exorcist@main   # pin to a commit SHA in production
```

```yaml
# .apix.yml (optional; with no file every rule runs at its default)
enforce:
  rules:
    spec-without-handler: off
  allow:
    - endpoint: "GET /healthz"
      reason: "load-balancer probe; infrastructure, not an API"
```

Findings appear as annotations on the exact lines of the pull request, with a
summary table on the run page. Locally, or in any other CI:

```bash
apix enforce --base origin/main                  # exit 0 pass, 1 findings, 2 cannot run
python demo/make_enforce_demo.py demo/enforce-demo && apix enforce --repo demo/enforce-demo --base main
```

Route strings come from the pull request, whose author is untrusted in CI, so the
output cannot be used to forge annotations: workflow-command data is escaped, and
the readable report is wrapped in `::stop-commands::` with an unpredictable token.
The action passes its inputs to the shell through environment variables, never by
interpolating them into the script, and installs exact scanner versions from
`action-constraints.txt` rather than whatever PyPI served that hour.

Two things the action cannot protect against on its own, because they are
repository settings: run it on `pull_request`, never `pull_request_target`
(which grants a fork's code the base repository's secrets and write token), and
make the check required with CODEOWNERS covering `.github/` and `.apix.yml`. On
`pull_request`, GitHub runs the workflow as the pull request has it, so a
change could edit the workflow itself; review of those paths is what closes that.

---

## Scanning a project in the browser

The app opens on the **Dashboard**: every project's latest scan, the estate's
totals, and the endpoints to look at first across all of them. **New scan** has
three ways in:

| Input | What happens | Needs |
|---|---|---|
| **Upload a project folder** | Pick the project's top folder. Dependency and build folders (`node_modules`, `.git`, `dist`...), images and files over 2 MB are left out in the browser, and the page says how many and why. The rest is copied to a temporary folder, scanned, and deleted. | Semgrep |
| **Paste a GitHub link** | Any form: `https://github.com/owner/repo`, with `.git` or a `/tree/...` path, or just `owner/repo`. The repository is downloaded with its commit history. Public repositories only; a private or missing one fails at once with that reason. | git, Semgrep |
| **Scan a live website** | Shown, but not available in this version; the page says so. | |

A scan runs in the background and its page shows each stage as it happens.
GitHub scans take ten seconds to a couple of minutes, mostly downloading. The
report has four parts:

- **Headline counts**: endpoints found, undocumented, without an owner, unchanged
  for over a year, deprecated in the specification.
- **What was checked**: every stage, marked *worked*, *partly*, *not available* or
  *failed*, each with its reason. For example: an uploaded folder has no git
  history, so staleness is "unknown", never zero; no `CODEOWNERS` file means no
  endpoint has an owner; routes mounted under `prefix=settings.API_V1_STR` are shown
  without that prefix, because its value is only known by running the project.
- **True of the whole project**: findings every endpoint shares, listed once.
- **Endpoints**: method and path, file and line, documented or not, owner, when the
  code last changed, and the findings behind each. Download the report as JSON.

No endpoint in a project scan is called a zombie. Active, deprecated, orphaned
and zombie are all defined by *use*, and a project's files cannot show use; the
report says this rather than guessing. The **Demo bank** pages show the full
classification and Safe Kill on the simulated estate, where usage data exists.

### What a scan concludes on real code: zombie candidates

A repository holds no traffic, so it cannot prove an endpoint is dead. It does
hold evidence that one is, and every report now opens with the endpoints that
evidence points at, ranked, each with the sentences behind its score:

| Signal | Weight | Real example |
|---|---|---|
| A newer version of the same operation exists | +3 | crAPI: `POST /identity/api/auth/v2/check-otp` beside `v3` |
| ...and the project's own client calls only the newer one | +2 | crAPI's web app calls `v3/check-otp`, never `v2` |
| Marked deprecated in the specification or the code (`@Deprecated`, `deprecated=True`) | +3 | |
| The project's own clients use its neighbours but not it (front end, generated SDK) | +2 | the FastAPI template's React app never calls `readItem()` |
| A debug or test endpoint shipped in the API | +2 | VAmPI: `/users/v1/_debug`, `/createdb` |
| Undocumented while the specification documents its neighbours | +2 | crAPI: `POST /identity/management/admin/lockUser` |
| An internal endpoint a public gateway route also matches | +1 | |
| Unchanged for a year while the rest of the project changes | +1 | |
| Referenced by a client, or called by another service | -2 | |

A score of 2 makes an endpoint a candidate; "Likely zombie" needs 4 and a
newer version, a deprecation, or no client use of an endpoint frozen for a year.
Every candidate is labelled suspected, not proven: confirming one takes usage
data, which is what Safe Kill's shadow window collects before anything is
removed. Health probes, metrics, token-key and documentation endpoints are never
candidates, and neither are admin endpoints merely because a front end does not
call them.

Measured on eight public repositories (`tests/test_realworld.py` checks the
first four and idurar, and asserts what must not be flagged):

| Repository | Endpoints | Candidates | What the top of the list says |
|---|---|---|---|
| OWASP crAPI | 62 | 6 | the two insecure old versions it deliberately keeps beside their fixes, `v2/check-otp` and `v2.7/user/login-with-token` (the pattern OWASP API9 describes), ranked first, as likely zombies |
| VAmPI | 14 | 2 | `/users/v1/_debug` and `/createdb` |
| spring-petclinic-rest | 38 | 3 | `GET /owners` and `GET /pets`, superseded by their v2 |
| full-stack-fastapi-template | 23 | 6 | the six endpoints its generated client has but its front end never calls |
| spring-petclinic-microservices | 16 | 0 | |
| node-express-realworld-example-app | 20 | 0 | |
| digital-banking-platform | 27 | 0 | |
| idurar-erp-crm | 33 | 0 | its React app does call these, but as `entity + '/create'`, which the client reader does not follow yet |

The last four hold no evidence that tells their endpoints apart: no versions,
no deprecations, no specification, and (for the first three) no front end that
covers their services. The report says exactly that, and says what would.
idurar first came out with **0 endpoints**: every route is written in Express's
chained `router.route('/x').get(h)` form, its CRUD routes are template literals
built in a loop, and its routers are mounted from `app.js` through `require()`.
None of the three was read. All 33 are now found under `/api`, `/download` and
`/public`. Before this, every one of
the seven reported the same thing about every endpoint; the same testing also
fixed clone failures on Windows long paths, handlers wired by an OpenAPI
`operationId` (Connexion, API-first code generation) going unseen, OpenAPI tags
read as owners, prefixes set by a variable left unresolved, and a route split in
two because code and specification named its parameter differently.

**Why use this rather than Semgrep alone?** Semgrep is one sensor inside API
Exorcist: it answers "where are the routes?". API Exorcist answers "which of
them are dead or dangerous, how sure are we, and is it safe to remove them?",
by combining what no single tool holds (code, specification, version structure,
the project's own clients, history and the service dependency graph) and then
carrying a removal through review, an audit trail and pull-request enforcement.

### Proving it: usage evidence from access logs

A candidate is suspected. To prove an endpoint dead takes usage, and every bank
already records it: the access logs of its gateway or load balancer. On a scan's
**Usage** view, upload them (several files, gzip-rotated ones included) and every
endpoint is classified by the same four definitions the demo bank uses.

| Read | Formats |
|---|---|
| Line formats | nginx and Apache `combined`/`common`; AWS Application Load Balancer |
| JSON lines | Kong, AWS API Gateway, Envoy, Traefik, or any gateway whose field names are recognisable |

Each request is matched to the endpoint whose route template it fits, the most
literal first (`/users/me` before `/users/{id}`), and a gateway prefix the code
never sees (`/api/...`) is found and reported. Three rules keep "no traffic" from
being over-read, because a false ZOMBIE is an outage:

1. **Absence counts only where the logs cover the service.** If a service has no
   request at all, the logs come from somewhere else; nothing in it is called
   unused, and the page names the service.
2. **The window must be long enough.** Under seven days nothing is a zombie. Over
   it, the rule of three bounds what was missed: no call in *W* days means, at 95%
   confidence, fewer than one call every *W*/3 days, and the page says so per endpoint.
3. **Failed requests are not use.** An endpoint that only ever answered 401, 403 or
   404 has someone probing it, which is attack surface, not a customer.

Requests that fit no endpoint in the code are listed as **traffic the code does
not explain** (a shadow API served by something else) or, if they only failed,
as **probing**. Logs are the most sensitive file anyone will hand this tool, so
query strings (tokens, account numbers, OTPs) are dropped as each line is read,
and client addresses become salted hashes used only to count distinct clients;
the salt is random per import and never stored. The import is written to the
scan's audit chain with a SHA-256 fingerprint of its result.

**On public repositories this cannot be shown on real traffic**: no public project
publishes its production logs. `demo/make_access_log.py` writes a log for a scan
that says it is synthetic three ways (its first line, its RFC 5737 documentation
addresses, and the file name you give it). On crAPI it leaves the two likely
zombies without a successful request and has one address brute-force the old OTP
check; the import then labels exactly those two ZOMBIE, with the reason.

### Retirement plans, exports and drift

- **Retirement plans** (Safe Kill view): for every endpoint the logs prove unused,
  or every likely zombie before logs exist, a four-step plan with the gateway
  configuration written out: announce with `Deprecation` and `Sunset` headers
  (RFC 9745, RFC 8594), watch 90 days of fresh logs, answer `410 Gone` reversibly,
  then delete the handler (file and line given) and its specification entry
  together. A plan states what blocks it: use in the logs, no usage evidence, or
  no owning team.
- **Exports**: SARIF 2.1.0 for GitHub code scanning and most security dashboards,
  an inventory CSV for a spreadsheet or a GRC tool (formula-like values defused),
  an OpenAPI 3.1 skeleton of every undocumented endpoint so "needs documentation"
  starts half done, and a printable **executive report** with priority actions,
  coverage, and the audit chain's state.
- **Drift**: each GitHub scan is compared with the previous scan of the same
  repository: endpoints added, removed, newly undocumented, new candidates. When
  both scans read the same commit, the page says the differences are the
  scanner's, not the project's.
- **Priority**: every endpoint carries a data category read from its path
  (authentication, payments, cards, identity and KYC, administration, accounts,
  personal data) and a priority that weights the evidence against it by what it
  handles. The category is a heuristic and is labelled one: it orders the queue,
  it never decides a removal.

### Every scan has the same views

A finished scan, and the demo bank, open on the same tabs; a project scan adds
**Usage**. Without imported logs each view shows what can honestly be shown from
code alone:

| View | On a project scan |
|---|---|
| Overview | Headline counts, usage summary, zombie candidates, exposure by data category, changes since the previous scan, what was checked and why |
| Endpoints | List and detail, ordered by priority: where each endpoint is defined, what it handles, which sources saw it, its usage, its findings, its decision |
| Usage | Import access logs; lifecycle from real usage, per-endpoint requests, clients and trend, traffic the code does not explain, probing |
| Dependency graph | Services as boxes listing their endpoints, drawn in columns by dependency depth; calls, gateway routes and message topics as arrows. Click an endpoint for its blast radius, with the file and line behind every caller |
| Safe Kill | Which of removal's four prerequisites the scan has and lacks, **retirement plans**, then a **review queue**: keep, needs documentation, needs an owner, or investigate for removal, recorded under the reviewer's name |
| Audit log | The scan's own hash-chained log: who started it, a SHA-256 fingerprint of its report, every decision since; verifiable in one click |
| Benchmark | What a documentation-only inventory would have listed against what the scan found. Coverage, not accuracy: a real project has no answer key, and the page says so |

**The dependency graph of a project is read from its code** (`apix/live/deps.py`):
HTTP client calls between services (Spring RestClient, WebClient, RestTemplate and
Feign; fetch and axios; Python requests and httpx), gateway routes (Spring Cloud
Gateway), and Kafka and RabbitMQ topics. Only calls feed the blast radius: a gateway
route exposes endpoints rather than depending on one, and a topic links services,
not endpoints. Test code is left out, since a call in a test is not a production
dependency. On the Spring banking repository that prompted it, the graph shows
`transaction-service` calling `account-service`'s internal debit and credit
endpoints, so removing either would break five transaction endpoints, and it notes
that the public `/api/accounts/**` gateway route also matches them. The page says
plainly that this is what the code *can* call: callers outside the repository, and
URLs built at run time, do not appear. The demo bank's graph is drawn from
observed traffic instead, and says so.

Nothing is removed from a project scan. Removing an endpoint on the strength of
its code alone is how outages happen; the code cannot show the month-end batch job
that still calls it. **Run the demo** on New scan opens the simulated bank, where
traffic and a gateway exist, with the full classification and Safe Kill.

Reports are kept in `data/scans/` and listed under **Projects**. Nothing from a
scanned project is ever run: routes are read by static analysis and
specifications are parsed as data. Uploaded file names that could point outside
the upload (`../../x`, absolute paths, drive letters) are refused.

---

## Dashboard

`apix serve` opens the dashboard at `http://127.0.0.1:8600/`, signed in. The
one-time token it mints is handed to the browser in the URL *fragment*
(`#signin=...`), which browsers never send to a server or put in a Referer
header; the page reads it and erases it from the address bar and history at once.
With `--no-browser`, or with configured tokens, sign in by pasting a token. If
port 8600 is taken (an earlier `apix serve` still running, say), it uses the next
free one and says so.

The demo bank opens from **Run the demo** on New scan, as a scan with the same
five views:

| View | What it shows |
|---|---|
| Overview | Counts by label, what the removal gate cleared, what awaits a decision |
| Endpoints | Every endpoint, filterable; per verdict, the signed evidence that produced it, which of the six sources saw it, its flags, its blast radius |
| Safe Kill | Start a shadow, see its evidence, approve or decline; the full path of every decision |
| Audit log | Every transition, its actor and hash; recompute the whole chain in one click |
| Benchmark | The before/after comparison |

React and TypeScript, as the design document specifies, with React as the only
runtime dependency: no UI kit, so there is little to audit and little the team
cannot explain. The production build is **committed into the Python package**, so
`pip install` and `apix serve` give a working dashboard on a machine with no Node
at all; CI rebuilds it and fails if the committed output differs from the source.

Security, in the browser as on the server:

- **Same origin as the API**, so there is no CORS to configure or get wrong.
- **A strict Content-Security-Policy**: scripts, styles and connections from this
  origin only, and no inline script anywhere in the build. A stored token is only
  as safe as the page holding it.
- **The token lives in `sessionStorage`**, gone when the tab closes, sent only in
  the `Authorization` header, never in a URL.
- **The approve button is disabled over unidentified traffic**, with the advice
  beside it, mirroring the server's rule. The server remains the authority; the UI
  only saves a round trip.
- **Viewers see every decision and no way to make one.**

```bash
cd dashboard && npm ci && npm run dev      # hot-reload against a running `apix serve`
npm test && npm run build                  # 48 Vitest tests; build into src/apix/api/dashboard
```

---

## Deployment and operations (Phases 7 and 8)

```bash
docker build -t api-exorcist .
docker run --rm api-exorcist token ops --role approver     # prints a token and its entry
docker run -d --name apix -p 127.0.0.1:8600:8600 \
  -e APIX_API_TOKENS='ops:approver:<sha256>' \
  -v apix-data:/data --read-only --tmpfs /tmp \
  --cap-drop ALL --security-opt no-new-privileges api-exorcist
```

The image is 53 MB and serves the API and the dashboard. What it does, and why:

| Property | Why |
|---|---|
| Base image pinned by digest | A rebuild cannot silently pick up a different Python |
| Two-stage build; no compiler, source tree or pip in the runtime image | pip-audit found known vulnerabilities only in the base image's own pip, which the server never uses |
| Runs as uid 10001; works with a read-only root filesystem | The only writable path is `/data`, the audit log |
| Refuses to start without `APIX_API_TOKENS` | On a served bind, a one-time token printed to stdout lands in retained log storage |
| JSON logs, no Swagger pages, no `Server` header | Logs a SIEM ingests without a parser; Swagger loads scripts from a CDN |
| Health check on `/v1/health` | The orchestrator restarts it; the route says nothing about the estate |

A CI job builds the image and runs it exactly as above: it must become healthy,
refuse an anonymous read, serve metrics to a token, keep the token out of its
logs, and contain no pip.

**TLS is the proxy's job.** Publish the port on 127.0.0.1, or put the container
behind a TLS-terminating proxy or ingress. Bearer tokens over plain HTTP travel
in cleartext, which is why `apix serve` refuses a non-loopback bind unless told
`--allow-remote`.

### Metrics

`GET /metrics` is Prometheus text format, written by hand rather than through a
client library: one fewer dependency for a bank's software review to clear.

| Metric | What it answers |
|---|---|
| `apix_http_requests_total`, `apix_http_request_duration_seconds` | Traffic and latency, by route template |
| `apix_auth_failures_total{reason}` | Missing, unrecognised or under-privileged credentials. A rising rate is someone guessing |
| `apix_safekill_actions_total{kind,result}` | Shadows started; decisions approved, declined or refused |
| `apix_endpoints{label}`, `apix_removal_candidates`, `apix_cleared_by_gate` | The estate, as the last scan saw it |
| `apix_safekill_awaiting_approval` | Removals waiting on a person |
| `apix_audit_entries`, `apix_audit_chain_ok` | Whether the audit chain still verifies: alert on 0 |

It needs a token like every other route, because a scrape is a summary of an
estate's weak points; Prometheus sends one natively
(`authorization: {credentials_file: ...}`). Requests are labelled by **route
template, never raw path**: endpoint ids appear in URLs, and labelling by path
would let any client create a new time series per request until the process ran
out of memory. A test sends random paths and checks none of them appears.

### Logs

`--log-format json` (the image's default) writes one object per line: an access
line per request with its route template, status, duration, request id and the
**principal's name**, plus an event for each Safe Kill action. The token never
appears, and neither does a request body, which can carry an approver's note;
tests check both. Every response carries an `X-Request-ID`, echoed from the
client when it is well formed, so one failed approval can be followed from the
browser to the log line to the audit entry.

### The audit log under concurrent writers

The CLI, the API and any second process can now append to one audit file at the
same instant. Each append takes an exclusive lock on a sidecar file, re-reads the
head under it, writes and fsyncs before releasing. A test starts four writer
processes appending 25 entries each at once: on the unlocked code the chain
broke within its first 25 entries in two runs of three; with the lock, all 100
entries verify, every run.

### Security review: what it found

| Finding | Severity | Fixed by |
|---|---|---|
| A pull request could exempt its own endpoint by adding it to `.apix.yml` in the same change | High | The policy is read from the merge base; an edit is reported, applied after merge |
| Two simultaneous audit writers forked the hash chain | High | Cross-process lock and fsync per append |
| `apix serve` on a served bind would print a one-time token into container logs | Medium | Refuses; configured tokens are required off loopback |
| GitHub Actions referenced by movable tags; scanner installed at whatever version PyPI had | Medium | Actions pinned to commit SHAs; exact scanner versions in `action-constraints.txt` |
| pip in the runtime image carried known vulnerabilities | Low | Removed from the image |
| Request bodies had no size limit | Low | 64 KiB cap; a body without a length is refused |

Checked and found sound: token comparison is constant time over every stored
digest; every route but `/v1/health` needs a token, including `/metrics`
(the route-coverage test found it on its own); error messages echo endpoint ids
only inside JSON, under a CSP with no inline script.

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
| macro-F1 | 0.843 | 0.861 |
| ZOMBIE false positives | 14 | **0** |
| DEPRECATED F1 | 0.681 | 0.587 |

**Aggregate: the model is slightly ahead, on one split.** But the average hides what
matters — the rules produce 14 false zombies on unseen estates and the model produces
none. A false zombie
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
4. **Repository scans make lifecycle claims only from imported access logs.** From
   code alone they rank candidates and never label one a zombie. Enforced, not advisory.
5. **Router mount prefixes held in variables resolve only when the project spells
   the value out.** `prefix=settings.API_V1_STR` is applied when `API_V1_STR = "/api/v1"`
   appears in the code; general constant resolution is not implemented. Otherwise
   the paths are flagged `prefix_resolved=False` rather than presented as absolute.
6. **Graph isolation means no dependency was *observed*.** A caller silent during the
   capture window is invisible.
7. **The estate is synthetic.** The architecture is not — `apix scan --github` reads
   real repositories.
8. **Safe Kill catches callers no rarer than its window assumes.** The default
   catches a monthly caller with 95% confidence. Quarterly and annual jobs need a
   longer window or a business-calendar check.
9. **Safe Kill's traffic is simulated.** The controller and the protocol are real;
   the gateway behind them is a model whose assumptions are written down in
   `simulated_env/enforcement.py`. A real deployment replaces it with a gateway
   plugin.
10. **The API holds pending approvals in memory, so it runs as one replica.**
    Restarting it forgets a candidate awaiting a decision, and its shadow must
    run again. That can only delay a removal, never cause one. The audit log is
    safe to share between concurrent writers (it is locked); the approval queue
    is not yet, and needs a database before a second replica.
11. **Enforcement sees only what route extraction sees.** A framework the
    Semgrep rules do not cover is invisible to it, which is why a spec entry
    with no handler is only a warning by default.
12. **The audit chain proves tampering only with its head anchored elsewhere.**
    Someone who can rewrite the whole file can recompute the whole chain.
    `apix_audit_chain_ok` catches an edit, not a rewrite; the deployment answer
    is to ship the head hash to a store the operator does not control.
13. **Candidates from code are suspected, not proven.** Use by callers outside
    the repository cannot be seen, and a gateway that rewrites paths (Spring
    Cloud Gateway's StripPrefix) can hide a front end's calls; coverage below 30%
    therefore never counts as evidence of non-use. Django and Go routes are not
    extracted yet, so their endpoints are seen only through the specification.
14. **Live website scanning is not available in this version.** The app shows
    the option and says so; scan the project's folder or repository instead.
15. **An uploaded folder has no history.** `.git` is left out of uploads, so
    staleness is reported as unknown. A GitHub scan includes it.
16. **Access logs see only the traffic that passes where they are written.** A
    service called directly by another service, bypassing the gateway, has no
    lines in the gateway's log. That is why absence counts only for services the
    logs demonstrably cover, and why the code's dependency graph still gates
    removal; importing the internal load balancer's logs as well closes it.
17. **Owners come from CODEOWNERS and `x-owner` in the specification only.** A
    repository with neither shows every endpoint in use as ORPHANED, which is
    correct by the definition and says what to fix, but is noisy until it is fixed.
18. **Data categories are read from path words.** A heuristic, labelled as one: it
    orders the queue and never decides a removal.
19. **The container image has neither git nor Semgrep.** Scans started inside it
    report both as unavailable, with the reason; install them, or run the app
    directly, to scan.
20. **The client reader matches path strings, not call sites.** In a framework
    whose routes are not extracted (Go, Django), the file that declares a route
    also mentions its path, and is counted as a reference to it. That can only
    lower a candidate's score, never raise one, so it errs toward keeping an
    endpoint.

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
    view.py                The graph as something to draw: one shape for traffic and code
  api/
    auth.py                Bearer tokens, stored hashed; viewer and approver roles
    workspace.py           The served state: a scan, its gate, a Safe Kill controller
    app.py                 FastAPI routes over the workspace; limits, request ids
    observe.py             Prometheus metrics and JSON logs, no client library
  scanning/
    jobs.py                Background scans, GitHub link parsing, kept reports
    report.py              One report shape: counts, what was checked and why, endpoints
    upload.py              Saving an uploaded folder without letting a name escape it
    sensitivity.py         What an endpoint handles, from its path; priority
    retire.py              Retirement plans: Deprecation/Sunset, 90-day watch, 410, removal
    exports.py             SARIF 2.1.0, inventory CSV, OpenAPI stubs
    compare.py             Drift between two scans of the same repository
  traffic/
    logs.py                nginx/Apache, AWS ALB and JSON-lines gateway logs; no query strings, hashed clients
    usage.py               Request to endpoint, then the four lifecycle labels from real use
  enforce/
    config.py              Rules, severities, and exemptions that must give a reason
    snapshot.py            One commit's API surface: routes, spec entries, owners
    check.py               The four rules, applied only to what the change touches
    runner.py              Merge base, temporary worktree, the two snapshots
    report.py              Text, JSON, GitHub annotations; injection-safe
  safekill/
    states.py              The design's state machine; illegal moves raise
    policy.py              Rule-of-three shadow window, breach criteria
    backend.py             EnforcementBackend: what a gateway plugin implements
    controller.py          Shadow, approval, canary, automatic rollback
    audit.py               Append-only, hash-chained audit log
  extractors/
    base.py                ExtractedRoute, path normalisation across frameworks
    semgrep_extractor.py   AST route extraction; router prefix composition
    rules/routes.yaml      Semgrep rules: FastAPI, Flask, Express, Spring
  live/
    deps.py                Calls, gateway routes and topics between services, read from code
    repo.py                Clone a repository; git-history staleness, CODEOWNERS
    connectors.py          CODE / OPENAPI / CICD read from a real checkout
    scan.py                Orchestrates a repository scan
  evaluation/
    metrics.py             Precision, recall, F1, confusion matrix
    benchmark.py           The comparative before/after study
    train.py               Model training and the honest rules-vs-model report
    safekill_eval.py       Safe Kill against the gate alone; the shadow sweep
  dataset/build.py         Feature extraction + labelled dataset
  simulated_env/
    estate.py              The estate and its ground truth (the answer key)
    generator.py           Parameterised estates, generated by mechanism
    enforcement.py         Simulated gateway for Safe Kill; its world model

dashboard/                 React + TypeScript source; builds into src/apix/api/dashboard
Dockerfile                 The deployable image: API and dashboard, non-root, read-only
action.yml                 The GitHub Action; action-constraints.txt pins what it installs
tests/                     299 tests, three ground-truth leakage guards
demo/                      Review runbook, paced demo runner, expected output
docs/                      Literature review, design document, interim report,
                           source papers, diagram renderer, Word and
                           PowerPoint builders, claims verifier
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

**299 tests**, ruff clean, mypy `--strict` clean. The dashboard adds 48 Vitest
tests under TypeScript strict mode (`cd dashboard && npm test`).

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

Two more jobs run alongside: the dashboard (types, Vitest, and a rebuild that must
match the committed build), and the container image, which is built and run as
deployed and must pass a smoke test.

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
| [`docs/literature-review.md`](docs/literature-review.md) | Twelve peer-reviewed sources, each verified against DBLP or Crossref, with a traceability matrix mapping every paper to the module it justifies |
| [`docs/design-document.md`](docs/design-document.md) | Structural and behavioural design — 10 diagrams, measured results, known design limitations |
| [`docs/interim-report.md`](docs/interim-report.md) | Interim report, Chapters 1–3 — introduction, literature survey, methodology and implementation, in the prescribed submission format |
| [`docs/final-report.md`](docs/final-report.md) | Final report (black book), Chapters 1–6, references and appendices, in the prescribed format; `python docs/build_docx.py final` builds it |
| [`docs/build_pptx.py`](docs/build_pptx.py) | Generates the review presentation from the same verified figures |
| [`docs/build_logbook.py`](docs/build_logbook.py) | Generates the capstone log book, week by week |
| [`docs/papers/README.md`](docs/papers/README.md) | The source PDFs and their full-text verification status |
| [`demo/DEMO.md`](demo/DEMO.md) | Presentation runbook: the browser walkthrough, anticipated questions, fallbacks |
| [`CLAUDE.md`](CLAUDE.md) | Working notes: the non-negotiable rules and environment gotchas |

Nine of the twelve paper PDFs are present; five have been checked against their full
text. **That checking mattered:** one paper turned out not to contain a result the
review had attributed to it, and the claim was removed rather than softened.

---

## Team

Group 4, B.Tech CSE (Cyber Security), MPSTME, NMIMS University, Mumbai.

- **Nakul Hintya**
- **Shivansh Rohit Jindal**
- **Dhyey Kharayat**

Mentor: **Dr. Pintu R Shah**, Head of Department, Computer Science & Engineering
(Cyber Security), MPSTME.

---

## Licence

MIT — see [LICENSE](LICENSE).
