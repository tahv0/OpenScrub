"""Stored scan pixels stay small and retain exact source-space geometry."""
import importlib
import json
import sqlite3
from types import SimpleNamespace

import cv2
import numpy as np
import pytest


@pytest.fixture
def previews():
    assert importlib.util.find_spec('finding_previews'), 'compact preview module is missing'
    return importlib.import_module('finding_previews')


def row(frame=3, box=(100, 90, 220, 140), **kwargs):
    return dict(t_start=frame / 10, t_end=frame / 10, last_seen=frame / 10,
                frame_index=frame, cbox=list(box), category='plate', text='plate',
                aoff=[20, 10], track=-1, **kwargs)


def state():
    return {'fps': 10., 'cum': [[20, 10]] * 80}


def frame():
    pixels = np.zeros((900, 1600, 3), np.uint8)
    pixels[:] = (55, 105, 155)
    return pixels


def test_capture_maps_source_geometry_and_uses_unpainted_pixels(previews, tmp_path, monkeypatch):
    monkeypatch.setattr(cv2, 'VideoCapture', lambda *_: pytest.fail('must never decode video'))
    pixels = frame()
    original = pixels.copy()
    stats = previews.capture(tmp_path, pixels, 3, 10., [SimpleNamespace(**row())],
                             source={'video_hash': 'source-identity'})
    assert stats['added'] == 1
    meta, jpeg = previews.lookup(tmp_path, row(), state())
    decoded = cv2.imdecode(np.frombuffer(jpeg, np.uint8), cv2.IMREAD_COLOR)
    assert np.array_equal(pixels, original)
    assert max(decoded.shape[:2]) <= 640
    assert np.max(np.abs(decoded.astype(float) - [55, 105, 155])) < 5
    assert meta['width'] == 1600 and meta['height'] == 900
    assert meta['box'] == [120., 100., 240., 150.]
    assert meta['frame'] == 3 and meta['t'] == .3
    assert meta['source']['video_hash'] == 'source-identity'
    x1, y1, x2, y2 = meta['crop']
    assert x1 <= 120 and x2 >= 240 and y1 <= 100 and y2 >= 150
    assert meta['image_width'] == decoded.shape[1]
    assert meta['scale_x'] == pytest.approx(decoded.shape[1] / (x2-x1))
    assert meta['scale_y'] == pytest.approx(decoded.shape[0] / (y2-y1))
    assert meta['points'] == [[120., 100.], [240., 100.], [240., 150.], [120., 150.]]


def test_track_is_saved_once_and_cross_frame_is_explicit(previews, tmp_path):
    a = row(); a['track'] = 12
    previews.capture(tmp_path, frame(), 3, 10., [a, a])
    b = row(frame=4, box=(101, 91, 221, 141)); b['track'] = 12
    stats = previews.capture(tmp_path, frame(), 4, 10., [b])
    assert stats['added'] == 0 and previews.pending(tmp_path)['total'] == 1
    assert previews.lookup(tmp_path, b, state()) is None
    meta, _ = previews.lookup(tmp_path, b, state(), allow_representative=True)
    assert meta['frame'] == 3 and meta['requested_frame'] == 4
    assert meta['match'] == 'representative'
    assert meta['box'] == [120., 100., 240., 150.]


def test_stale_geometry_or_timeline_is_a_miss(previews, tmp_path):
    previews.capture(tmp_path, frame(), 3, 10., [row()])
    changed = row(box=(101, 90, 220, 140))
    assert previews.lookup(tmp_path, changed, state()) is None
    moved = state(); moved['cum'][3] = [22, 10]
    assert previews.lookup(tmp_path, row(), moved) is None
    retimed = state(); retimed['fps'] = 20
    assert previews.lookup(tmp_path, row(), retimed) is None


