# Video-specific learning and full rescans (experimental)

This is the connected workflow: **review -> Train & rescan this video ->
validate -> original-detector rescan from the beginning -> learned mask
refinement -> reapply human decisions -> review -> render**. It is not Resume.
Existing successfully saved four-corner annotations are imported; no manual
export command is needed for this workflow.

## Windows Docker / NVIDIA setup

Keep the existing checkout, media/data environment variables and persistent
mounts. Do not restart during a scan or render you need to preserve. Training is
optional and installs into a separate `/opt/openscrub-training` virtual
environment, not into the CUDA OpenCV/Paddle runtime. The extra build downloads
PyTorch and training packages and uses additional disk space.

From PowerShell in the checkout:

```powershell
git switch integration/all-prs
git pull --ff-only origin integration/all-prs
$compose = @('-f', 'compose.windows-test.yml', '-f', 'compose.windows-cuda.yml', '-f', 'compose.windows-training.yml')
docker compose @compose build openscrub
```

Review the optional framework/checkpoint terms at
https://www.ultralytics.com/license. After accepting them, explicitly download
the fixed official checkpoint into the **existing persistent data mount**:

```powershell
docker compose @compose run --rm --no-deps openscrub python /src/scripts/download_training_checkpoint.py --accept-ultralytics-license
docker compose @compose up -d
```

The downloader verifies SHA256 and never replaces an existing mismatched file.
The checkpoint is downloaded, not bundled in the OpenScrub repository/image.
Keep all three Compose files on subsequent build/up/run commands. Hard-refresh
the browser after recreating the service. Optional readiness check:

```powershell
docker compose @compose exec openscrub /opt/openscrub-training/bin/python -c "import torch; print(torch.__version__, torch.cuda.is_available()); assert torch.cuda.is_available(); print(torch.cuda.get_device_name(0))"
```

A native installation can instead configure `OPENSCRUB_TRAIN_PYTHON` and
`OPENSCRUB_TRAIN_WEIGHTS` to an isolated CUDA training interpreter and trusted
local segmentation checkpoint. Do not set either from untrusted HTTP input.

## Review and improve a video

1. Scan normally. Optionally use **Stop & Review** at a checkpoint, or let the
   scan finish. Both paused and completed reviews support learning.
2. Use **Review 10% of plate groups** for a proposed subset, or review all.
   Repeated frame sightings are grouped by detected object/track first. The
   budget is 10% of those unreviewed groups (rounded up), with one representative
   image per chosen group. For example, 10,000 frame sightings of 100 tracks
   produce 10 review cards, not 1,000. Groups are spread along the timeline;
   disagreements and uncertain scores determine which group to include
   within each batch. The card keeps the full track's time span and decisions
   apply to its members. Sampling never deletes per-frame rendering data.
   Switching between the sample and **Show all findings** is a local view filter:
   it does not save the review, fetch the report again, or wait for corner saves.
   Group ranking considers all loaded unreviewed members and current draft labels;
   each chosen group keeps its displayed representative image and corner editor.
   Unsaved decisions, pending/failed corner adjustments and existing images survive
   either switch. Use the explicit save confirmation before refreshing, or
   **Train & rescan** to save and begin learning. Changing the view is not a save.
   Untracked detections remain separate rather than guessing object identity.
   It can be smaller when too few distinct examples remain. This is not a claim
   that reviewing 10% proves the rest of the video is safe.
3. Correct corners; they autosave. Explicitly label **Not a plate** examples.
   Merely choosing Keep visible is not a negative training label. Confirm plate
   alone, without manually verified corners, is not a segmentation polygon.
4. Click **Train & rescan this video**. The first use asks for acknowledgment of
   the optional training framework terms. Status/logs distinguish source-hash
   verification, example collection, training, validation, rescanning and mask
   refinement. Training uses CUDA, 40 epochs and batch 8; absence of a working
   training environment is an explicit error, never a silent unchanged rescan.
5. Review disagreements and new findings. A subsequent accepted pass starts
   from the last accepted learned weights. Unchanged feedback after an accepted
   pass is refused rather than launching the same training again.
6. **Save edits & render** creates the video for the new pass. The previous
   output cannot be downloaded as though it contained the new corrections.
   Inspect the rendered result before releasing it.

**Restore previous pass** restores the saved review report, retains annotation
and model files, and requires rendering again. A failed/cancelled training or
rescan leaves the previous report intact. An interrupted pass is not resumed
silently after a restart; the committed report remains the source of truth.

## What training uses and what wins

