# B03 / S01 baseline report evidence

Measured 2026-11-16 at Austin baseline
`5d3a15ae683c08f368d6ba4bd0d2d77b4e7b8e2f`. Research only: no product
changes, fixes, commits, inference, downloaded models, real jobs, or publication.
A Git archive was exported to `/tmp/openscrub-report-research-20261116/source`;
the active Save As worktree was not used. [Source verification](source-verification.json)
checks the imported engine/web/helper bytes against the pinned Git objects.

This promotes R05/R06's source-only failures to the actual Flask application.
The main script imports the entire unmodified modules and invokes the registered
route with ordinary request parsing, before/after hooks and Flask error handling.
Encoding/write failures run both through Flask's test client and a real
loopback-only threaded Werkzeug HTTP server. Overlap, replay, combined edits and
all timing samples use real loopback HTTP via `urllib`, with no browser or TLS.
The socket command needed approved sandbox escalation; a normal sandbox run
was blocked at socket creation before any request. No remote server was contacted.

## Confirmed baseline behavior

| Case | Real route result | Ordinary report outcome |
| --- | --- | --- |
| Encoder failure after destination opens | HTTP 500 in both transports | 107,533-byte valid report becomes zero bytes. |
| Injected interruption after 16 output characters | HTTP 500 in both transports | Report becomes 16 bytes of invalid JSON. Previous bytes are lost. |
| Two controlled overlapping sparse saves | Both socket requests HTTP 200 | Expected rows 1/2 `[false,false]`; actual `[true,false]`. Both read old data, row 1 publishes, row 2 overwrites its choice. |
| Identical manual request replay | Both socket requests HTTP 200 | 10 → 11 → 12 rows; appended rows are equal. Existing rows/other fields survive. First response is ignored before identical replay. |
| Combined enabled/box/time/audio update | HTTP 200 | All four updates persist; existing `suggest_allowlist` response remains correct. |

The race uses a bounded barrier at the real `_load_job_report` boundary and
waits for the first response before allowing the second stale document to
continue. It demonstrates a permitted execution, not random collision frequency.
Failure injection wraps the route's actual `json.dump`; file opening/truncation,
request handling and resulting bytes are real. Encoding and write injection were
tested; flush/replace failures and power loss were not. Baseline does not use
atomic replacement here. Synthetic fault tracebacks in [run.log](run.log) are
expected HTTP 500 evidence.

## S01 report/save measurements

Each sparse/no-op scenario has three warm-up operations and five measured
repetitions. All 30 measured requests returned 200. Sparse requests alternate one
row's choice on every operation; no-op sends an empty enabled map. Reports retain
ordinary cumulative motion and band histories, dense track/person fields,
manual rows, disabled choices, audio spans/suggestions/transcript and provenance.
Every field except the deliberately toggled enabled value compares equal after
measurement. Identifiers and formulas are fixed; there is no RNG or footage.

| Rows | Report bytes | Frames / duration | Dense / manual rows | Sparse median seconds | No-op median seconds |
| --- | ---: | --- | --- | ---: | ---: |
| 1,000 | 535,273 | 3,000 / 100s | 600 / 200 | 0.0471 | 0.0463 |
| 10,000 | 5,368,380 | 30,000 / 1,000s | 6,000 / 2,000 | 0.4573 | 0.4436 |
| 100,000 | 54,078,012 | 300,000 / 10,000s | 60,000 / 20,000 | 5.0744 | 4.7366 |

FPS is 30. Motion history has one pair per frame, with compact JSON lengths
34,201 / 342,501 / 3,425,001 bytes. Band history also has one pair per frame.
Distinct dense tracks are 200 / 2,000 / 20,000. Disabled row counts are
92 / 911 / 9,092. Sparse payloads are 22 or 23 bytes as the boolean changes;
no-op payloads are 14 bytes. Bulk-all-false payload lengths are
11,903 / 128,903 / 1,388,903 bytes; bulk latency was not measured.

Every sparse and no-op operation performs one report parse, one serialization,
and one direct report publication. A 100k no-op emits 54,078,012 characters via
9,880,143 Python stream writes even though resulting bytes are unchanged. These
are stream method calls, **not OS write syscalls**; Python buffering remains in
use. One `report_write_opens` count means the probe receives the already-open
real destination once for `dump`, rather than a syscall trace of every open.

Timings include the JSON stream accounting proxy, loopback HTTP, threaded server
and in-process client. The proxy adds Python work on every stream write, so
these are **instrumented baselines**, not an uninstrumented production latency
claim. Original source-isolated ~1.074s/100k evidence used a different minimal
24,866,772-byte fixture and remains a separate result; this report supplies no
before/after improvement or speedup claim.

