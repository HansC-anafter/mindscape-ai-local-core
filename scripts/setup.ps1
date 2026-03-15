# Mindscape AI Local Core - Windows Setup Script
# Called by install.ps1 during first-time installation
# Ensures prerequisites and environment are ready before starting services

$ErrorActionPreference = "Stop"

Write-Host "Running Windows setup..." -ForegroundColor Cyan
Write-Host ""

# --- Check Node.js (required for Device Node + MCP Gateway) ---
$nodeAvailable = Get-Command node -ErrorAction SilentlyContinue
if ($nodeAvailable) {
    $nodeVersion = node --version 2>$null
    Write-Host "  ✓ Node.js found: $nodeVersion" -ForegroundColor Green
} else {
    Write-Host "  ⚠️  Node.js not found. Device Node and MCP Gateway require Node.js." -ForegroundColor Yellow
    Write-Host "     Install from: https://nodejs.org/ or: winget install OpenJS.NodeJS" -ForegroundColor Yellow
}

# --- Check Ollama (optional — for local inference) ---
$ollamaAvailable = Get-Command ollama -ErrorAction SilentlyContinue
if ($ollamaAvailable) {
    Write-Host "  ✓ Ollama found" -ForegroundColor Green
} else {
    Write-Host "  ⚠️  Ollama not found (optional). For local inference without API keys:" -ForegroundColor Yellow
    Write-Host "     Install from: https://ollama.com/download" -ForegroundColor Yellow
}

# --- Ensure .env exists ---
$envFile = Join-Path $PSScriptRoot "..\.env"
if (-not (Test-Path $envFile)) {
    $envTemplate = Join-Path $PSScriptRoot "..\.env.example"
    if (Test-Path $envTemplate) {
        Copy-Item $envTemplate $envFile
        Write-Host "  ✓ Created .env from template" -ForegroundColor Green
    } else {
        Write-Host "  ⚠️  No .env file found. start.ps1 will use defaults." -ForegroundColor Yellow
    }
} else {
    Write-Host "  ✓ .env file exists" -ForegroundColor Green
}

# --- Build Device Node if present ---
$deviceNodeDir = Join-Path $PSScriptRoot "..\device-node"
if ((Test-Path $deviceNodeDir) -and $nodeAvailable) {
    Write-Host ""
    Write-Host "Building Device Node..." -ForegroundColor Cyan
    Set-Location $deviceNodeDir
    npm install --silent 2>$null
    npm run build --silent 2>$null
    Set-Location (Join-Path $PSScriptRoot "..")
    Write-Host "  ✓ Device Node built" -ForegroundColor Green
}

Write-Host ""
Write-Host "  ✓ Setup complete" -ForegroundColor Green
Write-Host ""
