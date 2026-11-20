import os

import cv2
import numpy as np
import pytest

from openscrub_internal import thumbnails as th


def test_ordinal_requires_seek_and_verified_positions():
    class Capture:
        def __init__(self): self.pos = 0
        def isOpened(self): return True
        def set(self, prop, value): self.pos = value; return True
        def get(self, prop): return self.pos
        def read(self): self.pos += 1; return True, np.zeros((2, 2, 3), np.uint8)
    cap = Capture()
    assert th.read_ordinal_capture(cap, 2, count=3).shape == (2, 2, 3)
    for index, count in [(True, 3), (0, False), (3, 3), (-1, 3)]:
        with pytest.raises(th.ThumbnailDecodeError):
            th.read_ordinal_capture(cap, index, count=count)


def test_recipe_uses_clamped_same_ordinal_and_raw_row():
    row = {'t_start': 0., 't_end': 3., 'last_seen': 9., 'cbox': [1, 2, 4, 5], 'enabled': True, 'opaque': {'x': [1, None]}}
    rs = {'fps': 2., 'cum': [[0, 0], [1, 2], [3, 4]]}
    recipe = th.recipe_for_row(row, rs, 'crop')
    assert recipe.indices == (2, 2, 0)
    assert recipe.offsets == ((3., 4.), (3., 4.), (0., 0.))
    assert recipe.jpeg_quality == 80 and recipe.padding == 24
    assert th.recipe_for_row(row, rs, 'detframe').indices == (2,)
    changed = dict(row, opaque={'x': [2, None]})
    assert th.raw_row_fingerprint(row) != th.raw_row_fingerprint(changed)
    assert th.raw_row_fingerprint(row) == th.raw_row_fingerprint(dict(reversed(list(row.items()))))


def test_retirement_blocks_new_fill_until_reader_writer_and_paths_clear(tmp_path):
    state = th.ThumbnailState()
    a = th.accept_generation_locked(state, th.Candidate(), 3)
    accepted = th.begin_fill_locked(state, a, 'crop', 0)
    staged = th.stage_jpeg(tmp_path, accepted, b'first')
    entry = th.accept_jpeg_locked(state, accepted, staged)
    th.finish_fill_locked(state, accepted)
    reader_file = open(entry.path, 'rb')
    reader = th.begin_reader_locked(state, a, entry, reader_file)
    old_fill = th.begin_fill_locked(state, a, 'crop', 1)
    th.invalidate_locked(state, 'update')
    b = th.accept_generation_locked(state, th.Candidate(), 3)
    with pytest.raises(th.ThumbnailPending): th.begin_fill_locked(state, b, 'crop', 0)
    th.invalidate_locked(state, 'update')
    c = th.accept_generation_locked(state, th.Candidate(), 3)
    stale = th.stage_jpeg(tmp_path, old_fill, b'stale')
    with pytest.raises(th.ThumbnailObsolete): th.accept_jpeg_locked(state, old_fill, stale)
    th.finish_fill_locked(state, old_fill, stale.path)
    with pytest.raises(ValueError): th.end_reader_locked(state, reader)
    reader_file.close()
    th.end_reader_locked(state, reader)
    batch = th.claim_cleanup_locked(state)
    assert batch and th.claim_cleanup_locked(state) is None
    result = th.cleanup(batch, unlink=lambda path: (_ for _ in ()).throw(PermissionError()))
    th.complete_cleanup_locked(state, batch, result)
    with pytest.raises(th.ThumbnailPending): th.begin_fill_locked(state, c, 'crop', 0)
    batch = th.claim_cleanup_locked(state)
    result = th.cleanup(batch)
    th.complete_cleanup_locked(state, batch, result)
    assert not list(tmp_path.iterdir())
    assert th.begin_fill_locked(state, c, 'crop', 0)


def test_four_fills_and_per_key_gate():
    state = th.ThumbnailState(); gen = th.accept_generation_locked(state, th.Candidate(), 5)
    tickets = [th.begin_fill_locked(state, gen, 'crop', 0)]
    with pytest.raises(th.ThumbnailPending): th.begin_fill_locked(state, gen, 'crop', 0)
    tickets.extend(th.begin_fill_locked(state, gen, 'crop', i) for i in range(1, 4))
    with pytest.raises(th.ThumbnailPending): th.begin_fill_locked(state, gen, 'crop', 0)
    with pytest.raises(th.ThumbnailPending): th.begin_fill_locked(state, gen, 'crop', 4)
    th.finish_fill_locked(state, tickets[0])
    assert th.begin_fill_locked(state, gen, 'crop', 4)


