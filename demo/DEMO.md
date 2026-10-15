# Final Presentation: Demonstration Script

API Exorcist · B.Tech CSE (Cyber Security), MPSTME/NMIMS

Everything in this demo happens in the browser. The terminal is used once, to
start the app.

---

## 0. The day before: prepare once

Open PowerShell in the project folder and run:

```powershell
powershell -ExecutionPolicy Bypass -File demo\prepare.ps1
```

It installs the package with the live scanner and the API, checks `git`,
`semgrep` and the dashboard build, **moves earlier scans and audit logs into
`data\archive\`** so the "All scans" list starts clean, and then **scans three
real repositories from GitHub through the app's own scan engine**: OWASP crAPI,
VAmPI and spring-petclinic-rest. Those finished reports appear under "All
scans" in the browser, so if the room's network fails you still have real
results to open. It ends with the full test suite. About five minutes, most of
it cloning.

If any line prints `!!` in red, fix it now, not in the room. Red pip lines about
*other* packages are your Python environment, not this project.

**Timings to expect live:** VAmPI about 10 seconds, crAPI about 50 seconds,
petclinic about two minutes (cloning dominates). Start crAPI live and talk while
it runs; open the pre-scanned petclinic rather than waiting for it.

---

## 1. Starting the app

In VS Code: open the `api-exorcist` folder and press **F5**. Or, in a terminal:

```powershell
powershell -ExecutionPolicy Bypass -File demo\run.ps1
```

The browser opens **already signed in** as you. If port 8600 is taken, the app
picks the next free port and prints it; nothing to fix.

Before the panel is watching: browser full screen (`F11`), zoom to 125% if the
room is large, light theme if projecting.

---

## 2. The walkthrough

### Step 1: The question (no clicks, 1 minute)

**Say:** *"A zombie API is an endpoint that is still deployed and reachable but
that nobody uses or maintains. A shadow API is one nobody documented. OWASP
lists this as API9, improper inventory management. Banks have hundreds of these,
and the hard part is not finding endpoints, it is knowing which ones are dead
and removing them without causing an outage."*

### Step 2: Scan a real repository, live (3 minutes)

On **New scan**, option 2, paste `https://github.com/OWASP/crAPI` and press
**Scan repository**. The progress lines stream while it clones and parses.

**Say while it runs:** *"crAPI is OWASP's deliberately vulnerable API. Nothing
from the repository is executed: we read its code with Semgrep, its OpenAPI
specification and its git history, and we read what its own web app calls."*

When it finishes, on **Overview**:

> 62 endpoints. **6 zombie candidates, 2 likely zombies**, at the top:
> `POST .../v2/check-otp` and `POST .../v2.7/user/login-with-token`.

Open the **Zombie candidates** card and read the reasons on `v2/check-otp`
aloud:

> +3 a newer version exists, `v3/check-otp`. +2 the project's own client calls
> the newer version and never this one. +2 its clients call 24 other identity
> endpoints, but not this one. +1 unchanged for two years while the project is
> still changing.

**Then say why it matters:** *"This is not a cosmetic finding. In crAPI's own
code the v3 OTP check locks after 10 wrong attempts; the v2 check has no limit,
so a six-digit OTP can be brute-forced. The fix was shipped, and the old
endpoint was left running beside it. That is exactly how a zombie happens."*

**Be precise:** these are labelled *candidates*, suspected not proven. A
repository has no traffic, so the scan never claims a lifecycle label it cannot
prove (see Step 7).

### Step 3: Endpoints (1 minute)

**Endpoints** tab: every route with where it is defined (file and line), whether
the specification documents it, its owner and when its code last changed.
Filter to undocumented: 18 of them, shadow APIs by definition.

### Step 4: Dependency graph (2 minutes)

**Dependency graph** tab: services, the calls between them, gateway routes and
message topics, read from the code. Click a service to see what it calls and
what calls it.

**Say:** *"Before anything is removed we have to know what breaks. In the demo
bank, `GET /v2/accounts/{id}` has three direct callers, but removing it reaches
nine services, five hops deep: **13 endpoints degraded**. That depth is not
known in advance, which is why the dependency layer is a graph."*

