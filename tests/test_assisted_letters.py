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
        def __init__(self, *a, **kw):
            if not text:
                self.error = "synthetic load failure"
        def available(self): return text
        def find_letters_many(self, frame, boxes):
            self.last_sizes_many = []
            out = []
            for box in boxes:
                seen.append(tuple(box))
                self.last_sizes_many.append((320,))
                # one outline inside the box, one sticking out of it (clipped)
                out.append([np.array([[20, 20], [70, 20], [70, 40], [20, 40]], np.float32),
                            np.array([[5, 30], [90, 30], [90, 45], [5, 45]], np.float32)])
            return out
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


def test_assisted_scan_without_text_model_is_refused(tmp_path, monkeypatch):
    # An overnight scan that can mask no letters would cover nothing at all.
    decoded = []
    real = openscrub.cv2.VideoCapture
    monkeypatch.setattr(openscrub.cv2, "VideoCapture",
                        lambda *a, **k: decoded.append(a) or real(*a, **k))
    with pytest.raises(RuntimeError) as err:
        scan_assisted(tmp_path, monkeypatch, text=False)
    assert str(err.value) == ("letters only, no box fallback needs the text model, "
                              "which could not be loaded: synthetic load failure")
    assert not decoded                          # refused before reading frames


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


# --- render: apply the cover plan --------------------------------------------

import importlib.util
import json
import shutil
import subprocess
import sys
from pathlib import Path
from types import MappingProxyType

from openscrub_internal import plate_policy

FPS = 10.0
PLATE = (20, 20, 140, 76)                 # frame pixels
LETTER_RECT = (.25, .3, .75, .7)          # box-normalized
# The letters' pixel area, inset 2 px against codec ringing at the edges.
LETTERS = (20 + 30 + 2, 20 + 16.8 + 2, 20 + 90 - 2, 20 + 39.2 - 2)


def _rect_poly(r):
    x1, y1, x2, y2 = r
    return (((x1, y1), (x2, y1), (x2, y2), (x1, y2)),)


def black_share(frame, region):
    x1, y1, x2, y2 = (int(round(v)) for v in region)
    roi = frame[y1:y2, x1:x2]
    return float((roi.max(axis=2) < 40).mean())


def _plain_video(path, frames, size=(160, 96)):
    writer = cv2.VideoWriter(str(path), cv2.VideoWriter_fourcc(*"mp4v"), FPS, size)
    assert writer.isOpened()
    for _ in range(frames):
        writer.write(np.full((size[1], size[0], 3), 220, np.uint8))
    writer.release()


def _read_all(path):
    cap = cv2.VideoCapture(str(path))
    frames = []
    while True:
        ok, frame = cap.read()
        if not ok:
            break
        frames.append(frame)
    cap.release()
    return frames


def _plate_row(i, poly=(), track=0, box=PLATE, origin=None, choice=None):
    row = openscrub.Detection(i / FPS, i / FPS + .03, box, "plate", "plate", .9,
                              dense=True, track=track, poly=poly)
    if origin is not None:
        row._plate_policy_evidence = MappingProxyType(
            {"origin": origin, "frame": i, "geometry_valid": True})
        row._plate_saved_enabled = True
        row._plate_output_choice = choice
    return row



def render_assisted(tmp_path, report=None):
    """5 frames: 0-1 masked, 2 borrows from 1, a cut at 3, 3-4 have no mask."""
    source = tmp_path / "assisted.mp4"
    output = tmp_path / "assisted_out.mp4"
    _plain_video(source, 5)
    rows = [_plate_row(i, _rect_poly(LETTER_RECT) if i < 2 else ()) for i in range(5)]
    parser = openscrub.build_parser()
    argv = [str(source), "--mode", "box", "--pad", "0",
            "--plate-coverage", "assisted", "--no-box-fallback", "-o", str(output)]
    if report:
        argv += ["--report", str(report)]
    args = openscrub._prep_args(parser.parse_args(argv), parser)
    state = {"fps": FPS, "cum": [(0, 0)] * 5, "bands": [(0, 0)] * 5,
             "detections": rows, "stats": {}, "scene_cuts": [3]}
    openscrub.run_render(args, state)
    return _read_all(output)


