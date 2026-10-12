# Run this the day before the presentation, on the machine you will present
# from, and again an hour before if you have time. It is safe to rerun.
#
# It fetches everything the demo needs so that nothing depends on the network,
# a proxy, or a GitHub outage while you are standing in front of the panel,
# and it resets the demo state so the audit log starts empty.
#
#   powershell -ExecutionPolicy Bypass -File demo\prepare.ps1
#
# ASCII only, for the same reason as run.ps1.

$ErrorActionPreference = "Continue"
$root = Split-Path -Parent $PSScriptRoot
Set-Location $root
$problems = 0

function Step($n, $msg) { Write-Host "`n[$n] $msg" -ForegroundColor Cyan }
function Ok($msg)       { Write-Host "    OK  $msg" -ForegroundColor Green }
function Bad($msg)      { Write-Host "    !!  $msg" -ForegroundColor Red; $script:problems++ }

Write-Host "API Exorcist - presentation preparation" -ForegroundColor White
Write-Host "=======================================" -ForegroundColor White

# ---------------------------------------------------------------- 1. install
Step 1 "Installing the package: live scanning and the REST API"
python -m pip install --quiet -e ".[dev,live,api]"
if ($LASTEXITCODE -eq 0) { Ok "installed" } else { Bad "install failed"; exit 1 }

# ---------------------------------------------------------------- 2. checks
Step 2 "Checking the tools the demo relies on"
foreach ($t in @("git", "semgrep", "apix")) {
    $p = (Get-Command $t -ErrorAction SilentlyContinue)
    if ($p) { Ok "$t -> $($p.Source)" } else { Bad "$t NOT FOUND" }
}
python -c "import fastapi, uvicorn" 2>$null
if ($LASTEXITCODE -eq 0) { Ok "fastapi and uvicorn import" } else { Bad "the API extra is missing" }
if (Test-Path "src\apix\api\dashboard\index.html") { Ok "dashboard build present" } `
    else { Bad "dashboard build missing: cd dashboard; npm ci; npm run build" }

# ------------------------------------------------------- 3. pre-clone target
Step 3 "Cloning the demo repository (so the live scan needs no network)"
$repo = "demo\repos\full-stack-fastapi-template"
if (Test-Path $repo) {
    Ok "already present at $repo"
} else {
    New-Item -ItemType Directory -Force -Path "demo\repos" | Out-Null
    git clone --filter=blob:none --quiet `
        https://github.com/fastapi/full-stack-fastapi-template.git $repo
    if ($LASTEXITCODE -eq 0) { Ok "cloned to $repo" } else { Bad "clone failed" }
}

# --------------------------------------------------------- 4. warm the caches
Step 4 "Warming caches (the first Semgrep run is slower than the rest)"
apix scan --local $repo --limit 0 | Out-Null
Ok "semgrep warm"

# --------------------------------------------------------------- 5. dry run
Step 5 "Dry run of every demo command"
$card = 'GET /v1/cards/{id}/pin'
$scratch = Join-Path $env:TEMP "apix-prepare-audit.jsonl"
$cmds = @(
    @("apix version", 0),
    @("apix benchmark", 0),
    @("apix scan", 1),
    @("apix impact", 0),
    @('apix impact "GET /v2/accounts/{id}"', 0),
    @("apix safekill `"$card`" --approve-as rehearsal --hidden-caller `"$card`" --audit `"$scratch`"", 0),
    @("apix scan --local $repo --limit 0", 0)
)
foreach ($c in $cmds) {
    $sw = [Diagnostics.Stopwatch]::StartNew()
    Invoke-Expression $c[0] | Out-Null
    $sw.Stop()
    $label = if ($c[0].Length -gt 44) { $c[0].Substring(0, 41) + "..." } else { $c[0] }
    if ($LASTEXITCODE -eq $c[1]) {
        Ok ("{0,-46} {1,5:N1}s" -f $label, $sw.Elapsed.TotalSeconds)
    } else {
        Bad "$label exited $LASTEXITCODE, expected $($c[1])"
    }
}
Remove-Item -Force -ErrorAction SilentlyContinue $scratch, "$scratch.lock"

if (Test-Path "demo\enforce-demo") { Remove-Item -Recurse -Force "demo\enforce-demo" }
python demo\make_enforce_demo.py demo\enforce-demo | Out-Null
$out = (apix enforce --repo demo\enforce-demo --base main) -join "`n"
if ($LASTEXITCODE -eq 1 -and $out -match "FAIL: 4 error\(s\), 1 warning\(s\)") {
    Ok "apix enforce on the demo fixture: 4 errors, 1 warning, as scripted"
} else {
    Bad "apix enforce did not give the scripted result (exit $LASTEXITCODE)"
}

# ------------------------------------------------- 6. a clean slate to present
Step 6 "Resetting demo state"
$audit = "data\safekill-audit.jsonl"
if (Test-Path $audit) {
    # Archived, never deleted: an audit log is the one file nobody should lose.
    $stamp = Get-Date -Format "yyyyMMdd-HHmmss"
    New-Item -ItemType Directory -Force -Path "data\archive" | Out-Null
    Move-Item $audit "data\archive\safekill-audit-$stamp.jsonl"
    Remove-Item -Force -ErrorAction SilentlyContinue "$audit.lock"
    Ok "previous audit log moved to data\archive\safekill-audit-$stamp.jsonl"
} else {
    Ok "audit log already empty"
}
$busy = Get-NetTCPConnection -LocalPort 8600 -State Listen -ErrorAction SilentlyContinue
if ($busy) { Bad "port 8600 is in use; close whatever holds it before presenting" } `
    else { Ok "port 8600 is free for the dashboard" }

# ---------------------------------------------------------------- 7. tests
Step 7 "Full test suite (about a minute and a half)"
python -m pytest -p no:cacheprovider | Select-Object -Last 1
if ($LASTEXITCODE -ne 0) { Bad "tests failed" }

Write-Host ""
if ($problems -eq 0) {
    Write-Host "Ready. Present with:  powershell -ExecutionPolicy Bypass -File demo\run.ps1" -ForegroundColor White
} else {
    Write-Host "$problems problem(s) above, marked !!. Fix them before presenting." -ForegroundColor Red
}
Write-Host "Reminder: 'apix scan' and 'apix enforce' exit 1 when they find something. That is correct." -ForegroundColor DarkGray
