# Faster Docker rebuilds on Windows (CUDA)

The Windows Compose overlay builds the **local checkout** with `Dockerfile.cuda`.
Buildx/BuildKit is included with modern Docker Desktop.

## Recommended: stable local CUDA/PyTorch image (PowerShell)

The old BuildKit pip cache saved downloaded wheels, not installed packages.
If Docker Desktop removes that cache or you switch build arguments/builders,
`RUN ... python3 -m venv ... pip install torch` has to reinstall everything.

From the repository root, use the checked-in wrapper instead of manually
alternating `build --build-arg ...` and `up --build`:

```powershell
git switch integration/all-prs
git pull --ff-only
.\scripts\build-windows-cuda.ps1
```

If Windows PowerShell reports that scripts are disabled by execution policy,
run the checked-in script for this process only with:

```powershell
powershell.exe -NoProfile -ExecutionPolicy Bypass -File .\scripts\build-windows-cuda.ps1
```

The wrapper checks `docker context show` and selects its matching Docker-driver
Buildx builder. On Windows Docker Desktop, this is normally `desktop-linux`.
It does not force `--builder default`, which causes
`use docker --context=default buildx to switch to context "default"`
on `desktop-linux`. No Docker context switch is required.

The wrapper:

1. Builds `openscrub-cuda-deps:local` **once** with CUDA runtime packages,
   PaddleOCR, the complete PyTorch training virtualenv and prefetched models,
   then keeps that image under a normal local Docker tag.
2. Rebuilds just the application from this tagged image using the same Docker
   engine's active-context builder (usually `desktop-linux` on Windows), avoiding even Docker Desktop's default 20GB
   build-cache garbage collection affecting the expensive installation step.
3. Rebuilds the dependency image **only** when its dependency-stage recipe
   or `requirements*.txt` / pinned model-prefetch code changes (or when
   `-ForceDependencies` is explicitly provided). Application source edits
   and later Dockerfile instructions do not affect this fingerprint.
4. Starts your existing Windows test Compose service. Its media/data volume
   paths and NVIDIA GPU reservation are unchanged.

For build-only, use `.\scripts\build-windows-cuda.ps1 -BuildOnly`; after
changing the CUDA base or dependencies, use `-ForceDependencies` if you want
to explicitly refresh the tagged dependency image. The first run is still
expensive. Normal rebuilds should print "Using retained CUDA/PyTorch
dependency image", and **must not execute** the PyTorch install step.

A *tagged image* stays available even when BuildKit's temporary cache is
garbage-collected. Do not remove it with `docker image rm
openscrub-cuda-deps:local` or `docker image prune -a`. If removed, the
wrapper rebuilds it. Large images still consume Docker Desktop disk space.

The standard Compose build below remains supported without the wrapper,
but it relies on BuildKit's normal layer cache; it cannot guarantee
retention of the multi-GB training layer.

## Build or rebuild (PowerShell)

Run in the OpenScrub repository directory after updating your checkout:

```powershell
git switch integration/all-prs
git pull --ff-only
docker buildx version
docker buildx ls
docker compose --progress plain -f compose.windows-test.yml -f compose.windows-cuda.yml build
docker compose -f compose.windows-test.yml -f compose.windows-cuda.yml up -d --no-build
```

For subsequent source-only updates, use the same two Compose files and
the **same Docker builder**. You can also use `up -d --build` directly.
With plain progress, expensive steps should print `CACHED`:

- Ubuntu system packages and original CUDA/OpenCV base
- Runtime Python dependencies, PaddleOCR and ONNX Runtime GPU
- Optional PyTorch training environment (if previously built with training)
- Detection-model downloads and the Ubuntu security-refresh step

The application COPY/install steps still run whenever source code changes.
The first build after this Dockerfile change can be expensive **once**, since
the BuildKit `RUN --mount` instructions are new. The improvements become
visible from the next warm rebuild.

## Optional CUDA training

Training lives in a separate virtual environment. The Windows CUDA Compose
overlay now defaults to `OPENSCRUB_ENABLE_TRAINING=1`, so regular
`up --build` does not unexpectedly toggle to the non-training variant.
Use the retained-image wrapper above for the most reliable warm rebuilds.

For manual builds, you can still pass the training build argument explicitly:

```powershell
docker compose --progress plain -f compose.windows-test.yml -f compose.windows-cuda.yml build --build-arg OPENSCRUB_ENABLE_TRAINING=1
docker compose -f compose.windows-test.yml -f compose.windows-cuda.yml up -d --no-build
```

To opt out in Windows PowerShell, set `$env:OPENSCRUB_ENABLE_TRAINING="0"`
before a manual Compose build (the standalone Dockerfile still defaults to
0). The wrapper always builds the training-enabled variant.

## Why this now stays cached

1. **Ubuntu updates:** There is an initial cached OS-package installation.
   The separate weekly `SECURITY_REFRESH` stage now runs **after** expensive
   dependency/model steps but **before** application source is copied.
   Editing Python code no longer invalidates the `apt-get dist-upgrade`
   layer. Published release builds can still deliberately refresh OS
   security packages using the existing build argument.
2. **Python downloads:** BuildKit cache mounts at `/root/.cache/pip` keep
   downloaded packages outside the image, including CUDA/PaddleOCR/PyTorch
   wheel downloads. On a dependency cache miss, pip can reuse downloaded
   files instead of retrieving all of them again.
3. **Build context:** `.dockerignore` omits local videos, weights, Python
   environments, temporary files and common job artifacts.
4. **GPU compatibility:** CUDA/PaddleOCR/ONNX Runtime pins, CUDA OpenCV
   restoration/validation, and training isolation are unchanged.

## Troubleshooting another full rebuild

- **Don't use `--no-cache` or `--pull`** for routine local updates.
- **Don't run `docker builder prune`, `docker buildx prune` or
  `docker system prune`** to free space if you want to keep caches.
  Docker Desktop can also evict caches under disk pressure.
- Check which builder is active with `docker buildx ls`. Switching or
  deleting builders loses access to their separate cache stores.
- A changed `requirements.txt`, `requirements.training.txt`, CUDA base
  image, or build argument can still invalidate the affected dependency
  layers. Cache mounts can save downloads, not the time spent installing or
  validating packages.
- BuildKit cache mounts are **local to the builder** and can be garbage
  collected. GitHub Actions' registry cache reuses completed image layers,
  but does not automatically export the pip cache mount itself.

A fast sanity check of the Dockerfile cache contracts, without running CUDA:

```powershell
python -m unittest discover -s tests -p test_docker_build_cache.py -v
```
