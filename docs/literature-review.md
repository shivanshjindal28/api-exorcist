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
dead methods in open-source Java desktop applications, quantitatively analysing the
commit histories of **23 GitHub-hosted projects across 1,587 commits**. Their
contribution matters to us in two ways. First, it establishes that unused code is not
an occasional defect but a persistent, measurable property of real codebases — which
is the premise our entire project depends on. Second, their method is *commit-level*:
dead methods are identified by tracking the repository over time rather than by
inspecting a single snapshot. That temporal framing directly informed our decision to
treat `CODE_UNTOUCHED_1Y` as an evidence signal rather than inspecting only the
current state of a repository.

Three of their five reported findings bear directly on our design, and one of them
supports the part of this project that is hardest to justify.

**"Dead methods generally survive for a long time before being buried or revived."**
Decay is slow and silent. An inventory refreshed on a scan cadence of days or weeks
loses nothing, which is why our pipeline is a periodic batch rather than a real-time
stream — and, as §6 explains, that choice is also what makes exact SHAP attribution
affordable for us where it is not for an intrusion detection system.

**"Dead methods are rarely revived."** This is the empirical result that underwrites
Safe Kill. The central risk of automated remediation is removing something that turns
out to still be needed; [1] provides published evidence that, in practice, code which
has gone dead overwhelmingly stays dead. That does not make removal safe on its own —
which is why the blast-radius check, the approval gate and the automatic rollback all
exist — but it establishes that the base rate favours removal rather than indefinite
retention. Without it, "leave everything running forever" would be the defensible
policy and this project would have no thesis.

**"Most dead methods are stillborn, rather than becoming dead later."** Most dead code
was never used at all, from the moment it was written. This maps precisely onto the
decay mechanisms in our simulated estate: the debug replay route added during an
incident, the concluded A/B experiment, the PIN endpoint abandoned in security review.
These were never live; they were born dead and never removed. Our estate models that
pattern because the literature says it is the dominant one, not because it was
convenient to simulate.

The authors also survey prior quantifications of the problem: Eder et al. found **25%
of methods dead** in a commercial .NET web application, Boomsma et al. found
developers removing **30% of a PHP subsystem's files** as dead, and Eder et al.
further reported that 7.6% of maintenance modifications touched dead methods, of which
**48% were unnecessary work**. That last figure is the maintenance-cost argument for
remediation, stated in the literature rather than asserted by us.

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
that a distributed system's real architecture must be *recovered* from source, because
the documented architecture drifts from the deployed reality — is the same premise
that motivates our OPENAPI-versus-CODE coverage gap.

Two statements of theirs bear directly on our design, and both are quoted from the
paper rather than paraphrased loosely:

> "Our method does not need system runtime data; instead, it uses code analysis to
> identify microservice endpoints and calls between individual microservices."

> Developers "can get an updated view of the system's service APIs and service
> interactions as the code changes, rather than waiting for deployments."

This is the justification for the `CodeConnector` and for using **Semgrep rather than
regular expressions**. Semgrep parses source into an abstract syntax tree and matches
route declarations structurally, so `@app.get("/v1/accounts")`, `@RestController` and
`router.post(...)` are recognised as the same kind of construct across languages
regardless of formatting — and a route written inside a comment or a string literal is
not matched at all, because structurally it is not a decorator applied to a function.
A regular expression over source text cannot make that distinction. Our own scan of a
real repository confirms the practical difference: the extractor finds the routes and
ignores planted decoys in comments and string constants.

It also explains why source analysis reaches **100% coverage of the estate where the
gateway registry reaches 76%**: the code is the record of what exists, independent of
whether anything registered it or observed it running.

**The same property is the source of our sharpest limitation, and [3] states it
plainly.** Their method deliberately needs no runtime data — which means it also
yields none. Our Phase 1 work independently rediscovered the consequence: a scan with
no traffic source cannot place an endpoint anywhere in a taxonomy whose every class is
defined in terms of use. Static analysis establishes what exists; it cannot establish
what is used. That is precisely why this project correlates six sources rather than
building a better static analyser.

**A note on what this paper is.** [3] is a three-page paper presenting a method, with
sections for introduction, background and approach. **It reports no empirical
evaluation** — no recall, precision or ground-truth comparison. It is cited here for
the approach it proposes and the premise it argues, and no quantitative claim is
attributed to it. An earlier draft of this review credited it with a "measured result"
and with a three-phase extraction pipeline; neither is in the paper, and both have
been removed.

