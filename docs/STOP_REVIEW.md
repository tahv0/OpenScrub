# Stop & Review: review a partially scanned video, then continue

This experimental feature is built on the four-corner plate-annotation
changes in PR #5. It is **not** a way to publish half-anonymized video.

## Workflow

1. Start an ordinary scan of the full video. You do not need to trim the
   30-minute recording or choose a special 5-minute scan window.
2. During **Scanning**, click **Stop & Review**. The request is cooperative:
   OpenScrub completes a full video frame, closes the decoder, performs the
   normal detection/track post-processing, then atomically saves a reviewable
   report. On a long video, post-processing may take noticeable time.
3. The job changes to **Paused** and automatically opens **Review**. Accept,
   reject, resize and draw plate polygons as in PR #5. Click **Save review
   edits only**. These edits stay in the local report and the same job.
4. Click **Save edits & resume**. The scanner verifies the source hash,
   seeks to roughly one second before the recorded checkpoint and rescans
   just the overlap + remaining video. Previously reviewed detections
   and manual four-corner polygons are preserved, not replaced. New track
   IDs are remapped to avoid colliding with old reviewed objects.
5. Repeat as needed. When the scan reaches the configured end of the
   detection windows, the job enters ordinary **Review** and can be rendered
   only after a complete scan. The edited report continues to be the
   audit input for rendering.

**Stop & Review and Cancel are different.** Cancel keeps its historical
behavior and does not produce a usable new partial review report.

## Persistence and safety

- The checkpoint is stored in the job's `report.json` with a
  `stop_review` marker: schema, verified source SHA-256, source FPS,
  next unscanned frame, total frames and original web scan options.
- The scanner finishes normal detection-merging, continuity smoothing
  and report creation *before* it replaces the existing checkpoint file
  using an atomic rename. Failure during a resume leaves the previous
  checkpoint and reviewed polygons untouched.
- The paused state and original settings are rehydrated if the server
  restarts. Resume is allowed only when the source is the same file
  according to SHA-256 and the frame timeline agrees.
- Paused jobs cannot be rendered or downloaded as anonymized video.
  Keep raw source recordings and checkpoint reports private.
- Training remains a **separate, opt-in operation**: reviewed four-corner
  samples captured here are available to PR #5's local dataset exporter
  and PR #6's independent CUDA training tool.

## Limitations

A resumed scan restores **review data, not the in-memory state of every
detector**. The scanner independently reinitializes the OCR, optical
scroll tracking and dense object tracking for each chunk. It intentionally
overlaps a short boundary interval so the boundary can be reviewed.
It does not guarantee that an object track remains a single continuous
identity over the stop boundary. Review boundaries carefully, especially
moving license plates, screen recordings, and very short appearances.
The actual video frames before the checkpoint are **not scanned again**;
the one-second overlap is deliberate. Some post-processing operations
(e.g., confirming object onset) can still seek earlier in the source.

Because continuity and original/current scan masks can differ, the
feature needs field validation on long videos and variable-frame-rate
source footage. Never use it to claim that a partial scan is publishable.

## Tests

```sh
pytest -q test_stop_review.py
```

Includes an actual synthetic-video stop/resume using the scanner,
checkpoint atomicity/failure injection, changed-video/fps rejection,
preservation of reviewer-approved/denied polygons, unique track IDs,
Flask stop/resume endpoints, and rehydration behavior. The GitHub
workflow runs on Python 3.9, 3.11 and 3.12 without downloading neural
network models.
