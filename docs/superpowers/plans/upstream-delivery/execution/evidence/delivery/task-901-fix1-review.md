### Finding Verdicts

- **I1 — direct script startup can invalidate the checked import origin — ADDRESSED.** `docs/superpowers/plans/upstream-delivery/execution/tooling/verification_hook.py:83` adds an actual-resolution finder ahead of the normal finders. For every declared fullname it rechecks the frozen bytes and returns the selected file's spec (`:90`–`:95`), so CPython's subsequent script-directory/cwd insertion cannot override that declared import. The finder is installed before configured application imports and independently in guarded children. `tests/test_verification.py:150`–`:209` adds real file-adapter, file-child and module-child cases in source and installed modes; the cases assert the actual expected file path against conflicting siblings. The twelve retained `fixture-{file,child,module}-{source,installed}{312,39}.log` files show the expected selected paths and VALUE17/module marker. Final RED logs reproduce all six defects per interpreter against the original helper; final GREEN logs pass them against the fix.

- **I2 — prefixed pytest invocation bypasses ownership and serial enforcement — ADDRESSED.** `docs/superpowers/plans/upstream-delivery/execution/tooling/verify.py:164`–`:176` first consumes only the explicitly supported individual `-B`/`-u` prefixes, then recognizes `-m pytest`, rejects worker/root overrides and injects the owned basetemp/cache. Other interpreter prefixes, including combined startup-bypass forms, fail closed before execution. Script/code/module arguments remain workload arguments. `tests/test_verification.py:211` executes real `-B -u -m pytest` and checks both owned directories; `:218` checks five worker/ownership cases through the real builder; `:226` checks six unsupported/combined option cases without launching bypassed interpreters. The narrow contract and examples are explicit in tooling `README.md:51`. The original `-B -m pytest` and `-Es` cases no longer escape these checks.

### New Breakage in the Fix Diff

- None found.
- **Nested-parent boundary checked:** the initial nonexecuting `PathFinder` origin walk remains ahead of the new finder (`verification_hook.py:73`–`:82`). When both parent and leaf are declared, the finder pins the parent's `__init__.py` as a package before the leaf is imported, preserving its selected package location. All four retained configs declare both `openscrub_internal` and `openscrub_internal.job_logs`; this matches the existing requirement to declare all imported product modules, including package/leaf (`README.md:37`). Declaring only a child does not newly promise byte verification of an undeclared parent's initialization. The prior unselected-parent rejection regression remains passing (`final-green312.log:12`, `final-green39.log:12`). No extra execution was needed to resolve this question.

### Out-of-Scope Observations

- **M1 remains deferred and non-blocking:** the unchanged tar-extraction warning from the original review was explicitly excluded from this fix round. No new finding or extraction rerun is required here.
- Root-owned next-real-task adoption remains pending. Neither the original product smoke nor the fix's affected startup executions close D01 or renew the product candidate's historical acceptance.

### Verdict

**Fix round:** All findings addressed, no new Critical/Important breakage.

**SpecCompliance:** Compliant for the Task901 implementation/tooling gate, with the documented caller-owned inventory, supported invocation and Python-hook boundaries.

**TaskQuality:** Approved; deferred Minor M1 remains recorded. D01 completion still requires root's next-real-task adoption result.

**Checks and evidence:** Reviewed fix base `afbd2078a292e4ba2ced55ffdc89fcacaa27502e` → head `081816d93d6aaa18944fc88f251040cf11d4135f`, the same task brief, fix report, and the four-file provided diff once in two nonoverlapping bounded reads. [Commands](task901-fix1-evidence/commands.md) and complete retained test outputs support 25 methods / 16 expected failing assertions on each original-helper snapshot (`final-red312.log:315`, `final-red39.log:278`), then 25/25 passing on each actual interpreter (`final-green312.log:28`, `final-green39.log:28`). Complete GREEN output is clean. Read RED/fixture/runtime logs with compact extraction of repeated identities and diagnostics; an initially truncated evidence view was followed by bounded targeted extraction rather than regenerating results.

**Identity checks:** All 47 files listed in `task901-fix1-evidence/identities.json` match their retained sizes/hashes. Original-helper snapshot bytes match both the fix manifest and original Task901 identity records; its final test bytes match the declared final test SHA `beaed6c5071a7b2fb672b04c60ab8843b906c9d4b82922b4c3048a730ef9d38e`. This independently supports the unchanged-test RED/GREEN comparison without rerunning it.

**Affected integration evidence:** Six exact command arrays retain exit0 (`runtime-commands.json`). Source/default logs identify the immutable product `f44e0b7` and actual Python3.12.16/3.9.25; installed CLI logs retain selected installed origins/defaults (`cli312.log:3`, `cli39.log:3`). Both actual listening HTTP adapters retain empty jobs200, page200/`logStatus`, cleanup/reap0 and final exit0 (`http312.log:5`–`:7`, `http39.log:5`–`:7`), with installed parent/leaf paths also retained in server-child logs. `reused-package-identities.json` exactly preserves the previously reviewed sdist/wheel identities. Reusing those unchanged artifacts while rerunning affected startup gates respects the requested boundary.

**Review limits:** No Git regeneration, native/source/index/branch mutation, suite/build/install/startup rerun, product import, new fixture execution, subagent, publication or timing work occurred during re-review. Read-only stdlib checks inspected retained evidence identities and the original-helper snapshot; only this local review report was written. Findings are scoped to I1/I2 and new breakage in this fix, with M1 and next-task adoption retained outside the fix gate.
