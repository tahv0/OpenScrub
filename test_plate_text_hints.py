"""Bounded local known-plate evidence; all identifiers here are synthetic."""
import shutil

import cv2
import numpy as np
import pytest


def api():
    # A missing implementation should report an ordinary, explanatory failure.
    try:
        import plate_text_hints
    except ImportError:
        pytest.fail("known-plate hint discovery module is not implemented")
    return plate_text_hints


def test_normalization_validates_limits_and_preserves_distinct_targets():
    m = api()
    assert m.normalize_hints("ab-c 123; XY987\nABC123") == ["ABC123", "XY987"]
    assert m.normalize_hints(["ab123", "CD-456"]) == ["AB123", "CD456"]
    assert m.normalize_hints("ABC123\n\nXY987\n") == ["ABC123", "XY987"]
    for value in (None, "", [], "A1", "X" * 17, "AB/123", "ÅBC123",
                  ["ABC123"] * 11, " " * 1025, ["ABC123", 123]):
        with pytest.raises(ValueError):
            m.normalize_hints(value)


def test_exact_matches_outrank_meaningful_partial_without_character_substitution():
    m = api()
    exact = m.match_text("ABC 1234", ["ABC1234"])
    partial = m.match_text("BC123", ["ABC1234"])
    assert exact["match_kind"] == "exact"
    assert partial["match_kind"] == "partial"
    assert exact["match_strength"] > partial["match_strength"]
    assert partial["matched_target"] == "ABC1234"
    assert partial["matched_text"] == "BC123"
    assert m.match_text("ABC", ["ABC1234"]) is None  # less than half
    assert m.match_text("AB", ["AB123"]) is None
    assert m.match_text("ABQXYZ", ["ABC123"]) is None
    assert m.match_text("ABO1", ["AB01"]) is None


def plate_frame():
    image = np.full((250, 500, 3), 35, np.uint8)
    cv2.rectangle(image, (120, 90), (380, 155), (250, 250, 250), -1)
    cv2.rectangle(image, (120, 90), (380, 155), (0, 0, 0), 3)
    cv2.putText(image, "ABC 123", (138, 138), cv2.FONT_HERSHEY_SIMPLEX,
                1.15, (0, 0, 0), 3, cv2.LINE_AA)
    return image


def test_split_tokens_join_and_partial_protects_entire_candidate():
    m = api()
    def reader(image):
        return [("ABC", (10, 15, 70, 45), .9),
                ("123", (78, 15, 140, 45), .8)]
    proposals = m.search_frame(plate_frame(), ["ABC123"],
                              regions=[(120, 90, 380, 155)], reader=reader)
    candidate = next(p for p in proposals if p["provenance"]["candidate"] == "provided_region")
    assert candidate["match_kind"] == "exact"
    assert candidate["review_status"] == "unreviewed"
    assert candidate["source_box"][0] <= 120 and candidate["source_box"][1] <= 90
    assert candidate["source_box"][2] >= 380 and candidate["source_box"][3] >= 155
    assert candidate["protection_box"] == candidate["source_box"]
    assert candidate["text_box"][2] < candidate["protection_box"][2]
    partial = m.search_frame(plate_frame(), ["ABC123"],
        regions=[(120, 90, 380, 155)],
        reader=lambda image: [("ABC", (20, 15, 100, 45), .9)])
    candidate = next(p for p in partial if p["provenance"]["candidate"] == "provided_region")
    assert candidate["match_kind"] == "partial"
    assert candidate['provenance']['boundary_requires_review'] is True
    assert candidate["protection_box"][0] <= 120 and candidate["protection_box"][1] <= 90
    assert candidate["protection_box"][2] >= 380 and candidate["protection_box"][3] >= 155


