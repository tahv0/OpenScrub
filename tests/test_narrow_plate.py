"""Safety and localization coverage for optional lettering-only plates."""

import cv2
import numpy as np

import openscrub


def test_guard_preserves_disconnected_letter_regions():
    crop = np.full((80, 220, 3), 240, np.uint8)
    for x in (35, 145):
        cv2.rectangle(crop, (x, 25), (x + 20, 55), (20, 20, 20), -1)
    probability = np.zeros((80, 220), np.float32)
    probability[27:54, 37:54] = .9
    probability[27:54, 147:164] = .9

    polygons, reason = openscrub._narrow_from_probability(crop, probability)
    mask = np.zeros(crop.shape[:2], np.uint8)
    cv2.fillPoly(mask, [np.rint(p).astype(np.int32) for p in polygons], 1)
    assert reason == ""
    assert len(polygons) == 2
    assert mask[40, 45] and mask[40, 155]
    assert not mask[40, 105]


def test_guard_rejects_low_contrast_and_uncovered_letters():
    crop = np.full((80, 220, 3), 240, np.uint8)
    probability = np.zeros((80, 220), np.float32)
    probability[27:54, 37:54] = .9
    assert openscrub._narrow_from_probability(crop, probability)[1] == 'unverifiable_contrast'
    for x in (35, 145):
        cv2.rectangle(crop, (x, 25), (x + 20, 55), (20, 20, 20), -1)
    assert openscrub._narrow_from_probability(crop, probability)[1] == 'residual_text_evidence'


def test_guard_keeps_distinct_rows_and_hyphen():
    crop = np.full((100, 240, 3), 240, np.uint8)
    prob = np.zeros((100, 240), np.float32)
    for x1, y1, x2, y2 in ((40, 20, 60, 45), (80, 29, 91, 33),
                            (110, 20, 130, 45), (55, 65, 68, 80)):
        cv2.rectangle(crop, (x1, y1), (x2, y2), (20, 20, 20), -1)
        prob[y1+1:y2, x1+1:x2] = .9
    polygons, reason = openscrub._narrow_from_probability(crop, prob)
    assert reason == '' and len(polygons) == 4


def test_plate_localization_missing_model_and_clipped_crop():
    detector = openscrub.TextRegionDetector.__new__(openscrub.TextRegionDetector)
    detector.sess = None
    frame = np.full((80, 220, 3), 240, np.uint8)
    assert detector.find_plate(frame, (10, 10, 180, 70))[1] == 'model_unavailable'
    assert detector.find_plate(frame, (-1, 10, 180, 70))[1] == 'invalid_crop'
    assert detector.find_plate(frame, (float('nan'), 10, 180, 70))[1] == 'invalid_crop'


def test_corrupt_cached_text_model_disables_narrow_localization(tmp_path, monkeypatch):
    (tmp_path / 'text_detection_ppocrv5_mobile.onnx').write_bytes(b'x' * 10001)
    monkeypatch.setattr(openscrub, '_model_dir', lambda: str(tmp_path))
    detector = openscrub.TextRegionDetector(verify_hash=True)
    frame = np.full((60, 120, 3), 240, np.uint8)
    assert not detector.available()
    assert detector.find_plate(frame, (10, 10, 100, 50))[1] == 'model_unavailable'
