# The live demo, one step per key press.
#
#   powershell -ExecutionPolicy Bypass -File demo\run.ps1
#
# Press ENTER to advance. Nothing runs until you press it, so you can talk over
# each screen for as long as you need. Ctrl+C stops.
#
# Run demo\prepare.ps1 first, at least once, on this machine.

$ErrorActionPreference = "Continue"
$root = Split-Path -Parent $PSScriptRoot
Set-Location $root
$repo = "demo\repos\full-stack-fastapi-template"

function Slide($n, $of, $title, $point) {
    Write-Host ""
    Write-Host ("=" * 76) -ForegroundColor DarkCyan
    Write-Host ("  [$n/$of]  $title") -ForegroundColor Cyan
    Write-Host ("=" * 76) -ForegroundColor DarkCyan
    Write-Host "  $point" -ForegroundColor Gray
    Write-Host ""
}

function Run($cmd) {
    Write-Host "  PS> $cmd" -ForegroundColor Yellow
    Write-Host ""
    Read-Host "  [enter to run]" | Out-Null
    Invoke-Expression $cmd
    Write-Host ""
    Read-Host "  [enter for next]" | Out-Null
}

Clear-Host
Write-Host @"

    API EXORCIST
    Autonomous discovery and safe elimination of
    zombie, shadow and orphaned APIs

    50% review demonstration
"@ -ForegroundColor White
Read-Host "  [enter to begin]" | Out-Null

# ---------------------------------------------------------------------------
Slide 1 6 "THE PROBLEM — what a conventional API inventory misses" `
    "Four configurations, identical pipeline code. Only the evidence differs."
Run "apix benchmark"

# ---------------------------------------------------------------------------
Slide 2 6 "DISCOVERY AND CLASSIFICATION — with reasons, not just labels" `
    "Six sources correlated, then classified. Every verdict carries its evidence."
Run "apix scan"

# ---------------------------------------------------------------------------
Slide 3 6 "WHY REMOVAL IS DANGEROUS — blast radius" `
    "Three direct callers. Nine services. Five hops. This is why you cannot just delete."
Run 'apix impact "GET /v2/accounts/{id}"'

# ---------------------------------------------------------------------------
Slide 4 6 "HOW REMOVAL IS MADE SAFE — the gate" `
    "Classifier AND graph must agree. All 8 zombies are isolated; that is why they are safe."
Run "apix impact"

# ---------------------------------------------------------------------------
Slide 5 6 "IT WORKS ON REAL CODE — not only the simulation" `
    "A real repository. Real Semgrep AST extraction. Real commit history."
Run "apix scan --local $repo --limit 3"

# ---------------------------------------------------------------------------
Slide 6 6 "IT IS TESTED — including the parts that must never break" `
    "64 tests. Ground-truth leakage guards. The removal gate. CI on 3.10 and 3.12."
Run "python -m pytest -q"

Write-Host ""
Write-Host ("=" * 76) -ForegroundColor DarkCyan
Write-Host "  Demo complete." -ForegroundColor Cyan
Write-Host ("=" * 76) -ForegroundColor DarkCyan
Write-Host @"

  Where the numbers live:
    data/benchmark.json   the comparative figures
    data/verdicts.json    every verdict in audit-log shape
    docs/                 literature review, design document

"@ -ForegroundColor Gray
