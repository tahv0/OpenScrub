"""The private progress file of a stopped scan.

A detector-only scan keeps very little state from frame to frame: the raw
per-frame detections (tracking, smoothing and grouping run once after the
frame loop) and a few counters. This module stores that state in one
gzip-JSON file in the job folder, restores it exactly, and decides whether a
continued scan still matches the stopped one. Anything it does not recognise
is refused: a continued scan must never differ from an uninterrupted one.
"""
import dataclasses
import gzip
import hashlib
import json
import math
import os
import re
import time
from types import MappingProxyType

SCAN_PROGRESS_VERSION = 1
PROGRESS_NAME = "scan-progress.json.gz"
_STAGE = ".stage"


class ProgressError(ValueError):
    """The progress file is unreadable, corrupt or from another format."""


class ProgressMismatch(ProgressError):
    """The video, settings, models or OpenScrub changed since the stop."""

    def __init__(self, what):
        super().__init__("can't continue: " + what)
        self.what = what


# Settings that never change what a scan detects: transport paths, output and
# render choices, and the execution backend. Every other setting is identity.
EXCLUDED_SETTINGS = frozenset({
    "video",              # path: the content hash is identity instead
    "output",             # path
    "report",             # path
    "config",             # path: its values are already applied to args
    "batch",              # path
    "from_report",        # render path
    "overwrite",          # output
    "preview",            # render
    "encoder",            # output encoder
    "codec",              # output codec
    "out_quality",        # output
    "hdr_output",         # output dynamic range
    "mode",               # render cover style
    "mode_map",           # render cover style
    "coverage",           # render person cover
    "face_shape",         # render
    "draw_scores",        # render
    "pad",                # render padding
    "mute_audio_tracks",  # render audio
    "audio_lane_count",   # render audio
    "audio_redact",       # render audio
    "audio_redact_mode",  # render audio
    "audio_pii_apply",    # render audio
    "device",             # execution backend
})

# Settings holding a file path: their CONTENT is identity, never the path.
_FILE_SETTINGS = frozenset({"face_model", "plate_model", "person_model", "phrases",
                            "allow_names", "extra_names", "windows", "zones"})


