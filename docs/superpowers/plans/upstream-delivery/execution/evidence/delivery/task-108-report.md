Task 108 / N08 is implemented and committed locally. Invalid scan options now receive JSON HTTP 400 before a job is created, copied, registered or queued. Nothing was pushed or published. This initial implementation snapshot is followed by the review-fix report below; the current head is `b26b6685b237ba1c4caffaaefb47b029a3205b51`, pending scoped controller re-review.

Base: `e21ebdf6e3ee46e6c65050dc956a9a3459152269` (the exact reviewed Austin-plus-test-only base).
Head: `e34313e1b136254fb2777cabb385f2097a54935a`.
Branch: `pr/scan-options-validation`.
Worktree: `/home/tahv0/.codex/worktrees/c832/OpenScrub`.
The worktree was clean at dispatch; the head's direct parent is the required base and the worktree is clean after committing.

The shared registered `POST /api/jobs` handler decodes `request.form.get("options", "{}")` once. Only that decode is inside `except json.JSONDecodeError`; a separate `dict` check rejects every decoded non-object, including falsey values. Both rejection paths return `{"error":"Scan options must be a JSON object."}` with status 400. File/job exceptions remain outside this catch. Auth, vault, disk-room hooks and the later upload/server-path admission checks retain their existing order. Multipart parsing/spooling still happens through the framework before this durable-job boundary.

The five changed files are:

- `openscrub_web.py`: the local seven-line route change (six additions, one removal).
- `tests/test_scan_options.py`: 36 actual registered-route cases using synthetic two-frame MJPG input, temporary job storage, real persistence/queue admission and disabled worker/model execution.
- `pyproject.toml`: include `tests` in the sdist and discover both `test_openscrub.py` and `tests`, following the reviewed P06A/P07a pattern.
- `CONTRIBUTING.md` and `README.md`: update suite commands/discovery descriptions.

No report-transaction, learned-model, settings-framework or per-key validation implementation was imported. Python >=3.9, dependency versions and scan defaults are unchanged.

Observed RED and GREEN

The test file was written before the route change. The owning RED run on the untouched product source produced **28 failed, 8 passed in 0.22s**. Empty text, whitespace, `{` and `not-json` produced 500 with zero durable jobs/queue/files on each intake (8 cases). `[]`, `[1]`, `null`, strings including an empty JSON string, integers including zero, a decimal and both booleans produced 200 with a job directory and queue entry on each intake (20 cases). Captured per-case status/admission counts and Flask JSONDecodeError traces are in `/tmp/openscrub-task108/red.log`. The eight object controls already passed. These failures were expected status mismatches, not collection/setup errors.

After the minimal guard, the same focused file produced **36 passed in 0.13s**, recorded in `green.log`. Invalid cases assert exact JSON400, no JOBS registration, an empty actual job listing, zero queued/unfinished work, an empty job store and unchanged source bytes. Valid controls cover omitted options, `{}`, supported settings and a nested unknown key on both multipart upload and server-path forms. They check exact persisted option bytes, input SHA-256 equality, upload ownership versus server input in place, job size, the actual queue tuple, unchanged selected `build_args` defaults/settings, and actual cancel/delete cleanup. No worker was started in these route cases.

Commands for these two runs, from the worktree:

```sh
. /tmp/openscrub-baseline-20261116/env-opencv4.sh
python -m pytest tests/test_scan_options.py -q --basetemp=/tmp/openscrub-task108/red-temp -o cache_dir=/tmp/openscrub-task108/pytest-cache
# Apply the route guard and discovery/documentation updates.
python -m pytest tests/test_scan_options.py -q --basetemp=/tmp/openscrub-task108/green-temp -o cache_dir=/tmp/openscrub-task108/pytest-cache
```

Stabilized verification

The product/tests did not change after focused GREEN. There was one full discovered suite run: **170 passed in 58.09s**, no failures or skips, in `full.log`.

```sh
. /tmp/openscrub-baseline-20261116/env-opencv4.sh
export PYTEST_PLUGINS=task108_isolation
export PYTHONPATH=/home/tahv0/.codex/worktrees/c832/OpenScrub:/tmp/openscrub-task108:$PYTHONPATH
python -m pytest -q --basetemp=/tmp/openscrub-task108/full-temp -o cache_dir=/tmp/openscrub-task108/pytest-cache
```

`/tmp/openscrub-task108/task108_isolation.py` keeps suite runtime under the task directory, reuses a copy of the already available baseline YuNet model and refuses remote model fetching. The existing suite can exercise its established synthetic inference/render tests; the new admission tests and HTTP harness forbid worker/inference execution. There were no model downloads, installations of dependencies or system changes.

