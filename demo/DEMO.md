# 50% Review — Demonstration Script

API Exorcist · B.Tech CSE (Cyber Security), MPSTME/NMIMS

---

## 0. The day before — do this once

Open PowerShell in the project folder and run:

```powershell
powershell -ExecutionPolicy Bypass -File demo\prepare.ps1
```

This installs the package, checks `git` / `semgrep` / `apix` are on PATH,
**pre-clones the demo repository so the live scan needs no network**, warms the
Semgrep cache, and dry-runs every command with timings.

If any line prints `!!` in red, fix it now, not in the room.

**Why pre-clone matters.** `apix scan --github …` takes **~99 seconds**, almost
all of it cloning. The same scan against the pre-cloned copy takes **~9 seconds**
and works with the Wi-Fi off. Use the local form live; mention the GitHub form
exists.

---

## 1. VS Code setup — click by click

Do this *before* the panel is watching.

1. **File → Open Folder…** → select `Capstone\api-exorcist` → **Select Folder**
2. **View → Appearance → Full Screen** (or `F11`) — removes desktop clutter
3. Open a terminal: **Terminal → New Terminal** (or `` Ctrl+` ``)
4. Drag the terminal's top border **upward** so it fills roughly two-thirds of
   the window. The output is the demo; the code is the backdrop.
5. **Make the terminal text large enough to read from the back of the room.**
   Click once inside the terminal, then press **`Ctrl` + `=`** four or five
   times. Check the coverage table still fits on one line — if it wraps, press
   **`Ctrl` + `-`** once.
6. **View → Command Palette** (`Ctrl+Shift+P`) → type `Toggle Light/Dark` →
   choose **Light** if projecting. Dark themes wash out on most projectors.
7. In the Explorer sidebar, pre-open these tabs so you can click straight to
   them without hunting:
   - `src/apix/engine/rules.py`
   - `src/apix/simulated_env/estate.py`
   - `docs/design-document.md`
8. **Close the sidebar** (`Ctrl+B`) once those are open. Reopen only if asked.

**Terminal check.** Run `apix version` — it should print in under a second. If
`apix` is not recognised, run `pip install -e ".[dev,live]"` and reopen the
terminal.

---

## 2. Running the demo

```powershell
powershell -ExecutionPolicy Bypass -File demo\run.ps1
```

Six steps, each waiting for **Enter**. Nothing executes until you press it, so
you can talk for as long as you like on each screen. Total runtime under a
minute; the talking is what fills the slot.

If you would rather type the commands yourself, they are below in order.

---

### Step 1 — The problem

```powershell
apix benchmark
```

**Say:** *"Four configurations. Identical pipeline code — only the evidence
sources differ, so any difference in outcome is caused by the correlation, not
by a different algorithm."*

**Point at:** the recall column.

> A conventional API inventory — gateway plus specification, what most banks
> actually have — finds **0 of 8** zombies. Correlating six sources finds **8**.

**Then point at the rules-usable column.** A gateway registry alone can evaluate
**0 of 14** classification rules. It can list endpoints; it cannot say anything
about them.

**If asked "why zero?"** — because every classification rule needs evidence a
registry does not hold. Rules whose sources were never consulted *abstain*
rather than firing. An earlier version of this benchmark credited the baselines
with traffic evidence they cannot observe, and reported 2 of 8. That was our
bug, and correcting it made our own result look better, which is why it is
written up in the design document rather than quietly changed.

---

### Step 2 — Discovery, classification and explanation

```powershell
apix scan
```

**Say:** *"Six connectors, each a partial and imperfect witness. No source sees
more than 76% of the estate. The correlation is what surfaces the rest."*

**Point at:** a `[#####]` finding, and read its `because:` block aloud.

> `GET /v1/kyc/documents/{id}/raw` — no meaningful traffic, absent from both the
> spec and the gateway, still resolvable via DNS, unauthenticated. Raw identity
> documents, on an endpoint nobody knows exists.

**This is the answer to "can it use explainable AI".** Every verdict carries
signed evidence contributions — the same additive shape SHAP produces, so the
rule layer and the model layer will share one renderer.

---

### Step 3 — Why removal is dangerous

```powershell
apix impact "GET /v2/accounts/{id}"
```

**Say:** *"Before anything can be removed, we have to know what breaks."*

> Three direct callers. **Nine services. Five hops deep.** Twelve endpoints
> degraded.

**The architectural point:** the depth is not known in advance. In SQL that is a
recursive CTE whose cost grows per hop; in Cypher it is one variable-length path
match. That is why the dependency layer is a graph.

---

### Step 4 — How removal is made safe

```powershell
apix impact
```

**Say:** *"Both signals must agree. The classifier says an endpoint looks dead;
the graph says nothing depends on it. Either alone is not enough."*

> All 8 zombies are **isolated** — nothing observed calls them. That is *why*
> they are safe, not a coincidence. All 3 deprecated endpoints still have live
> callers and would be blocked even if the classifier misjudged them.

**Say the limitation before they find it:** *"Isolated means no dependency was
observed, not that none exists. A caller silent during the capture window is
invisible here. That is exactly why this is a gate and not a proof, and why the
approval step and canary rollout still come after it."*

---

### Step 5 — It works on real code

```powershell
apix scan --local demo\repos\full-stack-fastapi-template --limit 3
```

**Say:** *"That was the simulation. This is a real repository off GitHub."*

> 23 real routes. 1,497 commits walked for per-file staleness. Semgrep AST
> matching — a route written inside a comment or a string literal is **not**
> counted, which a regular expression cannot distinguish.

**Point at `sources UNAVAILABLE` and `Lifecycle classification: NOT AVAILABLE`.**

> A repository has no gateway, no traffic sensor, no DNS. All four lifecycle
> classes are defined in terms of *use* — so without a usage source we report
> **findings**, not a verdict. Nothing here is a removal candidate.

That paragraph is the strongest thing in the demo. A tool that says what it
cannot know is a tool a bank can deploy.

**Mention, do not run:** `apix scan --github owner/repo` does the same thing
straight from GitHub; it takes about 99 seconds, nearly all of it cloning.

---

### Step 6 — It is tested

```powershell
python -m pytest -q
```

> **64 tests.** Including two ground-truth leakage guards, the removal gate, and
> a test asserting no live endpoint is ever cleared for removal.

**Then, if there is time,** click to `src/apix/engine/rules.py` in VS Code and
scroll to `RULES`. Say: *"Fourteen evidence rules. The weights were set from the
class definitions before accuracy was measured, and deliberately never tuned
against the answer key — otherwise the number would mean nothing."*

---

## 3. What was asked, and what was delivered

### The three concerns raised at the initial review

| # | Concern | Status | Where to show it |
|---|---|---|---|
| 1 | Identify the dataset for the ML engine | **Delivered** (schema; volume is open) | `apix dataset` — 16 features, 4 classes, leakage-guarded |
| 2 | Can it use explainable AI | **Delivered and running** | Step 2 — every verdict carries signed evidence |
| 3 | Comparative before/after study | **Delivered** | Step 1 — `apix benchmark`, reproducible figures |

**On concern 1, be precise and do not overclaim.** The dataset is *identified*,
schema-complete, and leakage-guarded — but it is **25 rows**, and `ORPHANED` has
two examples. That cannot train a model. What exists is the schema, the
provenance, and the labelling method; the volume is the open item, and a
parameterised estate generator closes it. **No model has been trained yet** —
the 0.960 accuracy is the *rule* classifier, not machine learning. Say that
plainly; the distinction is one a panel will probe.

### The three 50% deliverables

| Deliverable | Status |
|---|---|
| Literature review, 5+ papers, shown utilised in the implementation | **Done** — 9 peer-reviewed sources, all verified against DBLP, with a traceability matrix mapping each to the module it justifies |
| Design document, structural and behavioural | **Done** — 9 sections, 9 diagrams (component, class, deployment, sequence, two state machines, decision logic, DFD, interface) |
| ~50% of implementation | **Done** — see below |

### What is actually built

| Capability | State |
|---|---|
| Six-source discovery with realistic blind spots | Done |
| Multi-source correlation → unified inventory, 15 flags | Done |
| Four-class rule classifier, deterministic and auditable | Done |
| Per-verdict explanations with signed evidence | Done |
| Source-availability handling — abstention, indeterminacy | Done |
| Evaluation harness — per-class P/R/F1, confusion matrix | Done |
| Comparative before/after benchmark | Done |
| Labelled dataset for the ML engine | Done (schema) |
| **Real GitHub repository scanning** — Semgrep AST, git history, CODEOWNERS | Done |
| **Dependency graph + blast radius**, Neo4j backend | Done |
| **Removal gate** — classifier and graph must both agree | Done |
| Packaging, CLI, CI on 3.10/3.12, mypy strict, 64 tests | Done |

### What is left

| Remaining | Phase | Notes |
|---|---|---|
| Scaled dataset + trained model + SHAP | 3 | The estate generator is the first step |
| Safe Kill Simulation — canary, rollback, audit log | 4 | The research contribution |
| REST API + dashboard | 5 | First thing to cut if time runs short |
| CI/CD enforcement plugin | 6 | The prevention half |
| Security hardening, deployment, observability | 7–8 | |
| Paper [2] Cassieri | — | Last one outstanding; 9 of 10 now in `docs/papers/` |

---

## 4. Questions to expect

**"Is any of this real, or is it all simulated?"**
The architecture is real; the estate is synthetic. Step 5 scans a real GitHub
repository with no simulation involved. The estate exists because measuring
detection accuracy requires ground truth, and no organisation publishes a real
API inventory — it would be publishing a map of its attack surface.

**"Why is the dataset synthetic?"**
No public zombie-API corpus exists and there is a structural reason it never
will. Generating it is not a shortcut around an available dataset; it is the
only way to obtain ground-truth labels. State the limitation plainly: the
defensible claim is *"the engine recovers known decay patterns from partial,
disagreeing evidence"*, never *"validated on production bank data"*.

**"You got 96% — isn't that suspiciously high?"**
It is a rule classifier on 25 endpoints, and the weights were fixed before
accuracy was measured. The single error is instructive: `POST /v1/kyc/aadhaar/ekyc`
is genuinely deprecated but classified active — it is the one deprecated
endpoint whose team never set the OpenAPI flag, exactly the behaviour Cassieri
et al. documented. Its confidence is 0.803, the *same* as correct actives: the
classifier is confidently wrong, because the observable evidence genuinely does
not distinguish the cases. No model fixes that; only a new signal would.

**"What if it deletes something important?"**
Three independent barriers. The classifier must say ZOMBIE *and* have consulted
a usage source. The graph must show nothing depends on it. And Safe Kill is
canary-and-rollback, never immediate deletion. A test asserts no live endpoint
is ever cleared, and CI fails the build if that ever changes.

**"Why not just use machine learning?"**
A new deployment has zero labels on day one. If the product needed a trained
model it could not onboard a single customer. The rule engine works immediately
and generates the labels the model later learns from. In deployment the audit
log becomes the training set — every approved kill and every rollback is a
human-verified label.

**"How much of this did AI write?"**
Answer honestly and specifically. The value you add is the review, the
architectural decisions, and being able to defend every one of them — which is
what this document exists to let you do.

---

## 5. If something goes wrong

| Symptom | Fix |
|---|---|
| `apix` not recognised | `pip install -e ".[dev,live]"`, then reopen the terminal |
| `apix scan` "fails" with exit code 1 | **That is correct.** Exit 1 means zombies were found, so it works as a CI gate |
| Semgrep slow or missing | Skip Step 5. Everything else needs no Semgrep |
| No network | Irrelevant — the whole demo runs offline after `prepare.ps1` |
| Output wraps and looks messy | `Ctrl` + `-` in the terminal to reduce font size |
| A command errors live | Say *"the reproducible figures are in `data/benchmark.json`"* and open it. Do not debug in front of the panel |

---

## 6. Timing

| Step | Runtime | Talk |
|---|---|---|
| 1 Benchmark | 0.3s | 3 min |
| 2 Scan | 0.3s | 4 min |
| 3 Blast radius | 0.3s | 2 min |
| 4 Removal gate | 0.3s | 3 min |
| 5 Real repository | 9s | 4 min |
| 6 Tests | 2s | 2 min |

**Under 15 seconds of execution.** Everything else is you talking, which is what
is being assessed. Do not rush the explanations to reach the next command.
