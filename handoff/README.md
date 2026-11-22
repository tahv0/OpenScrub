# Handoff, 2026-11-22

Temporary branch for continuing work on another PC. **Never open a PR from it.**
No scans, reports, media, or job details belong here: this repository is public.

## What this branch is

`integration/current-work` (`2c1caa4`) with these branches merged:

| Branch | Head | What it does |
|---|---|---|
| `fix/review-card-decided-state` | `b22a233` | Decided cards stay in place and show their state |
| `fix/plate-policy-track-blur` | `fb90557` | A Blur decision covers the whole plate track |
| `fix/review-report-parse-cache` | `2391ccb` | Faster Review thumbnails |
| `fix/tile-seam-plate-boxes` | `eb436cf` | Merges plate boxes cut at 4K tile seams |
| `diag/plate-flash-clips` | `55fc346` | `tools/plate_flash_clips.py`, diagnostics only |

## Run this branch, not the tile-seam branch alone

Without `fix/plate-policy-track-blur`, plate policy `manual_review` is fail-open:

- **Blur all** leaves interpolated rows visible. Synthetic 3000-card test:
  180,000 of 270,000 rows visible, 471 of 1800 frames masked.
- A confident plate can be unmasked on frames without their own qualifying sample.

With it: 0 rows visible, and every frame that has a detection is masked (1797 of
1800). Reports scanned or saved without the fix work on this branch without a
rescan. Any video rendered without the fix must be rendered again.

## PR order into `integration/current-work`

1. `fix/review-card-decided-state`
2. `fix/plate-policy-track-blur` (before anyone relies on Blur all)
3. `fix/review-report-parse-cache`
4. `fix/tile-seam-plate-boxes`: **squash merge**. Its first commit `4896705` is
   fail-open on its own and is corrected by `eb436cf`.

Testing was against integration, not upstream main.

## Next tasks (both requested, neither started)

1. **Warn next to Save edits & render** when cards hidden by the current filter
   will stay visible. The Output select only filters the view, while Blur all acts
   on every card. Keep the human review step prominent.
2. **Reduce false plate detections**, the cause of very large card counts.
   - Needs a real `report.json` and crops from `tools/plate_flash_clips.py`, kept
     outside git.
   - A confidence threshold alone was not enough: real and false detections
     overlapped around the 0.8 cutoff in the sample that was checked.
   - Fail closed: prefer grouping or ordering in Review over dropping detections.

Not requested: fixing lettering mode (`plate_coverage: narrow`). It succeeded on
no real plate in the sample checked, so keep it off until it is fixed.

## Testing

```
python -m venv .venv && . .venv/bin/activate
pip install -r requirements.txt pytest build     # also: ffmpeg, tesseract-ocr
PYTHONPATH=$PWD python -m pytest -q
bash handoff/blur_all_check.sh                   # also: node + Playwright
```

For the browser check set `OPENSCRUB_PLAYWRIGHT_MODULE` and `OPENSCRUB_CHROMIUM`
if Playwright is not installed normally.

Nine tests already failed on `2c1caa4` in the last test environment, in these
areas: browser_composition, checkpoint_web_owner, editor_resize,
hdr_decoder_cleanup (encoder-write), job_polling_node,
job_source_allowlist_lifecycle, manual_tracker_cancel (2), opencv_compat.
Compare names against the base before blaming a change.

## Moving a scan between PCs (outside git)

- Copy the whole data folder while the container is stopped. It can hold
  detected personal data, learned words and the vault keystore.
- A server-path job does not contain its video. The video must be at the same
  path **inside the container**. Otherwise the job is silently absent from the
  job list until the video is back and the app is restarted.
- The video must be byte-identical (SHA-256). A plate-policy report refuses to
  render from a different file.
- Keep `--retain-days 0`. The default of 7 can delete copied older jobs.
