# Faster Docker rebuilds on Windows (CUDA)

## Optional inference-only size experiment (does not replace OpenScrub)

The regular Windows CUDA image still includes the training environment.
To measure an *inference-only* image without touching the running container,
use the opt-in `scripts/build-windows-cuda-inference.ps1` helper and
[CUDA inference preview guide](CUDA_INFERENCE_IMAGE_PREVIEW.md). It creates
separate `openscrub-cuda-inference*:local` tags and never changes the
`openscrub-cuda-deps:local` image or Windows Compose defaults. A real GPU
scan and size comparison are required before switching the running app.


## Measure image size before changing dependencies

For a **read-only** report of installed training, inference, CUDA, OpenCV
and model assets in the retained image, use:

```powershell
.\scripts\audit-windows-cuda.ps1 -DockerContext desktop-linux -Output 'D:\OpenScrubTest\cuda-audit.json'
```

This does not rebuild the image, download packages, touch user datasets or
delete anything. See [CUDA image audit and shared-layer architecture](CUDA_SHARED_LAYER_ARCHITECTURE.md)
for the future inference/trainer split, duplicate-library safeguards and
disk-size acceptance criteria.


The Windows Compose overlay builds the **local checkout** with `Dockerfile.cuda`.
Buildx/BuildKit is included with modern Docker Desktop.

## Recommended: stable local CUDA/PyTorch image (PowerShell)

The old BuildKit pip cache saved downloaded wheels, not installed packages.
If Docker Desktop removes that cache or you switch build arguments/builders,
`RUN ... python3 -m venv ... pip install torch` has to reinstall everything.

The Windows CUDA Compose overlay **now defaults to the saved local
`openscrub-cuda-deps:local` image**, even in a new PowerShell window.
Previously it silently selected the Dockerfile's `cuda_deps` stage whenever
`OPENSCRUB_CUDA_DEPS_IMAGE` was unset. If Docker Desktop had evicted the
BuildKit cache, that rebuilt `python3-venv`, PyTorch and CUDA/cuDNN wheels
again. The separate training venv is intentional; there is no reason to
reinstall it for normal application edits.

From the repository root, use the checked-in wrapper for initial setup and
subsequent updates:

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
It uses explicit `docker --context desktop-linux` on Docker Desktop. The
dependency image is built by Buildx and loaded into that daemon; the
application is built by **Compose without `--builder`**, which is the
working configuration on Windows. Passing `--builder desktop-linux`
to Compose produced `use docker --context=desktop-linux buildx` despite
the identical option working for the direct dependency build.

The wrapper:

1. Builds `openscrub-cuda-deps:local` **once** with CUDA runtime packages,
   PaddleOCR, the complete PyTorch training virtualenv and prefetched models,
   then keeps that image under a normal local Docker tag.
2. Rebuilds just the application from this tagged image using Docker
   Compose with the active context selected explicitly and **no** `--builder`
   flag. The tagged image survives BuildKit cache garbage collection.
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

**Manual Compose builds now also reuse the local dependency image** because
the Windows overlay defaults to `openscrub-cuda-deps:local`. If that image
does not exist (e.g., on a fresh PC, or after `docker image prune -a`),
Compose will fail rather than silently redownload multi-GB dependencies.
Run `.\scripts\build-windows-cuda.ps1` once to create it, and keep using
the helper when dependency requirements change.

To confirm which base Compose uses in the current shell:

```powershell
docker --context desktop-linux compose -f compose.windows-test.yml -f compose.windows-cuda.yml config | Select-String OPENSCRUB_CUDA_DEPS_IMAGE
docker --context desktop-linux image inspect openscrub-cuda-deps:local --format '{{.Id}}'
```

The expected build argument is `openscrub-cuda-deps:local`, not `cuda_deps`.
An explicit `$env:OPENSCRUB_CUDA_DEPS_IMAGE='cuda_deps'` overrides the
default and intentionally selects the costly stage; remove that override
or set it back to the local image.

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

For source-only updates, prefer the helper, which checks the dependency
fingerprint and preserves the tagged image. You can also use manual
`up -d --build` with the same Compose files once the local image exists.
With plain progress, expensive stages should be **skipped entirely** (they
might not print `CACHED` because they are not part of the app's build graph):

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

For manual builds, the saved dependency image must already exist. The
training argument may still be specified explicitly:

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
- The helper **intentionally rebuilds** the saved dependency image when
  `requirements.txt`, `requirements.training.txt`, the CUDA base recipe,
  or pinned model-prefetch inputs change. A genuine dependency update may
  reinstall large packages; ordinary Python code edits do not.
  Cache mounts can save downloads but not installation time.
- BuildKit cache mounts are **local to the builder** and can be garbage
  collected. GitHub Actions' registry cache reuses completed image layers,
  but does not automatically export the pip cache mount itself.

A fast sanity check of the Dockerfile cache contracts, without running CUDA:

```powershell
python -m unittest discover -s tests -p test_docker_build_cache.py -v
```
