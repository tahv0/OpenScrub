# Run a read-only dependency inventory against the *existing* CUDA image.
# No rebuilds, pip installs, GPUs, package deletion, or network access.
# Example: .\scripts\audit-windows-cuda.ps1 -Output D:\OpenScrubTest\cuda-audit.json
[CmdletBinding()]
param(
    [string]$DockerContext = '',
    [string]$Image = 'openscrub-cuda-deps:local',
    [string]$Output = '',
    [switch]$VerifyDuplicates
)

$ErrorActionPreference = 'Stop'
$repoRoot = Split-Path -Parent $PSScriptRoot
$auditScript = (Resolve-Path (Join-Path $repoRoot 'docker/audit_cuda_image.py')).Path

if ([string]::IsNullOrWhiteSpace($DockerContext)) {
    $DockerContext = (& docker context show)
    if ($LASTEXITCODE -ne 0 -or [string]::IsNullOrWhiteSpace($DockerContext)) {
        throw 'Could not determine Docker context. Check docker context ls.'
    }
    $DockerContext = $DockerContext.Trim()
}

# Explicit context avoids the Docker Desktop mismatch previously seen when
# using a separate Buildx/Compose context. Fail closed if the tag vanished.
$imageId = (& docker --context $DockerContext image inspect $Image --format '{{.Id}}' 2>&1)
if ($LASTEXITCODE -ne 0) {
    throw "CUDA image '$Image' not found in context '$DockerContext'. Nothing was built or deleted. $imageId"
}

# The audit program only accesses preinstalled system dependency directories.
# No data volume is mounted; it cannot inspect OpenScrub's private jobs.
$mount = 'type=bind,source=' + $auditScript + ',target=/opt/openscrub-image-audit.py,readonly'
$dockerArgs = @(
    '--context', $DockerContext,
    'run', '--rm', '--network', 'none', '--read-only',
    '--mount', $mount,
    '--entrypoint', 'python3',
    $Image, '-B', '/opt/openscrub-image-audit.py',
    '--top', '15'
)
if ($VerifyDuplicates) { $dockerArgs += '--verify-duplicates' }
Write-Host "Auditing installed dependency files in '$Image' (image $imageId)." -ForegroundColor Cyan
$jsonLines = & docker @dockerArgs
if ($LASTEXITCODE -ne 0) {
    throw 'CUDA dependency audit failed. No image contents were modified.'
}

$jsonText = $jsonLines -join "`n"
$report = $jsonText | ConvertFrom-Json
if ($Output) {
    $target = [System.IO.Path]::GetFullPath($Output)
    # The requested report directory may not exist yet (e.g. D:\OpenScrubTest).
    # Create only the parent of the explicitly supplied output file, never
    # modify container data, Docker images, or user media.
    $parent = [System.IO.Path]::GetDirectoryName($target)
    if (-not [string]::IsNullOrWhiteSpace($parent)) {
        [System.IO.Directory]::CreateDirectory($parent) | Out-Null
    }
    [System.IO.File]::WriteAllText($target, $jsonText, (New-Object System.Text.UTF8Encoding($false)))
    Write-Host "Audit report saved: $target"
}

Write-Host 'Installed dependency directory sizes (logical bytes, not unique Docker layers):'
$report.components |
    Sort-Object bytes -Descending |
    Select-Object category, files, @{Name='GiB'; Expression={[math]::Round($_.bytes / 1GB, 3)}} |
    Format-Table -AutoSize
Write-Host "Candidate duplicate libraries: $($report.possible_duplicate_libraries.Count)"
Write-Host "Hash-verified identical libraries: $($report.verified_identical_libraries.Count)"
Write-Host 'Nothing was deleted. Use docker system df -v for unique/shared image sizes.'
