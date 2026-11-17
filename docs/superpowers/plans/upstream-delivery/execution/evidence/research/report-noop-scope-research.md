# P06C: unchanged saves and the smallest performance scope

Research complete on reviewed transaction head **`f2cdf4813c86296644911f3f0b09bfc56d3e03c5`**. An unchanged save still parses, serializes, fsyncs and atomically replaces the report. Skipping only unchanged publication is independently measurable and should be the first P06C subcard. Sparse/bulk serialization tuning remains a separate conditional subcard. No product implementation or speedup is claimed.

The experiment imported the full, unmodified Git export at `/tmp/openscrub-report-noop-20261117/export`; every one of its **124 tracked files** was compared byte-for-byte with its pinned Git object after the probe. The active native worktree was neither read nor imported. The delivery-plan and SDD documents were read from the supervisor workspace because they are not part of that export. [Results](report-noop-scope-evidence/results.json) contain import paths, exact source hashes, all request outcomes, before/after file metadata and assertions. [Probe](report-noop-scope-evidence/probe.py) is research evidence, not a shipped benchmark or replacement route.

## Current save route and boundaries

Source references below are relative to the pinned export:

- `openscrub_web.py:1163–1257`: auth, activity timestamp, vault/file-lifetime admission, release and response cache headers. File admission happens before route payload parsing. Failure still releases ownership. The request touches `LAST_ACTIVITY`; detached JSON releases its lease before the response transfers.
- `openscrub_web.py:1702–1761`: job lookup; `request.get_json(force=True)`; per-job `report_lock`; current identity/deleting/active-work checks; one `_load_job_report` parse; ordered enabled/box/time/manual/audio application; one `atomic_report`; suggestion derivation; success response. Missing report is 404; active scan/render or cleanup is 409. No request-independent empty-save return exists.
- `openscrub_internal/reports.py:7–43`: same-directory exclusive 0600 staging file, `json.dump(..., indent=1)`, explicit flush and fsync, close, replace, temporary-name cleanup. Publication exceptions propagate. Existing P06A platform/durability limits remain applicable.
- `openscrub_web.py:523–533`: `job_public` has no report revision or edited flag. This route updates no public phase/stats/options/log/output state, for either changed or unchanged data. No such field needs to be invented to implement P06C.

The normal route has **one request-JSON parse, one report parse, one report serialization/publication and one response-JSON serialization**. Successful publication includes one staging creation, explicit fsync and replacement. It also traverses every detection for sparse enabled patches and again for suggestions. P06C no-op skipping can remove report encoding/publication, but does not eliminate the necessary latest-report parse or existing detection traversals.

### Normalization and absent fields are the contract boundary

| Supplied operation | Existing behavior that must survive no-op detection |
| --- | --- |
| Empty request / absent maps | Still reads `detections` and `render_state`, publishes and computes suggestions. Omitting an optional stored value does not create its default. |
| `enabled` | Iterates existing row indices and matches their canonical decimal string keys. Assigns `bool(value)`: string `"false"` is truthy. Unknown/negative/noncanonical keys are ignored. Missing stored `enabled` plus explicit `true` inserts a field; stored `1` plus explicit `true` converts a number to a boolean. Both are changes. `enabled: null` currently raises 500, not a successful no-op. |
| `box_overrides` | Converts each key with `int`, then checks index and four-coordinate length, then converts coordinates with `float`. Same numeric integer coordinates can therefore become floats and change serialized representation. Noninteger key raises 500; out-of-range integer index is ignored before inspecting its value. Wrong length on a valid index is ignored. |
| `time_overrides` | Integer key, two-element span, floats and `t1 > t0 >= 0`. Accepted spans set both times and clamp `last_seen`; a numerically same span can insert missing `last_seen`, clamp a bad existing value or change time number representation. Invalid interval/length is ignored; conversion errors still fail. |
| `manual` | Each legacy item appends after time/box/reference-offset normalization. Equal geometry is not a no-op. P07b's identified replay is a future interface, described below. |
| `audio` absent | Leaves `audio_redactions` untouched, including absence and unknown nested fields. |
| `audio` explicit | Whole-list replacement. `null`/empty list becomes `[]`; valid intervals become float `t0`/`t1` plus `mode` (`mute` fallback); invalid intervals are filtered. Incoming extras are discarded. Existing extras on spans are removed by explicit replacement, so equal visible spans are not necessarily equal stored data. Absent audio field plus explicit empty list inserts a field and must publish. |

