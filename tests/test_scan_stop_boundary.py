"""Whole-frame scan accounting with real decoded synthetic frames."""
import threading

import cv2
import numpy as np
import pytest

import openscrub as core


class Quiet(core.Callbacks):
    def log(self, message):
        pass


def clip(tmp_path, n=12, fps=6):
    path = tmp_path / 'source.avi'
    out = cv2.VideoWriter(str(path), cv2.VideoWriter_fourcc(*'FFV1'), fps, (96, 64))
    assert out.isOpened()
    try:
        for i in range(n):
            image = np.full((64, 96, 3), (i * 10) % 256, dtype=np.uint8)
            out.write(image)
    finally:
        out.release()
    return str(path)


def args_for(path, categories='email', extra=()):
    parser = core.build_parser()
    args = parser.parse_args([path, '--categories', categories,
                              '--engine', 'tesseract', '--sample-interval', '0.16666666666666666',
                              '--scroll-track', 'off', '--adaptive', 'off',
                              '--ocr-upscale', 'off', '--no-vfr-fix', '--no-backtrack', *extra])
    return core._prep_args(args, parser)


def watch_captures(monkeypatch, *, stop_after=None, stop=None, fail_after=None,
                   raise_after=None, reported_count=None, reported_fps=None,
                   reported_width=None, on_release=None):
    actual = core.cv2.VideoCapture
    seen = []

    class Capture:
        def __init__(self, *a, **kw):
            self.cap = actual(*a, **kw)
            self.reads = 0
            self.closed = False
            seen.append(self)

        def get(self, prop):
            if prop == cv2.CAP_PROP_FPS and reported_fps is not None:
                return float(reported_fps)
            if prop == cv2.CAP_PROP_FRAME_WIDTH and reported_width is not None:
                return float(reported_width)
            if prop == cv2.CAP_PROP_FRAME_COUNT and reported_count is not None:
                return float(reported_count)
            return self.cap.get(prop)

        def read(self):
            if raise_after is not None and self.reads == raise_after:
                raise OSError('injected decoder error')
            if fail_after is not None and self.reads == fail_after:
                return False, None
            result = self.cap.read()
            if result[0]:
                self.reads += 1
                if stop is not None and self.reads == stop_after:
                    stop.set()
            return result

        def release(self):
            self.closed = True
            self.cap.release()
            if on_release is not None:
                on_release()

        def __getattr__(self, name):
            return getattr(self.cap, name)

    monkeypatch.setattr(core.cv2, 'VideoCapture', Capture)
    return seen


def fake_ocr(monkeypatch, on_read=None):
    seen = []
    class OCR:
        def read(self, frame):
            seen.append(int(frame[0, 0, 0]))
            if on_read is not None:
                on_read(len(seen))
            return [('alice@example.invalid', (8, 8, 78, 28), .99),
                    ('status', (8, 35, 55, 55), .98),
                    ('active', (60, 35, 90, 55), .97)]
    monkeypatch.setattr(core, 'make_ocr', lambda *a, **kw: OCR())
    return seen


def test_stop_during_detector_work_finishes_frame_and_postprocessing(tmp_path, monkeypatch):
    path = clip(tmp_path)
    stop = threading.Event()
    captures = watch_captures(monkeypatch)
    reads = fake_ocr(monkeypatch, lambda n: stop.set() if n == 3 else None)
    stages = []
    real_merge = core.merge_detections
    def merge(*a, **kw):
        stages.append(('merge', len(a[0]), captures[0].closed))
        return real_merge(*a, **kw)
    monkeypatch.setattr(core, 'merge_detections', merge)
    state = core.run_scan(args_for(path), Quiet(), stop_requested=stop.is_set)
    boundary = state['scan_boundary']
    # The existing text scanner deliberately enforces at least two frames
    # between OCR calls. The third hit is on canonical frame index 4.
    assert reads == [0, 20, 40]
    assert captures[0].reads == 5 and captures[0].closed
    assert stages and stages[0][1] >= 3 and stages[0][2]
    assert any(d.category == 'email' and d.text == 'alice@example.invalid'
               for d in state['detections'])
    assert boundary['reason'] == 'stop_requested'
    assert boundary['next_frame'] == 5 and boundary['reported_total_frames'] == 12
    assert boundary['prefix_candidate'] is True
    assert boundary['checkpoint_available'] is False
    assert boundary['count_verified'] is False
    assert boundary['count_source'] == 'opencv_reported'
    assert len(state['cum']) == len(state['bands']) == 5


