# Synthetic TFLite segmentation check

Research only. No inference was run in the preparation environment. The runner must have network access to the official GitHub release; the pinned binary is downloaded to `--model` if absent and verified against GitHub's published size and SHA-256 before loading. Do not publish the model file as an artifact without resolving its license. Only generated synthetic fixture images, masks, and `metrics.json` belong in the evidence artifact.

Example on Linux x86-64, Python 3.11:

```bash
python -m pip install 'numpy==1.26.4' 'opencv-python-headless==4.10.0.84' 'ai-edge-litert==1.4.0'
python ci-evidence/validate_tflite.py --model /tmp/plate_seg.tflite --output /tmp/plate-evidence --threads 2
```

LiteRT's [Python package](https://pypi.org/project/ai-edge-litert/1.4.0/) publishes a CPython 3.11 manylinux x86-64 wheel. Its [upstream interpreter](https://github.com/google-ai-edge/LiteRT/blob/main/tflite/python/interpreter.py) is the Python API used here. Package availability does not prove this particular model's operators are supported: installation, tensor validation, allocation, and inference must pass on the CI host. A failure is a blocker, not a model result.

The [author's inference example](https://github.com/amirreza-hos/tflite-license-plate-segmentation/blob/main/README.md) resizes the entire RGB image bilinearly to 512×512, normalizes to [0,1], thresholds sigmoid output strictly greater than 0.5, then resizes the binary mask nearest-neighbor. This script follows that example, using floating-point OpenCV bilinear input resizing and explicit half-pixel nearest output mapping. Training-example preprocessing differs; do not silently alter the declared inference pipeline based on ground truth. The fixture generator produces 12 deterministic toy scenes, including 10 original plate cases and two lettering variations. Ground truth is only used after inference to compute metrics; all components and holes remain in the raw binary mask. Saved images are wholly synthetic.

`metrics.json` reports visible plate and visible main-lettering coverage, all pixels outside visible plate redacted, occluder preservation, components, output range and warmed invoke-only latency. The `occluder` region is the synthetic full plate footprint minus visible plate, not all pixels of the foreground object. The run does not measure detection recall or real-world accuracy; it uses full frames and no detector box. No dilation or fallback is applied, and positive pixels do not establish reliable redaction. Runtime, operators, exact model tensors and measured outputs are unverified until the runner finishes.
