# Mock Docker CLI: ensure the experimental CUDA inference build cannot replace
# full app tags, Compose containers, media mounts or training dependency layers.
$ErrorActionPreference = 'Stop'
$repoRoot = Split-Path -Parent $PSScriptRoot
$helper = Join-Path $repoRoot 'scripts/build-windows-cuda-inference.ps1'
$global:MockCalls = @()
$global:MockFingerprint = $null

function global:docker {
    param([Parameter(ValueFromRemainingArguments = $true)][string[]]$parts)
    $global:MockCalls += ,($parts -join ' ')
    $global:LASTEXITCODE = 0
    if ($parts.Count -gt 2 -and $parts[0] -eq '--context') {
        if ($parts[1] -ne 'desktop-linux') {
            throw 'Incorrect docker context'
        }
        $parts = @($parts | Select-Object -Skip 2)
    }
    $line = $parts -join ' '
    if ($line -match '^buildx inspect ') {
        return "Name: desktop-linux`nDriver: docker"
    }
    if ($line -match '^image inspect ') {
        if (-not $global:MockFingerprint) {
            $global:LASTEXITCODE = 1
            return
        }
        return '[{"Config":{"Labels":{"org.openscrub.cuda.deps-fingerprint":"' + $global:MockFingerprint + '"}}}]'
    }
    if ($line -match '^buildx build ') {
        if ($line -match '--target cuda_inference_deps') {
            if ($line -notmatch 'OPENSCRUB_DEPS_FINGERPRINT=([0-9a-f]+)') {
                throw 'Inference dependency build omitted fingerprint'
            }
            $global:MockFingerprint = $Matches[1]
        }
        return
    }
    if ($line -match '^run ') {
        return 'GPU smoke test mock'
    }
    throw "Unexpected Docker operation: $line"
}

function AssertBuildCount($pattern, $wanted) {
    $matches = @($global:MockCalls | Where-Object { $_ -match $pattern })
    if ($matches.Count -ne $wanted) {
        throw "Expected $wanted for $pattern; found $($matches.Count): $($global:MockCalls -join '; ')"
    }
}
function AssertNoProductionMutations {
    $bad = @($global:MockCalls | Where-Object {
        $_ -match ' compose ' -or
        $_ -match 'system prune' -or
        $_ -match 'image rm' -or
        $_ -match 'openscrub-windows-test-openscrub(:| )' -or
        $_ -match 'openscrub-cuda-deps:local'
    })
    if ($bad.Count) {
        throw "Experimental helper touched production Docker resources: $($bad -join '; ')"
    }
}

try {
    & $helper -DockerContext 'desktop-linux'
    AssertBuildCount '--target cuda_inference_deps' 1
    AssertBuildCount '--target app' 1
    AssertBuildCount '--tag openscrub-cuda-inference-deps:local' 1
    AssertBuildCount '--tag openscrub-cuda-inference:local' 1
    AssertNoProductionMutations

    $global:MockCalls = @()
    & $helper -DockerContext 'desktop-linux'
    AssertBuildCount '--target cuda_inference_deps' 0
    AssertBuildCount '--target app' 1
    AssertNoProductionMutations

    $global:MockCalls = @()
    & $helper -DockerContext 'desktop-linux' -SmokeTest
    AssertBuildCount '--target cuda_inference_deps' 0
    AssertBuildCount ' run --rm --network none --gpus all ' 1
    AssertNoProductionMutations

    Write-Host 'Inference-only CUDA cold/warm/smoke mock tests passed.'
} finally {
    Remove-Item Function:\docker -ErrorAction SilentlyContinue
}