def test_stop_during_excluded_frames_counts_them_without_inference(tmp_path, monkeypatch):
    path = clip(tmp_path, n=18)
    stop = threading.Event()
    captures = watch_captures(monkeypatch, stop=stop, stop_after=3)
    reads = fake_ocr(monkeypatch)
    state = core.run_scan(args_for(path, extra=('--detect-windows', '1.0-2.0')),
                          Quiet(), stop_requested=stop.is_set)
    assert reads == []
    assert captures[0].reads == 3 and captures[0].closed
    assert state['scan_boundary']['reason'] == 'stop_requested'
    assert state['scan_boundary']['next_frame'] == 3
    assert len(state['cum']) == len(state['bands']) == 3
    assert state['cum'] == state['bands'] == [(0.0, 0.0)] * 3


def test_decoder_read_failure_is_not_a_verified_completion_or_checkpoint(tmp_path, monkeypatch):
    path = clip(tmp_path)
    captures = watch_captures(monkeypatch, fail_after=3)
    fake_ocr(monkeypatch)
    state = core.run_scan(args_for(path), Quiet(), stop_requested=lambda: False)
    status = state['scan_boundary']
    assert captures[0].closed
    assert status['reason'] == 'decoder_read_stopped_before_reported_count'
    assert status['next_frame'] == 3 and status['reported_total_frames'] == 12
    assert status['prefix_candidate'] is False
    assert status['count_verified'] is status['checkpoint_available'] is False
    assert len(state['cum']) == len(state['bands']) == 3


def test_fast_stop_has_aligned_unverified_prefix(tmp_path, monkeypatch):
    path = clip(tmp_path, n=18)
    captures = watch_captures(monkeypatch)
    fake_ocr(monkeypatch)
    state = core.run_scan(args_for(path, extra=('--detect-windows', '0.0-0.5')),
                          Quiet(), stop_requested=lambda: False)
    status = state['scan_boundary']
    assert captures[0].closed
    assert status['reason'] == 'scope_fast_stop'
    assert status['next_frame'] == 5
    assert status['reported_total_frames'] == 18
    assert status['prefix_candidate'] is status['checkpoint_available'] is False
    assert status['count_verified'] is False
    assert len(state['cum']) == len(state['bands']) == 5


def test_cancel_wins_over_simultaneous_stop_and_closes_capture(tmp_path, monkeypatch):
    path = clip(tmp_path)
    stop, cancel = threading.Event(), threading.Event()
    captures = watch_captures(monkeypatch)
    def request(n):
        if n == 3:
            stop.set()
            cancel.set()
    fake_ocr(monkeypatch, request)
    class Cancelling(Quiet):
        def cancelled(self):
            return cancel.is_set()
    with pytest.raises(core.PipelineCancelled):
        core.run_scan(args_for(path), Cancelling(), stop_requested=stop.is_set)
    assert captures[0].reads == 5 and captures[0].closed


def test_no_progress_stop_is_reported_without_reading_a_frame(tmp_path, monkeypatch):
    path = clip(tmp_path)
    stop = threading.Event()
    stop.set()
    captures = watch_captures(monkeypatch)
    reads = fake_ocr(monkeypatch)
    state = core.run_scan(args_for(path), Quiet(), stop_requested=stop.is_set)
    assert reads == [] and captures[0].reads == 0 and captures[0].closed
    assert state['scan_boundary']['reason'] == 'stop_requested'
    assert state['scan_boundary']['next_frame'] == 0
    assert state['scan_boundary']['prefix_candidate'] is False
    assert state['cum'] == state['bands'] == []


def test_decoder_stop_at_reported_count_is_still_unverified(tmp_path, monkeypatch):
    path = clip(tmp_path)
    captures = watch_captures(monkeypatch)
    fake_ocr(monkeypatch)
    state = core.run_scan(args_for(path), Quiet(), stop_requested=lambda: False)
    status = state['scan_boundary']
    assert captures[0].closed and captures[0].reads == 12
    assert status['reason'] == 'decoder_read_stopped_at_reported_count'
    assert status['next_frame'] == status['reported_total_frames'] == 12
    assert status['count_verified'] is status['checkpoint_available'] is False
    assert status['prefix_candidate'] is False
    assert len(state['cum']) == len(state['bands']) == 12


