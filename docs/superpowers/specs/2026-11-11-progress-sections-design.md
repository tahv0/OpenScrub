# Reliable progress and preserved video sections

The user approved low-cost training/rescan feedback and independently reviewed
video sections, and added a bug: the progress/log view stops updating after a
while or after the window is inactive. Changes target `integration/all-prs`.

## Behavior

The active job view catches up immediately on foreground/network recovery, retries
failed requests, and cannot be held by stale requests from another view. Log
transfer and visible history are bounded. Status distinguishes connection contact
from actual worker progress. Existing rescan images are reused; no additional
inference or video decoding is added for animation. Learning stages and real
epoch/frame counts are displayed with elapsed and last-progress time.

A video has named nonoverlapping sections on its original frame timeline. A
section can be created from saved scan results, reviewed, approved, exported, or
rescanned with an explicitly selected learned model. A candidate rescan is an
attached job with its own report and model snapshot, sharing the original source.
It cannot replace the previous approved report until explicitly approved. An
approved revision is copied to an immutable snapshot and merged into the parent
report only within its interval. Parent report metadata is the commit record.
Older snapshots remain available and source files stay available for editing.

New scans use boundary context but own only their selected interval. Approved
sections are preserved through other section operations. Section edits happen in
their candidate review; whole-job operations must not silently replace approved
sections. A partial export includes exactly its approved interval and matching
audio. HDR trim must either work correctly or fail explicitly; it must never
silently export the entire source. No source deletion or automatic cleanup is
introduced.

## Chosen structure

Extend the existing single-file Flask UI and report format. Use attached candidate
jobs to reuse the existing review/model/worker flow, rather than introducing a
second review editor or changing human-decision semantics. A pure range-report
module handles clipping, merging, timeline validation and per-range provenance.
Reuse existing atomic report publication and model snapshots. Content identity
and frame alignment, rather than filenames or detection array positions, bind
results to footage. Render caching is an optional later optimization.

## Verification

Reproduce polling stalls and lifecycle recovery with browser tests. Exercise
actual subprocess telemetry without CUDA, source/range validation, interval
boundaries, rejected and corrected detections, audio, failed candidates, approved
snapshot survival, restart recovery, and exact-length synthetic exports. Preserve
the existing Python/browser suite and package all new runtime files.
