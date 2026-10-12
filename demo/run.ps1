# The live demo, one step per key press.
#
#   powershell -ExecutionPolicy Bypass -File demo\run.ps1
#
# Press ENTER to advance. Nothing runs until you press it, so you can talk over
# each screen for as long as you need. Ctrl+C stops.
#
# Run demo\prepare.ps1 first, at least once, on this machine.
#
# This file is ASCII on purpose: Windows PowerShell 5.1 reads a UTF-8 file
# without a byte-order mark as ANSI, and any dash or quote outside ASCII would
# print as mojibake on the projector.

$ErrorActionPreference = "Continue"
$root = Split-Path -Parent $PSScriptRoot
Set-Location $root
$repo = "demo\repos\full-stack-fastapi-template"
$card = 'GET /v1/cards/{id}/pin'
$url = "http://127.0.0.1:8600"
$total = 10

function Slide($n, $title, $point) {
    Write-Host ""
    Write-Host ("=" * 76) -ForegroundColor DarkCyan
    Write-Host ("  [$n/$total]  $title") -ForegroundColor Cyan
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

    Final presentation
"@ -ForegroundColor White
Read-Host "  [enter to begin]" | Out-Null

# ---------------------------------------------------------------------------
Slide 1 "THE PROBLEM: what a conventional API inventory misses" `
    "Four configurations, identical pipeline code. Only the evidence differs."
Run "apix benchmark"

# ---------------------------------------------------------------------------
Slide 2 "DISCOVERY AND CLASSIFICATION: with reasons, not just labels" `
    "Six sources correlated, then classified. Every verdict carries its evidence."
Run "apix scan"

# ---------------------------------------------------------------------------
Slide 3 "WHY REMOVAL IS DANGEROUS: blast radius" `
    "Three direct callers. Nine services. Five hops. This is why you cannot just delete."
Run 'apix impact "GET /v2/accounts/{id}"'

# ---------------------------------------------------------------------------
Slide 4 "THE GATE: classifier AND graph must agree" `
    "All 8 zombies are isolated; that is why they are safe. All 3 deprecated are blocked."
Run "apix impact"

# ---------------------------------------------------------------------------
Slide 5 "SAFE KILL: the caller everything else missed" `
    "A month-end batch job the capture never saw. 90-day shadow: it is found, removal rejected."
Run "apix safekill `"$card`" --approve-as shivansh --hidden-caller `"$card`""
Write-Host "  Now the same endpoint with the shadow cut to 9 days, which is WRONG:" -ForegroundColor Gray
Run "apix safekill `"$card`" --approve-as shivansh --hidden-caller `"$card`" --slowest-caller-days 3 --seed 3"
Write-Host "  Seed 3: the canary catches it and rolls back. Seed 1 is the outage:" -ForegroundColor Gray
Run "apix safekill `"$card`" --approve-as shivansh --hidden-caller `"$card`" --slowest-caller-days 3 --seed 1"

# ---------------------------------------------------------------------------
Slide 6 "THE DASHBOARD: approval over HTTP, by a named person" `
    "The server starts in its own window. The sign-in token is copied to your clipboard."
Read-Host "  [enter to start the server and open the browser]" | Out-Null

$busy = Get-NetTCPConnection -LocalPort 8600 -State Listen -ErrorAction SilentlyContinue
if ($busy) {
    Write-Host "  !! Something is already listening on port 8600. Close it, then rerun." -ForegroundColor Red
    $token = $null
} else {
    # Mint a token for this demo only. The server is given its SHA-256, never
    # the token itself; the token goes to the clipboard, not the screen.
    $minted = (apix token shivansh --role approver) -join "`n"
    $token = [regex]::Match($minted, 'apx_[A-Za-z0-9_-]+').Value
    $entry = [regex]::Match($minted, 'shivansh:approver:[0-9a-f]+').Value
    $serve = "`$env:APIX_API_TOKENS='$entry'; Set-Location '$root'; apix serve"
    Start-Process powershell -ArgumentList "-NoExit", "-Command", $serve | Out-Null

    $up = $false
    foreach ($i in 1..60) {
        try {
            $r = Invoke-WebRequest "$url/v1/health" -UseBasicParsing -TimeoutSec 2
            if ($r.StatusCode -eq 200) { $up = $true; break }
        } catch { Start-Sleep -Milliseconds 500 }
    }
    if ($up) {
        Set-Clipboard -Value $token
        Start-Process $url
        Write-Host "  Server up at $url. Token copied: paste it into the sign-in box." -ForegroundColor Green
    } else {
        Write-Host "  !! The server did not come up in 30 seconds; check its window." -ForegroundColor Red
    }
}
Write-Host @"

  Show, in order (demo\DEMO.md step 4c has the words):
    1. Overview: 25 endpoints, 8 zombies, the simulated-estate banner
    2. Endpoints: click GET /v1/kyc/documents/{id}/raw; read the evidence
    3. Safe Kill: start shadows on the KYC endpoint and POST /v1/debug/payments/replay
    4. Approve the KYC endpoint; note Approve is disabled on the debug route
    5. Audit log: Verify the whole chain

