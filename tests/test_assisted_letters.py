"""Mode switch for the assisted plate-letters cover."""

import cv2
import numpy as np
import pytest

import openscrub


def test_assisted_needs_explicit_permission():
    parser = openscrub.build_parser()
    with pytest.raises(SystemExit):
        openscrub._prep_args(parser.parse_args(["x.mp4", "--plate-coverage", "assisted"]), parser)
    args = openscrub._prep_args(parser.parse_args(
        ["x.mp4", "--plate-coverage", "assisted", "--no-box-fallback"]), parser)
    assert args.plate_coverage == "assisted"
    settings = openscrub._settings_dict(args)
    assert settings["plate_coverage"] == "assisted"
    assert "no_box_fallback" not in settings and "plate_narrow_margin" not in settings


def test_full_and_narrow_settings_unchanged():
    parser = openscrub.build_parser()
    args = openscrub._prep_args(parser.parse_args(["x.mp4"]), parser)
    assert "plate_coverage" not in openscrub._settings_dict(args)
    narrow = openscrub._prep_args(parser.parse_args(
        ["x.mp4", "--plate-coverage", "narrow", "--plate-narrow-margin", "2"]), parser)
    settings = openscrub._settings_dict(narrow)
    assert settings["plate_coverage"] == "narrow" and settings["plate_narrow_margin"] == 2


def test_saved_assisted_survives_from_report_restore(tmp_path, monkeypatch):
    source = str(tmp_path / "original.mp4")
    writer = cv2.VideoWriter(source, cv2.VideoWriter_fourcc(*"mp4v"), 10, (96, 64))
    assert writer.isOpened()
    writer.write(np.full((64, 96, 3), 220, np.uint8))
    writer.release()
    parser = openscrub.build_parser()
    scan_args = openscrub._prep_args(parser.parse_args(
        [source, "--plate-coverage", "assisted", "--no-box-fallback"]), parser)
    row = openscrub.Detection(0, .1, (10, 10, 80, 50), "plate", "plate", 1)
    report = tmp_path / "report.json"
    openscrub.write_report(report, scan_args, {"fps": 10, "cum": [(0, 0)], "bands": [(0, 0)],
                                               "detections": [row]})
    output = str(tmp_path / "out.mp4")
    args = openscrub._prep_args(parser.parse_args(
        [source, "--from-report", str(report), "--mode", "box", "--pad", "0",
         "--encoder", "x264", "-o", output]), parser)
    assert not args.no_box_fallback  # a saved report must not need the flag
    # The coverage restore runs before encoding; stop there so no ffmpeg is needed.
    monkeypatch.setattr(openscrub, "_render_into", lambda *a, **k: None)
    openscrub.run_pipeline(args)
    assert args.plate_coverage == "assisted"


# --- scan: letter masks and scene cuts -------------------------------------

FRAME = np.full((200, 400, 3), 230, np.uint8)
BOX = (50, 50, 350, 150)
# Box-normalized rectangles the fake text model "finds".
SPECK = (.45, .45, .5, .55)
LEFT_HALF = (.05, .3, .6, .7)
RIGHT_HALF = (.4, .3, .95, .7)
WORD = (.1, .3, .9, .7)


class _SizedSession:
    """Fake text model: the outline it returns depends on the input size."""

    def __init__(self, outlines, sizes_run):
        self.outlines, self.sizes_run = outlines, sizes_run

    def run(self, outputs, inputs):
        blob = next(iter(inputs.values()))
        h, w = blob.shape[2:]
        size = max(h, w)
        self.sizes_run.append(size)
        prob = np.zeros((h, w), np.float32)
        rect = self.outlines.get(size)
        if rect:
            x1, y1, x2, y2 = rect
            prob[int(y1 * h):int(y2 * h), int(x1 * w):int(x2 * w)] = .9
        return [prob[None, None]]


def fake_text_detector(outlines):
    det = openscrub.TextRegionDetector.__new__(openscrub.TextRegionDetector)
    det.sizes_run = []
    det.sess, det._in = _SizedSession(outlines, det.sizes_run), "x"
    det.log = lambda *a: None
    return det


