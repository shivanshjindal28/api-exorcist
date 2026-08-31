# Run this ONCE, the day before the review, on the machine you will present from.
#
# It fetches everything the demo needs so that nothing depends on the network,
# a proxy, or a GitHub outage while you are standing in front of the panel.
#
#   powershell -ExecutionPolicy Bypass -File demo\prepare.ps1

$ErrorActionPreference = "Stop"
$root = Split-Path -Parent $PSScriptRoot
Set-Location $root

function Step($n, $msg) { Write-Host "`n[$n] $msg" -ForegroundColor Cyan }
function Ok($msg)       { Write-Host "    OK  $msg" -ForegroundColor Green }
function Bad($msg)      { Write-Host "    !!  $msg" -ForegroundColor Red }

Write-Host "API Exorcist - demo preparation" -ForegroundColor White
Write-Host "===============================" -ForegroundColor White

# ---------------------------------------------------------------- 1. install
Step 1 "Installing the package with live-scanning support"
python -m pip install --quiet -e ".[dev,live]"
if ($LASTEXITCODE -eq 0) { Ok "installed" } else { Bad "install failed"; exit 1 }

# ---------------------------------------------------------------- 2. checks
Step 2 "Checking the tools the demo relies on"
foreach ($t in @("git", "semgrep", "apix")) {
    $p = (Get-Command $t -ErrorAction SilentlyContinue)
    if ($p) { Ok "$t -> $($p.Source)" } else { Bad "$t NOT FOUND" }
}

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
Step 4 "Warming caches (first Semgrep run is slower than the rest)"
apix scan --local $repo --limit 0 | Out-Null
Ok "semgrep warm"

# --------------------------------------------------------------- 5. dry run
Step 5 "Dry run of every demo command"
$cmds = @(
    "apix version",
    "apix benchmark",
    "apix scan",
    "apix impact",
    'apix impact "GET /v2/accounts/{id}"',
    "apix dataset"
)
foreach ($c in $cmds) {
    $sw = [Diagnostics.Stopwatch]::StartNew()
    Invoke-Expression $c | Out-Null
    $sw.Stop()
    if ($LASTEXITCODE -le 1) {
        Ok ("{0,-38} {1,5:N1}s" -f $c, $sw.Elapsed.TotalSeconds)
    } else {
        Bad "$c FAILED (exit $LASTEXITCODE)"
    }
}

$sw = [Diagnostics.Stopwatch]::StartNew()
apix scan --local $repo --limit 0 | Out-Null
$sw.Stop()
Ok ("{0,-38} {1,5:N1}s" -f "apix scan --local <repo>", $sw.Elapsed.TotalSeconds)

Step 6 "Test suite"
python -m pytest -q | Select-Object -Last 1

Write-Host "`nReady. Open demo\DEMO.md and follow it." -ForegroundColor White
Write-Host "Reminder: 'apix scan' exits 1 when zombies are found. That is correct." -ForegroundColor DarkGray
