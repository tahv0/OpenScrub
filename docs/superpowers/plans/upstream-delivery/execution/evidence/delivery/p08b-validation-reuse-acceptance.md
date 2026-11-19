# Reuse validation of an unchanged fresh thumbnail report

**Local acceptance:** `pr/thumbnail-validation-reuse` at `9bfb9d96865f0f67a58df868d5e167feb7b31212`, based on accepted thumbnail coherence `194864493962d9951cab482bde507d489f07c998`. The full task and scoped repair received independent specification and quality approval. Application composition and publication remain separate.

## What, why and delivery stage

Repeated metadata and cold-thumbnail requests parse the report and validate every row and cumulative offset again. On the tested POSIX filesystem, the existing generation already proves that the same report was validated. Reuse that proof only for a fresh private snapshot with the exact current generation, selected source, full opened-file stamps, paths, incarnation, operation and epochs. Recheck at selection; reuse cannot create a replacement generation or begin discovery.

Only the successful snapshot producer supplies the private four-value witness. Callers retain tuple compatibility and assign the cleanup lease before the new witness. First, changed and reconstructed snapshots validate the complete document. Metadata still fingerprints every raw row, including disabled and opaque data. Mutation documents remain fresh. Warm JPEGs remain parse-free; pre-generation retains its fully validated private-document path.

Recipe identifiers stay in `openscrub_internal/thumbnails.py`; coordination stays with its existing web owner. Regressions live in `tests/test_thumbnail_validation_reuse.py`. There is no retained report tree or new cache subsystem. This focused performance PR follows P08A and its source/lifetime prerequisites.

## Platform and identity limits

Reuse requires `os.name == 'posix'` and an adequate report-filesystem change timestamp. Windows and unknown OS families fully validate every fresh metadata/cold document. CPython's Windows ctime represents creation time in the supported versions, so same-size edits with restored mtime can retain all five stamp fields. [Python 3.9 stat documentation](https://docs.python.org/3.9/library/os.html#os.stat_result.st_ctime_ns), [Python 3.12 stat documentation](https://docs.python.org/3.12/library/os.html#os.stat_result.st_ctime_ns).

Actual-route tests simulate weak stamps with real writes and verify structured refusal for invalid unselected data and late cumulative offsets. Valid changed documents parse and fully validate on both requests. These are Linux-hosted simulations; native Windows was not run. Coarse/nonconforming POSIX mounts retain a timestamp assumption. The existing parse-free warm path cannot independently detect an external edit aliasing its entire stamp. No universal filesystem identity or heap-erasure guarantee is claimed.

## Matched Linux observations

Repeat the [accepted baseline protocol](p08b-report-read-baseline.md) with identical immutable inputs at A=`1948644` and B=`ed58a34`, before the platform-only safety narrowing. Final `9bfb9d9` verification is separate below; these timings were not rerun or relabeled.

Reports contain 1k/10k/100k rows and 181,417/1,797,631/17,959,368 bytes. A marked 256-frame MJPG source is 128×96 at 5 fps. Cheroot 11.1.2 ran on Linux/WSL2 with Python 3.12.16, OpenCV 4.14.0.94, NumPy 2.5.5 and FFmpeg/FFprobe 8.0.1.

| Rows | Metadata median A → B | Cold crop median A → B | Four cold crops A → B |
| --- | ---: | ---: | ---: |
| 1,000 | 25.39 → 19.30 ms | 20.38 → 14.64 ms | 69.08 → 45.24 ms |
| 10,000 | 249.84 → 189.27 ms | 88.35 → 29.47 ms | 364.27 → 108.66 ms |
| 100,000 | 2,514.22 → 1,914.54 ms | 784.35 → 194.95 ms | 3,374.88 → 883.41 ms |

At 100k, metadata through one fresh crop was3.5153→2.2829 s and metadata plus three cold crops 5.2374→2.9089 s. Warm medians were 1.165→1.128 ms. The single first-metadata observations were 2.6397→2.6528 s; no first-discovery gain is claimed.

Short workloads used three warmups/five measured repetitions; expensive100k shapes used one/three. Cold means a distinct derived JPEG; OS caches were not dropped. All 42 series and 576 timed response bodies remain recorded. Separate counters show fresh parsing on both; eligible steady validation falls from one to zero calls, or four to zero for four crops. First discovery validates once on both. Instrumented spans overlap and cannot be added to predict latency.

Memory did not improve: separate100k sampled four-cold peaks were 630.1→630.4 MiB and mixed peaks646.8→657.2 MiB. Corrected unseeded report-only and steady-combined controls are separate from earlier post-seed samples. Each memory shape has one observation and can miss brief peaks. The proposed 128 MiB retained-object budget belongs to an unimplemented future design; this change establishes no cap.

## Verification and source attribution

- Final `9bfb9d9`:492 affected/owning checks on Python 3.12.16 and 492 on actual Python 3.9.25, including real PAGE/browser, vault-source and lifecycle cases. Weak-stamp route tests first produced ten expected failures at `ed58a34`, with test hash captured before execution.
- Final fresh offline sdist→wheel→installed checks cover Cheroot metadata/cold/warm/304, invalid reports, replacement/old-version refusal, DELETE, module origins/defaults, CLI and updater.
- Final sdist SHA256 `e4c6365b7af745eb99c08cd8bf06b8dd75c1e2e87458b353f40d8e3e4c8d371b`; wheel `28f2f18009206eb57dcd6d98398a6496b8b009045797ed26f6e4373db0c83cb0`. Sdist has 51 source files plus generated metadata; wheel 18 source-mapped plus four generated entries. RECORD verifies 21 hashes plus itself. Three Docker COPY controls are unchanged; no container build was run.
- Earlier full native 896 and floor 477 checks remain at `ed58a34`. The incorrect initial full-suite setup and superseded discovery-fixture failure are preserved separately from passing profiles.
- Matched controls preserve complete normalized metadata, JPEG/detframe bytes/validators, report/source replacement refusal, master hashes, drained ownership, deletion and server reaping. Application source/runtime pins preceded execution; measurement-driver hashes were collected afterward. The earliest original RED lacked a contemporaneous test-file hash.

The inherited archive-extraction warning remains separate verifier maintenance. A corruption fixture's field-order sensitivity is nonblocking test maintenance; its assertion verifies that the intended field was invalid in the passing runs.

Reproduction uses the new module and existing thumbnail I/O/primitives/browser/PAGE, review-save, vault-source/job-source and lifecycle suites. Follow the linked baseline protocol for immutable reports, actual source readiness, replacement controls and fresh-server memory, keeping timing/counters/RSS separate. No inference, long-GOP/4K, Windows/GPU/frozen or combined-application performance is established.

[Canonical PR draft](../../pr-drafts/thumbnail-validation-reuse.md). Retained snapshots are deferred pending additional measured benefit and lifecycle/memory justification. P10B decoder measurements are next.
