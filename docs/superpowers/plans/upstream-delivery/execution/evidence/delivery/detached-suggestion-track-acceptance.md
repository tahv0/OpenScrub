# Track a region selected from a plate-text suggestion

`optional/detached-suggestion-track` at `9b836ea12acf4429aca94d8d9d312517c4693bb7` follows [plate text search in the editor](detached-plate-editor-acceptance.md). The user can select a suggestion, choose **Adjust for tracking**, adjust the proposed rectangle and timeline window, and explicitly select **Track this region**.

| What | Why | When to deliver |
| --- | --- | --- |
| Stage an editable region against the exact inspected frame and send the confirmed box to the existing strict tracking route. | OCR provides an approximate text region. The user chooses what actually needs coverage before the tracker starts. | After the independent OCR editor. Review the confirmation, route binding, and controls together. |
| Retire stale proposals on seek, cancel, query change, and remount. On resize, release the pointer and keep the last applied box. | A proposal must never retain authority from another sample or be stranded when the browser changes size. | In the same editor PR, with real Chromium checks for seek away and back, cancellation and resizing during a drag. |

144 selected checks passed on each of Python 3.12 and 3.9, including real Chromium, stock OCR and the existing tracking endpoint. The browser fixture controls tracker output to check its exact request and report interaction. The test makes no measurement of tracking quality on filmed plates.
