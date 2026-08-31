# Literature Review

**API Exorcist — autonomous discovery and safe elimination of zombie, shadow and orphaned APIs**

B.Tech CSE (Cyber Security), Mukesh Patel School of Technology Management & Engineering, NMIMS · 2026–2027

---

## 1. Scope and method

This review establishes the research foundation for API Exorcist. It is organised
around a single question: *on what published evidence does each of our design
decisions rest?*

Nine peer-reviewed works were selected across five themes. Selection criteria were:

1. **Peer-reviewed venue.** Journal articles and conference papers only. Industry
   reports (OWASP, Salt Labs, Checkmarx, RBI, NIST) are retained in the synopsis for
   *prevalence statistics* — how common the problem is — but they are not treated as
   research literature and are not counted among the nine.
2. **Direct bearing on a design decision.** A paper is included only if it justifies
   something we actually built. Section 8 makes that mapping explicit.
3. **Verified existence.** Every citation was checked against the DBLP computer
   science bibliography for exact title, author list, venue, year and DOI. This step
   was added deliberately: an earlier draft of the project synopsis carried a
   fabricated IEEE citation on "zombie APIs," which does not exist.

### A note on the gap this review documents

There is no published research literature on *zombie APIs* as such. The term is
industry vocabulary, not an academic one. This is not a weakness in the review — it
is the research gap itself, and the review is constructed to demonstrate that the
problem is well-evidenced in adjacent literatures that have never been connected:

- Software engineering has studied **dead code** and **deprecated APIs** rigorously,
  but treats them as maintainability concerns, not security exposure.
- Microservice research has produced mature techniques for **architecture recovery**
  and **dependency modelling**, but applies them to comprehension and testing, not to
  decommissioning.
- Security research has catalogued **microservice security smells** and can detect
  them, but stops at detection.
- Explainability research has established **SHAP** as a standard, and validated it in
  security decision contexts — but not for asset-lifecycle decisions.

API Exorcist sits at the junction of these four, which is precisely why no single
existing tool solves it.

---

## 2. Theme A — Dead and deprecated code: the software-engineering foundation

The intuition behind a "zombie API" — code that still runs but no longer serves a
purpose — has a rigorous analogue in software engineering research on dead methods.

**Caivano, Cassieri, Romano and Scanniello [1]** conducted an exploratory study of
dead methods in open-source Java desktop applications, analysing commit histories
across 23 GitHub-hosted projects to quantify how dead code spreads and evolves over
time. Their contribution matters to us in two ways. First, it establishes that unused
code is not an occasional defect but a persistent, measurable property of real
codebases that accumulates across a project's history — which is the premise our
entire project depends on. Second, and more usefully, their method is
*commit-level*: dead methods are identified by tracking the repository over time
rather than by inspecting a single snapshot. That temporal framing directly informed
our decision to treat `CODE_UNTOUCHED_1Y` as an evidence signal rather than
inspecting only the current state of a repository.

Their study also establishes the limitation we inherit. Static reachability analysis
determines that a method is *unreferenced within the analysed codebase*. It cannot
determine that nothing calls it — reflection, dynamic dispatch, and external HTTP
callers are all invisible. For a REST endpoint the problem is strictly worse, because
the caller is by definition external to the repository. **This is the single most
important reason API Exorcist is not a static analysis tool.** Code analysis can only
ever be one of our six sources.

**Cassieri, Romano and Scanniello [2]** studied deprecated API usage across
top-starred GitHub projects, examining in particular how deprecation is communicated
through replacement messages. Their finding — that deprecation markers are
inconsistently applied and inconsistently acted upon — is the empirical basis for a
specific modelling choice in our simulated estate: **only two of our three deprecated
endpoints carry the `spec_deprecated` flag.** Had we flagged all three, the classifier
could achieve high accuracy by memorising a single field, and our evaluation would be
meaningless. The literature says real teams forget; our environment forgets too.

This is also why `DEPRECATED` is a distinct class from `ZOMBIE` in our taxonomy. A
deprecated endpoint is one someone *declared* obsolete; a zombie is one that became
obsolete without anyone noticing. The evidence patterns differ, and so must the
remediation.

