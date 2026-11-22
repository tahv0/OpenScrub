import time

from openscrub_internal.plate_letters import Sample, plan_cover

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
