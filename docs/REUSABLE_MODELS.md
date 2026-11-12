# Reusable learned plate models

A learned model can be saved for an environment, selected for another video, and transferred to another PC through the UI. The new video does not need the same name, contents, directory, or operating system as the training video.

## Save and use a model

The [Findings workflow](CONFIRMED_FINDINGS.md#train-a-named-model-from-accumulated-examples)
trains a named checker from selected human confirmations and saves it directly
to the model library. Completed **Train & rescan this video** candidates also
receive the optional run name, or an automatic video/timestamp name. Select a
saved model in Scan Setup when you want to use it; saving does not activate it.

To save an older accepted mask or evaluated candidate manually:

1. Complete an accepted mask-refinement learning pass, or evaluate a retained
   training candidate using the secondary checker in Review findings.
2. In Review findings, open **Save trained model for other videos**.
3. Choose the accepted mask or evaluated secondary candidate as the source.
   Enter a name and optional environment description, then choose **Save model**.
4. In Scan Setup, select it under **Learned plate model**, choose its mode, and
   start a scan with plate detection enabled.

The default is **None — use original plate masks**. Saving or importing does not select a model automatically. The selected model is copied into each new job. Choosing a different model or removing its library entry does not change an existing job, including a paused job.

Existing full-frame detectors still find plate proposals using every-frame
plate detection. Accepted mask models refine their geometry; empty, uncertain
or spatially inconsistent predictions retain original coverage. Secondary
checker models instead offer **Review suggestions — preserve output choices**
(the default) or explicit **Filter validated false positives** after an
independent held-out positive/negative assessment passes. Review-only
candidates remain review-only after transfer.
Human decisions take precedence in both modes. The selected mode is pinned
alongside the model and survives a restart, including a paused scan.

Reuse runs inference; it does not retrain the model. Review output on each
recording: calibration on one recording does not establish accuracy on another.
See [Secondary checker assessment and limits](VIDEO_LEARNING.md#use-a-retained-candidate-to-reject-false-detections).

## Transfer through the UI

Open **Settings → Learned plate models**.

- **Export** downloads one `.openscrub-model` package.
- On the other PC, **Import model** validates and adds that package to its library.
- **Use for next scan**, or the Scan Setup selector, activates it for a new scan.
- **Remove** removes a library entry while existing job copies remain available.

Packages contain only `model.onnx` and a versioned `manifest.json`: display metadata, model type, decoder contract, checksum, input size, threshold, and the original calibration summary. There are no absolute source paths or source-video matching requirements. Original videos, training crops, exact human corner edits, rejected detections, training history and `weights.pt` are not included.

These are OpenScrub plate crop models, not generic full-frame ONNX detectors.
Schema 1 packages contain accepted mask refiners. Schema 2 packages, kind
`openscrub-plate-verifier`, contain independently assessed secondary checkers;
they do not claim to have passed mask tightening. Import checks bounded archive
contents, the SHA-256 digest, metadata compatibility, and real ONNX inference
before publication. The model limit is 256 MiB.

Import packages from sources you trust. These checks establish integrity and decoder compatibility; they do not authenticate the exporter or sandbox arbitrary ONNX computations. The original calibration summary describes the training recording and does not prove accuracy on another recording.

## Training and storage

Reusable ONNX packages are for processing videos. Local named training also
retains a separate checkpoint, example snapshot, and training history. These
locally trainable models appear under **Start from** in the Findings view, so
you can continue with new confirmed examples while keeping previous versions.
Current corrections and forgotten examples are reconciled before a new training
snapshot; older weights are not retrospectively untrained.

**Train & rescan this video** uses the current job's verified polygon examples
and can continue its accepted local checkpoint/history. Its mask acceptance
rules remain separate from the named checker's filtering assessment.
Importing an inference package does not import a PyTorch checkpoint, example
corpus, or another video's human decisions. Such a model cannot serve as a
trainable parent just because it can perform inference.

The library is stored under the reserved `openscrub_jobs/learned_plate_models/` directory and follows the app's encryption vault. It survives job retention and deletion. Each selected job has an independent `plate_model/` snapshot. Locking the vault blocks model management along with other job operations.

The confirmed-picture library and retained local training state are also
reserved data, independent of individual job retention. The
[Findings guide](CONFIRMED_FINDINGS.md#source-identity-retention-and-another-pc)
explains content-based video identity and what is retained. Export/import of a
model is not an export/import operation for those records.

Use matching OpenScrub builds on both PCs. The normal Windows test/CUDA/training Compose commands remain unchanged; rebuild the application to obtain the new UI and runtime module. Continuing to train requires the optional training environment, while using saved models uses the normal ONNX runtime.

## Verification scope

Automated coverage uses synthetic video and small real ONNX graphs for file transfer, inference, browser controls, checkpoint boundaries, and preserved review decisions. No real recording or NVIDIA GPU is used in these checks.
