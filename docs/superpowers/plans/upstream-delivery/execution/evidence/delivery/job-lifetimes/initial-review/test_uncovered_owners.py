import json
from pathlib import Path
import threading

import openscrub
import openscrub_web as web
from test_job_lifecycle import store, request


def test_allowlist_cannot_write_plaintext_after_vault_lock(store):
    store.enable()
    assert request('post', '/api/vault/lock').status_code == 200
    response = request('post', '/api/allowlist', json={'words': ['synthetic-person']})
    path = store.jobs / 'allowlist.txt'
    print(json.dumps({'route_status': response.status_code,
                      'vault_locked': web.vault_locked(),
                      'plaintext_created': path.exists(),
                      'plaintext': path.read_text() if path.exists() else None}))
    assert response.status_code == 423
    assert not path.exists()


def test_render_original_source_is_owned_before_normalization(store, monkeypatch):
    destination = web.new_job('', {}, 'normalized-synthetic.avi')
    normalized = Path(destination['dir']) / 'input.cfr.mp4'
    normalized.write_bytes(b'synthetic normalized input')
    destination.update(video=str(normalized), phase='review')
    doc = dict(store.doc)
    doc['provenance'] = dict(store.doc['provenance'], input=str(normalized),
                             original_input=store.job['video'], vfr_normalized=True)
    doc['render_state'] = dict(store.doc['render_state'], bands=[[0, 0]] * 30)
    (Path(destination['dir']) / 'report.json').write_text(json.dumps(doc))
    entered, release = threading.Event(), threading.Event()
    sources = []
    def normalize(args, cb):
        sources.append(args.video)
        entered.set()
        assert release.wait(8)
        raise RuntimeError('stop at synthetic normalization boundary')
    monkeypatch.setattr(openscrub, 'normalize_vfr', normalize)
    assert request('post', '/api/jobs/' + destination['id'] + '/render').status_code == 200
    web.WORK_Q.put(None)
    worker = threading.Thread(target=web.worker)
    worker.start()
    try:
        assert entered.wait(5)
        response = request('delete', store.url)
        print(json.dumps({'actual_render_source': sources,
                          'source_delete_status': response.status_code,
                          'source_exists': Path(store.job['video']).exists(),
                          'destination_phase': destination['phase']}))
        assert sources == [store.job['video']]
        assert response.status_code == 409
    finally:
        release.set()
        worker.join(8)
        assert not worker.is_alive()