def test_geometry_edit_reuses_pixels_only_while_fitting_source_crop(previews, tmp_path):
    previews.capture(tmp_path, frame(), 3, 10., [row()])
    before, jpeg = previews.lookup(tmp_path, row(), state())
    edited = row(); edited['plate_quad'] = [[.1,.1], [.9,.1], [.9,.9], [.1,.9]]
    after, again = previews.lookup(tmp_path, edited, state())
    assert again == jpeg and after['points'][0] == [132., 105.]
    assert after['preview_token'] != before['preview_token']
    edited['plate_quad'][0] = [-10, -10]
    assert previews.lookup(tmp_path, edited, state()) is None


def test_cache_is_bounded_and_reports_truncation(previews, tmp_path, monkeypatch):
    monkeypatch.setattr(previews, 'MAX_ITEMS', 2)
    for i in range(4):
        candidate = row(frame=i); candidate['track'] = i
        stats = previews.capture(tmp_path, frame(), i, 10., [candidate])
    queue = previews.pending(tmp_path, limit=1)
    assert queue['total'] == 2 and len(queue['items']) == 1
    assert queue['truncated'] is True and stats['truncated'] is True
    assert previews.pending(tmp_path, offset=2)['items'] == []
    assert len(previews.pending(tmp_path, offset=1)['items']) == 1


def test_byte_budget_includes_metadata_and_never_acknowledges_a_save(previews, tmp_path, monkeypatch):
    monkeypatch.setattr(previews, 'MAX_BYTES', 50)
    stats = previews.capture(tmp_path, frame(), 3, 10., [row()])
    assert stats['added'] == 0 and stats['truncated']
    assert previews.pending(tmp_path)['total'] == 0


def test_untracked_nearby_objects_are_sampled_without_frame_mismatch(previews, tmp_path):
    previews.capture(tmp_path, frame(), 3, 10., [row()])
    b = row(frame=4, box=(101, 90, 221, 140))
    previews.capture(tmp_path, frame(), 4, 10., [b])
    assert previews.pending(tmp_path)['total'] == 1
    assert previews.lookup(tmp_path, b, state()) is None


def test_cache_survives_reload_and_does_not_touch_source(previews, tmp_path, monkeypatch):
    previews.capture(tmp_path, frame(), 3, 10., [row()])
    key = previews.pending(tmp_path)['items'][0]['key']
    importlib.reload(previews)
    monkeypatch.setattr(cv2, 'VideoCapture', lambda *_: pytest.fail('must never decode video'))
    meta, jpeg = previews.image(tmp_path, key)
    assert jpeg.startswith(b'\xff\xd8') and meta['frame'] == 3
    assert previews.lookup(tmp_path, row(), state())[1] == jpeg


def test_keys_and_cache_symlinks_are_confined(previews, tmp_path):
    assert previews.image(tmp_path, '../../outside') is None
    assert previews.image(tmp_path, '0'*64) is None
    outside = tmp_path / 'outside'; outside.mkdir()
    (tmp_path / 'compact_previews').symlink_to(outside, target_is_directory=True)
    with pytest.raises(ValueError, match='symlink|confined'):
        previews.capture(tmp_path, frame(), 3, 10., [row()])
    assert list(outside.iterdir()) == []


def test_legacy_crop_storage_retains_explicit_transform(previews, tmp_path, monkeypatch):
    monkeypatch.setattr(cv2, 'VideoCapture', lambda *_: pytest.fail('must never decode video'))
    meta = dict(width=1600, height=900, frame=3, t=.3,
                box=[120.,100.,240.,150.], crop=[50,50,850,450])
    saved, jpeg = previews.store(tmp_path, row(), state(), meta,
                                  np.full((400,800,3), 90, np.uint8))
    assert saved['image_width'] == 640 and saved['image_height'] == 320
    assert saved['scale_x'] == .8 and saved['scale_y'] == .8
    assert previews.lookup(tmp_path, row(), state())[1] == jpeg


def test_invalid_frames_and_missing_cache_are_honest(previews, tmp_path):
    assert previews.pending(tmp_path) == {'items': [], 'total': 0, 'truncated': False}
    assert previews.lookup(tmp_path, row(), state()) is None
    with pytest.raises(ValueError):
        previews.capture(tmp_path, frame(), 3, 0, [row()])
    bad = row(box=(0, 0, 0, 0))
    stats = previews.capture(tmp_path, frame(), 3, 10., [bad])
    assert stats['added'] == 0 and stats['invalid'] == 1