The first no-isolation build attempt found no `hatchling` in the OpenCV4 venv (`build.log`). Rather than install anything, task-local `build-tools` symlinks exposed already installed pure Python hatchling/pathspec/trove-classifiers packages from the Python3.9 venv. This successful rerun built **sdist then wheel from that sdist**, with no dependency installation (`build-reused-tools.log`):

```sh
. /tmp/openscrub-baseline-20261116/env-opencv4.sh
export PYTHONPATH=/tmp/openscrub-task108/build-tools:$PYTHONPATH
python -m build --no-isolation --outdir /tmp/openscrub-task108/dist
python /tmp/openscrub-task108/check_package.py
```

`check_package.py` verified exact active bytes for web source, both test locations, pyproject and README inside the sdist; exact guarded web source and unchanged `Requires-Python: >=3.9` inside the wheel. Tests remain sdist-only, following the existing wheel include policy. Member lists and hashes are in `package-evidence.json`. SHA-256: sdist `dfa7ff2d5d2ea2dc52b41b97ba0225958e99d6473232e5e1d05cdbf8e40bc434`; wheel `3b39a81d4eff87bda39da5af89aed0abbcd4c82c994313681cdccbb087aadddf`.

Python3.9 floor verification passed **36/36 in 0.17s**, using CPython3.9.25. `floor-final.log` records explicit assertions that both `openscrub.__file__` and `openscrub_web.__file__` resolve to the active worktree, before pytest runs. Two initial harness attempts failed because the pre-existing Python3.9 audit hook restricted writes to its previous task root, and then because TMPDIR still pointed there. A task-local copy of its hook retains the network/write restrictions with `/tmp/openscrub-task108` as root; task-local TMPDIR/cache/config overrides resolved this without touching installed tools or product source. Failed setup evidence remains in `floor.log` and `floor-reused-tools.log`.

```sh
. /tmp/openscrub-python39-20261117/env.sh
export TMPDIR=/tmp/openscrub-task108/tmp
export XDG_CACHE_HOME=/tmp/openscrub-task108/cache
export XDG_CONFIG_HOME=/tmp/openscrub-task108/config
export PYTHONPATH=/home/tahv0/.codex/worktrees/c832/OpenScrub:/tmp/openscrub-task108:$PYTHONPATH
export PYTEST_PLUGINS=task108_isolation
# Explicit version/import-path assertions, retained in floor-final.log.
python -m pytest tests/test_scan_options.py -q --basetemp=/tmp/openscrub-task108/floor-temp -o cache_dir=/tmp/openscrub-task108/pytest-cache
```

Real HTTP and clean installed startup

The already installed uv tool installed only this built wheel, offline and with `--no-deps`, into a fresh task-local target. Existing environments were not modified:

```sh
. /tmp/openscrub-baseline-20261116/env-opencv4.sh
/tmp/openscrub-baseline-20261116/bootstrap/bin/uv pip install --python /tmp/openscrub-baseline-20261116/venv-opencv4/bin/python --no-deps --offline --target /tmp/openscrub-task108/install/lib/python3.12/site-packages /tmp/openscrub-task108/dist/openscrub-1.0.96-py3-none-any.whl
```

With cwd `/tmp/openscrub-task108` and `PYTHONPATH` preferring that installed target plus the task harness, explicit module provenance assertions passed (`installed-imports.log`). Its generated `bin/openscrub --help` and `bin/openscrub-web --help` both exited 0, retaining their full output. The installed live server also ran its generated web console entry point.

```sh
. /tmp/openscrub-baseline-20261116/env-opencv4.sh
export PYTHONPATH=/tmp/openscrub-task108
export TMPDIR=/tmp/openscrub-task108/tmp
python /tmp/openscrub-task108/http_smoke.py source-http /home/tahv0/.codex/worktrees/c832/OpenScrub 18488
python /tmp/openscrub-task108/http_smoke.py installed-http /tmp/openscrub-task108/install/lib/python3.12/site-packages 18489
```

These bounded loopback checks used the real configured `main()` / cheroot server, HTTP multipart upload, a synthetic token, `--host 127.0.0.1 --http --retain-days 0`, and disabled only worker execution/watchdog restarts. The sandbox's first socket attempt failed with EPERM (`source-http.log`); authorized escalated loopback runs then passed. Source and installed runs each observed `false` → JSON400 with no directory/registration/queue, `{}` → JSON200 with exact `{}` persistence and matching input hash, cancel/delete → 200, and no remaining registered jobs or job-owned files. The existing stale generation-1 queue tuple remained after cancellation/deletion because no worker ran; the harness explicitly drained it at teardown, ending with zero queued/unfinished work. Both servers exited cleanly with SIGINT and status0.

