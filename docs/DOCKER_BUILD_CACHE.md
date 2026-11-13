# Faster Docker rebuilds on Windows (CUDA)

The Windows Compose overlay builds the **local checkout** with `Dockerfile.cuda`.
Buildx/BuildKit is already used by modern Docker Desktop/Compose; a separate
builder is not normally necessary.

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

Training requires the explicit build argument and lives in its own virtual
environment. Preserve this argument each time you rebuild a training image:

```powershell
docker compose --progress plain -f compose.windows-test.yml -f compose.windows-cuda.yml build --build-arg OPENSCRUB_ENABLE_TRAINING=1
docker compose -f compose.windows-test.yml -f compose.windows-cuda.yml up -d --no-build
```

If you later run `up --build` without that build argument, Compose may
rebuild the **non-training** image (the Dockerfile default is 0).

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
