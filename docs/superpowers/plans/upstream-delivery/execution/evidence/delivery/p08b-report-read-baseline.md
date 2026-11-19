# Current report-read costs before retained snapshots

**Source and stage:** local P08A candidate `194864493962d9951cab482bde507d489f07c998`, measured 2026-11-19 after [thumbnail coherence acceptance](p08a-thumbnail-coherence-acceptance.md). Independent measurement review and the scoped evidence correction passed. This completes the P08B baseline gate; a performance implementation and its before/after evidence remain separate.

## What, why and when

Measure read-only metadata and derived images before choosing a cache. On this source, warm JPEGs already avoid report parsing, while four cold requests load and validate the same report independently. A smaller validation-reuse change is the next source study: the existing generation already records successful validation and the observed report/source identity. Its authority and invalidation rules must be checked before implementation. Retained snapshots remain conditional on useful gains, admission cost and memory.

These fixtures exercise report scale and resource ownership. They do not measure detector inference, real-video decode quality, 4K/long-GOP cost or optional assistance.

## Inputs and latency

The immutable ASCII reports have 1,000 / 10,000 / 100,000 ordered rows and 181,417 / 1,797,631 / 17,959,368 bytes. Rows include bounded text, repeated track/person IDs, disabled/manual entries, audio and an opaque field; no row exceeds 217 serialized bytes. One marked 285,246-byte MJPG clip supplies 256 frames at 5 fps and 128×96, with 256 finite cumulative offset pairs. Exact master hashes were recorded before requests and matched afterward. Absolute synthetic provenance paths contribute to these observed JSON sizes; a reproduction should pin its own fixed path and input hashes.

External clients fully consumed production Cheroot 11.1.2 responses over loopback, with 64 server threads. Python was 3.12.16, OpenCV 4.14.0.94, NumPy 2.5.5 and FFmpeg/FFprobe 8.0.1 on Linux/WSL2. Source, module, native-library and tool identities were recorded; each server checked the prepared tool environment and positive FFprobe readiness. First metadata bound actual 128×96, 5-fps, 256-frame source facts without a policy error.

| Median seconds | 1,000 rows | 10,000 rows | 100,000 rows |
| --- | ---: | ---: | ---: |
| Streamed report | 0.0019 | 0.0094 | 0.0828 |
| Metadata | 0.0253 | 0.2516 | 2.4977 |
| Metadata through a fresh versioned crop | 0.0468 | 0.3643 | 3.5261 |
| Cold crop | 0.0194 | 0.0872 | 0.8002 |
| Warm crop | 0.0012 | 0.0012 | 0.0012 |
| Four distinct cold crops, batch | 0.0685 | 0.3544 | 3.4703 |
| Metadata plus three cold crops, batch | 0.0818 | 0.5589 | 5.4768 |

Short workloads used three warmups and five measured repetitions. At 100k, metadata, metadata-to-crop, cold crop and both parallel shapes used one warmup and three repetitions. First discovery through the first crop was separately observed once: 0.099 / 0.406 / 3.692 seconds. Metadata-to-crop includes client JSON parsing for the real version. Cold means a previously unrequested derived JPEG, with distinct raw indices; operating-system caches were not dropped.

Batch timestamps begin just before the client release barrier and finish after collecting the futures. The exact barrier-release instant was not captured. Review bounded that timestamp's lead below 0.172 ms and the collection tail below 0.118 ms across the recorded native batches. All individual samples and completion offsets are retained locally. These are current-host observations, with no before/after speedup claim.

## Attribution and memory are separate observations

At 100k, steady metadata opened and parsed the report once and computed 100,000 row fingerprints. A separate instrumented pass observed enclosing JSON-load wall time of 0.1814 seconds, full validation 0.6615, row fingerprints 1.5131 and serialization 0.1781. The text-read subspan includes UTF-8 encoding for byte counting and counter locks. These single observations contain instrumentation overhead; parse/read/decode and snapshot spans overlap. They cannot be added to predict latency or a future cache gain.

Four cold crops loaded the report four times, reading 71,837,472 report bytes, with four decoder calls and peak four fills. Warm JPEG hits performed no report open, parse, validation or fingerprint call. Streaming the report read its exact bytes without JSON decoding.