@pytest.mark.parametrize("attempt", range(8))
def test_inverse_mapping_rectification_rotation_and_mirror(attempt):
    m = api()
    flat = np.full((81, 241, 3), 230, np.uint8)
    flat[20:55, 50:170] = (0, 0, 255)
    source_quad = np.float32([[80, 70], [320, 85], [300, 165], [65, 145]])
    transform = cv2.getPerspectiveTransform(np.float32([[0, 0], [240, 0],
                                                       [240, 80], [0, 80]]), source_quad)
    frame = cv2.warpPerspective(flat, transform, (400, 240))
    calls = []
    def reader(image):
        index = len(calls)
        calls.append(image.shape)
        if index != attempt:
            return []
        mask = (image[:, :, 2] > 180) & (image[:, :, 0] < 70)
        ys, xs = np.where(mask)
        return [("ABC123", (xs.min(), ys.min(), xs.max(), ys.max()), .9)]
    proposals = m.search_frame(frame, ["ABC123"], regions=[source_quad], reader=reader)
    proposal = next(p for p in proposals if p["provenance"]["candidate"] == "provided_region")
    # Hand specified source correspondence, independent of production helpers.
    expected = cv2.perspectiveTransform(np.float32([[[50,20],[169,20],
                                                    [169,54],[50,54]]]), transform)[0]
    actual = np.array(proposal["text_quad"])
    for point in expected:
        assert np.min(np.linalg.norm(actual - point, axis=1)) < 4.0
    assert proposal["orientation"] == {"rotation": (attempt % 4) * 90,
                                        "mirrored": attempt >= 4}


def test_discovers_plate_like_contour_without_detector_region():
    m = api()
    proposals = m.search_frame(plate_frame(), ["ABC123"],
        reader=lambda image: [("ABC123", (5, 5, image.shape[1]-5,
                                                   image.shape[0]-5), .9)])
    local = [p for p in proposals if p["provenance"]["candidate"] == "plate_contour"]
    assert local
    assert any(p["source_box"][0] <= 125 and p["source_box"][2] >= 375 for p in local)


def test_discovery_slots_survive_many_preexisting_detector_boxes():
    m = api()
    proposals = m.search_frame(plate_frame(), ["ABC123"],
        regions=[(i, 20, i+35, 35) for i in range(0, 400, 45)],
        reader=lambda image: [("ABC123", (2, 2, image.shape[1]-2,
                                                   image.shape[0]-2), .9)])
    assert any(p["provenance"]["candidate"] == "plate_contour" for p in proposals)


def test_invalid_regions_are_ignored_and_explicit_normalized_quad_maps_to_pixels():
    m = api()
    proposal = m.search_frame(plate_frame(), ["ABC123"], regions=[
        (1, 2), {"box": [1, 2, 3, 4], "quad": [[float("inf"), 1]]*4},
        {"box": [100, 70, 400, 170], "plate_quad": [[.1,.2],[.9,.2],[.9,.8],[.1,.8]],
         "plate_quad_normalized": True}],
        reader=lambda image: [("ABC123", (2, 2, image.shape[1]-2,
                                                   image.shape[0]-2), .9)]
        if image.shape[:2] == (101, 401) else [])
    supplied = next(p for p in proposal if p["provenance"]["candidate"] == "provided_region")
    assert supplied["source_box"] == [130, 90, 370, 150]


def test_protection_preserves_half_open_frame_edge_box():
    m = api()
    result = m.search_frame(plate_frame(), ["ABC123"], regions=[(0, 0, 500, 250)],
        reader=lambda image: [("ABC", (5, 5, 30, 30), .9)])
    assert result[0]["protection_box"] == [0, 0, 500, 250]


def test_missing_tesseract_fails_actionably_without_exiting(monkeypatch):
    m = api()
    pytest.importorskip("pytesseract")
    monkeypatch.setattr(m.shutil, "which", lambda command: None)
    monkeypatch.setattr(m.os.path, "isfile", lambda path: False)
    with pytest.raises(RuntimeError, match="Tesseract.*openscrub-setup"):
        m.search_frame(plate_frame(), ["ABC123"])


def test_full_frame_text_fallback_rejects_partial_evidence():
    m = api()
    frame = np.full((120, 240, 3), 100, np.uint8)
    partial = m.search_frame(frame, ["ABC123"],
        reader=lambda image: [("ABC", (10, 10, 80, 40), .9)])
    assert partial == []
    full = m.search_frame(frame, ["ABC123"],
        reader=lambda image: [("ABC123", (10, 10, 100, 40), .9)])
    assert full and full[0]["provenance"]["candidate"] == "full_frame_text"
    # Protect the entire OCR number plus margin, not all of a full video frame.
    assert full[0]["protection_box"][0] < full[0]["text_box"][0]
    assert full[0]["protection_box"][2] > full[0]["text_box"][2]


def test_full_frame_fallback_preserves_legible_resolution():
    m = api()
    image = np.full((720, 1280, 3), 100, np.uint8)
    def reader(view):
        # A whole video frame must not be crushed to plate-crop height (~100px).
        return [("ABC123", (400, 300, 500, 330), .9)] if view.shape[:2] == (720, 1280) else []
    result = m.search_frame(image, ["ABC123"], reader=reader)
    assert result
    assert result[0]["text_box"] == [400, 300, 500, 330]


