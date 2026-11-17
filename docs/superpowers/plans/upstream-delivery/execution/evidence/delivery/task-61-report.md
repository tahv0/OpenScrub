# Task 61 — P06A atomic report publication

Implemented and locally committed as `c7cf1f02d98742e93a728e4b1e94d8c6bd02c318`
(`Preserve complete reports with atomic publication`) on
`pr/atomic-report-publication`, based on
`e21ebdf6e3ee46e6c65050dc956a9a3459152269` (Austin
`5d3a15ae683c08f368d6ba4bd0d2d77b4e7b8e2f` plus the independently reviewed,
two-line test-only prerequisite). Worktree:
`/home/tahv0/.codex/worktrees/c832/OpenScrub`. No Save As changes, version bump,
remote writes, downloaded models, user data, training, or subagents.

## Result and scope

An interrupted review save preserves the last complete report. The private,
stdlib-only `openscrub_internal.reports.atomic_report(path, report)` stages
UTF-8 JSON with the existing `indent=1` options in the destination directory.
`NamedTemporaryFile` creates an exclusive, restrictive POSIX 0600 file with a
`.tmp` suffix. The helper flushes and file-fsyncs, closes the staging file,
then calls `os.replace`. It raises on publication failure and attempts staging
cleanup in `finally`; cleanup errors do not mask the publication error.
Successful replacement leaves no staging name. Cleanup is best effort when
filesystem permissions or external interference prevent removal.

The three existing publishers use this boundary: engine `write_report`, Flask
`job_save_edits`, and `job_track_object`'s background append. Existing document
construction, arbitrary existing fields in web edits, defaults, JSON semantics,
face margins, and entry points are unchanged. The review route still returns
its existing success object only after publication; failures remain HTTP 500.
Tracking still accepts asynchronously with HTTP 200 and reports background
publication failure through `track_status`, with zero added rows and an error.

Hatch wheel and sdist include the package. The sdist also includes `tests/`;
CONTRIBUTING's test command collects both the original file and that directory.
The CPU, Intel, and root CUDA Dockerfiles copy the private package before
installation. `docker/Dockerfile.cuda` is untouched. Both runtime entry points
have static imports, so no speculative PyInstaller hidden-import edit was made.
The existing nested-path source updater is unchanged.

## Regression evidence

Raw logs and small synthetic verification scripts are in
[task61-evidence](task61-evidence/). The actual published tests are
`tests/test_large_report_io.py` (13 cases).

- **RED, actual Flask route:** encoding failure returned 500 and replaced a
  valid report with zero bytes; interrupted-write injection returned 500 and
  replaced it with `{"interrupted":`. Both preservation assertions failed for
  the intended baseline defect ([red.log](task61-evidence/red.log)). A broader
  pre-implementation run additionally failed because the helper API did not
  yet exist ([red-all.log](task61-evidence/red-all.log)); this is API absence
  evidence, not an independent baseline flush/replace corruption claim.
- **GREEN:** all 13 focused cases pass. Coverage includes encoding, partial
  write, explicit flush, fsync, and replacement failure through the registered
  save route; original report bytes and parseability; no staging leftovers;
  rehydration/review GET after every injected route failure; success response
  compatibility; first publication and POSIX 0600 mode; real nonserializable
  JSON values with existing/missing reports; successful and failed engine
  publication; successful and failed real background tracking publication.
  Only tracking inference/model discovery is substituted, not persistence.
- **Acknowledgement/readers:** a bounded gate holds the real replacement
  boundary. The complete new staged JSON exists in the same directory with
  the required suffix/mode, the save has not returned, and the ordinary report
  still contains the complete old bytes. After release the request returns 200
  with the existing allowlist suggestion/total shape and readers parse the
  complete new document, including preserved audio/custom fields. This tests
  old/new visibility at the controlled boundary, not exhaustive filesystem
  behavior or resolution of concurrent read/modify/write conflicts.
- **Real socket HTTP and fresh process restart:** a threaded loopback Werkzeug
  server received encoding and partial-write fault POSTs; each returned 500,
  preserved the old bytes, and removed staging. A new Python process imported
  the app, called `rehydrate_jobs`, recovered phase `review`, and returned 200
  for the real detection GET after each failure. An ordinary manual edit then
  returned `{"ok": true, "total": 1, "suggest_allowlist": []}`. See
  [runtime-results.json](task61-evidence/runtime-results.json).
