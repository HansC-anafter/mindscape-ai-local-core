#Requires -Version 5.1
<#
.SYNOPSIS
    Mindscape AI Local Core - One-Line Installer for Windows
.DESCRIPTION
    Automatically clones, sets up, and starts Mindscape AI Local Core
.PARAMETER Dir
    Custom directory name for installation (default: mindscape-ai-local-core)
.PARAMETER Branch
    Git branch to clone (default: master)
.EXAMPLE
    irm https://raw.githubusercontent.com/HansC-anafter/mindscape-ai-local-core/master/install.ps1 | iex
.EXAMPLE
    irm https://... | iex -Dir my-project
#>

param(
    [string]$Dir = "mindscape-ai-local-core",
    [string]$Branch = "master"
)

$ErrorActionPreference = "Stop"
$RepoUrl = "https://github.com/HansC-anafter/mindscape-ai-local-core.git"

Write-Host ""
Write-Host "╔═══════════════════════════════════════════════════╗" -ForegroundColor Cyan
Write-Host "║   Mindscape AI Local Core - Installer             ║" -ForegroundColor Cyan
Write-Host "╚═══════════════════════════════════════════════════╝" -ForegroundColor Cyan
Write-Host ""

# Check prerequisites
function Test-Command($cmdname) {
    return [bool](Get-Command -Name $cmdname -ErrorAction SilentlyContinue)
}

Write-Host "Checking prerequisites..." -ForegroundColor Yellow

if (-not (Test-Command "git")) {
    Write-Host "❌ Git is required but not installed." -ForegroundColor Red
    Write-Host "   Install from: https://git-scm.com/download/win" -ForegroundColor Gray
    exit 1
}
Write-Host "✓ Git found" -ForegroundColor Green

if (-not (Test-Command "docker")) {
    Write-Host "❌ Docker is required but not installed." -ForegroundColor Red
    Write-Host "   Install from: https://www.docker.com/products/docker-desktop/" -ForegroundColor Gray
    exit 1
}
Write-Host "✓ Docker found" -ForegroundColor Green

# Check if Docker is running
try {
    docker info 2>&1 | Out-Null
    Write-Host "✓ Docker is running" -ForegroundColor Green
} catch {
    Write-Host "❌ Docker is not running. Please start Docker Desktop and try again." -ForegroundColor Red
    exit 1
}

Write-Host ""

# Check if directory exists
if (Test-Path $Dir) {
    Write-Host "⚠️  Directory '$Dir' already exists." -ForegroundColor Yellow
    $response = Read-Host "Update existing installation? (y/N)"
    if ($response -match "^[Yy]") {
        Write-Host "Updating existing installation..." -ForegroundColor Cyan
        Set-Location $Dir
        git pull origin $Branch
    } else {
        Write-Host "Installation cancelled." -ForegroundColor Yellow
        exit 0
    }
} else {
    Write-Host "Cloning repository..." -ForegroundColor Cyan
    git clone --branch $Branch $RepoUrl $Dir
    Set-Location $Dir
}

Write-Host ""
Write-Host "Installing..." -ForegroundColor Cyan

# Run setup if exists
if (Test-Path "scripts\setup.ps1") {
    Write-Host "Running setup..." -ForegroundColor Cyan
    & .\scripts\setup.ps1
}

# Start services
if (Test-Path "scripts\start.ps1") {
    Write-Host ""
    Write-Host "Starting services..." -ForegroundColor Cyan
    & .\scripts\start.ps1
}

Write-Host ""
Write-Host "╔═══════════════════════════════════════════════════╗" -ForegroundColor Green
Write-Host "║   ✅ Installation Complete!                       ║" -ForegroundColor Green
Write-Host "╚═══════════════════════════════════════════════════╝" -ForegroundColor Green
Write-Host ""
Write-Host "Your Mindscape AI is running at:" -ForegroundColor White
Write-Host "  • Web Console: http://localhost:8300" -ForegroundColor Cyan
Write-Host "  • Backend API: http://localhost:8200" -ForegroundColor Cyan
Write-Host ""
Write-Host "Next steps:" -ForegroundColor Yellow
Write-Host "  cd $Dir"
Write-Host "  # Configure API keys in .env (optional if using Ollama)"
Write-Host ""
