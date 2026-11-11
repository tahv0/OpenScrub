# Reusable learned plate models

A learned model can be saved for an environment, selected for another video, and transferred to another PC through the UI. The new video does not need the same name, contents, directory, or operating system as the training video.

## Save and use a model

1. Complete **Train & rescan this video** and an accepted learning pass.
2. In Review findings, open **Save trained model for other videos**.
3. Enter a model name and optional environment description, then choose **Save model**.
4. In Scan Setup, select it under **Learned plate model** and start a scan with plate detection enabled.

The default is **None — use original plate masks**. Saving or importing does not select a model automatically. The selected model is copied into each new job. Choosing a different model or removing its library entry does not change an existing job, including a paused job.

Existing full-frame detectors still find plate proposals. The learned model refines masks around those proposals using every-frame plate detection. Empty, uncertain or spatially inconsistent predictions retain original coverage and are flagged for review. Reuse runs inference; it does not retrain the model. Review output on each recording: calibration on one recording does not establish accuracy on another.

## Transfer through the UI

Open **Settings → Learned plate models**.

- **Export** downloads one `.openscrub-model` package.
- On the other PC, **Import model** validates and adds that package to its library.
- **Use for next scan**, or the Scan Setup selector, activates it for a new scan.
- **Remove** removes a library entry while existing job copies remain available.

Packages contain only `model.onnx` and a versioned `manifest.json`: display metadata, model type, decoder contract, checksum, input size, threshold, and the original calibration summary. There are no absolute source paths or source-video matching requirements. Original videos, training crops, exact human corner edits, rejected detections, training history and `weights.pt` are not included.

These are OpenScrub plate **crop-mask** models. Saving from a job requires its accepted learned artifact; generic ONNX detectors are incompatible. Import checks bounded archive contents, the SHA-256 digest, metadata compatibility, and real ONNX inference before publication. The model limit is 256 MiB.

Import packages from sources you trust. These checks establish integrity and decoder compatibility; they do not authenticate the exporter or sandbox arbitrary ONNX computations. The original calibration summary describes the training recording and does not prove accuracy on another recording.

## Training and storage

Reusable ONNX models are for processing videos. **Train & rescan this video** still uses the current job's own verified examples, accepted training checkpoint and history. Importing an inference model does not import a PyTorch checkpoint or transfer another video's human decisions.

The library is stored under the reserved `openscrub_jobs/learned_plate_models/` directory and follows the app's encryption vault. It survives job retention and deletion. Each selected job has an independent `plate_model/` snapshot. Locking the vault blocks model management along with other job operations.

Use matching OpenScrub builds on both PCs. The normal Windows test/CUDA/training Compose commands remain unchanged; rebuild the application to obtain the new UI and runtime module. Continuing to train requires the optional training environment, while using saved models uses the normal ONNX runtime.

## Verification scope

Automated coverage uses synthetic video and small real ONNX graphs for file transfer, inference, browser controls, checkpoint boundaries, and preserved review decisions. No real recording or NVIDIA GPU is used in these checks.
