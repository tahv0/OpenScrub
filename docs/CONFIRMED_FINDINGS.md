# Confirmed findings, named models, and known plate numbers

OpenScrub keeps your explicit **Is a …** and **Not a …** decisions in a
**Findings** library, separate from the video job. Each example has a small
saved picture, its label and region, and a link to the source video's content.
You can inspect and correct these examples without opening the video, then
choose which plate examples to use for a new named model.

## Protect the whole plate number

The privacy target is every letter and digit of the registration number.
Choose the coverage you want in Scan Setup:

| Plate coverage | What it protects |
| --- | --- |
| **Full plate** | The number together with the plate background and edges. |
| **Lettering only** | Letters and numbers more narrowly, with full-plate fallback when the lettering region is uncertain. |

Lettering-only processing runs every frame and can be slower. HDR input needs
SDR output in this mode. Review the complete number region in either mode;
finding or reading only some characters does not make the remaining characters
safe to leave visible. A plate missed by the scan still needs attention.

## Save an explicit human finding

1. Scan a video, then open Review. You can also use **Stop & Review** to pause
   at a reviewable boundary. Small pictures collected during scanning are
   available without repeatedly decoding the video.
2. Choose **Is a plate** for a real plate or **Not a plate** for a false
   detection such as a hand. Other categories have their corresponding
   **Is a … / Not a …** controls.
3. For a plate, adjust the four corners on the picture if the region needs
   correcting. An area adjustment alone is saved while classification is pending:
   choose **Is a plate** or **Not a plate** to create the confirmed example.
4. Wait for the save acknowledgment. The confirmed example is then available
   from the **Findings** navigation link, or **Browse saved findings & train a
   named model** in the review.

The card initially says **Not reviewed**. Automatic protection can already be
active, but neither output button appears as a human choice until you make one.
The distinction matters:

| Action | Saved meaning |
| --- | --- |
| **Is a plate** | Positive human example; the reviewed group is set to be protected. |
| **Not a plate** | Negative human example; the reviewed group is set to stay visible. |
| **Blur / Keep visible** | An output choice for this job. It does not create, remove, or change a training label. |
| Adjust an unconfirmed area's corners | A region correction awaiting explicit classification. It is not a positive example by itself. |
| A model or OCR suggestion | Machine evidence to review. It is not a human training label. |

For a tracked object, the review choice can apply to its grouped appearances.
Only the picture you explicitly confirmed is archived as a human example;
automatically propagated frames do not multiply the training labels. If you
adjust an already confirmed example, the saved example receives a new revision.

Ordinary Blur/Keep changes still need **Save edits & render** to produce updated
output. A saved example is not evidence that an older rendered file has changed.

During scanning, available candidate pictures can accumulate in the review
queue while processing continues. They stay unconfirmed until you classify
them. The temporary scan-preview cache has a size limit; an older job or a
picture missing from that cache can require one CPU decode from the source when
requested. Permanently saved findings use their stored JPEGs for browsing and
editing, including when the original video is unavailable.

Older variable-frame-rate jobs may have timestamp-based findings without exact
frame indices. You can still view their cached pictures and adjust output or
regions, but these approximate frame matches cannot be saved as exact training
examples. The card explains when a new scan is needed to obtain frame-indexed
findings for confirmation.

## Browse, correct, and forget saved examples

Open **Findings** and filter by video, category, or positive/negative label.
Each card shows its source video name, frame/time, confirmation, and saved JPEG.
Choose **Edit confirmation** to change the label or, for plates, adjust the
corners. **Save confirmation** writes a new revision. The editor only uses the
saved picture; it does not load or play the source video.

Pictures are JPEGs with a longest side of at most 640 pixels and quality 65.
Their coordinates still map to the original source. Corners must remain inside
the saved picture: this keeps the visible evidence and saved geometry together.
Compression and small crops can hide fine detail. Use the video editor when
you need more context or to locate a plate absent from the available picture.

**Forget this example** removes it from the active library and future example
selection. Continuing a locally retained model omits known forgotten examples
from its new training data and refreshes corrected examples. It cannot undo
what an older model has already learned; older models, job reviews, and their
saved training snapshots are not rewritten by forgetting an example.

If a saved example was changed or forgotten elsewhere, the job card shows a
conflict instead of overwriting that newer decision. Read the conflict message,
then click **Is a …** or **Not a …** again to explicitly confirm your intended
choice against the current revision. You can instead choose **Keep current
review choice**, or **Discard this unsaved adjustment** for a conflicting area
edit. This dismisses that rejected action while preserving your other work.
Changes to the library do not globally rewrite existing independent job review
decisions.

## Train a named model from accumulated examples

The Findings library can store several categories, but this training workflow
currently trains **plate models**.

1. In Findings, select **Use for plate training** on the examples you want.
   **Select plate examples on this page** selects the visible page only.
   Selection stays when changing filters or pages; check the positive,
   negative, and video counts before starting. Examples from other videos are
   included only when you select them or retain them through a chosen parent.
2. Under **Train a named plate model**, enter a model name or leave it blank.
   The automatic name uses the video name and UTC timestamp for one video,
   or **Confirmed findings** and a timestamp for a selection across videos.
