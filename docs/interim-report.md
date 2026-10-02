# Interim Report

<!--
Chapters 1-3 only, as required for the midterm (Review 2) submission.
Chapters 4 and 5, Conclusion and the Appendices follow in the final report.

Source of truth: this Markdown file. Build the Word version with
    python docs/build_docx.py interim
Every number in Chapter 3 is checked against the running code by
    python docs/verify_claims.py
-->

## Chapter 1: Introduction

Modern banking runs on APIs. A single retail bank exposes hundreds of HTTP
endpoints across mobile banking, internet banking, payments, KYC, partner
integrations and internal microservices. Those endpoints are created quickly and
retired slowly, and a substantial fraction of them are never retired at all. This
report describes API Exorcist, a system that identifies endpoints which are still
running but no longer serve any purpose, and that establishes, before anything is
switched off, whether removing one is safe. Chapter 1 states the background,
motivation, scope and problem. Chapter 2 surveys the literature that the design
draws on and identifies the research gap the project addresses. Chapter 3 presents
the methodology, the system design and the implementation completed to date, with
measured results.

### 1.1 Background of the project topic

An API endpoint has a lifecycle. It is written, deployed, documented, used, and
eventually superseded. The final step, decommissioning, depends on a human
deciding that nothing depends on it any more. That decision is expensive to make
correctly and cheap to postpone, so in practice it is postponed. The endpoint keeps
running. It keeps its database credentials, its network route and its access to
production data, and it stops appearing in anybody's mental model of the system.

The industry has a name for the resulting failure mode. OWASP lists it as
**API9:2023 Improper Inventory Management** in the API Security Top 10 **[13]**,
describing hosts and API versions that remain deployed and reachable while the
organisation's documentation and inventory no longer account for them. The concern
is not hypothetical for Indian banks in particular: the Reserve Bank of India's
*Cyber Security Framework in Banks* **[14]** requires an accurate, maintained
inventory of information assets, and an endpoint nobody knows about cannot be
patched, cannot be monitored, and cannot be included in an audit.

Four distinct conditions are conflated under the informal label "old API", and the
project separates them because they demand different responses:

Table: The four lifecycle states the project distinguishes

| Class | Definition | Correct action |
|---|---|---|
| **ACTIVE** | Documented, owned, and carrying meaningful traffic | Leave alone |
| **DEPRECATED** | Declared end-of-life but still serving real callers | Managed sunset with consumer notice |
| **ORPHANED** | Carrying real traffic but with no owning team | Assign an owner, never remove |
| **ZOMBIE** | Reachable, unowned, undocumented, and not meaningfully used | Candidate for removal |

The distinction that matters most is between ORPHANED and ZOMBIE. Both are unowned.
Only one is unused. Removing an orphaned endpoint causes an outage in whatever is
still calling it, and the fact that no team claims it makes that outage harder to
diagnose, not easier. A tool that cannot tell the two apart is not usable in
production.

### 1.2 Motivation and scope of the report

The motivation is a gap between what can be detected and what can be safely acted
upon. Static analysis can list the routes a repository defines. A gateway can list
the routes it proxies. Traffic capture can list the routes that were called. Each of
these is a partial and imperfect witness, and each is routinely wrong in a
predictable direction: the gateway does not see a service that is addressed
directly, the specification does not describe a route the team forgot to document,
and traffic capture cannot see a route that nothing called during the capture window.

The central observation of this project is therefore that **a zombie endpoint is not
identified by any single source of evidence. It is identified by a pattern of
disagreement between sources.** An endpoint that the code defines, that DNS
resolves, that the gateway has never registered, that the specification does not
describe, that no pipeline has deployed in a year and that traffic has not seen in
six months is a zombie, and no one of those six facts says so on its own.

**Scope of the work reported here.** This interim report covers the discovery,
correlation, classification, explanation and dependency-analysis layers, together
with the evaluation harness that measures them: Phases 0 to 3 of an eight-phase
plan. Specifically in scope and completed:

- six independent discovery connectors, each with deliberate, documented blind spots;
- correlation of their observations into a single inventory carrying fourteen
  discrepancy flags;
- a four-class classifier built from fifteen weighted evidence rules, which abstains
  rather than guesses when a source was never consulted;
- a per-verdict explanation carrying every signed evidence contribution;
- real scanning of a GitHub repository using Semgrep AST matching, git history and
  CODEOWNERS;
- a dependency graph with blast-radius computation, backed by Neo4j, and a removal
  gate that requires the classifier and the graph to agree;
- a labelled dataset generator, a trained gradient-boosted model, and SHAP
  attribution rendered through the same explanation objects the rules produce;
- a comparative evaluation that measures the same pipeline under restricted and full
  evidence.

**Explicitly out of scope for this report** and scheduled for the second half:
the Safe Kill Simulation (canary shutdown, automatic rollback, hash-chained audit
log), the CI/CD enforcement plugin, the REST API and dashboard, the active tier of
the URL scanner, and production hardening and deployment.

**One boundary is stated here because it governs how every result in Chapter 3
should be read.** The architecture, the connectors, the correlator, the classifier,
the graph and the evaluation harness are real code. The banking estate they are
measured against is **synthetic**, a generated twenty-five-endpoint retail-banking
microservice estate with a known answer key. No production bank data was used, and
none was available. The defensible claim, made consistently throughout this report,
is that *the engine recovers known decay patterns from partial and disagreeing
evidence*; it is not, and is never presented as, validation against live bank
traffic.

### 1.3 Problem statement

