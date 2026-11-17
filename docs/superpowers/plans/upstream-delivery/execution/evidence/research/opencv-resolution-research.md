# B02b bounded core dependency-resolution evidence

Status: **PASS for the two existing Linux interpreter targets, resolver only.**
Task date: 2026-11-17, Europe/Helsinki. Fresh public-index compiles ran
2026-11-17 02:25:38–02:25:51 UTC. No package installation, tool upgrade, source
build, model download, product mutation, runtime probe or suite/build was run.

The proposed normal `opencv-python<5` requirement resolves with all nine
unchanged package-core declarations on both actual existing interpreters. Both
solutions contain exactly one cv2 wheel distribution, `opencv-python==4.14.0.94`.
No declaration-level incompatibility was found in the unchanged package core.
This closes the bounded Linux Python 3.12/3.9 fresh core resolver question; it
cannot establish binary/runtime behavior or optional Paddle coexistence.

## Pinned source and exact input

Only Git objects at `e21ebdf6e3ee46e6c65050dc956a9a3459152269` were used for
product source; tree `795af785b672d397d2e287b5b963c10dcc4dbdf8`. No moving native
product worktree was read/imported. The existing
[installation-scope report](opencv-install-scope-research.md) was reused for its
recommendation/limits and the [Task 91 plan](opencv-compat-source-plan.md) only
as future implementation scope. Paddle metadata and previous OpenCV runtime
research were not repeated.

| Pinned declaration | Git blob | Extracted scope |
|---|---|---|
| `pyproject.toml` | `2a60019772d14238c4c301d6bdfa965dbd628062` | Python `>=3.9`; ten package-core requirements |
| `requirements.txt` | `2bca4605ea363d447b331ef52e6e22279263d4a6` | Same ten plus `spacy` |
| `install.py` | `5b1d3de6141783a19c8bc83ecf8aae7cbf6fc1e4` | Seven direct `CORE_PKGS`, all within package core |

[Source manifest](opencv-resolution-evidence/source-manifest.json) records
exact content SHA256, byte counts, source/export declarations and proposed delta.
Unmodified source exports remain under
`/tmp/openscrub-opencv-resolution-20261117/source-*`.
The independent [candidate input](opencv-resolution-evidence/core-candidate.in)
changes **only** `opencv-python` to `opencv-python<5` from the
[original package-core export](opencv-resolution-evidence/core-original.in):

```text
opencv-python<5
numpy
onnxruntime
rapidfuzz
pytesseract
pillow
flask
pyyaml
cryptography
cheroot>=10.0
```

Candidate SHA256:
`a953b90959297225f8b361917b7e1e733262b128e7b0275fd126b13cf86463ca`.
No lower bound, exact pin or other candidate constraint was added. The
requirements-file spaCy addition, NER extras, optional Paddle/GPU extras and
installer system tools are outside this core resolution. This is not a full
`requirements.txt` resolution or a run of the standalone installer.

## Resolver and target evidence

Already available `uv 0.13.8 (x86_64-unknown-linux-gnu)` was invoked in `pip compile`
mode against each actual interpreter, with binary wheels only. Explicit
`--no-config`, a small constructed environment, disabled keyring and explicit
`https://pypi.org/simple` excluded private registries, credentials and inherited
pip/uv settings. No installed package set or prior lockfile constrained the
solutions. Each target used a new task-local cache; no shared wheel cache was
modified. Python automatic downloads were disabled. The timeout was 100 seconds
per compile and HTTP retries were disabled; actual runs finished under one second.

The exact executable command arrays, constructed environment, UTC start/end,
exit 0 and durations are in [Python 3.12 command](opencv-resolution-evidence/command-312-online.json)
and [Python 3.9 command](opencv-resolution-evidence/command-39-online.json).
The command shape was:

```text
/tmp/openscrub-baseline-20261116/bootstrap/bin/uv --no-config --no-progress --color never pip compile /tmp/openscrub-opencv-resolution-20261117/core-candidate.in --python TARGET --no-python-downloads --only-binary :all: --default-index https://pypi.org/simple --keyring-provider disabled --cache-dir TASK_TARGET_CACHE --no-strip-markers --emit-index-annotation --format pylock.toml --output-file TARGET_PYLOCK --verbose
```

`--only-binary :all:` excludes source builds. Initial option/filename validation
failures, the sandbox DNS failure and a harmless unsupported pylock index-annotation
warning are recorded in [attempt notes](opencv-resolution-evidence/attempt-notes.txt).
The successful runs used authorized read-only public-network escalation.

