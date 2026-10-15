# Run this the day before the presentation, on the machine you will present
# from, and again an hour before if you have time. It is safe to rerun.
#
# It installs what the app needs, gives the "All scans" list a clean start,
# and scans three real repositories through the app's own scan engine, so the
# results are there to open even if the room's network fails.
#
#   powershell -ExecutionPolicy Bypass -File demo\prepare.ps1
#
# ASCII only: Windows PowerShell 5.1 reads a UTF-8 file without a byte-order
# mark as ANSI, and anything outside ASCII prints as mojibake.

$ErrorActionPreference = "Continue"
$root = Split-Path -Parent $PSScriptRoot
Set-Location $root
$problems = 0
$env:PYTHONIOENCODING = "utf-8"

function Step($n, $msg) { Write-Host "`n[$n] $msg" -ForegroundColor Cyan }
function Ok($msg)       { Write-Host "    OK  $msg" -ForegroundColor Green }
function Bad($msg)      { Write-Host "    !!  $msg" -ForegroundColor Red; $script:problems++ }

Write-Host "API Exorcist - presentation preparation" -ForegroundColor White
Write-Host "=======================================" -ForegroundColor White

# ---------------------------------------------------------------- 1. install
Step 1 "Installing the package: live scanning and the web app"
python -m pip install --quiet -e ".[dev,live,api]"
if ($LASTEXITCODE -eq 0) { Ok "installed" } else { Bad "install failed"; exit 1 }

# ---------------------------------------------------------------- 2. checks
Step 2 "Checking the tools the app relies on"
foreach ($t in @("git", "semgrep", "apix")) {
    $p = (Get-Command $t -ErrorAction SilentlyContinue)
    if ($p) { Ok "$t -> $($p.Source)" } else { Bad "$t NOT FOUND" }
}
python -c "import fastapi, uvicorn" 2>$null
if ($LASTEXITCODE -eq 0) { Ok "web app dependencies import" } else { Bad "the api extra is missing" }
if (Test-Path "src\apix\api\dashboard\index.html") { Ok "dashboard build present" } `
    else { Bad "dashboard build missing: cd dashboard; npm ci; npm run build" }

# ------------------------------------------------- 3. a clean slate to present
Step 3 "Archiving earlier scans and audit logs"
# Archived, never deleted: an audit log is the one file nobody should lose.
$stamp = Get-Date -Format "yyyyMMdd-HHmmss"
$archive = "data\archive\$stamp"
$moved = 0
if (Test-Path "data\scans") {
    New-Item -ItemType Directory -Force -Path $archive | Out-Null
    Move-Item "data\scans" "$archive\scans"
    $moved++
}
if (Test-Path "data\safekill-audit.jsonl") {
    New-Item -ItemType Directory -Force -Path $archive | Out-Null
    Move-Item "data\safekill-audit.jsonl" "$archive\safekill-audit.jsonl"
    Remove-Item -Force -ErrorAction SilentlyContinue "data\safekill-audit.jsonl.lock"
    $moved++
}
if ($moved) { Ok "moved to $archive" } else { Ok "nothing to archive" }

# --------------------------------------------- 4. real scans, ready to open
Step 4 "Scanning three real repositories from GitHub (about four minutes)"
python demo\prescan.py OWASP/crAPI erev0s/VAmPI spring-petclinic/spring-petclinic-rest
if ($LASTEXITCODE -eq 0) { Ok "all three are under 'All scans' in the app" } `
    else { Bad "a scan failed (network?); rerun this script before presenting" }

# --------------------------------------- 4b. synthetic logs for the Usage demo
Step "4b" "Writing a SYNTHETIC access log for crAPI (labelled as such inside)"
python demo\make_access_log.py OWASP/crAPI demo\synthetic-crapi-access.log
if ($LASTEXITCODE -eq 0) { Ok "demo\synthetic-crapi-access.log: import it on crAPI's Usage view" } `
    else { Bad "could not write the synthetic log (is the crAPI scan above done?)" }

# ------------------------------------------- 5. the optional enforcement step
Step 5 "Checking the enforcement demo (optional step 10)"
if (Test-Path "demo\enforce-demo") { Remove-Item -Recurse -Force "demo\enforce-demo" }
python demo\make_enforce_demo.py demo\enforce-demo | Out-Null
$out = (apix enforce --repo demo\enforce-demo --base main) -join "`n"
if ($LASTEXITCODE -eq 1 -and $out -match "FAIL: 4 error\(s\), 1 warning\(s\)") {
    Ok "4 errors, 1 warning, as scripted"
} else {
    Bad "apix enforce did not give the scripted result (exit $LASTEXITCODE)"
}

# ---------------------------------------------------------------- 6. port
Step 6 "Checking the port"
$busy = Get-NetTCPConnection -LocalPort 8600 -State Listen -ErrorAction SilentlyContinue
if ($busy) { Ok "port 8600 is in use; the app will take the next free port and say so" } `
    else { Ok "port 8600 is free" }

# ---------------------------------------------------------------- 7. tests
Step 7 "Full test suite (about a minute and a half)"
python -m pytest -p no:cacheprovider | Select-Object -Last 1
if ($LASTEXITCODE -ne 0) { Bad "tests failed" }

Write-Host ""
if ($problems -eq 0) {
    Write-Host "Ready. Present with F5 in VS Code, or:" -ForegroundColor White
    Write-Host "  powershell -ExecutionPolicy Bypass -File demo\run.ps1" -ForegroundColor White
} else {
    Write-Host "$problems problem(s) above, marked !!. Fix them before presenting." -ForegroundColor Red
}
