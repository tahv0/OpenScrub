"""Stage ETA behavior using the actual web callback and a controlled clock."""
import math
import threading
from types import SimpleNamespace

import pytest

import openscrub_web as web
from test_job_lifecycle import store


@pytest.fixture
def clock(monkeypatch):
    clock = SimpleNamespace(now=0.0, wall=10000.0)
    # Replace only this module's clock: wall time remains independently movable.
    monkeypatch.setattr(web, "time", SimpleNamespace(
        monotonic=lambda: clock.now, time=lambda: clock.wall))
    return clock


def test_sustained_slow_tail_replaces_fast_prefix(clock):
    job = {"cancel": threading.Event()}
    cb = web.WebCallbacks(job)
    # 600 s at 10 units/s, then 180 s at 1 unit/s; 3820 units remain.
    for t in range(0, 601, 5):
        clock.now, clock.wall = t, 10000 + t
        cb.progress("scan", t * 10, 10000)
    for t in range(605, 781, 5):
        clock.now, clock.wall = t, 10000 + t
        cb.progress("scan", 6000 + t - 600, 10000)
    assert 3815 <= job["eta"] <= 3835
    assert job["progress"] == 0.2781


def observe(cb, clock, t, cur, total=100, stage="scan"):
    clock.now, clock.wall = t, 10000 + t
    cb.progress(stage, cur, total)
    eta = cb.job["eta"]
    assert eta is None or (math.isfinite(eta) and eta >= 0)
    return eta


def test_startup_waits_three_seconds_and_smooths_new_estimates(clock):
    cb = web.WebCallbacks({"cancel": threading.Event()})
    assert observe(cb, clock, 0, 10) is None
    assert observe(cb, clock, 2, 12) is None
    assert observe(cb, clock, 3, 13) == 87
    assert observe(cb, clock, 5, 15) == 86
    # New rate is (40-10)/10 = 3/s, raw remaining 20 s.
    assert observe(cb, clock, 10, 40) == 43


def test_steady_rate_tracks_remaining_time(clock):
    cb = web.WebCallbacks({"cancel": threading.Event()})
    for t in range(0, 101, 5):
        eta = observe(cb, clock, t, t, 200)
        if t >= 20:
            assert 200 - t <= eta <= 200 - t + 3


def test_zero_progress_and_mature_stall_have_no_useful_rate(clock):
    cb = web.WebCallbacks({"cancel": threading.Event()})
    for t in range(0, 151, 5):
        assert observe(cb, clock, t, 0) is None
    cb = web.WebCallbacks({"cancel": threading.Event()})
    observe(cb, clock, 0, 0)
    assert observe(cb, clock, 20, 20) == 80
    for t in range(25, 151, 5):
        observe(cb, clock, t, 20)
    assert cb.job["eta"] is None  # Historical startup rate must not return.


def test_recent_window_retains_one_predecessor_for_interval_rate(clock):
    cb = web.WebCallbacks({"cancel": threading.Event()})
    observe(cb, clock, 0, 0, 1000)
    assert observe(cb, clock, 100, 100, 1000) == 900
    assert observe(cb, clock, 230, 230, 1000) == 816
    # At t=240 the cutoff is 120. Retain (100,100) to measure the
    # crossing interval: recent rate = (330-100)/(240-100) = 23/14.
    assert observe(cb, clock, 240, 330, 1000) == 551


def test_recent_rate_is_mature_at_twenty_seconds(clock):
    cb = web.WebCallbacks({"cancel": threading.Event()})
    observe(cb, clock, 0, 0)
    assert observe(cb, clock, 20, 20) == 80
    # The last sampled rate is 1/s over 20 s. Before the next sample,
    # whole-stage rate would be 2.5/s and imply only 16 s remaining.
    assert observe(cb, clock, 24, 60) == 54


def test_subsample_and_repeated_calls_do_not_grow_sample_storage(clock):
    cb = web.WebCallbacks({"cancel": threading.Event()})
    observe(cb, clock, 0, 0)
    for t in range(1, 5):
        observe(cb, clock, t, t)
        observe(cb, clock, t, t)
    assert len(cb._rate_points) == 1
    observe(cb, clock, 5, 5)
    assert len(cb._rate_points) == 2