def covers(polys, rects):
    x1, y1, x2, y2 = BOX
    mask = np.zeros(FRAME.shape[:2], np.uint8)
    for p in polys:     # one call per polygon: a joint call XORs overlaps
        cv2.fillPoly(mask, [np.rint(p).astype(np.int32)], 1)
    for rx1, ry1, rx2, ry2 in rects:
        for fx in (rx1 + .05, (rx1 + rx2) / 2, rx2 - .05):
            if not mask[int(y1 + (ry1 + ry2) / 2 * (y2 - y1)), int(x1 + fx * (x2 - x1))]:
                return False
    inside = all(x1 <= x <= x2 and y1 <= y <= y2 for p in polys for x, y in p)
    return inside


def test_find_letters_uses_320_first_and_unions_fallback_sizes():
    det = fake_text_detector({320: SPECK, 640: LEFT_HALF, 224: RIGHT_HALF})
    polys = det.find_letters(FRAME, BOX)
    assert det.sizes_run == [320, 640, 224]
    assert covers(polys, [LEFT_HALF, RIGHT_HALF])
    det = fake_text_detector({320: WORD})
    assert det.find_letters(FRAME, BOX) and det.sizes_run == [320]
    det = fake_text_detector({320: SPECK, 640: SPECK})
    assert det.find_letters(FRAME, BOX) == [] and det.sizes_run == [320, 640, 224]
    # an outline larger than the plate box is clipped into it, not dropped
    det = fake_text_detector({320: (0, 0, 1, 1)})
    polys = det.find_letters(FRAME, BOX)
    assert det.sizes_run == [320] and covers(polys, [WORD])
    det.sess = None
    assert det.find_letters(FRAME, BOX) == []


def _guard_cases():
    """The strict guard's fixtures (tests/test_narrow_plate.py) plus failure cases."""
    cases = {}
    crop = np.full((80, 220, 3), 240, np.uint8)
    prob = np.zeros((80, 220), np.float32)
    prob[27:54, 37:54] = .9
    prob[27:54, 147:164] = .9
    cases["blank_crop"] = (crop.copy(), prob)
    lettered = crop.copy()
    for x in (35, 145):
        cv2.rectangle(lettered, (x, 25), (x + 20, 55), (20, 20, 20), -1)
    cases["two_letters"] = (lettered, prob)
    one = np.zeros((80, 220), np.float32)
    one[27:54, 37:54] = .9
    cases["uncovered_letter"] = (lettered, one)
    crop = np.full((100, 240, 3), 240, np.uint8)
    prob = np.zeros((100, 240), np.float32)
    for x1, y1, x2, y2 in ((40, 20, 60, 45), (80, 29, 91, 33),
                            (110, 20, 130, 45), (55, 65, 68, 80)):
        cv2.rectangle(crop, (x1, y1), (x2, y2), (20, 20, 20), -1)
        prob[y1 + 1:y2, x1 + 1:x2] = .9
    cases["rows_and_hyphen"] = (crop, prob)
    crop = np.full((120, 400, 3), 235, np.uint8)
    chars = range(40, 350, 45)
    for x in chars:
        cv2.rectangle(crop, (x, 22), (x + 26, 98), (130, 40, 15), -1)
    prob = np.zeros((120, 400), np.float32)
    prob[43:78, chars[1] + 14:chars[-1] + 14] = .9
    cases["missed_character"] = (crop, prob)
    edge = np.zeros((120, 400), np.float32)
    edge[0:40, 0:120] = .9
    cases["touches_edge"] = (crop, edge)
    cases["nothing"] = (crop, np.zeros((120, 400), np.float32))
    cases["tiny_crop"] = (np.zeros((6, 6, 3), np.uint8), np.zeros((6, 6), np.float32))
    cases["nan_prob"] = (crop, np.full((120, 400), np.nan, np.float32))
    return cases


