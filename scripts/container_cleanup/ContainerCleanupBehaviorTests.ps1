$ErrorActionPreference = "Stop"

$script:DockerResponses = [System.Collections.Queue]::new()
$script:DockerCalls = @()

function global:docker {
    $script:DockerCalls += ,@($args)
    if ($script:DockerResponses.Count -eq 0) {
        throw "Unexpected docker invocation: $($args -join ' ')"
    }

    $response = $script:DockerResponses.Dequeue()
    foreach ($line in @($response.Output)) {
        Write-Output $line
    }
    $global:LASTEXITCODE = $response.ExitCode
}

function New-DockerResponse {
    param(
        [int]$ExitCode,
        [string[]]$Output = @()
    )

    [PSCustomObject]@{
        ExitCode = $ExitCode
        Output = $Output
    }
}

function Reset-DockerFake {
    $script:DockerResponses.Clear()
    $script:DockerCalls = @()
}

function Assert-Equal {
    param(
        [Parameter(Mandatory = $true)]$Expected,
        [Parameter(Mandatory = $true)]$Actual,
        [Parameter(Mandatory = $true)][string]$Message
    )

    if ($Expected -ne $Actual) {
        throw "$Message Expected '$Expected', got '$Actual'."
    }
}

$modulePath = Join-Path $PSScriptRoot "ContainerCleanup.psm1"
Import-Module $modulePath -Force

Reset-DockerFake
$script:DockerResponses.Enqueue((New-DockerResponse -ExitCode 0))
Remove-MindscapeResidualContainers
Assert-Equal -Expected 1 -Actual $script:DockerCalls.Count `
    -Message "An empty post-compose query must not invoke docker rm."

Reset-DockerFake
$script:DockerResponses.Enqueue((
    New-DockerResponse -ExitCode 0 -Output @("mindscape-ai-local-core-backend")
))
$script:DockerResponses.Enqueue((New-DockerResponse -ExitCode 1))
$script:DockerResponses.Enqueue((New-DockerResponse -ExitCode 0))
Remove-MindscapeResidualContainers
Assert-Equal -Expected 3 -Actual $script:DockerCalls.Count `
    -Message "A container that disappears during removal must be accepted."

Reset-DockerFake
$script:DockerResponses.Enqueue((
    New-DockerResponse -ExitCode 0 -Output @("mindscape-ai-local-core-backend")
))
$script:DockerResponses.Enqueue((New-DockerResponse -ExitCode 1))
$script:DockerResponses.Enqueue((
    New-DockerResponse -ExitCode 0 -Output @("mindscape-ai-local-core-backend")
))
$failedAsExpected = $false
try {
    Remove-MindscapeResidualContainers
} catch {
    $failedAsExpected = $_.Exception.Message -match "mindscape-ai-local-core-backend"
}
Assert-Equal -Expected $true -Actual $failedAsExpected `
    -Message "A container that remains after removal must fail cleanup."

Write-Host "Container cleanup behavior tests passed."
