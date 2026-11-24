import time

import numpy as np

from openscrub_internal.plate_letters import Sample, frame_signature, is_cut, plan_cover

POLY = (((0.1, 0.2), (0.9, 0.2), (0.9, 0.8), (0.1, 0.8)),)


def S(key, track, t0, t1, poly, direct, box=(10, 10, 110, 40)):
    return Sample(key, track, t0, t1, tuple(box), poly, direct)


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


def test_cotemporal_dropped_samples_make_one_gap():
    s = [S(0, 1, 0.0, 0.0, (), True), S(1, 1, 0.0, 0.0, (), True)]
    gaps = plan_cover(s, 10.0, []).gaps
    assert [(g.track, g.frames, g.t0, g.t1) for g in gaps] == [(1, 1, 0.0, 0.0)]


def noise_frame(seed):
    rng = np.random.default_rng(seed)
    colour = rng.integers(0, 256, 3)
    base = np.empty((48, 64, 3), np.uint8)
    base[:] = colour
    return base + rng.integers(0, 8, base.shape, dtype=np.uint8)


def test_cut_detected_between_different_scenes_not_within_one():
    a, b = noise_frame(1), noise_frame(2)
    assert is_cut(frame_signature(a), frame_signature(b))
    assert not is_cut(frame_signature(a), frame_signature(a + 3))


def test_moving_plate_keeps_its_letters_through_a_100ms_miss_until_a_cut():
    fps = 30
    gray = np.random.default_rng(42).integers(20, 200, (90, 160), dtype=np.uint8)
    scene = np.repeat(gray[:, :, None], 3, axis=2)
    scene[35:48, 70:100] = (90, 90, 150)
    cuts, samples = [], []
    previous = None
    for i in range(6):
        frame = np.roll(scene, i, axis=1)
        frame[:, :, 0] += i % 2  # near-neutral pixels switch HSV hue
        if i == 5:
            frame[:] = (20, 180, 200)
        signature = frame_signature(frame)
        if previous is not None and is_cut(previous, signature):
            cuts.append(i)
        previous = signature
        samples.append(S(i, 1, i / fps, i / fps, POLY if i in (0, 4) else (),
                         True, box=(70 + i, 35, 100 + i, 48)))
    plan = plan_cover(samples, fps, cuts)
    assert set(plan.polys) == {0, 1, 2, 3, 4}
    assert cuts == [5] and plan.drop == {5}


def test_handoff_keeps_cover_if_the_other_track_cannot_replace_the_hold():
    # Second track is detected briefly. Trimming the first track at its
    # sighting would expose frames 3 and 4, where it is the only cover.
    a = Sample(0, 1, 0, .4, (0, 0, 100, 30), POLY, True, 0)
    b = Sample(1, 2, .1, .2, (15, 0, 115, 30), POLY, True, .2)
    plan = plan_cover([a, b], 10, [])
    assert plan.spans.get(a.key, (a.t0, a.t1))[1] == .4


def test_ambiguous_or_cross_cut_handoffs_keep_the_original_masks():
    a = Sample(0, 1, 0, .3, (0, 0, 100, 30), POLY, True, 0)
    b = Sample(1, 2, 0, .4, (15, 0, 115, 30), POLY, True, .2)
    c = Sample(2, 3, 0, .4, (20, 0, 120, 30), POLY, True, .2)
    assert not plan_cover([a, b, c], 10, []).spans
    assert not plan_cover([a, b], 10, [1]).spans


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


def test_frames_past_the_video_end_are_not_counted_or_listed():
    # a grace-padded sample reaching frames 8..14 of a 10-frame video
    s = [S(0, 1, 0.0, 0.0, POLY, True), S(1, 1, 0.8, 1.4, POLY, True),
         S(2, 2, 0.9, 1.4, (), True)]
    plan = plan_cover(s, 10.0, [], frame_count=10)
    assert plan.stats == {"masked_frames": 3, "bridged_frames": 0, "gap_frames": 1}
    assert [(g.t0, g.t1, g.frames, g.frame) for g in plan.gaps] == [(0.9, 0.9, 1, 9)]
    assert all(g.frame <= 9 for g in plan.gaps)
    # no frame count: unchanged behaviour
    assert plan_cover(s, 10.0, []).stats["masked_frames"] == 8


def test_bridge_frames_past_the_video_end_are_ignored():
    a = S(0, 1, 0.0, 0.0, POLY, True)
    b = S(1, 2, 0.9, 0.9, POLY, True)
    plan = plan_cover([a, b], 10.0, [], frame_count=6)
    assert [br.frame for br in plan.bridges] == [1, 2, 3, 4, 5]


def test_half_frame_start_does_not_hide_a_gap():
    # 30 fps: a direct sample at frame 40 has no mask and no donor within
    # 1.0 s; the next (interpolated) sample starts half a frame later, at
    # 40.5, and borrows a donor just inside 1.0 s. The renderer never paints
    # frame 40 with that interpolated sample, so frame 40 must be a gap.
    fps = 30.0
    direct = S(0, 1, 40 / fps, 40 / fps, (), True)
    interp = S(1, 1, 40.5 / fps, 41 / fps, (), False)
    donor = S(2, 1, 41 / fps + 0.99, 41 / fps + 0.99, POLY, True)
    plan = plan_cover([direct, interp, donor], fps, [])
    assert 0 in plan.drop and plan.polys[1] == POLY
    assert [(g.frame, g.frames) for g in plan.gaps] == [(40, 1)]