# Recorded from _narrow_from_probability BEFORE it was split (polygons rounded).
ORIGINAL = {
    "blank_crop": ("unverifiable_contrast", []),
    "missed_character": ("residual_text_evidence", []),
    "nan_prob": ("inference_error", []),
    "nothing": ("no_text_detected", []),
    "rows_and_hyphen": ("", [
        [[71.469, 83.469], [51.531, 83.469], [51.531, 61.531], [71.469, 61.531]],
        [[91.227, 33.227], [79.773, 33.227], [79.773, 28.773], [91.227, 28.773]],
        [[136.573, 51.573], [103.427, 51.573], [103.427, 13.427], [136.573, 13.427]],
        [[66.573, 51.573], [33.427, 51.573], [33.427, 13.427], [66.573, 13.427]]]),
    "tiny_crop": ("invalid_crop", []),
    "touches_edge": ("invalid_geometry", []),
    "two_letters": ("", [
        [[170.429, 60.429], [139.571, 60.429], [139.571, 19.571], [170.429, 19.571]],
        [[60.429, 60.429], [29.571, 60.429], [29.571, 19.571], [60.429, 19.571]]]),
    "uncovered_letter": ("residual_text_evidence", []),
}


def test_strict_check_unchanged_by_the_split():
    for name, (crop, prob) in _guard_cases().items():
        polys, reason = openscrub._narrow_from_probability(crop, prob)
        summary = (reason, [np.round(np.asarray(p, np.float64), 3).tolist() for p in polys])
        assert summary == ORIGINAL[name], name


def _write_video(path, frames, cut_at):
    writer = cv2.VideoWriter(path, cv2.VideoWriter_fourcc(*"mp4v"), 10, (96, 64))
    assert writer.isOpened()
    for i in range(frames):
        colour = (200, 60, 30) if i >= cut_at else (40, 160, 220)
        image = np.full((64, 96, 3), colour, np.uint8)
        cv2.rectangle(image, (34, 25), (54, 35), (20, 20, 20), -1)
        writer.write(image)
    writer.release()


def scan_assisted(tmp_path, monkeypatch, windows=None, frames=6, cut_at=3, text=True):
    source = str(tmp_path / "scan.mp4")
    _write_video(source, frames, cut_at)
    seen = []

    class Plate:
        INPUT = 640
        def __init__(self, *a, **kw): pass
        def available(self): return True
        def find(self, frame, scale):
            assert scale == 1.0
            return [(10, 10, 80, 50, .9)]

    class Text:
        def __init__(self, *a, **kw): pass
        def available(self): return text
        def find_letters(self, frame, box):
            seen.append(tuple(box))
            self.last_sizes = (320,)
            # one outline inside the box, one sticking out of it (clipped)
            return [np.array([[20, 20], [70, 20], [70, 40], [20, 40]], np.float32),
                    np.array([[5, 30], [90, 30], [90, 45], [5, 45]], np.float32)]
        def find_plate(self, frame, box):
            raise AssertionError("assisted mode must not run the strict check")

    monkeypatch.setattr(openscrub, "PlateDetector", Plate)
    monkeypatch.setattr(openscrub, "TextRegionDetector", Text)
    parser = openscrub.build_parser()
    argv = [source, "--categories", "plate", "--plate-coverage", "assisted",
            "--no-box-fallback", "--scan-speed", "fastest", "--tile", "off", "--no-backtrack"]
    if windows:
        argv += ["--detect-windows-frac", windows]
    args = openscrub._prep_args(parser.parse_args(argv), parser)
    logs = []

    class CB(openscrub.Callbacks):
        def log(self, msg):
            logs.append(msg)

    state = openscrub.run_scan(args, CB())
    state["_seen"], state["_logs"] = seen, logs
    return state


