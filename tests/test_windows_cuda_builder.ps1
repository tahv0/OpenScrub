# Mock the real Docker CLI on Windows/Linux, with no CUDA or network access.
# Proves the retained dependency image is built via Buildx, the application
# uses the SAME Buildx path, and Compose only starts the tagged local image.
$ErrorActionPreference = 'Stop'
$global:MockDockerCalls = @()
$global:MockDockerContext = 'desktop-linux'
$global:MockDockerDriver = 'docker'
$global:MockDepsFingerprint = $null
$wrapper = Join-Path (Split-Path -Parent $PSScriptRoot) 'scripts/build-windows-cuda.ps1'
$dependencyTag = 'openscrub-cuda-deps:local'
$applicationTag = 'openscrub-windows-test-openscrub:local'

function global:docker {
    param([Parameter(ValueFromRemainingArguments = $true)][string[]]$cliArgs)
    $global:MockDockerCalls += ,($cliArgs -join ' ')
    $argsWithoutContext = @($cliArgs)
    if ($argsWithoutContext.Count -gt 1 -and $argsWithoutContext[0] -eq '--context') {
        if ($argsWithoutContext[1] -ne $global:MockDockerContext) {
            throw "Wrong Docker context: $($argsWithoutContext[1])"
        }
        $argsWithoutContext = @($argsWithoutContext | Select-Object -Skip 2)
    }
    $global:LASTEXITCODE = 0
    $call = $argsWithoutContext -join ' '
    if ($call -eq 'context show') { return $global:MockDockerContext }
    if ($call -match '^buildx inspect ') {
        return "Name: $global:MockDockerContext`nDriver: $global:MockDockerDriver"
    }
    if ($call -match '^image inspect ') {
        if (-not $global:MockDepsFingerprint) {
            $global:LASTEXITCODE = 1
            return
        }
        return '[{"Config":{"Labels":{"org.openscrub.cuda.deps-fingerprint":"' + $global:MockDepsFingerprint + '"}}}]'
    }
    if ($call -match '^buildx build ') {
        if ($call -match [regex]::Escape("--tag $dependencyTag")) {
            if ($call -notmatch 'OPENSCRUB_DEPS_FINGERPRINT=([0-9a-f]+)') {
                throw 'Dependency build omitted its fingerprint'
            }
            $global:MockDepsFingerprint = $Matches[1]
        }
        return
    }
    if ($call -match '^compose ' -and $call -match ' build ') {
        throw 'The helper must never delegate its application build to Compose'
    }
}

function AssertBuildxTag($tag, $context, $expectedCount) {
    $builds = @($global:MockDockerCalls | Where-Object {
        $_ -match "^--context $([regex]::Escape($context)) buildx build " -and
        $_ -match [regex]::Escape("--tag $tag")
    })
    if ($builds.Count -ne $expectedCount) {
        throw "Expected $expectedCount Buildx builds for $tag in $context; got $($builds -join '; ')"
    }
}

try {
    foreach ($context in @('desktop-linux', 'default')) {
        $global:MockDockerCalls = @()
        $global:MockDockerContext = $context
        $global:MockDockerDriver = 'docker'
        $global:MockDepsFingerprint = $null

        & $wrapper -BuildOnly
        AssertBuildxTag $dependencyTag $context 1
        AssertBuildxTag $applicationTag $context 1
        $app = @($global:MockDockerCalls | Where-Object {
            $_ -match [regex]::Escape("--tag $applicationTag")
        })
        if ($app.Count -ne 1 -or $app[0] -notmatch '--target app' -or
            $app[0] -notmatch [regex]::Escape("OPENSCRUB_CUDA_DEPS_IMAGE=$dependencyTag")) {
            throw "App build did not start from retained dependencies: $($app -join '; ')"
        }
        if (@($global:MockDockerCalls | Where-Object { $_ -match ' compose ' }).Count -ne 0) {
            throw 'BuildOnly unexpectedly invoked Compose'
        }

        # Reusing the same dependency fingerprint must skip its expensive build.
        $global:MockDockerCalls = @()
        & $wrapper -BuildOnly
        AssertBuildxTag $dependencyTag $context 0
        AssertBuildxTag $applicationTag $context 1

        # A normal invocation may start the *already built* local image, but
        # must never call Compose build, which triggered the Windows failure.
        $global:MockDockerCalls = @()
        & $wrapper
        AssertBuildxTag $dependencyTag $context 0
        AssertBuildxTag $applicationTag $context 1
        $up = @($global:MockDockerCalls | Where-Object {
            $_ -match "^--context $([regex]::Escape($context)) compose " -and
            $_ -match ' up -d --no-build$'
        })
        if ($up.Count -ne 1) {
            throw "Compose did not start the prebuilt app in $context: $($up -join '; ')"
        }
    }

    # Fail early if someone selects a nonlocal builder. Its image cache could
    # be in a different daemon, losing the dependency image and rerunning pip.
    $global:MockDockerCalls = @()
    $global:MockDockerContext = 'desktop-linux'
    $global:MockDockerDriver = 'docker-container'
    $global:MockDepsFingerprint = $null
    $rejected = $false
    try { & $wrapper -BuildOnly } catch {
        $rejected = $_.Exception.Message -match 'must use the docker driver'
    }
    if (-not $rejected) {
        throw 'Non-local builder was not rejected before package installation'
    }
    if (@($global:MockDockerCalls | Where-Object { $_ -match ' buildx build ' }).Count -ne 0) {
        throw 'A nonlocal builder started an expensive dependency installation'
    }
    Write-Host 'Windows CUDA dependency/app Buildx handoff tests passed.'
} finally {
    Remove-Item Function:\docker -ErrorAction SilentlyContinue
}
