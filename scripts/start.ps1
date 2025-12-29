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
            $null = docker compose down 2>&1
            if ($LASTEXITCODE -ne 0 -and $LASTEXITCODE -ne 1) {
                # Exit code 1 is OK (some containers may not exist)
                Write-Host "  ⚠ Warning: docker compose down had issues, trying individual removal..." -ForegroundColor Yellow
            }
            # Also try to remove individual containers if compose down didn't work
            foreach ($container in $containerList) {
                $null = docker rm -f $container 2>&1
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
    $serviceStatus = docker compose ps --format "table {{.Service}}\t{{.State}}\t{{.Health}}" 2>&1
    $failedServices = @()
    
    # Parse the output line by line (skip header)
    $lines = $serviceStatus -split "`n" | Where-Object { $_ -match "^\w" -and $_ -notmatch "SERVICE" }
    foreach ($line in $lines) {
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
            docker compose logs --tail=50 $service
            Write-Host ""
        }
    } else {
        # If we can't parse, show all logs
        Write-Host "Showing recent logs from all services..." -ForegroundColor Cyan
        Write-Host ""
        docker compose logs --tail=50
    }

    Write-Host ""
    Write-Host "For more detailed logs, run:" -ForegroundColor Yellow
    Write-Host "  docker compose logs [service-name]" -ForegroundColor Cyan
    Write-Host ""
    Write-Host "To check service status:" -ForegroundColor Yellow
    Write-Host "  docker compose ps" -ForegroundColor Cyan
    Write-Host ""
    exit 1
}

# Check if any services are unhealthy after starting
Start-Sleep -Seconds 3
$serviceStatus = docker compose ps --format "table {{.Service}}\t{{.State}}\t{{.Health}}" 2>&1
$unhealthyServices = @()

# Parse the output line by line (skip header)
$lines = $serviceStatus -split "`n" | Where-Object { $_ -match "^\w" -and $_ -notmatch "SERVICE" }
foreach ($line in $lines) {
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

