"""First-OCR sanity must work independently of optional backtracking.

Only OCR inference is controlled: lossless decoding, Canny, primary email
matching, scan finalization, and report serialization use production code.
"""
from dataclasses import asdict
from datetime import datetime
import hashlib
import json

import cv2
import numpy as np
import pytest

import openscrub as core


SANITY_WARNING = (
    "      *** OCR SANITY WARNING: the first scan read almost no text, but "
    "the frame looks text-dense. If this recording contains text to redact, "
    "check the OCR setup (run openscrub-setup, or install PaddleOCR) before "
    "trusting this run.")
EMAIL = ("alice@example.invalid", (8, 8, 78, 28), .99)
FILLERS = [("status", (8, 40, 68, 60), .98),
           ("active", (88, 40, 150, 60), .97)]


def scan_and_report(tmp_path, monkeypatch, *, counts, busy=True,
                    no_backtrack=True):
    video = tmp_path / "fixed.avi"
    frame = (np.random.default_rng(115).integers(
        0, 256, (96, 160, 3), dtype=np.uint8) if busy else
        np.full((96, 160, 3), 245, np.uint8))
    writer = cv2.VideoWriter(str(video), cv2.VideoWriter_fourcc(*"FFV1"),
                             6., (160, 96))
    assert writer.isOpened(), "lossless FFV1 fixture codec required"
    try:
        for _ in range(12):
            writer.write(frame)
    finally:
        writer.release()
    cap = cv2.VideoCapture(str(video))
    try:
        ok, decoded = cap.read()
        assert ok
        assert np.array_equal(decoded, frame)
    finally:
        cap.release()
    # Independently measure the fixture at the existing sanity resolution.
    gray = cv2.cvtColor(decoded, cv2.COLOR_BGR2GRAY)
    half = cv2.resize(gray, (80, 48))
    density = np.count_nonzero(cv2.Canny(half, 60, 180)) / half.size
    assert density > .02 if busy else density == 0.

    class ControlledOCR:
        def __init__(self):
            self.counts = iter(counts)

        def read(self, image):
            assert np.array_equal(image, frame)
            count = next(self.counts)
            return ([EMAIL] + FILLERS)[:count]

    monkeypatch.setattr(core, "make_ocr", lambda *a, **k: ControlledOCR())
    parser = core.build_parser()
    options = [str(video), "--categories", "email", "--engine", "tesseract",
               "--sample-interval", "0.3333333333333333", "--scroll-track", "off",
               "--adaptive", "off", "--ocr-upscale", "off", "--no-vfr-fix"]
    if no_backtrack:
        options.append("--no-backtrack")
    args = core._prep_args(parser.parse_args(options), parser)
    messages = []

    class Quiet(core.Callbacks):
        def log(self, message):
            messages.append(message)

    state = core.run_scan(args, Quiet())
    assert args.no_backtrack is no_backtrack
    if no_backtrack:
        assert not any("backtrack:" in m for m in messages)
    path = tmp_path / "report.json"
    core.write_report(str(path), args, state)
    document = json.loads(path.read_text())
    return state, document, messages, hashlib.sha256(video.read_bytes()).hexdigest()


