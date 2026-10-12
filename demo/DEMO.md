# Final Presentation: Demonstration Script

API Exorcist · B.Tech CSE (Cyber Security), MPSTME/NMIMS

---

## 0. The day before — do this once

Open PowerShell in the project folder and run:

```powershell
powershell -ExecutionPolicy Bypass -File demo\prepare.ps1
```

This installs the package with the API, checks `git` / `semgrep` / `apix` and
the dashboard build, **pre-clones the demo repository so the live scan needs no
network**, warms the Semgrep cache, dry-runs every command with timings, checks
enforcement gives its scripted result, **moves the old audit log into
`data\archive\` so the demo starts with an empty one**, checks port 8600 is
free, and runs the full test suite. About three minutes.

If any line prints `!!` in red, fix it now, not in the room. Run it again an hour
before presenting if you rehearsed in between: it resets the audit log each time.
Red pip lines about *other* packages (transformers, huggingface-hub) are your
Python environment, not this project, and are harmless.

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

Ten slides, each waiting for **Enter**. Nothing executes until you press it, so
you can talk for as long as you like on each screen.

| Slide | Runbook step below |
|---|---|
| 1 Benchmark, 2 Scan, 3 Blast radius, 4 Gate | Steps 1 to 4 |
| 5 Safe Kill, three runs | Step 4b |
| 6 Dashboard | Step 4c. The server opens in its own window and the browser opens by itself; the sign-in token is **already on your clipboard**, so press `Ctrl+V` in the sign-in box |
| 7 Enforcement | Step 4d |
| 8 Metrics | Step 4e, read with the same token, no copying |
| 9 Real repository; 10 the test suite | Steps 5 and 6 |

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
> actually have — finds **2 of 8** zombies. It classifies those two correctly; it
never discovers the other six. Correlating six sources finds **8**.

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

> Three direct callers. **Nine services. Five hops deep.** Thirteen endpoints
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

### Step 4b: Safe Kill, and the hidden caller

```powershell
apix safekill "GET /v1/cards/{id}/pin" --approve-as shivansh --hidden-caller "GET /v1/cards/{id}/pin"
```

**Say:** *"The gate cleared this endpoint. Now suppose a month-end batch job calls it
every 25 days, and the traffic capture never saw it. Classifier and graph both missed
it. Watch what Safe Kill does."*

> The 90-day shadow names `month-end-recon-batch` three times and **rejects** the
> removal. Nothing was refused. Nobody was harmed.

**Then shorten the window, and say why it is wrong:**

```powershell
apix safekill "GET /v1/cards/{id}/pin" --approve-as shivansh --hidden-caller "GET /v1/cards/{id}/pin" --slowest-caller-days 3 --seed 3
apix safekill "GET /v1/cards/{id}/pin" --approve-as shivansh --hidden-caller "GET /v1/cards/{id}/pin" --slowest-caller-days 3 --seed 1
```

> Seed 3: the shadow misses it, the canary refuses one real request, and the
> controller **rolls back automatically**. Seed 1: it slips through everything and is
> **retired into an outage**. At that window this happens 15 times in 40.

**Say:** *"The 90 days is not a guess. To be 95% sure of catching a caller that calls
once a month you have to watch for ln(20) times 30 days: the rule of three. These seeds
were chosen to show each branch; the evaluation measures how often each happens."*

**If asked "why not just a canary?":** *"We measured it. A canary with no shadow has
no baseline for anonymous traffic, so scanner noise triggers rollbacks. It wrongly
keeps 118 dead endpoints running, 15% of the attack surface, and refuses 67 real
requests before it catches the live ones."*

---

### Step 4c: The dashboard, and approval over HTTP

```powershell
apix serve --as shivansh
```

Open the address it prints (`http://127.0.0.1:8600`) and paste the one-time token it
prints. Show, in order:

1. **Overview.** 25 endpoints, 8 zombies, and the banner on every page saying the
   estate is simulated.
2. **Endpoints**, then click `GET /v1/kyc/documents/{id}/raw`. The signed evidence
   bars are the verdict's reasons; the source chips show which of the six sources
   saw it, crossed out where they did not. *"Absence is the evidence."*
3. **Safe Kill.** Start a shadow on that endpoint and on
   `POST /v1/debug/payments/replay`. The KYC shadow is clean, so Approve is live.
   The debug route saw 266 anonymous requests, so **Approve stays disabled** until
   the risk is accepted in writing.
