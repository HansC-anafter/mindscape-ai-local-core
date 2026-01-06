# Mindscape AI Local Core - Start Script for Windows PowerShell
# This script checks Docker availability and starts services

param(
    [switch]$SkipCheck
)

# Check execution policy and provide helpful message if blocked
$executionPolicy = Get-ExecutionPolicy
if ($executionPolicy -eq "Restricted") {
    Write-Host "⚠️  PowerShell execution policy is 'Restricted'" -ForegroundColor Yellow
    Write-Host ""
    Write-Host "To run this script, you need to change the execution policy." -ForegroundColor Yellow
    Write-Host "Run PowerShell as Administrator and execute:" -ForegroundColor Cyan
    Write-Host "  Set-ExecutionPolicy -ExecutionPolicy RemoteSigned -Scope CurrentUser" -ForegroundColor White
    Write-Host ""
    Write-Host "Or run this script with bypass:" -ForegroundColor Cyan
    Write-Host "  powershell -ExecutionPolicy Bypass -File .\scripts\start.ps1" -ForegroundColor White
    Write-Host ""
    exit 1
}

$ErrorActionPreference = "Stop"

Write-Host "=== Mindscape AI Local Core - Start Script ===" -ForegroundColor Cyan
Write-Host ""

# Function to check Docker availability
function Test-DockerAvailable {
    Write-Host "Checking Docker availability..." -ForegroundColor Yellow

    # Check if docker command exists
    try {
        $dockerVersion = docker version --format '{{.Server.Version}}' 2>&1
        if ($LASTEXITCODE -ne 0) {
            return $false
        }
        Write-Host "  ✓ Docker client found" -ForegroundColor Green
    } catch {
        return $false
    }

    # Check if Docker daemon is running
    try {
        $dockerInfo = docker info 2>&1
        if ($LASTEXITCODE -ne 0) {
            Write-Host "  ✗ Docker daemon is not running" -ForegroundColor Red
            return $false
        }
        Write-Host "  ✓ Docker daemon is running" -ForegroundColor Green
    } catch {
        Write-Host "  ✗ Docker daemon is not running" -ForegroundColor Red
        return $false
    }

    # Check Docker context (Windows specific)
    try {
        $context = docker context show 2>&1
        if ($context -match "desktop-linux") {
            Write-Host "  ✓ Docker context: $context" -ForegroundColor Green
        } else {
            Write-Host "  ⚠ Docker context: $context (expected: desktop-linux)" -ForegroundColor Yellow
        }
    } catch {
        Write-Host "  ⚠ Could not check Docker context" -ForegroundColor Yellow
    }

    # Check Docker Compose
    try {
        $composeVersion = docker compose version 2>&1
        if ($LASTEXITCODE -eq 0) {
            Write-Host "  ✓ Docker Compose: $composeVersion" -ForegroundColor Green
        } else {
            Write-Host "  ✗ Docker Compose not available" -ForegroundColor Red
            return $false
        }
    } catch {
        Write-Host "  ✗ Docker Compose not available" -ForegroundColor Red
        return $false
    }

    return $true
}

# Check Docker if not skipped
if (-not $SkipCheck) {
    $dockerAvailable = Test-DockerAvailable

    if (-not $dockerAvailable) {
        Write-Host ""
        Write-Host "❌ Docker is not available or not running" -ForegroundColor Red
        Write-Host ""
        Write-Host "Please ensure:" -ForegroundColor Yellow
        Write-Host "  1. Docker Desktop is installed" -ForegroundColor Yellow
        Write-Host "  2. Docker Desktop is running" -ForegroundColor Yellow
        Write-Host "  3. Docker context is set to 'desktop-linux'" -ForegroundColor Yellow
        Write-Host ""
        Write-Host "To start Docker Desktop manually:" -ForegroundColor Cyan
        Write-Host "  - Open Docker Desktop from Start Menu" -ForegroundColor Cyan
        Write-Host "  - Wait for it to fully start" -ForegroundColor Cyan
        Write-Host ""
        Write-Host "To check Docker context:" -ForegroundColor Cyan
        Write-Host "  docker context show" -ForegroundColor Cyan
        Write-Host "  docker context use desktop-linux  # if needed" -ForegroundColor Cyan
        Write-Host ""
        Write-Host "After starting Docker Desktop, run this script again:" -ForegroundColor Cyan
        Write-Host "  .\scripts\start.ps1" -ForegroundColor Cyan
        Write-Host ""

        # Optional: Ask if user wants to try opening Docker Desktop
        $response = Read-Host "Would you like to try opening Docker Desktop? (Y/N)"
        if ($response -eq "Y" -or $response -eq "y") {
            Write-Host "Attempting to open Docker Desktop..." -ForegroundColor Yellow
            try {
                Start-Process "C:\Program Files\Docker\Docker\Docker Desktop.exe" -ErrorAction SilentlyContinue
                Write-Host "  Docker Desktop launch attempted. Please wait for it to start, then run this script again." -ForegroundColor Yellow
            } catch {
                Write-Host "  Could not automatically open Docker Desktop. Please start it manually." -ForegroundColor Yellow
            }
        }

        exit 1
    }

    Write-Host ""
    Write-Host "✅ Docker is ready" -ForegroundColor Green
    Write-Host ""
}