| Actual target | Platform / ABI | Result | Normal OpenCV | NumPy | ONNX Runtime | Pillow | RapidFuzz |
|---|---|---|---|---|---|---|---|
| CPython 3.12.16, `/tmp/openscrub-baseline-20261116/venv-opencv4/bin/python` | Linux x86_64, glibc 2.43; `cpython-312-x86_64-linux-gnu` | 23 packages, exit 0 | 4.14.0.94 | 2.5.5 | 1.32.0 | 13.0.0 | 3.14.6 |
| CPython 3.9.25, `/tmp/openscrub-python39-20261117/venv/bin/python` | Linux x86_64, glibc 2.43; `cpython-39-x86_64-linux-gnu` | 30 packages, exit 0 | 4.14.0.94 | 2.0.2 | 1.19.2 | 11.3.0 | 3.13.0 |

Both also select Cheroot 11.1.2, cryptography 50.0.2, Flask 3.1.3,
pytesseract 0.3.13 and PyYAML 6.0.3. All selected versions, markers, wheel tags,
URLs, sizes and SHA256s are preserved in
[Python 3.12 pylock](opencv-resolution-evidence/pylock.312.toml),
[Python 3.9 pylock](opencv-resolution-evidence/pylock.39.toml) and
[validation](opencv-resolution-evidence/validation.json).
[Target identity](opencv-resolution-evidence/targets.json) records each actual
interpreter and complete marker environment. uv emits generic lock
`requires-python` lower bounds `>=3.12.16` / `>=3.9.25`; these files are evidence
for these interpreter/platform resolutions, not a universal support declaration.

The selected OpenCV metadata is Python `>=3.6` and declares
`numpy>=2; python_version >= "3.9"`. Both targets satisfy this active edge and
the new `<5` bound. The project Python `>=3.9` declaration is preserved; both
actual targets satisfy it. Independent checks of all selected package
`Requires-Python`, every active dependency edge with no extras, and available
wheel tags passed for both target interpreters. Each selected package has at
least one wheel accepted by that target's actual `packaging.tags.sys_tags()`.

Direct OpenCV input is normal `opencv-python<5`. Neither resolved graph has
transitive OpenCV requirements or any of `opencv-contrib-python`,
`opencv-python-headless`, `opencv-contrib-python-headless`. Python-dependent
transitives include cffi/pycparser implementation markers on both; Python 3.9
also includes importlib-metadata/zipp below Python 3.10 and typing-extensions
below Python 3.11. Python 3.9's older ONNX Runtime selects coloredlogs/sympy
and their dependencies. These are compatible selections, not newly introduced
product pins or evidence that latest releases all support Python 3.9.

## Metadata/download boundary and remaining gates

The new evidence is a **fresh public-PyPI metadata resolution**, not an offline
or preinstalled-environment result. Resolver logs contain 46/60 fresh GETs
respectively: only official PyPI simple-index URLs and `.whl.metadata` URLs
from `files.pythonhosted.org`. No wheel archive GETs appear, and task caches
contain zero wheel/archive files. Cache data totals 9,324,957 / 9,611,505 bytes,
mostly package index history and parsed wheel metadata; the large OpenCV/NumPy/
ONNX Runtime wheels listed in the locks were not downloaded. Original complete
logs are compressed in
[Python 3.12 output](opencv-resolution-evidence/resolver-312-online.log.gz) and
[Python 3.9 output](opencv-resolution-evidence/resolver-39-online.log.gz).

For explicit validation, 43 unique already-selected official wheel metadata
URLs were fetched again with a per-response 256,000-byte cap, totaling 360,621
bytes. [Metadata declarations](opencv-resolution-evidence/metadata-declarations.json)
preserve URL, server/retrieval time, SHA256, exact `Requires-Python` and every
`Requires-Dist`. These official metadata URLs and
[PyPI OpenCV index](https://pypi.org/simple/opencv-python/) are source provenance;
no package runtime was imported. GitHits MCP skill was read; `quick_start` and
package lookups were unnecessary because the new deciding evidence is actual
resolver output and direct selected official metadata, not repeated Paddle research.

Remaining implementation gates: built metadata/declaration synchronization,
installed package/runtime behavior and the prepared compatibility diagnostics.
Windows/macOS, frozen packaging, GPU/CUDA, broad Python/platform support,
spaCy/NER and optional Paddle command environments remain separate. In
particular, the pre-existing normal/contrib Paddle flavor policy remains open;
this core graph cannot certify optional-Paddle coexistence. Unbounded future
index changes and resolver differences can change future selections. No broad
dependency-upgrade work is proposed from the older Python 3.9 selections.

Evidence inventory/hashes:
[evidence-sha256.json](opencv-resolution-evidence/evidence-sha256.json).
Reproduction/validation scripts are included alongside evidence. All research
writes are confined to this report/evidence directory and
`/tmp/openscrub-opencv-resolution-20261117`.
