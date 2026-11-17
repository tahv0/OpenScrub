# B01/B02 baseline report

Date: 2026-11-16. Scope: environment and baseline evidence only; no product edits,
P01 implementation, version changes, commits, system-package installation, or
remote writes.

## Disposition

B01 is complete. B02 environment preparation and required baseline checks are
complete with concerns: the unchanged baseline is red under unconstrained current
core dependencies. A separate OpenCV 4 compatibility investigation is recorded
below. No new test files/discovery changes belong to this task;
`test_openscrub.py` remains in place. The first owning PR must explicitly collect
any new `tests/test_<topic>.py` beside it in contribution instructions and CI.

## Source and preservation evidence

- Native worktree: `/home/tahv0/.codex/worktrees/c832/OpenScrub`.
- Branch: `pr/save-as-progress`.
- Tested HEAD and local `main`: `5d3a15ae683c08f368d6ba4bd0d2d77b4e7b8e2f`.
- Connected GitHub API `github.fetch_commit(repo_full_name="austinmabry/OpenScrub", commit_sha="main")`
  returned the same SHA on this date. Commit: “Benchmark: publish the v1.0.96 re-measurement”.
  The response is preserved in [upstream-main-snapshot.json](task-1-artifacts/upstream-main-snapshot.json).
- Donor/archive: `b4d0c75f25d91510fe1692f901d11853dc7db005`, preserved as
  `archive/integration-all-prs-2026-11-16` by supervisor.
- Plan preserved separately on `docs/upstream-delivery-plan`, commit
  `33fdabe73c8105b23980e53d7ac7aeca792ab205`, by supervisor.
- `git status --short` produced no output before/after checks;
  `git diff --exit-code 5d3a15ae683c08f368d6ba4bd0d2d77b4e7b8e2f --` exited 0.
- Import scan `rg -n '^(from|import) .*?(train|learn|workbench|openscrub_review)' --glob '*.py'`
  found no matches. No donor training/review-workbench module was imported.
- `origin` remains `git@github.com:tahv0/OpenScrub.git`; no remotes renamed.
- Original checkout/runtime data were not used. All job/cache data here are
  synthetic and live under `/tmp/openscrub-baseline-20261116/synthetic-data/`.

## Guides and environment

Read upstream `CONTRIBUTING.md`, `pyproject.toml`, `requirements.txt`, and relevant
`CLAUDE.md` architecture/verification rules. `CLAUDE.local.md` is absent.
`pyproject.toml` is authoritative for core Python `>=3.9`; CLAUDE prose says
3.10+, a pre-existing documentation mismatch left unchanged. This execution tests
Python 3.12 only and does not establish Python 3.9 compatibility.

The host has `/usr/bin/python3` 3.14.4, no `python` alias, no FFmpeg/Tesseract, and
no Chromium/Chrome/Firefox. Node is `/usr/bin/node` v22.22.1. Browser plugin is
absent (supervisor verified); there were no UI changes in this baseline task and
no browser interaction is claimed.

Isolated environment:

- Root: `/tmp/openscrub-baseline-20261116`.
- Interpreter: `/tmp/openscrub-baseline-20261116/venv/bin/python`, Python 3.12.16.
- Downloaded interpreter under `python/cpython-3.12.16-linux-x86_64-gnu`.
- Bootstrap venv: `bootstrap`, created with host Python and ensurepip; uv 0.13.8.
- Install: editable upstream core from `pyproject.toml`, plus pytest/build only.
  `requirements.txt` was deliberately not used because it includes optional spaCy.
- Resolved primary versions: OpenScrub 1.0.96, opencv-python 5.0.0.93 (`cv2` 5.0.0),
  NumPy 2.5.5, onnxruntime 1.32.0, Flask 3.1.3, cheroot 11.1.2,
  cryptography 50.0.2, pytest 9.2.0, build 1.6.1; build isolation used hatchling 1.33.0.
- Full versions: `task-1-artifacts/python-packages.txt` and `environment.json`.
- Host platform: Linux WSL2 x86_64, glibc 2.43.
- Available inference providers: AzureExecutionProvider, CPUExecutionProvider;
  CUDA devices: 0. CUDA/OpenVINO/DirectML inference was not exercised.
- Task-local FFmpeg/ffprobe 8.0.1-3ubuntu2, Tesseract 5.5.0, Leptonica 1.86.0.
  English/osd standard Tesseract language resources are included; supervisor
  explicitly ruled these allowed declared OCR runtime dependencies.
