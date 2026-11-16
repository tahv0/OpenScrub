"""Saved review documents survive real render/reopen; all footage is synthetic."""
import builtins
import copy
import json
from pathlib import Path
import subprocess
import sys
from types import SimpleNamespace

import cv2
import numpy as np
import pytest

import openscrub


class Quiet(openscrub.Callbacks):
    def log(self, message):
        pass


@pytest.fixture
def review(tmp_path):
    video = tmp_path / 'input.avi'
    writer = cv2.VideoWriter(str(video), cv2.VideoWriter_fourcc(*'MJPG'),
                             30, (160, 96))
    assert writer.isOpened(), 'synthetic MJPEG writer unavailable'
    for i in range(60):
        writer.write(np.full((96, 160, 3), 180 + i % 20, dtype=np.uint8))
    writer.release()
    rows = []
    categories = ['name', 'plate', 'face', 'manual', 'person',
                  'name', 'person', 'face', 'manual', 'manual']
    for i, category in enumerate(categories):
        rows.append(dict(t_start=0.0, t_end=1.99,
                         cbox=[2 + 16 * i, 20.25, 14 + 16 * i, 60.75],
                         category=category, text='synthetic-%02d' % i,
                         confidence=.85000000001, aoff=[0.0, 0.0],
                         last_seen=.5, enabled=i not in (0, 4, 8),
                         dense=category in ('face', 'person'),
                         track=100 + i, person=200 + i,
                         poly=[[[0, 0], [1, 0], [.5, 1]]]
                              if category == 'manual' and i != 9 else [],
                         future_row={'nested': [i, None, False], 'note': '雪'}))
    rows[4]['zone_dropped'] = True
    doc = dict(provenance={'input': str(video), 'input_sha256':
                          openscrub.sha256_file(str(video)),
                          'output': '/stale/output.mp4', 'output_sha256': 'stale',
                          'timestamp': 'old', 'version': 'old',
                          'future_provenance': {'retain': True},
                          'settings': {'mode': 'blur', 'future_setting': {'x': 1}}},
               render_state={'fps': 30, 'cum': [[0., 0.]] * 60,
                             'bands': [[0., 0.]] * 60,
                             'future_state': {'retain': True}},
               detections=rows,
               audio_redactions=[{'t0': .2, 't1': .4, 'mode': 'mute',
                                  'future_span': {'retain': True}}],
               audio_suggestions=[{'t0': .5, 't1': .7, 'text': 'synthetic',
                                   'category': 'name', 'future_suggestion': []}],
               audio_transcript=[[0., .9, 'synthetic audio']],
               future_top={'nested': [False, None, '雪']})
    path = tmp_path / 'report.json'
    path.write_text(json.dumps(doc, indent=1), encoding='utf-8')
    return SimpleNamespace(video=video, path=path, doc=doc,
                           output=tmp_path / 'rendered.mp4')


def render_args(review, *extra, source=None, destination=None, output=None):
    return openscrub.build_parser().parse_args([
        str(review.video), '--from-report', str(source or review.path),
        '--report', str(destination or review.path),
        '--output', str(output or review.output), '--encoder', 'x264',
        '--mode', 'box', '--pad', '0', *extra])


def read(path):
    return json.loads(path.read_text(encoding='utf-8'))


def assert_review_preserved(before, after):
    # Only provenance belongs to an ordinary render. This also checks empty,
    # absent, additive, and high-precision values without normalizing them.
    assert {k: v for k, v in after.items() if k != 'provenance'} == {
        k: v for k, v in before.items() if k != 'provenance'}