> Banking API estates accumulate endpoints that remain deployed and reachable after
> they have ceased to serve any purpose. No single source of evidence, gateway
> registry, API specification, source code, traffic capture, DNS or deployment
> history, can establish whether a given endpoint is genuinely unused, because each
> source has systematic blind spots. Existing tooling therefore either misses these
> endpoints or, worse, flags live endpoints for removal. Furthermore, the tools that
> do detect anomalous endpoints stop at detection: they produce a report, and the
> decision to decommission remains an unaided human judgement made without knowing
> what depends on the endpoint. The problem is to determine an endpoint's true
> lifecycle state by correlating multiple partial sources, to quantify the
> consequence of removing it, and to make both the classification and the removal
> decision explainable enough to be defended in a regulated audit.

Three sub-problems follow, and the project is organised around them:

1. **Determination under partial evidence.** Establish lifecycle state from sources
   that disagree, and, critically, distinguish *"this source says no"* from
   *"this source was never asked"*. A system that treats an unconsulted source as
   negative evidence will confidently mislabel a live estate.
2. **Consequence prediction.** Before an endpoint is cleared for removal, determine
   what calls it, transitively, and refuse to clear anything with dependants.
3. **Auditability.** Every classification and every removal decision must carry the
   complete evidence that produced it, in a form a compliance reviewer can read.

### 1.4 Salient contribution

The individual capabilities the project relies on all exist in the literature. The
contribution is their composition, plus three specific design decisions that the
survey in Chapter 2 did not find combined anywhere:

1. **Absence treated as first-class evidence, with abstention.** The inventory
   records which sources did *not* observe an endpoint, and each evidence rule
   declares which sources it needs. A rule whose source was never consulted abstains
   instead of firing. This is what makes a partial deployment honest: scanning only a
   repository yields six of fifteen usable rules and the system reports that it
   cannot make a lifecycle claim, rather than declaring every endpoint dead.
2. **A removal gate requiring two independent agreements.** An endpoint is cleared
   only when the evidence classifier calls it a zombie *and* the dependency graph
   finds it has no callers. Either alone is insufficient, and the project's tests
   assert that no live endpoint is ever marked for removal.
3. **A learned model used as a veto, never as a proposer.** The rule layer is what
   allows a new deployment to work on day one with zero training data, and it is
   auditable line by line. The trained model, evaluated separately on held-out
   estates, is aggregate-equivalent to the rules but produces zero false zombies
   where the rules produce seventeen. It is therefore permitted to *block* a removal
   and never to *create* one, an asymmetry chosen because a false zombie is an
   outage and a missed one is a line on a report.

A fourth contribution is methodological. The synthetic estate is generated **by
lifecycle mechanism rather than by label rule**: an endpoint is put through a story,
a product is discontinued, a team dissolves, a migration stalls, a debug route
outlives an incident, and its observable features are consequences of that story.
Two guards enforce, at import and token level, that the ground-truth fields never
reach detection code. Both guards were written after an early connector was found
deriving a feature from the answer key, which would have silently inflated every
reported figure.

### 1.5 Organization of the report

**Chapter 1** states the background, motivation, scope, problem and contribution.
**Chapter 2** surveys the literature across six themes, dead-code detection,
architecture recovery through static analysis, graph-based dependency modelling,
security smells and the detection-remediation gap, explainability in security
decisions, and passive discovery, and closes by naming the research gap and
tracing each finding to the module that implements it. **Chapter 3** presents the
methodology: the layered architecture, the technology stack and its justification,
the correlation and classification algorithms, the removal gate, and the
implementation completed to date with measured results. The design document is
prepared separately and is reproduced in full as Appendix A.

**Summary.** Banking API estates accumulate endpoints that are still reachable but
no longer serve any purpose, and no single evidence source can identify them because
every source has systematic blind spots. This chapter has defined the four lifecycle
states the project distinguishes, stated the problem as one of determination under
partial evidence followed by consequence prediction and auditable explanation, and
fixed the scope of the work reported here at Phases 0 to 3 of eight.

---

## Chapter 2: Literature Survey

This chapter reviews the research the project builds on. It is organised by theme
rather than by paper, because the argument the project makes is cumulative: each
theme supplies one necessary component, and the gap the project addresses is that
nobody has assembled them. Section 2.1 introduces the overall topic. Sections 2.2
to 2.7 survey the six themes across twelve peer-reviewed sources. Section 2.8 traces every finding to the design
decision it justifies and the module that implements it. Section 2.9 states the
research gap and how the problem statement follows from it. Section 2.10 records
which citations were verified against full text, and what that verification changed.

### 2.1 Introduction to the overall topic

The topic sits at the intersection of three research communities that rarely cite
each other. Empirical software engineering studies *dead code*, code that is
present in a system but never executed, and has established both its prevalence and
its evolution over time. Microservice architecture research studies *architecture
recovery*, the problem of reconstructing a system's true structure from its
artefacts because its documentation has drifted. Security research studies *security
smells*, structural indicators of elevated risk in a deployed system, and the
triage of those findings.

An abandoned API endpoint is simultaneously all three: it is dead code that happens
to be network-reachable, it is a component missing from the recovered architecture,
and it is a security exposure. The literature treats these separately, and the
techniques each community has developed are single-source in a way that a
network-reachable artefact defeats. Static analysis cannot see who calls an endpoint
from outside the repository. Traffic analysis cannot see an endpoint nothing called.
The problem requires the correlation of sources that no individual technique
combines.

A parallel body of work supplies the two remaining components. Graph-based
dependency modelling gives a way to compute the consequence of removal, and
explainable-AI research gives a way to make an automated security decision auditable
, which is a precondition for any of this being deployable in a regulated bank.

### 2.2 Theme A: Dead and deprecated code, the software-engineering foundation

Caivano, Cassieri, Romano and Scanniello **[1]** conducted an exploratory study of
the spread and evolution of dead methods across twenty-three open-source Java desktop
applications and 1,587 commits. Their design is the significant part: dead code is
identified at *commit* level rather than from a single snapshot, which makes decay a
temporal property rather than a static one. Four of their findings shape this
project directly. Dead methods are widespread. Decay is slow, unfolding over many
commits rather than appearing at once. Most dead methods are *stillborn*, they were
never called from the moment they were introduced. And, most consequentially for a
tool that proposes deletion, **dead methods are rarely revived**: once a method
stops being called, it very seldom starts again.

