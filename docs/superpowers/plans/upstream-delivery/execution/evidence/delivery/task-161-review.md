### Spec Compliance

- ✅ **Spec compliant for Task161/P16A.** Reviewed exact base `e21ebdf6e3ee46e6c65050dc956a9a3459152269` to head `0c648c2e7d3e40304dce9ae878d14709966b1fe1` using the supplied diff package once. The implementation changes only the existing HDR silhouette owner's mask mapping: global origin offsets, ceil-ended chroma extents, zero padding, and 2×2 max select precisely the union of selected luma pixels (`openscrub.py:3716–3725`). The clipped U/V ROI receives the corresponding leading submask (`openscrub.py:3746–3753`).
- ✅ **Luma, effects, defaults and geometry preserved.** Mask creation/dilation precedes the new mapping unchanged; the per-plane box/inpaint/mosaic/blur effect calculations remain unchanged, and luma receives the original mask (`openscrub.py:3701–3714`, `3727–3753`). No new helper, field, schema, dependency, version, face/rectangle path, SDR renderer, or optional plate behavior appears in the diff. The independent base/candidate source-boundary assertion and 348 luma, 348 SDR silhouette and 56 HDR face/rectangle comparisons support preservation (`/tmp/openscrub-task161/control_compare.py:29–61`; `control-comparison.json:2–5`).
- ✅ **Independent coverage oracle and meaningful modes.** The oracle rasterizes literal local integer vertices, expands padding through coordinate neighborhoods, and enumerates selected global coordinates into `(row//2, col//2)` rather than reproducing the implementation's aligned reduction (`tests/test_hdr_chroma_coverage.py:40–63`). The 29 geometries cover four origin parities, odd ROI sizes, thin/diagonal/sparse masks and all clipped corners, multiplied by padding 0/1/3 and all four modes (`:23–35`, `:79–104`). Exact whole-plane expected arrays include unrelated samples; seeded contrast plus the visibility assertion prevents vacuous coverage checks (`:71–104`). Literal sparse cells and the baseline-passing filled-square control are retained (`:107–119`).
- ✅ **Actual report/render/encoder evidence.** A synthetic lossless 10-bit PQ/BT.2020 source is independently decoded back to its raw bytes (`tests/test_hdr_chroma_coverage.py:139–158`). Ordinary `load_report` and actual `run_render` feed real HDR/SDR render owners (`:218–233`, `:252–300`). The trace copies the actual pre-write buffer without replacing write operations or bytes (`:162–198`); exact whole-frame HDR assertions use hand-derived luma and U/V cells (`:263–271`), while ffprobe checks frame count, format and colour signalling (`:272–278`). The SDR control uses actual OpenCV decode (`:281–300`).
- ✅ **RED/GREEN and actual preencoder distinction established.** Exact base source is identified in `red.log:1`; final baseline replay reports 161 failures/191 passes at `red.log:7793`, including the actual sparse HDR case. Candidate source is identified in `green.log:1`, with 352 passes at `:17`. Retained controls show the required U cell changing from `[800,512]` to `[512,512]`, V from `[300,512]` to `[512,512]`, and total changed samples from 5 to 7 (`control-comparison.json:72–106`). SDR and unmasked HDR preencoder/decoded bytes match base (`:7–48`); lossy sparse decoded output is explicitly excluded as a mask oracle (`:50–71`).
- ✅ **Harness containment covers the exercised RED/GREEN renders.** Normal child return codes, closed pipe streams and POSIX reaping are asserted before the exact-mask assertion (`tests/test_hdr_chroma_coverage.py:236–248`, `:258–271`); unconditional trace restoration and child/stream/tempfile cleanup enclose failures (`:191–215`). Actual RED and GREEN logs retain successful child observations (`red.log:6`, `green.log:6`, `:11`, `:15`). This does not imply broader production exception cleanup.
- ✅ **Delivery evidence retained.** Full discovered run: 486 passed (`full.log:68`). Actual Python 3.9.25 focused run: 360 passed/126 deselected with matching native engine hash (`floor.log:1`, `:21`). Offline sdist→wheel build succeeded (`build.log:1–16`), package source/test/guidance byte checks passed (`packaging.json:2–7`), and installed CLI/web startup passed from installed paths (`installed-startup.json:2–11`). The small `pyproject.toml:119–120`, `CONTRIBUTING.md:25–30` and `README.md:603` changes are the requested test discovery/distribution guidance.

