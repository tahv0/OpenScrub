# CUDA image dependency audit and shared-layer design

Status: **audit and architecture contract**. No production CUDA Dockerfile,
Paddle/PyTorch pin, builder tag or runtime workflow changes in this phase.
This avoids invalidating the expensive Docker layers that already work on
Windows Docker Desktop.

## Why this is needed

Measured on an existing Windows NVIDIA installation (Docker containerd):

| Item | Observed | Meaning |
| --- | ---: | --- |
| OpenScrub CUDA application | ~30 GB | Shares nearly every layer with the dependency image |
| Retained `openscrub-cuda-deps:local` | ~30 GB | **Not** an additional 30 GB when both images exist |
| App-only unique layer | ~7.3 MB | Application code changes are already efficiently shared |
| BuildKit cache | 12.27 GB | Separate build-time storage, not necessarily reclaimable |
| Pip `exec.cachemount` | 5.79 GB | Wheel/download cache, not installed packages |

The app image is already a thin descendant of the retained dependency
image. Making a second full 30 GB trainer by copying the runtime would
**increase** disk use. The goal is to branch from identical shared CUDA
layers while keeping incompatible framework-specific libraries isolated.

## Run the audit without rebuilding any image

In a Windows PowerShell session in the repository:

```powershell
$dockerContext = 'desktop-linux'
$reportPath = 'D:\OpenScrubTest\cuda-dependency-audit.json'
.\scripts\audit-windows-cuda.ps1 -DockerContext $dockerContext -Output $reportPath
```

This launches a read-only, offline Python process from the **existing**
`openscrub-cuda-deps:local` image. It mounts only the audit Python file;
it does not mount video, review data, checkpoints or persistent volumes,
install packages, run a GPU or delete anything. The report includes:

- Logical installed file bytes by component: training venv, inference
  Python, OpenCV, CUDA toolkit, runtime libraries, model cache and remaining
  installation residue.
- Largest immediate package/library directories in each component.
- Libraries with matching **names and file sizes** across those components.
  These are candidates for investigation, **not** proof of duplication.
- Optional hash-based validation for same-name, same-size libraries:

```powershell
.\scripts\audit-windows-cuda.ps1 -DockerContext $dockerContext `
    -VerifyDuplicates -Output 'D:\OpenScrubTest\cuda-library-hashes.json'
```

Hashing reads large binaries and is slower; the basic audit is the default.
A matching SHA256 is still **not** a license to remove a shared library:
loader search order, package ownership and wheel repair may depend on it.
The audit never mutates the image.

Logical bytes are not the same as uncompressed image layers, actual shared
disk blocks, or compressed registry transfer sizes. To correlate the
report with real Docker storage:

```powershell
$depsImage = 'openscrub-cuda-deps:local'
docker --context $dockerContext image history --human $depsImage
docker --context $dockerContext system df -v
docker --context $dockerContext buildx du --builder $dockerContext
```

Do **not** prune the current build cache or remove the retained image while
evaluating the replacement: doing so can trigger another multi-GB CUDA,
PaddlePaddle or PyTorch download.

## Target layer graph

`docker/cuda-shared-layers.json` is the machine-readable architecture
contract. Proposed topology:

```text
nvidia/cuda:12.6.3-cudnn-runtime-ubuntu22.04 (pin by immutable digest)
                 |
            cuda-core
             /    \
       opencv-cuda training-deps (isolated PyTorch + CUDA wheels)
             |                 |
       inference-deps     trainer-worker
      (Paddle, ORT, OCR)    (no Paddle)
             |
          scan-app (no PyTorch)
