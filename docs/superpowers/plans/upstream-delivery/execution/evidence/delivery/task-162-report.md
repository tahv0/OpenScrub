# Task 162 — unusable polygons retain full known-box redaction

## Delivery identity

- Exact base: `e21ebdf6e3ee46e6c65050dc956a9a3459152269`.
- Exact head: `a3c3193e8dff41ec0588e66443398048a5c15ece`.
- Commit: `fix: fall back to known box for unusable polygons`.
- Native branch/worktree: `pr/invalid-polygon-fallback`, `/home/tahv0/.codex/worktrees/c832/OpenScrub`; final native Git status is clean.
- Artifacts: `/tmp/openscrub-task162`. This report and `task-162-pr.md` are the requested handoff documents in the SDD workspace, outside the product commit.
- Requirements/provenance: `task-162-brief.md`, including its degeneracy compatibility clarification; `mask-fidelity-research.md` N03 and relevant `probe_masks.py` source. Task161/109 isolation, packaging and observation recipes were consulted. Donor `8697c2811db6cfda644f730284e037f7294b47cc` identifies research provenance; no donor file or combined-branch runtime code was copied. P16A and N09 are absent from this base by design.

## Trigger and implementation

When the renderer has a valid finite positive render box, malformed polygon data must choose the existing full-box redaction over that same clipped/padded region in the requested mode. The former unchecked conversion could throw for NaN/Inf, malformed or nonnumeric points; a collinear/repeated contour could leave only a tiny nonempty mask and evade fallback.

A local `_silhouette_mask` helper next to `blur_silhouette` shares only validation and raster decisions. SDR and HDR retain their own full-box fill functions, masked fill, clipping, kernels, dilation and encoder paths. Each caller computes its existing clipped integer region, returns normally for an empty intersection, then requests a mask. `None` selects its existing `blur_region` or `_blur_yuv10` fallback with the original region arguments. No detection is silently dropped on polygon conversion failure.

Validation requires a real four-coordinate finite positive `poly_box`, finite two-coordinate point rows, finite coordinate mapping and safe signed int32 local coordinates before conversion. Box width/height retain the existing `max(1.0, span)` mapping. A malformed component invalidates the overall polygon mask; the existing empty/two-point component skip remains, including empty-plus-valid compatibility. Missing/empty/two-point-only and wholly clipped-empty polygons retain their existing fallback. Legitimate out-of-normalized-range coordinates still go through OpenCV clipping, with no arbitrary cap. A passing control uses a normalized coordinate `-10000001` and local mapped coordinate `-120000012`, well beyond the rejected donor's arbitrary ceiling but within int32.

After rounding, each painted contour needs noncollinear integer vertices. The cross products use Python integers, avoiding int32/int64 arithmetic overflow. Repeated points, collinear points and shapes that quantize to a line request full-box fallback. Signed contour area is deliberately not a validity condition: an actual bowtie control has zero signed area and a usable two-dimensional fill; it remains byte-identical to baseline. Concave contours and valid clipped contours also retain their exact prior behavior. No compound holes or new polygon semantics are introduced.

Conversion failures are caught locally as `TypeError`, `ValueError` and `OverflowError`. OpenCV `StsBadArg` (-5), `StsOutOfRange` (-211) and `StsAssert` (-215) select known-box fallback. Other OpenCV errors propagate. Controlled tests specifically preserve `MemoryError`, unrelated `RuntimeError` and native-coded `StsNoMem` (-4), so resource/programmer failures do not become claimed successful redactions. Mask allocation remains outside the conversion exception boundary.

## Changed files

| File | Change |
| --- | --- |
| `openscrub.py` | Shared local validation/raster helper, stdlib math import, and two narrow leaf substitutions. |
| `tests/test_polygon_fallback.py` | 548 synthetic direct/actual render regressions and compatibility cases. |
| `pyproject.toml` | Include `tests/` and contributor guidance in sdist; ordinary runtime wheel contents stay unchanged. |
| `CONTRIBUTING.md` | Use full discovered pytest command so new directory tests run. |

