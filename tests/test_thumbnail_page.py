"""Real PAGE and HTTP thumbnail recovery with an optional prepared browser."""
import json
import os
from pathlib import Path
import shutil
import subprocess
import threading

import pytest
from werkzeug.serving import make_server

import openscrub_web as web
from test_exact_samples import exact
from test_job_lifecycle import store


def test_thumbnail_page_review_recovery(exact, tmp_path):
    module = os.environ.get('OPENSCRUB_PLAYWRIGHT_MODULE')
    chromium = os.environ.get('OPENSCRUB_CHROMIUM')
    node = os.environ.get('OPENSCRUB_NODE') or shutil.which('node')
    if not module or not chromium or not node:
        pytest.skip('prepared Playwright, Chromium, and Node are required for PAGE test')
    doc = json.loads(exact.path.read_text())
    base = doc['detections'][0]
    base.update(track=8, confidence=.95, cbox=[3, 3, 20, 20])
    doc['detections'][1].update(track=8, confidence=.5, t_start=.2, t_end=1.2)
    doc['detections'].append(dict(base, track=-1, text='ordinary', cbox=[25, 5, 45, 25]))
    doc['detections'].append(dict(base, track=-1, text='outside zone', zone_dropped=True, cbox=[4, 20, 24, 40]))
    exact.path.write_text(json.dumps(doc))
    other = web.new_job('', {}, 'synthetic-b.avi')
    other_video = Path(other['dir']) / 'input.avi'
    shutil.copyfile(exact.job['video'], other_video)
    other.update(video=str(other_video), phase='review')
    other_doc = json.loads(json.dumps(doc))
    other_doc['provenance']['input'] = str(other_video)
    (Path(other['dir']) / 'report.json').write_text(json.dumps(other_doc))
    artifacts = Path(os.environ.get('OPENSCRUB_BROWSER_ARTIFACTS', str(tmp_path / 'artifacts')))
    if not artifacts.is_dir():
        artifacts.mkdir(parents=True, exist_ok=True)
    server = make_server('127.0.0.1', 0, web.app, threaded=True)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    env = dict(os.environ, OPENSCRUB_PAGE_URL=f'http://127.0.0.1:{server.server_port}/',
               OPENSCRUB_PAGE_JOB=exact.job['id'], OPENSCRUB_PAGE_JOB_B=other['id'], OPENSCRUB_BROWSER_ARTIFACTS=str(artifacts))
    try:
        result = subprocess.run([node, str(Path(__file__).with_name('thumbnail_page.cjs'))],
                                env=env, capture_output=True, text=True, timeout=90)
        assert result.returncode == 0, result.stdout + result.stderr
    finally:
        server.shutdown()
        thread.join(10)
        server.server_close()
        assert not thread.is_alive()
    raw = json.loads(exact.path.read_text())
    assert raw['custom'] == {'preserved': True}
    assert raw['detections'][2]['cbox'] == [2.0, 2.0, 14.0, 14.0]
    assert raw['detections'][2]['enabled'] is True
    assert sum(row.get('manual_id') == 'page-newer' for row in raw['detections']) == 1
    assert len(raw['audio_redactions']) == 2
    print(result.stdout)
