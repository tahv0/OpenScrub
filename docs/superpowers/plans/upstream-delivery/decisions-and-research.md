# Decisions and research for the OpenScrub delivery plan

Research date: 2026-11-16. This record separates the user's requirements, maintainer guidance, source observations, experiments and implementation proposals. Read it with the [delivery plan](README.md) and [preservation ledger](../2026-11-16-upstream-pr-map.md).

## Decisions from this conversation

| ID | Decision and reason | Where / when it applies |
| --- | --- | --- |
| D01 | Upstream always means Austin's `austinmabry/OpenScrub`; the user's fork is called remote and is configured locally as `origin`. | B01 and every branch/PR description. |
| D02 | Keep upstream's current behavior as the default. The planned assistance behavior is an option. | Every P task; O01–O05 selection and C01 default-equivalence checks. |
| D03 | Remove custom model creation, fine-tuning, training datasets/workflows, saved learned-model management and the expanded custom review system from the cleaned application. Preserve upstream's ordinary scan/review/render workflow. | B03 disposition, every extraction, C01 packaging/import audit. |
| D04 | Existing and published pretrained inference is acceptable, including YOLO and PP-OCRv5. Initializing a visual tracker or using an existing checkpoint is acceptable; it must not create a reusable training dataset. | O02–O05; no training extras in generic PRs. |
| D05 | Preserve all applicable performance, reliability, bug and UX improvements, especially long recordings, large files, 4K previews, saves, memory and resource bounds. | P01–P18 and B03. Reproduce applicability; record already-upstream/fork-only outcomes rather than silently forgetting a candidate. |
| D06 | Deliver focused PRs in the form Austin requested, not the integration branch as a large merge. | E–L cycle for every P task; assembled branch remains local/fork integration only. |
| D07 | Keep both tighter whole-plate geometry and optional lettering-only masks where pretrained/classical tools support them. YOLO's current boxes do not establish corners or character masks. | P17 for manual whole-plate geometry; O04/O05 for automatic/refined modes. |
| D08 | Retain optional full/partial plate-number search without training. A plate on the ground or a wall must be discoverable without a detected vehicle or YOLO plate. | O03 independent whole-frame OCR path. |
| D09 | Let users adjust confidence so uncertain detections can remain available for manual work without being automatically blurred. Separate candidate retention from automatic output. | O01; reuse existing candidate floor, add opt-in policy without changing upstream defaults. |
| D10 | When the user selects a detection, shape, text region or arbitrary object, follow it through the chosen footage interval. One frame's correction should reduce repeated work. | O02 seeded bidirectional tracking and correction keyframes; required for completed assistance workflow. |
| D11 | The user's preferred optional workflow minimizes unnecessary boxes, excessive blur and brief flashes. Uncertainty must not automatically produce broader masks or a compulsory review queue. | O01/O02/O05 and optional-mode success metrics. Suggestions/gaps remain actionable but may be left unhandled. |
| D12 | An aggressive Blur uncertain option may accept extra masks/flashes. It remains a distinct choice and does not redefine upstream's default. | O01; same evidence/geometry pipeline, separate output policy. |
| D13 | A lost target must not silently become a frozen box or a different object. In the optional assistance mode, stop unsupported propagation, keep visible gap status and let the user correct or leave it. | O02; output/report accurately reflects unresolved work without a new mandatory export gate. |
| D14 | Improve code/module structure in small justified steps; avoid accumulating new files at repository root or undertaking an unrelated rewrite. | S stage of every task, packaging checks in the owning PR. |
| D15 | Preserve old branches and runtime videos/jobs/datasets/weights. Removing code is not permission to delete data or reinterpret learned decisions. | B01, C01/C02. |
| D16 | Research and document what, why, dependencies, validation and delivery/PR timing for every task, so Austin's descriptions can be written from evidence. | This directory and the evidence template; fill actual results during V/D/L. |
| D17 | The existing Save As works well but needs visible activity and progress, specifically how much has been written out of the total. Use a bar and byte counter, elapsed time and an estimated remaining time when reliable. | P01, in the first Save As PR; separate from scan/render ETA. Preserve streaming and show finalization/failure honestly. |

