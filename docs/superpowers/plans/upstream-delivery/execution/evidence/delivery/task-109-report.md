# Task109 / N09: deterministic HDR decoder-pipe closure

Date: 2026-11-17. Implemented and self-reviewed; independent review belongs to the supervisor. No publication.

- Exact base: `e21ebdf6e3ee46e6c65050dc956a9a3459152269` (Austin plus the test-only handoff correction).
- Exact head: `ded411cbec308333d1416ae3d58b4f6e918d7849`.
- Commit: `fix: close HDR decoder pipe during partial cleanup`.
- Native branch/worktree: `pr/hdr-decoder-cleanup`, `/home/tahv0/.codex/worktrees/c832/OpenScrub`.
- Artifacts: `/tmp/openscrub-task109`; final native status is clean. This report and `task-109-pr.md` are the requested SDD handoff documents, outside the product commit.

## What, why, and when

`render_hdr.cleanup_partial` now explicitly closes its owned decoder stdout in the existing decoder branch, alongside the existing encoder stdin close, before its existing terminate/wait sequence. Production change: exactly two added lines (`else:` / `pr.stdout.close()`), within the existing close exception guard. Existing commands, default quality/encoder settings, checkpoints, output paths/deletion and success/error branches are byte-for-byte unchanged outside those lines.

The owning trigger is an ordinary caller retaining the exception and traceback after actual `run_render` → actual `render_hdr` frame-zero callback cancellation or real first encoder-write failure. The old cleanup already reaped both children, but decoder stdout remained open while the traceback retained renderer locals. Explicit close makes the descriptor state deterministic while retained owners remain live. This does not establish a permanent leak or a cancellation-speed/native-interruption improvement.

The bounded baseline research and actual tiny-fixture recipe were read before implementation: `hdr-decoder-cleanup-baseline-research.md` and `hdr-decoder-cleanup-baseline-evidence/probe_cleanup.py`. The donor reference was `08f432b6160d2fc22e51456020df929de6717e16`, used only to understand the generic two-line close. No donor module/function or section behavior was transplanted. No assembled-application source was used.

## Changed files

| File | Purpose |
| --- | --- |
| `openscrub.py` | Two-line decoder stdout close in existing HDR partial cleanup. |
| `tests/test_hdr_decoder_cleanup.py` | Three actual-boundary cases: frame-zero cancellation, actual encoder-child death causing real first write failure, and real tiny PQ success control. |
| `pyproject.toml` | Include `tests/` and contributor instructions in the sdist. Dependencies, backend/version constraints, wheel inclusion and application version unchanged. |
| `CONTRIBUTING.md` | Run full discovery (`python -m pytest -q`), document synthetic FFmpeg/libx265 regressions and POSIX/waitid observation requirements. No CI/build overhaul. |

## Provenance and runtime isolation

Every pytest command ran from the native cwd. `/tmp/openscrub-task109/task109_isolation.py` asserts the actual imported paths of `openscrub`, `openscrub_web`, and `zones_ui`, and both `run_render`/`render_hdr` code filenames, before running tests. This avoids original-cwd import shadowing; PYTHONPATH alone is not the source gate. Every log starts with interpreter version and actual module path/SHA256 data.

- Baseline engine SHA256 at RED: `0e4f0f9a7846080f591038d021aaf3ca6f01201d83ac32bbdc273f53d5067ee7`.
- Candidate/committed engine SHA256: `dbba61eebd93d17adae37d8f1ece2d8a29170d2534734010b751d904076fc480`.
- Committed test SHA256: `5422b3e78c8d048e93c86d82c5881e2e10296078f7c3f74f6064501d380c5f36`.
- Unchanged web SHA256: `9835e1137abee62c0a78e2669ed8bae7059e36bf4bed9f5c7a44f0eb8b40ed3a`.
- Unchanged zones SHA256: `a1cdb4e5be90cf2e4282268f7c2499ed2b00879a034f68235d35d56cd74752f7`.

Main runtime: existing Python 3.12.16, OpenCV 4.14.0, NumPy 2.5.5, FFmpeg/ffprobe 8.0.1-3ubuntu2, Linux WSL2 x86_64 CPU. Floor runtime: existing actual Python 3.9.25, executing the real cases with the same native import assertions. Runtime/library paths and build hashes are in `final-provenance.json`; all 114 tracked/new tested file hashes are in `tested-source-sha256.json`. Before commit and after commit, every manifest entry matched source bytes; after commit each also matched `git show <head>:<file>`. `HEAD^` equals the exact base.