def test_wall_clock_jump_does_not_change_eta(clock):
    cb = web.WebCallbacks({"cancel": threading.Event()})
    observe(cb, clock, 0, 0)
    assert observe(cb, clock, 5, 5) == 95
    clock.now, clock.wall = 10, -10000
    cb.progress("scan", 10, 100)
    assert cb.job["eta"] == 92


def test_counter_regression_between_samples_starts_fresh(clock):
    cb = web.WebCallbacks({"cancel": threading.Event()})
    observe(cb, clock, 0, 10)
    observe(cb, clock, 1, 15)
    assert observe(cb, clock, 2, 14) is None
    assert observe(cb, clock, 5, 17) == 83


@pytest.mark.parametrize("stage,progress", [
    ("scan", 0.05556), ("post", 0.45617),
    ("render", 0.56173), ("other", 0.56173),
])
def test_progress_mapping_and_stage_reset(clock, stage, progress):
    cb = web.WebCallbacks({"cancel": threading.Event()})
    observe(cb, clock, 0, 0, stage="old")
    observe(cb, clock, 5, 5, stage="old")
    assert observe(cb, clock, 10, 1, 8.1, stage) is None
    assert cb.job["progress"] == progress
    assert observe(cb, clock, 13, 2, 8.1, stage) == 18


def test_completion_resets_estimator_for_same_stage_next_attempt(clock):
    cb = web.WebCallbacks({"cancel": threading.Event()})
    observe(cb, clock, 0, 0)
    observe(cb, clock, 5, 5)
    assert observe(cb, clock, 6, 100) is None
    assert cb._rate_points == []
    # A following call at the same counter must still begin fresh.
    assert observe(cb, clock, 20, 100, 200) is None
    assert observe(cb, clock, 23, 103, 200) == 97
    assert observe(web.WebCallbacks({"cancel": threading.Event()}), clock, 30, 103, 200) is None


@pytest.mark.parametrize("cur,total", [
    (0, 0), (0, -1), (float("nan"), 100),
    (float("inf"), 100), (1, float("inf")), (1, float("nan")),
    (1e-308, 1e308),
])
def test_unusable_numeric_observations_never_publish_invalid_eta(clock, cur, total):
    cb = web.WebCallbacks({"cancel": threading.Event()})
    observe(cb, clock, 0, 0)
    observe(cb, clock, 5, cur, total)
    assert cb.job["eta"] is None


def test_storage_stays_bounded_over_a_long_stage(clock):
    cb = web.WebCallbacks({"cancel": threading.Event()})
    for t in range(0, 10001, 5):
        observe(cb, clock, t, t, 20000)
        assert len(cb._rate_points) <= 26
        assert sum(point[0] < t - 120 for point in cb._rate_points) <= 1
    assert cb.job["eta"] == 10003


@pytest.mark.parametrize("result", ["done", "cancelled", "error"])
def test_worker_clears_published_eta_and_uses_fresh_callback(
        clock, monkeypatch, store, result):
    job = store.job
    callbacks = []
    monkeypatch.setattr(web, "build_args", lambda *a, **kw: SimpleNamespace())
    monkeypatch.setattr(web.openscrub, "load_report", lambda *a: ([], {}, {}))

    def pipeline(args, cb):
        callbacks.append(cb)
        assert observe(cb, clock, 0, 10, stage="render") is None
        assert observe(cb, clock, 5, 15, stage="render") == 85
        if result == "cancelled":
            raise web.openscrub.PipelineCancelled()
        if result == "error":
            raise RuntimeError("synthetic stage error")
        return {"output": str(store.root / "result.mp4")}

    monkeypatch.setattr(web.openscrub, "run_pipeline", pipeline)
    for _ in range(2):
        web._run_job(job, "render")
        assert job["phase"] == result
        assert web.job_public(job)["eta"] is None
    assert callbacks[0] is not callbacks[1]
