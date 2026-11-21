"""Scan pre-renders one thumbnail per Review card, chosen like the page does."""
import json

import openscrub_web as web

from test_exact_samples import exact  # noqa: F401
from test_job_lifecycle import store  # noqa: F401


def _card_rows_fixture():
    row = lambda t, conf, track=-1, person=-1, cat='plate', zone=False: dict(
        category=cat, text='r', t_start=t, t_end=t + .1, confidence=conf,
        track=track, person=person, zone_dropped=zone, enabled=True)
    return [row(.3, .5, track=1), row(.2, .9, track=1), row(.1, .9, track=1),
            row(.4, .7, person=0, cat='face'), row(.5, .8, person=0, cat='face'),
            row(.6, .4), row(.7, .9, track=1, zone=True), row(.05, .6, track=1, cat='face')]


def test_review_card_rows_pick_one_representative_per_card():
    # track 1 plate: equal .9 confidence -> earliest (row 2); face person 0 -> row 4;
    # the ungrouped and zone-dropped rows are cards; same track in another category is too.
    assert web._review_card_rows(_card_rows_fixture()) == [7, 2, 4, 5, 6]


def test_review_card_rows_match_the_page_card_builder(tmp_path):
    import re
    import shutil
    import subprocess
    import pytest
    node = shutil.which('node')
    if node is None:
        pytest.skip('node unavailable')
    page = web.PAGE
    pieces = [re.search(r'\nfunction %s\(.*?\n}\n' % name, page, re.S).group(0)
              for name in ('reviewGroupKey', 'reviewDescriptors')]
    rows = [dict(r, i=i) for i, r in enumerate(_card_rows_fixture())]
    script = tmp_path / 'cards.js'
    script.write_text('let TRKMEM={},ROWCARD={};const EN={},EDITS={enabled:{}};\n' + ''.join(pieces) +
                      '\nconst ids=reviewDescriptors(%s).flatMap(s=>s.cards.map(c=>c.id));'
                      'console.log(JSON.stringify(ids));' % json.dumps(rows))
    ids = json.loads(subprocess.run([node, str(script)], capture_output=True, text=True, check=True).stdout)
    assert sorted(ids) == sorted(web._review_card_rows(_card_rows_fixture()))


def test_scan_pregenerates_only_card_thumbnails(exact, monkeypatch):
    import cv2
    import numpy as np
    import openscrub
    from test_report_transactions import join
    writer = cv2.VideoWriter(exact.job['video'], cv2.VideoWriter_fourcc(*'MJPG'), 5, (160, 120))
    for _ in range(10):
        frame = np.zeros((120, 160, 3), np.uint8)
        frame[:, ::4] = (20, 180, 230)  # textured: blank crops are refused
        writer.write(frame)
    writer.release()
    doc = json.loads(exact.path.read_text())
    base = doc['detections'][0]
    doc['detections'] = [dict(base, **{k: v for k, v in r.items() if k != 't_end'},
                              t_end=min(r['t_end'], 1.9), cbox=[55, 45, 105, 75])
                         for r in _card_rows_fixture()]
    monkeypatch.setattr(openscrub, 'run_scan', lambda args, cb: dict(source_report=doc, stats={}))
    threads = []
    real = web._start_owned_thread
    monkeypatch.setattr(web, '_start_owned_thread', lambda *a: threads.append(real(*a)) or threads[-1])
    web._run_job(exact.job, 'scan')
    assert len(threads) == 1
    join(threads[0])
    state = web.FILES.initialize(exact.job).thumbnail
    assert {index for kind, index in state.entries if kind == 'crop'} == {7, 2, 4, 5, 6}
    assert any('thumbnails ready (5)' in line for line in exact.job['log'].snapshot()['lines'])