"@ -ForegroundColor Gray
Read-Host "  [enter for next]" | Out-Null

# ---------------------------------------------------------------------------
Slide 7 "ENFORCEMENT: stopping the next zombie at the pull request" `
    "A feature branch that breaks every rule once. Only the change is judged."
if (Test-Path "demo\enforce-demo") { Remove-Item -Recurse -Force "demo\enforce-demo" }
python demo\make_enforce_demo.py demo\enforce-demo | Out-Null
Run "apix enforce --repo demo\enforce-demo --base main"

# ---------------------------------------------------------------------------
Slide 8 "RUNNING AS A SERVICE: what monitoring sees" `
    "Prometheus metrics, behind the same token. Alert on apix_audit_chain_ok."
Write-Host "  PS> (metrics from $url/metrics, filtered)" -ForegroundColor Yellow
Read-Host "  [enter to run]" | Out-Null
if ($token) {
    try {
        $m = Invoke-WebRequest "$url/metrics" -UseBasicParsing `
            -Headers @{ Authorization = "Bearer $token" }
        $m.Content -split "`n" |
            Select-String '^apix_(endpoints|audit_entries|audit_chain_ok|auth_failures|safekill_actions)' |
            ForEach-Object { "  $_" }
    } catch {
        Write-Host "  !! Could not read metrics: $($_.Exception.Message)" -ForegroundColor Red
    }
} else {
    Write-Host "  (skipped: the server from step 6 is not running)" -ForegroundColor DarkGray
}
Write-Host ""
Read-Host "  [enter for next]" | Out-Null

# ---------------------------------------------------------------------------
Slide 9 "IT WORKS ON REAL CODE: not only the simulation" `
    "A real repository. Real Semgrep AST extraction. Real commit history."
Run "apix scan --local $repo --limit 3"

# ---------------------------------------------------------------------------
Slide 10 "IT IS TESTED: including the parts that must never break" `
    "Leakage guards, the removal gate, auth on every route, the audit chain under concurrent writers."
Write-Host "  The two tests that drive real Semgrep take 45 seconds; they are left out" -ForegroundColor Gray
Write-Host "  here and run in full by demo\prepare.ps1 and in CI." -ForegroundColor Gray
Run "python -m pytest -k `"not real_semgrep_end_to_end and not cli_exit_codes_follow_ci_convention`""

Write-Host ""
Write-Host ("=" * 76) -ForegroundColor DarkCyan
Write-Host "  Demo complete." -ForegroundColor Cyan
Write-Host ("=" * 76) -ForegroundColor DarkCyan
Write-Host @"

  The server window from step 6 is still open; close it when you are done.

  Where the numbers live:
    data/benchmark.json          the comparative figures
    data/verdicts.json           every verdict in audit-log shape
    data/safekill-audit.jsonl    the hash-chained audit log
    docs/                        literature review, design document

"@ -ForegroundColor Gray
