"""Owning staged-render/publication schedules; footage and faults are synthetic."""
import hashlib
import json
import os
from pathlib import Path

import pytest
import openscrub as app
from test_report_roundtrip import review, render_args, Quiet, assert_review_preserved
from test_render_resources import source, owners, assert_closed, render as direct_render


@pytest.mark.parametrize('present', [False, True])
@pytest.mark.parametrize('failure', ['callback', 'cancel', 'final'])
def test_render_failure_or_cancel_preserves_previous_or_absent_final(source, tmp_path, monkeypatch, present, failure):
    output = tmp_path / 'output.mp4'
    if present:
        output.write_bytes(b'previous video')
    class Stop(Quiet):
        def progress(self, *args, **kwargs):
            if failure == 'callback':
                raise RuntimeError('compute sentinel')
        def cancelled(self):
            return failure == 'cancel'
        def log(self, message):
            if failure == 'final' and message.startswith('rendered'):
                raise RuntimeError('final sentinel')
    with owners(monkeypatch) as observed:
        with pytest.raises((RuntimeError, app.PipelineCancelled)) as caught:
            direct_render('sdr', source, output, Stop())
        assert caught.value.__traceback__ is not None
        assert_closed(observed)
        assert output.exists() is present
        if present:
            assert output.read_bytes() == b'previous video'
        assert not list(tmp_path.glob('.render-*.tmp*'))


def test_final_untouched_until_computation_and_report_ready(review, monkeypatch):
    review.output.write_bytes(b'previous video')
    old_report = review.path.read_bytes()
    real_hash = app.sha256_file
    seen = []
    def hashed(path):
        if '.render-' in str(path):
            assert review.output.read_bytes() == b'previous video'
            assert review.path.read_bytes() == old_report
            seen.append(str(path))
        return real_hash(path)
    monkeypatch.setattr(app, 'sha256_file', hashed)
    result = app.run_pipeline(render_args(review), Quiet())
    assert seen and result['output'] == str(review.output)
    assert not list(review.path.parent.glob('.render-*.tmp*'))
    saved = json.loads(review.path.read_text())
    assert_review_preserved(review.doc, saved)
    assert saved['provenance']['output'] == str(review.output)
    assert saved['provenance']['output_sha256'] == real_hash(review.output)


def test_report_hash_reads_stage_but_names_final(review, monkeypatch):
    sentinel = RuntimeError('hash sentinel')
    review.output.write_bytes(b'previous video')
    old_report = review.path.read_bytes()
    real = app.sha256_file
    def fail_output(path):
        if str(path) != str(review.video):
            raise sentinel
        return real(path)
    monkeypatch.setattr(app, 'sha256_file', fail_output)
    with pytest.raises(RuntimeError) as caught:
        app.run_pipeline(render_args(review), Quiet())
    assert caught.value is sentinel
    assert review.output.read_bytes() == b'previous video'
    assert review.path.read_bytes() == old_report


@pytest.mark.parametrize('writes,raises', [(True, True), (False, False)])
def test_legacy_report_publisher_write_raise_and_no_write(review, writes, raises):
    review.output.write_bytes(b'previous video')
    old_report = review.path.read_bytes()
    sentinel = RuntimeError('legacy sentinel')
    calls = []
    class Legacy(Quiet):
        def publish_report(self, path, doc):
            calls.append((path, doc))
            assert review.output.read_bytes() != b'previous video'
            if writes:
                Path(path).write_text(json.dumps(doc))
            if raises:
                raise sentinel
    if raises:
        with pytest.raises(RuntimeError) as caught:
            app.run_pipeline(render_args(review), Legacy())
        assert caught.value is sentinel
        assert review.output.read_bytes() == b'previous video'
    else:
        assert app.run_pipeline(render_args(review), Legacy())['output'] == str(review.output)
    assert len(calls) == 1 and calls[0][0] == str(review.path)
    assert_review_preserved(review.doc, calls[0][1])
    assert review.path.read_bytes() == old_report


def test_same_source_video_fallback_preserves_original_until_commit(source, monkeypatch):
    original = source.read_bytes()
    real_which = app.shutil.which
    monkeypatch.setattr(app.shutil, 'which', lambda name: None if name == 'ffmpeg' else real_which(name))
    class Check(Quiet):
        def progress(self, *args, **kwargs):
            assert source.read_bytes() == original
    direct_render('sdr', source, source, Check())
    assert source.read_bytes() != original