def test_scan_hook_supplies_each_actual_source_frame_before_painting(tmp_path, monkeypatch):
    import openscrub
    source = tmp_path / 'scan.mp4'
    writer = cv2.VideoWriter(str(source), cv2.VideoWriter_fourcc(*'mp4v'), 8., (160, 90))
    assert writer.isOpened()
    for _ in range(16):
        writer.write(np.full((90, 160, 3), 70, np.uint8))
    writer.release()

    class QR:
        def __init__(self, *args):
            pass
        def find(self, pixels, scale):
            return [(20, 20, 50, 40, .8)]

    class Callback(openscrub.Callbacks):
        wants_frames = True
        wants_finding_previews = True
        def __init__(self):
            self.source_frames = []
            self.painted_frames = []
            self.events = []
        def log(self, message):
            pass
        def scan_findings(self, pixels, frame_index, fps, detections):
            self.events.append(('source', frame_index))
            self.source_frames.append((pixels.copy(), frame_index, fps, list(detections)))
        def scan_frame(self, pixels, t, found):
            self.events.append(('painted', round(t*8)))
            self.painted_frames.append(pixels.copy())

    monkeypatch.setattr(openscrub, 'QRDetector', QR)
    parser = openscrub.build_parser()
    args = openscrub._prep_args(parser.parse_args([
        str(source), '--categories', 'qrcode', '--no-backtrack',
        '--scroll-track', 'off', '--dense-face-stride', '1']), parser)
    callback = Callback()
    openscrub.run_scan(args, callback)
    assert [entry[1] for entry in callback.source_frames] == list(range(16))
    for pixels, index, fps, rows in callback.source_frames:
        assert fps == 8. and len(rows) == 1
        assert rows[0].t_start == index/fps
        assert tuple(rows[0].cbox) == (20, 20, 50, 40)
        assert abs(int(pixels[20,20,2]) - int(pixels[20,20,0])) < 8
    assert callback.painted_frames
    for pos, (kind, index) in enumerate(callback.events):
        if kind == 'painted':
            assert ('source', index) in callback.events[:pos]
    assert any(int(pixels[20,20,2]) > int(pixels[20,20,0])+100
               for pixels in callback.painted_frames)


def test_per_frame_sampling_limit_is_visible(previews, tmp_path, monkeypatch):
    monkeypatch.setattr(previews, 'MAX_PER_CAPTURE', 2)
    rows = []
    for i in range(5):
        candidate = row(box=(100+i*20,90,220+i*20,140)); candidate['track'] = i
        rows.append(candidate)
    stats = previews.capture(tmp_path, frame(), 3, 10., rows)
    assert stats['added'] == 2 and stats['skipped'] == 3 and stats['truncated']
    assert previews.pending(tmp_path)['truncated']


def test_huge_source_crop_is_downscaled_with_separate_axis_factors(previews, tmp_path):
    candidate = row(box=(100, 100, 1400, 700))
    previews.capture(tmp_path, frame(), 3, 10., [candidate])
    meta, jpeg = previews.lookup(tmp_path, candidate, state())
    pixels = cv2.imdecode(np.frombuffer(jpeg, np.uint8), cv2.IMREAD_COLOR)
    assert max(pixels.shape[:2]) == 640
    for source_x, source_y in meta['points']:
        image_x = (source_x-meta['crop'][0])*meta['scale_x']
        image_y = (source_y-meta['crop'][1])*meta['scale_y']
        assert source_x == pytest.approx(image_x/meta['scale_x']+meta['crop'][0])
        assert source_y == pytest.approx(image_y/meta['scale_y']+meta['crop'][1])


