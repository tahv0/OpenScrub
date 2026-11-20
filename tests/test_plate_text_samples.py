"""Sampling coverage must describe completed exact frame reads only."""
from types import SimpleNamespace

import numpy as np
import pytest

from openscrub_internal import exact_samples
from openscrub_internal.plate_search.matching import PlateQuery
from openscrub_internal.plate_search.samples import search_capture


def test_sampled_frames_use_exact_indices_and_describe_gaps(monkeypatch):
    calls = []
    def read(cap, index, **kw):
        calls.append((cap, index, kw))
        return SimpleNamespace(pixels=np.zeros((80,200,3), np.uint8),
                               canonical_s=index/4, index=index)
    monkeypatch.setattr(exact_samples, 'read_indexed_capture', read)
    result = search_capture('capture', (PlateQuery('ABC123'),), [0,4,12],
        fps=4.0, count=16, width=200, height=80, tolerance_s=.01,
        reader=lambda image: [('ABC123', (20,20,100,50), .9)])
    assert [row[1] for row in calls] == [0,4,12]
    assert result.requested_indices == result.completed_indices == (0,4,12)
    assert not result.cancelled
    assert [(frame.index, frame.time_s) for frame in result.frames] == [(0,0.),(4,1.),(12,3.)]
    assert all(len(frame.hits) == 1 for frame in result.frames)
    assert 'ABC123' not in repr(result)


def test_cancel_during_frame_does_not_claim_it_was_searched(monkeypatch):
    reads = []
    def read(cap, index, **kw):
        reads.append(index)
        return SimpleNamespace(pixels=np.zeros((80,2400,3), np.uint8),
                               canonical_s=index/4, index=index)
    monkeypatch.setattr(exact_samples, 'read_indexed_capture', read)
    tiles = []
    def reader(image):
        tiles.append(1)
        return []
    result = search_capture('capture', (PlateQuery('ABC123'),), [0,1],
        fps=4.0, count=16, width=2400, height=80, tolerance_s=.01,
        reader=reader, cancelled=lambda: bool(tiles))
    assert result.cancelled and result.requested_indices == (0,1)
    assert result.completed_indices == () and result.frames == () and reads == [0]


@pytest.mark.parametrize('indices', [[], [0,0], [2,1], [-1], [16], [True], list(range(17))])
def test_invalid_frame_selection_is_rejected_before_decode(indices):
    with pytest.raises(ValueError):
        search_capture(None, (PlateQuery('ABC123'),), indices,
            fps=4., count=16, width=200, height=80, tolerance_s=.01,
            reader=lambda image: [])


def test_invalid_queries_are_rejected_before_frame_or_cancellation(monkeypatch):
    def forbidden(*a, **kw):
        pytest.fail('invalid queries must not decode')
    monkeypatch.setattr(exact_samples, 'read_indexed_capture', forbidden)
    with pytest.raises(ValueError):
        search_capture(None, ['ABC123'], [0], fps=4., count=16,
            width=200, height=80, tolerance_s=.01, reader=lambda image: [],
            cancelled=lambda: False)
    with pytest.raises(ValueError):
        search_capture(None, [], [0], fps=4., count=16,
            width=200, height=80, tolerance_s=.01, reader=lambda image: [],
            cancelled=lambda: True)
