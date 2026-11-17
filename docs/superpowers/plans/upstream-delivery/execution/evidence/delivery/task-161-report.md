# Task161 / P16A: HDR silhouette chroma coverage

Nearest-neighbor mask resizing omitted U/V cells touched by ordinary silhouette luma pixels, particularly sparse edges and odd origins. The existing HDR silhouette owner now aligns its unchanged luma mask to global 2×2 cells and selects each cell's union. Luma rasterization, padding/dilation, effect calculations, defaults, report geometry and SDR rendering remain unchanged.

Implemented and self-reviewed on 2026-11-17; supervisor supplies independent review. No publication.

- Exact base: `e21ebdf6e3ee46e6c65050dc956a9a3459152269` (Austin plus test-only correction).
- Exact head/commit: `0c648c2e7d3e40304dce9ae878d14709966b1fe1`, `fix: cover every touched HDR silhouette chroma cell`.
- Native branch/worktree: `pr/hdr-chroma-coverage`, `/home/tahv0/.codex/worktrees/c832/OpenScrub`; final status clean.
- Retained artifacts: `/tmp/openscrub-task161`. This report and `task-161-pr.md` are the explicitly requested SDD handoff files outside the product commit.
- Requirements/provenance read: `task-161-brief.md`, `mask-fidelity-research.md` N02, and its actual-function/preencoder recipe `mask-fidelity-research-evidence/probe_masks.py`. Donor `8697c2811db6cfda644f730284e037f7294b47cc` is provenance; no donor file, rasterizer, schema or defaults were transplanted.

## Product change and owners

`_blur_silhouette_yuv10` alone changes in `openscrub.py`: place the existing luma mask at its odd-origin offset in a zero-padded grid, reduce each aligned 2×2 cell with max, and explicitly pass luma/chroma masks to the existing per-plane fill. Crop the selected chroma mask to the actual clipped chroma ROI. The full-plane source prefix before this owner and suffix after it are exactly identical to base, as asserted by `control_compare.py`. Luma mask creation/dilation and all four mode effect calculations retain their original code. Chroma values outside selected cells retain their original bytes. Final partial cells and clipped borders are covered.

| Changed file | Purpose |
| --- | --- |
| `openscrub.py` | Only the existing HDR silhouette luma-to-chroma mapping;15 additions/9 removals. |
| `tests/test_hdr_chroma_coverage.py` |348 direct geometry/pad/mode cases plus literal/square control, actual sparse HDR report render, unmasked HDR control and SDR report render. |
| `pyproject.toml` | Include `tests/` and contributor instructions in sdist; unchanged dependencies/backend/version/wheel application inclusion. |
| `README.md`, `CONTRIBUTING.md` | Full discovery via `python -m pytest -q`; document synthetic FFmpeg/ffprobe/libx265 tests and their tool-availability skips. |

No invalid-polygon, invalid-box, fallback/repair, shape/schema, coordinate ceiling, model or environment migration work was included. Comprehensive resource/output policy remains P16B/C/N09. No neighboring face/rectangle change was made.

## Independent oracle and direct coverage

The oracle rasterizes literal integer polygon vertices with the existing OpenCV polygon semantics, independently of normalized-coordinate production conversion. It expands padding through an explicit coordinate-neighbourhood union rather than the production dilation. It enumerates each selected **global luma coordinate** and marks `(row//2, col//2)` in the expected U/V mask; it never uses aligned reshape/reduction or production mask mapping. A literal sparse fixture pins luma `[[5,5],[5,6],[6,5]]` and chroma `[[2,2],[2,3],[3,2]]` at origin(4,4). The existing filled square at(1,1,5,5) passes baseline and candidate as a control.

The348 direct cases are29 geometry/shape combinations × padding0/1/3 × box/blur/mosaic/inpaint:

- Full square, sparse triangle with local vertices(1,1),(2,1),(1,2), thin right-edge triangle and diagonal triangle.
- All four origin parities(4,4),(5,4),(4,5),(5,5),12×12 ROIs; an odd13×11 ROI at(5,5).
- Square/diagonal masks crossing top-left, bottom-right, bottom-left and top-right frame boundaries; a sparse clipped triangle at(-1,-1), with odd final clipped extents.
- Exact full Y/U/V arrays against independent masks and the unchanged full-ROI mode effect, obtained from the separate existing rectangle owner. Expected cell identity includes untouched areas; source patterns make coverage meaningful for every mode.