### Strengths

- The fix stays inside the owning function and makes the global grid alignment explicit; it preserves the existing effect code and uses the original luma mask directly (`openscrub.py:3716–3753`).
- The oracle is structurally independent of the new reduction, and exact full-plane assertions detect both omitted and extra chroma cells (`tests/test_hdr_chroma_coverage.py:40–63`, `:101–104`). Tests require meaningful contrast for every supported mode rather than merely calling each mode (`:95–100`).
- Media evidence checks real report loading, real rendering and real libx265 input; it separates exact preencoder membership from lossy output observations (`tests/test_hdr_chroma_coverage.py:218–278`; `control-comparison.json:50–106`).
- Evidence binds the observed native source, Python floor, built sources and final commit. Read-only SHA256 checks during this review independently matched the native engine/test and saved sparse RED/GREEN preencoder bytes to the recorded hashes (`final-provenance.json:2–15`; `packaging.json:6–7`; `control-comparison.json:53–55`).

### Issues

#### Critical (Must Fix)

- None found in the P16A change (`openscrub.py:3716–3753`; `tests/test_hdr_chroma_coverage.py:40–300`).

#### Important (Should Fix)

- None found. The independent oracle, exact baseline regression, preservation comparisons and actual preencoder observations support the narrow contract (`tests/test_hdr_chroma_coverage.py:40–119`, `:252–300`; `control-comparison.json:2–106`).

#### Minor (Nice to Have)

- **Retained full-suite output is not pristine.** `/tmp/openscrub-task161/full.log:2–5` includes optional spaCy warnings; `:8–9`, `:27–28`, `:37–38` retain deliberately blocked VitTrack fetching/fallback diagnostics, alongside detector fallback/error-path output at `:16` and `:42–49`. These are outside the changed owner and do not contradict the 486-pass result, but they make unexpected diagnostics harder to distinguish. In a separate test-hygiene change, capture/assert expected warning and fallback output in the owning existing tests, or explicitly retain its disposition with the validation result. No model download, dependency change or extra broad validation is warranted for P16A.

### Cannot verify items and review bounds

- ⚠️ The diff alone does not prove the reported native runtime, packaging or media outcomes. This review inspected the retained logs, comparison script/results, package/startup/provenance artifacts and native/saved-byte hashes cited above; it did not repeat any successful suite or build. The frozen checkout/head identity was supplied by the supervisor (`final-provenance.json:2–8`).
- ⚠️ Certification remains the exercised CPU/libx265 environment and focused actual Python 3.9 path (`final-provenance.json:9–13`; `floor.log:1`, `:21`). Other platforms/encoders, broad exception lifecycle, malformed geometry and whole-branch/C01 review are outside this gate, as the binding brief requires (`task-161-brief.md`, implementation contract 2/4 and evidence section).
- **Focused outside-diff inspection 1:** The diff begins mid-owner, so I checked only the omitted initialization/clipping prefix (`openscrub.py:3684–3710`) to resolve the concrete risk of interpreting the new offset relative to unclipped coordinates. `x1i/y1i` are clipped nonnegative frame coordinates, and `rw/rh` describe that clipped mask; the new alignment uses the correct origin.
- **Focused outside-diff inspection 2:** To resolve whether trace observations truly match encoder input, I checked the exact unchanged HDR and SDR write sites (`openscrub.py:4041`, `:4276`). They write `buf.tobytes()` and `frame.tobytes()` respectively, matching the observer's copied locals (`tests/test_hdr_chroma_coverage.py:183–188`).
- **Checks performed:** Read-only review of the supplied diff and retained evidence; SHA256 inspection only. No Git command, checkout/index/branch mutation, implementation edit, suite rerun, model/dependency download, publication or subagent was performed. This requested SDD review file is the sole written artifact.

### Assessment

**Task quality: Approved.**

**Reasoning:** The bounded mapping computes the required global luma-to-chroma union while leaving luma, effect calculations and neighboring owners intact. Independent exact oracles and actual preencoder RED/GREEN evidence support the fix; the minor inherited validation-log noise does not block this task.