def file_sha256(path):
    digest = hashlib.sha256()
    with open(path, "rb") as handle:
        for chunk in iter(lambda: handle.read(1 << 20), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _plain(value, where):
    """A JSON-portable copy of a settings value, refusing unknown types."""
    if value is None or isinstance(value, (bool, str)):
        return value
    if isinstance(value, int):
        return int(value)
    if isinstance(value, float):
        if not math.isfinite(value):
            raise ProgressError("setting %s is not a finite number" % where)
        return float(value)
    if isinstance(value, (list, tuple)):
        return [_plain(v, where) for v in value]
    if isinstance(value, (set, frozenset)):
        return sorted((_plain(v, where) for v in value), key=repr)
    if isinstance(value, dict):
        return {str(k): _plain(v, where) for k, v in sorted(value.items(), key=lambda kv: str(kv[0]))}
    if isinstance(value, re.Pattern):
        return {"regex": value.pattern, "flags": value.flags}
    if hasattr(value, "item") and callable(value.item):        # numpy scalar
        return _plain(value.item(), where)
    raise ProgressError("setting %s has an unsupported type %s" % (where, type(value).__name__))


def settings_identity(args):
    out = {}
    for key, value in sorted(vars(args).items()):
        if key in EXCLUDED_SETTINGS:
            continue
        if key in _FILE_SETTINGS:
            paths = value if isinstance(value, (list, tuple)) else [value]
            hashes = []
            for path in paths:
                if not path:
                    hashes.append(None)
                elif os.path.isfile(path):
                    hashes.append(file_sha256(path))
                else:
                    hashes.append("missing")
            out[key] = hashes if isinstance(value, (list, tuple)) else hashes[0]
            continue
        out[key] = _plain(value, key)
    return out


_WHAT = {
    "engine_version": "OpenScrub was updated",
    "format_version": "OpenScrub was updated",
    "input_sha256": "the video file changed",
    "scan_sha256": "the video file changed",
    "total_frames": "the video's frame count changed",
}


def compare_identity(saved, current):
    """Raise ProgressMismatch naming the first difference."""
    for key in sorted(set(saved) | set(current)):
        if key == "settings":
            continue
        if saved.get(key) != current.get(key):
            if key == "models":
                old, new = saved.get(key) or {}, current.get(key) or {}
                for kind in sorted(set(old) | set(new)):
                    if old.get(kind) != new.get(kind):
                        raise ProgressMismatch("the %s model changed" % kind)
            raise ProgressMismatch(_WHAT.get(key, "%s changed" % key))
    old, new = saved.get("settings") or {}, current.get("settings") or {}
    changed = sorted(k for k in set(old) | set(new) if old.get(k) != new.get(k))
    if changed:
        raise ProgressMismatch("scan settings changed: " + ", ".join(changed))


# --- detections -----------------------------------------------------------

def _scalar(value):
    if hasattr(value, "item") and callable(value.item) and not isinstance(value, (list, tuple)):
        value = value.item()
    return value


def _jsonable(value):
    """Tagged JSON for the value types a Detection holds."""
    value = _scalar(value)
    if value is None or isinstance(value, (bool, str, int)):
        return value
    if isinstance(value, float):
        if not math.isfinite(value):
            raise ProgressError("a detection holds a non-finite number")
        return value
    if isinstance(value, tuple):
        return {"t": [_jsonable(v) for v in value]}
    if isinstance(value, list):
        return {"l": [_jsonable(v) for v in value]}
    if isinstance(value, MappingProxyType):
        return {"mp": {k: _jsonable(v) for k, v in value.items()}}
    if isinstance(value, dict):
        if not all(isinstance(k, str) for k in value):
            raise ProgressError("a detection holds a dict with non-text keys")
        return {"d": {k: _jsonable(v) for k, v in value.items()}}
    raise ProgressError("a detection holds an unsupported %s" % type(value).__name__)


def _restore(obj):
    if obj is None or isinstance(obj, (bool, str, int, float)):
        return obj
    if isinstance(obj, dict) and len(obj) == 1:
        (tag, inner), = obj.items()
        if tag == "t":
            return tuple(_restore(v) for v in inner)
        if tag == "l":
            return [_restore(v) for v in inner]
        if tag == "mp":
            return MappingProxyType({k: _restore(v) for k, v in inner.items()})
        if tag == "d":
            return {k: _restore(v) for k, v in inner.items()}
    raise ProgressError("the progress file holds an unknown value")


def _classes():
    import openscrub
    return {"Detection": openscrub.Detection,
            "NarrowPlateDetection": openscrub.NarrowPlateDetection}


# Instance attributes a scan row may carry beyond the dataclass fields.
_EXTRA_ATTRS = frozenset({"manual_plate_quad", "_plate_policy_evidence"})


def encode_detection(d):
    classes = _classes()
    name = type(d).__name__
    if classes.get(name) is not type(d):
        raise ProgressError("unsupported detection type %s" % name)
    fields = {f.name for f in dataclasses.fields(d)}
    attrs = vars(d)
    unknown = set(attrs) - fields - _EXTRA_ATTRS
    if unknown:
        raise ProgressError("a detection carries unsaved state: %s" % ", ".join(sorted(unknown)))
    return {"type": name, "attrs": {k: _jsonable(v) for k, v in attrs.items()}}


def decode_detection(obj):
    try:
        cls = _classes()[obj["type"]]
        attrs = {k: _restore(v) for k, v in obj["attrs"].items()}
        fields = {f.name for f in dataclasses.fields(cls)}
        init = {k: v for k, v in attrs.items() if k in fields}
        row = cls(**init, manual_plate_quad=attrs.get("manual_plate_quad"))
        for key in set(attrs) - fields:
            if key not in _EXTRA_ATTRS:
                raise ProgressError("the progress file holds unknown detection state")
            setattr(row, key, attrs[key])
        return row
    except ProgressError:
        raise
    except (KeyError, TypeError, ValueError, AttributeError) as error:
        raise ProgressError("the progress file holds an invalid detection") from error


# --- the file ---------------------------------------------------------------

def save(path, state):
    """Replace the progress file atomically; never leaves a second copy."""
    stage = path + _STAGE
    try:
        os.remove(stage)
    except FileNotFoundError:
        pass
    data = json.dumps({"version": SCAN_PROGRESS_VERSION, "state": state},
                      allow_nan=False, separators=(",", ":")).encode("utf-8")
    try:
        with open(stage, "wb") as raw:
            with gzip.GzipFile(fileobj=raw, mode="wb", compresslevel=3, mtime=0) as handle:
                handle.write(data)
            raw.flush()
            os.fsync(raw.fileno())
        os.replace(stage, path)
    except BaseException:
        try:
            os.remove(stage)
        except OSError:
            pass
        raise
    if os.name == "posix":
        fd = os.open(os.path.dirname(os.path.abspath(path)), os.O_RDONLY)
        try:
            os.fsync(fd)
        finally:
            os.close(fd)


def load(path):
    try:
        with gzip.open(path, "rb") as handle:
            doc = json.loads(handle.read().decode("utf-8"))
    except FileNotFoundError:
        raise
    except (OSError, EOFError, ValueError, UnicodeDecodeError) as error:
        raise ProgressError("the saved progress is unreadable") from error
    if not isinstance(doc, dict) or doc.get("version") != SCAN_PROGRESS_VERSION \
            or not isinstance(doc.get("state"), dict):
        raise ProgressError("the saved progress is from another OpenScrub version")
    return doc["state"]


def remove(path):
    """Delete the progress file and any leftover stage file."""
    for name in (path, path + _STAGE):
        try:
            os.remove(name)
        except FileNotFoundError:
            pass


class ScanProgressControl:
    """How one scan run stops, autosaves and continues.

    The engine calls ``due()`` at each frame boundary and ``save()`` with
    its state; ``stop_requested`` is the web's stop signal.
    """

    def __init__(self, path, *, stop_requested, resume, autosave_seconds=300.0,
                 clock=time.monotonic):
        if not callable(stop_requested):
            raise TypeError("stop_requested must be callable")
        self.path = path
        self.stop_requested = stop_requested
        self.resume = bool(resume)
        self.autosave_seconds = autosave_seconds
        self.clock = clock
        self._last = clock()
        self.saved_frame = None
        self.total = None
        self.next_frame = 0      # the engine's next frame, set at each boundary
        self.autosave_disabled = False

    def autosave_due(self):
        if self.autosave_disabled or self.autosave_seconds is None:
            return False
        return self.clock() - self._last >= self.autosave_seconds

    def mark_saved(self, frame, total):
        self._last = self.clock()
        self.saved_frame, self.total = frame, total
