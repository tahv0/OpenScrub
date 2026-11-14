"""Review thumbnails must be prepared from final cards before Review opens."""
import numpy as np
import pytest

import finding_previews as previews
import openscrub_web as web
from test_finding_previews import frame, row, state
from werkzeug.exceptions import ServiceUnavailable


class Callbacks:
    def __init__(self):
        self.logs = []
        self.updates = []

    def log(self, message):
        self.logs.append(message)

    def progress(self, stage, done, total):
        self.updates.append((stage, done, total))

    def cancelled(self):
        return False

    def stop_requested(self):
        return False


def sample(category="plate", track=-1, person=-1, start=0., **extra):
    return dict(category=category, track=track, person=person, t_start=start, **extra)


def test_initial_representatives_match_review_grouping_and_excluded_cards():
    rows = [
        sample(track=7, start=5),
        sample(track=7, start=1),
        sample(track=8, person=22, start=6),
        sample(track=9, person=22, start=2),
        sample(start=3),
        sample(category="face", track=7, start=1),
        sample(track=7, start=4, zone_dropped=True),
    ]
    # Zone-excluded cards are individual; remaining cards use first actual
    # sighting per category and person/track, not first row in the report.
    assert previews.review_representatives(rows) == [6, 1, 3, 4, 5]


def test_preparation_protects_all_cache_hits_before_filling_misses(tmp_path, monkeypatch):
    rows = [sample(track=i, start=float(i)) for i in range(4)]
    seen = []
    keys = {0: "first-scan-sample", 2: "third-scan-sample"}

    def fake_preview(job, index, doc=None, cache_only=False, protected_keys=None):
        assert doc["detections"] is rows
        if cache_only:
            seen.append(("cached", index))
            if index in keys:
                return doc, rows[index], {"key": keys[index]}, b"jpeg"
            return None
        # Previously prepared scans must not be evicted to fill later cards,
        # including the sample which has not yet appeared on-screen.
        assert protected_keys is not None
        assert set(keys.values()).issubset(protected_keys)
        seen.append(("cold", index))
        return doc, rows[index], {"key": "new-%d" % index}, b"jpeg"

    monkeypatch.setattr(web.findings_web, "preview", fake_preview)
    monkeypatch.setattr(web.diagnostics, "event", lambda *args, **kwargs: None)
    cb = Callbacks()
    job = {"dir": str(tmp_path)}
    outcome = web._prepare_review_card_previews(job, {"detections": rows}, cb)
    assert seen == [("cached", 0), ("cached", 1), ("cached", 2),
                    ("cached", 3), ("cold", 1), ("cold", 3)]
    assert outcome["cached"] == 2 and outcome["generated"] == 2
    assert outcome["failed"] == 0 and outcome["ready"]
    assert job["review_preparation"] == outcome
    assert cb.updates[0] == ("thumbnails", 0, 4)
    assert cb.updates[-1] == ("thumbnails", 4, 4)


def test_preparation_reports_bad_source_without_abandoning_other_cards(tmp_path, monkeypatch):
    rows = [sample(track=i) for i in range(3)]
    cold = []

    def preview(job, index, doc=None, cache_only=False, protected_keys=None):
        if cache_only:
            return None
        cold.append(index)
        if index == 1:
            raise ServiceUnavailable("broken source frame")
        return doc, rows[index], {"key": str(index)}, b"jpeg"

    monkeypatch.setattr(web.findings_web, "preview", preview)
    monkeypatch.setattr(web.diagnostics, "event", lambda *args, **kwargs: None)
    cb = Callbacks()
    result = web._prepare_review_card_previews(
        {"dir": str(tmp_path)}, {"detections": rows}, cb)
    assert cold == [0, 1, 2]
    assert result["generated"] == 2 and result["failed"] == 1
    assert not result["ready"]
    assert any("unavailable" in msg for msg in cb.logs)


def test_protected_prepared_picture_is_not_evicted_under_budget(tmp_path, monkeypatch):
    monkeypatch.setattr(previews, "MAX_ITEMS", 1)
    assert previews.capture(tmp_path, frame(), 3, 10., [row()])["added"] == 1
    earlier = previews.lookup(tmp_path, row(), state())
    assert earlier is not None
    protected = {earlier[0]["key"]}
    meta = {"frame": 4, "width": 1600, "height": 900,
            "crop": [100, 90, 300, 190], "box": [120., 100., 240., 150.]}
    pixels = np.zeros((100, 200, 3), dtype=np.uint8)
    with pytest.raises(previews.PreviewLimitError):
        previews.store(tmp_path, row(frame=4), state(), meta, pixels,
                       protected_keys=protected)
    assert previews.lookup(tmp_path, row(), state()) == earlier
    assert previews.lookup(tmp_path, row(frame=4), state()) is None