Task-local TMPDIR/cache/config/profile/app/model directories were used. `env.sh`, `floor-env.sh`, `sitecustomize.py`, and `task109_isolation.py` are retained in the artifact directory. The site hook redirects profile expansion and blocks external Python socket connections and writes outside task artifacts. Native writes/commits and commands requiring loopback used authorized `require_escalated`. No environment migration, new tools/dependencies/models, or external download occurred. The unchanged full suite reused only the existing YuNet file, copied to task-local runtime/models after verifying against the existing engine pin `8f2383e4dd3cfbb4553ea8718107fc0423210dc964f9f4280604804ed2552fa4`; source and pin are recorded in `model-reuse.txt`. New cleanup cases require no inference/models.

## Actual boundary and observer effects

Tests invoke the complete imported production `run_render` and its actual `render_hdr`; no extracted renderer, substitute stream or raised fake write error is used. The three-frame 64×64,3 fps PQ/BT.2020 ten-bit fixture has constant native Y/U/V 900/800/300 planes, encoded losslessly by actual libx265. Synthetic state has no detections, zero motion/bands, box mode, pad 0, libx265, default archival quality and no report/audio.

A Popen subclass leaves commands, IO and return values intact and records actual wait returns. The test deliberately retains strong process/pipe owners and the actual raised exception/traceback during assertions; those references are explicit diagnostic observation effects. Tracebacks must contain the real production `run_render` and `render_hdr` code objects. Each decoder and encoder must have recorded waits and a non-None returncode; a separate `os.waitpid(pid, WNOHANG)` must raise `ChildProcessError`, proving the child is already reaped before any harness cleanup. Both pipe objects must report `closed` while all retained owners remain live.

Cancellation is the existing first callback checkpoint at frame 0, preserving exact `PipelineCancelled`. Encoder failure kills only the task's own actual encoder child at that same checkpoint, then uses `waitid(WNOWAIT|WNOHANG)` to observe exit without reaping; the real first `enc.stdin.write` raises `BrokenPipeError`. Production preserves its `RuntimeError` naming HDR encode and exit −9, with the actual `BrokenPipeError` as context. No alternate error is substituted by the new close. Both partial outputs remain absent as before.

The observer context has unconditional `finally` containment after assertions, including failures: close remaining handles, terminate/wait live children, kill/wait only if the harness wait times out, and close retained temporary stderr files. Harness cleanup is not credited as production cleanup. Temporary stderr lifetime is explicitly outside N09. The earlier baseline weak-reference research establishes caller traceback retention alone; this regression deliberately uses strong diagnostic owners to make the deterministic close requirement observable without GC.

## RED → GREEN and controls

| Check | Result / retained evidence |
| --- | --- |
| Baseline owning RED, new file | **2 failed, 1 passed**,0.70s; both failures are exactly `assert dec.stdout.closed`; `red.log`. |
| Candidate owning GREEN | **3 passed**,0.69s; `green.log`. |
| Relevant actual HDR/render/codec3.12 | **11 passed, 126 deselected**,16.63s; `focused.log`. |
| Full discovered suite, once at stable bytes | **137 passed**,76.70s; `full.log`. |
| Actual Python 3.9.25 focused cases | **11 passed, 126 deselected**,17.39s; `floor.log`, actual source paths/SHA asserted. |
| Offline full sdist→wheel | Passed; `build.log`. |
| Exact package/source/test contents and3.9 grammar | Passed; `packaging.log` / `packaging.json`. Grammar is supplementary to actual3.9 execution. |
| Correct-runtime installed CLI/web startup | Passed; `install-runtime.log`, `installed-startup.log` / `.json`, `installed-web.log`. |
| Exact before/after tiny-PQ success | Passed; `control-comparison.log` / `.json`, `red-decoded.yuv`, `green-decoded.yuv`. |
| Final commit/manifest/clean status/diff check | Passed; `final-check.log`, `final-provenance.json`. |

Owning RED retained observations: cancellation decoder pid 1271039 waited rc 255 with stdout open; encoder pid 1271054 waited rc −15 with stdin closed. Encoder-write case decoder pid 1271187 waited rc 255 with stdout open; encoder pid 1271201 waited rc −9 twice (write-error handling and cleanup) with stdin closed. Both pairs passed the independent reaping assertions before failing the decoder-close assertion. Successful baseline control had both waits rc 0 and both pipes closed.

