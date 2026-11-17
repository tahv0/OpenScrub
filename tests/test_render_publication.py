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
    store.doc['render_state']['bands'] = [[0,0]] * 30
    store.path.write_text(json.dumps(store.doc))
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


@pytest.mark.parametrize('kind',['parent-symlink','hardlink','final-symlink'])
def test_destination_entry_alias_semantics(tmp_path,kind):
    from openscrub_internal.render_delivery import _RenderDelivery
    directory=tmp_path/'real';directory.mkdir();video=directory/'output.mp4';report=directory/'report.json'
    video.write_bytes(b'old video')
    if kind=='parent-symlink':
        alias=tmp_path/'alias';alias.symlink_to(directory,target_is_directory=True)
        with pytest.raises(ValueError,match='distinct destination'):
            _RenderDelivery(str(video),str(alias/'output.mp4'))
        return
    target=directory/'untouched';target.write_bytes(b'link target')
    if kind=='hardlink': os.link(video,report)
    else: report.symlink_to(target)
    with _RenderDelivery(str(video),str(report)) as owned:
        Path(owned.video_stage).write_bytes(b'new video');owned.prepare_report({'new':True});owned.prepare_rollback();owned.commit()
    assert video.read_bytes()==b'new video' and json.loads(report.read_text())=={'new':True}
    assert target.read_bytes()==b'link target' and not report.is_symlink()


@pytest.mark.parametrize('kind',['sdr','hdr','fallback'])
def test_real_direct_stage_containers_and_resources(source,tmp_path,monkeypatch,kind):
    output=tmp_path/('output.mov' if kind=='sdr' else 'output.mkv' if kind=='hdr' else 'output')
    output.write_bytes(b'previous')
    if kind=='fallback': monkeypatch.setattr(app,'nvenc_available',lambda *args:None)
    class Check(Quiet):
        def progress(self,*args): assert output.read_bytes()==b'previous'
    with owners(monkeypatch) as observed:
        direct_render(kind,source,output,Check())
        assert_closed(observed)
        assert output.read_bytes()!=b'previous'
        assert not list(tmp_path.glob('.render-*.tmp*'))


@pytest.mark.parametrize('role',['video','report'])
@pytest.mark.parametrize('present',[True,False])
def test_each_restore_attempt_failure_retains_recovery(tmp_path,monkeypatch,role,present):
    from openscrub_internal import render_delivery as delivery
    video,report=tmp_path/'output.mp4',tmp_path/'report.json'
    for path in [video,report]:
        if present:path.write_bytes(b'old')
    real_replace,real_unlink=os.replace,os.unlink
    target=str(video if role=='video' else report)
    primary=RuntimeError('terminal sentinel')
    def replace(src,dst):
        if str(dst)==target and '.render-recovery-' in str(src):raise OSError('restore sentinel')
        return real_replace(src,dst)
    def unlink(path,*args,**kwargs):
        if str(path)==target:raise OSError('absence sentinel')
        return real_unlink(path,*args,**kwargs)
    with delivery._RenderDelivery(str(video),str(report)) as owned:
        Path(owned.video_stage).write_bytes(b'new');owned.prepare_report({'new':True});owned.prepare_rollback()
        monkeypatch.setattr(os,'replace',replace);monkeypatch.setattr(os,'unlink',unlink)
        def fail():raise primary
        with pytest.raises(delivery._DeliveryRecoveryError) as caught:owned.commit(publish_success=fail)
        assert caught.value.primary is primary
    assert list(tmp_path.glob('.render-recovery-*.json'))
    if present:assert list(tmp_path.glob('.render-recovery-*.'+role))


def test_postcommit_notification_or_backup_cleanup_cannot_relabel_success(review,monkeypatch):
    real_unlink=os.unlink
    def unlink(path,*args,**kwargs):
        if str(path).endswith('.video') and '.render-recovery-' in str(path): raise OSError('backup cleanup')
        return real_unlink(path,*args,**kwargs)
    review.output.write_bytes(b'previous')
    monkeypatch.setattr(os,'unlink',unlink)
    result=app.run_pipeline(render_args(review),Quiet())
    assert result['output']==str(review.output)
    assert json.loads(review.path.read_text())['provenance']['output_sha256']==app.sha256_file(review.output)


