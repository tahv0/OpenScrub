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
them. Tracking and continuity processing can later make a different frame the
first row of a final Review group, so OpenScrub reconciles the scan-time
pictures to the final track and automatically shows a nearby real cached frame
from that same track. This reconciliation is metadata-only and does not reopen
the video.

The temporary scan-preview cache still has a 64 MiB per-job disk ceiling; the\nitem-count safety ceiling is high enough that small crops normally reach the byte\nbudget first. Opening or scrolling
Review does not automatically reopen the source video for a genuinely missing
picture. Only those exceptional cards show **Load preview**. Clicking it may
perform one CPU decode from the source. Permanently saved findings use their
stored JPEGs for browsing and editing, including when the original video is
unavailable.

Older variable-frame-rate jobs may have timestamp-based findings without exact
frame indices. You can still view their cached pictures and adjust output or
regions, but these approximate frame matches cannot be saved as exact training
examples. The card explains when a new scan is needed to obtain frame-indexed
findings for confirmation.

## Filter detected types and what will actually be blurred

Review offers three independent **view-only** filters: **Review status**
(All / Needs review / Handled / Unsaved or failed), **Detection type**
(All / License plates / Other sensitive areas), and **Output**
(All / Will be blurred / Will remain visible). Combine them to inspect,
for example, only plate detections whose effective output will be blurred,
or other detected areas currently set to stay visible.

Output comes from the actual current enabled/disabled Review choices,
including unsaved Blur/Keep edits, **not** confidence scores or only
confirmed training labels. A group with different output choices across
its frames can appear in both output views. The totals count groups, not
individual frames; each selector's counts reflect the other active filters.
Lazy pages mount matching cards on demand without loading unrelated images.
The existing 10% plate sample, visual similarity grouping, and unsaved
corner drafts remain intact. **Show all findings** resets every view filter.
Filtering by output never changes a blur, confirms a training example,
saves a choice, or exempts another detection from rendering protection.

## Filter the Review queue without changing decisions

The **Show findings** selector in Review has **All**, **Needs review**,
**Handled**, and **Unsaved / failed**, with counts of review groups (not
individual frames). Needs review shows groups that lack an explicit human
output choice or Is/Not confirmation for any member, plus any group with a
pending or failed corner edit or human confirmation. A group partially reviewed
across its frames stays in Needs review. Handled shows complete groups without
outstanding draft/confirmation errors; Unsaved / failed focuses the exceptions.

This is strictly a browser-side view filter: changing it never confirms a
finding, disables protection, saves choices, or discards unsaved corner drafts.
Status updates as you use Blur/Keep and Is/Not, so handled groups drop from
the Needs review view. The existing 10% plate sampler is separate; **Show all
findings** resets both filters. Bulk category choices while filtered apply only
to matching review groups; other hidden findings retain their decisions.
Very large Review pages mount matching cards on demand without decoding all
the filtered-out images. Zone-excluded warnings remain in their separate
section and are not counted as ordinary review groups.

## Browse, correct, and forget saved examples

Open **Findings** and filter by video, category, or positive/negative label.
Each card shows its source video name, frame/time, confirmation, and saved JPEG.
In the gallery, **dashed yellow** outlines the original detector box;
**solid green** outlines saved human-confirmed four-corner plate geometry when
present. Both are drawn over the original **unredacted JPEG**, never painted
into the training pixels. A card that only shows yellow has no saved
human-confirmed quadrilateral; opening **Edit confirmation** lets you check
and correct it.

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

## Recover a timed-out saved picture

Review normally uses compact scan-time JPEGs without reopening the source
video. If a requested frame has no cached JPEG, the bounded source reader
decodes **only its source-coordinate crop** instead of transporting a full
uncompressed 4K frame. Its original frame PTS is verified before the crop
can become a Review image or confirmed training example. A picture from
the wrong frame, crop, video or source timeline is never substituted.

An uncached decoder has a normal 10-second limit. If it reports HTTP 504,
the card shows **Retry preview (up to 60s)**; the reviewer may also select
**Retry timed-out pictures** to queue the currently visible failures in one
click, using only one cold source decoder at a time. These user-initiated
retries have a bounded 60-second deadline and do not change automatic blur
coverage, the detector group, draft corners or the human classification.
Successful crops are persisted to the existing compact-preview cache, so
subsequent Review visits can use the JPEG without reopening video.
If the longer decode fails, the card reports that a seekable normalized
source copy may be required. A failed image remains unconfirmed for training
and does **not** imply a false positive.