# Get script directory and project root
$ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$ProjectRoot = Split-Path -Parent $ScriptDir

# Verify we're in the correct project directory (check for docker-compose.yml)
if (-not (Test-Path (Join-Path $ProjectRoot "docker-compose.yml"))) {
    Write-Host ""
    Write-Host "❌ ERROR: Cannot find docker-compose.yml in project root" -ForegroundColor Red
    Write-Host ""
    Write-Host "Current project root: $ProjectRoot" -ForegroundColor Yellow
    Write-Host ""
    Write-Host "This script must be run from the mindscape-ai-local-core project directory." -ForegroundColor Yellow
    Write-Host "Please ensure:" -ForegroundColor Cyan
    Write-Host "  1. You are in the correct project directory" -ForegroundColor White
    Write-Host "  2. The project was cloned correctly" -ForegroundColor White
    Write-Host "  3. You run the script from the project root:" -ForegroundColor White
    Write-Host "     cd C:\Projects\mindscape-ai-local-core" -ForegroundColor Cyan
    Write-Host "     .\scripts\start.ps1" -ForegroundColor Cyan
    Write-Host ""
    exit 1
}

# Check if project is in a system directory (Windows)
$systemPaths = @(
    "$env:SystemRoot\system32",
    "$env:SystemRoot\SysWOW64",
    "$env:ProgramFiles",
    "$env:ProgramFiles(x86)"
)

$projectPathLower = $ProjectRoot.ToLower()
$isInSystemPath = $false
$matchedSystemPath = ""

foreach ($systemPath in $systemPaths) {
    if ($systemPath) {
        $systemPathLower = $systemPath.ToLower()
        if ($projectPathLower.StartsWith($systemPathLower)) {
            $isInSystemPath = $true
            $matchedSystemPath = $systemPath
            break
        }
    }
}

if ($isInSystemPath) {
    Write-Host ""
    Write-Host "❌ ERROR: Project is located in a system directory" -ForegroundColor Red
    Write-Host ""
    Write-Host "Current location: $ProjectRoot" -ForegroundColor Yellow
    Write-Host "System path detected: $matchedSystemPath" -ForegroundColor Yellow
    Write-Host ""
    Write-Host "The project should NOT be in a system directory (system32, Program Files, etc.)" -ForegroundColor Yellow
    Write-Host "System directories require administrator privileges and may cause permission issues." -ForegroundColor Yellow
    Write-Host ""
    Write-Host "Solution:" -ForegroundColor Cyan
    Write-Host "  1. Move the project to a user directory, for example:" -ForegroundColor White
    Write-Host "     - C:\Users\$env:USERNAME\Documents\mindscape-ai-local-core" -ForegroundColor White
    Write-Host "     - C:\Projects\mindscape-ai-local-core" -ForegroundColor White
    Write-Host "     - D:\Projects\mindscape-ai-local-core" -ForegroundColor White
    Write-Host ""
    Write-Host "  2. After moving, run the start script again:" -ForegroundColor White
    Write-Host "     .\scripts\start.ps1" -ForegroundColor Cyan
    Write-Host ""
    Write-Host "To move the project:" -ForegroundColor Cyan
    Write-Host "  1. Close this PowerShell window" -ForegroundColor White
    Write-Host "  2. Move the 'mindscape-ai-local-core' folder to a user directory" -ForegroundColor White
    Write-Host "  3. Open PowerShell in the new location and run the start script" -ForegroundColor White
    Write-Host ""
    exit 1
}

# Change to project root
Set-Location $ProjectRoot

