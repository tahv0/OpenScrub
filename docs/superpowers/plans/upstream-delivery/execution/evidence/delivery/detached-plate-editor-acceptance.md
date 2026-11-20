# Plate text search in the existing editor

`optional/detached-plate-search` at `59ffb12c51a59131f6ba03ee8e1620f06875328a` follows the [bounded OCR worker](detached-plate-worker-acceptance.md). The editor searches the one exact frame currently being inspected. This can locate a detached plate on a wall or ground without requiring a YOLO hit.

| What | Why | When to deliver |
| --- | --- | --- |
| Add a collapsed panel for a literal full or fragment query. Let the user select a result to highlight its approximate region. | This can help find a known number when the ordinary plate detector misses it. An OCR region alone is insufficient for a physical plate mask. | After the matcher and worker. Keep the existing explicit Add box and Track object actions. |
| Retire stale results on seek, playback, job switch, or query change. Distinguish timeout and cancellation from a completed search with no hits. | A result belongs to the inspected frame. The editor must prevent a completed response from another frame or job from misleading the user. | Include delayed response and A→B→A browser tests, alongside actual loopback and installed OCR. |
| Keep the input and match labels together on small screens. Include the guide in the sdist and wheel. | Users need the two choices to stay readable on mobile and the feature needs deployment-specific guidance. | As part of the editor PR. Compare desktop and mobile against the exact installed page. |

The final source passed 71 selected checks on each of Python 3.12 and 3.9. The first 3.9 run passed 70 of 71 and the neighboring exact-editor test could not read one retired thumbnail response body. A full repeat of the same selection passed. The verified installed wheel passed 38 checks and the real browser flow on each version. Packaged browser tests used regular Playwright because the Browser plugin was unavailable. Desktop and mobile captures show stock Tesseract full and fragment matching and explicit suggestion selection without report writes. The layout regression failed on the ungrouped labels before the repair.

The worker is currently available on supported POSIX, non-frozen Python runtimes. Windows and frozen executables remain outside this verified scope. Search covers one inspected frame at a time. A search can miss text or match an unrelated shape, and a selected highlight is not a verified plate boundary.
