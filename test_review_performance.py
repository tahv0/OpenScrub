"""Resource and exact-frame regressions for inline plate review."""
import json
import subprocess
from unittest.mock import patch

import cv2
import numpy as np
import pytest

import openscrub_web as web
from test_plate_quad_editor import plate_job


def test_thumbnail_metadata_image_and_save_share_one_decode(plate_job, monkeypatch):
    client, jid, report, _ = plate_job
    original = web._frame_at
    calls = []
    def counted(*args, **kwargs):
        calls.append((args[1:], kwargs))
        return original(*args, **kwargs)
    monkeypatch.setattr(web, '_frame_at', counted)
    thumb = client.get('/api/jobs/%s/thumb/0' % jid)
    assert thumb.status_code == 200
    assert 'X-Plate-Geometry' in thumb.headers
    metadata = client.get('/api/jobs/%s/plate_quad/0' % jid).get_json()
    assert client.get('/api/jobs/%s/plate_quad/0/frame' % jid).status_code == 200
    response = client.post('/api/jobs/%s/plate_quad/0' % jid, json={
        'points': metadata['points'], 'preview_token': metadata['preview_token']})
    assert response.status_code == 200, response.get_data(as_text=True)
    assert len(calls) == 1


def test_plate_preview_uses_integer_frame_not_rounded_time(plate_job):
    client, jid, report, _ = plate_job
    doc = json.loads(report.read_text())
    doc['detections'][0].update(frame_index=7, last_seen=.2)
    report.write_text(json.dumps(doc))
    with patch.object(web, '_frame_at', return_value=np.zeros((160, 240, 3), np.uint8)) as decode:
        response = client.get('/api/jobs/%s/plate_quad/0' % jid)
    assert response.status_code == 200
    assert decode.call_args.args[3] == 7
    assert response.get_json()['frame'] == 7


def test_stale_preview_cannot_overwrite_changed_detection(plate_job):
    client, jid, report, _ = plate_job
    endpoint = '/api/jobs/%s/plate_quad/0' % jid
    meta = client.get(endpoint).get_json()
    doc = json.loads(report.read_text())
    doc['detections'][0]['cbox'] = [50, 70, 140, 105]
    report.write_text(json.dumps(doc))
    response = client.post(endpoint, json={'points': meta['points'],
                                         'preview_token': meta.get('preview_token', 'old')})
    assert response.status_code == 409
    assert json.loads(report.read_text())['detections'][0].get('plate_quad') is None


def test_late_frame_has_bounded_decode_work(tmp_path, monkeypatch):
    """A far-away target must not read target+1 frames in Python."""
    class CountCapture:
        reads = 0
        def __init__(self, *args, **kwargs): pass
        def read(self):
            CountCapture.reads += 1
            return True, np.zeros((4, 4, 3), np.uint8)
        def release(self): pass
    monkeypatch.setattr(web.cv2, 'VideoCapture', CountCapture)
    # The existing implementation makes 18,001 read calls here.
    path = tmp_path / 'fake.mp4'
    path.write_bytes(b'not a video')
    with web.app.test_request_context():
        try:
            web._read_exact_frame(str(path), 18000)
        except Exception:
            pass  # A bounded, explicit failure is safe for unsupported input.
    assert CountCapture.reads < 10


def test_inline_editor_has_no_modal_dependency():
    assert 'id="plateQuadOverlay"' not in web.APP_JS
    assert 'X-Plate-Geometry' in web.APP_JS
    assert 'POLL=setInterval(refresh,900)' not in web.APP_JS


def test_cached_preview_survives_frame_cache_eviction(plate_job, monkeypatch):
    client, jid, _, _ = plate_job
    endpoint = '/api/jobs/%s/plate_quad/0' % jid
    meta = client.get(endpoint).get_json()
    def forbidden(*args, **kwargs):
        pytest.fail('A cached crop must not decode video again')
    monkeypatch.setattr(web, '_frame_at', forbidden)
    assert client.get('/api/jobs/%s/thumb/0' % jid).status_code == 200
    assert client.get(endpoint+'/frame').status_code == 200
    assert client.post(endpoint, json={'points':meta['points'],
                                      'preview_token':meta['preview_token']}).status_code == 200
    assert client.get(endpoint).status_code == 200