Owning GREEN retained observations: cancellation decoder pid 1272237 waited rc 255 and encoder pid 1272245 waited rc −15, both pipes closed; encoder-write decoder pid 1272385 waited rc 255, encoder pid 1272400 waited rc −9 twice, both pipes closed. Success decoder/encoder pids 1272533/1272541 waited rc 0 with pipes closed. These statuses describe these bounded runs, not required cross-platform decoder termination codes. The successful encoder remains rc 0. Actual3.9 repeated both failure cases and success, with both pipes closed/reaped (`floor.log`).

The only setup failure was the first script-creation shell trying unqualified `python` before sourcing the existing environment (`python: command not found`, exit 127). That shell created task-local helper files only; it did not edit native source or run any tests. The next command sourced the existing3.12 environment, then created the new test and ran the owning RED. No test failure other than the two intended baseline RED failures occurred.

## Tiny PQ success comparison

The success test read-only traces actual `buf` immediately before each production encoder write. All three pre-encoder frames equal the exact raw fixture bytes; source FFmpeg decode independently equals those bytes too. Three output frames decode at 64×64, HEVC/yuv420p10le, with PQ/smpte2084, BT.2020 primaries and bt2020nc matrix tags.

Using the same unchanged settings, RED/baseline and GREEN/candidate decoded output bytes and selected tags match exactly. Observed output MP4 SHA256 is also the same in these two runs, `45efe5610a8b48c6b062d88a89422d7cd62deda648f01a8b10276cf5bc04c403`; this is an observation, not a general encoder determinism guarantee. Decoded output SHA256 is `9dbf6a7b145d92a65cdd24e009419ca35884a33f4bacbed50223f3ff96f2cea6`. Raw source SHA256 is `174c242e9bd68fe5ee9512274b5d681a990b06737ad4ff1b74221753eecd725d`.

The lossy output differs from source: decoded constant planes 856/560/341 versus source 900/800/300. The cleanup does not fix or explain those unchanged encode/color effects. Source/pre-encoder equality and before/after decoded-output equality are separate assertions; no source-bit-identical lossy output claim is made.

## Full commands and execution results

Commands below ran with native cwd `/home/tahv0/.codex/worktrees/c832/OpenScrub`, except helper creation and SDD document writing. Exact edit/helper scripts remain under `/tmp/openscrub-task109`. `env.sh` sources `/tmp/openscrub-baseline-20261116/env-opencv4.sh`, selects the task-local import-isolation plugin, disables plugin autoload and redirects task data/cache/TMPDIR. `floor-env.sh` instead sources `/tmp/openscrub-python39-20261117/env.sh` and selects the same task-local isolation/plugin/roots.