def test_assisted_scan_stores_masks_and_cuts(tmp_path, monkeypatch):
    state = scan_assisted(tmp_path, monkeypatch)
    plates = [d for d in state["detections"] if d.category == "plate" and d.dense]
    assert any(d.poly for d in plates) and state["scene_cuts"] == [3]
    assert not any(isinstance(d, openscrub.NarrowPlateDetection) for d in state["detections"])
    assert len(state["_seen"]) == 6     # every frame, full resolution
    for d in plates:
        for poly in d.poly:
            assert all(0 <= v <= 1 for point in poly for v in point)
    row = next(d for d in plates if d.poly)
    # box (10,10)-(80,50): the inside outline maps to (10/70, 10/40)…
    assert row.poly[0][0] == pytest.approx((10 / 70, 10 / 40))
    assert row.poly[1][0] == (0.0, pytest.approx(20 / 40))
    assert ("      assisted letters: masks on 6 of 6 plate detections; sizes used "
            "320:6 640:0 224:0; text model 0.0 s") in state["_logs"]


def test_assisted_scan_without_text_model_keeps_plates(tmp_path, monkeypatch):
    state = scan_assisted(tmp_path, monkeypatch, text=False)
    plates = [d for d in state["detections"] if d.category == "plate"]
    assert plates and not any(d.poly for d in plates) and not state["_seen"]
    assert any("text model unavailable" in m for m in state["_logs"])


def test_fast_skip_resume_counts_as_a_cut(tmp_path, monkeypatch):
    state = scan_assisted(tmp_path, monkeypatch, windows="0-0.2,0.8-1.0", frames=40, cut_at=99)
    assert any("fast-skip" in m for m in state["_logs"])
    assert state["scene_cuts"] and min(state["scene_cuts"]) > 0
    assert 31 in state["scene_cuts"]   # first frame read after the 0.9 s -> 3.2 s jump


def test_other_modes_have_no_scene_cuts(tmp_path, monkeypatch):
    source = str(tmp_path / "plain.mp4")
    _write_video(source, 4, 2)
    parser = openscrub.build_parser()
    args = openscrub._prep_args(parser.parse_args(
        [source, "--categories", "none", "--tile", "off", "--no-backtrack"]), parser)
    assert "scene_cuts" not in openscrub.run_scan(args)


def test_scene_cuts_roundtrip_through_report(tmp_path):
    source = str(tmp_path / "original.mp4")
    _write_video(source, 1, 9)
    parser = openscrub.build_parser()
    args = openscrub._prep_args(parser.parse_args(
        [source, "--plate-coverage", "assisted", "--no-box-fallback"]), parser)
    row = openscrub.Detection(0, .1, (10, 10, 80, 50), "plate", "plate", 1)
    report = tmp_path / "report.json"
    openscrub.write_report(report, args, {"fps": 10, "cum": [(0, 0)], "bands": [(0, 0)],
                                          "detections": [row], "scene_cuts": [3, 7]})
    import json
    assert json.loads(report.read_text())["scene_cuts"] == [3, 7]
    plain = tmp_path / "plain.json"
    openscrub.write_report(plain, args, {"fps": 10, "cum": [(0, 0)], "bands": [(0, 0)],
                                         "detections": [row]})
    assert "scene_cuts" not in json.loads(plain.read_text())


def test_from_report_reads_scene_cuts_back(tmp_path, monkeypatch):
    source = str(tmp_path / "original.mp4")
    _write_video(source, 1, 9)
    parser = openscrub.build_parser()
    scan_args = openscrub._prep_args(parser.parse_args(
        [source, "--plate-coverage", "assisted", "--no-box-fallback"]), parser)
    row = openscrub.Detection(0, .1, (10, 10, 80, 50), "plate", "plate", 1)
    seen = []
    monkeypatch.setattr(openscrub, "run_render", lambda args, state, cb: seen.append(state))
    for name, extra in (("cuts.json", {"scene_cuts": [2]}), ("none.json", {})):
        report = tmp_path / name
        openscrub.write_report(report, scan_args, {"fps": 10, "cum": [(0, 0)], "bands": [(0, 0)],
                                                   "detections": [row], **extra})
        args = openscrub._prep_args(parser.parse_args(
            [source, "--from-report", str(report), "--mode", "box", "-o",
             str(tmp_path / "out.mp4")]), parser)
        openscrub.run_pipeline(args)
    assert seen[0]["scene_cuts"] == [2] and "scene_cuts" not in seen[1]
