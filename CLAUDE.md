# API Exorcist — working notes

Autonomous discovery and safe elimination of zombie, shadow and orphaned APIs.
B.Tech CSE (Cyber Security) capstone, MPSTME/NMIMS, 2026–2027. Built to be
shippable, not only demonstrable.

## Commands

```bash
pip install -e ".[dev]"   # first-time setup
apix scan                 # discover, classify, explain
apix benchmark            # comparative before/after evaluation
pytest                    # 32 tests
ruff check . && mypy      # lint + strict types
```

## Three rules that are not negotiable

**1. Never let simulated data pass as real.** The architecture is real; the
estate is synthetic. The defensible claim is *"the engine recovers known decay
patterns from partial, disagreeing evidence"* — never *"validated on production
bank data."* Every README, paper section and demo script says which is which.

**2. Ground truth must never reach detection code.** `true_label` and
`decay_story` are forbidden inputs to connectors, the correlator, feature
extraction and the classifier. Two guards enforce this:

- `engine/` and `inventory/` must not *import* `simulated_env` at all (AST check)
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

## Environment gotchas

- **Windows PowerShell 5.1 corrupts source files.** `Get-Content | Set-Content
  -Encoding utf8` double-encodes UTF-8 and adds a BOM — it mangled em-dashes in
  `rules.py` once. Use the editor tools or Python for text edits, never a
  PowerShell round-trip. A pre-commit hook now catches BOMs.
- **PowerShell reports exit 255 on native stderr** even when the command
  succeeded. Check `git log` rather than trusting the exit code.
- **The repo lives inside OneDrive.** Syncing a live `.git` directory can
  corrupt it; `.git` should be excluded from sync.
- No GitHub remote is configured yet.

## Layout

```
src/apix/
  config.py        settings from environment, defaults that need no infra
  connectors/      six discovery sources, each a partial and imperfect witness
  ingestion/       LocalBus (default) / Kafka / Elasticsearch
  inventory/       multi-source correlation -> unified inventory + 15 flags
  engine/          verdict types, rule classifier, explanations
  evaluation/      metrics + the comparative benchmark
  dataset/         labelled dataset for the ML engine
  simulated_env/   the estate and its ground truth (the answer key)
docs/              literature review, design document, source papers
```

Dependency direction is one-way: connectors know nothing of ingestion, and the
engine never reaches back to a data source. That is what makes the simulated
estate swappable for live sources without touching anything downstream.
