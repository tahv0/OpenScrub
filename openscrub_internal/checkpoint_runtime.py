"""Internal single-owner stop/resume producer for one conservative subset.

The caller must exclusively own the source and report, including cancellation
and publication, for the whole call. This is not a web transaction or a UI
control: a later owner must supply operation fencing and its existing report
lock before exposing it to concurrent readers/writers. In particular, content
hashes do not prevent in-place modification followed by restoration.
"""
import copy
import glob
import hashlib
import json
import math
import os
import platform
import shutil
import sys

import cv2
import numpy as np

from openscrub_internal import checkpoint_media, checkpoints
from openscrub_internal.reports import _staged_report


class CheckpointRuntimeError(ValueError):
    """The requested checkpoint scan is outside the supported subset."""


def _identity(args, source):
    import openscrub as core
    categories = {c.strip() for c in args.categories.split(',') if c.strip()}
    if categories not in ({'qrcode'}, {'none'}, set()):
        raise CheckpointRuntimeError('checkpoint scanning supports only qrcode or none; start a fresh ordinary scan for other categories')
    if not getattr(args, 'no_vfr_fix', False) or getattr(args, 'original_video', None) or getattr(args, 'hdr_source', None):
        raise CheckpointRuntimeError('checkpoint scanning requires the original source without normalization; set --no-vfr-fix')
    if getattr(args, 'scroll_track', None) != 'off':
        raise CheckpointRuntimeError('checkpoint scanning currently requires --scroll-track off')
    if not getattr(args, 'no_backtrack', False):
        raise CheckpointRuntimeError('checkpoint scanning currently requires --no-backtrack')
    for key in ('zones', 'zones_data', 'windows', 'windows_data', 'ignore_region',
                'ignore_regions', 'detect_windows', 'detect_windows_frac', 'skip_start',
                'skip_end', 'audio_pii', 'allow_names', 'extra_names', 'phrases',
                'face_model', 'plate_model', 'person_model', 'dense_faces'):
        if getattr(args, key, None):
            raise CheckpointRuntimeError('checkpoint scanning does not yet support %s; use a fresh ordinary scan' % key)
    excluded = {'video', 'output', 'report', 'config', 'batch', 'from_report'}
    try:
        settings = json.loads(json.dumps({k: v for k, v in vars(args).items()
                                         if k not in excluded}, allow_nan=False,
                                        sort_keys=True))
    except (TypeError, ValueError, OverflowError) as exc:
        raise CheckpointRuntimeError('checkpoint scan settings are not portable JSON') from exc
    cv_binaries = glob.glob(os.path.join(os.path.dirname(cv2.__file__), 'cv2*.so'))
    cv_binaries += glob.glob(os.path.join(os.path.dirname(cv2.__file__), 'cv2*.pyd'))
    if len(cv_binaries) != 1:
        raise CheckpointRuntimeError('cannot identify the OpenCV native module for checkpoint scanning')
    binaries = {'engine': core.__file__, 'checkpoint_media': checkpoint_media.__file__,
                'checkpoint_runtime': __file__, 'opencv': cv_binaries[0],
                'ffmpeg': shutil.which('ffmpeg'), 'ffprobe': shutil.which('ffprobe')}
    try:
        files = {name: core.sha256_file(path) for name, path in binaries.items()}
    except (OSError, TypeError) as exc:
        raise CheckpointRuntimeError('cannot fingerprint the active checkpoint scan components') from exc
    settings['_runtime'] = {'python': sys.version, 'platform': platform.platform(),
                            'opencv': cv2.__version__, 'numpy': np.__version__,
                            'opencv_build_sha256': hashlib.sha256(
                                cv2.getBuildInformation().encode()).hexdigest()}
    fps = float(source.fps)
    participant = {'sha256': source.sha256, 'width': source.width,
                   'height': source.height, 'fps': fps,
                   'fps_source': 'mp4_rate_and_observed_pts_v1'}
    return {'sources': {'scan': dict(participant), 'original': dict(participant), 'render': None},
            'normalization': {'mode': 'none', 'target': 'none', 'transform_version': 'none'},
            'timeline': {'fps': fps, 'fps_source': 'mp4_rate_and_observed_pts_v1',
                         'total_frames': source.total_frames,
                         'count_source': 'mp4_reported_nb_frames', 'count_verified': False},
            'effective_settings': settings, 'file_identities': files}


def _load(path):
    try:
        with open(path, 'rb') as stream:
            raw = stream.read()
        return raw, json.loads(raw)
    except (OSError, ValueError) as exc:
        raise CheckpointRuntimeError('cannot read the existing checkpoint report') from exc


def _validate_previous(previous, identity, source):
    marker = checkpoints.validate_resume(previous, identity)
    boundary = marker['next_frame']
    # This first subset has no scrolling. Never reinterpret a saved scroll
    # coordinate system or future manual geometry as a screen-space one.
    for vector in previous['render_state']['cum']:
        if vector != [0.0, 0.0]:
            raise CheckpointRuntimeError('nonzero scroll coordinates are not supported for checkpoint resume')
    for row in previous['detections']:
        if (row.get('category') == 'manual' and
                row.get('t_end', 0) > boundary / float(source.fps)):
            raise CheckpointRuntimeError('manual geometry beyond the processed boundary is not supported')
    return boundary