def test_store_does_not_acknowledge_incompatible_existing_crop(previews, tmp_path):
    previews.capture(tmp_path, frame(), 3, 10., [row()])
    edited = row(); edited['plate_quad'] = [[-1,-1], [2,-1], [2,2], [-1,2]]
    assert previews.lookup(tmp_path, edited, state()) is None
    meta = dict(width=1600, height=900, frame=3, t=.3,
                box=[120.,100.,240.,150.], crop=[0,0,500,400])
    with pytest.raises(ValueError, match='incompatible'):
        previews.store(tmp_path, edited, state(), meta, np.zeros((400,500,3), np.uint8))


def test_saturated_cache_does_not_keep_writing_every_frame(previews, tmp_path, monkeypatch):
    monkeypatch.setattr(previews, 'MAX_ITEMS', 1)
    first = row(); first['track'] = 1
    previews.capture(tmp_path, frame(), 3, 10., [first])
    second = row(frame=4, box=(110,90,230,140)); second['track'] = 2
    previews.capture(tmp_path, frame(), 4, 10., [second])
    database = tmp_path / 'compact_previews' / 'index.sqlite3'
    published = database.read_bytes()
    third = row(frame=5, box=(120,90,240,140)); third['track'] = 3
    previews.capture(tmp_path, frame(), 5, 10., [third])
    assert database.read_bytes() == published, 'full cache rewrote SQLite for every later frame'


def test_explicit_store_evicts_oldest_preview_and_keeps_exact_pixels(previews, tmp_path, monkeypatch):
    monkeypatch.setattr(previews, 'MAX_ITEMS', 2)
    monkeypatch.setattr(previews, 'MAX_BYTES', 64 * 1024)
    monkeypatch.setattr(cv2, 'VideoCapture', lambda *_: pytest.fail('must never decode video'))
    for index in (0, 1):
        candidate = row(frame=index); candidate['track'] = index
        previews.capture(tmp_path, frame(), index, 10., [candidate])
    oldest, _ = previews.lookup(tmp_path, row(frame=0), state())
    retained = previews.lookup(tmp_path, row(frame=1), state())
    candidate = row(frame=2); candidate['track'] = 2
    assert previews.capture(tmp_path, frame(), 2, 10., [candidate])['added'] == 0

    meta = dict(width=1600, height=900, frame=4, crop=[80, 60, 400, 240])
    pixels = np.empty((180, 320, 3), np.uint8)
    pixels[:] = (180, 80, 20)
    saved, jpeg = previews.store(tmp_path, row(frame=4), state(), meta, pixels)
    queue = previews.pending(tmp_path)
    assert queue['total'] == 2 and queue['truncated']
    assert [item['frame'] for item in queue['items']] == [1, 4]
    assert previews.image(tmp_path, oldest['key']) is None
    assert previews.lookup(tmp_path, row(frame=0), state()) is None
    assert previews.lookup(tmp_path, row(frame=1), state()) == retained
    assert previews.image(tmp_path, saved['key']) == (saved, jpeg)
    exact, cached_jpeg = previews.lookup(tmp_path, row(frame=4), state())
    assert exact['match'] == 'exact' and exact['frame'] == exact['requested_frame'] == 4
    assert exact['box'] == [120., 100., 240., 150.]
    assert exact['points'] == [[120., 100.], [240., 100.], [240., 150.], [120., 150.]]
    assert exact['crop'] == [80, 60, 400, 240]
    assert exact['scale_x'] == exact['scale_y'] == 1.
    assert cached_jpeg == jpeg
    decoded = cv2.imdecode(np.frombuffer(jpeg, np.uint8), cv2.IMREAD_COLOR)
    assert decoded.shape == (180, 320, 3)
    assert np.max(np.abs(decoded.astype(float) - [180, 80, 20])) < 5

    database = tmp_path / 'compact_previews' / 'index.sqlite3'
    published = database.read_bytes()
    candidate = row(frame=5); candidate['track'] = 5
    assert previews.capture(tmp_path, frame(), 5, 10., [candidate])['added'] == 0
    assert database.read_bytes() == published
    monkeypatch.setattr(cv2, 'imencode', lambda *_: pytest.fail('warm reads must not encode'))
    assert previews.store(tmp_path, row(frame=4), state(), meta, pixels)[1] == jpeg
    assert database.read_bytes() == published
    assert database.stat().st_size <= previews.MAX_BYTES


