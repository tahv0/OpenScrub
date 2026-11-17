# Task 64 / P06D: preserve review reports through rendering

Completed locally on `pr/report-roundtrip-preservation` in the managed worktree
`/home/tahv0/.codex/worktrees/c832/OpenScrub`.

- Base: `66787aa09a958154e81e75f9bdc54d9788feb843`.
- Commit: `7063082ef2a2ff5e56d9aafacff9bd43363b05b3`
  (`Preserve complete review reports through rendering`).
- Product range: only `openscrub.py` and `tests/test_report_roundtrip.py`.
- Working tree clean after the commit. No remote publication.

## Problem and result

The supervisor's [baseline evidence](../research/report-baseline-research/README.md) measured
an actual render changing 10 review rows to 7 and losing audio suggestions and
transcript. The enabled-only `load_report()` result was being used as the source
for report reconstruction. Audio metadata was read repeatedly and then discarded
while constructing the render state.

The new regression and standalone reproduction render 60 synthetic 160×96 MJPEG
frames through the actual `run_pipeline` / FFmpeg path. They retain **10→10** rows
in the saved report and in a fresh Python process's actual Flask GET
`/api/jobs/reopen/detections`, with seven enabled render rows. All 60 decoded
output frames check seven black enabled regions and three visible disabled
regions. The disabled cases are an ordinary Keep row, a zone-dropped row, and a
manual polygon. Enabled manual polygon and rectangle rows are also present.
This augments the baseline's ten-row fixture with disabled manual geometry and
additive metadata; it is not represented as byte-identical baseline footage.

[Standalone results](task-64-artifacts/summary.json),
[before report](task-64-artifacts/render-before.json),
[after report](task-64-artifacts/render-after.json), and
[fresh-route response](task-64-artifacts/reopened-review.json) preserve the small
JSON evidence. Synthetic video files remain in `/tmp/openscrub-task64-evidence`.
All three audio fields (`audio_redactions`, `audio_suggestions`,
`audio_transcript`) compare equal in the ordinary render.

## Implementation and compatibility

`load_report(path)` retains its public three-value return contract, its legacy
plain-list support, enabled-only decoding, and grouping/polygon values. A small
private `_decode_report()` function permits the from-report pipeline to decode
one already-read document. The pipeline parses the source report once and keeps
that full review document separately from decoded render objects. Nested polygon
lists are copied so render-time geometry changes cannot mutate the retained rows.

The report publisher starts from the retained document for from-report renders,
keeping every row in its original position, enabled choices, zone flags, manual
geometry, dense/track/person fields, optional field presence, precision and
unknown additive values. Saved render-state extras and audio metadata survive.
It overlays freshly calculated known provenance, including the real output
path/hash and current settings, while retaining unknown provenance/settings
fields. It removes stale output path/hash before overlaying the current result.

Explicit CLI `--audio-redact`, programmatic `audio_spans`, and an explicit empty
`audio_spans=[]` take priority over saved spans; the empty list clears the field.
`--audio-pii-apply` now receives saved suggestions and records the resulting
applied spans. These explicit audio changes legitimately replace the
`audio_redactions` representation with the effective canonical spans; ordinary
renders preserve saved span additive fields exactly. Suggestions/transcript and
other review metadata survive either case.

The scan-generated report branch retains its prior serialization behavior.
Legacy plain-list render-only input still raises the existing actionable
`no render_state — re-run a scan ... v4+` error. Distinct report destinations
leave source bytes unchanged. Same-path publication and failed replacement keep
the shared P06A atomic publisher. No training IDs, manual IDs, models, dependency
or version changes, locking, replay layer, repository abstraction, or unrelated
refactor were introduced.

Preservation concerns JSON values and field presence. Successful publication
still uses the existing atomic helper's JSON encoding, so whitespace/escaping
and byte formatting can change. A source report used with a different destination
is not rewritten and is verified byte-for-byte unchanged.

## Verification commands and results

All commands below ran from the managed worktree after:

```sh
. /tmp/openscrub-baseline-20261116/env-opencv4.sh
```