---

## 4. Theme C — Graph-based dependency modelling

Discovery answers *what exists*. Safe removal requires answering *what breaks if this
disappears*, and that is a graph reachability question.

**Ma, Fan, Chuang, Liu and Lan [4]** present GSMART — Graph-based and Scenario-driven
Microservice Analysis, Retrieval and Testing — in *Future Generation Computer Systems*.
The first problem they name is the one this project exists to solve: **"the management
of complex call relationships among microservices."** Their answer is the automatic
generation of a *Service Dependency Graph* (SDG), used to visualise and analyse
dependency relationships between microservices, and to retrieve the regression tests
a given change requires.

This is the strongest single justification for our dependency layer, for a reason
worth being precise about: **they implement the SDG in Neo4j** (version 3.1.1, Bolt
driver), and evaluate SDG generation efficiency at systems ranging *"from less than
ten microservices to hundreds"*. So the choice of a graph database for exactly this
structure is not our inference from a paper about graphs in general — it is the
architecture the paper actually built and measured.

The argument for it is concrete rather than a matter of taste. "Which services
transitively depend on this endpoint?" is an unbounded-depth traversal. In SQL that is
a recursive common table expression whose cost grows with each hop and whose query text
obscures the intent; in Cypher it is a variable-length path match. Since blast-radius
computation runs on every removal decision and the depth is not known in advance, the
graph model fits the query we run most often — which is the one relational stores
handle worst.

Our implementation follows this directly: `Neo4jGraph` stores endpoints and services
as nodes with `CALLS` and `OWNS` relationships and answers blast radius with a single
`(dep)-[:CALLS|OWNS*1..N]->(e)` match. Against the simulated estate it reaches **nine
services across five hops from three direct callers** — a result no flat inventory can
produce and no single-hop query would find.

**Where we diverge, and why.** GSMART uses its SDG for comprehension and test
selection. We use it as a *safety gate*: an endpoint the classifier believes is dead
may only proceed toward removal if the graph shows nothing depends on it. That
repurposing — from understanding a system to deciding what may safely be removed from
it — is part of this project's contribution rather than theirs.

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

Their reported limitation is one we design around rather than inherit. They state that
generating explanations with LIME and SHAP "can be computationally expensive,
especially for large-scale IDS deployments with high data throughput," and report from
their own experiments that **SHAP was considerably more expensive than LIME on
identical workloads** — enough that computational load becomes a factor in choosing
between the two.

**Our workload is not real-time.** Classification runs per scan — hourly or daily —
over an inventory numbering in the thousands, not per packet at line rate. The cost
that forces an IDS to choose LIME over SHAP is simply not a constraint for an
asset-lifecycle classifier, which is why we can afford the method with the stronger
completeness guarantee where an IDS cannot. The same batch cadence is independently
justified by [1]'s finding that decay is slow.