Native values use seeded spatial contrast and odd source values, so inpaint's four-aligned fill is distinguishable. Box establishes every selected cell's identity. Blur/mosaic/inpaint must change at least80% of selected samples in each plane; complete expected plane bytes are asserted for all modes. Mosaic can legitimately retain a central sampled value on odd ROIs, so its changed-value identity is the selected mask intersected with values that differ, not an assertion that every effect necessarily alters every selected numerical value. `control_compare.py` separately compares every candidate luma plane to actual base for all348 cases and every SDR silhouette result to actual base: all byte-identical.56 unchanged HDR face/rectangle mode/origin/border controls also match base exactly.

## Owning RED → GREEN

Final test bytes were replayed against exact base source, then the candidate bytes restored unconditionally with a shell EXIT trap. `red.log` starts with actual native base import paths and engine SHA256. The replay failed161 cases and passed191:160 direct cases failed exactly at U coverage comparison, after exact Y passed; the161st is the actual sparse HDR encoder-input byte assertion. The filled square, unmasked HDR and SDR controls passed. This avoids crediting a square-only test as the regression.

Candidate owning `green.log`:352 passed. Focused/full/floor/build/installed verification was then run at stable source bytes. A restoration equality check confirmed the candidate engine matched the exact saved candidate after RED replay.

Earlier fixture development is retained transparently: the first test-creation attempt hit the task-local audit guard when3.12 attempted to write outside the artifact root; using system Python for authorized native edits resolved it. `red-initial.log` includes an SDR oracle mismatch caused by FFmpeg BGR conversion differing from the application's actual OpenCV decode, empty clipped polygons outside current scope, and checkerboard mosaic aliases. `red-fixture-alias.log` retained remaining checkerboard alias checks; `red-seed161.log` is161 intended failures/191 passes. The first candidate run (`green-fixture-collision.log`) had2 failed/350 passed, solely fixture visibility guards on a repeated V mosaic value. Final seeded162 contrast removes that collision. Final test bytes were rechecked against exact baseline (`red.log`:161/191), and candidate (`green.log`:352 passed). No product fix beyond the single mask mapping was made in response to fixture failures.

## Real ordinary report → run_render → HDR encoder

The fixture is64×64,3 fps,3 frames, exact native10-bit planes Y/U/V900/800/300. Actual libx265 lossless encoding sets PQ/smpte2084, BT.2020 primaries and bt2020nc matrix before input and in the bitstream. Independent FFmpeg decode of the source equals the raw fixture bytes. An ordinary report is loaded through real `load_report`, then actual imported `run_render` calls actual `render_hdr`; no renderer or leaf substitution is used. Detection is ordinary person silhouette with `cbox=[5,4,17,16]`, local sparse triangle, t0..1, zero motion/bands, pad0, box mode, libx265, unchanged default archival quality, no audio.

A read-only Python trace observes each real encoder-write argument immediately before `enc.stdin.write`, copies its bytes, and restores the previous trace in finally. Commands, pipe methods, write data and effects are untouched. Actual Popen children are retained for observation through a subclass that changes no command or IO. Before assertions on the mask, actual render children have returncode0, closed stdin/stdout and independent POSIX `waitpid` evidence that they are already reaped. The harness has unconditional finally containment to close streams, terminate/wait live children, kill/wait only on harness timeout, and close retained temporary stderr files, including RED assertion failures. Harness cleanup is not claimed as production cleanup or comprehensive exception-lifecycle coverage.

| Exact pre-encode first-frame evidence | Base | Candidate |
| --- | --- | --- |
| Luma selected global(y,x) |(5,6),(5,7),(6,6) |same |
| Required chroma(y,x) |(2,3),(3,3) |same |
| U at required cells |800,512 |512,512 |
| V at required cells |300,512 |512,512 |
| Changed native samples Y+U+V |5 |7 |
| Unrelated pre-encode samples |unchanged |unchanged |

All3 captured candidate frames equal a literal independently constructed expected frame. The base and candidate luma bytes are identical. Both source and candidate output probe as HEVC,64×64,yuv420p10le,bt2020nc,smpte2084,bt2020 with3 frames. The source and unmasked HDR control's pre-encoder SHA256 is `174c242e9bd68fe5ee9512274b5d681a990b06737ad4ff1b74221753eecd725d`. Sparse pre-encoder SHA256 changes from `b6ff469dce5d7bd12e445beef99c34bbbe9984332aad9dfea7397ae6f27f04bf` to `1bdc57cd37e7fb4a85bfdfd4f4409d5d7583c2d6634c695e2977615b80948868`.