## Maintainer guidance and acceptance boundaries

Austin welcomed separate Save As, explicit output-choice, four-corner-mask and Stop & Review contributions. For large saves and long-4K thumbnails he asked for synthetic/non-personal reproductions with report sizes and timings. He did not request the fork's custom confirmation-conflict recovery, SQLite journal or off-frame repair system. [Issue #22 response](https://github.com/austinmabry/OpenScrub/issues/22#issuecomment-6903629797), [issue #21 response](https://github.com/austinmabry/OpenScrub/issues/21#issuecomment-6902779771).

The contribution guide prioritizes conservative default redaction and human review. Its packaging/test workflow is concrete: run the existing suite, build through the sdist, exercise touched web behavior and render synthetic video for engine changes. The new assistance policy, number recognition and lettering-only mode therefore have separate acceptance questions; an opt-in flag does not imply maintainer approval. Keep them downstream while generic improvements proceed. [CONTRIBUTING at the researched SHA](https://github.com/austinmabry/OpenScrub/blob/5d3a15ae683c08f368d6ba4bd0d2d77b4e7b8e2f/CONTRIBUTING.md), [issue #21](https://github.com/austinmabry/OpenScrub/issues/21).

## Evidence levels

- **Source verified:** observed in the pinned implementation; not a measured user-visible failure.
- **Source-isolated probe:** the real function body exercised with a small synthetic environment; useful evidence, but not Flask/HTTP/browser/video integration proof.
- **Historical donor evidence:** measured or tested previously in the fork; not a current-upstream result.
- **External documentation:** a documented API/tool property; not local performance or accuracy evidence.
- **Proposed:** a design choice to implement and verify. Mark proposed numerical limits as such.
- **Integration verified:** reserved for a regression exercised through the real application on the stated base. None of the new tasks has reached that stage during this planning turn.

## Source findings

### R01 — upstream identity and newer fixes

The connected GitHub branch API was queried again on 2026-11-16 and returned upstream main `5d3a15ae683c08f368d6ba4bd0d2d77b4e7b8e2f`, matching local `main`. The donor tip remains `b4d0c75f25d91510fe1692f901d11853dc7db005`. All code observations below refer to that upstream SHA unless labeled donor. Austin's PhiMemory implementation and `a0b50a5` privacy fixes stay authoritative; do not restore the fork's older matching loop or isolated faulty regex commit. [Upstream commit](https://github.com/austinmabry/OpenScrub/commit/5d3a15ae683c08f368d6ba4bd0d2d77b4e7b8e2f), [privacy fix](https://github.com/austinmabry/OpenScrub/commit/a0b50a53655e8190d258bac541d0c7c841d7c098).

### R02 — Save As extends an existing download path

`job_download` already serves the real output extension through `send_file`; `job_report` already supplies an audit filename. P01 adds explicit destination choice and streaming UI behavior, not a claim that upstream currently buffers every download or gets extensions wrong. The browser picker requires user activation and a supporting secure context, so it must be invoked from the click before unrelated awaits and retain the existing direct-download fallback. Completion is tied to the stream operation, not fetch start. [Upstream downloads](https://github.com/austinmabry/OpenScrub/blob/5d3a15ae683c08f368d6ba4bd0d2d77b4e7b8e2f/openscrub_web.py#L1704), [MDN picker](https://developer.mozilla.org/en-US/docs/Web/API/Window/showSaveFilePicker), [MDN pipeTo](https://developer.mozilla.org/en-US/docs/Web/API/ReadableStream/pipeTo).

The user reports that Save As works but needs a progress indicator and written/total bytes. Inspection of `saveExportAs` at donor tip `b4d0c75` confirms the static `Saving…` label around `response.body.pipeTo(...)`, followed by `Saved` on completion, with no byte progress. P01 now includes that feedback in its first PR. This is source inspection plus user feedback, not a newly measured browser failure.

Count completed writes rather than received chunks. A write resolving means acceptance by the sink, not a physical-disk durability guarantee; the browser's file stream publishes changes on close. That supports a separate `Finalizing…` phase and success only after close. A valid matching response length supplies the denominator; unknown totals need indeterminate progress and a byte count. These are documented API properties, not a locally tested implementation. [Writer semantics](https://developer.mozilla.org/en-US/docs/Web/API/WritableStreamDefaultWriter/write), [file-stream finalization](https://developer.mozilla.org/en-US/docs/Web/API/FileSystemFileHandle/createWritable), [response length](https://developer.mozilla.org/en-US/docs/Web/HTTP/Reference/Headers/Content-Length).

### R03 — polling and save responses share mutable browser state

`openJob` resets global `CUR` and starts a 900ms interval. `refresh` awaits job and log responses while using mutable globals; `saveAndRender` also uses `CUR` across awaits, clears edit arrays after parsing a response and starts rendering afterward. These are concrete paths for delayed-response/job-switch regressions to investigate. The inspected upstream save code uses plain `fetch`; the fork's 15-second save deadline must not be described as an existing upstream timeout. [Polling](https://github.com/austinmabry/OpenScrub/blob/5d3a15ae683c08f368d6ba4bd0d2d77b4e7b8e2f/openscrub_web.py#L2114), [saveAndRender](https://github.com/austinmabry/OpenScrub/blob/5d3a15ae683c08f368d6ba4bd0d2d77b4e7b8e2f/openscrub_web.py#L2892).

### R04 — live preview publication is a separate problem from thumbnails

`WebCallbacks.scan_frame` overwrites `preview.jpg` through `cv2.imwrite`, throttled to 0.4 seconds. `job_preview` serves the path with `send_file`. P05 should test a reader observing replacement/publication and preserve bounded memory; no evidence yet establishes the frequency of an HTTP/JPEG race on actual deployments. It does not require the Findings cache or a new thumbnail service. [Producer](https://github.com/austinmabry/OpenScrub/blob/5d3a15ae683c08f368d6ba4bd0d2d77b4e7b8e2f/openscrub_web.py#L422), [route](https://github.com/austinmabry/OpenScrub/blob/5d3a15ae683c08f368d6ba4bd0d2d77b4e7b8e2f/openscrub_web.py#L1074).

### R05 — report handling: one parse/write, but no transaction boundary

`job_save_edits` loads once, applies only keys supplied in `enabled`, handles manual/time/box/audio changes, then writes directly to `report.json` using indented JSON. There is no atomic replacement or surrounding per-job read/modify/write lock in this handler. Manual entries append on each identical request. Thus P06's source-backed targets are publication/overlap correctness and measured serialization work; the fork's repeated-full-report bottleneck is not established upstream. P07 must separately address replay and browser state. [Handler](https://github.com/austinmabry/OpenScrub/blob/5d3a15ae683c08f368d6ba4bd0d2d77b4e7b8e2f/openscrub_web.py#L1290).

A same-directory temporary file and replacement can avoid exposing a partial file, but replacement alone does not serialize competing edits. Flush/fsync policy and platform behavior need explicit tests. Do not call atomic rename a universal power-loss guarantee. [Python file replacement](https://docs.python.org/3.9/library/os.html#os.replace), [Python fsync](https://docs.python.org/3.9/library/os.html#os.fsync).

### R06 — actual source-isolated report probes

[Probe script](research/probe_report_handler.py) extracts `_load_job_report` and `job_save_edits` from the pinned Git object, removes only route decorators, and supplies request/jsonify shims. It uses temporary synthetic reports, requires only Python's standard library, and touches no real jobs. [Recorded JSON](research/report-handler-results.json).

| Probe | Observed result | Meaning / next validation |
| --- | --- | --- |
| Sparse save, 1k / 10k / 100k minimal rows, three runs each | Median approximately 0.010 / 0.104 / 1.074 seconds; 100k report 24,866,772 bytes | A controlled baseline, not the fork's 20.5-second case and not a full long-video report. HTTP, browser, realistic motion history and other fields remain to be measured. |
| Exception injected after output writing begins | Previous bytes not preserved; resulting report is invalid JSON | P06 needs a production-route failure regression and atomic publication. |
| Same manual-region POST body invoked twice | Rows increase from 2 to 3 to 4 | P07 needs safe replay semantics if a response is lost; blindly retrying a request is not idempotent. |
| Two sparse saves read the same old report, then write in a controlled order | Expected enabled `[false, false]`; actual `[true, false]` | P06 needs serialization of the complete read/apply/publish operation; replacing files atomically alone cannot preserve both edits. |

Run from the repository root:

```bash
python3 docs/superpowers/plans/upstream-delivery/research/probe_report_handler.py
```

Environment: Linux, Python 3.14.4. The fixture's motion history is intentionally minimal; no video decoding, real Flask requests, browser testing, full application suite or post-fix measurement was performed. The default environment lacks the application's test/runtime dependencies. These results justify focused reproductions; they do not establish a complete fix or cross-platform impact.

### R07 — thumbnails already have a warm disk-cache path

`job_thumb` serves an existing `thumb2_<index>.jpg` without parsing the report. On a miss it reloads JSON, may try three timestamps, and each `_frame_at` call opens/seeks/reads/releases a `VideoCapture`. P08 must therefore target repeated cold-miss/report/listing work and correct invalidation, not claim every warm thumbnail reparses JSON. Browser cards already use lazy images, but `loadReview` constructs all group cards in one HTML string. P09 must preserve existing grouping while measuring DOM/request costs. [Thumbnail handler](https://github.com/austinmabry/OpenScrub/blob/5d3a15ae683c08f368d6ba4bd0d2d77b4e7b8e2f/openscrub_web.py#L1200), [review builder](https://github.com/austinmabry/OpenScrub/blob/5d3a15ae683c08f368d6ba4bd0d2d77b4e7b8e2f/openscrub_web.py#L2709).

### R08 — source time and exact frame selection need distinct contracts

`_frame_at` seeks using `int(t * fps)` while `job_frame_at` seeks timestamps and deliberately tries earlier times/zero when reading fails. A tolerant compare preview and a source frame used to save geometry are different contracts. P10 must not call a fallback frame the exact requested frame. FFmpeg input seeking also involves keyframes and decoding forward; a fast seek flag does not remove the need to validate returned timestamps/pixels. [Upstream frame helpers](https://github.com/austinmabry/OpenScrub/blob/5d3a15ae683c08f368d6ba4bd0d2d77b4e7b8e2f/openscrub_web.py#L1108), [FFmpeg seeking](https://ffmpeg.org/ffmpeg.html#Main-options).

### R09 — Docker and package layout already have useful structure

Upstream already places heavy requirements/model downloads before app source in CPU/Intel/CUDA images and has a separate scheduled security-refresh layer. The donor improves persistent pip download caching and moves refresh before app COPY; P13 must measure those deltas rather than claim to invent dependency-layer caching. Code edits should not rerun unnecessary apt work, but scheduled refresh must continue. [Upstream Dockerfile](https://github.com/austinmabry/OpenScrub/blob/5d3a15ae683c08f368d6ba4bd0d2d77b4e7b8e2f/Dockerfile), [CPU donor](https://github.com/tahv0/OpenScrub/commit/8fb396a).

The image workflow passes its run ID as the refresh argument and already imports/exports registry build layers. Measure a local source-only rebuild with an unchanged refresh argument separately from a CI build intentionally receiving a fresh one. Cache-mount persistence belongs to the builder; Docker specifically notes that GitHub Actions cache does not retain those mounts automatically. Do not infer cross-run pip-cache reuse from a local repeated build. [Upstream image workflow](https://github.com/austinmabry/OpenScrub/blob/5d3a15ae683c08f368d6ba4bd0d2d77b4e7b8e2f/.github/workflows/docker-image.yml), [Docker cache guidance](https://docs.docker.com/build/ci/github-actions/cache/).

`pyproject.toml` explicitly includes root modules in wheel/sdist. `update_source` already walks archive file paths and creates nested directories, so a private package does not inherently require rewriting the updater. Verify the distribution includes it and preserves data. PyInstaller uses static analysis plus explicit hidden imports for selected modules; only add hidden imports/data when the extraction requires them. [Packaging](https://github.com/austinmabry/OpenScrub/blob/5d3a15ae683c08f368d6ba4bd0d2d77b4e7b8e2f/pyproject.toml), [updater](https://github.com/austinmabry/OpenScrub/blob/5d3a15ae683c08f368d6ba4bd0d2d77b4e7b8e2f/openscrub_update.py#L140), [Windows spec](https://github.com/austinmabry/OpenScrub/blob/5d3a15ae683c08f368d6ba4bd0d2d77b4e7b8e2f/windows/openscrub.spec).

Hatch file-selection rules and pytest's recursive directory discovery support the proposed layout, but both require the owning PR's actual package/test command changes. Do not add an `openscrub/` package that shadows `openscrub.py`. [Hatch build configuration](https://hatch.pypa.io/latest/config/build/), [pytest integration practices](https://docs.pytest.org/en/stable/explanation/goodpractices.html).

### R10 — tracking exists; precise shape tracking does not follow automatically

Upstream `track_manual_region` already supports bidirectional user-seeded box tracking with pretrained VitTrack or template matching. Its weak/lost paths can emit widened/frozen score-zero boxes. The optional workflow must interpret those as uncertainty rather than approved masks. A tracked box is not a verified perspective quad. Do not require readable OCR or a YOLO hit in every frame when visual continuity is valid. [Upstream tracker](https://github.com/austinmabry/OpenScrub/blob/5d3a15ae683c08f368d6ba4bd0d2d77b4e7b8e2f/openscrub.py#L2438).

### R11 — previous pretrained-tool research remains applicable, not proven performance

- Reuse OpenScrub's current YOLO and OCR/text-region adapters first. The three registered YOLO exports return boxes/scores, not plate boundaries; PP-OCRv5 text-region detection can support lettering geometry without recognizing numbers.
- The fork's pure `plate_text_hints.py` already has a Tesseract/OpenCV search core. Its orchestration imports training/workbench helpers and its full-frame path rejects some partial matches. O03 decouples and corrects those paths rather than rewriting all OCR.
- [RapidOCR](https://github.com/RapidAI/RapidOCR) is an alternative full-frame text adapter; text polygons are not physical plate outlines. [fast-plate-ocr](https://github.com/ankandrew/fast-plate-ocr/blob/9ce7a5b64a939aa421c243b331d42e6bc25ffd44/README.md) is crop recognition and cannot replace whole-frame discovery. The [author confirmed MIT checkpoint licensing](https://github.com/ankandrew/fast-plate-ocr/issues/99#issuecomment-6303999259); its inspected Python/dependency requirements still need optional-runtime isolation from core.
- [EfficientViT-SAM](https://github.com/mit-han-lab/efficientvit/blob/de7d7733/applications/efficientvit_sam/README.md) is the first new box-prompted boundary candidate to evaluate. Its ONNX example still uses Torch/TorchVision. [SAM 2](https://github.com/facebookresearch/sam2) offers pretrained video propagation but a heavier runtime. Neither is a confirmed plate solution.
- [OpenCV optical flow](https://docs.opencv.org/4.13.0/d4/dee/tutorial_optical_flow.html) and [homography](https://docs.opencv.org/4.13.0/d1/de0/tutorial_py_feature_homography.html) can support a classical planar-quad experiment; drift/occlusion must be checked explicitly.
- Existing fork experiments reported missed glyph/plate fragments and occluder problems with GrabCut, EfficientSAM and Light HQ-SAM. Carry those fixtures forward; do not call a different SAM checkpoint a solved boundary feature before evaluation.

The earlier extraction outline contains the tool comparison and historical fixture references. No new models were installed or benchmarked during this planning turn.

## What research changes in the delivery plan

1. Promote P06/P07 correctness reproductions early; source probes give concrete interrupted-write, overlap and replay cases.
2. Keep throughput claims separate: the current upstream path differs from the fork's historical repeated-serialization case and has no observed 15-second browser deadline.
3. Make P08 distinguish warm disk hits, cold report loads and report/geometry revision changes.
4. Preserve tolerant preview behavior where intended while adding exact-frame semantics only for callers that need it.
5. Limit P13 to measured cache/refresh deltas; current upstream already caches major dependency layers.
6. Treat helper packaging and new test discovery as part of the owning PR; the updater's existing nested-path support is a check, not a pretext for a rewrite.
7. Keep new inference research and policy changes downstream until their own evidence and upstream scope are established.