That last finding is what makes automated removal defensible at all. If dead code
routinely came back to life, any removal proposal would carry a high expected cost
and the correct engineering answer would be to leave everything in place. Because the
base rate favours removal, a tool that removes carefully is doing the right thing on
average. The prevalence percentages quoted in this area, figures of the order of a
quarter to a half of a codebase being unused, are prior work *surveyed by* [1]
rather than [1]'s own measurements, and are attributed as such here.

Cassieri, Romano and Scanniello **[2]** studied deprecated API usage across
top-starred GitHub projects and found that deprecation markers are applied and acted
upon inconsistently by real teams. This is the empirical basis for a design decision
that would otherwise look like an over-complication: **DEPRECATED is modelled as a
class distinct from ZOMBIE, and the declared deprecation flag is treated as
unreliable evidence rather than as ground truth.** In the project's synthetic
estate, only two of the three genuinely deprecated endpoints carry the specification
flag, precisely because real teams do not set it reliably. The single
misclassification the system makes on the demo estate is the third one, and it is
reported as a finding rather than tuned away, because the observable evidence
genuinely does not distinguish that case.

Brito, Hora, Valente and Robbes **[11]** supply the quantitative anchor that **[2]**
leaves qualitative. Measuring across **622 Java and 229 C# systems**, they report that
on the median only **66.7% of Java and 77.8% of C# API elements are deprecated with a
replacement message** per project, roughly a third of Java deprecations tell a client
nothing about what to use instead, and that "there is no major effort to improve
deprecation messages", so the gap does not close as a project matures.

Two implementation decisions follow directly from that measurement. First, the
deprecation rule is deliberately **asymmetric**: `MARKED_DEPRECATED` carries the
largest single weight in the rule set because a marker, when present, is an explicit
human declaration, but there is **no rule for the absence of a marker**. If a third of
real deprecations are never marked, then "not marked deprecated" is not evidence of
anything, and a rule treating it as evidence would systematically mislabel exactly the
endpoints a bank most needs to find. Presence is evidence; absence is silence. Second,
the two-of-three flag rate in the estate is **66.7%, which is [11]'s measured Java
median**, a parameter that was previously chosen to avoid a trivially learnable field
and is now empirically grounded.

### 2.3 Theme B: Architecture recovery through static analysis

Bushong, Das, Al Maruf and Cerný **[3]** address microservice architecture
reconstruction using static analysis of source code. Their central argument is that
a system's true architecture must be recovered from its artefacts because
documentation drifts away from reality, and that source-code analysis yields a view
which updates as the code changes rather than as the documentation is maintained.
Their approach informs the project's choice of Semgrep AST matching over regular
expressions for route extraction: a route defined by a decorator, a router mount and
a path parameter is a *structural* pattern, and matching it structurally is correct
where matching it textually is a heuristic.

The paper's second contribution to this project is negative, and it is the more
important one. Static analysis of a repository yields no usage data whatsoever. It
can establish that an endpoint exists; it cannot establish that anything calls it.
This is the direct justification for the abstention mechanism described in
Section 3.4: **a repository scan is architecturally forbidden from making a
lifecycle claim**, because the evidence class required to support one is absent.

Gortney, Harris, Cerný, Al Maruf, Bures, Taibi and Tisnovsky **[12]** map the
complementary half of the same problem. Where **[3]** recovers architecture
statically, **[12]** systematically surveys reconstruction in the **dynamic
perspective**, the techniques, tools and models built from log analysis, tracing and
monitoring. Their motivating observation is that teams "fail to visualize the entire
system architecture holistically", and that dynamic analysis is an established
practice for obtaining a whole-system view because it can "build the system and then
show its behavior at run-time".

Read together, **[3]** and **[12]** are this project's architecture in miniature.
Static recovery establishes *what exists*; dynamic recovery establishes *what actually
runs and calls what*. Neither subsumes the other, and the surveyed literature treats
them as alternative research programmes rather than as two inputs to one decision. API
Exorcist consumes both: CODE and OPENAPI on the static side, TRAFFIC and DNS on the
dynamic side, and its central claim is that the *disagreement between the two
perspectives* is the signal. An endpoint that the static view knows and the dynamic
view has never seen is the definition of the thing being looked for. This is also the
formal justification for abstention: a repository-only scan is missing the dynamic
perspective by construction, so it must decline to make a claim that only the dynamic
perspective can support.

This citation is also the project's clearest example of why full-text verification
matters. [3] is a three-page method paper containing introduction, background and
approach sections and **no evaluation**. An earlier draft of this survey credited it
with a measured result and with a three-phase extraction pipeline; neither appears in
the paper, and the pipeline description had been mis-attributed from a different
work. Both claims were removed. No quantitative claim is attributed to [3] anywhere
in this report.

### 2.4 Theme C: Graph-based dependency modelling

Ma, Fan, Chuang, Liu and Lan **[4]** construct a Service Dependency Graph for
microservice analysis, retrieval and testing, implemented in Neo4j over the Bolt
driver and evaluated on systems ranging from ten to several hundred microservices.
Their work is precedent rather than inference for this project's graph layer: the
choice of a property-graph database over a relational schema, and of a Cypher
variable-length path traversal over a recursive common table expression, follows a
published implementation at the scale the project targets.

Where the project diverges is in purpose. [4] uses the dependency graph for
comprehension and test selection, understanding a system and choosing what to
re-test. API Exorcist repurposes the same structure as a **removal safety gate**: the
question asked of the graph is not "what is the shape of this system" but "if this
node disappeared, what breaks". The traversal is therefore inverted and bounded,
computing a blast radius over alternating call and ownership edges.

