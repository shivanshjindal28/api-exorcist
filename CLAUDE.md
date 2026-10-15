# API Exorcist — working notes

Autonomous discovery and safe elimination of zombie, shadow and orphaned APIs.
B.Tech CSE (Cyber Security) capstone, MPSTME/NMIMS, 2026–2027. Built to be
shippable, not only demonstrable.

## Commands

```bash
pip install -e ".[dev,live,ml]"   # first-time setup
apix scan                         # discover, classify, explain
apix impact                       # dependency graph + removal gate
apix benchmark                    # comparative before/after evaluation
apix train --estates 120 --save   # train the model, compare against rules
apix safekill --approve-as NAME   # shadow, approval, canary, rollback
apix safekill --evaluate          # Safe Kill vs the gate alone, shadow sweep
apix serve                        # THE APP: opens the browser signed in (F5 in VS Code)
apix token NAME --role approver   # mint an API token; stores only its hash
apix enforce --base origin/main   # judge a change's API surface (Phase 6)
docker build -t api-exorcist .    # the deployable image (Phases 7-8)
cd dashboard && npm ci && npm test && npm run build   # dashboard, 40 Vitest tests
pytest                            # 287 tests
ruff check . && mypy              # lint + strict types
APIX_REALWORLD=1 pytest tests/test_realworld.py   # real repos, known answers (network, ~6 min)
python demo/prescan.py OWASP/crAPI   # scan via the app's engine into data/scans (demo fallback)
python demo/make_access_log.py data/scans/<id>.json demo/synthetic-access.log   # SYNTHETIC logs for the Usage demo

python docs/render_diagrams.py    # mermaid -> png (run before the two below)
python docs/build_docx.py         # literature review, design doc, interim report
python docs/build_pptx.py         # the review presentation
python docs/finalise_docx.py docs/*.docx   # update TOC + figure/table page nos
python docs/verify_claims.py      # documented figures vs the running code
```

`finalise_docx.py` drives Word itself, because python-docx writes a TOC *field*
and cannot compute the page numbers inside it. Run it last, after build_docx.
Office here needs late-bound COM (`win32com.client.dynamic`); early binding
fails with TYPE_E_CANTLOADLIBRARY.

Submission artefacts (`docs/*.docx`, `docs/*.pptx`) are generated and gitignored.
The Markdown and the builders are the source of truth.

## Reproducing CI before you push

**CI installs only `.[dev]`.** A local machine with the ML extras will pass things
CI fails — this has happened twice. To check against the environment CI actually
has:

```bash
python -m venv .ci-venv && .ci-venv/bin/pip install -e ".[dev]"
.ci-venv/bin/python -m ruff check . && .ci-venv/bin/mypy && .ci-venv/bin/pytest
```

On Windows the interpreter is `.ci-venv\Scripts\python.exe`. Add `.ci-venv/` to
`.gitignore` if you keep it around.

Both failures this caused were the same shape: code that imports an optional
dependency, and a mypy override list that had not been updated to match.

## Three rules that are not negotiable

**1. Never let simulated data pass as real.** The architecture is real; the
estate is synthetic. The defensible claim is *"the engine recovers known decay
patterns from partial, disagreeing evidence"* — never *"validated on production
bank data."* Every README, paper section and demo script says which is which.

**2. Ground truth must never reach detection code.** `true_label` and
`decay_story` are forbidden inputs to connectors, the correlator, feature
extraction and the classifier. Two guards enforce this:

- `engine/`, `inventory/` and `safekill/` must not *import* `simulated_env` at all
  (AST check). For `safekill/` this is sharper still: a controller that could read
  the estate could "detect" a hidden caller by reading the answer.
- `connectors/` and `dataset/` may import it — in simulation mode it is their
  data source — but must never reference the answer-key fields (token check)

An early OpenAPI connector derived a feature from `true_label`. It would have
silently inflated accuracy and invalidated every number in the paper. If a guard
ever needs weakening to make a change pass, the change is wrong.