Actual SDR uses the ordinary report and real `run_render`→`render`→libx264 path. Its expected input is derived from actual OpenCV source frames plus the three literal luma pixels, avoiding a different decoder's conversion assumptions. Base/candidate SDR encoder-input bytes and decoded output bytes are identical; pre-encoder SHA256 `80aa54a2d073f3e186df70a5c204f5f701ec4937c7ae1238c3007b1bd90fba60`, decoded SHA256 `9ac0f6483017cb4ddbf4a444173e9d8e5e97ccde028eec6da600b4ed289a98c7`. Unmasked HDR input and decoded output controls also match base exactly. Sparse HDR decoded bytes change, as expected; they are lossy and are not used as an exact mask oracle. No visible-privacy-leak or quantified privacy-improvement claim is made.

## Source/runtime/package binding

Every pytest command starts in the native worktree and uses `task161_isolation.py` to assert actual `openscrub`, `openscrub_web`, `zones_ui` paths plus `run_render`/`render_hdr` code filenames before collection/testing. This is an actual-import gate, not PYTHONPATH alone. Main runtime: existing prepared Python3.12.16, OpenCV4.14.0, NumPy2.5.5, FFmpeg8.0.1-3ubuntu2, Linux WSL2 CPU. Actual Python3.9.25 executes the focused tests with the same source gate. Grammar checks supplement actual3.9 execution.

Task-local cache/TMPDIR/config/app/profile paths, Python outward-network/write guards, disabled model autofetch and an explicit local-only `_fetch_model` wrapper isolate test data. The unchanged full suite reuses only the existing YuNet file after SHA256 verification against the unchanged engine pin `8f2383e4dd3cfbb4553ea8718107fc0423210dc964f9f4280604804ed2552fa4`; see `model-reuse.txt`. Existing VitTrack fallback tests may log a download attempt, but the wrapper rejects external fetching before network access. No model or dependency was downloaded or added. Existing109 helpers were adapted for isolation/package/installed smoke only; no109 product source or branch was reused.

Engine base SHA256: `0e4f0f9a7846080f591038d021aaf3ca6f01201d83ac32bbdc273f53d5067ee7`.
Candidate/commit SHA256: `d69d965a83d0e1544e772839e72778e9cf653495fbe1819c22613e510b3aa3f8`.
Committed test SHA256: `a911fe2f3987be1385a2794f92ddf4e6836ff83e587c28c0246f350bab8851cd`.
Unchanged web SHA256: `9835e1137abee62c0a78e2669ed8bae7059e36bf4bed9f5c7a44f0eb8b40ed3a`; zones SHA256: `a1cdb4e5be90cf2e4282268f7c2499ed2b00879a034f68235d35d56cd74752f7`.

`tested-source-sha256.json` freezes114 source/test/guidance files. All hashes matched before commit and, afterward, native and `git show HEAD:<file>` bytes matched every hash. `packaging.json` verifies sdist engine/web/helper/test/guidance bytes and wheel application source bytes; tests stay in sdist rather than the application wheel. `final-provenance.json` binds exact base/head, native branch, interpreter/tool versions, hashes and clean status. Correct3.12 installed source bytes equal native/wheel bytes and CLI/web entrypoint shebangs name the prepared3.12 interpreter. Installed startup asserts installed source paths, current parser defaults, CLI help and HTTP200 for homepage/empty jobs using task-local profile data; server exits0 on SIGTERM.

## Commands and results

All commands below use cwd `/home/tahv0/.codex/worktrees/c832/OpenScrub`. Exact helper/edit scripts and logs remain under `/tmp/openscrub-task161`. Native edits/Git and loopback commands used authorized `require_escalated`. Source hooks are for verification; `/usr/bin/python3` performed authorized source-file edits because the task-only Python audit guard intentionally rejects source writes.