Exact binary multipart requests are retained as `source-http-{invalid,valid}-request.http` and `installed-http-{invalid,valid}-request.http`; full response statuses/headers/bodies are in `source-http-http.json` and `installed-http-http.json`. Server admission snapshots, queue state, import provenance and final cleanup are in each `*-server.log`. Synthetic HTTP fixture SHA-256: `3ee4f9eba8d62e039358afdd8a5cb43d672731236ded9a4977fcb16f5008d694`.

Self-review checked the complete five-file diff against the exact base, validation timing and catch scope, falsey cases, accepted object semantics, test isolation, discovery and archive contents. `git diff --check` and staged diff checks passed. Pytest temporary media trees were removed after verification; logs, harnesses, exact requests, package artifacts and isolated installation remain under `/tmp/openscrub-task108`, with top-level evidence hashes in `evidence-manifest.json`. Only the two designated delivery documents were written in the original checkout. No branch switching, nested agents, external publication or user-data edits occurred.

Practical limits: this validates JSON syntax and object shape only. Existing per-key/unknown-key behavior is preserved, framework upload spooling is outside the durable-job guarantee, and no browser work was needed. These admission probes do not reproduce a worker execution failure or permanent job leak. Later P06 lifecycle integration remains the controller's responsibility; accepted requests still use the same existing `new_job`/`enqueue` interfaces. No unresolved implementation concern was found in self-review.

Review fix round 1 — integer conversion limit

The independent review found a real omission in the initial exception boundary: `json.loads("1" * 4301)` raises plain `ValueError` on the supported runtime, so the original exclusive `JSONDecodeError` catch left this non-object as HTML500. The review is retained in [task-108-review.md](task-108-review.md).

Fix base: `e34313e1b136254fb2777cabb385f2097a54935a`.
Fix head: `b26b6685b237ba1c4caffaaefb47b029a3205b51`.
Original upstream/test base remains `e21ebdf6e3ee46e6c65050dc956a9a3459152269`.
Same branch/worktree; no branch switching or nested agents.

The fix changes only two lines across two files: `openscrub_web.py` now catches `ValueError` around the same single `json.loads` call, and `tests/test_scan_options.py` adds the 4,301-digit integer to its actual multipart invalid matrix. `JSONDecodeError` subclasses `ValueError`, so ordinary malformed inputs remain covered. File/job work is still outside the try block; the explicit dict check, accepted object behavior and all defaults are unchanged. No per-key/dependency/no-op changes were added.

Before changing the catch, the added regression was run against the original product head on Python3.12.16:

```sh
. /tmp/openscrub-baseline-20261116/env-opencv4.sh
export PYTEST_PLUGINS=task108_isolation
export PYTHONPATH=/home/tahv0/.codex/worktrees/c832/OpenScrub:/tmp/openscrub-task108:$PYTHONPATH
export TMPDIR=/tmp/openscrub-task108/tmp
python -m pytest tests/test_scan_options.py -q -k integer-over-runtime-limit --basetemp=/tmp/openscrub-task108/fix1-red-temp -o cache_dir=/tmp/openscrub-task108/pytest-cache
```

Observed output (`fix1-red.log`): both `integer-over-runtime-limit-upload` and `integer-over-runtime-limit-server-path` failed at expected status400 versus actual500; Flask logged `ValueError: Exceeds the limit (4300 digits) for integer string conversion: value has 4301 digits`. Each had zero registered/queued jobs and zero job directories. Result: **2 failed, 36 deselected in 0.07s**.

After the narrow correction, covering Python3.12 verification used the same environment block plus these exact commands:

```sh
python -B -c 'import pathlib,sys,openscrub,openscrub_web; root=pathlib.Path("/home/tahv0/.codex/worktrees/c832/OpenScrub"); assert sys.version_info[:2] == (3,12); assert pathlib.Path(openscrub.__file__).resolve() == root/"openscrub.py"; assert pathlib.Path(openscrub_web.__file__).resolve() == root/"openscrub_web.py"; print(sys.version); print(openscrub.__file__); print(openscrub_web.__file__)'
python -m pytest tests/test_scan_options.py -q --basetemp=/tmp/openscrub-task108/fix1-green-temp -o cache_dir=/tmp/openscrub-task108/pytest-cache
```

Observed output in `fix1-green312.log`: Python **3.12.16**, both module paths in the active worktree, **38 passed in 0.14s**. The complete matrix includes both new oversized integer requests and all original malformed/non-object/object controls.

Covering Python3.9 verification:

```sh
. /tmp/openscrub-python39-20261117/env.sh
export TMPDIR=/tmp/openscrub-task108/tmp
export XDG_CACHE_HOME=/tmp/openscrub-task108/cache
export XDG_CONFIG_HOME=/tmp/openscrub-task108/config
export PYTHONPATH=/home/tahv0/.codex/worktrees/c832/OpenScrub:/tmp/openscrub-task108:$PYTHONPATH
export PYTEST_PLUGINS=task108_isolation
python -B -c 'import pathlib,sys,openscrub,openscrub_web; root=pathlib.Path("/home/tahv0/.codex/worktrees/c832/OpenScrub"); assert sys.version_info[:2] == (3,9); assert pathlib.Path(openscrub.__file__).resolve() == root/"openscrub.py"; assert pathlib.Path(openscrub_web.__file__).resolve() == root/"openscrub_web.py"; print(sys.version); print(openscrub.__file__); print(openscrub_web.__file__)'
python -m pytest tests/test_scan_options.py -q --basetemp=/tmp/openscrub-task108/fix1-floor-temp -o cache_dir=/tmp/openscrub-task108/pytest-cache
```

Observed output in `fix1-green39.log`: Python **3.9.25**, both module paths in the active worktree, **38 passed in 0.19s**. No warnings/failures/skips in either covering run. As requested, the full suite was not repeated. The **170 passed in 58.09s** result remains evidence for original implementation head `e34313e1b136254fb2777cabb385f2097a54935a`, not a claim of a full run at this fix head.

Rebuilt/check-packaged source using the same existing tooling:

```sh
. /tmp/openscrub-baseline-20261116/env-opencv4.sh
export PYTHONPATH=/tmp/openscrub-task108/build-tools:$PYTHONPATH
export TMPDIR=/tmp/openscrub-task108/tmp
python -m build --no-isolation --outdir /tmp/openscrub-task108/fix1-dist
python /tmp/openscrub-task108/fix1-check-package.py
```

`fix1-build.log` records: `Successfully built openscrub-1.0.96.tar.gz and openscrub-1.0.96-py3-none-any.whl`, then `sdist contains exact active source/tests/config; wheel contains exact guarded source; Python >=3.9 preserved`. The wheel was built from the new sdist. `fix1-check-package.py` is the original package checker with only output-directory/evidence-path substitutions. `fix1-package-evidence.json` records member lists and these SHA-256 values: sdist `d370788ea5f0695b68011df438955be3443040b1555116e19bb8a27edb36e221`; wheel `137eb06d21ad0f037467ad51c8df8e6f79eb7878133887b4f988473a4103f2d4`.

Installed only the amended wheel into a fresh task-local target and tested the new payload over real configured HTTP:

```sh
. /tmp/openscrub-baseline-20261116/env-opencv4.sh
/tmp/openscrub-baseline-20261116/bootstrap/bin/uv pip install --python /tmp/openscrub-baseline-20261116/venv-opencv4/bin/python --no-deps --offline --target /tmp/openscrub-task108/fix1-install/lib/python3.12/site-packages /tmp/openscrub-task108/fix1-dist/openscrub-1.0.96-py3-none-any.whl
export PYTHONPATH=/tmp/openscrub-task108
export TMPDIR=/tmp/openscrub-task108/tmp
python /tmp/openscrub-task108/fix1-http-smoke.py fix1-installed-http /tmp/openscrub-task108/fix1-install/lib/python3.12/site-packages 18489
```

Observed output in `fix1-installed-http.log`: `fix1-installed-http multipart 4301-digit integer => JSON400, {} => 200; cancel/delete => 200; store/queue empty; server exit 0`. The actual installed console entrypoint was executed, and module provenance assertions resolve to the new installed target (`fix1-installed-http-server.log`). The invalid request had no registration, queue entry or durable job files. The valid request retained exact options/input, cancel/delete succeeded, the harness drained the stale queue entry at teardown and the server exited0. Exact requests are `fix1-installed-http-{invalid,valid}-request.http`; all response statuses/headers/bodies and cleanup are in `fix1-installed-http-http.json`. The HTTP script is the existing bounded harness with only the invalid payload changed to the 4,301-digit integer and its output label updated. No worker, inference or model download ran in these covering checks.

Self-review confirmed the two-line diff, narrow exception scope and unchanged accepted object behavior; working and staged `git diff --check` passed. Temporary pytest media trees were removed; all fix logs/scripts/packages/installation/HTTP evidence remain under `/tmp/openscrub-task108`. The branch is clean after the fix commit. No unresolved concern remains from this finding; scoped independent re-review is pending. The initial report's broader verification and practical limits remain applicable with the head-specific full-suite distinction above.