def test_cleanup_excludes_open_pinned_reader(tmp_path):
    state = th.ThumbnailState(); old = th.accept_generation_locked(state, th.Candidate(), 2)
    entries = []
    for index in range(2):
        fill = th.begin_fill_locked(state, old, 'crop', index)
        entries.append(th.accept_jpeg_locked(state, fill, th.stage_jpeg(tmp_path, fill, b'jpeg')))
        th.finish_fill_locked(state, fill)
    with open(entries[0].path, 'rb') as opened:
        reader = th.begin_reader_locked(state, old, entries[0], opened)
        th.invalidate_locked(state, 'update')
        current = th.accept_generation_locked(state, th.Candidate(), 1)
        batch = th.claim_cleanup_locked(state)
        assert set(batch.paths) == {entries[1].path}
        th.complete_cleanup_locked(state, batch, th.cleanup(batch))
        assert os.path.exists(entries[0].path) and opened.read() == b'jpeg'
        with pytest.raises(th.ThumbnailPending): th.begin_fill_locked(state, current, 'crop', 0)
    th.end_reader_locked(state, reader)
    batch = th.claim_cleanup_locked(state)
    th.complete_cleanup_locked(state, batch, th.cleanup(batch))
    assert not list(tmp_path.iterdir())
    fill = th.begin_fill_locked(state, current, 'crop', 0)
    th.finish_fill_locked(state, fill)


@pytest.mark.parametrize('mutation', ['closed', 'false_set', 'ignored_set', 'pre_nan', 'post_nan', 'post_wrong', 'read_false', 'empty'])
def test_ordinal_mutations_are_unavailable(mutation):
    class Capture:
        def __init__(self): self.pos = 0; self.reads = 0
        def isOpened(self): return mutation != 'closed'
        def set(self, prop, value):
            if mutation != 'ignored_set': self.pos = value
            return mutation != 'false_set'
        def get(self, prop):
            if mutation == 'pre_nan' and self.reads == 0 or mutation == 'post_nan' and self.reads: return float('nan')
            if mutation == 'post_wrong' and self.reads: return self.pos + 1
            return self.pos
        def read(self):
            self.reads += 1; self.pos += 1
            if mutation == 'read_false': return False, None
            if mutation == 'empty': return True, np.empty((0, 0, 3), np.uint8)
            return True, np.ones((3, 3, 3), np.uint8)
    cap = Capture()
    with pytest.raises(th.ThumbnailDecodeError): th.read_ordinal_capture(cap, 2, count=3)
    assert cap.reads <= 1


def test_real_cfr_ordinal_matches_sequential_oracle(tmp_path):
    path = str(tmp_path / 'tiny.avi')
    writer = cv2.VideoWriter(path, cv2.VideoWriter_fourcc(*'MJPG'), 5., (32, 24))
    assert writer.isOpened()
    for n in range(4):
        frame = np.zeros((24, 32, 3), np.uint8)
        frame[:] = (n * 50, 10 + n * 30, 220 - n * 40)
        frame[4:12, 4:12] = (200, n * 40, 50)
        writer.write(frame)
    writer.release()
    sequential = cv2.VideoCapture(path); frames = []
    while True:
        ok, frame = sequential.read()
        if not ok: break
        frames.append(frame)
    sequential.release()
    assert len(frames) == 4
    seek = cv2.VideoCapture(path)
    try:
        for index in (3, 0, 2, 1):
            assert np.array_equal(th.read_ordinal_capture(seek, index, count=4), frames[index])
    finally: seek.release()


def test_crop_clips_far_outside_and_jpeg_encodes():
    frame = np.zeros((100, 100, 3), np.uint8)
    frame[30:70, 30:70] = (0, 255, 0)
    crop, nonblank = th.crop_frame(frame, (30, 30, 70, 70), (0, 0))
    assert nonblank and crop.shape == (88, 88, 3)
    assert tuple(crop[24, 24]) == (0, 0, 255)
    assert cv2.imdecode(np.frombuffer(th.encode_jpeg(crop, 80), np.uint8), cv2.IMREAD_COLOR) is not None
    assert th.crop_frame(frame, (-1000, -1000, -100, -100), (0, 0)) == (None, False)


