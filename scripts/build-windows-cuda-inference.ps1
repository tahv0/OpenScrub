# EXPERIMENTAL, build-only CUDA inference preview.
# Never replaces or starts the existing OpenScrub container.
# No training virtualenv, torch, torchvision or Ultralytics in the image.
# Run after updating the repo:
#   .\scripts\build-windows-cuda-inference.ps1
#   .\scripts\build-windows-cuda-inference.ps1 -SmokeTest
[CmdletBinding()]
param(
    [string]$DockerContext = '',
    [switch]$ForceDependencies,
    [switch]$SmokeTest
)

$ErrorActionPreference = 'Stop'
$repoRoot = Split-Path -Parent $PSScriptRoot
$dockerfile = Join-Path $repoRoot 'Dockerfile.cuda.inference'
$depsImage = 'openscrub-cuda-inference-deps:local'
$appImage = 'openscrub-cuda-inference:local'
$boundary = 'FROM ${OPENSCRUB_CUDA_DEPS_IMAGE} AS app'

# Fingerprint only the inference dependency prefix. A Python-only source edit
# must not rebuild the enormous Paddle/ORT/CUDA dependency stage. Training
# requirements intentionally are NOT included in this fingerprint.
$dockerfileText = [System.IO.File]::ReadAllText($dockerfile)
$cut = $dockerfileText.IndexOf($boundary, [System.StringComparison]::Ordinal)
if ($cut -lt 0 -or -not $dockerfileText.Contains('AS cuda_inference_deps')) {
    throw 'Inference Dockerfile stage boundary is missing. Run the generator check.'
}
$inputText = $dockerfileText.Substring(0, $cut)
foreach ($relativePath in @('requirements.txt', 'docker/prefetch_models.py')) {
    $fullPath = Join-Path $repoRoot $relativePath
    $inputText += "`n--- $relativePath ---`n" + [System.IO.File]::ReadAllText($fullPath)
}
$hasher = [System.Security.Cryptography.SHA256]::Create()
try {
    $bytes = [System.Text.Encoding]::UTF8.GetBytes($inputText)
    $fingerprint = [System.BitConverter]::ToString($hasher.ComputeHash($bytes)).Replace('-', '').ToLowerInvariant()
} finally {
    $hasher.Dispose()
}

Push-Location $repoRoot
try {
    if ([string]::IsNullOrWhiteSpace($DockerContext)) {
        $DockerContext = (& docker context show)
        if ($LASTEXITCODE -ne 0 -or [string]::IsNullOrWhiteSpace($DockerContext)) {
            throw 'Could not resolve active Docker context.'
        }
        $DockerContext = $DockerContext.Trim()
    }
    # Match the daemon's builtin Buildx builder. Docker Compose --builder is
    # deliberately not involved (the previous desktop-linux mismatch).
    $builderName = $DockerContext
    $info = (& docker --context $DockerContext buildx inspect $builderName 2>&1) -join "`n"
    if ($LASTEXITCODE -ne 0 -or $info -notmatch '(?m)^Driver:\s*docker\s*$') {
        throw "Expected a local docker-driver Buildx builder for context '$DockerContext'."
    }

    $installedFingerprint = $null
    try {
        $inspect = & docker --context $DockerContext image inspect $depsImage 2>$null
        if ($LASTEXITCODE -eq 0) {
            $record = @((($inspect -join "`n") | ConvertFrom-Json))[0]
            $installedFingerprint = $record.Config.Labels.'org.openscrub.cuda.deps-fingerprint'
        }
    } catch {
        # The first experimental build normally starts without this tag.
    }

    if ($ForceDependencies -or $installedFingerprint -ne $fingerprint) {
        Write-Host "Building inference-only dependency image: $depsImage"
        Write-Host 'Existing full CUDA image and running containers will not be changed.'
        & docker --context $DockerContext buildx build --builder $builderName --progress plain --load `
            --file Dockerfile.cuda.inference --target cuda_inference_deps `
            --build-arg "OPENSCRUB_DEPS_FINGERPRINT=$fingerprint" `
            --tag $depsImage .
        if ($LASTEXITCODE -ne 0) {
            throw 'Inference-only dependency build failed; the existing application remains unchanged.'
        }
    } else {
        Write-Host "Using retained inference-only dependencies: $depsImage"
    }

    Write-Host "Building experimental OpenScrub application: $appImage"
    & docker --context $DockerContext buildx build --builder $builderName --progress plain --load `
        --file Dockerfile.cuda.inference --target app `
        --build-arg "OPENSCRUB_CUDA_DEPS_IMAGE=$depsImage" `
        --tag $appImage .
    if ($LASTEXITCODE -ne 0) {
        throw 'Experimental application build failed; the running full CUDA image was not replaced.'
    }

    if ($SmokeTest) {
        # This is a basic package + GPU visibility smoke test, not an actual
        # plate/OCR inference benchmark. --network none keeps everything local.
        $check = "import importlib.util,cv2,onnxruntime as ort,paddle; " +
                 "assert importlib.util.find_spec('torch') is None; " +
                 "assert importlib.util.find_spec('ultralytics') is None; " +
                 "assert 'CUDAExecutionProvider' in ort.get_available_providers(); " +
                 "assert paddle.device.is_compiled_with_cuda(); " +
                 "assert cv2.cuda.getCudaEnabledDeviceCount()>0; " +
                 "print('CUDA inference packages visible, training dependencies absent')"
        & docker --context $DockerContext run --rm --network none --gpus all `
            --entrypoint python3 $appImage -c $check
        if ($LASTEXITCODE -ne 0) {
            throw 'Inference-only CUDA smoke test failed. Existing full CUDA app is unchanged.'
        }
    }

    Write-Host 'Experimental inference images were created without changing Compose or running containers.'
    Write-Host 'Compare shared and unique image bytes with:'
    Write-Host "docker --context $DockerContext system df -v"
    Write-Host 'A real GPU video scan and training preservation review are required before deployment.'
} finally {
    Pop-Location
}