```sh
# Test first, engine still exact baseline. Exit 1, intended2 failures / 1 pass.
. /tmp/openscrub-task109/env.sh
python /tmp/openscrub-task109/add_tests.py
python -m pytest -q -s -o cache_dir=/tmp/openscrub-task109/pytest-cache tests/test_hdr_decoder_cleanup.py --basetemp /tmp/openscrub-task109/red-tmp > /tmp/openscrub-task109/red.log 2>&1

# Only after owning RED. Exit 0,3 passed.
python /tmp/openscrub-task109/implement.py
python -m pytest -q -s -o cache_dir=/tmp/openscrub-task109/pytest-cache tests/test_hdr_decoder_cleanup.py --basetemp /tmp/openscrub-task109/green-tmp > /tmp/openscrub-task109/green.log 2>&1

# Actual saved successful outputs, exit 0; exact source/output/tag comparisons.
python /tmp/openscrub-task109/control_compare.py > /tmp/openscrub-task109/control-comparison.log 2>&1

# Exit 0,11 passed.
python -m pytest -q -s -o cache_dir=/tmp/openscrub-task109/pytest-cache tests/test_hdr_decoder_cleanup.py test_openscrub.py -k 'hdr or render or codec' --basetemp /tmp/openscrub-task109/focused-tmp > /tmp/openscrub-task109/focused.log 2>&1

# Existing model hash checked against openscrub.YUNET_SHA256, then copied to
# /tmp/openscrub-task109/runtime/models; sitecustomize hook installed as above.
# Full discovery once at stable source/test bytes: exit 0,137 passed.
python -m pytest -q -o cache_dir=/tmp/openscrub-task109/pytest-cache --basetemp /tmp/openscrub-task109/full-tmp > /tmp/openscrub-task109/full.log 2>&1

# Actual floor execution, exit 0,11 passed; not grammar-only.
. /tmp/openscrub-task109/floor-env.sh
python -m pytest -q -s -o cache_dir=/tmp/openscrub-task109/floor-cache tests/test_hdr_decoder_cleanup.py test_openscrub.py -k 'hdr or render or codec' --basetemp /tmp/openscrub-task109/floor-tmp > /tmp/openscrub-task109/floor.log 2>&1

# Offline build, exit 0. Log explicitly shows wheel built from sdist.
. /tmp/openscrub-task109/env.sh
PIP_NO_INDEX=1 PIP_FIND_LINKS=/tmp/openscrub-task620/build-wheelhouse python -m build --outdir /tmp/openscrub-task109/dist > /tmp/openscrub-task109/build.log 2>&1
python /tmp/openscrub-task109/check_packaging.py > /tmp/openscrub-task109/packaging.log 2>&1

# Existing runtime has no pip: run the existing pip implementation under the
# CORRECT3.12 runtime, so entrypoint shebangs use its prepared interpreter.
# Exit 0; no dependencies/network, no new toolchain.
PYTHONPATH=/tmp/openscrub-baseline-20261116/bootstrap/lib/python3.14/site-packages python -m pip install --no-index --no-deps --upgrade --target /tmp/openscrub-task109/installed/site-packages /tmp/openscrub-task109/dist/openscrub-1.0.96-py3-none-any.whl > /tmp/openscrub-task109/install-runtime.log 2>&1
python /tmp/openscrub-task109/check_installed.py > /tmp/openscrub-task109/installed-startup.log 2>&1

# Pre-commit: all 114 frozen hashes matched candidate files, git diff --check.
git diff --check
git add openscrub.py tests/test_hdr_decoder_cleanup.py pyproject.toml CONTRIBUTING.md
git commit -m "fix: close HDR decoder pipe during partial cleanup"
git rev-parse HEAD
git status --short

# Final exact source/commit binding, exit 0; all 114 hashes and clean status.
python /tmp/openscrub-task109/final_check.py > /tmp/openscrub-task109/final-check.log 2>&1
```

`check_packaging.py` verifies exact engine delta against `git show <base>:openscrub.py`, exact runtime/source/new-test/contributor bytes in the sdist and exact runtime bytes in the wheel. The wheel deliberately retains ordinary runtime packaging; tests ship in the sdist. It parses shipped Python with 3.9 grammar without substituting that for actual execution. Build used existing hatchling 1.33.0 from the offline wheelhouse. Output wheel SHA256 `071e640fcf897d698a54ef39f6e889355980b047755fc1262b8e71d51a1937ce`; sdist SHA256 `a50a1bf62929f25d83edb1aebfbefc133e637307d1b8141cda3fede3ae1995de`.

`check_installed.py` runs from `/tmp/openscrub-task109`, uses only the installed package paths and a fresh profile, asserts actual installed modules/code filename and unchanged CLI defaults, invokes the installed `openscrub --help` entrypoint, starts the actual installed `openscrub-web --http --host 127.0.0.1 --port <ephemeral> --retain-days 0`, obtains homepage/empty job API HTTP 200 and stops/reaps the server with SIGTERM rc 0. Entrypoint shebang is `/tmp/openscrub-baseline-20261116/venv-opencv4/bin/python`. No browser or unrelated performance/vault matrix was run.

## Self-review and limits

Reviewed the four-file diff, actual cleanup call sites and new regressions after verification. Confirmed source bytes outside the two-line production addition are exactly baseline bytes; default/encoder/success/error semantics have no other implementation delta. Test logic observes before harness cleanup, retains actual exception and real children, never relies on GC, and has unconditional containment. No nested agent/reviewer was spawned.

N09 is intentionally limited to existing ordinary cancellation and encoder-write cleanup calls. Final encoder-wait failure, temporary stderr lifetime, arbitrary compute exceptions/all-exception ownership, short reads, P16C geometry and prior-output preservation/publication remain separate accepted work. Existing partial-output deletion is unchanged; this patch makes no prior-output atomicity claim. No deadline, cancellation-speed measurement, arbitrary native interruption, unreaped-child or permanent-process-leak claim. No benchmark was required or run. Linux CPU/FFmpeg evidence does not certify Windows, GPU encoders or every native-call cancellation boundary. Full suite was run once at the stabilized candidate, then committed-byte identity was checked; no unnecessary full rerun was substituted for that binding.