def test_explicit_store_reclaims_space_after_sqlite_page_limit(previews, tmp_path, monkeypatch):
    monkeypatch.setattr(previews, 'MAX_BYTES', 64 * 1024)
    monkeypatch.setattr(previews, 'MAX_ITEMS', 50)
    monkeypatch.setattr(cv2, 'VideoCapture', lambda *_: pytest.fail('must never decode video'))
    pixels = np.random.default_rng(1234).integers(0, 256, (192, 192, 3), dtype=np.uint8)
    meta = dict(width=1600, height=900, frame=3, crop=[80, 60, 272, 252])
    first, jpeg = previews.store(tmp_path, row(), state(), meta, pixels)
    # Two such payloads fit the logical budget; SQLite's tables and indexes
    # exhaust its page ceiling before that budget is reached.
    assert 2 * (len(jpeg) + len(json.dumps(first).encode())) < previews.MAX_BYTES
    database = tmp_path / 'compact_previews' / 'index.sqlite3'
    for index in range(4, 10):
        saved, latest_jpeg = previews.store(tmp_path, row(frame=index), state(),
                                          dict(meta, frame=index), pixels)
        exact, cached_jpeg = previews.lookup(tmp_path, row(frame=index), state())
        assert exact['frame'] == exact['requested_frame'] == index
        assert exact['box'] == [120., 100., 240., 150.]
        assert exact['crop'] == [80, 60, 272, 252]
        assert cached_jpeg == latest_jpeg == jpeg
        assert previews.image(tmp_path, saved['key'])[1] == latest_jpeg
        assert database.stat().st_size <= previews.MAX_BYTES
        with sqlite3.connect(database) as db:
            assert db.execute('PRAGMA integrity_check').fetchone() == ('ok',)
            assert db.execute('SELECT count(*) FROM previews').fetchone()[0] <= previews.MAX_ITEMS
    assert previews.image(tmp_path, first['key']) is None
    assert previews.pending(tmp_path)['truncated']


@pytest.mark.parametrize('side', [320, 640])
def test_unstorable_explicit_preview_keeps_existing_cache(previews, tmp_path, monkeypatch, side):
    monkeypatch.setattr(previews, 'MAX_BYTES', 64 * 1024)
    monkeypatch.setattr(previews, 'MAX_ITEMS', 1)
    previews.capture(tmp_path, frame(), 3, 10., [row()])
    original = previews.lookup(tmp_path, row(), state())
    pixels = np.random.default_rng(1234).integers(0, 256, (side, side, 3), dtype=np.uint8)
    meta = dict(width=1600, height=900, frame=4, crop=[0, 0, side, side])
    with pytest.raises(previews.PreviewLimitError):
        previews.store(tmp_path, row(frame=4), state(), meta, pixels)
    assert previews.lookup(tmp_path, row(), state()) == original
    assert previews.lookup(tmp_path, row(frame=4), state()) is None
    assert previews.pending(tmp_path)['total'] == 1
    assert (tmp_path / 'compact_previews' / 'index.sqlite3').stat().st_size <= previews.MAX_BYTES


@pytest.mark.parametrize('suffix', ['', '-journal', '-wal', '-shm'])
def test_explicit_store_rejects_database_symlinks_before_eviction(previews, tmp_path, monkeypatch, suffix):
    monkeypatch.setattr(previews, 'MAX_ITEMS', 1)
    previews.capture(tmp_path, frame(), 3, 10., [row()])
    outside = tmp_path / 'outside'
    outside.write_bytes(b'outside data must not change')
    path = tmp_path / 'compact_previews' / ('index.sqlite3' + suffix)
    if not suffix:
        path.rename(tmp_path / 'original.sqlite3')
    path.symlink_to(outside)
    meta = dict(width=1600, height=900, frame=4, crop=[80, 60, 400, 240])
    with pytest.raises(ValueError, match='symlink|confined'):
        previews.store(tmp_path, row(frame=4), state(), meta, np.zeros((180, 320, 3), np.uint8))
    assert outside.read_bytes() == b'outside data must not change'


