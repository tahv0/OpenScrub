# Local CUDA plate segmentation training (experimental)

**Connected web workflow:** see [Video-specific learning and full rescans](VIDEO_LEARNING.md)
for **Train & rescan this video**, optional Docker training setup, validation,
correction preservation and rollback. The standalone commands below still create
candidates; they do not replace the global full-frame detector.

For new confirmed examples stored as compact pictures, use
[Findings → Train a named plate model](CONFIRMED_FINDINGS.md). That UI can train
a secondary checker from selected positive regions and negative examples, use
an automatic or custom name, and continue a locally retained parent. It does
not require reopening videos just to inspect saved examples. Imported ONNX
packages do not carry the checkpoint needed for continued training.

The standalone commands on this page are an **opt-in, offline-data** workflow
for legacy job annotations and exported datasets. They train segmentation from
**explicitly human-adjusted polygons** and confirmed non-plates. They do not
sample unchanged video frames at fixed intervals. The optional known-number
search in Review can propose additional examples, but OCR proposals must be
confirmed by a human before they become training evidence.

Training is separate from OpenScrub's normal scan/render runtime and is **not
installed by default**. The training tool does not upload recordings, enable
a model, or silently replace the built-in plate detector. The third-party
framework may have its own settings/integrations; use a locally controlled
environment and review any integrations you enable.

## Prerequisites

- NVIDIA GPU, working driver and a CUDA-enabled PyTorch environment. For WSL2,
  verify the GPU is accessible inside WSL first.
- Python in an isolated virtual environment; choose a supported Python
  version for the CUDA build and Ultralytics release you install.
- A **locally downloaded** Ultralytics YOLO **instance segmentation**
  checkpoint (e.g. a compatible `*-seg.pt`). The tool never downloads
  pretrained weights on its own.
- **Licensing:** Ultralytics training code, architecture and models use
  AGPL-3.0 or an Enterprise license. OpenScrub remains Apache-2.0. Installing
  this optional component or distributing a fine-tuned model may create
  separate license obligations. Review
  https://www.ultralytics.com/license and your intended use before proceeding.
  The acknowledgment flag is **not** a replacement for legal compliance.

Install **CUDA PyTorch** using the exact command from the official selector:
https://pytorch.org/get-started/locally/ . Do not blindly install the CPU
wheel. Then install optional training tools in the environment:

```sh
python -m pip install ultralytics onnx onnxruntime opencv-python numpy pytest
python -c "import torch; assert torch.cuda.is_available(); print(torch.cuda.get_device_name(0))"
```