- **Real engine:** a generated 60-frame 160×96 MJPEG input underwent a
  manual-only `run_scan` and `write_report`, the HTTP manual edit, and
  `run_pipeline --from-report` with x264. Output: 60 frames, 7,811 bytes, valid
  one-row report. This exercises engine publication and render without model
  inference. The initial scratch script attempted an unsupported `--scan-only`
  CLI flag; it was corrected to the actual `run_scan` API before the recorded
  successful run. No product CLI option was added.

## Commands and environment

Linux WSL2; Python 3.12.16; OpenCV 4.14.0; FFmpeg 8.0.1, inherited from the
specified baseline environment. All verification uses synthetic inputs.
Run source commands from the worktree unless another cwd is stated:

```sh
. /tmp/openscrub-baseline-20261116/env-opencv4.sh
python -m pytest tests/test_large_report_io.py -q --basetemp=/tmp/openscrub-task61/red
python -m pytest tests/test_large_report_io.py -q --basetemp=/tmp/openscrub-task61/green2
python -m pytest -q --basetemp=/tmp/openscrub-task61/full
```

The first bare full collection passed **145 tests in 73.47s** (134 baseline plus
11 initial focused tests). Two additional real encoding cleanup cases were
then added. Final full file/directory collection, using task-specific runtime
paths through the small `task61_isolation` pytest plugin:

```sh
export PYTHONPATH=/tmp/openscrub-task61:$PYTHONPATH
export PYTEST_PLUGINS=task61_isolation
python -m pytest test_openscrub.py tests/test_large_report_io.py -q --basetemp=/tmp/openscrub-task61/final
python -m build --outdir /tmp/openscrub-task61/dist
```

Final result: **147 passed in 76.67s**, with no failing tests. Full build:
**success**, isolated Hatchling 1.33.0 sdist, then wheel built from that sdist.
No production changes followed these checks; only the local commit and these
out-of-tree evidence/report files followed. `git diff --check` passed and the
committed worktree was clean. A final byte comparison also confirmed the
committed runtime modules match the built wheel and extracted sdist, and the
committed tests/pyproject match the extracted sdist.

From `/tmp`, with the same sourced environment:

```sh
python /tmp/openscrub-task61/verify_runtime.py
python /tmp/openscrub-task61/verify_packaging.py
```

The packaging script uses the existing bootstrap Python/pip to perform a
`--no-deps --no-cache-dir --upgrade --target /tmp/openscrub-task61/installed`
installation of the built wheel. It inspects wheel/sdist members, extracts the
locally produced source archive, and launches actual CLI and web module
`--help` startup from both locations with cwd outside the checkout. It also
checks imported file paths, so the checkout cannot silently satisfy imports.
The actual source updater consumes the local, SHA-256-verified sdist through
a substituted local response (no network): the nested helper files are installed
and synthetic job, model-placeholder, certificate-placeholder, zones and
allowlist sentinel bytes are unchanged. See
[packaging-results.json](task61-evidence/packaging-results.json).

## Durability/platform limits and follow-up constraints

File-fsync precedes replacement. Directory metadata is not fsynced. Atomic
replacement is not a universal power-loss guarantee; network/filesystem
semantics and storage can differ. Windows requires staging closure before
replacement, which the implementation does, but readers/antivirus holding the
destination can prevent replacement; that error propagates. POSIX modes do not
establish a Windows ACL guarantee. Actual power cuts, disk-full hardware,
Windows/frozen builds, browser interaction, network filesystems, GPU models,
TLS/production WSGI, and audible output were not tested.

`docker info --format '{{.ServerVersion}}'` failed with permission denied on
`/var/run/docker.sock`; no CPU/Intel/CUDA image builds ran. Full Docker builds
would also require model-fetching layers excluded from this task. No Windows
runtime or PyInstaller executable is available here. The Docker copy edits and
static imports are included, but their platform builds remain unverified.