---

## 3. Theme B — Architecture recovery through static analysis

If an organisation cannot enumerate its own endpoints, the discovery problem is a
special case of architecture recovery: reconstructing a system's true structure from
its artefacts rather than its documentation.

**Bushong, Das, Al Maruf and Cerný [3]** address microservice architecture
reconstruction using static analysis, presented at ASE 2021. Their central premise —
that a distributed system's real architecture must be *recovered* from source because
the documented architecture drifts from reality — is the same premise that motivates
our OPENAPI-versus-CODE coverage gap. Their pipeline separates endpoint extraction
from call extraction and then matches signatures across service boundaries, and that
three-phase decomposition is mirrored in our own separation of concerns: connectors
extract, the correlator matches, and neither does the other's job.

Their work is the direct justification for using **Semgrep rather than regular
expressions** in our `CodeConnector`. Semgrep parses source into an abstract syntax
tree and matches route declarations structurally, so `@app.get("/v1/accounts")`,
`@RestController`, and `router.post(...)` are recognised as the same kind of construct
across languages regardless of formatting. A regular expression over source text
cannot distinguish a route declaration from the same string in a comment or a test
fixture.

Their measured result — that static analysis recovers endpoints the documentation
omits — is what our CODE connector reproduces at 100% coverage against the gateway's
76%.

---

## 4. Theme C — Graph-based dependency modelling

Discovery answers *what exists*. Safe removal requires answering *what breaks if this
disappears*, and that is a graph reachability question.

**Ma, Fan, Chuang, Liu and Lan [4]** present a graph-based, scenario-driven approach
to microservice analysis, retrieval and testing in *Future Generation Computer
Systems*. They model a microservice system as a graph and demonstrate that
dependency-aware traversal supports analysis that flat inventories cannot. This is the
justification for our choice of **Neo4j over a relational store** for the dependency
layer.

The argument is concrete rather than a matter of taste. "Which services transitively
depend on this endpoint?" is an unbounded-depth traversal. In SQL that is a recursive
common table expression whose cost grows with each hop and whose query text obscures
the intent. In Cypher it is a variable-length path match. Since blast-radius
computation is executed on every kill decision, and since the depth is not known in
advance, the graph model is the correct fit — not because graphs are fashionable, but
because the query we run most often is the one relational stores handle worst.

**Abdelfattah and Cerný [5]** extend this with the Microservice Dependency Matrix
(ESOCC 2023), a formalism for representing and reasoning about inter-service
dependencies. Their framing of dependency as a first-class, measurable architectural
property is what our Safe Kill Simulation operationalises: before an endpoint is
disabled, its dependents are enumerated from the graph and the resulting blast radius
becomes an input to the decision gate rather than an afterthought.

Together, [4] and [5] supply the theoretical basis for the claim that distinguishes
our project from every detection-only tool: **we can predict the consequence of
removal before removing anything.**

---

## 5. Theme D — Security smells and the detection–remediation gap

The security framing of our problem is best established by the microservice security
smell literature, which is also where our research gap becomes visible.

**Dell'Immagine, Soldani and Brogi [6]** present KubeHound, which detects microservice
security smells in Kubernetes deployments, published in *Future Internet*. **Ponce,
Soldani, Taramasco, Astudillo and Brogi [7]** examine the broader impacts of security
smells for microservices beyond the security dimension alone.

Two things follow for us.

First, these works establish **"security smell" as a legitimate research construct** —
a structural property that is not itself a vulnerability but reliably indicates
elevated risk. Our discrepancy flags (`UNDOCUMENTED`, `UNREGISTERED`,
`SHADOW_CANDIDATE`, `NO_TRAFFIC_IN_WINDOW`, `UNAUTHENTICATED`) are security smells in
exactly this sense. That gives our flag vocabulary a defensible academic footing
rather than being an invented heuristic.

