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
        def progress(self, stage, done, total):
            if failure == 'final' and done == total:
                raise RuntimeError('final sentinel')
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
    monkeypatch.setattr(app, 'nvenc_available', lambda *args: None)
    class Check(Quiet):
        def progress(self, *args, **kwargs):
            assert source.read_bytes() == original
    direct_render('sdr', source, source, Check())
    assert source.read_bytes() != original


@pytest.mark.parametrize('video_present,report_present', [(False,False),(True,False),(False,True),(True,True)])
@pytest.mark.parametrize('failed_role', ['video','report'])
def test_pair_publication_restores_each_previous_presence_case(tmp_path, monkeypatch, video_present, report_present, failed_role):
    from openscrub_internal import render_delivery as delivery
    video, report = tmp_path/'output.mp4', tmp_path/'report.json'
    if video_present: video.write_bytes(b'old video')
    if report_present: report.write_bytes(b'old report')
    sentinel = OSError('replace sentinel')
    real = os.replace
    def replace(src, dst):
        if Path(src).name.startswith('.render-') and '.tmp' in Path(src).name and failed_role == 'video':
            raise sentinel
        if Path(src).name.startswith('.report-') and failed_role == 'report':
            raise sentinel
        return real(src, dst)
    with delivery._RenderDelivery(str(video), str(report)) as owned:
        Path(owned.video_stage).write_bytes(b'new video')
        owned.prepare_report({'new': True})
        owned.prepare_rollback()
        monkeypatch.setattr(delivery.os, 'replace', replace)
        with pytest.raises(OSError) as caught: owned.commit()
        assert caught.value is sentinel
    assert video.exists() is video_present and report.exists() is report_present
    if video_present: assert video.read_bytes() == b'old video'
    if report_present: assert report.read_bytes() == b'old report'
    assert not list(tmp_path.glob('.render-*'))


def test_precommit_identity_change_rejects_stale_backup(tmp_path):
    from openscrub_internal.render_delivery import _RenderDelivery
    video = tmp_path/'output.mp4'; video.write_bytes(b'old')
    with _RenderDelivery(str(video)) as owned:
        Path(owned.video_stage).write_bytes(b'new')
        owned.prepare_rollback()
        video.write_bytes(b'changed externally')
        with pytest.raises(RuntimeError, match='changed before'): owned.commit()
    assert video.read_bytes() == b'changed externally'


@pytest.mark.parametrize('fault', ['rollback','descriptor'])
def test_rollback_or_descriptor_unlink_failure_exposes_recovery(tmp_path, monkeypatch, fault):
    from openscrub_internal import render_delivery as delivery
    video, report = tmp_path/'output.mp4', tmp_path/'report.json'
    video.write_bytes(b'old video'); report.write_bytes(b'old report')
    real_replace, real_unlink = os.replace, os.unlink
    primary = OSError('primary')
    def replace(src, dst):
        if Path(src).name.startswith('.report-'):
            raise primary
        if fault == 'rollback' and str(src).endswith('.video'):
            raise OSError('restore sentinel')
        return real_replace(src, dst)
    def unlink(path, *args, **kwargs):
        if fault == 'descriptor' and str(path).endswith('.json') and '.render-recovery-' in str(path):
            raise primary
        return real_unlink(path, *args, **kwargs)
    with delivery._RenderDelivery(str(video), str(report)) as owned:
        Path(owned.video_stage).write_bytes(b'new video')
        owned.prepare_report({'new': True}); owned.prepare_rollback()
        monkeypatch.setattr(delivery.os, 'replace', replace if fault == 'rollback' else real_replace)
        monkeypatch.setattr(delivery.os, 'unlink', unlink)
        with pytest.raises(delivery._DeliveryRecoveryError) as caught: owned.commit()
        assert caught.value.primary is primary and owned.recovery_required
    assert len(list(tmp_path.glob('.render-recovery-*.json'))) == 1
    if fault == 'rollback':
        assert len(list(tmp_path.glob('.render-recovery-*.video'))) == 1
    else:
        assert video.read_bytes() == b'old video' and report.read_bytes() == b'old report'


def test_pair_and_done_commit_before_cancel_ack(store, monkeypatch):
    import openscrub_web as web
    from test_job_lifecycle import request
    monkeypatch.setattr(app, 'normalize_vfr', lambda *args: None)
    def body(src, dst, *args, **kwargs): Path(dst).write_bytes(b'new video')
    monkeypatch.setattr(app, '_render_into', body)
    real_unlink = os.unlink
    seen = []
    def unlink(path, *args, **kwargs):
        if '.render-recovery-' in str(path) and str(path).endswith('.json'):
            assert store.job['phase'] == 'done'
            assert Path(store.job['output']).read_bytes() == b'new video'
            seen.append(True)
            store.job['cancel'].set() # signal before acknowledgement may follow committed success
        return real_unlink(path, *args, **kwargs)
    monkeypatch.setattr(os, 'unlink', unlink)
    web._run_job(store.job, 'render')
    assert seen and store.job['phase'] == 'done'
    assert web.FILES.initialize(store.job).output_epoch == 2
    assert request('post', store.url+'/cancel').status_code == 200
    assert store.job['phase'] == 'done'


def test_recovery_marker_rehydrates_without_report_and_refuses_unsafe_routes(store):
    import openscrub_web as web
    from test_job_lifecycle import request
    marker=Path(store.job['dir'])/('.render-recovery-'+'a'*32+'.json')
    marker.write_text('malformed deliberately')
    store.path.unlink()
    web.JOBS.clear(); web._rehydrate_jobs()
    job=next(iter(web.JOBS.values()))
    assert web.job_public(job)['recovery_required'] is True
    assert job['phase'] == 'error'
    for method, suffix in [('get','download'),('get','report'),('get','frame_at?src=output'),('post','render'),('post','retry'),('post','detections'),('post','track_object')]:
        response=request(method, store.url+'/'+suffix, json={} if method=='post' else None)
        assert response.status_code == 409, (suffix,response.data)
        assert b'render delivery requires recovery' in response.data
    assert request('get',store.url).status_code == 200


from test_job_lifecycle import store