def assert_scan_report(state, document, digest, tmp_path, *, has_email,
                       no_backtrack=True):
    # Six primary hits plus six reverse confirmations merge into one region.
    expected = ([{
        "t_start": 0., "t_end": 2.3, "cbox": (8, 8, 78, 28),
        "category": "email", "text": "alice@example.invalid", "confidence": .99,
        "aoff": (0., 0.), "last_seen": 5/3, "dense": False,
        "track": -1, "person": -1, "poly": (),
    }] if has_email else [])
    assert dict(state, detections=[asdict(d) for d in state["detections"]]) == {
        "fps": 6., "cum": [(0., 0.)] * 12, "bands": [(0., 0.)] * 12,
        "detections": expected, "zdropped": [], "audio_suggestions": [],
        "audio_transcript": [], "input_sha256": digest,
        "stats": {"scans": 6, "raw_hits": 12 if has_email else 0,
                  "regions": int(has_email), "recalls": 0,
                  "remembered": int(has_email), "zone_dropped": {}},
    }
    # All Detection fields and report-only choices are pinned, including order.
    assert document["detections"] == ([{
        "t_start": 0., "t_end": 2.3, "cbox": [8, 8, 78, 28],
        "category": "email", "text": "alice@example.invalid", "confidence": .99,
        "aoff": [0., 0.], "last_seen": 5/3, "dense": False,
        "track": -1, "person": -1, "poly": [], "enabled": True,
    }] if has_email else [])
    assert document["render_state"] == {
        "fps": 6., "cum": [[0., 0.]] * 12, "bands": [[0., 0.]] * 12}
    assert list(document) == ["provenance", "render_state", "detections"]
    provenance = document["provenance"]
    assert datetime.fromisoformat(provenance["timestamp"]).tzinfo is not None
    assert provenance == {
        "tool": "openscrub", "version": core.VERSION,
        "timestamp": provenance["timestamp"], "input": str(tmp_path / "fixed.avi"),
        "input_sha256": digest, "original_input": None,
        "vfr_normalized": False, "hdr_tonemapped": False, "hdr_output": False,
        "metadata_stripped": True, "zones": None, "windows": None,
        "settings": {
            "allow_names": None, "extra_names": None, "engine": "tesseract",
            "device": "auto", "encoder": "auto", "no_ner": False,
            "heuristic_names": "auto", "sample_interval": 1/3,
            "scan_trigger": 60, "pad": 8, "no_vfr_fix": True,
            "out_quality": "archival", "codec": "h264", "hdr_output": "match",
            "tile": "auto", "face_heads": False, "dense_faces": False,
            "dense_face_stride": 1, "scan_speed": "thorough", "plate_model": None,
            "face_shape": "ellipse", "face_model": None, "plate_threshold": .35,
            "person_model": None, "person_threshold": .5, "face_threshold": .6,
            "draw_scores": False, "detect_scale": 1., "face_expand": .15,
            "coverage": "tight", "mode": "blur", "mrn_regex": "",
            "scroll_track": "off", "adaptive": "off", "phrase": [],
            "phrases": None, "custom_regex": [], "bridge_gap": 4.,
            "no_memory": False, "preview": False, "detect_windows": "",
            "detect_windows_frac": "", "clip_frac": "", "mute_audio_tracks": "",
            "audio_lane_count": None, "clip_start": 0., "clip_end": 0.,
            "audio_pii": False, "audio_pii_model": "base", "audio_pii_apply": False,
            "audio_redact": "", "audio_redact_mode": "mute", "overwrite": False,
            "backtrack_window": 2.5, "no_backtrack": no_backtrack,
            "skip_start": 0., "skip_end": 0., "zones": None, "windows": None,
            "ignore_region": [], "ocr_upscale": "off", "paranoid": False,
            "vfr": "auto", "categories": "email", "ignore_regions": [],
            "zones_data": None, "windows_data": None,
        },
    }


@pytest.mark.parametrize("count", [0, 1, 2])
def test_first_low_word_scan_without_backtrack_warns_and_returns_report(
        tmp_path, monkeypatch, count):
    state, document, messages, digest = scan_and_report(
        tmp_path, monkeypatch, counts=[count] * 6)
    assert_scan_report(state, document, digest, tmp_path, has_email=count > 0)
    assert [m for m in messages if "OCR SANITY WARNING" in m] == [SANITY_WARNING]


def test_edge_free_low_word_scan_without_backtrack_returns_report_silently(
        tmp_path, monkeypatch):
    state, document, messages, digest = scan_and_report(
        tmp_path, monkeypatch, counts=[1] * 6, busy=False)
    assert_scan_report(state, document, digest, tmp_path, has_email=True)
    assert not any("OCR SANITY WARNING" in m for m in messages)


def test_default_backtracking_keeps_first_low_word_warning(tmp_path, monkeypatch):
    state, document, messages, digest = scan_and_report(
        tmp_path, monkeypatch, counts=[0] * 6, no_backtrack=False)
    assert_scan_report(state, document, digest, tmp_path, has_email=False,
                       no_backtrack=False)
    assert [m for m in messages if "OCR SANITY WARNING" in m] == [SANITY_WARNING]


@pytest.mark.parametrize("counts", [[3] * 6, [3, 1, 1, 1, 1, 1]])
def test_three_word_first_scan_does_not_warn_on_later_sparse_scans(
        tmp_path, monkeypatch, counts):
    state, document, messages, digest = scan_and_report(
        tmp_path, monkeypatch, counts=counts)
    assert_scan_report(state, document, digest, tmp_path, has_email=True)
    assert not any("OCR SANITY WARNING" in m for m in messages)
