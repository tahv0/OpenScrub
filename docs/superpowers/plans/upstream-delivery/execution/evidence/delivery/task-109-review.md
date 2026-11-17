### Spec Compliance

- ✅ Spec compliant for Task109/N09, exact base `e21ebdf6e3ee46e6c65050dc956a9a3459152269` → head `ded411cbec308333d1416ae3d58b4f6e918d7849`. The complete supplied commit/stat/contextual diff contains four files and exactly two added production lines. `openscrub.py:3975` adds the owned decoder stdout close inside the existing close guard, before the unchanged termination/wait sequence. No default, geometry, encoder, dependency, version, checkpoint, or output-policy change appears in this package.
- ✅ Required actual-boundary coverage is present: `tests/test_hdr_decoder_cleanup.py:146` parameterizes frame-zero cancellation and real encoder-write failure; `:180` calls production `run_render`; `:191` checks both actual production code objects remain in the retained traceback; `:193` checks the original cancellation/error types and real `BrokenPipeError` context. `:130` checks actual wait returns and independent `waitpid` reaping before closed-pipe assertions and before harness cleanup.
- ✅ Packaging/discovery changes stay within the brief: `pyproject.toml:119` includes tests and contributor instructions in the sdist; `CONTRIBUTING.md:25` documents full discovery and the real FFmpeg/POSIX prerequisites. Runtime wheel packaging is unchanged.
- ⚠️ Cannot verify from the diff alone: execution, package contents, installed startup, and committed-byte provenance. Reviewed their retained evidence and checker logic rather than rerunning them: `/tmp/openscrub-task109/red.log`, `green.log`, `focused.log`, `full.log`, `floor.log`, `build.log`, `packaging.json`, `installed-startup.json`, `final-check.log`, and `final-provenance.json`. They support the reported owning RED→GREEN, 137-test full pass, actual Python 3.9 focused pass, sdist→wheel build, installed entrypoint checks, and tested-source/head binding. No unresolved task requirement emerged from those artifacts.

### Strengths

- The fix matches the demonstrated resource boundary without importing the donor's broader lifecycle behavior (`openscrub.py:3970`). Existing primary-error handling remains intact; the real encoder-write case checks the underlying broken pipe and killed task-owned encoder (`tests/test_hdr_decoder_cleanup.py:163`, `:196`).
- Observation effects are explicit. Strong process/pipe owners and the actual exception survive all production-state assertions (`tests/test_hdr_decoder_cleanup.py:1`, `:74`, `:157`, `:202`). The observer's `finally` contains test-owned resources after assertions, with a bounded wait/kill fallback (`:98`). This cleanup is not credited as production cleanup. Baseline research separately explains why retained traceback ownership alone suffices, avoiding a permanent-leak claim.
- The retained RED log fails both owning cases specifically at `tests/test_hdr_decoder_cleanup.py:143`, after their independent reaping checks; success already passes. GREEN records both owned pipes closed and real waits for both children, including success (`/tmp/openscrub-task109/green.log:2`). Full/floor logs carry the native module path and matching candidate engine hash. Intentional baseline RED/setup failures are distinguished from final validation; no unexplained final pytest/build warnings were found. Installed-web HTTP notices follow the explicitly selected plain-HTTP startup command.
- Named concrete risk checked: the pre-encoder trace could have observed only an unchanged decode buffer while different planes were subsequently submitted. One focused inspection of the unchanged render-loop remainder (`openscrub.py:3985`–`:4061`) resolves it: `y/u/v` derive from `buf` at `:3995`, and the actual write is directly `enc.stdin.write(buf.tobytes())` at `:4037`. The trace at `tests/test_hdr_decoder_cleanup.py:220` captures that same buffer on the write line, before submission; this success control subsequently completes. There is no separate-plane serialization after that observation. Thus the exact pre-encoder-byte claim is supported for this fixture without an additional probe.
- Source and lossy output are kept distinct (`tests/test_hdr_decoder_cleanup.py:63`, `:235`, `:243`). `/tmp/openscrub-task109/control_compare.py:27` compares retained baseline/candidate decoded bytes, while `control-comparison.json` records equal output hashes/tags and explicitly unequal source/output bytes. The report discloses the 900/800/300 → 856/560/341 difference and leaves its cause unexplained; this review makes no causal inference.

### Issues

#### Critical (Must Fix)

- None.

#### Important (Should Fix)

- None.

#### Minor (Nice to Have)

- None.

### Cannot verify / scope limits

- Windows, GPU encoders, arbitrary native-call cancellation, and the separate P16C lifecycle/output/geometry boundaries are not established by this Linux CPU fixture. They are explicitly excluded from N09 claims and are not missing task requirements (`task-109-report.md`, “Self-review and limits”).
- Historical execution and clean-commit state are assessed from retained source-bound artifacts, not independently reproduced. No suite, build, media, browser, or Git command was run during review. The supplied diff was read once; no changed file was reread. The single unchanged-code check above addressed the specifically requested encoder-byte observation risk. This is not C01 or whole-branch certification.

### Assessment

**Task quality:** Approved.

**Reasoning:** The minimal owned-pipe close is backed by actual retained-exception failure cases, independent child-reaping checks, and a successful synthetic HDR control. Source/package/floor evidence supports the scoped claims, with no blocking or polish findings identified.

**Counts:** Critical 0; Important 0; Minor 0.