def test_cancellation_during_postprocessing_discards_candidate(tmp_path, monkeypatch):
    path = clip(tmp_path)
    stop, cancel = threading.Event(), threading.Event()
    captures = watch_captures(monkeypatch, stop=stop, stop_after=3)
    fake_ocr(monkeypatch)
    real_merge = core.merge_detections
    def merge(*a, **kw):
        result = real_merge(*a, **kw)
        cancel.set()
        return result
    monkeypatch.setattr(core, 'merge_detections', merge)
    class Cancelling(Quiet):
        def cancelled(self):
            return cancel.is_set()
    with pytest.raises(core.PipelineCancelled):
        core.run_scan(args_for(path), Cancelling(), stop_requested=stop.is_set)
    assert captures[0].closed


def test_frame_processing_error_closes_decoder_and_never_returns_candidate(tmp_path, monkeypatch):
    path = clip(tmp_path)
    captures = watch_captures(monkeypatch)
    class BrokenOCR:
        def read(self, frame):
            raise RuntimeError('injected OCR failure')
    monkeypatch.setattr(core, 'make_ocr', lambda *a, **kw: BrokenOCR())
    with pytest.raises(RuntimeError, match='injected OCR failure'):
        core.run_scan(args_for(path), Quiet(), stop_requested=lambda: False)
    assert captures[0].closed


def test_unverified_engine_candidate_cannot_be_rendered_or_serialized(tmp_path, monkeypatch):
    path = clip(tmp_path)
    stop = threading.Event()
    watch_captures(monkeypatch, stop=stop, stop_after=3)
    fake_ocr(monkeypatch)
    args = args_for(path)
    state = core.run_scan(args, Quiet(), stop_requested=stop.is_set)
    with pytest.raises(RuntimeError, match='unverified scan boundary'):
        core._report_document(args, state)
    with pytest.raises(RuntimeError, match='unverified scan boundary'):
        core.run_render(args, state, Quiet())


def test_requested_stop_defers_full_file_audio_analysis(tmp_path, monkeypatch):
    path = clip(tmp_path)
    stop = threading.Event()
    watch_captures(monkeypatch, stop=stop, stop_after=3)
    fake_ocr(monkeypatch)
    def forbidden(*a, **kw):
        raise AssertionError('partial stop must defer whole-file audio')
    monkeypatch.setattr(core, 'transcribe_audio_pii', forbidden)
    state = core.run_scan(args_for(path, extra=('--audio-pii',)), Quiet(),
                          stop_requested=stop.is_set)
    assert state['scan_boundary']['audio_incomplete'] is True
    assert state['audio_suggestions'] == state['audio_transcript'] == []


def test_decoder_exception_releases_capture_and_propagates(tmp_path, monkeypatch):
    path = clip(tmp_path)
    captures = watch_captures(monkeypatch, raise_after=3)
    fake_ocr(monkeypatch)
    with pytest.raises(RuntimeError, match='decoder exception at frame 3') as exc:
        core.run_scan(args_for(path), Quiet(), stop_requested=lambda: False)
    assert captures[0].closed
    assert exc.value.reason == 'decoder_exception'
    assert exc.value.next_frame == 3 and exc.value.reported_total_frames == 12
    assert exc.value.checkpoint_available is exc.value.count_verified is False
    assert isinstance(exc.value.__cause__, OSError)
    assert str(exc.value.__cause__) == 'injected decoder error'


def test_stop_cannot_claim_candidate_when_fps_is_only_a_fallback(tmp_path, monkeypatch):
    path = clip(tmp_path)
    stop = threading.Event()
    captures = watch_captures(monkeypatch, stop=stop, stop_after=3, reported_fps=0)
    fake_ocr(monkeypatch)
    state = core.run_scan(args_for(path), Quiet(), stop_requested=stop.is_set)
    assert captures[0].closed
    assert state['scan_boundary']['fps_source'] == 'fallback_30'
    assert state['scan_boundary']['prefix_candidate'] is False
    assert state['scan_boundary']['checkpoint_available'] is False


def test_unavailable_reported_count_cannot_make_a_checkpoint_candidate(tmp_path, monkeypatch):
    path = clip(tmp_path)
    stop = threading.Event()
    captures = watch_captures(monkeypatch, stop=stop, stop_after=1, reported_count=0)
    fake_ocr(monkeypatch)
    state = core.run_scan(args_for(path), Quiet(), stop_requested=stop.is_set)
    assert captures[0].closed
    status = state['scan_boundary']
    assert status['reason'] == 'stop_requested' and status['next_frame'] == 1
    assert status['reported_total_frames'] == 0 and status['count_source'] == 'unavailable'
    assert status['count_verified'] is status['prefix_candidate'] is False
    assert status['checkpoint_available'] is False


