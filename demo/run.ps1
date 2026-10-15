# Starts the app for the presentation. The browser opens signed in.
#
#   powershell -ExecutionPolicy Bypass -File demo\run.ps1
#   powershell -ExecutionPolicy Bypass -File demo\run.ps1 -Name "Your Name"
#
# The name is who the audit log records for every scan and decision.
# Run demo\prepare.ps1 first, at least once, on this machine.
# Ctrl+C in this window stops the app.
#
# ASCII only, for the same reason as prepare.ps1.

param([string]$Name = $env:USERNAME)

$ErrorActionPreference = "Continue"
$root = Split-Path -Parent $PSScriptRoot
Set-Location $root

if (-not (Get-Command apix -ErrorAction SilentlyContinue)) {
    Write-Host "apix is not installed. Run demo\prepare.ps1 first." -ForegroundColor Red
    exit 1
}
if ($env:APIX_API_TOKENS) {
    # Configured tokens would replace the one-time browser sign-in.
    Write-Host "Ignoring APIX_API_TOKENS for the demo session." -ForegroundColor DarkGray
    Remove-Item Env:APIX_API_TOKENS
}

Write-Host ""
Write-Host "  API Exorcist" -ForegroundColor White
Write-Host "  Starting the app as '$Name'. The browser opens by itself." -ForegroundColor Gray
Write-Host "  The walkthrough is in demo\DEMO.md. Ctrl+C here stops the app." -ForegroundColor Gray
Write-Host ""
apix serve --as $Name