- 108 downloaded Ubuntu `.deb` packages were extracted with `dpkg-deb -x` into
  `tools/`, without dpkg/apt installing anything. Exact package versions and SHA256
  values are in `task-1-artifacts/system-tool-package-manifest.json`.
- No training packages, training datasets, real user jobs, or optional OpenScrub
  model checkpoints were accessed/downloaded in this initial baseline.

## Reproduction commands

All application checks use the native worktree above. Downloads/build/native
worktree writes were run with tool escalation as required, not relocated.
These are reproduction instructions, not additional execution results. Run against
the recorded baseline SHA; later product edits will change the observed source.
The preserved helpers must first be staged into their expected task-local path.

```bash
mkdir -p /tmp/openscrub-baseline-20261116/debs
cp /home/tahv0/src/OpenScrub/.superpowers/sdd/README/task-1-artifacts/*.py /tmp/openscrub-baseline-20261116/
cp /home/tahv0/src/OpenScrub/.superpowers/sdd/README/task-1-artifacts/*.sh /tmp/openscrub-baseline-20261116/
cd /home/tahv0/.codex/worktrees/c832/OpenScrub
python3 -m venv /tmp/openscrub-baseline-20261116/bootstrap
/tmp/openscrub-baseline-20261116/bootstrap/bin/python -m pip install --disable-pip-version-check uv
UV_PYTHON_INSTALL_DIR=/tmp/openscrub-baseline-20261116/python UV_CACHE_DIR=/tmp/openscrub-baseline-20261116/uv-cache /tmp/openscrub-baseline-20261116/bootstrap/bin/uv python install 3.12
UV_PYTHON_INSTALL_DIR=/tmp/openscrub-baseline-20261116/python UV_CACHE_DIR=/tmp/openscrub-baseline-20261116/uv-cache /tmp/openscrub-baseline-20261116/bootstrap/bin/uv venv --python 3.12 /tmp/openscrub-baseline-20261116/venv
UV_CACHE_DIR=/tmp/openscrub-baseline-20261116/uv-cache /tmp/openscrub-baseline-20261116/bootstrap/bin/uv pip install --python /tmp/openscrub-baseline-20261116/venv/bin/python -e . pytest build
python3 /tmp/openscrub-baseline-20261116/get_tools.py
. /tmp/openscrub-baseline-20261116/env.sh
python -m pytest test_openscrub.py -q -ra -o cache_dir=/tmp/openscrub-baseline-20261116/pytest-cache
python -m build --outdir /tmp/openscrub-baseline-20261116/dist
python /tmp/openscrub-baseline-20261116/http_smoke.py
python - <<'PY'
import ast
from pathlib import Path
import re
from baseline_isolation import configure

web = configure('syntax')
blocks = re.findall(r'<script>(.*?)</script>', web.PAGE, re.S)
Path('/tmp/openscrub-baseline-20261116/evaluated-page.js').write_text(
    '\n'.join(blocks), encoding='utf-8')
print(f'evaluated PAGE: {len(blocks)} script blocks, {sum(map(len, blocks))} JS characters')
for path in Path('.').glob('*.py'):
    ast.parse(path.read_text(encoding='utf-8'), filename=str(path))
print('all top-level Python source AST parses passed')
PY
node --check /tmp/openscrub-baseline-20261116/evaluated-page.js
```

`env.sh`, `get_tools.py`, and `baseline_isolation.py` are preserved in
`task-1-artifacts/`. `env.sh` adds only task-local executable/library/data paths,
sets `PYTHONDONTWRITEBYTECODE=1`, and registers the external pytest plugin through
`PYTEST_PLUGINS=baseline_isolation`. This is environment setup, not shipped code.

The plugin runs real app code but redirects web job/settings/cert paths and engine
model cache to task-local synthetic directories. It sets
`OPENSCRUB_NO_AUTOFETCH=1` and rejects non-`file://` calls to `_fetch_model`
immediately. The real `_fetch_model` implementation remains active for synthetic
local-file hash/size tests. No tests were excluded, marked xfail, or forced to pass.
Consequently face-model-dependent coverage is limited by the missing YuNet file.

## Check results at the tested SHA