## Resolve blocked review saves before rendering or learning

An unsuccessful **Is a … / Not a …** confirmation is different from an
unsaved four-corner adjustment. If a confirmation fails, Review displays an
**Unsuccessful human confirmations** list near the top, with the affected
finding number, the server error, **Show finding**, and an explicit retry of the
label you originally chose. **Show finding** reveals the card even if a filter,
similarity group, or deferred page had hidden it. A rejected HTTP 400/409
confirmation can also be explicitly dismissed, preserving the current saved
review choice; an uncertain network error cannot be silently dismissed.

The **corner draft** error list remains independent. A corner archive-revision
conflict must not masquerade as a failed Is/Not confirmation. A rejected corner
polygon stays in the browser until it is corrected or deliberately discarded.

When a finding displays a **cached representative image from another frame**
(for example, finding frame 2305 shows cached frame 2332), Review clearly
identifies both frames and offers **Load exact source frame**. This explicit
request bypasses track-neighbor fallback, decodes that specific frame only if
no matching scan-time JPEG exists, and binds its preview token to the actual
picture. A clean corner editor is reloaded with the exact frame's geometry;
a pending manual polygon is never silently transferred. Inspect the exact
picture and explicitly choose **Is / Not** again. No human label is
automatically carried from the borrowed thumbnail to an uninspected frame.
An absent source or decoder failure leaves the previous image and any
unsaved draft intact and blocks unverified training evidence.
Render and video-specific training must still wait for all polygon edits and
human confirmation requests to be settled. **Save edits** can safely preserve
other Blur/Keep choices during a confirmation failure, but this limited save
does not acknowledge the rejected example, start rendering, train a model or
save an unsaved corner polygon. Retry the failed Is/Not choice from its
source-bound image, or deliberately dismiss a definitely rejected change
before trying again.

## Train a named model from accumulated examples

The Findings library can store several categories, but this training workflow
currently trains **plate models**.

1. In Findings, choose the **Video**, **Category** (Plate, or All
   categories), and **Confirmation** (positive, negative, or both) filters.
   **Select all matching plate examples** explicitly selects the entire matching
   set across *every page*; the count preview shows positive/negative totals
   and how many videos match before you confirm. Only already-confirmed plates
   can be selected, not unreviewed detector findings. You can uncheck any
   visible matching example to **exclude** it, or use **Clear selection** to
   start over. The counts display these exclusions and any manually added
   examples. A bulk scope stays pinned to its original video/label filters
   even when you browse other pages or filters; manually added examples from
   other videos are kept separately.
   **Select plate examples on this page** still selects only the current page.
   The backend validates the exact matching IDs and revisions when training is
   queued; if someone adds, edits, reclassifies, or forgets a matching example,
   the old bulk selection is rejected with HTTP 409 rather than silently using
   a changed dataset. Review and reselect the scope, including any exclusions.
   Examples from other videos are included only if explicitly selected or
   inherited from a chosen locally trainable parent.
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

### Recover a completed model after a publication error

Large named-model selections formerly wrote every selected finding/revision to
the small candidate run receipt. With thousands of confirmations, **Model file
exceeds its size limit** could occur *after* ONNX export succeeded. This is a
run-metadata limit, not the 256 MiB ONNX model package limit. No model is
automatically activated; the trained candidate remains in that failed job.

The failed model-training job now offers **Finish existing trained candidate
(no retraining)**. It reopens exactly one completed candidate, verifies the
original frozen selected revisions, training/validation split, artifact
hashes and held-out assessment, then saves the model with its locally
trainable checkpoint in the model library. It does not run new training epochs
or scan the source video. Missing, modified or incomplete candidate files are
rejected without deleting the saved training pass.

Keep the failed model-training job and its private learning directory until
the model has been finalized. The original data mount and vault must remain
available. Later changes to confirmed findings do not silently change the
frozen training dataset.

New training receipts store only a count and SHA-256 digest of the selected
revisions; the full frozen revision map remains in the private job request
and immutable corpus. Older large receipts remain readable within a separate
bounded limit.

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
