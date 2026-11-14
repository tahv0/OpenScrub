# Docker CLI mock tests: no daemon, CUDA image or network access required.
# Verify that the Windows build script uses the *active* context's builder for
# both dependency and application builds, not Docker's hard-coded "default".
$ErrorActionPreference = 'Stop'
$global:MockDockerCalls = @()
$global:MockDockerContext = 'desktop-linux'
$global:MockDockerDriver = 'docker'
$wrapper = Join-Path (Split-Path -Parent $PSScriptRoot) 'scripts/build-windows-cuda.ps1'

function global:docker {
    param([Parameter(ValueFromRemainingArguments = $true)][string[]]$cliArgs)
    $global:MockDockerCalls += ,($cliArgs -join ' ')
    $global:LASTEXITCODE = 0
    if ($cliArgs[0] -eq 'context' -and $cliArgs[1] -eq 'show') {
        return $global:MockDockerContext
    }
    if ($cliArgs[0] -eq 'buildx' -and $cliArgs[1] -eq 'inspect') {
        return "Name: $global:MockDockerContext`nDriver: $global:MockDockerDriver"
    }
    if ($cliArgs[0] -eq 'image' -and $cliArgs[1] -eq 'inspect') {
        # Cache-miss is normal: fake all subsequent build commands as success.
        $global:LASTEXITCODE = 1
        return
    }
}

try {
    foreach ($context in @('desktop-linux', 'default')) {
        $global:MockDockerCalls = @()
        $global:MockDockerContext = $context
        $global:MockDockerDriver = 'docker'
        & $wrapper -BuildOnly
        $depBuild = @($global:MockDockerCalls | Where-Object { $_ -match '^buildx build ' })
        $appBuild = @($global:MockDockerCalls | Where-Object { $_ -match '^compose ' -and $_ -match ' build --builder ' })
        if ($depBuild.Count -ne 1 -or $depBuild[0] -notmatch ("--builder " + [regex]::Escape($context) + " ")) {
            throw "Dependency build did not select '$context': $($depBuild -join '; ')"
        }
        if ($appBuild.Count -ne 1 -or $appBuild[0] -notmatch ("--builder " + [regex]::Escape($context) + "$")) {
            throw "Compose build did not select '$context': $($appBuild -join '; ')"
        }
        if ($depBuild[0] -notmatch '--target cuda_deps') {
            throw "Dependency stage was not targeted: $depBuild"
        }
    }

    # Explicitly reject docker-container builders; they need not see an image
    # tagged into the daemon that Compose uses to start the application.
    $global:MockDockerCalls = @()
    $global:MockDockerContext = 'desktop-linux'
    $global:MockDockerDriver = 'docker-container'
    $rejected = $false
    try { & $wrapper -BuildOnly } catch {
        $rejected = $_.Exception.Message -match 'must use the docker driver'
    }
    if (-not $rejected) { throw 'Non-local builder should be rejected before package installs.' }
    if (@($global:MockDockerCalls | Where-Object { $_ -match '^buildx build ' }).Count -ne 0) {
        throw 'A non-local builder unexpectedly started the dependency install.'
    }
    Write-Host 'Docker Desktop context/builder selection tests passed.'
} finally {
    Remove-Item Function:\docker -ErrorAction SilentlyContinue
}