def test_busy_decoder_returns_retry_without_queueing_workers(plate_job):
    import threading
    client, jid, _, _ = plate_job
    entered, release = threading.Event(), threading.Event()
    def occupy():
        with web._REVIEW_WORK_LOCK:
            entered.set();release.wait(5)
    worker = threading.Thread(target=occupy)
    worker.start();assert entered.wait(2)
    try:
        response = client.get('/api/jobs/%s/plate_quad/0' % jid)
        assert response.status_code == 503
        assert response.headers['Retry-After'] == '2'
    finally:
        release.set();worker.join(2)


def test_decoder_has_a_hard_process_deadline(plate_job, monkeypatch):
    client, jid, _, _ = plate_job
    seen = []
    def timeout(command, **options):
        seen.append(options)
        raise subprocess.TimeoutExpired(command, options['timeout'])
    monkeypatch.setattr(web.subprocess, 'run', timeout)
    response = client.get('/api/jobs/%s/plate_quad/0' % jid)
    assert response.status_code == 504
    assert 'timed out' in response.get_json()['error']
    assert seen and all(item['timeout'] <= 10 for item in seen)


@pytest.mark.parametrize('rate,offset', [('30', '0'), ('30000/1001', '5'), ('120', '0')])
def test_exact_seek_matches_b_frame_video_with_fractional_rates(tmp_path, rate, offset):
    import shutil
    if not shutil.which('ffmpeg'):
        pytest.skip('FFmpeg required')
    video = tmp_path / 'numbered.mp4'
    frames = [np.full((64, 96, 3), 20+i*3, np.uint8) for i in range(60)]
    command = ['ffmpeg','-v','error','-y','-f','rawvideo','-pix_fmt','bgr24',
               '-s','96x64','-r',rate,'-i','pipe:0','-c:v','libx264','-threads','1',
               '-g','30','-bf','3','-output_ts_offset',offset,str(video)]
    result = subprocess.run(command, input=b''.join(f.tobytes() for f in frames),
                            capture_output=True, timeout=15)
    assert result.returncode == 0, result.stderr
    with web.app.test_request_context():
        for index in (0, 1, 29, 30, 51, 59):
            frame = web._read_exact_frame(str(video), index)
            assert frame is not None
            assert abs(float(frame.mean()) - (20+index*3)) < 4
        # Cached source pixels must not be painted on by a previous caller.
        frame[:] = 0
        assert web._read_exact_frame(str(video), 59).mean() > 190


def test_pollers_are_single_flight_and_back_off(tmp_path):
    import shutil
    if not shutil.which('node'):
        pytest.skip('Node required')
    js = web.APP_JS
    load = js[js.index('async function loadJobs(){'):js.index('async function retryJob(')]
    refresh = js[js.index('async function refresh(){'):js.index('async function refreshJob(')]
    harness = r"""
const assert=require('node:assert/strict');
let JOBSFLIGHT=null,JOBSRETRYAT=0,JOBSFAILURES=0,JOBSJSON='',jobs={innerHTML:''};
let CUR='one',JOBVIEW=1,POLL=null,REFRESHFLIGHT=null,REFRESHCTRL=null,REFRESHFAILURES=0,SHELLPH='review';
const document={hidden:false,getElementById(){return {textContent:''}}};
let calls=0,resolve,reject,delays=[];
function clearTimeout(){};function setTimeout(fn,ms){delays.push(ms);return 1;}
function reviewRequest(){calls++;return new Promise((ok,no)=>{resolve=ok;reject=no;});}
function refreshJob(){return reviewRequest();}
""" + load + refresh + r"""
(async()=>{
 const first=loadJobs();for(let i=0;i<50;i++)loadJobs();
 assert.equal(calls,1);resolve({data:[]});await first;
 let next=loadJobs();assert.equal(calls,2);reject(new Error('connection lost'));await next;
 await loadJobs();assert.equal(calls,2);assert.ok(JOBSRETRYAT>Date.now());
 calls=0;const poll=refresh();for(let i=0;i<50;i++)refresh();
 assert.equal(calls,1);resolve();await poll;assert.equal(delays.at(-1),5000);
 const failed=refresh();reject(new Error('offline'));await failed;
 assert.equal(REFRESHFAILURES,1);assert.ok(delays.at(-1)>=2000);
 console.log('single-flight polling and backoff OK');
})().catch(e=>{console.error(e);process.exitCode=1;});
"""
    result = subprocess.run(['node', '-e', harness], capture_output=True, text=True, timeout=10)
    assert result.returncode == 0, result.stdout+result.stderr


