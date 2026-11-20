# Portable checkpoint data contract

The checkpoint helper is a data contract, not a complete Stop & Review feature.
This branch also has a monitored scanner boundary, completed-report frame
authority, and an opt-in web scan worker. A supported native progressive
8-bit H.264 MP4 scan with QR codes or no detection categories can stop at a
verified frame boundary. The worker fences report publication to its job and
persists a recovery marker before replacing the report. The Resume API requires
the exact current report-generation token. Partial rendering and editing are
not available in this slice; they require a separate bounded-review owner.
Older OpenScrub renderers do not honor checkpoint frame authority and must not
render bounded reports as if they did.

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
hash must match both provenance and the scan participant. Frame counts,
dimensions, bounds and track/person IDs are strict integers in the
interoperable range through 2^53−1. Values/arrays must be finite and
JSON-compatible, and render state FPS must equal the scan/timeline/marker FPS
exactly. FPS/count provenance
is descriptive; recording a reported count does not make it verified.
`count_source` records where the original canonical N came from; it remains
unchanged when later evidence verifies N.

`validate_resume(doc)` checks saved structure and internal identity.
`validate_resume(doc, source_sha256)` also accepts the scanned file's lowercase
SHA-256, but that checks **only** the scan participant. For a resume, the caller
must instead measure a complete current `options` snapshot and pass it as the
second argument; the helper compares all participants, normalization, timeline,
effective settings, and content identities. An initially reported but unverified
count may later be promoted from `count_verified: false` to `true`, with every
other identity value (including N and `count_source`) exactly unchanged. The
producer may assert this promotion only after it has independently established
that the **same hashed canonical scan source and normalization** have the exact
saved N frames, using an authoritative, hash-bound count/timeline or a decoder
termination signal that distinguishes clean EOF from failure. It must reject any
observed contradictory frame or changed source and retain the old checkpoint
when it cannot establish that evidence. A reported metadata count or `read()`
returning false by itself is not proof. A promotion establishes the count, not
that all selected work was scanned; completion still needs the separate proof
below. Do not run an unbounded second full-video pass merely to obtain this
evidence.

Validation alone does not update a report. A successful advancing merge persists
the promoted flag in both the provenance identity and a remaining paused marker;
completion retains it in provenance. A verified flag may never be downgraded. If
current verification is unavailable or any immutable identity value differs,
refuse the attempt rather than weaken or guess the saved identity. Before
publication, check selected sources again as required by the operation's
stability contract. A hash cannot itself keep a file unchanged during an attempt.

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
unknown/reported-only count without later successful verification, missing end
frame, stop request or `completed=True` alone is not proof. The engine must
reject contradictory observed frames and retain the previous checkpoint if it
cannot establish count/termination confidence. No decoder, EOF, concurrency,
crash durability, or actual rendering is tested or promised by this data contract.

## Engine boundary candidate

`run_scan(args, cb, stop_requested=callback)` is an opt-in engine-only boundary
probe. The callback belongs to one scan attempt and takes no arguments; a
caller using an event can pass `event.is_set`. It is distinct from
`cb.cancelled()`. The scanner checks for a stop between frames, after the
previous frame and its detection/skip accounting have finished. It closes the
primary decoder, runs the ordinary detection finalization, and checks Cancel
again before returning. Cancel still raises `PipelineCancelled`; an operation
owner must fence concurrent cancellation and publication separately.

The monitored path decodes sequentially through excluded windows instead of
using the existing seek shortcut, whose fallback can accept an unverified
position when PTS is unavailable. Excluded frames receive zero bands and, with
scroll tracking disabled, zero cumulative offsets. A monitored fast-stop after
the last selected window accounts for its last decoded excluded frame but does
not invent timeline rows for the unprocessed tail.

Only an opt-in result has `state["scan_boundary"]`. `next_frame` is its first
unaccounted exclusive index; `reported_total_frames`, `count_source` and
`fps_source` describe OpenCV metadata, not proof of canonical source length or timing. The `reason`
is `stop_requested`, `scope_fast_stop`, `decoder_invalid_frame`, or a
`decoder_read_stopped_*_reported_count`/`decoder_read_stopped_unknown_count`
status. A false decoder read is not distinguished from clean EOF. A decoder
exception raises `ScanDecodeError` after cleanup, carrying `next_frame`, the
reported count, and false verification/checkpoint flags; its original exception
is retained as the cause. Other exceptions propagate after decoder cleanup. A stopped zero-frame result, a missing or
contradictory reported count, invalid or mismatched reported/decoded dimensions,
invalid source FPS, or nonfinite or misaligned arrays cannot be a `prefix_candidate`.