**Concrete lifecycle risk discovered:** `openscrub_vault.encrypt_tree` and
`decrypt_tree` call `os.remove` on every `.tmp` path they enumerate, treating it
as a crash leftover. A live report stage deliberately uses that suffix to
preserve the existing convention. If a vault transition enumerates an active
stage, it can delete it before the publisher's `os.replace`, causing the save
to fail. The original report may also be undergoing ordinary vault encryption;
this helper alone cannot promise plaintext-path preservation against that
concurrent external mutation. A vault file-list snapshot taken before a new
stage is created can instead miss that stage. Save and background tracking do
not hold the vault lock for their whole report transaction, and review/tracking
are not busy phases in the vault exit/autolock checks. These are source-backed
race windows, not an executed vault-race regression or a claimed fix.

P06B must coordinate the complete **read → apply → publish** operation with
all report writers and job/vault lifecycle decisions; locking only this helper
cannot preserve overlapping edits or prevent every lifecycle race. Keep unique
same-directory `.tmp` staging, restrictive permissions, file sync, closed-handle
replacement, failure propagation, and cleanup semantics. Do not switch to an
unrecognized staging suffix to hide the lifecycle problem. Tracking remains an
async completion/status contract. P06D should change document reconstruction
and round-trip retention above this helper: it accepts the caller's entire
document and does not restore disabled rows or dropped metadata itself.
No retention, transaction locking, replay, serializer/no-op optimization, or
performance improvement is claimed by P06A.

## Self-review

Reviewed the complete diff against the brief. All three publication owners use
the same cohesive helper; other config/model/batch-summary writers are untouched.
The temp is never the ordinary report path, and file close precedes replacement.
Old reports survive every tested pre-publication error; failures do not become
successful acknowledgements. Existing JSON options and web response shapes are
preserved. Tests live in `tests/`, package inclusion is validated using built
artifacts and real imports, and updater behavior is tested without modifying its
implementation. Production-only changes are the helper, three call sites and
necessary distribution inclusion; no unrelated feature entered this branch.


## Fix round 1 — vanished staging names during vault cleanup

Independent review identified an Important compatibility regression distinct
from the previously documented ordering where vault cleanup removes a still-live
stage: if vault enumeration snapshots a stage, successful report publication
can remove that staging name before vault cleanup processes it. The resulting
`FileNotFoundError` used to abort encryption, preventing the vault key reset and
leaving remaining ordinary files plaintext. The supervisor explicitly expanded
P06A narrowly to resolve this temporary-cleanup compatibility issue.

Fixed in separate local commit
`66787aa09a958154e81e75f9bdc54d9788feb843` (`Tolerate vanished report stages during
vault cleanup`), following reviewed commit
`c7cf1f02d98742e93a728e4b1e94d8c6bd02c318`; no amend or remote write.
`encrypt_tree` and `decrypt_tree` now catch **only `FileNotFoundError`**, and only
around `os.remove` for an enumerated `.tmp` name. They continue processing the
remaining snapshot. Errors opening ordinary sources and other cleanup errors
still propagate. The atomic publisher, suffix convention, restrictive staging,
flush/fsync/close/replace policy, and best-effort publisher cleanup are unchanged.

The new `tests/test_vault_cleanup.py` adds eight cases:

- A bounded event-controlled interleaving runs actual `atomic_report` and the
  actual `_vault_lock_now` → `encrypt_tree` → `encrypt_file` path. Publication
  pauses before replacement, the vault snapshots the active stage first in a
  permitted enumeration order, publication completes successfully, and the
  vault processes the now-vanished stage before the ordinary report/input.
  The vault encrypts both ordinary files, resets the key to `None`, leaves no
  plaintext ordinary files, and real decryption recovers the complete new report
  and original synthetic input byte for byte. Only scheduling/enumeration order
  is controlled; report publication and encryption/decryption are real.
- Decryption tolerates the same vanished-name ordering and still removes an
  existing crash leftover while recovering ordinary files.
- Four parameter cases confirm generic `OSError` and `PermissionError` still
  propagate for cleanup in both directions.
- Two cases confirm a missing ordinary plaintext/encrypted source still raises
  `FileNotFoundError`, preventing accidental broad missing-file suppression.

