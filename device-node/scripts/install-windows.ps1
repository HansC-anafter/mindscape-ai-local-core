# Mindscape Device Node - Windows Installation Script
# Run as Administrator

$ErrorActionPreference = "Stop"

$ProjectDir = Split-Path -Parent (Split-Path -Parent $MyInvocation.MyCommand.Path)
$InstallDir = "$env:ProgramFiles\Mindscape\DeviceNode"
$ServiceName = "MindscapeDeviceNode"

Write-Host "🚀 Installing Mindscape Device Node..." -ForegroundColor Cyan

# Check for administrator privileges
$isAdmin = ([Security.Principal.WindowsPrincipal] [Security.Principal.WindowsIdentity]::GetCurrent()).IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)
if (-not $isAdmin) {
    Write-Host "❌ This script must be run as Administrator" -ForegroundColor Red
    exit 1
}

# Build the project
Write-Host "📦 Building project..." -ForegroundColor Yellow
Set-Location $ProjectDir
npm install
npm run build

# Install default CLI agent (skip if already present)
# Only gemini-cli by default (free tier). Others installed on-demand via bridge.
$geminiCmd = Get-Command gemini -ErrorAction SilentlyContinue
if ($geminiCmd) {
    Write-Host "   ✅ gemini-cli already installed ($($geminiCmd.Source))" -ForegroundColor Green
} else {
    Write-Host "📦 Installing gemini-cli (default agent)..." -ForegroundColor Yellow
    try {
        npm install -g @google/gemini-cli 2>$null
        Write-Host "   ✅ gemini-cli installed" -ForegroundColor Green
    } catch {
        Write-Host "   ⚠️ gemini-cli install failed (non-fatal). Install manually: npm install -g @google/gemini-cli" -ForegroundColor Yellow
    }
}

# Create installation directory
Write-Host "📁 Creating installation directory..." -ForegroundColor Yellow
New-Item -ItemType Directory -Force -Path $InstallDir | Out-Null
Copy-Item -Recurse -Force "$ProjectDir\dist" "$InstallDir\"
Copy-Item -Recurse -Force "$ProjectDir\config" "$InstallDir\"
Copy-Item -Force "$ProjectDir\package.json" "$InstallDir\"

# Install production dependencies
Write-Host "📦 Installing production dependencies..." -ForegroundColor Yellow
Set-Location $InstallDir
npm install --production

# Install as Windows Service using node-windows (or nssm)
Write-Host "🔧 Installing Windows Service..." -ForegroundColor Yellow

# Check if nssm is available
$nssm = Get-Command nssm -ErrorAction SilentlyContinue
if ($nssm) {
    # Remove existing service if present
    nssm stop $ServiceName 2>$null
    nssm remove $ServiceName confirm 2>$null

    # Install new service
    nssm install $ServiceName "node.exe" "$InstallDir\dist\index.js"
    nssm set $ServiceName AppDirectory $InstallDir
    nssm set $ServiceName DisplayName "Mindscape Device Node"
    nssm set $ServiceName Description "Local Host Agent for Mindscape AI"
    nssm set $ServiceName Start SERVICE_AUTO_START

    # Start the service
    nssm start $ServiceName

    Write-Host "✅ Service installed using NSSM" -ForegroundColor Green
} else {
    Write-Host "⚠️ NSSM not found. Please install NSSM or run manually:" -ForegroundColor Yellow
    Write-Host "   node $InstallDir\dist\index.js" -ForegroundColor White
}

Write-Host ""
Write-Host "✅ Mindscape Device Node installed successfully!" -ForegroundColor Green
Write-Host ""
Write-Host "To check status:" -ForegroundColor Cyan
Write-Host "  Get-Service $ServiceName"
Write-Host ""
Write-Host "To uninstall:" -ForegroundColor Cyan
Write-Host "  nssm remove $ServiceName confirm"
Write-Host "  Remove-Item -Recurse -Force '$InstallDir'"
