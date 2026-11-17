# B02 OpenCV compatibility research

Date: 2026-11-17. Research only: no product, dependency, Git, user-data, model,
or environment changes. No new dependency/model installation, suite repeat,
container/Windows build, GPU execution, or accuracy benchmark was performed.
The requested report and its diagnostic artifacts are the only repository writes.

## Finding and proposed disposition

**The unbounded `opencv-python` dependency admits a concrete incompatible default
fallback configuration.** With the same empty model cache and blocked downloads,
the unchanged production `FaceDetector` constructs and executes Haar on
`opencv-python 4.14.0.94`; `opencv-python 5.0.0.93` raises `AttributeError` at
`cv2.CascadeClassifier`. Its `cv2.data.haarcascades` directory also lacks the
required XML. This is a last-resort face detection compatibility gap, not evidence
that every OpenCV 5 feature fails. With the same existing verified YuNet cache,
both environments construct YuNet and execute the focused detection calls.

Recommend a **separate, narrowly scoped compatibility candidate**: add the
`opencv-python<5` upper bound consistently to core package metadata, source
requirements, and the standalone installer; give existing unsupported installs
an actionable compatibility check/repair path. Preserve the present normal wheel
flavor and YuNet → Haar behavior. Do not introduce an arbitrary new lower bound,
exact global version pin, Python-floor change, custom model, or model training
from this evidence. The already approved OpenCV 4 validation environment remains
validation infrastructure; it does not itself change shipped requirements.

The candidate requires review/implementation authorization separately. No proposed
constraint or runtime repair has been implemented by this research.

## Pinned source and prior evidence

Production source is Austin upstream commit
`5d3a15ae683c08f368d6ba4bd0d2d77b4e7b8e2f`. The exported engine is
`/tmp/openscrub-opencv-compat-20261117/source/openscrub.py`, 413,860 bytes,
SHA256 `0e4f0f9a7846080f591038d021aaf3ca6f01201d83ac32bbdc273f53d5067ee7`.
It is byte-identical to `e21ebdf:openscrub.py` (the later baseline assertion
correction changes tests only). The active native P07 worktree was not imported
or edited. All 21 inventoried tracked files match the pinned source; hashes are
in [source-inventory.json](opencv-compat-evidence/source-inventory.json).

Read [task-1-report.md](../delivery/task-1-report.md), [task-1-review.md](../delivery/task-1-review.md),
the retained environment scripts/isolation harness, manifests, and previous
baseline diagnostics under `/tmp/openscrub-baseline-20261116`.
The earlier unconstrained suite produced 116 passed / 14 failed / 4 errors;
the separate OpenCV 4 + cached YuNet comparison produced 133 passed / 1 brittle
log assertion failure. The subsequent test-only correction yielded 134 passing
tests, as recorded by the supervisor's baseline work. These are prior results,
not reruns here. Because both dependency version and model availability differed,
that earlier comparison alone cannot isolate OpenCV as the cause of every failure.

Relevant production source paths/lines at the pin:

- `openscrub.py:5729`: three tiers are optional ONNX, built-in YuNet, then Haar.
- `openscrub.py:5815`: checks the local YuNet file; missing/small file triggers
  `_fetch_model` with the built-in SHA256 pin.
- `openscrub.py:5823`: a usable YuNet file and `FaceDetectorYN_create` lead to
  `_make_yunet`; successful initialization returns before Haar construction.
- `openscrub.py:5833`: unconditional last-resort `cv2.CascadeClassifier` with
  `cv2.data.haarcascades + "haarcascade_frontalface_default.xml"`.
- `openscrub.py:5879`: without an ONNX/YuNet backend, `find()` converts to gray
  and calls Haar `detectMultiScale(gray, 1.1, 5, minSize=(36, 36))`.
- `openscrub.py:4454`: `_make_yunet` uses the existing top-level create API.
- `openscrub.py:4690`: `OPENSCRUB_NO_AUTOFETCH` gates opportunistic prefetch,
  **not** the constructor's direct `_fetch_model` call. The diagnostic explicitly
  blocks that call, rather than assuming the environment flag suffices.

## Matched production probe

