# Exact plate corners on rendered SDR scan copies

`pr/plate-quad-sdr-scan-copies` at `5d2c303a400967450f59c06c270009f7bc540cb0` extends the [reviewed manual corner editor](manual-plate-corners-acceptance.md).

| What | Why | When to deliver |
| --- | --- | --- |
| Allow a manual quad on the verified inspected frame of a normalized SDR scan copy when that exact file is the render input. Retain source digest, timeline and indexed-frame checks. | The scan and render share the same pixels and frame index in this case, even when the scan came from an HDR tone-map or VFR normalization. Rejecting the edit left that useful case unavailable. | An independently reviewable follow-up to the existing plate editor, before original HDR pairing. |
| Preserve ordinary fallback for unverified source choices. Reject render and report paths that alias the guarded input or retained original. | The same-file rule gives no correspondence between a normalized scan and the original source. Publication must preserve both input files. | Verify against fresh encoded normalized clips, an actual HDR output switch, altered scan bytes, and direct and linked aliases. |

The frozen source passed 490 selected tests on each of Python 3.12 and 3.9, including Chromium. The installed wheel passed 91 tests on each version. The original red case used a 10-bit PQ source and the production SDR normalizer. The accepted synthetic renders cover the quad's inside and outside edges, ordinary neighboring-frame masks, and VFR-to-SDR normalization. Rendering to an original HDR source still uses ordinary plate coverage until the matching source pair and HDR decoder can prove the selected frame.