This optional installation is intentionally absent from `requirements.txt`
and `pyproject.toml`. The normal OpenScrub CPU/CUDA Docker images are runtime
images. The optional training Compose overlay adds a separate training
environment; see the [connected setup instructions](VIDEO_LEARNING.md#windows-docker--nvidia-setup).

## 1. Export only reviewed examples

For legacy job data, the exporter reads explicit positive and **Not a plate**
judgments and verified four-corner annotations. Older reports may call the
positive action **Confirm plate**; the current UI calls it **Is a plate**.
Verified four-corner polygons are the **only positives** permitted in this
standalone segmentation workflow. Automatic protection, an auto-tracked box,
an unconfirmed corner adjustment, a confirmed rectangle without verified
corners, or a Keep visible output choice is not a verified segmentation polygon.

```sh
python scripts/prepare_plate_dataset.py \
  --jobs-dir openscrub_jobs \
  --out ./private_plate_seg \
  --task segment
```

The resulting `private_plate_seg/images/{train,val}`,
`labels/{train,val}`, `manifest.jsonl` and `data.yaml` must be kept
private. Positive labels must have four convex points. Negatives must have
an empty YOLO label file. **No unchanged periodic-frame sampling occurs.**

This script exports legacy job-based data; it does not export the separate
Findings library. Use named training from Findings for its selected saved
examples, or the connected **Train & rescan this video** workflow to import its
explicitly confirmed polygons and negatives into a video learning pass.

Keep an eye on dataset imbalance, one-video overfitting and stale/manual
corrections. The exporter deduplicates similar images and partitions
tracked objects into train/validation sets; this tool re-checks both. The
validation set still shares the same footage style if only one recording
was used; **test the candidate on a genuinely unseen second video before
considering deployment.**

## 2. Check data without a GPU

```sh
python scripts/train_plate_seg.py check --dataset ./private_plate_seg
```

This fails on invalid/unverified labels, corrupt or missing images, invalid
four-point polygons, positive-labelled hard negatives, train/validation
track leakage or near-duplicate imagery across splits. Minimum defaults:
12 training positives, 4 validation positives and at least one explicitly
confirmed false-positive image in each split. These are **sanity floors, not
a guarantee of training quality**; dozens to hundreds of distinct verified
plate polygons are preferable, including narrow, distant, night and angled
plates. Separate scenes and cameras matter more than sheer frame count.

## 3. Train with CUDA and export ONNX

Download your segmentation checkpoint explicitly (outside this tool). Keep it
on local disk and pass its full path. Use a private output directory **outside
the Git repository**:

```sh
python scripts/train_plate_seg.py train \
  --dataset ./private_plate_seg \
  --weights /path/to/local/yolo26n-seg.pt \
  --versions-dir /private/path/plate_training \
  --device 0 --epochs 40 --batch 8 --imgsz 640 \
  --accept-ultralytics-license
```

The workflow strictly requires CUDA: missing GPU/driver/build is an error,
not a silent CPU fallback. It also verifies that the supplied checkpoint is
an **instance segmentation** model before training. Reduce `--batch` to
4 or 2 if VRAM is insufficient. One sample GPU is used, no cloud service is
started by this script.

After training, the tool loads `best.pt`, validates its segmentation
metrics on the held-out split, and rejects candidates below the default
mask mAP50 threshold of 0.25. It exports a **raw FP32 ONNX segmentation
graph** and verifies both the ONNX graph and an actual CPU inference.
The version is published only after these checks pass.

## 4. Inspect candidate versions and rollback

```sh
python scripts/train_plate_seg.py list --versions-dir /private/path/plate_training
python scripts/train_plate_seg.py verify --versions-dir /private/path/plate_training \
  --version vYYYYMMDDTHHMMSSZ-xxxxxxxx
```

The directory `plate_training/v<timestamp>-<random>/` holds:
`weights.pt`, `model.onnx`, `manifest.json`, training and validation
diagnostics. `index.json` lists versions. Each manifest records source
checkpoint SHA-256, dataset fingerprint, environment/CUDA details, training
settings, validation metrics and SHA-256 of the saved checkpoint and ONNX
graph. Files are written to a private local directory. Version names are
unique and are never overwritten. The old built-in model remains unchanged;
an explicit future integration/selection step is required to deploy a
candidate. To roll back later, select the previous verified version.

**Compatibility:** a crop-trained YOLO-seg ONNX model is not a drop-in
replacement for the full-frame PlateDetector. The video-learning workflow uses
`video_learning.CropRefiner`, tests held-out coverage, and applies accepted
refinements alongside original detector proposals. Standalone CLI training still
publishes `status=candidate`, `deployment=not_activated`; use the connected
workflow for job-local validation and rescan activation.

## 5. Evaluation before activation

Measure on a **separate, never-used recording** with manually annotated
ground truth:

- Missed plate frames and kilven peiton katkeilu (temporal recall).
- Extra redacted pixels outside true plate polygons (overmask ratio).
- False detections and real plate recall, including narrow/far plates.
- CUDA/CPU ONNX latency and memory, especially on 30-minute videos.
- Baseline vs candidate (keep best old model and reject regressions).

Raw training crops, polygons, audit reports and even model diagnostics may
contain sensitive details; do not commit them or upload them to cloud
services. Keep backups only in appropriately protected local storage.

## Testing

```sh
pytest -q test_plate_seg_training.py
```

Tests do not need Ultralytics or an NVIDIA GPU: the training orchestration
and CUDA guard are exercised using test doubles. These tests **do not**
substitute for a real CUDA training run or comparison against independent
video footage.