def test_failed_stage_retirement_keeps_preexisting_entries(tmp_path):
    state = th.ThumbnailState(); g = th.accept_generation_locked(state, th.Candidate(), 2)
    first = th.begin_fill_locked(state, g, 'crop', 0)
    entry = th.accept_jpeg_locked(state, first, th.stage_jpeg(tmp_path, first, b'one'))
    th.finish_fill_locked(state, first)
    failed = th.begin_fill_locked(state, g, 'crop', 1)
    stage = th.stage_jpeg(tmp_path, failed, b'two')
    th.finish_fill_locked(state, failed, stage.path)
    assert state.current is None
    batch = th.claim_cleanup_locked(state)
    assert set(batch.paths) == {entry.path, stage.path}
    th.complete_cleanup_locked(state, batch, th.cleanup(batch))
    assert not list(tmp_path.iterdir())


def test_stage_cannot_be_accepted_by_another_ticket_or_forgotten(tmp_path):
    state = th.ThumbnailState(); g = th.accept_generation_locked(state, th.Candidate(), 2)
    a = th.begin_fill_locked(state, g, 'crop', 0)
    b = th.begin_fill_locked(state, g, 'crop', 1)
    staged = th.stage_jpeg(tmp_path, a, b'first')
    with pytest.raises(ValueError): th.accept_jpeg_locked(state, b, staged)
    th.finish_fill_locked(state, a)
    assert state.current is None
    th.finish_fill_locked(state, b)
    batch = th.claim_cleanup_locked(state)
    assert staged.path in batch.paths
    th.complete_cleanup_locked(state, batch, th.cleanup(batch))
    assert not list(tmp_path.iterdir())


def test_first_accepted_entry_cannot_be_replaced(tmp_path):
    state = th.ThumbnailState(); g = th.accept_generation_locked(state, th.Candidate(), 1)
    fill = th.begin_fill_locked(state, g, 'crop', 0)
    staged = th.stage_jpeg(tmp_path, fill, b'first')
    entry = th.accept_jpeg_locked(state, fill, staged)
    th.finish_fill_locked(state, fill)
    with pytest.raises(th.ThumbnailPending): th.begin_fill_locked(state, g, 'crop', 0)
    assert open(entry.path, 'rb').read() == b'first'
    assert entry.etag.startswith('"') and entry.etag.endswith('"')
    assert (os.stat(entry.path).st_mode & 0o777) == 0o600


def test_discovery_obsoleted_on_invalidation():
    state = th.ThumbnailState()
    discovery = th.begin_discovery_locked(state)
    with pytest.raises(th.ThumbnailPending): th.begin_discovery_locked(state)
    th.invalidate_locked(state, 'change')
    with pytest.raises(th.ThumbnailObsolete): th.accept_discovery_locked(state, discovery, th.Candidate(), 1)
    newer = th.begin_discovery_locked(state)
    assert th.accept_discovery_locked(state, newer, th.Candidate(), 1) is state.current


def test_failed_stage_write_records_closed_path_and_preserves_exception(tmp_path, monkeypatch):
    state = th.ThumbnailState(); g = th.accept_generation_locked(state, th.Candidate(), 1)
    fill = th.begin_fill_locked(state, g, 'crop', 0)
    error = OSError('injected fsync failure')
    def fail(_fd): raise error
    monkeypatch.setattr(th.os, 'fsync', fail)
    with pytest.raises(OSError) as caught: th.stage_jpeg(tmp_path, fill, b'partial')
    assert caught.value is error
    th.finish_fill_locked(state, fill)
    batch = th.claim_cleanup_locked(state)
    assert len(batch.paths) == 1 and os.path.exists(batch.paths[0])
    th.complete_cleanup_locked(state, batch, th.cleanup(batch))
    assert not list(tmp_path.iterdir())


def test_invalidation_before_stage_creation_keeps_fill_until_finished(tmp_path):
    state = th.ThumbnailState(); old = th.accept_generation_locked(state, th.Candidate(), 1)
    fill = th.begin_fill_locked(state, old, 'crop', 0)
    th.invalidate_locked(state, 'update')
    current = th.accept_generation_locked(state, th.Candidate(), 1)
    with pytest.raises(th.ThumbnailPending): th.begin_fill_locked(state, current, 'crop', 0)
    stage = th.stage_jpeg(tmp_path, fill, b'obsolete')
    with pytest.raises(th.ThumbnailObsolete): th.accept_jpeg_locked(state, fill, stage)
    th.finish_fill_locked(state, fill)
    with pytest.raises(th.ThumbnailPending): th.begin_fill_locked(state, current, 'crop', 0)
    batch = th.claim_cleanup_locked(state)
    th.complete_cleanup_locked(state, batch, th.cleanup(batch))
    assert th.begin_fill_locked(state, current, 'crop', 0)


