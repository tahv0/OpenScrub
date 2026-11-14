# Build a retained CUDA dependency image once, then rebuild only OpenScrub code.
# Run from any directory: .\scripts\build-windows-cuda.ps1
# The pinned, tagged dependency image is intentionally NOT just a BuildKit
# cache mount: Docker Desktop garbage collection can discard large caches.
param(
    [switch]$BuildOnly,
    [switch]$ForceDependencies
)

$ErrorActionPreference = 'Stop'
$repoRoot = Split-Path -Parent $PSScriptRoot
$depsImage = 'openscrub-cuda-deps:local'
$dockerfilePath = Join-Path $repoRoot 'Dockerfile.cuda'
$oldBase = [Environment]::GetEnvironmentVariable('OPENSCRUB_CUDA_DEPS_IMAGE', 'Process')
$oldTraining = [Environment]::GetEnvironmentVariable('OPENSCRUB_ENABLE_TRAINING', 'Process')

# Fingerprint the *dependency stage only*. Edits to the application Dockerfile
# tail or Python source MUST NOT make us reinstall multiple GB of PyTorch.
$dockerfile = [System.IO.File]::ReadAllText($dockerfilePath)
$boundary = 'FROM ${OPENSCRUB_CUDA_DEPS_IMAGE} AS app'
$index = $dockerfile.IndexOf($boundary, [System.StringComparison]::Ordinal)
if ($index -lt 0) {
    throw 'Dockerfile.cuda no longer has the expected CUDA dependency/app stage boundary.'
}
$inputText = $dockerfile.Substring(0, $index)
foreach ($relativePath in @('requirements.txt', 'requirements.training.txt', 'docker/prefetch_models.py')) {
    $fullPath = Join-Path $repoRoot $relativePath
    $inputText += "`n--- $relativePath ---`n" + [System.IO.File]::ReadAllText($fullPath)
}
$sha256 = [System.Security.Cryptography.SHA256]::Create()
try {
    $bytes = [System.Text.Encoding]::UTF8.GetBytes($inputText)
    $fingerprint = [System.BitConverter]::ToString($sha256.ComputeHash($bytes)).Replace('-', '').ToLowerInvariant()
} finally {
    $sha256.Dispose()
}

Push-Location $repoRoot
try {
    # Docker Desktop normally uses the "desktop-linux" context. Hard-coding
    # "default" as the builder fails there with a context mismatch error.
    # Contexts have their own built-in docker-driver Buildx builders. Select
    # the builder belonging to this Docker daemon, NOT a docker-container
    # builder that may be unable to resolve the tagged image we --load below.
    $dockerContext = (& docker context show)
    if ($LASTEXITCODE -ne 0 -or [string]::IsNullOrWhiteSpace($dockerContext)) {
        throw 'Cannot determine the active Docker context. Check docker context ls.'
    }
    $dockerContext = $dockerContext.Trim()
    $builderName = $dockerContext
    $builderInfo = (& docker buildx inspect $builderName 2>&1) -join "`n"
    if ($LASTEXITCODE -ne 0) {
        throw "No Buildx builder for Docker context '$dockerContext'. Check docker buildx ls."
    }
    if ($builderInfo -notmatch '(?m)^Driver:\s*docker\s*$') {
        throw "The Buildx builder '$builderName' must use the docker driver to reuse local CUDA images. Check docker buildx ls."
    }
    Write-Host "Using Docker context '$dockerContext' and local builder '$builderName'."

    $existingFingerprint = $null
    try {
        $imageJson = & docker image inspect $depsImage 2>$null
        if ($LASTEXITCODE -eq 0) {
            $imageInfo = @((($imageJson -join "`n") | ConvertFrom-Json))[0]
            $existingFingerprint = $imageInfo.Config.Labels.'org.openscrub.cuda.deps-fingerprint'
        }
    } catch {
        # A missing image is normal on the first run.
    }

    if ($ForceDependencies -or $existingFingerprint -ne $fingerprint) {
        Write-Host "Building retained CUDA/PyTorch dependency image ($depsImage)."
        Write-Host 'This expensive installation should only run once per dependency version.'
        & docker buildx build --builder $builderName --progress plain --load `
            --file Dockerfile.cuda --target cuda_deps `
            --build-arg OPENSCRUB_ENABLE_TRAINING=1 `
            --build-arg "OPENSCRUB_DEPS_FINGERPRINT=$fingerprint" `
            --tag $depsImage .
        if ($LASTEXITCODE -ne 0) {
            throw 'Failed to build the persistent CUDA dependency image; the existing application was not replaced.'
        }
    } else {
        Write-Host "Using retained CUDA/PyTorch dependency image ($depsImage); no Python installs required."
    }

    # The same active-context docker-driver builder sees the tagged dependency
    # image loaded into this daemon. Keep it for both build operations.
    $env:OPENSCRUB_CUDA_DEPS_IMAGE = $depsImage
    $env:OPENSCRUB_ENABLE_TRAINING = '1'
    & docker compose --progress plain -f compose.windows-test.yml -f compose.windows-cuda.yml build --builder $builderName
    if ($LASTEXITCODE -ne 0) {
        throw 'OpenScrub application build failed; the running container was not replaced.'
    }
    if (-not $BuildOnly) {
        & docker compose -f compose.windows-test.yml -f compose.windows-cuda.yml up -d --no-build
        if ($LASTEXITCODE -ne 0) {
            throw 'OpenScrub image built, but Compose could not start the service.'
        }
    }
} finally {
    if ($null -eq $oldBase) {
        Remove-Item Env:\OPENSCRUB_CUDA_DEPS_IMAGE -ErrorAction SilentlyContinue
    } else {
        $env:OPENSCRUB_CUDA_DEPS_IMAGE = $oldBase
    }
    if ($null -eq $oldTraining) {
        Remove-Item Env:\OPENSCRUB_ENABLE_TRAINING -ErrorAction SilentlyContinue
    } else {
        $env:OPENSCRUB_ENABLE_TRAINING = $oldTraining
    }
    Pop-Location
}
