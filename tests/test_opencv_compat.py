"""Capability and installation ownership are separate OpenCV health facts."""
import itertools
import json
import os
import subprocess
import sys

import pytest

from openscrub_internal.opencv_compat import assess_opencv, opencv_repair_hint, probe_opencv

FLAVORS = ("opencv-python", "opencv-contrib-python", "opencv-python-headless",
           "opencv-contrib-python-headless")


def snap(**changes):
    result = dict(status="ok", version="4.14.0", path="/chosen/cv2.so",
                  distributions={"opencv-python": "4.14.0.94"}, capability="ok", detail="")
    result.update(changes)
    return result


@pytest.mark.parametrize("distributions,state,usable", [
    ({"opencv-python": "4.14.0.94"}, "healthy", True),
    ({}, "unmanaged", True),
    *[({name: "4.14.0.94"}, "alternate", True) for name in FLAVORS[1:]],
    *[({name: "4.14.0.94" for name in names}, "conflict", True)
      for count in (2, 3, 4) for names in itertools.combinations(FLAVORS, count)],
])
def test_ownership_is_not_inferred_from_working_import(distributions, state, usable):
    assessment = assess_opencv(snap(distributions=distributions))
    assert assessment["state"] == state
    assert assessment["fallback_usable"] is usable
    assert assessment["healthy"] is (state == "healthy")


@pytest.mark.parametrize("changes,state", [
    ({"version": "5.0.0"}, "unsupported"),
    ({"distributions": {"opencv-python": "5.0.0.93"}}, "unsupported"),
    ({"distributions": {"opencv-python-headless": "5.0.0.93"}}, "unsupported"),
    ({"version": "unknown"}, "uncertain"),
    ({"distributions": {"opencv-python": "unknown"}}, "uncertain"),
    ({"version": "4.10.0"}, "uncertain"),
    ({"capability": "missing_api"}, "broken"),
    ({"capability": "missing_xml"}, "broken"),
    ({"capability": "classifier_error"}, "broken"),
    ({"capability": "empty_classifier"}, "broken"),
    ({"status": "missing_import", "distributions": {}, "version": None,
      "capability": "unavailable"}, "missing"),
    ({"status": "import_error", "capability": "unavailable"}, "broken"),
    *[({"status": status}, "uncertain") for status in
      ("timeout", "crash", "malformed_output", "metadata_error", "launch_error")],
])
def test_failures_never_become_fresh_install_assumptions(changes, state):
    assessment = assess_opencv(snap(**changes))
    assert assessment["state"] == state
    assert not assessment["healthy"]


def test_source_cuda_build_is_usable_without_wheel_ownership():
    result = assess_opencv(snap(version="4.10.0", distributions={}))
    assert result["state"] == "unmanaged"
    assert result["fallback_usable"]
    hint = opencv_repair_hint(snap(version="4.10.0", distributions={}, capability="missing_xml"), "/cuda/python")
    assert "source" in hint.lower()
    assert "--force-reinstall" not in hint


def test_repair_is_only_for_existing_sole_normal_known_install():
    hint = opencv_repair_hint(snap(version="5.0.0", distributions={"opencv-python": "5.0.0.93"}), "/path with space/python")
    assert '"opencv-python<5"' in hint
    assert "--force-reinstall" in hint
    assert "rerun" in hint.lower()
    for data in (snap(distributions={}), snap(distributions={FLAVORS[1]: "4.14.0.94"}),
                 snap(distributions={name: "4.14.0.94" for name in FLAVORS}), snap(status="timeout")):
        assert "--force-reinstall" not in opencv_repair_hint(data, sys.executable)


@pytest.mark.parametrize("response,want", [("garbage", "malformed_output"), ("{}", "malformed_output"),
    (json.dumps(snap(distributions=[])), "malformed_output"),
    (json.dumps(snap(capability="invented")), "malformed_output")])
def test_probe_rejects_malformed_child_output(monkeypatch, response, want):
    monkeypatch.setattr(subprocess, "run", lambda cmd, **kw: subprocess.CompletedProcess(cmd, 0, response, ""))
    assert probe_opencv("/target/python")["status"] == want


@pytest.mark.parametrize("failure,want", [(subprocess.TimeoutExpired("probe", 15), "timeout"),
                                          (OSError("cannot launch"), "launch_error")])
def test_probe_bounds_failed_children(monkeypatch, failure, want):
    def run(cmd, **kw):
        assert cmd[0] == "/actual/target/python"
        assert kw["timeout"] <= 20
        raise failure
    monkeypatch.setattr(subprocess, "run", run)
    assert probe_opencv("/actual/target/python")["status"] == want


def test_probe_reports_child_crash(monkeypatch):
    monkeypatch.setattr(subprocess, "run", lambda cmd, **kw: subprocess.CompletedProcess(cmd, -11, "", "crash"))
    assert probe_opencv(sys.executable)["status"] == "crash"


@pytest.mark.skipif(os.name == "nt", reason="POSIX executable wrapper; target argv also covered by subprocess tests")
def test_actual_selected_interpreter_is_self_contained(tmp_path):
    # -S excludes site-packages and OpenScrub; the probe must still run there.
    wrapper = tmp_path / "selected-python"
    wrapper.write_text('#!/bin/sh\nexec "' + sys.executable + '" -S "$@"\n')
    wrapper.chmod(0o755)
    result = probe_opencv(str(wrapper))
    assert result["status"] == "missing_import"
    assert result["distributions"] == {}
    assert assess_opencv(result)["state"] == "missing"