# Check for existing containers with same names and offer to clean them up
Write-Host "Checking for existing containers..." -ForegroundColor Yellow
$existingContainers = docker ps -a --filter "name=mindscape-ai-local-core" --format "{{.Names}}" 2>&1
if ($LASTEXITCODE -eq 0 -and $existingContainers) {
    $containerList = $existingContainers -split "`n" | Where-Object { $_ -ne "" }
    if ($containerList.Count -gt 0) {
        Write-Host ""
        Write-Host "⚠️  Found existing containers with conflicting names:" -ForegroundColor Yellow
        foreach ($container in $containerList) {
            Write-Host "  - $container" -ForegroundColor Yellow
        }
        Write-Host ""
        Write-Host "These containers may prevent new containers from starting." -ForegroundColor Yellow
        Write-Host ""
        $response = Read-Host "Would you like to remove them? (Y/N)"
        if ($response -eq "Y" -or $response -eq "y") {
            Write-Host "Removing existing containers..." -ForegroundColor Cyan
            # Suppress all output including warnings (like missing env vars)
            # Use Out-Null to suppress output and filter warnings
            docker compose down 2>&1 | Where-Object { $_ -notmatch "level=warning" -and $_ -notmatch "time=" } | Out-Null
            if ($LASTEXITCODE -ne 0 -and $LASTEXITCODE -ne 1) {
                # Exit code 1 is OK (some containers may not exist)
                Write-Host "  ⚠ Warning: docker compose down had issues, trying individual removal..." -ForegroundColor Yellow
            }
            # Also try to remove individual containers if compose down didn't work
            foreach ($container in $containerList) {
                docker rm -f $container 2>&1 | Where-Object { $_ -notmatch "level=warning" -and $_ -notmatch "time=" } | Out-Null
            }
            Write-Host "  ✓ Containers removed" -ForegroundColor Green
            Write-Host ""
        } else {
            Write-Host ""
            Write-Host "⚠️  Keeping existing containers. If you encounter errors, run:" -ForegroundColor Yellow
            Write-Host "  docker compose down" -ForegroundColor Cyan
            Write-Host "  docker compose up -d" -ForegroundColor Cyan
            Write-Host ""
        }
    }
}

Write-Host "Starting services..." -ForegroundColor Cyan
Write-Host ""

# Start services
Write-Host "Building and starting containers..." -ForegroundColor Cyan
docker compose up -d

if ($LASTEXITCODE -ne 0) {
    Write-Host ""
    Write-Host "❌ Failed to start services" -ForegroundColor Red
    Write-Host ""

    # Wait a moment for containers to initialize
    Start-Sleep -Seconds 2

    # Check which services failed
    Write-Host "Checking service status..." -ForegroundColor Yellow

    # Get service status using a more reliable method
    # Suppress warnings (like missing env vars) and capture only stdout
    $serviceStatus = docker compose ps --format "table {{.Service}}\t{{.State}}\t{{.Health}}" 2>$null
    if ($LASTEXITCODE -ne 0) {
        # If command failed, try without format to get basic info
        $serviceStatus = docker compose ps 2>$null
    }

    $failedServices = @()

    # Parse the output line by line (skip header and warning lines)
    $lines = $serviceStatus -split "`n" | Where-Object {
        $_ -match "^\w" -and
        $_ -notmatch "SERVICE" -and
        $_ -notmatch "level=warning" -and
        $_ -notmatch "time="
    }

    foreach ($line in $lines) {
        # Match table format: SERVICE STATE HEALTH
        if ($line -match "^(?<service>\S+)\s+(?<state>\S+)\s+(?<health>\S*)\s*$") {
            $serviceName = $matches['service']
            $state = $matches['state']
            $health = $matches['health']

            # Check if service failed or is unhealthy
            if ($state -ne "running" -or $health -eq "unhealthy") {
                $failedServices += $serviceName
                Write-Host "  - $serviceName : $state" -ForegroundColor Red
                if ($health -eq "unhealthy") {
                    Write-Host "    Health: $health" -ForegroundColor Red
                }
            }
        }
    }

    if ($failedServices.Count -gt 0) {
        Write-Host ""
        Write-Host "⚠️  The following services failed to start or are unhealthy:" -ForegroundColor Yellow
        Write-Host ""

        # Show logs for failed services
        Write-Host "Showing logs for failed services..." -ForegroundColor Cyan
        Write-Host ""
        foreach ($service in $failedServices) {
            Write-Host "=== Logs for $service ===" -ForegroundColor Yellow
            # Suppress warnings from docker compose (like missing env vars)
            $logs = docker compose logs --tail=100 $service 2>&1 | Where-Object { $_ -notmatch "level=warning" -and $_ -notmatch "time=" }
            Write-Host $logs
            Write-Host ""
        }

        # Special handling for backend service
        if ($failedServices -contains "backend") {
            Write-Host "=== Backend Service Troubleshooting ===" -ForegroundColor Cyan
            Write-Host ""
            Write-Host "Common causes for backend startup failure:" -ForegroundColor Yellow
            Write-Host "  1. Database connection issues" -ForegroundColor White
            Write-Host "  2. Missing or incorrect environment variables" -ForegroundColor White
            Write-Host "  3. Port 8200 already in use" -ForegroundColor White
            Write-Host "  4. Health check timeout (service may need more time to start)" -ForegroundColor White
            Write-Host ""
            Write-Host "To check backend logs in detail:" -ForegroundColor Cyan
            Write-Host "  docker compose logs backend" -ForegroundColor White
            Write-Host ""
            Write-Host "To check if port 8200 is in use:" -ForegroundColor Cyan
            Write-Host "  netstat -ano | findstr :8200" -ForegroundColor White
            Write-Host ""
        }
    } else {
        # If we can't parse, show all logs
        Write-Host "Showing recent logs from all services..." -ForegroundColor Cyan
        Write-Host ""
        # Suppress warnings from docker compose
        $logs = docker compose logs --tail=50 2>&1 | Where-Object { $_ -notmatch "level=warning" -and $_ -notmatch "time=" }
        Write-Host $logs
    }

    Write-Host ""
    Write-Host "For more detailed logs, run:" -ForegroundColor Yellow
    Write-Host "  docker compose logs [service-name]" -ForegroundColor Cyan
    Write-Host ""
    Write-Host "To check service status:" -ForegroundColor Yellow
    Write-Host "  docker compose ps" -ForegroundColor Cyan
    Write-Host ""
    Write-Host "💡 Tip: If backend is unhealthy, it may need more time to start." -ForegroundColor Cyan
    Write-Host "   Wait 1-2 minutes and check again: docker compose ps" -ForegroundColor White
    Write-Host ""
    exit 1
}

