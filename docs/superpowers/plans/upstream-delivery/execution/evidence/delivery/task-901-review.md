### Spec Compliance

- ❌ Issues found: exact source assertions do not survive ordinary direct-script startup (I1), and ordinary interpreter options bypass serial pytest/root ownership enforcement (I2). These affect binding requirements 3–4 and must be fixed before adoption.
- ✅ The five-file change otherwise implements the requested local stdlib helper, explicit frozen source/environment inputs, offline sdist → extracted source → wheel → installed target, caller-owned inventories, Python floor, output persistence, and documented containment/adoption limits. References: `verify.py:38`, `verify.py:91`, `verify.py:169`, tooling `README.md:31` and `README.md:77` (paths below).
- ⚠️ Next-real-candidate adoption remains explicitly root-owned and pending; it is not a missing implementation result. The product smoke establishes this tooling boundary, not renewed product acceptance. No benchmark or timing claim was evaluated.

### Strengths

- `docs/superpowers/plans/upstream-delivery/execution/tooling/verify.py:38`: source policy, caller-frozen hashes, actual interpreter/version, prerequisites and actual scratch headroom are checked explicitly; export-marker provenance is accurately limited in the usage document.
- `docs/superpowers/plans/upstream-delivery/execution/tooling/verify.py:91`: exclusive scratch lock and nonreusable run directories preserve prior output; `tests/test_verification.py:79` and `:172` exercise duplicate runs and existing-owner preservation.
- `docs/superpowers/plans/upstream-delivery/execution/tooling/sitecustomize.py:4` and `verification_hook.py:68`: startup fails closed, and nested origin inspection avoids executing an unselected parent. `tests/test_verification.py:162` covers the discovered parent-import regression.
- `docs/superpowers/plans/upstream-delivery/execution/tooling/verify.py:148` and `tests/test_verification.py:90`: logs are owned before execution, and actual success/exit7 child paths retain both streams. This directly addresses the prior source-found result-directory defect without repeating a workload matrix.
- `docs/superpowers/plans/upstream-delivery/execution/tooling/verify.py:179`: wheel input is the extracted sdist; selected archive/extracted/wheel bytes and exact Python floor are checked. `task901-evidence/package312-final.log:2`, `:12`, `:20`, `:26`, `:328` and `:332` retain offline build/install, installed defaults, generated CLI, actual listening HTTP and cleanup. Artifact hashes match `task-1203-fix1-report.md:35` and `:36` exactly.
- `task901-evidence/green312-final.log:19` and `green39-final.log:19`: retained final suites report 16 passing tests each with clean unittest output. Final source/floor and installed-floor logs identify actual 3.12.16/3.9.25 executables and source/default distinctions. The task-specific adapter owns server ports and reaping (`task901-evidence/listening_smoke.py:25`).

### Issues

#### Critical (Must Fix)

- None found.

#### Important (Should Fix)

- **I1 — direct script startup can invalidate the checked import origin.** `docs/superpowers/plans/upstream-delivery/execution/tooling/verification_hook.py:63`–`:81` validates `PathFinder` origins during `sitecustomize`, while `verify.py:166` launches arbitrary Python script paths directly. CPython subsequently prepends the script directory to `sys.path`. An ordinary adapter with a sibling module can therefore import different bytes after the guard has printed the selected source as active; this needs no environment change, explicit `sys.path` edit or native escape. A focused guarded fixture reproduced exit0 with `ACTIVE_SOURCE` naming frozen `source/sample.py` (VALUE17), followed by the adapter importing `adapter/sample.py` (VALUE99). Raw transcript: [script-origin-transcript.log](task901-review-evidence/script-origin-transcript.log), especially lines 3–5. Fix the execution/import contract so the selected origins remain authoritative when the script/module actually executes, including installed mode and Python3.9. Add a real file-based adapter/child regression with a conflicting sibling; existing direct-child coverage uses `-c` (`tests/test_verification.py:115`) and misses this startup ordering.

- **I2 — prefixed pytest invocation bypasses ownership and serial enforcement.** `docs/superpowers/plans/upstream-delivery/execution/tooling/verify.py:163` recognizes pytest only when the first two arguments are exactly `-m pytest`. The normal command `run -- -B -m pytest ...` therefore receives no unique `--basetemp`/cache injection and skips rejection of `-n`, `--numprocesses`, `--dist` and ownership overrides. A [pure argument probe](task901-review-evidence/argument-probe.log) confirmed `['-B', '-m', 'pytest', 'fixture.py', '-n', '2']` is returned unchanged. This violates the required serial pytest and per-invocation root contract even for cooperative callers using the ordinary no-bytecode flag. Parse/validate the interpreter prefix before identifying pytest, or reject unsupported prefixes explicitly; add positive prefixed-pytest and negative worker/ownership cases. The same token-only parser also accepts combined startup-bypass options such as `-Es`; assess that while correcting the interpreter-prefix handling rather than claiming complete flag rejection.

#### Minor (Nice to Have)

- **M1 — successful package output contains an extraction deprecation warning.** `docs/superpowers/plans/upstream-delivery/execution/tooling/verify.py:191`; owning output `task901-evidence/package312-final.log:10` emits `DeprecationWarning` for implicit tar extraction filtering. The preceding explicit member validation is useful, but choose an explicit compatible extraction policy (feature-detected where necessary for supported Python versions) so successful validation output is clean and the intended policy remains stable across Python versions.

### Assessment

**Task quality:** Needs fixes.

**Reasoning:** The change is focused, understandable and backed by meaningful retained failure/success evidence, but the launcher currently permits false source evidence for direct scripts and misses pytest ownership enforcement for a normal command form. Fix these two boundary defects before next-task adoption; retain the declared Python-hook and adapter-owned cleanup limits.

**Review checks and limitations:** Reviewed base `04677434d43d8acc54aebdcf9073db4d234f1ceb` to head `afbd2078a292e4ba2ced55ffdc89fcacaa27502e` using the provided diff once, task brief/report, D01/live-handoff constraints and linked owning evidence. The first batched tool response truncated the README/tests/startup-hook portions; only those missing changed-file sections were read separately to assess fail-closed behavior and coverage. One later focused AST extraction read `python_command` for the named prefix/ownership doubt. No Git diff regeneration, source/branch/index mutation, suite rerun, build, product import, product smoke or performance work was performed. The only executable check was a tiny dummy-source fixture under the uniquely owned review scratch linked above; the argument probe executed only the extracted stdlib command-construction function and did not launch pytest or a bypassed interpreter. Ordinary Python-hook limitations remain as documented; this review does not certify OS/native containment. Review output is local and unpublished.

**Retained review evidence:** [task901-review-evidence/README.md](task901-review-evidence/README.md) links the compact recipe, raw observations, frozen fixture config and exact helper/source identities. Helper hashes were read only to bind this retained evidence and all match the implementer manifest. Runtime fixture trees were excluded.
