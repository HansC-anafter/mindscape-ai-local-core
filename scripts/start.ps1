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

Write-Host "Starting services..." -ForegroundColor Cyan
Write-Host ""

# Start services
docker compose up -d

if ($LASTEXITCODE -ne 0) {
    Write-Host ""
    Write-Host "❌ Failed to start services" -ForegroundColor Red
    Write-Host ""
    Write-Host "Check logs with:" -ForegroundColor Yellow
    Write-Host "  docker compose logs" -ForegroundColor Cyan
    exit 1
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

