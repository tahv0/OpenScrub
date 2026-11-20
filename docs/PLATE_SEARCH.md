# Experimental plate-text search core

This optional Python core and exact-frame HTTP route search explicitly requested
ASCII text using an installed local Tesseract. The route has no editor control
yet. Search does not change a report, select or blur anything, and does not
require a vehicle or plate detector. A result is a suggestion for human inspection, not evidence
that an identifier has been redacted or that its physical plate boundary is
known. No model is trained or downloaded by this code.

`PlateQuery(text, "full")` requires equality after the literal normalizer
removes spaces, tabs, dots and hyphens; `PlateQuery(text, "fragment")` requires
the entire supplied literal fragment to appear in one OCR observation. Full
queries do not silently become fragments. No fuzzy substitution or joining of
separate OCR words is done. Each batch contains at most ten queries, each with
3–16 normalized ASCII letters/digits. Query and observation text are omitted
from default result representations and diagnostic messages. Tesseract receives
image pixels, not the user's query, and the query is never put in argv.

`search_frame(frame_bgr, queries, regions=None, reader=None, cancelled=None)`
returns a `FrameSearch`. Each hit retains the full OCR observation box in
source pixels, the literal match evidence, a suggested box containing the
whole observation, and a boundary label. `unknown` means the expanded OCR box
is merely a starting point; `provided_unverified` means a caller-supplied box
was used and is also unverified. Neither claims a physical plate outline or
coverage of all identifier pixels. Confidence belongs to the OCR observation;
it is not a calibrated probability of a correct plate or geometry. Tesseract
can return low scores for real text and high scores for unrelated text.

The full frame is always searched independently of optional caller-supplied
boxes. It is tiled without downscaling into overlapping tiles up to 1280×960
pixels. Sparse-page OCR runs on each tile; up to three classical quadrilateral
crops per tile are also rectified and read to help with bordered or skewed text.
If a crop's OCR box touches its edge, that observation is discarded and a
crop with extra source pixels is retried. The crop is not treated as a proven
boundary. The input is uint8 BGR, at most
8192 pixels on either side, with at most 64 total tiles/regions and eight
provided regions. Per tile, at most 64 OCR observations are examined and at
most 128 hits are retained per frame. `truncated` flags a token or hit limit;
`complete` means all scheduled tiles finished, not that recognition was
exhaustive. OCR boxes crossing a tile edge are discarded; overlap can provide
another view but cannot guarantee recovery. Rotations, tiny characters, glare,
blur, occlusion, non-ASCII scripts, split OCR words and physical plate borders
may be missed. Unrelated words and numbers that match are false suggestions.
No calibrated precision, recall or runtime claim follows from the fixtures.

`search_capture` searches at most 16 explicit, strictly increasing frame indices
through the existing exact CFR sample reader. The caller owns the capture and
must qualify the source metadata and source lifetime/identity before reading and
revalidate it before publishing results. The reader checks the FFmpeg backend,
FPS, count, decoded dimensions and observed timestamp against the supplied
policy. It cannot prove that pathname bytes are immutable or that a source is
CFR; the caller's existing observed-source and operation owners remain needed.
`requested_indices` and `completed_indices` are exact discrete samples, not a
claim of coverage between them. Cancellation returns only fully completed
frames with `cancelled=True`; decode or OCR failure raises instead of silently
treating an unsearched frame as a negative. There is no persistent cache or
report write in this core.

The Tesseract adapter uses pytesseract's local subprocess with a three-second
timeout for each OCR invocation. There can be up to seven invocations per tile,
so the OCR timeout budget alone is at most 1,344 seconds per frame or 21,504
seconds for 16 maximal frames; decode, crop computation and process startup are
additional and are not interrupted by this timeout. Cancellation is checked
between OCR calls and tiles; a call already in progress can take up to its
individual timeout. Native decoder and OpenCV calls have no separate timeout.
Callers using the core directly must bound concurrency themselves. No latency or
memory reservation is guaranteed. Pytesseract writes temporary image/TSV files
that can contain visual and recognized sensitive content; it cleans its own
files on normal completion and handled timeout. Abrupt process termination may
leave files behind. The HTTP wrapper supplies the job-owned directory described
below.

The HTTP route searches one current exact sample in an isolated POSIX process
(non-frozen Python with `waitid`/`WNOWAIT` support only), with at most one search
process per app instance. It has a 15-second admission-and-worker budget, kills
its process group on timeout, cancellation, or abnormal worker completion, and
uses a private temporary directory under the job. The worker leader remains
unreaped while its group is validated or stopped, preventing its process-group
ID from being recycled during cleanup. Cleanup waits for live descendants to
stop, and can exceed the budget if native work or process-table access stalls. The
directory is removed after the worker exits on normal completion and handled
failure; a sudden server/process death can leave it until the job's existing
deletion or vault lifecycle acts. Blocking filesystem and admission calls cannot
be interrupted by the worker deadline. Search responses are private/no-store;
cancel, timeout and failure are distinct from a completed search with no hits.
The route holds file lifetimes and rechecks the current exact source and report
before returning suggestions. The query is carried only in the request body and
the worker's stdin, never in its argv or app logs. It returns box geometry and
match kind, not the query or recognized OCR text. Search remains an opt-in
inspection aid and does not alter the report.

## Synthetic checks

A generated four-frame 960×540 MPEG-4 clip at 4 fps contained a flat wall plate
at frame 0, a perspective-skewed ground plate at frame 2, and blank scenes at
frames 1 and 3. Stock Tesseract 5.5.0 and the bundled English traineddata found
the complete six-character text and an explicit three-character fragment in
both plate frames, with no matching suggestion in the two blank frames. A
separate decoded 3840×2160 MPEG-4 frame contained a 210×52-pixel plate; the
native-resolution tiled search found its complete text and a fragment. These
are easy synthetic cases, not a dataset or accuracy measurement. A separate
occluded-text probe failed to recover its fragment and shows that partial text
is not reliably discoverable. The exact test corpus and privacy/timeout checks
are in `tests/test_plate_text_real_ocr.py`; no test establishes physical plate
boundaries or real-world accuracy.

In the same environment, an unrelated number drawn on a plain background also
produced a match, demonstrating that whole-frame matching alone cannot tell a
plate from other text. The test Tesseract binary SHA-256 was
`644efa639b77a21b1096a6ced155112f0c730d05c7db871d52f4b2eb16bdf42a`;
the English traineddata SHA-256 was
`7d4322bd2a7749724879683fc3912cb542f19906c83bcc1a52132556427170b2`.
One `/usr/bin/time` run of the 4K test, including Python/pytest startup, video
generation and decoding, took 2.32 seconds and reported a maximum RSS of
175,624 KiB. This single local measurement is not a capacity estimate and does
not characterize concurrent jobs or peak aggregate subprocess memory.