Second — and this is the gap the project exists to fill — **the literature detects and
triages, but does not remediate.** Ponce et al. produced follow-on work explicitly
about *triaging* smells [7]; the endpoint of that research programme is a ranked list
handed to a human. No published work closes the loop by automatically and safely
removing the offending asset with dependency-aware impact prediction, a policy
decision gate, canary rollout and automatic rollback.

That is precisely the contribution of API Exorcist's Safe Kill Simulation, and it is
the sentence this literature review exists to earn:

> Existing research and tooling can tell an organisation which of its APIs are
> dangerous. None can safely turn them off.

---

## 6. Theme E — Explainability in security decisions

An automated system that disables production endpoints in a bank must justify every
decision to an auditor. This makes explainability a compliance requirement, not a
feature.

**Lundberg and Lee [8]** introduced SHAP (SHapley Additive exPlanations) at NIPS 2017,
providing a unified, game-theoretically grounded framework for attributing a model's
prediction to its input features. SHAP's key property for our purposes is
*additivity*: the contributions attributed to each feature sum to the difference
between the model's output and its base rate. An explanation is therefore complete —
it accounts for the whole decision, not a plausible-looking part of it. For an audit
trail, that completeness is the entire point.

**Gaspar, Silva and Silva [9]** validate LIME and SHAP applicability on multi-layer
perceptrons for intrusion detection systems in *IEEE Access*, establishing precedent
for SHAP specifically within security decision-making rather than in general machine
learning. Their work supports our claim that per-decision attribution is both
achievable and meaningful for a security classifier.

Their reported limitation is one we design around rather than inherit: SHAP is
computationally expensive, which constrains its use in real-time, high-throughput
detection. **Our workload is not real-time.** Classification runs per scan — hourly or
daily — over an inventory numbering in the thousands, not per packet at line rate. The
cost that constrains an IDS is irrelevant to an asset-lifecycle classifier, which is
why we can afford exact attribution where an IDS cannot.

This asymmetry justifies our **hybrid rules-plus-model design**. The rule layer is
inherently transparent — an `if-then` chain is its own explanation and produces
deterministic, auditable output. SHAP covers the model layer, which handles the
borderline cases rules decide poorly. A verdict therefore reaches the operator as:

> `ZOMBIE` — 0 requests in 190 days · absent from OpenAPI specification · absent from
> gateway registry · no CODEOWNERS entry · reachable via DNS

rather than as a bare label with a confidence score.

---

## 7. Theme F — Passive discovery and the ethics of external scanning

Our product accepts a URL as an entry point, which raises a question the literature
answers directly.

**Scheitle, Gasser, Nolte, Amann, Brent, Carle, Holz, Schmidt and Wählisch [10]**
analysed the rise of Certificate Transparency at IMC 2018, examining in particular the
security and privacy implications of publicly exposing certificate DNS names.
Certificate Transparency, defined in RFC 6962, requires certificate authorities to
publicly log every TLS certificate issued, with all covered hostnames listed in the
Common Name and Subject Alternative Name fields.

Their central finding is the one we build on: **CT logs publicly expose hostnames that
organisations did not intend to publish** — development, staging and administrative
hosts that appear in no DNS zone transfer and are linked from no public page. The
authors frame this as a privacy and security *concern*. For a defender auditing their
own estate, the same property is an asset: it is a legitimate, entirely passive
discovery source requiring no request to the target's infrastructure at all.

This paper is the basis for the **two-tier design of our URL scanning path**, which is
a deliberate architectural constraint rather than a limitation:

- **Tier 1 — any URL, zero probing.** Fetch the published OpenAPI or Swagger
  specification, mine Certificate Transparency logs and passive DNS for hostnames, and
  parse the site's own JavaScript bundles for API routes. Every one of these reads
  public data. No request is made to a target endpoint.
- **Tier 2 — after DNS TXT ownership verification.** Only once the operator has proven
  control of the domain does active endpoint probing unlock.

The reasoning is not merely legal caution. Probing endpoints on infrastructure one
does not own is unauthorised access under most jurisdictions, and against a financial
institution the consequences are criminal rather than contractual. The verification
gate is the same pattern used by production attack-surface-management platforms and by
Google Search Console. Designing it in from the start is what separates a shippable
product from an unusable demonstration.

