"""Actual scan callback/adoption boundaries, with controlled finite holds."""
import json
import threading
from pathlib import Path

import pytest
import openscrub
import openscrub_web as web
from test_job_lifecycle import store, request
from test_report_transactions import join
from test_exact_samples import exact, sample


@pytest.fixture
def scan(exact,monkeypatch):
    def compute(args,cb):
        return dict(fps=5,cum=[[0,0]]*10,bands=[[0,0]]*10,detections=[],stats={})
    monkeypatch.setattr(openscrub,'run_scan',compute)
    threads=[];real=web._start_owned_thread
    def start(*a):
        thread=real(*a);threads.append(thread);return thread
    monkeypatch.setattr(web,'_start_owned_thread',start)
    yield exact, threads
    for thread in threads:join(thread)


def test_every_native_scan_is_pending_then_adopts_before_pregen(scan,monkeypatch):
    exact,threads=scan;files=web.FILES.initialize(exact.job)
    old=sample(exact)['sample']['source_ref'];entered,release=threading.Event(),threading.Event()
    real=web._prepare_observed_source
    def prepare(job,path):
        entered.set();assert release.wait(8);return real(job,path)
    monkeypatch.setattr(web,'_prepare_observed_source',prepare)
    worker=threading.Thread(target=web._run_job,args=(exact.job,'scan'));worker.start()
    try:
        assert entered.wait(5)
        assert files.committed_report_epoch==1 and files.source_status=='pending'
        response=request('get',exact.url+'/edit_sample?t=0.2')
        assert response.status_code==409 and response.json['error']=='source_report_pending'
        assert not threads
    finally:release.set();join(worker)
    assert files.source_status=='coherent' and exact.job['phase']=='review'
    assert sample(exact)['sample']['source_ref']==old
    assert len(threads)==1


def test_failed_preparation_is_unavailable_then_explicit_recovery(scan,monkeypatch):
    exact,threads=scan;real=web._prepare_observed_source
    def fail(*a):raise OSError('controlled preparation failure')
    monkeypatch.setattr(web,'_prepare_observed_source',fail)
    web._run_job(exact.job,'scan')
    files=web.FILES.initialize(exact.job)
    assert files.source_status=='unavailable' and not threads
    assert exact.job['phase']=='review'
    monkeypatch.setattr(web,'_prepare_observed_source',real)
    assert sample(exact)['sample']['index']==1
    assert files.source_status=='coherent' and not threads


def test_missing_normalized_source_never_pregenerates_old_source(scan,monkeypatch):
    exact,threads=scan;missing=Path(exact.job['dir'])/'missing.cfr.mp4'
    def compute(args,cb):
        args.original_video,args.video=args.video,str(missing)
        return dict(fps=5,cum=[[0,0]]*10,bands=[[0,0]]*10,detections=[],stats={})
    monkeypatch.setattr(openscrub,'run_scan',compute)
    web._run_job(exact.job,'scan')
    assert web.FILES.initialize(exact.job).source_status=='unavailable' and not threads
    assert request('get',exact.url+'/edit_sample?t=0.2').status_code==404


@pytest.mark.parametrize('replace',[False,True])
def test_late_cancel_or_replacement_cannot_adopt_or_pregen(scan,monkeypatch,replace):
    exact,threads=scan;entered,release=threading.Event(),threading.Event();real=web._prepare_observed_source
    def prepare(*a):
        value=real(*a);entered.set();assert release.wait(8);return value
    monkeypatch.setattr(web,'_prepare_observed_source',prepare)
    worker=threading.Thread(target=web._run_job,args=(exact.job,'scan'));worker.start()
    try:
        assert entered.wait(5)
        assert request('post',exact.url+'/cancel').status_code==200
        if replace:
            files=web.FILES.initialize(exact.job)
            with files.report_lock:files.operation=threading.Event()
    finally:release.set();join(worker)
    assert not threads
    assert web.FILES.initialize(exact.job).source_status!='coherent'
    assert request('get',exact.url+'/edit_sample?t=0.2').status_code!=200


def test_failed_report_publication_does_not_advance_epoch_or_pending(scan,monkeypatch):
    exact,threads=scan;files=web.FILES.initialize(exact.job)
    sample(exact)
    before=exact.path.read_bytes()
    def fail(*a):raise OSError('controlled report commit failure')
    monkeypatch.setattr(web,'_publish_job_report_locked',fail)
    web._run_job(exact.job,'scan')
    assert files.committed_report_epoch==0 and files.source_status=='coherent'
    assert exact.path.read_bytes()==before and not threads
    assert exact.job['phase']=='error'


def test_report_replaced_during_adoption_never_marks_pair_coherent(scan,monkeypatch):
    exact,threads=scan;entered,release=threading.Event(),threading.Event();real=web._prepare_observed_source
    def prepare(*a):
        result=real(*a);entered.set();assert release.wait(8);return result
    monkeypatch.setattr(web,'_prepare_observed_source',prepare)
    worker=threading.Thread(target=web._run_job,args=(exact.job,'scan'));worker.start()
    try:
        assert entered.wait(5)
        doc=json.loads(exact.path.read_text());doc['render_state']['cum'][0]=[100,200]
        replacement=exact.path.with_name('external.json');replacement.write_text(json.dumps(doc));replacement.replace(exact.path)
    finally:release.set();join(worker)
    files=web.FILES.initialize(exact.job)
    assert files.source_status=='unavailable'
    assert not threads
    assert request('get',exact.url+'/edit_sample?t=0.2').status_code==409


@pytest.mark.parametrize('retired_before_scan',[False,True])
def test_observed_old_source_failed_normalized_adoption_recovers_only_committed_pair(scan,monkeypatch,retired_before_scan):
    exact,threads=scan
    previous=sample(exact)['sample']['source_ref']
    source=Path(exact.job['video']);pixels=source.read_bytes()
    if retired_before_scan:
        replacement=source.with_name('replaced.avi');replacement.write_bytes(pixels);replacement.replace(source)
        assert request('get',exact.url+'/edit_sample?t=0.2').status_code==422
    normalized=source.with_name('normalized.avi')
    def compute(args,cb):
        args.original_video,args.video=args.video,str(normalized)
        return dict(fps=5,cum=[[0,0]]*10,bands=[[0,0]]*10,detections=[],stats={})
    monkeypatch.setattr(openscrub,'run_scan',compute)
    web._run_job(exact.job,'scan')
    files=web.FILES.initialize(exact.job)
    assert files.source_status=='unavailable' and not threads
    normalized.write_bytes(pixels)
    value=sample(exact)
    assert value['sample']['source_ref']!=previous
    assert exact.job['video']==str(normalized)
    assert files.source_pair is None and not files.source_retired
    replacement=normalized.with_name('later.avi');replacement.write_bytes(pixels);replacement.replace(normalized)
    assert request('get',exact.url+'/edit_sample?t=0.2').status_code==422
    assert request('get',exact.url+'/edit_sample?t=0.2').status_code==422
    assert files.source_pair is None and files.source_retired


def test_ordinary_scan_adoption_does_not_reread_report_for_hdr_evidence(scan, monkeypatch):
    import sys
    exact, threads = scan
    original = web._load_job_report
    adoption_reads = []
    def observe(job):
        if sys._getframe(1).f_code is web._adopt_scan_source.__code__:
            adoption_reads.append(job['id'])
        return original(job)
    monkeypatch.setattr(web, '_load_job_report', observe)
    web._run_job(exact.job, 'scan')
    assert web.FILES.initialize(exact.job).source_status == 'coherent'
    assert adoption_reads == []
