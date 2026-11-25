# Assisted plate letters: design

Status: approved by the owner, 2026-11-23.

## Why

The owner redacts long videos with many moving licence plates. A narrow cover
over only the letters and numbers looks far better than a big blur box, but
doing it by hand in Shotcut means a new static filter almost every second for
every moving plate. Today OpenScrub offers two plate covers:

- **Full box** (default): blurs the whole detected box. Safe, but big.
- **Lettering only, strict** (`--plate-coverage narrow`, experimental): masks only
  the letters when a strict check can prove nothing is left uncovered,
  otherwise the full box. On the owner's real test video it has never
  accepted a real plate. Four targeted fixes failed on real crops (country
  band, extra margin, smaller input, wider outline). The check is built to
  never leak, and on real plates (border, bolts, plate frame, partial
  occlusion) that means it never passes.

The owner wants OpenScrub to do most of the work, about 90% of it, and accepts
fixing the rest by hand: "it is fine if this tool reduces 90% of work". They
will watch every output and add Shotcut filters where OpenScrub missed, so
OpenScrub must say where it is unsure.

## Goals

1. A third plate cover, **assisted letters**: on every frame where a plate is
   covered, the cover is letter-sized, following the plate. It never falls back
   to the full box.
2. Where no usable letter mask exists, the plate is **left visible** and the
   stretch is reported as a **gap**.
3. A **gap list in the Review page**: each gap with plate, start and end time,
   a preview image, and a click that jumps there. Sorted by time, to work
   through beside Shotcut.
4. Hard to switch on by accident: an explicit choice in Scan Setup plus a
   confirmation dialog, and a reminder before rendering. They say that unclear
   letters get no box and that scanning is slow.
5. Reasonable scan speed: measure first, then the optimizations below.

## Non-goals (this project)

- Guaranteeing privacy. This mode is deliberately not fail-closed.
- Plates the detector never finds. They cannot be listed; the warning says so.
- Reducing false plate detections (separate follow-up). False plates get
  letter masks too, which is harmless.