4. Approve the KYC endpoint. Its path runs nominated to retired, **decided by
   shivansh**.
5. **Audit log**, then "Verify the whole chain". The approval entry's actor is the
   name bound to the token.

**Say:** *"The name on that approval comes from the token, not from anything the
browser sends. The API rejects a request that even tries to include an approver
field, so the audit log cannot be told who approved something."*

**If asked "is the inventory public?":** *"No. Every route except a health check
needs a token, reads included, because a list of unauthenticated endpoints is a
map for an attacker."*

---

### Step 4d: Enforcement, the prevention half

```powershell
python demo\make_enforce_demo.py demo\enforce-demo
apix enforce --repo demo\enforce-demo --base main
```

The script builds a small repository whose feature branch breaks every rule once.

> Four errors and a warning: an undocumented DELETE, a debug route that is
> undocumented **and** unowned, and `GET /v1/legacy/export` removed from the spec
> with its handler left behind, flagged as **"Zombie in the making"**. The health
> check passes, exempt with its reason shown, because that exemption is in the
> policy on `main`.

**Say:** *"Every zombie in our estate was made the same way: someone deleted the
route from the documentation and nobody deleted the code. This catches it at the
commit that does it. And it only judges the change, so a bank with four hundred
undocumented endpoints can switch it on today without every pull request failing."*

If asked *"can't a developer just add their endpoint to the exemption list?"*:
*"Not in the same pull request. The policy is read from main, never from the
change being judged. An edit to it is flagged and only applies after it has been
reviewed and merged. Our security review found that hole in the first version."*

---

### Step 4e: Running it as a service

With `apix serve` still running from step 4c, in a second terminal (paste the
token it printed in place of `TOKEN`):

```powershell
curl.exe -s -H "Authorization: Bearer TOKEN" http://127.0.0.1:8600/metrics | Select-String "apix_endpoints|apix_audit_chain_ok|auth_failures"
```

> The estate's composition, the audit chain's health, and failed sign-ins by
> reason, in the format every bank's monitoring already scrapes.

