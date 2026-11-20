# Sampled plate-text lookup across a video

`optional/detached-video-sampled-search` at `1d50a23d043d76c7dacbf0e83f67e1c3e5bc5ea8` follows [tracking a selected suggestion](detached-suggestion-track-acceptance.md). In the editor, **Search up to four video samples** runs a bounded check from the first to the last exact frame and shows a count beside each sampled time.

| What | Why | When to deliver |
| --- | --- | --- |
| Search up to four exact indices under a single worker deadline. Return counts and mark truncated samples. | A wider check can locate detached text without implying coverage of every frame or opening an unbounded job. | After current-frame OCR and explicit Track. Validate stock Tesseract on sampled wall, ground and blank scenes with a shared timeout and cancellation. |
| Open a listed frame using an exact index and confirm source and timeline again before using current-frame suggestions. | Approximate OCR boxes and rounded timestamps cannot authorize a Track request on their own. | In the same change, with a 25 fps boundary regression and tests for stale source or editor mounts. |

The independent selection passed 92 checks on each of Python 3.12 and 3.9, including real Chromium, loopback and stock Tesseract. **Search this frame** provides the geometry for the inspected frame after selection. The sampled response carries counts, no recognized text, and makes no modifications. A timeout, cancellation, or decode failure shows an incomplete search rather than a negative result.

`optional/detached-video-search-controls` at `8b33021fb7b38ff50321fa262166528a0fbb52dd` retains the count list through deliberate same-source inspections and single-frame searches so a second result can be opened directly. Query changes, ordinary seeks or a source or frame mismatch retire the list. The wording identifies indexed scan-timeline frames. The exact combined sampled controls passed three installed Chromium flows per interpreter.
