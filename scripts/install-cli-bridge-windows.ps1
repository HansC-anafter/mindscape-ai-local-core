# Mindscape CLI Bridge - Windows Installation Script
# Run as Administrator

$ErrorActionPreference = "Stop"

$ProjectDir = Split-Path -Parent (Split-Path -Parent $MyInvocation.MyCommand.Path)
$SupervisorScript = Join-Path $ProjectDir "scripts\start_cli_bridge_supervisor.ps1"
$PowerShellExe = Join-Path $env:SystemRoot "System32\WindowsPowerShell\v1.0\powershell.exe"
$ServiceName = "MindscapeCliBridge"
$LogDir = Join-Path $ProjectDir "logs"

Write-Host "Installing Mindscape CLI Bridge..." -ForegroundColor Cyan

$isAdmin = ([Security.Principal.WindowsPrincipal] [Security.Principal.WindowsIdentity]::GetCurrent()).IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)
if (-not $isAdmin) {
    Write-Host "This script must be run as Administrator" -ForegroundColor Red
    exit 1
}

if (-not (Test-Path $SupervisorScript)) {
    Write-Host "Supervisor script not found: $SupervisorScript" -ForegroundColor Red
    exit 1
}

$nssm = Get-Command nssm -ErrorAction SilentlyContinue
if (-not $nssm) {
    Write-Host "NSSM not found. Please install NSSM to run the CLI Bridge as a Windows service." -ForegroundColor Yellow
    Write-Host "   Fallback manual command:" -ForegroundColor Yellow
    Write-Host "   powershell -ExecutionPolicy Bypass -File $SupervisorScript -All" -ForegroundColor White
    exit 1
}

New-Item -ItemType Directory -Force -Path $LogDir | Out-Null

nssm stop $ServiceName 2>$null
nssm remove $ServiceName confirm 2>$null

$arguments = "-ExecutionPolicy Bypass -File `"$SupervisorScript`" -All"
nssm install $ServiceName $PowerShellExe $arguments
nssm set $ServiceName AppDirectory $ProjectDir
nssm set $ServiceName DisplayName "Mindscape CLI Bridge"
nssm set $ServiceName Description "Persistent multi-surface CLI bridge for Mindscape AI"
nssm set $ServiceName Start SERVICE_AUTO_START
nssm set $ServiceName AppStdout (Join-Path $LogDir "cli-bridge.log")
nssm set $ServiceName AppStderr (Join-Path $LogDir "cli-bridge.error.log")
nssm set $ServiceName AppRotateFiles 1
nssm set $ServiceName AppRotateOnline 1
nssm set $ServiceName AppEnvironmentExtra "MINDSCAPE_WORKSPACE_ROOT=$ProjectDir" "MINDSCAPE_BRIDGE_SURFACES=gemini_cli,codex_cli,claude_code_cli"
nssm start $ServiceName

Write-Host ""
Write-Host "Mindscape CLI Bridge installed as a Windows service." -ForegroundColor Green
Write-Host ""
Write-Host "  Status:  Get-Service $ServiceName"
Write-Host "  Logs:    Get-Content $LogDir\cli-bridge.log -Wait"
Write-Host "  Stop:    nssm stop $ServiceName"
Write-Host "  Remove:  nssm remove $ServiceName confirm"