def scan_to_report(args, report_path, *, cb, stop_requested, publication_lock,
                   resume=False, _commit_staged=None):
    """Run one synchronous attempt with caller-owned source and report locks.

    The caller must exclude source writers throughout the call, use the same
    report lock for all report writers and cancellation acknowledgement, and
    retain operation ownership through cleanup. This is not connected to
    web or CLI actions. Staging is outside the report lock; publication checks
    the latest raw bytes and cancellation under that lock. An owning service
    can supply a private staged-commit callback; it runs synchronously while
    that same lock is held and must consume the stage or raise.
    """
    import openscrub as core
    if not callable(stop_requested):
        raise TypeError('stop_requested must be a no-argument callback')
    if publication_lock is None:
        raise CheckpointRuntimeError('checkpoint scan requires the owning report lock')
    if _commit_staged is not None and not callable(_commit_staged):
        raise TypeError('_commit_staged must be callable')
    source = checkpoint_media.inspect_source(args.video)
    identity = _identity(args, source)
    with checkpoint_media.SourceLease(source) as lease:
        with publication_lock:
            if resume:
                _, previous = _load(report_path)
                boundary = _validate_previous(previous, identity, source)
            else:
                if os.path.exists(report_path):
                    raise CheckpointRuntimeError('report already exists; resume it or choose a new report')
                previous, boundary = None, 0
        start = (max(0, boundary - max(1, math.ceil(source.fps))) if resume else 0)
        scan_args = copy.deepcopy(args)
        # run_pipeline normally parses these before scanning. Checkpoint
        # attempts call run_scan directly, so retain the same explicit choices.
        if getattr(scan_args, 'audio_redact', ''):
            scan_args.audio_spans = core.parse_audio_spans(
                scan_args.audio_redact, scan_args.audio_redact_mode)
        def check_cancelled():
            if cb.cancelled():
                raise core.PipelineCancelled()
        with checkpoint_media.FrameStream(source, start_frame=start,
                                          check_cancelled=check_cancelled) as stream:
            state = core.run_scan(scan_args, cb, stop_requested=stop_requested,
                                  _checkpoint_stream=stream)
        status = state['scan_boundary']
        end = status['next_frame']
        if end <= boundary:
            return previous
        if status['reason'] == 'stop_requested':
            if not status['prefix_candidate']:
                raise CheckpointRuntimeError('stopped scan did not yield a valid whole-frame boundary')
            completed = False
        elif status['reason'] == 'decoder_clean_verified_range' and stream.completed:
            completed = True
        else:
            raise CheckpointRuntimeError('scan decoder did not establish a complete or stopped range')
        if state['input_sha256'] != source.sha256 or _identity(args, source) != identity:
            raise CheckpointRuntimeError('checkpoint source or scan settings changed during the attempt')
        if cb.cancelled():
            raise core.PipelineCancelled()
        snapshot = dict(state)
        snapshot.pop('scan_boundary')
        # Detection dataclasses contain tuples; validate their on-disk JSON form.
        doc = json.loads(json.dumps(core._report_document(scan_args, snapshot),
                                    allow_nan=False))
        if previous is None:
            if completed:
                # This is a fresh generated document, so every row has the
                # complete source range. The existing render owner checks the
                # attested identity and extent even when there are no rows.
                initial = doc
                completed_identity = copy.deepcopy(identity)
                completed_identity['timeline']['count_verified'] = True
                initial['provenance']['checkpoint_identity'] = completed_identity
                for row in initial['detections']:
                    row['scan_frame_start'], row['scan_frame_end'] = 0, source.total_frames
                core._report_frame_authorities(initial)
                core._validate_bounded_report_identity(initial, source.sha256, state)
            else:
                initial = checkpoints.with_checkpoint(doc, end, source.total_frames, identity)
        else:
            anchor = boundary - 1
            if doc['render_state']['cum'][anchor] != previous['render_state']['cum'][anchor]:
                raise CheckpointRuntimeError('the observed scroll anchor differs from the checkpoint')
            continuation_identity = copy.deepcopy(identity)
            continuation_identity['timeline']['count_verified'] = completed
            doc['provenance']['checkpoint_identity'] = continuation_identity
            if completed:
                doc['scan_completion'] = {'reason': 'accounted_verified_range',
                                          'next_frame': end, 'total_frames': source.total_frames}
        # A reviewer may save while scanning. Prepare from the latest complete
        # document, then compare its bytes again under the owner's report lock.
        # If a save wins between snapshot and commit, retry with the newer raw
        # document rather than clobbering it.
        for _ in range(3):
            with publication_lock:
                if cb.cancelled():
                    raise core.PipelineCancelled()
                if previous is None:
                    if os.path.exists(report_path):
                        raise CheckpointRuntimeError('report appeared during the scan; choose a new report')
                    before, result = None, initial
                else:
                    before, latest = _load(report_path)
                    if _validate_previous(latest, identity, source) != boundary:
                        raise CheckpointRuntimeError('checkpoint advanced during the scan; retry from the latest report')
                    if latest['render_state'] != previous['render_state']:
                        raise CheckpointRuntimeError('checkpoint timeline changed during the scan; retry from the latest report')
                    result = checkpoints.join_reports(latest, doc, end, source.total_frames,
                                                      completed=completed)
            with _staged_report(report_path, result) as staged:
                with publication_lock:
                    if cb.cancelled():
                        raise core.PipelineCancelled()
                    if previous is None:
                        changed = os.path.exists(report_path)
                    else:
                        try:
                            with open(report_path, 'rb') as current:
                                changed = current.read() != before
                        except OSError as exc:
                            raise CheckpointRuntimeError('checkpoint changed before publication') from exc
                    if changed:
                        continue
                    lease.check()
                    if _commit_staged is None:
                        os.replace(staged, os.path.abspath(report_path))
                    else:
                        _commit_staged(staged, os.path.abspath(report_path), result)
                    return result
        raise CheckpointRuntimeError('checkpoint changed repeatedly during publication; retry')
