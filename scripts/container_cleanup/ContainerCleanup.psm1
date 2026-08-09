Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

function Invoke-MindscapeContainerNameQuery {
    $oldErrorAction = $ErrorActionPreference
    $ErrorActionPreference = "SilentlyContinue"
    $output = @()
    $exitCode = 1

    try {
        $output = @(
            docker ps -a --filter "name=mindscape-ai-local-core" --format "{{.Names}}" 2>$null
        )
        $exitCode = $LASTEXITCODE
    } catch {
        $output = @()
        $exitCode = 1
    } finally {
        $ErrorActionPreference = $oldErrorAction
    }

    $names = @(
        $output |
            ForEach-Object { "$_".Trim() } |
            Where-Object { -not [string]::IsNullOrWhiteSpace($_) }
    )

    [PSCustomObject]@{
        ExitCode = $exitCode
        Names = $names
    }
}

function Get-MindscapeConflictingContainers {
    [CmdletBinding()]
    param()

    $query = Invoke-MindscapeContainerNameQuery
    if ($query.ExitCode -ne 0) {
        throw "Unable to list existing Mindscape containers."
    }

    return @($query.Names)
}

function Remove-MindscapeResidualContainers {
    [CmdletBinding()]
    param()

    $residualContainers = @(Get-MindscapeConflictingContainers)
    $failedContainers = @()

    foreach ($container in $residualContainers) {
        $oldErrorAction = $ErrorActionPreference
        $ErrorActionPreference = "SilentlyContinue"
        $removeExitCode = 1

        try {
            docker rm -f $container 2>$null | Out-Null
            $removeExitCode = $LASTEXITCODE
        } catch {
            $removeExitCode = 1
        } finally {
            $ErrorActionPreference = $oldErrorAction
        }

        if ($removeExitCode -eq 0) {
            continue
        }

        $verification = Invoke-MindscapeContainerNameQuery
        if ($verification.ExitCode -ne 0 -or $verification.Names -contains $container) {
            $failedContainers += $container
        }
    }

    if ($failedContainers.Count -gt 0) {
        throw "Unable to remove conflicting containers: $($failedContainers -join ', ')."
    }
}

Export-ModuleMember -Function @(
    "Get-MindscapeConflictingContainers",
    "Remove-MindscapeResidualContainers"
)