Abdelfattah and Cerný **[5]** propose the microservice dependency matrix,
establishing inter-service dependency as a first-class, measurable architectural
property rather than an incidental consequence of the code. This supports the
project's decision to compute and record blast radius as a stored property of every
removal assessment, rather than deriving it ad hoc at decision time.

### 2.5 Theme D: Security smells and the detection-remediation gap

Dell'Immagine, Soldani and Brogi **[6]** detect microservice security smells in
Kubernetes deployments, establishing "security smell" as a valid construct:
structural indicators that do not constitute a vulnerability by themselves but mark
elevated risk. The project's fourteen discrepancy flags, undocumented,
unregistered, shadow candidate, no owner, reachable but unused, unauthenticated,
legacy authentication, sensitive data, and so on, are modelled directly as security
smells in this sense, which gives them academic grounding rather than leaving them as
an ad hoc checklist.

Ponce Mella, Soldani, Taramasco, Astudillo and Brogi **[7]** examine the multiple
impacts of security smells for microservices, and their survey of the field is where
the project's gap becomes explicit. **The research programme terminates at detection
and triage.** Papers detect smells, rank them, and assess their impact. What follows
, the decision to actually change the deployed system, and the machinery to do so
safely, is left to human operators. That termination point is the gap the Safe Kill
Simulation is designed to close.

### 2.6 Theme E: Explainability in security decisions

Lundberg and Lee **[8]** introduce SHAP, a unified approach to interpreting model
predictions that provides additive, complete per-prediction feature attribution
grounded in Shapley values from cooperative game theory. Two properties matter here.
Attribution is *additive*: the contributions sum to the difference between the
prediction and the base value, so an explanation accounts for the whole decision
rather than for a selected part of it. And attribution is *per-prediction*, so the
explanation is about this endpoint rather than about the model in general, which is
what an auditor asking about one specific removal actually needs.

This shape is the reason the project's rule layer uses additive signed weights rather
than a decision tree. Additive evidence scoring degrades gracefully when a rule
abstains, derives confidence from the margin between the top two classes, and,
most decisively, produces explanations of exactly the same form SHAP produces.
The two layers therefore share one explanation type and one renderer, and a reviewer
reads rule-derived and model-derived reasoning in an identical format.

Gaspar, Silva and Silva **[9]** apply LIME and SHAP to intrusion detection with a
multi-layer perceptron, and report a limitation the project depends on: SHAP can be
computationally expensive for high-throughput deployments, and was considerably more
expensive than LIME in their experiments. The paper states this qualitatively and
reports no overhead figure, so none is quoted here. The relevance is that the
constraint does not bind for this workload. Intrusion detection is per-packet at line
rate; API Exorcist is a **per-scan batch workload** over hundreds of endpoints. Exact
`TreeExplainer` attribution is therefore affordable where an IDS must approximate.

### 2.7 Theme F: Passive discovery and the ethics of external scanning

Scheitle et al. **[10]** measure the rise of Certificate Transparency and its
implications for the internet ecosystem, showing among other findings that CT logs
publicly expose hostnames organisations did not intend to publish, with real privacy
consequences. For this project the finding cuts two ways. It confirms that a
substantial amount of estate information is obtainable **entirely passively**,
without sending a single packet to the target, which matters, because a discovery
tool that must probe an unfamiliar host is a tool that cannot be run responsibly.
And it establishes that this exposure is a known problem rather than a licence to
exploit it.

The project's response is a two-tier URL scanner. The passive tier, published
specification, CT logs, public DNS, the site's own JavaScript, may run against any
URL, because it touches only already-public records. The active tier, which probes
the host directly, unlocks only after a DNS TXT record proves domain ownership. This
is a design constraint carried in the code and the documentation, not an aspiration.

### 2.8 Traceability: how the literature is utilised in the implementation

The review requirement is to show not merely what was read, but how it is used. Each
row below traces one finding to the design decision it justifies and to the module
that implements it.

Table: Traceability: literature finding to design decision to implementing module

| # | Source | Finding used | Design decision it justifies | Implemented in |
|---|---|---|---|---|
| [1] | Caivano et al., EMSE 2023 | Dead code is detected at commit level, not from a snapshot; decay is slow; dead methods are rarely revived | Temporal signals are first-class evidence; periodic batch scanning rather than real-time; the base rate favouring removal is what makes Safe Kill defensible | `connectors/discovery.py`, six-source architecture, Phase 4 |
| [2] | Cassieri et al., PROFES 2023 | Deprecation markers are applied inconsistently by real teams | DEPRECATED is a class distinct from ZOMBIE; the deprecation flag is deliberately imperfect evidence | `simulated_env/estate.py`, `connectors/gateway.py` |
| [3] | Bushong et al., ASE 2021 | Architecture is recovered from source without runtime data, and yields no usage data in return | Semgrep AST matching over regex; repository scans must abstain from lifecycle claims | `extractors/semgrep_extractor.py`, `engine/rules.py` |
| [4] | Ma et al., FGCS 2019 | A Service Dependency Graph implemented in Neo4j, evaluated from ten to hundreds of microservices | Neo4j for the dependency layer; Cypher variable-length path rather than a recursive CTE; repurposed from comprehension to a removal safety gate | `graph/model.py`, `graph/neo4j_store.py` |
| [5] | Abdelfattah & Cerný, ESOCC 2023 | Inter-service dependency is a measurable first-class architectural property | Blast radius computed before any removal is cleared; classifier and graph must both agree | `graph/build.py` |
| [6] | Dell'Immagine et al., Future Internet 2023 | "Security smell" is a valid construct: structural indicators of elevated risk | The fourteen discrepancy flags are modelled as security smells | `inventory/correlator.py` |
| [7] | Ponce Mella et al., CLEIej 2024 | The research programme terminates at detection and triage | The research gap: automated *safe remediation* is the contribution | Phase 4: Safe Kill Simulation |
| [8] | Lundberg & Lee, NIPS 2017 | SHAP gives additive, complete per-prediction attribution | Additive signed evidence weights in the rule layer; SHAP values emitted as the *same* explanation objects the rules produce | `engine/model.py`, `engine/verdict.py` |
| [9] | Gaspar et al., IEEE Access 2024 | SHAP is applicable to security decisions; its cost constrains real-time use | Hybrid rules-plus-model; a per-scan batch workload makes exact attribution affordable | `engine/model.py`, `evaluation/train.py` |
| [10] | Scheitle et al., IMC 2018 | CT logs publicly expose unintended hostnames, with privacy implications | Two-tier URL scanning: passive first, active probing only after DNS TXT ownership proof | `live/`, URL tiers scheduled |
| [11] | Brito et al., JSS 2018 | Across 622 Java and 229 C# systems, on the median only 66.7% / 77.8% of API elements are deprecated with a replacement message, and message quality does not improve over time | `MARKED_DEPRECATED` fires on presence only, there is deliberately no rule for the *absence* of a marker; the estate's 2-of-3 flag rate is [11]'s measured Java median | `engine/rules.py`, `simulated_env/estate.py` |
| [12] | Gortney et al., IEEE Access 2022 | Systematic map of architecture reconstruction in the *dynamic* perspective, log analysis, tracing, monitoring, as a distinct practice from static recovery | Static and dynamic sources are both consumed and neither subsumes the other; their disagreement is the zombie signal, and a static-only scan must abstain | `connectors/`, `inventory/correlator.py` |

