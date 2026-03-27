# Mindscape CLI Bridge Supervisor (Windows PowerShell)
#
# Keeps one start_cli_bridge.ps1 watcher alive per surface.

param(
    [string]$Surfaces = $(if ($env:MINDSCAPE_BRIDGE_SURFACES) { $env:MINDSCAPE_BRIDGE_SURFACES } else { "gemini_cli,codex_cli,claude_code_cli" }),
    [string]$WorkspaceId = $env:MINDSCAPE_WORKSPACE_ID,
    [string]$Host_ = $(if ($env:MINDSCAPE_WS_HOST) { $env:MINDSCAPE_WS_HOST } else { "localhost:8200" }),
    [switch]$All,
    [switch]$Help
)

$ErrorActionPreference = "Stop"
$ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$BridgeScript = Join-Path $ScriptDir "start_cli_bridge.ps1"
$PowerShellExe = Join-Path $env:SystemRoot "System32\WindowsPowerShell\v1.0\powershell.exe"

function Write-Info { param([string]$Msg) Write-Host "[bridge-supervisor][INFO] $Msg" }
function Write-Warn { param([string]$Msg) Write-Host "[bridge-supervisor][WARN] $Msg" }
function Write-Err  { param([string]$Msg) Write-Host "[bridge-supervisor][ERROR] $Msg" -ForegroundColor Red }

if ($Help) {
    Write-Host "Usage: .\scripts\start_cli_bridge_supervisor.ps1 [OPTIONS]"
    Write-Host ""
    Write-Host "Options:"
    Write-Host "  -Surfaces CSV      Comma-separated surfaces (default: gemini_cli,codex_cli,claude_code_cli)"
    Write-Host "  -All               Connect all workspaces for each surface"
    Write-Host "  -WorkspaceId ID    Passed through to start_cli_bridge.ps1"
    Write-Host "  -Host_ HOST:PORT   Passed through to start_cli_bridge.ps1"
    Write-Host "  -Help              Show this help"
    exit 0
}

if (-not (Test-Path $BridgeScript)) {
    Write-Err "Bridge script not found: $BridgeScript"
    exit 1
}

if (-not $All -and -not $WorkspaceId) {
    $All = $true
}

$surfaceList = @($Surfaces -split "," | ForEach-Object { $_.Trim() } | Where-Object { $_ })
if ($surfaceList.Count -eq 0) {
    Write-Err "No surfaces configured."
    exit 1
}

$children = @{}

function Start-SurfaceWatcher {
    param([string]$SurfaceName)

    $arguments = @(
        "-ExecutionPolicy", "Bypass",
        "-File", $BridgeScript,
        "-Surface", $SurfaceName,
        "-Host_", $Host_
    )
    if ($All) {
        $arguments += "-All"
    } elseif ($WorkspaceId) {
        $arguments += @("-WorkspaceId", $WorkspaceId)
    }

    $proc = Start-Process -FilePath $PowerShellExe -ArgumentList $arguments -WorkingDirectory (Split-Path -Parent $ScriptDir) -PassThru -WindowStyle Hidden
    $children[$SurfaceName] = $proc
    Write-Info "Surface watcher PID $($proc.Id) for $SurfaceName"
}

function Stop-AllChildren {
    foreach ($proc in $children.Values) {
        try {
            if (-not $proc.HasExited) {
                Stop-Process -Id $proc.Id -Force -ErrorAction SilentlyContinue
            }
        } catch {
        }
    }
}

try {
    foreach ($surface in $surfaceList) {
        Start-SurfaceWatcher -SurfaceName $surface
    }

    while ($true) {
        Start-Sleep -Seconds 10
        foreach ($surface in @($children.Keys)) {
            $proc = $children[$surface]
            try {
                if ($proc.HasExited) {
                    Write-Warn "Surface watcher $surface exited with code $($proc.ExitCode); restarting"
                    $children.Remove($surface) | Out-Null
                    Start-SurfaceWatcher -SurfaceName $surface
                }
            } catch {
                Write-Warn "Surface watcher $surface could not be inspected; restarting"
                $children.Remove($surface) | Out-Null
                Start-SurfaceWatcher -SurfaceName $surface
            }
        }
    }
} finally {
    Write-Info "Stopping bridge supervisor children..."
    Stop-AllChildren
}
