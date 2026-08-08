Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"
$Script:IsWindowsHost = $PSVersionTable.PSEdition -eq "Desktop" -or (
    (Get-Variable -Name IsWindows -ErrorAction SilentlyContinue) -and $IsWindows
)

$Script:Entropy = [System.Text.Encoding]::UTF8.GetBytes(
    "mindscape-ai-local-core/runtime-secret/v1"
)

function Assert-MindscapeWindowsHost {
    if (-not $Script:IsWindowsHost) {
        throw "The DPAPI runtime secret adapter requires Windows."
    }
}

function Assert-MindscapePrivatePath {
    param([Parameter(Mandatory = $true)][string]$Path)

    if (Test-Path -LiteralPath $Path) {
        $item = Get-Item -LiteralPath $Path -Force
        if (($item.Attributes -band [System.IO.FileAttributes]::ReparsePoint) -ne 0) {
            throw "Runtime secret storage must not use a reparse point: $Path"
        }
    }
}

function Set-MindscapePrivateAcl {
    param(
        [Parameter(Mandatory = $true)][string]$Path,
        [switch]$Directory
    )

    $identity = [System.Security.Principal.WindowsIdentity]::GetCurrent().Name
    $userGrant = if ($Directory) { "${identity}:(OI)(CI)(F)" } else { "${identity}:(F)" }
    $systemGrant = if ($Directory) { "*S-1-5-18:(OI)(CI)(F)" } else { "*S-1-5-18:(F)" }
    & icacls.exe $Path /inheritance:r /grant:r $userGrant /grant:r $systemGrant | Out-Null
    if ($LASTEXITCODE -ne 0) {
        throw "Unable to restrict the runtime secret ACL: $Path"
    }
}

function Get-MindscapeDpapiSecret {
    param([Parameter(Mandatory = $true)][string]$Path)

    Assert-MindscapeWindowsHost
    Assert-MindscapePrivatePath -Path $Path
    if (-not (Test-Path -LiteralPath $Path -PathType Leaf)) {
        throw "DPAPI runtime secret is missing: $Path"
    }
    $directory = Split-Path -Parent $Path
    Assert-MindscapePrivatePath -Path $directory
    Set-MindscapePrivateAcl -Path $directory -Directory
    Set-MindscapePrivateAcl -Path $Path

    $encoded = [System.IO.File]::ReadAllText($Path).Trim()
    if ([string]::IsNullOrWhiteSpace($encoded)) {
        throw "DPAPI runtime secret is empty: $Path"
    }
    $protectedBytes = [Convert]::FromBase64String($encoded)
    try {
        $plainBytes = [System.Security.Cryptography.ProtectedData]::Unprotect(
            $protectedBytes,
            $Script:Entropy,
            [System.Security.Cryptography.DataProtectionScope]::CurrentUser
        )
        try {
            return [System.Text.Encoding]::UTF8.GetString($plainBytes)
        } finally {
            [Array]::Clear($plainBytes, 0, $plainBytes.Length)
        }
    } finally {
        [Array]::Clear($protectedBytes, 0, $protectedBytes.Length)
    }
}

function Set-MindscapeDpapiSecret {
    param(
        [Parameter(Mandatory = $true)][string]$Path,
        [Parameter(Mandatory = $true)][string]$Secret
    )

    Assert-MindscapeWindowsHost
    $directory = Split-Path -Parent $Path
    Assert-MindscapePrivatePath -Path $directory
    Assert-MindscapePrivatePath -Path $Path
    [System.IO.Directory]::CreateDirectory($directory) | Out-Null
    Set-MindscapePrivateAcl -Path $directory -Directory

    $plainBytes = [System.Text.Encoding]::UTF8.GetBytes($Secret)
    try {
        $protectedBytes = [System.Security.Cryptography.ProtectedData]::Protect(
            $plainBytes,
            $Script:Entropy,
            [System.Security.Cryptography.DataProtectionScope]::CurrentUser
        )
        try {
            $encoded = [Convert]::ToBase64String($protectedBytes)
            $utf8NoBom = New-Object System.Text.UTF8Encoding($false)
            [System.IO.File]::WriteAllText($Path, $encoded, $utf8NoBom)
        } finally {
            [Array]::Clear($protectedBytes, 0, $protectedBytes.Length)
        }
    } finally {
        [Array]::Clear($plainBytes, 0, $plainBytes.Length)
    }
    Set-MindscapePrivateAcl -Path $Path
}

Export-ModuleMember -Function Get-MindscapeDpapiSecret, Set-MindscapeDpapiSecret