### 2.9 Synthesis: the research gap and the resulting problem statement

The literature supports each of the following statements individually. No surveyed
work combines them.

1. Unused code persists in real systems and is detectable, but the techniques are
   single-source and cannot see external callers. Dead code is rarely revived, so
   the base rate favours removal **[1]**.
2. Deprecation is declared inconsistently, measurably so, with roughly a third of
   Java deprecations carrying no replacement message and no improvement over time, so
   declared state is an unreliable indicator of real state **[2] [11]**.
3. True architecture must be recovered from artefacts because documentation drifts;
   recovery from source yields no usage data, and the static and dynamic perspectives
   are distinct and complementary **[3] [12]**.
4. Dependency structure is graph-shaped, and traversal-based analysis is the
   appropriate tool **[4] [5]**.
5. Structural security indicators can be detected and triaged automatically
   **[6] [7]**.
6. Automated security decisions can be made explainable with complete, additive
   attribution **[8] [9]**.
7. Substantial estate information is available entirely passively **[10]**.

**The gap.** Statements 1 to 3 together imply that *no single source can establish
an endpoint's true status*, yet every surveyed tool is single-source. Statements 4
and 5 supply the machinery to predict the consequence of removal, yet no tool acts
on it. Statement 6 makes automated action auditable, yet no tool needs it, because
none acts.

The problem statement in Section 1.3 follows directly. The contribution is the
composition: multi-source correlation to establish a status that no single source
can determine, dependency-aware simulation to predict the consequence of removal, and
complete per-decision explanation to make the resulting action auditable in a
regulated environment.

### 2.10 Verification of citations

Every citation in this report was confirmed to exist, with exact title, author list,
venue, year and DOI validated against DBLP and Crossref. Five papers carrying
load-bearing claims were additionally checked against full text. That check changed
the report:

- **[3] Bushong et al.**, the full text contains no evaluation section. A measured
  result and a three-phase pipeline description previously attributed to it were
  removed; the second had been mis-attributed from a different paper.
- **[9] Gaspar et al.**, the computational-cost limitation is confirmed but is
  qualitative. No overhead figure is quoted, because the paper reports none.
- **[4] Ma et al.**, verified and stronger than first written: the Neo4j
  implementation is explicit in the paper, making the project's database choice
  precedent rather than inference.
- **[1] Caivano et al.**, the study design and all five take-away findings are the
  authors' own; the prevalence percentages are prior work surveyed by them and are
  attributed accordingly.
- **[2] Cassieri et al.**, full text pending library access. The claim made in
  Section 2.2 is supported by the abstract; no specific consistency rate is quoted
  from it. The quantitative figures in Section 2.2 come from **[11]**, which was read.
