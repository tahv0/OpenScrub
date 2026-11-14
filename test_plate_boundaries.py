"""Source-frame plate geometry: perspective fitting, privacy gates and tracking."""
import cv2
import numpy as np
import pytest

import plate_boundaries as edges
import video_learning as learning


def _trapezoid():
    mask = np.zeros((100, 180), np.uint8)
    truth = np.array([[25, 18], [145, 28], [123, 72], [38, 65]], np.int32)
    cv2.fillConvexPoly(mask, truth, 1)
    return mask, truth


def test_learned_trapezoid_preserves_perspective_and_covers_mask():
    mask, truth = _trapezoid()
    points, method, reason = edges.safe_plate_boundary(
        mask, [20, 14, 151, 78], [0, 0], (100, 180, 3))
    assert reason == '' and method == 'perspective'
    assert points.shape == (4, 2)
    assert cv2.isContourConvex(np.rint(points).astype(np.int32).reshape(-1, 1, 2))
    assert abs(points[0, 1] - points[1, 1]) > 3  # slanted top
    # Its top and bottom have different lengths (not a rectangular YOLO box).
    assert abs(np.linalg.norm(points[1]-points[0]) -
               np.linalg.norm(points[2]-points[3])) > 10
    filled = np.zeros_like(mask)
    cv2.fillConvexPoly(filled, np.rint(points).astype(np.int32), 1)
    assert (np.logical_and(mask, filled == 0).sum() / mask.sum()) < .005
    assert np.ptp(points[:, 0]) < 180 and np.ptp(points[:, 1]) < 100


def test_tiny_unrelated_segmentation_is_never_used_to_shrink_a_plate():
    mask = np.zeros((100, 180), np.uint8)
    cv2.rectangle(mask, (88, 46), (96, 50), 1, -1)
    points, method, reason = edges.safe_plate_boundary(
        mask, [20, 14, 151, 78], [0, 0], (100, 180, 3))
    assert points is method is None
    assert 'conceal too little' in reason


def test_learned_outline_must_be_inside_exact_source_frame():
    mask, _ = _trapezoid()
    points, method, reason = edges.safe_plate_boundary(
        mask, [150, 14, 275, 78], [130, 0], (100, 250, 3))
    assert points is method is None
    assert 'source frame' in reason


def test_invalid_empty_and_nan_masks_do_not_generate_plate_corners():
    for mask in [None, np.zeros((40, 40), np.uint8),
                 np.array([[float('nan')]*20]*20),
                 np.zeros((1, 1), np.uint8)]:
        corners, coverage = edges.conservative_quad(mask)
        assert corners is None and coverage is None


def test_alternating_learned_corner_geometry_falls_back_to_detector_for_each_frame():
    """Drastic frame-to-frame changes cannot leave an arbitrarily thin mask."""
    a = dict(category='plate', track=7, frame_index=15,
             plate_boundary_source='learned_perspective', enabled=True,
             plate_quad=[[.1, .1], [.6, .1], [.6, .8], [.1, .8]],
             poly=[[[.1, .1], [.6, .1], [.6, .8], [.1, .8]]],
             mask_pad=0)
    b = dict(category='plate', track=7, frame_index=16,
             plate_boundary_source='learned_perspective', enabled=True,
             plate_quad=[[.6, .1], [1., .1], [1., .8], [.6, .8]],
             poly=[[[.6, .1], [1., .1], [1., .8], [.6, .8]]],
             mask_pad=0)
    assert learning._guard_temporal_plate_boundaries([a, b], 30) == 2
    for row in [a, b]:
        assert row['enabled'] is True
        assert row['plate_quad'] == [] and row['poly'] == []
        assert row['mask_pad'] == -1
        assert row['plate_boundary_source'] == 'detector_fallback'
        assert 'detector coverage' in row['learning_conflict']


def test_adjacent_smooth_learned_corners_keep_independent_frame_geometry():
    def detection(frame, shift):
        return dict(category='plate', track=7, frame_index=frame, enabled=True,
                    plate_boundary_source='learned_perspective',
                    plate_quad=[[.1+shift,.1],[.9,.08],[.95,.8],[.08,.9]],
                    poly=[[[.1+shift,.1],[.9,.08],[.95,.8],[.08,.9]]])
    a, b = detection(15, 0.), detection(16, .02)
    assert learning._guard_temporal_plate_boundaries([a,b],30) == 0
    assert a['plate_quad'] != b['plate_quad']
    assert a['plate_boundary_source'] == b['plate_boundary_source'] == 'learned_perspective'


def test_protected_human_corners_are_not_overwritten_by_learned_fallback():
    row = dict(category='plate', human_region_confirmed=True, enabled=True,
               plate_boundary_source='human_corners',
               plate_quad=[[.1,.1],[.8,.1],[.9,.8],[.1,.9]],
               poly=[])
    before = list(row['plate_quad'])
    learning._fallback_plate_boundary(row, 'uncertain model')
    assert row['plate_quad'] == before
    assert row['plate_boundary_source'] == 'human_corners'
