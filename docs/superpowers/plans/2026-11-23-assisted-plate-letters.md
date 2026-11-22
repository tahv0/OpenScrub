# Assisted Plate Letters Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a third plate cover, `assisted`, that masks only plate letters on every covered frame, never falls back to the full box, continues masks through short dropouts, and lists the remaining visible stretches as gaps in Review.

**Architecture:** The scan stores a letter mask (box-normalized `poly`) on each plate row and records scene cuts. At render time, after the plate policy has decided which rows are covered, a pure planner (`openscrub_internal/plate_letters.py`) assigns borrowed masks, adds bridge rows across detector dropouts, drops rows with no mask, and lists gaps. The existing silhouette painters render the masks in both SDR and HDR. The web app exposes the same plan to Review as a gap list.

**Tech Stack:** Python 3.10+, OpenCV, numpy, onnxruntime (PP-OCRv5 det), Flask, vanilla JS in `openscrub_web.py`/`zones_ui.py`, pytest.

**Spec:** `docs/superpowers/specs/2026-11-23-assisted-plate-letters-design.md`

## Global Constraints

- Work on branch `fix/plate-lettering` in `/home/tahv0/src/OpenScrub-lettering`. Commit only once the owner has said commits are fine for this branch; never push.
- Report JSON is a compatibility surface: only additive fields. Full and strict (`narrow`) reports render byte-identically to before.
- Full and strict modes, and fail-closed behaviour while assisted is off, must not change.
- No real plates, frames, job ids or video names in committed files. Test data is synthetic.
- User-facing text says "PII", never "PHI". Every Advanced control needs a `<span class="qm" data-tip=...>?</span>` with no double quotes in the tip.
- Every CSS grid track is `minmax(0,1fr)`. The page must never scroll horizontally.
- The JS check runs on the evaluated page: `python -c "import openscrub_web as w, re; open('/tmp/p.js','w').write('\n'.join(re.findall(r'<script>(.*?)</script>', w.PAGE, re.S)))" && node --check /tmp/p.js`
- Tests: `HOME=$(mktemp -d) python -m pytest -q -p no:cacheprovider <paths>`. Many tests fail here for lack of ffmpeg, ffprobe and tesseract. Compare failure ids against a baseline taken before the first task; a task passes when it adds no new failing id.
- Values from the spec: text model sizes 320 first, then 640 and 224; borrow window 1.0 s; track join gap up to 1.0 s; plausibility rule unchanged (`NARROW_MIN_WIDTH, NARROW_MIN_HEIGHT = 0.5, 0.3`).
- CLI: `--plate-coverage assisted` is refused without `--no-box-fallback`. A render from a saved assisted report needs no flag (the choice is recorded in the report).
- Wording (owner's request): the mode is framed as "letters only, no box fallback". Where letters are not found clearly, nothing is drawn instead of the big box. OpenScrub never promises to find every plate, in any mode. Never present it as "allowing visible plates".
- Warnings (owner's request): the decision is made once, in Scan Setup, with the confirmation dialog. Review shows one notice at the top of the job, never on individual cards, and a reminder appears before rendering.
- Bridged stretches are covered and are NOT listed as gaps (owner's decision, see spec).

## Review Focus

1. A scene cut inside one track: a plate detected on both sides of a cut must not borrow a mask across the cut. Test in Task 2.
2. Frames skipped by the fast-skip outside detection windows: OpenScrub never saw them, so a skip counts as a cut. Test in Task 5.
3. Two plates near each other: a join must pick the track whose start is nearest the predicted position and in the size band, never a farther one. Test in Task 3.
4. A full-size report (about 270,000 rows): `plan_cover` must stay O(n log n) and the gap route must use the report parse cache. Test in Task 2 (timing bound on 300,000 synthetic samples) and Task 7.
5. Keep and undecided rows: no cover and no gap. A manual plate quad still wins over a letter mask. Tests in Task 6.

---

### Task 1: Drop the country-band rule, keep the plausibility rule

**Files:**
- Modify: `openscrub.py` (remove `_country_bands` and its use in `_narrow_from_probability`)
- Modify: `PLATES.md` (remove the band sentences from the lettering paragraph)
- Test: `tests/test_narrow_plate.py`

**Interfaces:**
- Produces: `_plausible_lettering(polygons) -> bool` and `NARROW_MIN_WIDTH, NARROW_MIN_HEIGHT` stay as on the branch.

- [ ] **Step 1:** Delete the three band tests (`test_guard_accepts_country_band_by_covering_it`, `test_country_band_does_not_excuse_a_missed_character`, `test_country_band_does_not_excuse_fragment_lettering`), `_band_plate` and `_covered`. Keep `test_missed_blue_character_is_not_mistaken_for_a_country_band`, renamed `test_missed_character_still_rejects`.
- [ ] **Step 2:** Remove `_country_bands`, the `bands` block, and restore `for evidence in (ink, (contrast > 20).astype(np.uint8)):` and `return polys, ""`.
- [ ] **Step 3:** Run `tests/test_narrow_plate.py tests/test_plate_quad.py tests/test_combined_checkpoint_plate.py`. Expected: no new failing ids; the four plausibility tests pass.
- [ ] **Step 4:** Commit: `fix(plates): reject fragment lettering masks; drop the unvalidated country-band rule`.

### Task 2: Planner core: borrowing and gaps

**Files:**
- Create: `openscrub_internal/plate_letters.py`
- Test: `tests/test_plate_letters.py`

**Interfaces:**
- Produces (all in `openscrub_internal/plate_letters.py`):
  - `BORROW_S = 1.0`, `JOIN_S = 1.0`, `MERGE_FRAMES = 3`
  - `@dataclass(frozen=True) class Sample: key: int; track: int; t0: float; t1: float; box: tuple[float, float, float, float]; poly: tuple; direct: bool` (`box` in frame pixels, `poly` box-normalized, `key` = caller's row index)
  - `@dataclass(frozen=True) class Bridge: track: int; frame: int; box: tuple; poly: tuple`
  - `@dataclass(frozen=True) class Gap: track: int; t0: float; t1: float; frames: int; frame: int; box: tuple`
  - `@dataclass class CoverPlan: polys: dict[int, tuple]; drop: set[int]; bridges: list[Bridge]; gaps: list[Gap]; stats: dict`, with `stats` keys `masked_frames`, `bridged_frames`, `gap_frames`
  - `plan_cover(samples: list[Sample], fps: float, cuts: list[int], borrow_s: float = BORROW_S, join_s: float = JOIN_S) -> CoverPlan`
- A sample's frames are `range(round(t0 * fps), round(t1 * fps) + 1)`. A frame belongs to the shot that starts at the last cut at or before it.

- [ ] **Step 1: Write the failing tests**

```python
def test_sample_with_own_mask_keeps_it():
    plan = plan_cover([S(0, 1, 0.0, 0.0, POLY, True)], 10.0, [])
    assert plan.polys[0] == POLY and not plan.drop and not plan.gaps

def test_unmasked_sample_borrows_nearest_direct_mask_within_one_second():
    s = [S(0, 1, 0.0, 0.0, POLY, True), S(1, 1, 0.9, 0.9, (), True), S(2, 1, 1.2, 1.2, (), False)]
    plan = plan_cover(s, 10.0, [])
    assert plan.polys[1] == POLY and 2 in plan.drop
    assert [(g.track, g.frames) for g in plan.gaps] == [(1, 1)]

def test_borrowing_never_crosses_a_scene_cut():
    s = [S(0, 1, 0.0, 0.0, POLY, True), S(1, 1, 0.5, 0.5, (), True)]
    plan = plan_cover(s, 10.0, [3])
    assert 1 in plan.drop and plan.gaps[0].t0 == 0.5

def test_gaps_closer_than_merge_frames_join_and_cover_both():
    s = [S(i, 1, i / 10, i / 10, (), True) for i in (0, 2, 4)]
    gaps = plan_cover(s, 10.0, []).gaps
    assert len(gaps) == 1 and gaps[0].t0 == 0.0 and gaps[0].t1 == 0.4

def test_stats_count_masked_and_gap_frames():
    s = [S(0, 1, 0.0, 0.1, POLY, True), S(1, 1, 5.0, 5.0, (), True)]
    assert plan_cover(s, 10.0, []).stats == {"masked_frames": 2, "bridged_frames": 0, "gap_frames": 1}

def test_plan_scales_to_a_full_report():
    s = [S(i, i // 100, i / 60, i / 60, POLY if i % 3 else (), i % 2 == 0) for i in range(300_000)]
    start = time.perf_counter(); plan_cover(s, 60.0, list(range(0, 300_000, 5000)))
    assert time.perf_counter() - start < 20
```

(`S(key, track, t0, t1, poly, direct)` is a test helper building a `Sample` with a fixed box `(10, 10, 110, 40)`; `POLY = (((0.1, 0.2), (0.9, 0.2), (0.9, 0.8), (0.1, 0.8)),)`.)

- [ ] **Step 2:** Run `tests/test_plate_letters.py`. Expected: FAIL, module not found.
- [ ] **Step 3:** Implement `plan_cover` for borrowing and gaps (joining comes in Task 3). Group samples by track, sort by `t0` once, and find the nearest masked direct sample in the same shot by bisect over the track's masked direct times. A gap frame is a frame of a dropped sample that no masked sample of the same track covers.
- [ ] **Step 4:** Run the tests. Expected: PASS.
- [ ] **Step 5:** Commit: `feat(plates): plan assisted letter cover, borrowing and gaps`.

### Task 3: Planner: scene cuts and track joining

**Files:**
- Modify: `openscrub_internal/plate_letters.py`
- Test: `tests/test_plate_letters.py`

**Interfaces:**
- Produces: `frame_signature(frame: np.ndarray) -> np.ndarray` (normalized HSV histogram of a copy 64 px wide) and `is_cut(previous: np.ndarray, current: np.ndarray) -> bool` (`cv2.compareHist(..., HISTCMP_CORREL) < CUT_CORREL`, `CUT_CORREL = 0.5`). `plan_cover` now also fills `bridges`.
- Join rule: track A's last masked sample and track B's first masked sample, with B starting after A ends by at most `join_s`, in the same shot. B's first box centre is within one A box width of A's last centre, and B's box area is 0.5x to 2.0x A's. When several B qualify, take the nearest centre. Each B joins at most one A. Every frame strictly between gets one `Bridge` with the box linearly interpolated and A's last poly. Bridge frames are counted in `bridged_frames` and are never gaps.

- [ ] **Step 1: Write the failing tests**

```python
def test_cut_detected_between_different_scenes_not_within_one():
    a, b = noise_frame(1), noise_frame(2)       # synthetic, different colours
    assert is_cut(frame_signature(a), frame_signature(b))
    assert not is_cut(frame_signature(a), frame_signature(a + 3))

def test_dropout_between_two_tracks_is_bridged_and_not_a_gap():
    s = [S(0, 1, 0.0, 0.0, POLY, True, box=(0, 0, 100, 30)), S(1, 2, 0.5, 0.5, POLY, True, box=(40, 0, 140, 30))]
    plan = plan_cover(s, 10.0, [])
    assert [b.frame for b in plan.bridges] == [1, 2, 3, 4]
    assert plan.bridges[1].box == (16.0, 0.0, 116.0, 30.0) and not plan.gaps
    assert plan.stats["bridged_frames"] == 4

def test_no_join_across_a_cut_or_beyond_one_second_or_size_band():
    far = [S(0, 1, 0.0, 0.0, POLY, True), S(1, 2, 1.2, 1.2, POLY, True)]
    big = [S(0, 1, 0.0, 0.0, POLY, True), S(1, 2, 0.3, 0.3, POLY, True, box=(10, 10, 410, 160))]
    assert not plan_cover(far, 10.0, []).bridges and not plan_cover(big, 10.0, []).bridges
    assert not plan_cover(far[:1] + [S(1, 2, 0.5, 0.5, POLY, True)], 10.0, [3]).bridges

def test_join_picks_the_nearest_of_two_neighbours():
    s = [S(0, 1, 0.0, 0.0, POLY, True, box=(0, 0, 100, 30)),
         S(1, 2, 0.3, 0.3, POLY, True, box=(10, 0, 110, 30)), S(2, 3, 0.3, 0.3, POLY, True, box=(90, 0, 190, 30))]
    assert {b.track for b in plan_cover(s, 10.0, []).bridges} == {1}
```

- [ ] **Step 2:** Run. Expected: FAIL (`frame_signature` undefined, no bridges).
- [ ] **Step 3:** Implement the two functions and the join rule as specified above.
- [ ] **Step 4:** Run `tests/test_plate_letters.py`. Expected: PASS, including Task 2's tests.
- [ ] **Step 5:** Commit: `feat(plates): scene cuts and joining plate tracks across short dropouts`.

### Task 4: Mode switch (CLI and settings)

**Files:**
- Modify: `openscrub.py` (`build_parser`, `_prep_args`, `_settings_dict`)
- Test: `tests/test_assisted_letters.py`

**Interfaces:**
- Produces: `--plate-coverage {full,narrow,assisted}`; `--no-box-fallback` (store_true); `args.plate_coverage == "assisted"` downstream. Saved settings keep `plate_coverage: "assisted"`.

- [ ] **Step 1: Write the failing tests**

```python
def test_assisted_needs_explicit_permission():
    parser = openscrub.build_parser()
    with pytest.raises(SystemExit):
        openscrub._prep_args(parser.parse_args(["x.mp4", "--plate-coverage", "assisted"]), parser)
    args = openscrub._prep_args(parser.parse_args(
        ["x.mp4", "--plate-coverage", "assisted", "--no-box-fallback"]), parser)
    assert args.plate_coverage == "assisted"
    assert openscrub._settings_dict(args)["plate_coverage"] == "assisted"

def test_full_and_narrow_settings_unchanged():
    parser = openscrub.build_parser()
    args = openscrub._prep_args(parser.parse_args(["x.mp4"]), parser)
    assert "plate_coverage" not in openscrub._settings_dict(args)
```

- [ ] **Step 2:** Run. Expected: FAIL (invalid choice).
- [ ] **Step 3:** Add the choice and the flag (help text: "with --plate-coverage assisted: where letters are not found clearly, draw nothing instead of the full plate box; such spots are listed as gaps in Review"). `_prep_args` calls `parser.error("--plate-coverage assisted never falls back to the full plate box; add --no-box-fallback to confirm")` when the flag is missing and the coverage came from the command line. `_settings_dict` keeps `plate_coverage` for `narrow` and `assisted` and drops `no_box_fallback`.
- [ ] **Step 4:** Run, plus `tests/test_narrow_plate.py`. Expected: PASS, no new failing ids.
- [ ] **Step 5:** Commit: `feat(plates): opt-in assisted letter coverage mode switch`.

### Task 5: Scan: letter masks and scene cuts

**Files:**
- Modify: `openscrub.py` (`_narrow_from_probability` split, `TextRegionDetector.find_letters`, `run_scan` plate block and frame loop, `_report_document`, from-report state)
- Test: `tests/test_assisted_letters.py`

**Interfaces:**
- Consumes: `plate_letters.frame_signature`, `plate_letters.is_cut`, `_plausible_lettering`.
- Produces:
  - `_restored_quads(crop, prob, clip=False) -> tuple[list[np.ndarray], str]`: the contour-to-quadrilateral part of `_narrow_from_probability`, moved unchanged. With `clip=True`, points outside the crop are clipped into it instead of returning `invalid_geometry`. `_narrow_from_probability` calls it with `clip=False`, so strict mode is unchanged.
  - `LETTER_SIZES = (320, 640, 224)`
  - `TextRegionDetector.find_letters(frame, box, sizes=LETTER_SIZES) -> list[np.ndarray]`: frame-coordinate polygons. Size 320 first; if its outline is empty or implausible, run 640 and 224 and return the union of each size's outline that is plausible on its own; `[]` if none.
  - Scan rows: plate rows get `poly` = box-normalized `find_letters` output, clipped to [0, 1], or `()`.
  - `state["scene_cuts"]: list[int]` (frame indices). Report top-level `scene_cuts`, read back on the from-report path.

- [ ] **Step 1: Write the failing tests**

```python
def test_find_letters_uses_320_first_and_unions_fallback_sizes(monkeypatch):
    # fake session: implausible outline at 320, plausible ones at 640 and 224
    det = fake_text_detector({320: SPECK, 640: LEFT_HALF, 224: RIGHT_HALF})
    polys = det.find_letters(FRAME, BOX)
    assert det.sizes_run == [320, 640, 224] and covers(polys, LEFT_HALF + RIGHT_HALF)
    det = fake_text_detector({320: WORD})
    assert det.find_letters(FRAME, BOX) and det.sizes_run == [320]

def test_strict_check_unchanged_by_the_split():
    for crop, prob in synthetic_guard_cases():   # the existing guard fixtures
        assert openscrub._narrow_from_probability(crop, prob) == ORIGINAL[id_of(crop)]

def test_assisted_scan_stores_masks_and_cuts(tmp_path, monkeypatch):
    # 6-frame synthetic video, scene change at frame 3, fake plate and text models
    state = scan_assisted(tmp_path, monkeypatch)
    plates = [d for d in state["detections"] if d.category == "plate" and d.dense]
    assert any(d.poly for d in plates) and state["scene_cuts"] == [3]

def test_fast_skip_resume_counts_as_a_cut(tmp_path, monkeypatch):
    state = scan_assisted(tmp_path, monkeypatch, windows="0-0.2,0.8-1.0")
    assert state["scene_cuts"] and min(state["scene_cuts"]) > 0
```

(For `test_strict_check_unchanged_by_the_split`, record `ORIGINAL` by running the unmodified function over the fixtures in the test before Step 3. Keep the recorded tuples as literals in the test file.)

- [ ] **Step 2:** Run. Expected: FAIL (`find_letters` missing, no `scene_cuts`).
- [ ] **Step 3:** Implement as in Interfaces. In `run_scan`, `assisted = args.plate_coverage == "assisted" and "plate" in cats`. It loads the text model like strict mode, detects plates on every frame at full resolution like strict mode, skips `_record_narrow_plate`, and sets `row.poly`. It computes `frame_signature` on every decoded frame, appends `idx` to `scene_cuts` when `is_cut`, and also when the loop seeks past skipped frames. Scan log lines: `assisted letters: masks on N of M plate detections; sizes used 320:a 640:b 224:c; text model T s`.
- [ ] **Step 4:** Run `tests/test_assisted_letters.py tests/test_narrow_plate.py`. Expected: PASS, no new failing ids.
- [ ] **Step 5:** Commit: `feat(plates): assisted scan stores letter masks and scene cuts`.

### Task 6: Render: apply the cover plan

**Files:**
- Modify: `openscrub.py` (`apply_assisted_cover`, `run_render`, `_report_document`)
- Test: `tests/test_assisted_letters.py`

**Interfaces:**
- Consumes: `plate_letters.plan_cover`, `Sample`, `CoverPlan`.
- Produces:
  - `apply_assisted_cover(dets: list[Detection], fps: float, cuts: list[int]) -> tuple[list[Detection], plate_letters.CoverPlan]`: dense plate rows become `Sample`s (`direct` = policy evidence origin `"detection"`, box = `cbox + aoff`). It returns a new list where planned rows carry their poly, dropped rows are removed, each `Bridge` becomes a dense plate `Detection` spanning its one frame (`t0 = t1 = frame / fps`, same track), and non-plate rows and rows with a manual plate quad pass through unchanged.
  - `assisted_cover_from_report(doc: dict) -> plate_letters.CoverPlan`: decodes the report, applies the plate policy exactly as `run_render` does (`plate_policy.evaluate(..., capable_off=True)`), and calls `apply_assisted_cover`. Used by Task 7.
  - Report additive fields after render: `plate_letter_gaps` (list of `Gap` as dicts) and `plate_letter_stats`.

- [ ] **Step 1: Write the failing tests**

```python
def test_assisted_render_masks_letters_and_leaves_gaps_visible(tmp_path):
    # synthetic 5-frame video; frames 0-1 masked, 2 borrows, 4 has no mask within 1 s of a cut
    out = render_assisted(tmp_path)
    assert black_share(out[0], PLATE) < 0.8 and black_share(out[0], LETTERS) > 0.99
    assert black_share(out[2], LETTERS) > 0.99 and black_share(out[4], PLATE) == 0

def test_keep_and_undecided_plates_are_neither_covered_nor_gaps():
    dets, plan = openscrub.apply_assisted_cover(rows_after_policy(keep_track=7), 10.0, [])
    assert all(d.track != 7 for d in dets) and all(g.track != 7 for g in plan.gaps)

def test_manual_quad_wins_over_letter_mask():
    dets, _ = openscrub.apply_assisted_cover([row_with_quad_and_poly()], 10.0, [])
    assert dets[0].manual_plate_quad and not dets[0].poly

def test_full_and_narrow_renders_unchanged(tmp_path):
    for coverage in ("full", "narrow"):
        assert render_bytes(tmp_path, coverage, branch_code=True) == render_bytes(tmp_path, coverage, branch_code=False)
```

(`render_bytes(..., branch_code=False)` renders with frames painted by a copy of `_render_into` taken from git `HEAD` before this task. If that harness is impractical, compare the decoded output frames against frames saved from the pre-task code in the test's fixtures.)

- [ ] **Step 2:** Run. Expected: FAIL (`apply_assisted_cover` missing).
- [ ] **Step 3:** Implement. In `run_render`, after the plate policy filter: if `args.plate_coverage == "assisted"`, replace `detections` via `apply_assisted_cover(detections, state["fps"], state.get("scene_cuts", []))`, store the plan's gaps and stats in `state`, and render with `narrow_plates=False`. A manual quad clears `poly` on its row so the quad painter is used. The HDR path needs no change beyond receiving the same list.
- [ ] **Step 4:** Run `tests/test_assisted_letters.py tests/test_narrow_plate.py tests/test_optional_plate_review.py`. Expected: PASS, no new failing ids. Where ffmpeg exists, also run an HDR synthetic render (`tests/test_hdr_decoder_cleanup.py` shows how to build a 10-bit clip) and check the letters are masked.
- [ ] **Step 5:** Commit: `feat(plates): render assisted letter masks with borrowing, bridges and gaps`.

### Task 7: Web: Scan Setup choice, confirmation, gap list in Review

**Files:**
- Modify: `zones_ui.py` (plate cover select, confirmation, options), `openscrub_web.py` (`build_args`, routes, `APP_JS` Review section)
- Test: `tests/test_assisted_letters_web.py`

**Interfaces:**
- Consumes: `openscrub.assisted_cover_from_report`, `_parse_report_once`, `openscrub._grab_frame`.
- Produces:
  - Scan Setup: `<select id="platecover">` with options `full` ("Full plate box (default)"), `narrow` ("Letters only, strict (experimental)"), `assisted` ("Letters only, no box fallback (experimental, slow)"), replacing `#plateletters`. Choosing `assisted` calls `confirm(ASSISTED_CONFIRM)`; Cancel restores the previous value. Options: `plate_coverage` = the value unless `full`; `no_box_fallback: true` with `assisted`.
  - `ASSISTED_CONFIRM` text: "Letters only, no box fallback: where letters are not found clearly, nothing is drawn instead of the full plate box. Those spots are listed as gaps in Review. OpenScrub does not find every plate, so check the output. Scanning is slow. Turn it on?"
  - `build_args`: adds `--plate-coverage assisted --no-box-fallback` for scans when both options are present. It raises `ValueError("assisted plate letters needs explicit confirmation")` when `plate_coverage` is `assisted` without `no_box_fallback`.
  - `GET /api/jobs/<jid>/letter_gaps` -> `{"mode": "assisted"|"off", "gaps": [{track, t0, t1, frames, frame, box}], "stats": {...}}`, computed from the saved report and cached per report stamp.
  - `GET /api/jobs/<jid>/letter_gap/<int:n>.jpg`: the gap's middle frame cropped to the box plus one box size of margin, box drawn, 240 px tall.
  - Review: in assisted jobs, a `#letterGaps` section above `#beslot` with:
    - one notice at the top (not on cards): "Letters only, no box fallback: gaps below are not covered. Check the output."
    - the summary "letters covered on P% of plate frames (B bridged), N gaps"
    - "Based on the last saved review choices."
    - a list sorted by `t0`, each item with a preview image, start and end time and frame count. Clicking an item opens the box editor at `t0` (`loadBoxEdit(true)`, then set `#beT` and call `beScrub()`).
  - Before rendering: the existing Save edits & render action, for an assisted job, first shows `confirm(ASSISTED_RENDER_REMINDER)` with the current gap count: "Letters only, no box fallback: N gaps listed in Review will not be covered. Render now?" Cancel does not render.

- [ ] **Step 1: Write the failing tests**

```python
def test_build_args_requires_confirmation_for_assisted(): ...      # ValueError without no_box_fallback; flags present with it
def test_letter_gaps_route_lists_gaps_of_assisted_job(client): ...  # synthetic assisted report -> gaps sorted by t0, stats keys
def test_letter_gaps_route_reports_off_for_other_jobs(client): ...  # full report -> {"mode": "off"}
def test_letter_gap_preview_is_a_jpeg(client): ...                  # 200, image/jpeg, height 240
def test_scan_setup_has_plate_cover_choice_with_help_tip(): ...     # three option values, qm tip, confirm text present in PAGE
def test_render_reminder_present_and_no_per_card_warning(): ...     # ASSISTED_RENDER_REMINDER in PAGE; card template has no assisted warning
```

(Each test asserts exactly what its comment states. Follow `tests/test_narrow_plate_web.py` for building synthetic jobs and the Flask client.)

- [ ] **Step 2:** Run. Expected: FAIL.
- [ ] **Step 3:** Implement as in Interfaces. Routes look up the job via `JOBS` and never build a path from request data. The list layout follows the existing Review styling and the mobile-fit rules.
- [ ] **Step 4:** Run the new tests, `test_openscrub.py::test_every_advanced_setting_has_a_help_tip`, `tests/test_narrow_plate_web.py`, and the JS check. Expected: PASS, `node --check` silent. Boot the server on a synthetic assisted job and confirm the gap list renders, a click opens the editor at that time, and Save edits & render shows the reminder.
- [ ] **Step 5:** Commit: `feat(web): assisted plate letters option and Review gap list`.

### Task 8: Speed

**Files:**
- Modify: `openscrub.py` (`TextRegionDetector`)
- Test: `tests/test_assisted_letters.py`

**Interfaces:**
- Produces: `TextRegionDetector.find_letters_many(frame, boxes, sizes=LETTER_SIZES) -> list[list[np.ndarray]]`, same result per box as `find_letters`. Crops with the same resized shape go to the model in one batched call per size. `run_scan` uses it per frame. At load the detector logs its execution provider: `text model on <provider>`.

- [ ] **Step 1: Write the failing test:** `test_find_letters_many_matches_single_calls_and_batches` checks that `find_letters_many` gives the same polygons as `find_letters` box by box on a fake session, and that the session saw one call per (size, shape) group.
- [ ] **Step 2:** Run. Expected: FAIL.
- [ ] **Step 3:** Implement and switch `run_scan` to it. Check that the PP-OCRv5 export accepts a batch dimension above 1 on CPU; if it does not, keep per-crop calls and log that batching is unavailable.
- [ ] **Step 4:** Run the tests. Measure the scan time of a synthetic 1080p 30-second clip with 3 plates per frame before and after, and record both numbers in the commit message.
- [ ] **Step 5:** Commit: `perf(plates): batch assisted letter detection per frame`.

Decode/model overlap (a decode thread) is left out unless the owner's first real scan shows decode is a large share of the time (spec: "how much of the speed list is needed" is the builder's call).

### Task 9: Documentation, rules and full verification

**Files:**
- Modify: `CLAUDE.md` (Hard rules: fail-closed exception; engine and web sections: assisted mode), `PLATES.md` (assisted section with the warnings), `README.md` (one paragraph under plates)
- Create (not committed, `tmp/` is ignored): `/home/tahv0/src/OpenScrub/tmp/assisted-letters-check.py`, a container check for the owner. It runs `find_letters` on the saved plate-shaped crops and saves before/after pictures of the union masks to the data folder, printing counts only.

- [ ] **Step 1:** Write the docs. CLAUDE.md hard rule text: "Fail closed — except in the opt-in letters-only, no-box-fallback mode (`--plate-coverage assisted`, which requires `--no-box-fallback` or the Scan Setup confirmation): there, where letters are not found clearly nothing is drawn instead of the full box, those spots are listed as gaps in Review, and the user checks the output. All other modes keep failing closed. No mode promises to find every plate." Also record that bridged stretches are deliberately not listed (owner's decision).
- [ ] **Step 2:** Full suite, compared with the baseline: no new failing ids. `python -m build` succeeds and the wheel contains `openscrub_internal/plate_letters.py`. JS check silent.
- [ ] **Step 3:** Synthetic end-to-end render in assisted mode (SDR) with the report checked for `plate_letter_gaps`, `plate_letter_stats` and `scene_cuts`.
- [ ] **Step 4:** Write and mechanics-test the container check script on synthetic crops with a fake text model, as with the earlier scripts.
- [ ] **Step 5:** Commit the docs: `docs: assisted plate letters mode and its fail-closed exception`. Regenerate `tmp/plate-lettering.patch` from the branch for the owner's Windows checkout.