Both pre-existing isolated venvs use Python 3.12.16, NumPy 2.5.5, Linux WSL2
x86_64, glibc 2.43. Only the OpenCV package differs for this comparison.
Installed metadata reports Python `>=3.6` for both OpenCV distributions, and
`>=3.12` for this installed NumPy; that resolver outcome does not establish
OpenScrub's Python 3.9 support. The package flavor is **normal `opencv-python`**,
not contrib or headless, in both environments.

The probe imports the exact exported production engine by absolute file path;
it does not use an editable installation's possibly moving import target.
The only runtime substitutions are an explicit task-local model-directory
selector and `_fetch_model` that raises before any I/O. A Python audit hook also
rejects socket connection/address-resolution events; zero such events occurred.
`OPENSCRUB_FACE_MODEL` is cleared. No web module/user job paths are imported.
Default constructor options are retained, including threshold/expansion.

| Same input condition | OpenCV 4.14.0 (`4.14.0.94` package) | OpenCV 5.0.0 (`5.0.0.93` package) |
|---|---|---|
| Empty synthetic cache; model fetch blocked | Constructs Haar; `haar.empty()` is false; `find()` executes | Constructor raises `AttributeError: module 'cv2' has no attribute 'CascadeClassifier'` at line 5833 |
| Missing optional ONNX path + same empty cache | Logs missing optional model, then uses working Haar | Same constructor failure after logged YuNet fallback |
| Same verified existing YuNet cache | Constructs YuNet; `find()` executes | Constructs YuNet; `find()` executes |
| Missing optional ONNX path + same verified YuNet cache | Logs optional fallback, constructs/runs YuNet | Logs optional fallback, constructs/runs YuNet |

Each successful case ran `find()` on a black 320×240 BGR frame and deterministic
synthetic noise (NumPy RNG seed 1234), at scales 1.0 and 0.4. All returned empty
lists. These negative-input probes establish API execution, not positive face
recall, output equivalence on faces, image-quality properties, or end-to-end
redaction correctness. A real positive face fixture was not introduced.

Both empty-cache cases made exactly one intercepted YuNet fetch attempt and
logged the intended Haar fallback. Cached cases made none. The empty cache
stayed empty and the existing model's hash was checked before/after. OpenCV 5
emitted two warnings about target support in its new graph engine in cached
cases; both constructors and all eight cached detection calls still succeeded.

Existing cache used read-only:

- Path: `/tmp/openscrub-baseline-20261116/synthetic-data/models-opencv4/face_detection_yunet_2023mar.onnx`.
- Size: 232,589 bytes.
- SHA256: `8f2383e4dd3cfbb4553ea8718107fc0423210dc964f9f4280604804ed2552fa4`,
  exactly the production `YUNET_SHA256` pin and prior `yunet-manifest.json`.
- No new model fetch was performed. No optional/custom model was loaded.

### Installed API/data inventory

| Item | OpenCV 4 environment | OpenCV 5 environment |
|---|---|---|
| Top-level `CascadeClassifier` | Present | Absent |
| Any top-level name containing `cascade` | Six names, including constructor | None |
| `cv2.objdetect`, `cv2.xobjdetect`, `cv2.legacy` | Absent | Absent |
| `FaceDetectorYN` / `_create`, `FaceRecognizerSF` / `_create` | Present | Present |
| `QRCodeDetector`, `TrackerVit` / `_create`, `dnn` | Present | Present |
| `cv2.data.haarcascades` directory | Exists, contains Haar XML files | Exists, contains only `__init__.py` |
| Required frontal-face XML | Present; 930,127 bytes | Absent |

OpenCV 4 XML SHA256 is
`0f7d4527844eb514d4a4948e822da90fbb16a34a0bbbbc6adc6498747a5aafb0`.
The OpenCV 5 directory-path attribute alone does not prove cascade data is
installed. No `cv2.objdetect.CascadeClassifier` or `cv2.legacy` workaround exists
in either installed package. Inventory of the other APIs proves presence only;
they were not exercised beyond YuNet in this task.