def test_cleanup_descriptor_failure_before_commit_is_visible_to_live_job(store,monkeypatch):
    import openscrub_web as web
    store.doc['render_state']['bands']=[[0,0]]*30;store.path.write_text(json.dumps(store.doc))
    monkeypatch.setattr(app,'normalize_vfr',lambda *args:None)
    monkeypatch.setattr(app,'_render_into',lambda src,dst,*args,**kwargs:Path(dst).write_bytes(b'new'))
    real_prepare=__import__('openscrub_internal.render_delivery',fromlist=['_RenderDelivery'])._RenderDelivery.prepare_rollback
    def prepare(owned):
        real_prepare(owned)
        store.job['cancel'].set()
    from openscrub_internal import render_delivery as delivery
    monkeypatch.setattr(delivery._RenderDelivery,'prepare_rollback',prepare)
    real_unlink=os.unlink
    def unlink(path,*args,**kwargs):
        if str(path).endswith('.json') and '.render-recovery-' in str(path): raise OSError('descriptor cleanup')
        return real_unlink(path,*args,**kwargs)
    monkeypatch.setattr(os,'unlink',unlink)
    web._run_job(store.job,'render')
    assert web.FILES.initialize(store.job).recovery_required
    assert store.job['error']=='render delivery requires recovery'


def test_vault_roundtrip_keeps_recovery_and_only_discards_reserved_stages(tmp_path):
    import openscrub_vault as vault
    key=os.urandom(32)
    retained=['.render-recovery-'+'a'*32+'.json','.render-recovery-'+'a'*32+'.video','.render-user.tmp.mp4','.hidden']
    discarded=['.render-'+'b'*32+'.tmp.mp4','.render-'+'c'*32+'.tmp.mov.noaudio.mp4','.report-arbitrary.tmp']
    for name in retained+discarded:(tmp_path/name).write_bytes(b'sensitive')
    assert vault.encrypt_tree(key,str(tmp_path))==len(retained)
    assert all(not (tmp_path/name).exists() for name in discarded)
    assert vault.decrypt_tree(key,str(tmp_path))==len(retained)
    assert all((tmp_path/name).read_bytes()==b'sensitive' for name in retained)


def test_terminal_assignment_failure_restores_pair_and_fields(store,monkeypatch):
    import openscrub_web as web
    store.doc['render_state']['bands']=[[0,0]]*30;store.path.write_text(json.dumps(store.doc))
    old_report=store.path.read_bytes();output=Path(store.job['dir'])/'output.mp4';output.write_bytes(b'old video')
    primary=RuntimeError('terminal assignment sentinel')
    class FailOnce(dict):
        failed=False
        def __setitem__(self,key,value):
            if key=='phase' and value=='done' and not self.failed:
                self.failed=True;raise primary
            return super().__setitem__(key,value)
    job=FailOnce(store.job);job['output']=str(output);web.JOBS[job['id']]=job;store.job=job
    monkeypatch.setattr(app,'normalize_vfr',lambda *args:None)
    monkeypatch.setattr(app,'_render_into',lambda src,dst,*args,**kwargs:Path(dst).write_bytes(b'new'))
    web._run_job(job,'render')
    assert job['phase']=='error' and job['error']==str(primary)
    assert job['output']==str(output) and output.read_bytes()==b'old video'
    assert store.path.read_bytes()==old_report and web.FILES.initialize(job).output_epoch==4


def test_acknowledged_cancel_prevents_pair_mutation(store,monkeypatch):
    import openscrub_web as web
    from openscrub_internal import render_delivery as delivery
    from test_job_lifecycle import request
    store.doc['render_state']['bands']=[[0,0]]*30;store.path.write_text(json.dumps(store.doc))
    old_report=store.path.read_bytes();output=Path(store.job['dir'])/'output.mp4';output.write_bytes(b'old video')
    store.job['output']=str(output)
    monkeypatch.setattr(app,'normalize_vfr',lambda *args:None)
    monkeypatch.setattr(app,'_render_into',lambda src,dst,*args,**kwargs:Path(dst).write_bytes(b'new'))
    real=delivery._RenderDelivery.prepare_rollback
    def prepare(owned):
        real(owned)
        assert request('post',store.url+'/cancel').status_code==200
        assert store.job['phase']=='cancelled'
    monkeypatch.setattr(delivery._RenderDelivery,'prepare_rollback',prepare)
    web._run_job(store.job,'render')
    assert output.read_bytes()==b'old video' and store.path.read_bytes()==old_report
    assert web.FILES.initialize(store.job).output_epoch==0


def test_postcommit_pipeline_notification_cannot_relabel_web_success(store,monkeypatch):
    import openscrub_web as web
    store.doc['render_state']['bands']=[[0,0]]*30;store.path.write_text(json.dumps(store.doc))
    monkeypatch.setattr(app,'normalize_vfr',lambda *args:None)
    monkeypatch.setattr(app,'_render_into',lambda src,dst,*args,**kwargs:Path(dst).write_bytes(b'new'))
    real=app.run_pipeline
    def pipeline(*args,**kwargs):
        real(*args,**kwargs)
        raise OSError('postcommit notification')
    monkeypatch.setattr(app,'run_pipeline',pipeline)
    web._run_job(store.job,'render')
    assert store.job['phase']=='done' and store.job['error'] is None
    assert Path(store.job['output']).read_bytes()==b'new'