def test_stop_after_reported_count_never_claims_checkpoint_or_completion(tmp_path, monkeypatch):
    path = clip(tmp_path)
    stop = threading.Event()
    captures = watch_captures(monkeypatch, stop=stop, stop_after=6, reported_count=4)
    fake_ocr(monkeypatch)
    state = core.run_scan(args_for(path), Quiet(), stop_requested=stop.is_set)
    status = state['scan_boundary']
    assert captures[0].closed and status['next_frame'] == 6
    assert status['reported_total_frames'] == 4 and status['reason'] == 'scope_fast_stop'
    assert status['prefix_candidate'] is status['count_verified'] is False
    assert status['checkpoint_available'] is False
    assert len(state['cum']) == len(state['bands']) == 6


def test_unfinished_setup_track_refuses_stop_without_following_future_frames(tmp_path, monkeypatch):
    path = clip(tmp_path)
    stop = threading.Event()
    captures = watch_captures(monkeypatch, stop=stop, stop_after=3)
    fake_ocr(monkeypatch)
    args = args_for(path)
    args.windows_data = [{'t0': 0.0, 't1': 1.0, 'cats': ['email'],
                          'track': [[.1, .1, .8, .8, .5]]}]
    def forbidden(*a, **kw):
        raise AssertionError('must not infer or follow a future setup track')
    monkeypatch.setattr(core, 'track_manual_region', forbidden)
    with pytest.raises(RuntimeError, match='setup tracked object extends'):
        core.run_scan(args, Quiet(), stop_requested=stop.is_set)
    assert captures[0].closed and captures[0].reads == 3


def test_postprocessing_failure_cannot_return_a_candidate(tmp_path, monkeypatch):
    path = clip(tmp_path)
    stop = threading.Event()
    captures = watch_captures(monkeypatch, stop=stop, stop_after=3)
    fake_ocr(monkeypatch)
    def fail(*a, **kw):
        raise RuntimeError('synthetic finalization failure')
    monkeypatch.setattr(core, 'merge_detections', fail)
    with pytest.raises(RuntimeError, match='synthetic finalization failure'):
        core.run_scan(args_for(path), Quiet(), stop_requested=stop.is_set)
    assert captures[0].closed


def test_cancel_during_boundary_cleanup_wins_over_unsupported_setup_track(tmp_path, monkeypatch):
    path = clip(tmp_path)
    stop, cancel = threading.Event(), threading.Event()
    captures = watch_captures(monkeypatch, stop=stop, stop_after=3, on_release=cancel.set)
    fake_ocr(monkeypatch)
    args = args_for(path)
    args.windows_data = [{'t0': 0.0, 't1': 1.0, 'cats': ['email'],
                          'track': [[.1, .1, .8, .8, .5]]}]
    class Cancelling(Quiet):
        def cancelled(self):
            return cancel.is_set()
    with pytest.raises(core.PipelineCancelled):
        core.run_scan(args, Cancelling(), stop_requested=stop.is_set)
    assert captures[0].closed


def test_ordinary_fast_stop_retains_existing_raw_timeline_shape(tmp_path, monkeypatch):
    path = clip(tmp_path, n=18)
    fake_ocr(monkeypatch)
    args = args_for(path, extra=('--detect-windows', '0.0-0.5'))
    state = core.run_scan(args, Quiet())
    assert 'scan_boundary' not in state
    assert len(state['cum']) == 5 and len(state['bands']) == 4
    report = core._report_document(args, state)
    assert len(report['render_state']['cum']) == 5
    assert len(report['render_state']['bands']) == 4


def test_ordinary_failed_seek_recovery_retains_existing_raw_timeline_shape(tmp_path, monkeypatch):
    path = clip(tmp_path, n=30)
    fake_ocr(monkeypatch)
    monkeypatch.setattr(core, '_seek_cap', lambda *a, **kw: False)
    args = args_for(path, extra=('--detect-windows', '0.0-0.5,3.0-4.0'))
    state = core.run_scan(args, Quiet())
    assert 'scan_boundary' not in state
    assert len(state['cum']) == 5 and len(state['bands']) == 4
    report = core._report_document(args, state)
    assert len(report['render_state']['cum']) == 5
    assert len(report['render_state']['bands']) == 4