Artifacts: [probe.py](opencv-compat-evidence/probe.py),
[OpenCV 4 JSON](opencv-compat-evidence/opencv4.json),
[OpenCV 5 JSON](opencv-compat-evidence/opencv5.json),
[OpenCV 4 stderr](opencv-compat-evidence/opencv4.log),
[OpenCV 5 stderr](opencv-compat-evidence/opencv5.log).
An initial harness attempt assumed the XML existed and failed in its metadata
collection before the OpenCV 5 cases ran. The harness was corrected to record
missing files, then both environments were rerun with the same final script.
That tooling error was not a product result.

## Dependency, image, installer, and update inventory

The tracked-file inventory covers all direct OpenCV declarations and applicable
indirect installation/update paths; raw search locations are retained in
[dependency-inventory.txt](opencv-compat-evidence/dependency-inventory.txt)
and [optional-installer-inventory.txt](opencv-compat-evidence/optional-installer-inventory.txt).

| Source at the pin | Current behavior / OpenCV 5 exposure |
|---|---|
| `pyproject.toml:10,37` | OpenScrub Python `>=3.9`; unbounded normal `opencv-python`. Applies to PyPI wheel/sdist installs, `pip install .`, editable installs, and `[ner]`/`[all]` extras (extras add spaCy, do not constrain OpenCV). |
| `requirements.txt:1` | Unbounded normal `opencv-python`; source/manual requirements installs accept 5. |
| `install.py:40,129–142` | Unbounded normal `opencv-python` in `CORE_PKGS`; installs only missing imports. Existing importable OpenCV 5 is reported as present, so changing the string alone will not repair it. Python check accepts 3.9+, frozen installer offers Python 3.12. |
| `install.py:180–212`; `README.md:344` | Optional `paddleocr` is installed without an OpenCV compatibility constraint. CUDA Dockerfile explicitly documents that PaddleOCR can install `opencv-contrib-python`; current Paddle transitive resolution was not installed or measured here. A constraint on the different distribution `opencv-python` alone cannot bound contrib/headless variants sharing `cv2`. |
| `openscrub_gui.py:80–91,376–379` | Source desktop GUI's optional engine commands install unbounded `paddleocr` for CPU and GPU paths through pip in the current interpreter. The GPU command pins PaddlePaddle, not OpenCV/PaddleOCR. spaCy is separately unbounded; no direct OpenCV package is listed. These commands carry no OpenCV constraint or post-install Haar check. |
| `openscrub_web.py:3410–3436,3452–3483` | Web CPU/GPU Paddle extras install unbounded `paddleocr` through pip in the running interpreter; GPU path uses Paddle's index and pins PaddlePaddle only. spaCy extra likewise uses pip. No OpenCV cap/reconciliation check; frozen installs are explicitly rejected. Optional Paddle can therefore change a different cv2 wheel flavor outside a main-package `<5` bound. Actual transitive versions remain unmeasured. |
| `fetch_plate_models.py:7,62–66` | Maintenance helper instructs a manual `pip install open-image-models`; does not install it automatically. Its transitive OpenCV choice was not resolved/tested here; it is not part of core runtime installation. |
| `openscrub_setup.py:206–211` | Checks only `import cv2, flask`; importable 5 passes. Suggested `pip install --force-reinstall OpenScrub` inherits the unbounded package declaration. No direct dependency installation is done here. |
| `openscrub_update.py:125–129` | Pip updater runs `pip install --upgrade OpenScrub==<latest>` without an additional constraint. May resolve 5 on a fresh/needed dependency resolution, or retain already installed 5; pip's default upgrade strategy does not mean every update upgrades every dependency. Corrected released metadata would govern pip's resolution. |
| `openscrub_update.py:141–184` | Source updater replaces release files from verified sdist; it does not install/reconcile Python dependencies. A new requirements file alone does not repair an existing source install's OpenCV 5. |
| `Dockerfile:25,42,64` | Python 3.12 slim; normal OpenCV wheel comes from unbounded requirements; app installed later with `--no-deps`. Prefetching YuNet can hide the fallback gap while that model remains usable. |
| `Dockerfile.intel:36,61–62,98` | Python 3.12 bookworm; requirements filter excludes only ONNX Runtime, retaining unbounded normal OpenCV. Later `--no-deps` app install does not re-resolve. |
| `Dockerfile.cuda:33,58–59,94–103,136` | Normal route is fixed source-built OpenCV base tag `4.10.0-cu126`; excludes OpenCV requirements, removes all four pip wheel variants after optional Paddle install, restores `/opt/opencv` cv2; app `--no-deps`. Not a default unbounded wheel route. No CUDA image was built/tested here. |
| `docker/Dockerfile.opencv-cuda:36,60–73,120` | `OPENCV_VERSION` defaults to 4.10.0 but is an overridable build arg. Both OpenCV/contrib checkouts use that tag; limited `BUILD_LIST` includes `objdetect,cudev`, not `xobjdetect`. Existing sanity prints YuNet/CUDA capability, not Haar/data availability. An override to 5 is not an established supported fallback build. |
| `.github/workflows/opencv-cuda-base.yml:29–32,70–74` | Manual version input defaults to 4.10.0 and has no major-version guard; can request unsupported source versions. Default consumer tag remains 4.10.0. |
| `.github/workflows/windows-installer.yml:38–41` | Python 3.12; `pip install .` resolves the unbounded core dependency before freezing. |
| `windows/build_installer.bat:7,21–34`; `windows/openscrub.spec:60–80` | Script documents Python 3.10+, installs PyInstaller/DirectML but uses existing cv2; spec freezes that environment. An unsupported installed OpenCV can propagate into the artifact. No Windows artifact was built/inspected. |
| `.github/workflows/publish.yml:28–32` | Floating Python 3.x builds distributions; no runtime installation/compatibility test. Publishes the metadata above. |
| `.github/workflows/docker-image.yml`; final security refresh layers in all three Dockerfiles | Workflow builds the three Dockerfiles. Security layers upgrade apt packages and pip/setuptools/wheel, not OpenCV explicitly; dependency layer rebuilds still inherit its declarations. |
| `README.md:286,301,318,398`; `CONTRIBUTING.md:20` | Documented pip install/update/editable flows inherit package metadata; no separate OpenCV cap. |
| `deploy/**`, `templates/**`, Winget/Inno installer entries | Deployment/image references or downloads/launch of prebuilt artifacts; no additional direct pip/OpenCV resolver found. Receive whatever OpenCV their artifact build supplied. |

