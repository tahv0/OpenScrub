# Exact CFR decoder for checkpoint scans

`pr/checkpoint-cfr-decoder` at `07510a457451ca1692716f7510e81e76ca8f22d1` follows the [completed-checkpoint renderer](completed-checkpoint-frame-bounds.md). It supplies the frame evidence needed to continue a scan over the same source timeline.

| What | Why | When to deliver |
| --- | --- | --- |
| Decode supported progressive 8-bit H.264 MP4 in one FFmpeg frame stream. Check the absolute source PTS, dimensions and consecutive index on each read, including after a bounded seek. | The previous scanner can report where it stopped. Its ordinary OpenCV reader cannot certify source index or distinguish normal completion from a failed read. | As a separate engine prerequisite to the verified checkpoint producer. |
| Hold the reported frame count as provisional until observing the complete requested range, equal count and successful decoder termination. Bound the wait if the decoder emits pixels without usable frame metadata. | A stopped prefix and decoder diagnostics can otherwise be confused with a completed scan, or wait indefinitely on each other. | Verify real MP4 with B-frames, premature stop, incorrect counts, missing metadata and cleanup before wiring the live scan. |

The final source passed 111 selected tests on each of Python 3.12 and 3.9. The isolated installed wheels passed the same 111 tests on each version. The real overlap seek produced frames pixel-identical to the same indices in sequential decoding. The supported subset requires one progressive H.264 video track, even dimensions, zero start and an exact integral CFR timestamp cadence. Codec, timeline and color transforms need their own acceptance. The next producer layer still binds source, effective scan settings and scan ownership before publishing or resuming a checkpoint.