**Say:** *"In production this runs as one container: non-root, read-only
filesystem, and it refuses to start without configured credentials. The metric
to alert on is `apix_audit_chain_ok`: if anyone edits the audit log, it drops to
zero."* Build the image before the review if you want to show it; the build
needs a network and takes about a minute.

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
python -m pytest
```

(Not `pytest -q`: the configuration already adds `-q`, and doubling it hides the
summary line. The runner leaves out the two tests that drive real Semgrep, which
take 45 seconds on their own; `prepare.ps1` and CI run all of them.)

> ** tests.** Including the ground-truth leakage guards, the removal gate, a
> test asserting no live endpoint is ever cleared for removal, and every Safe Kill
> safety path forced and asserted: rejection, denial, automatic rollback, and
> tamper detection in the audit chain, plus every API route checked for
authentication, a pull request that tries to exempt itself, and four processes
writing the audit log at once.

**Then, if there is time,** click to `src/apix/engine/rules.py` in VS Code and
scroll to `RULES`. Say: *"Fifteen evidence rules. The weights were set from the
class definitions before accuracy was measured, and deliberately never tuned
against the answer key — otherwise the number would mean nothing."*

---

## 3. What was asked, and what was delivered

### The three concerns raised at the initial review

| # | Concern | Status | Where to show it |
|---|---|---|---|
| 1 | Identify the dataset for the ML engine | **Delivered**, and a model trained on it | `apix dataset`; README, "The learned model" |
| 2 | Can it use explainable AI | **Delivered and running** | Step 2 — every verdict carries signed evidence |
| 3 | Comparative before/after study | **Delivered** | Step 1 — `apix benchmark`, reproducible figures |

**On concern 1, be precise and do not overclaim.** The hand-written estate is
**25 rows**, too few to train anything; the volume comes from the estate
generator (120 estates), and the model is trained on that. Two numbers are easy
to confuse, so keep them apart: **0.960 accuracy is the rule classifier** on the
25-endpoint estate. On 120 generated estates the trained model edges the rules on
macro-F1 (0.861 against 0.843) and, more importantly, produces no false zombies
where the rules produce 14, which is why it is used as a **veto** over removals
rather than as the decision-maker. All of it is synthetic; say so.

### The documents

| Deliverable | Status |
|---|---|
| Literature review, shown utilised in the implementation | **Done**: peer-reviewed sources verified against DBLP, with a traceability matrix mapping each to the module it justifies |
| Design document, structural and behavioural | **Done**, with an as-built note for every phase where the build departed from the design, and why |
| Implementation | **All eight phases built**: see below |

### What is actually built

| Capability | State |
|---|---|
| Six-source discovery with realistic blind spots | Done |
| Multi-source correlation → unified inventory, 14 flags | Done |
| Four-class rule classifier, deterministic and auditable | Done |
| Per-verdict explanations with signed evidence | Done |
| Source-availability handling — abstention, indeterminacy | Done |
| Evaluation harness — per-class P/R/F1, confusion matrix | Done |
| Comparative before/after benchmark | Done |
| Labelled dataset, estate generator, trained model with SHAP | Done |
| **Real GitHub repository scanning** — Semgrep AST, git history, CODEOWNERS | Done |
| **Dependency graph + blast radius**, Neo4j backend | Done |
| **Removal gate** — classifier and graph must both agree | Done |
| **Safe Kill**: rule-of-three shadow, named approval, canary, automatic rollback | Done |
| **Hash-chained audit log**, tamper-evident, every transition recorded | Done |
| **REST API**: hashed tokens, viewer and approver roles, approval over HTTP | Done |
| **Dashboard**: React + TypeScript, strict CSP, named approval | Done |
| **CI/CD enforcement**: a GitHub Action that judges only what a pull request changes | Done |
| **Container image**, Prometheus metrics, JSON logs, a security review with its fixes | Done |
| Packaging, CLI, CI on 3.10/3.12, mypy strict,  tests | Done |

### What is left, and why it is not in the repository

| Remaining | Why |
|---|---|
| A gateway plugin implementing `EnforcementBackend` for a real gateway | Needs a bank's gateway to plug into; the interface it implements is built and tested |
| An approval queue in a database, so the API can run as more than one replica | One replica is enough for a deployment of this size; stated as a limitation |
| Anchoring the audit chain's head outside the operator's control | A deployment decision (WORM bucket, SIEM); the chain is what makes one small anchor sufficient |
| Paper [2] Cassieri | Cited and used; the PDF is the one not yet in `docs/papers/` |

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
Four independent barriers. The classifier must say ZOMBIE *and* have consulted
a usage source. The graph must show nothing depends on it. A 90-day shadow must
see no named caller, and a named human must approve. Only then does a canary
start, and it rolls back automatically on the first breach. Across 120 estates
the gate alone would have removed 49 live endpoints; with Safe Kill, none.

**"Why not just use machine learning?"**
A new deployment has zero labels on day one. If the product needed a trained
model it could not onboard a single customer. The rule engine works immediately
and generates the labels the model later learns from. In deployment the audit
log becomes the training set — every approved kill and every rollback is a
human-verified label.

**"Is this production-ready?"**
The software is built the way a bank would need it: tokens stored hashed, every
route authenticated, a tamper-evident audit log, a hardened container, metrics,
and a security review whose findings were fixed with tests. What it has not done
is run against a real bank's traffic, and nothing here claims it has. The three
items under "What is left" are what stands between this and a pilot.

**"What stops a developer exempting their own endpoint?"**
The policy is read from `main`, never from the pull request being judged. The
first version read it from the pull request; the security review found that and
it was fixed, with a test that fails if it ever comes back.

**"How much of this did AI write?"**
Answer honestly and specifically. The value you add is the review, the
architectural decisions, and being able to defend every one of them — which is
what this document exists to let you do.

---

## 5. If something goes wrong

| Symptom | Fix |
|---|---|
| `apix` not recognised | `pip install -e ".[dev,live,api]"`, then reopen the terminal |
| Dashboard: "port 8600 in use" | Close the previous server window (or any other `apix serve`), then rerun `run.ps1` |
| Dashboard sign-in rejected | The token on the clipboard was replaced. Close the server window and rerun slide 6; a fresh token is minted each time |
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
| 4b Safe Kill (three runs) | 1s | 4 min |
| 4c Dashboard | 2s | 4 min |
| 4d Enforcement | 10s | 3 min |
| 4e As a service | 1s | 2 min |
| 5 Real repository | 9s | 4 min |
| 6 Tests | 60s | 1 min, talk over it |

**About 25 seconds of execution, plus a minute of tests.** Talk over the test run,
or skip slide 10 if time is short. Everything else is you talking, which is what
is being assessed. Do not rush the explanations to reach the next command.
