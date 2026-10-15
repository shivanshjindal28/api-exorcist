# Expected output

These are here so you can tell "the demo behaved differently" from "I misremembered
what it prints", and so the documents quote output that actually exists rather than
output someone typed from memory.

Captured on 2026-10-15, version 1.0.0:

| File | Command |
|---|---|
| `prescan.txt` | `python demo\prescan.py OWASP/crAPI erev0s/VAmPI spring-petclinic/spring-petclinic-rest` (step 4 of `prepare.ps1`; timings depend on the network) |
| `tests.txt` | `python -m pytest` (the config already adds `-q`; the 7 skips are the real-repository tests, run with `APIX_REALWORLD=1`) |

Captured on 2026-09-01, at commit `9987ae3`, from the command-line tools. The demo
is now run in the browser, but these commands still exist and still print this:

| File | Command |
|---|---|
| `benchmark.txt` | `apix benchmark` |
| `scan.txt` | `apix scan` |
| `impact.txt` | `apix impact` |
| `blast.txt` | `apix impact "GET /v2/accounts/{id}"` |
| `real.txt` | `apix scan --local demo\repos\full-stack-fastapi-template --limit 2` (before zombie candidates were added) |
| `dataset.txt` | `apix dataset` |

Regenerate after any change that could move the numbers:

```powershell
$env:PYTHONIOENCODING="utf-8"
apix benchmark | Out-File demo\expected-output\benchmark.txt -Encoding utf8
apix scan      | Out-File demo\expected-output\scan.txt      -Encoding utf8
apix impact    | Out-File demo\expected-output\impact.txt    -Encoding utf8
```

**These files are not a test.** CI asserts the figures directly from
`data/benchmark.json` and from `apix impact --json`, and `tests/test_realworld.py`
asserts the real-repository results. These exist for humans preparing to present.