No dependency, model, schema, Detection/report shape, custom model/training, mask_pad, chroma union, whole-frame fallback or UI change. Version, supported modes and Austin defaults remain unchanged. AST comparison confirms every preexisting function/class except the two owning leaf functions is identical to base, including parser defaults, report loading, render orchestration, encoder/color/quality policy and output lifecycle. Existing P16A-scoped HDR chroma behavior on this base is preserved, not repaired by this PR.

## RED → GREEN and corrections

Tests preceded the product change. Clean initial owning `red-final.log` at exact base: **336 failed, 184 passed, 27.25s**, exit1. These are real production leaf failures plus ordinary JSON report → actual SDR/HDR render failures. All usable contour controls and existing empty controls passed baseline. Initial candidate `green.log`: **520 passed, 5.00s**, exit0.

Additional exception-boundary tests produced an exact-base full-file replay (`red-replay.log`): **342 failed, 190 passed, 28.72s**, exit1. This run predates the corrected exception fixture and final container cases; it is not labeled as final-test-byte evidence. Candidate restoration was byte-exact.

The first focused run with exception injection (`focused.log`) had **6 failed, 534 passed, 126 deselected, 18.09s**. Root cause: manually calling `cv2.error(code, ...)` does not populate `.code`; native errors do. Only the test fixture changed to set the native error code explicitly. Corrected focused baseline replay (`red-exception.log`): **6 failed, 6 passed, 520 deselected, 0.68s**, proving the fallback cases fail baseline and resource/unrelated exceptions already propagate. No unchanged 520-case baseline rerun was needed. Restored candidate (`focused-final.log`): **540 passed, 126 deselected, 17.61s**.

Self-review found that generic `map(float, poly_box)` could interpret a four-character string or numeric-key dictionary as geometry. New tests first produced **16 failed, 72 passed, 460 deselected, 0.25s** (`red-container.log`). Requiring ndarray shape `(4,)` before unpacking fixed the issue; final focused/full/floor/package checks use these stable bytes.

Superseded initial `red.log` is not acceptance evidence: two accidentally overlapping baseline launches shared its output destination, and the initial SDR harness used `encoder="libx264"` rather than the existing CPU preference `"x264"`, unnecessarily exercising GPU probes. The clean owning rerun corrected that preference before product edits. A preparation script also stopped on a missing-math-import assertion before writing product code; the explicit stdlib import corrected preparation. These harness/preparation failures are retained separately from owning behavior evidence.

## Actual media versus controlled execution

Direct cases use synthetic deterministic 32x32 SDR frames and native 10-bit Y/U/V planes. Every supported mode (`box`, `blur`, `mosaic`, `inpaint`) is checked against the actual existing full-box renderer, including a partly out-of-frame padded render region with a separately supplied polygon box. Equality is over whole arrays, protecting unchanged unrelated pixels. Invalid poly_box cases deliberately provide a separate valid render box; they do not claim ordinary malformed primary boxes have independent fallback geometry.

Usable-path expected masks use literal hand-mapped integer contour tables, the existing OpenCV raster semantics and unchanged dilation/chroma resizing. These tests passed the original baseline before the new helper. Independent exact-base/current-function comparisons at final bytes cover **96 direct controls**: both paths, four modes, six valid contour/control shapes and two padding values. All output arrays are exactly equal (`control-comparison.json`).

The media tests load ordinary reports through actual `load_report`, then invoke actual `render` or `render_hdr` with actual FFmpeg processes. Fixtures are two-frame 64x64 synthetic SDR and 10-bit PQ/BT.2020 clips at2fps, a known person box `(4,4,16,16)` and existing2px pad. Four malformed/degenerate classes (missing coordinate, NaN, collinear, repeated), the existing two-point fallback and concave/bowtie controls run through both paths. Their actual pre-encode buffers are compared with an independently rendered report containing the absent polygon. Equality checks all bytes of both frames, including unrelated pixels. Separate decoded output equality is asserted after lossy encoding; this is not a claim that decoded pixels equal their source/pre-encode values.

At final candidate bytes an additional **8 actual-media baseline/current controls** compare concave, bowtie, valid clipped/partly out-of-frame and full-box reports in SDR and HDR. Pre-encode bytes match exactly, and decoded output matches separately; hashes are retained in `control-comparison.json`. These checks ran actual original and candidate functions from separate source modules, not a donor leaf swap.