| Check | Result | Evidence |
|---|---|---|
| Existing suite, current unconstrained core | **116 passed, 14 failed, 4 errors**, 0 skipped; 57.41s; exit 1 | `task-1-artifacts/pytest.log` |
| Separate OpenCV 4 + pinned built-in YuNet | **133 passed, 1 failed**, 0 skipped/errors; 74.88s; exit 1 | `task-1-artifacts/pytest-opencv4.log` |
| Full default build, sdist then wheel from sdist | Pass, exit 0 | `task-1-artifacts/build.log` |
| Evaluated combined embedded JavaScript | 2 script blocks, 100,416 characters; `node --check` exit 0 | `task-1-artifacts/syntax.log` |
| All top-level Python files parsed with `ast.parse` | Pass | `task-1-artifacts/syntax.log` |
| Real Cheroot startup + loopback HTTP smoke | Pass, exit 0 | `task-1-artifacts/http-smoke.log`, `startup.log` |
| Final source diff | Clean | git commands above |

Build artifacts (all under `/tmp/openscrub-baseline-20261116/dist`):

- `openscrub-1.0.96.tar.gz`, 523,547 bytes,
  SHA256 `0f5437a1a8b5099544b16403e19c08d395cfff2e2ca63152d14a0cfa77f47508`.
- `openscrub-1.0.96-py3-none-any.whl`, 434,343 bytes,
  SHA256 `56c03d6b6bc7c1ecc01f5a37c62081874d5c1e98f7e223a837c59176a3a6c6bd`.
- Wheel inspection confirmed engine/web/zones/vault modules, all three registries,
  third-party notices, and icon present. No versions/release metadata changed.

HTTP smoke starts the real `main()` with `--host 127.0.0.1 --port <ephemeral>
--http --retain-days 0`, using a separate empty startup job root. `GET /` returned
200 and `Cache-Control: no-store, no-cache, must-revalidate, max-age=0`;
`/api/jobs` returned an empty list; `/api/models/face`, `/api/model_status`,
`/api/vault` returned JSON with 200; `/zones` redirected to `/`; nonexistent
synthetic server-path intake returned 400. SIGTERM shutdown exited 0. TLS and
browser interactions were not exercised; no real jobs were queued or retained.

The suite itself exercised synthetic scan/render/report workflows using real
Tesseract and task-local FFmpeg. No engine changes were made in this task.

## Existing failures and execution limits

Thirteen failures and four shared-fixture errors enter Haar fallback after the
policy-blocked YuNet fetch and fail at `openscrub.py`'s use of
`cv2.CascadeClassifier`: OpenCV 5.0.0 has no such attribute. The API absence was
verified directly. This is a current dependency compatibility failure, not
introduced by a port. It prevents the shared chart fixture and affected face
paths from reaching their intended assertions. One additional case,
`test_face_model_unions_with_yunet`, explicitly requires a real YuNet instance,
so even a functioning Haar fallback alone cannot fulfill its assertion.

The remaining failure is `test_track_person_size_jump_handoff`: no log contains
"size jump" for the synthetic engulfing-lookalike scenario. It uses a stub person
detector and is independent of face model availability. Focused diagnosis follows
below; no product fix has been applied.

All 134 collected tests are accounted for. The 14 failed test names and four
fixture errors appear in the full retained log, without truncation.

The first suite invocation used a missing task-local `pulseaudio` library subpath
and produced 29 failures, 97 passes, 4 skips, 4 errors in 22.18s. This was setup
failure, retained as `pytest-initial-tooling-failure.log`; it is superseded by the
corrected complete run above. No source was changed to correct it. An initial
HTTP harness asserted an exact `Cache-Control == no-store` value; the app correctly
includes further directives. The corrected harness checks containment. Its initial
assertion is retained as `http-smoke-initial-harness-assertion.log` and is not an
application failure.

Additional limits: no browser available; no CUDA hardware/providers; no optional
OCR/ASR/spaCy/person/plate models; no pretrained-model accuracy or privacy benchmark
claims; no Python 3.9 floor verification; no Windows installer/container builds.
ORT emitted a telemetry-device-ID persistence warning during a diagnostic import
and used an in-memory identifier; inference-provider discovery still succeeded.

## OpenCV 4 compatibility and focused handoff diagnosis

Supervisor explicitly authorized a separate temporary OpenCV 4 constraint and
fetching an existing pinned built-in model strictly needed by the suite. The
unconstrained environment/log remains intact. No upstream requirement was changed.