Conversions and filters here describe compatibility, not strong input validation. This research does not broaden validation, change existing 500s into 400s, require finite indexed values, change request coercion, or repair unrelated imported metadata. The current standard JSON publisher permits nonfinite numbers by default; future comparisons must handle these conservatively rather than introducing an unrelated stricter encoder.

## Bounded actual-route work-count observations

One probe run made **31 tiny synthetic Flask test-client requests** through the registered route and all normal hooks. It used the real atomic publisher, real temporary files, fsync and replace. There was no AST extraction, substitute route, socket benchmark, inference or model download. Results: **25 HTTP 200, one 400, one 404, one 409, three 500**. Every request released all file owners; all public-job snapshots were unchanged; no staging files remained.

All 25 successful requests performed one report parse, one dump, one staging creation, one fsync and one successful replace—even those with no effective change. Request and response JSON work are counted separately from report work. The canonical two-row fixture emits 1,601 ASCII characters in **358 Python stream `write` calls**; these are not OS write syscalls. Existing text buffering already batches OS I/O. A filtered/empty audio list emits fewer chunks. No elapsed times or speedups were recorded.

| Case | HTTP | Report bytes before → after | Typed report change |
| --- | --- | ---: | --- |
| Empty, compact original | 200 | 907 → 1,601 | None; original formatting lost. |
| Empty, canonical original | 200 | 1,601 → 1,601 | None; bytes equal. |
| Same enabled / box / time / normalized audio | 200 | 1,601 → 1,601 each | None; bytes equal. |
| One sparse enabled change | 200 | 1,601 → 1,600 | Only that boolean; unknown nested data and all other fields survive. |
| Audio omitted | 200 | 1,601 → 1,601 | None. |
| Audio explicit empty / already empty | 200 | 1,601 → 1,545 / 1,545 → 1,545 | Clear list / no data change. |
| Audio absent, omitted / explicit empty | 200 | 1,520 → 1,520 / 1,520 → 1,545 | Stay absent / insert field. |
| Stored enabled absent / number `1`, explicit true | 200 | 1,580 → 1,600 / 1,597 → 1,600 | Insert field / number→boolean. |
| Same numeric integer box → float box | 200 | 1,593 → 1,601 | Four number representation changes. |
| Same numeric integer times → float times | 200 | 1,595 → 1,599 | Two number representation changes. |
| Same span, out-of-range / missing last_seen | 200 | 1,601 → 1,601 / 1,580 → 1,601 | Clamp / insert last_seen. |
| Audio boolean endpoints → numeric floats | 200 | 1,604 → 1,601 | Two boolean→number changes. |
| Explicit audio removes stored unknown span field | 200 | 1,639 → 1,601 | Removes only the explicitly replaced span's additive field. |
| Ignored indices, wrong-length box and invalid time interval | 200 | 1,601 → 1,601 | None. |
| Invalid box index / null enabled | 500 | 1,601 → 1,601 each | No publication. |
| Legacy manual addition | 200 | 1,601 → 1,836 | One appended row. |
| Queued empty / malformed request / malformed report / missing report | 409 / 400 / 500 / 404 | Original or missing state retained | No publication. |

Every successful request replaced the file: device/inode identity changed, the fixture's fixed mtime changed, and mode **0640 became 0600**, even when bytes were identical. Results retain exact dev/inode/mtime/ctime/mode/size/hash before and after each case. Failed requests retained the entire metadata snapshot or missing state. This POSIX observation is not a Windows identity guarantee.

Same-value responses still returned `{"ok": true, "total": 2, "suggest_allowlist": ["synthetic-recurring"]}`. Changing the first enabled value to true returned an empty suggestion list. A no-op must preserve these responses and derive them from the fresh locked snapshot, rather than return a generic cached success.

The previous 1k/10k/100k evidence at `report-baseline-research/README.md` remains **instrumented baseline only**, on older pin `5d3a15ae683c08f368d6ba4bd0d2d77b4e7b8e2f`. For example its 100k no-op serialized 54,078,012 characters through 9,880,143 Python writes. Those measurements were not repeated and are not an exact transaction-head latency baseline or before/after comparison.

## Proposed P06C.1: skip unchanged publication

Use a conservative **presence-aware, type-aware comparison of normalized mutation destinations**. An unchanged operation leaves the original report bytes and file identity/mtime/ctime/mode intact, not merely equivalent decoded JSON. Reading may affect atime; do not promise to preserve atime. There is no existing report revision counter, so do not add revisions, journals or hash state to satisfy the plan's “bytes/revision” wording.