def test_assisted_render_masks_letters_and_leaves_gaps_visible(tmp_path):
    report = tmp_path / "report.json"
    out = render_assisted(tmp_path, report)
    assert len(out) == 5
    assert black_share(out[0], PLATE) < 0.8 and black_share(out[0], LETTERS) > 0.99
    assert black_share(out[1], LETTERS) > 0.99
    assert black_share(out[2], LETTERS) > 0.99 and black_share(out[2], PLATE) < 0.8
    assert black_share(out[3], PLATE) == 0
    assert black_share(out[4], PLATE) == 0
    doc = json.loads(report.read_text())
    assert doc["plate_letter_gaps"] == [
        {"track": 0, "t0": .3, "t1": .4, "frames": 2, "frame": 4, "box": list(PLATE)}]
    assert doc["plate_letter_stats"] == {"masked_frames": 3, "bridged_frames": 0, "gap_frames": 2}


def test_assisted_render_retires_a_trailing_cover_after_a_track_handoff(tmp_path):
    source = tmp_path / "handoff.mp4"
    output = tmp_path / "out.mp4"
    _plain_video(source, 5, size=(224, 112))
    letters = _rect_poly((.15, .2, .85, .8))
    # Track 0's held box and track 1's onset padding overlap. Track 2 is
    # nearby and was actually observed alongside track 1 on frame 2.
    def plate(track, frame, x, y, start, end):
        row = _plate_row(frame, letters, track, box=(x, y, x + 100, y + 36),
                         origin="detection")
        row.t_start, row.t_end = start / FPS, end / FPS
        row.last_seen = frame / FPS
        return row
    rows = [plate(0, 0, 10, 14, 0, 3), plate(1, 2, 31, 14, 0, 2),
            plate(1, 3, 34, 14, 3, 3), plate(2, 2, 34, 25, 2, 4)]
    parser = openscrub.build_parser()
    args = openscrub._prep_args(parser.parse_args([
        str(source), "--mode", "box", "--pad", "0", "--plate-coverage", "assisted",
        "--no-box-fallback", "-o", str(output)]), parser)
    state = {"fps": FPS, "cum": [(0, 0)] * 5, "bands": [(0, 0)] * 5,
             "detections": rows, "stats": {}, "scene_cuts": []}
    openscrub.run_render(args, state)
    frames = _read_all(output)
    assert black_share(frames[0], (28, 25, 39, 31)) > .99  # original position
    assert black_share(frames[0], (100, 25, 110, 31)) < .01  # no premature copy
    assert black_share(frames[1], (60, 25, 80, 31)) > .99  # no flash at handoff
    assert black_share(frames[2], (28, 25, 39, 31)) < .01  # old position retired
    assert black_share(frames[2], (55, 25, 100, 31)) > .99
    assert black_share(frames[3], (58, 46, 102, 49)) > .99  # second plate's hold


def test_assisted_bridge_rows_span_one_frame_on_the_ending_track():
    rows = [_plate_row(i, _rect_poly(LETTER_RECT)) for i in range(3)]
    rows += [_plate_row(i, _rect_poly(LETTER_RECT), track=1, box=(24, 20, 144, 76))
             for i in range(6, 9)]
    dets, plan = openscrub.apply_assisted_cover(rows, FPS, [])
    bridges = [d for d in dets if d not in rows]
    assert [round(d.t_start * FPS) for d in bridges] == [3, 4, 5]
    assert all(d.t_start == d.t_end and d.track == 0 and d.dense and d.category == "plate"
               and d.poly == _rect_poly(LETTER_RECT) for d in bridges)
    assert bridges[0].cbox[0] == pytest.approx(21)
    assert plan.stats["bridged_frames"] == 3 and not plan.gaps


def rows_after_policy(keep_track):
    rows = []
    for track, choice in ((3, None), (keep_track, "keep")):
        rows += [_plate_row(i, _rect_poly(LETTER_RECT) if i == 0 else (), track=track,
                            origin="detection", choice=choice) for i in range(3)]
        rows.append(_plate_row(30, (), track=track, origin="interpolation", choice=choice))
    undecided = [_plate_row(i, (), track=8, origin="detection") for i in range(3)]
    for row in undecided:
        row._plate_saved_enabled = False   # a card still waiting for review
    rows += undecided
    choices = plate_policy.evaluate(rows, None, None, None, capable_off=True)
    return [d for d, c in zip(rows, choices) if c.enabled]


