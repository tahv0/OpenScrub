"""Source-frame-bound Review previews must remain viewable at frame edges.

No invalid/cropped detector proposal may silently become a trusted label,
editable human polygon, or a different video frame.
"""
import json
import subprocess
import shutil

import cv2
import numpy as np
import pytest

import finding_previews
import openscrub_web as web
from test_plate_quad_editor import plate_job


def _change_detection(report, **changes):
    doc = json.loads(report.read_text(encoding='utf-8'))
    doc['detections'][0].update(changes)
    report.write_text(json.dumps(doc), encoding='utf-8')
    return doc


@pytest.mark.parametrize('change', [
    {'plate_quad': [[-1.0, 0.0], [1.0, 0.0], [1.0, 1.0], [-1.0, 1.0]]},
    {'cbox': [-30, 67, 137, 103]},
    {'cbox': [-400, 67, -340, 103]},
])
def test_offframe_source_preview_is_viewable_but_not_training_evidence(
        plate_job, monkeypatch, change):
    client, jid, report, _ = plate_job
    doc = _change_detection(report, **change)
    endpoint = '/api/jobs/%s/finding-preview/0' % jid

    first = client.get(endpoint)
    assert first.status_code == 200, first.get_data(as_text=True)
    meta = json.loads(first.headers['X-Finding-Geometry'])
    assert meta['geometry_outside_frame'] is True
    assert meta['exact_frame'] is True
    assert meta['classification_allowed'] is False
    assert 'outside the source video frame' in meta['classification_note']
    assert meta['frame'] == 2
    assert meta['requested_frame'] == 2
    assert meta['source_token'] and meta['preview_token']
    assert meta['box'] == [float(v) for v in doc['detections'][0]['cbox']]
    assert 0 <= meta['crop'][0] < meta['crop'][2] <= 240
    assert 0 <= meta['crop'][1] < meta['crop'][3] <= 160
    picture = cv2.imdecode(np.frombuffer(first.data, np.uint8), cv2.IMREAD_COLOR)
    assert picture is not None and picture.size > 0

    # The picture is now in the same immutable, source-bound compact cache.
    # A second display or explicit cache-only request cannot decode the video.
    monkeypatch.setattr(web, '_frame_at',
                        lambda *a, **k: pytest.fail('warm picture decoded again'))
    cached = client.get(endpoint + '?cache_only=1')
    assert cached.status_code == 200
    assert cached.data == first.data
    assert json.loads(cached.headers['X-Finding-Geometry'])['preview_token'] == meta['preview_token']

    for label in ('positive', 'negative'):
        denied = client.post('/api/jobs/%s/confirm/0' % jid,
                             json={'label': label, 'preview_token': meta['preview_token']})
        assert denied.status_code == 409, denied.get_data(as_text=True)
        assert 'outside the source video frame' in denied.get_json()['error']

    denied_corners = client.post('/api/jobs/%s/finding-region/0' % jid,
                                 json={'points': [[45, 67], [100, 67],
                                                 [100, 103], [45, 103]],
                                       'preview_token': meta['preview_token']})
    assert denied_corners.status_code == 409
    assert 'outside the source video frame' in denied_corners.get_json()['error']
    assert json.loads(report.read_text(encoding='utf-8')) == doc
    assert doc['detections'][0].get('enabled', True) is True


def test_valid_detection_at_video_boundary_remains_editable(plate_job):
    client, jid, report, _ = plate_job
    _change_detection(report, cbox=[0, 67, 92, 103], frame_index=2)
    response = client.get('/api/jobs/%s/finding-preview/0' % jid)
    assert response.status_code == 200
    meta = json.loads(response.headers['X-Finding-Geometry'])
    assert not meta.get('geometry_outside_frame')
    assert meta['classification_allowed'] is True
    assert all(0 <= x <= 240 and 0 <= y <= 160 for x, y in meta['points'])


def test_outside_crop_inside_source_remains_rejected(tmp_path):
    # A stale or incorrectly-sized crop is NOT recoverable merely because
    # the requested preview is a cold decode. All in-frame corners must fit.
    row = dict(t_start=.3, t_end=.3, last_seen=.3, frame_index=3,
               cbox=[100, 90, 220, 140], category='plate', text='plate',
               aoff=[20, 10], track=-1)
    state = {'fps': 10., 'cum': [[20, 10]] * 10}
    crop = [0, 0, 150, 150]  # 240px right-hand corner is inside video, not crop
    pixels = np.zeros((150, 150, 3), np.uint8)
    with pytest.raises(ValueError, match='preview geometry lies outside the crop'):
        finding_previews.store(tmp_path, row, state, dict(
            width=1600, height=900, frame=3, crop=crop), pixels)
    assert finding_previews.lookup(tmp_path, row, state) is None


def test_offscreen_fallback_cache_is_not_rebound_to_new_corners(tmp_path):
    row = dict(t_start=.3, t_end=.3, last_seen=.3, frame_index=3,
               cbox=[100, 90, 220, 140], category='plate', text='plate',
               aoff=[20, 10], track=-1,
               plate_quad=[[-2, 0], [1, 0], [1, 1], [-2, 1]])
    state = {'fps': 10., 'cum': [[20, 10]] * 10}
    crop = [0, 0, 400, 240]
    pixels = np.zeros((240, 400, 3), np.uint8)
    original, data = finding_previews.store(tmp_path, row, state, dict(
        width=1600, height=900, frame=3, crop=crop), pixels)
    assert original['geometry_outside_frame'] is True
    assert original['points'][0][0] < 0
    assert finding_previews.lookup(tmp_path, row, state)[1] == data
    assert finding_previews.lookup(tmp_path, row, state,
                                   preferred_key=original['key'])[1] == data
    changed = dict(row, plate_quad=[[-3, 0], [1, 0], [1, 1], [-3, 1]])
    assert finding_previews.lookup(tmp_path, changed, state) is None
    assert finding_previews.lookup(tmp_path, changed, state,
                                   preferred_key=original['key']) is None


def test_offframe_picture_does_not_activate_corner_editor():
    """Execute production browser helper, not an imitation of its decision."""
    if not shutil.which('node'):
        pytest.skip('Node not available')
    js = web.APP_JS
    helper = js[js.index('function drawPlateThumbnail('):
                js.index('function updateReviewPreloadStatus(')]
    script = ("""
const assert=require('node:assert/strict');
const PLATE_EDITS=new Map();
let editorCalls=0, aborts=0;
function initPlateCorners(){editorCalls++;}
function plateCopy(points){return points.map(p=>p.slice());}
""" + helper + """
const canvas={width:320,style:{pointerEvents:'auto'}};
const editor={i:4,dirty:false,pending:null,drag:null,
  events:{abort(){aborts++}},observer:{disconnect(){}}};
PLATE_EDITS.set(4,editor);
const img={naturalWidth:320,_plateMeta:{geometry_outside_frame:true},
  _quadEdit:editor,closest(){return {querySelector(){return canvas}}}};
drawPlateThumbnail(img);
assert.equal(editorCalls,0);
assert.equal(aborts,1);
assert.equal(img._quadEdit,undefined);
assert.equal(canvas.style.pointerEvents,'none');
assert.equal(PLATE_EDITS.size,0);
""")
    run = subprocess.run(['node', '-e', script], capture_output=True, text=True,
                         timeout=15)
    assert run.returncode == 0, run.stderr
