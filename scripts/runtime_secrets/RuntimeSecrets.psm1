Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"
$Script:IsWindowsHost = $PSVersionTable.PSEdition -eq "Desktop" -or (
    (Get-Variable -Name IsWindows -ErrorAction SilentlyContinue) -and $IsWindows
)

function Assert-MindscapeRuntimeSecretValue {
    param([Parameter(Mandatory = $true)][string]$Secret)

    if ([string]::IsNullOrEmpty($Secret)) {
        throw "Runtime secret is empty."
    }
    if ($Secret.Length -gt 4096) {
        throw "Runtime secret exceeds the 4096-character limit."
    }
    if ($Secret.Contains("`r") -or $Secret.Contains("`n") -or $Secret.Contains([char]0)) {
        throw "Runtime secret must be a single line."
    }
}

function Get-MindscapeLegacyRuntimeSecret {
    param([Parameter(Mandatory = $true)][string]$EnvFile)

    if (-not (Test-Path -LiteralPath $EnvFile -PathType Leaf)) {
        return ""
    }
    $value = ""
    foreach ($line in [System.IO.File]::ReadLines($EnvFile)) {
        if ($line.StartsWith("POSTGRES_VECTOR_RUNTIME_PASSWORD=")) {
            $value = $line.Substring("POSTGRES_VECTOR_RUNTIME_PASSWORD=".Length).TrimEnd("`r")
        }
    }
    if ($value.Length -ge 2) {
        if (($value.StartsWith('"') -and $value.EndsWith('"')) -or
            ($value.StartsWith("'") -and $value.EndsWith("'"))) {
            $value = $value.Substring(1, $value.Length - 2)
        }
    }
    if (-not [string]::IsNullOrEmpty($value)) {
        Assert-MindscapeRuntimeSecretValue -Secret $value
    }
    return $value
}

function New-MindscapeRuntimeSecret {
    $bytes = New-Object byte[] 32
    $rng = [System.Security.Cryptography.RandomNumberGenerator]::Create()
    try {
        $rng.GetBytes($bytes)
        return [Convert]::ToBase64String($bytes).TrimEnd('=').Replace('+', '-').Replace('/', '_')
    } finally {
        $rng.Dispose()
        [Array]::Clear($bytes, 0, $bytes.Length)
    }
}

function Initialize-MindscapeRuntimeSecrets {
    [CmdletBinding()]
    param([string]$ProjectRoot)

    if ([string]::IsNullOrWhiteSpace($ProjectRoot)) {
        $ProjectRoot = [System.IO.Path]::GetFullPath(
            (Join-Path $PSScriptRoot "..\..")
        )
    }
    if (-not $Script:IsWindowsHost) {
        throw "The Windows runtime secret facade requires Windows DPAPI."
    }

    $adapterPath = Join-Path $PSScriptRoot "DpapiSecretStore.psm1"
    Import-Module $adapterPath -Force
    $secretRoot = if ($env:MINDSCAPE_RUNTIME_SECRET_ROOT) {
        $env:MINDSCAPE_RUNTIME_SECRET_ROOT
    } else {
        Join-Path $ProjectRoot "data\secrets"
    }
    $envFile = if ($env:MINDSCAPE_RUNTIME_ENV_FILE) {
        $env:MINDSCAPE_RUNTIME_ENV_FILE
    } else {
        Join-Path $ProjectRoot ".env"
    }
    $secretPath = Join-Path $secretRoot "postgres_vector_runtime_password.dpapi"

    if (Test-Path -LiteralPath $secretPath -PathType Leaf) {
        $secret = Get-MindscapeDpapiSecret -Path $secretPath
        $state = "existing"
    } else {
        $secret = Get-MindscapeLegacyRuntimeSecret -EnvFile $envFile
        if ([string]::IsNullOrEmpty($secret)) {
            $secret = New-MindscapeRuntimeSecret
            $state = "created"
        } else {
            $state = "imported"
        }
        Assert-MindscapeRuntimeSecretValue -Secret $secret
        Set-MindscapeDpapiSecret -Path $secretPath -Secret $secret
    }

    Assert-MindscapeRuntimeSecretValue -Secret $secret
    [Environment]::SetEnvironmentVariable(
        "POSTGRES_VECTOR_RUNTIME_PASSWORD",
        $secret,
        [EnvironmentVariableTarget]::Process
    )
    if ([string]::IsNullOrWhiteSpace($env:HOME) -and -not [string]::IsNullOrWhiteSpace($env:USERPROFILE)) {
        [Environment]::SetEnvironmentVariable(
            "HOME",
            $env:USERPROFILE,
            [EnvironmentVariableTarget]::Process
        )
    }

    [PSCustomObject]@{
        State = $state
        Backend = "dpapi-current-user"
        Version = 1
    }
}

Export-ModuleMember -Function Initialize-MindscapeRuntimeSecrets
