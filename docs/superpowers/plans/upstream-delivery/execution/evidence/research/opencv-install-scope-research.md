# B02b minimum installation compatibility scope

Task date: 2026-11-17, Europe/Helsinki. Metadata retrieval: 2026-11-16
23:25–23:26 UTC (2026-11-17 locally). Research/design only. This report is not
approval, an implementation, a resolver run, or a shipped compatibility claim.
The existing plan authorizes subsequent local bug-fix implementation.

## Recommendation

Make B02b one small core compatibility change: synchronize `opencv-python<5`
in the three direct declarations, replace import-only OpenCV health checks in
`install.py` and `openscrub_setup.py` with one read-only targeted check, and
provide deliberate repair instructions for an existing single normal-wheel
installation. Preserve normal `opencv-python`, Python >=3.9, current providers,
YuNet and Haar. No new lower bound or global exact pin is justified.

**Current Paddle metadata already excludes OpenCV 5 on its declared OCR path,
but does not solve wheel coexistence.** Keep Paddle flavor reconciliation as a
named separate task. A four-flavor `<5` constraints file alone would not solve
the verified declaration-level conflict: core asks for `opencv-python` and
PaddleX OCR asks for `opencv-contrib-python`; both distributions provide `cv2`.
Do not add automatic uninstalls, flavor replacement, a dependency manager,
an updater dependency migration, or unrelated packaging changes to B02b.

This recommendation reuses the completed matched experiment in
[opencv-compat-research.md](opencv-compat-research.md): unchanged production
Haar constructs/runs on normal 4.14.0.94 and crashes on normal 5.0.0.93 with
the same empty cache and blocked downloads; the same cached YuNet runs on both.
Those are previous results. Neither that probe nor the suite was repeated here.

## Current primary metadata and the actual optional commands

GitHits MCP skill was read before package tools; `quick_start` was not called.
GitHits identified PaddleOCR 3.7.0 and PaddleX 3.7.2 as its selected/latest
releases. Its dependency output omits the `ocr-core` extra from the displayed
PaddleOCR dependency edge, so raw official PyPI JSON supplied the deciding
extras/markers. The raw JSON confirmed the same current release versions.
The compact evidence preserves query URLs, UTC retrieval/server times, exact
dependency strings, and individual artifact upload times without downloading
artifacts: [pypi-declarations.json](opencv-install-scope-evidence/pypi-declarations.json).

| Primary package metadata | Exact relevant declaration | Meaning |
|---|---|---|
| PaddleOCR 3.7.0; wheel uploaded 2026-06-11T12:09:51.204074Z; Python >=3.8 | `paddlex[ocr-core]<3.8.0,>=3.7.0` | Plain `pip install paddleocr` selects the OCR-core extra; callers need not spell an extra. No direct OpenCV requirement. |
| PaddleX 3.7.2; wheel uploaded 2026-06-25T05:50:51.196355Z; Python >=3.8 | `opencv-contrib-python==4.10.0.84; extra == "ocr-core"` | This selected declared edge is exactly OpenCV 4 contrib. No platform/Python marker on this edge. |
| PaddleX 3.7.0 and 3.7.1, also currently admitted by that range | Same `ocr-core` contrib pin | All three current stable releases in the admitted 3.7 range have the same relevant pin. Exact upload times retained in evidence. |
| PaddleX 3.7.2 | `numpy<2.4,>=1.24` | Additional environment pressure; not a reason to change core NumPy policy in this fix. |
| PaddlePaddle CPU 3.3.1 | No direct OpenCV requirement; `numpy>=1.21` | CPU engine is a separate package. PyPI `requires_python` is null; file tags cannot establish complete floor/platform support. |

