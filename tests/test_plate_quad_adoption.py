"""A stale quad save cannot cross an actual new scan/adoption."""
import hashlib
import json
import threading
from pathlib import Path

import openscrub_web as web
from test_exact_adoption import scan
from test_exact_samples import exact
from test_job_lifecycle import store, start_call, finish
from test_plate_quad import quad_edit


def test_scan_adoption_during_quad_digest_rejects_stale_save(scan, monkeypatch):
    store, threads = scan
    doc = json.loads(store.path.read_text())
    doc['detections'][0]['category'] = 'plate'
    doc['provenance']['input_sha256'] = hashlib.sha256(Path(store.job['video']).read_bytes()).hexdigest()
    store.path.write_text(json.dumps(doc))
    edits = quad_edit(store)
    entered, release = threading.Event(), threading.Event()
    original = web._quad_source_digest
    def paused(job, source):
        digest = original(job, source)
        entered.set()
        assert release.wait(8)
        return digest
    monkeypatch.setattr(web, '_quad_source_digest', paused)
    call = start_call('post', store.url + '/detections', json=edits)
    try:
        assert entered.wait(5)
        web._run_job(store.job, 'scan')
        files = web.FILES.initialize(store.job)
        assert files.source_status == 'coherent'
        selected = files.current_source
        committed = store.path.read_bytes()
    finally:
        release.set()
        response = finish(call)
    assert response.status_code == 409
    assert store.path.read_bytes() == committed
    assert files.current_source is selected and files.source_status == 'coherent'