```

**Identical base digests are shared in the local image store.** The trainer
starts at `cuda-core`, **not** at `inference-deps`, so installing training
does not drag the full PaddlePaddle GPU stack into the trainer. OpenCV CUDA
remains in the inference branch because the trainer currently uses its own
pip OpenCV. If compatible shared OpenCV is useful later, benchmark first.

Shared files that are identical but installed in different layers are not
automatically deduplicated by Docker. We must avoid installing them twice in
the first place. In particular:

- Do not confuse `torch`'s pip `nvidia-*` packages with CUDA/cuDNN provided
  by `nvidia/cuda`. Verify actual library versions and CUDA symbols before
  excluding or substituting them.
- Keep OpenScrub inference's CUDA OpenCV bindings and `numpy==1.26.4`
  compatible. A pip OpenCV wheel must not overwrite the custom CUDA module.
- Preserve ONNX Runtime's `CUDAExecutionProvider` and Paddle GPU execution.
  Reordering the ONNX Runtime GPU reinstall requires a real GPU test.
- Keep pinned, license-acknowledged training checkpoints and learned ONNX
  exports in persistent **data** mounts, never in ephemeral image layers.

## Build and cleanup policy

1. **Shared core**: pin the upstream CUDA/cuDNN base by digest; install
   only runtime OS packages there. Never build or copy OpenCV sources, CUDA
   compiler, temporary archives or test artifacts into a runtime stage.
2. **Inference image**: add GPU OpenCV, PaddlePaddle, ONNX Runtime GPU, OCR
   and required video codecs once; no PyTorch/Ultralytics/torchvision.
3. **Optional trainer image**: separate venv and a small worker entrypoint.
   Do not repackage inference libraries. Reuse exactly the same CUDA-core
   ancestry, preserving lower-layer sharing.
4. **Download discipline**: separate pinned requirements/lockfiles by
   dependency family, cache package downloads with unique BuildKit cache IDs
   per architecture and Python ABI; do not use live `pip install --upgrade`
   for normal code-only rebuilds.
5. **Safe cleanup**: delete archive/extraction directories, compiler objects,
   wheel staging files, apt metadata and temporary caches **in the same RUN
   that creates them**, or copy only necessary runtime artifacts from a
   builder stage. Removing them in a later layer **does not reclaim earlier
   image bytes**. Keep pip's external cache mount optional and capped.
6. **No blind stripping**: never automatically remove `*.so`, `libcudnn*`,
   `*.pt` from user data, or `site-packages/nvidia`. The audit and GPU
   compatibility checks must prove safety before a removal.
7. **Rollback**: continue tagging the last working full CUDA image until
   inference and optional training both pass Windows/GPU acceptance tests.

## Training integration is a separate migration

`learning_session.py` currently calls `subprocess.Popen` using
`OPENSCRUB_TRAIN_PYTHON` inside the app container. A standalone training
image therefore cannot just be introduced as a Dockerfile change. A
controlled trainer-worker interface must preserve:

- Existing dataset validation and human-approved training provenance.
- Preflight and license acknowledgement before checkpoint use.
- Streaming progress, cancellation and 12-hour job limit semantics.
- Final ONNX export, CPU/GPU smoke inference, checksum verification and
  atomic acceptance of model candidates.
- Shared persistent datasets/checkpoints, with read-only or least-privilege
  mounts where possible. No reliance on a remote training service.

If trainer functionality cannot be preserved, keep the full existing image
as the compatibility option; do not silently disable the Training UI.

## Acceptance gates before switching production

- Audit the existing retained image and record total and component bytes,
  compared with `docker system df -v`.
- Benchmark clean and warm builds separately on `desktop-linux`.
  **Warm scan-code updates must execute zero CUDA/torch/paddle pip installs.**
- Compare on-disk *unique bytes* with both scanning and training images
  present, and again with only scan installed. Report compressed pulls too.
- Test real GPU OCR (Paddle), plate detection (ORT CUDA provider), face
  detection (OpenCV CUDA), FFmpeg/NVENC, training, cancellation, exports and
  ONNX model load in the normal application.
- Ensure training user data survives image replacement and rollback.
- Do not merge production layer changes until GPU and Windows tests pass.

## Implementation order

**PR A (this one)**: read-only audit tool, Windows audit wrapper, shared-core
topology contract, unit tests and lightweight CI. **No image rebuild.**

**PR B**: move the common CUDA/OpenCV runtime to locked reusable layers, add
a scan-only inference target, and compare real size/accuracy on Windows;
retain existing full image as default during verification.

**PR C**: separate optional trainer worker and preserve the existing training
UI/job lifecycle; ship only after end-to-end training and model-import tests.

**PR D**: apply measured build-stage cleanup and conservative cache budgets.
Cleanup must never delete currently tagged dependencies or persistent user
data without an explicit informed choice.