def test_real_compatible_runtime_has_required_fallback():
    result = probe_opencv(sys.executable)
    assert result["status"] == "ok", result
    assert result["path"]
    assert result["capability"] == "ok", result
    assert assess_opencv(result)["state"] == "healthy", result


@pytest.mark.parametrize("module,capability", [
    ("__version__='4.14.0'", "missing_api"),
    ("__version__='4.14.0'\nCascadeClassifier=lambda p: None", "missing_xml"),
    ("__version__='4.14.0'\nclass CascadeClassifier:\n def __init__(self,p): raise ValueError('broken')", "classifier_error"),
    ("__version__='4.14.0'\nclass CascadeClassifier:\n def __init__(self,p): pass\n def empty(self): return True", "empty_classifier"),
])
def test_real_child_checks_api_xml_and_construction(tmp_path, monkeypatch, module, capability):
    xml = tmp_path / "haarcascade_frontalface_default.xml"
    xml.write_text("broken controlled XML")
    if capability not in ("missing_api", "missing_xml"):
        module += "\nclass data:\n haarcascades=" + repr(str(tmp_path) + os.sep)
    (tmp_path / "cv2.py").write_text(module)
    monkeypatch.setenv("PYTHONPATH", str(tmp_path))
    result = probe_opencv(sys.executable)
    assert result["capability"] == capability, result


def test_unknown_distribution_version_never_gets_repair_permission():
    result = snap(status="import_error", distributions={"opencv-python": "unknown"}, capability="unavailable")
    assert assess_opencv(result)["state"] == "uncertain"
    assert "--force-reinstall" not in opencv_repair_hint(result, sys.executable)


def test_missing_runtime_version_is_distinct_from_malformed_output(tmp_path, monkeypatch):
    (tmp_path / "cv2.py").write_text("")
    monkeypatch.setenv("PYTHONPATH", str(tmp_path))
    result = probe_opencv(sys.executable)
    assert result["status"] == "ok"
    assert assess_opencv(result)["state"] == "uncertain"


@pytest.mark.parametrize("cached,optional_missing", [(False, False), (False, True), (True, False), (True, True)])
def test_production_face_detector_retains_haar_and_cached_yunet(tmp_path, monkeypatch, cached, optional_missing):
    import hashlib
    from pathlib import Path
    import numpy as np
    import openscrub
    model = Path(os.environ.get("OPENSCRUB_COMPAT_YUNET", openscrub._model_dir()))
    if model.is_dir():
        model = model / "face_detection_yunet_2023mar.onnx"
    if cached:
        if not model.is_file():
            pytest.skip("requires an existing verified YuNet fixture; never downloads")
        assert hashlib.sha256(model.read_bytes()).hexdigest() == "8f2383e4dd3cfbb4553ea8718107fc0423210dc964f9f4280604804ed2552fa4"
        cache = model.parent
    else:
        cache = tmp_path / "empty-models"
        cache.mkdir()
    fetches = []
    def block_fetch(*args, **kwargs):
        fetches.append(args)
        raise RuntimeError("test forbids model fetching")
    monkeypatch.setattr(openscrub, "_model_dir", lambda: str(cache))
    monkeypatch.setattr(openscrub, "_fetch_model", block_fetch)
    monkeypatch.delenv("OPENSCRUB_FACE_MODEL", raising=False)
    detector = openscrub.FaceDetector(model_path=str(tmp_path / "absent.onnx") if optional_missing else None)
    assert (detector.yunet is not None) is cached
    if not cached:
        assert not detector.haar.empty()
    frames = (np.zeros((240, 320, 3), np.uint8),
              np.random.default_rng(1234).integers(0, 256, (240, 320, 3), dtype=np.uint8))
    for frame in frames:
        for scale in (1.0, 0.4):
            assert detector.find(frame, detect_scale=scale) == []
    assert len(fetches) == (0 if cached else 1)
    if not cached:
        assert list(cache.iterdir()) == []
    else:
        assert hashlib.sha256(model.read_bytes()).hexdigest() == "8f2383e4dd3cfbb4553ea8718107fc0423210dc964f9f4280604804ed2552fa4"


def test_metadata_uncertainty_preserves_observed_fallback_capability():
    result = assess_opencv(snap(status="metadata_error", distributions={}))
    assert result["state"] == "uncertain"
    assert result["fallback_usable"]
    assert not result["healthy"]


@pytest.mark.parametrize("runtime,wheel", [("5.0.0", "4.14.0.94"), ("4.14.0", "5.0.0.93"),
                                          ("unknown", "5.0.0.93"), (None, "5.0.0.93")])
def test_normal_repair_requires_runtime_wheel_agreement(runtime, wheel):
    data = snap(version=runtime, distributions={"opencv-python": wheel})
    hint = opencv_repair_hint(data, "/selected/python")
    assert "--force-reinstall" not in hint
    assert "Reconcile cv2 ownership" in hint
    assert "/selected/python" in hint
    assert not assess_opencv(data)["healthy"]


@pytest.mark.parametrize("runtime,wheel,capability", [
    ("5.0.0", "5.0.0.93", "missing_api"),
    ("4.14.0", "4.14.0.94", "missing_api"),
    ("4.14.0", "4.14.0.94", "missing_xml"),
    ("4.14.0", "4.14.0.94", "classifier_error"),
    ("4.14.0", "4.14.0.94", "empty_classifier"),
])
def test_agreeing_sole_normal_wheel_keeps_deliberate_repair(runtime, wheel, capability):
    hint = opencv_repair_hint(snap(version=runtime, distributions={"opencv-python": wheel},
                                  capability=capability), "/selected/python")
    assert '/selected/python -m pip install --force-reinstall "opencv-python<5"' in hint
    assert "Rerun health checks" in hint