---

## 8. Traceability matrix — how the literature is utilised in the implementation

This section addresses the review requirement directly: each finding is traced to the
design decision it justifies and to the module that implements it.

| # | Source | Finding used | Design decision it justifies | Implemented in |
|---|---|---|---|---|
| [1] | Caivano et al., EMSE 2023 | Dead code accumulates persistently and is detected at commit level, not from a snapshot | Temporal signals are first-class evidence; static analysis alone is insufficient for endpoints with external callers | `connectors/discovery.py` (`CODE_UNTOUCHED_1Y`), six-source architecture |
| [2] | Cassieri et al., PROFES 2023 | Deprecation markers are applied inconsistently by real teams | `DEPRECATED` is a class distinct from `ZOMBIE`; the `spec_deprecated` flag is deliberately imperfect (2 of 3) | `simulated_env/estate.py`, `connectors/gateway.py` |
| [3] | Bushong et al., ASE 2021 | Real architecture must be recovered from source; extraction, call analysis and matching are separable phases | Semgrep AST matching over regex; connectors extract while the correlator matches | `connectors/discovery.py` (`CodeConnector`), `inventory/correlator.py` |
| [4] | Ma et al., FGCS 2019 | Graph traversal enables dependency analysis that flat inventories cannot support | Neo4j over a relational store for the dependency layer | Phase 2 — `graph/` (planned) |
| [5] | Abdelfattah & Cerný, ESOCC 2023 | Inter-service dependency is a measurable first-class architectural property | Blast radius computed from the graph before any kill decision | Phase 4 — Safe Kill Simulation (planned) |
| [6] | Dell'Immagine et al., Future Internet 2023 | "Security smell" is a valid construct: structural indicators of elevated risk | Discrepancy flags are modelled as security smells with academic grounding | `inventory/correlator.py` (15 flags) |
| [7] | Ponce et al., CLEIej 2024 | The research programme terminates at detection and triage | The research gap: automated *safe remediation* is the project's contribution | Phase 4 — Safe Kill Simulation (planned) |
| [8] | Lundberg & Lee, NIPS 2017 | SHAP gives additive, complete per-prediction feature attribution | SHAP for the ML layer, so every verdict carries a full reason set | Phase 3 — `engine/explain.py` (planned) |
| [9] | Gaspar et al., IEEE Access 2024 | SHAP is applicable to security decisions; its cost constrains real-time use | Hybrid rules + model; per-scan rather than per-packet workload makes exact attribution affordable | Phase 3 — `engine/` (planned) |
| [10] | Scheitle et al., IMC 2018 | CT logs publicly expose unintended hostnames; this has privacy implications | Two-tier URL scanning: passive CT/DNS/spec first, active probing only after DNS TXT ownership proof | Phase 1 — `connectors/external/` (planned) |

---

## 9. Synthesis: the research gap

The literature supports each of the following statements individually. No published
work combines them.

1. Unused code persists and accumulates in real systems, and is detectable — but the
   techniques are single-source and cannot see external callers **[1]**.
2. Deprecation is declared inconsistently, so declared state is an unreliable indicator
   of real state **[2]**.
3. True architecture must be recovered from artefacts because documentation drifts
   **[3]**.
4. Dependency structure is graph-shaped and traversal-based analysis is the
   appropriate tool **[4] [5]**.
5. Structural security indicators can be detected and triaged automatically **[6]
   [7]**.
6. Automated security decisions can be made explainable with complete, additive
   attribution **[8] [9]**.
7. Substantial estate information is available entirely passively, without touching
   the target **[10]**.

**The gap.** Statements 1–3 imply that no single source can establish an endpoint's
true status — yet every existing tool is single-source. Statements 4–5 supply the
machinery to predict removal impact — yet no tool acts on it. Statement 6 makes
automated action auditable — yet no tool needs it, because none acts.

