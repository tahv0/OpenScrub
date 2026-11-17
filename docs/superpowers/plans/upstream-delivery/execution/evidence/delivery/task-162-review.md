### Spec Compliance

- ✅ **Spec compliant for P16B.** Reviewed supplied `review-e21ebdf..a3c3193.diff` once, for exact base `e21ebdf6e3ee46e6c65050dc956a9a3459152269` and head `a3c3193e8dff41ec0588e66443398048a5c15ece`. The implementation follows `task-162-brief.md`, including its degeneracy clarification: valid render boxes retain full-box fallback for unusable polygon geometry; SDR and HDR share the decision without changing their existing fill policy (`openscrub.py:3182`, `openscrub.py:3257`, `openscrub.py:3745`).
- ✅ **Validation and geometry bounds:** point shape, finite values, positive finite polygon-box spans, finite mapped coordinates and exact signed-int32 local bounds precede conversion. Integer noncollinearity rejects repeated/collinear/quantized-line contours while allowing the zero-signed-area bowtie. Out-of-normalized-range coordinates remain legal, including the explicit large-but-representable control (`openscrub.py:3193`, `openscrub.py:3203`, `openscrub.py:3212`, `openscrub.py:3217`, `openscrub.py:3221`; `tests/test_polygon_fallback.py:100`, `tests/test_polygon_fallback.py:114`).
- ✅ **Known-region fallback:** both owners pass the original region and requested mode to the existing full-box renderer when the helper returns `None`; clipped-empty render intersections still return normally. The regression oracle compares whole output arrays with the real full-box leaf for both paths, every supported mode, ordinary and partly out-of-frame regions, plus invalid polygon boxes with separate valid render boxes (`openscrub.py:3254`, `openscrub.py:3259`, `openscrub.py:3742`, `openscrub.py:3747`; `tests/test_polygon_fallback.py:75`, `tests/test_polygon_fallback.py:90`, `tests/test_polygon_fallback.py:139`).
- ✅ **Local exception boundary:** allocation is outside the conversion catch, only the specified geometry OpenCV codes fall back, and other native errors propagate. Controlled tests distinguish geometry fallback from `MemoryError`, unrelated `RuntimeError`, and `StsNoMem` propagation (`openscrub.py:3191`, `openscrub.py:3230`; `tests/test_polygon_fallback.py:155`, `tests/test_polygon_fallback.py:172`).
- ✅ **Scope and delivery:** no schema, model, dependency, arbitrary coordinate cap, whole-frame mask, compound holes or mask padding policy was introduced. The two non-engine changes make the new test directory discoverable in contributor instructions and distributable in the sdist (`CONTRIBUTING.md:25`, `pyproject.toml:119`). P16A/N09 and invalid primary-box/output-publication work remain outside this candidate.
- ⚠️ **Cannot verify from the diff alone:** native Git identity/cleanliness, unrelated AST/default preservation, package byte binding, installed startup and the actual Python 3.9 runtime. Supervisor cleanliness confirmation and retained evidence support these claims: `/tmp/openscrub-task162/final-provenance.json:1`, `final_check.py:17`, `packaging.json:1`, `installed-startup.json:1`, `floor.log:1` and `floor.log:62`. No Git commands, suite reruns or builds were executed by this review.
- ⚠️ **Limits:** CPU synthetic Linux coverage does not certify every encoder/platform/native error. The media evidence exercises ordinary `load_report` followed by real `render`/`render_hdr`; it is not complete `run_render` integration. Primary cbox repair, arbitrary malformed report-container admission and production failure/publication lifecycle are not established by this task (`tests/test_polygon_fallback.py:273`; `task-162-report.md`, “Actual media versus controlled execution” and “Self-review and limits”).

### Strengths

- **Small shared owner:** one local mask helper removes duplicated raster decisions, while full-box fills, dilation and the remaining SDR/HDR pipelines remain with their existing owners (`openscrub.py:3182`, `openscrub.py:3257`, `openscrub.py:3745`). The geometric test uses Python integer cross products, avoiding signed-area cancellation and fixed-width overflow (`openscrub.py:3221`).
- **Behavioral oracles:** the direct tests compare actual full-box output across all four modes and protect unrelated pixels through whole-array equality. Literal contour tables and explicit concave/bowtie checks prevent the new validation from widening supported masks (`tests/test_polygon_fallback.py:75`, `tests/test_polygon_fallback.py:114`).
- **Meaningful real media observations:** tests load ordinary reports, use real subprocesses and copy the exact frame/buffer immediately before the real encoder write. Exact pre-encode coverage is asserted separately from decoded lossy-output equivalence; two frames and usable-mask distinction are required (`tests/test_polygon_fallback.py:208`, `tests/test_polygon_fallback.py:273`, `tests/test_polygon_fallback.py:293`). Harness cleanup restores tracing, releases captures and stops/closes/waits real children in `finally`; it is correctly described as test containment (`tests/test_polygon_fallback.py:249`).
- **Baseline compatibility evidence:** the retained comparison script imports separate original/current modules, exercises 96 direct controls and eight actual-media controls, and checks pre-encode and decoded bytes separately (`/tmp/openscrub-task162/control_compare.py:23`, `control_compare.py:36`, `control_compare.py:56`, `control_compare.py:65`; `control-comparison.log:25`, `control-comparison.json:1`).
- **Traceable chronology:** original 520-case RED, corrected exception replay and subsequent container failures are distinguished: `red-final.log:20691` reports 336 failed/184 passed; `red-exception.log:245` reports 6 failed/6 passed/520 deselected; `red-container.log:597` reports 16 failed/72 passed/460 deselected. Final stable logs report 556 focused passes, 682 discovered-suite passes and 556 Python 3.9 focused passes (`focused-stable.log:62`, `full.log:121`, `floor.log:62`). These are inspected retained results, not reviewer reruns.

### Issues

#### Critical (Must Fix)

- None found.

#### Important (Should Fix)

- None found.

#### Minor (Nice to Have)

- **Inherited test-output hygiene, nonblocking for P16B:** `/tmp/openscrub-task162/full.log:2` and subsequent optional-model/GPU/tracker/backend messages are noisy even though the suite passes (`full.log:121`). The report explicitly dispositions these inherited diagnostics and blocked-download fallbacks; they do not demonstrate a new polygon regression. Preserve that disposition and address expected diagnostic capture in the later owning-test hygiene work, without downloading models or expanding this candidate.

### Assessment

**Task quality: Approved.**

**Reasoning:** The narrow helper enforces safe geometry conversion and equivalent SDR/HDR fallback while preserving supported usable contours. Direct full-box oracles, real pre-encoder observations, baseline controls and retained source/package evidence support the task-scoped acceptance; no blocking defect was found.

**Focused checks beyond diff:** Named risk 1 was that unchanged report/render call sites could discard or bypass the tested malformed point data; one AST-selected inspection of `load_report:6385`, `render:4276` and `render_hdr:4039` confirmed report polygon rehydration and the actual leaf dispatch. Named risk 2 was that the tracing observer might capture a value other than the real encoder argument; one focused inspection confirmed `render:4307` writes `frame.tobytes()` and `render_hdr:4072` writes `buf.tobytes()`, exactly the observer's copied locals. Artifact-only checks inspected the retained comparison script, raw summary logs, provenance, package and startup JSON, and environment/final-check scripts. No focused test was needed: those inspections resolved the concrete doubts without repeating successful execution.