The separate environment is
`/tmp/openscrub-baseline-20261116/venv-opencv4/bin/python` (Python 3.12.16).
The constraint `opencv-python<5` resolved **opencv-python 4.14.0.94** (`cv2` 4.14.0)
and NumPy 2.5.5; all other package versions match the unconstrained environment.
`cv2.CascadeClassifier` exists here. Exact packages are preserved as
`python-packages-opencv4.txt` and `requirements-opencv4.txt`, with interpreter/API
details in `environment-opencv4.json`.

```bash
UV_PYTHON_INSTALL_DIR=/tmp/openscrub-baseline-20261116/python UV_CACHE_DIR=/tmp/openscrub-baseline-20261116/uv-cache /tmp/openscrub-baseline-20261116/bootstrap/bin/uv venv --python 3.12 /tmp/openscrub-baseline-20261116/venv-opencv4
UV_CACHE_DIR=/tmp/openscrub-baseline-20261116/uv-cache /tmp/openscrub-baseline-20261116/bootstrap/bin/uv pip install --python /tmp/openscrub-baseline-20261116/venv-opencv4/bin/python -e . pytest build 'opencv-python<5'
. /tmp/openscrub-baseline-20261116/env-opencv4.sh
python -m pytest test_openscrub.py -q -ra -o cache_dir=/tmp/openscrub-baseline-20261116/pytest-cache-opencv4
```

For exact recreation use `opencv-python==4.14.0.94`, rather than allowing the `<5`
constraint to resolve again. `requirements-opencv4.txt` preserves the full resolved
set. The environment setup script switches interpreter and sets
`OPENSCRUB_BASELINE_MODEL_DIR` to a separate `models-opencv4` cache. App model
network downloads remain blocked during tests.

Only the **built-in YuNet** model was fetched in this follow-up, via the unmodified
`openscrub._fetch_model(openscrub.YUNET_URL, dest, sha256=openscrub.YUNET_SHA256)`.
It is 232,589 bytes, SHA256
`8f2383e4dd3cfbb4553ea8718107fc0423210dc964f9f4280604804ed2552fa4`, exactly matching
upstream's declared pin, and lives exclusively in
`/tmp/openscrub-baseline-20261116/synthetic-data/models-opencv4/face_detection_yunet_2023mar.onnx`.
`yunet-manifest.json` records the URL, path, size, hash and source SHA. No VitTrack,
SFace, plate/person/ASR/research checkpoints were fetched.

OpenCV 4 suite result: **133 passed, 1 failed, 0 skipped/errors**, 74.88s, exit 1.
The only remaining failure is `test_track_person_size_jump_handoff`, diagnosed
below. This provides a compatible core validation environment with a known
pre-existing logging assertion failure; it is not claimed to be a green baseline.
The 17 OpenCV-5/missing-fallback errors/failures disappear in this separate
OpenCV-4 + built-in-YuNet configuration. Because both dependency and model
availability differ, that comparison alone does not isolate each factor; direct
API inspection independently proves OpenCV 5 lacks the Haar fallback constructor.

Focused tracking diagnosis used the **unchanged real test function and tracker**,
adding only task-local observation wrappers around `cv2.compareHist` and the
tracker's callback/output. `diagnose_handoff.py` was run with both environment
scripts; JSON captures and logs are preserved. No product/test source was edited.

- Both `cv2` 5.0.0 and 4.14.0 reproduce the same log-assertion failure.
- At t≈2.9s the ordinary appearance veto rejects a candidate and starts the held
  state. The test expects a later log containing `size jump`.
- From t≈3.03s the size guard **is evaluated**: size ratio 2.708333, histogram
  correlation ~0.704–0.706, below its 0.80 threshold. It rejects the larger box.
- Its `if not held` guard suppresses the size-jump log because the track was
  already held. This explains the assertion failure without assuming the size
  guard was bypassed.
- All 20 returned samples at t>=3s retain area **7,200px²**, the original seeded
  box; none adopts the 19,500px² lookalike. There are 81 total samples. Coverage
  pauses after the existing held grace, as designed.
- This is evidence of an overly specific logging assertion under the current
  synthetic fixture, not observed adoption of the larger person in this scenario.
  It does not establish broader tracker privacy/accuracy properties.
- Relevant unchanged code: `openscrub.py` around 2243–2264 (comparison/log guard),
  `test_openscrub.py` around 2335 (log assertion). No fix is proposed/applied here.