def test_reconcile_links_scan_picture_to_final_track_representative(previews, tmp_path):
    raw = row(frame=3)
    raw['track'] = -1
    assert previews.capture(tmp_path, frame(), 3, 10., [raw])['added'] == 1

    synthetic = row(frame=2)
    synthetic['track'] = 7
    real = row(frame=3)
    real['track'] = 7
    stats = previews.reconcile(tmp_path, [synthetic, real], state())
    assert stats['linked'] == 1

    assert previews.lookup(tmp_path, synthetic, state()) is None
    meta, jpeg = previews.lookup(tmp_path, synthetic, state(), allow_representative=True)
    assert jpeg.startswith(b'\xff\xd8')
    assert meta['match'] == 'representative'
    assert meta['frame'] == 3
    assert meta['requested_frame'] == 2
    assert meta['track'] == 7


def test_reconcile_matches_scan_picture_inside_final_track_interval(previews, tmp_path):
    # The saved detector sighting is at frame 3. Dense tracking extends the
    # final row to frame 6; last_seen is now 6, not the cached frame.
    raw = row(frame=3)
    raw['track'] = -1
    assert previews.capture(tmp_path, frame(), 3, 10., [raw])['added'] == 1
    final = row(frame=6)
    final.update(track=71, frame_index=-1, t_start=.2,
                 t_end=.6, last_seen=.6)
    stats = previews.reconcile(tmp_path, [final], state())
    assert stats['linked'] == 1
    result = previews.lookup(tmp_path, final, state(), allow_representative=True)
    assert result is not None
    meta, jpeg = result
    assert jpeg[:2] == bytes([0xff, 0xd8])
    assert meta['frame'] == 3 and meta['requested_frame'] == 6
    assert meta['track'] == 71 and meta['match'] == 'representative'


def test_reconcile_rejects_two_indistinguishable_tracks(previews, tmp_path):
    raw = row(frame=3)
    raw['track'] = -1
    previews.capture(tmp_path, frame(), 3, 10., [raw])
    a = dict(row(frame=3), track=17)
    b = dict(row(frame=3), track=18)
    stats = previews.reconcile(tmp_path, [a, b], state())
    assert stats['linked'] == 0 and stats['ambiguous'] == 1
    # Exact-frame pixels remain valid without assigning either ambiguous track.
    exact = previews.lookup(tmp_path, a, state(), allow_representative=True)
    assert exact is not None
    assert exact[0]['match'] == 'exact' and exact[0]['track'] == -1
    next_frame = dict(a, frame_index=4, t_start=.4, t_end=.4, last_seen=.4)
    assert previews.lookup(tmp_path, next_frame, state(),
                           allow_representative=True) is None


def test_reconcile_does_not_use_nearby_but_out_of_interval_preview(previews, tmp_path):
    raw = row(frame=3)
    raw['track'] = -1
    previews.capture(tmp_path, frame(), 3, 10., [raw])
    later = dict(row(frame=8), track=33, frame_index=-1,
                 t_start=.7, t_end=.9, last_seen=.8)
    assert previews.reconcile(tmp_path, [later], state())['linked'] == 0
    assert previews.lookup(tmp_path, later, state(), allow_representative=True) is None


def test_reconcile_refuses_source_timeline_offset_changes(previews, tmp_path):
    raw = row(frame=3)
    raw['track'] = -1
    previews.capture(tmp_path, frame(), 3, 10., [raw])
    timeline = state()
    timeline['cum'][3] = [999, 888]
    final = dict(row(frame=3), track=42)
    assert previews.reconcile(tmp_path, [final], timeline)['linked'] == 0