Their study also reports a result relevant to deployment rather than architecture: a
majority of participants said that being able to validate the explanations *increased
their trust* in the method. For a system asking a human to approve disabling a
production endpoint, that is the outcome the explanation layer exists to produce.

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
| [1] | Caivano et al., EMSE 2023 | Dead code is detected at commit level, not from a snapshot; decay is slow; **dead methods are rarely revived**; most are stillborn | Temporal signals are first-class evidence; periodic batch scanning rather than real-time; the base rate favouring removal is what makes Safe Kill defensible | `connectors/discovery.py` (`CODE_UNTOUCHED_1Y`), six-source architecture, Phase 4 |
| [2] | Cassieri et al., PROFES 2023 | Deprecation markers are applied inconsistently by real teams | `DEPRECATED` is a class distinct from `ZOMBIE`; the `spec_deprecated` flag is deliberately imperfect (2 of 3) | `simulated_env/estate.py`, `connectors/gateway.py` |
| [3] | Bushong et al., ASE 2021 | Architecture is recovered from source without runtime data, giving a view that updates as code changes; and yielding no usage data in return | Semgrep AST matching over regex; CODE reaches 100% coverage where the gateway reaches 76%; and repository scans must abstain from lifecycle claims | `extractors/semgrep_extractor.py`, `live/connectors.py`, `engine/rules.py` (abstention) |
| [4] | Ma et al., FGCS 2019 | A Service Dependency Graph implemented **in Neo4j**, evaluated from ten to hundreds of microservices | Neo4j for the dependency layer; a Cypher variable-length path rather than a recursive CTE. Repurposed from comprehension to a removal safety gate | `graph/model.py`, `graph/neo4j_store.py`, `graph/build.py` |
| [5] | Abdelfattah & Cerný, ESOCC 2023 | Inter-service dependency is a measurable first-class architectural property | Blast radius computed before any removal is cleared; classifier and graph must both agree | `graph/build.py` |
| [6] | Dell'Immagine et al., Future Internet 2023 | "Security smell" is a valid construct: structural indicators of elevated risk | Discrepancy flags are modelled as security smells with academic grounding | `inventory/correlator.py` (15 flags) |
| [7] | Ponce et al., CLEIej 2024 | The research programme terminates at detection and triage | The research gap: automated *safe remediation* is the project's contribution | Phase 4 — Safe Kill Simulation (planned) |
| [8] | Lundberg & Lee, NIPS 2017 | SHAP gives additive, complete per-prediction feature attribution | The rule layer already emits *additive signed contributions*, so SHAP will render through the same path rather than a second one | `engine/verdict.py`, `engine/explain.py` ✅ · SHAP itself Phase 3 ⬜ |
| [9] | Gaspar et al., IEEE Access 2024 | SHAP is applicable to security decisions; its cost constrains real-time use | Hybrid rules + model; a per-scan rather than per-packet workload makes exact attribution affordable | `engine/rules.py` (rules-first) ✅ · model layer Phase 3 ⬜ |
| [10] | Scheitle et al., IMC 2018 | CT logs publicly expose unintended hostnames; this has privacy implications | Two-tier URL scanning: passive CT/DNS/spec first, active probing only after DNS TXT ownership proof | `live/` scans repositories ✅ · URL tiers Phase 1b ⬜ |

---

## 9. Synthesis: the research gap

The literature supports each of the following statements individually. No published
work combines them.

1. Unused code persists in real systems and is detectable — but the techniques are
   single-source and cannot see external callers. Crucially, dead code is **rarely
   revived**, so the base rate favours removal over indefinite retention **[1]**.
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

Every citation is confirmed real — exact title, author list, venue, year and DOI
validated against DBLP.

### Verified against full text ✔

- **[1] Caivano et al.** — 23 open-source Java desktop applications and 1,587 commits
  confirmed from the abstract. All five take-away findings quoted in §2 are the
  authors' own wording. The 25% / 30% / 48% figures are prior work *surveyed by* [1]
  (Eder et al.; Boomsma et al.) and are cited here as such, not as [1]'s own results —
  if you quote them in the paper, attribute them the same way.
- **[9] Gaspar et al.** — the computational-cost limitation is confirmed, but it is
  **qualitative, not quantified**. The paper states SHAP "can be computationally
  expensive" for high-throughput IDS deployments and that SHAP was "considerably more
  expensive than LIME" in their experiments. It reports no overhead figure, so §6
  claims no number. Do not add one.

- **[3] Bushong et al.** — verified, and **it forced a correction**. The full text is a
  three-page method paper with only introduction, background and approach sections. It
  contains **no evaluation**: zero occurrences of "recall", "precision" or "ground
  truth". An earlier draft of §3 credited it with a "measured result" and with a
  three-phase extraction pipeline (endpoint extraction → call extraction → signature
  matching). Neither is in the paper — the three-phase description came from a
  different work and was mis-attributed. Both claims are removed, and §3 now quotes the
  paper directly. **No quantitative claim is attributed to [3].**
- **[4] Ma et al.** — verified, and stronger than first written. They implement their
  Service Dependency Graph **in Neo4j 3.1.1 over the Bolt driver** and evaluate
  generation efficiency from ten to hundreds of microservices. Our Neo4j choice is
  therefore precedent, not inference. §4 has been strengthened accordingly, and now
  also states where we diverge: they use the graph for comprehension and test
  selection, we use it as a removal safety gate.

### Still to verify ⚠

- **[2] Cassieri et al.** — pending library access. §2 says deprecation markers are
  "inconsistently applied and inconsistently acted upon", which the abstract supports.
  Confirm the specific consistency rate of replacement messages before quoting any
  figure, and correct anything the full text does not bear out.

**Why this section exists.** Of the four papers flagged for full-text checking, one
turned out to be carrying claims it does not make. That was found by reading the PDF,
not by trusting a summary — and it is exactly the failure a panel would find by
opening one citation. Do not skip the last one.

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