def test_keep_and_undecided_plates_are_neither_covered_nor_gaps():
    dets, plan = openscrub.apply_assisted_cover(rows_after_policy(keep_track=7), 10.0, [])
    assert all(d.track != 7 for d in dets) and all(g.track != 7 for g in plan.gaps)
    assert all(d.track != 8 for d in dets) and all(g.track != 8 for g in plan.gaps)
    # track 3 is enabled: frames 1-2 borrow, the far synthetic sample at 3 s is a gap
    assert [g.frame for g in plan.gaps if g.track == 3] == [30]
    assert all(d.poly for d in dets)


def test_assisted_rows_without_evidence_count_as_direct():
    # A report without the uncertain plate policy has no evidence: rows are direct.
    rows = [_plate_row(0, ()), _plate_row(1, _rect_poly(LETTER_RECT))]
    dets, plan = openscrub.apply_assisted_cover(rows, FPS, [])
    assert [d.poly for d in dets] == [_rect_poly(LETTER_RECT)] * 2 and not plan.gaps


def row_with_quad_and_poly():
    return openscrub.Detection(0, .1, PLATE, "plate", "plate", .9, dense=True, track=0,
                               poly=_rect_poly(LETTER_RECT),
                               manual_plate_quad={"stand-in": True})


def test_manual_quad_wins_over_letter_mask(monkeypatch):
    monkeypatch.setattr(openscrub.plate_quad, "valid_record", lambda q: bool(q))
    dets, _ = openscrub.apply_assisted_cover([row_with_quad_and_poly()], 10.0, [])
    assert dets[0].manual_plate_quad and not dets[0].poly


def test_non_plate_rows_pass_through_unchanged():
    face = openscrub.Detection(0, .1, (1, 1, 9, 9), "face", "face", .9, dense=True, track=0)
    dets, _ = openscrub.apply_assisted_cover([face], FPS, [])
    assert dets == [face] and dets[0] is face


def test_assisted_narrow_row_becomes_a_plain_lettered_row():
    base = _plate_row(0, ())
    row = openscrub._record_narrow_plate(base, 0, None, (), 0, "no_text")
    dets, _ = openscrub.apply_assisted_cover([row, _plate_row(1, _rect_poly(LETTER_RECT))], FPS, [])
    assert not any(isinstance(d, openscrub.NarrowPlateDetection) for d in dets)
    assert all(d.poly for d in dets)


def test_assisted_cover_from_report_mirrors_the_render(tmp_path):
    source = tmp_path / "src.mp4"
    _plain_video(source, 1)
    parser = openscrub.build_parser()
    args = openscrub._prep_args(parser.parse_args(
        [str(source), "--plate-coverage", "assisted", "--no-box-fallback"]), parser)
    rows = [_plate_row(i, _rect_poly(LETTER_RECT) if i < 2 else ()) for i in range(5)]
    report = tmp_path / "r.json"
    openscrub.write_report(report, args, {"fps": FPS, "cum": [(0, 0)] * 5,
                                          "bands": [(0, 0)] * 5, "detections": rows,
                                          "scene_cuts": [3]})
    plan = openscrub.assisted_cover_from_report(json.loads(report.read_text()))
    assert [(g.track, g.frame, g.frames) for g in plan.gaps] == [(0, 4, 2)]
    assert plan.stats == {"masked_frames": 3, "bridged_frames": 0, "gap_frames": 2}


def test_assisted_cover_from_capable_report_applies_keep(tmp_path):
    doc = {"plate_policy_evidence_version": 1,
           "provenance": {"settings": {"uncertain_policy": "off"}},
           "render_state": {"fps": FPS, "cum": [[0, 0]] * 30, "bands": [[0, 0]] * 30},
           "detections": []}
    for track, choice in ((1, None), (2, "keep")):
        for i in range(3):
            doc["detections"].append({
                "t_start": i / FPS, "t_end": i / FPS + .03, "cbox": list(PLATE),
                "category": "plate", "text": "plate", "confidence": .9, "dense": True,
                "track": track, "enabled": True, "output_choice": choice,
                "poly": [] if i else [list(map(list, _rect_poly(LETTER_RECT)[0]))],
                "policy_evidence": {"origin": "detection", "frame": i, "geometry_valid": True}})
    doc["detections"].append({
        "t_start": 2.0, "t_end": 2.03, "cbox": list(PLATE), "category": "plate",
        "text": "plate", "confidence": .9, "dense": True, "track": 1, "enabled": True,
        "policy_evidence": {"origin": "interpolation"}})
    plan = openscrub.assisted_cover_from_report(doc)
    assert [(g.track, g.frame) for g in plan.gaps] == [(1, 20)]


