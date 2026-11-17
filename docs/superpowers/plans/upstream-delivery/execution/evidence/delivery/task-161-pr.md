# Fix dropped HDR silhouette chroma cells at sparse edges

Nearest-neighbor mask resizing could leave a U/V cell unchanged even when an ordinary silhouette selected a luma pixel in that cell. For example, a three-pixel triangle at an odd-x origin reached two chroma cells, but only one was filled. Align the existing luma mask to the global2×2 grid and select the union of each cell. Luma, padding, redaction modes, defaults, SDR rendering and report geometry stay unchanged.

The change is confined to `_blur_silhouette_yuv10`, with independent global-coordinate oracle tests, actual report→run_render→libx265 encoder-input assertions, and test discovery/sdist guidance. No donor rasterizer/schema, geometry repair or resource/output policy changes.

Validation:

- Owning baseline RED:161 failed/191 passed; candidate GREEN:352 passed.
- Full discovered Python3.12 suite:486 passed; relevant focused3.12 and actual3.9:360 passed each.
-348 direct baseline/candidate luma and SDR byte comparisons,56 face/rectangle controls, actual sparse HDR wire coverage and byte-identical SDR/unmasked HDR controls.
- Real three-frame lossless PQ source and actual HEVC output retain10-bit format, frame count, PQ/BT.2020 signalling. Lossy decoded output is not the mask oracle.
- Offline sdist→wheel, exact source/test package bytes, correct-runtime installed CLI/web startup and114 committed-source hashes passed.

Base:`e21ebdf6e3ee46e6c65050dc956a9a3459152269`.
Head:`0c648c2e7d3e40304dce9ae878d14709966b1fe1`.
Artifacts:`/tmp/openscrub-task161`; details:`task-161-report.md`.

Bounded CPU/libx265 evidence; no quantified privacy, hardware or cross-platform claim. Independent review is pending with the supervisor. Not published.
