# Expected output

Captured from a real run on 2026-09-01, at commit `9987ae3`. These are here so you
can tell "the demo behaved differently" from "I misremembered what it prints", and so
the explainer document quotes output that actually exists rather than output someone
typed from memory.

| File | Command |
|---|---|
| `benchmark.txt` | `apix benchmark` |
| `scan.txt` | `apix scan` |
| `impact.txt` | `apix impact` |
| `blast.txt` | `apix impact "GET /v2/accounts/{id}"` |
| `real.txt` | `apix scan --local demo\repos\full-stack-fastapi-template --limit 2` |
| `dataset.txt` | `apix dataset` |
| `tests.txt` | `python -m pytest -q` |

Regenerate after any change that could move the numbers:

```powershell
$env:PYTHONIOENCODING="utf-8"
apix benchmark | Out-File demo\expected-output\benchmark.txt -Encoding utf8
apix scan      | Out-File demo\expected-output\scan.txt      -Encoding utf8
apix impact    | Out-File demo\expected-output\impact.txt    -Encoding utf8
```

**These files are not a test.** CI asserts the figures directly from
`data/benchmark.json` and from `apix impact --json`, which is a stronger check than
comparing text. These exist for humans preparing to present.
