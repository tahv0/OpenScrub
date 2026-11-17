# First-scan OCR sanity check with backtracking disabled

**Separate source-confirmed candidate; no Task 113 fix.** The first OCR sanity check can receive `small=None` when ordinary callers disable backtracking and the first processed OCR scan returns fewer than three words. This can crash the scan before it returns a review/report state. No further tests, timings, product edits or wider audit were performed for this handoff.

## Exact source and retained observation

Source inspected: full exact-base export `e21ebdf6e3ee46e6c65050dc956a9a3459152269`, `/tmp/openscrub-task113/base/openscrub.py`, SHA-256 `0e4f0f9a7846080f591038d021aaf3ca6f01201d83ac32bbdc273f53d5067ee7`. These line numbers belong to that exact base:

| Owner | Lines | Relevant behavior |
| --- | --- | --- |
| Parser flag |6936–6938 | `--no-backtrack` is an ordinary supported option. |
| `run_scan` initialization |7519, 7523–7524 | `n_scans=0`, `BT_SCALE=.5`, and `bt_on = not getattr(args, "no_backtrack", False)`. |
| Frame preparation |7644–7645 | Half-resolution grayscale `small` is constructed only when `bt_on`; otherwise it is explicitly `None`. |
| Ordinary OCR interface |7862–7868 | `read_adaptive(ocr, frame, ...)` supplies words for real primary detection; there is no three-word minimum. |
| First-scan sanity |8029–8040 | When OCR exists, `n_scans==0`, and `len(words)<3`, Canny receives `small`, then the code computes `(_edges>0).mean()` before incrementing `n_scans`. |

Retained failure: [contract-integration-prototype.log](../delivery/task113-evidence/contract-integration-prototype.log), SHA-256 `d8cc9f059b236c080ace15bad23ec08c4abaccd86c7ea6341f3a6d3e60e4711d`.

That executed observation used the initial complete Task 113 prototype (`openscrub.py` SHA-256 `a98dbcbe139af76b7178a972470a53321acb80a7aaee1fa5d30a9623ac7870f5`), Python 3.12/OpenCV 4.14, a real decoded lossless 160×96 video, `--no-backtrack`, and controlled OCR returning two email observations. Its unchanged sanity owner appears at prototype line 8064, corresponding to exact-base line 8034. `cv2.Canny(None,60,180)` returned `None` in this environment; `_edges > 0` raised `TypeError: '>' not supported between instances of 'NoneType' and 'int'`. The test stopped before reverse finalization. This is **controlled OCR integration evidence**, not a reproduction with pretrained/real OCR inference. The exact-base applicability is source-confirmed; this handoff did not execute a new exact-base reproduction.

Task 113 subsequently gave its controlled OCR fixture a third stopword to exercise its intended reverse/report boundary. That fixture change did not repair this generic owner. The original failure and all Task 113 evidence remain unchanged.

## Applicability to ordinary callers

The trigger does not depend on a custom matcher, malformed Detection, reverse index, timestamp ordering, or OCR text content. With a text category active, an ordinary CLI caller can combine `--no-backtrack` with a valid OCR result containing zero, one or two words. Sparse/blank title frames and OCR misses are plausible sources; the source itself explicitly anticipates such results through the sanity guard. An embedder supplying `args.no_backtrack=True` has the same path.

The error occurs on the **first processed OCR scan**, which need not be the video's first frame after window/skip controls. It happens before edge density can decide whether a warning is needed, so a blank frame is not exempt. Other OpenCV versions might reject the invalid Canny input differently; no cross-version exception claim is made. Default backtracking enables `small`, and detector-only jobs have `ocr=None`, so those paths do not meet this particular missing-image trigger. No normal-inference execution was performed to measure prevalence.

## Smallest separate repair boundary

Repair only the `run_scan` first-scan sanity owner: when that existing low-word-count guard fires, reuse `small` if available; otherwise lazily derive a local half-resolution grayscale sanity image from the already decoded current frame using the existing `BT_SCALE`. Feed that valid image to Canny. Keep the backtracking variable/buffers disabled and avoid computing extra images on every frame.

Preserve the existing first-scan/OCR/word-count guard, Canny thresholds 60/180, strict edge-density threshold>.02 and warning behavior. Merely suppressing sanity warnings under `--no-backtrack`, catching all exceptions, or enabling backtracking to obtain `small` would change the behavior this check exists to provide. Do not couple this repair to reverse recall, change OCR thresholds/defaults, or broaden it into generic image validation. A future implementation must pin its own exact reviewed base and verify the actual returned/report state.

## Meaningful future RED/GREEN integration cases

Use real video decoding, actual `run_scan`, actual Canny, actual primary detection and actual `write_report`; control OCR only at its existing inference interface. Do not replace Canny or initialize `small` in the test, since either would hide the defect.

- Parameterize first processed OCR output counts 0/1/2 with `--no-backtrack` on a deterministic edge-rich frame. Before the repair these reach the missing-image failure; afterwards each completes and retains the sanity warning when measured edge density exceeds the existing threshold. At least one case should include one actual primary email and assert its full returned/report record, rather than only absence of an exception.
- Use an edge-free frame with the same disabled-backtracking/low-word-count trigger. Afterwards the scan/report completes without a sanity warning. This proves the warning's density decision still executes instead of being unconditionally emitted.
- Compare enabled-backtracking low-word-count control behavior, plus a disabled-backtracking first scan with three words. Preserve the original warning/non-warning semantics and Detection fields/order. A later low-word-count scan after an initial three-word scan must not start a new first-scan warning.

These would be controlled pipeline integration tests, not OCR-model quality or throughput evidence. Ordinary nonstubbed OCR can be an additional follow-up check if already available offline, but is not required to reproduce this owner deterministically. Follow focused RED/GREEN and owning full/floor/package verification in that separate candidate; no tests were run for this source-only handoff.