def test_planner_frames_match_the_renderers_rule():
    import openscrub
    from openscrub_internal.plate_letters import RENDER_TOL_S, _frames
    assert RENDER_TOL_S == 0.01
    for fps in (10.0, 24.0, 25.0, 29.97, 30.0, 59.94, 60.0, 100.0, 120.0):
        for i in range(0, 400, 7):
            for t0, t1 in ((i / fps, i / fps), ((i + .5) / fps, (i + 1.5) / fps),
                           (i / fps + 0.01, (i + 2) / fps - 0.01), (i / fps - 0.03, i / fps + 0.03)):
                d = openscrub.Detection(t0, t1, (0, 0, 9, 9), "plate", "plate", .9)
                want = [f for f in range(max(0, i - 10), i + 20)
                        if openscrub._active_on_frame(d, f / fps, f)]
                got = [f for f in _frames(S(0, 1, t0, t1, (), True), fps) if f >= max(0, i - 10)]
                assert got == want, (fps, t0, t1)


def test_first_frame_drops_frames_before_an_output_clip():
    s = [S(0, 1, 0.0, 0.0, POLY, True), S(1, 1, 0.1, 0.5, (), True), S(2, 2, 2.5, 2.9, (), True)]
    plan = plan_cover(s, 10.0, [], frame_count=30, first_frame=3)
    # frame 0's mask still lends to frames 3-5 of track 1 (borrowing sees
    # every sample), track 2 is a gap trimmed to the clip
    assert [(g.track, g.t0, g.frames) for g in plan.gaps] == [(2, 2.5, 5)]
    assert plan.stats == {"masked_frames": 3, "bridged_frames": 0, "gap_frames": 5}


def test_partial_letters_recover_across_moving_boxes_and_empty_samples():
    line = (((.08, .3), (.92, .3), (.92, .7), (.08, .7)),)
    partial = (((.46, .27), (.91, .27), (.91, .66), (.46, .66)),)
    times = [0, .033, .10, .133, .166, .2]
    masks = [line, line, partial, (), partial, partial]
    rows = [S(i, 1, t, t, mask, True, box=(4*i, 10, 4*i+120, 50))
            for i, (t, mask) in enumerate(zip(times, masks))]
    plan = plan_cover(rows, 30, [])
    for i in range(2, 6):
        assert line[0] in plan.polys[i]
    assert partial[0] in plan.polys[2]  # the new observation extends above the old line
    assert rows[2].poly == partial


def test_diagonal_plate_rejects_isolated_corner_text_with_clean_neighbours():
    band = ((.04, .18), (.18, .04), (.96, .82), (.82, .96))
    corner = ((.03, .8), (.13, .8), (.13, .9), (.03, .9))
    inline = ((.02, .06), (.06, .06), (.06, .1), (.02, .1))
    rows = [S(i, 1, i / 30, i / 30, p, True, box=(10, 10, 210, 210))
            for i, p in enumerate([(band,), (band, corner, inline), (band,)])]
    assert plan_cover(rows, 30, []).polys[1] == (band, inline)


def test_partial_mask_needs_recent_independent_evidence_in_the_same_shot_and_track():
    partial = (((.5, .2), (.9, .2), (.9, .8), (.5, .8)),)
    def row(i, t, mask, track=1, direct=True):
        return S(i, track, t, t, mask, direct)
    for rows, cuts in [
        ([row(0, 0, POLY), row(1, .03, POLY), row(2, .1, partial)], [2]),
        ([row(0, 0, POLY), row(1, .03, POLY), row(2, 1, partial)], []),
        ([row(0, 0, POLY, 2), row(1, .03, POLY, 2), row(2, .1, partial)], []),
        ([row(0, 0, POLY), row(1, .03, POLY, direct=False), row(2, .1, partial)], []),
    ]:
        assert plan_cover(rows, 30, cuts).polys[2] == partial


def test_split_second_line_and_extension_past_the_band_stay_covered():
    band = ((.1, .25), (.9, .25), (.9, .45), (.1, .45))
    # The clean line spans 80% of the box. Each component of the second
    # line is small on its own, but together they span most of that line.
    def glyph(x, y):
        return ((x, y), (x + .08, y), (x + .08, y + .08), (x, y + .08))
    second = tuple(glyph(x, .65) for x in (.22, .35, .48, .61))
    extended = (band,) + second + (glyph(.88, .3),)
    rows = [S(i, 1, i / 30, i / 30, p, True)
            for i, p in enumerate([(band,), extended, (band,)])]
    assert plan_cover(rows, 30, []).polys[1] == extended


def test_letters_missing_at_one_end_even_when_new_mask_has_similar_length():
    line = (((.05, .3), (.85, .3), (.85, .7), (.05, .7)),)
    shifted = (((.19, .3), (.96, .3), (.96, .7), (.19, .7)),)
    fragment = ((.08, .4), (.12, .4), (.12, .5), (.08, .5))
    rows = [S(i, 1, i / 30, i / 30, p, True)
            for i, p in enumerate([line, line, shifted + (fragment,)])]
    assert line[0] in plan_cover(rows, 30, []).polys[2]