Sources: official [PaddleOCR 3.7.0 JSON](https://pypi.org/pypi/paddleocr/3.7.0/json),
[PaddleX 3.7.2 JSON](https://pypi.org/pypi/paddlex/3.7.2/json),
[3.7.0 JSON](https://pypi.org/pypi/paddlex/3.7.0/json),
[3.7.1 JSON](https://pypi.org/pypi/paddlex/3.7.1/json), and
[PaddlePaddle 3.3.1 JSON](https://pypi.org/pypi/paddlepaddle/3.3.1/json).
Other PaddleX extras also request that contrib pin; the actual plain PaddleOCR
commands are explained by `ocr-core`, so no larger extras graph is needed.

| Pinned OpenScrub entry point | Command/index implications |
|---|---|
| `install.py::step_paddle`, CPU | Separate PyPI-default calls for `paddlepaddle` and plain `paddleocr`. The current declaration chain above applies if those releases are selected. |
| `install.py::step_paddle`, GPU | Unpinned `paddlepaddle-gpu` from Paddle cu126 index, then a separate default-index `paddleocr` call. GPU failure falls back to CPU Paddle. Keep those provider choices unchanged. |
| `openscrub_gui.py::INSTALLS`, CPU | Default-index `paddleocr paddlepaddle` together. |
| Desktop GPU | Default-index `paddleocr`, then CPU Paddle uninstall and `paddlepaddle-gpu==3.2.2` from Paddle cu126. OpenCV effects come through the first call's PaddleOCR graph. |
| `openscrub_web.py::EXTRAS`, CPU | Default-index `paddleocr paddlepaddle` together. |
| Web GPU | `paddleocr paddlepaddle-gpu==3.2.2 -i https://www.paddlepaddle.org.cn/packages/stable/cu126/` together. This explicitly selects Paddle's index for the whole command. Do not claim a PyPI-only resolution proves this command. |

Metadata-only reads of Paddle's cu126 `paddleocr/` and `paddlex/` index pages
returned HTTP 200 with empty bodies; its `paddlepaddle-gpu/` page listed 3.2.2
Linux/Windows wheels, including cp39. This is an observation of those responses,
not proof of a successful/failed full install with arbitrary installed packages,
pip configuration, caches, mirrors or future index contents. No wheel or wheel
metadata was fetched. GPU-wheel dependencies were not established. An initial
PyPI lookup used nonapplicable GPU 3.2.1 and returned 404; pinned source inspection
confirmed the actual GUI/web pin is 3.2.2, and evidence uses that index listing.
See [paddle-cuda-index.json](opencv-install-scope-evidence/paddle-cuda-index.json)
and official [pip index-selection behavior](https://pip.pypa.io/en/stable/cli/pip_install/#finding-packages).

Guaranteed facts here are **declarations for the named releases**, not a
resolved environment. Python/platform filtering or installed requirements can
select older Paddle releases; future unbounded PaddleOCR releases can change
the graph. No resolver was run, so no OS/Python-specific solution, binary ABI,
Paddle inference, GPU availability, or full transitive closure is claimed.
The observed selected OCR-core edge requires neither main nor headless OpenCV;
it does not globally prohibit those packages through other dependencies.

OpenCV's own package guidance says choose one of the four distributions because
all share `cv2`: [official package instructions](https://github.com/opencv/opencv-python#installation-and-usage).
GitHits served README snapshot `031876bd` (2026-09-04), older than requested
HEAD `56b7342d` (2026-11-14, indexing). Its claim about bundled Haar data must
not override the completed concrete main5 experiment. The four names are
`opencv-python`, `opencv-contrib-python`, `opencv-python-headless`, and
`opencv-contrib-python-headless`; constraints on one do not constrain another.

## Existing checks and the smallest user-visible behavior

Source is pinned Austin `e21ebdf6e3ee46e6c65050dc956a9a3459152269`, read through
Git objects only. [source-manifest.json](opencv-install-scope-evidence/source-manifest.json)
records blob IDs/content hashes. No moving native worktree was imported.

* `install.py::have` only runs `import <module>` in its resolved `PYTHON`.
  `step_core` zips `CORE_PKGS` to import names and installs only missing imports.
  An importable main5, singleton contrib/headless, or mixed installation passes
  the current core check. Changing only `CORE_PKGS` will not fix this.
* `openscrub_setup.py::main` only tries `import cv2, flask`; main5 and mixed
  flavors pass. Import failures get an unbounded broad OpenScrub reinstall hint.
  Setup currently returns 0 even after missing checks; changing the entire
  command's exit-code policy is not necessary for this compatibility fix.
* `openscrub_update.py::update_pip` invokes pip on the new OpenScrub release;
  released corrected metadata governs that operation. `update_source` replaces
  release files after hash verification and preserves local state; it never
  reconciles dependencies. Keep updater behavior unchanged. Add documented
  post-source-update `python install.py --check` and intentional repair when
  reported. No updater pip calls or unconditional uninstall.

Use a targeted subprocess probe in the actual interpreter, independent of the
engine, Flask, models and optional providers. It should collect `cv2.__version__`,
`cv2.__file__`, metadata versions of all four wheel names, and Haar fallback
capability: callable `CascadeClassifier`, a real readable frontal-face XML at
`cv2.data.haarcascades`, construction of that cascade and `empty() == False`.
Construction is a health check, not inference; no model fetching is involved.
Capture missing import, malformed output, timeout/nonzero exit, missing API,
missing XML and failed/empty classifier separately. Version >=5 is unsupported
under this selected core policy even when cached YuNet or contrib capabilities
happen to work. Check runtime version and installed distribution versions;
disagreement is a diagnostic, not a basis for guessing file ownership.

The result must separate `fallback_usable` from `installation_state`. A real
single normal <5 runtime with working Haar can be reported healthy for this
check. Multiple wheel metadata entries are a conflict warning/failure even if
the currently imported Haar works; do not infer the last installed owner from
metadata. A singleton alternate <5 flavor, or no wheel metadata with importable
cv2 (source/distro/frozen build), may pass capability checking, but must be
identified as alternate/unmanaged rather than certified as the normal managed
installation. Do not replace it just to satisfy the default flavor. Unknown
version/import failures remain explicit, never `all present`.

The minimum deliberate repair is an actionable **printed command**, not a new
repair wizard or automatic mutation:

* Existing sole `opencv-python` incompatible/broken runtime: show the exact
  interpreter and `-m pip install --force-reinstall "opencv-python<5"`, then
  rerun the relevant check in a fresh process. Explain it restores the normal
  compatible wheel. Only print this direct repair when no other cv2 wheel
  flavor is registered. Do not present package installation success as health
  without rerunning the probe.
* Fresh state with no importable cv2 **and no registered cv2 wheel flavor**:
  existing installer prompt installs the bounded normal requirement. `--check`
  installs nothing. Reprobe after an accepted install and report actual status.
* Mixed, alternate, source-built or uncertain ownership: list detected names,
  versions, imported path and capability issue. Recommend a dedicated clean
  core environment or deliberate owner-specific reconciliation; show inspection
  and rerun instructions. Do not offer a single-main reinstall as a mixed-flavor
  cure. Existing `--yes` does not authorize a new blanket OpenCV uninstall.

In `step_core`, handle OpenCV separately from the generic missing-import list.
An alternate cv2 or broken existing flavor must never cause an ordinary
`pip install opencv-python<5` to silently add another flavor. Other core package
prompts keep their current behavior. Report incompatible OpenCV visibly in both
check and normal modes, including when users choose not to repair.

## Implementation boundaries

| File / function | Minimum change |
|---|---|
| `pyproject.toml` | Only core OpenCV requirement becomes `opencv-python<5`; preserve Python floor and other requirements. Include the justified shared helper in wheel/sdist and new tests in sdist. |
| `requirements.txt` | Same bound. CPU/Intel requirements-based images inherit it; no image-flavor migration. |
| `install.py::CORE_PKGS`, `step_core` | Bound the install string; separate OpenCV assessment from import-only checks; do not conflate distribution requirement string with import name. Probe the existing `PYTHON`, including frozen installer external-Python selection. |
| `openscrub_setup.py::main` Python sanity block | Use the same OpenCV assessment and repair text, retaining the independent Flask check. Remove broad unbounded OpenScrub reinstall advice specifically for the diagnosed OpenCV case. |
| `openscrub_internal/opencv_compat.py` and `__init__.py` | Small stdlib-only shared check/formatting module, justified by these two real consumers. Suggested boundaries: `probe_opencv(python_executable)` for bounded child-process collection; `assess_opencv(snapshot)` for pure decisions; `opencv_repair_hint(snapshot, python_executable)` for deliberate instructions. No installer engine or provider management. |
| `README.md`, `CONTRIBUTING.md` | Core repair/source-update instructions and explicit optional-Paddle limitation; document collection of the new tests with existing root tests. |
| `tests/test_opencv_compat.py`, `tests/test_install_opencv_compat.py` | Pure classification fixtures plus subprocess/pip spies for consumer behavior and metadata/archive assertions. Reuse existing runtime test fixtures where possible. |

The pin has no `openscrub_internal/` yet; this is the single proposed private
namespace already established in the delivery plan, not a reason to create a
new root helper. Add only this cohesive module. The subprocess collector must
be self-contained (for example a compact stdlib/cv2 `-c` probe carried by the
helper): the external interpreter chosen by a frozen installer cannot be
assumed to have OpenScrub or the helper installed. Normal setup also probes a
child process so an already loaded `cv2` cannot mask a changed environment.
Formatting can stay within this module; no generic command builder is needed.

New package contents matter: existing Hatch wheel/sdist includes are explicit.
Add `openscrub_internal/` to both relevant includes, retain current registries,
notices/icons, and include new `tests/` source files in sdist. The normal wheel
must not acquire bundled models or a private copy of OpenCV's XML. Haar data
continues to come from the chosen OpenCV wheel. An imported shared helper is
normally reachable by PyInstaller's static analysis; verify that in its platform
gate rather than adding unrelated hidden imports speculatively.

## Meaningful regression matrix and gates

| Case | Required result / evidence |
|---|---|
| All direct declarations and built wheel METADATA/sdist PKG-INFO | Exactly normal OpenCV `<5`, no new lower bound, Python >=3.9 preserved. Inspect archives using metadata readers; do not infer from source text alone. |
| Fresh missing cv2, zero cv2 distributions | `--check` makes zero pip calls; accepted normal install requests bounded main only; success is followed by fresh probe. Declined prompt remains missing. |
| Importable sole main5 | Both installer/setup visibly reject compatibility despite successful import; print bounded single-main repair and actual interpreter; no pip call merely from checking, normal mode or `--yes`. |
| Sole normal4, valid API/XML; same with cached YuNet | Health passes; no pip mutation. Cached model presence must not bypass the fallback check. |
| Normal4 missing API, missing XML, invalid/empty XML | Clear distinct issue; never healthy from import/version alone. Repair remains a deliberate bounded reinstall for sole main. |
| All six pairs among four flavors; three/four flavors | Conflict reported with versions/path even if runtime is4 and Haar appears usable; no flavor uninstall/reinstall or silent main addition. Parametrized metadata fixtures suffice. |
| Singleton contrib/headless4; source-built cv2 with no wheel metadata | Capability result retained with alternate/unmanaged warning; no forced normal wheel addition. Test >=5 and mismatched version variants too. No binary support claim from these simulated cases. |
| Probe import failure, corrupt output, timeout/crash, unknown version | Visible failure; no assumption that absence of parsed data means a fresh install or permission to replace packages. |
| Target interpreter differs from host | Both probe and any accepted fresh install use resolved target `PYTHON`; no helper import assumption in target. Use subprocess spies/fake child output, not environment modifications. |
| Real no-model Haar regression on supported normal4 | Existing production `FaceDetector` constructs and executes fallback with empty isolated cache and explicit fetch blocking. Preserve missing optional-ONNX fallback as well; no new model or positive-face accuracy claim required. |
| Existing verified cached YuNet | Production detector constructs/executes without download and retains existing behavior/default providers. Use the retained fixture; do not bundle/fetch a model just for this fix. |
| Optional installers | Verify existing CPU/GPU argv/provider/index choices remain unchanged in core fix. Document that current PyPI graph pins contrib4 but may create mixed flavors; no claim B02b protects GUI/web Paddle mutation. Include standalone's post-Paddle status warning in a focused final OpenCV recheck if it would otherwise finish with stale core success. This can reuse `step_core(check=True, ...)` or a small OpenCV-only reporter without reinstalling anything. |
| Built package data | Helper importable after wheel extraction/install in isolated validation; sdist can build wheel with helper included; existing registry/notices/icon payload retained; no model files added. |
| Existing source updater | Source update still has no pip reconciliation; repair/check docs accurate. A dependency migration must not appear as an updater side effect. |

For the standalone installer, its initial core success can become stale after
its own optional Paddle step. A final read-only OpenCV-only assessment is the
small necessary integration touch: append/report a distinct final status or
replace the earlier status so mixed flavors cannot end in `Install complete`.
Do not rerun the full core install logic, add hidden cleanup, or claim this
prevents Paddle's mutation. GUI/web completion/status hooks remain the named
Paddle follow-up, not part of this core compatibility PR.
When the final OpenCV result is incompatible, also suppress the existing
blanket summary that says everything else works and fallbacks cover gaps;
that reassurance contradicts the demonstrated unavailable-model face failure.

After implementation, run focused unit/integration checks, the current
authorized suite in the compatible isolated environment, and the required
sdist-then-wheel build. Avoid repeated broad runs after unchanged passing
results. This research ran none of them and makes no new runtime assertion.

Local implementation can verify metadata bounds/archive contents, all pure
diagnostic states, pip nonmutation, actual interpreter selection, and existing
Linux/Python3.12 normal4 Haar/YuNet fixtures. Fresh full dependency resolution
is still a future gate: the metadata queries here are not an install dry-run.
Use metadata-only dry-run/report where supported; do not silently download
large Paddle wheels to satisfy a purported metadata-only check.

Separate platform gates remain Python3.9 dependency resolution plus runtime,
Windows and macOS focused API/XML/runtime, Windows frozen artifact contents,
and GPU/CUDA execution. Current universal Paddle metadata and cp39 filename
listings prove none of those. Keep Python >=3.9 unless independent platform
evidence justifies a separately scoped change.

## Smallest task split

1. **B02b core installer compatibility:** bounds, the two shared check consumers,
   final standalone post-optional assessment, explicit nonmutating repair hints,
   source-update docs, focused regressions, and packaging verification. This is
   ready for a concrete implementation brief on the pinned Austin/B02a base.
2. **Paddle cv2 flavor policy follow-up:** desktop/web/standalone CPU/GPU flows,
   actual index/platform resolution, existing mixed installations, and clear
   pre/post-install health and deliberate ownership handling. Current pins
   already cover the named contrib dependency's `<5` need; additional blanket
   `<5` constraints would only guard future declarations, not fix coexistence.
   Choosing one flavor while satisfying both core and Paddle metadata is a
   packaging/provider design decision requiring dedicated evidence; do not use
   `--no-deps` or uninstallation to pretend both declared requirements are met.
3. **Independent platform/build gates:** retain source-CUDA defaults and existing
   provider choices. Default custom build is OpenCV4.10.0, with version override
   permitted in Docker/workflow; limited `BUILD_LIST` includes `objdetect,cudev`,
   not OpenCV5 `xobjdetect`. No default version bump here. Review/guard >=5
   overrides separately and verify actual cascade data/API in that custom
   build. No CUDA build, Windows/macOS/frozen build, or GPU inference was run.

## Research limits and retained evidence

No product/Git/user-environment change, installation, full build, inference,
model fetch, sustained benchmark, or subagent was performed. The only workspace
writes are this report and its supporting evidence. Temporary files are under
`/tmp/openscrub-opencv-install-scope-20261117`. Initial sandbox DNS failed;
approved read-only network access then retrieved only public JSON/index text.

Evidence: [PyPI declarations](opencv-install-scope-evidence/pypi-declarations.json),
[Paddle index observations](opencv-install-scope-evidence/paddle-cuda-index.json),
[GitHits package responses](opencv-install-scope-evidence/githits-package-evidence.json),
and [pinned source manifest](opencv-install-scope-evidence/source-manifest.json).
GitHits dependency results are retained for provenance; raw PyPI strings govern
extra/marker claims. The completed prior runtime evidence remains authoritative
for the concrete normal4/normal5 comparison and was not regenerated.