def test_monitored_stop_does_not_seek_across_a_long_initial_excluded_span(tmp_path, monkeypatch):
    path = clip(tmp_path, n=30)
    stop = threading.Event()
    captures = watch_captures(monkeypatch, stop=stop, stop_after=3)
    reads = fake_ocr(monkeypatch)
    def forbidden(*a, **kw):
        raise AssertionError('monitored prefix must not trust an unverified seek')
    monkeypatch.setattr(core, '_seek_cap', forbidden)
    state = core.run_scan(args_for(path, extra=('--detect-windows', '2.0-3.0')),
                          Quiet(), stop_requested=stop.is_set)
    assert captures[0].closed and captures[0].reads == 3 and reads == []
    assert state['scan_boundary']['reason'] == 'stop_requested'
    assert state['scan_boundary']['next_frame'] == 3
    assert len(state['cum']) == len(state['bands']) == 3


def test_monitored_stop_does_not_seek_across_a_long_excluded_gap(tmp_path, monkeypatch):
    path = clip(tmp_path, n=30)
    stop = threading.Event()
    captures = watch_captures(monkeypatch, stop=stop, stop_after=6)
    fake_ocr(monkeypatch)
    def forbidden(*a, **kw):
        raise AssertionError('monitored prefix must not trust an unverified seek')
    monkeypatch.setattr(core, '_seek_cap', forbidden)
    state = core.run_scan(args_for(path, extra=('--detect-windows', '0.0-0.5,3.0-4.0')),
                          Quiet(), stop_requested=stop.is_set)
    assert captures[0].closed and captures[0].reads == 6
    assert state['scan_boundary']['reason'] == 'stop_requested'
    assert state['scan_boundary']['next_frame'] == 6
    assert len(state['cum']) == len(state['bands']) == 6


def test_read_failure_cannot_follow_a_setup_track_beyond_the_processed_prefix(tmp_path, monkeypatch):
    path = clip(tmp_path)
    captures = watch_captures(monkeypatch, fail_after=3)
    fake_ocr(monkeypatch)
    args = args_for(path)
    args.windows_data = [{'t0': 0.0, 't1': 1.0, 'cats': ['email'],
                          'track': [[.1, .1, .8, .8, .5]]}]
    monkeypatch.setattr(core, 'PersonDetector', lambda *a, **kw: None)
    def forbidden(*a, **kw):
        raise AssertionError('must not track outside the accounted prefix')
    monkeypatch.setattr(core, 'track_manual_region', forbidden)
    with pytest.raises(RuntimeError, match='setup tracked object extends'):
        core.run_scan(args, Quiet(), stop_requested=lambda: False)
    assert captures[0].closed


def test_monitored_finalization_does_not_swallow_pipeline_cancellation(tmp_path, monkeypatch):
    path = clip(tmp_path)
    stop = threading.Event()
    captures = watch_captures(monkeypatch, stop=stop, stop_after=3)
    fake_ocr(monkeypatch)
    monkeypatch.setattr(core, 'assign_dense_tracks', lambda *a, **kw: 1)
    monkeypatch.setattr(core, 'smooth_dense_tracks', lambda *a, **kw: (0, 0, 0.0))
    def cancelled(*a, **kw):
        raise core.PipelineCancelled()
    monkeypatch.setattr(core, 'group_persons', cancelled)
    with pytest.raises(core.PipelineCancelled):
        core.run_scan(args_for(path), Quiet(), stop_requested=stop.is_set)
    assert captures[0].closed


def test_mismatched_decoded_dimensions_cannot_be_a_prefix_candidate(tmp_path, monkeypatch):
    path = clip(tmp_path)
    stop = threading.Event()
    captures = watch_captures(monkeypatch, stop=stop, stop_after=3, reported_width=80)
    fake_ocr(monkeypatch)
    state = core.run_scan(args_for(path), Quiet(), stop_requested=stop.is_set)
    assert captures[0].closed
    assert state['scan_boundary']['next_frame'] == 3
    assert state['scan_boundary']['dimensions'] == [80, 64]
    assert state['scan_boundary']['dimensions_match'] is False
    assert state['scan_boundary']['prefix_candidate'] is False
    assert state['scan_boundary']['checkpoint_available'] is False


