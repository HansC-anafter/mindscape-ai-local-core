# =============================================================================
# Mindscape CLI Bridge (Windows PowerShell)
#
# Starts the IDE WebSocket client on the HOST machine to bridge
# external CLI agents (Gemini CLI, Claude Code, etc.) to the
# Mindscape backend running in Docker.
#
# Usage:
#   .\scripts\start_cli_bridge.ps1                         # auto-detect workspace
#   .\scripts\start_cli_bridge.ps1 -All                    # connect ALL workspaces
#   .\scripts\start_cli_bridge.ps1 -WorkspaceId <ID>       # explicit workspace
#
# Requirements:
#   - Python 3.8+ with 'websockets' package
#   - Backend running at localhost:8200
# =============================================================================

param(
    [string]$WorkspaceId = $env:MINDSCAPE_WORKSPACE_ID,
    [string]$Host_ = $(if ($env:MINDSCAPE_WS_HOST) { $env:MINDSCAPE_WS_HOST } else { "localhost:8200" }),
    [string]$Surface = $(if ($env:MINDSCAPE_SURFACE) { $env:MINDSCAPE_SURFACE } else { "gemini_cli" }),
    [switch]$All,
    [switch]$Help
)

$ErrorActionPreference = "Stop"
$ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$ProjectDir = Split-Path -Parent $ScriptDir
$ClientScript = Join-Path $ProjectDir "backend\app\services\external_agents\agents\gemini_cli\ide_ws_client.py"
$BridgeScript = Join-Path $ProjectDir "scripts\gemini_cli_runtime_bridge.py"

function Write-Banner {
    Write-Host ""
    Write-Host "  +======================================+" -ForegroundColor Cyan
    Write-Host "  |     Mindscape CLI Bridge (Windows)   |" -ForegroundColor Cyan
    Write-Host "  +======================================+" -ForegroundColor Cyan
    Write-Host ""
}

function Write-Info  { param([string]$Msg) Write-Host "[INFO]  $Msg" -ForegroundColor Green }
function Write-Warn  { param([string]$Msg) Write-Host "[WARN]  $Msg" -ForegroundColor Yellow }
function Write-Err   { param([string]$Msg) Write-Host "[ERROR] $Msg" -ForegroundColor Red }

if ($Help) {
    Write-Host "Usage: .\scripts\start_cli_bridge.ps1 [OPTIONS]"
    Write-Host ""
    Write-Host "Options:"
    Write-Host "  -WorkspaceId ID   Workspace to connect to (auto-detected if omitted)"
    Write-Host "  -All              Connect to ALL workspaces"
    Write-Host "  -Host_ HOST:PORT  Backend host (default: localhost:8200)"
    Write-Host "  -Surface SURFACE  Agent surface type (default: gemini_cli)"
    Write-Host "  -Help             Show this help"
    exit 0
}

Write-Banner

# --- Pre-flight checks ---

# 1. Check Python
try {
    $pythonVersion = python --version 2>&1
    Write-Info "Python: $pythonVersion"
} catch {
    Write-Err "Python not found. Please install Python 3.8+"
    exit 1
}

# 2. Check/install websockets
$wsCheck = python -c "import websockets" 2>&1
if ($LASTEXITCODE -ne 0) {
    Write-Warn "'websockets' package not found. Installing..."
    python -m pip install websockets --quiet
    Write-Info "websockets installed"
}

# 3. Check client script
if (-not (Test-Path $ClientScript)) {
    Write-Err "Client script not found: $ClientScript"
    exit 1
}

# 4. Check backend health
$BackendHttp = "http://$Host_"
try {
    $health = Invoke-RestMethod -Uri "$BackendHttp/health" -TimeoutSec 3 -ErrorAction SilentlyContinue
    Write-Info "Backend health: OK"
} catch {
    Write-Warn "Backend at $BackendHttp may not be ready (health check failed)"
    Write-Warn "Proceeding anyway -- the client will retry with backoff"
}

# --- Helper: fetch workspace IDs ---
function Get-WorkspaceIds {
    try {
        $response = Invoke-RestMethod -Uri "$BackendHttp/api/v1/workspaces/?owner_user_id=default-user" -TimeoutSec 5
        $ids = @()
        if ($response -is [array]) {
            $ids = $response | ForEach-Object { $_.id } | Where-Object { $_ }
        } elseif ($response.workspaces) {
            $ids = $response.workspaces | ForEach-Object { $_.id } | Where-Object { $_ }
        }
        return $ids
    } catch {
        Write-Warn "Failed to fetch workspaces: $_"
        return @()
    }
}