Each memory shape used a fresh exec-started server. Fixtures, clients and full semantic validation stayed outside that process. Original sampling requested 20 ms; focused report-only and steady metadata-to-crop controls requested 1 ms. RSS and VmHWM are separate non-atomic kernel readings, and sampled peaks can miss brief spikes.

| Separate 100k observation | Sampled server peak, bytes | RSS after response close and owner drain, bytes |
| --- | ---: | ---: |
| Unseeded streamed report | 107,089,920 | 107,089,920 |
| Seeded metadata through fresh crop | 357,826,560 | 279,638,016 |
| Four cold crops | 660,869,120 | 370,585,600 |
| Metadata plus three cold crops | 677,851,136 | 396,685,312 |

The report-only server was about 106.6 MB at readiness and served no metadata or crop before the post-drain reading. The steady combined control seeded metadata and crop 0 before its window, then consumed metadata and crop 1 inside it. The original discovery shape remains a distinct first-discovery observation. Earlier report-only post-close readings taken after later seeding are explicitly labeled post-seed and do not supply the table's report-only value.

At 100k, the original warm-crop window had one sample; its lifetime high-water included earlier metadata seeding. The proposed 128 MiB retained-object budget is a future admission limit, not a process-RSS ceiling. Before large parallel work, effective cgroup headroom and MemAvailable both passed a conservative 4 GiB gate. Separate all-thread child sampling observed FFprobe peaks around 44.7–46.2 MB; its requested 5 ms interval can miss short-lived peaks, and those values were not added to server peaks as if simultaneous.

## Correctness and portable reproduction protocol

1. Pin the candidate source and prepared runtime, including the executable search path and native loader environment. Verify actual FFprobe source discovery before a full measurement batch. Check source-local migration/data paths before importing the application.
2. Generate and hash the bounded reports and marked clip once. Use fixed synthetic job paths and same-filesystem hardlinks. Register a tiny provenance/settings report through public guarded rehydration, then atomically install the measured master before first HTTP/source binding. Keep mutable report transactions outside this experiment.
3. Start a fresh production Cheroot server with out-of-band readiness. Measure the seven fully consumed HTTP workloads above; record first discovery separately, every repetition, cache state, system load and source/runtime identity. Put counters and allocation tracing in separate passes.
4. Use fresh servers for report-only, discovery, steady metadata, steady metadata-to-crop, cold, warm and both parallel memory shapes. Preserve ready, post-seed, timestamped request-window, post-drain and lifetime high-water observations. Take report-only post-drain RSS before any metadata/crop seed. Observe source-probe children separately.
5. Check report bytes against the immutable master and full metadata order/IDs/enabled/raw-row fingerprints. Earlier timed clients buffered the drained report before hashing; separate unseeded controls demonstrated incremental hashing in at most 65,536-byte chunks. Preserve cold/warm JPEG equality, ETags, current 304 and a detframe control.
6. Replace geometry through a same-length, distinct-inode report publication. The old version/ETag must be refused, and the new image must change. The actual decoded 88×96×3 arrays differed at 3,637 pixels, with maximum channel difference 146. Independent distinct-inode media replacement refused the old version with source conflict; unverified media was not forcibly reassociated.
7. Drain actual response/worker ownership, then require successful DELETE, absent job directory/registry entry and reaped owned servers. Recheck all master hashes and source preservation.

The first environment attempt lacked the prepared FFprobe path and followed the real missing-tool fallback. Its records are preserved and excluded from these native results. The older `944f6df` observations also have different instrumentation and post-save byte counts, so they are not a matched timing baseline. The full measurement harness/raw observations remain local; a portable benchmark should accompany any resulting performance PR.

## Next delivery gate

P08B now has a reviewed baseline. The next scope decision compares existing-generation validation reuse with immutable, single-flight report retention and declining an unjustified cache. Implementation must preserve whole-report rejection when identity changes, fresh mutation documents, source/report/operation fences, vault/deletion ownership and upstream defaults. A retained snapshot, if selected, needs owned-object accounting, oversized bypass, active-reader limits and measured admission/RSS costs. The owning focused PR supplies its actual candidate-versus-baseline measurements; this record supplies none in advance.