**3. No unauthorised external scanning.** The product shape is *"connect your
GitHub org, your gateway, your CI/CD"*. URL scanning is two-tier: passive
sources (published spec, CT logs, public DNS, the site's own JS) for any URL;
active probing only after a DNS TXT record proves domain ownership.

## Design invariants

- **Connectors emit observations, never verdicts.** They yield `DiscoverySignal`
  and do not classify.
- **Absence is evidence.** The inventory records which sources did *not* see an
  endpoint. That pattern is what identifies a zombie.
- **Observed beats declared.** Traffic-observed auth outranks gateway-declared
  auth, because a gateway can claim OAuth2 on a route the service also exposes
  directly with no auth.
- **Every verdict carries its reasons.** `Verdict` composes `list[Reason]` with
  signed contributions — never a bare label. It serialises straight into the
  audit log and renders straight in the dashboard.
- **ORPHANED is never actionable.** Orphaned endpoints carry real traffic;
  removing one causes an outage. Only ZOMBIE enters the Safe Kill queue. A test
  asserts no live endpoint is ever marked for removal.
- **Rules decide, the model advises.** The rule layer works day one with zero
  training data — which is what lets the product onboard a customer at all.

## Classifier weights

Set from the class definitions *before* accuracy was measured, and deliberately
never tuned against ground truth. Hand-fitting them to a 25-endpoint estate
would produce a number that means nothing. If you change a weight, re-run
`apix benchmark` and report what actually happens.

## Known-good results (CI asserts these)

Accuracy 0.960, macro-F1 0.940, zombie recall 1.000, zero live endpoints marked
for removal. Conventional inventory catches 2 of 8 zombies; correlation
catches 8.

The single misclassification — `POST /v1/kyc/aadhaar/ekyc`, truly DEPRECATED,
called ACTIVE — is a documented finding, not a bug to tune away. It is the one
deprecated endpoint whose team never set the OpenAPI flag, exactly what
Cassieri et al. [2] observed. Its confidence is 0.803, identical to correct
ACTIVEs: confidently wrong, because the observable evidence genuinely does not
distinguish the cases.

## Test against real repositories, not only our own fixtures

Fixtures written by whoever wrote the scanner are shaped like the scanner, so
they keep passing while real projects break. In October 2026 a seven-repository
check found: Windows refused long paths (crAPI, petclinic), Connexion and
API-first Spring handlers were invisible (0 of 14, 0 of 37), OpenAPI tags were
read as owners, and crAPI's two real zombies came out as ordinary rows. Every
scan read "nothing distinguishes these endpoints". `tests/test_realworld.py`
now checks known answers on real projects, including what must NOT be flagged.
Run it before any change to extraction, clients, evidence or ranking, and add a
repository when a new framework or false positive turns up.

## Environment gotchas

- **The shell here mangles backslashes in heredocs.** `\b` written through a
  bash heredoc landed in `verify_claims.py` as a literal backspace byte (0x08),
  so three regexes silently matched nothing for weeks. Write files containing
  backslashes with the file tools, not heredocs. `verify_claims.py` now fails on
  control characters in its own source and on any pattern matching nothing.

- **Windows PowerShell 5.1 corrupts source files.** `Get-Content | Set-Content
  -Encoding utf8` double-encodes UTF-8 and adds a BOM — it mangled em-dashes in
  `rules.py` once. Use the editor tools or Python for text edits, never a
  PowerShell round-trip. A pre-commit hook now catches BOMs.
- **PowerShell reports exit 255 on native stderr** even when the command
  succeeded. Check `git log` rather than trusting the exit code.
- **Git Bash rewrites container paths.** `-v vol:/data` became a Windows path
  and Docker refused it. Prefix docker commands that take container paths with
  `MSYS_NO_PATHCONV=1`.
- **The repo lives inside OneDrive.** Syncing a live `.git` directory can
  corrupt it; `.git` should be excluded from sync.
- **Remote:** `origin` is https://github.com/shivanshjindal28/api-exorcist (PUBLIC:
  every push is publishing). CI runs on main, phase* branches and pull requests.
  No `gh` CLI here; plain git over HTTPS works through Git Credential Manager.
  CI only runs on what is pushed, so a check that passes locally is unproven there.

## Layout

```
src/apix/
  config.py        settings from environment, defaults that need no infra
  connectors/      six discovery sources, each a partial and imperfect witness
  ingestion/       LocalBus (default) / Kafka / Elasticsearch
  inventory/       multi-source correlation -> unified inventory + 14 flags
  engine/          verdict types, rule classifier, explanations
  graph/           dependency graph, blast radius, removal gate
  safekill/        shadow, approval, canary, rollback, hash-chained audit
  api/             REST API: hashed bearer tokens, roles, approval over HTTP
  api/observe.py   Prometheus metrics and JSON logs; labels are route templates
  scanning/        browser scans: uploaded folder or GitHub link, background jobs;
                   exports (SARIF/CSV/OpenAPI), retirement plans, drift, sensitivity
  traffic/         access-log import: parse nginx/ALB/JSON logs, usage -> lifecycle
  enforce/         CI enforcement; action.yml at the repo root runs it on PRs
  api/dashboard/   the BUILT dashboard (committed; CI checks it is current)
  evaluation/      metrics, the comparative benchmark, Safe Kill evaluation
  dataset/         labelled dataset for the ML engine
  simulated_env/   the estate and its ground truth (the answer key)
dashboard/         React + TypeScript source for the dashboard
docs/              literature review, design document, source papers
```

Dependency direction is one-way: connectors know nothing of ingestion, and the
engine never reaches back to a data source. That is what makes the simulated
estate swappable for live sources without touching anything downstream.