def test_long_video_frame_identity_uses_integer_pts(tmp_path, monkeypatch):
    """showinfo's human-readable pts_time rounds away precision on long clips."""
    path = tmp_path / 'long.mp4'
    path.write_bytes(b'fixture')
    pixels = np.full((4, 4, 3), 73, np.uint8)
    ok, png = cv2.imencode('.png', pixels)
    assert ok
    monkeypatch.setattr(web, '_review_probe', lambda *_: {'fps':120., 'start':0., 'cfr':True})
    monkeypatch.setattr(web, '_review_process', lambda *_: subprocess.CompletedProcess(
        [], 0, png.tobytes(), b'[Parsed_showinfo_0] config in time_base: 1/120, frame_rate: 120/1\n'
        b'[Parsed_showinfo_0] n:   0 pts: 120001 pts_time:1000.01 pos: 42\n'))
    with web.app.test_request_context():
        frame = web._read_exact_frame(str(path), 120001)
    assert np.array_equal(frame, pixels)


def test_corrupt_cached_preview_is_rebuilt(plate_job):
    from pathlib import Path
    client, jid, _, _ = plate_job
    cache = Path(web.JOBS[jid]['dir']) / 'plate_preview_0.npz'
    cache.write_bytes(b'PK\x03\x04broken zip')
    response = client.get('/api/jobs/%s/thumb/0' % jid)
    assert response.status_code == 200
    assert response.headers.get('X-Plate-Geometry')


@pytest.mark.parametrize('path', ['thumb/0', 'plate_quad/0', 'plate_quad/0/frame'])
def test_cached_preview_bypasses_busy_decoder(plate_job, monkeypatch, path):
    import threading
    client, jid, _, _ = plate_job
    assert client.get('/api/jobs/%s/thumb/0' % jid).status_code == 200
    monkeypatch.setattr(web, '_frame_at', lambda *a, **k: pytest.fail('cache hit decoded video'))
    entered, release = threading.Event(), threading.Event()
    def occupy():
        with web._REVIEW_WORK_LOCK:
            entered.set()
            release.wait(10)
    worker = threading.Thread(target=occupy)
    worker.start()
    assert entered.wait(2)
    try:
        response = client.get('/api/jobs/%s/%s' % (jid, path))
        assert response.status_code == 200, response.get_data(as_text=True)
    finally:
        release.set()
        worker.join(2)


def test_cache_only_miss_does_not_decode_or_publish(plate_job, monkeypatch):
    client, jid, _, job_dir = plate_job
    calls = []
    def decoder(*a, **k):
        calls.append(True)
        return np.zeros((160, 240, 3), np.uint8)
    monkeypatch.setattr(web, '_frame_at', decoder)
    response = client.get('/api/jobs/%s/thumb/0?cache_only=1' % jid)
    assert response.status_code == 204
    assert response.cache_control.no_store
    assert not calls
    assert not list(job_dir.glob('plate_preview_*.npz'))


def test_plate_thumbnail_reads_report_only_once(plate_job, monkeypatch):
    client, jid, _, _ = plate_job
    original = web._load_job_report
    calls = []
    def counted(*a, **k):
        calls.append(True)
        return original(*a, **k)
    monkeypatch.setattr(web, '_load_job_report', counted)
    assert client.get('/api/jobs/%s/thumb/0' % jid).status_code == 200
    assert len(calls) == 1


def test_cache_only_refuses_stale_geometry_and_recovers(plate_job, monkeypatch):
    client, jid, report, _ = plate_job
    endpoint = '/api/jobs/%s/thumb/0' % jid
    old = client.get(endpoint)
    assert old.status_code == 200
    doc = json.loads(report.read_text())
    doc['detections'][0]['cbox'] = [50, 70, 140, 105]
    report.write_text(json.dumps(doc))
    with patch.object(web, '_frame_at', side_effect=AssertionError('cache-only decoded video')):
        assert client.get(endpoint+'?cache_only=1').status_code == 204
    new = client.get(endpoint)
    assert new.status_code == 200
    assert new.headers['X-Plate-Geometry'] != old.headers['X-Plate-Geometry']
    with patch.object(web, '_frame_at', side_effect=AssertionError('warm hit decoded video')):
        assert client.get(endpoint+'?cache_only=1').status_code == 200


def test_cache_only_corruption_falls_back_to_bounded_generation(plate_job):
    client, jid, _, job_dir = plate_job
    endpoint = '/api/jobs/%s/thumb/0' % jid
    cache = job_dir / 'plate_preview_0.npz'
    cache.write_bytes(b'PK\x03\x04broken zip')
    assert client.get(endpoint+'?cache_only=1').status_code == 204
    assert client.get(endpoint).status_code == 200
    assert client.get(endpoint+'?cache_only=1').status_code == 200