No direct headless/contrib requirement is declared for core/CPU/Intel. Changing
to headless is a separate packaging/flavor decision and is unnecessary for this
compatibility fix. CUDA is a custom limited source
build with contrib's `cudev`, not an installed `opencv-contrib-python` wheel.
Python 3.9 is the authoritative package floor; CLAUDE prose and the Windows build
instructions say 3.10+. That existing mismatch is not resolved here.

## Official primary evidence and remedy options

OpenCV's [4-to-5 migration guide](https://github.com/opencv/opencv/wiki/OpenCV-4-to-5-migration#objdetect-haar-and-hog-moved-to-contrib)
states that Haar/HOG moved to contrib's `xobjdetect` and the Python
`cv2.CascadeClassifier` API requires contrib. It proposes YuNet for new uses.
OpenCV's [5.0 release overview](https://github.com/opencv/opencv/wiki/OpenCV-5#big-opencv-cleanup)
independently records that module move. These official mutable wiki pages were
read on 2026-11-17; they corroborate the installed-wheel observation rather than
superseding it.

GitHits inspected `opencv_contrib` snapshot
`b67a855188a3d683813731010f6d39ac614733a4` (2026-11-05):
[`modules/xobjdetect/include/opencv2/xobjdetect.hpp:229–274`](https://github.com/opencv/opencv_contrib/blob/b67a855188a3d683813731010f6d39ac614733a4/modules/xobjdetect/include/opencv2/xobjdetect.hpp#L229)
exports `CascadeClassifier`, filename construction, `empty()`, and the expected
`detectMultiScale` signature. This verifies an upstream contrib API declaration,
not the contents/correctness of a particular uninstalled Python wheel.
An initial GitHits lookup for `doc/MIGRATION-4-to-5.md` found no indexed file;
the release overview's actual migration-guide link supplied the official wiki.
No GitHits `quick_start` was called because the skill was loaded first.

The official [OpenCV Python package instructions](https://github.com/opencv/opencv-python#installation-and-usage)
distinguish main/contrib and desktop/headless flavors and require selecting
exactly one because all share `cv2`. The served default repository branch was
4.x: its example mentioning Haar files in all packages is not evidence that
this installed OpenCV 5 main wheel includes them. This probe finds it does not.

| Option | Assessment |
|---|---|
| Bound existing normal dependency to `<5` | Smallest source-compatible packaging remedy; focused 4.14 execution and earlier approved validation provide concrete evidence. Must cover all three direct declarations and existing-installer checking. Does not itself certify every historical 4.x build/platform. |
| Switch entirely to an OpenCV 5 contrib distribution | Officially documented location of the same API, potentially preserves Haar after verifying wheel bindings and XML. Requires replacing the main package, avoiding coexistence, evaluating optional installers, platforms, footprint, and the rest of the OpenCV 5 behavior. No contrib5 wheel installed/tested here; not ready as the minimal recommendation. |
| Rename to `cv2.objdetect.CascadeClassifier` / `cv2.legacy...` | Unsupported by installed inventory or the migration guide; do not invent this migration. |
| Require cached/downloadable YuNet and remove Haar | Focused YuNet calls work on both versions, but this sacrifices upstream's model-unavailable fallback and offline/degraded behavior. Bundling YuNet similarly changes packaging/defaults and does not cover model init failure by itself. Not equivalent to preserving the fallback. |
| Explicit unsupported-runtime error | Clearer diagnostics, potentially useful alongside constraints for manual/old installs; cannot preserve face detection fallback by itself. Do not silently return no detections. |

## Gates for the separate candidate

1. Keep product scope to compatibility declarations plus the minimum existing
   installer/runtime handling. Synchronize `pyproject.toml`, `requirements.txt`,
   `install.py`; ensure an importable unsupported cv2 cannot be labeled healthy.
   Define an actionable bounded reinstall for existing source installs because
   their updater does not reconcile dependencies.
2. Make optional Paddle and manual/frozen-source build exposure explicit. If
   those flows can replace cv2, carry constraints/checks through those flows or
   document the tested limitation. Do not co-install wheel flavors as a repair.
   Guard/review CUDA major-version overrides separately; the default 4.10 source
   build was not validated in this research.
3. Verify built wheel/sdist metadata and installer constraint behavior, including
   an already importable unsupported cv2. Run a focused model-unavailable
   regression with a real supported Haar API/XML, and retain a cached-YuNet
   regression. Then run the authorized suite in the compatible environment.
4. Establish wheel/dependency resolution and focused runtime coverage at the
   advertised Python 3.9 floor and intended Windows/macOS/Linux targets before
   making those compatibility claims. No floor bump is justified solely by the
   Python 3.12 experiment. GPU/container/frozen-build claims need their own runs.

Reproduction of **the performed focused experiment**, with the existing two
venvs and existing verified model already present:

```bash
mkdir -p /tmp/openscrub-opencv-compat-20261117/source /tmp/openscrub-opencv-compat-20261117/empty-models
git show 5d3a15ae683c08f368d6ba4bd0d2d77b4e7b8e2f:openscrub.py > /tmp/openscrub-opencv-compat-20261117/source/openscrub.py
. /tmp/openscrub-baseline-20261116/env.sh
python .superpowers/sdd/README/opencv-compat-evidence/probe.py > .superpowers/sdd/README/opencv-compat-evidence/opencv5.json 2> .superpowers/sdd/README/opencv-compat-evidence/opencv5.log
. /tmp/openscrub-baseline-20261116/env-opencv4.sh
python .superpowers/sdd/README/opencv-compat-evidence/probe.py > .superpowers/sdd/README/opencv-compat-evidence/opencv4.json 2> .superpowers/sdd/README/opencv-compat-evidence/opencv4.log
```

Both final probe commands exited 0 because the harness records expected product
exceptions in JSON; the OpenCV 5 unavailable-model cases are explicitly errors,
not hidden passes. Reproduction must keep the empty cache empty. Environment
scripts merely select the existing interpreters/library paths; the probe itself
owns source selection, fetch blocking, and cache isolation.
