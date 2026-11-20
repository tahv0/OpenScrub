"""Portable destinations for optional media-test evidence."""
import pytest

from artifact_support import artifact_directory


@pytest.mark.parametrize("setting", [None, ""])
def test_unconfigured_output_is_writable_temporary_directory(tmp_path, monkeypatch, setting):
    if setting is None:
        monkeypatch.delenv("VERIFY_RUN", raising=False)
    else:
        monkeypatch.setenv("VERIFY_RUN", setting)
    directory = artifact_directory(tmp_path)
    assert directory == tmp_path / "artifacts"
    (directory / "evidence.json").write_text("{}")
    assert artifact_directory(tmp_path) == directory
    assert (directory / "evidence.json").read_text() == "{}"


def test_configured_output_preserves_logs_and_existing_evidence(tmp_path, monkeypatch):
    configured = tmp_path / "explicit" / "nested"
    monkeypatch.setenv("VERIFY_RUN", str(configured))
    directory = artifact_directory(tmp_path / "unused")
    assert directory == configured / "logs"
    (directory / "evidence.json").write_text("retained")
    assert artifact_directory(tmp_path / "another") == directory
    assert (directory / "evidence.json").read_text() == "retained"
    assert not (tmp_path / "unused").exists()


def test_unconfigured_tests_have_independent_directories(tmp_path, monkeypatch):
    monkeypatch.delenv("VERIFY_RUN", raising=False)
    first = artifact_directory(tmp_path / "first")
    second = artifact_directory(tmp_path / "second")
    (first / "evidence.json").write_text("first")
    (second / "evidence.json").write_text("second")
    assert first != second
    assert (first / "evidence.json").read_text() == "first"
    assert (second / "evidence.json").read_text() == "second"


@pytest.mark.parametrize("configured", [False, True])
def test_filesystem_errors_propagate(tmp_path, monkeypatch, configured):
    obstruction = tmp_path / "file"
    obstruction.write_text("keep")
    if configured:
        monkeypatch.setenv("VERIFY_RUN", str(obstruction))
    else:
        monkeypatch.delenv("VERIFY_RUN", raising=False)
    with pytest.raises(OSError):
        artifact_directory(obstruction)
    assert obstruction.read_text() == "keep"
