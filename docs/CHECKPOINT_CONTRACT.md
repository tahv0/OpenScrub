# Portable checkpoint data contract

This is the data-only first part of Stop & Review. It does not implement scan
stopping, resume, partial rendering, publishing, restart, or user controls.
Existing OpenScrub renderers do **not** honor checkpoint frame authority and
must not be used to render these reports as if they did.

The three functions in `openscrub_internal.checkpoints` consume and return
plain JSON documents. They do not mutate arguments or write a file. Publish a
successful result through `openscrub_internal.reports.atomic_report` under the
caller's existing operation and report transaction; a rejected merge must not
replace the old report. A no-progress stop must leave the old report bytes and
file identity unchanged. The helper raises `CheckpointError` on invalid input.
The old donor schema is incomplete and is rejected: start a fresh scan or use
an explicitly designed migration, never guess its missing identity.

## Producer identity

`with_checkpoint(doc, frame, total, options)` accepts the final raw scan
report and a complete identity snapshot. The caller must construct the identity
from the actual selected source files and resolved effective inputs, before
mutable scaling/popping of scan settings. An example shape (hashes abbreviated
here only):

```json
{
  "sources": {
    "scan": {"sha256": "<64 lowercase hex>", "width": 640, "height": 480,
             "fps": 30.0, "fps_source": "<measurement/probe provenance>"},
    "original": {"sha256": "<64 lowercase hex>", "width": 640, "height": 480,
                 "fps": 30.0, "fps_source": "<measurement/probe provenance>"},
    "render": null
  },
  "normalization": {"mode": "none", "target": "none", "transform_version": "none"},
  "timeline": {"fps": 30.0, "fps_source": "<provenance>", "total_frames": 900,
               "count_source": "<provenance>", "count_verified": false},
  "effective_settings": {"categories": ["face"], "...": "<resolved scan inputs>"},
  "file_identities": {"<selected model or file input>": "<64 lowercase hex>"}
}
```

The example is schematic; `effective_settings` must contain **all** inputs that
can change scanning, including complete windows, zones, ignore regions, measured
duration mapping, sampling/adaptive/scale thresholds, engine selection,
tracking and backtracking, NER/heuristics/regex/phrase/name/allowlist contents,
manual setup tracking, and relevant audio and normalization settings. The
producer supplies SHA-256 of every selected file-backed input/model in
`file_identities` (an empty object is valid only when none are used). Resolve
configuration defaults and contents, not path strings, mtimes, or defaults as
proxies for content. Exclude output/render style, transport paths, events and
resume position. A JSON snapshot comparison cannot prove a producer captured
every relevant input; establishing completeness and stable files is an owning
engine obligation. All selected source roles are explicit; `render` is null
only if there is no separately selected render participant. Any additional
selected participant must have the same digest, dimensions, FPS, and FPS-source
fields. Record real FPS and
its origin for each participant, and canonical count and its origin in the
shared timeline. Original and scanned files may be the same bytes. Actual
source hashes and metadata must be measured, not inferred from a saved path.

The marker has schema 2, `state: "paused"`, `next_frame`, `total_frames`,
`fps`, `input_sha256`, and `options`. The same options are saved under
`provenance.checkpoint_identity` so the identity survives completion. The scan
hash must match both provenance and the scan participant. All integers are
strict integers in the interoperable range through 2^53−1, values/arrays must
be finite and JSON-compatible, and render
state FPS must equal the scan/timeline/marker FPS exactly. FPS/count provenance
is descriptive; recording a reported count does not make it verified.

`validate_resume(doc)` checks saved structure and internal identity.
`validate_resume(doc, source_sha256)` also accepts the scanned file's lowercase
SHA-256, but that checks **only** the scan participant. For a resume, the caller
must instead measure a complete current `options` snapshot and pass it as the
second argument; the helper compares all participants, normalization, timeline,
effective settings, and content identities. Before publication, check the
selected sources again as required by the operation's stability contract. A
hash cannot itself keep a file unchanged during an attempt.

## Boundary, rows and merge

`frame` is the first unprocessed frame b, with `0 < b < N`. The entire prefix
`[0,b)` has finished ordinary postprocessing; this may include explicitly
out-of-scope frames and does not claim inference ran on every frame. `cum` and
`bands` must each contain exactly b finite two-vectors. The first checkpoint
producer supplies its generated rows; each receives the paired strict integer
`scan_frame_start: 0` and exclusive `scan_frame_end: b`. Later review-created
rows may omit both fields. One present without the other, invalid bounds, or a
non-finite/invalid original time is rejected. These fields intersect existing
time activity and are retained after completion. A consumer that ignores them
is not a compatible checkpoint renderer. No timestamp is shifted.

`join_reports(previous, continuation, next_frame, total_frames, completed=False)`
requires b < e <= N; partial progress ends before N, completion ends exactly
at N. The continuation must contain only new generated/context rows (never a
second copy of prior review rows), a full finite aligned timeline through e,
and its freshly measured identity in `provenance.checkpoint_identity`. Before
calling, the engine must align its continuation's scroll origin with the prior
report and ensure all source/settings and array values reflect the same
coordinate system. This helper does not invent the needed alignment. Bounds for
new rows are intersected with `[b,e)` and with their original time activity;
rows with no applicable frame are dropped. Distinct nonnegative track/person
IDs are mapped to fresh namespaces above the prior maxima. Previous rows, their
order, choices, manual/replay data, unknown fields and audio redactions stay
unchanged. Existing output path/hash provenance is invalidated on advancement.
On completed resume, missing machine audio suggestions/transcript may be
filled from the continuation; an existing field, including an empty array,
remains untouched, and redactions are never imported from the continuation.

For `completed=True`, the continuation must additionally carry:

```json
{"scan_completion": {"reason": "accounted_verified_range",
                     "next_frame": 900, "total_frames": 900}}
```

Both counts must equal N and `timeline.count_verified` must be true. This is a
producer attestation, not a decoder operation performed by this module. It may
be supplied only after every index in the verified canonical range has been
accounted for and normal finalization has succeeded. An early read failure,
unknown/reported-only count, missing end frame, stop request or `completed=True`
alone is not proof. The engine must reject contradictory observed frames and
retain the previous checkpoint if it cannot establish count/termination
confidence. No decoder, EOF, concurrency, crash durability, or actual rendering
is tested or promised by this data contract.