`prefix_candidate` means only that a requested stop produced a plausible,
frame-aligned prefix with ordinary visual finalization. `checkpoint_available`
is **always false** in this engine slice. A post-scan hash does not prove the
input remained unchanged during scanning, identify the original or render
participant, establish normalization identity, or capture complete immutable
effective settings before the scanner mutates them. Those measurements and
revalidation, plus compatible frame-bound render handling, belong to later
integration work. `count_verified` is always false here, even when the decoder
stops exactly at the metadata count. An unverified engine state cannot be
rendered or serialized through the ordinary report builder. This guard does not
reject a valid, separately constructed partial report; a future compatible
renderer must honor its bounds and the partial-render policy above.

For a requested stop, whole-file audio transcription is deferred and
`audio_incomplete` records whether configured audio analysis was deferred. A
setup object track that extends beyond any monitored processed boundary is
refused rather than followed into unknown future frames with a fabricated
offset. This slice does not add context overlap, scroll-origin reconciliation,
checkpoint publication,
resume, a CLI or web action, or a verified completion proof.

## Completed-report frame authority in rendering

For a complete report, `scan_frame_start` and exclusive `scan_frame_end` are
optional **paired** strict integers satisfying `0 <= start < end <= N`, where N
is the length of the aligned full render timelines. Missing both fields keeps
legacy time-only behavior; missing one, nulls, booleans, nonintegers, reversed
or out-of-range bounds fail validation. This includes disabled raw rows. A
report carrying any `stop_review` marker is refused before rendering because
partial timeline, source identity, and geometry handling are not yet integrated.
This does not change the separate unverified engine-state guard.

The report decoder uses `FrameBoundedDetection`, a `Detection` subclass, only
for bounded rows. Ordinary `Detection` construction and `asdict` output retain
their previous shape; the bounded subclass serializes both fields explicitly.
Both renderers first intersect the existing time test with the original source
frame index and its half-open authority, then apply dense-sample deduplication.
A trimmed SDR render uses the original source index, not the output index, and
sequentially decodes the trimmed prefix because the existing seek fallback can
accept a position without reliable PTS. Ordinary unbounded trims retain their
seek optimization. Concealed coverage groups same-track samples only within
identical frame authority, preventing geometry from another segment from expanding an active
box. Other coverage modes retain the original bounds on their copies.

The raw report remains the authority for publication: rendering preserves its
row order, enabled choices, bounds and unknown fields. This engine slice does
not add bound-aware review overlays, time-edit semantics, partial rendering,
or the source/timeline proof needed to turn a scanner candidate into a report.
A renderer that ignores these frame bounds is not compatible with bounded rows.
High-level replay of a bounded report requires the already-computed scan-file
SHA-256 to match both report provenance and the saved scan participant, and the
P18A verified count and FPS to match the aligned report timeline. Missing or
mismatched evidence is refused before rendering. Legacy unbounded reports retain
their existing source-mismatch warning. For bounded HDR replay, scan and render
sources must resolve to the same underlying file; other mappings are refused
without a second full-file hash. Low-level `render`/`render_hdr` callers supply
and own their source/timeline compatibility themselves.

These checks trust the producer's hash-bound count attestation and do not
independently establish full normalization, source-participant, or cross-decoder
correspondence. Direct `run_render` callers must supply the actual precomputed
scan hash; `run_pipeline` computes it from the selected scan file. A source
can change after hashing unless the caller maintains its existing source lease
and stability rules. Distinct normalized scan and HDR render files require a
future source-frame correspondence contract before bounded replay is supported.

A bounded completed-report render checks the attested frame domain during its
existing decode pass. Full SDR and HDR output must receive exactly N complete
frames; any observed frame at or beyond N, a missing required frame, or an HDR
partial frame prevents publication. Bounded HDR also requires the decoder to
exit successfully. This applies even when every bounded row is disabled. A
trimmed SDR render checks the requested range and any extra decoded frame it
actually observes, without scanning the unrequested tail or claiming to verify
it. A contradictory decode leaves the previous report and video intact under
the existing render staging contract. OpenCV's false read does not by itself
distinguish a clean EOF from failure; the count check relies on the separately
attested N and the frames observed in this render.