```sh
# Before product edit; final test bytes also replayed with exact base source.
# Final red.log: exit1,161 failed/191 passed,2.83s.
. /tmp/openscrub-task161/env.sh
python -m pytest -q -s -o cache_dir=/tmp/openscrub-task161/pytest-cache tests/test_hdr_chroma_coverage.py --basetemp /tmp/openscrub-task161/red-tmp > /tmp/openscrub-task161/red.log 2>&1

# Candidate owning GREEN: exit0,352 passed,2.00s.
python -m pytest -q -s -o cache_dir=/tmp/openscrub-task161/pytest-cache tests/test_hdr_chroma_coverage.py --basetemp /tmp/openscrub-task161/green-tmp > /tmp/openscrub-task161/green.log 2>&1

# Relevant stable-source3.12: exit0,360 passed/126 deselected,16.21s.
python -m pytest -q -s -o cache_dir=/tmp/openscrub-task161/pytest-cache tests/test_hdr_chroma_coverage.py test_openscrub.py -k 'hdr or render or codec or chroma' --basetemp /tmp/openscrub-task161/focused-tmp > /tmp/openscrub-task161/focused.log 2>&1

# Base/candidate direct and actual saved media controls: exit0.
python /tmp/openscrub-task161/control_compare.py > /tmp/openscrub-task161/control-comparison.log 2>&1

# After existing YuNet hash verification/copy into task-local runtime/models.
# One full discovered run at stable bytes: exit0,486 passed,76.30s.
python -m pytest -q -s -o cache_dir=/tmp/openscrub-task161/pytest-cache --basetemp /tmp/openscrub-task161/full-tmp > /tmp/openscrub-task161/full.log 2>&1

# Actual floor3.9.25: exit0,360 passed/126 deselected,16.79s.
. /tmp/openscrub-task161/floor-env.sh
python -m pytest -q -s -o cache_dir=/tmp/openscrub-task161/floor-cache tests/test_hdr_chroma_coverage.py test_openscrub.py -k 'hdr or render or codec or chroma' --basetemp /tmp/openscrub-task161/floor-tmp > /tmp/openscrub-task161/floor.log 2>&1

# Offline sdist→wheel and exact package bytes: both exit0.
. /tmp/openscrub-task161/env.sh
PIP_NO_INDEX=1 PIP_FIND_LINKS=/tmp/openscrub-task620/build-wheelhouse python -m build --outdir /tmp/openscrub-task161/dist > /tmp/openscrub-task161/build.log 2>&1
python /tmp/openscrub-task161/check_packaging.py > /tmp/openscrub-task161/packaging.log 2>&1

# Prepared3.12 has no pip: run existing pip code under the correct3.12.
# No dependencies/network/new toolchain. Both commands exit0.
PYTHONPATH=/tmp/openscrub-baseline-20261116/bootstrap/lib/python3.14/site-packages python -m pip install --no-index --no-deps --upgrade --target /tmp/openscrub-task161/installed/site-packages /tmp/openscrub-task161/dist/openscrub-1.0.96-py3-none-any.whl > /tmp/openscrub-task161/install-runtime.log 2>&1
python /tmp/openscrub-task161/check_installed.py > /tmp/openscrub-task161/installed-startup.log 2>&1

# After source/installed byte and entrypoint interpreter equality checks.
git diff --check
git add openscrub.py tests/test_hdr_chroma_coverage.py pyproject.toml CONTRIBUTING.md README.md
git commit -m "fix: cover every touched HDR silhouette chroma cell"
# Final exact base/head,114 hashes/committed bytes, clean status: exit0.
python /tmp/openscrub-task161/final_check.py > /tmp/openscrub-task161/final-check.log 2>&1
```

## Self-review and limits

Independent task review subsequently approved spec compliance and code quality at the exact committed head. Its sole Minor finding is inherited full-suite optional spaCy and deliberately blocked model/fallback output. These diagnostics are retained with their passing result; they are not new P16A failures. Capturing/asserting expected output in the owning existing tests is a later test-hygiene item, without downloading models or broadening this fix. See `task-161-review.md`. The supervisor verified the clean exact head and accepted the stated CPU/focused-floor and future P16B/C/C01 boundaries; no broader platform certification is implied.

Reviewed the complete product diff and oracle, mask offset/final-cell alignment, effect unchangedness, exact-byte assertions, subprocess/trace restoration and unconditional RED containment. The single owner change is independent of optional plate features and keeps Python>=3.9. No browser change/run, model migration, benchmark, hardware-performance or broad platform claim. Media certification is the bounded actual libx265/CPU path in this environment; other hardware encoders were not newly certified. Tests skip their real media cases when required FFmpeg/ffprobe/libx265 are unavailable; none skipped in these runs. Resource ownership/error-policy work remains separate. No additional neighboring product defect was found or changed. Independent review was completed after this self-review, as recorded above.