# 5. Resolve workspace(s)
if ($All) {
    Write-Info "Fetching all workspaces..."
    $wsIds = Get-WorkspaceIds
    if ($wsIds.Count -eq 0) {
        Write-Err "No workspaces found."
        exit 1
    }
    Write-Info "Found $($wsIds.Count) workspace(s)"
} elseif (-not $WorkspaceId) {
    Write-Info "Auto-detecting workspace ID..."
    $wsIds = Get-WorkspaceIds
    if ($wsIds.Count -eq 0) {
        Write-Err "Could not auto-detect workspace ID."
        Write-Err "Please specify: .\scripts\start_cli_bridge.ps1 -WorkspaceId YOUR_WORKSPACE_ID"
        exit 1
    }
    $WorkspaceId = $wsIds[0]
    Write-Info "Detected workspace: $WorkspaceId"
    $wsIds = @($WorkspaceId)
} else {
    $wsIds = @($WorkspaceId)
}

# --- Detect installed CLIs ---
Write-Info "Scanning for installed CLI agents..."
$detected = 0
foreach ($cli in @("gemini", "claude", "codex", "openclaw", "aider")) {
    if (Get-Command $cli -ErrorAction SilentlyContinue) {
        try {
            $ver = & $cli --version 2>&1 | Select-Object -First 1
        } catch {
            $ver = "unknown"
        }
        Write-Info "  Found: $cli ($ver)"
        $detected++
    }
}

if ($detected -eq 0) {
    Write-Warn "No CLI agents detected."
    if (Get-Command npm -ErrorAction SilentlyContinue) {
        Write-Warn "Installing gemini-cli..."
        npm install -g @google/gemini-cli 2>$null
        if ($LASTEXITCODE -eq 0) {
            Write-Info "gemini-cli installed successfully"
        }
    } else {
        Write-Warn "npm not found. Install Node.js first, then: npm install -g @google/gemini-cli"
    }
}

# --- Environment ---
$env:PYTHONPATH = "$ProjectDir;$($ProjectDir)\backend;$($env:PYTHONPATH)"
$env:MINDSCAPE_CLI_RUNTIME_CMD = "python $BridgeScript"
$env:GEMINI_CLI_RUNTIME_CMD = $env:MINDSCAPE_CLI_RUNTIME_CMD
$env:MINDSCAPE_WORKSPACE_ROOT = if ($env:MINDSCAPE_WORKSPACE_ROOT) { $env:MINDSCAPE_WORKSPACE_ROOT } else { $ProjectDir }
$env:MINDSCAPE_BACKEND_API_URL = if ($env:MINDSCAPE_BACKEND_API_URL) { $env:MINDSCAPE_BACKEND_API_URL } else { $BackendHttp }

# --- Start bridge ---
Write-Info "Surface:   $Surface"
Write-Info "Runtime:   $($env:MINDSCAPE_CLI_RUNTIME_CMD)"
Write-Host ""
Write-Info "Press Ctrl+C to stop"
Write-Host ""

$jobs = @()
foreach ($wsId in $wsIds) {
    Write-Info "  Starting bridge for workspace: $wsId"
    $job = Start-Job -ScriptBlock {
        param($PythonPath, $ClientScript, $WsId, $Host_, $Surface, $WorkspaceRoot,
              $RuntimeCmd, $BackendUrl, $ProjectDir)
        $env:PYTHONPATH = $PythonPath
        $env:MINDSCAPE_CLI_RUNTIME_CMD = $RuntimeCmd
        $env:GEMINI_CLI_RUNTIME_CMD = $RuntimeCmd
        $env:MINDSCAPE_BACKEND_API_URL = $BackendUrl
        $env:MINDSCAPE_WORKSPACE_ROOT = $WorkspaceRoot
        python $ClientScript --workspace-id $WsId --host $Host_ --surface $Surface --workspace-root $WorkspaceRoot
    } -ArgumentList @(
        $env:PYTHONPATH, $ClientScript, $wsId, $Host_, $Surface,
        $env:MINDSCAPE_WORKSPACE_ROOT, $env:GEMINI_CLI_RUNTIME_CMD,
        $env:MINDSCAPE_BACKEND_API_URL, $ProjectDir
    )
    $jobs += $job
    Write-Info "  Bridge job $($job.Id) started for $wsId"
}

# Keep alive and relay output
try {
    while ($true) {
        foreach ($job in $jobs) {
            $output = Receive-Job -Job $job -ErrorAction SilentlyContinue
            if ($output) { $output | ForEach-Object { Write-Host $_ } }
            if ($job.State -eq "Failed" -or $job.State -eq "Completed") {
                Write-Warn "Bridge job $($job.Id) ended ($($job.State)). Restarting..."
                $output = Receive-Job -Job $job -ErrorAction SilentlyContinue
                if ($output) { $output | ForEach-Object { Write-Host $_ } }
                # Restart
                $wsId = $job.Command  # Will need to track this differently
            }
        }
        Start-Sleep -Seconds 2
    }
} finally {
    Write-Info "Stopping all bridges..."
    $jobs | ForEach-Object { Stop-Job -Job $_ -ErrorAction SilentlyContinue; Remove-Job -Job $_ -Force -ErrorAction SilentlyContinue }
}
