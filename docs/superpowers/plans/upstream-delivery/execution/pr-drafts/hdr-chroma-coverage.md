# Cover every touched HDR silhouette chroma cell

Nearest-neighbor mask resizing could leave a U/V cell unchanged even when a silhouette selected a luma pixel in that cell. A three-pixel triangle at an odd horizontal origin, for example, reached two chroma cells but filled only one. Align the existing luma mask to the global 2×2 grid and include each touched cell.

The change stays inside the existing HDR silhouette function. Luma coverage, padding, effect calculations, defaults, SDR rendering and report geometry remain unchanged. Invalid polygon handling and resource cleanup are separate changes.

Validation:

- Final regression tests: 161 failures on the baseline; all 352 cases pass with the fix. An independent global-coordinate oracle covers sparse edges, origin parities, clipping, odd sizes, three padding values and all four modes.
- Full suite: 486 passes. Focused Python 3.12 and actual Python 3.9 runs: 360 passes each. Expected inherited optional-model/fallback diagnostics are retained in the evidence.
- Actual report-to-HDR rendering checks exact encoder-input bytes, frame count and PQ/BT.2020 signalling. Before/after luma, SDR, unmasked HDR and face/rectangle controls match. Lossy decoded pixels are not used as the mask oracle.
- Offline source distribution/wheel, exact packaged source/test bytes and installed CLI/web startup pass.

Independent task review approved. Local branch `pr/hdr-chroma-coverage`, head `0c648c2e7d3e40304dce9ae878d14709966b1fe1`, base `e21ebdf6e3ee46e6c65050dc956a9a3459152269`. [Detailed evidence](../evidence/delivery/task-161-report.md) and [review](../evidence/delivery/task-161-review.md) retain commands, fixture-development corrections and CPU/libx265 limits. Attach the relevant recipe/results when preparing an upstream PR; nothing has been published.
