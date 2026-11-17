# Python 3.9 verification environment setup

Status: **usable infrastructure; limited smoke passed**. This establishes a real Python 3.9 environment for later focused checks. It does **not** establish full acceptance of the advertised Python floor.

## Reuse

```bash
source /tmp/openscrub-python39-20261117/env.sh
cd /tmp/openscrub-python39-20261117/runtime
python --version
```

Interpreter: `/tmp/openscrub-python39-20261117/venv/bin/python`, CPython **3.9.25**. The supervisor received this path promptly after all core/test/build imports succeeded.

Pinned source export: `/tmp/openscrub-python39-20261117/source`, from full `git archive` of reviewed commit `3795d49f6293baf7b8c35534862a4881447e1b16`, tree `f1670ddc872a906851f2caa568f559eb9e9c2373`. The archive SHA-256 is `4e00221b724e226cfee2f2670bac19edb4b68fc74b4bf87d220ffab6b7f0d596`. All **119** exported regular files still exactly match their archive contents after setup/build/smokes. Runtime checks did not import the moving native worktree.

For a subsequent approved focused check on another committed export under this task root, explicitly select its source path before invoking Python; otherwise the installed package remains this pinned baseline:

```bash
PYTHONPATH=/tmp/openscrub-python39-20261117/harness:/tmp/openscrub-python39-20261117/ANOTHER_COMMITTED_EXPORT \
  python -m pytest path/to/explicit_focused_test.py
```

The example is guidance only; no tests on another commit or prior feature branches were run in this setup task. Pytest's task-local plugin isolates runtime paths and blocks model fetches; plugin autoload is disabled and its cache path is task-local.

## Resolution and isolation

The existing isolated `uv 0.13.8` executable was reused read-only. Its normal Python installer obtained the released CPython 3.9.25 standalone build from Astral's `python-build-standalone` GitHub release `20251031`. Dependencies came from `https://pypi.org/simple`. Interpreter installation, venv, package/build/runtime files, temporary files and caches are under `/tmp/openscrub-python39-20261117`. The only other new files are this report and its SDD evidence directory.

The actual core dependencies came from the pinned `pyproject.toml`, with `pytest`, `build`, and `hatchling` added. The repository's `requirements.txt` also contains optional spaCy, so it was deliberately not the resolution input. No optional Paddle/spaCy/training stack or model was downloaded.

The **separate validation constraint** is `opencv-python<5`, recorded in `validation-constraints.txt`. It reflects the established OpenCV 5 fallback gap and B02b's proposed fix. The exported and shipped metadata remain unchanged and declare unconstrained `opencv-python`; this report does not imply the cap is upstream. No other dependency pins were added to force resolution.

| Direct requirement/tool | Selected version |
| --- | --- |
| OpenScrub | 1.0.96, built from the pinned export |
| opencv-python | 4.14.0.94 (`cv2.__version__` 4.14.0) |
| numpy | 2.0.2 |
| onnxruntime | 1.19.2 |
| rapidfuzz | 3.13.0 |
| pytesseract | 0.3.13 |
| pillow | 11.3.0 |
| flask | 3.1.3 |
| pyyaml | 6.0.3 |
| cryptography | 50.0.2 |
| cheroot | 11.1.2 |
| pytest | 8.4.2 |
| build | 1.4.4 |
| hatchling | 1.27.0 |

All **42** selected distributions, their `Requires-Python` metadata, installed wheel tags and native-extension paths are in `packages.json`; exact versions are in `resolved-versions.txt`. Each installed wheel's tags intersect this interpreter's supported tags. SOABI is `cpython-39-x86_64-linux-gnu`; platform is Linux x86_64 on WSL2 with glibc 2.43. No Python 3.12 native package files were copied or reused. Selection reflects Python 3.9 compatibility and the one validation cap, rather than the versions selected previously on 3.12.

FFmpeg **8.0.1-3ubuntu2** and Tesseract **5.5.0**, with their extracted native libraries/tessdata, were reused read-only from `/tmp/openscrub-baseline-20261116/tools`. Their version invocations passed. No baseline Python site-packages were added to `PYTHONPATH`.

The reusable `env.sh`, `sitecustomize.py` and `python39_isolation.py` harnesses route the process's home expansion, models, web data, pytest cache and temporary paths into this task root. They do not change `$HOME`, shell profiles, installed source, Git state, or user data. The audit hook rejects task-process file writes outside the task root, except `/dev/null`, and rejects non-loopback socket connections. The plugin explicitly refuses non-file model fetches before networking; `OPENSCRUB_NO_AUTOFETCH=1` is also set.

## Verified evidence

- Imported every declared core dependency plus pytest/build/Hatchling and both installed application modules successfully on Python 3.9.25.
- Installed `openscrub --help` and `openscrub-web --help`, and both source-script `--help` paths, exited 0.
- Both installed and pinned-source Flask API smokes returned 200 for UI, jobs, face-model registry, model status and vault status; jobs were empty, UI was present with `no-store`, `/zones` redirected to `/`, and a synthetic nonexistent video job returned 400.
- Both modes completed an exact 32×24 synthetic PNG encode/decode roundtrip and grayscale conversion through the Python 3.9 NumPy/OpenCV native wheels.
- Explicit outward model-fetch attempts were rejected before networking. The socket audit policy rejected a directly emitted external-address audit event. The model directory remained empty; no YuNet file was required or reused.
- `python -m build --no-isolation` built an sdist and then a wheel from that sdist successfully under Python 3.9. Artifact hashes are in `environment.json`.
- Manifest generation verified all 119 source-file contents against the pinned archive and all 42 installed wheel-tag compatibilities.

All final commands exited 0. The complete setup/verification commands and reusable scripts are included alongside compact logs and manifests in [python39-verification-evidence](python39-verification-evidence/).

## Limits and setup observations

The first restricted-network interpreter download attempt failed DNS. The same authorized task-local setup command succeeded with network access; dependency installation then succeeded without extra pins. This was environment setup, not a package fix.

Two harness checks were corrected before final passing verification: the initial write guard also blocked harmless `/dev/null` use by Python's platform diagnostic, and the sandbox denied socket creation before a live connection could reach the audit hook. `/dev/null` is now allowed; the latter assertion uses `sys.audit` directly, with the initial socket-denial log preserved. Web checks use Flask's in-process test client, so they make no bound-port/server-startup claim.

No whole 230-test suite, prior-branch reruns, media benchmark, positive-face inference, GPU inference or other operating-system checks were performed. The temporary OpenCV cap and compatible dependency resolutions are explicit limits. Later focused checks must run against the actual upcoming committed source; this setup report is distinct from a full Python-floor acceptance result.