The observer uses a read-only Python trace immediately before each real encoder write, copying the actual buffer while leaving commands, streams and write effects intact. A Popen subclass retains real child owners; a VideoCapture factory retains real capture owners. Successful children have returncode0 and independent `waitpid(..., WNOHANG)` evidence that they are already reaped before harness containment. An unconditional finally restores tracing/patches, releases captures, terminates remaining children, closes streams and temporary stderr files, waits, and kills/waits only on harness timeout. This containment also runs on baseline geometry exceptions and failed assertions. It is test-harness cleanup, not a production resource-lifecycle fix or a claim that arbitrary errors preserve prior output.

The six injected OpenCV geometry-error tests and six resource/unrelated-error tests are explicitly controlled exception-boundary coverage. Actual conversion/degenerate/report regressions and valid media controls exercise real native rasterization; synthetic error codes are not presented as real decoder/encoder failure evidence.

## Stabilized verification

All commands run from native cwd `/home/tahv0/.codex/worktrees/c832/OpenScrub`, with active-import/code-filename assertions. Runtime versions: Python3.12.16, OpenCV4.14.0, NumPy2.5.5 and FFmpeg8.0.1. Focused floor uses actual Python3.9.25, not only grammar parsing.

| Check | Result | Artifact |
| --- | --- | --- |
| Final geometry/render3.12 | **556 passed,126 deselected,16.62s**, exit0 | `focused-stable.log` |
| Exact baseline/current usable controls | **96 direct +8 actual-media controls**, exit0 | `control-comparison.log/.json` |
| One stabilized full discovered suite | **682 passed,62.00s**, exit0 | `full.log` |
| Actual3.9 focused active-source | **556 passed,126 deselected,18.50s**, exit0 | `floor.log` |
| Offline sdist→wheel build | exit0; hatchling1.33.0 from existing wheelhouse | `build.log` |
| Exact source/test/guidance inclusion +3.9 grammar | exit0 | `packaging.log/.json` |
| Install using prepared3.12 and cached pip code | exit0 | `install-runtime.log` |
| Installed CLI/web startup with fresh profile | exit0; CLI help and homepage/empty jobs HTTP200; SIGTERM rc0 | `installed-startup.log/.json`, `installed-web.log` |
| Stable native/installed/committed bytes +clean status | exit0;114 frozen files | `final-check.log`, `final-provenance.json` |

The passing full suite retains inherited optional spaCy warnings, inactive optional plate/person model messages, failed real GPU probes with CPU fallback, blocked VitTrack fetch/template fallback and model-backend fallback diagnostics. No test failed. These expected diagnostics are dispositioned as inherited optional-model/fallback behavior and later owning-test hygiene, not new P16B failures. No model/dependency/download/test-cleanup expansion was performed to silence them.

## Isolation and package/source binding

Task-local TMPDIR/cache/config/profile/app/model paths and a task-only site hook block outward Python network connections and writes outside task artifacts. Autofetch is disabled, with a local-only model-fetch wrapper. The existing YuNet file was copied into task runtime only after matching the unchanged pin `8f2383e4dd3cfbb4553ea8718107fc0423210dc964f9f4280604804ed2552fa4`; `model-reuse.txt` records source/hash. New regressions require no models. Authorized escalation was used only for native-worktree/Git writes and actual loopback startup. No original-checkout product or user-data modification, model/dependency download, publication, external message or nested agent occurred. The supervisor supplies the independent reviewer; this report records implementation self-review, not independent approval.

`stable-source-sha256.json` froze114 source/test/guidance files before the full run. `tested-source-sha256.json` matches it exactly. Final native source, installed source and committed `git show HEAD:<file>` bytes match those manifests; all unrelated preexisting function/class ASTs match base. Engine SHA256 `d3f87fb77b8f855c730caea5c78c7e7ccb5c8c83a0c0ead40872e4c77f0d33eb`; regression test SHA256 `7a10ad61ac994f2943b3c20a7c7bba97f1e401c0978026c05d637cc6cd1e7858`. Sdist contains exact new tests, source and guidance; ordinary runtime wheel bytes match native application modules, and tests remain in the sdist rather than the runtime wheel. Installed CLI/web shebangs name `/tmp/openscrub-baseline-20261116/venv-opencv4/bin/python` and installed import/code filenames point into the task target.