1. Keep existing auth/vault/lifetime admission, per-job lock, identity/deleting/busy gates and fresh parse. Even an empty payload must still fail on missing or malformed reports and remain coordinated with scan/render/tracking/deletion. Keep the ownership order documented in Task622; never release a lifetime under the report lock.
2. Run the same conversion, filtering and validation paths for every supplied operation. Do not short-circuit because earlier values were equal, or because the request looks empty before required report accesses. A later conversion/ID conflict must still fail the entire request without publication.
3. At each actual assignment destination compare **presence plus the existing raw value** with the normalized candidate. Missing `enabled` is not stored `true`; missing audio is not `[]`. A boolean is not a number. Preserve the current explicit int→float transformations even though Python equates `1`, `1.0` and `True`. Retain signed-zero distinctions when a normalized numeric assignment would change their emitted representation. Nonfinite/unusual imported values can conservatively count as changed; no coercion of additive metadata merely for comparison.
4. Compare only JSON-shaped touched values: scalar enabled/times/last_seen, four-coordinate box, or the explicitly replaced audio list. Compare lists in order and dictionaries by key presence and type-aware nested values; do not sort/drop/coerce unknown data. Explicit audio equality includes all stored keys so removal of an unknown key remains a real change. Keep existing assignment order.
5. A simple monotone `changed |= ...` is safe against missed persistence, but can unnecessarily publish if alias indices such as `"0"` and `"00"` mutate then restore a box/time field in one request. For an exact final-effective-data contract, retain original presence/value only for touched destinations and compare their final values after applying the whole payload. This bounded touched-field ledger avoids copying the report. If a first implementation deliberately allows this conservative false positive, document and test that narrower promise rather than claim every final no-op is skipped.
6. If any effective stored destination changed or a new legacy/identified row appended, call the existing `atomic_report` exactly once and acknowledge only after it succeeds. Otherwise skip report serialization, staging, fsync and replacement. In both paths derive the unchanged success shape/suggestions under the same transaction. Do not add an edited-state flag.

The ordinary boolean/time comparisons are constant work per touched field; box comparison covers four values. Audio replacement inherently normalizes its supplied list and compares that touched subtree, so its comparison cost is proportional to supplied/stored audio content, including nested unknown fields until a mismatch. A ledger may retain the original touched list while the normalized candidate exists; it is not zero-memory and bulk edits can touch many rows. The report parse and full suggestion/legacy enabled loops remain. Deepcopy plus whole-document equality would add allocation and traversal of unrelated motion/band/transcript histories; whole-document reserialization or a new digest would defeat much of the intended work saving. Do not add a cache or second synchronization scheme.

`openscrub_web.py:3341–3500` already records explicit same-value browser actions, submits them once and clears only unchanged submitted values/references after successful acknowledgement. Keep that behavior and the current HTTP success body. An explicit same-value Keep is acknowledged even when no disk operation is required; a newer toggle-back remains pending. Do not optimize by dropping the user's deliberate action in the browser, omit suggestions, skip response parsing or claim success for a refused save. Existing save-and-render logic must still request rendering only after the successful save response.

### P07b replay interface, not passing code

`task-72-brief.md` specifies job-scoped `manual_id` plus immutable effective `manual_creation`, checked inside the existing transaction. A matching replay keeps current mutable row fields and appends nothing; incompatible/ambiguous IDs fail atomically, and legacy no-ID additions still append. P06C should consume that eventual effective-change result: replay alone may skip publication; replay plus a real indexed/audio change publishes once; duplicate same-ID creations in one request do not invent a second append. Do not compare current mutable geometry with immutable creation data, skip conflict checks, deduplicate distinct IDs by equal coordinates or introduce report revisions. The researched pin predates that work; no P07b behavior was imported, executed or claimed passing.

## Proposed P06C.2: conditional serialization experiments

Keep this separate: no-op skipping has a clear operation-count outcome while sparse/bulk saves still need one complete report publication. A serializer change could affect every writer using `atomic_report`, including engine/CLI/GUI, and needs its own evidence and compatibility review.

