# Confirmed findings, compact review and named training

## Intent

Human decisions belong to the source video, independently of a scan job. The user must be able to browse small stored pictures, confirm or reject a detection, adjust its region without reopening the video, and reuse confirmed examples in named training runs. Scanning must continue while possible mistakes accumulate for later review.

This implements the user's detailed request of 12 November 2026 on `integration/all-prs`. Ordinary Blur/Keep choices and automatic detector/checker judgments are not training labels. Existing output protection continues, but the UI must show an unreviewed state rather than present default Blur as a human decision.

## Chosen approach

Use a local confirmed-findings library inside the existing encrypted app data directory. Keep compact immutable JPEG assets and source-bound metadata separately from job reports. Use the existing ONNX checker, training subprocess and progress plumbing, with a new training path consuming selected stored examples and publishing a named checker automatically. Keep the existing accepted-mask workflow compatible.

Keeping only job reports was rejected because deletion and new scans lose the association. Keeping full frames or reopening the video for every edit was rejected because it reproduces the user's performance problem. Training after every click was rejected because accumulating evidence and running an expensive training pass are separate operations.

## Confirmed findings

- Only explicit **Is a … / Not a …** actions enter the permanent library. A geometry adjustment updates a stored example only after that finding has been explicitly classified. Unconfirmed geometry is a draft in the job.
- Keep category, positive/negative label, source-video content hash and display name, scanned-variant hash, frame/time, source dimensions, original box, corrected geometry, confirmation time, revision, and originating job. Paths and transient row/track numbers are not identities.
- A copied/renamed byte-identical source has the same video association. Coordinate replay additionally requires a compatible scanned variant/timeline. No guessing on an edited/re-encoded video.
- One representative image per confirmed finding/group; no image for every frame of a track. Store a JPEG with longest side at most 640 px, quality 65. Preserve original-coordinate crop transforms for editing/training.
- Listings are paginated and filterable by video, category and label. Browsing and changing a stored example do not open the source video. Corrections replace the current label/shape and increment a revision; forgetting an example excludes it from future training.
- Ordinary job deletion/retention keeps this library. Explicit example deletion is separate. The existing vault protects it.
- Training from stored crops works without the original video. Small images may limit fine detail; users can explicitly request a full-resolution source view when needed.

## Fast review and uncertainty queue

- Capture bounded representative crops from already decoded scan frames when possible. Keep these pending previews in the job, separate from the confirmed library. Cold legacy previews may decode once on CPU and cache; repeated browsing/editing must read the cached JPEG.
- Reuse the same image/coordinate metadata for thumbnail and area editing. Opening an editor must not launch a hidden video preview, GPU decoder or another full-frame read when a compact crop exists.
- Initial cards say **Not reviewed**, with neither classification selected. Explicit labels become **Confirmed …** or **Not …**. Output-only controls are secondary and must not look like a default human confirmation.
- Show a pending-review list/counter while scanning. Sampling is bounded, deduplicated by tracked object or nearby object/frame, and never blocks the scanner for user input. Candidates may be uncertain detector results or checker disagreements. Call them requests for review, not calibrated probabilities.
- Current plate training/inference remains plate-specific. The archive may retain confirmations for other existing detection categories, but the UI must not imply that the plate trainer trains all categories.

## Named training and reuse

- Every new training run gets a supplied name or `<video name> — <UTC timestamp>` (multiple sources use `Confirmed findings`). Persist the name even when training/assessment fails, so retained candidates remain identifiable.
- Add training from selected stored plate examples. The selection may span videos; each example retains its source link. The current-video link scopes the filter, but no examples are selected until the user selects them.
- The user may choose a locally trainable saved model as parent, or the configured base checkpoint. Preserve the chosen parent's cumulative examples and training/validation exposure history. An imported ONNX-only model is usable for scanning but cannot silently initialize the PyTorch trainer.
- A new training run creates a new version; it never overwrites an existing job's pinned model. Save the completed ONNX checker automatically with its name and separate positive/negative assessment. A candidate failing mask-tightening can still become a checker; it must not claim mask acceptance.
- Store a hash-checked local checkpoint and training lineage outside the two-file portable inference package. Export/import remains compatible; locally retained training resources survive source-job deletion.
- Reuse existing stage/epoch/batch progress and logs. Scanning uses the selected named model. Training and checking do not pause for individual review decisions.
- More examples do not promise improved accuracy. Preserve the old version and expose the new assessment; automatic filtering remains separately gated.

## Known plate text and number privacy

- The protected information is the entire plate number. Preserve the existing Full plate and Lettering only choices. A partial OCR match must never justify protecting only the recognized characters.
- An explicit **Find plate examples** operation accepts up to ten known ASCII plate numbers and searches a bounded sample of already scanned frames (default 120, maximum 600). This is local CPU OCR with one sequential source decoder, progress and cancellation; ordinary crop browsing never invokes OCR.
- Try plate/text-edge candidates and supplied plate regions through perspective rectification and eight right-angle/mirror views. Literal complete matches rank above meaningful fragments. Free full-frame text discovery requires complete matches. These are additional evidence, not calibrated neural probabilities.
- Add uncertain candidates to review with OCR evidence and whole-number boundary guidance. A partial match always requires boundary review; all new examples remain unreviewed until an explicit Is / Not decision. Source sample indices, scan windows and paused sections remain exact. Search samples do not imply complete video coverage.
- Keep detected numbers in local review/report evidence, excluded from diagnostic logs. Searches preserve manual corrections and output choices; repeated searches deduplicate existing proposals.

## Consistency and limits

- Explicit labels and geometry must have a recoverable save receipt; a thumbnail failure must not report a successful archive save. Do not acknowledge a library write that was not durable.
- No machine-generated labels, inherited tracking guesses, or unchanged default output choices become human evidence.
- Restore human decisions to exact compatible video frames/regions conservatively. Ambiguous matches remain for review.
- Freeze training inputs at a revision; retain prior training group exposure and near-duplicate separation to avoid validation leakage.
- Preserve sections, stopped scan prefixes, review edits, model-mode pinning, cancellation and vault behavior.
- No new production dependency is required. Use existing Python, Flask, OpenCV, ONNX and embedded browser JavaScript.

## Delivery and verification

Use synthetic footage and small real ONNX graphs. Test persistence after job/source removal, content identity, explicit-only labels, cached editing with the decoder forbidden, revision/revocation, dataset selection and parent lineage, named publication, scan progress/queue bounds, and UI states. Run desktop/mobile browser CI, installed-wheel packaging, Docker/render/restart, and the full suite. The exact base `12aad0c` has six previously confirmed OCR failures; report them separately from regressions. Deliver through Git and merge into `integration/all-prs`.
