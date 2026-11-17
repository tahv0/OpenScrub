"""Installer checks must not certify an importable unsupported cv2."""
import json
import subprocess

import pytest

import install


def snapshot(version="5.0.0", distributions=None, capability="missing_api", status="ok"):
    return dict(status=status, version=version, path="/target/cv2/__init__.py",
                distributions=distributions if distributions is not None else {"opencv-python": "5.0.0.93"},
                capability=capability, detail="")


def test_importable_opencv5_is_not_core_ready(monkeypatch, capsys):
    def child(cmd, **kwargs):
        if len(cmd) > 2 and cmd[1] == "-c" and "OPENSCRUB_OPENCV_PROBE" in cmd[2]:
            return subprocess.CompletedProcess(cmd, 0, json.dumps(snapshot()), "")
        return subprocess.CompletedProcess(cmd, 0, "", "")
    monkeypatch.setattr(subprocess, "run", child)
    monkeypatch.setattr(install, "PYTHON", "/selected/python")
    monkeypatch.setattr(install, "RESULTS", [])
    install.step_core(check=True, yes=False)
    assert any(not ok and "OpenCV" in name for name, ok, _ in install.RESULTS)
    output = capsys.readouterr().out
    assert "opencv-python<5" in output
    assert "/selected/python" in output


def wire(monkeypatch, snapshots):
    commands = []
    queue = iter(snapshots)
    def child(cmd, **kwargs):
        commands.append(cmd)
        if cmd[1] == "-c" and "OPENSCRUB_OPENCV_PROBE" in cmd[2]:
            return subprocess.CompletedProcess(cmd, 0, json.dumps(next(queue)), "")
        return subprocess.CompletedProcess(cmd, 0, "", "")
    monkeypatch.setattr(subprocess, "run", child)
    monkeypatch.setattr(install, "PYTHON", "/selected/python")
    monkeypatch.setattr(install, "RESULTS", [])
    return commands


def test_fresh_install_uses_target_and_reprobes(monkeypatch):
    missing = snapshot(version=None, distributions={}, capability="unavailable", status="missing_import")
    ready = snapshot(version="4.14.0", distributions={"opencv-python": "4.14.0.94"}, capability="ok")
    commands = wire(monkeypatch, [missing, ready])
    install.step_core(check=False, yes=True)
    assert [cmd for cmd in commands if "pip" in cmd] == [
        ["/selected/python", "-m", "pip", "install", "opencv-python<5"]]
    assert all(cmd[0] == "/selected/python" for cmd in commands)
    assert install.RESULTS[0][1]
    assert sum("OPENSCRUB_OPENCV_PROBE" in cmd[-1] for cmd in commands) == 2


def test_successful_pip_does_not_certify_failed_reprobe(monkeypatch):
    missing = snapshot(version=None, distributions={}, capability="unavailable", status="missing_import")
    wire(monkeypatch, [missing, missing])
    install.step_core(check=False, yes=True)
    assert not install.RESULTS[0][1]


@pytest.mark.parametrize("check,yes,accepted", [(True, False, True), (False, False, False)])
def test_missing_check_or_decline_never_runs_pip(monkeypatch, check, yes, accepted):
    missing = snapshot(version=None, distributions={}, capability="unavailable", status="missing_import")
    commands = wire(monkeypatch, [missing])
    monkeypatch.setattr(install, "ask", lambda *args: accepted)
    install.step_core(check=check, yes=yes)
    assert not any("pip" in cmd for cmd in commands)
    assert not install.RESULTS[0][1]


@pytest.mark.parametrize("data", [snapshot(),
    snapshot(distributions={"opencv-contrib-python": "4.14.0.94"}, version="4.14.0", capability="ok"),
    snapshot(distributions={}, version="4.10.0", capability="ok"),
    snapshot(distributions={"opencv-python": "4.14.0.94", "opencv-contrib-python": "4.14.0.94"}, version="4.14.0", capability="ok"),
    snapshot(status="timeout")])
@pytest.mark.parametrize("check,yes", [(True, False), (False, False), (False, True)])
def test_existing_or_uncertain_install_never_mutates(monkeypatch, data, check, yes):
    commands = wire(monkeypatch, [data])
    install.step_core(check=check, yes=yes)
    assert not any("pip" in cmd for cmd in commands)
    assert not install.RESULTS[0][1]


def test_other_missing_core_packages_keep_existing_prompt(monkeypatch):
    ready = snapshot(version="4.14.0", distributions={"opencv-python": "4.14.0.94"}, capability="ok")
    commands = wire(monkeypatch, [ready])
    monkeypatch.setattr(install, "have", lambda mod: mod != "flask")
    install.step_core(check=False, yes=True)
    assert [cmd for cmd in commands if "pip" in cmd] == [
        ["/selected/python", "-m", "pip", "install", "flask"]]


def test_setup_rejects_opencv5_and_keeps_flask_separate(monkeypatch, capsys):
    import openscrub_setup as setup
    commands = wire(monkeypatch, [snapshot()])
    monkeypatch.setattr(setup, "find_tesseract", lambda: "/tesseract")
    monkeypatch.setattr(setup, "find_ffmpeg", lambda: "/ffmpeg")
    monkeypatch.setitem(__import__('sys').modules, "spacy", None)
    assert setup.main(["--check"]) == 0  # retain historical exit policy
    output = capsys.readouterr().out
    assert "unsupported" in output and "opencv-python<5" in output
    assert "Flask Python dependency" in output
    assert not any("pip" in cmd for cmd in commands)


def test_final_assessment_does_not_hide_post_paddle_conflict(monkeypatch, capsys):
    import sys
    ready = snapshot(version="4.14.0", distributions={"opencv-python": "4.14.0.94"}, capability="ok")
    conflict = snapshot(version="4.14.0", distributions={"opencv-python": "4.14.0.94", "opencv-contrib-python": "4.10.0.84"}, capability="ok")
    commands = wire(monkeypatch, [ready, conflict])
    monkeypatch.setattr(sys, "argv", ["install.py", "--yes", "--no-shortcut"])
    for name in ("step_spacy", "step_system_tools", "step_paddle", "step_directml", "step_nvenc"):
        monkeypatch.setattr(install, name, lambda *args: None)
    install.main()
    output = capsys.readouterr().out
    assert "(final)" in output and "conflict" in output
    assert "Install complete." not in output
    assert "Everything else works" not in output
    assert not any("pip" in cmd for cmd in commands)


def test_setup_usable_source_build_is_not_reported_missing(monkeypatch, capsys):
    import re
    import sys
    import openscrub_setup as setup
    wire(monkeypatch, [snapshot(version="4.10.0", distributions={}, capability="ok")])
    monkeypatch.setattr(setup, "find_tesseract", lambda: "/tesseract")
    monkeypatch.setattr(setup, "find_ffmpeg", lambda: "/ffmpeg")
    monkeypatch.setitem(sys.modules, "spacy", None)
    setup.main(["--check"])
    output = re.sub(r"\x1b\[[0-9;]*m", "", capsys.readouterr().out)
    line = next(line for line in output.splitlines() if "OpenCV face fallback:" in line)
    assert "[note]" in line and "unmanaged" in line
    assert "--force-reinstall" not in output
