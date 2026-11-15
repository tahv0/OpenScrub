# Regression for a missing output directory such as D:\OpenScrubTest.
# Mock Docker to avoid CUDA builds, networking or any real container changes.
$ErrorActionPreference = 'Stop'
$scriptPath = Join-Path (Split-Path -Parent $PSScriptRoot) 'scripts/audit-windows-cuda.ps1'
$directory = Join-Path ([System.IO.Path]::GetTempPath()) ('openscrub-audit-' + [guid]::NewGuid().ToString('N'))
$target = Join-Path $directory 'missing/nested/cuda-audit.json'
$global:AuditMockCalls = @()

function global:docker {
    param([Parameter(ValueFromRemainingArguments = $true)][string[]]$arguments)
    $global:AuditMockCalls += ,($arguments -join ' ')
    $global:LASTEXITCODE = 0
    if ($arguments -contains 'inspect') { return 'sha256:mock-image' }
    if ($arguments -contains 'run') {
        return '{"components":[{"category":"training-python","files":1,"bytes":1024}],"possible_duplicate_libraries":[],"verified_identical_libraries":[]}'
    }
    throw "Unexpected Docker command: $($arguments -join ' ')"
}

try {
    if (Test-Path -LiteralPath $target) { throw 'Test output unexpectedly exists' }
    & $scriptPath -DockerContext 'desktop-linux' -Output $target
    if (-not (Test-Path -LiteralPath $target -PathType Leaf)) {
        throw 'Audit helper failed to create the report parent directory'
    }
    $report = Get-Content -LiteralPath $target -Raw | ConvertFrom-Json
    if ($report.components[0].category -ne 'training-python') {
        throw 'Audit output was not valid or expected JSON'
    }
    if ($global:AuditMockCalls.Count -ne 2) {
        throw "Expected Docker image inspect and one read-only run, got $($global:AuditMockCalls.Count)"
    }
    Write-Host 'CUDA audit report parent directory creation passed.'
} finally {
    Remove-Item Function:\docker -ErrorAction SilentlyContinue
    if (Test-Path -LiteralPath $directory) {
        Remove-Item -LiteralPath $directory -Recurse -Force
    }
}
