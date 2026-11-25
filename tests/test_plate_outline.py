import cv2
import numpy as np
import pytest

from openscrub_internal import plate_outline


@pytest.mark.parametrize("panel,backing,ink", [
    ((240, 240, 240), (240, 240, 240), (15, 15, 15)),
    ((20, 20, 20), (20, 20, 20), (235, 235, 235)),
    ((255, 0, 0), (255, 0, 0), (0, 0, 97)),
])
def test_detected_outline_with_matching_bodywork(panel, backing, ink):
    crop = np.full((100, 230, 3), panel, np.uint8)
    cv2.rectangle(crop, (16, 19), (212, 81), ink, -1)
    cv2.rectangle(crop, (19, 22), (209, 78), backing, -1)
    cv2.putText(crop, "AB 123", (36, 65), 0, 1.2, ink, 3)
    polygon = plate_outline.lettering(crop)
    assert polygon is not None
    mask = np.zeros(crop.shape[:2], np.uint8)
    cv2.fillPoly(mask, [np.rint(polygon).astype(np.int32)], 1)
    glyphs = np.all(crop[28:73, 28:194] == ink, axis=2)
    assert mask[28:73, 28:194][glyphs].all()
    assert not mask[:15].any() and not mask[85:].any()


def test_panel_outline_without_lettering():
    crop = np.zeros((100, 230, 3), np.uint8)
    cv2.rectangle(crop, (16, 19), (212, 81), (220, 220, 220), -1)
    assert plate_outline.lettering(crop) is None


def test_motion_follows_letters_and_resets_at_a_cut():
    rng = np.random.default_rng(8)
    image = rng.integers(0, 256, (120, 220, 3), dtype=np.uint8)
    quad = np.float32([[51,45], [149,46], [148,64], [50,63]])
    tracker = plate_outline.StripTracker()
    box = (43,35,160,76,.93)
    tracker.step(image, 0, [box], [[quad]], 30, False, lambda b: True)
    translated = np.roll(image, 5, axis=1)
    predicted = tracker.step(translated, 1, [], [], 30, False, lambda b: True)
    assert len(predicted) == 1 and not predicted[0][2]
    assert np.max(np.abs(predicted[0][1][0] - quad - [5,0])) < 1
    assert tracker.step(translated, 2, [], [], 30, True, lambda b: True) == []


def test_geometry_is_not_carried_through_an_excluded_zone():
    rng = np.random.default_rng(7)
    image = rng.integers(0, 256, (90, 180, 3), dtype=np.uint8)
    quad = np.float32([[21,26], [100,27], [100,45], [21,44]])
    tracker = plate_outline.StripTracker()
    tracker.step(image, 0, [(10,10,130,60,.9)], [[quad]], 30, False, lambda b: True)
    assert tracker.step(image, 1, [], [], 30, False, lambda b: False) == []


def test_reverse_follow_can_recover_an_entry_but_stops_at_the_cut():
    rng = np.random.default_rng(4)
    image = rng.integers(0, 256, (96, 180, 3), dtype=np.uint8)
    frames = [np.roll(image, i * 3, axis=1) for i in range(8)]
    quad = np.float32([[50, 35], [130, 35], [130, 58], [50, 58]])
    seed = object()
    samples = {7: {1: (seed, [quad])}}

    class Capture:
        def __init__(self):
            self.images = iter(frames)

        def read(self):
            return True, next(self.images)

    found = list(plate_outline.reverse_strips(samples, Capture(), 30, 0, {3}, lambda: None))
    assert [i for i, *_ in found] == [6, 5, 4, 3]
    for i, row, template, projected in found:
        assert row is None and template is seed
        assert np.max(np.abs(projected - quad + [(7 - i) * 3, 0])) < 1


def test_edge_fragment_reaches_the_actual_plate_boundary():
    image = np.full((100, 200, 3), 45, np.uint8)
    cv2.rectangle(image, (103, 44), (199, 68), (220, 220, 220), -1)
    cv2.putText(image, "A 381", (110, 63), 0, .6, (15, 15, 15), 2)
    seed = np.float32([[105, 40], [203, 40], [203, 59], [105, 59]])
    polygon = plate_outline.edge_fragment(image, seed)
    assert polygon is not None and polygon[:, 0].max() >= 199
    assert cv2.pointPolygonTest(np.float32(polygon), (197., 66.), False) >= 0
    assert polygon[:, 1].max() <= 72


def test_continuous_mask_keeps_both_lettering_estimates_and_a_separate_line():
    first = np.float32([[0, 0], [.8, 0], [.8, .2], [0, .2]])
    second = first + np.float32([.09, .02])
    separate = first + np.float32([0, .6])
    merged = plate_outline.continuous_mask([first, second, separate])
    assert len(merged) == 2
    for point in np.vstack((first, second)):
        assert cv2.pointPolygonTest(np.float32(merged[0]), tuple(map(float, point)), False) >= 0
    np.testing.assert_allclose(merged[1], separate)


def test_steady_interpolation_preserves_plate_when_corner_labels_flip():
    from openscrub_internal.steady_plate import trajectory
    gray = np.zeros((100, 100), np.uint8)
    quad = np.float32([[40, 12], [45, 80], [58, 79], [53, 11]])
    anchors = {0: quad, 2: np.roll(quad, 2, axis=0)}
    result = trajectory([gray] * 3, anchors)
    np.testing.assert_allclose(result[1], quad)


def test_plate_crossing_dropout_and_offscreen_return():
    from types import SimpleNamespace
    from openscrub_internal.steady_plate import assign_appearances
    def sample(i, x):
        return SimpleNamespace(t_start=i/30, cbox=(x, 20, x+20, 30), aoff=(0, 0))
    # One plate moves right, the other left. The first is missed on frame 3.
    right = [sample(i, 30+6*i) for i in (0, 1, 2, 4, 5)]
    left = [sample(i, 78-6*i) for i in range(6)]
    exiting = [sample(i, x) for i, x in [(10, 4), (11, 0), (14, 0), (15, 4)]]
    _, bounds = assign_appearances(left+right+exiting, 30, 140, 60, [10], 0)
    assert len({r.track for r in right}) == len({r.track for r in left}) == 1
    assert right[0].track != left[0].track
    before, after = exiting[1].track, exiting[2].track
    assert before != after and bounds[before][1] == 11 and bounds[after][0] == 14


def test_ambiguous_motion_retains_both_locations():
    from openscrub_internal.steady_plate import trajectory
    gray = np.zeros((80, 200), np.uint8)
    quad = np.float32([[10, 30], [55, 30], [55, 45], [10, 45]])
    other = quad + [90, 0]
    alternatives = {}
    path = trajectory([gray]*3, {0: quad, 2: np.float32(other)}, alternatives=alternatives)
    np.testing.assert_allclose(path[1], quad)
    np.testing.assert_allclose(alternatives[1], other)