### Step 5: Safe Kill review queue (2 minutes)

**Safe Kill** tab. On a code scan nothing is removed, because nothing proves an
endpoint is unused (the card says why). Instead each candidate gets a human
decision. Open `v2/check-otp`, read its signals, choose **Investigate for
removal**, and add a note.

### Step 6: Audit log (1 minute)

**Audit log** tab: who started the scan, what it found (with the report's
SHA-256), and your decision, with your name. Press **Verify the whole chain**.

**Say:** *"Every entry is hash-chained to the one before. Editing any line,
including the stored report, breaks the chain and this button says where."*

### Step 7: Why it does not just say "zombie" (1 minute)

Back on **Overview**, the card **"Why no endpoint is called a zombie here"**.

**Say:** *"All four lifecycle classes are defined by use. A repository has no
gateway, no traffic sensor, no DNS. So we rank candidates from the evidence the
code does hold, and we say what evidence is missing. A tool that says what it
cannot know is a tool a bank can deploy."*

**Benchmark** tab on this scan: what a documentation-only inventory would have
listed, against what the scan found.

### Step 8: Two more real repositories (2 minutes)

From **All scans**, open the pre-scanned reports:

| Repository | Top of the list |
|---|---|
| VAmPI | `GET /users/v1/_debug` and `GET /createdb`: debug endpoints shipped in the API |
| spring-petclinic-rest | `GET /owners` and `GET /pets`, superseded by their `v2`; and `GET /oops` |

**Say:** *"Different languages, different frameworks: Python with Connexion,
Java with Spring. These results are asserted by a test that scans the real
repositories, including what must not be flagged."*

### Step 9: Run the demo, the full pipeline (5 minutes)

On **New scan**, press **Not sure what to expect? Run the demo**. This opens
the simulated bank, with a banner on every page saying so.

**Say first:** *"Code alone cannot prove an endpoint is dead. With traffic,
gateway and DNS, it can. No bank publishes its real inventory, so this estate is
simulated, with known answers, to measure the engine."*

1. **Overview**: 25 endpoints, 8 zombies.
2. **Endpoints**, click `GET /v1/kyc/documents/{id}/raw`: no traffic, absent from
   spec and gateway, still in DNS, unauthenticated. The source chips show which
   of the six sources saw it. *"Absence is the evidence."*
3. **Benchmark**: a conventional inventory (gateway plus specification) finds
   **2 of 8** zombies; correlating six sources finds **8 of 8**. Accuracy 0.960,
   zero live endpoints marked for removal.
4. **Safe Kill**: **Start shadow** on the KYC endpoint and on
   `POST /v1/debug/payments/replay`. The KYC shadow is clean, so Approve is live;
   the debug route saw anonymous requests, so **Approve stays disabled** until the
   risk is accepted in writing. Approve the KYC endpoint: nominated to retired,
   decided by you.
5. **Audit log**: Verify the whole chain. The approver's name comes from the
   sign-in, never from anything the browser sends.

**If asked "why the 90-day shadow?":** *"To be 95% sure of seeing a caller that
calls once a month you must watch ln(20) times 30 days, the rule of three.
Across 120 generated estates the gate alone would have removed 49 live
endpoints; with Safe Kill, none."*

### Step 10 (optional): Stopping the next zombie at the pull request

Only if time allows; this one is in the terminal:

```powershell
python demo\make_enforce_demo.py demo\enforce-demo
apix enforce --repo demo\enforce-demo --base main
```

> Four errors and a warning, including `GET /v1/legacy/export` removed from the
> spec with its handler left behind: **"Zombie in the making"**.

**Say:** *"Every zombie is made the same way: the route is deleted from the
documentation and nobody deletes the code. This catches it at that commit, and
it only judges the change, so a bank with hundreds of existing undocumented
endpoints can switch it on today."*

---

## 3. Questions to expect

