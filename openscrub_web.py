#!/usr/bin/env python3
"""
openscrub_web.py — browser interface for openscrub, usable across your LAN.

Run on an always-on machine:
    python openscrub_web.py                  # port 8384, prints access URL
    python openscrub_web.py --port 9000 --token mysecret

Then from any device on the LAN (laptop, phone), open the printed URL.
Workflow: upload a recording (or give a server-side path) -> scan runs on
the server (live preview + log) -> review every detection with thumbnails,
uncheck false positives, draw missed regions -> render -> download.

Security model: HTTPS by default (self-signed cert generated on first
run, or install your own). Pass --token <secret> to require an access
token on every request (carried in a cookie after the first visit);
without it the server runs open and trusts everyone on the network.
Either way this is *LAN-grade* protection for a trusted home/office
network — do not expose this port to the internet. Uploaded videos and
audit reports contain PII; the jobs folder inherits that sensitivity.

Jobs are processed one at a time (FIFO) so concurrent requests don't fight
over the GPU.
"""

import argparse
from copy import deepcopy
import json
import os
import queue
import secrets
import sqlite3
import shutil
import sys
import socket
import threading
import time
import uuid

import cv2
import numpy as np
from flask import (Flask, Request, Response, abort, jsonify, redirect, request,
                   send_file)

import openscrub
import stop_review
import learning_session
import video_learning
import learned_models
import learning_candidates
import plate_verifier
import zones_ui
import openscrub_logging as diagnostics
import finding_previews
import review_preview_index
import findings_web
import findings_ui
import plate_text_web


# Anchor to the script's own folder, NOT the process working directory —
# double-clicking a .py on Windows can launch with cwd=C:\Windows\system32
# Computed ONCE at import: the vault's atexit lock hook runs during
# interpreter teardown, where module globals like __file__ may already be
# gone (a real NameError silently skipped the shutdown lock and left job
# files in plaintext). A captured constant survives teardown.
_HERE = os.path.dirname(os.path.abspath(__file__))


def _data_root():
    """Writable data root. From a normal checkout/deploy: the script's own
    folder (unchanged behavior). When pip-installed (module lives inside
    site-packages) or frozen into an exe (PyInstaller under Program Files),
    use a per-user data dir instead — PII jobs and TLS keys must never be
    written into the install tree."""
    here = _HERE
    if ("site-packages" in here or "dist-packages" in here
            or getattr(sys, "frozen", False)):
        # Confine the env-derived root to the user's own profile before any
        # filesystem use: a hostile LOCALAPPDATA can't point PII job/key
        # writes at a system directory. The guard's exact shape (single
        # startswith, value adopted in its true branch) matches the engine's
        # user_data_dir — the one form CodeQL's barrier analysis recognizes.
        home = os.path.realpath(os.path.expanduser("~"))
        base = os.path.join(home, ".local", "share")
        env = os.environ.get("LOCALAPPDATA")
        if env:
            cand = os.path.realpath(env)
            if cand.startswith(home.rstrip(os.sep) + os.sep):
                base = cand
        root = os.path.join(base, "OpenScrub")
        os.makedirs(root, exist_ok=True)
        return root
    return here


JOBS_DIR = os.path.join(_data_root(), "openscrub_jobs")
# One-time migration from the pre-rebrand job store: carries over all prior
# jobs, reviews, and the learned-words allowlist.
_legacy_jobs = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                            "phi_blur_jobs")
if os.path.isdir(_legacy_jobs) and not os.path.isdir(JOBS_DIR):
    try:
        os.rename(_legacy_jobs, JOBS_DIR)
    except OSError:
        pass  # e.g. cross-device or perms: fall back to fresh dir
ZONES_PATH = os.path.join(_data_root(), "zones.json")
# which optional detection model is in use per kind: {"face": id, "plate": id}
# (missing/empty = the built-in default: YuNet for faces, auto for plates)
MODEL_SELECT_PATH = os.path.join(_data_root(), "model_select.json")


def load_model_select():
    try:
        with open(MODEL_SELECT_PATH, encoding="utf-8") as f:
            d = json.load(f)
            return d if isinstance(d, dict) else {}
    except FileNotFoundError:
        return {}
    except Exception:
        diagnostics.exception("settings_load_failed")
        return {}


def save_model_select(d):
    with open(MODEL_SELECT_PATH, "w", encoding="utf-8") as f:
        json.dump(d, f, indent=1)


def find_model_file(fname):
    """models/<fname> can live next to the code (folder deploys) or in the
    per-user data dir (pip / frozen installs download there)."""
    roots = [os.path.dirname(os.path.abspath(openscrub.__file__))]
    if openscrub.install_is_readonly():
        roots.append(openscrub.user_data_dir())
    for r in roots:
        p = os.path.join(r, "models", fname)
        if os.path.exists(p):
            return p
    return None
# One-time migration: zones.json used to live next to the code, which for
# pip installs meant site-packages (lost on upgrade) and for frozen installs
# would be read-only. Carry an existing file over to the data root.
_legacy_zones = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                             "zones.json")
if (_legacy_zones != ZONES_PATH and os.path.exists(_legacy_zones)
        and not os.path.exists(ZONES_PATH)):
    try:
        import shutil as _sh
        _sh.copy2(_legacy_zones, ZONES_PATH)
    except OSError:
        pass
CERT_DIR = os.path.join(_data_root(), "certs")
CUSTOM_CERT = os.path.join(CERT_DIR, "custom_cert.pem")
CUSTOM_KEY = os.path.join(CERT_DIR, "custom_key.pem")
AUTO_CERT = os.path.join(CERT_DIR, "auto_cert.pem")
AUTO_KEY = os.path.join(CERT_DIR, "auto_key.pem")


def ensure_self_signed():
    """Generate a long-lived self-signed certificate once, with SANs for
    localhost and this machine's LAN IP so browsers tie it to the URL used."""
    if os.path.exists(AUTO_CERT) and os.path.exists(AUTO_KEY):
        return
    from cryptography import x509
    from cryptography.x509.oid import NameOID
    from cryptography.hazmat.primitives import hashes, serialization
    from cryptography.hazmat.primitives.asymmetric import rsa
    import datetime, ipaddress
    os.makedirs(CERT_DIR, exist_ok=True)
    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    name = x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, "openscrub")])
    sans = [x509.DNSName("localhost"),
            x509.IPAddress(ipaddress.ip_address("127.0.0.1"))]
    try:
        sans.append(x509.IPAddress(ipaddress.ip_address(lan_ip())))
    except Exception:
        pass
    now = datetime.datetime.now(datetime.timezone.utc)
    cert = (x509.CertificateBuilder()
            .subject_name(name).issuer_name(name)
            .public_key(key.public_key())
            .serial_number(x509.random_serial_number())
            .not_valid_before(now - datetime.timedelta(days=1))
            .not_valid_after(now + datetime.timedelta(days=3650))
            .add_extension(x509.SubjectAlternativeName(sans), critical=False)
            .sign(key, hashes.SHA256()))
    with open(AUTO_KEY, "wb") as f:
        f.write(key.private_bytes(
            serialization.Encoding.PEM,
            serialization.PrivateFormat.TraditionalOpenSSL,
            serialization.NoEncryption()))
    with open(AUTO_CERT, "wb") as f:
        f.write(cert.public_bytes(serialization.Encoding.PEM))
    try:
        os.chmod(AUTO_KEY, 0o600)
    except Exception:
        pass


def active_cert_pair():
    if os.path.exists(CUSTOM_CERT) and os.path.exists(CUSTOM_KEY):
        return CUSTOM_CERT, CUSTOM_KEY, "custom"
    ensure_self_signed()
    return AUTO_CERT, AUTO_KEY, "self-signed"
class _OpenScrubRequest(Request):
    @property
    def max_content_length(self):
        # A property override also supports Flask versions where the base
        # request limit is read-only. It applies before multipart parsing.
        configured = super().max_content_length
        if self.method == "POST" and self.path == "/api/jobs/learned-models/import":
            limit = learned_models.MAX_MODEL_BYTES + 1024 * 1024
            return min(configured, limit) if configured is not None else limit
        return configured


app = Flask(__name__)
app.request_class = _OpenScrubRequest


def _max_upload_bytes(cli_value=None):
    """Upload cap in bytes, or None for unlimited. Priority:
    --max-upload-gb > $OPENSCRUB_MAX_UPLOAD_GB > 8 GB default.
    0 (either source) = unlimited. A real 18 GB plate-removal job hit the
    hard-coded cap as a bare '413 Request Entity Too Large' with no path
    forward — the limit is now a dial, and the 413 explains the dial."""
    raw = cli_value if cli_value is not None else \
        os.environ.get("OPENSCRUB_MAX_UPLOAD_GB", "")
    try:
        gb = float(raw)
    except (TypeError, ValueError):
        gb = 8.0
    if gb == 0:
        return None                      # explicit 0 = unlimited
    if gb < 0:
        gb = 8.0
    return int(gb * 1024 ** 3)


app.config["MAX_CONTENT_LENGTH"] = _max_upload_bytes()   # default 8 GB


@app.errorhandler(413)
def _too_large(e):
    if request.method == "POST" and request.path == "/api/jobs/learned-models/import":
        return jsonify({"error": "Model package exceeds this server's model upload limit "
                                 "(maximum 256 MiB of model data)."}), 413
    cap = app.config.get("MAX_CONTENT_LENGTH")
    gb = cap / 1024 ** 3 if cap else 0
    return jsonify({"error":
        "upload exceeds this server's %.0f GB limit. Raise it with "
        "--max-upload-gb N (or OPENSCRUB_MAX_UPLOAD_GB=N in Docker, "
        "0 = unlimited) and restart — or better for very large files: "
        "put the file where the server can read it (Docker: a mounted "
        "folder) and use the 'path on the server' box instead of "
        "uploading through the browser." % gb}), 413


def _disk_free(path):
    """Free bytes on the filesystem holding `path` (own def: tests stub it,
    and every caller shares one failure mode)."""
    import shutil as _sh
    return _sh.disk_usage(path).free


def _upload_disk_error(content_length):
    """None, or a refusal message for an upload of `content_length` bytes
    that cannot fit on disk. Uploads are spooled through the system temp
    dir by the form parser and then copied into the job dir, so BOTH
    filesystems need room — double on a shared one — plus 1 GB headroom.
    Issue #16: each retry of a failed 18 GB job re-uploaded the file into
    a fresh job dir until the disk silently filled. Unmeasurable free
    space never blocks (same rule as the scan-copy verifier: the guard
    acts only on a measured certainty)."""
    cl = int(content_length or 0)
    if cl <= 0:
        return None
    margin = 1 << 30
    import tempfile
    tmp = tempfile.gettempdir()
    try:
        same = os.stat(JOBS_DIR).st_dev == os.stat(tmp).st_dev
    except OSError:
        same = True                       # can't tell -> assume shared
    try:
        if same:
            short = _disk_free(JOBS_DIR) < 2 * cl + margin
        else:
            short = (_disk_free(JOBS_DIR) < cl + margin
                     or _disk_free(tmp) < cl + margin)
    except OSError:
        return None
    if not short:
        return None
    try:
        free_gb = _disk_free(JOBS_DIR) / 1024 ** 3
    except OSError:
        free_gb = 0.0
    return ("not enough disk space on the server for this upload "
            "(%.1f GB upload, %.1f GB free where jobs are stored — an "
            "upload needs room for a temporary copy too). Delete old "
            "jobs (each keeps its upload and output until deleted), or "
            "use the 'path on the server' box, which reads the file in "
            "place without copying it." % (cl / 1024 ** 3, free_gb))


TOKEN = None
JOBS = {}          # id -> job dict
JOBS_LOCK = threading.Lock()
WORK_Q = queue.Queue()


# ----------------------------------------------------------------------------
# Job model
# ----------------------------------------------------------------------------

MEDIA_EXTS = {".mp4", ".mov", ".mkv", ".avi", ".webm", ".m4v", ".mpg",
              ".mpeg", ".wmv", ".ts", ".mts", ".m2ts", ".flv", ".3gp"}


def server_path_error(p):
    """Validate a user-supplied server-side media path. The path picker is a
    deliberate feature (process a file already on this machine/NAS), but the
    value is request data, so it is confined BEFORE any filesystem use:
    canonicalized, restricted to a known video extension, and — when
    $OPENSCRUB_MEDIA_ROOT is set — required to live inside that directory
    tree. Returns an error string, or None if the path is acceptable."""
    # canonicalize first, then apply the containment guard up front so the
    # confinement precedes EVERY filesystem access (path-injection barrier).
    # The guard is unconditional: with $OPENSCRUB_MEDIA_ROOT set, the path
    # must live inside that tree (real confinement — set it in any deployment
    # where the browser UI shouldn't reach the whole disk). Without it, the
    # picker is deliberately unrestricted (process any video already on this
    # machine/NAS is the feature), so the allowed prefix degrades to the
    # path's own filesystem root — the canonicalize+check still runs on
    # every request path rather than only on the configured branch.
    # NOTE the guard is a SINGLE startswith with an early return — the one
    # shape CodeQL's path-injection barrier analysis recognizes; compound
    # conditions defeat its dominance check. (The media root itself is
    # correctly rejected: a directory is never a valid video file.)
    p = os.path.realpath(p)
    root = os.environ.get("OPENSCRUB_MEDIA_ROOT")
    r = os.path.realpath(root) if root else os.path.realpath(
        os.path.splitdrive(p)[0] + os.sep)
    if not p.startswith(r.rstrip(os.sep) + os.sep):
        return "server path is outside OPENSCRUB_MEDIA_ROOT"
    if os.path.splitext(p)[1].lower() not in MEDIA_EXTS:
        return ("server path must be a video file ("
                + ", ".join(sorted(MEDIA_EXTS)) + ")")
    if not os.path.isfile(p):
        return "server path not found or not a file"
    return None


def learned_models_root():
    """Reserved job-store directory: included in the vault, never in retention."""
    return os.path.join(JOBS_DIR, "learned_plate_models")


def new_job(video_path, options, name):
    jid = uuid.uuid4().hex[:12]
    jdir = os.path.join(JOBS_DIR, jid)
    os.makedirs(jdir, exist_ok=True)
    job = {
        "id": jid, "dir": jdir, "video": video_path, "name": name,
        "options": dict(options), "phase": "queued", "progress": 0.0,
        "eta": None, "size": 0,
        "log": [], "error": None, "output": None, "created": time.time(),
        "cancel": threading.Event(), "stop": threading.Event(),
        "stats": {},
    }
    try:
        selected = job["options"].get("learned_plate_model", "")
        if not isinstance(selected, str):
            raise learned_models.ModelError("Choose a valid learned plate model.")
        if selected:
            with _REVIEW_EDIT_LOCK, _REVIEW_WORK_LOCK:
                if vault_locked():
                    abort(423, description="Unlock the vault before selecting a model.")
                job["refinement"] = learned_models.snapshot_model(
                    learned_models_root(), selected, jdir,
                    mode=job["options"].get("learned_plate_model_mode"))
                job["options"]["learned_plate_model_mode"] = learned_models.load_selection(
                    jdir, job["refinement"])
    except Exception:
        import shutil
        shutil.rmtree(jdir, ignore_errors=True)
        raise
    diagnostics.attach_job(job)
    diagnostics.event("job_created", job)
    with JOBS_LOCK:
        JOBS[jid] = job
    return job


def export_filenames(job):
    """Names used by both Save As and the regular download endpoints.

    Use the actual rendered container suffix (e.g. MKV instead of MP4).
    """
    stem = os.path.splitext(job["name"])[0]
    ext = os.path.splitext(job.get("output") or "")[1] or ".mp4"
    return stem + "_redacted" + ext, stem + "_audit.json"


def job_public(job):
    video_name, report_name = export_filenames(job)
    return {k: job[k] for k in ("id", "name", "phase", "progress", "error",
                                "stats")} | {
        "eta": job.get("eta"),      # .get(): jobs rehydrated from disk lack it
        # input size: lets the editor warn before re-uploading a file that
        # is ALREADY on the server (issue #16 — each retry re-uploaded the
        # same 18 GB until the disk filled)
        "size": job.get("size") or 0,
        "log_tail": job["log"][-30:],
        "log_len": len(job["log"]),
        "has_output": bool(job["output"] and os.path.exists(job["output"])),
        "download_name": video_name,
        "report_name": report_name,
        "stop_pending": bool(job.get("stop") and job["stop"].is_set()),
        "checkpoint_frame": job.get("checkpoint_frame"),
        "checkpoint_total": job.get("checkpoint_total"),
        "learning": job.get("learning"),
        "refinement": job.get("refinement"),
        "verification": job.get("verification"),
        "verification_history": job.get("verification_history"),
        "activity": job.get("activity"),
        "preview": job.get("preview"),
        "server_time": time.time(),
        "sections_revision": job.get("sections_revision", 0),
        "section": job.get("section"),
        "kind": job.get("kind", "video"),
        "training_result": job.get("training_result"),
        "review_queue": job.get("review_queue"),
        "plate_text_search": job.get("plate_text_search"),
    }


def _publish_preview_jpeg(path, image, quality):
    """Publish a complete preview without changing an open reader's bytes."""
    ok, encoded = cv2.imencode(".jpg", image, [cv2.IMWRITE_JPEG_QUALITY, quality])
    if not ok:
        return False
    temporary = None
    try:
        with tempfile.NamedTemporaryFile(dir=os.path.dirname(path),
                                         suffix=".jpg", delete=False) as out:
            temporary = out.name
            out.write(encoded.tobytes())
        os.replace(temporary, path)
        return True
    finally:
        if temporary and os.path.exists(temporary):
            os.unlink(temporary)


class WebCallbacks(openscrub.Callbacks):
    wants_frames = True
    wants_finding_previews = True

    def __init__(self, job):
        diagnostics.attach_job(job)
        self.job = job
        self._last_frame = 0.0
        self._stage = None          # ETA state: current stage,
        self._t0 = 0.0              # when it started,
        self._cur0 = 0              # its first cur value,
        self._eta = None            # and the smoothed estimate
        self._rate_points = []      # bounded recent stage progress samples
        self._last_rate_log = 0.0
        self._preview_groups = set()
        self._preview_stats = None

    def log(self, msg):
        self.job["log"].append(msg)

    def progress(self, stage, cur, total):
        context = self.job.get("options", {}).get("section_context")
        if context and stage == "scan":
            cur, total = max(0, min(cur, context[1])-context[0]), context[1]-context[0]
        diagnostics.progress(self.job, stage, cur, total)
        now = time.time()
        old = self.job.get("activity") or {}
        changed = old.get("stage") != stage
        advanced = changed or cur > old.get("done", -1)
        unit = "tracks" if stage == "post" else "frames"
        activity = dict(stage=stage, done=cur, total=total, unit=unit,
                        started_at=now if changed else old.get("started_at", now),
                        updated_at=now,
                        last_progress_at=now if advanced else old.get("last_progress_at", now))
        self.job["activity"] = activity
        if self.job.get("phase") == "learning":
            label = {"scan": "rescanning", "post": "postprocessing", "refine": "refining"}.get(stage)
            if label:
                learning_session.update_learning(self.job, stage=label,
                    message={"scan":"Rescanning video", "post":"Finalizing tracked detections",
                             "refine":"Applying learned plate masks"}[stage],
                    done=cur, total=total, unit=unit)
        # scan frame loop -> first 45% of the bar; "post" (dense-track
        # smoothing after the loop — previously a silent stall) -> 45-50%;
        # render -> back half. Jobs without a post stage jump 45 -> 50,
        # which reads as instant rather than stuck.
        # Rounded to 5 decimals, not 3: on a long slow scan 3-decimal
        # quantization froze the bar for 30s+ stretches, and the old
        # client-side ETA (extrapolated from bar movement) blanked out.
        stages = ({"scan": (0, 0.38), "post": (0.38, 0.04),
                   "refine": (0.42, 0.08)}
                  if self.job.get("options", {}).get("learned_plate_model")
                  else {"scan": (0, 0.45), "post": (0.45, 0.05)})
        base, span = stages.get(stage, (0.5, 0.5))
        self.job["progress"] = round(base + span * cur / max(total, 1), 5)

        # ETA uses a rolling recent rate once enough recent history exists.
        # The previous whole-stage average hid progressive slowdowns for hours:
        # an early fast prefix kept the ETA optimistic long after current
        # throughput had fallen. Keep the whole-stage rate as a fallback for
        # startup, but prefer roughly the last two minutes during long scans.
        now = time.time()
        if stage != self._stage:
            self._stage, self._t0, self._cur0 = stage, now, cur
            self._eta = None
            self._rate_points = [(now, cur)]
            self._last_rate_log = now
            self.job["eta"] = None
            return

        if (not self._rate_points or now - self._rate_points[-1][0] >= 5.0
                or cur >= total):
            self._rate_points.append((now, cur))
            cutoff = now - 120.0
            while len(self._rate_points) > 2 and self._rate_points[0][0] < cutoff:
                self._rate_points.pop(0)

        done, elapsed = cur - self._cur0, now - self._t0
        average_rate = done / elapsed if done > 0 and elapsed >= 3.0 else 0.0
        recent_rate = 0.0
        recent_seconds = 0.0
        if len(self._rate_points) >= 2:
            recent_seconds = self._rate_points[-1][0] - self._rate_points[0][0]
            recent_done = self._rate_points[-1][1] - self._rate_points[0][1]
            if recent_done > 0 and recent_seconds > 0:
                recent_rate = recent_done / recent_seconds
        rate = recent_rate if recent_seconds >= 20.0 and recent_rate > 0 else average_rate

        if rate > 0:
            activity["rate_per_second"] = round(rate, 4)
            activity["rate_window_seconds"] = round(
                recent_seconds if recent_seconds >= 20.0 else elapsed, 1)
        if cur < total and rate > 0:
            rem = (total - cur) / rate
            self._eta = (rem if self._eta is None
                         else 0.35 * self._eta + 0.65 * rem)
            self.job["eta"] = round(self._eta)
        else:
            self._eta = None
            self.job["eta"] = None

        if (stage == "scan" and rate > 0
                and now - self._last_rate_log >= 300.0):
            self._last_rate_log = now
            diagnostics.event("scan_throughput", self.job,
                frame=cur, total=total, recent_fps=round(rate, 4),
                average_fps=round(average_rate, 4),
                eta_minutes=round((total-cur)/rate/60, 1) if cur < total else 0)

    def scan_frame(self, frame, t, found):
        now = time.time()
        if now - self._last_frame < 0.4:   # throttle disk writes
            return
        self._last_frame = now
        h, w = frame.shape[:2]
        scale = 720 / w
        small = cv2.resize(frame, (720, int(h * scale)))
        if _publish_preview_jpeg(os.path.join(self.job["dir"], "preview.jpg"), small, 70):
            self.job["preview"] = dict(revision=uuid.uuid4().hex[:12], updated_at=now,
                                        source_time=t, found=found)

    def scan_findings(self, frame, frame_index, fps, detections):
        try:
            self._preview_stats = finding_previews.capture(
                self.job['dir'], frame, frame_index, fps, detections,
                seen_groups=self._preview_groups,
                previous_stats=self._preview_stats)
            self.job['review_queue'] = self._preview_stats
        except Exception:
            # Review caching must not turn an otherwise valid scan into failure.
            if not self.job.get('review_cache_error'):
                diagnostics.exception('compact_finding_preview_failed', self.job)
                self.job['review_cache_error'] = True
                self.log('Compact review preview unavailable; source previews remain available after scanning.')

    def cancelled(self):
        return self.job["cancel"].is_set()

    def stop_requested(self):
        return self.job["stop"].is_set()

def _job_mask_options(job):
    """Return the exact option values passed to the render command."""
    options = job.get("options") or {}
    face = options.get("face_shape")
    return (options.get("coverage", "tight"), options.get("pad", 8),
            face if face in ("ellipse", "rect") else "ellipse")


def build_args(job, for_render=False):
    o = job["options"]
    jdir = job["dir"]
    coverage, pad, face_shape = _job_mask_options(job)
    plate_coverage = o.get("plate_coverage", "full")
    if plate_coverage not in ("full", "narrow"):
        raise ValueError("invalid plate coverage")
    try:
        plate_margin = float(o.get("plate_narrow_margin", 0))
        if not np.isfinite(plate_margin) or plate_margin < 0:
            raise ValueError()
    except (ValueError, TypeError):
        raise ValueError("invalid narrow plate margin")
    argv = [job["video"],
            "--plate-coverage", plate_coverage,
            "--plate-narrow-margin", str(plate_margin),
            "--engine", o.get("engine", "auto"),
            "--device", o.get("device", "auto"),
            "--encoder", o.get("encoder", "auto"),
            "--mode", o.get("mode", "blur"),
            "--coverage", coverage,
            "--mode-map", o.get("mode_map", ""),
            "--sample-interval", str(o.get("sample_interval", 0.5)),
            "--scan-trigger", str(o.get("scan_trigger", 60)),
            "--pad", str(pad),
            "--bridge-gap", str(o.get("bridge_gap", 4.0)),
            "--face-expand", str(o.get("face_expand", 0.15)),
            "--face-threshold", str(o.get("face_threshold", 0.6)),
            "--plate-threshold", str(o.get("plate_threshold", 0.35)),
            "--detect-scale", str(o.get("detect_scale", 1.0)),
            "--skip-start", str(o.get("skip_start", 0)),
            "--skip-end", str(o.get("skip_end", 0)),
            "--clip-frac", o.get("clip_frac", "") or "",
            "--detect-windows-frac", o.get("detect_windows_frac", "") or "",
            "--mute-audio-tracks", o.get("mute_tracks", "") or "",
            *(["--audio-lane-count", str(int(o["audio_lanes"]))]
              if isinstance(o.get("audio_lanes"), int)
              and not isinstance(o.get("audio_lanes"), bool)
              and 0 < o["audio_lanes"] < 64 else []),
            "--hdr-output", (o.get("hdr_output")
                             if o.get("hdr_output") in ("match", "sdr")
                             else "match"),
            "--codec", (o.get("codec")
                        if o.get("codec") in ("h264", "hevc") else "h264"),
            "--out-quality", (o.get("out_quality")
                              if o.get("out_quality") in
                              ("archival", "balanced", "share")
                              else "archival"),
            "--face-shape", face_shape,
            "--scan-speed", (o.get("scan_speed")
                             if o.get("scan_speed") in openscrub.SCAN_SPEEDS
                             else "thorough"),
            "--categories", o.get("categories",
                                  "name,dob,phone,ssn,email,address,card,apikey,ipaddr,plate,face,person"),
            "-o", os.path.join(jdir, "output."
                               + (o.get("out_format", "mp4")
                                  if o.get("out_format") in ("mp4", "mov", "mkv")
                                  else "mp4")),
            "--report", os.path.join(jdir, "report.json")]
    # user-defined regex categories ride along on every job; the engine only
    # activates the ones whose id is in --categories
    for c in load_custom_cats():
        argv += ["--custom-regex", "%s=%s" % (c["id"], c["regex"])]
    # selected detection models (Detection models panel). A selected id
    # whose file is missing falls back to the engine default silently-safe
    # ladder (YuNet / plate auto-search).
    sel = load_model_select()
    for kind, flag in (("face", "--face-model"), ("plate", "--plate-model"),
                       ("person", "--person-model")):
        mid = sel.get(kind)
        if mid:
            p = find_model_file("%s.onnx" % mid)
            if p:
                argv += [flag, p]
    if o.get("no_memory"):
        argv.append("--no-memory")
    if o.get("no_ner"):
        argv.append("--no-ner")
    if o.get("preview_mode"):
        argv.append("--preview")
    if o.get("dense_faces"):
        argv.append("--dense-faces")
    if o.get("face_heads"):
        argv.append("--face-heads")
    if o.get("audio_pii"):
        argv.append("--audio-pii")
    if o.get("draw_scores"):
        argv.append("--draw-scores")
    # unified Scan Setup jobs: stacked detection windows (fractions of
    # duration, resolved server-side by the engine) with per-window
    # categories + zones travel as a windows.json inside the job dir
    if o.get("windows"):
        wpath = os.path.join(jdir, "windows.json")
        with open(wpath, "w", encoding="utf-8") as f:
            json.dump({"windows": o["windows"],
                       "ignore": o.get("ignore_zones") or []}, f)
        argv += ["--windows", wpath]
    if o.get("use_zones", True) and os.path.exists(ZONES_PATH):
        try:
            with open(ZONES_PATH, encoding="utf-8") as f:
                if json.load(f):
                    argv += ["--zones", ZONES_PATH]
        except Exception:
            diagnostics.exception("detection_zone_load_failed", job)
    server_allow = os.path.join(JOBS_DIR, "allowlist.txt")
    for kind in ("allow_names", "extra_names"):
        text = (o.get(kind) or "").strip()
        if kind == "allow_names" and os.path.exists(server_allow):
            text = (text + "\n" + open(server_allow, encoding="utf-8").read()).strip()
        if text:
            p = os.path.join(jdir, kind + ".txt")
            with open(p, "w", encoding="utf-8") as f:
                f.write(text)
            argv += ["--" + kind.replace("_", "-"), p]
    # ignore zones (drawn in the zone editor) apply to every job,
    # independent of the "apply detection zones" checkbox
    try:
        if os.path.exists(ZONES_PATH):
            with open(ZONES_PATH, encoding="utf-8") as f:
                for r in (json.load(f).get("ignore") or []):
                    argv += ["--ignore-region", "%s,%s,%s,%s" % tuple(r)]
    except Exception:
        diagnostics.exception("ignore_zone_load_failed", job)
    if for_render:
        argv += ["--from-report", os.path.join(jdir, "report.json")]
    parser = openscrub.build_parser()
    args = openscrub._prep_args(parser.parse_args(argv), parser)
    if o.get("section_range"):
        args.section_range = tuple(o["section_range"])
        args.clip_frac = ""
    if o.get("learned_plate_model") and not for_render:
        _selected_plate_model(job)
        args.plate_learning_exact = True
    return args


def _selected_plate_model(job):
    """The pinned artifact and durable mode, never a mode guessed on restart."""
    meta, data = learned_models.load_snapshot(job["dir"])
    selected = job.get("options", {}).get("learned_plate_model")
    if selected and selected != meta["id"]:
        raise learned_models.ModelError("The selected job model does not match its saved copy.")
    mode = learned_models.load_selection(job["dir"], meta)
    job.setdefault("options", {}).update(learned_plate_model=meta["id"],
                                        learned_plate_model_mode=mode)
    return meta, data, mode


def _recover_plate_model(job):
    """Keep damaged selections visible and fail closed when retrying/resuming."""
    if (not job.get("options", {}).get("learned_plate_model") and
            not os.path.lexists(os.path.join(job["dir"], "plate_model"))):
        return
    try:
        meta, _, _ = _selected_plate_model(job)
        job.setdefault("refinement", meta)
    except learned_models.ModelError as error:
        job["options"]["learned_plate_model"] = "unavailable"
        job["phase"] = "error"
        job["error"] = "The saved learned model selection cannot be recovered: " + str(error)


def _verifier_audit(doc, model_record, assessment, mode, stats, frame_range=None):
    record = dict(model_record, mode=mode, assessment=assessment, inference=stats)
    start, end = frame_range or (0, len(doc["render_state"]["cum"]))
    record["scope"] = {"start_frame": start, "end_frame": end,
                       "fps": doc["render_state"]["fps"]}
    doc["verification"] = record
    for row in doc["detections"]:
        marker = row.get("plate_verification")
        if marker and "model_sha256" not in marker:
            marker.update(model_sha256=model_record["model_sha256"])
    return record


def _model_frame_range(job, doc):
    """Intersect section context with the prefix actually scanned so far."""
    context = job.get("options", {}).get("section_context")
    if not context:
        return None
    if (not isinstance(context, (tuple, list)) or len(context) != 2 or
            any(type(value) is not int for value in context) or
            not 0 <= context[0] < context[1]):
        raise ValueError("Section bounds must be two ordered integer source frames")
    end = len(doc["render_state"]["cum"])
    checkpoint = doc.get("stop_review") or {}
    if checkpoint.get("state") == "paused":
        end = min(end, stop_review.validate_resume(doc)["next_frame"])
    return min(context[0], end), min(context[1], end)


def _run_plate_model(job, video, doc, model, mode, *, threshold=None,
                     assessment=None, progress=None):
    frame_range = _model_frame_range(job, doc)
    if job["cancel"].is_set():
        raise InterruptedError("Plate model check cancelled; previous review retained")
    if frame_range is not None and frame_range[0] == frame_range[1]:
        # A Stop request may precede the section context. Preserve that valid
        # checkpoint without decoding or claiming checks on unscanned frames.
        stats = dict(model_calls=0, decoded_frames=0)
        stats.update(dict(refined=0, disagreements=0) if mode == "refine" else
                     dict(checked=0, suggested=0, suppressed=0, kept=0, human_preserved=0))
        return deepcopy(doc), stats, frame_range
    options = dict(cancelled=job["cancel"].is_set, progress=progress)
    if frame_range is not None:
        options["frame_range"] = frame_range
    if mode == "refine":
        result, stats = video_learning.refine_report(video, doc, model, threshold=threshold, **options)
    else:
        result, stats = plate_verifier.review_report(video, doc, model, assessment, mode=mode, **options)
    return result, stats, frame_range


def apply_selected_plate_model(job, chunk):
    """Apply the selected mode to fresh proposals; reviewed rows merge afterward."""
    selected = job.get("options", {}).get("learned_plate_model")
    if not selected:
        return chunk
    meta, data, mode = _selected_plate_model(job)
    cb = WebCallbacks(job)
    cb.log("Applying learned plate model: " + meta["name"])
    model = video_learning.CropRefiner(data)
    try:
        refined, stats, frame_range = _run_plate_model(
            job, chunk["provenance"]["input"], chunk, model, mode,
            threshold=meta["threshold"], assessment=meta["validation"],
            progress=lambda cur, total: cb.progress("refine", cur, total))
    except InterruptedError as error:
        raise openscrub.PipelineCancelled() from error
    record = {key: meta[key] for key in
              ("id", "name", "contract", "model_sha256", "input_size", "threshold")}
    record.update(schema=meta["schema"], kind=meta["kind"], mode=mode, inference=stats)
    refined["refinement"] = record
    job["refinement"] = record
    if mode == "refine":
        cb.log("Learned model applied: %d mask refinements, %d uncertain proposals kept "
               "with original coverage." % (stats["refined"], stats["disagreements"]))
    else:
        job["verification"] = _verifier_audit(
            refined, record, meta["validation"], mode, stats,
            frame_range=frame_range)
        cb.log("Secondary plate model checked %d proposals: %d suggested false positives, "
               "%d filtered; %d human decisions preserved." %
               (stats["checked"], stats["suggested"], stats["suppressed"], stats["human_preserved"]))
    return refined


def worker():
    while True:
        jid, action = WORK_Q.get()
        with JOBS_LOCK:
            job = JOBS.get(jid)
        if job is None:
            diagnostics.event("queued_job_missing", job_id=jid, action=action, level=30)
            WORK_Q.task_done()
            continue
        cb = WebCallbacks(job)
        log_context = diagnostics.bind_job(job)
        diagnostics.start_job(job, action)
        try:
            if action == "learn_examples":
                findings_web.perform_training(job)
            elif action == "learn":
                perform_learning(job)
            elif action == "verify":
                perform_verification(job)
            elif action == "plate_text":
                plate_text_web.perform(job)
            elif action in ("scan", "resume"):
                resuming = action == "resume"
                if not resuming:
                    cache = os.path.join(job['dir'], 'compact_previews')
                    if os.path.isdir(cache) and not os.path.islink(cache):
                        shutil.rmtree(cache)
                    job.pop('review_queue', None)
                    job.pop('review_cache_error', None)
                job["phase"] = "scanning"
                job["preview"] = None
                job["activity"] = None
                args = build_args(job)
                previous = None
                old_frame = 0
                if resuming:
                    previous = _load_job_report(job)
                    meta = stop_review.validate_resume(previous)
                    old_frame = int(meta["next_frame"])
                    if previous["provenance"]["input_sha256"] != openscrub.sha256_file(
                            job["video"]):
                        raise stop_review.CheckpointError(
                            "Video changed after checkpoint; resume refused")
                    # Re-scan only a one-second overlap for onset continuity.
                    # Already reviewed findings win on the older side.
                    args.resume_start = max(0.0, old_frame / float(meta["fps"]) - 1.0)
                    job["log"].append("      resuming near %.2fs (1s overlap)"
                                      % (old_frame / float(meta["fps"])))
                state = openscrub.run_scan(args, cb)
                report_path = os.path.join(job["dir"], "report.json")
                staging_path = os.path.join(job["dir"], ".scan-chunk.json")
                try:
                    openscrub.write_report(staging_path, args, state)
                    with open(staging_path, encoding="utf-8") as f:
                        chunk = json.load(f)
                    chunk = apply_selected_plate_model(job, chunk)
                    chunk, restored = findings_web.library.apply_to_report(findings_web.root(), chunk)
                    if restored.get('applied', 0):
                        cb.log('Restored saved confirmed findings for this video: %d' % restored['applied'])
                    if job.get("section") and state.get("stop_at_frame") is None:
                        chunk = _SECTIONS.finish_scan(job, chunk)
                    end_frame = state.get("stop_at_frame")
                    total_frames = int(state["total_frames"])
                    if resuming:
                        if end_frame is not None and end_frame <= old_frame:
                            combined = previous  # stop request before new work
                        else:
                            combined = stop_review.join_reports(
                                previous, chunk,
                                int(end_frame) if end_frame is not None
                                else len(state["cum"]),
                                total_frames, completed=end_frame is None)
                            for key in ("video_sections", "source_identity", "range_provenance", "render_required", "preview_revision"):
                                if key in previous:
                                    combined[key] = previous[key]
                    elif end_frame is not None:
                        combined = stop_review.with_checkpoint(
                            chunk, end_frame, total_frames, job["options"])
                    else:
                        combined = chunk
                    # Never replace the last good checkpoint until the
                    # continuation scan AND postprocessing have both passed.
                    stop_review.atomic_report(report_path, combined)
                    try:
                        # Vault encryption and index publication must not touch
                        # the same job files concurrently.
                        with _REVIEW_CACHE_LOCK:
                            if not vault_locked():
                                review_preview_index.prepare(report_path, combined)
                    except Exception:
                        diagnostics.exception("review_index_build_failed", job)
                    try:
                        cache_stats = _reconcile_compact_previews(job, combined)
                        if cache_stats.get("linked"):
                            cb.log("      review cache: linked %d scan-time picture(s) "
                                   "to final tracked findings" % cache_stats["linked"])
                    except Exception:
                        diagnostics.exception("compact_preview_reconcile_failed", job)
                    for key in ("verification", "verification_history"):
                        if key in combined:
                            job[key] = combined[key]
                        else:
                            job.pop(key, None)
                finally:
                    if os.path.exists(staging_path):
                        os.remove(staging_path)
                job["stop"].clear()
                meta = combined.get("stop_review")
                job["checkpoint_frame"] = (meta or {}).get("next_frame")
                job["checkpoint_total"] = (meta or {}).get("total_frames")
                job["stats"] = state["stats"]
                if meta:
                    job["log"].append(
                        "      saved checkpoint %d/%d frames; prior decisions "
                        "and four-corner polygons retained" %
                        (meta["next_frame"], meta["total_frames"]))
                else:
                    job["log"].append(
                        "      full scan complete; prior review edits retained")
                # Representative compact previews were captured from decoded scan
                # frames. Cold legacy images decode lazily once; do not reopen
                # the entire video in a second thumbnail-generation pass.
                try:
                    prov = _load_job_report(job).get("provenance", {})
                    if ((prov.get("vfr_normalized") or meta)
                            and os.path.exists(prov.get("input", ""))):
                        job["video"] = prov["input"]
                        job["log"].append(
                            "using CFR-normalized file for previews/thumbnails")
                except Exception:
                    diagnostics.exception("preview_source_selection_failed", job)
                if meta:
                    job["phase"] = "paused"
                elif (not resuming and job["options"].get("skip_review")):
                    job["log"].append("review skipped — rendering all detections")
                    job["phase"] = "review"
                    WORK_Q.put((jid, "render"))
                else:
                    job["phase"] = "review"
                job["progress"] = 0.5
                job["eta"] = None
            elif action == "render":
                job["phase"] = "rendering"
                args = build_args(job, for_render=True)
                review_doc = _load_job_report(job)
                try:
                    res = openscrub.run_pipeline(args, cb)
                    rendered_doc = learning_session.preserve_render_review(
                        review_doc, _load_job_report(job))
                    for key in ("source_identity", "video_sections", "range_provenance", "section_range", "preview_revision", "plate_text_search", "compact_preview_source"):
                        if key in review_doc:
                            rendered_doc[key] = review_doc[key]
                    rendered_doc.pop("render_required", None)
                    stop_review.atomic_report(os.path.join(job["dir"], "report.json"), rendered_doc)
                except Exception:
                    # Render may already have rewritten its audit. Annotation
                    # rows (including rejected findings) remain authoritative.
                    stop_review.atomic_report(os.path.join(job["dir"], "report.json"), review_doc)
                    raise
                job["output"] = res["output"]
                # refresh report with output hash
                dets, rstate, prov = openscrub.load_report(
                    os.path.join(job["dir"], "report.json"))
                job["phase"] = "done"
                job["progress"] = 1.0
                job["eta"] = None
        except openscrub.PipelineCancelled:
            diagnostics.event("job_cancelled", job, action=action)
            job["stop"].clear()
            job["phase"] = "cancelled"
            job["error"] = "cancelled by user"
        except Exception as e:
            diagnostics.exception("job_action_failed", job, action=action)
            job["stop"].clear()
            # The prior report is untouched if a resumed scan fails.
            job["phase"] = ("paused" if action == "resume"
                            and os.path.isfile(os.path.join(
                                job["dir"], "report.json")) else "error")
            job["error"] = str(e)
            job["log"].append(f"ERROR: {e}")
        finally:
            job["eta"] = None       # a dead/paused job must not show "~N left"
            diagnostics.finish_job(job, action)
            diagnostics.reset_job(log_context)
            WORK_Q.task_done()


# ----------------------------------------------------------------------------
# Auth
# ----------------------------------------------------------------------------


@app.before_request
def diagnostic_request_start():
    from flask import g
    g.diagnostic_started = time.monotonic()
    g.diagnostic_id = uuid.uuid4().hex[:12]
    jid = (request.view_args or {}).get("jid")
    g.diagnostic_context = diagnostics.bind_job(JOBS.get(jid))


@app.after_request
def diagnostic_request_finish(response):
    from flask import g
    elapsed = time.monotonic() - getattr(g, "diagnostic_started", time.monotonic())
    request_id = getattr(g, "diagnostic_id", "unknown")
    response.headers["X-OpenScrub-Request-ID"] = request_id
    if response.status_code >= 400 or elapsed >= 5:
        reason = ""
        if response.status_code >= 400 and response.is_json and (response.content_length or 0) <= 16384:
            data = response.get_json(silent=True)
            if isinstance(data, dict) and isinstance(data.get("error"), str):
                reason = data["error"]
        diagnostics.event("http_request_failed" if response.status_code >= 400 else "http_request_slow",
            level=40 if response.status_code >= 500 else 30,
            request_id=request_id, method=request.method,
            route=str(request.url_rule) if request.url_rule else "unmatched",
            status=response.status_code, elapsed_ms=round(elapsed * 1000, 1), reason=reason)
    return response


@app.teardown_request
def diagnostic_request_teardown(error):
    from flask import g
    if error is not None:
        diagnostics.event("http_unhandled_exception", level=40,
            request_id=getattr(g, "diagnostic_id", "unknown"),
            route=str(request.url_rule) if request.url_rule else "unmatched",
            exc_info=(type(error), error, error.__traceback__))
    token = g.pop("diagnostic_context", None)
    if token is not None:
        diagnostics.reset_job(token)


@app.before_request
def check_token():
    if TOKEN is None:          # open mode: anyone on the network is trusted
        return
    tok = (request.args.get("token") or request.cookies.get("phiblur_token")
           or request.headers.get("X-Token"))
    if tok != TOKEN:
        abort(401, "missing or wrong access token — open the URL printed "
                   "at server startup (includes ?token=...)")


@app.before_request
def _touch_activity():
    LAST_ACTIVITY["t"] = time.time()


@app.before_request
def enforce_vault_lock():
    """While the vault is locked, every job/archive operation is refused — the
    files are ciphertext, so this fails closed rather than half-working."""
    protected = (request.path.startswith("/api/jobs") or
                 request.path == "/api/findings" or request.path.startswith("/api/findings/"))
    if protected and vault_locked():
        abort(423, "vault is locked — unlock it (Encryption panel) to "
                   "access jobs and saved findings")


@app.before_request
def refuse_upload_without_disk_room():
    """Registered after auth on purpose, but still BEFORE the view runs:
    by the time create_job touches request.files, werkzeug has already
    spooled the whole upload into the temp dir — too late to protect the
    disk. Checking the Content-Length header here reads nothing."""
    if request.method == "POST" and request.path == "/api/jobs/learned-models/import":
        # The request class supplies the same cap to the multipart parser,
        # including uploads without a Content-Length header.
        if request.content_length is not None and request.content_length > request.max_content_length:
            return _too_large(None)
    if request.method == "POST" and request.path in ("/api/jobs", "/api/jobs/learned-models/import"):
        err = _upload_disk_error(request.content_length)
        if err:
            return jsonify({"error": err}), 507


@app.after_request
def set_cookie(resp):
    if TOKEN is not None and request.args.get("token") == TOKEN:
        resp.set_cookie("phiblur_token", TOKEN, max_age=90 * 86400,
                        samesite="Lax")
    # the UI is a single served page whose JS/CSS is inlined: without this,
    # browsers (iOS Safari especially) keep showing a STALE cached copy
    # after the server is updated — new panels/fixes invisibly missing (a
    # user's waveform fix ran only in Private mode because the normal tab
    # served old cached JS). `no-cache` still lets Safari store and serve
    # the page; `no-store` forbids storing it at all, so the app is never
    # stale. Images (thumbnails, frames) keep their own caching.
    if resp.mimetype == "text/html":
        resp.headers["Cache-Control"] = "no-store, no-cache, must-revalidate, max-age=0"
        resp.headers["Pragma"] = "no-cache"          # HTTP/1.0 caches
        resp.headers["Expires"] = "0"
    elif resp.mimetype == "application/json":
        resp.headers["Cache-Control"] = "no-store"
    return resp


# ----------------------------------------------------------------------------
# API
# ----------------------------------------------------------------------------

@app.route("/api/jobs", methods=["POST"])
def create_job():
    try:
        options = json.loads(request.form.get("options", "{}"))
        if not isinstance(options, dict):
            raise ValueError()
    except (ValueError, TypeError):
        return jsonify({"error": "Scan options must be a JSON object."}), 400
    try:
        margin = float(options.get("plate_narrow_margin", 0))
        if not np.isfinite(margin) or margin < 0 or options.get("plate_coverage", "full") not in ("full", "narrow"):
            raise ValueError()
    except (ValueError, TypeError):
        abort(400, description="invalid plate coverage or margin")
    jobs = []
    files = request.files.getlist("video")
    if files and files[0].filename:
        for f in files:
            name = os.path.basename(f.filename.replace("\\", "/"))
            # extension comes from the client: keep it only if it's a plain
            # known media suffix, never splice arbitrary text into the path
            ext = os.path.splitext(name)[1].lower()
            if ext not in MEDIA_EXTS:
                ext = ".mp4"
            job = new_job("", options, name)
            path = os.path.join(job["dir"], "input" + ext)
            f.save(path)
            job["video"] = path
            try:
                job["size"] = os.path.getsize(path)
            except OSError:
                pass
            WORK_Q.put((job["id"], "scan"))
            jobs.append(job["id"])
    elif request.form.get("server_path"):
        p = os.path.realpath(request.form["server_path"].strip())
        err = server_path_error(p)
        if err:
            return jsonify({"error": err}), 400
        # Containment guard REPEATED inline before the getsize() sink below:
        # server_path_error already enforces it, but CodeQL's path-injection
        # barrier analysis is function-local — without this single-startswith
        # shape in THIS function the alert opens (code-scanning #21, the
        # v1.0.83 duplicate-upload size lookup). Same as server_video.
        root = os.environ.get("OPENSCRUB_MEDIA_ROOT")
        r = os.path.realpath(root) if root else os.path.realpath(
            os.path.splitdrive(p)[0] + os.sep)
        if not p.startswith(r.rstrip(os.sep) + os.sep):
            return jsonify({"error": "server path is outside "
                                     "OPENSCRUB_MEDIA_ROOT"}), 400
        job = new_job(p, options, os.path.basename(p))
        try:
            job["size"] = os.path.getsize(p)
        except OSError:
            pass
        WORK_Q.put((job["id"], "scan"))
        jobs.append(job["id"])
    else:
        return jsonify({"error": "no file uploaded and no server path"}), 400
    return jsonify({"jobs": jobs})


@app.route("/api/jobs")
def list_jobs():
    with JOBS_LOCK:
        js = sorted(JOBS.values(), key=lambda j: -j["created"])
    return jsonify([job_public(j) for j in js])


DELETE_MARKER = ".delete_pending"


def _reap_job_dir(jdir, jid="?", retries=2, delay=0.8):
    """rmtree with retries. A just-closed review session can still hold a
    streaming handle on the video for a moment (and holds a LOCK on it on
    Windows), so the first attempt can fail transiently — a real user's
    delete failed exactly this way."""
    import shutil as _sh
    err = None
    for i in range(retries):
        try:
            _sh.rmtree(jdir)
            return True
        except OSError as e:
            err = e
            time.sleep(delay)
    # log the detail server-side only: OSError text contains filesystem
    # paths, which don't belong in an HTTP response body
    print(f"[web] job {jid} delete incomplete: {err}", flush=True)
    return False


@app.route("/api/jobs/<jid>", methods=["DELETE"])
def job_delete(jid):
    """Delete a job and every file it owns (upload, normalized video,
    report, thumbnails, output). Running jobs must be cancelled first.
    Deletion is GUARANTEED, not merely attempted: if a file is still
    held open (Windows locks, a streaming handle, a busy network share),
    a marker is written and background retries + the startup and
    retention sweeps finish the removal — the old behavior popped the
    job from the list FIRST and then failed, leaving an orphaned folder
    the UI could no longer reach, which rose from the dead as a zombie
    review job at the next restart."""
    with JOBS_LOCK:
        job = JOBS.get(jid)
        if job is None:
            abort(404)
        if job.get("phase") in ("queued", "scanning", "rendering",
                                "queued_render", "learning"):
            abort(409, "job is queued or running — cancel it first")
    dependency = _SECTIONS.deletion_error(job)
    if dependency:
        return jsonify({"error": dependency}), 409
    if _reap_job_dir(job["dir"], jid):
        with JOBS_LOCK:
            JOBS.pop(jid, None)
        return jsonify({"ok": True})
    # couldn't remove everything now: mark the dir so every future sweep
    # (background retries below, startup, retention) knows it is condemned,
    # take it out of the UI, and keep trying quietly
    try:
        with open(os.path.join(job["dir"], DELETE_MARKER), "w") as f:
            f.write(str(time.time()))
    except OSError:
        pass
    with JOBS_LOCK:
        JOBS.pop(jid, None)

    def _retry():
        for _ in range(10):
            time.sleep(30)
            if not os.path.isdir(job["dir"]):
                return
            if _reap_job_dir(job["dir"], jid, retries=1):
                print(f"[web] job {jid} delete completed on retry",
                      flush=True)
                return
    threading.Thread(target=_retry, daemon=True).start()
    return jsonify({"ok": True, "pending": True,
                    "note": "some files were still in use; removal will "
                            "complete automatically"})


@app.route("/api/jobs/<jid>/retry", methods=["POST"])
def job_retry(jid):
    """Re-run a failed or cancelled job's SCAN, reusing the file that is
    already on the server. Before this existed, the only path after an
    error was Start scan — which uploaded the same multi-GB file into a
    fresh job dir on every attempt until the disk filled (issue #16)."""
    with JOBS_LOCK:
        job = JOBS.get(jid)
        if job is None:
            abort(404)
        if job["phase"] not in ("error", "cancelled"):
            return jsonify({"error": "only a failed or cancelled job can "
                                     "be retried"}), 409
        protected = _SECTIONS.whole_job_error(job)
        if protected:
            return jsonify({"error": protected}), 409
        if not (job.get("video") and os.path.exists(job["video"])):
            return jsonify({"error": "the job's video file is no longer "
                                     "on the server — start a new "
                                     "scan"}), 410
        job["cancel"].clear()
        job["error"] = None
        job["output"] = None
        job["progress"] = 0.0
        job["eta"] = None
        job["phase"] = "queued"
        job["log"].append("— retrying scan (reusing the file already on "
                          "the server — nothing is re-uploaded) —")
    WORK_Q.put((jid, "scan"))
    return jsonify({"ok": True})


@app.route("/api/jobs/<jid>")
def job_status(jid):
    job = JOBS.get(jid) or abort(404)
    return jsonify(job_public(job))


@app.route("/api/jobs/<jid>/log")
def job_log(jid):
    job = JOBS.get(jid) or abort(404)
    try:
        frm = max(0, int(request.args.get("from", 0)))
        limit = max(1, min(400, int(request.args.get("limit", 400))))
    except (TypeError, ValueError):
        abort(400, description="log cursor and limit must be integers")
    # Capture one end position before slicing: a worker can append between
    # calls, and the cursor must only acknowledge lines in this response.
    lines = job["log"]
    end = len(lines)
    if frm > end:
        frm = 0  # a restarted/rehydrated job may have a shorter log
    frm = max(frm, end - limit)
    tail = lines[frm:end]
    return jsonify({"from": frm, "lines": tail, "len": frm + len(tail)})


@app.route("/api/jobs/<jid>/preview.jpg")
def job_preview(jid):
    job = JOBS.get(jid) or abort(404)
    p = os.path.join(job["dir"], "preview.jpg")
    # send_file stats the path separately from streaming its contents. A live
    # scanner can publish another JPEG between those steps. Freeze this small
    # response so Cheroot's Content-Length always describes the bytes sent.
    try:
        with open(p, "rb") as source:
            data = source.read()
    except FileNotFoundError:
        abort(404)
    return Response(data, mimetype="image/jpeg",
                    headers={"Cache-Control": "no-store"})


@app.route("/api/jobs/<jid>/stop", methods=["POST"])
def job_stop(jid):
    """Request a cooperative scan stop; Cancel keeps its old meaning."""
    job = JOBS.get(jid) or abort(404)
    with JOBS_LOCK:
        if job["phase"] != "scanning":
            return jsonify({"error": "Stop & Review is available only "
                                     "during scanning"}), 409
        job["stop"].set()
    return jsonify({"ok": True, "message": "Finishing a whole frame and "
                    "finalizing the checkpoint before Review"})


@app.route("/api/jobs/<jid>/resume", methods=["POST"])
def job_resume(jid):
    """Resume from a saved checkpoint without re-scanning its prefix."""
    job = JOBS.get(jid) or abort(404)
    with JOBS_LOCK:
        if job["phase"] != "paused":
            return jsonify({"error": "Only paused scans can resume"}), 409
        if job.get("trackbg", {}).get("state") == "running":
            return jsonify({"error": "Finish tracking the selected object "
                                     "before resuming the scan"}), 409
        report = _load_job_report(job)
        try:
            meta = stop_review.validate_resume(report)
        except (stop_review.CheckpointError, TypeError, KeyError,
                ValueError) as exc:
            return jsonify({"error": str(exc)}), 409
        # Persist the initial settings as part of the checkpoint, so a
        # restart cannot silently resume with unrelated default settings.
        job["options"] = meta["options"]
        if (job["options"].get("learned_plate_model") or
                os.path.lexists(os.path.join(job["dir"], "plate_model"))):
            try:
                _selected_plate_model(job)
            except learned_models.ModelError as error:
                return jsonify({"error": str(error)}), 409
        job["stop"].clear()
        job["cancel"].clear()
        job["error"] = None
        job["phase"] = "queued"
        job["eta"] = None
    WORK_Q.put((jid, "resume"))
    return jsonify({"ok": True, "next_frame": meta["next_frame"]})


@app.route("/api/jobs/<jid>/cancel", methods=["POST"])
def job_cancel(jid):
    job = JOBS.get(jid) or abort(404)
    job["cancel"].set()
    return jsonify({"ok": True})


def perform_learning(job):
    """Worker-only operation. Failed training/rescans leave the old report intact."""
    previous = job.get("learning_previous_phase", "review")
    cb = WebCallbacks(job)
    job["phase"] = "learning"
    job["preview"] = None
    job["activity"] = None
    job["model_root"] = learned_models_root()
    try:
        job["learning"] = {"stage": "preflight", "message": "Checking the local CUDA training environment"}
        document = _load_job_report(job)
        active = (document.get('learning') or {}).get('active') or learning_session._load(
            os.path.join(job['dir'],'learning','active.json'),{})
        parent = findings_web.training.session_parent(job,document,active)
        ready = learning_session.preflight(weights=parent['weights']) if parent else learning_session.preflight()
        if not ready["ready"]:
            raise ValueError("; ".join(ready["problems"]))
        def scan(destination):
            args = build_args(job)
            args.resume_start = 0.0
            args.plate_learning_exact = True
            state = openscrub.run_scan(args, cb)
            if state.get("stop_at_frame") is not None:
                raise ValueError("Learning rescan stopped before completion; previous review retained")
            openscrub.write_report(str(destination), args, state)
            with open(destination, encoding="utf-8") as source:
                return json.load(source)
        def publish(doc):
            with _REVIEW_EDIT_LOCK, _REVIEW_WORK_LOCK:
                if job.get("section"):
                    import video_sections
                    relation = job["section"]
                    doc = video_sections.slice_report(doc, relation["start_frame"], relation["end_frame"])
                stop_review.atomic_report(os.path.join(job["dir"], "report.json"), doc)
                # Current thumbnails are indexed by row; a full rescan changes IDs.
                for name in os.listdir(job["dir"]):
                    if re.fullmatch(r"(?:thumb2_\d+\.jpg|plate_preview_\d+\.npz)", name):
                        try:
                            os.unlink(os.path.join(job["dir"], name))
                        except OSError:
                            pass
        result = learning_session.run_session(
            job, None,  # Collection owns a cancellable batch decoder, not a preview request.
            scan, publish, cb.log)
        job["phase"] = "review"
        job["error"] = None
        job["output"] = None  # Old output may exist, but does not represent this pass.
        job["checkpoint_frame"] = job["checkpoint_total"] = None
        job["progress"] = 0.5
        job["learning"]["inference"] = result["learning"]["inference"]
        job.pop("refinement", None)
        job.pop("verification", None)
    except learning_session.CoverageRejected as error:
        job["phase"] = previous
        job["error"] = None
        job["learning"] = dict(job.get("learning") or {}, stage="candidate_ready", message=str(error))
        diagnostics.event("learning_candidate_retained", job, reason=str(error))
        cb.log(str(error))
    except Exception as error:
        diagnostics.exception("learning_failed", job)
        job["phase"] = previous
        job["error"] = str(error)
        job["learning"] = {"stage": "failed", "message": str(error)}
        cb.log("Learning stopped: " + str(error))
    finally:
        job["cancel"].clear()
        job["stop"].clear()
        job["eta"] = None


def perform_verification(job):
    """Evaluate a retained candidate and check proposals without training again."""
    previous = job.get("verification_previous_phase", "review")
    cb = WebCallbacks(job)
    job.update(phase="learning", preview=None, activity=None)
    path = os.path.join(job["dir"], "report.json")
    try:
        settings = job["verification_request"]
        candidate_id, mode = settings["candidate_id"], settings["mode"]
        selected_candidate = learning_candidates.load_candidate(job["dir"], candidate_id)
        with open(path, "rb") as source:
            before = source.read()
        doc = json.loads(before)
        fingerprint = learning_session.verify_source(job, doc)
        learning_session.update_learning(job, "assessing", "Checking held-out plates and non-plates")
        def assessment_progress(done, total):
            learning_session.update_learning(job, "assessing", "Checking held-out plates and non-plates",
                                             done=done, total=total, unit="examples")
        assessment = learning_candidates.evaluate(
            job["dir"], candidate_id, cancelled=job["cancel"].is_set, progress=assessment_progress)
        if mode == "filter" and assessment["status"] != "validated":
            raise ValueError("This candidate supports review suggestions only. " + assessment["reason"])
        candidate = learning_candidates.load_candidate(job["dir"], candidate_id)
        if (candidate["model_sha256"] != selected_candidate["model_sha256"] or
                candidate["assessment"] != assessment):
            raise ValueError("Candidate changed after its assessment; previous review retained")
        model_data = candidate["model_path"].read_bytes()
        if hashlib.sha256(model_data).hexdigest() != candidate["model_sha256"]:
            raise ValueError("Candidate changed before checking; previous review retained")
        def inference_progress(done, total):
            learning_session.update_learning(job, "checking", "Checking existing plate detections",
                                             done=done, total=total, unit="frames")
        learning_session.update_learning(job, "checking", "Checking existing plate detections")
        result, stats, frame_range = _run_plate_model(
            job, job["video"], doc, video_learning.CropRefiner(model_data), mode,
            assessment=assessment, progress=inference_progress)
        audit = _verifier_audit(result, dict(schema=1, candidate_id=candidate_id,
            version=candidate["version"], model_sha256=candidate["model_sha256"]), assessment, mode, stats,
            frame_range=frame_range)
        result["render_required"] = True
        if learning_session.verify_source(job, result) != fingerprint:
            raise ValueError("Source changed during checking; previous review retained")
        with _REVIEW_EDIT_LOCK, _REVIEW_WORK_LOCK:
            if job["cancel"].is_set():
                raise InterruptedError("Plate verification cancelled; previous review retained")
            latest = learning_candidates.load_candidate(job["dir"], candidate_id)
            if (latest["model_sha256"] != candidate["model_sha256"] or
                    latest["assessment"] != assessment):
                raise ValueError("Candidate changed during checking; previous review retained")
            with open(path, "rb") as source:
                if source.read() != before:
                    raise ValueError("Review changed during checking; save your choices and try again")
            stop_review.atomic_report(path, result)
        job.update(phase="paused" if previous == "paused" else "review",
                   error=None, output=None, verification=audit)
        message = ("Secondary model checked %d detections: %d suggested false positives, "
                   "%d filtered; %d human decisions preserved. Review the results before rendering." %
                   (stats["checked"], stats["suggested"], stats["suppressed"], stats["human_preserved"]))
        learning_session.update_learning(job, "checked", message)
        cb.log(message)
    except InterruptedError as error:
        job.update(phase=previous, error=None, learning={"stage": "cancelled", "message": str(error)})
        cb.log(str(error))
    except Exception as error:
        diagnostics.exception("plate_verification_failed", job)
        job.update(phase=previous, error=str(error), learning={"stage": "failed", "message": str(error)})
        cb.log("Plate verification stopped: " + str(error))
    finally:
        job["cancel"].clear()
        job["stop"].clear()
        job["eta"] = None


@app.route("/api/jobs/<jid>/learning", methods=["GET", "POST"])
def job_learning(jid):
    job = JOBS.get(jid) or abort(404)
    if request.method == "POST":
        protected = _SECTIONS.whole_job_error(job)
        if protected:
            return jsonify({"error": protected}), 409
    if request.method == "GET":
        return jsonify({"status": job.get("learning"),
            "weights_configured": os.path.isfile(os.environ.get("OPENSCRUB_TRAIN_WEIGHTS", "")),
            "note": "Training is local and video-specific. Empty model predictions are not automatic permission to leave a plate visible."})
    payload = request.get_json(silent=True) or {}
    if not isinstance(payload, dict) or payload.get("license_accepted") is not True:
        return jsonify({"error": "Acknowledge the locally installed training framework's terms before training."}), 400
    name = payload.get('name')
    if name:
        name = learned_models._text(name, 'Model name', 80, required=True)
    with JOBS_LOCK:
        if job["phase"] not in ("paused", "review", "done"):
            return jsonify({"error": "Pause or complete the scan before training."}), 409
        if job.get("trackbg", {}).get("state") == "running":
            return jsonify({"error": "Finish the current tracking operation before training."}), 409
        prior = _load_job_report(job)
        parent_id = ((prior.get('learning') or {}).get('active') or {}).get('model_id') or (prior.get('learning') or {}).get('library_model_id')
        parent_ready = parent_id and findings_web.training.training_info(learned_models_root(),parent_id).get('trainable')
        if not os.path.isfile(os.environ.get('OPENSCRUB_TRAIN_WEIGHTS','')) and not parent_ready:
            return jsonify(error='Training setup needed: configure a trusted local segmentation checkpoint or retain the accepted model’s local training checkpoint. Your saved annotations are unchanged.'),503
        if prior.get("provenance", {}).get("hdr_output"):
            return jsonify({"error": "This learning path currently requires SDR output. HDR-match learning is not supported; the existing HDR report and edits are unchanged."}), 409
        job["learning_previous_phase"] = job["phase"]
        job['model_root'] = learned_models_root()
        job["learning_request"] = {"license_accepted": True, "epochs": 40, "batch": 8, "name": name}
        job["phase"] = "learning"
        job["learning"] = {"stage": "queued", "message": "Learning pass queued"}
        job["cancel"].clear()
        job["stop"].clear()
        job["error"] = None
    WORK_Q.put((jid, "learn"))
    return jsonify({"ok": True})


@app.route("/api/jobs/<jid>/learning/rollback", methods=["POST"])
def job_learning_rollback(jid):
    from pathlib import Path
    job = JOBS.get(jid) or abort(404)
    protected = _SECTIONS.whole_job_error(job)
    if protected:
        return jsonify({"error": protected}), 409
    with JOBS_LOCK:
        if job["phase"] not in ("paused", "review", "done"):
            return jsonify({"error": "Finish or cancel the active pass before restoring."}), 409
        with _REVIEW_EDIT_LOCK, _REVIEW_WORK_LOCK:
            current = _load_job_report(job)
            root = (Path(job["dir"]) / "learning" / "passes").resolve()
            previous = (current.get("learning") or {}).get("previous_report")
            if not previous:
                return jsonify({"error": "There is no previous learning pass to restore."}), 409
            archived = Path(previous).resolve()
            if root not in archived.parents or archived.name != "before-report.json":
                return jsonify({"error": "Invalid archived report location."}), 400
            try:
                doc = json.loads(archived.read_text(encoding="utf-8"))
            except (OSError, ValueError):
                return jsonify({"error": "Previous report could not be read; current review kept."}), 409
            if (doc.get("provenance", {}).get("input_sha256") !=
                    current.get("provenance", {}).get("input_sha256")):
                return jsonify({"error": "Archived report belongs to another source."}), 409
            meta = doc.setdefault("learning", {})
            meta["needs_render"] = True
            meta.setdefault("active", {})
            stop_review.atomic_report(os.path.join(job["dir"], "report.json"), doc)
            # Source annotations and all versioned model files remain intact.
            try:
                learning_session.atomic_json(Path(job["dir"]) / "learning" / "active.json", meta["active"])
            except OSError:
                pass  # Report remains the authority for version selection.
            for name in os.listdir(job["dir"]):
                if re.fullmatch(r"(?:thumb2_\d+\.jpg|plate_preview_\d+\.npz)", name):
                    try:
                        os.unlink(os.path.join(job["dir"], name))
                    except OSError:
                        pass
            checkpoint = doc.get("stop_review") or {}
            job["phase"] = "paused" if checkpoint.get("state") == "paused" else "review"
            job["output"] = None
            job["learning"] = {"stage": "restored", "message": "Previous review restored; training examples retained."}
            for key in ("refinement", "verification", "verification_history"):
                if doc.get(key):
                    job[key] = doc[key]
                else:
                    job.pop(key, None)
            job["error"] = None
    return jsonify({"ok": True})


@app.route("/api/jobs/<jid>/learning/review")
def job_learning_review(jid):
    job = JOBS.get(jid) or abort(404)
    try:
        fraction = float(request.args.get("fraction", ".1"))
        sample = video_learning.review_sample_details(_load_job_report(job), fraction)
    except (ValueError, TypeError) as error:
        return jsonify({"error": str(error)}), 400
    return jsonify(sample)


def _load_job_report(job):
    with open(os.path.join(job["dir"], "report.json"), encoding="utf-8") as f:
        return json.load(f)


def _invalidate_review_previews(job):
    for name in os.listdir(job['dir']):
        if re.fullmatch(r'(?:thumb2_\d+(?:_[0-9a-f]{16})?\.jpg|plate_preview_\d+\.npz)', name):
            try:
                os.unlink(os.path.join(job['dir'], name))
            except OSError:
                pass


# Review work is deliberately bounded. Never replay a long video's prefix for
# every HTTP thumbnail request, or let each request start an all-core decoder.
from collections import OrderedDict
from fractions import Fraction
import hashlib
import re
import subprocess
import tempfile
import zipfile

# Lock order for operations needing more than one gate: edit -> work -> cache.
# Cached annotation saves must not compete with unrelated video decoding.
_REVIEW_EDIT_LOCK = threading.RLock()
_REVIEW_WORK_LOCK = threading.RLock()
_REVIEW_CACHE_LOCK = threading.Lock()
_REVIEW_FRAMES = OrderedDict()
_REVIEW_PROBES = OrderedDict()
_REVIEW_FRAME_BYTES = 64 * 1024 * 1024
_REVIEW_TIMEOUT = 10
# Only thumbnail readers share this snapshot. Writers always load independent
# documents. Retain at most ONE report, with a 32 MiB serialized-size ceiling;
# this is an input-size bound, not a claim about Python object memory usage.
_REVIEW_REPORT_LOCK = threading.Lock()
_REVIEW_REPORTS = OrderedDict()
_REVIEW_REPORT_MAX_FILE_BYTES = 32 * 1024 * 1024


def _preview_report_identity(path):
    stat = os.stat(path)
    return (path, stat.st_dev, stat.st_ino, stat.st_size,
            stat.st_mtime_ns, stat.st_ctime_ns)


def _load_preview_report(job):
    """Read-only, revision-fenced metadata for individual thumbnail requests.

    A large report is deserialized at most once per revision. Repeated warm
    thumbnails use one SQLite row and a small cached shared timeline, rather
    than parsing hundreds of thousands of detections per HTTP request.
    """
    path = os.path.realpath(os.path.join(job["dir"], "report.json"))
    with _REVIEW_REPORT_LOCK:
        identity = _preview_report_identity(path)
        with _REVIEW_CACHE_LOCK:
            if vault_locked():
                abort(423)
            cached = _REVIEW_REPORTS.get(identity)
            if cached is not None:
                return cached
        doc = review_preview_index.load(path)
        if doc is None:
            # Legacy jobs are indexed once on demand. Scan completion builds
            # the index up front, so normal new jobs avoid this path entirely.
            source = _load_job_report(job)
            try:
                # A legacy job may need indexing after scan. Serialize this
                # disk publication with vault encryption, then recheck lock
                # state before serving any resulting preview pixels.
                with _REVIEW_CACHE_LOCK:
                    if vault_locked():
                        abort(423)
                    review_preview_index.prepare(path, source)
                    doc = review_preview_index.load(path)
            except (OSError, ValueError, sqlite3.DatabaseError):
                diagnostics.exception("review_index_build_failed", job)
            if doc is None:
                doc = source  # safe fallback; never sacrifice review accuracy
        current = _preview_report_identity(path)
        with _REVIEW_CACHE_LOCK:
            if vault_locked():
                abort(423)
            if current == identity:
                # Indexed metadata is small even when report.json exceeds 32 MB.
                if (isinstance(doc.get("detections"), review_preview_index.IndexedRows)
                        or identity[3] <= _REVIEW_REPORT_MAX_FILE_BYTES):
                    _REVIEW_REPORTS.clear()
                    _REVIEW_REPORTS[identity] = doc
        return doc


def _video_identity(path):
    st = os.stat(path)
    return (os.path.realpath(path), st.st_size, st.st_mtime_ns)


@app.errorhandler(422)
@app.errorhandler(503)
@app.errorhandler(504)
def review_error(error):
    response = jsonify({"error": error.description})
    response.status_code = error.code
    if error.code == 503:
        response.headers["Retry-After"] = "2"
    return response


def _review_process(command):
    try:
        result = subprocess.run(command, capture_output=True,
                                timeout=_REVIEW_TIMEOUT)
    except subprocess.TimeoutExpired:
        diagnostics.exception("preview_process_timeout", tool=os.path.basename(str(command[0])), timeout_seconds=_REVIEW_TIMEOUT)
        abort(504, description="Preview decoding timed out. Retry this finding; "
              "a video with very sparse keyframes may need a seekable scan copy.")
    except OSError:
        diagnostics.exception("preview_process_start_failed", tool=os.path.basename(str(command[0])))
        abort(503, description="FFmpeg and ffprobe are required for review previews.")
    if result.returncode:
        diagnostics.event("preview_process_failed", level=40, tool=os.path.basename(str(command[0])),
                          returncode=result.returncode, stderr=result.stderr.decode("utf-8", errors="replace")[-8000:])
        abort(422, description="Could not decode this video preview.")
    return result


def _review_probe(path, identity):
    with _REVIEW_CACHE_LOCK:
        info = _REVIEW_PROBES.get(identity)
        if info is not None:
            _REVIEW_PROBES.move_to_end(identity)
            return info
    result = _review_process([
        "ffprobe", "-v", "error", "-select_streams", "v:0",
        "-show_entries", "stream=avg_frame_rate,r_frame_rate,start_time,width,height",
        "-of", "json", path])
    try:
        stream = json.loads(result.stdout)["streams"][0]
        fps = float(Fraction(stream["avg_frame_rate"]))
        nominal = float(Fraction(stream["r_frame_rate"]))
        info = {"fps": fps, "start": float(stream.get("start_time", 0)),
                "width": int(stream["width"]), "height": int(stream["height"]),
                "cfr": abs(fps-nominal) <= max(.001, fps*.0001)}
        if not np.isfinite(fps) or fps <= 0:
            raise ValueError()
    except (ValueError, KeyError, IndexError, ZeroDivisionError):
        abort(422, description="Cannot establish the preview frame rate.")
    with _REVIEW_CACHE_LOCK:
        _REVIEW_PROBES[identity] = info
        while len(_REVIEW_PROBES) > 16:
            _REVIEW_PROBES.popitem(last=False)
    return info


def _read_review_frame(path, index, exact=True):
    """Accurate seek on the CFR scan video, verified by the decoded frame PTS.

    Indexed/narrow review requires normalized CFR input. Refuse unverifiable
    input rather than substituting a nearby frame or replaying from frame zero.
    FFmpeg's input seek decodes from the preceding keyframe, not the beginning;
    a hard process deadline also bounds pathological single-keyframe footage.
    """
    index = int(index) if exact else float(index)
    if index < 0:
        return None
    if vault_locked():
        abort(423)
    identity = _video_identity(path)
    key = identity + ("frame" if exact else "time", index)
    with _REVIEW_CACHE_LOCK:
        cached = _REVIEW_FRAMES.get(key)
        if cached is not None:
            _REVIEW_FRAMES.move_to_end(key)
            return cached.copy()  # callers may paint a mask on their image
    if not _REVIEW_WORK_LOCK.acquire(blocking=False):
        abort(503, description="Another preview is decoding. Retry this finding.")
    try:
        if vault_locked():
            abort(423)
        with _REVIEW_CACHE_LOCK:
            cached = _REVIEW_FRAMES.get(key)
            if cached is not None:
                return cached.copy()
        info = _review_probe(path, identity)
        if exact and not info["cfr"]:
            abort(422, description="Exact review needs a constant-frame-rate scan copy.")
        # Seek slightly before the target to avoid rounding it to the next frame.
        target = max(0.0, (index-.1) / info["fps"]) if exact else index
        # PPM transports lossless pixels without compressing a full 4K PNG
        # just to decode it again before extracting a small plate crop.
        result = _review_process([
            "ffmpeg", "-hide_banner", "-loglevel", "info", "-nostdin",
            "-threads", "1", "-filter_threads", "1", "-copyts", "-ss", "%.9f" % target,
            "-i", path, "-map", "0:v:0", "-an", "-sn",
            "-vf", "showinfo", "-frames:v", "1", "-vsync", "0",
            "-threads", "1", "-f", "image2pipe", "-vcodec", "ppm", "pipe:1"])
        log = result.stderr.decode("utf-8", errors="replace")
        match = re.search(r"\bn:\s*0\s+pts:\s*(-?\d+)\s+pts_time:", log)
        timebase = re.search(r"config in time_base:\s*(\d+/\d+)", log)
        if not match or not timebase:
            return None
        # pts_time is printed with limited precision: at long durations it
        # rounds by more than a high-FPS frame. Integer PTS retains precision.
        timestamp = float(int(match.group(1)) * Fraction(timebase.group(1)))
        got = (timestamp-info["start"]) * info["fps"]
        if exact and abs(got-index) > .15:
            abort(422, description="Preview frame identity could not be verified.")
        frame = cv2.imdecode(np.frombuffer(result.stdout, np.uint8), cv2.IMREAD_COLOR)
        if frame is None:
            return None
        with _REVIEW_CACHE_LOCK:
            if frame.nbytes <= _REVIEW_FRAME_BYTES:
                _REVIEW_FRAMES[key] = frame
                while sum(f.nbytes for f in _REVIEW_FRAMES.values()) > _REVIEW_FRAME_BYTES:
                    _REVIEW_FRAMES.popitem(last=False)
        return frame.copy()
    finally:
        _REVIEW_WORK_LOCK.release()


def _read_exact_frame(path, index):
    return _read_review_frame(path, index, exact=True)


def _frame_at(job, t, rstate, frame_index=None):
    if frame_index is not None:
        return _read_exact_frame(job["video"], frame_index)
    # Legacy, time-based findings may come from deliberately unnormalized VFR.
    # Keep that path timestamp-based; indexed review remains strictly verified.
    return _read_review_frame(job["video"], max(0.0, float(t)), exact=False)


@app.route("/api/jobs/<jid>/mediainfo")
def job_mediainfo(jid):
    """Basic video properties straight from the file — available in every
    job phase, no scan report required."""
    job = JOBS.get(jid) or abort(404)
    cap = cv2.VideoCapture(job["video"])
    fps = cap.get(cv2.CAP_PROP_FPS) or 30.0
    n = cap.get(cv2.CAP_PROP_FRAME_COUNT) or 0
    w_ = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
    h_ = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
    cap.release()
    return jsonify({"duration": n / fps if fps else 0, "fps": fps,
                    "width": w_, "height": h_})


def _reconcile_compact_previews(job, doc):
    """Bind scan-time cached pictures to final post-processed track ids.

    This is metadata-only: it never opens the source video. The report file
    identity makes repeated Review opens effectively free, while older jobs
    created before reconciliation gain the mapping on first open.
    """
    try:
        signature = _preview_report_identity(
            os.path.realpath(os.path.join(job["dir"], "report.json")))
    except OSError:
        return dict(total=0, linked=0, already=0)
    if job.get("_compact_preview_reconcile") == signature:
        return dict(total=0, linked=0, already=0)
    if not _REVIEW_CACHE_LOCK.acquire(timeout=1.):
        return dict(total=0, linked=0, already=0)
    try:
        if vault_locked():
            return dict(total=0, linked=0, already=0)
        stats = finding_previews.reconcile(
            job["dir"], doc.get("detections", []), doc.get("render_state") or {})
        job["_compact_preview_reconcile"] = signature
        return stats
    finally:
        _REVIEW_CACHE_LOCK.release()


@app.route("/api/jobs/<jid>/detections")
def job_detections(jid):
    job = JOBS.get(jid) or abort(404)
    doc = _load_job_report(job)
    _reconcile_compact_previews(job, doc)
    items = []
    for i, d in enumerate(doc["detections"]):
        items.append({"i": i, "category": d["category"], "text": d["text"],
                      "t_start": d["t_start"], "t_end": round(d["t_end"], 2),
                      "enabled": d.get("enabled", True),
                      "track": d.get("track", -1),
                      "person": d.get("person", -1),
                      "confidence": d.get("confidence", 0),
                      "verified_label": d.get("verified_label", ""),
                      "human_confirmation": d.get("human_confirmation"),
                      "confirmed_finding_id": d.get("confirmed_finding_id"),
                      "confirmed_finding_revision": d.get("confirmed_finding_revision"),
                      "output_choice_explicit": bool(d.get("output_choice_explicit")),
                      "plate_text_evidence": d.get("plate_text_evidence"),
                      "learning_conflict": d.get("learning_conflict", ""),
                      "learning_score": d.get("learning_score"),
                      "plate_verification": d.get("plate_verification"),
                      "fallback_reason": d.get("fallback_reason", ""),
                      "human_region_confirmed": bool(d.get("human_region_confirmed")),
                      "zone_dropped": bool(d.get("zone_dropped")),
                      "shaped": bool(d.get("poly"))})
    return jsonify({"detections": items,
                    "learning": doc.get("learning"),
                    "video_id": (doc.get('provenance') or {}).get('original_input_sha256') or (doc.get('provenance') or {}).get('input_sha256'),
                    "plate_text_search": doc.get("plate_text_search"),
                    "refinement": doc.get("refinement"),
                    "verification": doc.get("verification"),
                    "verification_history": doc.get("verification_history"),
                    "learning_candidates": learning_candidates.list_candidates(job["dir"]),
                    "indexed_frames": any(d.get("frame_index", -1) >= 0 for d in doc["detections"]),
                    "frame_count": len(doc["render_state"]["cum"]),
                    "fps": doc["render_state"]["fps"],
                    "duration": len(doc["render_state"]["cum"]) /
                                doc["render_state"]["fps"]})


def _review_detections(job, doc):
    """Compute rendered coverage while retaining all report row indices."""
    rows = doc["detections"]
    dets = [openscrub.Detection(
        r["t_start"], r["t_end"], tuple(r["cbox"]), r["category"],
        r.get("text", ""), r.get("confidence", 1.0),
        tuple(r.get("aoff", (0, 0))), dense=r.get("dense", False),
        track=r.get("track", -1), poly=r.get("poly") or (),
        poly_holes=r.get("poly_holes") or (), mask_pad=r.get("mask_pad", -1),
        plate_quad=tuple(tuple(pt) for pt in (r.get("plate_quad") or ())))
        for r in rows]
    coverage, pad, _ = _job_mask_options(job)
    if coverage not in ("tight", "box", "concealed"):
        abort(400, description="invalid coverage option")
    try:
        int(str(pad))
    except ValueError:
        abort(400, description="invalid padding option")
    enabled_indices = [i for i, row in enumerate(rows) if row.get("enabled", True)]
    enabled = openscrub.apply_coverage([dets[i] for i in enabled_indices], coverage)
    effective = list(dets)
    for i, det in zip(enabled_indices, enabled):
        effective[i] = det
    for i, row in enumerate(rows):
        if not row.get("enabled", True):
            effective[i] = openscrub.apply_coverage([dets[i]], coverage)[0]
    result = []
    for row, det in zip(rows, effective):
        copy = dict(row)
        copy.update(cbox=det.cbox, poly=det.poly, poly_holes=det.poly_holes,
                    mask_pad=det.mask_pad)
        copy["_coverage_box"] = (coverage in ("box", "concealed") and
                                  det.dense and det.category in ("person", "manual"))
        result.append(copy)
    return result


def _review_mask_data(d, ox, oy, shape, job, doc):
    """Rasterize the effective mask at the review frame coordinates."""
    box = [d["cbox"][0] + ox, d["cbox"][1] + oy,
           d["cbox"][2] + ox, d["cbox"][3] + oy]
    base = d.get("mask_pad", -1)
    try:
        base = float(base)
        if not np.isfinite(base) or base < 0:
            raise ValueError()
    except (ValueError, TypeError):
        base = int(str(_job_mask_options(job)[1]))
    anchor = d.get("aoff", (0, 0))
    drift = 0 if d.get("category") == "plate" and d.get("frame_index", -1) >= 0 and d.get("poly") else min(24.0, 0.05 * (abs(ox-anchor[0]) + abs(oy-anchor[1])))
    pad = base + drift
    region = (box[0]-pad, box[1]-pad, box[2]+pad, box[3]+pad)
    if d.get("category") == "plate" and len(d.get("plate_quad") or ()) == 4:
        quad = openscrub._plate_quad_pixels(box, d["plate_quad"])
        tight = (min(p[0] for p in quad)-2, min(p[1] for p in quad)-2,
                 max(p[0] for p in quad)+2, max(p[1] for p in quad)+2)
        return openscrub.rasterize_mask(
            shape, tight, (d["plate_quad"],), box, 1, ())
    if d.get("poly"):
        return openscrub.rasterize_mask(
            shape, region, d["poly"], box, pad, d.get("poly_holes") or ())
    face_shape = _job_mask_options(job)[2]
    kind = "ellipse" if d["category"] == "face" and face_shape != "rect" else "rect"
    return openscrub.rasterize_region_mask(shape, region, kind)


def _review_mask(d, ox, oy, shape, job, doc):
    data = _review_mask_data(d, ox, oy, shape, job, doc)
    if data is None:
        return []
    region, mask = data
    contours, _ = cv2.findContours(mask, cv2.RETR_TREE, cv2.CHAIN_APPROX_SIMPLE)
    return [[[int(pt[0][0] + region[0]), int(pt[0][1] + region[1])]
             for pt in contour] for contour in contours]


def _human_plate_override(row):
    """Explicit choices supersede a machine decision without inventing a label."""
    changed = False
    confirmation = row.get('human_confirmation')
    if isinstance(confirmation, dict) and confirmation.get('source') == 'confirmed_findings':
        confirmation['source'] = 'explicit'
        changed = True
    if row.get("category") != "plate":
        return changed
    marker = row.pop("plate_verification", None)
    if marker and marker.get("applied"):
        previous = marker.get("previous_enabled", True)
        row["enabled"] = previous if type(previous) is bool else True
    changed |= bool(marker) or row.get("plate_verification_override") is not True
    row["plate_verification_override"] = True
    return changed


def _apply_detection_edits(doc, edits, cutoff=None):
    """Apply the same pending changes for preview and save, in memory."""
    enabled = edits.get("enabled", {})
    changed = False
    for i, d in enumerate(doc["detections"]):
        explicit_output = (edits.get('output_choices') or {}).get(str(i)) is True
        if explicit_output:
            changed |= _human_plate_override(d)
            changed |= not bool(d.get('output_choice_explicit'))
            d['output_choice_explicit'] = True
        if str(i) in enabled:
            if d.get("enabled", True) != bool(enabled[str(i)]):
                changed |= _human_plate_override(d)
            d["enabled"] = bool(enabled[str(i)])
    for i, box in (edits.get("box_overrides") or {}).items():
        i = int(i)
        if 0 <= i < len(doc["detections"]) and len(box) == 4:
            d = doc["detections"][i]
            new_box = [float(v) for v in box]
            if new_box != d["cbox"]:
                changed |= _human_plate_override(d)
                d["cbox"] = new_box
                d["poly"] = []
                d["poly_holes"] = []
                d["mask_pad"] = -1
                d["fallback_reason"] = ""
                d["plate_quad"] = []
    for i, span in (edits.get("time_overrides") or {}).items():
        i = int(i)
        if 0 <= i < len(doc["detections"]) and len(span) == 2:
            t0, t1 = float(span[0]), float(span[1])
            if cutoff is not None:
                t1 = min(t1, cutoff)
            if t1 > t0 >= 0:
                d = doc["detections"][i]
                if t0 != d["t_start"] or t1 != d["t_end"]:
                    changed |= _human_plate_override(d)
                if (d.get("category") == "plate" and d.get("frame_index", -1) >= 0
                        and (t0 != d["t_start"] or t1 != d["t_end"])):
                    d["frame_index"] = -1
                    d["fallback_reason"] = ""
                    d["plate_quad"] = []
                    d["poly"] = []
                    d["poly_holes"] = []
                    d["mask_pad"] = -1
                doc["detections"][i]["t_start"] = t0
                doc["detections"][i]["t_end"] = t1
                doc["detections"][i]["last_seen"] = min(
                    max(doc["detections"][i].get("last_seen", t0), t0), t1)
    return changed


@app.route("/api/jobs/<jid>/detframe/<int:i>")
def job_detframe(jid, i):
    """Full video frame at a real sighting of detection i, with its box
    outlined — the review lightbox."""
    job = JOBS.get(jid) or abort(404)
    doc = _load_job_report(job)
    d = _review_detections(job, doc)[i]
    rs = doc["render_state"]
    tref = min(max(d.get("last_seen", d["t_start"]), d["t_start"]), d["t_end"])
    exact = d.get("frame_index", -1)
    fidx = min(exact if exact >= 0 else int(tref * rs["fps"]), len(rs["cum"]) - 1)
    ox, oy = rs["cum"][fidx]
    frame = _frame_at(job, tref, rs, exact if exact >= 0 else None)
    if frame is None:
        abort(404)
    x1, y1 = int(d["cbox"][0] + ox), int(d["cbox"][1] + oy)
    x2, y2 = int(d["cbox"][2] + ox), int(d["cbox"][3] + oy)
    data = _review_mask_data(d, ox, oy, frame.shape, job, doc)
    if data is not None:
        region, mask = data
        xlo, ylo, xhi, yhi = region
        roi = frame[ylo:yhi, xlo:xhi]
        if mask.size:
            tint = np.full_like(roi, (0, 0, 255))
            blended = cv2.addWeighted(roi, 0.75, tint, 0.25, 0)
            cv2.copyTo(blended, mask, roi)
            contours, _ = cv2.findContours(mask, cv2.RETR_TREE, cv2.CHAIN_APPROX_SIMPLE)
            cv2.drawContours(frame, contours, -1, (0, 0, 255), 2,
                             offset=(xlo, ylo))
    else:
        cv2.rectangle(frame, (x1 - 4, y1 - 4), (x2 + 4, y2 + 4), (0, 0, 255), 3)
    ok, buf = cv2.imencode(".jpg", frame, [cv2.IMWRITE_JPEG_QUALITY, 84])
    from flask import Response
    return Response(buf.tobytes(), mimetype="image/jpeg")



def _save_verified_plate_sample(job, frame, points, index, tref, origin=(0, 0),
                                sample_key=None):
    """Store ONE reviewer-verified plate crop; never promote track guesses.

    Data stays inside the job directory so it inherits the job vault's
    encryption-at-rest lifecycle and is deleted with the job.
    """
    from uuid import uuid4
    p = np.asarray(points, dtype=np.float64) - np.asarray(origin, dtype=np.float64)
    h, w = frame.shape[:2]
    margin = max(12, int(0.15 * max(
        np.ptp(p[:, 0]), np.ptp(p[:, 1]))))
    x1 = max(0, int(np.floor(p[:, 0].min())) - margin)
    y1 = max(0, int(np.floor(p[:, 1].min())) - margin)
    x2 = min(w, int(np.ceil(p[:, 0].max())) + margin)
    y2 = min(h, int(np.ceil(p[:, 1].max())) + margin)
    if x2 <= x1 or y2 <= y1:
        raise ValueError("empty plate annotation crop")
    sample_dir = os.path.join(job["dir"], "plate_annotations")
    os.makedirs(sample_dir, mode=0o700, exist_ok=True)
    filename = uuid4().hex + ".jpg"
    filepath = os.path.join(sample_dir, filename)
    if not cv2.imwrite(filepath, frame[y1:y2, x1:x2],
                       [cv2.IMWRITE_JPEG_QUALITY, 95]):
        raise OSError("could not write training sample")
    try:
        os.chmod(filepath, 0o600)
    except OSError:
        pass
    entry = {"image": filename, "category": "plate",
             "verified_by_user": True, "frame_time": tref,
             "detection_index": index,
             "corners": [[round((float(x)-x1)/(x2-x1), 7),
                          round((float(y)-y1)/(y2-y1), 7)]
                         for x, y in p],
             "source": "four-corner-review"}
    manifest = os.path.join(sample_dir, "annotations.jsonl")
    if sample_key is None:
        with open(manifest, "a", encoding="utf-8") as out:
            out.write(json.dumps(entry) + "\n")
    else:
        # Autosave replaces only this manually edited source frame's sample.
        # Immutable image + atomic manifest avoids mismatched pixels/labels.
        entry["sample_key"] = sample_key
        previous = []
        temp_manifest = None
        try:
            if os.path.exists(manifest):
                with open(manifest, encoding="utf-8") as source:
                    previous = [json.loads(line) for line in source if line.strip()]
            kept = [row for row in previous if row.get("sample_key") != sample_key]
            with tempfile.NamedTemporaryFile(mode="w", encoding="utf-8",
                    dir=sample_dir, delete=False) as out:
                temp_manifest = out.name
                for row in kept + [entry]:
                    out.write(json.dumps(row) + "\n")
            os.replace(temp_manifest, manifest)
        except Exception:
            if os.path.exists(filepath):
                os.unlink(filepath)
            raise
        finally:
            if temp_manifest and os.path.exists(temp_manifest):
                os.unlink(temp_manifest)
        retained = {row.get("image") for row in kept}
        for row in previous:
            old = row.get("image", "")
            if (row.get("sample_key") == sample_key and old not in retained
                    and re.fullmatch(r"[a-f0-9]{32}\.jpg", old)):
                try:
                    os.unlink(os.path.join(sample_dir, old))
                except OSError:
                    pass

    try:
        os.chmod(manifest, 0o600)
    except OSError:
        pass


def _plate_editor_crop(box, points, width, height):
    """View-sized crop around an editable plate, including skewed corners.

    Keep enough context to find the edges of a narrow/distant plate, while
    magnifying it instead of showing the full video frame at 4K scale.
    """
    xs = [float(box[0]), float(box[2])] + [float(p[0]) for p in points]
    ys = [float(box[1]), float(box[3])] + [float(p[1]) for p in points]
    xmin, xmax = min(xs), max(xs)
    ymin, ymax = min(ys), max(ys)
    # Leave a square working area containing the plate's rotation
    # envelope. Rectangular crops clip the plate when turned 45–90°.
    cx, cy = (xmin + xmax) / 2.0, (ymin + ymax) / 2.0
    radius = max(38.0, 0.5 * np.hypot(xmax - xmin, ymax - ymin)
                 + max(28.0, 0.15 * (xmax - xmin)))
    x1 = max(0, int(np.floor(cx - radius)))
    y1 = max(0, int(np.floor(cy - radius)))
    x2 = min(width, int(np.ceil(cx + radius)))
    y2 = min(height, int(np.ceil(cy + radius)))
    if x2 <= x1 or y2 <= y1:
        abort(400, description="Plate is outside the video frame")
    return [x1, y1, x2, y2]


def _plate_preview_key(job, index, d, rs):
    exact = d.get("frame_index", -1)
    tref = min(max(float(d.get("last_seen", d["t_start"])),
                   float(d["t_start"])), float(d["t_end"]))
    fidx = exact if exact >= 0 else int(tref * float(rs["fps"]))
    if exact >= len(rs["cum"]):
        abort(400, description="Plate frame is outside the review timeline")
    fidx = min(max(0, fidx), len(rs["cum"])-1)
    if exact >= 0:
        tref = fidx / float(rs["fps"])
    payload = [_video_identity(job["video"]), index, fidx, rs["cum"][fidx],
               d["cbox"], d.get("plate_quad") or [], float(rs["fps"]), tref]
    key = hashlib.sha256(json.dumps(payload, sort_keys=True).encode()).hexdigest()
    return key, fidx, tref


def _store_plate_preview(job, index, meta, pixels):
    """One atomically replaced, lossless crop per finding, inside the job vault."""
    destination = os.path.join(job["dir"], "plate_preview_%d.npz" % int(index))
    temp = None
    try:
        with tempfile.NamedTemporaryFile(dir=job["dir"], suffix=".npz", delete=False) as out:
            temp = out.name
            np.savez_compressed(out, pixels=pixels, metadata=json.dumps(meta))
        with _REVIEW_CACHE_LOCK:
            if vault_locked():
                abort(423)
            os.replace(temp, destination)
    finally:
        if temp and os.path.exists(temp):
            os.unlink(temp)


def _plate_frame_bounds(points, box, width, height):
    """Polygon vertices may lie on the outer image edge, not just pixel centers.

    Snap only the error from six-decimal box-relative storage. Real overflow
    remains invalid; do not silently shrink a user's mask to fit the frame.
    """
    p = np.asarray(points, dtype=np.float64).copy()
    limit = np.asarray([width, height], dtype=np.float64)
    scale = np.abs(np.asarray([box[2]-box[0], box[3]-box[1]], dtype=np.float64))
    tolerance = scale * 0.5e-6 + 1e-9
    invalid = np.any((p < -tolerance) | (p > limit+tolerance), axis=1)
    p = np.where((p < 0) & (p >= -tolerance), 0, p)
    p = np.where((p > limit) & (p <= limit+tolerance), limit, p)
    return p, (np.flatnonzero(invalid)+1).tolist()


def _cached_plate_preview(job, index, key, source_key=None, points=None):
    """Read a valid published crop without occupying the video decoder.

    The cache gate also protects reads from vault encryption. Never acquire
    the work/decoder gate while holding this lock (lock order: work -> cache).
    Atomic publication means readers see either complete version, never half
    a crop. A mismatching token is a miss, not an editable stale fallback.
    """
    cache = os.path.join(job["dir"], "plate_preview_%d.npz" % int(index))
    with _REVIEW_CACHE_LOCK:
        if vault_locked():
            abort(423)
        try:
            with np.load(cache, allow_pickle=False) as stored:
                meta = json.loads(str(stored["metadata"]))
                exact = meta.get("preview_token") == key
                same_source = source_key is not None and meta.get("source_token") == source_key
                if exact or same_source:
                    # Retain the original crop only when the current shape fits.
                    # Old caches without source_token remain exact-hit-only.
                    x1, y1, x2, y2 = meta["crop"]
                    if points is not None:
                        points = _plate_frame_bounds(points, meta["box"],
                            meta["width"], meta["height"])[0].tolist()
                    if not exact and (not points or not all(
                            x1 <= x <= x2 and y1 <= y <= y2 for x, y in points)):
                        return None
                    meta = dict(meta, preview_token=key)
                    if source_key is not None:
                        meta["source_token"] = source_key
                    if points is not None:
                        meta["points"] = points
                    return meta, stored["pixels"].copy()
        except (OSError, ValueError, KeyError, EOFError, zipfile.BadZipFile):
            pass
    return None


def _plate_preview(job, index, doc=None, cache_only=False):
    if doc is None:
        doc = _load_job_report(job)
    rows = doc.get("detections", [])
    if not (0 <= index < len(rows)) or rows[index].get("category") != "plate":
        abort(404)
    d, rs = rows[index], doc["render_state"]
    if not rs.get("cum") or float(rs["fps"]) <= 0:
        abort(400, description="Review timeline not available")
    key, fidx, tref = _plate_preview_key(job, index, d, rs)
    source_key = _plate_preview_key(job, index, dict(d, plate_quad=[]), rs)[0]
    ox, oy = rs["cum"][fidx]
    box = [float(d["cbox"][0])+ox, float(d["cbox"][1])+oy,
           float(d["cbox"][2])+ox, float(d["cbox"][3])+oy]
    bw, bh = box[2]-box[0], box[3]-box[1]
    if bw <= 0 or bh <= 0:
        abort(400, description="Invalid plate detection box")
    q = d.get("plate_quad") or ((0., 0.), (1., 0.), (1., 1.), (0., 1.))
    points = [[box[0]+float(x)*bw, box[1]+float(y)*bh] for x, y in q]
    cached = _cached_plate_preview(job, index, key, source_key, points)
    if cached is not None:
        return doc, d, *cached
    if cache_only:
        return None
    # Cold generation stays bounded. Warm reads above never wait for it.
    if not _REVIEW_WORK_LOCK.acquire(blocking=False):
        abort(503, description="Another preview is decoding. Retry this finding.")
    try:
        # Another request may have published the crop before we got the gate.
        cached = _cached_plate_preview(job, index, key, source_key, points)
        if cached is not None:
            return doc, d, *cached
        frame = _frame_at(job, tref, rs, fidx if d.get("frame_index", -1) >= 0 else None)
        if frame is None:
            abort(404, description="Could not decode plate frame")
        h, w = frame.shape[:2]
        points = _plate_frame_bounds(points, box, w, h)[0].tolist()
        crop = _plate_editor_crop(box, points, w, h)
        x1, y1, x2, y2 = crop
        meta = {"i": index, "t": tref, "frame": fidx, "width": w, "height": h,
                "box": box, "crop": crop, "points": points,
                "track": d.get("track", -1), "preview_token": key,
                "source_token": source_key}
        pixels = frame[y1:y2, x1:x2].copy()
        _store_plate_preview(job, index, meta, pixels)
        return doc, d, meta, pixels
    finally:
        _REVIEW_WORK_LOCK.release()


def _plate_preview_response(meta, pixels):
    success, encoded = cv2.imencode(".jpg", pixels, [cv2.IMWRITE_JPEG_QUALITY, 95])
    if not success:
        abort(500, description="Could not encode the review frame")
    response = Response(encoded.tobytes(), mimetype="image/jpeg")
    response.headers["Cache-Control"] = "no-store"
    response.headers["X-Plate-Geometry"] = json.dumps(meta, separators=(",", ":"))
    return response


@app.route("/api/jobs/<jid>/plate_quad/<int:i>/frame")
def job_plate_quad_frame(jid, i):
    job = JOBS.get(jid) or abort(404)
    _, _, meta, pixels = _plate_preview(job, i)
    return _plate_preview_response(meta, pixels)


@app.route("/api/jobs/<jid>/plate_quad/<int:i>", methods=["GET", "POST"])
def job_plate_quad(jid, i):
    job = JOBS.get(jid) or abort(404)
    compact = request.args.get('compact') == '1'
    payload = request.get_json(silent=True) or {} if request.method == 'POST' else {}
    if compact or payload.get('compact') is True:
        if request.method == 'GET':
            return jsonify(findings_web.preview(job, i)[2])
        if job['phase'] not in ('paused','review','done'):
            return jsonify(error='Pause or finish scanning before editing.'),409
        with _REVIEW_EDIT_LOCK:
            try:
                return jsonify(findings_web.region(job,i,payload))
            except findings_web.library.ConflictError as error:
                details = {'error': str(error)}
                if getattr(error, 'current_archive', None):
                    details['current_archive'] = error.current_archive
                return jsonify(details),409
            except ValueError as error:
                return jsonify(error=str(error)),400
    if request.method == "POST" and job["phase"] not in ("paused", "review", "done"):
        return jsonify({"error": "Cannot edit plates while scanning"}), 409
    if request.method == "GET":
        _, _, meta, _ = _plate_preview(job, i)
        return jsonify(meta)
    # Serialize report writers independently of the bounded video decoder.
    if not _REVIEW_EDIT_LOCK.acquire(blocking=False):
        abort(503, description="Another review edit is saving. Retry shortly.")
    try:
        if vault_locked():
            abort(423)
        # Writes need an independently mutable authoritative report, never the
        # lightweight read-only thumbnail index.
        doc = _load_job_report(job)
        doc, d, meta, pixels = _plate_preview(job, i, doc=doc)
        payload = request.get_json(silent=True) or {}
        if doc.get("video_sections") or (job.get("section") or {}).get("role") == "export":
            fps = doc["render_state"]["fps"]
            if ((job.get("section") or {}).get("role") == "export" or any(
                _SECTIONS.locked_overlap(doc, int(row["t_start"]*fps),
                                         int(row["t_end"]*fps)+1)
                for index, row in enumerate(doc["detections"])
                if index == i or (d.get("track", -1) >= 0 and
                                  row.get("track") == d["track"]))):
                return jsonify({"error": "Open a section candidate to revise an approved section."}), 409
        autosave = payload.get("autosave") is True
        edit_id = payload.get("edit_id") if autosave else None
        if autosave and (not isinstance(edit_id, str) or
                         not re.fullmatch(r"[A-Za-z0-9_.:-]{1,120}", edit_id)):
            return jsonify({"error": "Autosave requires a valid edit identifier"}), 400
        try:
            p = np.asarray(payload["points"], dtype=np.float64)
        except (KeyError, TypeError, ValueError):
            return jsonify({"error": "Four corner points required"}), 400
        if p.shape != (4, 2) or not np.isfinite(p).all():
            return jsonify({"error": "Invalid corner coordinates"}), 400
        h, w = meta["height"], meta["width"]
        p, invalid = _plate_frame_bounds(p, meta["box"], w, h)
        if invalid:
            details = "; ".join("corner %d (x=%.6f, y=%.6f)" %
                                (k, p[k-1, 0], p[k-1, 1]) for k in invalid)
            return jsonify({"error": "Corners must be inside the video frame: " + details +
                            ". Allowed edges: x=0..%d, y=0..%d." % (w, h),
                            "invalid_corners": invalid, "frame_size": [w, h]}), 400
        contour = p.astype(np.float32).reshape((-1, 1, 2))
        if not cv2.isContourConvex(contour) or cv2.contourArea(contour) < 8.0:
            return jsonify({"error": "Corners must form a convex quadrilateral"}), 400
        box = meta["box"]
        bw, bh = box[2]-box[0], box[3]-box[1]
        q = [[round((float(x)-box[0])/bw, 6), round((float(y)-box[1])/bh, 6)] for x, y in p]
        apply_track, tid = autosave or payload.get("apply_track") is True, d.get("track", -1)
        applied = sum(1 for j, row in enumerate(doc["detections"])
                      if j == i or (apply_track and tid >= 0 and row.get("track", -1) == tid
                                    and row.get("category") == "plate"))
        sample_key = (hashlib.sha256(json.dumps([
            _video_identity(job["video"]), i, meta["frame"]]).encode()).hexdigest()
                      if autosave else None)
        receipt = d.get("plate_edit_receipt") or {}
        if autosave and receipt.get("id") == edit_id:
            if (d.get("plate_quad") != q or receipt.get("source") != sample_key
                    or receipt.get("token") != payload.get("preview_token")):
                return jsonify({"error": "Edit identifier belongs to different corners"}), 409
            return jsonify({"ok": True, "applied": applied,
                            "verified_samples_added": 0, "preview": meta})
        if (payload.get("preview_token") is not None and
                payload["preview_token"] != meta["preview_token"]):
            return jsonify({"error": "This finding changed. Reload its preview before saving."}), 409
        if autosave and np.allclose(p, meta["points"], rtol=0, atol=1e-5):
            return jsonify({"ok": True, "applied": 0,
                            "verified_samples_added": 0, "preview": meta})
        x1, y1, x2, y2 = meta["crop"]
        # The inline editor constrains edits to its visible source crop. Older
        # clients may submit a wider polygon; decode once only for that case.
        if (np.all(p[:, 0] >= x1) and np.all(p[:, 0] <= x2) and
                np.all(p[:, 1] >= y1) and np.all(p[:, 1] <= y2)):
            _save_verified_plate_sample(job, pixels, p, i, meta["t"],
                                        origin=(x1, y1), sample_key=sample_key)
        else:
            frame = _frame_at(job, meta["t"], doc["render_state"],
                              meta["frame"] if d.get("frame_index", -1) >= 0 else None)
            if frame is None:
                abort(404)
            _save_verified_plate_sample(job, frame, p, i, meta["t"],
                                        sample_key=sample_key)
            meta["crop"] = _plate_editor_crop(box, p, w, h)
            x1, y1, x2, y2 = meta["crop"]
            pixels = frame[y1:y2, x1:x2].copy()
        d["verified_label"] = "plate"
        changed = 0
        for j, row in enumerate(doc["detections"]):
            if j == i or (apply_track and tid >= 0 and row.get("track", -1) == tid
                          and row.get("category") == "plate"):
                _human_plate_override(row)
                row["plate_quad"] = q
                row.pop("plate_edit_receipt", None)
                changed += 1
        if autosave:
            d["plate_edit_receipt"] = {"id": edit_id, "source": sample_key,
                                       "token": payload.get("preview_token")}
        stop_review.atomic_report(os.path.join(job["dir"], "report.json"), doc)
        # Reuse the exact source pixels after saving; round-trip the stored
        # geometry/token so reopening doesn't fetch/decode the video again.
        meta["points"] = _plate_frame_bounds(
            [[box[0]+x*bw, box[1]+y*bh] for x, y in q], box, w, h)[0].tolist()
        meta["preview_token"] = _plate_preview_key(job, i, d, doc["render_state"])[0]
        _store_plate_preview(job, i, meta, pixels)
        return jsonify({"ok": True, "applied": changed,
                        "verified_samples_added": 1, "preview": meta})
    finally:
        _REVIEW_EDIT_LOCK.release()


def _requested_review_frame(rstate):
    raw = request.args.get("frame")
    if raw is None:
        return None
    try:
        index = int(raw)
    except (TypeError, ValueError):
        abort(400, description="invalid frame index")
    if index < 0 or index >= len(rstate["cum"]):
        abort(400, description="frame index out of range")
    return index


@app.route("/api/jobs/<jid>/boxes_at", methods=["GET", "POST"])
def job_boxes_at(jid):
    """Active blur boxes (screen coords) at time t, plus the scroll offset so
    the client can convert edited boxes back to content coordinates."""
    job = JOBS.get(jid) or abort(404)
    doc = _load_job_report(job)
    if request.method == "POST":
        _apply_detection_edits(doc, request.get_json(silent=True) or {})
    rs = doc["render_state"]
    fidx = _requested_review_frame(rs)
    t = float(request.args.get("t", 0)) if fidx is None else fidx / rs["fps"]
    if fidx is None:
        fidx = min(max(0, int(round(t * rs["fps"]))), len(rs["cum"]) - 1)
    ox, oy = rs["cum"][fidx]
    boxes = []
    cap = cv2.VideoCapture(job["video"])
    shape = (int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT)),
             int(cap.get(cv2.CAP_PROP_FRAME_WIDTH)))
    cap.release()
    want_all = request.args.get("all") == "1"
    rows = _review_detections(job, doc)
    active = [(i, d) for i, d in enumerate(rows)
              if (d.get("owned_start_frame", -1) < 0 or fidx >= d["owned_start_frame"])
              and (d.get("owned_end_frame", -1) < 0 or fidx < d["owned_end_frame"])
              and (d.get("frame_index", -1) == fidx if d.get("frame_index", -1) >= 0
                   else d["t_start"] - 0.01 <= t <= d["t_end"] + 0.01)]
    # Use the renderer's identity-based selector and retain report indices.
    from types import SimpleNamespace
    candidates = [(i, d, SimpleNamespace(t_start=d["t_start"],
                   dense=d.get("dense", False), track=d.get("track", -1)))
                  for i, d in active if d.get("enabled", True)]
    winners = {id(x) for x in openscrub._dedupe_dense([c[2] for c in candidates])}
    selected = {i for i, _, obj in candidates if id(obj) in winners}
    for i, d in active:
        if i not in selected and (d.get("enabled", True) or not want_all):
            continue
        if True:
            boxes.append({"i": i, "category": d["category"],
                          "enabled": d.get("enabled", True),
                          "text": d.get("text", ""),
                          "verified_label": d.get("verified_label", ""),
                          "human_confirmation": d.get("human_confirmation"),
                          "output_choice_explicit": bool(d.get("output_choice_explicit")),
                          "human_region_confirmed": bool(d.get("human_region_confirmed")),
                          "learning_conflict": d.get("learning_conflict", ""),
                          "learning_score": d.get("learning_score"),
                          "plate_verification": d.get("plate_verification"),
                          "plate_quad": d.get("plate_quad") or [],
                          "fallback_reason": d.get("fallback_reason", ""),
                          "shaped": bool(d.get("poly")),
                          "mask_contours": _review_mask(d, ox, oy, shape, job, doc),
                          "t_start": d["t_start"], "t_end": d["t_end"],
                          "box": [d["cbox"][0] + ox, d["cbox"][1] + oy,
                                  d["cbox"][2] + ox, d["cbox"][3] + oy]})
    return jsonify({"t": t, "frame": fidx, "ox": ox, "oy": oy, "boxes": boxes})


@app.route("/api/jobs/<jid>/thumb/<int:i>")
def job_thumb(jid, i):
    job = JOBS.get(jid) or abort(404)
    doc = _load_preview_report(job)
    if not (0 <= i < len(doc["detections"])):
        abort(404)
    cache_only = request.args.get("cache_only") == "1"
    if doc["detections"][i].get("category") == "plate":
        preview = _plate_preview(job, i, doc=doc, cache_only=cache_only)
        if preview is None:
            return Response(status=204, headers={"Cache-Control": "no-store"})
        _, _, meta, pixels = preview
        return _plate_preview_response(meta, pixels)
    # i is already a Flask <int:> route var, but CodeQL doesn't trust the
    # converter — format it as an explicit non-negative integer so the
    # cache filename can never carry anything but digits.
    i = int(i)
    if i < 0:
        abort(404)
    revision = doc.get('preview_revision')
    suffix = ('_' + hashlib.sha256(str(revision).encode()).hexdigest()[:16]) if revision else ''
    cache = os.path.join(job["dir"], "thumb2_%d%s.jpg" % (i, suffix))
    if not os.path.exists(cache):
        if cache_only:
            return Response(status=204, headers={"Cache-Control": "no-store"})
        d = doc["detections"][i]
        rs = doc["render_state"]
        # cut the thumbnail at a moment the detector actually SAW the object.
        # t_start can be earlier than the object's appearance (backtracking
        # deliberately moves it to just before onset) — a frame there shows
        # nothing and made review pictures mismatch their text.
        ls = min(max(d.get("last_seen", d["t_start"]), d["t_start"]),
                 d["t_end"])
        mid = (d["t_start"] + d["t_end"]) / 2
        crop = None
        pad = 24
        times = (ls,) if d.get("frame_index", -1) >= 0 else (ls, mid, min(d["t_start"] + 0.2, d["t_end"]))
        for tref in times:
            exact = d.get("frame_index", -1)
            fidx = min(exact if exact >= 0 else int(tref * rs["fps"]), len(rs["cum"]) - 1)
            ox, oy = rs["cum"][fidx]
            frame = _frame_at(job, tref, rs, exact if exact >= 0 else None)
            if frame is None:
                continue
            h, w = frame.shape[:2]
            x1 = max(0, int(d["cbox"][0] + ox) - pad)
            y1 = max(0, int(d["cbox"][1] + oy) - pad)
            x2 = min(w, int(d["cbox"][2] + ox) + pad)
            y2 = min(h, int(d["cbox"][3] + oy) + pad)
            c = frame[y1:y2, x1:x2]
            if c.size == 0:
                continue
            crop = c
            inner = c[pad:-pad or None, pad:-pad or None]
            if inner.size and float(inner.std()) > 8:
                break   # crop shows real content — use this moment
        if crop is None:
            abort(404)
        cv2.rectangle(crop, (pad, pad), (crop.shape[1] - pad,
                                         crop.shape[0] - pad), (0, 0, 255), 2)
        cv2.imwrite(cache, crop, [cv2.IMWRITE_JPEG_QUALITY, 80])
    response = send_file(cache, mimetype="image/jpeg", max_age=0)
    # The URL identifies a report row, which may change after a rescan.
    response.headers['Cache-Control'] = 'no-store'
    return response


@app.route("/api/jobs/<jid>/frame_at")
def job_frame_at(jid):
    job = JOBS.get(jid) or abort(404)
    t = max(0.0, float(request.args.get("t", 0)))
    path = (job["output"] if request.args.get("src") == "output"
            and job.get("output") else job["video"])
    if request.args.get("frame") is not None:
        rs = _load_job_report(job)["render_state"]
        fidx = _requested_review_frame(rs)
        frame = _read_exact_frame(path, fidx)
        if frame is None:
            abort(404)
        ok, buf = cv2.imencode(".jpg", frame, [cv2.IMWRITE_JPEG_QUALITY, 82])
        if not ok:
            abort(500)
        return Response(buf.tobytes(), mimetype="image/jpeg")
    cap = cv2.VideoCapture(path)
    # seek by TIMESTAMP, not frame index: the original upload is often VFR
    # (iPhone), where index = t*fps drifts out of sync with the CFR output
    # and can overshoot the file entirely (broken compare pane)
    frame = None
    for tt in (t, max(0.0, t - 0.34), max(0.0, t - 1.0), 0.0):
        cap.set(cv2.CAP_PROP_POS_MSEC, tt * 1000)
        ok, fr = cap.read()
        if ok:
            frame = fr
            break   # walk back instead of 404ing at the very end of the file
        if tt == 0.0:
            break
    cap.release()
    if frame is None:
        abort(404)
    ok, buf = cv2.imencode(".jpg", frame, [cv2.IMWRITE_JPEG_QUALITY, 82])
    return Response(buf.tobytes(), mimetype="image/jpeg")


@app.route("/api/jobs/<jid>/video")
def job_video_stream(jid):
    """Range-aware stream of the job's scan video so review can PLAY the
    footage with live boxes (issue #17: the box editor was scrub-only,
    'you cannot play review and see hits'). Serves the same file frame_at
    reads — for HDR/VFR jobs that is the normalized SDR scan copy, which
    every browser can decode."""
    job = JOBS.get(jid) or abort(404)
    if not (job.get("video") and os.path.exists(job["video"])):
        abort(404)
    return send_file(job["video"], conditional=True)


def _serialize_review_edit(fn):
    from functools import wraps
    @wraps(fn)
    def write(*args, **kwargs):
        if not _REVIEW_EDIT_LOCK.acquire(blocking=False):
            abort(503, description="Another review edit is saving. Retry shortly.")
        try:
            if vault_locked():
                abort(423)
            return fn(*args, **kwargs)
        finally:
            _REVIEW_EDIT_LOCK.release()
    return write


def _serialize_review_read(fn):
    """Protect small stored-picture I/O from vault encryption, without decoding.

    Callers must not acquire the edit/decoder gates inside this cache gate.
    Allow ordinary concurrent thumbnails a brief wait for another small read.
    Bound the wait during encryption, then recheck the vault after acquisition.
    """
    from functools import wraps
    @wraps(fn)
    def read(*args, **kwargs):
        if not _REVIEW_CACHE_LOCK.acquire(timeout=1.):
            abort(503, description="Saved pictures are temporarily busy. Retry shortly.")
        try:
            if vault_locked():
                abort(423)
            return fn(*args, **kwargs)
        finally:
            _REVIEW_CACHE_LOCK.release()
    return read



@app.errorhandler(learned_models.ModelError)
def learned_model_error(error):
    app.logger.warning("Learned model operation failed: %s", error)
    return jsonify({"error": str(error)}), 400


@app.route("/api/jobs/learned-models")
@_serialize_review_edit
def learned_model_list():
    models = learned_models.list_models(learned_models_root())
    for model in models:
        if model.get('id'):
            model['training'] = findings_web.training.training_info(learned_models_root(), model['id'])
    return jsonify({"models": models})


@app.route("/api/jobs/<jid>/plate-verifier", methods=["POST"])
@_serialize_review_edit
def job_plate_verifier(jid):
    job = JOBS.get(jid) or abort(404)
    protected = _SECTIONS.whole_job_error(job)
    if protected:
        return jsonify({"error": protected}), 409
    payload = request.get_json(silent=True)
    if not isinstance(payload, dict) or payload.get("mode", "review") not in ("review", "filter"):
        return jsonify({"error": "Choose a retained candidate and review or filter mode."}), 400
    if job["phase"] not in ("review", "done", "paused"):
        return jsonify({"error": "Finish or pause the current work before checking detections."}), 409
    if job.get("trackbg", {}).get("state") == "running":
        return jsonify({"error": "Finish tracking before checking detections."}), 409
    with _REVIEW_WORK_LOCK:
        candidate = learning_candidates.load_candidate(job["dir"], payload.get("candidate_id"))
    job["verification_previous_phase"] = job["phase"]
    job["verification_request"] = {"candidate_id": candidate["id"], "mode": payload.get("mode", "review")}
    job["cancel"].clear()
    job["stop"].clear()
    job.update(phase="learning", error=None, eta=None,
               learning={"stage": "queued", "message": "Queued secondary plate check; no retraining needed"})
    WORK_Q.put((jid, "verify"))
    return jsonify({"ok": True})


@app.route("/api/jobs/<jid>/learned-models", methods=["POST"])
@_serialize_review_edit
def learned_model_save(jid):
    job = JOBS.get(jid) or abort(404)
    if job["phase"] not in ("review", "done", "paused"):
        return jsonify({"error": "Finish or pause the current work before saving a model."}), 409
    payload = request.get_json(silent=True)
    if not isinstance(payload, dict):
        return jsonify({"error": "Supply a model name and optional environment description."}), 400
    with _REVIEW_WORK_LOCK:
        if "candidate_id" in payload:
            model = learned_models.save_candidate(
                learned_models_root(), job["dir"], payload["candidate_id"],
                payload.get("name"), payload.get("description", ""))
        else:
            model = learned_models.save_model(
                learned_models_root(), job["dir"], payload.get("name"),
                payload.get("description", ""))
    return jsonify({"model": model})


@app.route("/api/jobs/learned-models/import", methods=["POST"])
@_serialize_review_edit
def learned_model_import():
    uploaded = request.files.get("model")
    if uploaded is None or not uploaded.filename:
        return jsonify({"error": "Choose an OpenScrub model package."}), 400
    with _REVIEW_WORK_LOCK:
        model = learned_models.import_model(learned_models_root(), uploaded.stream)
    return jsonify({"model": model})


@app.route("/api/jobs/learned-models/<model_id>/export")
@_serialize_review_edit
def learned_model_export(model_id):
    import io
    with _REVIEW_WORK_LOCK:
        data = learned_models.export_model(learned_models_root(), model_id)
    return send_file(io.BytesIO(data), mimetype="application/zip",
                     as_attachment=True, download_name=model_id + ".openscrub-model",
                     max_age=0)


@app.route("/api/jobs/learned-models/<model_id>", methods=["DELETE"])
@_serialize_review_edit
def learned_model_delete(model_id):
    with _REVIEW_WORK_LOCK:
        learned_models.delete_model(learned_models_root(), model_id)
    return jsonify({"ok": True})


@app.route("/api/jobs/<jid>/detections", methods=["POST"])
@_serialize_review_edit
def job_save_edits(jid):
    job = JOBS.get(jid) or abort(404)
    if job["phase"] not in ("paused", "review", "done"):
        return jsonify({"error": "Review edits require a paused or "
                                 "finished scan"}), 409
    started = time.perf_counter()
    edits = request.get_json(force=True)
    parsed = time.perf_counter()
    path = os.path.join(job["dir"], "report.json")
    doc = _load_job_report(job)
    loaded = time.perf_counter()
    # Legacy tabs send all rows. A retry of already-published choices needs
    # confirmation, not another expensive rewrite. Non-choice edits still use
    # the full existing transaction (manual additions must never be skipped).
    changed = bool(edits.get("manual") or edits.get("box_overrides") or
                   edits.get("time_overrides") or "audio" in edits)
    for key, enabled in (edits.get("enabled") or {}).items():
        try:
            i = int(key)
        except (ValueError, TypeError):
            continue
        if 0 <= i < len(doc["detections"]):
            changed |= doc["detections"][i].get("enabled", True) != bool(enabled)
    stop_meta = doc.get("stop_review") or {}
    cutoff = (stop_meta["next_frame"] / stop_meta["fps"]
              if stop_meta.get("state") == "paused" else None)
    if cutoff is not None:
        # Paused jobs only contain verified footage up to this boundary.
        # Do not let a manual UI box implicitly mark the unscanned tail.
        for m in edits.get("manual", []):
            if float(m.get("t_start", 0)) >= cutoff:
                return jsonify({"error": "Manual boxes must be inside the "
                                        "scanned portion while paused"}), 400
    # Only an explicit reviewer judgement is training evidence.
    # Keep-visible is NOT a negative label: a user may intentionally keep
    # a real plate unredacted. Nor is default enabled a positive label.
    for key, label in (edits.get("verified_labels") or {}).items():
        try:
            i = int(key)
        except (ValueError, TypeError):
            continue
        if 0 <= i < len(doc["detections"]):
            d = doc["detections"][i]
            if d.get("category") == "plate" and label in ("plate", "not_plate", "clear"):
                normalized = "" if label == "clear" else label
                changed |= _human_plate_override(d)
                changed |= d.get("verified_label", "") != normalized
                d["verified_label"] = normalized
    changed |= _apply_detection_edits(doc, edits, cutoff=cutoff)
    rs = doc["render_state"]
    for m in edits.get("manual", []):
        t0 = float(m["t_start"]); t1 = float(m["t_end"])
        tref = float(m.get("t_ref", t0))
        if cutoff is not None:
            t1 = min(t1, cutoff)
        fidx = min(int(tref * rs["fps"]), len(rs["cum"]) - 1)
        ox, oy = rs["cum"][fidx]
        b = m["screen_box"]
        doc["detections"].append({
            "t_start": t0, "t_end": t1,
            "cbox": [int(b[0] - ox), int(b[1] - oy),
                     int(b[2] - ox), int(b[3] - oy)],
            "category": "manual", "text": "user-drawn", "confidence": 1.0,
            "aoff": [ox, oy], "last_seen": t0, "enabled": True})
    if "audio" in edits:
        # audio redaction spans (mute/bleep): stored in the report so the
        # --from-report render applies them and re-renders keep them
        doc["audio_redactions"] = [
            {"t0": float(s["t0"]), "t1": float(s["t1"]),
             "mode": (s.get("mode") if s.get("mode") in ("mute", "bleep")
                      else "mute")}
            for s in (edits.get("audio") or [])
            if float(s.get("t1", 0)) > float(s.get("t0", 0)) >= 0]
    applied = time.perf_counter()
    if changed:
        if doc.get("video_sections") or (job.get("section") or {}).get("role") == "export":
            _SECTIONS.guard_edits(job, _load_job_report(job), doc)
        stop_review.atomic_report(path, doc)
    published = time.perf_counter()
    # suggest allowlisting any string whose EVERY instance was disabled —
    # the review just taught us it's a recurring false positive
    per = {}
    for d in doc["detections"]:
        if d["category"] in ("name",):
            per.setdefault(d["text"], []).append(d.get("enabled", True))
    suggest = sorted(t for t, states in per.items()
                     if len(states) >= 2 and not any(states))
    timings = dict(zip(("parse", "load", "apply", "write"),
                       [round((b-a)*1000, 2) for a, b in
                        ((started, parsed), (parsed, loaded),
                         (loaded, applied), (applied, published))]))
    response = jsonify({"ok": True, "total": len(doc["detections"]),
                        "suggest_allowlist": suggest, "changed": bool(changed),
                        "timings_ms": timings})
    response.headers["Server-Timing"] = ", ".join(
        "%s;dur=%.2f" % (stage, elapsed) for stage, elapsed in timings.items())
    return response


@app.route("/api/jobs/<jid>/track_object", methods=["POST"])
def job_track_object(jid):
    """Targeted redaction: the user circled an object on one frame and
    picked a time window on the review timeline — template-track it through
    that window and add the result as a dense track in the report, so the
    review shows one card (with fan-out) and the render blurs it wherever
    it went. Runs in a background thread; poll /track_status."""
    job = JOBS.get(jid) or abort(404)
    if job.get("trackbg", {}).get("state") == "running":
        return jsonify({"error": "tracking already in progress"}), 409
    p = request.get_json(force=True)
    try:
        box = [float(v) for v in p["box"]]
        t_ref, t0, t1 = (float(p["t_ref"]), float(p["t0"]), float(p["t1"]))
    except (KeyError, TypeError, ValueError):
        abort(400)
    if len(box) != 4 or not (t1 > t0 >= 0) or not (t0 <= t_ref <= t1):
        abort(400)
    locked_doc = _load_job_report(job)
    if ((job.get("section") or {}).get("role") == "export" or
        _SECTIONS.locked_overlap(locked_doc, int(t0*locked_doc["render_state"]["fps"]),
                                int(t1*locked_doc["render_state"]["fps"])+1)):
        return jsonify({"error": "Open a section candidate to track inside an approved section."}), 409
    if job["phase"] == "paused":
        saved = stop_review.validate_resume(_load_job_report(job))
        until = saved["next_frame"] / saved["fps"]
        if t_ref >= until or t0 >= until:
            return jsonify({"error": "Track seed is outside the scanned "
                                     "portion"}), 400
        t1 = min(t1, until)
    # Optional manually drawn 4-corner license plate (TL, TR, BR, BL).
    # These points are relative to the submitted seed box, not the frame.
    quad_req = None
    if "plate_quad" in p:
        try:
            q = np.asarray(p["plate_quad"], dtype=np.float64)
        except (TypeError, ValueError):
            abort(400)
        if (q.shape != (4, 2) or not np.isfinite(q).all() or
                np.any(q < -0.5) or np.any(q > 1.5) or
                not cv2.isContourConvex(q.astype(np.float32).reshape((-1, 1, 2))) or
                cv2.contourArea(q.astype(np.float32)) < 0.002):
            abort(400)
        quad_req = [[round(float(v), 6) for v in pt] for pt in q]
    require_confirmation = p.get("require_confirmation") is True
    st = {"state": "running", "added": 0, "error": None}
    job["trackbg"] = st

    def _run():
        try:
            class L(openscrub.Callbacks):
                def log(self, m):
                    job["log"].append(m)
            det = None
            if quad_req is None:
                try:
                    # same person-model resolution the scan uses: the panel
                    # selection first, then the engine's default ladder
                    mid = load_model_select().get("person")
                    p = find_model_file("%s.onnx" % mid) if mid else None
                    det = openscrub.PersonDetector(L(), model_path=p,
                                                   thresh=0.2)
                    if det.net is None and det.ort is None:
                        det = None
                except Exception:
                    det = None
            samples = openscrub.track_manual_region(
                job["video"], box, t_ref, t0, t1, cb=L(),
                person_det=(det if quad_req is None else None))
            if not samples:
                st.update(state="done", added=0,
                          error="could not track that region — try a "
                                "larger box or a frame where it's clearer")
                return
            doc = _load_job_report(job)
            rs = doc["render_state"]
            fps = float(rs["fps"]) or 30.0
            step = 2.0 / fps
            tid = max([d.get("track", -1) for d in doc["detections"]]
                      + [-1]) + 1
            new = []
            tcls = samples[0][4] if len(samples[0]) > 4 else None
            label = ("tracked %s" % openscrub.COCO_NAMES[tcls]
                     if tcls is not None
                     and 0 <= tcls < len(openscrub.COCO_NAMES)
                     else "tracked object")
            if quad_req is not None:
                label = "manually drawn plate"
            for s in samples:
                t, b, score = s[0], s[1], s[2]
                poly = s[3] if len(s) > 3 and s[3] else ()
                fidx = min(int(t * fps), len(rs["cum"]) - 1)
                ox, oy = rs["cum"][fidx]
                new.append({
                    "t_start": t, "t_end": t + step * 1.2,
                    "cbox": [int(b[0] - ox), int(b[1] - oy),
                             int(b[2] - ox), int(b[3] - oy)],
                    "category": ("plate" if quad_req is not None else "manual"),
                    "text": label,
                    "confidence": round(float(score), 3),
                    "aoff": [ox, oy], "last_seen": t,
                    "dense": True, "track": tid, "enabled": True,
                    "plate_quad": (quad_req or []),
                    "poly": ([[[float(x), float(y)] for x, y in c]
                              for c in poly] if quad_req is None else [])})
            # grace pads: cover the sub-sample sliver at both ends
            new[0]["t_start"] = max(0.0, new[0]["t_start"] - 0.25)
            new[-1]["t_end"] += 0.25
            seed_index = len(doc["detections"])
            doc["detections"].extend(new)
            if quad_req is not None and require_confirmation:
                # Drawing records an area, not an Is a plate decision. Only
                # the actual drawn source instant has human-provided corners;
                # other tracked positions remain geometric predictions.
                seed = min(new, key=lambda row: abs(row["last_seen"]-t_ref))
                if abs(seed["last_seen"]-t_ref) < 1e-6:
                    seed["human_region_confirmed"] = True
            elif quad_req is not None:
                # The drawn reference is reviewed; propagated frames aren't.
                nearest = min(range(len(new)),
                              key=lambda k: abs(new[k]["t_start"]-t_ref))
                new[nearest]["verified_label"] = "plate"
            if quad_req is not None and not require_confirmation:
                frame = _frame_at(job, t_ref, rs)
                if frame is not None:
                    points = [[box[0] + qx*(box[2]-box[0]),
                               box[1] + qy*(box[3]-box[1])]
                              for qx, qy in quad_req]
                    _save_verified_plate_sample(job, frame, points,
                                                seed_index, t_ref)
            path = os.path.join(job["dir"], "report.json")
            with _REVIEW_EDIT_LOCK:
                current = _load_job_report(job)
                # Tracking runs in the background. Publish against the latest
                # report so concurrent section approvals and edits survive.
                if current != doc:
                    current["detections"].extend(new)
                    proposed = current
                else:
                    proposed = doc
                _SECTIONS.guard_edits(job, _load_job_report(job), proposed)
                stop_review.atomic_report(path, proposed)
            job["log"].append(
                "      tracked object: %d position(s), %.1f-%.1fs "
                "(review card added)" % (len(new),
                                         new[0]["t_start"], new[-1]["t_end"]))
            st.update(state="done", added=len(new))
        except Exception as e:
            diagnostics.exception("background_tracking_failed", job)
            st.update(state="done", added=0, error=str(e))

    threading.Thread(target=_run, daemon=True).start()
    return jsonify({"ok": True})


@app.route("/api/jobs/<jid>/track_status")
def job_track_status(jid):
    job = JOBS.get(jid) or abort(404)
    return jsonify(job.get("trackbg") or {"state": "idle"})


def _models_state(kind):
    """Registry entries + installed/selected/active state for one kind."""
    models = openscrub.load_model_registry(kind)
    sel = load_model_select().get(kind, "")
    out = []
    for m in models:
        out.append({
            "id": m.get("id"), "label": m.get("label"),
            "license": m.get("license"), "source_url": m.get("source_url"),
            "notes": m.get("notes"), "recommended": bool(m.get("recommended")),
            "verified": m.get("download_url") not in (None, "", "TODO_VERIFY"),
            "pinned": bool(m.get("sha256")) and m.get("sha256") != "TODO_VERIFY",
            "installed": bool(find_model_file("%s.onnx" % m.get("id"))),
            "attribution": m.get("attribution", ""),
        })
    if kind == "face":
        p = find_model_file("%s.onnx" % sel) if sel else None
        active = os.path.basename(p) if p else "built-in YuNet"
        status = ("Active: " + active) if p else \
            "Active: built-in YuNet (works out of the box — models below are optional upgrades)"
    else:
        # plate and person share the same model-required pattern: INERT
        # (loudly) until a model is installed or provided
        env = ("OPENSCRUB_PERSON_MODEL" if kind == "person"
               else "OPENSCRUB_PLATE_MODEL")
        base = ("person_yolov8.onnx" if kind == "person"
                else "plate_yolov8.onnx")
        what = ("person (full-body blur)" if kind == "person"
                else "plate")
        active = os.environ.get(env)
        if not (active and os.path.exists(active)):
            active = ((find_model_file("%s.onnx" % sel) if sel else None)
                      or find_model_file(base))
        if not active:
            for m in models:
                p = find_model_file("%s.onnx" % m.get("id"))
                if p:
                    active = p
                    break
        status = ("Active model: " + os.path.basename(active)) if active else \
            ("No model installed — %s detection is INACTIVE until you "
             "install or provide one." % what)
    return {"models": out, "selected": sel, "status": status,
            "active": bool(active) if kind != "face" else True}


@app.route("/api/models/<kind>")
def models_list(kind):
    if kind not in ("face", "plate", "person"):
        abort(404)
    return jsonify(_models_state(kind))


@app.route("/api/models/<kind>/select", methods=["POST"])
def models_select(kind):
    if kind not in ("face", "plate", "person"):
        abort(404)
    mid = (request.get_json(force=True) or {}).get("id", "")
    if mid and not any(m.get("id") == mid
                       for m in openscrub.load_model_registry(kind)):
        return jsonify({"error": "unknown model id"}), 404
    sel = load_model_select()
    sel[kind] = mid
    save_model_select(sel)
    return jsonify({"ok": True, "selected": mid})


@app.route("/api/model_status")
def model_status():
    """Whether the model-requiring detectors would find a model RIGHT NOW
    (the same resolution ladder the engine runs — selected file first,
    then conventional/registry/cache locations). Powers the editor's
    'this category will detect nothing' warnings (issue #18). screen
    rides the person model. plate_autofetch says whether a missing plate
    model would self-heal at scan start (recommended registry entry is
    permissively licensed and hash-pinned)."""
    sel = load_model_select()
    out = {}
    for kind, cls in (("plate", openscrub.PlateDetector),
                      ("person", openscrub.PersonDetector)):
        mp = None
        mid = sel.get(kind)
        if mid:
            mp = find_model_file("%s.onnx" % mid)
        try:
            out[kind] = bool(cls.resolve_model(mp)[0])
        except Exception:
            diagnostics.exception("model_availability_check_failed", model_kind=kind)
            out[kind] = True        # can't tell -> don't cry wolf
    try:
        rec = next((m for m in openscrub.load_model_registry("plate")
                    if m.get("recommended")), None)
        out["plate_autofetch"] = bool(
            rec and (rec.get("sha256") or "").strip()
            and str(rec.get("license", "")).lower().startswith(
                ("mit", "apache", "bsd")))
    except Exception:
        diagnostics.exception("plate_registry_load_failed")
        out["plate_autofetch"] = False
    return jsonify(out)


_model_dl = {"state": "idle", "pct": 0, "error": "", "id": "", "kind": ""}


@app.route("/api/models/<kind>/<mid>/download", methods=["POST"])
def model_download(kind, mid):
    """Download+verify a registry model in a background thread."""
    if kind not in ("face", "plate", "person"):
        abort(404)
    entry = next((m for m in openscrub.load_model_registry(kind)
                  if m.get("id") == mid), None)
    if entry is None:
        return jsonify({"error": "unknown model id"}), 404
    if _model_dl["state"] == "downloading":
        return jsonify({"error": "a download is already in progress"}), 409
    _model_dl.update(state="downloading", pct=0, error="", id=mid, kind=kind)
    def work():
        try:
            openscrub.download_model(
                entry, kind,
                progress=lambda f: _model_dl.update(pct=int(f * 100)))
            _model_dl.update(state="done", pct=100)
        except Exception as e:
            diagnostics.exception("model_download_failed", model_id=mid, model_kind=kind)
            _model_dl.update(state="error", error=str(e))
    threading.Thread(target=work, daemon=True).start()
    return jsonify({"ok": True})


@app.route("/api/models/download_status")
def model_download_status():
    return jsonify(_model_dl)


# Detection-quality tiers: one click maps to per-kind registry selections
# (the "" face id = built-in YuNet). Applying a tier downloads any missing
# model first and only then selects it — a selection must never point at a
# file that is not on disk (fail closed). Manual picks in the models panel
# still work; when they stop matching a tier the UI shows "Custom".
QUALITY_TIERS = {
    "fast": {"face": "", "plate": "oim-yolov9-t-640",
             "person": "yolo11n-seg-person"},
    "balanced": {"face": "centerface", "plate": "oim-yolov9-t-640",
                 "person": "yolo11s-seg-person"},
    "accurate": {"face": "centerface", "plate": "oim-yolov9-s-608",
                 "person": "yolo11m-seg-person"},
}

_tier_apply = {"state": "idle", "tier": "", "step": "", "error": ""}


@app.route("/api/quality_tier", methods=["GET", "POST"])
def quality_tier():
    if request.method == "GET":
        sel = load_model_select()
        cur = next((tid for tid, t in QUALITY_TIERS.items()
                    if all(sel.get(k, "") == v for k, v in t.items())), "")
        needs = {tid: [k for k, v in t.items()
                       if v and not find_model_file("%s.onnx" % v)]
                 for tid, t in QUALITY_TIERS.items()}
        return jsonify({"tier": cur, "applying": _tier_apply, "needs": needs})
    tier = (request.get_json(force=True) or {}).get("tier", "")
    t = QUALITY_TIERS.get(tier)
    if t is None:
        return jsonify({"error": "unknown tier"}), 404
    if _model_dl["state"] == "downloading" or _tier_apply["state"] == "applying":
        return jsonify({"error": "a download is already in progress"}), 409
    _tier_apply.update(state="applying", tier=tier, step="", error="")

    def work():
        try:
            for kind, mid in t.items():
                if mid:
                    entry = next((m for m in
                                  openscrub.load_model_registry(kind)
                                  if m.get("id") == mid), None)
                    if entry is None:
                        raise RuntimeError(
                            "model registry is missing %s/%s" % (kind, mid))
                    if not find_model_file("%s.onnx" % mid):
                        _tier_apply["step"] = ("downloading %s"
                                               % entry.get("label", mid))
                        _model_dl.update(state="downloading", pct=0,
                                         error="", id=mid, kind=kind)
                        try:
                            openscrub.download_model(
                                entry, kind,
                                progress=lambda f:
                                    _model_dl.update(pct=int(f * 100)))
                            _model_dl.update(state="done", pct=100)
                        except Exception:
                            _model_dl.update(state="error")
                            raise
                sel = load_model_select()
                sel[kind] = mid
                save_model_select(sel)
            _tier_apply.update(state="done", step="")
        except Exception as e:
            diagnostics.exception("model_tier_setup_failed")
            _tier_apply.update(state="error", error=str(e), step="")
    threading.Thread(target=work, daemon=True).start()
    return jsonify({"ok": True})


# legacy aliases (pre-1.0.30 clients)
@app.route("/api/plate_models")
def plate_models():
    return jsonify(_models_state("plate"))


@app.route("/api/plate_models/<mid>/download", methods=["POST"])
def plate_model_download(mid):
    return model_download("plate", mid)


@app.route("/api/plate_models/download_status")
def plate_model_download_status():
    return jsonify(_model_dl)


@app.route("/api/allowlist", methods=["GET", "POST"])
def allowlist():
    path = os.path.join(JOBS_DIR, "allowlist.txt")
    if request.method == "POST":
        body = request.get_json(force=True)
        existing = []
        if os.path.exists(path):
            existing = [l.strip() for l in open(path, encoding="utf-8")
                        if l.strip()]
        for wd in body.get("words", []):
            wd = wd.strip()
            if wd and wd not in existing:
                existing.append(wd)
        removes = {r.strip() for r in body.get("remove", [])}
        if removes:
            existing = [wd for wd in existing if wd not in removes]
        if body.get("clear"):
            existing = []
        with open(path, "w", encoding="utf-8") as f:
            f.write("".join(wd + chr(10) for wd in existing))
        return jsonify({"ok": True, "count": len(existing)})
    words = []
    if os.path.exists(path):
        words = [l.strip() for l in open(path, encoding="utf-8") if l.strip()]
    return jsonify({"words": words, "path": path})


@app.route("/api/jobs/<jid>/render", methods=["POST"])
def job_render(jid):
    job = JOBS.get(jid) or abort(404)
    if job["phase"] == "learning":
        return jsonify({"error": "Finish or cancel learning before rendering."}), 409
    if job["phase"] in ("rendering", "queued_render"):
        return jsonify({"ok": True, "note": "render already in progress"})
    if job["phase"] not in ("review", "done", "error", "cancelled"):
        return jsonify({"error": f"cannot render from phase {job['phase']}"}), 400
    job["phase"] = "queued_render"
    job["cancel"].clear()
    job["error"] = None
    WORK_Q.put((jid, "render"))
    return jsonify({"ok": True})


@app.route("/api/jobs/<jid>/download")
def job_download(jid):
    job = JOBS.get(jid) or abort(404)
    if _load_job_report(job).get("render_required"):
        return jsonify({"error": "Render the updated sections before downloading this video."}), 409
    if (_load_job_report(job).get("learning") or {}).get("needs_render"):
        return jsonify({"error": "Render this learning pass before downloading; the previous video does not contain these changes."}), 409
    if not job["output"] or not os.path.exists(job["output"]):
        abort(404)
    return send_file(job["output"], as_attachment=True,
                     download_name=export_filenames(job)[0])


@app.route("/api/jobs/<jid>/report")
def job_report(jid):
    job = JOBS.get(jid) or abort(404)
    return send_file(os.path.join(job["dir"], "report.json"),
                     as_attachment=True,
                     download_name=export_filenames(job)[1])


# ----------------------------------------------------------------------------
# UI
# ----------------------------------------------------------------------------

findings_web.install(app, sys.modules[__name__])
plate_text_web.install(app, sys.modules[__name__])

# ----------------------------------------------------------------------------
# The app page. PAGE is COMPOSED at import time: zones_ui.ZONES_PAGE is the
# shell (dark Scan Setup editor at the top), and the pieces below fill its
# %%MARKER%% slots — jobs list + job detail/review under the editor, the
# settings view behind the header gear, the footer, and the app JS (jobs/
# review/settings) as a second <script>. All intake happens in the editor.
# ----------------------------------------------------------------------------

FAVICON_URI = "data:image/png;base64,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"

LOGO_URI = "data:image/png;base64,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"

WORDMARK_URI = "data:image/png;base64,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"

APP_CSS = r"""
/* ---- app sections (jobs / review / settings) on the dark shell ---- */
#appzone,#settingsview{max-width:1560px;margin:0 auto;padding:0 16px 8px}
#appzone .card,#settingsview .card{padding:14px 16px}
#appzone .card h2,#settingsview .card h2{font-size:15px;text-transform:none;
 letter-spacing:0;color:#e2e8f0;font-weight:700;margin:0 0 10px}
#appzone h3,#settingsview h3{color:#e2e8f0}
#appzone label,#settingsview label{display:block;margin:6px 0 2px;
 font-size:13px;color:#94a3b8}
#appzone input[type=text],#appzone input[type=number],
#appzone input[type=password],#appzone select,#appzone textarea,
#settingsview input[type=text],#settingsview input[type=number],
#settingsview input[type=password],#settingsview select,
#settingsview textarea{width:100%;padding:7px}
input[type=password]{background:var(--panel);border:1px solid #334155;
 color:var(--txt);border-radius:6px;padding:5px 8px;font-size:12.5px;
 font-family:inherit}
textarea{height:64px}
.grid2{display:grid;grid-template-columns:minmax(0,1fr) minmax(0,1fr);gap:8px}
.grid3{display:grid;grid-template-columns:repeat(auto-fill,minmax(175px,1fr));gap:9px}
.row{display:flex;gap:8px;flex-wrap:wrap;align-items:center}
#appzone button,#settingsview button{background:var(--acc);color:#fff;
 padding:8px 14px;font-size:13px}
#appzone button.sec,#settingsview button.sec{background:#475569}
#appzone button.danger,#settingsview button.danger{background:#dc2626}
button:disabled{opacity:.5}
progress{width:100%;height:12px;accent-color:var(--acc)}
.det{background:var(--panel);border:1px solid #334155;border-radius:8px;
 padding:6px;text-align:center;font-size:12px;color:#cbd5e1}
.det img{max-width:100%;border-radius:5px}

.plate-preview{position:relative;width:100%;min-height:90px;margin:0 auto;touch-action:none}
.plate-preview img{display:block;width:100%;min-height:90px;object-fit:contain}
.plate-outline{position:absolute;inset:0;width:100%;height:100%;pointer-events:none;touch-action:none}
.preview-status{display:block;font-size:11px;color:#94a3b8;margin:5px 0}
.preview-retry[hidden],.quad-retry[hidden],#review [hidden]{display:none!important}
.quad-status{display:block;min-height:2.5em;margin:4px 0;font-size:11px;color:#94a3b8;overflow-wrap:anywhere}
.det.corner-save-error{outline:2px solid #fbbf24;outline-offset:3px}
#plateSaveIssues{border:1px solid #fbbf24;border-radius:6px;padding:8px;overflow-wrap:anywhere}
#plateSaveIssues .row{margin-top:5px}
.plate-outline:focus-visible{outline:2px solid #60a5fa;outline-offset:2px}
.review-overlay-legend{display:flex;gap:8px 14px;flex-wrap:wrap;align-items:center;
 margin:8px 0 10px;padding:8px 10px;border:1px solid #334155;border-radius:8px;
 background:#0f172a;color:#cbd5e1;font-size:11.5px}
.review-overlay-key{display:inline-flex;align-items:center;gap:6px;white-space:nowrap}
.review-overlay-swatch{display:inline-block;width:25px;height:14px;border-radius:3px;
 box-sizing:border-box}
.review-overlay-swatch.proposal{border:2px dashed #f5c400;background:transparent}
.review-overlay-swatch.hidden{border:2px solid #dc2626;background:rgba(220,38,38,.28)}
.review-overlay-swatch.visible{border:2px solid #22c55e;background:rgba(34,197,94,.08)}
.review-overlay-swatch.edit{border:2px solid #38bdf8;background:transparent;position:relative}
.review-overlay-swatch.edit::after{content:"";position:absolute;width:5px;height:5px;border-radius:50%;
 background:#38bdf8;left:8px;top:2px}
.plate-output-badge{position:absolute;left:6px;bottom:6px;z-index:3;max-width:calc(100% - 12px);
 padding:4px 6px;border-radius:6px;background:rgba(2,6,23,.86);border:1px solid #475569;
 color:#e2e8f0;font-size:10.5px;line-height:1.25;text-align:left;pointer-events:none;
 box-sizing:border-box;overflow-wrap:anywhere}
.plate-output-badge strong{display:block;font-size:10.5px;letter-spacing:.03em}
.plate-output-badge.hidden strong{color:#fca5a5}
.plate-output-badge.visible strong{color:#86efac}

.det.selected{outline:2px dashed #60a5fa;outline-offset:2px}
.review-copy{font-size:13px;color:#cbd5e1;line-height:1.5;margin:0 0 10px}
.det-status{font-weight:600;margin:7px 0 5px}
.det-status.blur{color:#fca5a5}
.det-status.keep{color:#6ee7b7}
.det-choices{display:grid;grid-template-columns:.85fr 1.4fr;gap:4px}
#appzone .det-choice{padding:7px 3px;min-height:34px;font-size:12px;
 font-weight:600;border:1px solid #475569;border-radius:6px;
 background:#1e293b;color:#cbd5e1;white-space:nowrap}
#appzone .det-choice::before{content:"";display:inline-block;width:11px;margin-right:2px}
#appzone .det-choice[aria-pressed="true"]::before{content:"✓"}
#appzone .det-choice.blur[aria-pressed="true"]{background:#7f1d1d;border-color:#f87171;color:#fff}
#appzone .det-choice.keep[aria-pressed="true"]{background:#064e3b;border-color:#34d399;color:#fff}
#appzone .det-choice:focus-visible{outline:2px solid #60a5fa;outline-offset:2px}
.marq{position:absolute;border:1.5px dashed #60a5fa;
 background:rgba(96,165,250,.12);z-index:50;pointer-events:none}
.selmenu{position:absolute;z-index:60;background:#0f172a;border-radius:10px;
 border:1px solid #334155;box-shadow:0 8px 28px rgba(0,0,0,.5);
 padding:7px 10px;display:flex;gap:8px;align-items:center;font-size:12.5px;
 color:#cbd5e1}
#appzone .selmenu button{padding:7px 16px;font-weight:700}
#appzone .selmenu .mkeep{background:#16a34a}
#appzone .selmenu .mblur{background:#dc2626}
.badge{display:inline-block;background:#334155;color:#cbd5e1;border-radius:5px;
 padding:1px 6px;font-size:11px;margin-left:4px}
#log{background:#020617;color:#cbd5e1;font:12px/1.4 ui-monospace,Consolas,monospace;
 padding:10px;border-radius:8px;height:180px;overflow:auto;white-space:pre-wrap}
#preview img,#framewrap{max-width:100%;border-radius:8px}
#framewrap{position:relative;display:inline-block}
#framewrap canvas{position:absolute;left:0;top:0;cursor:crosshair}
#appzone a,#settingsview a{color:#93c5fd}
.joblist a{color:#93c5fd;text-decoration:none}
.warn{background:#3b2905;border:1px solid #b45309;color:#fcd34d;
 border-radius:8px;padding:8px 12px;font-size:13px}
.chk{display:flex;gap:12px;flex-wrap:wrap}
.chk label{display:flex;gap:4px;align-items:center;margin:0}
.plist{display:flex;flex-wrap:wrap;gap:4px;margin-top:5px}
.pw{background:#052e16;color:#4ade80;border:1px solid #14532d;border-radius:7px;
 padding:2px 7px;font-size:12px;font-weight:600;display:flex;gap:6px;
 align-items:center}
.pw span{cursor:pointer;color:#4ade80;font-weight:700}
.pw span:hover{color:#86efac}
.pnote{font-size:11.5px;color:#4ade80;margin-top:4px}
.qm{display:inline-flex;align-items:center;justify-content:center;
 width:15px;height:15px;border-radius:50%;background:#475569;color:#cbd5e1;
 font-size:10.5px;font-weight:700;cursor:help;margin-left:5px;
 position:relative;vertical-align:middle;user-select:none}
.qm:hover::after,.qm.open::after{content:attr(data-tip);position:absolute;
 left:50%;transform:translateX(-50%);bottom:135%;background:#0f172a;
 border:1px solid #334155;color:#e5e7eb;padding:9px 11px;border-radius:9px;
 width:250px;font-size:12px;font-weight:400;line-height:1.4;z-index:90;
 box-shadow:0 8px 24px rgba(0,0,0,.6);white-space:normal;text-align:left}
footer{text-align:center;color:#64748b;font-size:12px;padding:18px 12px 26px}
.hdrtag{display:none}
@media(min-width:900px){.hdrtag{display:inline}}
@media(max-width:640px){.grid2{grid-template-columns:minmax(0,1fr)}}
"""

JOBS_HTML = """<div class="card"><h2>Jobs</h2><div class="joblist" id="jobs">loading…</div><small id="jobsLoadStatus" role="status"></small></div>
<div id="detail"></div>"""

SETTINGS_HTML = """<div id="settingsview" style="display:none">
<div class="card"><h2>App settings <a href="#" style="float:right;font-size:14px;font-weight:400" onclick="location.hash=&quot;&quot;;return false">&#8592; back to jobs</a></h2>
<div style="font-size:12px;color:#94a3b8">Server-level configuration — these apply to every job.</div>
</div>
<div class="card"><h2>Learned safe words</h2>
<div style="font-size:12px;color:#94a3b8;margin-bottom:6px">Words marked safe
during reviews load automatically and are applied to every scan, in addition
to any per-job allow names set in the Scan Setup editor.</div>
<div id="persistlist" class="plist"></div>
<div id="persistnote" class="pnote" style="display:none"></div>
<button type="button" class="sec" id="clearpersist" style="display:none;margin-top:5px;padding:4px 10px;font-size:12px" onclick="clearPersist()">Clear all learned words</button>
</div>
<div class="card" id="qualitypanel">
<h2>Detection quality <span class="qm" data-tip="One switch for the face / plate / person model set. Higher tiers use larger models: they catch small, distant and partly hidden subjects the fast models can miss, at the cost of longer scans. Applying a tier downloads any missing model (SHA-256 verified) and selects it; picking individual models below still works and shows as Custom. Scan-time multiples are approximate - GPU builds feel the increase far less than CPU.">?</span></h2>
<div id="qtiers" style="font-size:13px">loading&#8230;</div>
</div>
<div class="card" id="modelpanel">
<h2>Detection models <span class="qm" data-tip="Face detection works out of the box (built-in YuNet); optional higher-accuracy models can be downloaded and selected here. Plate detection needs a model file (not bundled). Every download is SHA-256 verified against a pinned hash before use, and each entry shows its license — some are non-commercial.">?</span></h2>
 <div id="msec_face"></div>
 <div id="msec_plate"></div>
 <div id="msec_person"></div>
</div>
<div class="card" id="learnedModelsPanel">
<h2>Learned plate models</h2>
<p class="review-copy">Save a trained model from a video review, then choose it for similar footage in Scan Setup. Import and export models to use on another PC.</p>
<div class="row" style="gap:8px;flex-wrap:wrap">
 <label for="learnedModelImport">Import model</label>
 <input type="file" id="learnedModelImport" accept=".openscrub-model,.zip" style="max-width:100%" onchange="importLearnedModel(this)">
 <button type="button" class="sec" onclick="refreshLearnedModels()">Refresh</button>
</div>
<p id="learnedModelStatus" class="review-copy" role="status" aria-live="polite"></p>
<div id="learnedModelLibrary">Loading models...</div>
<p class="review-copy">Model packages contain the learned model and its settings. Video files, training images and review decisions stay with their original jobs.</p>
</div>
<div class="card"><h2>Optional detection engines</h2>
<div id="extras" style="font-size:13px">loading…</div>
</div>
<div class="card"><h2>Encryption at rest</h2>
<div id="vstat" style="font-size:13px;color:#94a3b8;margin-bottom:8px">loading…</div>
<div id="vsetup" style="display:none">
 <div style="background:#3b2905;border:1px solid #b45309;border-radius:8px;padding:10px 12px;font-size:13px;margin-bottom:8px">
  <b>&#9888; No password reset exists.</b> If you lose this password, every
  encrypted job — uploads, audit reports, rendered output — is
  <b>permanently unrecoverable</b>. Write it down and store it safely.
 </div>
 <div class="row" style="gap:8px;flex-wrap:wrap;font-size:13px">
  <input type="password" id="vpw1" placeholder="password (8+ chars)">
  <input type="password" id="vpw2" placeholder="repeat password">
  <button onclick="vaultSetup()">Enable encryption</button>
 </div>
 <div style="font-size:12px;color:#9ca3af;margin-top:6px">Job files are
 encrypted (AES-256) whenever you lock or shut the server down, and
 decrypted while unlocked so scanning and review work normally. Pair with
 OS disk encryption (e.g. BitLocker) for full coverage.</div>
</div>
<div id="vunlock" style="display:none" class="row">
 <input type="password" id="vpw" placeholder="vault password">
 <button onclick="vaultUnlock()">Unlock</button>
</div>
<div id="vlock" style="display:none">
 <div class="row"><button onclick="vaultDoLock()">Lock now (encrypt all job files)</button></div>
 <div class="row" style="font-size:13px;margin-top:8px;gap:8px">
  <label style="margin:0"><input type="checkbox" id="valk" onchange="vaultAutolockSave()"> auto-lock after</label>
  <input type="number" id="valkmin" min="1" max="1440" value="30" style="width:70px" onchange="vaultAutolockSave()"> idle minutes (no activity, no jobs)
 </div>
</div>
</div>
<div class="card"><h2>HTTPS certificate</h2>
<div id="certinfo" style="font-size:13px;color:#94a3b8;margin-bottom:8px">loading…</div>
<div class="row" style="gap:8px;flex-wrap:wrap;font-size:13px">
 <label>Certificate (PEM): <input type="file" id="certfile" accept=".pem,.crt,.cer"></label>
 <label>Private key (PEM): <input type="file" id="keyfile" accept=".pem,.key"></label>
 <button onclick="uploadCerts()">Install</button>
 <button onclick="removeCerts()">Remove custom cert</button>
</div>
<div style="font-size:12px;color:#9ca3af;margin-top:6px">Installing or removing a
certificate takes effect after a server restart.</div>
</div>
</div>"""

FOOT_HTML = """<footer style="text-align:center;color:#9ca3af;font-size:12px;padding:18px 12px 26px">
OpenScrub v%%VERSION%% <span id="upd"></span>· <a href="license" style="color:#94a3b8">Apache-2.0 license</a>
· best-effort redaction — always review output before sharing PII</footer>"""

APP_JS = """function renderAudioSugg(){
 const el=document.getElementById("beASugg");
 if(!el)return;
 const sg=BE.audioSugg||[];
 if(!sg.length){el.style.display="none";el.innerHTML="";return;}
 el.style.display="block";
 let h='<div style="font-size:12px;color:#f59e0b;margin-bottom:3px">'
  +'&#127908; Spoken PII heard in the audio (local transcription) — '
  +'review each, then Add to mute it:</div>';
 sg.forEach((s,i)=>{
  const used=(BE.audio||[]).some(a=>Math.abs(a.t0-s.t0)<0.05&&Math.abs(a.t1-s.t1)<0.05);
  h+='<div style="font-size:12px;padding:2px 0">'
   +(used?'<span style="color:#4ade80">&#10003; added</span> '
     :'<button class="tog" style="font-size:11px;padding:1px 7px" '
      +'onclick="applyAudioSugg('+i+')">Add</button> ')
   +s.t0.toFixed(1)+'&ndash;'+s.t1.toFixed(1)+'s '
   +'<b>'+(CATDN[s.category]||s.category)+'</b> '
   +'<span style="color:#94a3b8">&ldquo;'
   +String(s.text||"").replace(/[<>&]/g,"")+'&rdquo;</span></div>';
 });
 h+='<div style="margin-top:3px"><button class="tog" style="font-size:11px" '
  +'onclick="applyAudioSugg(-1)">Add all</button></div>';
 el.innerHTML=h;
}
function applyAudioSugg(i){
 const sg=BE.audioSugg||[];
 const list=(i<0)?sg:[sg[i]].filter(Boolean);
 for(const s of list){
  if(!(BE.audio||[]).some(a=>Math.abs(a.t0-s.t0)<0.05&&Math.abs(a.t1-s.t1)<0.05))
   BE.audio.push({t0:s.t0,t1:s.t1,mode:"mute"});
 }
 renderAudioSugg();renderTranscript();beTLDraw();
}
// Full transcript with matched spans highlighted — the fail-closed check
// for spoken PII: ASR patterns can miss (a real half-muted address shipped
// once), but a human reading the transcript catches it in seconds. Click a
// start word then an end word to mute that range directly.
function renderTranscript(){
 const el=document.getElementById("beATx");
 if(!el)return;
 const tx=BE.audioTx||[];
 if(!tx.length){el.style.display="none";el.innerHTML="";return;}
 el.style.display="block";
 const wasOpen=el.querySelector("details")?el.querySelector("details").open:true;
 const esc=s=>String(s).replace(/[<>&]/g,"");
 const muted=w=>(BE.audio||[]).some(a=>w[0]<a.t1&&w[1]>a.t0);
 const sugg=w=>(BE.audioSugg||[]).some(a=>w[0]<a.t1&&w[1]>a.t0);
 let h='<details'+(wasOpen?' open':'')+'><summary style="font-size:12px;color:#94a3b8;cursor:pointer">&#128221; Transcript ('+tx.length+' words) — verify nothing sensitive slipped through</summary>'
  +'<div style="max-height:150px;overflow-y:auto;line-height:2.1;padding:6px 2px;font-size:12.5px;color:#cbd5e1">';
 tx.forEach((wd,i)=>{
  const m=muted(wd),g=sugg(wd),a=i===BE.txAnchor;
  let st='cursor:pointer;border-radius:4px;padding:1px 3px;';
  if(a)st+='outline:2px solid #f59e0b;';
  if(m)st+='background:#7f1d1d;color:#fecaca;text-decoration:line-through;';
  else if(g)st+='background:#78350f;color:#fde68a;';
  h+='<span style="'+st+'" title="'+wd[0].toFixed(2)+'&ndash;'+wd[1].toFixed(2)+'s'+(m?' (will be muted)':'')+'" onclick="txWordClick('+i+')">'+esc(wd[2])+'</span>';
 });
 h+='</div><div style="font-size:11px;color:#64748b">'
  +(BE.txAnchor>=0?'<b style="color:#f59e0b">now click the last word of the range to mute it</b>'
    :'<span style="background:#7f1d1d;border-radius:3px;padding:0 4px">red</span> will be muted &nbsp;'
     +'<span style="background:#78350f;border-radius:3px;padding:0 4px">amber</span> detected PII (not yet added) &nbsp;'
     +'— click a start word, then an end word, to mute a missed range (&plusmn;0.5s pad)')
  +'</div></details>';
 el.innerHTML=h;
}
function txWordClick(i){
 const tx=BE.audioTx||[];if(!tx[i])return;
 if(BE.txAnchor<0){BE.txAnchor=i;renderTranscript();return;}
 const a=Math.min(BE.txAnchor,i),b=Math.max(BE.txAnchor,i);
 BE.txAnchor=-1;
 BE.audio.push({t0:Math.max(0,+(tx[a][0]-0.5).toFixed(2)),
                t1:+(tx[b][1]+0.5).toFixed(2),
                mode:(document.getElementById("beAMode")||{}).value||"mute"});
 renderTranscript();renderAudioSugg();beTLDraw();
}
const CATDN={mrn:"regex",person:"person (full body)",manual:"tracked object",qrcode:"QR / barcode",screen:"screen (tv/laptop/phone)",anytext:"all text",bank:"bank number",crypto:"crypto address",passport:"passport / MRZ"};   // display names — ids are a compat surface
async function refreshModelPanel(){
 // always visible: model choice lives on the settings page now, so users
 // can set up face/plate models before ticking the categories on a job
 document.getElementById("modelpanel").style.display="block";
 for(const kind of ["face","plate","person"]){
  const sec=document.getElementById("msec_"+kind);
  sec.style.display="block";
  try{
   const d=await(await fetch("/api/models/"+kind)).json();
   const dflt=kind==="face"?"Built-in YuNet (no download needed)"
                           :"Automatic — first installed model";
   const row=(val,checked,disabled,inner,right)=>`
    <div style="display:flex;align-items:center;gap:8px;padding:6px 0;border-top:1px solid #334155">
     <input type="radio" name="msel_${kind}" ${checked?"checked":""} ${disabled?"disabled":""}
      onchange="selModel('${kind}','${val}')" style="margin:0" title="${disabled?'download the model first':'use this model'}">
     <div style="flex:1;min-width:0">${inner}</div>${right||""}
    </div>`;
   let h=`<div style="font-weight:600;font-size:13.5px;margin:8px 0 2px">${kind==="face"?"Face":kind==="person"?"Person (full-body blur)":"License-plate"} model</div>
    <div style="font-size:12px;margin-bottom:4px;color:${d.active?'#4ade80':'#fbbf24'}">${d.status}</div>`;
   h+=row("",!d.selected,false,
     `<div style="font-size:12.5px;font-weight:600">${dflt}</div>`);
   for(const m of d.models){
    h+=row(m.id,d.selected===m.id,!m.installed,
     `<div style="font-size:12.5px;font-weight:600">${m.label} ${m.recommended?'<span style="color:#4ade80;font-size:11px">★ recommended</span>':''}</div>
      <div style="font-size:11px;color:#94a3b8">${m.notes||""}</div>`,
     `<a href="${m.source_url}" target="_blank" style="font-size:11px;background:#1e3a8a;color:#bfdbfe;border-radius:5px;padding:2px 7px;text-decoration:none" title="${m.attribution||''}">${m.license}</a>
      ${m.installed?'<span style="font-size:11px;color:#4ade80;font-weight:700">installed</span>'
       :(m.verified?`<button onclick="dlModel('${kind}','${m.id}',this)" title="${m.pinned?'SHA-256 verified against pinned hash':'first download: hash will be computed and pinned'}" style="font-size:11.5px;padding:3px 10px">Download</button>`
       :'<span style="font-size:11px;color:#9ca3af" title="registry entry has no download URL">manual install</span>')}`);
   }
   sec.innerHTML=h;
  }catch(e){sec.textContent="model registry unavailable";}
 }
}
async function selModel(kind,id){
 await fetch(`/api/models/${kind}/select`,{method:"POST",
  headers:{"Content-Type":"application/json"},body:JSON.stringify({id})});
 refreshModelPanel();renderTiers();
}
async function dlModel(kind,id,btn){
 btn.disabled=true;btn.textContent="0%";
 const r=await fetch(`/api/models/${kind}/${id}/download`,{method:"POST"});
 if(!r.ok){const d=await r.json();btn.textContent="error";btn.title=d.error||"";return;}
 const t=setInterval(async()=>{
  const s=await(await fetch("/api/models/download_status")).json();
  if(s.state==="downloading"){btn.textContent=(s.pct||0)+"%";}
  else{clearInterval(t);
   if(s.state==="done"){refreshModelPanel();}
   else{btn.disabled=false;btn.textContent="retry";btn.title=s.error||"download failed";}}
 },500);
}

// Detection-quality tiers: one click per tier; scan-time multiples and
// accuracy staging shown beside each. Multiples are honest approximations
// (measured on the person model, the dominant per-frame cost).
const QTIERS=[
 {id:"fast",name:"Fast",mult:"~1× scan time (baseline)",stage:"Good",
  desc:"Built-in YuNet face + nano person model. Lightest and quickest; can miss small, distant or partly hidden subjects."},
 {id:"balanced",name:"Balanced",mult:"~1.5–2× scan time",stage:"Better",
  desc:"CenterFace face + small person model — catches most small or partly hidden subjects the Fast tier misses."},
 {id:"accurate",name:"Accurate",mult:"~2.5–4× scan time",stage:"Best",
  desc:"CenterFace face + medium person model + the most-accurate plate model. Highest recall on crowds, occlusion and distant subjects; best experienced on a GPU."}];
let QAPPLY=0;
async function renderTiers(){
 const el=document.getElementById("qtiers"); if(!el)return;
 try{
  const d=await(await fetch("/api/quality_tier")).json();
  const ap=d.applying||{};
  let h="";
  for(const t of QTIERS){
   const cur=d.tier===t.id, busy=ap.state==="applying"&&ap.tier===t.id;
   const dl=((d.needs&&d.needs[t.id])||[]).length;
   h+=`<div style="display:flex;align-items:center;gap:8px;padding:7px 0;border-top:1px solid #334155">
    <input type="radio" name="qtier" ${cur?"checked":""} ${ap.state==="applying"?"disabled":""} onchange="applyTier('${t.id}')" style="margin:0">
    <div style="flex:1;min-width:0">
     <div style="font-size:12.5px;font-weight:600">${t.name}
      <span style="color:#94a3b8;font-weight:400">— ${t.mult}</span>
      <span style="font-size:11px;border-radius:5px;padding:1px 7px;margin-left:4px;background:${t.stage==="Good"?"#374151":t.stage==="Better"?"#1e3a8a":"#14532d"};color:${t.stage==="Good"?"#d1d5db":t.stage==="Better"?"#bfdbfe":"#86efac"}">${t.stage} accuracy</span></div>
     <div style="font-size:11px;color:#94a3b8">${t.desc}</div>
     ${busy?`<div style="font-size:11px;color:#fbbf24">${ap.step||"applying…"}</div>`:""}
    </div>
    ${!cur&&dl?`<span style="font-size:11px;color:#9ca3af;white-space:nowrap">${dl} download${dl>1?"s":""}</span>`:""}
   </div>`;
  }
  if(!d.tier&&ap.state!=="applying")h+=`<div style="font-size:11px;color:#fbbf24;padding-top:5px">Current selection: Custom (models picked individually below)</div>`;
  if(ap.state==="error")h+=`<div style="font-size:11px;color:#f87171;padding-top:5px">${ap.error}</div>`;
  h+=`<div style="font-size:11px;color:#64748b;padding-top:6px">Higher tiers download larger models on demand (person/plate models are AGPL/MIT licensed — shown per model below). For the strongest face detection, SCRFD (non-commercial license) can be selected manually in Detection models.</div>`;
  el.innerHTML=h;
  if(ap.state==="applying"){QAPPLY=1;setTimeout(renderTiers,900);}
  else if(QAPPLY){QAPPLY=0;refreshModelPanel();}
 }catch(e){el.textContent="quality tiers unavailable";}
}
async function applyTier(id){
 const d=await(await fetch("/api/quality_tier")).json();
 const need=(d.needs&&d.needs[id])||[];
 if(need.length&&!confirm(`Switching to this tier downloads ${need.length} model file(s) first (SHA-256 verified). Continue?`)){renderTiers();return;}
 const r=await fetch("/api/quality_tier",{method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify({tier:id})});
 if(!r.ok){let e={};try{e=await r.json();}catch(_){/**/}alert(e.error||"could not apply tier");}
 renderTiers();
}
refreshModelPanel();renderTiers();
let CUR=null, EN={}, MAN=[], DUR=0, POLL=null, PHIST=[], PHPH="", LOGN=0, SHELLPH=null, JOBSJSON="";
let JOBVIEW=0,JOBSFLIGHT=null,JOBSRETRYAT=0,JOBSFAILURES=0;
let REFRESHFLIGHT=null,REFRESHCTRL=null,REFRESHFAILURES=0;
let EXPORT_NAMES={video:null,report:null};
// Browsers without a native file picker still get the direct download links.
const CAN_SAVE_AS=!!(window.isSecureContext&&window.showSaveFilePicker);

async function loadJobs(){
 if(JOBSFLIGHT)return JOBSFLIGHT.promise;
 if(Date.now()<JOBSRETRYAT||(document.hidden&&JOBSJSON))return;
 const flight={controller:new AbortController(),promise:null};JOBSFLIGHT=flight;
 flight.promise=(async()=>{try{
 const {data:js}=await reviewRequest("api/jobs",{signal:flight.controller.signal});
 if(JOBSFLIGHT!==flight)return;
 JOBSFAILURES=0;JOBSRETRYAT=0;
 const note=document.getElementById("jobsLoadStatus");if(note)note.textContent="";
 const s=JSON.stringify(js);
 if(s===JOBSJSON)return;
 JOBSJSON=s;
 jobs.innerHTML=js.length?js.map(j=>
  `<div class="row" style="justify-content:space-between;padding:4px 0">
   <a href="#" onclick="openJob('${j.id}');return false">${sectionEscape(j.name)}</a>
   <span style="display:flex;gap:10px;align-items:center"><span class="badge">${j.phase}</span>
   ${((j.phase=="error"||j.phase=="cancelled")&&j.kind!=="model_training")?`<a href="#" title="${j.section?.role==="export"?"Retry section export":"Retry the scan — reuses the file already on the server, nothing is re-uploaded"}" aria-label="${j.section?.role==="export"?"Retry section export":"Retry scan"}" style="text-decoration:none;font-size:15px" onclick="retryJob('${j.id}',${j.section?.role==="export"});return false">&#8635;</a>`:""}
   <a href="#" title="Delete this job and all of its files" style="text-decoration:none;font-size:15px" onclick="delJob('${j.id}');return false">&#128465;&#65039;</a></span></div>`).join(""):"none yet";
 }catch(error){
  if(JOBSFLIGHT!==flight||flight.controller.signal.aborted)return;
  JOBSFAILURES++;JOBSRETRYAT=Date.now()+Math.min(30000,2000*2**Math.min(4,JOBSFAILURES-1));
  const note=document.getElementById("jobsLoadStatus");
  if(note)note.textContent=error.status===423?"Vault locked — unlock in Settings.":"Connection interrupted; retrying with backoff.";
 }finally{if(JOBSFLIGHT===flight)JOBSFLIGHT=null;}})();
 return flight.promise;
}

async function retryJob(id,sectionExport=false){
 const opened=CUR,view=JOBVIEW;
 try{
  await reviewRequest("api/jobs/"+encodeURIComponent(id)+(sectionExport?"/render":"/retry"),
   {method:"POST",headers:{"Content-Type":"application/json"},body:"{}"});
  JOBSJSON="";loadJobs();
  if(CUR===opened&&JOBVIEW===view)await openJob(id);
 }catch(error){alert(error.message||"could not retry the job");}
}
async function delJob(id){
 if(CUR===id&&!await flushPlateSaves())return;
 if(!confirm("Delete this job and ALL of its files — upload, report, and rendered output?\\n\\nThis cannot be undone."))return;
 const r=await fetch("api/jobs/"+id,{method:"DELETE"});
 if(!r.ok){
  let m="could not delete the job";
  try{const e=await r.json();m=e.error||e.description||m;}catch(_){}
  alert(m);return;
 }
 if(CUR===id){CUR=null;stopJobPolling();detail.innerHTML="";}
 JOBSJSON="";loadJobs();
}
async function openJob(id){
 if(CUR&&document.getElementById("review")&&reviewChoicesPending()){
  if(!await saveAndRender(true))return;
 }
 if(!await flushPlateSaves())return;
 if(!closePlateQuad())return;
 clearReviewPreviews();JOBVIEW++;REFRESHFAILURES=0;
 stopJobPolling();
 CUR=id; EN={}; MAN=[]; PHIST=[]; PHPH=""; LOGN=0; SHELLPH=null;
 REVIEW_VERSION=0;REVIEW_SAVED=0;plateUnloadGuard();
 detail.innerHTML="";
 refresh();
}

function stopJobPolling(){
 if(POLL)clearTimeout(POLL);POLL=null;
 const previous=REFRESHCTRL;REFRESHCTRL=null;REFRESHFLIGHT=null;
 if(previous)previous.abort();
}

function shellHtml(j){
 return `<div class="card" id="jobcard"><h2>${sectionEscape(j.name)}
  <span class="badge" id="ph"></span><small id="eta"></small></h2>
 <progress id="prog" value="0" max="1"></progress>
 <div id="jobWorkStatus" class="review-copy" role="status" style="margin:8px 0"></div>
 <progress id="workStageBar" value="0" max="1" hidden aria-label="Current stage progress"></progress>
 <div class="row" id="actions" style="margin-top:8px"></div>
 <div id="sectionsPanel" style="margin-top:14px" hidden></div>
 <p id="selectedLearnedModel" class="review-copy" role="status"></p>
 <div style="margin-top:8px;text-align:center"><img id="pimg"
   style="max-width:100%;border-radius:8px;display:none;margin:0 auto"></div>
 <div id="pcap" style="font-size:12px;color:#94a3b8"></div>
 <div id="log" style="margin-top:8px"></div>
 <div class="warn" id="warnbox" style="display:none;margin-top:8px"></div>
 </div>`;
}

// Open the picker before any network await: it needs a direct user gesture.
// Stream the response to disk instead of buffering multi-GB videos in RAM.
async function saveExportAs(kind, btn){
 const id=CUR, name=EXPORT_NAMES[kind];
 if(!id||!name)return;
 let handle;
 try{
  handle=await window.showSaveFilePicker({suggestedName:name});
 }catch(e){
  if(e.name!=="AbortError")alert("Could not open Save As: "+(e.message||e));
  return; // cancel must never start an automatic download
 }
 const previous=btn.textContent;
 btn.disabled=true;btn.textContent="Saving…";
 try{
  const path=kind==="video"?"download":"report";
  const response=await fetch(`api/jobs/${encodeURIComponent(id)}/${path}`);
  if(!response.ok)throw new Error(response.status===423
   ?"encryption vault is locked":`server returned HTTP ${response.status}`);
  if(!response.body)throw new Error("browser did not provide a file stream");
  await response.body.pipeTo(await handle.createWritable());
  btn.textContent="Saved ✓";
 }catch(e){
  btn.textContent=previous;
  alert("Could not save file: "+(e.message||e));
 }finally{btn.disabled=false;}
}

async function refresh(){
 if(REFRESHFLIGHT)return REFRESHFLIGHT;
 if(POLL)clearTimeout(POLL);POLL=null;
 // Return before assigning the flight. An async body with no await finishes
 // its finally synchronously, then the outer assignment stores its completed
 // promise forever (the hidden-tab freeze).
 const id=CUR,view=JOBVIEW;if(!id||document.hidden)return;
 const ctl=REFRESHCTRL=new AbortController();
 REFRESHFLIGHT=(async()=>{try{
  await refreshJob(id,view,ctl.signal);
  if(REFRESHCTRL===ctl)REFRESHFAILURES=0;
 }catch(error){
  if(REFRESHCTRL===ctl&&!ctl.signal.aborted){
   REFRESHFAILURES++;
   const note=document.getElementById("jobsLoadStatus");
   if(note)note.textContent="Connection interrupted; retrying with backoff.";
  }
 }finally{
  // Navigation or wake-up may already own a newer request. Late completion
  // must not clear its slot, change its backoff, or schedule a duplicate poll.
  if(REFRESHCTRL===ctl){
   REFRESHFLIGHT=null;REFRESHCTRL=null;
   if(CUR&&!document.hidden){
    const idle=["review","paused","done","error","cancelled"].includes(SHELLPH);
    const delay=CUR!==id||JOBVIEW!==view?0:REFRESHFAILURES
     ?Math.min(30000,2000*2**Math.min(4,REFRESHFAILURES-1)):(idle?5000:900);
    POLL=setTimeout(refresh,delay);
   }
  }
 }})();return REFRESHFLIGHT;
}

async function refreshJob(id,view,signal){
 const {data:j}=await reviewRequest("api/jobs/"+id,{signal});
 if(signal.aborted||CUR!==id||JOBVIEW!==view)return;
 const modelNote=document.getElementById("selectedLearnedModel");
 if(modelNote&&CUR===id&&JOBVIEW===view)modelNote.textContent=j.refinement
  ?"Learned plate model: "+j.refinement.name:"";

 EXPORT_NAMES={video:j.download_name,report:j.report_name};
 if(SHELLPH===null){
  detail.insertAdjacentHTML("afterbegin",shellHtml(j));SHELLPH="";
  const im=document.getElementById("pimg");
  im.onload=()=>{im.style.display="block";};   // show only once a real frame arrives
  im.onerror=()=>{im.style.display="none";};   // 404 before first preview: stay hidden
 }

 // progress + ETA (updated in place — nothing is rebuilt).
 // The server sends a smoothed per-stage estimate (j.eta, seconds) built
 // from recent throughput on long stages — prefer it. The old
 // client-side extrapolation from bar movement stays only as a fallback
 // (rehydrated jobs mid-phase), with its history reset on phase change so
 // it never extrapolates a scan-speed rate across the render phase.
 if(PHPH!==j.phase){PHIST=[];PHPH=j.phase;}
 PHIST.push([Date.now(),j.progress]); if(PHIST.length>40)PHIST.shift();
 let sec=null;
 if(typeof j.eta==="number"&&j.progress<1)sec=j.eta;
 else if(j.progress>0&&j.progress<1&&PHIST.length>3){
  const[t0,p0]=PHIST[0],[t1,p1]=PHIST[PHIST.length-1];
  if(p1>p0)sec=(1-p1)*(t1-t0)/(p1-p0)/1000;}
 const eta=sec===null?"":` ~${sec>90?Math.round(sec/60)+" min":Math.round(sec)+" s"} left`;
 document.getElementById("ph").textContent=j.phase;
 document.getElementById("eta").textContent=eta;
 document.getElementById("prog").value=j.progress;
 renderWorkProgress(j);

 // incremental log append with stick-to-bottom (respects manual scroll-up)
 const lg=document.getElementById("log");
 const stick=lg.scrollTop+lg.clientHeight>=lg.scrollHeight-40;
 const from=LOGN;
 const {data:nl}=await reviewRequest(`api/jobs/${id}/log?from=${from}&limit=400`,{signal});
 if(signal.aborted||CUR!==id||JOBVIEW!==view)return;
 const NL=String.fromCharCode(10),reset=nl.len<from;
 const start=Number.isInteger(nl.from)?nl.from:from;
 const existing=reset||start>from?[]:lg.textContent?lg.textContent.split(NL):[];
 const added=nl.lines.slice(reset?0:Math.max(0,from-start));
 const text=existing.concat(added).slice(-400).join(NL).slice(-200000);
 if(lg.textContent!==text){lg.textContent=text;if(stick)lg.scrollTop=lg.scrollHeight;}
 LOGN=reset?nl.len:Math.max(from,nl.len);

 // live preview: swap src in place (browser keeps old frame until new loads)
 const img=document.getElementById("pimg");
 const previewActive=j.phase==="scanning"||(j.phase==="learning"&&["rescanning","postprocessing"].includes(j.learning?.stage));
 if(previewActive&&j.preview){
  if(img.dataset.revision!==j.preview.revision){
   img.dataset.revision=j.preview.revision;
   img.src=`api/jobs/${id}/preview.jpg?revision=${encodeURIComponent(j.preview.revision)}`;
  }
  const age=Math.max(0,Math.floor((j.server_time||Date.now()/1000)-j.preview.updated_at));
  document.getElementById("pcap").textContent=`Scan detections at ${sectionTime(j.preview.source_time)} · updated ${age}s ago`;
 }else{img.style.display="none";img.removeAttribute("src");delete img.dataset.revision;document.getElementById("pcap").textContent="";}

 const wb=document.getElementById("warnbox");
 if(j.error){wb.style.display="block";wb.textContent=j.error;}
 else wb.style.display="none";

 const learningProgress=document.getElementById("learningProgress");
 if(learningProgress&&j.learning)learningProgress.textContent=j.learning.message||j.learning.stage;

 // action buttons rebuilt ONLY when the phase changes
 if(SHELLPH!==j.phase){
  let a="";
  if(j.phase=="scanning")
   a=`<button class="sec" id="stopReviewBtn" onclick="stopReview()">&#9632; Stop &amp; Review</button>
    <button class="danger" onclick="cancelJob()">Cancel (discard scan)</button>
    <span style="font-size:12px;color:#94a3b8">Stop saves a reviewable checkpoint; Cancel discards this run.</span>`;
  if(j.phase=="learning")
   a=`<button class="danger" onclick="cancelJob()">Cancel learning pass</button>
    <div id="learningProgress" role="status">Training and full rescan queued</div>
    <div class="warn">The previous reviewed result is retained until this pass succeeds. New output still requires review and rendering.</div>`;
  if(j.kind==="model_training"){
   if(j.phase==="learning")a=`<button class="danger" onclick="cancelJob()">Cancel model training</button><div id="learningProgress" role="status">Training selected confirmed examples</div>`;
   else a=`<a href="#findings">Confirmed findings &amp; training</a> · <a href="#settings">Manage saved models</a>`;
  }
  if(j.phase==="learning"&&j.learning?.stage?.startsWith("plate_text"))
   a=`<button class="danger" onclick="cancelJob()">Cancel plate text search</button><div id="learningProgress" role="status">Searching sampled frames for known plate text</div><p class="review-copy">Possible matches accumulate for review. The search does not stop for individual decisions.</p>`;
  if(j.phase=="rendering")
   a=`<button class="danger" onclick="cancelJob()">Cancel render</button>`;
  if((j.phase=="error"||j.phase=="cancelled")&&j.kind!=="model_training"){
   a=j.section?.role==="export"
    ?`<button onclick="retryJob('${id}',true)">Retry section export</button>
      <div class="review-copy">Renders the saved approved section again.</div>`
    :`<button onclick="retryJob('${id}')">Retry scan (no re-upload)</button>
    <div style="width:100%;font-size:12px;color:#9ca3af">The uploaded file
    is still on the server — Retry re-runs the scan without uploading it
    again. Delete the job (&#128465;&#65039; in the list) to free its disk
    space.</div>`;
  }
  if(j.phase=="paused"){
   const f=j.checkpoint_frame||0,t=j.checkpoint_total||1;
   a=`<button onclick="resumeJob()">&#9654; Save edits &amp; resume</button>
    <button class="sec" onclick="saveAndRender(true)">Save review edits only</button>
    <div class="warn" style="width:100%">INCOMPLETE: ${(f/t*100).toFixed(1)}%
    scanned (${f}/${t} frames). Do not publish as redacted video.
    Existing review decisions and plate corners remain saved on resume.</div>`;
   if(!await loadReview(signal,j.phase)||signal.aborted||CUR!==id||JOBVIEW!==view)return;
  }
  if(j.phase=="review"){
   // no interstitial button: review is the ONLY next step after a scan,
   // so open it directly — both on a live scan finishing and on
   // selecting a job that is already waiting in review
   a="";
   if(!await loadReview(signal,j.phase)||signal.aborted||CUR!==id||JOBVIEW!==view)return;
  }
  if(j.phase=="done"&&j.has_output){
   const video=CAN_SAVE_AS
    ?`<button onclick="saveExportAs('video',this)">Save redacted video as…</button>`
    :`<a href="api/jobs/${CUR}/download"><button>Download redacted video</button></a>`;
   const report=CAN_SAVE_AS
    ?`<button class="sec" onclick="saveExportAs('report',this)">Save audit report as…</button>`
    :`<a href="api/jobs/${CUR}/report"><button class="sec">Download audit report</button></a>`;
   const downloadHint=CAN_SAVE_AS
    ?`<div style="width:100%;font-size:12px;color:#94a3b8">
       Download directly to your browser folder instead:
       <a href="api/jobs/${CUR}/download">video</a> ·
       <a href="api/jobs/${CUR}/report">audit report</a></div>`
    :`<div style="width:100%;font-size:12px;color:#94a3b8">
       To choose a location, enable "Ask where to save each file"
       in your browser's download settings.</div>`;
   a=`${video}${report}${downloadHint}
    <button class="sec" onclick="loadReview()">Re-open review</button>
    ${j.section?.role==="export"?"":`<button class="sec" onclick="loadCompare()">Compare before/after</button>`}
    <button class="sec" onclick="loadBoxEdit()">Preview &amp; edit blur boxes</button>
    <div class="warn" style="width:100%">Reminder: scrub the result before
    sharing. This tool is best-effort, not a compliance guarantee.</div>
    <div id="compare" style="width:100%"></div>
    <div id="beslot_done" style="width:100%"></div>`;
  }
  SHELLPH=j.phase;
  document.getElementById("actions").innerHTML=a;
  if(!previewActive)img.style.display="none";
 }
 if(j.kind!=="model_training")loadSectionsPanel(j,id,view);
 refreshPendingFindings(j,id,view);
 showTrainingResult(j);
 loadJobs(); // the list must not hold up the selected job's next progress poll
}

function sectionTime(seconds){
 const n=Math.max(0,Number(seconds)||0),m=Math.floor(n/60),s=n-m*60;
 return `${m}:${s.toFixed(1).padStart(4,"0")}`;
}
function renderWorkProgress(j){
 const box=document.getElementById("jobWorkStatus"),bar=document.getElementById("workStageBar");
 if(!box||!bar)return;
 const active=["scanning","learning","rendering"].includes(j.phase);
 const p=j.phase==="learning"?j.learning:j.activity;
 document.getElementById("prog").hidden=j.phase==="learning";
 if(!active||!p){box.textContent="";bar.hidden=true;return;}
 const labels={scan:"Scanning video",post:"Finalizing tracks",refine:"Applying learned masks",render:"Rendering video"};
 const text=[p.message||labels[p.stage]||p.stage||"Working"];
 if(Number.isFinite(p.done)&&Number.isFinite(p.total)&&p.total>0){
  text.push(`${p.done.toLocaleString()} / ${p.total.toLocaleString()} ${p.unit||"items"}`);
  bar.max=p.total;bar.value=Math.min(p.done,p.total);bar.hidden=false;
 }else bar.hidden=true;
 const now=j.server_time||Date.now()/1000;
 if(p.started_at)text.push(`elapsed ${sectionTime(now-p.started_at)}`);
 if(p.stage==="scan"&&Number.isFinite(p.rate_per_second)&&p.rate_per_second>0){
  const rate=p.rate_per_second<.1?p.rate_per_second.toFixed(3):p.rate_per_second.toFixed(2);
  text.push(`${rate} frames/s recent`);
 }
 if(p.last_progress_at)text.push(`last progress ${Math.max(0,Math.floor(now-p.last_progress_at))}s ago`);
 box.textContent=text.join(" · ");
 if(p.last_progress_at&&now-p.last_progress_at>30)document.getElementById("eta").textContent="";
}

function sectionEscape(value){return String(value).replace(/[&<>"']/g,c=>({"&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;","'":"&#39;"}[c]));}
function sectionSeconds(value){
 const parts=String(value).trim().split(":");
 if(parts.length>3||parts.some(p=>!p.trim()||!Number.isFinite(Number(p))||Number(p)<0))throw new Error("Enter a time in seconds or mm:ss.");
 return parts.reduce((n,p)=>n*60+Number(p),0);
}
function refreshSectionModels(){
 const select=document.getElementById("sectionModel");if(!select)return;
 const models=typeof LEARNED_MODEL_LIST!=="undefined"?LEARNED_MODEL_LIST:[];
 const key=JSON.stringify(models.map(m=>[m.id,m.name,m.kind,m.validation?.status]));
 if(select.dataset.models===key){
  if(document.getElementById("sectionModelMode"))refreshLearnedModelMode("sectionModel","sectionModelMode");
  return;
 }
 const selected=select.value;
 select.replaceChildren(new Option("Original plate masks",""));
 for(const model of models)select.add(new Option(model.name,model.id));
 select.value=models.some(m=>m.id===selected)?selected:"";
 select.dataset.models=key;
 if(document.getElementById("sectionModelMode"))refreshLearnedModelMode("sectionModel","sectionModelMode");
}
async function loadSectionsPanel(j,id,view){
 const panel=document.getElementById("sectionsPanel");if(!panel)return;
 const available=["review","paused","done"].includes(j.phase);
 panel.hidden=!available;if(!available)return;
 refreshSectionModels();
 const key=`${id}:${j.sections_revision||0}:${j.phase}`;
 if(panel.dataset.key===key||panel.dataset.loading===key)return;
 panel.dataset.loading=key;
 try{
  if(j.section){
   const s=j.section;
   panel.innerHTML=`<div class="warn"><b>${s.role==="export"?"Approved section export":"Section candidate"}</b>
    <p class="review-copy">${s.role==="export"?"This video uses the saved approved revision.":"Review this candidate, then approve it to update only its section. The previous approved result stays available."}</p>
    <button class="sec" onclick="openJob('${sectionEscape(s.parent_id)}')">Back to video sections</button>
    ${s.role==="candidate"?`<button onclick="sectionAction('${sectionEscape(s.parent_id)}','${sectionEscape(s.section_id)}','approve','${id}',this)">Approve this section</button>`:""}</div>`;
   panel.dataset.key=key;return;
  }
  const {data}=await reviewRequest(`api/jobs/${id}/sections`);
  if(CUR!==id||JOBVIEW!==view||!panel.isConnected)return;
  const fps=data.identity.fps,total=data.identity.total_frames;
  const next=data.items.reduce((m,s)=>Math.max(m,s.end_frame),0);
  const end=Math.min(total,next+Math.ceil(300*fps));
  let html=`<details open><summary style="cursor:pointer;font-weight:600">Video sections</summary>
   <p class="review-copy">Approve finished sections, export them, or review a new scan of one interval. Times refer to the original video.</p>
   <div class="row" style="align-items:end;gap:10px;flex-wrap:wrap">
    <label>Name<br><input id="sectionName" value="Section ${data.items.length+1}" style="width:160px"></label>
    <label>Start (s or mm:ss)<br><input id="sectionStart" value="${String(next/fps)}" style="width:100px"></label>
    <label>End (s or mm:ss)<br><input id="sectionEnd" value="${String(end/fps)}" style="width:100px"></label>
    <button onclick="createSection(this)">Add section</button></div>
   <label style="display:block;margin:12px 0">Model for section rescans
    <select id="sectionModel" style="max-width:100%" onchange="refreshLearnedModelMode('sectionModel','sectionModelMode')"><option value="">Original plate masks</option></select></label>
   <label style="display:block;margin:12px 0">Selected model use
    <select id="sectionModelMode" aria-label="Section model use" disabled style="max-width:100%"><option value="">Select a model first</option></select></label>`;
  for(const s of data.items){
   const sid=sectionEscape(s.id),approved=s.approved;
   html+=`<div style="border-top:1px solid #334155;padding:10px 0;overflow-wrap:anywhere">
    <b>${sectionEscape(s.name)}</b> <span class="badge">${sectionTime(s.start_frame/fps)}–${sectionTime(s.end_frame/fps)}</span>
    <p class="review-copy">${approved?`Approved · revision ${approved.revision} · ${sectionEscape(approved.model)}`:"Needs review"}</p>
    <div class="row" style="gap:8px;flex-wrap:wrap">
    ${!approved?`<button onclick="sectionAction('${id}','${sid}','approve','',this)">Approve current results</button>`:""}
    <button class="sec" onclick="sectionAction('${id}','${sid}','rescan','',this)">Rescan section</button>
    ${s.candidate_id?`<button class="sec" onclick="openJob('${sectionEscape(s.candidate_id)}')">Open candidate</button>`:""}
    ${approved?`<button onclick="sectionAction('${id}','${sid}','export','',this)">Export approved section</button>`:""}
    ${s.export_id?`<button class="sec" onclick="openJob('${sectionEscape(s.export_id)}')">Open export</button>`:""}
    </div></div>`;
  }
  panel.innerHTML=html+'</details>';panel.dataset.key=key;refreshSectionModels();
 }catch(error){if(CUR===id&&JOBVIEW===view)panel.textContent="Sections unavailable: "+(error.message||error);}
 finally{if(panel.dataset.loading===key)delete panel.dataset.loading;}
}
async function saveSectionReview(){
 const id=CUR,view=JOBVIEW;
 if(!await flushPlateSaves()||CUR!==id||JOBVIEW!==view)return false;
 // Box and audio edits do not increment the card-decision revision.
 if(document.getElementById("beCv")||(document.getElementById("review")&&reviewChoicesPending())){
  const saved=await saveAndRender(true);
  return saved&&CUR===id&&JOBVIEW===view;
 }
 return true;
}
async function createSection(button){
 try{
  const id=CUR,view=JOBVIEW;
  const payload={name:document.getElementById("sectionName").value,
   start:sectionSeconds(document.getElementById("sectionStart").value),end:sectionSeconds(document.getElementById("sectionEnd").value)};
  button.disabled=true;
  if(!await saveSectionReview()||CUR!==id||JOBVIEW!==view)return;
  await reviewRequest(`api/jobs/${id}/sections`,{method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify(payload),timeoutMs:120000});
  if(CUR===id&&JOBVIEW===view){delete document.getElementById("sectionsPanel").dataset.key;refresh();}
 }catch(error){alert(error.message||error);}finally{button.disabled=false;}
}
async function sectionAction(id,sid,action,candidate,button){
 const selected=document.getElementById("sectionModel")?.value||"";
 const selectedMode=document.getElementById("sectionModelMode")?.value||"";
 const view=JOBVIEW,opened=CUR;
 try{
  if(!await saveSectionReview())return;
  if(CUR!==opened||JOBVIEW!==view)return;
  button.disabled=true;
  const payload=candidate?{candidate_id:candidate}:{model_id:selected};
  if(action==="rescan"&&selected&&selectedMode)payload.learned_plate_model_mode=selectedMode;
  const {data}=await reviewRequest(`api/jobs/${id}/sections/${sid}/${action}`,{method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify(payload),timeoutMs:120000});
  if(CUR!==opened||JOBVIEW!==view)return;
  JOBSJSON="";
  if(data.job_id)await openJob(data.job_id);
  else{await openJob(id);}
 }catch(error){alert(error.message||error);}finally{button.disabled=false;}
}

let BE={t:0,ox:0,oy:0,boxes:[],sel:-1,ov:{},dis:{},times:{},adds:[],
        add:false,addAnchor:null,drag:null,scale:1,dur:10,
        plateMode:false,platePoints:[]};
async function loadBoxEdit(fromReview){
 if(!await showPanel(fromReview?"boxedit_rev":"boxedit"))return;
 const mi=await (await fetch(`api/jobs/${CUR}/mediainfo`)).json();
 const ri=await (await fetch(`api/jobs/${CUR}/detections`)).json();
 // in review: the slot right under the Preview button; on done: the actions slot
 let c=document.getElementById("beslot")||document.getElementById("beslot_done");
 if(!c){c=document.createElement("div");c.id="beslot";c.style.width="100%";
  (document.getElementById("review")||document.getElementById("jobcard")||detail)
   .appendChild(c);}
 BE={t:0,ox:0,oy:0,boxes:[],sel:-1,ov:{},dis:{},times:{},adds:[],
     add:false,addAnchor:null,drag:null,scale:1,dur:mi.duration,
     win:[0,mi.duration],trk:false,muteArm:false,tlDrag:null,
     plateMode:false,platePoints:[],
     tlspans:[],audio:[],audioSel:-1,indexed:!!ri.indexed_frames,
     fps:ri.fps,frameCount:ri.frame_count,frame:0,imageFrame:-1,maskFrame:-1};
 c.innerHTML=`${reviewOverlayLegendHTML()}<div class="row" style="margin-top:8px">
  <button class="sec" id="bePlay" style="padding:3px 11px" title="${BE.indexed?'Play video; pause for precise masks':'Play the video with live boxes — pause to edit them'}" onclick="beTogglePlay()">&#9654;</button>t=
  ${BE.indexed?'<button class="sec" id="bePrev" onclick="beStepFrame(-1)" title="Previous frame">&#9664; frame</button>':''}
  <input type="range" id="beT" min="0" max="${BE.indexed?Math.max(0,BE.frameCount-1):Math.max(0.2,mi.duration-0.1).toFixed(1)}"
   step="${BE.indexed?'1':'0.1'}" value="0" style="flex:1" oninput="beScrub()"><span id="beL">0s</span>
  ${BE.indexed?'<button class="sec" id="beNext" onclick="beStepFrame(1)" title="Next frame">frame &#9654;</button>':''}</div>
  ${BE.indexed?'<div style="font-size:12px;color:#94a3b8">Pause to inspect the exact frame and mask; masks are hidden during playback.</div>':''}
  <div style="position:relative;display:inline-block;max-width:100%">
   <img id="beImg" style="max-width:100%;border-radius:8px">
   <video id="beVid" style="max-width:100%;border-radius:8px;display:none" playsinline preload="none"></video>
   <canvas id="beCv" style="position:absolute;left:0;top:0;touch-action:none"></canvas></div>
  <canvas id="beTL" style="width:100%;height:72px;display:block;margin-top:6px;
   border-radius:6px;touch-action:none;cursor:crosshair"
   title="Timeline: colored spans = detections. Drag the orange handles to set the active window; click to seek."></canvas>
  <div class="row" style="font-size:12.5px;align-items:center;margin-top:2px">
   <span id="beWinL" style="color:#94a3b8">window: whole video</span>
   <button class="sec" style="padding:3px 8px;font-size:12px" onclick="beWinReset()">reset window</button>
   <span style="flex:1"></span>
   <select id="beAMode" style="font-size:12px"><option value="mute">mute</option>
    <option value="bleep">bleep</option></select>
   <button class="tog" id="beMute" onclick="beMuteMode()">&#128263; Audio span</button>
   <button class="danger" id="beARm" style="display:none" onclick="beAudioRm()">Delete span</button></div>
  <div id="beASugg" style="display:none;margin-top:6px"></div>
  <div id="beATx" style="display:none;margin-top:6px"></div>
  <div style="font-size:12px;color:#94a3b8">Moving or resizing a shaped mask removes its shape; faces follow the selected face shape, other detections use a box. The effective red/green shape matches renderer coverage; the yellow dashed box is only the primary detector proposal.</div>
  <div class="row" style="margin-top:6px">
   <button class="tog" id="beAdd" onclick="beAddMode()">&#65291; Add box</button>
   <button class="tog" id="beTrk" onclick="beTrackMode()">&#8857; Track object</button>
   <button class="tog" id="bePlate" onclick="bePlateMode()">&#9645; Draw plate (4 corners)</button>
   <button class="danger" id="beRm" style="display:none" onclick="beRemove()">Remove blur</button>
   <span id="beTimes" style="display:none;align-items:center;gap:4px;font-size:13px">
    from <input type="number" id="beT0" step="0.1" min="0" style="width:74px">
    to <input type="number" id="beT1" step="0.1" style="width:74px"> s
    <button class="sec" onclick="beApplyTimes()">Apply times</button></span>
   <span id="beTrkSt" style="display:none;font-size:13px;color:#fbbf24">tracking&#8230;</span>
   <button onclick="beSave()">Save changes &amp; re-render</button></div>
  <p style="font-size:12px;color:#94a3b8;margin:4px 0 0">&#9654; ${BE.indexed?"plays the video without masks; pause to inspect a frame.":"plays the video with the overlays moving live (pause to edit)."} Click an effective outline to
   select — red means hidden, green means visible, and yellow dashed is only the detector proposal. Drag inside to move, a corner to resize, edit its from/to times,
   or remove its blur. &#65291; Add box: drag a static region. &#8857; Track object:
   drag the timeline handles to the part of the video you care about, scrub
   to a frame where the object is clear, draw a box around it — it will be
   followed and blurred through the window. &#9645; Draw plate: choose the
   time window, then click its four corners clockwise (top-left, top-right,
   bottom-right, bottom-left) to create a tracked, perspective-tight plate
   mask and a local verified training sample. &#128263; Audio span: drag
   on the timeline's bottom lane to silence (or bleep) that stretch of sound.</p>`;
 const img=document.getElementById("beImg");
 img.onload=()=>{if(BE.playing)return;const cv=document.getElementById("beCv");
  cv.width=img.clientWidth;cv.height=img.clientHeight;
  BE.scale=img.clientWidth/(img.naturalWidth||1);beDraw();};
 const bv=document.getElementById("beVid");
 bv.addEventListener("pause",()=>{if(BE.playing)bePlayStop();});
 bv.addEventListener("ended",()=>{if(BE.playing)bePlayStop();});
 beHook();tlHook();await tlInit();beScrub();
}

// ---- playback with live boxes (issue #17: review was scrub-only) ----
async function beTogglePlay(){
 const v=document.getElementById("beVid"),img=document.getElementById("beImg");
 if(!v)return;
 if(BE.playing){v.pause();return;}          // the pause handler cleans up
 if(!v.src)v.src=`api/jobs/${CUR}/video`;
 BE.playing=true;
 if(BE.indexed){BE.seq=(BE.seq||0)+1;BE.pending=true;BE.imageFrame=-1;BE.maskFrame=-1;BE.addAnchor=null;BE.addFloat=null;BE.drag=null;beDraw();}
 v.style.display="block";img.style.display="none";
 // boxes are view-only while playing: freeze pointer edits so a moving
 // box can't be grabbed mid-flight
 const cv=document.getElementById("beCv");cv.style.pointerEvents="none";
 document.getElementById("bePlay").innerHTML="&#10074;&#10074;";
 try{
  if(v.readyState<1)await new Promise((res,rej)=>{
   v.onloadedmetadata=res;
   v.onerror=()=>rej(new Error("the browser cannot decode this file"));
   v.load();});
  v.currentTime=BE.t||0;
  await v.play();
 }catch(e){
  bePlayStop();
  alert("Could not play the video in this browser ("+(e&&e.message||e)
   +") — the scrub slider still works frame by frame.");
  return;
 }
 if(v.clientWidth){cv.width=v.clientWidth;cv.height=v.clientHeight;
  BE.scale=v.clientWidth/(v.videoWidth||1);}
 // boxes come from the server per timestamp; refresh them on a throttle
 // while rAF keeps the playhead, label and box painting per-frame smooth
 let lastQ=0,inFlight=false;
 const step=()=>{
  if(!BE.playing)return;
  BE.t=v.currentTime;
  document.getElementById("beT").value=BE.indexed?Math.max(0,Math.min(BE.frameCount-1,Math.round(BE.t*BE.fps))):BE.t;
  document.getElementById("beL").textContent=BE.t.toFixed(1)+"s";
  const now=performance.now();
  if(!BE.indexed&&!inFlight&&now-lastQ>150){
   inFlight=true;lastQ=now;
   beRefresh(BE.t).finally(()=>{inFlight=false;});
  }
  beDraw();beTLDraw();
  requestAnimationFrame(step);
 };
 requestAnimationFrame(step);
}
function bePlayStop(){
 BE.playing=false;
 const v=document.getElementById("beVid");
 if(BE.indexed){if(v&&Number.isFinite(v.currentTime))BE.t=v.currentTime;
  const frame=Math.max(0,Math.min(BE.frameCount-1,Math.round(BE.t*BE.fps)));
  const slider=document.getElementById("beT");if(slider)slider.value=frame;}
 if(v){try{v.pause();}catch(e){}v.style.display="none";}
 const img=document.getElementById("beImg");if(img)img.style.display="";
 const b=document.getElementById("bePlay");if(b)b.innerHTML="&#9654;";
 const cv=document.getElementById("beCv");if(cv)cv.style.pointerEvents="auto";
 beScrub();   // crisp frame + authoritative boxes at the pause point
}

const TLC={name:"#3b82f6",dob:"#22c55e",phone:"#f59e0b",ssn:"#ef4444",
 mrn:"#8b5cf6",email:"#14b8a6",address:"#f97316",card:"#db2777",
 apikey:"#0891b2",ipaddr:"#65a30d",plate:"#7c3aed",face:"#ec4899",
 person:"#0ea5e9",manual:"#eab308"};
async function tlInit(){
 // one fetch of the full report: detection spans for the lanes (dense
 // tracks collapse to one span per track) + stored audio redactions
 try{
  const doc=await (await fetch(`api/jobs/${CUR}/report`)).json();
  const per={};
  for(const d of (doc.detections||[])){
   if(d.enabled===false)continue;
   const key=d.category+((d.track??-1)>=0?(":t"+d.track):(":i"+Math.random()));
   const s=per[key]||(per[key]={cat:d.category,t0:d.t_start,t1:d.t_end});
   s.t0=Math.min(s.t0,d.t_start);s.t1=Math.max(s.t1,d.t_end);
  }
  BE.tlspans=Object.values(per);
  BE.audio=(doc.audio_redactions||[]).map(s=>({t0:s.t0,t1:s.t1,mode:s.mode||"mute"}));
  BE.audioSugg=doc.audio_suggestions||[];
  BE.audioTx=doc.audio_transcript||[];BE.txAnchor=-1;
  renderAudioSugg();renderTranscript();
 }catch(e){BE.tlspans=[];}
 beTLDraw();
}
function tlX(t,w){return Math.max(0,Math.min(w,t/Math.max(0.1,BE.dur)*w));}
function beTLDraw(){
 const cv=document.getElementById("beTL");if(!cv)return;
 const w=cv.clientWidth||600;cv.width=w;cv.height=72;
 const g=cv.getContext("2d");
 g.fillStyle="#0f172a";g.fillRect(0,0,w,72);
 // category lanes
 const cats=[...new Set(BE.tlspans.map(s=>s.cat))];
 const laneH=cats.length?Math.min(10,44/Math.max(1,cats.length)):0;
 BE.tlspans.forEach(s=>{
  const row=cats.indexOf(s.cat);
  g.fillStyle=TLC[s.cat]||"#94a3b8";
  g.globalAlpha=0.9;
  g.fillRect(tlX(s.t0,w),4+row*laneH,
             Math.max(2,tlX(s.t1,w)-tlX(s.t0,w)),Math.max(3,laneH-2));
 });
 g.globalAlpha=1;
 // audio lane (bottom 14px)
 g.fillStyle="#1e293b";g.fillRect(0,54,w,14);
 BE.audio.forEach((s,i)=>{
  g.fillStyle=i===BE.audioSel?"#f87171":(s.mode==="bleep"?"#fb923c":"#dc2626");
  g.fillRect(tlX(s.t0,w),55,Math.max(2,tlX(s.t1,w)-tlX(s.t0,w)),12);
 });
 g.fillStyle="#64748b";g.font="9px sans-serif";g.fillText("audio",3,64);
 // dim outside the active window + orange handles
 g.fillStyle="rgba(2,6,23,0.72)";
 g.fillRect(0,0,tlX(BE.win[0],w),72);
 g.fillRect(tlX(BE.win[1],w),0,w-tlX(BE.win[1],w),72);
 g.fillStyle="#f59e0b";
 g.fillRect(tlX(BE.win[0],w)-2,0,4,72);g.fillRect(tlX(BE.win[1],w)-2,0,4,72);
 // playhead
 g.strokeStyle="#f8fafc";g.beginPath();
 g.moveTo(tlX(BE.t,w),0);g.lineTo(tlX(BE.t,w),72);g.stroke();
 const full=BE.win[0]<0.05&&BE.win[1]>BE.dur-0.05;
 document.getElementById("beWinL").textContent=full?"window: whole video"
  :`window: ${BE.win[0].toFixed(1)}–${BE.win[1].toFixed(1)}s`;
}
function tlHook(){
 const cv=document.getElementById("beTL");if(!cv)return;
 const tAt=e=>{const r=cv.getBoundingClientRect();
  return Math.max(0,Math.min(BE.dur,(e.clientX-r.left)/r.width*BE.dur));};
 const yAt=e=>{const r=cv.getBoundingClientRect();return e.clientY-r.top;};
 cv.addEventListener("pointerdown",e=>{
  cv.setPointerCapture(e.pointerId);
  const t=tAt(e),w=cv.clientWidth,px=e.clientX-cv.getBoundingClientRect().left;
  if(Math.abs(px-tlX(BE.win[0],w))<7){BE.tlDrag={k:"w0"};return;}
  if(Math.abs(px-tlX(BE.win[1],w))<7){BE.tlDrag={k:"w1"};return;}
  if(yAt(e)>=54){                                  // audio lane
   if(BE.muteArm){BE.tlDrag={k:"anew",t0:t};
    BE.audio.push({t0:t,t1:t,mode:document.getElementById("beAMode").value});
    BE.audioSel=BE.audio.length-1;beTLDraw();return;}
   const hit=BE.audio.findIndex(s=>t>=s.t0&&t<=s.t1);
   BE.audioSel=hit;
   document.getElementById("beARm").style.display=hit>=0?"inline-block":"none";
   beTLDraw();return;
  }
  BE.tlDrag={k:"seek"};
  document.getElementById("beT").value=BE.indexed?Math.round(t*BE.fps):t.toFixed(1);beScrub();
 });
 cv.addEventListener("pointermove",e=>{
  if(!BE.tlDrag)return;
  const t=tAt(e);
  if(BE.tlDrag.k==="w0")BE.win[0]=Math.min(t,BE.win[1]-0.2);
  else if(BE.tlDrag.k==="w1")BE.win[1]=Math.max(t,BE.win[0]+0.2);
  else if(BE.tlDrag.k==="anew"){
   const s=BE.audio[BE.audioSel];
   s.t0=Math.min(BE.tlDrag.t0,t);s.t1=Math.max(BE.tlDrag.t0,t);
  }else if(BE.tlDrag.k==="seek"){
   document.getElementById("beT").value=BE.indexed?Math.round(t*BE.fps):t.toFixed(1);beScrub();}
  beTLDraw();
 });
 cv.addEventListener("pointerup",()=>{
  if(BE.tlDrag&&BE.tlDrag.k==="anew"){
   const s=BE.audio[BE.audioSel];
   if(s.t1-s.t0<0.15){BE.audio.pop();BE.audioSel=-1;}   // stray click
   BE.muteArm=false;document.getElementById("beMute").classList.remove("on");
   document.getElementById("beARm").style.display=BE.audioSel>=0?"inline-block":"none";
   renderTranscript();
  }
  BE.tlDrag=null;beTLDraw();
 });
}
function beWinReset(){BE.win=[0,BE.dur];beTLDraw();}
function beMuteMode(){
 BE.muteArm=!BE.muteArm;BE.trk=false;BE.add=false;BE.addAnchor=null;
 BE.plateMode=false;BE.platePoints=[];
 const pb=document.getElementById("bePlate");if(pb)pb.classList.remove("on");
 document.getElementById("beMute").classList.toggle("on",BE.muteArm);
 document.getElementById("beTrk").classList.remove("on");
 document.getElementById("beAdd").classList.remove("on");
}
function beAudioRm(){
 if(BE.audioSel>=0){BE.audio.splice(BE.audioSel,1);BE.audioSel=-1;
  document.getElementById("beARm").style.display="none";
  renderTranscript();renderAudioSugg();beTLDraw();}
}
function beTrackMode(){
 BE.trk=!BE.trk;BE.add=false;BE.addAnchor=null;BE.muteArm=false;
 BE.plateMode=false;BE.platePoints=[];
 const pb=document.getElementById("bePlate");if(pb)pb.classList.remove("on");
 document.getElementById("beTrk").classList.toggle("on",BE.trk);
 document.getElementById("beAdd").classList.remove("on");
 document.getElementById("beMute").classList.remove("on");
}
function bePlateMode(){
 BE.plateMode=!BE.plateMode;BE.platePoints=[];BE.add=false;
 BE.addAnchor=null;BE.trk=false;BE.muteArm=false;BE.sel=-1;
 document.getElementById("bePlate").classList.toggle("on",BE.plateMode);
 document.getElementById("beAdd").classList.remove("on");
 document.getElementById("beTrk").classList.remove("on");
 document.getElementById("beMute").classList.remove("on");
 beDraw();
}
async function beTrackGo(box,quad=null){
 const st=document.getElementById("beTrkSt");st.style.display="inline";
 st.textContent=`tracking ${BE.win[0].toFixed(1)}–${BE.win[1].toFixed(1)}s…`;
 const r=await fetch(`api/jobs/${CUR}/track_object`,{method:"POST",
  headers:{"Content-Type":"application/json"},
  body:JSON.stringify({box,t_ref:BE.t,t0:BE.win[0],t1:BE.win[1],
   ...(quad?{plate_quad:quad,require_confirmation:true}:{})})});
 if(!r.ok){st.textContent="tracking failed to start";return;}
 const poll=setInterval(async()=>{
  const d=await (await fetch(`api/jobs/${CUR}/track_status`)).json();
  if(d.state!=="running"){
   clearInterval(poll);
   st.textContent=d.error?("⚠ "+d.error)
    :`tracked ✓ ${d.added} position(s) — review card added`;
   if(!d.error){await tlInit();beScrub();
    if(document.getElementById("review"))loadReview();}
  }
 },1500);
}
async function beScrub(){
 const sl=document.getElementById("beT");if(!sl)return;
 if(BE.playing){
  const v=document.getElementById("beVid");
  if(v)v.currentTime=BE.indexed?(+sl.value/BE.fps):+sl.value;
  return;
 }
 BE.sel=-1;document.getElementById("beRm").style.display="none";
 document.getElementById("beTimes").style.display="none";
 const img=document.getElementById("beImg");
 if(BE.indexed){
  const owner=BE,frame=Math.max(0,Math.min(owner.frameCount-1,Math.round(+sl.value)));
  if(frame!==owner.frame){owner.addAnchor=null;owner.addFloat=null;owner.drag=null;}
  owner.frame=frame;sl.value=frame;owner.t=frame/owner.fps;
  owner.imageFrame=-1;owner.maskFrame=-1;owner.pending=true;
  document.getElementById("beL").textContent=`Frame ${frame} (${owner.t.toFixed(3)}s)`;
  const imageUrl=`api/jobs/${CUR}/frame_at?frame=${frame}`;
  img.onload=()=>{
   if(BE!==owner||owner.playing||owner.frame!==frame||
      (img.currentSrc&&!img.currentSrc.endsWith('/'+imageUrl)))return;
   owner.imageFrame=frame;
   const cv=document.getElementById("beCv");if(cv){cv.width=img.clientWidth;cv.height=img.clientHeight;owner.scale=img.clientWidth/(img.naturalWidth||1);}
   owner.pending=owner.maskFrame!==frame;beDraw();
  };
  img.onerror=()=>{if(BE===owner&&owner.frame===frame){owner.imageFrame=-1;owner.pending=true;beDraw();}};
  img.src=imageUrl;
 }else{
  BE.t=+sl.value;document.getElementById("beL").textContent=BE.t.toFixed(1)+"s";
  img.src=`api/jobs/${CUR}/frame_at?t=${BE.t}`;
 }
 await beRefresh();beTLDraw();
}
function beStepFrame(delta){
 if(!BE.indexed||BE.playing)return;
 const sl=document.getElementById("beT");
 sl.value=Math.max(0,Math.min(BE.frameCount-1,Number(sl.value)+delta));
 beScrub();
}
// Server computes the same pending edits, coverage and dense winner as render.
async function beRefresh(t=BE.t){
 const owner=BE,seq=owner.seq=(owner.seq||0)+1,frame=owner.frame;
 if(owner.indexed&&owner.playing)return false;
 owner.pending=true;beDraw();
 try{
  const query=owner.indexed?`frame=${frame}`:`t=${t}`;
  const r=await fetch(`api/jobs/${CUR}/boxes_at?${query}&all=1`,{
   method:"POST",headers:{"Content-Type":"application/json"},
   body:JSON.stringify({enabled:EN,box_overrides:owner.ov,time_overrides:owner.times})});
  if(!r.ok)throw new Error("mask preview failed");
  const d=await r.json();
  if(BE!==owner||owner.seq!==seq||owner.drag||(owner.indexed&&(owner.playing||owner.frame!==frame||d.frame!==frame)))return false;
  owner.ox=d.ox;owner.oy=d.oy;owner.raw=d.boxes;
  if(owner.indexed){owner.maskFrame=frame;owner.pending=owner.imageFrame!==frame;}
  else owner.pending=false;
  beFilter();beDraw();return !owner.pending;
 }catch(e){
  if(BE===owner&&owner.seq===seq){owner.pending=true;beDraw();}
  return false;
 }
}
function beFilter(){
 // Keep visible/model-filtered plate findings in the editor so green really
 // means "this stays visible", without reintroducing every kept face/text hit.
 BE.boxes=(BE.raw||[]).filter(b=>{
  const on=(b.i in EN)?EN[b.i]:b.enabled;
  return on||b.category==="plate";
 });
}
function beDraw(){
 const cv=document.getElementById("beCv");if(!cv)return;
 const x=cv.getContext("2d"),s=BE.scale;
 // Keep this primitive independently executable: focused regressions extract
 // the video editor without loading the rest of Review.
 const oc=typeof REVIEW_OVERLAY_COLORS!=="undefined"?REVIEW_OVERLAY_COLORS:{
  proposal:"#f5c400",hidden:"#dc2626",hiddenFill:"rgba(220,38,38,.24)",
  visible:"#22c55e",visibleFill:"rgba(34,197,94,.08)",edit:"#38bdf8"
 };
 const overlayState=b=>typeof reviewOverlayState==="function"
  ?reviewOverlayState(b.i,b)
  :{enabled:(b.i in EN)?!!EN[b.i]:b.enabled!==false,
    machineFiltered:false,machineSuggestion:false};
 x.clearRect(0,0,cv.width,cv.height);
 if(BE.indexed&&(BE.playing||BE.pending))return;
 for(const a of BE.adds){
  if(BE.t<a.t0-0.01||BE.t>a.t1+0.01)continue;
  const[a1,b1,a2,b2]=a.box.map(v=>v*s);
  x.fillStyle="rgba(245,158,11,.25)";x.strokeStyle="#f59e0b";x.lineWidth=2;
  x.fillRect(a1,b1,a2-a1,b2-b1);x.strokeRect(a1,b1,a2-a1,b2-b1);
 }
 if(BE.add&&BE.addAnchor&&BE.addFloat){
  const[p,q]=[BE.addAnchor,BE.addFloat];
  x.strokeStyle="#f59e0b";x.setLineDash([6,4]);x.lineWidth=2;
  x.strokeRect(Math.min(p[0],q[0])*s,Math.min(p[1],q[1])*s,
   Math.abs(q[0]-p[0])*s,Math.abs(q[1]-p[1])*s);x.setLineDash([]);
 }
 if(BE.platePoints&&BE.platePoints.length){
  x.beginPath();BE.platePoints.forEach((p,k)=>{
   if(k)x.lineTo(p[0]*s,p[1]*s);else x.moveTo(p[0]*s,p[1]*s);
  });
  x.strokeStyle=oc.edit;x.lineWidth=2;x.stroke();
  for(const p of BE.platePoints){
   x.beginPath();x.arc(p[0]*s,p[1]*s,5,0,Math.PI*2);
   x.fillStyle=oc.edit;x.fill();
  }
 }
 for(const b of BE.boxes){
  const[a1,b1,a2,b2]=b.box.map(v=>v*s),state=overlayState(b);
  const line=state.enabled?oc.hidden:oc.visible;
  const fill=state.enabled?oc.hiddenFill:oc.visibleFill;
  const machineVisible=!state.enabled&&state.machineFiltered;
  x.fillStyle=fill;x.strokeStyle=line;x.lineWidth=2;
  x.setLineDash(machineVisible?[7,4]:[]);
  let drew=false;
  if(!BE.pending&&!BE.drag&&b.mask_contours?.length){
   x.beginPath();
   for(const ring of b.mask_contours){if(!ring.length)continue;
    x.moveTo(ring[0][0]*s,ring[0][1]*s);
    for(const p of ring.slice(1))x.lineTo(p[0]*s,p[1]*s);
    x.closePath();}
   x.fill("evenodd");x.stroke();drew=true;
  }else if(b.category==="plate"&&b.plate_quad&&b.plate_quad.length===4){
   x.beginPath();b.plate_quad.forEach((p,k)=>{
    const px=(b.box[0]+p[0]*(b.box[2]-b.box[0]))*s;
    const py=(b.box[1]+p[1]*(b.box[3]-b.box[1]))*s;
    if(k)x.lineTo(px,py);else x.moveTo(px,py);
   });x.closePath();x.fill();x.stroke();drew=true;
  }
  if(!drew){x.fillRect(a1,b1,a2-a1,b2-b1);x.strokeRect(a1,b1,a2-a1,b2-b1);}
  x.setLineDash([]);
  if(b.category==="plate"&&b.plate_quad&&b.plate_quad.length===4){
   x.fillStyle=line;
   for(const p of b.plate_quad){
    const px=(b.box[0]+p[0]*(b.box[2]-b.box[0]))*s;
    const py=(b.box[1]+p[1]*(b.box[3]-b.box[1]))*s;
    x.beginPath();x.arc(px,py,3,0,Math.PI*2);x.fill();
   }
  }
  if(b.category==="plate"){
   x.strokeStyle=oc.proposal;x.lineWidth=1.5;x.setLineDash([6,4]);
   x.strokeRect(a1,b1,a2-a1,b2-b1);x.setLineDash([]);
  }
  if(b.category==="plate"&&state.machineSuggestion&&state.enabled){
   x.strokeStyle=oc.visible;x.lineWidth=1.5;x.setLineDash([5,4]);
   const inset=3;x.strokeRect(a1+inset,b1+inset,Math.max(0,a2-a1-2*inset),Math.max(0,b2-b1-2*inset));
   x.setLineDash([]);
  }
  if(b.i===BE.sel)for(const[hx,hy] of [[a1,b1],[a2,b1],[a1,b2],[a2,b2]]){
   x.fillStyle="#0f172a";x.fillRect(hx-5,hy-5,10,10);
   x.strokeStyle=oc.edit;x.lineWidth=2;x.strokeRect(hx-5,hy-5,10,10);}
 }
}
function beAddMode(){
 BE.add=!BE.add;BE.addAnchor=null;BE.sel=-1;
 BE.plateMode=false;BE.platePoints=[];
 const pb=document.getElementById("bePlate");if(pb)pb.classList.remove("on");
 BE.trk=false;BE.muteArm=false;
 document.getElementById("beAdd").classList.toggle("on",BE.add);
 const tb=document.getElementById("beTrk");if(tb)tb.classList.remove("on");
 const mb=document.getElementById("beMute");if(mb)mb.classList.remove("on");
 document.getElementById("beRm").style.display="none";
 document.getElementById("beTimes").style.display="none";
 beDraw();
}
function beApplyTimes(){
 if(BE.sel<0)return;
 const t0=+document.getElementById("beT0").value,
       t1=+document.getElementById("beT1").value;
 if(!(t1>t0&&t0>=0)){alert("'to' must be after 'from'.");return;}
 BE.times[BE.sel]=[t0,Math.min(t1,BE.dur)];
 const b=BE.boxes.find(x=>x.i===BE.sel);
 if(b){b.t_start=t0;b.t_end=t1;}
 beRefresh();
}
function beShowTimes(b){
 const el=document.getElementById("beTimes");
 el.style.display="inline-flex";
 document.getElementById("beT0").value=BE.indexed?String(b.t_start):b.t_start.toFixed(1);
 document.getElementById("beT1").value=BE.indexed?String(b.t_end):b.t_end.toFixed(1);
}
function beHook(){
 const cv=document.getElementById("beCv");
 const pt=e=>{const r=cv.getBoundingClientRect();
  return[(e.clientX-r.left)/BE.scale,(e.clientY-r.top)/BE.scale];};
 cv.addEventListener("pointerdown",e=>{
  if(BE.indexed&&(BE.playing||BE.pending||BE.imageFrame!==BE.frame||BE.maskFrame!==BE.frame))return;
  const p=pt(e);cv.setPointerCapture(e.pointerId);
  if(BE.plateMode){
   BE.platePoints.push(p);
   if(BE.platePoints.length===4){
    const pts=BE.platePoints.slice();BE.platePoints=[];
    BE.plateMode=false;document.getElementById("bePlate").classList.remove("on");
    const xs=pts.map(v=>v[0]),ys=pts.map(v=>v[1]);
    const box=[Math.min(...xs),Math.min(...ys),Math.max(...xs),Math.max(...ys)];
    if(box[2]-box[0]>5&&box[3]-box[1]>3){
     const quad=pts.map(v=>[(v[0]-box[0])/(box[2]-box[0]),
                            (v[1]-box[1])/(box[3]-box[1])]);
     beTrackGo(box,quad);
    }else alert("Plate corners are too close together.");
   }
   beDraw();return;
  }
  if(BE.trk){
   // Track object: same two-click box draw as Add box, but on completion
   // the region is template-tracked through the active timeline window
   if(!BE.addAnchor){BE.addAnchor=p;BE.addFloat=p;}
   else{
    const a=BE.addAnchor,q=p;BE.addAnchor=null;BE.addFloat=null;
    const box=[Math.min(a[0],q[0]),Math.min(a[1],q[1]),
               Math.max(a[0],q[0]),Math.max(a[1],q[1])];
    BE.trk=false;document.getElementById("beTrk").classList.remove("on");
    if(box[2]-box[0]>10&&box[3]-box[1]>10)beTrackGo(box);
    beDraw();
   }
   return;
  }
  if(BE.add){
   if(!BE.addAnchor){BE.addAnchor=p;BE.addFloat=p;}
   else{
    const a=BE.addAnchor,q=p;BE.addAnchor=null;BE.addFloat=null;
    const box=[Math.min(a[0],q[0]),Math.min(a[1],q[1]),
               Math.max(a[0],q[0]),Math.max(a[1],q[1])];
    if(box[2]-box[0]>6&&box[3]-box[1]>6){
     const t0=Math.max(0,+(BE.t-0.5).toFixed(1)),
           t1=Math.min(BE.dur,+(BE.t+3).toFixed(1));
     const fr=prompt("Blur this region FROM (seconds):",t0);
     if(fr===null){beDraw();return;}
     const to=prompt("...TO (seconds):",t1);
     if(to===null){beDraw();return;}
     BE.adds.push({box,t0:Math.max(0,+fr||0),
                   t1:Math.min(BE.dur,+to||t1),tref:BE.t});
    }
    beDraw();
   }
   return;
  }
  const sel=BE.boxes.find(b=>b.i===BE.sel);
  if(sel){const[a1,b1,a2,b2]=sel.box,hs=9/BE.scale;
   const corners=[[a1,b1,0],[a2,b1,1],[a1,b2,2],[a2,b2,3]];
   for(const[hx,hy,ci] of corners)
    if(Math.abs(p[0]-hx)<hs&&Math.abs(p[1]-hy)<hs){
     BE.drag={kind:"corner",ci};return;}
   if(p[0]>=a1&&p[0]<=a2&&p[1]>=b1&&p[1]<=b2){
    BE.drag={kind:"move",off:[p[0]-a1,p[1]-b1]};return;}
  }
  const hit=[...BE.boxes].reverse().find(b=>{
   const[a1,b1,a2,b2]=b.box;
   return p[0]>=a1&&p[0]<=a2&&p[1]>=b1&&p[1]<=b2;});
  BE.sel=hit?hit.i:-1;
  document.getElementById("beRm").style.display=hit?"inline-block":"none";
  if(hit)beShowTimes(hit);
  else document.getElementById("beTimes").style.display="none";
  beDraw();
 });
 cv.addEventListener("pointermove",e=>{
  if(BE.add&&BE.addAnchor){BE.addFloat=pt(e);beDraw();return;}
  if(!BE.drag||BE.sel<0)return;
  const p=pt(e),b=BE.boxes.find(x=>x.i===BE.sel);if(!b)return;
  let[a1,b1,a2,b2]=b.box;
  if(BE.drag.kind==="move"){
   const w0=a2-a1,h0=b2-b1;a1=p[0]-BE.drag.off[0];b1=p[1]-BE.drag.off[1];
   a2=a1+w0;b2=b1+h0;
  }else{
   if(BE.drag.ci===0){a1=p[0];b1=p[1];}
   if(BE.drag.ci===1){a2=p[0];b1=p[1];}
   if(BE.drag.ci===2){a1=p[0];b2=p[1];}
   if(BE.drag.ci===3){a2=p[0];b2=p[1];}
  }
  b.box=[Math.min(a1,a2),Math.min(b1,b2),Math.max(a1,a2),Math.max(b1,b2)];
  BE.seq=(BE.seq||0)+1;BE.pending=true;
  BE.ov[BE.sel]=[b.box[0]-BE.ox,b.box[1]-BE.oy,b.box[2]-BE.ox,b.box[3]-BE.oy];
  beDraw();
 });
 cv.addEventListener("pointerup",()=>{if(BE.drag){BE.drag=null;beRefresh();}});
}

// Only visible finding previews are requested. Editing reuses the same image
// and geometry; it never starts a second video/image request.
let REVIEW_MEDIA=null;
async function reviewRequest(url, options={}, type="json"){
 const {timeoutMs=15000,...fetchOptions}=options;
 const ctl=new AbortController(),parent=fetchOptions.signal;
 // Abort fetch as well as settling our caller: a suspended transport or body
 // reader must not keep a single-flight slot occupied after its deadline.
 let rejectStopped;
 const stopped=new Promise((_,reject)=>{rejectStopped=reject;});
 const stop=error=>{rejectStopped(error);ctl.abort();};
 const abort=()=>stop(new DOMException("Request cancelled","AbortError"));
 if(parent){if(parent.aborted)ctl.abort();else parent.addEventListener("abort",abort,{once:true});}
 const timer=setTimeout(()=>stop(new DOMException("Request timed out","TimeoutError")),timeoutMs);
 try{
  const request=(async()=>{
   if(ctl.signal.aborted)throw new DOMException("Request cancelled","AbortError");
   const response=await fetch(url,{...fetchOptions,signal:ctl.signal});
   if(!response.ok){
    let message="Server returned HTTP "+response.status,details=null;
    try{details=await response.json();message=details.error||message;}catch(_){}
    const error=new Error(message);error.status=response.status;error.details=details;throw error;
   }
   return {response,data:await response[type]()};
  })();
  return await Promise.race([request,stopped]);
 }finally{clearTimeout(timer);if(parent)parent.removeEventListener("abort",abort);}
}
function clearReviewPreviews(){
 if(!REVIEW_MEDIA)return;
 const old=REVIEW_MEDIA;REVIEW_MEDIA=null;
 if(old.observer)old.observer.disconnect();
 if(old.retryTimer)clearTimeout(old.retryTimer);
 old.controllers.forEach(c=>c.abort());
 [...old.queue.splice(0),...old.cacheQueue.splice(0)].forEach(task=>task.resolve(false));
 old.urls.forEach(url=>URL.revokeObjectURL(url));
}
function drawPlateThumbnail(img){
 if(!img._plateMeta||!img.naturalWidth)return;
 const state=initPlateCorners(img);if(state)state.draw();
}
function queueReviewPreview(img, priority=false){
 const state=REVIEW_MEDIA;
 if(!state||!img||!img.isConnected)return Promise.resolve(false);
 if((img._plateMeta||(!priority&&img._previewLoaded))&&img.naturalWidth)return Promise.resolve(true);
 if(img._previewTask){
  if(priority){
   img._previewTask.priority=true;
   for(const queue of [state.cacheQueue,state.queue]){
    const n=queue.indexOf(img._previewTask);
    if(n>=0)queue.unshift(...queue.splice(n,1));
   }
  }
  return img._previewTask.promise;
 }
 const task={img,priority,resolve:null,promise:null};
 task.promise=new Promise(resolve=>task.resolve=resolve);
 img._previewTask=task;
 if(priority)state.cacheQueue.unshift(task);else state.cacheQueue.push(task);
 pumpReviewPreviews(state);return task.promise;
}
async function loadReviewPreview(state,task,cacheOnly){
 const img=task.img, counter=cacheOnly?"cacheActive":"active";
 state[counter]++;
 const ctl=new AbortController();state.controllers.add(ctl);
 const card=img.closest(".det"),status=card.querySelector(".preview-status"),retry=card.querySelector(".preview-retry");
 if(status)status.textContent="Loading preview…";
 if(retry)retry.hidden=true;
 let missing=false,retryBusy=false,ok=false,url=null;
 try{
  const base=img.dataset.previewUrl;
  const target=cacheOnly?base+(base.includes("?")?"&":"?")+"cache_only=1":base;
  const {response,data}=await reviewRequest(target,{signal:ctl.signal,timeoutMs:cacheOnly?15000:120000},"blob");
  if(REVIEW_MEDIA!==state||!img.isConnected)return;
  if(cacheOnly&&response.status===204){missing=true;return;}
  const raw=response.headers.get("X-Plate-Geometry"),meta=raw?JSON.parse(raw):null;
  // Decode a replacement off-DOM first. A failed/aborted refresh must leave
  // the usable old image in place rather than turn the finding blank.
  url=URL.createObjectURL(data);state.urls.add(url);
  const candidate=new Image();candidate.src=url;await candidate.decode();
  if(REVIEW_MEDIA!==state||!img.isConnected)return;
  const previous=img.src;
  img.src=url;img._plateMeta=meta;await img.decode();
  if(state.urls.delete(previous))URL.revokeObjectURL(previous);
  url=null;
  if(REVIEW_MEDIA!==state||!img.isConnected)return;
  drawPlateThumbnail(img);
  if(meta?.classification_allowed===false){
   if(typeof FINDING_META!=="undefined"&&FINDING_META[meta.i]){
    FINDING_META[meta.i].classification_allowed=false;
    FINDING_META[meta.i].classification_note=meta.classification_note;
   }
   card.querySelectorAll('.finding-confirm button').forEach(button=>button.disabled=true);
   const note=card.querySelector('[id^="vlabel"]');if(note)note.textContent=meta.classification_note;
  }
  if(status)status.textContent="";
  ok=true;img._previewLoaded=true;
 }catch(error){
  if(REVIEW_MEDIA===state&&img.isConnected){
   if(error.status===503&&(task.busyRetries||0)<2){
    task.busyRetries=(task.busyRetries||0)+1;
    task.readyAt=Date.now()+250*2**task.busyRetries;retryBusy=true;
    if(status)status.textContent="Decoder busy — retrying preview…";
    return;
   }
   if(status)status.textContent=error.name==="AbortError"
    ?"Preview timed out. Retry when ready.":"Preview unavailable: "+error.message;
   if(retry){retry.hidden=false;retry.textContent="Retry preview";}
  }
 }finally{
  if(url){state.urls.delete(url);URL.revokeObjectURL(url);}
  state[counter]--;state.controllers.delete(ctl);
  if(missing&&cacheOnly&&!task.priority&&REVIEW_MEDIA===state&&img.isConnected){
   // Opening Review must never start source-video decoding just because a
   // compact scan-time picture is missing. Keep the card interactive and let
   // the person opt into the expensive path for the few findings they need.
   if(status)status.textContent="Preview not cached — load only if needed.";
   if(retry){retry.hidden=false;retry.textContent="Load preview";}
   img._previewTask=null;task.resolve(false);
  }else if((missing||retryBusy)&&REVIEW_MEDIA===state&&img.isConnected){
   if(missing&&status)status.textContent="Loading source preview…";
   const queue=retryBusy&&cacheOnly?state.cacheQueue:state.queue;
   if(task.priority)queue.unshift(task);else queue.push(task);
  }else{img._previewTask=null;task.resolve(ok);}
  pumpReviewPreviews(state);
 }
}
function reviewPreviewRank(task){
 if(!task.img.isConnected||task.img.closest?.("[hidden]"))return Infinity;
 if(task.priority)return -1;  // an explicit Retry must not be silently dropped
 // Old non-layout harnesses / browsers without geometry retain FIFO behavior.
 if(!task.img.getBoundingClientRect)return 0;
 const r=task.img.getBoundingClientRect(),h=window.innerHeight||document.documentElement.clientHeight;
 const distance=r.bottom<0?-r.bottom:r.top>h?r.top-h:0;
 return distance>240?Infinity:distance;
}
function pumpReviewPreviews(state){
 if(REVIEW_MEDIA!==state)return;
 if(state.retryTimer){clearTimeout(state.retryTimer);state.retryTimer=null;}
 let wake=Infinity;
 // Cache hits overtake cold decoding. Re-rank at dispatch, not when the card
 // first entered view: scrolling must not leave minutes of obsolete work.
 for(const [queue,counter,limit,cached] of [
  [state.cacheQueue,"cacheActive",3,true],[state.queue,"active",1,false]]){
  const ranked=queue.splice(0).map(task=>({task,rank:reviewPreviewRank(task)}));
  ranked.sort((a,b)=>a.rank-b.rank);
  for(const {task,rank} of ranked){
   if(rank===Infinity){task.img._previewTask=null;task.resolve(false);}
   else queue.push(task);
  }
  while(state[counter]<limit&&queue.length){
   const n=queue.findIndex(task=>!task.readyAt||task.readyAt<=Date.now());
   if(n<0)break;
   loadReviewPreview(state,queue.splice(n,1)[0],cached);
  }
  for(const task of queue)if(task.readyAt>Date.now())wake=Math.min(wake,task.readyAt);
 }
 if(Number.isFinite(wake))state.retryTimer=setTimeout(()=>pumpReviewPreviews(state),Math.max(1,wake-Date.now()));
}
function initReviewPreviews(){
 clearReviewPreviews();
 const state=REVIEW_MEDIA={queue:[],cacheQueue:[],active:0,cacheActive:0,retryTimer:null,
  controllers:new Set(),urls:new Set(),observer:null};
 const images=document.querySelectorAll("#review img[data-preview-url]");
 if(typeof IntersectionObserver!=="undefined"){
  state.observer=new IntersectionObserver(entries=>{
   for(const e of entries)if(e.isIntersecting)queueReviewPreview(e.target);
   // Keep observing: skipped queued work is requested again on re-entry.
   pumpReviewPreviews(state);
  },{rootMargin:"240px"});images.forEach(img=>state.observer.observe(img));
 }else images.forEach(img=>queueReviewPreview(img));
}
function retryReviewPreview(button){
 const img=button.closest(".det").querySelector("img[data-preview-url]");
 if(img){
  button.disabled=true;button.textContent="Loading preview…";
  img._plateMeta=null;
  queueReviewPreview(img,true).finally(()=>{if(button.isConnected)button.disabled=false;});
 }
}

let QEDIT=null;
let CONFIRM_CHAIN=Promise.resolve();
const CONFIRM_PENDING=new Set(),CONFIRM_FAILED=new Map();
const PLATE_EDITS=new Map();
let PLATE_SAVE=null,PLATE_TIMER=null,PLATE_SERIAL=0,PLATE_REVIEW_BUSY=false;
const plateCopy=points=>points.map(p=>p.slice());
const plateSame=(a,b)=>a.length===b.length&&a.every((p,k)=>p.every((v,j)=>Math.abs(v-b[k][j])<1e-5));
function plateQuadValid(points){
 if(points.length!==4||points.some(p=>p.length!==2||p.some(v=>!Number.isFinite(v))))return false;
 const cross=points.map((a,k)=>{const b=points[(k+1)%4],c=points[(k+2)%4];
  return (b[0]-a[0])*(c[1]-b[1])-(b[1]-a[1])*(c[0]-b[0]);});
 const area=Math.abs(points.reduce((n,p,k)=>{const q=points[(k+1)%4];return n+p[0]*q[1]-q[0]*p[1];},0))/2;
 return area>=8&&(cross.every(v=>v>0)||cross.every(v=>v<0));
}
function plateEditsPending(){return [...PLATE_EDITS.values()].some(s=>s.dirty||s.pending||s.drag);}
let REVIEW_VERSION=0,REVIEW_SAVED=0;
function reviewChoicesPending(){return REVIEW_VERSION!==REVIEW_SAVED||CONFIRM_PENDING.size>0||CONFIRM_FAILED.size>0;}
function reviewSaveStatus(text,failed=false){
 document.querySelectorAll(".review-save-status").forEach(el=>{
  el.textContent=text;el.setAttribute("role",failed?"alert":"status");
  el.style.color=failed?"#fbbf24":"#94a3b8";
 });
}
function markReviewChanged(){
 REVIEW_VERSION++;reviewSaveStatus("Review choices not saved.");plateUnloadGuard();
}
function plateUnloadWarning(e){
 if(plateEditsPending()||reviewChoicesPending()){e.preventDefault();e.returnValue="";}
}
function plateUnloadGuard(){
 window.removeEventListener("beforeunload",plateUnloadWarning);
 if(plateEditsPending()||reviewChoicesPending())window.addEventListener("beforeunload",plateUnloadWarning);
}
function showUnsavedPlate(i){
 const s=PLATE_EDITS.get(i);if(!s||s.job!==CUR)return;
 // Reveal through the normal local filter; never reload/discard an editor.
 if(typeof reviewAllFindings==="function")reviewAllFindings();
 const card=s.card||document.getElementById("det"+i);if(!card)return;
 for(let el=card;el&&el.id!=="review";el=el.parentElement){
  el.hidden=false;if(el.tagName==="DETAILS")el.open=true;
 }
 card.scrollIntoView({block:"center"});s.draw();
 if(s.cv)s.cv.focus({preventScroll:true});
}
function updatePlateSaveIssues(){
 const panel=document.getElementById("plateSaveIssues");if(!panel)return;
 const issues=[...PLATE_EDITS.values()].filter(s=>s.job===CUR&&s.dirty&&s.error);
 panel.replaceChildren();panel.hidden=!issues.length;
 if(!issues.length)return;
 const title=document.createElement("strong");
 title.textContent=issues.length+" unsaved corner adjustment"+(issues.length===1?"":"s")+". Your drafts are kept.";
 panel.appendChild(title);
 for(const s of issues){
  const row=document.createElement("div");row.className="row";
  const button=document.createElement("button");button.type="button";button.className="sec";
  button.textContent="Show finding #"+s.i;button.onclick=()=>showUnsavedPlate(s.i);
  const note=document.createElement("span");
  note.textContent="Source frame "+s.meta.frame+" — "+s.error.message;
  row.append(button,note);panel.appendChild(row);
 }
}
function plateStatus(s,text,retry=false){
 s.status.textContent=text;s.retry.hidden=!retry;
 s.retry.textContent=s.archiveConflict?"Discard this unsaved adjustment":s.conflict?"Reload preview":"Retry save";
 if(s.card)s.card.classList.toggle("corner-save-error",!!(s.dirty&&s.error));
 updatePlateSaveIssues();
}
function schedulePlateSaves(){
 clearTimeout(PLATE_TIMER);PLATE_TIMER=null;plateUnloadGuard();
 if(PLATE_SAVE)return;
 const pending=[...PLATE_EDITS.values()].filter(s=>s.dirty&&!s.drag&&!s.error);
 if(pending.length)PLATE_TIMER=setTimeout(pumpPlateSaves,
  Math.max(0,Math.min(...pending.map(s=>s.readyAt))-Date.now()));
}
function commitPlateGesture(s,before){
 if(plateSame(s.points,before))return;
 if(!plateQuadValid(s.points)){
  s.points=before;s.draw();plateStatus(s,"Corners cannot cross; adjustment reverted.");return;
 }
 s.undo=before;s.version++;s.dirty=true;s.failures=0;
 if(s.archiveConflict){
  plateStatus(s,"Saved example changed · choose Is / Not to confirm this adjustment.",true);return;
 }
 s.error=null;s.conflict=false;
 s.readyAt=Date.now()+450;
 plateStatus(s,"Saving…");schedulePlateSaves();
}
function syncPlateTrack(s){
 if(s.meta.track<0)return;
 const b=s.meta.box,q=s.meta.points.map(([x,y])=>[(x-b[0])/(b[2]-b[0]),(y-b[1])/(b[3]-b[1])]);
 for(const other of PLATE_EDITS.values()){
  if(other===s||other.job!==s.job||other.meta.track!==s.meta.track)continue;
  other.refreshBeforeSave=true;
  // Keep an unsubmitted human adjustment; only refresh untouched siblings.
  if(!other.dirty&&!other.drag&&!other.pending){
   const box=other.meta.box;
   other.saved=q.map(([x,y])=>[box[0]+x*(box[2]-box[0]),box[1]+y*(box[3]-box[1])]);
   other.points=plateCopy(other.saved);other.draw();
  }
 }
}
function discardRejectedCorners(i){
 const s=PLATE_EDITS.get(i);if(!s)return;
 if(s.cancelDrag)s.cancelDrag();
 // The explicit rejection supersedes this track's uncommitted geometry.
 // A running request may complete, but its old response must not restore it.
 s.pending=null;s.version++;s.dirty=false;s.error=null;s.conflict=false;s.archiveConflict=false;
 s.points=plateCopy(s.saved);s.draw();plateStatus(s,"Not a plate");
 schedulePlateSaves();
}
function pumpPlateSaves(){
 if(PLATE_SAVE)return PLATE_SAVE;
 const s=[...PLATE_EDITS.values()].find(s=>s.dirty&&!s.drag&&!s.error&&s.readyAt<=Date.now());
 if(!s){schedulePlateSaves();return Promise.resolve();}
 let pending=s.pending;
 plateStatus(s,"Saving…");
 PLATE_SAVE=(async()=>{
  try{
   if(!pending&&s.refreshBeforeSave){
    const {data}=await reviewRequest("api/jobs/"+s.job+"/plate_quad/"+s.i+(s.meta.compact?"?compact=1":""));
    if(!s.meta.source_token||data.source_token!==s.meta.source_token)
     throw Object.assign(new Error("Source frame or detection changed. Reload this preview."),{status:409});
    s.meta.preview_token=data.preview_token;s.refreshBeforeSave=false;
   }
   if(!s.dirty||s.drag)return; // Rejected, or a new gesture began during metadata loading.
   if(!pending){
    // Keep a request/ID only after an uncertain result, not a definite 503.
    pending=s.pending={points:plateCopy(s.points),preview_token:s.meta.preview_token,compact:!!s.meta.compact,
     apply_track:true,autosave:true,edit_id:Date.now().toString(36)+"-"+(++PLATE_SERIAL)+"-"+Math.random().toString(36).slice(2),
     version:s.version,label:VLBL[s.i]};
   }
   const {data}=await reviewRequest("api/jobs/"+s.job+"/plate_quad/"+s.i,{method:"POST",
    headers:{"Content-Type":"application/json"},body:JSON.stringify(pending)});
   Object.assign(s.meta,data.preview);s.img._plateMeta=s.meta;
   // The corner endpoint commits its own explicit label. Reflect that disk
   // state even if a newer Blur/Keep/Not-a-plate choice superseded the gesture,
   // so the next sparse choice save can clear or replace it correctly.
   if(typeof REVIEW_BASE!=="undefined"&&REVIEW_BASE&&REVIEW_BASE.job===s.job&&data.applied>0)
    REVIEW_BASE.labels[s.i]=s.meta.compact?(data.verified_label||""):"plate";
   if(data.finding&&typeof FINDING_META!=="undefined"&&FINDING_META[s.i])
    FINDING_META[s.i].confirmed_finding_revision=data.finding.revision;
   s.saved=plateCopy(s.meta.points);s.failures=0;
   if(typeof FINDING_META!=="undefined"&&FINDING_META[s.i])
    FINDING_META[s.i].human_region_confirmed=true;
   if(typeof REVIEW_DISPLAY_META!=="undefined"&&REVIEW_DISPLAY_META[s.i])
    REVIEW_DISPLAY_META[s.i].human_region_confirmed=true;
   syncPlateTrack(s);
   if(s.pending!==pending)return; // A newer Not-a-plate decision wins.
   s.pending=null;
   if(s.version===pending.version&&!s.drag)s.points=plateCopy(s.saved);
   s.dirty=s.version!==pending.version;
   if(VLBL[s.i]===pending.label&&VLBL[s.i]!=="not_plate"&&(!s.meta.compact||data.verified_label)){
    VLBL[s.i]=s.meta.compact?data.verified_label:"plate";const label=document.getElementById("vlabel"+s.i);
    if(label)label.textContent=VLBL[s.i]==="plate"?"Confirmed plate":"Not a plate";
   }
   s.draw();plateStatus(s,s.dirty?"Saving…":data.classification_required?"Saved area · choose Is / Not to confirm":s.meta.track>=0?"Saved to track":"Saved");
   if(!s.dirty&&CUR===s.job&&document.getElementById("beCv"))beRefresh();
  }catch(error){
   if(!s.dirty||(pending&&s.pending!==pending))return;
   if(error.status===409&&error.details?.current_archive){
    rememberFindingConflict(s.i,error.details.current_archive);
    s.pending=null;s.error=error;s.conflict=false;s.archiveConflict=true;
    showFindingFailure(s.i,error);
    s.draw();plateStatus(s,"Saved example changed · choose Is / Not to confirm this adjustment.",true);return;
   }
   // 400 is validation BEFORE any write in this endpoint. Never keep its
   // rejected coordinates as an idempotent retry. Timeouts/5xx are ambiguous
   // and MUST retain the original ID/payload until acknowledged.
   if(error.status===400){
    s.pending=null;
    if(pending&&s.version!==pending.version){
     s.error=null;s.conflict=false;s.readyAt=0;
     plateStatus(s,"Saving corrected corners…");return;
    }
   }
   if(error.status===503&&++s.failures<=3){
    s.pending=null; // Server explicitly refused this write before applying it.
    s.readyAt=Date.now()+1000*2**s.failures;plateStatus(s,"Waiting to save…");
   }else{
    s.error=error;s.conflict=error.status===409;
    s.draw();plateStatus(s,"Not saved — "+error.message,true);
   }
  }finally{PLATE_SAVE=null;schedulePlateSaves();}
 })();
 return PLATE_SAVE;
}
async function flushPlateSaves(){
 if([...PLATE_EDITS.values()].some(s=>s.drag))return false;
 for(const s of PLATE_EDITS.values())if(s.dirty&&!s.error)s.readyAt=0;
 while([...PLATE_EDITS.values()].some(s=>s.dirty&&!s.error)||PLATE_SAVE){
  await (PLATE_SAVE||pumpPlateSaves());
  if([...PLATE_EDITS.values()].some(s=>s.dirty&&!s.error))
   await new Promise(resolve=>setTimeout(resolve,100));
 }
 const failed=[...PLATE_EDITS.values()].find(s=>s.dirty||s.pending||s.drag);
 if(failed){showUnsavedPlate(failed.i);return false;}
 return true;
}
async function retryPlateSave(s){
 if(s.archiveConflict){dismissFindingConfirmation(s.i);return;}
 if(s.conflict){
  if(!confirm("Reload this finding and discard its unsaved corner adjustment?"))return;
  s.events.abort();if(s.observer)s.observer.disconnect();
  PLATE_EDITS.delete(s.i);delete s.img._quadEdit;s.img._plateMeta=null;
  if(QEDIT===s)QEDIT=null;schedulePlateSaves();
  await queueReviewPreview(s.img,true);return;
 }
 if(s.error?.status===400)s.pending=null;
 s.error=null;s.failures=0;s.readyAt=0;
 plateStatus(s,"Saving…");schedulePlateSaves();
}
function closePlateQuad(){
 if(plateEditsPending())return false;
 clearTimeout(PLATE_TIMER);PLATE_TIMER=null;
 for(const s of PLATE_EDITS.values()){
  s.events.abort();if(s.observer)s.observer.disconnect();delete s.img._quadEdit;
 }
 PLATE_EDITS.clear();QEDIT=null;updatePlateSaveIssues();plateUnloadGuard();return true;
}
function initPlateCorners(img){
 const meta=img._plateMeta,card=img.closest(".det"),stage=img.closest(".plate-preview");
 if(!meta||!stage)return null;
 if(img._quadEdit)return img._quadEdit;
 const cv=stage.querySelector("canvas"),status=card.querySelector(".quad-status"),retry=card.querySelector(".quad-retry");
 const s={i:meta.i,job:CUR,img,cv,meta,displayCrop:meta.crop.slice(),card,status,retry,points:plateCopy(meta.points),
  saved:plateCopy(meta.points),version:0,dirty:false,pending:null,drag:null,error:null,
  failures:0,readyAt:0,selected:0,events:new AbortController()};
 img._quadEdit=s;PLATE_EDITS.set(s.i,s);const options={signal:s.events.signal};
 cv.style.pointerEvents="auto";cv.tabIndex=0;
 cv.setAttribute("aria-label","Plate corners: drag a numbered handle. Keyboard: 1–4 selects a corner, arrows adjust, Ctrl+Z undoes. Autosaves to this track.");
 retry.onclick=()=>retryPlateSave(s);
 s.draw=()=>{
  const r=img.getBoundingClientRect(),c=s.displayCrop;
  if(r.width<1||r.height<1)return;
  cv.width=Math.max(1,Math.round(r.width));cv.height=Math.max(1,Math.round(r.height));
  const x=cv.getContext("2d"),sx=cv.width/(c[2]-c[0]),sy=cv.height/(c[3]-c[1]);
  const state=reviewOverlayState(s.i),valid=plateQuadValid(s.points);
  x.clearRect(0,0,cv.width,cv.height);x.beginPath();
  s.points.forEach((p,k)=>{const px=(p[0]-c[0])*sx,py=(p[1]-c[1])*sy;
   if(k)x.lineTo(px,py);else x.moveTo(px,py);});
  x.closePath();
  x.fillStyle=state.enabled?REVIEW_OVERLAY_COLORS.hiddenFill:REVIEW_OVERLAY_COLORS.visibleFill;
  x.strokeStyle=valid?(state.enabled?REVIEW_OVERLAY_COLORS.hidden:REVIEW_OVERLAY_COLORS.visible):REVIEW_OVERLAY_COLORS.invalid;
  x.lineWidth=2;x.setLineDash(!state.enabled&&state.machineFiltered?[7,4]:[]);
  x.fill();x.stroke();x.setLineDash([]);
  const b=s.meta.box,bx1=(b[0]-c[0])*sx,by1=(b[1]-c[1])*sy,
        bx2=(b[2]-c[0])*sx,by2=(b[3]-c[1])*sy;
  x.strokeStyle=REVIEW_OVERLAY_COLORS.proposal;x.lineWidth=1.5;x.setLineDash([6,4]);
  x.strokeRect(bx1,by1,bx2-bx1,by2-by1);x.setLineDash([]);
  if(state.machineSuggestion&&state.enabled){
   x.strokeStyle=REVIEW_OVERLAY_COLORS.visible;x.lineWidth=1.5;x.setLineDash([5,4]);
   const inset=3;x.strokeRect(bx1+inset,by1+inset,Math.max(0,bx2-bx1-2*inset),Math.max(0,by2-by1-2*inset));
   x.setLineDash([]);
  }
  s.points.forEach((p,k)=>{const px=(p[0]-c[0])*sx,py=(p[1]-c[1])*sy;
   const hx=Math.max(9,Math.min(cv.width-9,px)),hy=Math.max(9,Math.min(cv.height-9,py));
   const outside=p[0]<0||p[0]>s.meta.width||p[1]<0||p[1]>s.meta.height;
   const rejected=(s.error?.details?.invalid_corners||[]).includes(k+1);
   x.strokeStyle=outside||rejected?REVIEW_OVERLAY_COLORS.invalid:REVIEW_OVERLAY_COLORS.edit;
   if(hx!==px||hy!==py){x.beginPath();x.moveTo(px,py);x.lineTo(hx,hy);x.stroke();}
   x.beginPath();x.arc(hx,hy,8,0,Math.PI*2);x.fillStyle="#0f172a";x.fill();x.lineWidth=2;x.stroke();
   x.fillStyle="#fff";x.font="bold 10px sans-serif";x.textAlign="center";x.fillText(String(k+1),hx,hy+3);
  });
  updateReviewOverlayLabel(s.i);
 };
 function point(e){const r=cv.getBoundingClientRect(),c=s.displayCrop,o=s.drag?.offset||[0,0];
  return [Math.max(c[0],Math.min(c[2],c[0]+(e.clientX-r.left)/r.width*(c[2]-c[0])-o[0])),
          Math.max(c[1],Math.min(c[3],c[1]+(e.clientY-r.top)/r.height*(c[3]-c[1])-o[1]))];}
 function nearest(e){const r=cv.getBoundingClientRect(),c=s.displayCrop;
  let index=-1,best=e.pointerType==="touch"?26:18;
  s.points.forEach((v,k)=>{
   const x=Math.max(9,Math.min(r.width-9,(v[0]-c[0])*r.width/(c[2]-c[0])));
   const y=Math.max(9,Math.min(r.height-9,(v[1]-c[1])*r.height/(c[3]-c[1])));
   const distance=Math.hypot(x-(e.clientX-r.left),y-(e.clientY-r.top));
   if(distance<best){index=k;best=distance;}});return index;}
 function finish(e,cancel=false){
  if(!s.drag||(e&&e.pointerId!==s.drag.id))return;
  const drag=s.drag;s.drag=null;
  if(cancel)s.points=drag.before;else commitPlateGesture(s,drag.before);
  if(cv.hasPointerCapture(drag.id))cv.releasePointerCapture(drag.id);
  s.draw();schedulePlateSaves();
 }
 s.cancelDrag=()=>finish(null,true);
 cv.addEventListener("pointerdown",e=>{
  e.stopPropagation();if(e.button!==0||s.drag||PLATE_REVIEW_BUSY||CONFIRM_PENDING.has(s.i))return;
  const k=nearest(e);if(k<0)return;
  e.preventDefault();QEDIT=s;s.selected=k;
  const at=point(e),p=s.points[k],c=s.displayCrop;
  // The visible handle is inset at a crop edge. Preserve the true vertex
  // offset so grabbing it does not jump/shrink a valid boundary mask.
  const inside=p[0]>=c[0]&&p[0]<=c[2]&&p[1]>=c[1]&&p[1]<=c[3];
  s.drag={id:e.pointerId,before:plateCopy(s.points),offset:inside?[at[0]-p[0],at[1]-p[1]]:[0,0]};
  cv.focus({preventScroll:true});cv.setPointerCapture(e.pointerId);plateUnloadGuard();
 },options);
 cv.addEventListener("pointermove",e=>{
  if(!s.drag){cv.style.cursor=nearest(e)>=0?"grab":"default";return;}
  if(e.pointerId!==s.drag.id)return;
  e.preventDefault();e.stopPropagation();s.points[s.selected]=point(e);cv.style.cursor="grabbing";s.draw();
 },options);
 cv.addEventListener("pointerup",e=>finish(e),options);
 cv.addEventListener("pointercancel",e=>finish(e,true),options);
 cv.addEventListener("lostpointercapture",e=>finish(e,true),options);
 cv.addEventListener("click",e=>e.stopPropagation(),options);
 cv.addEventListener("keydown",e=>{
  QEDIT=s;
  if(e.key==="Escape"){s.cancelDrag();return;}
  if(s.drag||PLATE_REVIEW_BUSY||CONFIRM_PENDING.has(s.i))return;
  if(/^[1-4]$/.test(e.key)){s.selected=Number(e.key)-1;e.preventDefault();return;}
  const before=plateCopy(s.points),c=s.displayCrop;
  if((e.ctrlKey||e.metaKey)&&e.key.toLowerCase()==="z"&&s.undo){s.points=plateCopy(s.undo);}
  else{
   const delta={ArrowLeft:[-1,0],ArrowRight:[1,0],ArrowUp:[0,-1],ArrowDown:[0,1]}[e.key];
   if(!delta)return;
   const p=s.points[s.selected],step=e.shiftKey?10:1;
   s.points[s.selected]=[Math.max(c[0],Math.min(c[2],p[0]+delta[0]*step)),
                         Math.max(c[1],Math.min(c[3],p[1]+delta[1]*step))];
  }
  e.preventDefault();commitPlateGesture(s,before);s.draw();
 },options);
 s.observer=typeof ResizeObserver!=="undefined"?new ResizeObserver(s.draw):null;
 if(s.observer)s.observer.observe(img);
 plateStatus(s,"Drag corners · autosaves");s.draw();updateReviewOverlayLabel(s.i);return s;
}
document.addEventListener("visibilitychange",()=>{
 if(document.hidden){for(const s of PLATE_EDITS.values())if(s.dirty&&!s.error)s.readyAt=0;pumpPlateSaves();}
});
async function zoomDet(i){
 const el=document.getElementById("det"+i);if(el&&el.dataset.cat==="plate")return;
 let ov=document.getElementById("lb");
 if(!ov){ov=document.createElement("div");ov.id="lb";document.body.appendChild(ov);}
 ov.style.cssText="position:fixed;inset:0;background:rgba(0,0,0,.82);z-index:100;display:flex;align-items:center;justify-content:center;cursor:zoom-out;padding:18px";
 ov.onclick=()=>ov.remove();
 const original=document.getElementById("thumb"+i);
 const picture=document.createElement("img");picture.src=original?.src||('api/jobs/'+CUR+'/finding-preview/'+i);
 picture.style.cssText="max-width:96%;max-height:96%;border-radius:8px";ov.replaceChildren(picture);
}
function beRemove(){
 if(BE.sel<0)return;
 applyDet(BE.sel,false);   // syncs thumbnail + refilters editor
 BE.sel=-1;
 document.getElementById("beRm").style.display="none";
 document.getElementById("beTimes").style.display="none";
}
async function beSave(){
 const ok=await saveAndRender(SHELLPH==="paused");
 if(!ok)return;
 const c=document.querySelector("#beslot");
 if(c)c.innerHTML=SHELLPH==="paused"
   ?"Review edits saved; resume when ready.":"rendering with your edits…";
}
async function stopReview(){
 const btn=document.getElementById("stopReviewBtn");
 if(btn)btn.disabled=true;
 const response=await fetch("api/jobs/"+CUR+"/stop",{method:"POST"});
 if(!response.ok){
  if(btn)btn.disabled=false;
  alert("Stop request failed");return;
 }
 if(btn)btn.textContent="Finishing scan & preparing Review…";
}
async function resumeJob(){
 if(document.getElementById("review")){
  const saved=await saveAndRender(true);
  if(!saved)return;
 }
 const response=await fetch("api/jobs/"+CUR+"/resume",{method:"POST"});
 if(!response.ok){
  let data={};try{data=await response.json();}catch(_){}
  alert(data.error||"Unable to resume scan");return;
 }
 closePlateQuad();clearReviewPreviews();
 const rv=document.getElementById("review");if(rv)rv.remove();
 SHELLPH=null;await refresh();
}
async function cancelJob(){await fetch("api/jobs/"+CUR+"/cancel",{method:"POST"})}

// the three post-render views (compare, review, box editor) are mutually
// exclusive: opening one closes the others instead of stacking them
async function showPanel(which){
 if(which!=="boxedit_rev"&&which!=="review"){
  if(!await flushPlateSaves()||!closePlateQuad())return false;clearReviewPreviews();
 }
 // a playing box-editor video must be PAUSED before its DOM is wiped —
 // an element removed via innerHTML can keep its audio running
 try{const v=document.getElementById("beVid");
  if(v&&!v.paused){BE.playing=false;v.pause();}}catch(e){}
 // "boxedit_rev" = the editor button INSIDE the review card: the editor
 // mounts in the review's own slot, so the review stays. Everything else
 // is standalone and closes the other panels.
 if(which!=="compare"){
  const c=document.getElementById("compare");if(c)c.innerHTML="";}
 const b=document.getElementById("beslot_done");
 const b2=document.getElementById("beslot");
 if(which==="boxedit_rev"){if(b)b.innerHTML=""}
 else{
  if(which!=="boxedit"){if(b)b.innerHTML=""}
  if(b2)b2.innerHTML="";
  if(which!=="review"){
   const rev=document.getElementById("review");if(rev)rev.remove();}
 }
 return true;
}

async function loadCompare(){
 if(!await showPanel("compare"))return;
 const d=await (await fetch(`api/jobs/${CUR}/detections`)).json();
 const c=document.getElementById("compare");
 c.innerHTML=`<div class="row" style="margin-top:8px">t=
  <input type="range" id="cmpT" min="0" max="${d.duration.toFixed(1)}" step="0.2"
   value="0" style="flex:1" oninput="cmpShow()">
  <span id="cmpLbl">0s</span></div>
  <div class="grid2"><div><b>Original</b><br><img id="cmpO" style="max-width:100%"></div>
  <div><b>Redacted</b><br><img id="cmpR" style="max-width:100%"></div></div>`;
 cmpShow();
}
function cmpShow(){
 const t=document.getElementById("cmpT").value;
 document.getElementById("cmpLbl").textContent=t+"s";
 document.getElementById("cmpO").src=`api/jobs/${CUR}/frame_at?t=${t}`;
 document.getElementById("cmpR").src=`api/jobs/${CUR}/frame_at?t=${t}&src=output`;
}

const plateFallbackLabels={
 model_unavailable:"localizer unavailable", inference_error:"localizer error",
 invalid_crop:"plate crop unclear", no_text_detected:"lettering not found",
 invalid_geometry:"uncertain lettering shape", ambiguous_text:"possible occlusion",
 residual_text_evidence:"possible missed lettering", unverifiable_contrast:"uncertain contrast",
 interpolated_sample:"missing sample",known_text_candidate:"number match awaiting review"
};
function plateFallbackText(x){
 const reasons=(x.fallbacks||[x.fallback_reason]).filter(Boolean);
 if(!reasons.length)return "";
 const prefix=x.fallbackCount && x.fallbackCount<x.frames ? "Some frames use full plate" : "Full plate fallback";
 const labels=[...new Set(reasons.map(r=>plateFallbackLabels[r]||"uncertain lettering"))];
 return prefix+": "+labels.join(", ");
}
let LEARNING_SELECTION=null,LEARNING_SELECTION_JOB=null,LEARNING_TERMS=false;
function sampleReviewGroups(rows,fraction=.1,labels={}){
 // Same grouping/quota as video_learning.review_sample_details. Work from
 // already loaded metadata and current draft labels, never save to filter.
 if(!Number.isFinite(fraction)||fraction<=0||fraction>1)throw new Error("Review fraction must be in (0, 1]");
 const groups=new Map();
 for(const row of rows){
  const label=Object.prototype.hasOwnProperty.call(labels,row.i)?labels[row.i]:row.verified_label;
  if(row.category!=="plate"||row.zone_dropped||(label&&label!=="clear"))continue;
  const person=row.person??-1,track=row.track??-1;
  const key=person>=0?"p"+person:track>=0?"t"+track:"r"+row.i;
  const t=Number(row.t_start||0),confidence=Number(row.confidence||0);
  const score=2*!!(row.learning_conflict||row.fallback_reason)+(1-Math.abs(confidence-.5)*2);
  const g=groups.get(key);
  if(!g)groups.set(key,{start:t,first:row.i,score,index:row.i});
  else{
   if(t<g.start||(t===g.start&&row.i<g.first)){g.start=t;g.first=row.i;}
   if(score>g.score||(score===g.score&&row.i<g.index)){g.score=score;g.index=row.i;}
  }
 }
 const ordered=[...groups.values()].sort((a,b)=>a.start-b.start||a.first-b.first);
 const budget=Math.ceil(ordered.length*fraction),indices=[];
 for(let slot=0;slot<budget;slot++){
  const start=Math.floor(slot*ordered.length/budget),end=Math.floor((slot+1)*ordered.length/budget);
  let best=ordered[start];
  for(let k=start+1;k<end;k++){
   const g=ordered[k];if(g.score>best.score||(g.score===best.score&&g.index<best.index))best=g;
  }
  indices.push(best.index);
 }
 return {indices,fraction,unit:"finding_group",eligible_groups:groups.size,selected_groups:indices.length};
}
function applyReviewGroupFilter(){
 const panel=document.getElementById("review");
 if(!panel||panel._sampleJob!==CUR||panel._sampleView!==JOBVIEW)return false;
 clearSel();
 const selected=LEARNING_SELECTION;
 let shown=0;
 panel.querySelectorAll(".det").forEach(card=>{
  const i=Number(card.id.slice(3));
  card.hidden=!!selected&&(card.dataset.cat!=="plate"||!(TRKMEM[i]||[i]).some(m=>selected.has(m)));
  if(!card.hidden)shown++;
 });
 panel.querySelectorAll("[data-review-category]").forEach(grid=>{
  const count=grid.querySelectorAll(".det:not([hidden])").length;
  grid.hidden=count===0;
  const heading=grid.previousElementSibling;heading.hidden=count===0;
  heading.querySelector(".badge").textContent=count;
 });
 const zones=panel.querySelector("#reviewZones");if(zones)zones.hidden=!!selected;
 const all=panel.querySelector("#reviewShowAll");if(all)all.hidden=!selected;
 const summary=panel.querySelector("#reviewSampleSummary");
 if(summary){
  summary.hidden=!selected;
  if(selected){
   const total=LEARNING_SAMPLE_INFO?.eligible_groups??selected.size;
   summary.textContent="Showing "+shown+" of "+total+" unreviewed plate groups (10%). "+
    "One representative image per group, not one per frame. Groups are spread across the video; "+
    "the most uncertain in each batch is selected. This only filters the view; unsaved edits are kept.";
  }
 }
 // Keep existing images/editors and autosaves alive. Drop hidden queued images
 // without aborting unrelated requests or decoding every preview again.
 if(REVIEW_MEDIA)pumpReviewPreviews(REVIEW_MEDIA);
 return true;
}
function reviewUncertain(){
 const panel=document.getElementById("review");
 if(!panel||panel._sampleJob!==CUR||panel._sampleView!==JOBVIEW||!panel._sampleRows){
  reviewSaveStatus("Open the review before selecting a sample.",true);return false;
 }
 if([...PLATE_EDITS.values()].some(s=>s.drag)){
  reviewSaveStatus("Finish dragging the corner before changing the view.",true);return false;
 }
 const data=sampleReviewGroups(panel._sampleRows,.1,VLBL);
 LEARNING_SELECTION=new Set(data.indices);LEARNING_SELECTION_JOB=CUR;LEARNING_SAMPLE_INFO=data;
 return applyReviewGroupFilter();
}
function reviewAllFindings(){
 LEARNING_SELECTION=null;
 return applyReviewGroupFilter();
}
async function rollbackLearning(){
 if(!await saveAndRender(true))return;
 if(!confirm("Restore the previous pass? Your saved training examples and model versions will be kept."))return;
 try{
  await reviewRequest(`api/jobs/${CUR}/learning/rollback`,{method:"POST"});
  LEARNING_SELECTION=null;VLBL={};VLBLJOB=null;await loadReview();await refresh();
 }catch(error){alert(error.message);}
}
async function trainAndRescan(){
 if(!await saveAndRender(true))return;
 if(!LEARNING_TERMS){
  if(!confirm("Train locally from your reviewed examples and rescan this video from the beginning? The training environment uses Ultralytics; review its AGPL/Enterprise terms in docs/PLATE_TRAINING.md. Previous review is retained if training or validation fails."))return;
  LEARNING_TERMS=true;
 }
 try{
  await reviewRequest(`api/jobs/${CUR}/learning`,{method:"POST",headers:{"Content-Type":"application/json"},
    body:JSON.stringify({license_accepted:true,name:document.getElementById("trainingRunName")?.value.trim()||""})});
  LEARNING_SELECTION=null;clearReviewPreviews();
  const panel=document.getElementById("review");if(panel)panel.remove();
  await refresh();
 }catch(error){alert(error.message);}
}
async function searchKnownPlateText(){
 const job=CUR,view=JOBVIEW,plate_texts=document.getElementById('knownPlateTexts')?.value||'';
 const max_frames=Number(document.getElementById('plateTextSamples')?.value||120);
 const note=document.getElementById('plateTextStatus'),button=document.getElementById('plateTextSearchButton');
 if(button)button.disabled=true;
 if(note)note.textContent='Saving review edits before starting local OCR search…';
 try{
  if(!await saveAndRender(true)){
   if(CUR===job&&JOBVIEW===view&&note)note.textContent='Search not started because review edits were not saved.';
   return;
  }
  if(CUR!==job||JOBVIEW!==view)return;
  if(note)note.textContent='Starting local OCR search…';
  await reviewRequest('api/jobs/'+job+'/plate-text-search',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({plate_texts,max_frames})});
  if(CUR!==job||JOBVIEW!==view)return;
  if(note)note.textContent='Local OCR search queued…';
  clearReviewPreviews();document.getElementById('review')?.remove();await refresh();
 }catch(error){if(note)note.textContent='Search could not start: '+error.message;}
 finally{if(button)button.disabled=false;}
}
function plateTextBadge(row){
 const evidence=row.plate_text_evidence;if(!evidence)return '';
 const kind=evidence.match_kind==='exact'?'Full number match':'Partial number match';
 return `<p class="review-copy"><b>${kind}</b> · OCR “${sectionEscape(evidence.observed_text||'')}” · target “${sectionEscape(evidence.matched_target||'')}”. Additional evidence; confirm the whole number region.</p>`;
}
let LEARNING_SAMPLE_INFO=null;
let VLBL={},VLBLJOB=null;  // explicit human labels; never infer from default blur state
let FINDING_META={},OUTPUT_CHOICES={},OUTPUT_VERSION={};
let REVIEW_DISPLAY_META={};
let REVIEW_BASE=null; // Only decision scalars, not a second detection report.
const REVIEW_OVERLAY_COLORS={
 proposal:"#f5c400",hidden:"#dc2626",hiddenFill:"rgba(220,38,38,.24)",
 visible:"#22c55e",visibleFill:"rgba(34,197,94,.08)",edit:"#38bdf8",invalid:"#f87171"
};
function reviewOverlayState(i,row=null){
 // A boxes_at row is authoritative for the standalone video editor. Live
 // Review maps override it only while they belong to this same current job.
 const liveReview=!row||(REVIEW_BASE?.job===CUR);
 const raw=row||FINDING_META[i]||{},display=row?{}:(REVIEW_DISPLAY_META[i]||{});
 const marker=raw.plate_verification||display.plate_verification||{};
 const draft=(liveReview&&Object.prototype.hasOwnProperty.call(VLBL,i)&&VLBL[i]!=="clear")?VLBL[i]:"";
 const verified=draft||raw.verified_label||display.verified_label||"";
 const confirmation=raw.human_confirmation?.label||display.human_confirmation?.label||"";
 const enabled=(liveReview&&Object.prototype.hasOwnProperty.call(EN,i))?!!EN[i]:(row?row.enabled!==false:raw.enabled!==false);
 const explicit=(liveReview&&!!OUTPUT_CHOICES[i])||!!raw.output_choice_explicit||!!display.output_choice_explicit;
 const humanNegative=confirmation==="negative"||verified==="not_plate";
 const humanPositive=confirmation==="positive"||verified==="plate";
 const humanRegion=!!(raw.human_region_confirmed||display.human_region_confirmed);
 const machineFiltered=marker.decision==="suppress"&&marker.applied===true&&!humanNegative&&!explicit;
 const machineSuggestion=marker.decision==="suggest_not_plate"&&!humanNegative&&!explicit;
 const conflict=raw.learning_conflict||display.learning_conflict||"";
 const fallback=raw.fallback_reason||display.fallback_reason||"";
 const shaped=!!(raw.shaped||display.shaped||row?.shaped);
 const learnedScore=raw.learning_score??display.learning_score;
 let source="Detector coverage";
 if(humanNegative)source="Human confirmed · not a plate";
 else if(humanRegion)source="Human corrected corners";
 else if(humanPositive)source="Human confirmed · plate";
 else if(explicit)source=enabled?"Human choice · hidden":"Human choice · visible";
 else if(machineFiltered)source="Learned model · filtered false positive";
 else if(machineSuggestion)source="Learned model · suggests false positive";
 else if(conflict)source="Fallback · detector box";
 else if(fallback)source="Fallback · full plate coverage";
 else if(Number.isFinite(learnedScore)&&shaped)source="Learned mask";
 else if(shaped)source="Shaped redaction";
 return {enabled,explicit,humanNegative,humanPositive,humanRegion,machineFiltered,
         machineSuggestion,conflict,fallback,shaped,source};
}
function reviewOverlayLegendHTML(){
 return `<div class="review-overlay-legend" role="note" aria-label="Plate review overlay legend">
  <span class="review-overlay-key"><span class="review-overlay-swatch proposal"></span>Detector proposal</span>
  <span class="review-overlay-key"><span class="review-overlay-swatch hidden"></span>Will be hidden</span>
  <span class="review-overlay-key"><span class="review-overlay-swatch visible"></span>Visible / false positive</span>
  <span class="review-overlay-key"><span class="review-overlay-swatch edit"></span>Edit corners</span>
  <span>Dashed green = learned-model judgement; solid green = human-visible decision.</span>
 </div>`;
}
function updateReviewOverlayLabel(i,row=null){
 const el=document.getElementById("plateOverlay"+i);if(!el)return;
 const state=reviewOverlayState(i,row);
 el.className="plate-output-badge "+(state.enabled?"hidden":"visible");
 el.innerHTML=`<strong>OUTPUT · ${state.enabled?"HIDDEN":"VISIBLE"}</strong><span>${sectionEscape(state.source)}</span>`;
}
function redrawReviewOverlay(i){
 const edit=typeof PLATE_EDITS!=="undefined"?PLATE_EDITS.get(i):null;
 if(edit)edit.draw();else updateReviewOverlayLabel(i);
}
function verifierAssessmentText(assessment){
 if(!assessment)return "Not evaluated yet. Check detections in review mode to assess this candidate without retraining.";
 return `${assessment.status==="validated"?"Filtering validated on held-out examples":"Review suggestions only"}: ${assessment.retained_positive}/${assessment.held_out_positive} plates retained, ${assessment.rejected_positive} rejected plates, ${assessment.rejected_negative}/${assessment.held_out_negative} negatives rejected. ${assessment.reason||""}`;
}
function updatePlateVerifierCandidate(){
 const panel=document.getElementById("review"),select=document.getElementById("plateVerifierCandidate");
 const mode=document.getElementById("plateVerifierMode"),note=document.getElementById("plateVerifierStatus");
 if(!panel||!select||!mode||!note)return;
 const candidate=(panel._learningCandidates||[]).find(c=>c.id===select.value);
 const validated=candidate?.assessment?.status==="validated";
 const filter=Array.from(mode.options).find(option=>option.value==="filter");
 if(filter)filter.disabled=!validated;
 if(!validated&&mode.value==="filter")mode.value="review";
 note.textContent=verifierAssessmentText(candidate?.assessment);
}
function plateVerificationBadge(row){
 const marker=row.plate_verification;if(!marker)return "";
 const label=marker.applied?"Model filtered":marker.decision==="suggest_not_plate"?"Model suggests false positive":"Model retained";
 const score=Number.isFinite(marker.score)?` · plate score ${Math.round(marker.score*100)}%`:"";
 return `<span class="badge plate-verification-badge" title="Secondary model decision; this is not a human label">${sectionEscape(label+" · "+(marker.mode||"review")+score)}</span> `;
}
async function checkPlateDetections(){
 const job=CUR,view=JOBVIEW;
 const candidate_id=document.getElementById("plateVerifierCandidate")?.value;
 const mode=document.getElementById("plateVerifierMode")?.value||"review";
 const note=document.getElementById("plateVerifierStatus"),button=document.getElementById("plateVerifierButton");
 if(!job||!candidate_id||!note||!button)return;
 button.disabled=true;note.textContent="Saving review edits before checking detections...";
 try{
  if(!await saveAndRender(true)){
   if(CUR===job&&JOBVIEW===view)note.textContent="Save the pending review edits before checking detections.";
   return;
  }
  if(CUR!==job||JOBVIEW!==view)return;
  await reviewRequest("api/jobs/"+encodeURIComponent(job)+"/plate-verifier",{
   method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify({candidate_id,mode}),timeoutMs:120000});
  if(CUR!==job||JOBVIEW!==view)return;
  await openJob(job);
 }catch(error){if(CUR===job&&JOBVIEW===view)note.textContent="Could not check detections: "+error.message;}
 finally{if(button.isConnected)button.disabled=false;}
}
function reviewChoiceDelta(){
 const base=REVIEW_BASE&&REVIEW_BASE.job===CUR?REVIEW_BASE:null;
 const enabled={},verified_labels={},output_choices={};
 for(const [i,value] of Object.entries(EN)){
  if(!base||base.enabled[i]!==value)enabled[i]=value;
 }
 for(const [i,value] of Object.entries(VLBL)){
  const normalized=value==="clear"?"":value;
  if(value==="clear"||!base||(base.labels[i]||"")!==normalized){
   verified_labels[i]=value;
   if(value==="clear"&&Object.prototype.hasOwnProperty.call(EN,i))enabled[i]=EN[i];
  }
 }
 for(const [i,value] of Object.entries(OUTPUT_CHOICES)){
  if(value&&(!base||!base.output_choices?.[i])){output_choices[i]=true;enabled[i]=EN[i];}
 }
 return {enabled,verified_labels,...(Object.keys(output_choices).length?{output_choices}:{})};
}
async function loadReview(signal=null,phase=SHELLPH){
 const job=CUR,view=JOBVIEW;
 const current=()=>!(signal&&signal.aborted)&&CUR===job&&JOBVIEW===view;
 await CONFIRM_CHAIN;
 if(!current()||CONFIRM_FAILED.size||!await flushPlateSaves()||!current())return false;
 if(!closePlateQuad())return false;
 clearReviewPreviews();
 if(!await showPanel("review")||!current())return false;
 if(VLBLJOB!==CUR){VLBL={};VLBLJOB=CUR;}
 let d;
 try{d=(await reviewRequest(`api/jobs/${job}/detections`,{signal})).data;}catch(error){
  if(current()){
   const w=document.getElementById("warnbox");if(w){w.style.display="block";w.textContent="Review could not load: "+error.message;}
   if(signal)throw error; // keep polling backoff and retry an unfinished transition
  }
  return false;
 }
 if(!current())return false;
 DUR=d.duration;
 const candidates=Array.isArray(d.learning_candidates)?d.learning_candidates:[];
 const evaluated=candidates.filter(candidate=>candidate.assessment);
 const acceptedMask=!!(d.learning&&d.learning.active&&d.learning.active.model);
 const verification=d.verification||(d.verification_history||[]).at(-1);
 if(LEARNING_SELECTION_JOB!==CUR)LEARNING_SELECTION=null;
 const groups={}; const zdrop=[]; TRKMEM={};
 REVIEW_BASE={job,enabled:{},labels:{},output_choices:{}};
 FINDING_META={};REVIEW_DISPLAY_META={};OUTPUT_CHOICES={};OUTPUT_VERSION={};
 d.detections.forEach(x=>{
  FINDING_META[x.i]=x;
  if(x.output_choice_explicit)OUTPUT_CHOICES[x.i]=REVIEW_BASE.output_choices[x.i]=true;
  REVIEW_BASE.enabled[x.i]=x.enabled;
  if(x.verified_label)REVIEW_BASE.labels[x.i]=x.verified_label;
  EN[x.i]=x.enabled;
  if(!(x.i in VLBL)&&x.verified_label)VLBL[x.i]=x.verified_label;
  if(x.zone_dropped){zdrop.push(x);return;}
  (groups[x.category]=groups[x.category]||[]).push(x);});
 let html=`<div class="card" id="review"><h2>Review findings</h2>
 <p class="review-copy">Review small saved pictures. Choose <b>Is a …</b> or <b>Not a …</b> to save a human example with its source video.
 Scan-time pictures are matched to final tracked findings automatically; Review may show a nearby real cached frame from the same track.
 A genuinely missing picture stays unloaded until you click <b>Load preview</b>, so opening Review does not reopen the source video.
 Drag plate corners to adjust the area; an area edit alone does not confirm a plate.<br>Automatic protection stays active while a finding is <b>Not reviewed</b>. Output choices apply after <b>Save edits &amp; render</b>.
 Drag across cards to select several.</p>
 <div class="row" style="margin-bottom:10px">
  <a href="#findings" onclick="openFindingsForVideo('${sectionEscape(d.video_id||"")}')">Browse saved findings &amp; train a named model</a>
 </div><label for="trainingRunName">Training run name (optional)</label>
 <input id="trainingRunName" maxlength="80" placeholder="Automatic: video name and timestamp" style="width:100%;box-sizing:border-box;margin-bottom:8px">
 <div class="row" style="margin-bottom:10px">
  <button type="button" onclick="trainAndRescan()">Train &amp; rescan this video</button>
  <button type="button" class="sec" onclick="reviewUncertain()">Review 10% of plate groups</button>
  <button type="button" id="reviewShowAll" class="sec" hidden onclick="reviewAllFindings()">Show all findings</button>
 </div>
 <details id="knownPlateSearch" style="margin-bottom:12px"><summary>Find examples using known plate numbers</summary>
  <p class="review-copy">Optional local OCR search. Enter the number(s) you expect, one per line. Full matches count more strongly than fragments. It tries rotated, upside-down, mirrored and perspective-corrected views, then adds possible matches to review. Confirm examples before training.</p>
  <label for="knownPlateTexts">Known plate numbers</label><textarea id="knownPlateTexts" rows="2" maxlength="400" placeholder="ABC-123" autocomplete="off" spellcheck="false" style="width:100%;box-sizing:border-box"></textarea>
  <label for="plateTextSamples">Maximum sampled frames</label><input id="plateTextSamples" type="number" min="1" max="600" step="1" value="120" style="max-width:130px">
  <button type="button" id="plateTextSearchButton" onclick="searchKnownPlateText()">Find plate examples</button>
  <p id="plateTextStatus" class="review-copy" role="status">${d.plate_text_search?sectionEscape(`${d.plate_text_search.done||0} frames searched; ${d.plate_text_search.added||0} new candidates, ${d.plate_text_search.matched_existing||0} matches to existing findings.`):'Search reads sampled source frames once on CPU. It does not run when opening a saved picture.'}</p>
  <p class="review-copy">A sample search can miss plates between checked frames. Partial matches never mean that only the recognized characters need hiding: protect the whole number. Full plate / Lettering only remains your scan coverage choice.</p>
 </details>
 ${verification?`<p id="plateVerifierResults" class="review-copy" role="status">${sectionEscape(`${d.verification?"Last check":"Earlier checker pass"}: ${verification.mode} mode; ${verification.inference?.checked||0} checked, ${verification.inference?.suggested||0} suggested, ${verification.inference?.suppressed||0} filtered, ${verification.inference?.human_preserved||0} human decisions preserved. `+verifierAssessmentText(verification.assessment))}</p>`:""}
 ${candidates.length?`<details id="plateVerifierPanel" open style="margin-bottom:12px">
  <summary>Check plate detections with a trained candidate</summary>
  <p class="review-copy">Use learned background examples such as hands to check existing detections. This runs the retained model without training again or rescanning with the original detector.</p>
  <label for="plateVerifierCandidate">Trained candidate</label>
  <select id="plateVerifierCandidate" style="width:100%" onchange="updatePlateVerifierCandidate()">${candidates.map(candidate=>`<option value="${sectionEscape(candidate.id)}">${sectionEscape(candidate.name||candidate.version)}${candidate.assessment?" · "+sectionEscape(candidate.assessment.status):" · not evaluated"}</option>`).join("")}</select>
  <label for="plateVerifierMode">Check mode</label>
  <select id="plateVerifierMode" style="max-width:100%"><option value="review">Review suggestions — preserve output choices</option><option value="filter" disabled>Filter validated false positives</option></select>
  <button type="button" id="plateVerifierButton" onclick="checkPlateDetections()">Check detections</button>
  <p id="plateVerifierStatus" class="review-copy" role="status" aria-live="polite"></p>
  <p class="review-copy">Plate scores are model confidence, not a probability that an object is not a plate. Review the results before rendering.</p>
 </details>`:""}
 <details id="saveLearnedModelPanel" style="margin-bottom:12px">
  <summary>Save trained model for other videos</summary>
  <p class="review-copy">Save an accepted mask model or an evaluated secondary checker for another video.</p>
  <label for="learnedModelSource">Model to save</label>
  <select id="learnedModelSource" style="width:100%">${acceptedMask?'<option value="">Accepted plate mask model</option>':""}${evaluated.map(candidate=>`<option value="${sectionEscape(candidate.id)}">Secondary checker · ${sectionEscape(candidate.version)} · ${sectionEscape(candidate.assessment.status)}</option>`).join("")}${!acceptedMask&&!evaluated.length?'<option value="" disabled>No evaluated model available</option>':""}</select>
  <label for="learnedModelName">Model name</label>
  <input id="learnedModelName" type="text" maxlength="80" placeholder="e.g. Garage daylight" style="width:100%;box-sizing:border-box">
  <label for="learnedModelDescription">Environment description</label>
  <textarea id="learnedModelDescription" maxlength="500" rows="2" placeholder="Camera, lighting or other useful notes" style="width:100%;box-sizing:border-box"></textarea>
  <button id="saveLearnedModelButton" type="button" onclick="saveLearnedModel()" ${acceptedMask||evaluated.length?"":"disabled"}>Save model</button>
  <p id="saveLearnedModelStatus" class="review-copy" role="status" aria-live="polite">${acceptedMask||evaluated.length?"Choose the model to save. Secondary checkers default to review suggestions on new videos.":"Check a retained candidate above, or complete an accepted mask training pass, to save a reusable model."}</p>
 </details>
 <p id="reviewSampleSummary" class="review-copy" role="status" hidden></p>
 <p id="reviewSaveStatus" class="review-copy review-save-status" role="status" aria-live="polite">Review choices loaded from disk.</p>
 <div id="plateSaveIssues" class="review-copy" role="status" aria-live="polite" hidden></div>
 <p class="review-copy">Training uses saved corrections and the original detectors. It does not guarantee that undetected plates have been found. Review the output.</p>
 ${reviewOverlayLegendHTML()}
 <p class="review-copy">Yellow is the primary detector proposal. Red is the effective area that will be concealed; it keeps four-corner rotation, skew and perspective. Green stays visible. Labels identify human corrections, learned masks and safe fallbacks.</p>
 <div class="row" style="margin:0 0 8px">
  <button class="sec" onclick="loadBoxEdit(1)">▶ Preview video &amp; edit boxes
  (before rendering)</button></div>
 <div id="beslot"></div>
 <div id="detwrap" style="position:relative;user-select:none">`;
 if(zdrop.length){
  html+=`<details id="reviewZones" style="margin:4px 0 10px;border:1px dashed #f59e0b;border-radius:9px;padding:8px 10px;background:#26200a">
   <summary style="cursor:pointer;color:#fbbf24;font-weight:600">
    ⚠ ${zdrop.length} detection(s) outside your zones — NOT blurred
    (mostly logos/labels by design; open only if something real was zoned out)
   </summary>
   <div class="row" style="margin:8px 0 4px">
    <button class="sec" onclick="setAllZd(true)">Blur all of these</button>
    <button class="sec" onclick="setAllZd(false)">Keep all of these visible</button></div>
   <div class="grid3">`;
  for(const x of zdrop){
   html+=`<div class="det ${EN[x.i]?'':'off'}" id="det${x.i}" data-cat="zdrop">
    <img id="thumb${x.i}" data-preview-url="api/jobs/${job}/finding-preview/${x.i}" alt="Original detection preview"
     style="cursor:zoom-in" onclick="zoomDet(${x.i})">
    <small class="preview-status" role="status">Preview not loaded</small><button class="sec preview-retry" hidden onclick="retryReviewPreview(this)">Retry preview</button>
    <div>"${sectionEscape(x.text)}" <br>${x.t_start.toFixed(1)}–${x.t_end.toFixed(1)}s</div>
    <div id="bb${x.i}">${detChoices(x.i)}</div>
   </div>`;
  }
  html+=`</div></details>`;
 }
 for(const[cat,rawItems] of Object.entries(groups)){
  // collapse dense tracks: one card per physical object, not per frame
  const byGroup={},items=[];
  // Group BEFORE filtering: a sampled card retains the entire track's span
  // and decision membership instead of becoming an isolated per-frame card.
  for(const x of rawItems){
   // identity first: one card per PERSON (all their tracks); then per
   // track; ungrouped detections stand alone
   const key=x.person>=0?("p"+x.person):(x.track>=0?("t"+x.track):null);
   if(key){(byGroup[key]=byGroup[key]||[]).push(x);}
   else{TRKMEM[x.i]=[x.i];items.push(x);}
  }
  for(const [key,members] of Object.entries(byGroup)){
   members.sort((a,b)=>a.t_start-b.t_start);
   const sampled=LEARNING_SELECTION?members.find(m=>LEARNING_SELECTION.has(m.i)):null;
   let best=sampled||members[0];     // use the sampler's representative frame
   // The first exact sighting normally has its compact scan-time crop.
   const rep={...best};
   rep.learning_conflict=members.some(m=>m.learning_conflict)?"Model disagreement — review this track":"";
   rep.plate_verification=(members.find(m=>m.plate_verification?.applied)||members.find(m=>m.plate_verification?.decision==="suggest_not_plate")||best).plate_verification;
   rep.t_start=members[0].t_start;
   rep.t_end=members[members.length-1].t_end;
   rep.frames=members.length;
   rep.fallbacks=[...new Set(members.map(m=>m.fallback_reason).filter(Boolean))];
   rep.fallbackCount=members.filter(m=>m.fallback_reason).length;
   rep.human_region_confirmed=members.some(m=>m.human_region_confirmed);
   rep.shaped=members.some(m=>m.shaped);
   rep.personcard=key[0]==="p";
   TRKMEM[rep.i]=members.map(m=>m.i);
   items.push(rep);
  }
  // person cards first, then everything else chronologically
  items.sort((a,b)=>((b.personcard?1:0)-(a.personcard?1:0))||a.t_start-b.t_start);
  if(!items.length)continue;
  html+=`<h3 style="margin:10px 0 6px">${CATDN[cat]||cat} <span class="badge">${items.length}</span>
   <button class="sec" style="padding:3px 8px;font-size:12px"
    onclick="setAll('${cat}',true)">Blur all</button>
   <button class="sec" style="padding:3px 8px;font-size:12px"
    onclick="setAll('${cat}',false)">Keep all visible</button></h3><div class="grid3" data-review-category="${cat}">`;
  for(const x of items){
   REVIEW_DISPLAY_META[x.i]=x;
   html+=`<div class="det ${EN[x.i]?'':'off'}" id="det${x.i}" data-cat="${cat}">
    <div class="${x.category==="plate"?"plate-preview":"finding-preview"}">
    <img id="thumb${x.i}" data-preview-url="api/jobs/${job}/finding-preview/${x.i}" alt="Original detection preview"
     class="${x.category==="plate"?"plate-edit-thumb":""}"
     title="${x.category==="plate"?"Drag numbered corners; autosaved to this track":"Enlarge detection"}"
     style="cursor:${x.category==="plate"?"pointer":"zoom-in"}"
     onclick="${x.category==="plate"?"":"zoomDet("+x.i+")"}"
     onpointerdown="${x.category==="plate"?"event.stopPropagation()":""}"
     draggable="false" ondragstart="return false"
     >${x.category==="plate"?'<canvas class="plate-outline"></canvas><span id="plateOverlay'+x.i+'" class="plate-output-badge"></span>':""}</div>
    <small class="preview-status" role="status">Preview not loaded</small>
    <button class="sec preview-retry" hidden onclick="retryReviewPreview(this)">Retry preview</button>
    ${x.category==="plate"?'<small class="quad-status" role="status" title="Corners apply to this detected track. Review changing perspective. Keyboard: select corner 1–4, use arrows; Ctrl+Z undoes.">Corners autosave to track</small><button type="button" class="sec quad-retry" hidden>Retry save</button>':""}
    <div>${plateVerificationBadge(x)}${x.learning_conflict?'<span class="badge" title="The original coverage was retained where the learned model could not make a reliable refinement">Model disagreement — review</span> ':""}${plateFallbackText(x)?`<span class="badge" style="white-space:normal">${plateFallbackText(x)}</span> `:""}${x.shaped?'<span class="badge" title="Thumbnail rectangle is a selection guide; open to inspect the mask and any exclusions">shaped mask</span> ':""}${x.personcard?`<b>Person ${x.person+1}</b> — one decision for ALL their appearances`:`"${sectionEscape(x.text)}"`}${x.frames?` <span class="badge">×${x.frames} frames</span>`:""}${x.confidence?` <span class="badge" title="detector confidence — not a human decision">${Math.round(x.confidence*100)}%</span>`:""} <br>${x.t_start.toFixed(1)}–${x.t_end.toFixed(1)}s</div>
    ${plateTextBadge(x)}
    <div class="finding-confirm" role="group" aria-label="Human classification">
     <button class="sec" onclick="confirmFinding(${x.i},'positive')" aria-pressed="${reviewFindingLabel(x.i)==='positive'}">✓ Is ${findingNoun(x.i)}</button>
     <button class="sec" onclick="confirmFinding(${x.i},'negative')" aria-pressed="${reviewFindingLabel(x.i)==='negative'}">✕ Not ${findingNoun(x.i)}</button></div>
    <small id="vlabel${x.i}" style="color:#93c5fd" role="status">${findingStatus(x.i)}</small>
    <button class="sec" id="findingDismiss${x.i}" hidden onclick="dismissFindingConfirmation(${x.i})">Keep current review choice</button>
    <div id="bb${x.i}">${detChoices(x.i)}</div>
   </div>`}
  html+=`</div>`}
 html+=`</div>
 <div class="row" style="margin-top:12px">
 <button onclick="saveAndRender()">${phase==="paused"?"Save review edits":"Save edits &amp; render"}</button>
 <span class="review-save-status" role="status" aria-live="polite"></span>
 <span style="font-size:12px;color:#94a3b8">missed something? use
  ▶ Preview video &amp; edit boxes above — its ＋ Add box replaces the old
  add-region tool</span></div></div>`;
 const old=document.getElementById("review"); if(old)old.remove();
 detail.insertAdjacentHTML("beforeend",html);
 // Bind the snapshot to this panel/view; removing it releases the metadata.
 const panel=document.getElementById("review");
 if(panel){
  panel._learningCandidates=candidates;
  panel._sampleRows=d.detections.filter(x=>x.category==="plate"&&!x.zone_dropped).map(x=>({
   i:x.i,category:"plate",person:x.person,track:x.track,t_start:x.t_start,
   confidence:x.confidence,verified_label:x.verified_label,
   learning_conflict:!!x.learning_conflict,fallback_reason:!!x.fallback_reason}));
  panel._sampleJob=job;panel._sampleView=view;
 }
 updatePlateVerifierCandidate();
 if(LEARNING_SELECTION)applyReviewGroupFilter();
 if(typeof updateReviewOverlayLabel==="function"&&typeof REVIEW_DISPLAY_META!=="undefined"){
  for(const key of Object.keys(REVIEW_DISPLAY_META))updateReviewOverlayLabel(Number(key));
 }
 initMarquee();initReviewPreviews();
 return true;
}

function detChoices(i){
 const blur=!!EN[i],chosen=!!OUTPUT_CHOICES[i];
 return `<div class="det-status ${chosen?(blur?"blur":"keep"):"unreviewed"}">${chosen?(blur?"Will be blurred":"Will stay visible"):"Not reviewed"}</div>
  <small class="review-copy">${chosen?"Output choice":"Automatic output: "+(blur?"protected":"visible")}</small>
  <div class="det-choices" role="group" aria-label="Output for this finding">
   <button class="det-choice blur" aria-label="Blur" aria-pressed="${chosen&&blur}"
    onclick="applyDet(${i},true)">Blur</button>
   <button class="det-choice keep" aria-label="Keep visible" aria-pressed="${chosen&&!blur}"
    onclick="applyDet(${i},false)">Keep visible</button>
  </div>`;
}
let TRKMEM={};
function findingNoun(i){
 const cat=FINDING_META[i]?.category||"finding";
 return sectionEscape(({plate:"a plate",face:"a face",person:"a person",name:"a name",email:"an email address",manual:"a sensitive region"})[cat]||("a "+cat.replaceAll("_"," ")));
}
function reviewFindingLabel(i){return FINDING_META[i]?.human_confirmation?.label||(VLBL[i]==="plate"?"positive":VLBL[i]==="not_plate"?"negative":"");}
function findingStatus(i){
 const label=reviewFindingLabel(i);if(!label)return "Choose Is / Not to save a training example";
 return (FINDING_META[i]?.confirmed_finding_id?"Saved · ":"Reviewed · ")+(label==="positive"?"Is ":"Not ")+findingNoun(i);
}
function labelPlate(i,label){
 if(label!=="plate"&&label!=="not_plate")return;
 return confirmFinding(i,label==="plate"?"positive":"negative");
}
function rememberFindingConflict(i,current){
 const row=FINDING_META[i];
 if(row&&typeof current?.id==='string'&&(!row.confirmed_finding_id||current.id===row.confirmed_finding_id)&&Number.isInteger(current.revision)){
  row.confirmed_finding_id=current.id;
  row.confirmed_finding_revision=current.revision;
 }
}
function showFindingFailure(i,error){
 CONFIRM_FAILED.set(i,error);
 const current=error.details?.current_archive,note=document.getElementById('vlabel'+i);
 if(current)rememberFindingConflict(i,current);
 const reason=current?(current.revoked?'This saved example was forgotten.':
  'The saved example now says '+(current.label==='positive'?'Is ':'Not ')+findingNoun(i)+'.'):error.message;
 if(note)note.textContent='Not saved · '+reason+' Click Is / Not to confirm your current decision.';
 const dismiss=document.getElementById('findingDismiss'+i);
 if(dismiss){
  // A definite rejection can be dismissed. An uncertain network result must
  // be retried with its saved receipt so the browser learns what was written.
  dismiss.hidden=![400,409].includes(error.status)&&!error.beforeWrite;
  dismiss.textContent=PLATE_EDITS.get(i)?.archiveConflict?'Discard this unsaved adjustment':'Keep current review choice';
 }
}
function dismissFindingConfirmation(i){
 if(CONFIRM_PENDING.has(i))return;
 const error=CONFIRM_FAILED.get(i);
 if(error&&![400,409].includes(error.status)&&!error.beforeWrite)return;
 const edit=PLATE_EDITS.get(i);
 if(edit?.archiveConflict){
  edit.pending=null;edit.version++;edit.dirty=false;edit.error=null;
  edit.archiveConflict=false;edit.conflict=false;edit.points=plateCopy(edit.saved);
  edit.draw();plateStatus(edit,'Saved area · current review choice kept');schedulePlateSaves();
 }
 CONFIRM_FAILED.delete(i);
 const note=document.getElementById('vlabel'+i);if(note)note.innerHTML=findingStatus(i);
 const dismiss=document.getElementById('findingDismiss'+i);if(dismiss)dismiss.hidden=true;
 plateUnloadGuard();
}
function confirmFinding(i,label){
 if(!['positive','negative'].includes(label)||CONFIRM_PENDING.has(i))return CONFIRM_CHAIN;
 if(PLATE_REVIEW_BUSY){
  const note=document.getElementById('vlabel'+i);
  if(note)note.textContent='Review is being saved; choose Is / Not after it finishes.';
  return CONFIRM_CHAIN;
 }
 if(FINDING_META[i]?.classification_allowed===false){
  const note=document.getElementById('vlabel'+i);if(note)note.textContent=FINDING_META[i].classification_note;
  return CONFIRM_CHAIN;
 }
 const members=TRKMEM[i]||[i],versions=Object.fromEntries(members.map(m=>[m,OUTPUT_VERSION[m]||0]));
 const job=CUR,view=JOBVIEW;CONFIRM_PENDING.add(i);CONFIRM_FAILED.delete(i);plateUnloadGuard();
 const card=document.getElementById('det'+i),note=document.getElementById('vlabel'+i);
 const dismiss=document.getElementById('findingDismiss'+i);if(dismiss)dismiss.hidden=true;
 if(note)note.textContent='Saving confirmation…';
 card?.querySelectorAll('button').forEach(button=>button.disabled=true);
 CONFIRM_CHAIN=CONFIRM_CHAIN.then(async()=>{
  try{
   const edit=PLATE_EDITS.get(i);
   if(edit?.drag)throw Object.assign(new Error('Finish moving the corners before confirming.'),{beforeWrite:true});
   if(label==='negative')for(const m of members)discardRejectedCorners(m);
   if(edit?.dirty&&!edit.archiveConflict){
    edit.readyAt=0;
    while((edit.dirty&&!edit.error)||PLATE_SAVE){
     await (PLATE_SAVE||pumpPlateSaves());
     if(edit.dirty&&!edit.error)await new Promise(resolve=>setTimeout(resolve,100));
    }
    if(edit.dirty||edit.error)
     throw edit.archiveConflict?edit.error:Object.assign(new Error('Save or reload this area adjustment before confirming.'),{beforeWrite:true});
   }else if(PLATE_SAVE)await PLATE_SAVE;
   if(CUR!==job||JOBVIEW!==view)return;
   const body={label,expected_revision:FINDING_META[i]?.confirmed_finding_revision};
   if(edit?.meta.preview_token)body.preview_token=edit.meta.preview_token;
   if(label==='positive'&&edit?.archiveConflict)body.points=plateCopy(edit.points);
   const editVersion=edit?.version;
   const {data}=await reviewRequest('api/jobs/'+job+'/confirm/'+i,{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(body),timeoutMs:120000});
   if(CUR!==job||JOBVIEW!==view)return;
   for(const m of members){
    const row=FINDING_META[m];if(!row)continue;
    row.human_confirmation={label,propagated:m!==i};OUTPUT_CHOICES[m]=true;
    const confirmedOutput=label==='positive';
    if((OUTPUT_VERSION[m]||0)===versions[m])EN[m]=confirmedOutput;
    if(row.category==='plate')VLBL[m]=label==='positive'?'plate':'not_plate';
    if(REVIEW_BASE?.job===job){REVIEW_BASE.enabled[m]=confirmedOutput;REVIEW_BASE.labels[m]=VLBL[m]||'';REVIEW_BASE.output_choices[m]=true;}
    const output=document.getElementById('bb'+m);if(output)output.innerHTML=detChoices(m);
    document.getElementById('det'+m)?.classList.toggle('off',!EN[m]);
    if(typeof redrawReviewOverlay==="function")redrawReviewOverlay(m);
   }
   Object.assign(FINDING_META[i],{confirmed_finding_id:data.finding.id,confirmed_finding_revision:data.finding.revision});
   if(edit&&data.preview){
    Object.assign(edit.meta,data.preview);edit.img._plateMeta=edit.meta;
    edit.saved=plateCopy(edit.meta.points);syncPlateTrack(edit);
    if(edit.version===editVersion&&!edit.drag){
     edit.points=plateCopy(edit.saved);edit.pending=null;edit.dirty=false;
     edit.error=null;edit.conflict=false;edit.archiveConflict=false;
    }
    edit.draw();plateStatus(edit,edit.dirty?'Saving…':'Saved area · confirmation stored');
   }
   CONFIRM_FAILED.delete(i);
   if(note)note.innerHTML=findingStatus(i);
   card?.querySelectorAll('.finding-confirm button').forEach((button,index)=>button.setAttribute('aria-pressed',index===(label==='positive'?0:1)));
   if(document.getElementById('beCv'))beRefresh();
  }catch(error){showFindingFailure(i,error);}
  finally{CONFIRM_PENDING.delete(i);card?.querySelectorAll('button').forEach(button=>button.disabled=FINDING_META[i]?.classification_allowed===false&&!!button.closest('.finding-confirm'));plateUnloadGuard();}
 });
 return CONFIRM_CHAIN;
}
function applyDet(i,blur,preserveLabel=false){
 for(const m of (TRKMEM[i]||[i])){
  EN[m]=blur;
  OUTPUT_CHOICES[m]=true;
  OUTPUT_VERSION[m]=(OUTPUT_VERSION[m]||0)+1;
  const b=document.getElementById("bb"+m),t=document.getElementById("det"+m);
  if(b)b.innerHTML=detChoices(m);
  if(t)t.classList.toggle("off",!blur);
  if(typeof redrawReviewOverlay==="function")redrawReviewOverlay(m);
 }
 markReviewChanged();
 if(document.getElementById("beCv")){beRefresh();}
}
function setAll(cat,on){document.querySelectorAll(`.det[data-cat=${cat}]:not([hidden])`)
 .forEach(el=>applyDet(+el.id.slice(3),on));}
function thumbRetry(img){
 const n=+(img.dataset.r||0);
 if(n>=3)return;
 img.dataset.r=n+1;
 setTimeout(()=>{img.src=img.src.split("?r=")[0]+"?r="+Date.now();},
            600*(n+1));
}
function setAllZd(on){document.querySelectorAll(`.det[data-cat=zdrop]:not([hidden])`)
 .forEach(el=>applyDet(+el.id.slice(3),on));}

let selSet=new Set(),marqEl=null,menuEl=null,mStart=null;
function clearSel(){
 selSet.forEach(i=>{const t=document.getElementById("det"+i);
  if(t)t.classList.remove("selected");});
 selSet.clear();
 if(menuEl){menuEl.remove();menuEl=null;}
}
function initMarquee(){
 const wrap=document.getElementById("detwrap");
 if(!wrap||wrap.dataset.mq)return;
 wrap.dataset.mq=1;
 wrap.addEventListener("pointerdown",e=>{
  if(e.pointerType==="touch")return;         // touch keeps normal scrolling
  if(e.target.closest("button,a,input,select,textarea,img,.plate-edit-thumb"))return;
  // Dragging a plate thumbnail edits its preview, never selects a card.
  clearSel();
  mStart=[e.pageX,e.pageY];
  marqEl=document.createElement("div");marqEl.className="marq";
  document.body.appendChild(marqEl);
  const move=ev=>{
   const x1=Math.min(mStart[0],ev.pageX),y1=Math.min(mStart[1],ev.pageY),
         x2=Math.max(mStart[0],ev.pageX),y2=Math.max(mStart[1],ev.pageY);
   Object.assign(marqEl.style,{left:x1+"px",top:y1+"px",
    width:(x2-x1)+"px",height:(y2-y1)+"px"});
  };
  const up=ev=>{
   document.removeEventListener("pointermove",move);
   document.removeEventListener("pointerup",up);
   const r=marqEl.getBoundingClientRect();
   marqEl.remove();marqEl=null;
   if(r.width<8&&r.height<8)return;          // just a click — not a drag
   document.querySelectorAll("#detwrap .det:not([hidden])").forEach(t=>{
    const b=t.getBoundingClientRect();
    if(b.left<r.right&&b.right>r.left&&b.top<r.bottom&&b.bottom>r.top){
     selSet.add(+t.id.slice(3));t.classList.add("selected");}});
   if(selSet.size)showSelMenu(ev.pageX,ev.pageY);
  };
  document.addEventListener("pointermove",move);
  document.addEventListener("pointerup",up);
  e.preventDefault();
 });
}
function showSelMenu(x,y){
 menuEl=document.createElement("div");menuEl.className="selmenu";
 menuEl.innerHTML=`<span>${selSet.size} selected</span>
   <button class="mkeep" onclick="bulkSet(false)">Keep visible</button>
  <button class="mblur" onclick="bulkSet(true)">Blur</button>
  <button class="sec" onclick="bulkLabelPlate('plate')">Confirm plates</button>
  <button class="sec" onclick="bulkLabelPlate('not_plate')">Not plates</button>`;
 Object.assign(menuEl.style,{left:x+"px",top:(y+10)+"px"});
 document.body.appendChild(menuEl);
}
function bulkSet(blur){selSet.forEach(i=>applyDet(i,blur));clearSel();}
function bulkLabelPlate(label){
 selSet.forEach(i=>{
  const el=document.getElementById("det"+i);
  if(el&&el.dataset.cat==="plate")labelPlate(i,label);
 });
 clearSel();
}
document.addEventListener("pointerdown",e=>{
 if(menuEl&&!e.target.closest(".selmenu")
    &&!e.target.closest("#detwrap"))clearSel();});
document.addEventListener("click",e=>{
 const q=e.target.closest(".qm");
 document.querySelectorAll(".qm.open").forEach(x=>{if(x!==q)x.classList.remove("open");});
 if(q)q.classList.toggle("open");});
document.addEventListener("keydown",e=>{
 if(e.key==="Escape"){clearSel();if(QEDIT)QEDIT.cancelDrag();
  const lb=document.getElementById("lb");if(lb)lb.remove();}});

async function saveAndRender(saveOnly=false){
 if(PLATE_REVIEW_BUSY){
  reviewSaveStatus("Save is still in progress; no new training/rendering action has started.");return false;
 }
 PLATE_REVIEW_BUSY=true;
 const job=CUR,view=JOBVIEW;
 try{
  reviewSaveStatus("Saving review…");
  await CONFIRM_CHAIN;
  if(CONFIRM_FAILED.size){reviewSaveStatus('A confirmation was not saved. Retry its Is / Not choice, or dismiss its rejected change, before training or rendering.',true);return false;}
  if([...PLATE_EDITS.values()].some(s=>s.drag)){
   reviewSaveStatus("Finish dragging the corner first. Review has not been saved.",true);return false;
  }
  const cornersSaved=await flushPlateSaves();
  if(CUR!==job||JOBVIEW!==view)return false;
  if(!cornersSaved){
   // An unrelated corner failure must not prevent saving rejection/visibility
   // decisions. Do not submit failed geometry or pretend the review is complete.
   if(!await persistReview(true,job,view,true))return false;
   const n=[...PLATE_EDITS.values()].filter(s=>s.dirty||s.pending||s.drag).length;
   reviewSaveStatus("Review choices saved to disk, but "+n+" corner adjustment(s) not saved. "+
    "Training/rendering is blocked. Keep this page open and retry the corner save.",true);
   return false;
  }
  return await persistReview(saveOnly,job,view);
 }catch(error){
  reviewSaveStatus("Review save not confirmed. Keep this page open and retry. "+error.message,true);
  alert("Review save failed for job "+job+": "+
   (error.name==="AbortError"?"request timed out":error.message)+
   ". The save was not confirmed. Keep the review open and retry before leaving.");
  return false;
 }finally{PLATE_REVIEW_BUSY=false;}
}
async function persistReview(saveOnly=false,job=CUR,view=JOBVIEW,choicesOnly=false){
 // Do not render until the server has confirmed the latest pending preview.
 if(!choicesOnly&&document.getElementById("beCv")){
  if(BE.drag||BE.pending){
   alert("Wait for the mask preview to finish updating before saving.");return false;
  }
  if(!await beRefresh()){
   alert("Could not update the mask preview. Finish editing and try again.");return false;
  }
 }
 const manual=[...MAN,...BE.adds.map(a=>({t_start:a.t0,t_end:a.t1,
  t_ref:a.tref,screen_box:a.box}))];
 const revision=REVIEW_VERSION,baseline=REVIEW_BASE;
 const choices=reviewChoiceDelta();
 const payload=choicesOnly?choices:
  {...choices,manual,box_overrides:BE.ov,time_overrides:BE.times};
 // only send audio spans when the box editor actually loaded them —
 // otherwise a save from plain review would wipe stored spans with []
 if(!choicesOnly&&Array.isArray(BE.audio)&&BE.tlspans!==undefined)payload.audio=BE.audio;
 if(CUR!==job||JOBVIEW!==view)return false;
 const slow=setTimeout(()=>{
  if(CUR===job&&JOBVIEW===view&&REVIEW_BASE===baseline)
   reviewSaveStatus("Still saving review to disk… Keep this tab open. Training/rendering will wait for confirmation.");
 },5000);
 let r;
 try{
  // A disk transaction may legitimately outlast a preview request. Bounded,
  // save-only allowance; do not lengthen thumbnail/poll/network timeouts.
  ({data:r}=await reviewRequest(`api/jobs/${job}/detections`,{method:"POST",
   headers:{"Content-Type":"application/json"},timeoutMs:120000,
   body:JSON.stringify(payload)}));
 }finally{clearTimeout(slow);}
 // A delayed response belongs to its original review, never a newly opened job.
 if(CUR!==job||JOBVIEW!==view||REVIEW_BASE!==baseline)return false;
 if(!r||r.ok!==true)throw new Error("The server did not confirm saving the review");
 if(baseline){
  Object.assign(baseline.enabled,payload.enabled);
  baseline.output_choices=Object.assign(baseline.output_choices||{},payload.output_choices||{});
  for(const [i,label] of Object.entries(payload.verified_labels))
   baseline.labels[i]=label==="clear"?"":label;
 }
 for(const [i,label] of Object.entries(payload.verified_labels)){
  if(label==="clear"&&VLBL[i]==="clear"&&EN[i]===payload.enabled[i])VLBL[i]="";
 }
 REVIEW_SAVED=revision;plateUnloadGuard();
 if(!choicesOnly){BE.adds=[];BE.ov={};BE.times={};}
 if(r.suggest_allowlist&&r.suggest_allowlist.length){
  if(confirm("You disabled every instance of: "+r.suggest_allowlist.join(", ")+". Add these to the permanent allow-list so future scans skip them?"))
   {await fetch("api/allowlist",{method:"POST",
    headers:{"Content-Type":"application/json"},
    body:JSON.stringify({words:r.suggest_allowlist})});
    loadPersist();}}
 if(CUR!==job||JOBVIEW!==view)return false;
 if(!choicesOnly)MAN=[];
 if(reviewChoicesPending()){
  reviewSaveStatus("Earlier choices saved. Newer changes are not saved; save again before leaving.",true);return false;
 }
 if(saveOnly||SHELLPH==="paused"){
  reviewSaveStatus(choicesOnly?"Review choices saved to disk.":"Review edits saved to disk.");
  return true;
 }
 if(CUR!==job||JOBVIEW!==view)return false;
 await reviewRequest(`api/jobs/${job}/render`,{method:"POST"});
 if(CUR!==job||JOBVIEW!==view)return false;
 closePlateQuad();clearReviewPreviews();
 const rv=document.getElementById("review"); if(rv)rv.remove();
 return true;
}
async function loadPersist(){
 const a=await (await fetch("api/allowlist")).json();
 const el=document.getElementById("persistlist"),
       nt=document.getElementById("persistnote");
 el.innerHTML=(a.words||[]).map(x=>
  `<div class="pw">${x}<span title="remove from allow-list"
    onclick="rmPersist('${x.replace(/'/g,"")}')">✕</span></div>`).join("");
 if((a.words||[]).length){
  nt.style.display="block";
  nt.textContent="Green words load automatically from "+a.path+
   " — marked safe during previous reviews. They are always applied in "+
   "addition to anything typed above. Click ✕ to remove one.";
 }else nt.style.display="none";
 document.getElementById("clearpersist").style.display=
  (a.words||[]).length?"inline-block":"none";
}
async function clearPersist(){
 if(!confirm("Remove ALL learned safe words? Future scans will flag them again until re-reviewed."))return;
 await fetch("api/allowlist",{method:"POST",
  headers:{"Content-Type":"application/json"},
  body:JSON.stringify({clear:true})});
 loadPersist();
}
async function rmPersist(word){
 await fetch("api/allowlist",{method:"POST",
  headers:{"Content-Type":"application/json"},
  body:JSON.stringify({remove:[word]})});
 loadPersist();
}
async function loadCertInfo(){
 try{
  const c=await (await fetch("api/certinfo")).json();
  document.getElementById("certinfo").textContent=
   `Current: ${c.mode} certificate — ${c.subject}, expires ${c.expires}`;
 }catch(e){
  document.getElementById("certinfo").textContent=
   "Running over plain HTTP (started with --http).";
 }
}
async function uploadCerts(){
 const cf=document.getElementById("certfile").files[0],
       kf=document.getElementById("keyfile").files[0];
 if(!cf||!kf){alert("Choose both a certificate file and a key file.");return;}
 const fd=new FormData();fd.append("cert",cf);fd.append("key",kf);
 const r=await fetch("api/certs",{method:"POST",body:fd});
 alert(r.ok?(await r.json()).note:"Upload failed: "+await r.text());
 loadCertInfo();
}
async function removeCerts(){
 if(!confirm("Remove the custom certificate and return to self-signed on next restart?"))return;
 const r=await fetch("api/certs",{method:"DELETE"});
 alert((await r.json()).note);
 loadCertInfo();
}
async function updCheck(){
 try{
  const d=await (await fetch("/api/update_check")).json();
  if(!d.available)return;
  const el=document.getElementById("upd");
  if(d.can_update===false){
   // Docker/Podman: the in-place updater would write into the ephemeral
   // container and be lost on recreate — inform only, never offer.
   el.innerHTML='· <span style="color:#fbbf24" title="Pull the new image tag and recreate the container — job data lives in the mounted volume and is preserved.">v'
    +d.latest+' available — pull the new image to update</span> ';
  }else{
   el.innerHTML='· <a href="#" style="color:#fbbf24" onclick="updRun();return false">v'
    +d.latest+' available — update</a> ';
  }
 }catch(e){}
}
async function updRun(){
 if(!confirm("Update OpenScrub to the newest release now?\\n\\nJobs must be idle, and the server needs a restart afterwards to run the new version."))return;
 const r=await fetch("/api/update_run",{method:"POST"});
 if(!r.ok){alert(await r.text());return;}
 const el=document.getElementById("upd");
 el.textContent="· updating… ";
 const t=setInterval(async()=>{
  const s=await (await fetch("/api/update_status")).json();
  if(!s.running&&s.ok!==null){
   clearInterval(t);
   el.textContent=s.ok?"· updated — restart the server to finish ":"· update failed ";
   alert((s.ok?"Update installed.\\nRestart the OpenScrub server to run the new version.":"Update failed:")+"\\n\\n"+s.log.slice(-8).join("\\n"));
  }
 },2000);
}
async function vaultStatus(){
 try{
  const d=await (await fetch("/api/vault")).json();
  const st=document.getElementById("vstat");
  document.getElementById("vsetup").style.display=d.enabled?"none":"block";
  document.getElementById("vunlock").style.display=(d.enabled&&d.locked)?"flex":"none";
  document.getElementById("vlock").style.display=(d.enabled&&!d.locked)?"flex":"none";
  if(!d.enabled){st.textContent="Disabled — job files (PII) are stored in plaintext. Set a password to enable at-rest encryption.";st.style.color="#fbbf24";}
  else if(d.locked){
   st.textContent="LOCKED — "+d.encrypted_files+" file(s) encrypted on disk. Unlock to work with jobs.";st.style.color="#f87171";
   clearLearnedModels("Unlock the vault to access saved models.");
  }
  else{st.textContent="Unlocked — files decrypt while you work; they re-encrypt when you lock or shut down. Losing the password makes encrypted files unrecoverable.";st.style.color="#4ade80";}
  if(d.enabled&&!d.locked){
   document.getElementById("valk").checked=d.autolock_min>0;
   if(d.autolock_min>0)document.getElementById("valkmin").value=d.autolock_min;
  }
 }catch(e){}
}
async function vaultSetup(){
 const a=document.getElementById("vpw1").value,b=document.getElementById("vpw2").value;
 if(a.length<8){alert("Password must be at least 8 characters.");return;}
 if(a!==b){alert("Passwords do not match.");return;}
 if(!confirm("Enable at-rest encryption?\\n\\nTHERE IS NO PASSWORD RESET. If you lose this password, every encrypted job file is PERMANENTLY UNRECOVERABLE.\\n\\nContinue?"))return;
 const r=await fetch("/api/vault/setup",{method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify({password:a})});
 alert(r.ok?(await r.json()).note:await r.text());
 vaultStatus();
}
async function vaultUnlock(){
 const r=await fetch("/api/vault/unlock",{method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify({password:document.getElementById("vpw").value})});
 if(!r.ok){alert(await r.text());return;}
 document.getElementById("vpw").value="";
 await vaultStatus();loadJobs();await refreshLearnedModels();
}
async function vaultAutolockSave(){
 const on=document.getElementById("valk").checked;
 const m=on?parseInt(document.getElementById("valkmin").value||"30",10):0;
 await fetch("/api/vault/autolock",{method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify({minutes:m})});
 vaultStatus();
}
async function vaultDoLock(){
 if(!await flushPlateSaves())return;
 if(!confirm("Encrypt all job files now?\\n\\nYou will need the password to access them again."))return;
 const r=await fetch("/api/vault/lock",{method:"POST"});
 if(r.ok)clearLearnedModels("Unlock the vault to access saved models.");
 alert(r.ok?("Locked — "+(await r.json()).encrypted+" file(s) encrypted."):await r.text());
 vaultStatus();loadJobs();
}
let EXTPOLL=null;
async function extrasStatus(){
 try{
  const d=await (await fetch("/api/extras")).json();
  const el=document.getElementById("extras");
  if(d.frozen){el.innerHTML='This standalone install has no pip, so optional engines cannot be added here. Use the pip install of OpenScrub (<code>pip install "OpenScrub[ner]"</code>) if you need spaCy NER or PaddleOCR.';return;}
  el.innerHTML=d.items.map(i=>{
   let right;
   if(i.installed)right='<span style="color:#4ade80">installed</span>';
   else if(d.state==="installing"&&d.target===i.id)right='<span style="color:#fbbf24">installing… '+(d.log.length?d.log[d.log.length-1]:'')+'</span>';
   else right=`<button onclick="extraInstall('${i.id}')">Install</button>`;
   return '<div class="row" style="justify-content:space-between;gap:10px;padding:5px 0"><span><b>'+i.label+'</b><br><span style="color:#94a3b8;font-size:12px">'+i.desc+'</span></span>'+right+'</div>';
  }).join("");
  if(d.state==="installing"){if(!EXTPOLL)EXTPOLL=setInterval(extrasStatus,3000);}
  else if(EXTPOLL){clearInterval(EXTPOLL);EXTPOLL=null;
   if(d.state==="error")alert("Engine install failed:\\n"+d.log.join("\\n"));}
 }catch(e){}
}
async function extraInstall(id){
 const r=await fetch("/api/extras/"+id+"/install",{method:"POST"});
 if(!r.ok){alert(await r.text());return;}
 extrasStatus();
}

let LEARNED_MODEL_LIST=[],LEARNED_MODEL_REFRESH=0;
function clearLearnedModels(message){
 ++LEARNED_MODEL_REFRESH;
 LEARNED_MODEL_LIST=[];
 refreshSectionModels();
 const select=document.getElementById("learnedPlateModel");
 if(select){select.replaceChildren(new Option("None — use original plate masks",""));select.disabled=true;}
 document.getElementById("learnedModelLibrary").replaceChildren();
 document.getElementById("learnedModelStatus").textContent=message;
 document.getElementById("learnedPlateModelHint").textContent=message;
 refreshLearnedModelMode();
}
function refreshLearnedModelMode(selectId="learnedPlateModel",modeId="learnedPlateModelMode"){
 const select=document.getElementById(selectId),mode=document.getElementById(modeId);
 if(!select||!mode)return;
 const model=LEARNED_MODEL_LIST.find(item=>item.id===select.value);
 const previous=mode.dataset.model===select.value?mode.value:"";
 const secondary=model?.kind==="openscrub-plate-verifier";
 const validated=secondary&&model.validation?.status==="validated";
 mode.replaceChildren();
 if(!model){
  mode.add(new Option("Select a model first",""));mode.disabled=true;mode.dataset.model="";
  const hint=selectId==="learnedPlateModel"?document.getElementById("learnedPlateModelHint"):null;
  if(hint&&!select.disabled)hint.textContent="Use the original plate masks; no learned model is selected.";
  return;
 }
 if(secondary){
  mode.add(new Option("Review suggestions — preserve output choices","review"));
  const filter=new Option("Filter validated false positives","filter");filter.disabled=!validated;mode.add(filter);
  mode.value=previous==="filter"&&validated?"filter":"review";
 }else{mode.add(new Option("Refine plate masks","refine"));mode.value="refine";}
 mode.disabled=false;mode.dataset.model=model.id;
 if(selectId==="learnedPlateModel"){
  const hint=document.getElementById("learnedPlateModelHint");
  if(hint)hint.textContent="Selected: "+model.name+". "+(secondary?
   (validated?"Review suggests false positives; filtering applies the separately validated cutoff. Human choices are preserved.":"Review suggestions only; filtering has not passed held-out checks."):
   "Refines masks around original detector proposals. Review the results.");
 }
}
async function refreshLearnedModels(){
 const refresh=++LEARNED_MODEL_REFRESH;
 const select=document.getElementById("learnedPlateModel");
 const box=document.getElementById("learnedModelLibrary");
 const note=document.getElementById("learnedModelStatus");
 try{
  const {data}=await reviewRequest("api/jobs/learned-models",{timeoutMs:120000});
  if(refresh!==LEARNED_MODEL_REFRESH)return false;
  // The person may choose a model while this request is outstanding.
  const selected=select?select.value:"";
  LEARNED_MODEL_LIST=data.models;
  refreshSectionModels();
  note.textContent="";
  if(select){
   select.replaceChildren(new Option("None — use original plate masks",""));
   for(const model of data.models)select.add(new Option(model.name,model.id));
   select.value=data.models.some(m=>m.id===selected)?selected:"";
   select.disabled=false;
   const chosen=data.models.find(m=>m.id===select.value);
   document.getElementById("learnedPlateModelHint").textContent=chosen?
    "Selected: "+chosen.name+". Used for plate detection in new scans.":
    "Choose a saved model for this environment. Applied when plate detection is enabled; uses every-frame plate proposals and may take longer. Review the results.";
   refreshLearnedModelMode();
  }
  box.replaceChildren();
  if(!data.models.length)box.textContent="No saved models yet. Save an accepted mask model or an evaluated secondary checker from review, or import a model package.";
  for(const model of data.models){
   const row=document.createElement("div");row.className="learned-model";
   row.style.cssText="padding:12px 0;border-top:1px solid #334155;overflow-wrap:anywhere";
   const title=document.createElement("strong");title.textContent=model.name;row.appendChild(title);
   if(model.description){
    const description=document.createElement("p");description.className="review-copy";
    description.textContent=model.description;row.appendChild(description);
   }
   const size=document.createElement("p");size.className="review-copy";
   size.textContent=(model.model_size/1048576).toFixed(1)+" MiB · "+(model.kind==="openscrub-plate-verifier"?
    "Secondary verifier · "+(model.validation?.status==="validated"?"filtering validated":"review suggestions only"):"Plate mask model");
   row.appendChild(size);
   const actions=document.createElement("div");actions.className="row";
   actions.style.cssText="gap:10px;flex-wrap:wrap";
   const use=document.createElement("button");use.type="button";use.className="sec";
   use.textContent="Use for next scan";use.onclick=()=>{
    select.value=model.id;
    refreshLearnedModelMode();
    location.hash="";
    requestAnimationFrame(()=>select.scrollIntoView({block:"center"}));
   };
   const download=document.createElement("a");
   download.textContent="Export";download.href="api/jobs/learned-models/"+encodeURIComponent(model.id)+"/export";
   download.setAttribute("download","");
   const remove=document.createElement("button");remove.type="button";remove.className="sec";
   remove.textContent="Remove";remove.onclick=()=>removeLearnedModel(model.id,model.name);
   actions.append(use,download,remove);row.appendChild(actions);box.appendChild(row);
  }
  return true;
 }catch(error){
  if(refresh!==LEARNED_MODEL_REFRESH)return false;
  if(error.status===423)clearLearnedModels("Unlock the vault to access saved models.");
  else{note.textContent=error.message;if(select)select.disabled=true;}
  return false;
 }
}
async function importLearnedModel(input){
 const file=input.files[0];if(!file)return;
 const note=document.getElementById("learnedModelStatus");
 if(file.size>257*1024*1024){note.textContent="Model package is too large (256 MiB model limit).";input.value="";return;}
 const data=new FormData();data.append("model",file);
 input.disabled=true;note.textContent="Importing and checking the model...";
 try{
  const {data:result}=await reviewRequest("api/jobs/learned-models/import",
    {method:"POST",body:data,timeoutMs:120000});
  await refreshLearnedModels();
  note.textContent="Imported "+result.model.name+". Choose it in Scan Setup when you want to use it.";
 }catch(error){note.textContent="Import failed: "+error.message;}
 finally{input.disabled=false;input.value="";}
}
async function removeLearnedModel(id,name){
 if(!confirm("Remove "+name+" from the model library? Existing jobs keep their selected copy."))return;
 const note=document.getElementById("learnedModelStatus");
 try{
  await reviewRequest("api/jobs/learned-models/"+encodeURIComponent(id),{method:"DELETE",timeoutMs:120000});
  await refreshLearnedModels();note.textContent="Removed from the model library.";
 }catch(error){note.textContent="Could not remove model: "+error.message;}
}
async function saveLearnedModel(){
 const job=CUR,view=JOBVIEW;
 const name=document.getElementById("learnedModelName").value.trim();
 const description=document.getElementById("learnedModelDescription").value.trim();
 const candidate_id=document.getElementById("learnedModelSource")?.value||"";
 const note=document.getElementById("saveLearnedModelStatus");
 const button=document.getElementById("saveLearnedModelButton");
 if(!name){note.textContent="Enter a model name.";return;}
 button.disabled=true;note.textContent="Saving selected model...";
 try{
  if(!await saveAndRender(true)){
   if(CUR===job&&JOBVIEW===view)note.textContent="Review changes could not be saved. Resolve the review error and try again.";
   return;
  }
  if(CUR!==job||JOBVIEW!==view)return;
  const {data}=await reviewRequest("api/jobs/"+encodeURIComponent(job)+"/learned-models",
    {method:"POST",headers:{"Content-Type":"application/json"},
     body:JSON.stringify(candidate_id?{name,description,candidate_id}:{name,description}),timeoutMs:120000});
  if(CUR===job&&JOBVIEW===view)note.textContent="Saved "+data.model.name+" to the model library. Select it in Scan Setup for other videos.";
  await refreshLearnedModels();
 }catch(error){if(CUR===job&&JOBVIEW===view)note.textContent="Could not save model: "+error.message;}
 finally{if(button.isConnected)button.disabled=false;}
}

loadPersist();loadCertInfo();loadJobs();refreshLearnedModels();setInterval(loadJobs,5000);
function resumeJobPolling(){
 if(document.hidden)return;
 stopJobPolling();REFRESHFAILURES=0;
 const previous=JOBSFLIGHT;JOBSFLIGHT=null;
 if(previous)previous.controller.abort();
 JOBSFAILURES=0;JOBSRETRYAT=0;
 loadJobs();refresh();
}
document.addEventListener("visibilitychange",()=>{
 if(document.hidden)stopJobPolling();else resumeJobPolling();
});
for(const event of ["focus","pageshow","online"])window.addEventListener(event,resumeJobPolling);
function showView(){
 const s=location.hash==="#settings";
 const f=location.hash==="#findings";
 document.getElementById("mainview").style.display=s||f?"none":"block";
 document.getElementById("settingsview").style.display=s?"block":"none";
 document.getElementById("findingsview").style.display=f?"block":"none";
 if(s){window.scrollTo(0,0);refreshLearnedModels();}
 if(f){window.scrollTo(0,0);loadConfirmedFindings();}
}
window.addEventListener("hashchange",showView);
updCheck();vaultStatus();extrasStatus();showView();
"""

PAGE = (zones_ui.ZONES_PAGE
        .replace("%%FAVICON%%", FAVICON_URI)
        .replace("%%LOGO%%", LOGO_URI)
        .replace("%%WORDMARK%%", WORDMARK_URI)
        .replace("%%APP_CSS%%", APP_CSS + findings_ui.CSS)
        .replace("%%JOBS_HTML%%", JOBS_HTML)
        .replace("%%SETTINGS_HTML%%", SETTINGS_HTML + findings_ui.HTML)
        .replace("%%FOOT_HTML%%", FOOT_HTML)
        .replace("%%APP_JS%%", findings_ui.SCRIPT + APP_JS))


ASSET_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "assets")
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))


# ----------------------------------------------------------------------------
# Self-update (openscrub_update.py does the heavy lifting). The update
# endpoints refuse to run while any job is queued or processing, and an
# installed update only takes effect after the server restarts.
# ----------------------------------------------------------------------------
try:
    import openscrub_update
except Exception:                       # module missing: endpoints degrade
    openscrub_update = None

UPD = {"running": False, "log": [], "ok": None, "cache": (0.0, None)}
UPD_LOCK = threading.Lock()


def _in_container():
    """True inside Docker/Podman. The in-place updater writes into the
    container's ephemeral filesystem — the "update" would vanish on the
    next recreate while the UI claimed success. Containers update by
    pulling the new image, so the web UI must inform, never offer."""
    return (os.environ.get("OPENSCRUB_IN_DOCKER", "") not in ("", "0")
            or os.path.exists("/.dockerenv")
            or os.path.exists("/run/.containerenv"))


@app.route("/api/update_check")
def update_check():
    if openscrub_update is None:
        return jsonify({"current": openscrub.VERSION, "latest": None,
                        "available": False, "can_update": False})
    now = time.time()
    with UPD_LOCK:
        ts, latest = UPD["cache"]
        if now - ts > 6 * 3600 or request.args.get("force"):
            try:
                latest = openscrub_update.get_latest(timeout=6)
            except Exception:
                latest = None       # offline / PyPI down: just no notice
            UPD["cache"] = (now, latest)
    avail = bool(latest and openscrub_update.is_newer(latest["version"],
                                                      openscrub.VERSION))
    return jsonify({"current": openscrub.VERSION,
                    "latest": latest["version"] if latest else None,
                    "available": avail,
                    "can_update": not _in_container()})


@app.route("/api/update_run", methods=["POST"])
def update_run():
    if _in_container():
        abort(400, "running in a container — update by pulling the new "
                   "image and recreating the container (job data lives in "
                   "the mounted volume and is preserved)")
    if openscrub_update is None:
        abort(400, "updater module not available")
    with JOBS_LOCK:
        busy = any(j.get("phase") in ("queued", "scanning", "rendering",
                                      "queued_render", "learning")
                   for j in JOBS.values())
    if busy:
        abort(409, "a job is queued or running — update after it finishes")
    with UPD_LOCK:
        if UPD["running"]:
            return jsonify({"started": False, "reason": "already running"})
        UPD["running"], UPD["log"], UPD["ok"] = True, [], None

    def _go():
        def log(msg):
            with UPD_LOCK:
                UPD["log"].append(str(msg))
        try:
            openscrub_update.run_update(log=log)
            ok = True
        except Exception as e:
            diagnostics.exception("self_update_failed")
            log("update failed: %s" % e)
            ok = False
        with UPD_LOCK:
            UPD["ok"], UPD["running"] = ok, False

    threading.Thread(target=_go, daemon=True).start()
    return jsonify({"started": True})


@app.route("/api/update_status")
def update_status():
    with UPD_LOCK:
        return jsonify({"running": UPD["running"], "ok": UPD["ok"],
                        "log": list(UPD["log"])})


# ----------------------------------------------------------------------------
# Vault: password-based at-rest encryption of the job store (PII!).
# LOCKED = job files encrypted on disk, job APIs refuse to run.
# UNLOCKED = decrypted in place so the pipeline works unchanged.
# NO PASSWORD RESET EXISTS — a lost password means the data is gone.
# ----------------------------------------------------------------------------
import openscrub_vault as vault

VAULT = {"key": None}          # data key while unlocked; None = locked
VAULT_LOCK = threading.Lock()
WEB_SETTINGS_PATH = os.path.join(_data_root(), "web_settings.json")
LAST_ACTIVITY = {"t": time.time()}


def _web_settings():
    try:
        with open(WEB_SETTINGS_PATH, encoding="utf-8") as f:
            return json.load(f)
    except FileNotFoundError:
        return {}
    except Exception:
        diagnostics.exception("settings_load_failed")
        return {}


def _save_web_settings(d):
    with open(WEB_SETTINGS_PATH, "w", encoding="utf-8") as f:
        json.dump(d, f, indent=2)


def _autolock_watcher():
    """Opt-in: when enabled in App settings, re-lock the vault after N
    minutes with no web activity and no running jobs. Default OFF —
    people should never find their data locked unless they asked for it."""
    while True:
        time.sleep(30)
        try:
            mins = int(_web_settings().get("vault_autolock_min", 0) or 0)
            if mins <= 0 or not vault_enabled() or VAULT["key"] is None:
                continue
            if time.time() - LAST_ACTIVITY["t"] < mins * 60:
                continue
            with JOBS_LOCK:
                busy = any(j.get("phase") in ("queued", "scanning",
                                              "rendering", "queued_render", "learning")
                           for j in JOBS.values())
            if busy:
                continue
            n = _vault_lock_now()
            print("vault: auto-locked after %d idle minute(s) — "
                  "%d file(s) encrypted" % (mins, n))
        except Exception:
            diagnostics.exception("vault_autolock_failed")


def vault_enabled():
    return vault.keystore_exists(_data_root())


def vault_locked():
    return vault_enabled() and VAULT["key"] is None


def _vault_lock_now():
    """Encrypt the job store and forget the key. Returns files encrypted."""
    with VAULT_LOCK:
        key = VAULT["key"]
        if key is None:
            return 0
        with _REVIEW_EDIT_LOCK, _REVIEW_WORK_LOCK:
            with _REVIEW_CACHE_LOCK:
                _REVIEW_FRAMES.clear()
                _REVIEW_PROBES.clear()
                _REVIEW_REPORTS.clear()
                # Cached crop readers do not take the decoder gate. Keep their
                # cache gate held until encryption and the locked state agree.
                n = vault.encrypt_tree(key, JOBS_DIR)
                VAULT["key"] = None
        return n


def _vault_lock_atexit():
    try:
        if vault_enabled() and VAULT["key"] is not None:
            busy = any(j.get("phase") in ("queued", "scanning", "rendering",
                                          "queued_render", "learning") for j in JOBS.values())
            if busy:
                diagnostics.event("vault_not_locked_active_jobs", level=40)
                print("vault: NOT locking on exit — a job was still running; "
                      "job files remain in plaintext. Restart and lock.")
                return
            n = _vault_lock_now()
            print("vault: locked on shutdown (%d file(s) encrypted)" % n)
    except Exception as e:
        diagnostics.exception("vault_shutdown_lock_failed")
        # never die silently here: a swallowed error means plaintext on disk
        print("vault: LOCK ON SHUTDOWN FAILED (%s) — job files may remain "
              "in plaintext. Restart the server and use the Lock button." % e)


@app.route("/api/vault")
def vault_status():
    enc, plain = (0, 0)
    if vault_enabled():
        enc, plain = vault.tree_locked_state(JOBS_DIR)
    return jsonify({"enabled": vault_enabled(), "locked": vault_locked(),
                    "encrypted_files": enc, "plaintext_files": plain,
                    "autolock_min": int(_web_settings().get(
                        "vault_autolock_min", 0) or 0)})


@app.route("/api/vault/setup", methods=["POST"])
def vault_setup():
    pw = (request.json or {}).get("password") or ""
    if vault_enabled():
        abort(409, "vault already set up")
    if len(pw) < 8:
        abort(400, "password must be at least 8 characters")
    with VAULT_LOCK:
        VAULT["key"] = vault.create_keystore(_data_root(), pw)
    return jsonify({"ok": True, "note":
                    "Encryption enabled. Jobs encrypt when you lock or "
                    "shut down. LOSING THIS PASSWORD MAKES THE ENCRYPTED "
                    "FILES PERMANENTLY UNRECOVERABLE."})


@app.route("/api/vault/unlock", methods=["POST"])
def vault_unlock():
    pw = (request.json or {}).get("password") or ""
    if not vault_enabled():
        abort(400, "vault is not set up")
    try:
        key = vault.open_keystore(_data_root(), pw)
    except ValueError:
        abort(403, "wrong password")
    with VAULT_LOCK:
        VAULT["key"] = key
        n = vault.decrypt_tree(key, JOBS_DIR)
    rehydrate_jobs()               # pick up jobs that were locked at startup
    return jsonify({"ok": True, "decrypted": n})


# ----------------------------------------------------------------------------
# Optional engines (spaCy NER, PaddleOCR) — installable from the web UI on
# pip/folder installs. Frozen (Program Files) builds have no pip, so the
# endpoints report that instead of pretending.
# ----------------------------------------------------------------------------
# ----------------------------------------------------------------------------
# Custom regex categories — user-defined, stored in the data root, injected
# into the category checkboxes, job args, and the zones page.
# ----------------------------------------------------------------------------
CUSTOM_CATS_PATH = os.path.join(_data_root(), "custom_categories.json")
BUILTIN_CATS = {"name", "dob", "phone", "ssn", "mrn", "email", "address",
                "card", "apikey", "ipaddr", "plate", "face", "person",
                "qrcode", "screen", "anytext", "manual", "bank", "crypto",
                "passport"}


def load_custom_cats():
    try:
        with open(CUSTOM_CATS_PATH, encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return []


def _cat_color(cid):
    import colorsys, hashlib
    h = int(hashlib.sha256(cid.encode()).hexdigest()[:6], 16) / 0xFFFFFF
    r, g, b = colorsys.hls_to_rgb(h, 0.45, 0.75)
    return "#%02x%02x%02x" % (int(r * 255), int(g * 255), int(b * 255))


@app.route("/api/custom_cats", methods=["GET", "POST"])
def custom_cats():
    cats = load_custom_cats()
    if request.method == "GET":
        return jsonify(cats)
    d = request.json or {}
    name = (d.get("name") or "").strip()
    pattern = (d.get("regex") or "").strip()
    if not name:
        abort(400, "the category needs a name")
    cid = "".join(ch for ch in name.lower().replace(" ", "_")
                  if ch.isalnum() or ch == "_")[:24]
    if not cid:
        abort(400, "name must contain letters or digits")
    if cid in BUILTIN_CATS or any(c["id"] == cid for c in cats):
        abort(409, "a category with that name already exists")
    try:
        import re as _re
        _re.compile(pattern)
    except Exception as e:
        abort(400, "invalid regex: %s" % e)
    if not pattern:
        abort(400, "a regex pattern is required")
    cats.append({"id": cid, "label": name, "regex": pattern,
                 "color": _cat_color(cid)})
    with open(CUSTOM_CATS_PATH, "w", encoding="utf-8") as f:
        json.dump(cats, f, indent=2)
    return jsonify({"ok": True, "id": cid})


@app.route("/api/custom_cats/<cid>", methods=["DELETE"])
def custom_cats_delete(cid):
    cats = [c for c in load_custom_cats() if c["id"] != cid]
    with open(CUSTOM_CATS_PATH, "w", encoding="utf-8") as f:
        json.dump(cats, f, indent=2)
    return jsonify({"ok": True})


def _spec(name):
    import importlib.util
    try:
        return importlib.util.find_spec(name) is not None
    except Exception:
        return False


EXTRAS = {
    "ner": {
        "label": "spaCy NER (name detection)",
        "desc": "The primary name detector. Without it, names rely on "
                "the built-in heuristics.",
        "pip": ["spacy"],
        "post": [["-m", "spacy", "download", "en_core_web_sm"]],
        "check": lambda: _spec("spacy") and _spec("en_core_web_sm"),
    },
    "paddle": {
        "label": "PaddleOCR — CPU (better OCR on small fonts)",
        "desc": "Stronger OCR engine, picked automatically once "
                "installed. Large download.",
        "pip": ["paddleocr", "paddlepaddle"],
        "post": [],
        "check": lambda: _spec("paddleocr") and _spec("paddle"),
    },
    "paddle_gpu": {
        "label": "PaddleOCR — NVIDIA GPU (CUDA 12.x)",
        "desc": "GPU-accelerated build for NVIDIA cards — much faster "
                "OCR. Very large download. Shows installed if either "
                "Paddle build is present.",
        "pip": ["paddleocr", "paddlepaddle-gpu==3.2.2", "-i",
                "https://www.paddlepaddle.org.cn/packages/stable/cu126/"],
        "post": [["-m", "pip", "install", "-U", "nvidia-cudnn-cu12"]],
        "check": lambda: _spec("paddleocr") and _spec("paddle"),
    },
}
_EXT = {"state": "idle", "target": "", "log": []}


@app.route("/api/extras")
def extras_status():
    frozen = bool(getattr(sys, "frozen", False))
    items = [{"id": k, "label": v["label"], "desc": v["desc"],
              "installed": (False if frozen else v["check"]())}
             for k, v in EXTRAS.items()]
    return jsonify({"frozen": frozen, "items": items,
                    "state": _EXT["state"], "target": _EXT["target"],
                    "log": _EXT["log"][-4:]})


@app.route("/api/extras/<eid>/install", methods=["POST"])
def extras_install(eid):
    if getattr(sys, "frozen", False):
        abort(400, "this is a standalone (Program Files) install without "
                   "pip — optional engines need the pip install of "
                   "OpenScrub")
    spec = EXTRAS.get(eid) or abort(404)
    if _EXT["state"] == "installing":
        abort(409, "another install is already running")
    _EXT.update(state="installing", target=eid, log=[])

    def work():
        import subprocess
        try:
            cmds = [[sys.executable, "-m", "pip", "install"] + spec["pip"]]
            cmds += [[sys.executable] + p for p in spec["post"]]
            for cmd in cmds:
                _EXT["log"].append("$ " + " ".join(cmd[1:]))
                r = subprocess.run(cmd, capture_output=True, text=True)
                if r.returncode != 0:
                    tail = (r.stderr or r.stdout or "").strip().splitlines()
                    _EXT["log"] += tail[-3:] or ["exit %d" % r.returncode]
                    _EXT["state"] = "error"
                    return
            _EXT["log"].append("done — takes effect on the next scan")
            _EXT["state"] = "done"
        except Exception as e:
            diagnostics.exception("optional_dependency_install_failed")
            _EXT["log"].append(str(e))
            _EXT["state"] = "error"
    threading.Thread(target=work, daemon=True).start()
    return jsonify({"ok": True})


@app.route("/api/vault/autolock", methods=["POST"])
def vault_autolock():
    mins = int((request.json or {}).get("minutes") or 0)
    if mins < 0 or mins > 24 * 60:
        abort(400, "minutes must be between 0 (off) and 1440")
    d = _web_settings()
    d["vault_autolock_min"] = mins
    _save_web_settings(d)
    return jsonify({"ok": True, "autolock_min": mins})


@app.route("/api/vault/lock", methods=["POST"])
def vault_lock_route():
    with JOBS_LOCK:
        busy = any(j.get("phase") in ("queued", "scanning", "rendering",
                                      "queued_render", "learning")
                   for j in JOBS.values())
    if busy:
        abort(409, "a job is queued or running — lock after it finishes")
    n = _vault_lock_now()
    return jsonify({"ok": True, "encrypted": n})


@app.route("/license")
def license_page():
    p = os.path.join(SCRIPT_DIR, "LICENSE")
    if os.path.exists(p):
        with open(p, encoding="utf-8") as f:
            body = f.read()
    else:
        body = ("OpenScrub is licensed under the Apache License 2.0.\n"
                "See https://www.apache.org/licenses/LICENSE-2.0")
    from flask import Response
    return Response(body, mimetype="text/plain")


@app.route("/logo.png")
def logo():
    p = os.path.join(ASSET_DIR, "logo.png")
    if not os.path.exists(p):
        abort(404)
    return send_file(p,
                     mimetype="image/png", max_age=86400)


@app.route("/logo_dark.png")
def logo_dark():
    p = os.path.join(ASSET_DIR, "logo_dark.png")
    if not os.path.exists(p):
        abort(404)
    return send_file(p,
                     mimetype="image/png", max_age=86400)


@app.route("/favicon.ico")
def favicon():
    p = os.path.join(ASSET_DIR, "openscrub.ico")
    if not os.path.exists(p):
        abort(404)
    return send_file(p,
                     mimetype="image/x-icon", max_age=86400)


@app.route("/")
def index():
    # inject user-defined categories into the editor's color map so they can
    # be zoned exactly like built-ins (per request: customs change at runtime)
    page = PAGE
    extra = "".join(',%s:"%s"' % (c["id"], c.get("color", "#64748b"))
                    for c in load_custom_cats())
    if extra:
        page = page.replace('face:"#ec4899"', 'face:"#ec4899"%s' % extra)
    page = page.replace("%%MAXUP%%",
                        str(app.config.get("MAX_CONTENT_LENGTH") or 0))
    # free disk at serve time, so the editor can refuse an upload that
    # cannot fit BEFORE hours of transfer (issue #16: repeated 18 GB
    # re-uploads filled the disk). The server-side guard on POST
    # /api/jobs stays authoritative — this is only the early warning.
    try:
        free = _disk_free(JOBS_DIR)
    except OSError:
        free = 0                       # unknown -> preflight disabled
    page = page.replace("%%FREEDISK%%", str(free))
    return page.replace("%%VERSION%%", openscrub.VERSION)


@app.route("/zones")
def zones_page():
    """The editor IS the homepage now; keep old bookmarks working."""
    return redirect("/")


@app.route("/api/server_video")
def server_video():
    """Stream a server-side video for the Scan Setup preview. The path is
    request data: the same server_path_error confinement that gates job
    intake runs BEFORE any filesystem access. conditional=True gives Range
    support so the <video> element can seek/scrub."""
    p = os.path.realpath(request.args.get("path", ""))
    err = server_path_error(p)
    if err:
        return jsonify({"error": err}), 400
    # Containment guard REPEATED inline: server_path_error already enforces
    # it, but CodeQL's path-injection barrier analysis is function-local —
    # the sink below must be dominated by the single-startswith shape in
    # THIS function or the alert re-opens (same lesson as the models route).
    root = os.environ.get("OPENSCRUB_MEDIA_ROOT")
    r = os.path.realpath(root) if root else os.path.realpath(
        os.path.splitdrive(p)[0] + os.sep)
    if not p.startswith(r.rstrip(os.sep) + os.sep):
        return jsonify({"error": "server path is outside OPENSCRUB_MEDIA_ROOT"}), 400
    return send_file(p, conditional=True)


@app.route("/api/waveform")
def waveform():
    """Audio peak envelope for a server-side video's track — powers the
    editor's waveform lanes. Same confinement as every server-path route:
    server_path_error runs first, and the containment guard is repeated
    inline in the CodeQL-recognized shape before any use."""
    p = os.path.realpath(request.args.get("path", ""))
    err = server_path_error(p)
    if err:
        return jsonify({"error": err}), 400
    root = os.environ.get("OPENSCRUB_MEDIA_ROOT")
    r = os.path.realpath(root) if root else os.path.realpath(
        os.path.splitdrive(p)[0] + os.sep)
    if not p.startswith(r.rstrip(os.sep) + os.sep):
        return jsonify({"error": "server path is outside OPENSCRUB_MEDIA_ROOT"}), 400
    try:
        track = max(0, min(15, int(request.args.get("track", 0) or 0)))
    except ValueError:
        track = 0
    import subprocess
    import numpy as np
    try:
        raw = subprocess.run(
            ["ffmpeg", "-v", "error", "-i", p, "-map", "a:%d" % track,
             "-ac", "1", "-ar", "1000", "-f", "s16le", "-"],
            capture_output=True, timeout=180).stdout
    except Exception:
        diagnostics.exception("waveform_extraction_failed")
        raw = b""
    if len(raw) < 4:
        return jsonify({"peaks": []})
    a = np.abs(np.frombuffer(raw[:len(raw) // 2 * 2], dtype=np.int16)
               .astype(np.int32))
    N = 2000
    per = max(1, len(a) // N)
    a = a[:(len(a) // per) * per].reshape(-1, per).max(axis=1)
    mx = int(a.max()) or 1
    return jsonify({"peaks": [round(float(v) / mx, 3) for v in a[:N]]})


@app.route("/api/certinfo")
def certinfo():
    cert_path, _, mode = active_cert_pair()
    from cryptography import x509
    with open(cert_path, "rb") as f:
        c = x509.load_pem_x509_certificate(f.read())
    return jsonify({
        "mode": mode,
        "subject": c.subject.rfc4514_string(),
        "issuer": c.issuer.rfc4514_string(),
        "expires": c.not_valid_after_utc.strftime("%Y-%m-%d"),
    })


@app.route("/api/certs", methods=["POST", "DELETE"])
def upload_certs():
    if request.method == "DELETE":
        for p in (CUSTOM_CERT, CUSTOM_KEY):
            if os.path.exists(p):
                os.remove(p)
        return jsonify({"ok": True,
                        "note": "custom certificate removed — restart the "
                                "server to return to the self-signed one"})
    cert_f, key_f = request.files.get("cert"), request.files.get("key")
    if not cert_f or not key_f:
        abort(400, "both certificate and key PEM files are required")
    cert_pem, key_pem = cert_f.read(), key_f.read()
    from cryptography import x509
    from cryptography.hazmat.primitives.serialization import load_pem_private_key
    try:
        cert = x509.load_pem_x509_certificate(cert_pem)
        key = load_pem_private_key(key_pem, password=None)
        if key.public_key().public_numbers() != cert.public_key().public_numbers():
            abort(400, "private key does not match the certificate")
    except ValueError as e:
        abort(400, f"could not parse PEM files: {e}")
    os.makedirs(CERT_DIR, exist_ok=True)
    with open(CUSTOM_CERT, "wb") as f:
        f.write(cert_pem)
    with open(CUSTOM_KEY, "wb") as f:
        f.write(key_pem)
    try:
        os.chmod(CUSTOM_KEY, 0o600)
    except Exception:
        pass
    return jsonify({"ok": True,
                    "note": "certificate installed — restart the server to apply"})


@app.route("/api/zones", methods=["GET", "POST"])
def api_zones():
    if request.method == "POST":
        data = request.get_json(force=True) or {}
        clean = {}
        for cat, rects in data.items():
            rs = []
            for r in rects or []:
                if len(r) == 4:
                    x1, y1, x2, y2 = [max(0.0, min(1.0, float(v))) for v in r]
                    if x2 - x1 > 0.004 and y2 - y1 > 0.004:
                        rs.append([round(x1, 4), round(y1, 4),
                                   round(x2, 4), round(y2, 4)])
            if rs:
                clean[cat] = rs
        with open(ZONES_PATH, "w", encoding="utf-8") as f:
            json.dump(clean, f, indent=1)
        return jsonify({"ok": True, "classes": len(clean)})
    if os.path.exists(ZONES_PATH):
        with open(ZONES_PATH, encoding="utf-8") as f:
            return jsonify(json.load(f))
    return jsonify({})


def lan_ip():
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.connect(("8.8.8.8", 80))
        ip = s.getsockname()[0]
        s.close()
        return ip
    except Exception:
        return "127.0.0.1"


def rehydrate_jobs():
    """Re-register jobs found on disk after a restart. A job with a report
    is a reviewable job; one with an output file is a finished one — either
    way the person's work survives the server going down."""
    n = 0
    for jid in sorted(os.listdir(JOBS_DIR)):
        if jid in findings_web.RESERVED:
            continue
        jdir = os.path.join(JOBS_DIR, jid)
        rep = os.path.join(jdir, "report.json")
        if not os.path.isdir(jdir):
            continue
        if os.path.exists(os.path.join(jdir, DELETE_MARKER)):
            # the user deleted this job but a file was still held open at
            # the time — finish the removal instead of resurrecting the
            # job as a zombie (restarts release whatever held the lock)
            _reap_job_dir(jdir, jid, retries=1)
            continue
        if jid in JOBS:
            continue
        if not os.path.exists(rep):
            recovered_training = findings_web.recover_training(jid, jdir)
            if recovered_training:
                with JOBS_LOCK:
                    JOBS[jid] = recovered_training
                n += 1
                continue
            from pathlib import Path
            recovered_section = _SECTIONS.restore_interrupted(jid, Path(jdir))
            if recovered_section:
                _recover_plate_model(recovered_section)
                with JOBS_LOCK:
                    JOBS[jid] = recovered_section
                n += 1
                continue
            # NO report: the scan never completed (crashed or the server
            # went down mid-scan). If the dir still holds an uploaded
            # input, surface it as a FAILED job instead of skipping it —
            # a skipped dir was an invisible orphan the UI could neither
            # retry nor delete, silently eating an 18 GB upload per
            # failed attempt (issue #16).
            up = next((os.path.join(jdir, "input" + e)
                       for e in sorted(MEDIA_EXTS)
                       if os.path.exists(os.path.join(jdir, "input" + e))),
                      None)
            if not up:
                continue
            try:
                size = os.path.getsize(up)
            except OSError:
                size = 0
            job = {
                "id": jid, "dir": jdir, "video": up,
                "name": os.path.basename(up), "options": {},
                "phase": "error", "progress": 0.0, "size": size,
                "log": ["(recovered after server restart — the scan had "
                        "not completed)"],
                "error": "recovered after a server restart before the "
                         "scan finished — Retry re-runs it with default "
                         "settings (the uploaded file was kept), or "
                         "Delete frees its disk space",
                "output": None, "created": os.path.getmtime(jdir),
                "cancel": threading.Event(), "stop": threading.Event(),
                "stats": {},
            }
            if os.path.lexists(os.path.join(jdir, "plate_model")):
                # A snapshot is published before queueing, even if a restart
                # happened before the first report. Keep selection fail-closed
                # if that copy is damaged; Retry must not silently omit it.
                job["options"]["learned_plate_model"] = "unavailable"
                try:
                    selected, _ = learned_models.load_snapshot(jdir)
                    mode = learned_models.load_selection(jdir, selected)
                except learned_models.ModelError as error:
                    job["error"] = ("Recovered upload, but its selected learned model "
                                    "copy is unavailable: %s. Start a new scan with "
                                    "a valid model; the uploaded file was kept." % error)
                else:
                    job["options"]["learned_plate_model"] = selected["id"]
                    job["options"]["learned_plate_model_mode"] = mode
                    job["refinement"] = selected
                    job["error"] = ("Recovered before the scan finished. Retry uses "
                                    "the saved learned model and default settings for "
                                    "other options; the uploaded file was kept.")
                    job["log"].append("Pinned learned model recovered: " + selected["name"])
            with JOBS_LOCK:
                JOBS[jid] = job
            n += 1
            continue
        try:
            with open(rep, encoding="utf-8") as f:
                report_doc = json.load(f)
            prov = report_doc.get("provenance", {})
            checkpoint = report_doc.get("stop_review") or {}
            video = prov.get("input")
            if not video or not os.path.exists(video):
                continue
            out = os.path.join(jdir, "output.mp4")
            has_out = (os.path.exists(out) and not report_doc.get("render_required")
                       and not (report_doc.get("learning") or {}).get("needs_render"))
            job = {
                "id": jid, "dir": jdir, "video": video,
                "name": os.path.basename(prov.get("original_input")
                                          or video),
                "options": prov.get("settings", {}) or {},
                "phase": ("paused" if checkpoint.get("state") == "paused"
                          else "done" if has_out else "review"),
                "progress": 1.0 if has_out else 0.5,
                "log": ["(recovered after server restart)"],
                "error": None, "output": out if has_out else None,
                "created": os.path.getmtime(jdir),
                "cancel": threading.Event(), "stop": threading.Event(),
                "checkpoint_frame": checkpoint.get("next_frame"),
                "checkpoint_total": checkpoint.get("total_frames"),
                "stats": {},
            }
            if report_doc.get("refinement"):
                job["refinement"] = report_doc["refinement"]
                job["options"]["learned_plate_model"] = report_doc["refinement"]["id"]
            if report_doc.get("verification"):
                job["verification"] = report_doc["verification"]
            if report_doc.get("verification_history"):
                job["verification_history"] = report_doc["verification_history"]
            _SECTIONS.recover(job, report_doc)
            if checkpoint.get("state") == "paused":
                job["options"] = checkpoint.get("options") or {}
                job["log"].append("Stop & Review checkpoint recovered; "
                                  "resume starts from saved frame")
            _recover_plate_model(job)
            try:
                # original upload size, for the editor's duplicate-upload
                # warning (prov input may be the normalized scan copy)
                orig = next((os.path.join(jdir, "input" + e)
                             for e in sorted(MEDIA_EXTS)
                             if os.path.exists(
                                 os.path.join(jdir, "input" + e))), video)
                job["size"] = os.path.getsize(orig)
            except OSError:
                pass
            with JOBS_LOCK:
                JOBS[jid] = job
            n += 1
        except Exception:
            diagnostics.exception("job_recovery_failed", recovered_job_id=jid)
            continue
    if n:
        diagnostics.event("jobs_recovered", count=n)
        print(f"  recovered {n} job(s) from {JOBS_DIR}")


def retention_sweep(days):
    import shutil as _sh
    if vault_locked():
        # Persisted section/source links cannot be checked while encrypted.
        return
    cutoff = time.time() - days * 86400
    for jid in os.listdir(JOBS_DIR):
        if jid in findings_web.RESERVED:
            continue
        retained = JOBS.get(jid)
        if (_SECTIONS.deletion_error({'id': jid}) or
                (retained and retained.get("section")) or
                os.path.isfile(os.path.join(JOBS_DIR, jid, 'section-job.json'))):
            continue
        p = os.path.join(JOBS_DIR, jid)
        if not os.path.isdir(p):
            continue
        if os.path.exists(os.path.join(p, DELETE_MARKER)):
            _reap_job_dir(p, jid, retries=1)     # condemned: age-independent
            continue
        if os.path.getmtime(p) < cutoff:
            _sh.rmtree(p, ignore_errors=True)
            with JOBS_LOCK:
                JOBS.pop(jid, None)


def retention_loop(days):
    while True:
        retention_sweep(days)
        time.sleep(6 * 3600)


def main():
    global TOKEN
    ap = argparse.ArgumentParser()
    ap.add_argument("--port", type=int, default=8384)
    ap.add_argument("--host", default="0.0.0.0")
    ap.add_argument("--token",
                    default=os.environ.get("OPENSCRUB_TOKEN") or None,
                    help="require this access token on every "
                    "request (default: open — anyone on the network can use "
                    "the server)")
    ap.add_argument("--http", action="store_true",
                    help="serve plain HTTP (not recommended: video uploads "
                         "and previews contain PII and would cross the "
                         "network unencrypted)")
    ap.add_argument("--retain-days", type=int, default=7,
                    help="auto-delete job folders (which contain PII) after "
                         "this many days (default 7; 0 = keep forever)")
    ap.add_argument("--max-upload-gb", default=None,
                    help="largest browser upload accepted, in GB (default 8; "
                         "0 = unlimited; env OPENSCRUB_MAX_UPLOAD_GB works "
                         "too). Very large files are better served in place "
                         "via the 'path on the server' box than uploaded.")
    args = ap.parse_args()
    TOKEN = args.token or None
    diagnostics.set_secrets([TOKEN])
    diagnostics.configure(_data_root())
    diagnostics.event("server_starting", version=openscrub.VERSION, python=sys.version.split()[0],
                      port=args.port, transport="http" if args.http else "https")
    app.config["MAX_CONTENT_LENGTH"] = _max_upload_bytes(args.max_upload_gb)
    os.makedirs(JOBS_DIR, exist_ok=True)
    import atexit
    atexit.register(_vault_lock_atexit)
    # docker stop sends SIGTERM. Python's default SIGTERM disposition kills
    # the process WITHOUT running atexit hooks — and as PID 1 in a container
    # an unhandled SIGTERM is ignored outright, so the container just waits
    # out the grace period and gets SIGKILLed: either way the vault never
    # locked and job files stayed in plaintext (verified empirically).
    # sys.exit() is NOT enough here — cheroot's serve loop swallows the
    # SystemExit (also verified) — so the handler locks the vault itself and
    # then hard-exits. os._exit skips atexit, so the lock cannot run twice.
    # NOTE: encryption must finish within the stop grace period — give
    # Docker a generous one (docker stop -t 120).
    import signal
    _terming = []

    def _on_sigterm(sig, frm):
        if _terming:                      # second SIGTERM: just die
            os._exit(1)
        _terming.append(1)
        print("SIGTERM — locking vault before exit…")
        diagnostics.event("server_sigterm", signal=sig)
        _vault_lock_atexit()
        diagnostics.shutdown(clean=True)
        os._exit(0)
    signal.signal(signal.SIGTERM, _on_sigterm)
    threading.Thread(target=_autolock_watcher, daemon=True).start()
    rehydrate_jobs()
    threading.Thread(target=worker, name="openscrub-job-worker", daemon=True).start()
    if args.retain_days > 0:
        threading.Thread(target=retention_loop, args=(args.retain_days,),
                         daemon=True).start()
    print("=" * 60)
    ssl_ctx = None
    scheme = "http"
    if not args.http:
        try:
            import cryptography  # noqa: F401 — needed for cert generation
        except ImportError:
            diagnostics.exception("https_dependency_missing")
            print("=" * 60)
            print("HTTPS needs the 'cryptography' package, which isn't")
            print("installed. Fix it with ONE of these:")
            print()
            print("    pip install cryptography      (recommended)")
            print("    python install.py --yes       (installs everything)")
            print()
            print("or start with --http to serve unencrypted")
            print("(not recommended: PII would cross the network in plain text).")
            print("=" * 60)
            if os.name == "nt":
                input("Press Enter to close.")
            sys.exit(1)
        cert, key, mode = active_cert_pair()
        ssl_ctx = (cert, key)
        scheme = "https"
    in_docker = _in_container()
    # Inside a container lan_ip() returns the CONTAINER's bridge address
    # (172.17.x.x) — unreachable from a macOS/Windows host, where only the
    # published port on localhost works. A real Mac user followed that IP
    # straight to a dead end while the server sat healthy on localhost:8384
    # (and Python's block-buffered stdout kept this whole banner invisible
    # in `docker logs` — the images now set PYTHONUNBUFFERED=1).
    url_host = "localhost" if in_docker else lan_ip()
    print("openscrub web — open from any device on your LAN:")
    if TOKEN:
        print(f"    {scheme}://{url_host}:{args.port}/?token={TOKEN}")
    else:
        print(f"    {scheme}://{url_host}:{args.port}/")
        print("    (open access: no token — everyone on this network can use it;")
        print("     add --token <secret> if you ever want a gate back)")
    if in_docker:
        print("    Docker: open the PUBLISHED port on localhost (or this")
        print("    machine's LAN IP from other devices). The container's")
        print("    internal 172.17.x.x address is NOT reachable from a")
        print("    Mac/Windows host.")
    if vault_enabled():
        print("Encryption: vault is LOCKED — unlock in the web UI "
              "(Encryption panel) to access jobs."
              if vault_locked() else "Encryption: vault unlocked.")
    print("Jobs folder (contains PII):", JOBS_DIR,
          f"— auto-deleted after {args.retain_days} day(s)" if args.retain_days else "— kept forever")
    print("Do NOT expose this port to the internet.")
    print("=" * 60)
    if ssl_ctx:
        if mode == "self-signed":
            print("    HTTPS with a self-signed certificate: your browser will")
            print("    warn once — choose Advanced -> Proceed, or install your")
            print("    own certificate at the bottom of the main page.")
        else:
            print("    HTTPS with your installed custom certificate.")
    else:
        print("    WARNING: plain HTTP — PII crosses the network unencrypted.")
    sys.stdout.flush()      # the banner must reach redirected logs NOW, not
    # when an 8KB block buffer eventually fills (a container ran "silent"
    # for minutes and the user debugged a healthy server)
    try:
        _serve(args.host, args.port, ssl_ctx)
    except BaseException:
        diagnostics.exception("server_serve_failed")
        # Keep diagnostics alive for the existing atexit vault-lock handler.
        # The unclean marker is retained by the logging atexit hook.
        raise
    else:
        _vault_lock_atexit()
        diagnostics.shutdown(clean=True)


def _serve(host, port, ssl_ctx):
    """Run under cheroot (a production WSGI server that supports TLS and
    Windows) when available; otherwise fall back to Flask's built-in dev
    server, which works fine for a small LAN but prints a warning."""
    try:
        from cheroot.wsgi import Server
    except ImportError:
        diagnostics.event("production_server_missing_using_flask", level=30)
        print("    (running on Flask's built-in server — `pip install cheroot`")
        print("     to switch to a production server and silence its warning)")
        app.run(host=host, port=port, threaded=True, ssl_context=ssl_ctx)
        return
    # A browser opens several connections per host (Safari preconnects up to
    # ~6), and each idle keep-alive connection holds a cheroot worker until
    # it times out — so the pool needs headroom well past one browser's
    # connection count or real requests queue behind idle sockets. 16 was
    # tight enough that a phone plus a laptop could stall; 64 is ample and
    # cheroot worker threads are cheap.
    server = Server((host, port), app, server_name="openscrub",
                    numthreads=64)
    # Cheroot's default stderr-only logger bypasses the persistent app log.
    def _quiet_log(msg="", level=20, traceback=False):
        # Retain server errors even when the browser disconnects or TLS fails.
        diagnostics.event("wsgi_server_error", level=max(30, level),
                          message=msg, exc_info=sys.exc_info() if traceback and sys.exc_info()[0] else None)

    server.error_log = _quiet_log
    if ssl_ctx:
        from cheroot.ssl.builtin import BuiltinSSLAdapter

        class RedirectingTLS(BuiltinSSLAdapter):
            """When a browser sends plain HTTP to the TLS port (user typed
            http:// or left the scheme off), answer with a redirect to the
            https URL instead of cheroot's default 400 error page."""
            redirect_url = "https://%s:%d/" % (lan_ip(), port)

            def wrap(self, sock):
                # peek the first byte before TLS: a real TLS ClientHello
                # starts with 0x16; anything else is plaintext HTTP (user
                # typed http://) and gets a redirect to the https URL.
                #
                # The peek MUST NOT block. cheroot runs this on a worker
                # thread, and a blocking recv() parks that thread until the
                # client sends data. Normal Safari (unlike Private mode)
                # opens speculative *preconnect* sockets that finish the TCP
                # handshake but delay their first byte — each blocking peek
                # would wedge a worker, and enough of them starve the whole
                # 16-thread pool so real requests never get served (the
                # "loads over and over, never finishes" bug; Private mode has
                # no preconnect so it's unaffected). A plaintext HTTP client
                # sends "GET ..." immediately, so its bytes are already in
                # the buffer here; a near-instant select catches that. If no
                # byte is ready yet we assume TLS and hand straight to
                # cheroot's normal handshake path — exactly how preconnects
                # behaved before this adapter existed, so there's no
                # starvation and no regression.
                from cheroot import errors as _cherr
                import select as _select
                try:
                    ready = _select.select([sock], [], [], 0.1)[0]
                    first = sock.recv(1, socket.MSG_PEEK) if ready else b""
                except OSError:
                    first = b""
                if first and first[0] != 0x16:
                    try:
                        sock.sendall((
                            "HTTP/1.1 301 Moved Permanently\r\n"
                            "Location: %s\r\n"
                            "Content-Length: 0\r\n"
                            "Connection: close\r\n\r\n"
                            % self.redirect_url).encode())
                    except OSError:
                        pass
                    raise _cherr.FatalSSLAlert(
                        "plain HTTP redirected to %s" % self.redirect_url)
                # Bound the TLS handshake itself. A bare TCP preconnect that
                # completes the socket connect but never sends a ClientHello
                # would otherwise park this worker thread in the handshake
                # read forever — just six of them (a normal Safari per-host
                # count) starve the 16-thread pool and real requests never
                # get served. A short timeout frees the thread; a genuine
                # handshake finishes in well under a second even on mobile.
                # cheroot resets the socket timeout for request handling.
                try:
                    sock.settimeout(4.0)
                except OSError:
                    pass
                return super().wrap(sock)

        server.ssl_adapter = RedirectingTLS(ssl_ctx[0], ssl_ctx[1])
    try:
        server.start()
    except KeyboardInterrupt:
        server.stop()


import section_workflow
_SECTIONS = section_workflow.Sections(sys.modules[__name__])
_SECTIONS.register(app)
for _endpoint in ("job_learning", "job_learning_rollback", "job_retry", "job_resume", "job_render", "job_delete", "job_track_object"):
    app.view_functions[_endpoint] = _serialize_review_edit(app.view_functions[_endpoint])


if __name__ == "__main__":
    try:
        main()
    except SystemExit:
        raise
    except BaseException:
        import traceback
        traceback.print_exc()
        if os.name == "nt":
            input("\nStartup failed — see the error above. Press Enter to close.")
        raise