def test_real_render_and_fresh_route_reopen_keep_all_ten_rows(review):
    """Reconstructing a report from enabled detections loses Keep rows/indices."""
    summary = openscrub.run_pipeline(render_args(review), Quiet())
    assert summary['regions'] == 7
    saved = read(review.path)
    assert len(saved['detections']) == 10
    assert_review_preserved(review.doc, saved)
    provenance = saved['provenance']
    assert provenance['output'] == str(review.output.resolve())
    assert provenance['output_sha256'] == openscrub.sha256_file(str(review.output))
    assert provenance['input_sha256'] == openscrub.sha256_file(str(review.video))
    assert provenance['timestamp'] != 'old'
    assert provenance['version'] == openscrub.VERSION
    assert provenance['future_provenance'] == {'retain': True}
    assert provenance['settings']['mode'] == 'box'
    assert provenance['settings']['future_setting'] == {'x': 1}

    # Actual decoded output, every frame: disabled ordinary, zone-dropped and
    # manual geometry must stay visible; seven enabled regions must be black.
    cap = cv2.VideoCapture(str(review.output))
    frames = 0
    while True:
        ok, frame = cap.read()
        if not ok:
            break
        for i in (0, 4, 8):
            assert frame[35, 8 + 16 * i].mean() > 100
        for i in (1, 2, 3, 5, 6, 7, 9):
            assert frame[35, 8 + 16 * i].mean() < 15
        frames += 1
    cap.release()
    assert frames == 60

    # Fresh module imports/process, actual registered Flask GET route. No
    # browser, server socket, models or user jobs are involved.
    script = '''
import json, sys
from pathlib import Path
import openscrub_web as web
folder = Path(sys.argv[1])
web._data_root = lambda: str(folder)
web.JOBS_DIR = str(folder / 'jobs')
web.JOBS = {'reopen': {'dir': str(folder), 'video': sys.argv[2]}}
web.TOKEN = None
with web.app.test_client() as client:
    response = client.get('/api/jobs/reopen/detections')
    assert response.status_code == 200, response.data
    print(json.dumps(response.get_json()))
'''
    result = subprocess.run([sys.executable, '-c', script, str(review.path.parent),
                             str(review.video)], capture_output=True, text=True,
                            check=True, cwd=str(Path(openscrub.__file__).parent))
    reopened = json.loads(result.stdout)
    rows = reopened['detections']
    assert [r['i'] for r in rows] == list(range(10))
    assert [r['text'] for r in rows] == ['synthetic-%02d' % i for i in range(10)]
    assert [r['enabled'] for r in rows] == [False, True, True, True, False,
                                           True, True, True, False, True]
    assert [r['track'] for r in rows] == list(range(100, 110))
    assert [r['person'] for r in rows] == list(range(200, 210))
    assert rows[4]['zone_dropped'] is True


@pytest.mark.parametrize('metadata', ['empty', 'absent'])
def test_empty_or_absent_audio_and_additive_metadata_stay_exact(review, metadata):
    for key in ('audio_redactions', 'audio_suggestions', 'audio_transcript'):
        if metadata == 'empty':
            review.doc[key] = []
        else:
            del review.doc[key]
    review.doc['future_top'] = {}
    review.doc['provenance'] = {}
    review.path.write_text(json.dumps(review.doc), encoding='utf-8')
    openscrub.run_pipeline(render_args(review), Quiet())
    assert_review_preserved(review.doc, read(review.path))


@pytest.mark.parametrize('override', ['cli', 'programmatic', 'clear', 'apply'])
def test_explicit_audio_changes_win_without_losing_review_metadata(review, override):
    extra = ['--audio-redact', '.8-1.2', '--audio-redact-mode', 'bleep'] \
        if override == 'cli' else ['--audio-pii-apply'] if override == 'apply' else []
    args = render_args(review, *extra)
    if override == 'programmatic':
        args.audio_spans = [(1.1, 1.3, 'mute')]
    elif override == 'clear':
        args.audio_spans = []
    openscrub.run_pipeline(args, Quiet())
    saved = read(review.path)
    expected = {'cli': [{'t0': .8, 't1': 1.2, 'mode': 'bleep'}],
                'programmatic': [{'t0': 1.1, 't1': 1.3, 'mode': 'mute'}],
                'clear': [],
                'apply': [{'t0': .2, 't1': .4, 'mode': 'mute'},
                          {'t0': .5, 't1': .7, 'mode': 'mute'}]}[override]
    assert saved['audio_redactions'] == expected
    before = copy.deepcopy(review.doc)
    before['audio_redactions'] = expected
    assert_review_preserved(before, saved)


