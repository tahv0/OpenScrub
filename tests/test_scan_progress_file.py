"""The private progress file of a stopped scan: exact rows, one file, fail closed."""
import gzip
import os
from types import MappingProxyType

import pytest

import openscrub
from openscrub_internal import scan_progress as sp


def _plain():
    return openscrub.Detection(1.25, 1.55, (10, 12, 40, 30), "plate", "plate", 0.873,
                               (0.0, 0.0), dense=True)


def test_detection_round_trip_is_exact():
    plain = _plain()
    poly = openscrub.Detection(2.0, 2.1, (1, 2, 30, 40), "person", "person", 0.5,
                               (1.5, -2.25), dense=True, poly=(((.1, .2), (.3, .4), (.5, .6)),))
    poly.track, poly.person, poly.last_seen = 3, 1, 2.1
    narrow = openscrub._record_narrow_plate(_plain(), 12, "ab" * 32,
                                            (((0.0, 0.0), (1.0, 0.0), (1.0, 1.0)),), 0, "")
    evidence = _plain()
    evidence._plate_policy_evidence = MappingProxyType(
        {"origin": "detection", "frame": 7, "geometry_valid": True})
    for d in (plain, poly, narrow, evidence):
        out = sp.decode_detection(sp.encode_detection(d))
        assert type(out) is type(d)
        assert vars(out) == vars(d)
        assert type(out.cbox) is tuple and type(out.aoff) is tuple
        for a, b in zip(out.poly, d.poly):
            assert type(a) is tuple and all(type(p) is tuple for p in a)
    out = sp.decode_detection(sp.encode_detection(evidence))
    assert isinstance(out._plate_policy_evidence, MappingProxyType)


def test_unknown_detection_attribute_is_refused():
    d = _plain()
    d.surprise = 1
    with pytest.raises(sp.ProgressError):
        sp.encode_detection(d)


def test_save_replaces_and_leaves_one_file(tmp_path):
    path = str(tmp_path / sp.PROGRESS_NAME)
    sp.save(path, {"next_frame": 3})
    sp.save(path, {"next_frame": 9})
    assert os.listdir(tmp_path) == [sp.PROGRESS_NAME]
    assert sp.load(path)["next_frame"] == 9


def test_leftover_stage_is_removed_and_old_file_kept(tmp_path):
    path = str(tmp_path / sp.PROGRESS_NAME)
    sp.save(path, {"next_frame": 4})
    with open(path + ".stage", "wb") as handle:
        handle.write(b"half written")
    assert sp.load(path)["next_frame"] == 4
    sp.save(path, {"next_frame": 5})
    assert sorted(os.listdir(tmp_path)) == [sp.PROGRESS_NAME]


def test_corrupt_or_other_version_is_refused(tmp_path):
    path = str(tmp_path / sp.PROGRESS_NAME)
    sp.save(path, {"next_frame": 4})
    with open(path, "rb") as handle:
        data = handle.read()
    with open(path, "wb") as handle:
        handle.write(data[: len(data) // 2])
    with pytest.raises(sp.ProgressError):
        sp.load(path)
    with gzip.open(path, "wt", encoding="utf-8") as handle:
        handle.write('{"version": 99, "state": {}}')
    with pytest.raises(sp.ProgressError):
        sp.load(path)


def _args(*extra):
    parser = openscrub.build_parser()
    return openscrub._prep_args(parser.parse_args(
        ["clip.mp4", "--categories", "plate", "--tile", "off", *extra]), parser)


def test_identity_names_what_changed():
    a = {"settings": sp.settings_identity(_args()), "input_sha256": "a" * 64}
    b = {"settings": sp.settings_identity(_args("--plate-threshold", "0.5")),
         "input_sha256": "a" * 64}
    with pytest.raises(sp.ProgressMismatch) as err:
        sp.compare_identity(a, b)
    assert "plate_threshold" in err.value.what
    c = dict(a, input_sha256="b" * 64)
    with pytest.raises(sp.ProgressMismatch) as err:
        sp.compare_identity(a, c)
    assert err.value.what == "the video file changed"
    sp.compare_identity(a, dict(a))


def test_render_only_settings_are_not_identity():
    assert (sp.settings_identity(_args("--mode", "blur"))
            == sp.settings_identity(_args("--mode", "inpaint")))


def test_autosave_interval_scales_with_scan_size():
    now = [0.0]
    control = sp.ScanProgressControl("unused", stop_requested=lambda: False, resume=False,
                                     clock=lambda: now[0])
    assert control.autosave_interval() == 60          # nothing saved yet: every minute
    control.mark_saved(10, 100, cost=0.05)            # a light scan: still every minute
    assert control.autosave_interval() == 60
    control.mark_saved(10, 100, cost=2.0)             # a big scan: 2 s saves -> 200 s
    assert control.autosave_interval() == 200
    control.mark_saved(10, 100, cost=9.0)             # never longer than 5 minutes
    assert control.autosave_interval() == 300
    now[0] += 299
    assert not control.autosave_due()
    now[0] += 1
    assert control.autosave_due()
    fixed = sp.ScanProgressControl("unused", stop_requested=lambda: False, resume=False,
                                   autosave_seconds=None)
    assert not fixed.autosave_due()