**"Why would anyone use this instead of Semgrep?"**
Semgrep is one of our inputs: it finds where routes are defined. It does not
know that `v2/check-otp` has a `v3`, that the project's own web app only calls
`v3`, that the spec does not document it, or that it has not changed in two
years while the rest of the project has. API Exorcist correlates those sources
into one ranked, explained list, draws the dependencies, and runs the removal
through a review, a shadow period, a named approval and a tamper-evident audit
log. Semgrep finds code; this decides what to do about an endpoint.

**"I give you a random repository and it finds 0 candidates. So it does not work?"**
Zero is an honest answer when there is no evidence: no older version beside a
newer one, no client code to compare against, no deprecation, no debug route.
The Zombie candidates card then lists which of those the repository lacks. A
tool that invents zombies on a healthy project would remove live endpoints,
which in a bank is an outage. If they hand you a repository live, scan it and
read that card aloud.

**"Is any of this real, or is it all simulated?"**
The repository scans are real: real code from GitHub, nothing simulated. The
demo bank is simulated, and says so on every page, because measuring detection
accuracy needs ground truth, and no bank publishes its inventory. The defensible
claim is *"the engine recovers known decay patterns from partial, disagreeing
evidence"*, never *"validated on production bank data"*.

**"You got 96%. Isn't that suspiciously high?"**
It is a rule classifier on 25 endpoints, and the weights were fixed before
accuracy was measured. The one error, `POST /v1/kyc/aadhaar/ekyc`, is genuinely
deprecated but classified active: its team never set the OpenAPI flag, exactly
what Cassieri et al. observed. Its confidence is 0.803, the same as correct
actives, because the evidence genuinely does not distinguish the cases.

**"What if it deletes something important?"**
On a code scan it deletes nothing. In the pipeline, four barriers: the
classifier must say ZOMBIE having consulted a usage source; the graph must show
nothing depends on it; a 90-day shadow must see no named caller and a named
person must approve; then a canary rolls back automatically on the first breach.

**"Why not just a canary rollout?"**
We measured it. A canary with no shadow period has no baseline for anonymous
traffic, so scanner noise triggers rollbacks: it wrongly keeps dead endpoints
running, and it refuses 67 real
requests before it catches the live ones.

**"Why not just use machine learning?"**
A new deployment has zero labels on day one. The rule engine works immediately.
The model is trained on data from the estate generator (120 generated estates);
the trained model is used as a veto over removals, and in deployment the audit
log becomes its training set.

**"Is it production-ready?"**
Tokens stored hashed, every route authenticated, a hash-chained audit log, a
hardened container, Prometheus metrics, CI on every push, and a security review
whose findings were fixed with tests. It has not run against a real bank's
traffic, and nothing here claims it has.

**"How much of this did AI write?"**
Answer honestly and specifically. What you add is the review, the architectural
decisions, and being able to defend each of them.

---

## 4. If something goes wrong

| Symptom | Fix |
|---|---|
| The browser did not open | Open the address printed in the terminal; the sign-in is in the link it prints |
| "Port 8600 in use" | Nothing to do: the app takes the next free port and prints it |
| A GitHub scan fails (no network, rate limit) | Open the pre-scanned report under **All scans**; say the room's network failed |
| A scan is slow | Talk over it, or open the pre-scanned report of the same repository |
| A scan of their repository finds 0 candidates | Read the Zombie candidates card aloud: it says which evidence the repository lacks |
| `apix` not recognised | `pip install -e ".[dev,live,api]"`, then reopen the terminal |
| Anything else errors live | Do not debug in front of the panel. Switch to **Run the demo** |

---

## 5. Timing

| Step | Talk |
|---|---|
| 1 The question | 1 min |
| 2 Live crAPI scan (about 50 s to run) | 3 min |
| 3 Endpoints, 4 Graph | 3 min |
| 5 Safe Kill review, 6 Audit, 7 Why no verdict | 4 min |
| 8 VAmPI and petclinic | 2 min |
| 9 The demo bank | 5 min |
| 10 Enforcement (optional) | 2 min |

About 18 minutes without step 10. Everything else is you explaining, which is
what is being assessed.
