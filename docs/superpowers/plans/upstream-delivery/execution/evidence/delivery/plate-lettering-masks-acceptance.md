# Optional lettering-only masks on native SDR

`optional/plate-lettering-masks` at `54a3209a8ae1bdca97a8a5d2a857885f20a77fa6` follows the [stock text-region guard](plate-lettering-guard-acceptance.md). The CLI accepts `--plate-coverage narrow` and an optional source-pixel margin. Full plate coverage stays the default.

| What | Why | When to deliver |
| --- | --- | --- |
| Detect plate candidates with the existing model and propose text polygons with stock PP-OCRv5. Bind every accepted mask to the decoded frame, pixel digest and geometry. | This can reduce the area masked on a clearly localized plate without carrying lettering onto another frame. | After the isolated guard. Review scan and SDR render together so the report evidence is exercised through export. |
| Keep full-box fallbacks for unreliable or stale evidence where a plate was detected. Preserve existing unrelated plate polygons without hashing or copying the default render's full detection list. | A narrower mask needs usable evidence. Existing report geometry and the default path must continue to work. | In the same PR, with a default render regression, from-report overrides, and an encoded fallback check. |
| Expose the option through Scan Setup and restore it when rendering the same saved report. | Web users use Scan Setup and Save & Render as the normal entry points. | After native scan and render are verified independently. Keep changed, unsupported and unverified sources on ordinary coverage. |

The final commit passed 281 selected source and 18 installed checks on each of Python 3.12 and 3.9. The installed checks include actual PP-OCRv5 inference and encoded output. Removing the compatibility repair reproduces full coverage for a legacy report polygon in the default render. Narrow rows and fallback reasons persist in the report.

An independent encoded four-frame check ran both stock YOLOv9-T and stock PP-OCRv5. The same two frames narrowed and two fell back on both Python versions. All 1,080 marked strong glyph pixels per frame were below luminance 10 in the black-box output. The corner check stayed bright at roughly 230 on the narrow frames and was zero on the full-box frames. An earlier synthetic four-frame fixture with borders and a side strip produced four full-box fallbacks. The two fixtures demonstrate both paths and provide no field accuracy estimate.

The branch supports verified native SDR/CFR source frames. The visual guard can reject correctly detected plates when the secondary locator cannot establish safe geometry. The render uses the full plate box where a detection exists on unsupported video or without eligible evidence. There is no claim that the option fixes missed plates, identifies every glyph, or supports original HDR/VFR lettering masks.