@pytest.mark.parametrize("exact_box", [(52, 35, 168, 65), (80, 35, 130, 65)])
def test_full_frame_exact_replaces_overlap_partial_without_shrinking_protection(exact_box):
    m = api()
    frame = np.full((120, 240, 3), 100, np.uint8)
    def reader(view):
        if view.shape[:2] == (120, 240):
            return [("ABC123", exact_box, .9)]
        return [("ABC", (5, 5, min(45, view.shape[1]-1), min(25, view.shape[0]-1)), .9)]
    result = m.search_frame(frame, ["ABC123"], regions=[(40, 20, 180, 80)], reader=reader)
    assert len(result) == 1
    assert result[0]["match_kind"] == "exact"
    assert result[0]["protection_box"][0] <= 40
    assert result[0]["protection_box"][1] <= 20
    assert result[0]["protection_box"][2] >= 180
    assert result[0]["protection_box"][3] >= 80
    assert result[0]["source_box"] == result[0]["protection_box"]
    assert result[0]["review_status"] == "unreviewed"


def test_full_frame_keeps_equal_strength_nonoverlapping_targets():
    m = api()
    frame = np.full((120, 240, 3), 100, np.uint8)
    result = m.search_frame(frame, ["ABC123", "XYZ987"], reader=lambda view: [
        ("ABC123", (10, 10, 85, 30), .9),
        ("XYZ987", (150, 80, 225, 100), .9)])
    assert {row["matched_target"] for row in result} == {"ABC123", "XYZ987"}
    assert len(result) == 2
    assert all(row["match_kind"] == "exact" for row in result)


def test_full_frame_keeps_distinct_instances_of_same_target():
    m = api()
    frame = np.full((120, 240, 3), 100, np.uint8)
    result = m.search_frame(frame, ["ABC123"], reader=lambda view: [
        ("ABC123", (10, 10, 85, 30), .9),
        ("ABC123", (150, 80, 225, 100), .9)])
    assert len(result) == 2


def test_full_frame_many_distinct_hits_stop_at_proposal_limit():
    m = api()
    frame = np.full((480, 1280, 3), 100, np.uint8)
    hits = [("ABC123", (20+240*x, 20+100*y, 100+240*x, 40+100*y), .9)
            for y in range(4) for x in range(5)]
    result = m.search_frame(frame, ["ABC123"], reader=lambda view: hits)
    assert len(result) == 12


def test_cancel_and_bounded_attempts_and_unreadable_frame():
    m = api()
    calls = []
    def unreadable(image):
        calls.append(image.shape)
        return []
    frame = plate_frame()
    assert m.search_frame(frame, ["ABC123"], reader=unreadable,
                          cancelled=lambda: True) == []
    assert calls == []
    assert m.search_frame(frame, ["ABC123"],
        regions=[(i, 30, i+45, 50) for i in range(0, 400, 10)], reader=unreadable) == []
    assert len(calls) <= 48
    assert m.search_frame(None, ["ABC123"], reader=unreadable) == []
    calls.clear()
    m.search_frame(frame, ["ABC123"], reader=unreadable,
                   cancelled=lambda: len(calls) >= 2)
    assert len(calls) == 2


def test_many_ocr_hits_remain_bounded_and_bad_boxes_are_ignored():
    m = api()
    hits = [("ABC123", (x, 5, x+15, 15), .9) for x in range(0, 5000, 20)]
    hits += [("ABC123", (float("nan"), 2, 3, 4), .9)]
    result = m.search_frame(plate_frame(), ["ABC123"], reader=lambda image: hits)
    assert len(result) <= 12
    assert all(p["review_status"] == "unreviewed" for p in result)


@pytest.mark.skipif(not shutil.which("tesseract"), reason="Tesseract not installed")
def test_real_local_tesseract_synthetic_plate_smoke():
    m = api()
    pytest.importorskip("pytesseract")
    image = np.full((160, 600, 3), 255, np.uint8)
    cv2.putText(image, "ABC123", (35, 112), cv2.FONT_HERSHEY_SIMPLEX,
                2.8, (0, 0, 0), 5, cv2.LINE_AA)
    result = m.search_frame(image, ["ABC123"], regions=[(0, 0, 600, 160)])
    assert any(p["match_kind"] == "exact" for p in result)
