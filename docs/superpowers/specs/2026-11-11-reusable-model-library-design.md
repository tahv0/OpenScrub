# Reusable learned plate models

## Intent

Save an accepted learned plate-mask model for an environment, select it when processing any video, and transfer it through UI export/import. Filename, source-video identity, disk layout and PC must not restrict model use. The user clarified that reusable models are the goal; whole-job migration and matching one video are outside this change.

## Behavior

- An accepted learning pass can be saved with a name and environment description.
- Settings lists saved models with Import, Export and Remove actions.
- Scan Setup provides an explicit learned plate-model selection; the default is no learned model. Saving/importing does not activate a model.
- Each job pins its own immutable ONNX snapshot and calibration threshold. Removing a library entry or choosing another one cannot change running/paused jobs.
- Original detectors produce proposals. The chosen model refines their masks without retraining. Empty/uncertain predictions preserve original coverage and remain reviewable.
- Refine only fresh scan chunks before checkpoint merge, preserving previous human edits. Resume uses the pinned model.
- Model packages contain model.onnx and a versioned manifest with display metadata, type/decoder contract, checksum, fixed input size, threshold and original calibration summary. They contain no videos, crops, review decisions, dataset history or Python/PyTorch checkpoints.
- Import validates archive limits, compatibility, checksums and an actual ONNX inference before atomic publication. It never reads exporter filesystem paths.
- Reusable inference is distinct from per-video training. Training continues to use that job's accepted weights/history; imported ONNX does not pretend to be a training checkpoint.
- Saved models follow the existing vault lifecycle and survive ordinary job retention/deletion.

## Implementation decisions

Retain Flask, the embedded UI, Python and existing ONNX Runtime/NumPy/OpenCV dependencies. Store the library in the reserved openscrub_jobs/learned_plate_models directory, exclude it from job recovery/retention, and snapshot chosen models under each job's plate_model directory. Use relative internal model locations.

Approaches considered: moving complete jobs was a poor fit for the clarified goal and would carry video-specific decisions; a global detector replacement would be incompatible with the crop-trained model. A separate reusable mask-model library preserves the actual inference contract and allows per-video activation.

## Verification

Real small ONNX graphs and synthetic videos exercise save/import/export at different roots, selection, inference and cancellation. Validate corrupt/unsupported bundles, vault access, model deletion after pinning, paused scan boundaries, review preservation, restart/render audit retention and desktop/mobile UI. Run full existing suite and report any baseline failures. No real user videos or GPU are available.

## Scope

This delivers reusable inference models and UI management. It does not make generic third-party ONNX detectors compatible, move video review projects, or claim a model is validated for every future video.

## Model trust boundary

Import is for packages from trusted OpenScrub sources. Archive/schema/hash/decoder checks reject malformed or incompatible packages; they do not authenticate their author or isolate arbitrary ONNX graph computation. Execution uses the app's existing ONNX runtime. A general untrusted-model execution sandbox is outside this change.
