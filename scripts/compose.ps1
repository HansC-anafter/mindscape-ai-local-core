param(
    [Parameter(ValueFromRemainingArguments = $true)]
    [string[]]$ComposeArguments
)

$ErrorActionPreference = "Stop"
$projectRoot = Split-Path -Parent $PSScriptRoot
$modulePath = Join-Path $PSScriptRoot "runtime_secrets\RuntimeSecrets.psm1"
Import-Module $modulePath -Force
$secretState = Initialize-MindscapeRuntimeSecrets -ProjectRoot $projectRoot
Write-Host "Runtime secrets ready ($($secretState.Backend), $($secretState.State))."

Push-Location $projectRoot
try {
    & docker compose @ComposeArguments
    exit $LASTEXITCODE
} finally {
    Pop-Location
}