def test_stop_after_last_selected_frame_does_not_claim_a_paused_prefix(tmp_path, monkeypatch):
    path = clip(tmp_path, n=18)
    stop = threading.Event()
    captures = watch_captures(monkeypatch, stop=stop, stop_after=4)
    fake_ocr(monkeypatch)
    state = core.run_scan(args_for(path, extra=('--detect-windows', '0.0-0.5')),
                          Quiet(), stop_requested=stop.is_set)
    status = state['scan_boundary']
    assert captures[0].closed and captures[0].reads == 4
    assert status['reason'] == 'scope_fast_stop' and status['next_frame'] == 4
    assert status['count_verified'] is status['prefix_candidate'] is False
    assert status['checkpoint_available'] is False
    assert len(state['cum']) == len(state['bands']) == 4


@pytest.mark.parametrize('kind', ['cancel', 'error'])
def test_gap_capture_closes_with_retained_finalization_exception(tmp_path, monkeypatch, kind):
    path = clip(tmp_path)
    stop = threading.Event()
    captures = watch_captures(monkeypatch, stop=stop, stop_after=3)
    fake_ocr(monkeypatch)
    def interrupted(*a, **kw):
        if kind == 'cancel':
            raise core.PipelineCancelled()
        raise OSError('secondary gap decode failed')
    def merge_with_gap(*a, **kw):
        d = core.Detection(0, 1, (2, 2, 20, 20), 'email', 'x', .9, (0., 0.))
        return kw['gap_check'](d, 0, 1)
    monkeypatch.setattr(core, '_grab_frame', interrupted)
    monkeypatch.setattr(core, 'merge_detections', merge_with_gap)
    expected = core.PipelineCancelled if kind == 'cancel' else OSError
    with pytest.raises(expected) as caught:
        core.run_scan(args_for(path), Quiet(), stop_requested=stop.is_set)
    assert caught.value.__traceback__ is not None  # keep the frame cycle alive
    assert len(captures) == 2
    assert [capture.closed for capture in captures] == [True, True]


@pytest.mark.parametrize('kind', ['cancel', 'error'])
def test_deep_backtrack_capture_closes_with_retained_exception(tmp_path, monkeypatch, kind):
    path = tmp_path / 'textured.avi'
    writer = cv2.VideoWriter(str(path), cv2.VideoWriter_fourcc(*'FFV1'), 6, (96, 64))
    assert writer.isOpened()
    image = np.random.default_rng(12).integers(0, 255, (64, 96, 3), dtype=np.uint8)
    try:
        for _ in range(12):
            writer.write(image)
    finally:
        writer.release()
    stop = threading.Event()
    captures = watch_captures(monkeypatch, stop=stop, stop_after=3)
    calls = []
    class DelayedOCR:
        def read(self, frame):
            calls.append(True)
            if len(calls) == 1:
                return []
            return [('alice@example.invalid', (8, 8, 78, 28), .99)]
    monkeypatch.setattr(core, 'make_ocr', lambda *a, **kw: DelayedOCR())
    monkeypatch.setattr(core, 'backtrack_onset', lambda d, buf, *a: buf[0][0] if buf else None)
    def interrupted(*a, **kw):
        if kind == 'cancel':
            raise core.PipelineCancelled()
        raise OSError('secondary backtrack decode failed')
    monkeypatch.setattr(core, '_grab_frame', interrupted)
    args = args_for(str(path))
    args.no_backtrack = False
    expected = core.PipelineCancelled if kind == 'cancel' else OSError
    with pytest.raises(expected) as caught:
        core.run_scan(args, Quiet(), stop_requested=stop.is_set)
    assert caught.value.__traceback__ is not None
    assert len(captures) == 2
    assert [capture.closed for capture in captures] == [True, True]


def test_successful_gap_capture_preserves_result_and_closes(tmp_path, monkeypatch):
    path = clip(tmp_path)
    stop = threading.Event()
    captures = watch_captures(monkeypatch, stop=stop, stop_after=3)
    fake_ocr(monkeypatch)
    expected = core.run_scan(args_for(path), Quiet(), stop_requested=stop.is_set)
    stop.clear()
    fake_ocr(monkeypatch)
    original = core.merge_detections
    def merge_with_gap(*a, **kw):
        d = core.Detection(0, 1, (2, 2, 20, 20), 'email', 'x', .9, (0., 0.))
        assert kw['gap_check'](d, 0, 1) is False
        return original(*a, **kw)
    monkeypatch.setattr(core, 'merge_detections', merge_with_gap)
    actual = core.run_scan(args_for(path), Quiet(), stop_requested=stop.is_set)
    assert actual == expected
    assert len(captures) == 3
    assert all(capture.closed for capture in captures)
