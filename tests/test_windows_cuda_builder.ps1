# Mock Docker on CI without a daemon, CUDA install, or network requests.
# Regression for Docker Desktop: Buildx --builder works for the dependency
# image; Compose build succeeds only when --context is set with NO --builder.
$ErrorActionPreference = 'Stop'
$global:MockDockerCalls = @()
$global:MockDockerContext = 'desktop-linux'
$global:MockDockerDriver = 'docker'
$global:MockDepsFingerprint = $null
$wrapper = Join-Path (Split-Path -Parent $PSScriptRoot) 'scripts/build-windows-cuda.ps1'

function global:docker {
    param([Parameter(ValueFromRemainingArguments = $true)][string[]]$cliArgs)
    $global:MockDockerCalls += ,($cliArgs -join ' ')
    $remaining = @($cliArgs)
    if ($remaining.Count -ge 2 -and $remaining[0] -eq '--context') {
        if ($remaining[1] -ne $global:MockDockerContext) {
            throw "Wrong Docker context: $($remaining[1])"
        }
        $remaining = @($remaining | Select-Object -Skip 2)
    }
    $global:LASTEXITCODE = 0
    $call = $remaining -join ' '
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
        if ($call -notmatch '--target cuda_deps') {
            throw "Unexpected Buildx target: $call"
        }
        if ($call -notmatch 'OPENSCRUB_DEPS_FINGERPRINT=([0-9a-f]+)') {
            throw 'Dependency build omitted its fingerprint'
        }
        $global:MockDepsFingerprint = $Matches[1]
        return
    }
    if ($call -match '^compose ' -and $call -match '\sbuild(\s|$)' -and $call -match '--builder') {
        throw 'Compose must not receive --builder on Docker Desktop'
    }
}

function AssertCommands($context, $depsCount, $composeBuilds, $composeUps) {
    $prefix = "^--context $([regex]::Escape($context)) "
    $dep = @($global:MockDockerCalls | Where-Object {
        $_ -match ($prefix + 'buildx build ') -and $_ -match '--target cuda_deps'
    })
    $build = @($global:MockDockerCalls | Where-Object {
        $_ -match ($prefix + 'compose --progress plain ') -and
        $_ -match ' compose.windows-cuda.yml build$'
    })
    $up = @($global:MockDockerCalls | Where-Object {
        $_ -match ($prefix + 'compose -f ') -and
        $_ -match ' compose.windows-cuda.yml up -d --no-build$'
    })
    if ($dep.Count -ne $depsCount -or $build.Count -ne $composeBuilds -or $up.Count -ne $composeUps) {
        throw "Wrong command counts in $context: deps=$($dep.Count), compose-build=$($build.Count), up=$($up.Count). Calls: $($global:MockDockerCalls -join '; ')"
    }
    if ($global:MockDockerCalls -match '--builder default' -and $context -ne 'default') {
        throw 'Used default builder in another Docker context'
    }
    if (@($build | Where-Object { $_ -match '--builder' }).Count -gt 0) {
        throw 'Compose received an explicit --builder argument'
    }
}

try {
    foreach ($context in @('desktop-linux', 'default')) {
        $global:MockDockerContext = $context
        $global:MockDockerDriver = 'docker'
        $global:MockDepsFingerprint = $null
        $global:MockDockerCalls = @()
        & $wrapper -BuildOnly
        AssertCommands $context 1 1 0

        # A second code-only build must skip the expensive PyTorch image.
        $global:MockDockerCalls = @()
        & $wrapper -BuildOnly
        AssertCommands $context 0 1 0

        # A normal run still builds the application and starts it without
        # calling Compose's problematic --builder path.
        $global:MockDockerCalls = @()
        & $wrapper
        AssertCommands $context 0 1 1
    }
    $global:MockDockerContext = 'desktop-linux'
    $global:MockDockerDriver = 'docker-container'
    $global:MockDepsFingerprint = $null
    $global:MockDockerCalls = @()
    $rejected = $false
    try { & $wrapper -BuildOnly } catch {
        $rejected = $_.Exception.Message -match 'must use the docker driver'
    }
    if (-not $rejected) { throw 'Non-local builder was not rejected' }
    if (@($global:MockDockerCalls | Where-Object { $_ -match '\sbuild(\s|$)' }).Count -ne 0) {
        throw 'Build started with an unsupported builder'
    }
    Write-Host 'Windows CUDA context-only Compose builder regression tests passed.'
} finally {
    Remove-Item Function:\docker -ErrorAction SilentlyContinue
}
