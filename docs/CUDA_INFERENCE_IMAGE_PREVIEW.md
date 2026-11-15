# Experimental inference-only CUDA image (do not replace the running app yet)

OpenScrub's Windows full CUDA dependency image includes **both** GPU
inference and the optional PyTorch training environment. A measured audit
of the user's retained image found:

| Component | Installed (GiB) |
| --- | ---: |
| Training Python venv (PyTorch, `nvidia-*`, Triton, etc.) | 6.519 |
| Inference Python (PaddlePaddle GPU, ORT GPU, etc.) | 7.52 |
| CUDA toolkit | 1.905 |
| System runtime libraries | 1.444 |
| CUDA OpenCV library directory | 0.082 |

These are **logical files**, not unique disk usage or compressed image
transfer sizes. The current full CUDA app and full dependency image share
virtually all layers, so saving 6.519 GiB from the app's installed files
does *not* imply saving the same amount while retaining the full image too.

## What is implemented

`Dockerfile.cuda.inference` is a **generated, opt-in** Dockerfile derived
from the authoritative `Dockerfile.cuda`:

- Uses the **identical CUDA/OpenCV base image and identical RUN/COPY commands**
  for the expensive inference stack, so BuildKit *can* reuse their cached
  layers (when available to the active builder).
- Omits only the training-specific `python3-venv`, PyTorch, torchvision,
  Ultralytics and training ONNX environment installation block.
- Keeps runtime PaddlePaddle GPU 3.2.2, ONNX Runtime GPU 1.20.2,
  CUDA-enabled OpenCV, FFmpeg, OCR models, the existing application source,
  healthcheck and volume declarations.
- Uses distinct tags `openscrub-cuda-inference-deps:local` and
  `openscrub-cuda-inference:local` so it **cannot overwrite** the full
  dependency image or the existing Windows Compose app by accident.
- Does **not** change `Dockerfile.cuda`, existing
  `openscrub-cuda-deps:local`, Windows Compose or training UI behavior for
  the normal full image.

The inference image is *not ready to replace* a full training-enabled
OpenScrub installation. The existing UI's training handler currently
spawns `OPENSCRUB_TRAIN_PYTHON` inside the app container
(`learning_session.py`). It cannot train from this inference-only
image until the optional trainer-worker integration is implemented.

## Safe preview build on Windows

Run this only if you have sufficient temporary Docker disk space. The
first inference-only build may need to fetch/install large libraries,
especially if BuildKit has evicted the identical full-image cached layers.
**Do not prune, delete the full images or restart a running container.**

In PowerShell from the OpenScrub repository checkout:

```powershell
git switch integration/all-prs
git pull --ff-only

$dockerContext = 'desktop-linux'
.\scripts\build-windows-cuda-inference.ps1 -DockerContext $dockerContext
```

This creates two **new** local tags and stops. It does **not** invoke
`docker compose up`, mount private videos, change port 8384 or touch
existing data. For a basic actual-GPU device/import check, pass
`-SmokeTest` (requires an available NVIDIA GPU). The optional test
checks PyTorch/Ultralytics are absent, CUDA/OpenCV sees a GPU, Paddle
reports a CUDA build and the ONNX GPU provider is registered; it does
**not** substitute for a real video scan.

Repeated source-only builds reuse
`openscrub-cuda-inference-deps:local`; the script fingerprints only
the dependency Dockerfile prefix, `requirements.txt` and pinned model
prefetch file. A genuine dependency update or `-ForceDependencies` will
rebuild the inference dependencies. Training requirements changes do not
invalidate that cached stage.

## Compare sizes after a successful preview build

```powershell
$dockerContext = 'desktop-linux'
docker --context $dockerContext system df -v
docker --context $dockerContext image history --human openscrub-cuda-deps:local
docker --context $dockerContext image history --human openscrub-cuda-inference-deps:local
```

Compare **shared and unique bytes** across all four local tags (full
dependency/app and inference dependency/app) rather than adding their
reported 30 GB virtual sizes. Keeping the full image around means its
training bytes are still on disk. To measure scan-only deployment space
accurately, use a **separate test Docker store/host**, not by deleting the
working full images. Do not estimate savings from logical file bytes alone.

## Required acceptance before switching

1. Run real GPU plate detection on ONNX Runtime CUDA, GPU Paddle OCR,
   OpenCV CUDA face detection and NVENC export on a test video.
2. Confirm no calls to the optional training Python environment occur
   in scan/review/export flows.
3. Compare `docker system df -v` and actual pulled compressed bytes on
   equivalent builds, including clean and warm results.
4. Preserve all existing review/job models and trained checkpoint data.
5. Keep the full image available until an optional GPU trainer worker
   preserves training preflight, progress, cancellation and ONNX export.
6. Obtain a separate affirmative decision before changing the regular
   Windows Compose image to inference-only.

## Regenerate after dependency changes

To avoid manually maintaining duplicate large Dockerfiles:

```powershell
python docker/generate_cuda_inference.py --check
python docker/generate_cuda_inference.py --write
```

`--check` is run in CI. The generator deliberately fails closed if
the full Dockerfile's optional training block moves or stops matching
expected markers. The first line remains the BuildKit `# syntax`
directive so cache mounts continue to function.

## Rollback

No production changes are made by the preview. The normal command
`.\scripts\build-windows-cuda.ps1` still builds the original full
training-capable CUDA image. Nothing needs rolling back unless a
future PR explicitly changes the deployed variant.
