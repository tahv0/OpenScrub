# Task901 fix1 — preserve imports after startup and pytest ownership with flags

**Status:** I1/I2 fixed and self-reviewed; fresh scoped review remains root-owned. Base **`afbd2078a292e4ba2ced55ffdc89fcacaa27502e`** → head **`081816d93d6aaa18944fc88f251040cf11d4135f`**, `tools: preserve selected imports and pytest ownership`, on clean `tools/local-verification`. D01 real-task adoption remains pending. Minor M1 is explicitly deferred.

## Fixes and scope

I1 was reproduced with ordinary file adapters and separate file children: after `sitecustomize` printed the frozen `sample.py` as active, CPython prepended the adapter directory and imported sibling VALUE99 or child sibling VALUE101 instead of selected VALUE17. A module child likewise selected a run-cwd sibling after startup. All six source/installed scenarios reproduced on actual Python3.12 and3.9.

The existing startup origin/hash checks remain. A small task-local import finder now pins each **declared** module to its frozen selected file during actual resolution and rechecks its bytes, so later normal script/cwd insertion cannot shadow it. It is installed in each guarded Python process, including file and module children, before configured application imports. Unrelated dependency imports retain normal behavior. This is an import contract, not a native sandbox or a general task framework.

I2 was reproduced by real `-B -u -m pytest` losing its owned basetemp/cache and by pure command-builder probes accepting worker/ownership overrides and combined `-Es`. The launcher now parses only individual optional `-B`/`-u` prefixes, then identifies the script, `-c` code or `-m` module. Pytest after those prefixes gets the same owned paths and worker/ownership rejection. All other interpreter prefixes, including combined `-Bu`, `-Es`, `-sE`, `-IS`, standalone `-S` and `-X`, are rejected. Workload arguments after script/code/module remain workload arguments. The documented pytest contract is `-m pytest`, optionally prefixed by individual `-B`/`-u`; arbitrary pytest scripts/wrappers are outside that contract.

Four files changed under the assigned native `tooling/`: hook (+14 lines), launcher (net +10), nine additional test methods (+85), and two usage paragraphs. No new support file, general parser, product source change, dependency install, branch switch, nested agent or publication occurred. Python audit/native/fd/environment limits and adapter-owned process cleanup remain as documented.

## RED → GREEN and complete outputs

The final suite has **25 test methods**: the original16 plus nine new methods. The same final test bytes were executed against a task-local snapshot of the original committed helper and against the fix, without changing native branches/source. Snapshot helper hashes are bound to base `afbd207…`; final test SHA is recorded in the evidence identity manifest.

| Gate | Actual3.12.16 | Actual3.9.25 |
| --- | --- | --- |
| Final unchanged-base RED | 25 methods, **16 expected failing assertions** | 25 methods, **16 expected failing assertions** |
| Final fixed GREEN | **25/25 pass**, complete clean unittest output | **25/25 pass**, complete clean unittest output |
| Affected reviewed-source/default preflight | exit0, selected frozen origins/defaults | exit0, selected frozen origins/defaults |
| Existing-target generated CLI with `-B` | exit0, selected installed origins/defaults | exit0, selected installed origins/defaults |
| Existing-target actual listening HTTP adapter | `/api/jobs`200 empty, `/`200 `logStatus`, cleanup/reap0 | same responses, cleanup/reap0 |

The RED failures are six file/child/module source/installed scenarios, one end-to-end prefixed pytest ownership scenario, five worker/ownership subcases, and four previously accepted unsupported-prefix subcases. Two other combined/startup option subcases were already rejected by the old helper. The original16 methods remain passing. Negative worker/bypass cases call the **real command builder** and never launch workers or an interpreter with bypass options. Positive prefixed pytest executes a real isolated fixture and asserts both basetemp and cache ownership. File and module cases assert the **actual expected source/installed file path**, with conflicting siblings retained in fixtures; twelve compact successful child logs retain their output.

Commands and **complete outputs** are under [task901-fix1-evidence](task901-fix1-evidence/README.md): final authoritative `final-red312.log`, `final-red39.log`, `final-green312.log`, `final-green39.log`; I1-only GREEN and intermediate logs; actual file/child/module output; all six startup transcripts and server child logs; exact command arrays/exits; frozen configs and preflight manifests. The shell recipes identify actual interpreter paths and exact test directories. All tooling and runtime checks ran serially. The existing tiny socket test used authorized escalation.

Initial draft tests had two module-fixture newline escaping errors and, separately, over-specific expected diagnostic wording for options already rejected by the old helper. Those drafts are preserved and are **not** counted as meaningful final RED. After correcting the fixtures/behavior assertions, both interpreters showed the actual defects before the implementation change. Module-origin output was then strengthened to show the expected path explicitly; identical final test bytes were verified RED against the isolated base snapshot and GREEN against the final helper. No draft/setup error is labeled a product failure.

## Exact source and reused package boundary

Application source remains immutable reviewed **`f44e0b786ad065010fbfd2b8328350bde44116ec`**, expected base `4670641cb8e53e6daa6f77fb505397bfdb6733b8`, in existing Task901 product export. Full caller configs retain all **125** frozen file hashes. Web SHA **`04af11cce1eaf4be0dc157ba5b4d78783a85bcbbb17596078c75d9df79f46c93`** and private leaf **`63d08c124db019b120bb17efc64706d910f1d831f8ccfd9c1ba124368643d1b8`** are unchanged. The documentation branch was never application runtime source.

Installed startup uses the existing byte-verified `runtime/task901/product-runs/package312-final/site-packages` target. The selected six runtime/private module bytes are checked again for both actual interpreters. The already built artifacts were reread and hashes checked before startup: sdist **569,239 bytes / `a23d7a70fb086ad618e67e4ae31292b8a4954201b75fc2aa0c880969c8db2703`**; wheel **443,575 bytes / `912bd8f54571eb75fb41236ebc247a426d1272bc54fa7f36a46acec470e0997d`**. **No rebuild or reinstall ran**: package bytes/build behavior were unchanged, so the existing exact-byte package evidence is reused while the affected import/startup gates are new executions. These are tooling checks, not renewed product acceptance.

Actual Python paths remain `/tmp/openscrub-baseline-20261116/venv-opencv4/bin/python` (3.12.16) and `/tmp/openscrub-python39-20261117/venv/bin/python` (3.9.25), as captured in new manifests/logs. Prepared libraries/tools/environments are unchanged. All new runtime/snapshot data is under assigned ignored `runtime/task901` (product startup runs specifically `runtime/task901/fix1/runs`); evidence excludes exports, targets and environments. No new model/network download, cache pruning, product-wide/full/browser/media suite, benchmark or timing measurement occurred.

## Self-review and remaining work

Self-review read the four-file diff, checked source/installed pinning in real file/module children on both interpreters, checked prefix separation before pytest ownership, retained existing fail-closed startup/nested-parent behavior, and confirmed the narrow documented invocation contract. `git diff --check` and staged whitespace check passed; final native worktree is clean. Committed bytes and baseline/final test identity matches are in `identities.json`.

No unresolved Important finding is known from this fix. Minor **M1** (explicit compatible tar extraction filter/deprecation output) was deferred by root and is untouched; no extraction gate was rerun. Python-hook limitations, caller-owned declared inventories/provenance, and adapter cleanup limits remain. Root owns fresh scoped re-review, copying/adoption on the next real candidate, and recording D01 completion afterward.