@pytest.mark.skipif(shutil.which("ffmpeg") is None, reason="HDR render needs ffmpeg")
def test_assisted_hdr_render_masks_letters(tmp_path):
    src = tmp_path / "hdr.mkv"
    made = subprocess.run(["ffmpeg", "-v", "error", "-y", "-f", "lavfi", "-i",
                           "color=c=0xdddddd:s=160x96:r=10:d=0.5", "-pix_fmt", "yuv420p10le",
                           "-c:v", "libx265", "-x265-params", "log-level=error", str(src)])
    if made.returncode != 0:
        pytest.skip("ffmpeg has no libx265")
    out = tmp_path / "hdr_out.mkv"
    rows = [_plate_row(i, _rect_poly(LETTER_RECT) if i < 2 else ()) for i in range(5)]
    dets, _ = openscrub.apply_assisted_cover(rows, FPS, [3])
    openscrub._render_hdr_into(str(src), str(out), dets, [(0, 0)] * 5, [(0, 0)] * 5, FPS,
                               pad=0, mode="box", encoder="libx265", tags={})
    frames = _read_all(out)
    assert black_share(frames[0], LETTERS) > 0.95 and black_share(frames[0], PLATE) < 0.8
    assert black_share(frames[2], LETTERS) > 0.95
    assert black_share(frames[4], PLATE) < 0.05


# --- full and narrow renders unchanged against the base engine ---------------

BASE_COMMIT = "09086f6"
REPO = Path(__file__).resolve().parent.parent


def _base_engine(tmp_path):
    """Import openscrub.py and openscrub_internal as they were at BASE_COMMIT."""
    root = tmp_path / "base_engine"
    root.mkdir()
    try:
        code = subprocess.run(["git", "-C", str(REPO), "show", BASE_COMMIT + ":openscrub.py"],
                              check=True, capture_output=True).stdout
        tar = subprocess.run(["git", "-C", str(REPO), "archive", BASE_COMMIT, "openscrub_internal"],
                             check=True, capture_output=True).stdout
    except (OSError, subprocess.CalledProcessError):
        pytest.skip("base commit not available (no git checkout)")
    (root / "openscrub_base.py").write_bytes(code)
    subprocess.run(["tar", "-x", "-C", str(root)], input=tar, check=True)
    saved = {k: v for k, v in sys.modules.items()
             if k == "openscrub_internal" or k.startswith("openscrub_internal.")}
    for k in saved:
        del sys.modules[k]
    sys.path.insert(0, str(root))
    try:
        spec = importlib.util.spec_from_file_location(
            "openscrub_base_" + BASE_COMMIT, root / "openscrub_base.py")
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
    finally:
        sys.path.remove(str(root))
        for k in [k for k in sys.modules
                  if k == "openscrub_internal" or k.startswith("openscrub_internal.")]:
            del sys.modules[k]
        sys.modules.update(saved)
    return module


def _render_frames(engine, tmp_path, coverage, tag):
    source = tmp_path / "unchanged.mp4"
    if not source.exists():
        _plain_video(source, 4, (96, 64))
    cap = cv2.VideoCapture(str(source))
    ok, first = cap.read()
    cap.release()
    assert ok
    letters = (((.25, .25), (.75, .25), (.75, .75), (.25, .75)),)
    rows = [engine.Detection(i / FPS, i / FPS + .03, (10, 10, 80, 50), "plate", "plate", .9,
                             dense=True, track=0, poly=letters if i % 2 else ())
            for i in range(4)]
    rows.append(engine._record_narrow_plate(
        engine.Detection(0, .03, (10, 10, 80, 50), "plate", "plate", .9, dense=True, track=1),
        0, engine._frame_sha256(first), letters, 0, ""))
    rows.append(engine.Detection(0, .4, (60, 30, 90, 60), "face", "face", .9))
    output = tmp_path / f"{tag}_{coverage}.mp4"
    parser = engine.build_parser()
    args = engine._prep_args(parser.parse_args(
        [str(source), "--mode", "box", "--pad", "0",
         "--plate-coverage", coverage, "-o", str(output)]), parser)
    engine.run_render(args, {"fps": FPS, "cum": [(0, 0)] * 4, "bands": [(0, 0)] * 4,
                             "detections": rows, "stats": {}})
    return _read_all(output)