def test_publication_interrupted_after_in_memory_insert_keeps_stage_owned(tmp_path):
    state = th.ThumbnailState(); g = th.accept_generation_locked(state, th.Candidate(), 1)
    fill = th.begin_fill_locked(state, g, 'crop', 0)
    staged = th.stage_jpeg(tmp_path, fill, b'first')
    error = OSError('injected after entry insertion')
    class InterruptedEntries(dict):
        def __setitem__(self, key, value):
            super().__setitem__(key, value)
            raise error
    state.entries = InterruptedEntries()
    with pytest.raises(OSError) as caught: th.accept_jpeg_locked(state, fill, staged)
    assert caught.value is error and os.path.exists(staged.destination)
    th.finish_fill_locked(state, fill)
    batch = th.claim_cleanup_locked(state)
    assert staged.destination in batch.paths
    th.complete_cleanup_locked(state, batch, th.cleanup(batch))
    assert not list(tmp_path.iterdir())


def test_etag_binds_kind_generation_index_and_bytes(tmp_path):
    state = th.ThumbnailState(); a = th.accept_generation_locked(state, th.Candidate(), 2)
    tickets = [th.begin_fill_locked(state, a, 'crop', 0), th.begin_fill_locked(state, a, 'crop', 1), th.begin_fill_locked(state, a, 'detframe', 0)]
    tags = [th.stage_jpeg(tmp_path, ticket, b'same').etag for ticket in tickets]
    for ticket in tickets: th.finish_fill_locked(state, ticket)
    batch = th.claim_cleanup_locked(state)
    th.complete_cleanup_locked(state, batch, th.cleanup(batch))
    b = th.accept_generation_locked(state, th.Candidate(), 1)
    ticket = th.begin_fill_locked(state, b, 'crop', 0)
    tags.append(th.stage_jpeg(tmp_path, ticket, b'same').etag)
    assert len(set(tags)) == 4


def test_invalidation_transfers_populated_entries_without_traversing():
    class GuardedEntries(dict):
        def values(self): raise AssertionError('invalidation traversed entries')
        def clear(self): raise AssertionError('invalidation destroyed entries')
        def __iter__(self): raise AssertionError('invalidation iterated entries')
    state = th.ThumbnailState()
    th.accept_generation_locked(state, th.Candidate(), 1000)
    entries = GuardedEntries({('crop', i): th.JPEGEntry('crop', i, str(i), None, 1, 'x')
                              for i in range(1000)})
    state.entries = entries
    th.invalidate_locked(state, 'report commit')
    assert state.entries is not entries
    assert state.retirement is not None


def test_populated_retirement_claims_bounded_batches_and_preserves_pin(tmp_path):
    state = th.ThumbnailState()
    generation = th.accept_generation_locked(state, th.Candidate(), 70)
    for index in range(70):
        path = str(tmp_path / ('entry-%d.jpg' % index))
        with open(path, 'wb') as file: file.write(b'x')
        state.entries[('crop', index)] = th.JPEGEntry('crop', index, path, None, 1, 'x')
    first = state.entries[('crop', 0)]
    opened = open(first.path, 'rb')
    reader = th.begin_reader_locked(state, generation, first, opened)
    try:
        th.invalidate_locked(state, 'report commit')
        counts = []
        while True:
            batch = th.claim_cleanup_locked(state)
            if batch is None: break
            counts.append(len(batch.paths))
            assert len(batch.paths) <= 32 and first.path not in batch.paths
            th.complete_cleanup_locked(state, batch, th.cleanup(batch))
        assert sum(counts) == 69 and os.path.exists(first.path)
        assert state.retirement is not None
    finally:
        opened.close()
        th.end_reader_locked(state, reader)
    batch = th.claim_cleanup_locked(state)
    assert batch.paths == (first.path,)
    th.complete_cleanup_locked(state, batch, th.cleanup(batch))
    assert state.retirement is None and not list(tmp_path.iterdir())