- First compare readable-output batching with unchanged `indent=1` and all other encoder defaults. `json.dumps` followed by one write or joined encoder chunks can reduce Python write calls, but allocates the serialized string and potentially a chunk list at once alongside the parsed document and text encoding buffers. Lower stream-call counts are not evidence of fewer syscalls or lower HTTP latency.
- A bounded aggregation buffer over `JSONEncoder.iterencode` may avoid retaining the entire output string, at the cost of Python buffering work. Individual JSON string tokens can themselves be large; an aggregation target is not a strict memory ceiling unless token handling is accounted for. Existing `TextIOWrapper` is already buffered. `writelines` alone may simply move the iteration and needs measurement.
- Compact output (`indent=None`, `separators=(',', ':')`) changes the readable audit artifact and byte size even when meaning matches. Make readability an explicit product choice, not an assumed free optimization. Preserve ordering, Unicode/escaping policy, `allow_nan`, `check_circular`, `skipkeys`, key handling and no-trailing-newline behavior unless a separately approved compatibility change is intended. No new JSON dependency or encoder-private API is justified here.
- [Python3.9 introspection](report-noop-scope-evidence/python39-json.txt) confirms the public `dump`/`dumps` options exist in the actual 3.9.25 environment. In that runtime `dump` iterates chunks and writes each; `dumps` calls encoder `encode`; the C one-shot path is conditional on `indent is None`. Merely compacting `dump` does not guarantee that one-shot path. This is API/source inspection, not a Python3.9 application test or performance result.

## Acceptance gates and open choices

For P06C.1, add actual-route regressions showing unchanged canonical **and noncanonical** reports retain exact bytes, dev/inode and meaningful metadata on supported platforms; normalized same-value enabled/box/time/audio and ignored indices produce zero report dump/staging/fsync/replace; request parsing, fresh report parsing and response success/suggestions remain. Add sparse combined/unknown preservation, explicit empty-vs-absent fields, bool/number/int/float/signed-zero cases, last_seen clamping/insertion, alias-index restoration, invalid payload/error preservation and atomic write failure/waiter-release cases. On the reviewed P07b base add replay-only/replay-plus-edit/conflict coverage. Preserve P06B overlap/lifetime/gate tests and P07a emitted-JS same-value acknowledgement/newer-edit tests. These are proposed tests, not passing tests from this research.

For either performance claim, use identical deterministic realistic motion/band/dense/manual/audio/unknown-field fixtures before and after, exact before/after source SHAs and the same hardware/runtime. Separately measure actual no-op, true sparse toggles and real bulk changes. Warm both versions, alternate uninstrumented loopback HTTP samples between versions and report all statuses/sample counts/bytes with distribution summaries; do not present the earlier instrumented timings as the baseline. Measure parse/dump/staging/replace/stream-call counts in separate instrumented runs. Observe RSS before and during requests plus high-water/transient memory, accounting for fixture generation/imports/client buffers and serialization materialization. Do not ship a benchmark helper in the product as part of this research. Coordinate any repeated multi-second or memory workload with the supervisor while product verification is running.

P06C.1's expected independent outcome is one fresh parse and **zero report publications for a true no-op**, versus one of each for sparse/bulk changes. It makes no claim to accelerate sparse serialization. P06C.2 must demonstrate worthwhile sparse/bulk HTTP gains without unacceptable temporary memory or audit compatibility cost; close it if measurement does not support a change. Focused/full tests, packaging and relevant browser verification belong to the eventual implementer after changes, not this research run.

Open choices are the tolerance for conservative false-positive writes on exotic numeric values, whether an exact alias-restoration ledger is worth its small extra complexity, and whether compact audit JSON is acceptable at all. Recommended first scope preserves all existing normalization distinctions, covers ordinary finite values exactly, and keeps readable serialization unchanged.

## Reproduction and limits

```sh
mkdir -p /tmp/openscrub-report-noop-20261117/export
git archive f2cdf4813c86296644911f3f0b09bfc56d3e03c5 | tar -x -C /tmp/openscrub-report-noop-20261117/export
. /tmp/openscrub-baseline-20261116/env-opencv4.sh
python /tmp/openscrub-report-noop-20261117/probe.py > .superpowers/sdd/README/report-noop-scope-evidence/run.log 2>&1
```

The evidence copy of `probe.py` can be placed at that `/tmp` path for reproduction. It asserts imported paths, verifies all tracked export bytes and records Python/platform data. Models reuse the supplied fixture location with downloads explicitly blocked; all synthetic job files are under this task's `/tmp` root. [Input hashes and commands](report-noop-scope-evidence/inputs-and-commands.txt) identify the supervisor-side documents and stdlib inspection command.

No product edits/commits, native-worktree imports, subagents, dependency/model installs, publication, real user data, repeat 1k/10k/100k workloads, full suites/builds, browser sessions, render/media work or latency/memory benchmarks ran. The bounded route probe used Python3.12.16 on Linux/WSL, not configured network HTTP/WSGI or another OS. Source inventory and future acceptance gates are distinct from this measured route evidence. No caching, JSON canonicalization, durability expansion or general revision/recovery protocol is proposed.