def test_full_and_narrow_renders_unchanged_against_base_engine(tmp_path):
    base = _base_engine(tmp_path)
    for coverage in ("full", "narrow"):
        new = _render_frames(openscrub, tmp_path, coverage, "branch")
        old = _render_frames(base, tmp_path, coverage, "base")
        assert len(new) == len(old) == 4
        assert all(np.array_equal(a, b) for a, b in zip(new, old)), coverage


# --- batching ----------------------------------------------------------------

class _BatchSession:
    """Fake text model that accepts batches and records every call's input shape."""

    def __init__(self, rects, limit=None):
        self.rects, self.limit, self.calls = rects, limit, []

    def run(self, outputs, inputs):
        blob = next(iter(inputs.values()))
        n, _, h, w = blob.shape
        self.calls.append(tuple(blob.shape))
        if self.limit and n > self.limit:
            from onnxruntime.capi import onnxruntime_pybind11_state as ort_err
            raise ort_err.InvalidArgument("batch axis is fixed at 1")
        prob = np.zeros((n, 1, h, w), np.float32)
        rect = self.rects.get(max(h, w))
        if rect:
            x1, y1, x2, y2 = rect
            prob[:, 0, int(y1 * h):int(y2 * h), int(x1 * w):int(x2 * w)] = .9
        return [prob]


def _batch_detector(session):
    det = openscrub.TextRegionDetector.__new__(openscrub.TextRegionDetector)
    logs = []
    det.sess, det._in, det.log = session, "x", logs.append
    return det, logs


BOXES = [(50, 50, 350, 150), (40, 50, 340, 150), (20, 20, 120, 180)]


def test_find_letters_many_matches_single_calls_and_batches():
    rects = {320: WORD}
    det, _ = _batch_detector(_BatchSession(rects))
    many = det.find_letters_many(FRAME, BOXES)
    sessions_calls = det.sess.calls
    single_det, _ = _batch_detector(_BatchSession(rects))
    singles = [single_det.find_letters(FRAME, b) for b in BOXES]
    assert len(many) == len(BOXES)
    for got, want in zip(many, singles):
        assert len(got) == len(want) > 0
        for g, w in zip(got, want):
            np.testing.assert_allclose(g, w)
    # boxes 0 and 1 resize to one shape (one call of 2); box 2 is taller
    assert len(sessions_calls) == 2 and sorted(c[0] for c in sessions_calls) == [1, 2]
    assert len(single_det.sess.calls) == 3
    assert det.last_sizes_many == [(320,)] * 3


def test_find_letters_many_escalates_per_box_only():
    class Mixed(_BatchSession):
        def run(self, outputs, inputs):
            out = super().run(outputs, inputs)
            blob = next(iter(inputs.values()))
            n, _, h, w = blob.shape
            if max(h, w) == 320 and h > w:      # the tall crop gets a speck only
                out[0][:] = 0
                out[0][:, 0, int(.45 * h):int(.55 * h), int(.45 * w):int(.5 * w)] = .9
            return out
    det, _ = _batch_detector(Mixed({320: WORD, 640: WORD, 224: WORD}))
    wide = (20, 20, 120, 180)       # 100x160: tall, speck at 320
    many = det.find_letters_many(FRAME, [BOXES[0], wide])
    assert det.last_sizes_many[0] == (320,)
    assert det.last_sizes_many[1] == (640, 224)
    assert many[0] and many[1]
    # the first box never went on to 640/224
    assert [c[0] for c in det.sess.calls if max(c[2:]) != 320] == [1, 1]
    singles = _batch_detector(Mixed({320: WORD, 640: WORD, 224: WORD}))[0].find_letters(FRAME, wide)
    for g, w in zip(many[1], singles):
        np.testing.assert_allclose(g, w)