Sampled total process RSS peaks during sparse/no-op scenarios were approximately
115/116 MB, 157/168 MB and 472/472 MB (decimal). Whole-process high-water RSS
reached approximately 757 MB at 100k, including fixture generation, HTTP client,
imports and observation buffers; this is not report-object retained memory.
`results.json` records RSS before, 10ms-sampled peaks and `ru_maxrss` separately;
they come from different kernel interfaces and need not match exactly. Large
reports are removed after their scenario. Videos and render snapshots remain
under `/tmp/openscrub-report-research-20261116/data`; no 250k stress case ran.

## N06 actual render/reopen preservation

This is an actual `run_pipeline --from-report` → `run_render` → `write_report`
execution, using 60 generated 160×96 MJPEG AVI frames and FFmpeg libx264. It is
render-only: no scan/model operation. Input is 36,660 bytes; output is 7,811 bytes
with 60 frames. Render completed in 0.185s (one correctness run, not a benchmark).

The report starts with 10 ordinary detections, seven enabled and three disabled,
including a disabled zone-dropped detection, two enabled manual rows and ordinary
dense track/person data. The successful render rewrites it as seven enabled rows.
The two disabled ordinary name rows and disabled zone-dropped person row vanish.
All seven remaining positional row indices shift; enabled dense track/person
values and both enabled manual rows survive. This establishes row/index loss,
not loss of the enabled `track`/`person` grouping fields. There are no custom
training identities or new manual-ID schema fields in this fixture.

Audio redaction spans survive equal. `audio_suggestions` and `audio_transcript`
are absent after the rewrite. Source inspection explains this additional loss:
`run_pipeline` reads those fields into `rstate`, then constructs the new render
`state` without them; `write_report` conditionally emits them only from `state`.
The input has no audio stream, so this checks report metadata and successful
visual rendering, not audible mute/bleep quality.

A fresh process imports the baseline again and performs real Flask test-client
GET `/api/jobs/reopen/detections` against a copy of that rendered report. It
returns HTTP 200 with the same seven rows, seven shifted indices and two manual
rows. [reopened-review.json](reopened-review.json) records the complete response.
This is route-level reopen evidence; browser rendering was not exercised.
Small [before](render-before.json) and [after](render-after.json) reports are kept
here as raw evidence. No preservation fix was applied.

## Reproduction and artifacts

Run from the repository root, with the existing isolated environment prepared:

```sh
mkdir -p /tmp/openscrub-report-research-20261116/source
git archive 5d3a15ae683c08f368d6ba4bd0d2d77b4e7b8e2f | tar -x -C /tmp/openscrub-report-research-20261116/source
. /tmp/openscrub-baseline-20261116/env-opencv4.sh
python .superpowers/sdd/README/report-baseline-research/run_report_baseline.py --source /tmp/openscrub-report-research-20261116/source --work-dir /tmp/openscrub-report-research-20261116/data --output .superpowers/sdd/README/report-baseline-research/results.json
python .superpowers/sdd/README/report-baseline-research/reopen_render_review.py --source /tmp/openscrub-report-research-20261116/source --work-dir /tmp/openscrub-report-research-20261116/data --output .superpowers/sdd/README/report-baseline-research/reopened-review.json
python3 .superpowers/sdd/README/report-baseline-research/verify_evidence.py
```

Host: AMD Ryzen 7 5800X3D, 16 logical CPUs, Linux WSL2, Python 3.12.16,
OpenCV 4.14.0, FFmpeg 8.0.1. Dependencies are listed in `pip-freeze.txt`
(collected via `importlib.metadata`; this venv has no pip module).
`ffmpeg-version.txt` records the installed encoder build. The initial research
run used an unsupported `--encoder cpu` fixture argument and exited after the
route regressions; its raw error is retained in `initial-argument-error.log`.
The final run uses supported `x264` and completes.

[results.json](results.json) contains exact byte counts, every measured timing,
operation counts, memory observations, environment, failure outcomes and source
hashes. [verification.log](verification.log) confirms all expected evidence
assertions, including 30 measured HTTP samples. Application filesystem cache
state is warm from repeated operations; OS caches were not dropped. No browser,
production WSGI/TLS/load test, Windows, restart rehydration after corruption,
tracking overlap, locking/deletion/vault race, real scan/inference or audible
audio check is claimed. B03/S01 overall remains incomplete: these targeted
regressions and measurements do not establish all preservation or browser gates.