def test_distinct_destination_and_successive_renders_preserve_source(review):
    original_bytes = review.path.read_bytes()
    destination = review.path.with_name('copy.json')
    openscrub.run_pipeline(render_args(review, destination=destination), Quiet())
    first = read(destination)
    assert review.path.read_bytes() == original_bytes
    assert_review_preserved(review.doc, first)
    second_output = review.output.with_name('second.mp4')
    openscrub.run_pipeline(render_args(review, source=destination,
                           destination=destination, output=second_output), Quiet())
    second = read(destination)
    assert_review_preserved(review.doc, second)
    assert second['provenance']['output'] == str(second_output)
    assert second['provenance']['output_sha256'] == openscrub.sha256_file(str(second_output))
    assert review.path.read_bytes() == original_bytes


def test_from_report_reads_one_coherent_snapshot(review, monkeypatch):
    original_open = builtins.open
    reads = []
    def counted_open(path, mode='r', *args, **kwargs):
        if Path(path) == review.path and 'r' in mode:
            reads.append(path)
        return original_open(path, mode, *args, **kwargs)
    monkeypatch.setattr(builtins, 'open', counted_open)
    openscrub.run_pipeline(render_args(review), Quiet())
    assert len(reads) == 1
    assert_review_preserved(review.doc, read(review.path))


def test_render_objects_are_separate_from_retained_review_rows(review, monkeypatch):
    original_render = openscrub.render
    def mutate_then_render(src, dst, detections, *args, **kwargs):
        # Coverage/render transformations may edit decoded objects. Such edits
        # must never replace the exact saved review representation.
        detections[0].text = 'render-only change'
        detections[0].cbox = (30, 30, 35, 35)
        detections[2].poly[0][0][0] = .25
        return original_render(src, dst, detections, *args, **kwargs)
    monkeypatch.setattr(openscrub, 'render', mutate_then_render)
    openscrub.run_pipeline(render_args(review), Quiet())
    assert_review_preserved(review.doc, read(review.path))


@pytest.mark.parametrize('failure', ['render', 'publish'])
def test_failure_before_publication_preserves_existing_report(review, monkeypatch, failure):
    previous = review.path.read_bytes()
    def fail(*args, **kwargs):
        raise OSError('synthetic ' + failure + ' failure')
    if failure == 'render':
        monkeypatch.setattr(openscrub, 'render', fail)
    else:
        from openscrub_internal import reports
        monkeypatch.setattr(reports.os, 'replace', fail)
    with pytest.raises(OSError, match='synthetic'):
        openscrub.run_pipeline(render_args(review), Quiet())
    assert review.path.read_bytes() == previous
    assert not list(review.path.parent.glob('*.tmp'))


def test_public_loader_keeps_enabled_only_contract_and_legacy_error(review):
    detections, state, provenance = openscrub.load_report(review.path)
    assert [d.text for d in detections] == ['synthetic-01', 'synthetic-02',
        'synthetic-03', 'synthetic-05', 'synthetic-06', 'synthetic-07', 'synthetic-09']
    assert state == review.doc['render_state']
    assert provenance == review.doc['provenance']
    assert detections[1].track == 102
    assert detections[1].person == 202
    assert detections[2].poly == ([[0, 0], [1, 0], [.5, 1]],)
    legacy = review.path.with_name('legacy.json')
    legacy.write_text(json.dumps(review.doc['detections']), encoding='utf-8')
    old_bytes = legacy.read_bytes()
    legacy_detections, legacy_state, legacy_prov = openscrub.load_report(legacy)
    assert [d.text for d in legacy_detections] == [d.text for d in detections]
    assert legacy_state is None
    assert legacy_prov == {}
    with pytest.raises(RuntimeError, match='no render_state.*re-run a scan'):
        openscrub.run_pipeline(render_args(review, source=legacy,
                                           destination=legacy), Quiet())
    assert legacy.read_bytes() == old_bytes