3. Choose **Configured base checkpoint** to start a new training lineage, or
   select a locally trainable model under **Start from**. A parent carries its
   saved examples and training history forward alongside your new selection.
   Existing corrections are reconciled before the next training snapshot.
4. Acknowledge the optional training framework terms, then choose **Train
   selected plate examples**. The job view shows collection, training,
   validation, and completion progress. The optional local training environment
   is required; see [training setup](VIDEO_LEARNING.md#windows-docker--nvidia-setup).
5. Once training succeeds, the new named checker is saved in the learned model
   library. Choose it under **Learned plate model** in Scan Setup when you want
   to use it. Previous models remain available.

Confirmed plate rectangles are usable for the named checker; a manually
verified four-corner polygon provides stronger shape information. Mask-focused
**Train & rescan this video** has stricter polygon and coverage requirements.
That workflow also accepts an optional **Training run name** and retains a
successfully published candidate as a named model. See
[Video-specific learning](VIDEO_LEARNING.md) for its acceptance rules.

Training starts only when you request it. Clicking Is/Not accumulates evidence;
it does not retrain in the background after every click. Each request freezes
the chosen revisions, so a correction or forgotten example made before the
worker freezes them requires a fresh selection. Training can refuse too few
independent examples or poor validation. More similar frames from one car do
not establish better performance on another recording.

## Use a learned checker during scanning

The original plate detector still finds proposals. A learned checker evaluates
those proposals using your positive and negative examples, which can help with
repeated false detections such as hands.

| Selected model use | Behavior |
| --- | --- |
| **Review suggestions — preserve output choices** | Shows possible false positives for review and keeps the current output choices. This is the default. |
| **Filter validated false positives** | Applies a separately assessed cutoff to suppress low-scoring proposals. Available only when the model passed the filtering checks. |

Explicit human decisions take precedence. A candidate that failed to produce
tighter masks can still be useful as a checker; tightening coverage and
rejecting false detections have separate assessments. A model that has only
passed the review-suggestion path remains review-only after export/import.
The checker is not a standalone full-frame detector and cannot find an object
that no proposal source found.

## Find extra examples using a known plate number

For a video where you know a car's number, you can ask local OCR to look for
additional evidence:

1. Pause or finish the scan. In Review, open **Find examples using known plate
   numbers**.
2. Enter one number per line in **Known plate numbers**, for example `ABC-123`.
   Up to ten targets are supported. Each must normalize to 3–16 ASCII letters
   or digits; case, spaces, periods, and hyphens do not affect matching.
3. Choose **Maximum sampled frames** and click **Find plate examples**. The
   default is 120 sampled frames, with a maximum of 600.
4. Follow progress, then review the resulting candidates together. They show
   **Full number match** or **Partial number match** evidence. Confirm the
   correct examples and adjust their complete number region before training.

The search tries rotated, upside-down, mirrored, and perspective-corrected
views. It uses existing regions, candidate contours, and a limited full-frame
OCR fallback. A partial match must contain at least three contiguous characters
and at least half the supplied number; text-only fallback requires a full
match. It does not guess that `O` and `0`, for example, are interchangeable.
Up to 12 distinct proposals can be returned for a sampled frame.

This operation uses local Tesseract on CPU and one sequential source-video
pass. The frame limit bounds OCR samples, not the total number of frames the
decoder may read to reach them. Searching a long recording can therefore still
take time and read substantial video data once. Merely opening a saved finding
does not start the search or decode the video.

Candidates accumulate for review; the operation does not stop for a decision
on each detection. On paused or section jobs, it respects the available scanned
range. Failed or cancelled searches retain the prior review. OCR matches never
become automatic human labels, and a fragment never shrinks protection to just
the recognized substring. This sampled search can miss brief appearances,
unreadable numbers, or unusual plate layouts; it does not replace a complete
scan and output review.

## Source identity, retention, and another PC

Saved findings use a SHA-256 content fingerprint, together with the compatible
scan variant and timeline. Copying the same video to a different folder does
not require the old folder structure. Re-encoding or trimming the video changes
its content/timeline, so old frame-level decisions are not blindly reapplied to
it. You can still deliberately include its examples when training a model for
other videos.

Confirmed examples, saved models, and locally retained training checkpoints
survive ordinary video-job deletion and retention. They follow the app's vault
and remain sensitive: the JPEGs contain original unredacted pixels and OCR
evidence can contain registration numbers. Keep the persistent app data when
recreating the application if you want to retain these records.

To move a model, use **Settings → Learned plate models → Export**, then
**Import model** on the other PC. The `.openscrub-model` package contains the
ONNX inference model and its manifest. It does **not** transfer the findings
library, source videos, human corrections, or local training checkpoint.
Imported inference-only models can process videos, but cannot be selected as a
trainable parent without the separate local training state. The model itself
does not require the original video or folder structure. See
[Reusable learned models](REUSABLE_MODELS.md) for the transfer workflow.

The older `scripts/prepare_plate_dataset.py` commands export legacy job-based
annotations and review feedback. They are not an export command for this
separate Findings library; use the named-training UI for these saved examples.
