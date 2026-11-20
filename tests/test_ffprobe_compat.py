"""Real media probes must work with the FFmpeg 4.4 CUDA image's sections."""
import json
import shutil
import subprocess
from types import SimpleNamespace

import cv2
import pytest

import openscrub
from openscrub_internal import checkpoint_media, exact_samples


@pytest.fixture
def source(tmp_path):
    if not shutil.which('ffmpeg') or not shutil.which('ffprobe'):
        pytest.skip('ffmpeg and ffprobe required')
    path = tmp_path / 'source.mp4'
    subprocess.run([
        'ffmpeg', '-v', 'error', '-f', 'lavfi', '-i',
        'testsrc2=size=96x64:rate=6', '-frames:v', '6', '-c:v', 'libx264',
        '-threads', '1', '-pix_fmt', 'yuv420p', str(path)],
        capture_output=True, check=True, timeout=15)
    return path


@pytest.fixture(params=['installed', 'pre-5.1-sections'])
def probe_sections(request, monkeypatch):
    """Only emulate the old parser; the installed binary still reads the media.

    FFmpeg 4.4/5.0 have stream_side_data_list, but no stream_side_data alias.
    CI also exercises the actual Ubuntu 22.04 binary without this adapter.
    """
    if request.param == 'installed':
        return
    real_run = subprocess.run

    def run(command, *args, **kwargs):
        if command[0] == 'ffprobe' and '-show_entries' in command:
            entries = command[command.index('-show_entries') + 1]
            sections = {part.partition('=')[0] for part in entries.split(':')}
            if 'stream_side_data' in sections:
                result = subprocess.CompletedProcess(
                    command, 1, b'',
                    b"No match for section 'stream_side_data'\n"
                    b"Failed to set value for option 'show_entries': Invalid argument\n")
                if kwargs.get('check'):
                    result.check_returncode()
                return result
        return real_run(command, *args, **kwargs)

    monkeypatch.setattr(subprocess, 'run', run)


def qualify(kind, path):
    if kind == 'narrow':
        cap = cv2.VideoCapture(str(path))
        try:
            tolerance, reason = openscrub._narrow_source_policy(
                SimpleNamespace(video=str(path)), cap, 6, 6, 96, 64)
            return tolerance is not None, reason
        finally:
            cap.release()
    try:
        if kind == 'exact':
            facts = exact_samples.probe_source(str(path))
            assert (facts['width'], facts['height'], facts['rate'], facts['count']) == (96, 64, 6, 6)
        else:
            facts = checkpoint_media.inspect_source(path)
            assert (facts.width, facts.height, facts.fps, facts.total_frames) == (96, 64, 6, 6)
    except (exact_samples.ExactError, checkpoint_media.FrameEvidenceError) as error:
        return False, str(error)
    return True, ''


@pytest.mark.parametrize('kind', ['narrow', 'exact', 'checkpoint'])
def test_plain_cfr_source_qualifies_with_supported_probe_sections(source, probe_sections, kind):
    accepted, reason = qualify(kind, source)
    if kind == 'checkpoint':
        # FFmpeg 4.4's MOV demuxer can leave H.264 field order unknown.
        # A successful query must not waive the checkpoint's stricter gate.
        metadata = subprocess.run([
            'ffprobe', '-v', 'error', '-show_streams', '-of', 'json', str(source)],
            capture_output=True, check=True, timeout=15)
        field_order = json.loads(metadata.stdout)['streams'][0].get('field_order')
        if field_order in (None, 'unknown'):
            assert not accepted
            assert 'only progressive 8-bit H.264 yuv420p' in reason
            return
    assert accepted, reason
    assert not reason


@pytest.mark.parametrize('kind', ['narrow', 'exact', 'checkpoint'])
def test_rotation_side_data_still_rejects_source(source, probe_sections, kind):
    rotated = source.with_name('rotated.mp4')
    result = subprocess.run([
        'ffmpeg', '-v', 'error', '-display_rotation:v:0', '90',
        '-i', str(source), '-map', '0', '-c', 'copy', str(rotated)],
        capture_output=True, timeout=15)
    if result.returncode and b'Unrecognized option' in result.stderr:
        result = subprocess.run([
            'ffmpeg', '-v', 'error', '-i', str(source), '-map', '0', '-c', 'copy',
            '-metadata:s:v:0', 'rotate=90', str(rotated)],
            capture_output=True, timeout=15)
    result.check_returncode()
    # Verify the fixture independently; recent FFmpeg ignores the old tag.
    metadata = subprocess.run([
        'ffprobe', '-v', 'error', '-show_streams', '-of', 'json', str(rotated)],
        capture_output=True, check=True, timeout=15)
    stream = json.loads(metadata.stdout)['streams'][0]
    side_data = stream['side_data_list']
    assert any(abs(item.get('rotation', 0)) == 90 for item in side_data)
    accepted, reason = qualify(kind, rotated)
    assert not accepted
    if kind == 'checkpoint' and stream.get('field_order') in (None, 'unknown'):
        assert 'only progressive 8-bit H.264 yuv420p' in reason
        return
    assert ('display transform' in reason or 'rotated video' in reason), reason


@pytest.mark.parametrize('kind', ['narrow', 'exact', 'checkpoint'])
def test_multiple_video_streams_remain_unsupported(source, kind):
    multiple = source.with_name('multiple.mp4')
    subprocess.run([
        'ffmpeg', '-v', 'error', '-i', str(source),
        '-map', '0:v:0', '-map', '0:v:0', '-c', 'copy', str(multiple)],
        capture_output=True, check=True, timeout=15)
    accepted, reason = qualify(kind, multiple)
    assert not accepted
    assert ('one unambiguous video stream' in reason or 'exactly one video track' in reason), reason


@pytest.mark.parametrize('kind', ['narrow', 'exact', 'checkpoint'])
@pytest.mark.parametrize('stderr', [b'Permission denied\n\xff' + b'x' * 3000, b''])
def test_probe_failure_keeps_bounded_stderr_and_exit_code(source, monkeypatch, kind, stderr):
    real_run = subprocess.run

    def fail_probe(command, *args, **kwargs):
        if command[0] != 'ffprobe':
            return real_run(command, *args, **kwargs)
        result = subprocess.CompletedProcess(command, 1, b'', stderr)
        if kwargs.get('check'):
            result.check_returncode()
        return result

    monkeypatch.setattr(subprocess, 'run', fail_probe)
    accepted, reason = qualify(kind, source)
    assert not accepted
    assert 'ffprobe exited 1' in reason
    if stderr:
        assert 'Permission denied' in reason
        assert len(reason) < 2300
    else:
        assert len(reason) < 150
