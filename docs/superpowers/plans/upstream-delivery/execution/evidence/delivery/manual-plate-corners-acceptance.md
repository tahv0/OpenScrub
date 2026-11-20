# Manual whole-plate corners

The manual mask gives a user four corners around a plate on a selected exact frame. It uses the ordinary editor and existing plate detections. The user chooses the geometry. A verified manual mask can reduce how much surrounding picture is covered while retaining the existing padding.

| What | Why | When to deliver |
| --- | --- | --- |
| A versioned normalized quad tied to the input video and exact decoded index. The report transaction retains comparison evidence for a prior quad and replays the same saved edit without republishing it. | A narrower geometry needs to describe the same frame and source the user inspected. An interrupted save must preserve the user’s choices and remain safe to repeat. | P17A backend after the exact editor sample and report transaction. Lead with the source-bound record, synthetic save and encoded SDR render. [Plate discussion #22](https://github.com/austinmabry/OpenScrub/issues/22) |
| An explicit corner mode in the ordinary editor, with Reset to full plate mask and the existing geometry-draft controls. | Perspective can make a rectangle cover much more than the plate. The user can finish an edit in place and recover it across resize, review and an interrupted acknowledgement. | P17B after the backend. Lead with the manual interaction and include an ordinary box edit after a saved quad as the key compatibility control. |
| Apply a saved quad on the exact verified native SDR frame, keep ordinary mask coverage on surrounding frames, and refuse guarded output destinations that alias the input. | The user inspects and edits one frame at a time. Other frames need their own verified geometry. Render publication must preserve source bytes and identity. | Test both exact and neighboring frames on encoded synthetic media. Treat normalized or HDR source correspondence as a separate compatibility question. |

## Backend acceptance

`pr/verified-plate-quad-backend` is stored locally at `25a4de2b7828c895e21b48da67b18df9e12c9cc9`, based on the clean v1.0.97 integration. The independently reviewed patch refuses changes from a different source or stale report row, retires a valid old quad when a new ordinary box is deliberately saved, and keeps source validation through output/report publication and rollback. Creating an ordinary box, changing its times, choosing Blur or Keep visible and handling opaque fields retain the established report behavior.

In the earlier stack immediately before the alias repair, 539 selected tests and 122 installed-wheel checks passed on each Python version. The final alias patch at `e869b99` passed 153 checks on each version. Its actual video tests show that direct, hard-linked and symbolic input aliases for the report destination are refused before staging and preserve the original input and any prior output. A legacy strict box client receives a pre-mutation conflict when it cannot prove the prior valid quad. The companion editor carries the server’s exact comparison token.

## Editor acceptance

`pr/manual-plate-corners` at `4b16d13570f3628d4a8ddedb8e8a4072822d08a6` contains the clean integration and reviewed backend. The independently reviewed editor keeps corner geometry and its comparison token in the existing per-job draft. A completed save preserves newer independent edits. An acknowledgement arriving after a seek reports when saved corners belong to the previous frame and keeps the current gesture intact. Ordinary box edits can retire saved corners and render the chosen whole box in the same transaction.

- The final combined source passed 750 selected tests on each of Python 3.12 and 3.9, including real Chromium. The offline package passed 126 installed tests on each version. The identical implementation on the donor source passed four focused Chromium editor and renderer cases.
- The synthetic browser interaction dragged four handles at desktop and mobile sizes, reopened persisted corners, retried exactly after a lost save acknowledgement, resized a previously masked box, and then reset another saved quad. Decoded pixels inside the selected quad and inside the restored full mask were black. At the inspected frame, the synthetic pixel outside the quad but inside the original box retained its original color.
- The tests pin the fixture source and timeline, exercise normal non-plate saves alongside the plate editor, and verify acknowledgement when an editor has already moved to another frame. The local runtime evidence includes screenshots of the narrow viewport and decoded output samples.

## Limits

The mask is opt-in and supports the verified native SDR frame path. An unsupported frame or source keeps the ordinary mask. Existing filename, export and choice handling still apply. This topic covers manual whole-plate geometry. Pretrained text lookup, lettering-only treatment and multi-frame shape tracking remain distinct topics. [Plate discussion #21](https://github.com/austinmabry/OpenScrub/issues/21) · [Plate discussion #22](https://github.com/austinmabry/OpenScrub/issues/22)
