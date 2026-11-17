# Task1203 fix1: persist portable-runner process output on fresh scratch

**Fix base:** `4670641cb8e53e6daa6f77fb505397bfdb6733b8`, clean on `pr/bounded-browser-logs`. **Fix head:** `f44e0b786ad065010fbfd2b8328350bde44116ec`. Scope is I1 only: `benchmark/browser_logs.py` plus new owning `tests/test_browser_log_benchmark.py`. No branch switch, nested agent, unrelated runtime change, publication or new timing/browser workload occurred.

Independent review found that the portable runner never created `$ROOT/logs`, so normal completion and timeout diagnostics could be masked by `FileNotFoundError`. The previous setup-only check returned before this branch. The runner now calls `log.parent.mkdir(parents=True, exist_ok=True)` inside the configured root, before executing its child. This keeps log-directory ownership beside the output path and protects both existing persistence branches without changing their behavior.

## RED, GREEN and regression boundary

The new three-case regression executes the **real public CLI main**, manifest/source checks, public isolation configuration, synthetic HTTP fixture and final cleanup/hash checks in a fresh isolated process/root per case. It controls only `subprocess.run` at the external comparison-child boundary. Python executable paths stand in for required Node/Chromium tool arguments; **neither tool is launched**. No callback timing batch, browser page or performance data is produced.

Before the controlled child returns or raises, it asserts the process-log parent already exists. This catches both absent creation and incorrect creation after child execution. The cases then verify:

- Success: exit0 and exact persisted stdout **and** stderr.
- Child failure: exit7 preserved, both streams persisted, original stderr reaches the caller.
- Timeout: byte stdout/stderr decode with replacement, the fixed `SUBPROCESS TIMEOUT` diagnostic persists, and the original `subprocess.TimeoutExpired` is propagated rather than masked by a filesystem error.

Actual RED on the fix base: **3 failed in3.43s**, each at `process-log directory must exist before the controlled child executes`, after real source/configuration checks. No import/setup/browser-tool failure was used as RED. The owning test bytes stayed unchanged through RED/native GREEN/floor GREEN.

| Gate | Exact scoped command / result |
| --- | --- |
| Native RED | Source `runtime/task1203/fix1/env.sh`, pin web04af11c…; `python -m pytest tests/test_browser_log_benchmark.py -q --basetemp="$TASK1203_ROOT/red-native" -o cache_dir="$TASK1203_ROOT/cache/pytest-red"` → **3 expected failures /3.43s**. |
| Native GREEN | Same env/source; `python -m pytest tests/test_browser_log_benchmark.py -q --basetemp="$TASK1203_ROOT/green-native" -o cache_dir="$TASK1203_ROOT/cache/pytest-native"` → **3 passed /3.36s**, actual Python3.12.16. |
| Actual floor GREEN | Source `runtime/task1203/fix1/env39.sh`, same pinned web hash; `python -m pytest tests/test_browser_log_benchmark.py -q --basetemp="$TASK1203_ROOT/green39" -o cache_dir="$TASK1203_ROOT/cache/pytest39"` → **3 passed /3.96s**, actual Python3.9.25. |
| Final offline sdist | Prepared backend tools reused read-only; `python -m build --sdist --no-isolation --outdir "$TASK1203_ROOT/dist" "$TASK1203_SOURCE"` → pass. |
| Wheel from sdist | Extract into `$TASK1203_ROOT/extracted`; `python -m build --wheel --no-isolation --outdir "$TASK1203_ROOT/wheel" "$TASK1203_ROOT/extracted/openscrub-1.0.96"` → pass. |
| Exact inclusion | `$TASK1203_ROOT/package_check.py` → **18 required runtime/private/test/recipe/documentation paths** equal native bytes in sdist and extracted tree; wheel runtime/private bytes and Python>=3.9 metadata pass. Wheel is **byte-for-byte identical** to the reviewed candidate's wheel. |

Complete clean GREEN outputs, complete expected RED, package outputs, the six actual persisted process logs and their hashes are under [task1203-fix1-evidence](task1203-fix1-evidence/README.md). No additional failed attempt occurred in this round.

## Exact identities and historical evidence

- Final portable runner SHA-256: **`722c26b00c8934f2e6ec310ba3b3031af58dba92fbe19529614907c9896563db`** (fix-base portable runner43accec…; historical measured runner617b64b… remains unchanged in original evidence).
- New regression SHA-256: **`44d41cc59df60fe4814756016b559e3fc83821134fe17bb37c1729dbea64c3ef`**.
- Runtime unchanged: web **`04af11cce1eaf4be0dc157ba5b4d78783a85bcbbb17596078c75d9df79f46c93`**, leaf **`63d08c124db019b120bb17efc64706d910f1d831f8ccfd9c1ba124368643d1b8`**. Existing browser-owning testdfc32a0…, Node/P12B tests, JS, helper, summary and packaging rules are unchanged against the fix base.
- Final sdist: **569,239 bytes**, SHA-256 **`a23d7a70fb086ad618e67e4ae31292b8a4954201b75fc2aa0c880969c8db2703`**. Includes amended recipe and new test through existing scoped sdist/test inclusion; no packaging-rule change.
- Final wheel: **443,575 bytes**, SHA-256 **`912bd8f54571eb75fb41236ebc247a426d1272bc54fa7f36a46acec470e0997d`**, exactly identical to the original candidate wheel.

Original full250, browser6, floor59, installed54, evaluated JS, listening-server/installed-browser and calibration evidence retain their original source/test/recipe/package identities. They were **not rerun or relabeled as fix1 executions**. This fix supplies native/floor3-case process-output coverage and exact package inclusion only. No real Node comparison, new browser/timing matrix, broad suite, installed startup or unrelated updater/platform gate was run for this delivery-directory change. The supervisor-accepted dense-layout44.8ms/66ms budget exception, initial regressions and native-suspension/platform limitations remain unchanged.

## Isolation and self-review

All fix scratch is under `/home/tahv0/src/OpenScrub/.superpowers/sdd/README/runtime/task1203/fix1`. Sitecustomize/env/floor hooks were copied and retargeted before collection; native/floor/child imports assert selected paths/hashes, including the unchanged private leaf. Every child public runner installs its own configured-root profile/write/network/source protections before product imports, independently of a pytest plugin. Pytest invocations were serial with distinct basetemps. Existing interpreters and cached build tools were read-only; no downloads or user/original-checkout product changes occurred. Initial free-space check was803,652,612,096 bytes.

Self-review verified the two-file scope, pre-child directory creation, fresh-root behavior, success/nonzero/timeout diagnostics and exact archive bytes. There is no new substantive issue. The regression intentionally stubs child execution; it establishes process-output delivery, not benchmark timing or browser correctness. Root owns the same reviewer's scoped fix review; no review/delegation was performed here.