# Check if any services are unhealthy after starting
Start-Sleep -Seconds 3
# Suppress warnings (like missing env vars) and capture only stdout
$serviceStatus = docker compose ps --format "table {{.Service}}\t{{.State}}\t{{.Health}}" 2>$null
if ($LASTEXITCODE -ne 0) {
    # If command failed, try without format to get basic info
    $serviceStatus = docker compose ps 2>$null
}

$unhealthyServices = @()

# Parse the output line by line (skip header and warning lines)
$lines = $serviceStatus -split "`n" | Where-Object {
    $_ -match "^\w" -and
    $_ -notmatch "SERVICE" -and
    $_ -notmatch "level=warning" -and
    $_ -notmatch "time="
}

foreach ($line in $lines) {
    # Match table format: SERVICE STATE HEALTH
    if ($line -match "^(?<service>\S+)\s+(?<state>\S+)\s+(?<health>\S*)\s*$") {
        $serviceName = $matches['service']
        $health = $matches['health']

        if ($health -eq "unhealthy") {
            $unhealthyServices += $serviceName
        }
    }
}

if ($unhealthyServices.Count -gt 0) {
    Write-Host ""
    Write-Host "⚠️  Warning: Some services are unhealthy:" -ForegroundColor Yellow
    foreach ($service in $unhealthyServices) {
        Write-Host "  - $service" -ForegroundColor Yellow
    }
    Write-Host ""
    Write-Host "Showing logs for unhealthy services..." -ForegroundColor Cyan
    Write-Host ""
    foreach ($service in $unhealthyServices) {
        Write-Host "=== Logs for $service ===" -ForegroundColor Yellow
        docker compose logs --tail=50 $service
        Write-Host ""
    }
    Write-Host ""
    Write-Host "Services may still be starting. Check again with:" -ForegroundColor Yellow
    Write-Host "  docker compose ps" -ForegroundColor Cyan
    Write-Host "  docker compose logs [service-name]" -ForegroundColor Cyan
    Write-Host ""
}

Write-Host ""
Write-Host "✅ Services started successfully!" -ForegroundColor Green
Write-Host ""
Write-Host "Access the application:" -ForegroundColor Cyan
Write-Host "  Frontend: http://localhost:8300" -ForegroundColor White
Write-Host "  Backend API: http://localhost:8200" -ForegroundColor White
Write-Host "  API Docs: http://localhost:8200/docs" -ForegroundColor White
Write-Host ""
Write-Host "Useful commands:" -ForegroundColor Cyan
Write-Host "  docker compose ps          # Check service status" -ForegroundColor White
Write-Host "  docker compose logs -f     # View logs" -ForegroundColor White
Write-Host "  docker compose stop        # Stop services" -ForegroundColor White
Write-Host "  docker compose down        # Stop and remove containers" -ForegroundColor White
Write-Host ""