def test_find_letters_many_falls_back_when_batching_is_refused():
    rects = {320: WORD}
    det, logs = _batch_detector(_BatchSession(rects, limit=1))
    many = det.find_letters_many(FRAME, BOXES[:2])
    want = [_batch_detector(_BatchSession(rects))[0].find_letters(FRAME, b) for b in BOXES[:2]]
    for got, exp in zip(many, want):
        assert len(got) == len(exp) > 0
    assert logs.count("      text model: batching unavailable, using one crop per call") == 1
    before = len(det.sess.calls)
    det.find_letters_many(FRAME, BOXES[:2])
    assert all(c[0] == 1 for c in det.sess.calls[before:])     # no more batch attempts
    assert logs.count("      text model: batching unavailable, using one crop per call") == 1


def test_find_letters_many_without_model_or_boxes():
    det, _ = _batch_detector(None)
    assert det.find_letters_many(FRAME, BOXES) == [[], [], []]
    det, _ = _batch_detector(_BatchSession({320: WORD}))
    assert det.find_letters_many(FRAME, []) == []
    assert det.find_letters_many(FRAME, [(0, 0, 3, 3), BOXES[0]])[0] == []


def test_assisted_cover_gets_the_timeline_length(tmp_path, monkeypatch):
    source = tmp_path / "src.mp4"
    _plain_video(source, 1)
    parser = openscrub.build_parser()
    args = openscrub._prep_args(parser.parse_args(
        [str(source), "--plate-coverage", "assisted", "--no-box-fallback"]), parser)
    # the last row is grace-padded past the 5-frame timeline
    rows = [_plate_row(i, _rect_poly(LETTER_RECT) if i < 2 else ()) for i in range(5)]
    rows[4].t_end = 1.2
    report = tmp_path / "r.json"
    openscrub.write_report(report, args, {"fps": FPS, "cum": [(0, 0)] * 5,
                                          "bands": [(0, 0)] * 5, "detections": rows,
                                          "scene_cuts": [3]})
    plan = openscrub.assisted_cover_from_report(json.loads(report.read_text()))
    assert max(g.frame for g in plan.gaps) <= 4
    assert plan.stats["gap_frames"] == 2
    seen = []
    real = openscrub.plate_letters.plan_cover
    monkeypatch.setattr(openscrub.plate_letters, "plan_cover",
                        lambda *a, **k: (seen.append(k.get("frame_count")), real(*a, **k))[1])
    openscrub.apply_assisted_cover(rows, FPS, [3], frame_count=5)
    assert seen == [5]


def _render_saved_assisted(tmp_path, coverage, rewrite=None):
    """Write an assisted report whose rows all carry letter masks, then render
    it with an explicit `coverage` (run_render with the loaded source report,
    as the from-report path builds it)."""
    source = tmp_path / "saved.mp4"
    _plain_video(source, 3)
    parser = openscrub.build_parser()
    report = tmp_path / "saved.json"
    if rewrite is None:
        scan_args = openscrub._prep_args(parser.parse_args(
            [str(source), "--plate-coverage", "assisted", "--no-box-fallback"]), parser)
        rows = [_plate_row(i, _rect_poly(LETTER_RECT)) for i in range(3)]
        openscrub.write_report(report, scan_args, {"fps": FPS, "cum": [(0, 0)] * 3,
                                                   "bands": [(0, 0)] * 3, "detections": rows,
                                                   "scene_cuts": []})
    else:
        report = rewrite
    doc = json.loads(Path(report).read_text())
    dets, rstate, _ = openscrub._decode_report(doc)
    output = tmp_path / ("out_%s.mp4" % coverage)
    argv = [str(source), "--mode", "box", "--pad", "0", "-o", str(output),
            "--report", str(report)]
    if coverage != "saved":
        argv += ["--plate-coverage", coverage]
    args = openscrub._prep_args(parser.parse_args(argv), parser)
    if coverage == "saved":
        args.plate_coverage = doc["provenance"]["settings"].get("plate_coverage", "full")
    state = {"fps": rstate["fps"], "cum": [tuple(v) for v in rstate["cum"]],
             "bands": [tuple(v) for v in rstate["bands"]], "detections": dets,
             "source_report": doc, "stats": {}}
    if "scene_cuts" in doc:
        state["scene_cuts"] = list(doc["scene_cuts"])
    logs = []

    class CB(openscrub.Callbacks):
        def log(self, msg):
            logs.append(msg)

    openscrub.run_render(args, state, CB())
    return _read_all(output), report, logs, dets


