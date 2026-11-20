# Manual plate corners on a verified live HDR pair

`pr/manual-plate-corners-hdr` at `1ff66cfd03df082867180c672c67a76af5a75ba6` adds live editor and 10-bit render support after the [fresh HDR proof](optional-hdr-pair-proof-acceptance.md). A job requests the proof explicitly through `verify_hdr_plate_frames: true` or `--verify-hdr-plate-frames`. The Scan Setup checkbox remains open.

| What | Why | When to deliver |
| --- | --- | --- |
| Carry the opt-in fresh-pair evidence with the job's live source owner. Allow corner edits only while the inspected SDR frame, saved geometry and original HDR bytes still correspond. | The normalized review pixels and the actual output must identify the same frame. | After the independent fresh-pair producer. Show the actual scan, editor save and 10-bit decode/render on a small fixture. |
| Apply the selected quad on its one HDR frame. Preserve full masks on other frames and guard both sources through publication, including early decoder exit and file replacement. | Correspondence covers a single user edit. Partial or mixed-source output would lose previously protected pixels. | Verify actual 10-bit luma and each touched 4:2:0 chroma cell, neighboring frames, fallback and rollback before local acceptance. |

324 selected tests, including real Chromium, passed on each Python version. The installed-wheel verification passed 61 checks on each version. The real scan used the pinned stock YOLOv9-T model. The native pre-encode Y/U/V arrays show the selected-frame mask, untouched outside samples and whole-plate masking at the adjacent indices. The emitted file remained 10-bit PQ. Ordinary source adoption keeps its existing function call and avoids loading the report for an absent optional proof.

The initial HDR path covers a fresh zero-origin, nonrotated integer-rate CFR PQ/HLG pair in a live job. A cached copy alone, a restarted job, unsupported transformation or changed source falls back to ordinary plate coverage. A verified SDR scan copy can also be rendered directly with [the same-file rule](quad-sdr-scan-copy-acceptance.md).