**RED:** the controlled encryption/lock and decrypt-symmetry regressions failed
with the intended `FileNotFoundError`; six existing error-propagation cases
passed. Output: **2 failed, 6 passed in 0.09s**
([fix1-red.log](task61-evidence/fix1-red.log)). The narrow production fix followed
this failing run.

Commands from the task worktree, using the same synthetic baseline environment:

```sh
. /tmp/openscrub-baseline-20261116/env-opencv4.sh
export PYTHONPATH=/tmp/openscrub-task61:$PYTHONPATH
export PYTEST_PLUGINS=task61_isolation
python -m pytest tests/test_vault_cleanup.py -q --basetemp=/tmp/openscrub-task61/fix1-red
python -m pytest tests/test_large_report_io.py tests/test_vault_cleanup.py test_openscrub.py::test_vault_roundtrip_and_wrong_password test_openscrub.py::test_vault_tamper_fails_closed -q --basetemp=/tmp/openscrub-task61/fix1-green
python -m build --outdir /tmp/openscrub-task61/fix1-dist
```

**GREEN:** **23 passed in 0.94s**, clean output
([fix1-green.log](task61-evidence/fix1-green.log)); this includes all 13 atomic
publication cases, all eight new vault compatibility cases, and both existing
root vault tests. No new concern justified repeating the broad suite; the
147-test full result above belongs to the original reviewed commit, not a full
run of this follow-up. The scoped follow-up validation was authorized explicitly.

**Rebuild:** full isolated sdist → wheel build passed with Hatchling 1.33.0:
`Successfully built openscrub-1.0.96.tar.gz and openscrub-1.0.96-py3-none-any.whl`
([fix1-build.log](task61-evidence/fix1-build.log)). The focused packaging script
reads archive members directly, verifies the shipped vault bytes equal the
changed source and the report helper bytes remain equal to source, and verifies
the sdist includes both focused regression files. It installs that wheel under
`/tmp/openscrub-task61/fix1-installed` and verifies vault/helper imports resolve
there. It does not extract an archive, so the separately ledgered extraction
filter warning was not changed in this fix.

From `/tmp` with the same environment:

```sh
python /tmp/openscrub-task61/verify_fix1_packaging.py
export PYTHONPATH=/tmp/openscrub-task61/fix1-installed:/tmp/openscrub-task61:$PYTHONPATH
export PYTEST_PLUGINS=task61_isolation
python -m pytest /home/tahv0/.codex/worktrees/c832/OpenScrub/tests/test_large_report_io.py /home/tahv0/.codex/worktrees/c832/OpenScrub/tests/test_vault_cleanup.py --import-mode=importlib -q -o cache_dir=/tmp/openscrub-task61/fix1-installed-cache --basetemp=/tmp/openscrub-task61/fix1-installed-final
```

The installed-wheel focused run passed **21 tests in 0.09s**, clean output
([fix1-installed-final.log](task61-evidence/fix1-installed-final.log)); imported
runtime modules came from the installed wheel, with cwd outside the checkout and
pytest importlib mode. A first installed run also passed 21 tests but emitted a
cache-write warning because the checkout cache is read-only in the normal
sandbox; the final focused run moved only pytest's cache to task scratch.
[fix1-packaging.log](task61-evidence/fix1-packaging.log) records verified archive
members and installed paths; the corresponding small script is retained.

**Self-review:** inspected the complete two-file follow-up diff. Both catches
are limited to transient `.tmp` cleanup; ordinary file processing is untouched,
no general `OSError` tolerance or transaction design was introduced, and all
error-propagation regressions passed. Scheduling waits are bounded and the
publisher thread is joined before patches are restored. Existing crash cleanup
is preserved. `git diff --check` passed; the fix was committed locally with a
clean worktree. No production changes followed the tested snapshot.

**Remaining limits:** this resolves the successful-publication/vanished-stage
ordering without claiming complete vault coordination. The opposite ordering
(vault deletes a still-active stage), snapshots that miss new files, concurrent
ordinary-file changes, job deletion, and overlapping read/apply/publish edits
remain P06B lifecycle/transaction work. P06D still owns document reconstruction
and review-row retention. Docker/Windows/platform and power-loss limits above
remain unchanged; no platform rebuild is claimed by this fix round.