@pytest.mark.parametrize("coverage", ["full", "narrow"])
def test_assisted_report_rendered_as_full_or_narrow_blacks_out_the_box(tmp_path, coverage):
    out, report, logs, dets = _render_saved_assisted(tmp_path, coverage)
    assert len(out) == 3
    inner = (PLATE[0] + 2, PLATE[1] + 2, PLATE[2] - 2, PLATE[3] - 2)
    for frame in out:
        assert black_share(frame, inner) > 0.99
    assert all(d.poly for d in dets)          # copies changed, report rows untouched
    assert any("letter masks" in m and "full plate box" in m for m in logs)
    if coverage == "full":
        # the rewritten report drops plate_coverage; a later default render
        # must still treat the saved letter masks as assisted-only
        out2, _, _, _ = _render_saved_assisted(tmp_path, "saved", rewrite=report)
        for frame in out2:
            assert black_share(frame, inner) > 0.99


def test_output_clip_resolves_like_the_render_loop():
    assert openscrub.resolve_output_clip("", 0, 0, lambda: 1 / 0) is None
    assert openscrub.resolve_output_clip("", 0.5, 0, lambda: 1 / 0) == (0.5, None)
    assert openscrub.resolve_output_clip("0.25-1.0", 0, 0, lambda: 8.0) == (2.0, None)
    assert openscrub.resolve_output_clip("0.25-0.5", 0, 0, lambda: 8.0) == (2.0, 4.0)
    assert openscrub.output_frame_range(None, 10.0, 30) == (0, 30)
    assert openscrub.output_frame_range((0.35, None), 10.0, 30) == (4, 30)
    assert openscrub.output_frame_range((0.5, 0.75), 10.0, 30) == (5, 8)
    assert openscrub.output_frame_range((0.5, 9.0), 10.0, 30) == (5, 30)
    for fps in (24.0, 29.97, 30.0, 59.94):
        for cs, ce in ((1.0, 2.0), (1 / 3, 7 / 3), (0.1, None)):
            first, end = openscrub.output_frame_range((cs, ce), fps, 1000)
            kept = [i for i in range(1000) if i / fps >= cs - 1e-6
                    and (ce is None or i / fps <= ce + 1e-6)]
            assert (first, end) == (kept[0], kept[-1] + 1)


def test_untracked_plate_rows_are_logged_once_per_render(tmp_path):
    rows = [_plate_row(0, _rect_poly(LETTER_RECT))]
    loose = openscrub.Detection(0, .1, PLATE, "plate", "plate", .9)            # not dense
    orphan = openscrub.Detection(0, .1, PLATE, "plate", "plate", .9, dense=True)  # track -1
    logs = []
    dets, _ = openscrub.apply_assisted_cover(rows + [loose, orphan], FPS, [], log=logs.append)
    assert loose in dets and orphan in dets
    assert logs == ["      assisted letters: 2 plate detections without a track get the full box"]
    logs.clear()
    openscrub.apply_assisted_cover(rows, FPS, [], log=logs.append)
    assert logs == []
    openscrub.apply_assisted_cover(rows + [loose], FPS, [])   # callers without a log still work
    # run_render threads its callbacks through
    source = tmp_path / "loose.mp4"
    _plain_video(source, 2)
    parser = openscrub.build_parser()
    args = openscrub._prep_args(parser.parse_args(
        [str(source), "--mode", "box", "--pad", "0", "--plate-coverage", "assisted",
         "--no-box-fallback", "-o", str(tmp_path / "loose_out.mp4")]), parser)

    class CB(openscrub.Callbacks):
        def log(self, msg):
            logs.append(msg)

    openscrub.run_render(args, {"fps": FPS, "cum": [(0, 0)] * 2, "bands": [(0, 0)] * 2,
                                "detections": rows + [loose], "stats": {}}, CB())
    assert logs.count("      assisted letters: 1 plate detection without a track gets the full box") == 1