- **[11] Brito et al.**, verified against the author-hosted full text. The study size
  (622 Java, 229 C# systems), both median percentages and the finding that message
  quality does not improve over time are the authors' own wording, taken from the
  abstract of the paper itself.
- **[12] Gortney et al.**, abstract verified verbatim and metadata confirmed against
  DBLP. Full text not yet read, so no quantitative claim is attributed to it, only
  the qualitative static-versus-dynamic distinction, which the abstract states
  directly.

**Summary.** The survey establishes that dead code is prevalent, slow-moving and
rarely revived; that declared deprecation is unreliable; that architecture must be
recovered from artefacts and that source recovery yields no usage data; that
dependency analysis is graph-shaped; that security smells can be detected but that
the research programme stops at detection; that additive per-prediction attribution
can make automated decisions auditable; and that substantial discovery is possible
passively. The gap is that no work composes multi-source correlation, consequence
prediction and auditable explanation into a system that can safely act.

---

## Chapter 3: Methodology and Implementation

This chapter describes how the system is built and what has been implemented. Section
3.1 presents the block diagram and the layered architecture. Section 3.2 describes the
execution environment and the technology stack with the justification for each choice.
Section 3.3 describes the software, module by module. Section 3.4 gives the algorithms
, correlation, evidence scoring with abstention, and the removal gate, with
pseudo-code. Section 3.5 states what has been implemented against what was planned.
Section 3.6 reports measured results. The full design document, prepared separately,
is reproduced as Appendix A; this chapter presents the parts needed to follow the
implementation.

### 3.1 Block diagram: system architecture

The system is five layers with a strictly one-way dependency direction. Connectors
know nothing of ingestion, and the engine never reaches back to a data source. That
constraint is what allows the synthetic estate to be swapped for live sources without
altering anything downstream, and it is the reason the same pipeline code produces
both the simulated results and the real GitHub repository scans in Section 3.6.

![figure](diagrams/component.png "Component diagram: the five architectural layers")

**Layer 1: Discovery.** Six connectors, each a partial and imperfect witness, each
emitting observations and never verdicts. Their common output type is the
`DiscoverySignal`, an eight-field record stating what one source observed about one
endpoint.

**Layer 2: Ingestion.** A message bus that decouples collection from analysis. The
default is an in-process `LocalBus` requiring no infrastructure; Kafka and
Elasticsearch backends implement the same interface for deployed operation.

**Layer 3: Analysis.** Correlation of signals into a unified inventory record per
endpoint, derivation of fourteen discrepancy flags, four-class classification by
weighted evidence rules, explanation, dependency-graph construction and blast-radius
computation, and the learned model with SHAP attribution.

**Layer 4: Decision.** The removal gate, which requires the classifier and the graph
to agree independently. The Safe Kill Simulation attaches here in Phase 4.

**Layer 5: Presentation.** The command-line interface, implemented; the REST API and
dashboard, designed and scheduled.

The class model of the core domain is shown below. The significant structural point
is that `Verdict` composes a list of `Reason` objects with signed contributions and
is never a bare label, the same type serialises into the audit log and renders in
the explanation output.

![figure](diagrams/classes.png "Class diagram: core domain model")

### 3.2 Execution environment and technology stack

This is a software project with no custom hardware. The execution environment is
commodity: Python 3.10 or 3.12 on Linux or Windows, with an optional Neo4j instance
and an optional Kafka broker, both supplied through `docker-compose.yml` for a
deployed configuration. The default configuration deliberately requires no external
infrastructure at all, so that a reviewer can clone the repository and reproduce
every number in Section 3.6 with two commands.

Table: Technology stack and the justification for each choice

| Component | Technology | Why this and not the alternative |
|---|---|---|
| Route extraction | Semgrep (AST matching) | A route is a structural pattern, decorator, router mount, path parameter. Regex matching over source text is a heuristic that breaks on formatting; AST matching does not. Justified by [3]. |
| Dependency store | Neo4j (Cypher) | Blast radius is a bounded multi-hop traversal over alternating call and ownership edges. A variable-length Cypher path expresses it directly where a relational recursive CTE does not. Precedent in [4]. |
| Traffic observation | Zeek | Passive full-visibility logging of what was actually called, rather than signature matching against known-bad patterns. The question is "what was used", not "what was an attack". |
| Streaming | Kafka | Traffic-derived signals are bursty and high-volume; the bus must buffer rather than block the collector. |
| Classification | Weighted evidence rules, with a gradient-boosted model as a veto | Rules work on day one with no training data and are auditable line by line, which is what allows a customer to be onboarded at all. The model adds precision where training data exists. |
| Explanation | SHAP `TreeExplainer` | Exact, additive, per-prediction attribution [8], affordable because this is a per-scan batch workload rather than the per-packet workload of [9]. |
| Repository access | `git clone --filter=blob:none` | A partial clone fetches history and file names without blob contents, which is what the staleness and ownership analysis needs. Nothing from a scanned repository is ever executed. |

### 3.3 Software description

`src/apix/` is organised as follows.

Table: Module responsibilities within src/apix/

| Module | Responsibility |
|---|---|
| `config.py` | Settings from environment, with defaults that need no infrastructure |
| `connectors/` | Six discovery sources, each with deliberate and documented blind spots |
| `ingestion/` | `LocalBus` (default), Kafka and Elasticsearch backends behind one interface |
| `inventory/` | Multi-source correlation into a unified inventory carrying 14 flags |
| `engine/` | Verdict types, the 15 evidence rules, explanations, the model and the hybrid veto |
| `graph/` | Dependency graph, blast radius, the removal gate; in-memory and Neo4j backends |
| `extractors/` | Semgrep AST route extraction and cross-framework path normalisation |
| `live/` | Real GitHub repository scanning, clone, git history, CODEOWNERS |
| `evaluation/` | Metrics, the comparative benchmark, and model training |
| `dataset/` | The labelled dataset and its 16 observable features |
| `simulated_env/` | The synthetic estate and its ground truth, the answer key |

**The six discovery sources and what each can and cannot see.** The choice of exactly
six is not arbitrary; each answers one question that no other source answers, and the
blind spots are the point.

Table: The six discovery sources and their systematic blind spots

| Source | Question it answers | Systematic blind spot |
|---|---|---|
| CODE | Does this endpoint exist in the source? | Cannot see whether anything calls it |
| DNS | Is it reachable on the network? | Says nothing about use or ownership |
| GATEWAY | Is it registered with the proxy? | Blind to services addressed directly |
| CICD | Was it deployed by a known pipeline? | Blind to manual and legacy deployments |
| TRAFFIC | Was it actually called? | Blind to anything silent during the window |
| OPENAPI | Is it documented? | Blind to whatever the team forgot to document |

A zombie is the pattern where these answers **disagree**: the code defines it, DNS
resolves it, and the gateway, the specification, the pipeline and the traffic capture
have all never heard of it.

The correlation step turns signals into an inventory record and derives fourteen
discrepancy flags: `UNDOCUMENTED`, `UNREGISTERED`, `SHADOW_CANDIDATE`,
`NO_TRAFFIC_IN_WINDOW`, `EFFECTIVELY_SILENT`, `STALE_6M`, `NO_OWNER`,
`REACHABLE_BUT_UNUSED`, `UNAUTHENTICATED`, `LEGACY_AUTH`, `SENSITIVE_DATA`,
`MARKED_DEPRECATED`, `CODE_UNTOUCHED_1Y` and `NO_PIPELINE_RECORD`. The dataset layer
derives sixteen observable features from the same record for the learned model.

The sequence of a full scan is shown below.

![figure](diagrams/sequence-scan.png "Sequence diagram: a discovery scan")

An endpoint's lifecycle, and the transitions the classifier is detecting, are shown
as a state machine.

![figure](diagrams/state-lifecycle.png "State machine: endpoint lifecycle")

### 3.4 Algorithms

#### 3.4.1 Multi-source correlation

```
DEFINE correlate(signals):
  GROUP signals BY (method, path) normalised across frameworks
  FOR each endpoint group:
    CREATE inventory record
    RECORD which sources observed it        -- presence
    RECORD which sources were consulted     -- so absence can be distinguished
                                            -- from "never asked"
    MERGE attributes, preferring OBSERVED over DECLARED
        (traffic-observed auth outranks gateway-declared auth, because a gateway
         can claim OAuth2 on a route the service also exposes directly with none)
    DERIVE the 14 discrepancy flags from the merged record
  RETURN inventory
```

The `sources_consulted` set is the mechanism that makes the whole system honest. It is
what distinguishes *"traffic saw nothing"* from *"traffic was never collected"*, and
every downstream claim depends on that distinction.

#### 3.4.2 Evidence scoring with abstention

Classification is additive rather than a decision tree. Each of fifteen rules holds a
predicate over the inventory record, a set of source requirements, and a signed weight
per class.

```
DEFINE classify(record, sources_consulted):
  scores <- {ACTIVE: 0, DEPRECATED: 0, ORPHANED: 0, ZOMBIE: 0}
  reasons <- []

  FOR each rule in RULES:                      -- 15 rules
    IF NOT rule.evaluable_with(sources_consulted):
      CONTINUE                                 -- abstain: the source was never asked
    IF rule.predicate(record):
      FOR each class, weight in rule.weights:
        scores[class] <- scores[class] + weight
      APPEND Reason(rule.statement, contribution) to reasons

  label      <- argmax(scores)
  confidence <- softmax(scores, temperature = 3.0)[label]
  RETURN Verdict(label, confidence, reasons, sources_consulted)
```

Two properties follow from the additive form and neither is available from a decision
tree. It **degrades gracefully**: an abstaining rule removes its contribution instead
of breaking a branch. And confidence is derived from the **margin** between the top two
classes, so an endpoint whose evidence genuinely does not distinguish two classes
reports low confidence rather than an arbitrary choice.

The classification logic is shown below.

![figure](diagrams/decision-tree.png "Classification decision logic")

**Abstention has a measurable effect, and it is the project's answer to the question
of what happens when sources are missing.** A rule declares the sources it needs; when
those were never consulted it contributes nothing.

Table: Rule availability and the claims permitted under each source set

| Sources available | Rules usable | What the system can claim |
|---|---|---|
| All six | 15 / 15 | Full lifecycle classification |
| Repository only (CODE, OPENAPI, CICD) | 6 / 15 | Endpoints exist; **no lifecycle claim** |
| Traffic only | 5 / 15 | Usage, but not documentation or ownership |
| Code only | 3 / 15 | Existence only |
| Gateway only | 0 / 15 | Can list endpoints; **classifies nothing** |

The gateway-only row is the important one. With no evaluable rules the system reports
every endpoint as *undetermined* rather than defaulting them to healthy, it has not
classified anything, it has failed to, and it says so.

#### 3.4.3 The removal gate

```
DEFINE assess_removal(verdict, graph, endpoint):
  IF verdict.label is not ZOMBIE:              RETURN blocked("not a zombie")
  IF NOT verdict.is_determinate:               RETURN blocked("insufficient evidence")
  IF verdict.vetoed_by_model:                  RETURN blocked("model objection")
  IF TRAFFIC not in verdict.sources_consulted: RETURN blocked("no usage evidence")

  radius <- graph.blast_radius(endpoint)       -- BFS over alternating CALLS/OWNS edges
  IF NOT radius.is_isolated:                   RETURN blocked("has dependants")

  RETURN may_proceed(radius)
```

Two independent systems must agree. The evidence classifier must call it a zombie and
the dependency graph must find nothing depending on it. A test asserts that no live
endpoint is ever cleared for removal.

![figure](diagrams/hybrid-veto.png "The learned layer as a veto over rule-derived removals")

The learned model participates only through `vetoed_by_model`. It may block a removal
the rules proposed; it can never create one. The rules propose because they need no
training data and are auditable; the model objects because on held-out estates it
produces no false zombies. Both opinions are retained on the verdict, so an auditor
sees that the rules proposed removal and the model objected.

The end-to-end data flow is summarised below.

![figure](diagrams/dfd.png "Data flow diagram: level 1")

### 3.5 Implementation status against plan

Table: Implementation status against the eight-phase plan

| Phase | Scope | State |
|---|---|---|
| 0 | Packaging, CLI, CI, strict typing | Complete |
| 1 | Real GitHub scanning: Semgrep AST, git history, CODEOWNERS | Complete |
| 2 | Dependency graph, blast radius, removal gate | Complete |
| 3 | Scaled dataset, trained model, SHAP attribution | Complete |
| 4 | Safe Kill Simulation, canary, rollback, audit log | Next |
| 5 | REST API and dashboard | Planned |
| 6 | CI/CD enforcement plugin | Planned |
| 7–8 | Security hardening, deployment, observability | Planned |

Phases 0 to 3 of eight are complete, which is the basis for the 50% claim. The two
preconditions for Phase 4, the dependency graph and the removal gate, are both in
place, so the next phase begins from a working foundation rather than from a design.

Engineering state: 85 tests, three ground-truth leakage guards, continuous integration
on Python 3.10 and 3.12, strict type checking, and a documentation self-verification
script that fails the build when a number written in a document stops matching the
running code.

### 3.6 Results

**Classification quality** on the twenty-five-endpoint synthetic estate:

Table: Classification quality on the 25-endpoint synthetic estate

| Class | Precision | Recall | F1 | Support |
|---|---|---|---|---|
| ACTIVE | 0.923 | 1.000 | 0.960 | 12 |
| DEPRECATED | 1.000 | 0.667 | 0.800 | 3 |
| ORPHANED | 1.000 | 1.000 | 1.000 | 2 |
| ZOMBIE | 1.000 | 1.000 | 1.000 | 8 |
| **Macro average** | **0.981** | **0.917** | **0.940** | **25** |

Accuracy is 0.960, twenty-four of twenty-five correct, with **zombie recall 1.000
and zero live endpoints marked for removal**. The single error is a genuinely
DEPRECATED endpoint called ACTIVE: it is the one deprecated endpoint whose team never
set the specification flag, which is exactly the behaviour [2] observed in real
projects. Its confidence is 0.803, identical to correctly classified ACTIVE
endpoints, confidently wrong, because the observable evidence genuinely does not
distinguish the two cases. It is reported as a finding rather than tuned away.

**Comparative evaluation.** The same pipeline code runs under restricted evidence;
only the sources available differ. This is the before-and-after comparison the review
required.

Table: Comparative evaluation: the same pipeline under restricted evidence

| Configuration | Coverage | Rules usable | Zombies caught | Recall |
|---|---|---|---|---|
| Gateway registry only | 76.0% | 0 / 15 | 0 / 8 | 0.0% |
| OpenAPI specification only | 68.0% | 3 / 15 | 0 / 8 | 0.0% |
| Gateway + specification (conventional inventory) | 76.0% | 5 / 15 | 2 / 8 | 25.0% |
| **All six sources, correlated** | **100%** | **15 / 15** | **8 / 8** | **100%** |

A conventional inventory built from a gateway registry and an API specification,
which is what most organisations actually have, finds two of eight zombies.
Correlating all six sources finds all eight. **Four of the six additional endpoints
carry no authentication at all.**

**The learned model,** trained on generated estates and evaluated on thirty-six
held-out estates, split by estate rather than by endpoint so that within-estate
correlations do not appear on both sides:

Table: Rules against the learned model on 36 held-out estates

| On 36 held-out estates | Rules | Model |
|---|---|---|
| Macro-F1 | 0.842 | 0.844 |
| ZOMBIE false positives | 17 | **0** |
| DEPRECATED F1 | 0.674 | 0.514 |

In aggregate the two are indistinguishable, and the aggregate hides what matters. The
rules produce seventeen false zombies on unseen estates; the model produces none. A
false zombie is an outage and a missed one is a line on a report, so the model is used
as a veto rather than as a replacement. That veto has a measured cost which is
reported rather than hidden: on the demo estate it wrongly blocks one genuine zombie,
an unauthenticated debug route with three calls per day that the model reads as still
in use. That endpoint keeps its ZOMBIE label and its full evidence; it simply does not
auto-clear.

**Explanation output.** SHAP values render through the same `Reason` objects the rules
emit, so rule-derived and model-derived reasoning are read in one format:

```
GET /v1/kyc/documents/{id}/raw  ->  ZOMBIE (100%)
   +10.736  last used 3650 days ago
   + 7.692  handler last committed 548 days ago
   + 1.536  0 calls/day
   + 0.136  no owning team recorded
```

That endpoint serves raw identity documents, is unauthenticated, is documented
nowhere and registered nowhere, and has carried no traffic in six months, while DNS
still resolves it. **No single source could have found it.** Code alone establishes
that it exists but not that it is exposed; traffic never saw it; the gateway and the
specification have never heard of it. Only the disagreement identifies it.

**Real repository scanning** is implemented and is not simulated. The system clones a
GitHub repository, extracts routes with Semgrep AST matching across Express, Flask
and Django path conventions, derives staleness from a single `git log` pass and
ownership from CODEOWNERS, and then correctly abstains from lifecycle claims because
the repository supplies no usage evidence. Extraction performance was reduced from
92 seconds to 9.3 seconds by excluding vendored and generated directories.

**Summary.** Five architectural layers are implemented with a one-way dependency
direction that allows sources to be swapped without downstream change. Six discovery
connectors feed a correlator that produces fourteen discrepancy flags, which fifteen
weighted evidence rules turn into an explained four-class verdict, with abstention when
a source was never consulted. A dependency graph computes blast radius, and a removal
gate requires the classifier and the graph to agree. On the synthetic estate the system
achieves 0.960 accuracy and 0.940 macro-F1 with perfect zombie recall and no live
endpoint cleared for removal, and it finds eight of eight zombies where a conventional
gateway-plus-specification inventory finds two.

---

## References

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

[11] G. Brito, A. Hora, M. T. Valente, and R. Robbes, "On the use of replacement messages in API deprecation: an empirical study," *Journal of Systems and Software*, vol. 137, pp. 306–321, 2018, doi: 10.1016/j.jss.2017.12.007.

[12] M. E. Gortney, P. E. Harris, T. Cerný, A. Al Maruf, M. Bures, D. Taibi, and P. Tisnovsky, "Visualizing microservice architecture in the dynamic perspective: a systematic mapping study," *IEEE Access*, vol. 10, pp. 119999–120012, 2022, doi: 10.1109/ACCESS.2022.3221130.

[13] OWASP, "API9:2023 Improper Inventory Management," *OWASP API Security Top 10*, 2023.

[14] Reserve Bank of India, "Cyber Security Framework in Banks," DBS.CO/CSITE/BC.11/33.01.001/2015-16, 2016.

[15] National Institute of Standards and Technology, "Guide to Secure Web Services," NIST SP 800-95, 2007.