- Persisting Review choices across reloads. The SQLite review journal from
  `integration/all-prs` (PR #54 and follow-ups) is the follow-up; the gap list
  should later be storable and re-fetchable there.
- The "plate cover" stand-in plate, skipping text-model frames for speed, and
  automatic plate corner finding. All possible follow-ups.

## Anti-goals (a failure even if it works)

- A visible plate that the gap list does not report.
- The mode turning on without the user explicitly choosing it.
- Any change to the full-box or strict modes, or to fail-closed behaviour when
  this mode is off.
- Big full boxes in this mode.

## Constraints

- Report JSON is a compatibility surface: extend, never break. Saved
  full/strict reports must render exactly as before.
- No real plates, frames or job details in committed files. The validation
  video stays outside git.
- The project hard rule "fail closed" is amended, only for this mode: CLAUDE.md
  and PLATES.md must say that fail-closed does not apply while assisted letters
  is on, that it must be switched on explicitly, and that the output must be
  checked by a human. Everything else keeps failing closed.
- Builds on branch `fix/plate-lettering`, which adds the plausibility rule
  (`_plausible_lettering`: a mask must span at least half the box width and 30%
  of its height). The country-band rule on that branch is removed, as it had no
  effect on real crops (my call).

## Behaviour

### Switching it on

- Scan Setup, Advanced, plate category: the existing "Plate lettering only"
  checkbox becomes a choice of three: full box (default), letters only, strict
  (experimental), letters only, no box fallback (experimental, slow).
- Picking it opens a confirmation dialog: where letters are not found clearly,
  nothing is drawn instead of the full plate box; those spots are listed as
  gaps in Review; OpenScrub does not find every plate, so the output must be
  checked; the scan is slow. Cancel keeps the previous choice.
- Wording (owner's request): the mode is "letters only, no box fallback", not
  "allow visible plates". OpenScrub does not promise to find every plate in
  any mode; this mode only skips the big box where letters are unclear.
- CLI: `--plate-coverage assisted` is refused unless `--no-box-fallback`
  is also given, the command-line equivalent of the dialog (my call).
- The report records the mode in provenance settings (`plate_coverage:
  assisted`), so a render from the saved report uses it, as the strict mode
  does today.
- Warnings (owner's request): the decision is made once, in Scan Setup. Review
  shows one notice at the top of the job, never on individual cards. Before
  rendering, a reminder states how many gaps will stay uncovered, with Cancel.

### Finding letters (scan)

For every frame where a plate is detected (plate detection already runs on
every frame in the strict mode; the same applies here):

1. Run the text model on the plate crop at 320 px long side.
2. If that outline fails the plausibility rule or is empty, also run 640 and
   224 px. The mask is the union of the plausible outlines. A union only adds
   cover.
3. No strict check. Only the plausibility rule discards specks.
4. The mask is stored on the detection row as box-normalized polygons, like the
   strict mode's `poly`, with an additive evidence record (for example
   `plate_letters: {"frame_index", "sizes"}`). Rows without a mask get no
   polygons.

The 320-first order and the size set come from the owner's real-crop runs,
where 320 and 224 sometimes outlined the characters well and 640 did not. They
are starting values; tuning them is left to the builder, with measurements.

### Covering frames without their own mask

- Every rendered plate sample in a track (direct detections, interpolated and
  grace samples) without its own mask borrows the box-normalized mask of the
  nearest masked direct detection of the same track, mapped onto its own box.
- Borrowing is limited to a time window (my call: 1.0 s either side; tuning
  left to the builder). Beyond it, the frame has no cover.
- A track with no mask at all has no cover in this mode.

### Continuing a plate through short dropouts (owner's request)

The owner's example: the letters are covered, then nothing for 0.5 s, then
covered again on the same plate. If nothing changed in the scene, that is the
same plate and the cover should continue through the gap.

- Scene cuts: the scan marks a cut wherever consecutive frames differ almost
  entirely (for example colour histograms of a small copy). Cheap; stored
  additively in the report. Neither borrowing nor joining ever crosses a cut.
- Letter dropouts while the plate is still detected: handled by borrowing
  (above).
- Detector dropouts: smoothing already bridges up to 0.75 s inside a track.
  New in this mode: a plate track that ends is joined to a track starting within
  a short time (my call: up to 1.0 s; tuning left to the builder), when the new
  track starts near where the old one was heading, at a similar size, with no
  cut in between. The gap frames get a box interpolated between the two ends,
  carrying the letter mask. Joining only adds cover; it never changes either
  track's own frames.
- Bridged frames count as covered, but the Review summary shows how many frames
  were bridged, so the owner can judge how much is guessed.
- Bridged stretches are NOT added to the gap list. Owner's decision
  (2026-11-23): listing them would add checking work, and the point of the mode
  is less manual work. The cost: a wrong join (a bridged cover that is in the
  wrong place) is not listed, so it can only be caught while watching the
  output. If that becomes a problem, listing bridged stretches separately is
  the fix.
- A manual plate corner quad on a row still wins, as today.
- Keep and Blur decisions and the plate policy decide *whether* a plate is
  covered, exactly as now. This mode only changes the *shape* of the cover.
  An enabled sample without a mask is a gap; a sample kept visible by the
  user's Keep choice is not a gap.

### Gaps

- A gap is a run of consecutive rendered frames where an enabled plate sample
  of a track has no letter mask, own or borrowed.
- Computed from the report state, so it is correct after Review edits and on
  re-render; stored additively in the report (for example
  `plate_letter_gaps: [{track, t0, t1, frames, frame_index}]`).
- Plates left visible because the plate policy did not enable them (an
  undecided "Needs review" card, or Keep) are not gaps: Review already lists
  them as cards, and listing every unconfirmed false plate would bury the real
  gaps (my call).
- A one-frame gap is still a gap. Merging gaps closer than a few frames into
  one entry is allowed, as long as the merged range covers both.

### Review page

- A gap list section: per gap the plate/track, start and end time, frame
  count, and a preview image at the gap's middle frame with the plate box drawn.
  Clicking jumps the review editor to that time.
- A summary line: frames with a letter mask vs gap frames, for example
  "letters covered on 92% of plate frames, 37 gaps".
- Uses the existing thumbnail machinery and the box editor seek. Layout is left
  to the builder, within the existing Review styling and mobile-fit rules.

### Rendering

- SDR and HDR: masked samples render with the silhouette painters that exist for
  both paths (`blur_silhouette`, `_blur_silhouette_yuv10`) in the plate
  category's mode. No frame-hash binding (that is the strict mode's guarantee,
  not needed here).
- Samples without a mask are not painted.
- Full and strict modes are unchanged.

### Speed

Measure on a real-size clip first: decode, plate detector, text model, render.
Then, in order of expected value:

1. Confirm the text model runs on the GPU in the CUDA image (the owner's
   container prints an onnxruntime GPU discovery warning) and fix it if not.
2. 320-first with fallback sizes only when needed (above).
3. Batch all plate crops of a frame into one text-model call per size.
4. Overlap frame decoding with model work (a decode thread).

The Scan Setup label and dialog say the mode is slow. Leaving it running
overnight is an accepted way to use it.

## Validation

- Unit tests for the new rules (escalation, union, borrowing window, gap
  computation, Keep vs gap, CLI refusal without the second flag), with
  synthetic data. Full, strict and default renders unchanged (existing tests
  plus a byte-identical check on a synthetic report).
- A synthetic render end to end (SDR and HDR).
- A container check the owner runs on the job's saved crops: the per-size union
  outlines, for the owner to judge on real plates. Pictures stay local.
- The real test: the owner rescans their usual long test video in this mode
  and watches it with the gap list. Success: letters covered on about 90% of
  frames where a real plate is detected and covered, every visible stretch of
  a detected plate is in the gap list, and the owner's Shotcut work clearly
  drops. The frame share printed by the tool counts false plates as well, so
  the owner's viewing is the deciding measure.
- Full test suite, build through the sdist, JS checked from the evaluated page.

## Left to the builder

Thresholds and window lengths (with measurements), data field names within the
additive-only rule, the Review gap-list layout, how much of the speed list is
needed to make the mode usable, and how to label the mode in the UI within the
warnings above.

## Calls I made (for the owner to check)

1. The new mode is a third choice beside full and strict; strict stays.
2. The country-band rule is removed from `fix/plate-lettering`.
3. CLI needs `--no-box-fallback` together with the mode.
4. Masks are borrowed from the same track for up to 1.0 s either side.
5. The validation video and results stay outside git.
6. Plates the plate policy leaves visible (undecided or Keep) stay in Review's
   card list and are not added to the gap list.
7. Tracks are joined across detector dropouts of up to 1.0 s, never across a
   scene cut; bridged frames count as covered and are counted in the summary.