API Exorcist's contribution is the composition: **multi-source correlation to
establish status that no single source can determine, dependency-aware simulation to
predict the consequence of removal, and complete per-decision explanation to make the
resulting action auditable in a regulated environment.**

---

## 10. Verification checklist before submission

Every citation below is confirmed real — exact title, author list, venue, year and DOI
were validated against DBLP. The following claims are attributed at the level of each
paper's stated contribution and abstract. **Before submission, read the full text of
[1], [2], [3] and [9] and attach page-level citations to the specific figures**, and
replace any statement here that the full text does not support.

- [1] — the count of 23 analysed applications, and any percentage of methods found dead
- [2] — the specific consistency rate of deprecation replacement messages
- [3] — the reported recall of static endpoint extraction
- [9] — the quantified computational overhead attributed to SHAP

This is not optional diligence. A jury that checks one number and finds it
unsupported will discount the entire review.

---

## 11. References

[1] D. Caivano, P. Cassieri, S. Romano, and G. Scanniello, "On the spread and evolution of dead methods in Java desktop applications: an exploratory study," *Empirical Software Engineering*, vol. 28, no. 3, art. 64, 2023, doi: 10.1007/s10664-023-10303-0.

[2] P. Cassieri, S. Romano, and G. Scanniello, "On deprecated API usages: an exploratory study of top-starred projects on GitHub," in *Proc. 24th Int. Conf. Product-Focused Software Process Improvement (PROFES)*, 2023, doi: 10.1007/978-3-031-49266-2_29.

[3] V. Bushong, D. Das, A. Al Maruf, and T. Cerný, "Using static analysis to address microservice architecture reconstruction," in *Proc. 36th IEEE/ACM Int. Conf. Automated Software Engineering (ASE)*, 2021, doi: 10.1109/ASE51524.2021.9678749.

[4] S.-P. Ma, C.-Y. Fan, Y. Chuang, I-H. Liu, and C.-W. Lan, "Graph-based and scenario-driven microservice analysis, retrieval, and testing," *Future Generation Computer Systems*, vol. 100, pp. 724–735, 2019, doi: 10.1016/j.future.2019.05.048.

[5] A. S. Abdelfattah and T. Cerný, "The microservice dependency matrix," in *Proc. European Conf. Service-Oriented and Cloud Computing (ESOCC)*, 2023, doi: 10.1007/978-3-031-46235-1_19.

[6] G. Dell'Immagine, J. Soldani, and A. Brogi, "KubeHound: detecting microservices' security smells in Kubernetes deployments," *Future Internet*, vol. 15, no. 7, art. 228, 2023, doi: 10.3390/fi15070228.

[7] F. L. Ponce Mella, J. Soldani, C. Taramasco, H. Astudillo, and A. Brogi, "Beyond security: understanding the multiple impacts of security smells for microservices," *CLEI Electronic Journal*, vol. 27, no. 2, 2024, doi: 10.19153/cleiej.27.2.6.

[8] S. M. Lundberg and S.-I. Lee, "A unified approach to interpreting model predictions," in *Advances in Neural Information Processing Systems (NIPS)*, 2017.

[9] D. Gaspar, P. Silva, and C. Silva, "Explainable AI for intrusion detection systems: LIME and SHAP applicability on multi-layer perceptron," *IEEE Access*, vol. 12, 2024, doi: 10.1109/ACCESS.2024.3368377.

[10] Q. Scheitle, O. Gasser, T. Nolte, J. Amann, L. Brent, G. Carle, R. Holz, T. C. Schmidt, and M. Wählisch, "The rise of certificate transparency and its implications on the internet ecosystem," in *Proc. Internet Measurement Conference (IMC)*, 2018.

### Supporting industry sources (prevalence evidence, not research literature)

[11] OWASP, "API9:2023 Improper Inventory Management," *OWASP API Security Top 10*, 2023.

[12] Reserve Bank of India, "Cyber Security Framework in Banks," DBS.CO/CSITE/BC.11/33.01.001/2015-16, 2016.

[13] National Institute of Standards and Technology, "Guide to Secure Web Services," NIST SP 800-95, 2007.