def test_cached_preview_is_not_served_when_vault_is_locked(plate_job, monkeypatch):
    client, jid, _, _ = plate_job
    endpoint = '/api/jobs/%s/thumb/0' % jid
    assert client.get(endpoint).status_code == 200
    monkeypatch.setattr(web, 'vault_locked', lambda: True)
    assert client.get(endpoint+'?cache_only=1').status_code == 423


def test_browser_cached_previews_do_not_wait_for_cold_generation():
    import shutil
    if not shutil.which('node'):
        pytest.skip('Node required')
    source = web.APP_JS
    helpers = source[source.index('let REVIEW_MEDIA=null;'):source.index('let QEDIT=null;')]
    harness = r'''
const assert=require('node:assert/strict');
let QEDIT=null,requests=[],badImage=false,activeCache=0,maxCache=0,activeCold=0,maxCold=0;
const images=Array.from({length:8},(_,i)=>({
 isConnected:true,naturalWidth:0,dataset:{previewUrl:'/thumb/'+i},src:'',
 closest(selector){if(selector==='[hidden]')return null;assert.equal(selector,'.det');return {querySelector(){return {textContent:'',hidden:false}}}},
 async decode(){this.naturalWidth=100;}
}));
const document={querySelectorAll(){return images}};
let next=0;URL.createObjectURL=()=> 'blob:'+ ++next;URL.revokeObjectURL=()=>{};
global.Image=class {async decode(){if(badImage)throw new Error('corrupt image');}};
''' + helpers + r'''
reviewRequest=async (url,options)=>{
 requests.push(url);
 if(url.includes('cache_only=1')){
  activeCache++;maxCache=Math.max(maxCache,activeCache);
  await new Promise(resolve=>setImmediate(resolve));activeCache--;
  return {response:{status:url.startsWith('/thumb/1?')?200:204,headers:{get(){return null}}},data:{}};
 }
 activeCold++;maxCold=Math.max(maxCold,activeCold);
 return new Promise((resolve,reject)=>options.signal.addEventListener('abort',()=>{
  activeCold--;reject(new DOMException('aborted','AbortError'));
 },{once:true}));
};
(async()=>{
 initReviewPreviews();
 const pending=images.map(img=>img._previewTask.promise);
 for(let i=0;i<20;i++)await new Promise(resolve=>setImmediate(resolve));
 assert.equal(images[1].naturalWidth,100,'warm preview is blocked behind cold decoder');
 assert.equal(images[0].naturalWidth,0);
 assert.equal(maxCold,1);assert.ok(maxCache<=3);
 const old=images[1].src;badImage=true;
 const failed=queueReviewPreview(images[1],true);
 assert.equal(await failed,false);
 assert.equal(images[1].src,old,'failed refresh discarded the usable image');
 assert.equal(images[1].naturalWidth,100);
 clearReviewPreviews();
 await Promise.all(pending);
 assert.equal(REVIEW_MEDIA,null);assert.equal(activeCold,0);
 console.log('cached preview overtakes cold work; limits, fallback and cancellation OK');
})().catch(e=>{console.error(e);process.exitCode=1;});
'''
    result = subprocess.run(['node','-e',harness],capture_output=True,text=True,timeout=10)
    assert result.returncode == 0, result.stdout+result.stderr


def test_cache_only_rejects_replaced_source(plate_job):
    import os
    client, jid, _, _ = plate_job
    endpoint = '/api/jobs/%s/thumb/0' % jid
    assert client.get(endpoint).status_code == 200
    path = web.JOBS[jid]['video']
    stat = os.stat(path)
    os.utime(path, ns=(stat.st_atime_ns, stat.st_mtime_ns+1000000000))
    with patch.object(web, '_frame_at', side_effect=AssertionError('cache-only decoded')):
        assert client.get(endpoint+'?cache_only=1').status_code == 204


def test_cache_only_nonplate_does_not_start_decoder(plate_job, monkeypatch):
    client, jid, report, job_dir = plate_job
    doc = json.loads(report.read_text())
    doc['detections'][0]['category'] = 'face'
    report.write_text(json.dumps(doc))
    endpoint = '/api/jobs/%s/thumb/0?cache_only=1' % jid
    monkeypatch.setattr(web, '_frame_at', lambda *a, **k: pytest.fail('cache-only decoded'))
    assert client.get(endpoint).status_code == 204
    assert cv2.imwrite(str(job_dir/'thumb2_0.jpg'), np.full((16, 16, 3), 88, np.uint8))
    assert client.get(endpoint).status_code == 200