The source fingerprint, frame identity and geometry bind saved decisions to the
video. Detection-array positions and new track IDs are not identities. Known
human corners override new model outlines at the reviewed frame. Reviewed
negative tracks are transferred using source-frame geometry, interpolating only
short observed gaps; ambiguous matches are flagged rather than suppressing a
possibly different real plate. Inherited rejections do not expand automatically
into a new tracker identity. Only a directly edited seed is human-verified;
automatically propagated masks are not training labels.

Original detector models remain the proposal source. The crop-trained ONNX
model refines those proposals; it does **not** replace the full-frame detector.
Learning rescans force every-frame plate proposals even with a fast preset.
One sequential source decode then applies the learned masks, with the same
four-corner geometry used in calibration, review and rendering. Low-confidence,
empty, malformed or spatially inconsistent predictions retain the original
coverage and create a review disagreement. They do not automatically unblur a
new object. Explicit human false-positive decisions do remain rejected.

## Gates and limitations

The existing dataset validator requires at least **12 training positives,
4 held-out positives, and 1 negative in each split**, grouped by reviewed object.
The deterministic split may require more examples than those numerical minima.
It rejects corrupt labels and cross-split duplicates. The candidate must meet
the segmentation metric gate, load through actual ONNX inference, and demonstrate
less excess coverage on held-out examples without more than 0.5% known plate-pixel
loss on accepted validation masks. These small held-out checks are engineering
safeguards, **not** proof of complete anonymization. No useful runtime refinement
means the prior report is retained rather than publishing an unchanged pass.

This first connected path supports **constant-frame-rate SDR scan/output**.
HDR-match learning is rejected explicitly before training; it must not silently
downgrade an existing HDR job. It does not discover plates that every original
proposal detector misses. It does not guarantee correctness through every
occlusion, tracking identity error or perspective change. It is video-specific
adaptation, not a model validated for unrelated recordings.

All snapshots, models, logs and pass reports stay under the job's private
`learning/` directory and inherit its vault lifecycle. Deleting the job deletes
them. Back up the persistent data directory appropriately; it contains original
unredacted pixels. Training does not upload recordings.

## Verification commands

```sh
OPENSCRUB_NO_AUTOFETCH=1 pytest -q test_video_learning.py test_learning_session.py test_learning_packaging.py
pytest -q test_learning_browser.py test_review_browser.py
python tools/smoke_learning_cpu.py --checkpoint /trusted/yolo11n-seg.pt --output /private/smoke-output
```

The final command deliberately substitutes the CUDA guard/device for a CPU
mechanical test and uses a deterministic original proposal detector on generated
video. Training, ONNX export/inference, the scan loop and renderer are real. It
does not measure the user's GPU, footage, original plate-model recall or privacy
accuracy. Production CUDA remains required and is not bypassed by that test.

## Retrying a corrected-polygon crop error

Older learning builds can stop during example collection with **Verified polygon
does not fit its training crop** even after the review UI successfully saved
valid corners. The old collector crops around the original detector rectangle;
a human correction can extend beyond that rectangle and its padding.

The collector now includes the original proposal **and all verified corners**
in its training crop, then normalizes the label to those exact pixels. It does
not shrink the annotation, drop the example or relax the dataset quality gates.
Only the tiny source-boundary rounding error from six-decimal saved coordinates
is tolerated; genuinely off-frame or non-convex polygons still stop collection
with the finding index and frame in the error.

Update/rebuild with all three Compose files above, keep the existing persistent
data mount, and retry **Train & rescan this video** on the same saved job. No
rescan, reannotation, cache deletion or checkpoint download is needed just to
retry collection. An unsuccessful collection has not replaced the review report
or activated a new model. This fix does not bypass the later minimum-example
or validation checks.

## Unsaved corner adjustments

A rejected corner save keeps the draft and shows **Show finding #…** in the
review's error summary. This reveals and focuses the same card even when it
was hidden by the 10% filter. The card is outlined and an out-of-frame error
names the numbered corners and their source coordinates; rejected handles
are red. Correct the shape and let autosave finish, or use Retry save.

Image-edge polygon vertices are valid at x=0/width and y=0/height. Only tiny
rounding error from stored relative coordinates is snapped to an edge; genuinely
out-of-frame shapes are rejected, not silently shrunk. A definite validation
rejection is not reused as a stale request after a new adjustment. For an
uncertain network result, retries retain the request ID to avoid double saves.

Filtering or finding an unsaved card does not save it. Wait for **Saved** /
**Saved to track**, then confirm **Review edits saved to disk** before leaving.
Do not use **Reload preview** to preserve a draft: that conflict-recovery action
explicitly asks permission to discard the unsaved shape.