def test_repeated_scan_group_does_no_sqlite_work_after_first_capture(previews, tmp_path, monkeypatch):
    seen = set()
    first = previews.capture(tmp_path, frame(), 3, 10., [row()],
                             seen_groups=seen)
    assert first['added'] == 1 and seen

    # Same physical untracked region in the same ten-second bucket should be
    # rejected by the in-process scan set before SQLite is even opened.
    again = row(frame=4, box=(100, 90, 220, 140))
    monkeypatch.setattr(previews, '_db',
        lambda *a, **k: pytest.fail('duplicate scan group reopened SQLite'))
    stats = previews.capture(tmp_path, frame(), 4, 10., [again],
                             seen_groups=seen, previous_stats=first)
    assert stats['duplicates'] == 1
    assert stats['total'] == first['total']
    assert stats['bytes'] == first['bytes']


def test_preview_totals_are_incremental_not_full_table_aggregates(previews, tmp_path):
    seen = set()
    stats = None
    for i in range(20):
        candidate = row(frame=i, box=(100 + i*40, 90, 220 + i*40, 140))
        candidate['track'] = i
        stats = previews.capture(tmp_path, frame(), i, 10., [candidate],
                                 seen_groups=seen, previous_stats=stats)
    assert stats['total'] == 20

    db = previews._db(tmp_path)
    statements = []
    db.set_trace_callback(statements.append)
    try:
        count, size, _ = previews._totals(db)
    finally:
        db.close()
    assert count == 20 and size > 0
    sql = '\n'.join(statements).lower()
    assert 'count(*)' not in sql and 'sum(' not in sql, (
        'hot-path totals must come from O(1) counters, not rescan every JPEG row')


def test_large_same_frame_lookup_fetches_only_selected_jpeg(previews, tmp_path, monkeypatch):
    # Real long videos can have dozens of distinct proposals on one frame.
    # Do not read every image blob merely to find the matching geometry.
    boxes = [(100 + i * 80, 90, 220 + i * 80, 140) for i in range(10)]
    candidates = [row(frame=3, box=box) for box in boxes]
    saved = previews.capture(tmp_path, frame(), 3, 10., candidates)
    assert saved['added'] == len(candidates)
    original_db = previews._db
    queries = []
    class CheckedConnection:
        def __init__(self, connection):
            self.connection = connection
        def execute(self, sql, params=()):
            queries.append(sql)
            assert 'metadata,jpeg' not in sql.lower(), 'Fetched all image blobs before matching'
            return self.connection.execute(sql, params)
        def close(self):
            self.connection.close()
    def checked_db(*args, **kwargs):
        connection = original_db(*args, **kwargs)
        return CheckedConnection(connection) if connection is not None else None
    monkeypatch.setattr(previews, '_db', checked_db)
    result = previews.lookup(tmp_path, candidates[8], state())
    assert result is not None and result[0]['match'] == 'exact'
    assert result[1][:2] == bytes([0xff,0xd8])
    assert sum('select jpeg' in q.lower() for q in queries) == 1


def test_untracked_representative_lookup_limits_sql_to_real_time_window(previews, tmp_path, monkeypatch):
    first = row(frame=3)
    first['track'] = -1
    previews.capture(tmp_path, frame(), 3, 10., [first])
    unrelated = dict(row(frame=60), track=-1)
    previews.capture(tmp_path, frame(), 60, 10., [unrelated])
    target = dict(row(frame=4), track=-1, frame_index=-1,
                  t_start=.25, t_end=.65, last_seen=.4)
    original_db = previews._db
    queries = []
    class CheckedConnection:
        def __init__(self, connection):
            self.connection = connection
        def execute(self, sql, params=()):
            queries.append((sql,params))
            return self.connection.execute(sql,params)
        def close(self):
            self.connection.close()
    monkeypatch.setattr(previews, '_db', lambda *args, **kwargs:
                        CheckedConnection(original_db(*args,**kwargs)))
    result = previews.lookup(tmp_path, target, state(), allow_representative=True)
    assert result is not None and result[0]['frame'] == 3
    assert any('frame BETWEEN ? AND ?' in sql for sql,_ in queries)