def test_vault_encryption_excludes_cache_readers(monkeypatch):
    monkeypatch.setitem(web.VAULT, 'key', b'test-key')
    calls = []
    def encrypt(*args):
        assert web._REVIEW_CACHE_LOCK.locked()
        calls.append(True)
        return 0
    monkeypatch.setattr(web.vault, 'encrypt_tree', encrypt)
    assert web._vault_lock_now() == 0
    assert calls and web.VAULT['key'] is None


def test_cached_corner_save_does_not_wait_for_video_decoder(plate_job, monkeypatch):
    import threading
    client, jid, report, _ = plate_job
    url = '/api/jobs/%s/plate_quad/0' % jid
    meta = client.get(url).get_json()
    points = [p[:] for p in meta['points']]
    points[0][0] += 2
    entered, release = threading.Event(), threading.Event()
    def occupy():
        with web._REVIEW_WORK_LOCK:
            entered.set(); release.wait(10)
    worker = threading.Thread(target=occupy)
    worker.start(); assert entered.wait(2)
    monkeypatch.setattr(web, '_frame_at', lambda *a, **k: pytest.fail('warm save decoded video'))
    try:
        response = client.post(url, json=dict(points=points, preview_token=meta['preview_token'],
                               autosave=True, edit_id='warm-save'))
        assert response.status_code == 200, response.get_data(as_text=True)
        assert json.loads(report.read_text())['detections'][0]['plate_quad']
    finally:
        release.set(); worker.join(2)


def test_track_geometry_refresh_reuses_original_crop(plate_job, monkeypatch):
    from copy import deepcopy
    client, jid, report, _ = plate_job
    doc = json.loads(report.read_text())
    doc['detections'].append(deepcopy(doc['detections'][0]))
    doc['detections'][1]['last_seen'] = .4
    report.write_text(json.dumps(doc))
    urls = ['/api/jobs/%s/plate_quad/%d' % (jid, i) for i in range(2)]
    first, second = [client.get(url).get_json() for url in urls]
    points = [p[:] for p in first['points']]; points[0][0] += 2
    saved = client.post(urls[0], json=dict(points=points, preview_token=first['preview_token'],
                                        autosave=True, edit_id='track-save'))
    assert saved.status_code == 200
    monkeypatch.setattr(web, '_frame_at', lambda *a, **k: pytest.fail('shape-only change decoded video'))
    refreshed = client.get(urls[1])
    assert refreshed.status_code == 200
    data = refreshed.get_json()
    assert data['points'][0][0] == pytest.approx(points[0][0], abs=.001)
    assert data['crop'] == second['crop']
    assert data['preview_token'] != second['preview_token']
    assert data['source_token'] == second['source_token']


def test_review_decisions_cannot_race_corner_report_write(plate_job, monkeypatch):
    import threading
    client, jid, report, _ = plate_job
    endpoint = '/api/jobs/%s/plate_quad/0' % jid
    meta = client.get(endpoint).get_json()
    points = [p[:] for p in meta['points']]; points[0][0] += 2
    entered, release = threading.Event(), threading.Event()
    original = web._save_verified_plate_sample
    def pause(*args, **kwargs):
        entered.set(); assert release.wait(10)
        return original(*args, **kwargs)
    monkeypatch.setattr(web, '_save_verified_plate_sample', pause)
    result = []
    def save():
        with web.app.test_client() as other:
            result.append(other.post(endpoint, json=dict(points=points, autosave=True,
                preview_token=meta['preview_token'], edit_id='serial-report-write')).status_code)
    worker = threading.Thread(target=save); worker.start(); assert entered.wait(3)
    payload = dict(enabled={'0':False}, verified_labels={'0':'not_plate'})
    try:
        busy = client.post('/api/jobs/%s/detections'%jid,json=payload)
        assert busy.status_code == 503, 'concurrent report read/modify/write can erase the other edit'
    finally:
        release.set(); worker.join(3)
    assert result == [200]
    assert client.post('/api/jobs/%s/detections'%jid,json=payload).status_code == 200
    row=json.loads(report.read_text())['detections'][0]
    assert row['plate_quad'] and row['verified_label']=='not_plate' and row['enabled'] is False