This uses synthetic runtime/model paths and prevents model autofetch. Python
3.12.16, OpenCV 4.14.0 (`opencv-python` 4.14.0.94), NumPy 2.5.5, pytest 9.2.0,
build 1.6.1. Isolated builds installed hatchling 1.33.0. Package and distribution
byte/hash checks are in [packaging.json](task-64-artifacts/packaging.json).

| Command | Result | Evidence |
| --- | --- | --- |
| `python -m pytest tests/test_report_roundtrip.py -q` before implementation | Exit 1; **10 failed, 3 passed**. Includes 10→7 row loss, metadata loss, and three source reads rather than one. | [RED log](task-64-red.log) |
| `python -m pytest tests/test_report_roundtrip.py::test_render_objects_are_separate_from_retained_review_rows -q` before implementation, with nested polygon mutation added | Exit 1; **1 failed** on loss/mutation of the saved review representation. | [geometry RED log](task-64-red-geometry.log) |
| `python -m pytest tests/test_report_roundtrip.py -q` after implementation | Exit 0; **13 passed in 2.99s**. | [GREEN log](task-64-green.log) |
| `python -m pytest -q --basetemp /tmp/openscrub-task64-full` after final source/test cleanup | Exit 0; **168 passed in 75.90s**. This is 134 root + 13 atomic + 8 vault + 13 new cases. | [full suite](task-64-full.log) |
| `PIP_CACHE_DIR=/tmp/openscrub-task64-pip-cache python -m build --outdir /tmp/openscrub-task64-dist` | Exit 0; full sdist followed by wheel **from that sdist**. | [build log](task-64-build.log) |
| `python /home/tahv0/src/OpenScrub/.superpowers/sdd/README/task-64-evidence.py --source /home/tahv0/.codex/worktrees/c832/OpenScrub --work-dir /tmp/openscrub-task64-evidence --artifacts /home/tahv0/src/OpenScrub/.superpowers/sdd/README/task-64-artifacts` | Exit 0; real engine, all-frame pixel checks, fresh-process Flask GET 200, 10 rows/unchanged indices, all audio fields equal. | [script](task-64-evidence.py), [log](task-64-evidence.log) |
| `git diff --check` / `git diff --cached --check` | Exit 0, before local commit. | Tool output; commit recorded above. |

Wheel bytes for `openscrub.py`, `openscrub_web.py`, and
`openscrub_internal/reports.py` match the worktree. The sdist carries byte-identical
new roundtrip tests and existing atomic/vault tests. Distribution files remain
under `/tmp/openscrub-task64-dist`. No installed-wheel test run is claimed.

The first local edit helper attempted unsourced `python` and did not execute;
it was rerun after sourcing the environment. The first implementation import
caught an unmatched closing parenthesis; that syntax error was corrected before
the GREEN run. Neither tooling correction is counted as behavioral RED evidence.
The final full suite has no failures or skips. There is no claim that a prior
full 155-case run existed; **168 is this task's fresh measured result**.

New regressions cover exact full-document review values, row order/choices,
rendered disabled exclusion, provenance refresh, fresh-route reopening, empty and
absent metadata, distinct paths/source bytes, successive renders, explicit audio
overrides/clear/apply, one source snapshot, nested geometry isolation, render and
publication failures, and legacy loading/error behavior.

## Self-review and limits

Performed a separate author self-review of the complete diff against the brief:
checked enabled-only public compatibility, scan branch behavior, provenance
ownership, raw-vs-decoded aliasing, explicit audio priorities, unchanged source
bytes for separate destinations, and P06A publisher reuse. No outstanding product
findings were identified. No subagents were spawned. This is author self-review;
the supervisor's independent review remains a separate gate.

The new integration fixture has no audio stream. Metadata preservation alone
does not establish audible mute/bleep quality. The existing root-suite audio
regressions ran as part of the full suite, but no additional listening, ASR,
model inference, browser, production server, Windows, or performance benchmark
is claimed.

**P06A dependency:** uses its existing shared atomic report publisher, packaging,
and tests, preserved on this base. **P06B boundary:** a parsed source snapshot is
not a transaction across rendering and later publication. Overlapping
edits/tracking/vault/deletion/lifecycle writers can still publish stale work;
coordination remains P06B. This change does not claim concurrent-writer safety.
The original checkout's product files/Git and user runtime data were not changed;
only these authorized SDD artifacts were written there.
