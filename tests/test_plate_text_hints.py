"""Contracts for optional, independent whole-frame plate text discovery."""
import math

import cv2
import numpy as np
import pytest

from openscrub_internal.plate_search.matching import PlateQuery
from openscrub_internal.plate_search.search import search_frame, SearchError


def blank(width=300, height=100):
    return np.zeros((height, width, 3), np.uint8)


def test_full_and_explicit_fragment_find_whole_observation_without_detector():
    frame = blank()
    def reader(image):
        return [('ABC123', (40, 20, 120, 50), .91)]
    result = search_frame(frame, (PlateQuery('ABC123'), PlateQuery('BC1', 'fragment')),
                          reader=reader)
    assert result.complete and result.tiles_completed == result.tiles_total == 1
    assert len(result.hits) == 1
    hit = result.hits[0]
    assert hit.observation.text == 'ABC123'
    assert hit.observation.box == (40, 20, 120, 50)
    assert [m.match_kind for m in hit.matches] == ['full_equal', 'fragment']
    assert hit.suggested_box[0] <= 40 and hit.suggested_box[2] >= 120
    assert hit.suggested_box[1] <= 20 and hit.suggested_box[3] >= 50
    assert hit.boundary == 'unknown'
    assert 'ABC123' not in repr(result) and 'BC1' not in repr(result)
    assert not search_frame(frame, (PlateQuery('BC1'),), reader=reader).hits


def test_tiling_preserves_native_resolution_and_deduplicates_overlap():
    frame = blank(2400, 100)
    frame[25, 1150, 0] = 77
    calls = []
    def reader(image):
        calls.append(image.shape)
        ys, xs = np.where(image[:,:,0] == 77)
        return [('ABC123', (int(xs[0]), 25, int(xs[0])+60, 55), .8)] if len(xs) else []
    result = search_frame(frame, (PlateQuery('ABC123'),), reader=reader)
    assert len(calls) > 1 and all(shape[1] <= 1280 for shape in calls)
    assert all(shape[0] == 100 for shape in calls)
    assert len(result.hits) == 1 and result.hits[0].observation.box == (1150,25,1210,55)


def test_invalid_observations_are_discarded_and_regions_do_not_block_full_frame():
    frame = blank()
    def reader(image):
        if image.shape[1] < 300:
            return []
        return [('ABC123', (-1,0,20,20), .8), ('ABC123', (3,3,9,9), math.nan),
                ('ABC123', (3,3,9,9), 1.1), ('ABC123', (3,3,9,9), True),
                ('ABC123', (3,3,9,9), '0.5'), ('ABC123', (3,3,3,9), .8),
                ('ABC123', (30,20,90,50), .8)]
    result = search_frame(frame, (PlateQuery('ABC123'),), regions=[(150,10,250,60)], reader=reader)
    assert len(result.hits) == 1
    assert result.hits[0].observation.box == (30,20,90,50)
    assert result.hits[0].boundary == 'unknown'


def test_provided_region_is_retained_as_candidate_but_not_a_verified_boundary():
    def reader(image):
        return [('ABC123', (10,10,70,30), .8)] if image.shape[1] == 100 else []
    result = search_frame(blank(), (PlateQuery('ABC123'),),
                          regions=[(100,10,200,60)], reader=reader)
    hit = result.hits[0]
    assert hit.observation.box == (110,20,170,40)
    assert hit.suggested_box == (100,10,200,60)
    assert hit.boundary == 'provided_unverified'


def test_cancellation_and_limits_are_explicit():
    count = []
    def reader(image):
        count.append(1)
        return []
    result = search_frame(blank(2400), (PlateQuery('ABC123'),), reader=reader,
                          cancelled=lambda: bool(count))
    assert not result.complete and result.tiles_completed == 0 and result.tiles_total > 1
    with pytest.raises(ValueError):
        search_frame(np.zeros((9000,9000,3), np.uint8), (PlateQuery('ABC123'),), reader=reader)
    with pytest.raises(ValueError):
        search_frame(blank(), (PlateQuery('ABC123'),), regions=[(-1,0,5,5)], reader=reader)
    with pytest.raises(ValueError):
        search_frame(np.zeros((100,300,3), np.float32), (PlateQuery('ABC123'),), reader=reader)


def test_reader_errors_have_fixed_diagnostic():
    def reader(image):
        raise RuntimeError('sensitive OCR output')
    with pytest.raises(SearchError) as error:
        search_frame(blank(), (PlateQuery('ABC123'),), reader=reader)
    assert str(error.value) == 'OCR reader failed or timed out'
    assert error.value.__cause__ is None


def test_token_limit_reports_truncation():
    def reader(image):
        for _ in range(65):
            yield ('ABC123', (40,20,120,50), .9)
    result = search_frame(blank(), (PlateQuery('ABC123'),), reader=reader)
    assert result.complete and result.truncated and len(result.hits) == 1


def test_absurd_coordinates_are_rejected_without_overflow():
    with pytest.raises(ValueError, match='Invalid source region'):
        search_frame(blank(), (PlateQuery('ABC123'),),
                     regions=[(0,0,10**1000,50)], reader=lambda image: [])


def test_contour_crop_discards_words_clipped_at_crop_edge(monkeypatch):
    from openscrub_internal.plate_search import search
    crop = blank(100,50)
    inverse = np.array([[1.,0.,30.],[0.,1.,10.],[0.,0.,1.]])
    padded = crop.copy()
    calls = []
    monkeypatch.setattr(search, '_contour_crops', lambda image: [(crop, inverse, padded, inverse)])
    def read(self, image, psm):
        calls.append(image)
        return [] if psm == 11 else [('ABC123',(0,10,70,30),.9)]
    monkeypatch.setattr(search.LocalTesseract, '_read', read)
    result = search_frame(blank(), (PlateQuery('ABC123'),), reader=search.LocalTesseract())
    assert result.complete and not result.hits and len(calls) == 3