Wheel SHA256 `2ce0dea67a0dc540c1c1bb6f16bfd8da276faeb19451d526d80fa68656f98f3c`.
Sdist SHA256 `1cde9830e6efd468a64b67b2fc7c9bfc901206a3f21064e9e26f727762219d65`.

Reproduction commands (task-local helper scripts are retained):

```sh
cd /home/tahv0/.codex/worktrees/c832/OpenScrub
. /tmp/openscrub-task162/env.sh
python -m pytest -q -s -o cache_dir=/tmp/openscrub-task162/pytest-cache tests/test_polygon_fallback.py test_openscrub.py -k 'polygon or silhouette or hdr or render or codec' --basetemp /tmp/openscrub-task162/focused-stable-tmp > /tmp/openscrub-task162/focused-stable.log 2>&1
python /tmp/openscrub-task162/control_compare.py > /tmp/openscrub-task162/control-comparison.log 2>&1
python -m pytest -q -s -o cache_dir=/tmp/openscrub-task162/pytest-cache --basetemp /tmp/openscrub-task162/full-tmp > /tmp/openscrub-task162/full.log 2>&1
. /tmp/openscrub-task162/floor-env.sh
python -m pytest -q -s -o cache_dir=/tmp/openscrub-task162/floor-cache tests/test_polygon_fallback.py test_openscrub.py -k 'polygon or silhouette or hdr or render or codec' --basetemp /tmp/openscrub-task162/floor-tmp > /tmp/openscrub-task162/floor.log 2>&1
. /tmp/openscrub-task162/env.sh
PIP_NO_INDEX=1 PIP_FIND_LINKS=/tmp/openscrub-task620/build-wheelhouse python -m build --outdir /tmp/openscrub-task162/dist > /tmp/openscrub-task162/build.log 2>&1
python /tmp/openscrub-task162/check_packaging.py > /tmp/openscrub-task162/packaging.log 2>&1
PYTHONPATH=/tmp/openscrub-baseline-20261116/bootstrap/lib/python3.14/site-packages python -m pip install --no-index --no-deps --upgrade --target /tmp/openscrub-task162/installed/site-packages /tmp/openscrub-task162/dist/openscrub-1.0.96-py3-none-any.whl > /tmp/openscrub-task162/install-runtime.log 2>&1
python /tmp/openscrub-task162/check_installed.py > /tmp/openscrub-task162/installed-startup.log 2>&1
python /tmp/openscrub-task162/final_check.py > /tmp/openscrub-task162/final-check.log 2>&1
```

Pip code is supplied through PYTHONPATH to the existing3.12 interpreter; the bootstrap3.14 interpreter is not used to install. The installed web smoke uses a fresh task profile, ephemeral loopback port, real entrypoint, and unconditional server stop/reap.

## Self-review and limits

Reviewed the final four-file diff, owning raster call sites, compatibility oracles, error-code boundary, actual pre-write observation and unconditional test containment. The final source has one local shared helper, exact representational bounds and no broad renderer rewrite. Hash/AST gates bind validation to the committed candidate; no unnecessary repeat full suite was substituted for that binding.

This is P16B only. A nonfinite, reversed or zero-area primary cbox has no usable known fallback, and its rejection/publication contract remains separate P16C-G work. A separately invalid poly_box with a valid render box does fall back here. Finite boxes partly outside the frame and normal empty intersections remain legal. No primary-box repair, whole-frame mask, prior-output atomicity/publication preservation, arbitrary-failure cleanup or N09 decoder-close claim is made. Preview-outline rendering, compound holes, new masking policy, P16A chroma union, GPU/Windows certification, browser UI, models and heavy benchmarks are outside this narrow change. CPU synthetic Linux and focused actual3.9 evidence do not certify every encoder, platform or native-call failure boundary.
