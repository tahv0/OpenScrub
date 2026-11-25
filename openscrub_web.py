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
import contextlib
import errno
import hashlib
from io import BytesIO
import base64
import subprocess
import json
import math
import os
import queue
import re
import secrets
import sys
import socket
import stat
import tempfile
import threading
import time
import uuid

import cv2
from flask import (Flask, Response, abort, jsonify, redirect, request, g,
                   send_file, has_request_context)
from werkzeug.exceptions import Conflict

import openscrub
from openscrub_internal.reports import _staged_report, atomic_report
from openscrub_internal.render_delivery import _DeliveryRecoveryError, _has_render_recovery
from openscrub_internal import exact_samples as exact
from openscrub_internal import plate_quads as plate_quad
from openscrub_internal import checkpoints
from openscrub_internal import scan_progress
from openscrub_internal import thumbnails as thumbs
from openscrub_internal import diagnostics
from openscrub_internal.lifetimes import FileOwners, OwnedIterable
from openscrub_internal.job_logs import JobLog
from openscrub_internal.plate_search import worker as plate_search_worker
from openscrub_internal.plate_search.matching import normalize_queries as normalize_plate_queries
import zones_ui


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
    except Exception:
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
app = Flask(__name__)


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


OPTIONS_FILE = "options.json"


class FilesBusy(RuntimeError):
    pass


class _ThumbnailArtifactPending(FilesBusy):
    pass


def _thumbnail_begin_admission_locked(lease):
    FILES.thumbnail_admission += 1
    FILES.thumbnail_resolving.add(lease)


def _thumbnail_resolve_admission(lease, path):
    """Resolve an owned source outside the guard, then fence its inode."""
    try:
        try:
            observed = os.stat(path)
            identity = (observed.st_dev, observed.st_ino)
        except FileNotFoundError:
            identity = None
        with VAULT_LOCK:
            records = []
            by_path = FILES.thumbnail_paths.get(path)
            by_inode = FILES.thumbnail_inodes.get(identity)
            if by_path is not None:
                records.append(by_path)
            if by_inode is not None and by_inode is not by_path:
                records.append(by_inode)
            for record in records:
                _thumbnail_settle_abandoned_claim_locked(record)
            if any(record['claimed'] for record in records):
                raise _ThumbnailArtifactPending()
            for record in records:
                record['protected'] = True
    finally:
        with VAULT_LOCK:
            FILES.thumbnail_resolving.discard(lease)


def _thumbnail_admit_path(path, lease):
    if not path:
        return
    canonical = os.path.realpath(path)
    with VAULT_LOCK:
        source_job = _source_job_locked(canonical)
        if source_job is not None and all(
                token.state is not FILES.initialize(source_job)
                for token in [lease] + lease.related):
            lease.related.append(FILES.reserve(source_job))
        _thumbnail_begin_admission_locked(lease)
    _thumbnail_resolve_admission(lease, canonical)


def _thumbnail_register_stage(job, sequence, path, fd):
    observed = os.fstat(fd)
    canonical = os.path.realpath(path)
    identity = (observed.st_dev, observed.st_ino)
    record = dict(path=canonical, identity=identity, job=job,
                  protected=True, claimed=False)
    with VAULT_LOCK:
        record['authority'] = FILES.thumbnail_authority
        protected = (FILES.thumbnail_admission != sequence
                     or bool(FILES.thumbnail_resolving))
        FILES.thumbnail_paths[canonical] = record
        FILES.thumbnail_inodes[identity] = record
        FILES.initialize(job).thumbnail_artifacts.add(canonical)
        record['protected'] = protected


def _thumbnail_forget_artifact_locked(record):
    FILES.initialize(record['job']).thumbnail_artifacts.discard(record['path'])
    if FILES.thumbnail_paths.get(record['path']) is record:
        del FILES.thumbnail_paths[record['path']]
    if FILES.thumbnail_inodes.get(record['identity']) is record:
        del FILES.thumbnail_inodes[record['identity']]


def _thumbnail_settle_abandoned_claim_locked(record):
    claim = record['claimed']
    if not isinstance(claim, dict):
        return
    batch = claim['batch']
    if batch.retirement.claimed is batch:
        return  # Its worker is still active or its batch is not yet unwound.
    _thumbnail_finish_claim_locked(record)


def _thumbnail_finish_claim_locked(record):
    if record['claimed']['disposition'] != 'failed':
        # Successful or ambiguous removal cannot authorize a later unlink.
        _thumbnail_forget_artifact_locked(record)
    record['claimed'] = False


def _thumbnail_unlink_owned(path, batch):
    # Do not follow a replacement at the owned leaf while finding its receipt.
    canonical = os.path.join(os.path.realpath(os.path.dirname(path)), os.path.basename(path))
    if not VAULT_LOCK.acquire(blocking=False):
        raise OSError('thumbnail cleanup guard busy')
    try:
        record = FILES.thumbnail_paths.get(canonical)
        if record is None:
            return  # Unknown/replaced ownership is preserved, never removed.
        _thumbnail_settle_abandoned_claim_locked(record)
        if FILES.thumbnail_paths.get(canonical) is not record:
            return
        if record['claimed']:
            raise OSError('thumbnail cleanup already claimed')
        if (record.get('authority') is not FILES.thumbnail_authority
                or record['protected'] or FILES.thumbnail_resolving):
            _thumbnail_forget_artifact_locked(record)
            return
        claim = {'batch': batch, 'disposition': 'uncertain'}
        record['claimed'] = claim
    finally:
        VAULT_LOCK.release()
    try:
        try:
            observed = os.stat(path, follow_symlinks=False)
        except FileNotFoundError:
            claim['disposition'] = 'settled'
            return
        if ((observed.st_dev, observed.st_ino) != record['identity']
                or not stat.S_ISREG(observed.st_mode)):
            claim['disposition'] = 'settled'
            return
        os.unlink(path)
        claim['disposition'] = 'settled'
    except OSError:
        claim['disposition'] = 'failed'
        raise
    finally:
        with VAULT_LOCK:
            _thumbnail_finish_claim_locked(record)


def _validate_files_locked(job=None):
    # Admission always rechecks after waiting for the transition guard.
    if vault_locked():
        abort(423, "vault is locked or needs recovery — unlock it to access jobs")
    if job is not None:
        with JOBS_LOCK:
            if not any(current is job for current in JOBS.values()):
                abort(404)
        if FILES.initialize(job).closed:
            abort(409, "job is being deleted")


def _source_job_locked(canonical, missing_ok=False, *, thumbnail_job=None):
    root = os.path.realpath(JOBS_DIR).rstrip(os.sep) + os.sep
    if not canonical.startswith(root):
        return None
    jid = canonical[len(root):].split(os.sep, 1)[0]
    with JOBS_LOCK:
        source_job = JOBS.get(jid)
    if source_job is None:
        if missing_ok:
            return None
        abort(404, "source job is no longer available")
    _validate_files_locked(source_job)
    try:
        _recovery_gate(source_job)
    except Conflict as error:
        if (thumbnail_job is not None and source_job is not thumbnail_job
                and error.description == 'render delivery requires recovery'):
            raise _ThumbnailError('thumbnail_obsolete', 409, 'Containing source changed') from None
        raise
    return source_job


def _reserve_files_locked(job=None, work=False, read_source=True, source=None, *, thumbnail_recovery=False):
    source = (os.path.realpath(source if source is not None else job["video"])
              if read_source and job and (source is not None or job.get("video")) else None)
    source_job = _source_job_locked(source, thumbnail_job=job if thumbnail_recovery else None) if source else None
    lease = FILES.reserve(job, work)
    try:
        lease.source = source
        lease.source_job = source_job
        lease.source_state = FILES.initialize(source_job) if source_job is not None else None
        if source_job is not None and source_job is not job:
            lease.related.append(FILES.reserve(source_job))
        if source:
            _thumbnail_begin_admission_locked(lease)
    except BaseException:
        try:
            lease.release_locked()
        except BaseException:
            pass
        raise
    return lease


def _select_render_input(job, owner):
    """Resolve original-input provenance while the report/current source is owned.

    Only source selection is pinned, not the report document or its edits.
    Missing originals keep the engine's fallback to the current input. An
    extant unregistered/deleting job source is never admitted for reading.
    """
    try:
        doc = _load_job_report(job)
        prov = doc.get("provenance", {}) if isinstance(doc, dict) else {}
        original = prov.get("original_input")
    except (OSError, ValueError, TypeError, AttributeError):
        # Keep asynchronous missing/invalid-report errors in run_pipeline.
        original = None
    if original:
        candidate = os.path.realpath(original)
        added = None
        with VAULT_LOCK:
            _validate_files_locked(job)
            source_job = _source_job_locked(candidate, missing_ok=True)
            root = os.path.realpath(JOBS_DIR).rstrip(os.sep) + os.sep
            if source_job is None and candidate.startswith(root):
                # No live owner exists. Only inspect absence, under the store
                # admission boundary: never open an orphan/condemned source.
                if os.path.exists(candidate):
                    abort(404, "source job is no longer available")
                owner.report_input = True
                return
            if source_job is not None and all(
                    token.state is not FILES.initialize(source_job)
                    for token in [owner] + owner.related):
                added = FILES.reserve(source_job)
                owner.related.append(added)
            _thumbnail_begin_admission_locked(owner)
        selected = False
        try:
            _thumbnail_resolve_admission(owner, candidate)
            # Live containing jobs are reserved BEFORE this first source stat.
            # External filesystem changes remain outside web coordination.
            if os.path.exists(candidate):
                owner.source = candidate
                owner.source_job = source_job
                owner.source_state = FILES.initialize(source_job) if source_job is not None else None
                selected = True
        finally:
            if added is not None and not selected:
                with VAULT_LOCK:
                    owner.related.remove(added)
                    added.release_locked()
    owner.report_input = True


def _request_source_path(path):
    """Canonical path used for both admission and actual server-path I/O."""
    canonical = os.path.realpath(path)
    with VAULT_LOCK:
        source_job = _source_job_locked(canonical)
        if source_job is not None:
            lease = FILES.reserve(source_job)
            lease.source = canonical
            lease.source_job = source_job
            lease.source_state = FILES.initialize(source_job)
            if g.get("file_owner") is None:
                g.file_owner = lease
            else:
                g.setdefault("file_children", []).append(lease)
        else:
            lease = g.get('file_owner')
            if lease is None:
                lease = FILES.reserve()
                g.file_owner = lease
        _thumbnail_begin_admission_locked(lease)
    try:
        _thumbnail_resolve_admission(lease, canonical)
    except _ThumbnailArtifactPending:
        abort(409, 'source cleanup is in progress')
    return canonical


def _job_video(job):
    # Requests use their admitted source even if scan normalization updates
    # the live job while a decoder is waiting. Worker/thread callers snapshot
    # their own lease's source before starting work.
    if has_request_context():
        lease = g.get("file_owner")
        if lease is not None and lease.state is FILES.initialize(job):
            return lease.source or job.get("video")
    return job.get("video")


def _update_job_source(job, path, owner):
    canonical = os.path.realpath(path)
    with VAULT_LOCK:
        _validate_files_locked(job)
        source_job = _source_job_locked(canonical)
        if source_job is not None and source_job is not job:
            # Reserve before following a changed normalized input. This stays
            # with the worker through its final report/provenance access.
            if owner is not None and all(
                    token.state is not FILES.initialize(source_job)
                    for token in [owner] + owner.related):
                owner.related.append(FILES.reserve(source_job))
        if owner is not None:
            _thumbnail_begin_admission_locked(owner)
    if owner is not None:
        _thumbnail_resolve_admission(owner, canonical)
    with VAULT_LOCK:
        _validate_files_locked(job)
        if owner is not None:
                owner.source = canonical
                owner.source_job = source_job
                owner.source_state = FILES.initialize(source_job) if source_job is not None else None
        job["video"] = canonical


def _own_files(job=None, work=False):
    with VAULT_LOCK:
        _validate_files_locked(job)
        lease = _reserve_files_locked(job, work)
    try:
        if lease.source:
            _thumbnail_resolve_admission(lease, lease.source)
        return lease
    except BaseException:
        if job is not None:
            _thumbnail_release_lease(job, lease, primary_pending=True)
        else:
            try:
                lease.release()
            except BaseException:
                pass
        raise


def _files_busy_locked(blocking=True):
    if not JOBS_LOCK.acquire(blocking=blocking):
        return True  # shutdown cannot safely inspect the registry now
    try:
        # Cleanup releases its lease before clearing the active operation.
        # Inspect only existing owners while admission is held, without waiting
        # for a report transaction or constructing a new owner.
        return bool(FILES.count or any(
            j.get("phase") in _ACTIVE_PHASES
            or (j.get("_files") is not None and j["_files"].active is not None)
            for j in JOBS.values()))
    finally:
        JOBS_LOCK.release()


def _start_owned_thread(target, lease):
    def run():
        try:
            target()
        finally:
            lease.release()
    try:
        thread = threading.Thread(target=run, daemon=True)
        thread.start()
        return thread
    except BaseException:
        lease.release()
        raise


def new_job(video_path, options, name, *, _defer_registration=False):
    with _own_files() as owner:
        _thumbnail_admit_path(video_path, owner)
        return _new_job(video_path, options, name, _defer_registration=_defer_registration)


class _CheckpointOptionsError(OSError):
    """Original checkpoint settings could not be made durable."""


def _persist_checkpoint_options(jdir, options):
    """Persist one private options generation before admitting a checkpoint."""
    flags = os.O_RDONLY | getattr(os, 'O_DIRECTORY', 0) | getattr(os, 'O_CLOEXEC', 0)
    with contextlib.ExitStack() as stack:
        directory = os.open(jdir, flags)
        stack.callback(os.close, directory)
        parent = os.open(JOBS_DIR, flags)
        stack.callback(os.close, parent)
        atomic_report(os.path.join(jdir, OPTIONS_FILE), options)
        os.fsync(directory)
        os.fsync(parent)


def _discard_unregistered_checkpoint(job):
    """Remove an unadmitted private directory, or leave the existing reaper marker."""
    if not _reap_job_dir(job['dir'], job['id'], retries=1, delay=0):
        try:
            with open(os.path.join(job['dir'], DELETE_MARKER), 'w') as marker:
                marker.write(str(time.time()))
        except OSError:
            pass


def _register_new_jobs(jobs):
    with VAULT_LOCK:
        with JOBS_LOCK:
            for job in jobs:
                JOBS[job['id']] = job
        if has_request_context() and g.get("file_owner") is not None:
            g.setdefault("file_children", []).extend(FILES.reserve(job, work=True) for job in jobs)


def _new_job(video_path, options, name, *, _defer_registration=False):
    jid = uuid.uuid4().hex[:12]
    jdir = os.path.join(JOBS_DIR, jid)
    checkpoint = options.get('checkpoint_review') is True
    if checkpoint:
        try:
            os.mkdir(jdir, 0o700)
        except OSError as error:
            raise _CheckpointOptionsError('checkpoint settings could not be saved') from error
    else:
        os.makedirs(jdir, exist_ok=True)
    job = {
        "id": jid, "dir": jdir, "video": video_path, "name": name,
        "options": options, "phase": "queued", "progress": 0.0,
        "eta": None, "size": 0,
        "log": JobLog(), "error": None, "output": None, "created": time.time(),
        "cancel": threading.Event(), "stats": {}, "qgen": 0,
    }
    FILES.initialize(job)
    # keep the job's settings beside its upload: a scan that never finished
    # has no report to recover them from, and a Retry after a restart then
    # ran with DEFAULT settings (all categories) instead of the user's own
    if checkpoint:
        try:
            _persist_checkpoint_options(jdir, options)
        except BaseException as error:
            _discard_unregistered_checkpoint(job)
            if isinstance(error, (OSError, TypeError, ValueError, RecursionError)):
                raise _CheckpointOptionsError('checkpoint settings could not be saved') from error
            raise
    else:
        try:
            with open(os.path.join(jdir, OPTIONS_FILE), "w",
                      encoding="utf-8") as f:
                json.dump(options, f)
        except (OSError, TypeError, ValueError):
            pass
    if not _defer_registration:
        _register_new_jobs([job])
    return job


def export_filenames(job) -> tuple[str, str]:
    """Share picker suggestions and attachment names, using the real container."""
    stem = os.path.splitext(job["name"])[0]
    ext = os.path.splitext(job.get("output") or "")[1] or ".mp4"
    return stem + "_redacted" + ext, stem + "_audit.json"


def job_public(job):
    video_name, report_name = export_filenames(job)
    logs = job["log"].snapshot(tail=30)
    result = {k: job[k] for k in ("id", "name", "phase", "progress", "error",
                                "stats")} | {
        "eta": job.get("eta"),      # .get(): jobs rehydrated from disk lack it
        # input size: lets the editor warn before re-uploading a file that
        # is ALREADY on the server (issue #16 — each retry re-uploaded the
        # same 18 GB until the disk filled)
        "size": job.get("size") or 0,
        "log_tail": logs["lines"],
        "log_len": logs["len"],
        "log_epoch": logs["epoch"],
        "log_base": logs["base"],
        "log_retained": logs["retained"],
        "log_bytes": logs["bytes"],
        "log_dropped": logs["dropped"],
        "log_truncated": logs["truncated"],
        "has_output": bool(not FILES.initialize(job).recovery_required and job["output"] and os.path.exists(job["output"])),
        "recovery_required": FILES.initialize(job).recovery_required,
        "checkpoint_unfinished": bool(job.get("_checkpoint_unfinished")),
        # "render" | "scan" | None: which step an error/cancelled job was on
        "failed_action": job.get("failed_action"),
        # stop and continue: a running scan offers Stop when it supports it;
        # a stopped one says where it stopped
        "stop_supported": getattr(FILES.initialize(job).active, 'progress_stop', None) is not None,
        "stopping": bool(getattr(getattr(FILES.initialize(job).active, 'progress_stop', None),
                                 'is_set', lambda: False)()),
        "stopped_frame": job.get("stopped_frame"),
        "stopped_total": job.get("stopped_total"),
        "download_name": video_name,
        "report_name": report_name,
    }
    if job.get('options', {}).get('plate_coverage') == 'assisted':
        # Lets a re-render from the done view show the gap reminder too.
        result['assisted_letters'] = True
    if job.get('options', {}).get('checkpoint_review') is True:
        stop = getattr(FILES.initialize(job).active, 'checkpoint_stop', None)
        result['checkpoint_enabled'] = True
        result['checkpoint_stopping'] = bool(stop is not None and stop.is_set())
    return result


def _publish_preview_jpeg(path, image, quality) -> bool:
    """Publish a complete disposable preview, retaining the previous one on failure."""
    temporary = None
    try:
        ok, encoded = cv2.imencode(".jpg", image,
                                  [cv2.IMWRITE_JPEG_QUALITY, quality])
        if not ok or encoded is None or not encoded.size:
            return False
        # A same-directory replace keeps readers of the old generation intact.
        # No fsync: a preview is disposable, rather than a durable scan report.
        with tempfile.NamedTemporaryFile(dir=os.path.dirname(path),
                                         prefix=".preview-", suffix=".jpg",
                                         delete=False) as output:
            temporary = output.name
            output.write(encoded)
        os.replace(temporary, path)
        return True
    except (cv2.error, OSError):
        return False
    finally:
        if temporary is not None:
            try:
                os.unlink(temporary)
            except OSError:
                pass


# ETA observations belong to the callback, independently of UI polling.
_ETA_WINDOW_SECONDS = 120.0
_ETA_SAMPLE_SECONDS = 5.0
_ETA_RECENT_MIN_SECONDS = 20.0
_ETA_STARTUP_SECONDS = 3.0


class WebCallbacks(openscrub.Callbacks):
    wants_frames = True

    def __init__(self, job, cancel_event=None, diagnostic_sink=None, diagnostic_ref=None):
        self.job = job
        self._diagnostic_sink = diagnostic_sink
        self._diagnostic_ref = diagnostic_ref
        self.cancel_event = cancel_event if cancel_event is not None else job["cancel"]
        self._last_frame = 0.0
        self._stage = None          # ETA state: current stage,
        self._t0 = 0.0              # when it started,
        self._cur0 = 0             # its first cur value,
        self._eta = None            # and the smoothed estimate
        self._rate_points = []      # recent monotonic (time, counter) samples
        self._last_cur = None       # detect restarts even between samples

    def log(self, msg):
        self.job["log"].append(msg)

    def progress(self, stage, cur, total):
        if self._diagnostic_sink is not None:
            self._diagnostic_sink.progress(self._diagnostic_ref, stage, cur, total)
        # scan frame loop -> first 45% of the bar; "post" (dense-track
        # smoothing after the loop — previously a silent stall) -> 45-50%;
        # render -> back half. Jobs without a post stage jump 45 -> 50,
        # which reads as instant rather than stuck.
        # Rounded to 5 decimals, not 3: on a long slow scan 3-decimal
        # quantization froze the bar for 30s+ stretches, and the old
        # client-side ETA (extrapolated from bar movement) blanked out.
        base, span = {"scan": (0, 0.45),
                      "post": (0.45, 0.05)}.get(stage, (0.5, 0.5))
        self.job["progress"] = round(base + span * cur / max(total, 1), 5)

        # A fast early prefix must not dominate a long stage's slow tail.
        # Use the whole-stage rate only during startup, then a bounded
        # recent window. Wall-clock adjustments cannot affect throughput.
        now = time.monotonic()
        if (not math.isfinite(cur) or not math.isfinite(total)
                or total <= 0 or cur >= total):
            self._stage = None
            self._last_cur = None
            self._rate_points.clear()
            self._eta = self.job["eta"] = None
            return
        if (stage != self._stage
                or (self._last_cur is not None and cur < self._last_cur)):
            self._stage, self._t0, self._cur0 = stage, now, cur
            self._last_cur = cur
            self._rate_points = [(now, cur)]
            self._eta = self.job["eta"] = None
            return
        self._last_cur = cur
        if now - self._rate_points[-1][0] >= _ETA_SAMPLE_SECONDS:
            self._rate_points.append((now, cur))
        cutoff = now - _ETA_WINDOW_SECONDS
        # Keep at most one predecessor to include the crossing interval.
        while len(self._rate_points) > 2 and self._rate_points[1][0] < cutoff:
            self._rate_points.pop(0)

        done, elapsed = cur - self._cur0, now - self._t0
        rate = done / elapsed if done > 0 and elapsed >= _ETA_STARTUP_SECONDS else 0
        first, last = self._rate_points[0], self._rate_points[-1]
        recent_seconds = last[0] - first[0]
        if recent_seconds >= _ETA_RECENT_MIN_SECONDS:
            # A mature stalled window has no useful rate; do not revive
            # the optimistic whole-stage average in that case.
            rate = (last[1] - first[1]) / recent_seconds
        if math.isfinite(rate) and rate > 0:
            rem = (total - cur) / rate
            if math.isfinite(rem) and rem >= 0:
                self._eta = (rem if self._eta is None
                             else 0.35 * self._eta + 0.65 * rem)
                self.job["eta"] = round(self._eta)
                return
        self._eta = self.job["eta"] = None

    def scan_frame(self, frame, t, found):
        now = time.time()
        if now - self._last_frame < 0.4:   # throttle disk writes
            return
        self._last_frame = now
        h, w = frame.shape[:2]
        scale = 720 / w
        small = cv2.resize(frame, (720, int(h * scale)))
        _publish_preview_jpeg(os.path.join(self.job["dir"], "preview.jpg"),
                              small, 70)

    def cancelled(self):
        return self.cancel_event.is_set()


def _optional_plate_settings(options):
    """Validate explicit scan policy without clamping its candidate floor."""
    policy = options.get('uncertain_policy')
    if policy is None or policy == 'off':
        return None
    if not isinstance(policy, str) or policy not in ('manual_review', 'blur_candidates'):
        raise ValueError('invalid optional plate settings')
    values = (options.get('plate_threshold', .35), options.get('plate_auto_cutoff'))
    if any(isinstance(v, bool) or not isinstance(v, (str, int, float)) for v in values):
        raise ValueError('invalid optional plate settings')
    try:
        floor, cutoff = (float(v) for v in values)
        openscrub.plate_policy.validate_settings(policy, floor, cutoff)
    except (ValueError, OverflowError):
        raise ValueError('invalid optional plate settings') from None
    return policy, floor, cutoff


def build_args(job, for_render=False):
    o = job["options"]
    jdir = job["dir"]
    optional = None if for_render else _optional_plate_settings(o)
    argv = [job["video"],
            "--engine", o.get("engine", "auto"),
            "--device", o.get("device", "auto"),
            "--encoder", o.get("encoder", "auto"),
            "--mode", o.get("mode", "blur"),
            "--coverage", o.get("coverage", "tight"),
            "--mode-map", o.get("mode_map", ""),
            "--sample-interval", str(o.get("sample_interval", 0.5)),
            "--scan-trigger", str(o.get("scan_trigger", 60)),
            "--pad", str(o.get("pad", 8)),
            "--bridge-gap", str(o.get("bridge_gap", 4.0)),
            "--face-expand", str(o.get("face_expand", 0.15)),
            "--face-threshold", str(o.get("face_threshold", 0.6)),
            "--plate-threshold", _plate_threshold(o.get("plate_threshold")),
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
            "--face-shape", (o.get("face_shape")
                             if o.get("face_shape") in ("ellipse", "rect")
                             else "ellipse"),
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
    if optional:
        policy, _, cutoff = optional
        argv += ["--uncertain-policy", policy, "--plate-auto-cutoff", str(cutoff)]
    if o.get('checkpoint_review') is True:
        # The checkpoint producer has one conservative native source domain.
        argv += ['--no-vfr-fix', '--scroll-track', 'off', '--no-backtrack']
    # user-defined regex categories ride along on every job; the engine only
    # activates the ones whose id is in --categories
    for c in load_custom_cats():
        argv += ["--custom-regex", "%s=%s" % (c["id"], c["regex"])]
    # selected detection models (Detection models panel). A selected id
    # whose file is missing falls back to the engine default silently-safe
    # ladder (YuNet / plate auto-search).
    # The checkpoint subset does not run face, plate or person inference.
    sel = {} if o.get('checkpoint_review') is True else load_model_select()
    for kind, flag in (("face", "--face-model"), ("plate", "--plate-model"),
                       ("person", "--person-model")):
        mid = sel.get(kind)
        if mid:
            p = find_model_file("%s.onnx" % mid)
            if p:
                argv += [flag, p]
    if o.get("verify_hdr_plate_frames") is True:
        argv.append("--verify-hdr-plate-frames")
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
    # A render is governed by the saved report, not a later job option.
    if not for_render and o.get("plate_coverage") == "narrow":
        argv += ["--plate-coverage", "narrow"]
    elif not for_render and o.get("plate_coverage") == "assisted":
        # The Scan Setup dialog is the only consent; never infer it.
        if o.get("no_box_fallback") is not True:
            raise ValueError("assisted plate letters needs explicit confirmation")
        argv += ["--plate-coverage", "assisted", "--no-box-fallback"]
        if o.get("steady_single_plate") is True:
            argv.append("--steady-single-plate")
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
            pass
    # "specific text" terms travel as a file in the job dir (never on the
    # command line, where process listings would show them)
    ptext = (o.get("phrases") or "")
    if isinstance(ptext, str) and ptext.strip():
        ppath = os.path.join(jdir, "phrases.txt")
        with open(ppath, "w", encoding="utf-8") as f:
            f.write(ptext.strip() + "\n")
        argv += ["--phrases", ppath]
    server_allow = os.path.join(JOBS_DIR, "allowlist.txt")
    for kind in ("allow_names", "extra_names"):
        text = (o.get(kind) or "").strip()
        # Checkpoint scans support only QR/no categories, so the name
        # detector and its global allowlist are irrelevant to that scan.
        if (kind == "allow_names" and o.get('checkpoint_review') is not True
                and os.path.exists(server_allow)):
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
        pass
    if for_render:
        argv += ["--from-report", os.path.join(jdir, "report.json")]
    parser = openscrub.build_parser()
    argv = _sanitize_argv(parser, argv, job)

    # argparse's error()/exit() call sys.exit — a SystemExit that, raised in
    # the job worker THREAD, killed that thread without a traceback: the job
    # sat at "scanning" with an empty log forever, Cancel did nothing, and
    # every later job queued behind it (a real iPhone job: Safari submitted
    # engine="" and `--engine ''` is an invalid choice). Inside the server a
    # bad setting must fail THE JOB, loudly — never the process's only worker.
    def _no_exit(message=None, *a, **k):
        raise ValueError("invalid job settings — %s" % (message or "rejected"))
    parser.error = _no_exit
    parser.exit = lambda status=0, message=None: _no_exit(message)
    return openscrub._prep_args(parser.parse_args(argv), parser)


def _plate_threshold(v):
    """Editor's plate confidence cutoff, clamped to 0.05-0.95: above that
    the detector finds (almost) nothing — a silent fail-OPEN — and below
    it everything is a plate. Unset/garbage -> the engine default."""
    try:
        f = float(v)
    except (TypeError, ValueError):
        return "0.35"
    if not math.isfinite(f):
        return "0.35"
    return str(min(0.95, max(0.05, f)))


def _sanitize_argv(parser, argv, job=None):
    """Repair option VALUES the browser sent that the engine's parser would
    reject: a choice outside its list (iOS Safari can report a <select> with
    no selection as value ""), or a number that isn't one / isn't finite
    ("None", "", "NaN" from an empty input). Each falls back to the engine's
    own default — the same thing the CLI uses when the flag is omitted —
    with a NOTE in the job log, so one odd form value can't sink a scan.
    The choice lists and defaults come from the parser itself, so this can
    never drift from the engine. Detection SCOPE is not repaired here:
    categories/windows are free-form and are validated by the engine."""
    out = list(argv)
    i = 0
    while i < len(out) - 1:
        a = parser._option_string_actions.get(out[i])
        if a is None or a.nargs is not None:     # positional / flag / list
            i += 1
            continue
        v = out[i + 1]
        bad = bool(a.choices) and v not in a.choices
        if not bad and a.type in (int, float):
            try:
                bad = not math.isfinite(a.type(v))
            except (TypeError, ValueError):
                bad = True
        if not bad:
            i += 2
            continue
        if a.default is None:          # no engine default: omit the flag
            del out[i:i + 2]
            msg = "omitted"
        else:
            out[i + 1] = str(a.default)
            msg = "using the default %r" % (a.default,)
            i += 2
        if job is not None and isinstance(job.get("log"), JobLog):
            job["log"].append("NOTE: setting %s=%r is not valid — %s"
                              % (a.option_strings[0], v, msg))
    return out


# The single job worker. WORKER["current"] is the job it is running right
# now (read by Cancel and the watchdog); WORKER["thread"] is the live thread.
DIAGNOSTICS = None
WORKER = {"current": None, "thread": None}
_PLATE_SEARCH_SLOT = threading.BoundedSemaphore(1)
_PLATE_SEARCH_DEADLINE = 15.0
_ACTIVE_PHASES = ("queued", "scanning", "rendering", "queued_render")


def _report_current(job):
    """Identity lookup only; caller owns report_lock and a file lifetime.

    Admission takes VAULT_LOCK -> JOBS_LOCK and releases both before this
    boundary. Never acquire VAULT_LOCK (including lease release) inside it.
    """
    with JOBS_LOCK:
        if not any(current is job for current in JOBS.values()):
            abort(404)
        if FILES.initialize(job).closed:
            abort(409, "job is being deleted")


def _recovery_gate(job):
    if FILES.initialize(job).recovery_required:
        abort(409, "render delivery requires recovery")


def _checkpoint_source_unchanged(selected):
    try:
        current = os.stat(selected['path'])
        return stat.S_ISREG(current.st_mode) and _file_stamp(current) == selected['stamp']
    except (OSError, KeyError, TypeError):
        return False


def _publish_job_report_locked(job, path, doc, *, expected_stamp=None, expected_source=None):
    """Caller owns this job's report transaction and file lifetime."""
    with _staged_report(path, doc) as staged:
        if expected_stamp is not None:
            try:
                staged_stat = os.stat(staged, follow_symlinks=False)
                named = os.stat(path, follow_symlinks=False)
                if (not stat.S_ISREG(staged_stat.st_mode) or not stat.S_ISREG(named.st_mode) or
                        _file_stamp(named) != expected_stamp or
                        not _checkpoint_source_unchanged(expected_source)):
                    raise OSError('report changed')
            except OSError:
                raise exact.ExactError('checkpoint report changed during save',
                                       409, 'geometry_conflict') from None
        FILES.initialize(job).output_epoch += 1
        os.replace(staged, os.path.abspath(path))
        if expected_stamp is not None:
            try:
                installed = os.stat(path, follow_symlinks=False)
                if (not stat.S_ISREG(installed.st_mode) or
                        (installed.st_dev, installed.st_ino, installed.st_size, installed.st_mtime_ns) !=
                        (staged_stat.st_dev, staged_stat.st_ino, staged_stat.st_size, staged_stat.st_mtime_ns)):
                    raise OSError('report changed')
            except OSError:
                raise RuntimeError('checkpoint save committed but its acknowledgement is uncertain') from None
            return _file_stamp(installed)


_CHECKPOINT_FD_PUBLICATION = os.name == 'posix'
_CHECKPOINT_RECOVERY_NAME = '.checkpoint-publication-recovery.json'
_CHECKPOINT_UNOBSERVED = object()


class _CheckpointPublicationCommittedError(RuntimeError):
    """Report bytes were replaced, but the source notification needs recovery."""
    committed = True


def _checkpoint_report_state(doc):
    """Recognize only structurally valid paused or verified complete reports."""
    if not isinstance(doc, dict) or not isinstance(doc.get('provenance'), dict):
        raise ValueError('checkpoint report has invalid provenance')
    provenance = doc['provenance']
    if provenance.get('output') is not None or provenance.get('output_sha256') is not None:
        raise ValueError('checkpoint report retains an output')
    if 'stop_review' in doc:
        checkpoints.validate_resume(doc)
        return 'paused'
    identity = provenance.get('checkpoint_identity')
    if not isinstance(identity, dict) or not isinstance(identity.get('timeline'), dict):
        raise ValueError('completed checkpoint lacks a timeline identity')
    timeline = identity['timeline']
    total = timeline.get('total_frames')
    if type(total) is not int or total < 1 or timeline.get('count_verified') is not True:
        raise ValueError('completed checkpoint lacks a verified frame count')
    _, _, _, fps, scan_hash = checkpoints._report(doc, total, total)
    checkpoints._identity(identity, total, fps, scan_hash)
    openscrub._report_frame_authorities(doc)
    return 'completed'


def _checkpoint_file_evidence(path, *, absent=False, parse=False, durable=False):
    """Hash an unchanged regular named file, without following symlinks."""
    try:
        stream = open(path, 'rb', opener=_thumbnail_nonblocking_opener)
    except FileNotFoundError:
        if absent and not os.path.lexists(path):
            return None, None, None
        raise
    with stream:
        before = os.fstat(stream.fileno())
        named = os.stat(path, follow_symlinks=False)
        if (not stat.S_ISREG(before.st_mode) or not stat.S_ISREG(named.st_mode)
                or _file_stamp(before) != _file_stamp(named)):
            raise ValueError('checkpoint file is not a stable regular file')
        digest = hashlib.sha256()
        while True:
            chunk = stream.read(1024 * 1024)
            if not chunk:
                break
            digest.update(chunk)
        doc = None
        if parse:
            stream.seek(0)
            doc = json.load(stream)
        if (before.st_size > (1 << 53) - 1 or
                _file_stamp(os.fstat(stream.fileno())) != _file_stamp(before) or
                _file_stamp(os.stat(path, follow_symlinks=False)) != _file_stamp(before)):
            raise ValueError('checkpoint file changed during inspection')
        if durable:
            os.fsync(stream.fileno())
        return {'size': before.st_size, 'sha256': digest.hexdigest()}, _file_stamp(before), doc


def _recover_checkpoint_publication(directory):
    """Resolve only byte-proven old/new outcomes; otherwise retain the fence."""
    marker = os.path.join(directory, _CHECKPOINT_RECOVERY_NAME)
    report = os.path.join(directory, 'report.json')
    try:
        directory_stat = os.stat(directory, follow_symlinks=False)
        if not stat.S_ISDIR(directory_stat.st_mode):
            raise ValueError('checkpoint directory is not a directory')
        with open(marker, 'rb', opener=_thumbnail_nonblocking_opener) as stream:
            observed = os.fstat(stream.fileno())
            named = os.stat(marker, follow_symlinks=False)
            if (not stat.S_ISREG(observed.st_mode) or not stat.S_ISREG(named.st_mode)
                    or _file_stamp(observed) != _file_stamp(named)
                    or observed.st_size > 1024):
                raise ValueError('invalid checkpoint recovery marker')
            def unique_pairs(pairs):
                result = {}
                for key, value in pairs:
                    if key in result:
                        raise ValueError('duplicate checkpoint recovery field')
                    result[key] = value
                return result
            proof = json.loads(stream.read(1025), object_pairs_hook=unique_pairs)
            if (_file_stamp(os.fstat(stream.fileno())) != _file_stamp(observed) or
                    _file_stamp(os.stat(marker, follow_symlinks=False)) != _file_stamp(observed)):
                raise ValueError('checkpoint recovery marker changed')
        if (type(proof) is not dict or set(proof) != {'version', 'kind', 'old', 'new'}
                or type(proof['version']) is not int or proof['version'] != 2
                or proof['kind'] != 'checkpoint-publication'):
            raise ValueError('unsupported checkpoint recovery marker')
        def valid_evidence(value, *, new=False):
            keys = {'size', 'sha256', 'state'} if new else {'size', 'sha256'}
            return (type(value) is dict and set(value) == keys
                    and type(value['size']) is int and 0 <= value['size'] <= (1 << 53) - 1
                    and type(value['sha256']) is str
                    and re.fullmatch('[0-9a-f]{64}', value['sha256']) is not None
                    and (not new or value['state'] in ('paused', 'completed')))
        if ((proof['old'] is not None and not valid_evidence(proof['old']))
                or not valid_evidence(proof['new'], new=True)):
            raise ValueError('invalid checkpoint file evidence')
        evidence, report_stamp, doc = _checkpoint_file_evidence(
            report, absent=True, parse=True, durable=True)
        new = {key: proof['new'][key] for key in ('size', 'sha256')}
        if evidence == new:
            if _checkpoint_report_state(doc) != proof['new']['state']:
                raise ValueError('checkpoint report state does not match its proof')
        elif evidence == proof['old']:
            if evidence is not None and _checkpoint_report_state(doc) != 'paused':
                raise ValueError('previous checkpoint is not paused')
        else:
            raise ValueError('checkpoint report matches neither recorded outcome')
        flags = (os.O_RDONLY | getattr(os, 'O_DIRECTORY', 0) |
                 getattr(os, 'O_CLOEXEC', 0) | getattr(os, 'O_NOFOLLOW', 0))
        dirfd = os.open(directory, flags)
        try:
            current = os.fstat(dirfd)
            named_directory = os.stat(directory, follow_symlinks=False)
            if (not stat.S_ISDIR(current.st_mode) or not stat.S_ISDIR(named_directory.st_mode)
                    or (current.st_dev, current.st_ino) != (directory_stat.st_dev, directory_stat.st_ino)
                    or (named_directory.st_dev, named_directory.st_ino) !=
                       (directory_stat.st_dev, directory_stat.st_ino)):
                raise ValueError('checkpoint directory changed during recovery')
            # Persist the chosen report/absence before removing the fence.
            os.fsync(dirfd)
            if (_file_stamp(os.stat(marker, follow_symlinks=False)) != _file_stamp(observed)
                    or (report_stamp is None and os.path.lexists(report))
                    or (report_stamp is not None and
                        _file_stamp(os.stat(report, follow_symlinks=False)) != report_stamp)):
                raise ValueError('checkpoint outcome changed during recovery')
            os.unlink(marker)
            os.fsync(dirfd)
        finally:
            os.close(dirfd)
        return True
    except (OSError, TypeError, ValueError, OverflowError, RecursionError):
        return False


def _publish_checkpoint_locked(job, owner, generation, operation, staged, path, doc,
                               *, _stage_stamp=None, _old_stamp=_CHECKPOINT_UNOBSERVED):
    """Commit a checkpoint stage under the existing per-job report lock.

    The owning worker remains responsible for its phase transition, source
    adoption and lifetime cleanup. Cross-job source publication needs its
    ordered foreign-owner guard and is deliberately not admitted here. This
    prerequisite is POSIX-only: it retains the staged descriptor across
    rename, and a post-replace failure explicitly marks committed recovery.
    """
    files = FILES.initialize(job)
    _report_current(job)
    _recovery_gate(job)
    if (not _operation_valid(job, owner) or files.active is not owner or
            owner.release_started or owner.operation is not operation or
            operation is None or operation.is_set()):
        raise openscrub.PipelineCancelled()
    with JOBS_LOCK:
        if type(generation) is not int or job.get('qgen') != generation:
            raise openscrub.PipelineCancelled()
    if owner.source_state is not None and owner.source_state is not files:
        raise ValueError('checkpoint source owned by another job is not supported')
    if not _CHECKPOINT_FD_PUBLICATION:
        raise ValueError('checkpoint publication currently requires POSIX stage descriptors')
    target = os.path.abspath(os.path.join(job['dir'], 'report.json'))
    if (os.path.abspath(path) != target or
            os.path.dirname(os.path.abspath(staged)) != os.path.dirname(target)):
        raise ValueError('checkpoint stage does not belong to this report')
    provenance = doc.get('provenance') if isinstance(doc, dict) else None
    selected = provenance.get('input') if isinstance(provenance, dict) else None
    original = provenance.get('original_input') if isinstance(provenance, dict) else None
    if (not isinstance(selected, str) or not owner.source or
            os.path.realpath(selected) != owner.source or
            (original is not None and
             (not isinstance(original, str) or not original or
              os.path.realpath(original) != owner.source)) or
            provenance.get('output') is not None):
        raise ValueError('checkpoint report source differs from the owned scan source')
    # POSIX rename retains the opened inode; this supplies the actual
    # post-rename stamp without a second path lookup or a Windows share-delete
    # assumption. The stage must still be the owned regular file we opened.
    flags = (os.O_RDONLY | getattr(os, 'O_CLOEXEC', 0) |
             getattr(os, 'O_NOFOLLOW', 0) | getattr(os, 'O_NONBLOCK', 0))
    descriptor = os.open(staged, flags)
    try:
        opened_stage = os.fdopen(descriptor, 'rb')
    except BaseException:
        try:
            os.close(descriptor)
        except OSError:
            pass
        raise
    with opened_stage as opened:
        held, named = os.fstat(opened.fileno()), os.stat(staged, follow_symlinks=False)
        if (not stat.S_ISREG(held.st_mode) or not stat.S_ISREG(named.st_mode) or
                (held.st_dev, held.st_ino) != (named.st_dev, named.st_ino)):
            raise ValueError('checkpoint stage changed before publication')
        # A failing preparation or replacement leaves the old report and
        # committed epochs intact. Generation retirement is conservative.
        initial_stamp = _file_stamp(held)
        thumbs.invalidate_locked(files.thumbnail, 'checkpoint report preparing')
        held, named = os.fstat(opened.fileno()), os.stat(staged, follow_symlinks=False)
        if (not stat.S_ISREG(held.st_mode) or not stat.S_ISREG(named.st_mode)
                or _file_stamp(held) != initial_stamp or _file_stamp(named) != initial_stamp):
            raise ValueError('checkpoint stage changed during publication preparation')
        if _stage_stamp is not None and _file_stamp(held) != _stage_stamp:
            raise ValueError('checkpoint stage changed after recording recovery evidence')
        if _old_stamp is None:
            if os.path.lexists(target):
                raise ValueError('checkpoint report appeared after recording recovery evidence')
        elif _old_stamp is not _CHECKPOINT_UNOBSERVED:
            old = os.stat(target, follow_symlinks=False)
            if not stat.S_ISREG(old.st_mode) or _file_stamp(old) != _old_stamp:
                raise ValueError('checkpoint report changed after recording recovery evidence')
        os.replace(staged, target)
        files.output_epoch += 1
        try:
            report_stat = os.fstat(opened.fileno())
            _report_committed_locked(job, doc, owner, _thumbnail_ready=True,
                                     _report_stat=report_stat)
        except BaseException as error:
            # No UI invokes this prerequisite. A later owner must persist and
            # resolve this state across restart before exposing controls.
            files.recovery_required = True
            files.recovery_diagnostics = ('checkpoint report replaced; source notification unverified',)
            files.current_source = None
            files.source_pair = None
            files.source_status = 'unavailable'
            files.source_retired = True
            files.source_reason = 'checkpoint report committed but requires recovery'
            job.update(phase='error', error=files.source_reason, eta=None)
            raise _CheckpointPublicationCommittedError(files.source_reason) from error


def _publish_checkpoint_job_locked(job, owner, generation, operation, staged, path, doc):
    """Fence one report replacement with a durable same-directory marker."""
    files = FILES.initialize(job)
    directory = os.path.abspath(job['dir'])
    marker = os.path.join(directory, _CHECKPOINT_RECOVERY_NAME)
    flags = os.O_RDONLY | getattr(os, 'O_DIRECTORY', 0) | getattr(os, 'O_CLOEXEC', 0)
    dirfd = os.open(directory, flags)
    created = replaced = False
    try:
        state = _checkpoint_report_state(doc)
        old, old_stamp, _ = _checkpoint_file_evidence(os.path.join(directory, 'report.json'), absent=True)
        new, stage_stamp, _ = _checkpoint_file_evidence(staged)
        proof = {'version': 2, 'kind': 'checkpoint-publication', 'old': old,
                 'new': dict(new, state=state)}
        marker_flags = (os.O_WRONLY | os.O_CREAT | os.O_EXCL |
                        getattr(os, 'O_NOFOLLOW', 0) | getattr(os, 'O_CLOEXEC', 0))
        descriptor = os.open(marker, marker_flags, 0o600)
        created = True
        try:
            opened_marker = os.fdopen(descriptor, 'wb')
        except BaseException:
            os.close(descriptor)
            raise
        with opened_marker as stream:
            stream.write((json.dumps(proof, separators=(',', ':')) + '\n').encode('ascii'))
            stream.flush()
            os.fsync(stream.fileno())
        os.fsync(dirfd)
        _publish_checkpoint_locked(job, owner, generation, operation, staged, path, doc,
                                   _stage_stamp=stage_stamp, _old_stamp=old_stamp)
        replaced = True
        os.fsync(dirfd)  # the report rename is durable before marker retirement
        unfinished = 'stop_review' in doc
        job.update(phase='paused' if unfinished else 'review',
                   _checkpoint_unfinished=unfinished, output=None,
                   progress=0.5, eta=None, error=None)
        os.unlink(marker)
        created = False
        os.fsync(dirfd)
    except BaseException as error:
        # A surviving staged path proves the rename did not happen. A lost
        # stage or explicit committed error must remain fenced on restart.
        uncertain = (replaced or getattr(error, 'committed', False)
                     or not os.path.exists(staged) or (not created and os.path.lexists(marker)))
        if created and not uncertain:
            try:
                os.unlink(marker)
                created = False
                os.fsync(dirfd)
            except OSError:
                uncertain = True
        if uncertain:
            files.recovery_required = True
            files.recovery_diagnostics = ('checkpoint publication requires recovery',)
            job.update(phase='error', error='checkpoint publication requires recovery',
                       output=None, eta=None)
        raise
    finally:
        os.close(dirfd)


def _edit_gate(job):
    _recovery_gate(job)
    _report_current(job)
    if FILES.initialize(job).active is not None or job.get("phase") in _ACTIVE_PHASES:
        abort(409, "job work is queued, running or still cleaning up")


def _unfinished_checkpoint_locked(job):
    """Recognize even invalid checkpoint markers before destructive admission."""
    if job.get('_checkpoint_unfinished'):
        return True
    path = os.path.join(job['dir'], 'report.json')
    try:
        named = os.stat(path, follow_symlinks=False)
    except FileNotFoundError:
        return False
    except OSError:
        return True
    try:
        if not stat.S_ISREG(named.st_mode):
            return True
        stamp = _file_stamp(named)
        cached = job.get('_checkpoint_observation')
        if cached is not None and cached[0] == stamp:
            return cached[1]
        with open(path, encoding='utf-8', opener=_thumbnail_nonblocking_opener) as stream:
            opened = os.fstat(stream.fileno())
            if not stat.S_ISREG(opened.st_mode) or _file_stamp(opened) != stamp:
                return True
            doc = json.load(stream)
            if (_file_stamp(os.fstat(stream.fileno())) != stamp or
                    _file_stamp(os.stat(path, follow_symlinks=False)) != stamp):
                return True
    except (OSError, ValueError, RecursionError):
        return True
    result = isinstance(doc, dict) and 'stop_review' in doc
    job['_checkpoint_observation'] = (stamp, result)
    return result


def _checkpoint_resume_token_locked(job):
    """Identify the current report generation while the report lock is held."""
    _report_current(job)
    _recovery_gate(job)
    files = FILES.initialize(job)
    path = os.path.join(job['dir'], 'report.json')
    try:
        with open(path, 'rb', opener=_thumbnail_nonblocking_opener) as stream:
            opened = os.fstat(stream.fileno())
            named = os.stat(path, follow_symlinks=False)
            if (not stat.S_ISREG(opened.st_mode) or not stat.S_ISREG(named.st_mode)
                    or _file_stamp(opened) != _file_stamp(named)):
                raise OSError('report changed')
    except (OSError, ValueError):
        raise Conflict('checkpoint report is unavailable or changed') from None
    value = (files.incarnation, files.committed_report_epoch, *_file_stamp(opened))
    return hashlib.sha256(json.dumps(value, separators=(',', ':')).encode('ascii')).hexdigest()


def _operation_valid(job, owner):
    files = FILES.initialize(job)
    with JOBS_LOCK:
        return (any(current is job for current in JOBS.values()) and not files.closed
                and owner.operation is not None
                and files.operation is owner.operation)


def _begin_operation(job, owner):
    files = FILES.initialize(job)
    thumbs.invalidate_locked(files.thumbnail, 'operation changed')
    if files.source_pair is not None:
        files.source_pair = None
        files.source_retired = True
        files.source_status, files.source_reason = 'unavailable', 'scan source adoption replaced'
    owner.operation = threading.Event()
    files.operation = owner.operation
    job["cancel"] = owner.operation
    files.active = owner


def _finish_operation(job, owner):
    # Release lifecycle ownership outside the report transaction. Keep the
    # mutation gate closed until actual worker cleanup/release has completed.
    owner.release()
    if job is None:  # a cancelled ticket's job may already have been deleted
        return
    files = FILES.initialize(job)
    with files.report_lock:
        if files.active is owner:
            files.active = None


def _reserve_queue_locked(job, action, prepared):
    """Transfer a PREPARED lifetime under report_lock, without vault nesting."""
    _report_current(job)
    _recovery_gate(job)
    _begin_operation(job, prepared)
    with JOBS_LOCK:
        job["qgen"] = job.get("qgen", 0) + 1
        gen = job["qgen"]
        FILES.initialize(job).queued[gen] = prepared
    job["phase"] = "queued_render" if action == "render" else "queued"
    job["failed_action"] = None
    return job["id"], action, gen, prepared


def _prepare_work(job, action):
    # Source selection can reserve related jobs and release provisional leases;
    # all of that must finish before taking report_lock.
    prepared = _own_files(job, work=True)
    try:
        if action == "render":
            _select_render_input(job, prepared)
        return prepared
    except BaseException:
        prepared.release()
        raise


def enqueue(job, action, ticket=None):
    if ticket is None:
        prepared = _prepare_work(job, action)
        try:
            with FILES.initialize(job).report_lock:
                # Intake may have been cancelled while upload was writing.
                # Queueing its eventual completed upload must not revive it.
                if not job["cancel"].is_set():
                    ticket = _reserve_queue_locked(job, action, prepared)
        finally:
            if ticket is None:
                prepared.release()
        if ticket is None:
            return
    try:
        WORK_Q.put(ticket)
    except BaseException:
        files = FILES.initialize(job)
        with files.report_lock:
            with JOBS_LOCK:
                files.queued.pop(ticket[2], None)
            if _operation_valid(job, ticket[3]):
                job["phase"] = "error"
                job["error"] = "could not queue job work"
        _finish_operation(job, ticket[3])
        raise



def worker():
    """Run queued jobs forever. NOTHING may end this loop: it is the
    server's only worker, and when it died (a SystemExit from argparse —
    which a thread swallows silently) the job froze at "scanning" with an
    empty log, Cancel was ignored and every later job queued forever until
    the container was restarted. Every per-job failure, BaseException
    included, now fails that job loudly and the loop carries on."""
    while True:
        try:
            item = WORK_Q.get()
        except BaseException:          # pragma: no cover — queue can't fail
            time.sleep(1)
            continue
        if item is None:               # explicit stop (tests); the watchdog
            WORK_Q.task_done()         # starts a fresh worker in production
            return
        lease = None
        resolve_legacy = False
        try:
            jid, action = item[0], item[1]
            gen = item[2] if len(item) > 2 else None
            lease = item[3] if len(item) > 3 else None
            with VAULT_LOCK:
                with JOBS_LOCK:
                    job = JOBS.get(jid)
                    stale = (job is None
                             or (gen is not None and gen != job.get("qgen", 0))
                             or job.get("phase") == "cancelled"
                             or (lease is not None and (lease.release_started
                                 or FILES.initialize(job) is not lease.state))
                             or FILES.initialize(job).closed)
                    if job is not None:
                        FILES.initialize(job).queued.pop(gen, None)
                    if not stale:
                        # Cancel and this handoff share the same guard. Once
                        # removed from queued, only the worker releases it.
                        WORKER["current"] = jid
                if not stale and lease is None:  # old queue entries
                    _validate_files_locked(job)
                    lease = _reserve_files_locked(job, work=True)
                    resolve_legacy = bool(lease.source)
            if not stale and resolve_legacy:
                _thumbnail_resolve_admission(lease, lease.source)
            if not stale:
                _run_job(job, action, lease)
        except BaseException as e:     # belt and braces: never die
            if DIAGNOSTICS is not None:
                code, _ = diagnostics.classify(e)
                DIAGNOSTICS.emit("worker_loop_error", active_action_lost=WORKER["current"] is not None, error=code)
            print(f"[web] worker: unexpected {type(e).__name__}: {e}",
                  flush=True)
        finally:
            if lease is not None:
                _finish_operation(job, lease)
            WORKER["current"] = None
            WORK_Q.task_done()


def _run_job(job, action, owner=None):
    if owner is None:
        owner = _prepare_work(job, action)
        try:
            with FILES.initialize(job).report_lock:
                _begin_operation(job, owner)
            return _run_job(job, action, owner)
        finally:
            _finish_operation(job, owner)
    jid = job["id"]
    files = FILES.initialize(job)
    progress_path = os.path.join(job["dir"], scan_progress.PROGRESS_NAME)
    with files.report_lock:
        if owner.operation is None:  # compatibility with old queue entries
            _begin_operation(job, owner)
        if not _operation_valid(job, owner):
            return
        job["phase"] = "scanning" if action in ('scan', 'resume', 'continue') else "rendering"
        job["failed_action"] = None
        checkpoint_stop = (threading.Event() if action in ('scan', 'resume')
                           and job['options'].get('checkpoint_review') is True else None)
        owner.checkpoint_stop = checkpoint_stop
        owner.progress_stop = None      # set once the scan is known to support Stop
        if action == 'continue':
            job["error"] = None
        generation = job.get('qgen', 0)
    sink = DIAGNOSTICS
    diagnostic_ref = (sink.start("scan" if action in ("resume", "continue") else action)
                      if sink is not None else None)
    outcome, diagnostic_error = "superseded", None
    escaped = False
    try:
        if diagnostic_ref is not None and WORKER.get("current") == jid:
            WORKER["diagnostic_ref"] = diagnostic_ref
        cb = WebCallbacks(job, owner.operation, sink, diagnostic_ref)
        def publish_report(path, doc):
            provenance = doc.get('provenance', {}) if isinstance(doc, dict) else {}
            if isinstance(provenance, dict):
                for role in ('input', 'original_input', 'output'):
                    if isinstance(provenance.get(role), str):
                        _thumbnail_admit_path(provenance[role], owner)
            with files.report_lock:
                if not _operation_valid(job, owner) or owner.operation.is_set():
                    raise openscrub.PipelineCancelled()
                _publish_job_report_locked(job, path, doc)
                _report_committed_locked(job, doc, owner if action == "scan" else None)
        cb.publish_report = publish_report
        committed = False
        def publish_render(delivery, summary):
            nonlocal committed
            _thumbnail_admit_path(summary['output'], owner)
            with files.report_lock:
                _recovery_gate(job)
                if not _operation_valid(job, owner) or owner.operation.is_set():
                    raise openscrub.PipelineCancelled()
                missing = object()
                keys = ("output", "phase", "progress", "eta", "error")
                previous = {key: job.get(key, missing) for key in keys}
                def success():
                    job["output"] = summary["output"]
                    job["phase"] = "done"
                    job["progress"] = 1.0
                    job["eta"] = None
                    job["error"] = None
                def restore():
                    for key, value in previous.items():
                        if value is missing:
                            job.pop(key, None)
                        else:
                            job[key] = value
                def mutate():
                    files.output_epoch += 1
                try:
                    delivery.commit(before_mutation=mutate, publish_success=success,
                                    restore_success=restore)
                except _DeliveryRecoveryError as error:
                    files.recovery_required = True
                    files.recovery_diagnostics = error.rollback_diagnostics
                    job.update(phase="error", error="render delivery requires recovery", eta=None)
                    raise
                committed = delivery.committed
                if committed and delivery.report_path is not None:
                    _report_committed_locked(job)
        cb.publish_render = publish_render
        source = owner.source if owner is not None else job["video"]
        try:
            if action in ('scan', 'resume', 'continue'):
                job["log"].append("— scan continued —" if action == 'continue'
                                  else "— scan started —")
                args = build_args(dict(job, video=source))
                if action == 'continue' and checkpoint_stop is not None:
                    raise ValueError('Stop & Review jobs continue with Resume')
                if action == 'resume' and checkpoint_stop is None:
                    raise ValueError('resume requires an opted-in checkpoint scan')
                if checkpoint_stop is not None:
                    if not _CHECKPOINT_FD_PUBLICATION:
                        raise ValueError('checkpoint publication requires POSIX support')
                    if owner.source_state is not None and owner.source_state is not files:
                        raise ValueError('checkpoint source owned by another job is not supported')
                    from openscrub_internal import checkpoint_runtime
                    published = False
                    def commit_checkpoint(staged, path, doc):
                        nonlocal published
                        if (getattr(owner, 'checkpoint_stop', None) is not checkpoint_stop
                                or ('stop_review' in doc and not checkpoint_stop.is_set())):
                            raise openscrub.PipelineCancelled()
                        _publish_checkpoint_job_locked(job, owner, generation, owner.operation,
                                                       staged, path, doc)
                        published = True
                    result = checkpoint_runtime.scan_to_report(
                        args, os.path.join(job['dir'], 'report.json'), cb=cb,
                        stop_requested=checkpoint_stop.is_set,
                        publication_lock=files.report_lock, resume=(action == 'resume'),
                        _commit_staged=commit_checkpoint)
                    if result is None:
                        raise ValueError('Stop occurred before any complete frame was available')
                    if not published:
                        with files.report_lock:
                            if not _operation_valid(job, owner) or owner.operation.is_set():
                                raise openscrub.PipelineCancelled()
                            current = _checkpoint_resume_token_locked(job)
                            if current != getattr(owner, 'checkpoint_resume_token', None):
                                raise ValueError('checkpoint report changed during a no-progress resume')
                            stamp = _file_stamp(os.stat(os.path.join(job['dir'], 'report.json')))
                            files.source_pair = (owner.operation, files.committed_report_epoch,
                                                 owner.source, stamp)
                            files.source_status, files.source_reason = 'pending', None
                            job.update(phase='paused', _checkpoint_unfinished=True, output=None,
                                       progress=0.5, eta=None, error=None)
                    _adopt_scan_source(job, owner)
                    outcome = "review"
                    return
                control = None
                if action == 'continue' or openscrub.stop_supported(args):
                    if action == 'scan':
                        scan_progress.remove(progress_path)   # a fresh scan starts over
                    stop_event = threading.Event()
                    with files.report_lock:
                        owner.progress_stop = stop_event
                    control = scan_progress.ScanProgressControl(
                        progress_path, stop_requested=stop_event.is_set,
                        resume=(action == 'continue'),
                        meta={"video": source, "name": job.get("name"),
                              # the report this scan will REPLACE (a rescan
                              # keeps the old one until it finishes): restart
                              # tells "stopped" from "finished, not cleaned"
                              "report_before": _report_digest(job["dir"])})
                state = (openscrub.run_scan(args, cb) if control is None
                         else openscrub.run_scan(args, cb, progress=control))
                openscrub.write_report(os.path.join(job["dir"], "report.json"),
                                      args, state, publisher=cb.publish_report)
                # The report is published: the saved progress has done its job.
                scan_progress.remove(progress_path)
                with files.report_lock:
                    if not _operation_valid(job, owner):
                        return
                    job["stats"] = state["stats"]
                hdr_proof = getattr(args, '_hdr_quad_proof', None)
                if hdr_proof is None:
                    coherent = _adopt_scan_source(job, owner)
                else:
                    coherent = _adopt_scan_source(job, owner, hdr_proof, state.get('input_sha256'))
                if owner.operation.is_set():
                    raise openscrub.PipelineCancelled()
                if coherent:
                    try:
                        thumbnail_owner = _own_files(job, work=True)
                    except Conflict as error:
                        if error.description != "render delivery requires recovery":
                            raise
                        coherent = False
                    except (OSError, _ThumbnailArtifactPending):
                        # Thumbnail generation is optional after a committed scan.
                        # _own_files releases any provisional ownership on failure.
                        coherent = False
                if coherent:
                    pregen_source = files.current_source
                    def _pregen(jb=job, video=thumbnail_owner.source):
                        cap = lease = None
                        try:
                            doc, selected, fence, lease = _thumbnail_snapshot(jb, operation_owner=owner)
                            if selected is not pregen_source or selected['path'] != video:
                                return
                            rows, rs = _thumbnail_validate_report(doc)
                            generation = _thumbnail_select(jb, doc, selected, fence, lease, operation_owner=owner, validated=(rows, rs))
                            cap = _open_preview_capture(video)
                            generated = 0
                            for index in _review_card_rows(rows):
                                try:
                                    _thumbnail_image(jb, index, 'crop', generation.version, operation_owner=owner,
                                                     capture=cap, snapshot=(doc, selected, fence, rows, rs))
                                    generated += 1
                                except _ThumbnailError as error:
                                    if error.code in ('thumbnail_obsolete', 'thumbnail_source_conflict',
                                                      'source_report_pending'):
                                        break
                                    if error.code == 'thumbnail_pending':
                                        with files.report_lock:
                                            stalled = files.thumbnail.retirement is not None
                                        if stalled:
                                            break
                                    continue
                            jb['log'].append('thumbnails ready (%d)' % generated)
                        except Exception:
                            pass
                        finally:
                            try:
                                if cap is not None:
                                    cap.release()
                            finally:
                                if lease is not None:
                                    _thumbnail_release_lease(jb, lease, primary_pending=sys.exc_info()[0] is not None)
                    _start_owned_thread(_pregen, thumbnail_owner)
                next_owner = (_prepare_work(job, "render")
                              if job["options"].get("skip_review") else None)
                ticket = None
                try:
                    with files.report_lock:
                        if not _operation_valid(job, owner) or owner.operation.is_set():
                            raise openscrub.PipelineCancelled()
                        if next_owner is not None:
                            job["log"].append("review skipped — rendering all detections")
                            ticket = _reserve_queue_locked(job, "render", next_owner)
                        else:
                            job["phase"] = "review"
                        outcome = "review"
                        job["progress"] = 0.5
                        job["eta"] = None
                finally:
                    if next_owner is not None and ticket is None:
                        next_owner.release()
                if ticket is not None:
                    enqueue(job, "render", ticket)
            elif action == "render":
                if not owner.report_input:  # compatibility with older queue entries
                    _select_render_input(job, owner)
                args = build_args(dict(job, video=owner.source), for_render=True)
                args._report_input = owner.source
                with files.report_lock:
                    selected = files.current_source
                    if selected is not None:
                        args._hdr_quad_render_proof = selected.get('hdr_quad_proof')
                res = openscrub.run_pipeline(args, cb)
                # Compatibility for substituted pipelines which do not use the new
                # hook. Actual renders publish their terminal fields inside it.
                if not committed:
                    _thumbnail_admit_path(res["output"], owner)
                    with files.report_lock:
                        _recovery_gate(job)
                        if not _operation_valid(job, owner) or owner.operation.is_set():
                            return
                        job.update(output=res["output"], phase="done", progress=1.0, eta=None)
                outcome = "done"
        except openscrub.ScanStopped as stop:
            with files.report_lock:
                if _operation_valid(job, owner) and not owner.operation.is_set():
                    job.update(phase="stopped", stopped_frame=stop.frame,
                               stopped_total=stop.total, error=None, eta=None,
                               progress=_stopped_progress(stop.frame, stop.total))
                    job["log"].append("— stopped at frame %d of %d; progress saved —"
                                      % (stop.frame, stop.total))
                    outcome = "cancelled"
                else:
                    scan_progress.remove(progress_path)   # cancelled meanwhile
        except openscrub.PipelineCancelled:
            if action in ('scan', 'continue'):
                scan_progress.remove(progress_path)       # Cancel discards progress
            recovery = _has_render_recovery(job["dir"])
            with files.report_lock:
                if recovery:
                    files.recovery_required = True
                    job.update(phase="error", error="render delivery requires recovery", eta=None)
                if not committed and not files.recovery_required and _operation_valid(job, owner):
                    job["phase"] = "cancelled"
                    outcome = "cancelled"
                    job["error"] = "cancelled by user"
                    job["failed_action"] = _failed_step(action)
        except BaseException as e:
            msg = str(e) or type(e).__name__
            if isinstance(e, SystemExit):
                msg = "the job stopped unexpectedly (exit %s)" % (e.code,)
            error_code = diagnostics.classify(e) if sink is not None else None
            recovery = _has_render_recovery(job["dir"])
            with files.report_lock:
                if recovery:
                    files.recovery_required = True
                    job.update(phase="error", error="render delivery requires recovery", eta=None)
                if not committed and not files.recovery_required and _operation_valid(job, owner):
                    outcome, diagnostic_error = "error", error_code
                    saved = (_saved_progress_frame(progress_path)
                             if action in ('scan', 'continue') else None)
                    if saved is not None:
                        # The scan's progress survives the error: keep the job
                        # stopped so Continue carries on from the last save.
                        frame, total = saved
                        if isinstance(e, scan_progress.ProgressMismatch):
                            msg = ("Can't continue: %s. Cancel the scan and start it again."
                                   % e.what)
                        elif isinstance(e, scan_progress.ProgressError) and action == 'continue':
                            msg = ("Can't continue: %s. Try Continue scan again; if it keeps "
                                   "failing, Cancel the scan and start it again." % msg)
                        else:
                            msg = _with_disk_full_hint(msg, e, "continue")
                            msg = ("The scan stopped because of an error at %d%% (%s). "
                                   "Continue scan carries on from the last save."
                                   % (int(100 * frame / max(total, 1)), msg))
                        job.update(phase="stopped", stopped_frame=frame, stopped_total=total,
                                   progress=_stopped_progress(frame, total), error=msg)
                        job["log"].append(f"ERROR: {msg}")
                    else:
                        job["phase"] = "error"
                        job["failed_action"] = _failed_step(action)
                        msg = _with_disk_full_hint(msg, e, job["failed_action"])
                        job["error"] = msg
                        job["log"].append(f"ERROR: {msg}")
        finally:
            with files.report_lock:
                if _operation_valid(job, owner):
                    job["eta"] = None
                if action in ('scan', 'continue') and job.get("phase") == "cancelled":
                    # a Cancel that raced a failure still discards the progress
                    scan_progress.remove(progress_path)
    except BaseException:
        escaped = True
        raise
    finally:
        if sink is not None:
            try:
                if escaped:
                    sink.abandon(diagnostic_ref)
                else:
                    if outcome == "superseded" and owner.operation.is_set():
                        outcome = "cancelled"
                    sink.finish(diagnostic_ref, outcome, diagnostic_error)
            finally:
                if WORKER.get("diagnostic_ref") == diagnostic_ref:
                    WORKER.pop("diagnostic_ref", None)


def _report_digest(jdir):
    path = os.path.join(jdir, "report.json")
    try:
        return scan_progress.file_sha256(path)
    except OSError:
        return None


def _stopped_progress(frame, total):
    # The scan frame loop fills the first 45% of the bar (WebCallbacks.progress).
    return round(0.45 * frame / max(total, 1), 5)


def _saved_progress(path):
    """(next_frame, total, meta) of a job's saved scan progress, or None."""
    try:
        state = scan_progress.load(path)
        meta = state.get("meta")
        return (int(state["next_frame"]), int(state["total"]),
                meta if isinstance(meta, dict) else {})
    except (OSError, scan_progress.ProgressError, KeyError, TypeError, ValueError,
            AttributeError):
        return None


def _saved_progress_frame(path):
    """(next_frame, total) of a job's saved scan progress, or None."""
    saved = _saved_progress(path)
    return None if saved is None else saved[:2]


def _failed_step(action):
    """Which step a failed/cancelled job was on: the page offers Retry render
    (keeps the review) for a render and Retry scan for a scan."""
    return "render" if action == "render" else "scan"


_WRITE_ERRNOS = {errno.EIO, errno.EROFS, errno.EACCES, errno.EPERM,
                 getattr(errno, "EDQUOT", -1), getattr(errno, "ESTALE", -1)}


def _with_disk_full_hint(msg, error, step):
    """A full disk or a failed write is the user's to fix: say so, with steps,
    and which retry keeps the work. ffmpeg reports both only in its stderr
    text, so match the message too."""
    retry = ("press Retry render — your review choices are kept" if step == "render"
             else "press Continue scan" if step == "continue"
             else "press Retry scan")
    full = (isinstance(error, OSError) and error.errno == errno.ENOSPC
            or "No space left on device" in msg)
    if full:
        return f"{msg} — the disk is full. Free some disk space, then {retry}."
    write = ("writing the output file failed" in msg
             or any(words in msg for words in openscrub._WRITE_FAILURES))
    os_level = isinstance(error, OSError) and error.errno in _WRITE_ERRNOS
    if not (write or os_level):
        return msg
    what = ("the output could not be written to disk (this is not an encoder "
            "problem)" if write else "a file could not be read or written on disk")
    return (f"{msg} — {what}. Check that the drive holding OpenScrub's data "
            "folder is connected and healthy and has free space, and that no "
            "antivirus, indexer, backup or sync tool is locking files there (on "
            f"Windows, exclude the folder from Defender scanning). Then {retry}.")


def start_worker():
    t = threading.Thread(target=worker, daemon=True, name="job-worker")
    WORKER["thread"] = t
    t.start()
    return t


def check_worker():
    """Watchdog step: if the worker thread is gone, fail the job it was
    running (it can never finish now) and start a fresh worker so the
    queue keeps moving. Returns True when it had to restart one."""
    t = WORKER.get("thread")
    if t is not None and t.is_alive():
        return False
    jid = WORKER.get("current")
    with JOBS_LOCK:
        job = JOBS.get(jid) if jid else None
        lost_action = job is not None and job.get("phase") in _ACTIVE_PHASES
        saved = (_saved_progress_frame(os.path.join(job["dir"], scan_progress.PROGRESS_NAME))
                 if lost_action and job.get("phase") in ("scanning", "queued") else None)
        if saved is not None:
            # The scan's autosaved progress survives the dead worker.
            job.update(phase="stopped", stopped_frame=saved[0], stopped_total=saved[1],
                       progress=_stopped_progress(*saved), eta=None,
                       error="the job worker stopped unexpectedly — Continue scan "
                             "carries on from the last save")
            job["log"].append("ERROR: " + job["error"])
        elif lost_action:
            rendering = job.get("phase") in ("rendering", "queued_render")
            job["phase"] = "error"
            job["eta"] = None
            job["failed_action"] = "render" if rendering else "scan"
            job["error"] = ("the job worker stopped unexpectedly — the "
                            "server restarted it; Retry render renders again "
                            "with your saved review choices" if rendering else
                            "the job worker stopped unexpectedly — the "
                            "server restarted it; Retry re-runs the scan "
                            "with the file already on the server")
            job["log"].append("ERROR: " + job["error"])
    WORKER["current"] = None
    if t is not None:
        if DIAGNOSTICS is not None:
            lost_ref = WORKER.pop("diagnostic_ref", None)
            DIAGNOSTICS.abandon(lost_ref)
            DIAGNOSTICS.emit("worker_restarted",
                             active_action_lost=lost_action or lost_ref is not None)
        print("[web] job worker was not running — restarted it", flush=True)
    start_worker()
    return True


def _worker_watchdog():
    while True:
        time.sleep(5)
        try:
            check_worker()
        except Exception as e:
            print(f"[web] worker watchdog: {e}", flush=True)
        _expire_idle_report_parses()


# ----------------------------------------------------------------------------
# Auth
# ----------------------------------------------------------------------------

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
    """Admit file work before intake parsing or a view captures a job."""
    if request.endpoint == "allowlist":
        g.file_owner = _own_files()  # shared file lives directly in JOBS_DIR
        return
    if request.path.startswith("/api/jobs"):
        # Deletion closes admissions itself, without becoming its own busy owner.
        if request.endpoint == "job_delete":
            with VAULT_LOCK:
                _validate_files_locked()
            return
        with VAULT_LOCK:
            jid = (request.view_args or {}).get("jid")
            job = JOBS.get(jid) if jid is not None else None
            if jid is not None and job is None:
                abort(404)
            _validate_files_locked(job)
            if job is not None and request.endpoint not in {"job_status", "job_log", "job_cancel"}:
                _recovery_gate(job)
            if (job is not None and job.get('_checkpoint_unfinished') and
                    request.endpoint in {'job_frame_at', 'job_video_stream', 'job_boxes_at',
                        'job_track_object'}):
                abort(409, 'partial checkpoint review is not available')
            read_source = request.endpoint in {
                "job_retry", "job_render", "job_track_object", "job_mediainfo",
                "job_detections", "job_detframe", "job_thumb", "job_frame_at", "job_video_stream", "job_edit_sample",
                "job_letter_gap"}
            version = request.args.get('v')
            versioned_image = (request.endpoint in {'job_thumb', 'job_detframe'}
                               and version is not None and re.fullmatch(r'[0-9a-f]{32}', version))
            try:
                g.file_owner = _reserve_files_locked(job, read_source=read_source,
                                                     thumbnail_recovery=bool(versioned_image))
            except _ThumbnailError as error:
                return _thumbnail_error_response(error)
        try:
            if g.file_owner.source:
                _thumbnail_resolve_admission(g.file_owner, g.file_owner.source)
        except _ThumbnailArtifactPending:
            if request.endpoint in {'job_detections', 'job_thumb', 'job_detframe'}:
                return _thumbnail_error_response(_ThumbnailError(
                    'thumbnail_pending', 409, 'Thumbnail cleanup is in progress'))
            abort(409, 'source cleanup is in progress')
        except OSError:
            if request.endpoint in {'job_detections', 'job_thumb', 'job_detframe'}:
                return _thumbnail_error_response(_ThumbnailError(
                    'thumbnail_source_conflict', 409, 'Source requires rescan'))
            raise


@app.after_request
def _finish_file_response(response):
    if (request.endpoint in {"job_edit_sample", "job_detections", "job_thumb", "job_detframe",
                             "job_plate_search", "job_plate_search_cancel"}
            and not g.get('thumbnail_versioned_response')):
        response.headers["Cache-Control"] = "private, no-store"
    children = g.pop("file_children", [])
    lease = g.pop("file_owner", None)
    if response.direct_passthrough:
        if lease is None and children:
            lease = children.pop(0)
        if lease is not None:
            lease.related.extend(children)
            response.response = OwnedIterable(response.response, lease)
    else:
        for child in children:
            child.release()
        if lease is not None:
            _release_thumbnail_request_lease(lease)
    return response


@app.teardown_request
def _release_failed_request(error):
    for child in g.pop("file_children", []):
        child.release()
    lease = g.pop("file_owner", None)
    if lease is not None:
        _release_thumbnail_request_lease(lease, primary_pending=error is not None)


def _release_thumbnail_request_lease(lease, *, primary_pending=False):
    if request.endpoint in {'job_detections', 'job_thumb', 'job_detframe'}:
        job = JOBS.get((request.view_args or {}).get('jid'))
        if job is not None and job.get('_files') is lease.state:
            _thumbnail_release_lease(job, lease, primary_pending=primary_pending)
            return
    lease.release()



@app.before_request
def refuse_upload_without_disk_room():
    """Registered after auth on purpose, but still BEFORE the view runs:
    by the time create_job touches request.files, werkzeug has already
    spooled the whole upload into the temp dir — too late to protect the
    disk. Checking the Content-Length header here reads nothing."""
    if request.method == "POST" and request.path == "/api/jobs":
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
    except (ValueError, RecursionError):
        return jsonify({"error": "Scan options must be a JSON object."}), 400
    if not isinstance(options, dict):
        return jsonify({"error": "Scan options must be a JSON object."}), 400
    try:
        _optional_plate_settings(options)
    except ValueError:
        return jsonify({"error": "Invalid optional plate policy settings."}), 400
    checkpoint = options.get('checkpoint_review', False)
    if type(checkpoint) is not bool:
        return jsonify({"error": "checkpoint_review must be a boolean."}), 400
    if checkpoint:
        categories = options.get('categories')
        selected = ({part.strip() for part in categories.split(',') if part.strip()}
                    if isinstance(categories, str) else None)
        unsupported = ('windows', 'ignore_zones', 'skip_review', 'skip_start',
                       'skip_end', 'detect_windows_frac', 'audio_pii', 'dense_faces',
                       'face_heads', 'phrases', 'allow_names', 'extra_names')
        if (selected not in ({'qrcode'}, {'none'}, set())
                or any(options.get(key) for key in unsupported)
                or options.get('scroll_track', 'off') != 'off'
                or options.get('no_backtrack', True) is not True
                or options.get('no_vfr_fix', True) is not True):
            return jsonify({"error": "Checkpoint scans support only QR or no categories without windows, scrolling, backtracking, or normalization."}), 400
    jobs = []
    files = request.files.getlist("video")
    if files and files[0].filename:
        if checkpoint:
            # Stage all options and uploads before registering any job. A
            # failure cannot strand unreported queued work or partial copies.
            allocated = []
            try:
                for f in files:
                    name = os.path.basename(f.filename.replace("\\", "/"))
                    allocated.append(new_job("", options, name, _defer_registration=True))
                for f, job in zip(files, allocated):
                    name = os.path.basename(f.filename.replace("\\", "/"))
                    ext = os.path.splitext(name)[1].lower()
                    if ext not in MEDIA_EXTS:
                        ext = ".mp4"
                    path = os.path.join(job["dir"], "input" + ext)
                    f.save(path)
                    job["video"] = path
                    job["size"] = os.path.getsize(path)
            except BaseException as error:
                for job in allocated:
                    _discard_unregistered_checkpoint(job)
                if isinstance(error, _CheckpointOptionsError):
                    return jsonify({"error": "Could not save checkpoint settings; no scan was queued."}), 507
                if isinstance(error, OSError):
                    return jsonify({"error": "Could not save checkpoint upload; no scan was queued."}), 507
                raise
            _register_new_jobs(allocated)
            for job in allocated:
                enqueue(job, "scan")
                jobs.append(job["id"])
        else:
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
                enqueue(job, "scan")
                jobs.append(job["id"])
    elif request.form.get("server_path"):
        p = _request_source_path(request.form["server_path"].strip())
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
        try:
            job = new_job(p, options, os.path.basename(p))
        except _CheckpointOptionsError:
            return jsonify({"error": "Could not save checkpoint settings; no scan was queued."}), 507
        try:
            job["size"] = os.path.getsize(p)
        except OSError:
            pass
        enqueue(job, "scan")
        jobs.append(job["id"])
    else:
        return jsonify({"error": "no file uploaded and no server path"}), 400
    return jsonify({"jobs": jobs})


@app.route("/api/jobs")
def list_jobs():
    with VAULT_LOCK:
        _validate_files_locked()
        with JOBS_LOCK:
            js = sorted(JOBS.values(), key=lambda j: -j["created"])
        leases = [FILES.reserve(j) for j in js if not FILES.initialize(j).closed]
        js = [j for j in js if not FILES.initialize(j).closed]
    try:
        return jsonify([job_public(j) for j in js])
    finally:
        for lease in leases:
            lease.release()



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
    job = JOBS.get(jid) or abort(404)
    return jsonify(_delete_job(job))


def _delete_job(job):
    jid = job["id"]
    target = FILES.initialize(job)
    with JOBS_LOCK:
        owners = list(JOBS.values())
    for owner in owners:
        _thumbnail_lifecycle_cleanup(owner, target=target)
    with VAULT_LOCK:
        _validate_files_locked(job)
        state = FILES.initialize(job)
        if state.count or job.get("phase") in _ACTIVE_PHASES:
            abort(409, "job files are still in use — wait for cleanup")
        state.closed = True
        lease = FILES.reserve()  # deletion owns the tree, not an admitted job
    with lease:
        # Forget current receipts in bounded batches; their last references and
        # associated job data are disposed outside the store guard.
        while True:
            discarded = []
            record = None
            with VAULT_LOCK:
                for _ in range(32):
                    if not state.thumbnail_artifacts:
                        break
                    path = state.thumbnail_artifacts.pop()
                    record = FILES.thumbnail_paths.get(path)
                    if record is not None and record['job'] is job:
                        discarded.append(record)
                        _thumbnail_forget_artifact_locked(record)
                    else:
                        state.thumbnail_artifacts.discard(path)
                done = not state.thumbnail_artifacts
            del discarded
            record = None
            if done:
                break
        with state.report_lock:
            state.operation = None
        _forget_report_parses()  # the deleted report's parse leaves memory too
        if _reap_job_dir(job["dir"], jid):
            with JOBS_LOCK:
                JOBS.pop(jid, None)
            return {"ok": True}
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
            try:
                # A retry does not keep the store busy during its sleep. If
                # locked, leave the marker for unlock/startup/retention.
                retry_lease = _own_files()
            except Exception:
                continue
            with retry_lease:
                if not os.path.isdir(job["dir"]):
                    return
                if _reap_job_dir(job["dir"], jid, retries=1):
                    print(f"[web] job {jid} delete completed on retry", flush=True)
                    return
    threading.Thread(target=_retry, daemon=True).start()
    return {"ok": True, "pending": True,
            "note": "some files were still in use; removal will complete automatically"}



@app.route("/api/jobs/<jid>/retry", methods=["POST"])
def job_retry(jid):
    """Re-run a failed or cancelled job's SCAN, reusing the file that is
    already on the server. Before this existed, the only path after an
    error was Start scan — which uploaded the same multi-GB file into a
    fresh job dir on every attempt until the disk filled (issue #16)."""
    job = JOBS.get(jid) or abort(404)
    prepared = _prepare_work(job, "scan")
    ticket = None
    try:
        video = prepared.source
        exists = bool(video and os.path.exists(video))
        with FILES.initialize(job).report_lock:
            _report_current(job)
            if _unfinished_checkpoint_locked(job):
                return jsonify({"error": "unfinished checkpoint cannot be retried as a new scan"}), 409
            if (FILES.initialize(job).active is not None
                    or FILES.initialize(job).work > 1):
                return jsonify({"error": "job work is still cleaning up"}), 409
            if job["phase"] not in ("error", "cancelled"):
                return jsonify({"error": "only a failed or cancelled job can be retried"}), 409
            if not exists:
                return jsonify({"error": "the job's video file is no longer on the server — start a new scan"}), 410
            job.update(error=None, output=None, progress=0.0, eta=None)
            job["log"].append("— retrying scan (reusing the file already on the server — nothing is re-uploaded) —")
            ticket = _reserve_queue_locked(job, "scan", prepared)
    finally:
        if ticket is None:
            prepared.release()
    enqueue(job, "scan", ticket)
    return jsonify({"ok": True})


@app.route('/api/jobs/<jid>/resume', methods=['POST'])
def job_resume(jid):
    """Queue a resume only for the exact saved report generation."""
    job = JOBS.get(jid) or abort(404)
    body = request.get_json(silent=True)
    token = body.get('resume_token') if isinstance(body, dict) else None
    if (not isinstance(body, dict) or set(body) != {'resume_token'}
            or not isinstance(token, str) or re.fullmatch('[0-9a-f]{64}', token) is None):
        return jsonify(error='a current resume token is required'), 400
    prepared = _prepare_work(job, 'scan')
    ticket = None
    try:
        files = FILES.initialize(job)
        with files.report_lock:
            _report_current(job)
            _recovery_gate(job)
            if (job.get('phase') != 'paused' or not job.get('_checkpoint_unfinished')
                    or job.get('options', {}).get('checkpoint_review') is not True
                    or files.active is not None or files.work > 1):
                return jsonify(error='checkpoint is not ready to resume'), 409
            current = _checkpoint_resume_token_locked(job)
            if not secrets.compare_digest(token, current):
                return jsonify(error='checkpoint changed; save again before resuming'), 409
            if prepared.source_state is not None and prepared.source_state is not files:
                return jsonify(error='checkpoint source is owned by another job'), 409
            prepared.checkpoint_resume_token = current
            ticket = _reserve_queue_locked(job, 'resume', prepared)
    finally:
        if ticket is None:
            prepared.release()
    enqueue(job, 'resume', ticket)
    return jsonify(ok=True, state='queued'), 202


@app.route("/api/jobs/<jid>")
def job_status(jid):
    job = JOBS.get(jid) or abort(404)
    return jsonify(job_public(job))


@app.route("/api/jobs/<jid>/log")
def job_log(jid):
    job = JOBS.get(jid) or abort(404)
    raw = request.args.get("from", "0")
    epoch = request.args.get("epoch")
    if len(raw) > 64 or (epoch is not None and len(epoch) > 128):
        return jsonify({"error": "invalid log cursor"}), 400
    try:
        frm = max(0, int(raw))
    except ValueError:
        return jsonify({"error": "invalid log cursor"}), 400
    snapshot = job["log"].snapshot(frm, epoch)
    return jsonify({key: snapshot[key] for key in
                    ("from", "lines", "len", "epoch", "base", "reset",
                     "dropped", "truncated")})


@app.route("/api/jobs/<jid>/preview.jpg")
def job_preview(jid):
    job = JOBS.get(jid) or abort(404)
    p = os.path.join(job["dir"], "preview.jpg")
    try:
        with open(p, "rb") as preview:
            snapshot = preview.read()
    except FileNotFoundError:
        abort(404)
    # Publication replaces complete files; this opened generation is immutable.
    # Derive length and ETag from its bytes, closing the path-stat/open gap.
    # Omit Last-Modified: second-resolution dates cannot distinguish rapid frames.
    return send_file(BytesIO(snapshot), mimetype="image/jpeg",
                     download_name="preview.jpg", max_age=0,
                     etag=hashlib.sha256(snapshot).hexdigest())


@app.route('/api/jobs/<jid>/stop', methods=['POST'])
def job_stop(jid):
    """Request an owned scan to stop after its current whole frame."""
    job = JOBS.get(jid) or abort(404)
    files = FILES.initialize(job)
    with files.report_lock:
        _report_current(job)
        _recovery_gate(job)
        owner = files.active
        stop = getattr(owner, 'checkpoint_stop', None)
        if (job.get('phase') != 'scanning' or job['options'].get('checkpoint_review') is not True
                or owner is None or stop is None or not _operation_valid(job, owner)
                or owner.operation.is_set()):
            return jsonify(error='no active checkpoint scan to stop'), 409
        stop.set()
    return jsonify(state='stopping'), 202


@app.route('/api/jobs/<jid>/stop_scan', methods=['POST'])
def job_stop_scan(jid):
    """Stop a running scan after its current frame and save its progress,
    so Continue scan can carry on later (frees the GPU in between)."""
    job = JOBS.get(jid) or abort(404)
    files = FILES.initialize(job)
    with files.report_lock:
        owner = files.active
        stop = getattr(owner, 'progress_stop', None)
        if (job.get('phase') != 'scanning' or owner is None or stop is None
                or not _operation_valid(job, owner) or owner.operation.is_set()):
            return jsonify(error='this scan cannot be stopped and continued'), 409
        stop.set()
        job['log'].append('— stopping: saving progress after the current frame —')
    return jsonify(state='stopping'), 202


@app.route('/api/jobs/<jid>/continue', methods=['POST'])
def job_continue(jid):
    """Queue a stopped scan to carry on from its saved progress."""
    job = JOBS.get(jid) or abort(404)
    prepared = _prepare_work(job, 'continue')
    ticket = None
    try:
        files = FILES.initialize(job)
        with files.report_lock:
            _report_current(job)
            if files.active is not None or files.work > 1:
                return jsonify(error='job work is still cleaning up'), 409
            if job.get('phase') != 'stopped':
                return jsonify(error='only a stopped scan can be continued'), 409
            if not os.path.exists(os.path.join(job['dir'], scan_progress.PROGRESS_NAME)):
                return jsonify(error='this job has no saved scan progress'), 409
            job.update(error=None, eta=None)
            job['log'].append('— continuing the stopped scan —')
            ticket = _reserve_queue_locked(job, 'continue', prepared)
    finally:
        if ticket is None:
            prepared.release()
    enqueue(job, 'continue', ticket)
    return jsonify(ok=True)


@app.route("/api/jobs/<jid>/cancel", methods=["POST"])
def job_cancel(jid):
    """Cancel a job. The job the worker is RUNNING stops cooperatively at
    its next checkpoint. Any other active job (still queued, or orphaned by
    a worker that died) is cancelled on the spot — before, Cancel only set
    a flag the worker checks mid-scan, so a job the worker never picked up
    could never be cancelled (or deleted: delete refuses active jobs)."""
    job = JOBS.get(jid) or abort(404)
    files = FILES.initialize(job)
    operation = files.operation  # capture the operation this request cancels
    if operation is not None:
        operation.set()  # promptly signal compute, before waiting for report I/O
    released = []
    with files.report_lock:
        _report_current(job)
        if files.operation is not operation:
            # That attempt finished/replaced while this request waited. Do not
            # signal, invalidate or release a newer attempt's queue ownership.
            return jsonify({"ok": True})
        if operation is None:
            job["cancel"].set()  # idle/intake: no running compute to interrupt
        files.operation = None  # Event.clear cannot revive the captured attempt
        thumbs.invalidate_locked(files.thumbnail, 'operation cancelled')
        if files.source_pair is not None:
            files.source_pair = None
            files.source_retired = True
            files.source_status, files.source_reason = 'unavailable', 'scan source adoption cancelled'
        with JOBS_LOCK:
            released = list(files.queued.values())
            files.queued.clear()
            job["qgen"] = job.get("qgen", 0) + 1
        if files.active in released:
            files.active = None
        if job.get('_checkpoint_unfinished') and not files.recovery_required:
            # Cancel a resume without losing the already-published checkpoint.
            # The still-active owner keeps edit admission closed until cleanup;
            # the next reader must rediscover and verify the source afresh.
            files.current_source = files.source_pair = None
            files.source_retired = False
            files.source_status, files.source_reason = 'undiscovered', None
            files.source_report_bound = False
            job.update(phase='paused', error=None, output=None, eta=None)
            job['log'].append('— resume cancelled; saved checkpoint retained —')
        elif job.get("phase") == "stopped":
            # Cancel discards a stopped scan's saved progress.
            scan_progress.remove(os.path.join(job["dir"], scan_progress.PROGRESS_NAME))
            job.update(phase="cancelled", error="cancelled by user", eta=None,
                       failed_action="scan")
            job["log"].append("— cancelled; saved scan progress discarded —")
        elif job.get("phase") in _ACTIVE_PHASES:
            step = "render" if job.get("phase") in ("rendering", "queued_render") else "scan"
            job.update(phase="cancelled", error="cancelled by user", eta=None,
                       failed_action=step)
            job["log"].append("— cancelled —")
            if step == "scan" and files.active is None:
                # nothing is running that could still save: discard now (a
                # running scan discards its own progress when it sees Cancel)
                scan_progress.remove(os.path.join(job["dir"], scan_progress.PROGRESS_NAME))
        if job.get("trackbg", {}).get("state") == "running":
            job["trackbg"] = {"state": "done", "added": 0,
                              "error": "cancelled by user"}
    for lease in released:
        lease.release()
    return jsonify({"ok": True})


def _load_job_report(job):
    with open(os.path.join(job["dir"], "report.json"), encoding="utf-8") as f:
        return json.load(f)


def _capture_frame_source(job, output=False):
    """Capture admitted selection and its owners using sequential short locks."""
    state = FILES.initialize(job)
    lease = g.get("file_owner") if has_request_context() else None
    with state.report_lock:
        _report_current(job)
        _recovery_gate(job)
        if output and _unfinished_checkpoint_locked(job):
            abort(409, "unfinished checkpoint has no completed output")
        selected_output = job.get("output") if output else None
        path = selected_output or _job_video(job)
        epoch = state.output_epoch
        source_job = job
        source_state = state
        if not selected_output and lease is not None and lease.state is state:
            source_job, source_state = lease.source_job, lease.source_state
    source_epoch = None
    if source_job is not None and source_state is not state:
        with source_state.report_lock:
            _report_current(source_job)
            _recovery_gate(source_job)
            source_epoch = source_state.output_epoch
    return dict(job=job, state=state, epoch=epoch, path=path, output=output,
                selection=selected_output, source_job=source_job,
                source_state=source_state, source_epoch=source_epoch)


def _frame_source_current(snapshot):
    job, state = snapshot["job"], snapshot["state"]
    with state.report_lock:
        _report_current(job)
        _recovery_gate(job)
        if snapshot["output"] and _unfinished_checkpoint_locked(job):
            abort(409, "unfinished checkpoint has no completed output")
        selected = job.get("output") if snapshot["output"] else None
        if (FILES.initialize(job) is not state or state.output_epoch != snapshot["epoch"]
                or selected != snapshot["selection"]
                or (selected or _job_video(job)) != snapshot["path"]):
            return False
    source_job, source_state = snapshot["source_job"], snapshot["source_state"]
    if source_job is not None and source_state is not state:
        with source_state.report_lock:
            _report_current(source_job)
            _recovery_gate(source_job)
            if (FILES.initialize(source_job) is not source_state
                    or source_state.output_epoch != snapshot["source_epoch"]):
                return False
    return True


def _validated_frame_read(job, output, decode):
    for attempt in range(2):
        snapshot = _capture_frame_source(job, output)
        error = None
        try:
            value = decode(snapshot["path"])
        except Exception as caught:
            error = caught
        if _frame_source_current(snapshot):
            if error is not None:
                raise error
            return value
    abort(409, "output changed during frame read; retry")


def _file_stamp(stat):
    return (stat.st_dev, stat.st_ino, stat.st_size, stat.st_mtime_ns, stat.st_ctime_ns)


def _report_committed_locked(job, doc=None, scan_owner=None, *, _thumbnail_ready=False,
                             _report_stat=None):
    """Success-only notification; caller owns report/lifetime transaction."""
    files = FILES.initialize(job)
    files.committed_report_epoch += 1
    if not _thumbnail_ready:
        thumbs.invalidate_locked(files.thumbnail, 'report committed')
    if scan_owner is not None:
        expected = doc.get('provenance', {}).get('input')
        report_stat = (_report_stat if _report_stat is not None else
                       os.stat(os.path.join(job['dir'], 'report.json')))
        files.source_pair = (scan_owner.operation, files.committed_report_epoch, expected,
                             _file_stamp(report_stat))
        files.source_status, files.source_reason = 'pending', None
    elif files.source_pair is not None and files.source_status == 'unavailable':
        operation, _, expected, _ = files.source_pair
        files.source_pair = (operation, files.committed_report_epoch, expected,
                             _file_stamp(os.stat(os.path.join(job['dir'], 'report.json'))))


def _probe_exact_source(path):
    return exact.probe_source(path)


@contextlib.contextmanager
def _exact_owner_guard(job, lease):
    """Hold relevant report locks in a stable order; never acquire VAULT here."""
    state = FILES.initialize(job)
    foreign = lease.source_state if lease is not None else None
    if foreign is state:
        foreign = None
    states = sorted([state] + ([foreign] if foreign is not None else []), key=id)
    with contextlib.ExitStack() as stack:
        for item in states:
            stack.enter_context(item.report_lock)
        if foreign is not None:
            source_job = lease.source_job
            _report_current(source_job)
            if (FILES.initialize(source_job) is not foreign or foreign.recovery_required
                    or foreign.output_epoch != lease.exact_source_epoch):
                raise exact.ExactError('containing source changed', 409, 'sample_conflict')
        yield


def _snapshot_exact_source_owner(job, lease):
    foreign = lease.source_state
    if foreign is not None and foreign is not FILES.initialize(job):
        with foreign.report_lock:
            _report_current(lease.source_job)
            if foreign.recovery_required:
                raise exact.ExactError('containing source requires recovery', 409, 'sample_conflict')
            lease.exact_source_epoch = foreign.output_epoch


def _prepare_observed_source(job, path, thumbnail_recovery=False, *, checkpoint_sha256=None):
    """Reserve containing lifetime before first stat/probe; never under report_lock."""
    with VAULT_LOCK:
        _validate_files_locked(job)
        lease = _reserve_files_locked(job, source=path, thumbnail_recovery=thumbnail_recovery)
    try:
        canonical = lease.source
        _snapshot_exact_source_owner(job, lease)
        _thumbnail_resolve_admission(lease, canonical)
        with open(canonical, 'rb', opener=_thumbnail_nonblocking_opener) as opened:
            observed = os.fstat(opened.fileno())
            if not stat.S_ISREG(observed.st_mode):
                raise exact.ExactError('source is not a regular file', 409, 'sample_conflict')
            stamp = _file_stamp(observed)
            if stamp != _file_stamp(os.stat(canonical)):
                raise exact.ExactError('source changed while opening', 409, 'sample_conflict')
            files = FILES.initialize(job)
            with files.report_lock:
                cached = files.current_source
                cached = cached if cached and (cached['path'], cached['stamp']) == (canonical, stamp) else None
            if cached is not None:
                facts, policy_error = cached['facts'], cached['policy_error']
            else:
                try:
                    facts, policy_error = _probe_exact_source(canonical), None
                except exact.ExactError as error:
                    facts, policy_error = None, str(error)
            digest = cached.get('checkpoint_sha256') if cached is not None else None
            if checkpoint_sha256 is not None:
                if digest is None:
                    hasher = hashlib.sha256()
                    for chunk in iter(lambda: opened.read(1024 * 1024), b''):
                        hasher.update(chunk)
                    digest = hasher.hexdigest()
                if digest != checkpoint_sha256:
                    raise exact.ExactError('checkpoint source changed; rescan required', 409, 'sample_conflict')
            if stamp != _file_stamp(os.fstat(opened.fileno())) or stamp != _file_stamp(os.stat(canonical)):
                raise exact.ExactError('source changed during preparation', 409, 'sample_conflict')
        with _exact_owner_guard(job, lease):
            pass  # Foreign owner must still match the pre-I/O snapshot.
        prepared = dict(path=canonical, stamp=stamp, facts=facts, policy_error=policy_error)
        if cached is not None and cached.get('hdr_quad_proof') is not None:
            prepared['hdr_quad_proof'] = cached['hdr_quad_proof']
        if digest is not None:
            prepared['checkpoint_sha256'] = digest
        return prepared, lease
    except _ThumbnailArtifactPending:
        _thumbnail_release_lease(job, lease, primary_pending=True)
        if has_request_context() and request.endpoint in {'job_detections', 'job_thumb', 'job_detframe'}:
            raise _ThumbnailError('thumbnail_pending', 409, 'Thumbnail cleanup is in progress') from None
        raise exact.ExactError('source cleanup is in progress', 409, 'sample_conflict') from None
    except BaseException:
        _thumbnail_release_lease(job, lease, primary_pending=True)
        raise


def _select_observed_locked(job, prepared, authoritative=False, *, report_bound=True):
    files = FILES.initialize(job)
    try:
        if (_file_stamp(os.stat(prepared['path'])) != prepared['stamp']
                or not authoritative and os.path.realpath(job['video']) != prepared['path']):
            raise exact.ExactError('source changed before association', 409, 'sample_conflict')
    except OSError:
        raise exact.ExactError('source unavailable before association', 409, 'sample_conflict') from None
    current = files.current_source
    same = current and (current['path'],current['stamp']) == (prepared['path'],prepared['stamp'])
    if not authoritative and files.source_status == 'pending':
        raise exact.ExactError('scan report awaits source adoption', 409, 'source_report_pending')
    if not authoritative and (files.source_retired or current is not None and not same):
        thumbs.invalidate_locked(files.thumbnail, 'source changed')
        files.source_retired = True
        files.current_source = None
        files.source_status, files.source_reason = 'unavailable', 'observed source changed; rescan required'
        raise exact.ExactError(files.source_reason)
    new_proof = (same and prepared.get('checkpoint_sha256') is not None and
                 current.get('checkpoint_sha256') != prepared['checkpoint_sha256'])
    if new_proof:
        thumbs.invalidate_locked(files.thumbnail, 'checkpoint source verified')
    if not same or new_proof:
        files.source_epoch += 1
        prepared = dict(prepared, source_ref='%s:%d' % (files.incarnation, files.source_epoch))
        files.current_source = prepared
    files.source_retired = False
    if authoritative:
        files.source_pair = None
    files.source_status, files.source_reason = 'coherent', None
    if report_bound:
        files.source_report_bound = True
    return files.current_source


def _adopt_scan_source(job, owner, hdr_proof=None, scan_digest=None):
    files = FILES.initialize(job)
    with files.report_lock:
        pair = files.source_pair
        if (pair is None or pair[0] is not owner.operation or
                not _operation_valid(job, owner) or owner.operation.is_set()):
            return False
    prepared = lease = None
    try:
        if not isinstance(pair[2], str) or not pair[2]:
            raise exact.ExactError('scan report has no selected input')
        prepared, lease = _prepare_observed_source(job, pair[2])
        with _exact_owner_guard(job, lease):
            if (files.source_pair != pair or not _operation_valid(job, owner)
                    or owner.operation.is_set()):
                return False
            if _file_stamp(os.stat(os.path.join(job['dir'], 'report.json'))) != pair[3]:
                raise exact.ExactError('committed scan report changed during adoption', 409, 'sample_conflict')
            selected = _select_observed_locked(job, prepared, authoritative=True)
            selected.pop('hdr_quad_proof', None)
            if isinstance(hdr_proof, dict) and hdr_proof.get('scan_sha256') == scan_digest:
                doc = _load_job_report(job)
                if openscrub.hdr_quad_pairs.usable(hdr_proof, doc, selected):
                    selected['hdr_quad_proof'] = hdr_proof
            job['video'] = selected['path']
            return True
    except Exception as error:
        with files.report_lock:
            if files.source_pair == pair and _operation_valid(job, owner) and not owner.operation.is_set():
                files.source_status, files.source_reason = 'unavailable', str(error)
                job['log'].append('exact source unavailable: '+str(error))
        return False
    finally:
        if lease is not None:
            lease.release()


def _exact_snapshot(job):
    """One parsed raw document and one convergent current source descriptor."""
    files = FILES.initialize(job)
    path = os.path.join(job['dir'], 'report.json')
    with files.report_lock:
        _report_current(job)
        fence = files.committed_report_epoch, files.operation
        observation = (files.incarnation, files.current_source, files.source_epoch,
                       files.source_status, files.source_pair)
        if files.source_status == 'pending':
            raise exact.ExactError('scan report awaits source adoption', 409, 'source_report_pending')
        if files.active is not None:
            raise exact.ExactError('job work is active', 409, 'sample_conflict')
        recovery = files.source_pair if files.source_status == 'unavailable' else None
        if files.source_retired and recovery is None:
            raise exact.ExactError(files.source_reason)
    try:
        with open(path, encoding='utf-8') as opened:
            report_stamp = _file_stamp(os.fstat(opened.fileno()))
            doc = json.load(opened)
            if report_stamp != _file_stamp(os.fstat(opened.fileno())) or report_stamp != _file_stamp(os.stat(path)):
                raise exact.ExactError('report changed while reading', 409, 'sample_conflict')
    except FileNotFoundError:
        raise exact.ExactError('job report not found', 404, 'missing_report') from None
    except exact.ExactError:
        raise
    except (ValueError, UnicodeError):
        raise exact.ExactError('invalid raw report') from None
    if not isinstance(doc, dict):
        raise exact.ExactError('legacy list report has no exact timeline')
    marker = _checkpoint_marker(doc)
    evidence = marker or _completed_checkpoint(doc)
    candidate = doc.get('provenance', {}).get('input')
    if not isinstance(candidate, str) or not candidate:
        raise exact.ExactError('report has no selected scan input')
    canonical = os.path.realpath(candidate)
    with files.report_lock:
        _report_current(job)
        try:
            changed = ((files.committed_report_epoch, files.operation) != fence
                       or (fence[1] is not None and fence[1].is_set())
                       or files.active is not None or files.source_status == 'pending'
                       or _file_stamp(os.stat(path)) != report_stamp)
        except FileNotFoundError:
            changed = True
        if changed:
            raise exact.ExactError('source/report selection changed', 409, 'sample_conflict')
        if recovery is None and canonical != os.path.realpath(job['video']):
            if files.current_source is not None:
                thumbs.invalidate_locked(files.thumbnail, 'source changed')
                files.source_retired = True
                files.current_source = None
                files.source_status, files.source_reason = 'unavailable', 'selected scan path changed; rescan required'
            raise exact.ExactError('report and selected scan input disagree')
    if recovery and report_stamp != recovery[3]:
        raise exact.ExactError('committed scan report changed before recovery', 409, 'sample_conflict')
    if recovery and (recovery[0] is not fence[1] or recovery[0].is_set()
                     or canonical != os.path.realpath(recovery[2])):
        raise exact.ExactError('scan adoption was cancelled or replaced')
    lease = None
    try:
        if evidence is None:
            prepared, lease = _prepare_observed_source(job, canonical)
        else:
            prepared, lease = _prepare_observed_source(job, canonical,
                checkpoint_sha256=evidence['input_sha256'])
        with _exact_owner_guard(job, lease):
            _report_current(job)
            if ((files.committed_report_epoch, files.operation) != fence
                    or files.active is not None or _file_stamp(os.stat(path)) != report_stamp
                    or files.source_status == 'pending'):
                raise exact.ExactError('source/report selection changed', 409, 'sample_conflict')
            if recovery is not None and (
                    files.source_pair != recovery or recovery[0] is not files.operation
                    or recovery[0].is_set() or recovery[1] != files.committed_report_epoch
                    or recovery[3] != report_stamp
                    or prepared['path'] != os.path.realpath(recovery[2])):
                raise exact.ExactError('scan recovery authority changed', 409, 'sample_conflict')
            if evidence is not None:
                _checkpoint_source_policy(evidence, prepared)
            selected = _select_observed_locked(job, prepared, authoritative=recovery is not None)
            if recovery:
                job['video'] = selected['path']
        return doc, selected, (fence, report_stamp), lease
    except FileNotFoundError:
        if lease is not None:
            lease.release()
        raise exact.ExactError('selected source not found', 404, 'missing_source') from None
    except BaseException:
        if lease is not None:
            lease.release()
        raise


class _ThumbnailError(Exception):
    def __init__(self, code, status, detail):
        super().__init__(detail)
        self.code, self.status, self.detail = code, status, detail


def _thumbnail_error_response(error):
    value = {'error': error.code, 'detail': error.detail}
    if error.code == 'thumbnail_obsolete':
        value['refresh'] = 'detections'
    return jsonify(value), error.status


def _thumbnail_nonblocking_opener(path, flags):
    return os.open(path, flags | getattr(os, 'O_NONBLOCK', 0)
                   | getattr(os, 'O_NOFOLLOW', 0) | getattr(os, 'O_BINARY', 0))


class _ThumbnailHandle:
    """Descriptor owner established before any higher-level wrapper exists."""
    def __init__(self):
        self.fd = None
        self.close_uncertain = False

    @property
    def closed(self):
        return self.fd is None

    def fileno(self):
        if self.fd is None:
            raise ValueError('closed thumbnail')
        return self.fd

    def read(self):
        chunks = []
        while True:
            chunk = os.read(self.fileno(), 65536)
            if not chunk:
                return b''.join(chunks)
            chunks.append(chunk)

    def close(self):
        if self.fd is not None:
            if self.close_uncertain:
                raise OSError('thumbnail descriptor close outcome is uncertain')
            # Any interruption can occur after the descriptor was consumed.
            self.close_uncertain = True
            os.close(self.fd)
            self.fd = None
            self.close_uncertain = False


def _thumbnail_open(path, reader):
    handle = _ThumbnailHandle()
    reader.file = handle
    handle.fd = _thumbnail_nonblocking_opener(path, os.O_RDONLY)
    return handle


def _source_observation_current_locked(job, observation, fence, report_stamp):
    files = FILES.initialize(job)
    incarnation, selected, epoch, status, pair = observation
    if (files.incarnation != incarnation or files.current_source is not selected
            or files.source_epoch != epoch or files.source_status != status
            or files.source_pair != pair or (files.committed_report_epoch, files.operation) != fence
            or fence[1] is not None and fence[1].is_set()):
        return False
    try:
        return _file_stamp(os.stat(os.path.join(job['dir'], 'report.json'))) == report_stamp
    except FileNotFoundError:
        return report_stamp is None
    except OSError:
        return False


def _thumbnail_missing_source(job, path, observation, fence, report_stamp):
    files = FILES.initialize(job)
    with files.report_lock:
        if not _source_observation_current_locked(job, observation, fence, report_stamp):
            return _ThumbnailError('thumbnail_obsolete', 409, 'Source or report changed')
        current = files.current_source
        if current is not None and current['path'] == path:
            files.current_source = None
            files.source_retired = True
            files.source_status, files.source_reason = 'unavailable', 'observed source disappeared; rescan required'
            thumbs.invalidate_locked(files.thumbnail, 'source disappeared')
            return _ThumbnailError('thumbnail_source_conflict', 409, 'Source requires rescan')
        if files.source_retired or files.source_pair is not None:
            return _ThumbnailError('thumbnail_source_conflict', 409, 'Source requires rescan')
    return _ThumbnailError('missing_source', 404, 'Source unavailable')


def _thumbnail_observation_error(job, observation, fence, report_stamp, fallback):
    files = FILES.initialize(job)
    with files.report_lock:
        if not _source_observation_current_locked(job, observation, fence, report_stamp):
            return _ThumbnailError('thumbnail_obsolete', 409, 'Source or report changed')
    return fallback


def _thumbnail_release_lease(job, lease, *, primary_pending=False):
    """Install a retry owner before releasing a detached thumbnail lease."""
    if lease is None:
        return
    files = FILES.initialize(job)
    ticket = thumbs.ReleaseTicket()
    with files.report_lock:
        thumbs.defer_resource_locked(files.thumbnail, ticket, lease)
    try:
        lease.release()
    except BaseException:
        if not primary_pending:
            raise
    finally:
        if lease.released:
            try:
                with files.report_lock:
                    if ticket in files.thumbnail.deferred:
                        discarded = thumbs.remove_deferred_locked(files.thumbnail, ticket)
                    else:
                        discarded = None
                del discarded
            except BaseException:
                if not primary_pending:
                    raise


def _read_thumbnail_ordinal(selected, index, *, count, capture=None):
    cap = capture
    owned = capture is None
    try:
        if owned:
            cap = _open_preview_capture(selected['path'])
        try:
            result = thumbs.read_ordinal_capture(cap, index, count=count)
        except BaseException:
            if owned and cap is not None:
                try:
                    cap.release()
                except BaseException:
                    pass
                cap = None
            raise
        if owned:
            cap.release()
            cap = None
        return result
    except (openscrub.PipelineCancelled, thumbs.ThumbnailDecodeError):
        raise
    except Exception as error:
        raise thumbs.ThumbnailDecodeError('thumbnail unavailable') from error


def _thumbnail_source_owner(job, lease):
    state = lease.source_state
    if state is None or state is FILES.initialize(job):
        return None
    return state, lease.exact_source_epoch


@contextlib.contextmanager
def _thumbnail_owner_guard(job, lease, generation=None):
    try:
        with _exact_owner_guard(job, lease):
            if generation is not None and generation.source_owner != _thumbnail_source_owner(job, lease):
                state = FILES.initialize(job).thumbnail
                if state.current is generation:
                    thumbs.invalidate_locked(state, 'containing source changed')
                raise _ThumbnailError('thumbnail_obsolete', 409, 'Containing source changed')
            yield
    except exact.ExactError:
        raise _ThumbnailError('thumbnail_obsolete', 409, 'Containing source changed') from None


def _thumbnail_current_locked(job, selected, fence, *, operation_owner=None):
    """Check the shared source, committed report and operation before acceptance."""
    files = FILES.initialize(job)
    _report_current(job)
    operation = fence[0][1]
    if operation is not None and operation.is_set():
        current = files.thumbnail.current
        if (current is not None and current.selected_source is selected
                and (current.report_epoch, current.operation) == fence[0]
                and current.report_stamp == fence[1]):
            thumbs.invalidate_locked(files.thumbnail, 'operation signalled')
        raise _ThumbnailError('thumbnail_obsolete', 409, 'Operation changed')
    if (files.current_source is not selected or files.source_status != 'coherent'
            or files.source_retired or os.path.realpath(job['video']) != selected['path']
            or (files.committed_report_epoch, files.operation) != fence[0]
            or operation_owner is not None and operation_owner.operation is not operation):
        raise _ThumbnailError('thumbnail_obsolete', 409, 'Thumbnail generation changed')
    try:
        if _file_stamp(os.stat(os.path.join(job['dir'], 'report.json'))) != fence[1]:
            current = files.thumbnail.current
            if (current is not None and current.selected_source is selected
                    and (current.report_epoch, current.operation) == fence[0]
                    and current.report_stamp == fence[1]):
                thumbs.invalidate_locked(files.thumbnail, 'report changed')
            raise _ThumbnailError('thumbnail_obsolete', 409, 'Report changed')
    except FileNotFoundError:
        current = files.thumbnail.current
        if current is not None and current.selected_source is selected and current.report_stamp == fence[1]:
            thumbs.invalidate_locked(files.thumbnail, 'source or report disappeared')
        raise _ThumbnailError('thumbnail_obsolete', 409, 'Source or report changed') from None
    except OSError:
        raise _ThumbnailError('thumbnail_invalid_report', 500, 'Report unavailable') from None

    try:
        source_stat = os.stat(selected['path'])
    except FileNotFoundError:
        source_stat = None
    except OSError:
        raise _ThumbnailError('thumbnail_source_conflict', 409, 'Source unavailable') from None
    if source_stat is None or not stat.S_ISREG(source_stat.st_mode) or _file_stamp(source_stat) != selected['stamp']:
        files.source_retired = True
        files.current_source = None
        files.source_status, files.source_reason = 'unavailable', 'observed source changed; rescan required'
        thumbs.invalidate_locked(files.thumbnail, 'source changed')
        raise _ThumbnailError('thumbnail_source_conflict', 409, 'Source changed; rescan required')


class _FreshThumbnailSnapshot(tuple):
    """The four values returned by a successful private fresh report parse."""


# Parsed report.json, at most one parse per file identity (_file_stamp: inode,
# size, mtime, ctime — an atomic replace changes it). Every uncached Review
# thumbnail takes a snapshot; re-reading a 100k-row report per thumbnail over a
# Docker Desktop bind mount pinned CPU and disk and starved every request.
# Callers treat the shared doc as READ-ONLY. Cleared when the vault locks.
_REPORT_PARSES = {}          # realpath -> (stamp, doc)
_REPORT_PARSE_USED = {}      # realpath -> monotonic last use
_REPORT_PARSE_IDLE_S = 120   # a 100k-row parse holds ~1.5 GB; the watchdog drops it when Review goes quiet
_REPORT_PARSE_LOCKS = {}     # realpath -> Lock serializing a cold parse
_REPORT_PARSE_GUARD = threading.Lock()
_REPORT_PARSE_EPOCH = [0]
_REPORT_PARSE_MAX = 1        # a 100k-row parse can be GBs; keep one


def _parse_report_once(path, stamp, opened):
    # Windows ctime is creation time; like validation reuse, only a posix
    # stamp may stand in for the bytes.
    if os.name != 'posix':
        return json.load(opened)
    key = os.path.realpath(path)
    with _REPORT_PARSE_GUARD:
        cached = _REPORT_PARSES.get(key)
        if cached is not None and cached[0] == stamp:
            _REPORT_PARSE_USED[key] = time.monotonic()
            return cached[1]
        lock = _REPORT_PARSE_LOCKS.setdefault(key, threading.Lock())
    with lock:
        with _REPORT_PARSE_GUARD:
            cached = _REPORT_PARSES.get(key)
            if cached is not None and cached[0] == stamp:
                return cached[1]
            epoch = _REPORT_PARSE_EPOCH[0]
        doc = json.load(opened)
        with _REPORT_PARSE_GUARD:
            # A vault lock during the parse must not repopulate the cache.
            if epoch == _REPORT_PARSE_EPOCH[0]:
                _REPORT_PARSES.pop(key, None)
                while len(_REPORT_PARSES) >= _REPORT_PARSE_MAX:
                    _REPORT_PARSE_USED.pop(next(iter(_REPORT_PARSES)), None)
                    _REPORT_PARSES.pop(next(iter(_REPORT_PARSES)))
                _REPORT_PARSES[key] = (stamp, doc)
                _REPORT_PARSE_USED[key] = time.monotonic()
        return doc


# Assisted plate-letter gap lists, one per report stamp (small: a list of gap
# dicts). Computed from the SAVED report so they reflect the last saved review
# choices before any render; shares the parse cache's guard and epoch.
_LETTER_PLANS = {}           # realpath -> (stamp, (result, fps))
_LETTER_PLANS_MAX = 8
_LETTER_GAPS_OFF = {"mode": "off", "gaps": [], "stats": {}}


def _report_is_assisted(doc):
    prov = doc.get("provenance") if isinstance(doc, dict) else None
    settings = prov.get("settings") if isinstance(prov, dict) else None
    return isinstance(settings, dict) and settings.get("plate_coverage") == "assisted"


def _letter_gap_output_frames(job, doc, fps):
    """-> (first, end) source frames the job's render keeps, resolved from the
    report's saved settings exactly as run_render trims: SDR only (an HDR
    render ignores the trim and writes the full length)."""
    n = len(doc["render_state"].get("cum") or ())
    prov = doc.get("provenance") or {}
    settings = prov.get("settings") or {}
    if prov.get("hdr_output"):
        return 0, n
    clip = openscrub.resolve_output_clip(
        settings.get("clip_frac", ""), settings.get("clip_start", 0),
        settings.get("clip_end", 0),
        lambda: openscrub._probe_duration(job["video"]) or n / (fps or 30.0))
    return openscrub.output_frame_range(clip, fps, n)


def _letter_gap_plan(job):
    """-> ({"mode", "gaps", "stats"}, fps) for the job's saved report."""
    path = os.path.join(job["dir"], "report.json")
    key = os.path.realpath(path)
    try:
        opened = open(path, encoding="utf-8")
    except FileNotFoundError:
        return dict(_LETTER_GAPS_OFF), None
    with opened:
        st = os.fstat(opened.fileno())
        if not stat.S_ISREG(st.st_mode):
            abort(500, "report is not a regular file")
        stamp = _file_stamp(st)
        with _REPORT_PARSE_GUARD:
            cached = _LETTER_PLANS.get(key)
            epoch = _REPORT_PARSE_EPOCH[0]
        if os.name == "posix" and cached is not None and cached[0] == stamp:
            return cached[1]
        try:
            doc = _parse_report_once(path, stamp, opened)
        except (ValueError, UnicodeError):
            abort(500, "report invalid")
    fps = None
    if not _report_is_assisted(doc):
        result = dict(_LETTER_GAPS_OFF)
    else:
        try:
            fps = float(doc["render_state"]["fps"])
            first, end = _letter_gap_output_frames(job, doc, fps)
            plan = openscrub.assisted_cover_from_report(doc, frame_range=(first, end))
        except (ValueError, KeyError, TypeError, ZeroDivisionError):
            abort(409, "report has no usable render state")
        # out_*: the rendered video's own timeline (an SDR clip starts at
        # its first kept frame), the times the owner types into an editor.
        gaps = [{"track": g.track, "t0": g.t0, "t1": g.t1, "frames": g.frames,
                 "frame": g.frame, "box": [float(v) for v in g.box],
                 "out_t0": (round(g.t0 * fps) - first) / fps,
                 "out_t1": (round(g.t1 * fps) - first) / fps,
                 "out_frame": g.frame - first,
                 "out_f0": round(g.t0 * fps) - first,
                 "out_f1": round(g.t1 * fps) - first} for g in plan.gaps]
        gaps.sort(key=lambda g: (g["t0"], g["track"]))
        result = {"mode": "assisted", "gaps": gaps, "stats": dict(plan.stats), "fps": fps}
    # The report generation this list describes: a preview by index must
    # name it, so a list from before a save never previews the new plan.
    result["token"] = hashlib.sha256(repr(stamp).encode()).hexdigest()[:16]
    if os.name == "posix":
        with _REPORT_PARSE_GUARD:
            # A vault lock or delete during the computation must not repopulate.
            if epoch == _REPORT_PARSE_EPOCH[0]:
                _LETTER_PLANS.pop(key, None)
                while len(_LETTER_PLANS) >= _LETTER_PLANS_MAX:
                    _LETTER_PLANS.pop(next(iter(_LETTER_PLANS)))
                _LETTER_PLANS[key] = (stamp, (result, fps))
    return result, fps


def _letter_gap_jpeg(frame, box):
    """The gap's frame cropped to the box plus one box size of margin, 240 px tall.

    Everything outside the plate box is dimmed and the box gets a thick
    outline, so the plate the gap is about stands out at thumbnail size."""
    H, W = frame.shape[:2]
    x1, y1, x2, y2 = box
    bw, bh = max(1.0, x2 - x1), max(1.0, y2 - y1)
    cx1, cy1 = max(0, int(x1 - bw)), max(0, int(y1 - bh))
    cx2, cy2 = min(W, int(x2 + bw + 1)), min(H, int(y2 + bh + 1))
    if cx2 - cx1 < 2 or cy2 - cy1 < 2:
        cx1, cy1, cx2, cy2 = 0, 0, W, H
    crop = frame[cy1:cy2, cx1:cx2]
    scale = 240.0 / crop.shape[0]
    out = cv2.resize(crop, (max(1, int(round(crop.shape[1] * scale))), 240),
                     interpolation=cv2.INTER_AREA if scale < 1 else cv2.INTER_LINEAR)
    p1 = (int(round((x1 - cx1) * scale)), int(round((y1 - cy1) * scale)))
    p2 = (int(round((x2 - cx1) * scale)), int(round((y2 - cy1) * scale)))
    lit = out.copy()
    out = cv2.convertScaleAbs(out, alpha=.45)
    ys, xs = slice(max(0, p1[1]), max(0, p2[1])), slice(max(0, p1[0]), max(0, p2[0]))
    out[ys, xs] = lit[ys, xs]
    cv2.rectangle(out, (p1[0] - 2, p1[1] - 2), (p2[0] + 2, p2[1] + 2), (36, 191, 251), 4)
    ok, buf = cv2.imencode(".jpg", out, [cv2.IMWRITE_JPEG_QUALITY, 82])
    if not ok:
        abort(404)
    return buf.tobytes()


def _expire_idle_report_parses(now=None):
    now = time.monotonic() if now is None else now
    with _REPORT_PARSE_GUARD:
        for key in [k for k, used in _REPORT_PARSE_USED.items()
                    if now - used >= _REPORT_PARSE_IDLE_S]:
            _REPORT_PARSES.pop(key, None)
            _REPORT_PARSE_USED.pop(key, None)


def _forget_report_parses():
    with _REPORT_PARSE_GUARD:
        _REPORT_PARSE_EPOCH[0] += 1
        _REPORT_PARSES.clear()
        _LETTER_PLANS.clear()
        _REPORT_PARSE_USED.clear()
        _REPORT_PARSE_LOCKS.clear()


def _thumbnail_snapshot(job, *, operation_owner=None):
    """Read one private report and associate its source under existing authority."""
    files = FILES.initialize(job)
    report_path = os.path.join(job['dir'], 'report.json')
    with files.report_lock:
        _report_current(job)
        fence = (files.committed_report_epoch, files.operation)
        observation = (files.incarnation, files.current_source, files.source_epoch,
                       files.source_status, files.source_pair)
        try:
            initial_report_stamp = _file_stamp(os.stat(report_path))
        except OSError:
            initial_report_stamp = None
        if fence[1] is not None and fence[1].is_set():
            current = files.thumbnail.current
            if current is not None and current.operation is fence[1]:
                thumbs.invalidate_locked(files.thumbnail, 'operation signalled')
            raise _ThumbnailError('thumbnail_obsolete', 409, 'Operation changed')
        if operation_owner is not None and operation_owner.operation is not fence[1]:
            raise _ThumbnailError('thumbnail_obsolete', 409, 'Operation changed')
        if files.source_status == 'pending':
            raise _ThumbnailError('source_report_pending', 409, 'Source adoption pending')
        recovery = files.source_pair if files.source_status == 'unavailable' else None
        if files.source_retired and recovery is None:
            raise _ThumbnailError('thumbnail_source_conflict', 409, 'Source requires rescan')
    try:
        with open(report_path, encoding='utf-8', opener=_thumbnail_nonblocking_opener) as opened:
            report_stat = os.fstat(opened.fileno())
            if not stat.S_ISREG(report_stat.st_mode):
                raise OSError('report is not regular')
            report_stamp = _file_stamp(report_stat)
            doc = _parse_report_once(report_path, report_stamp, opened)
            if (report_stamp != _file_stamp(os.fstat(opened.fileno()))
                    or report_stamp != _file_stamp(os.stat(report_path))):
                raise _ThumbnailError('thumbnail_obsolete', 409, 'Report changed')
    except FileNotFoundError:
        raise _thumbnail_observation_error(job, observation, fence, initial_report_stamp,
            _ThumbnailError('missing_report', 404, 'Report unavailable')) from None
    except (ValueError, UnicodeError, OSError):
        error = _ThumbnailError('thumbnail_invalid_report', 500, 'Report invalid')
        error = _thumbnail_observation_error(job, observation, fence, initial_report_stamp, error)
        raise error from None
    if not isinstance(doc, dict):
        raise _thumbnail_observation_error(job, observation, fence, report_stamp,
            _ThumbnailError('thumbnail_invalid_report', 500, 'Report invalid'))
    try:
        marker = _checkpoint_marker(doc)
        evidence = marker or _completed_checkpoint(doc)
    except exact.ExactError as error:
        raise _ThumbnailError('thumbnail_source_conflict', error.status, str(error)) from None
    provenance = doc.get('provenance', {})
    if not isinstance(provenance, dict):
        raise _thumbnail_observation_error(job, observation, fence, report_stamp,
            _ThumbnailError('thumbnail_invalid_report', 500, 'Report provenance invalid'))
    missing = 'input' not in provenance
    candidate = job.get('video') if missing else provenance['input']
    if not isinstance(candidate, str) or not candidate.strip():
        raise _thumbnail_observation_error(job, observation, fence, report_stamp,
            _ThumbnailError('thumbnail_invalid_report', 500, 'Report provenance invalid'))
    with files.report_lock:
        if missing and (files.source_report_bound or files.source_pair is not None
                        or files.source_retired or files.source_status == 'unavailable'):
            if not _source_observation_current_locked(job, observation, fence, report_stamp):
                raise _ThumbnailError('thumbnail_obsolete', 409, 'Source or report changed')
            raise _ThumbnailError('thumbnail_source_conflict', 409, 'Source association unavailable')
    try:
        canonical = os.path.realpath(candidate)
    except ValueError:
        raise _thumbnail_observation_error(job, observation, fence, report_stamp,
            _ThumbnailError('thumbnail_invalid_report', 500, 'Report provenance invalid')) from None
    if recovery is None and canonical != os.path.realpath(job['video']):
        with files.report_lock:
            if not _source_observation_current_locked(job, observation, fence, report_stamp):
                raise _ThumbnailError('thumbnail_obsolete', 409, 'Source or report changed')
            if files.current_source is not None:
                files.source_retired = True
                files.current_source = None
                files.source_status, files.source_reason = 'unavailable', 'selected scan path changed; rescan required'
                thumbs.invalidate_locked(files.thumbnail, 'source changed')
        raise _ThumbnailError('thumbnail_source_conflict', 409, 'Source association unavailable')
    if recovery and (report_stamp != recovery[3] or recovery[0] is not fence[1]
                     or recovery[0].is_set() or canonical != os.path.realpath(recovery[2])):
        raise _thumbnail_observation_error(job, observation, fence, report_stamp,
            _ThumbnailError('thumbnail_source_conflict', 409, 'Source recovery unavailable'))
    lease = None
    try:
        if evidence is None:
            prepared, lease = _prepare_observed_source(job, canonical)
        else:
            prepared, lease = _prepare_observed_source(job, canonical,
                checkpoint_sha256=evidence['input_sha256'])
        source_stat = os.stat(canonical)
        if not stat.S_ISREG(source_stat.st_mode) or _file_stamp(source_stat) != prepared['stamp']:
            raise _ThumbnailError('thumbnail_source_conflict', 409, 'Source changed')
        with _thumbnail_owner_guard(job, lease):
            _report_current(job)
            try:
                final_report_stamp = _file_stamp(os.stat(report_path))
            except FileNotFoundError:
                raise _ThumbnailError('thumbnail_obsolete', 409, 'Report changed') from None
            if ((files.committed_report_epoch, files.operation) != fence
                    or fence[1] is not None and fence[1].is_set()
                    or final_report_stamp != report_stamp
                    or files.source_status == 'pending'):
                raise _ThumbnailError('thumbnail_obsolete', 409, 'Source or report changed')
            if recovery is not None and (files.source_pair != recovery
                    or recovery[0] is not files.operation or recovery[0].is_set()
                    or recovery[1] != files.committed_report_epoch
                    or recovery[3] != report_stamp
                    or prepared['path'] != os.path.realpath(recovery[2])):
                raise _ThumbnailError('thumbnail_obsolete', 409, 'Source recovery changed')
            if missing and (files.source_report_bound or files.source_pair is not None
                            or files.source_retired or files.source_status == 'unavailable'):
                raise _ThumbnailError('thumbnail_source_conflict', 409, 'Source association unavailable')
            try:
                if evidence is not None:
                    _checkpoint_source_policy(evidence, prepared)
                selected = _select_observed_locked(job, prepared, authoritative=recovery is not None,
                                                   report_bound=not missing)
            except exact.ExactError:
                raise _ThumbnailError('thumbnail_source_conflict', 409, 'Source association unavailable') from None
            if recovery is not None:
                job['video'] = selected['path']
            final_fence = (fence, report_stamp)
            _thumbnail_current_locked(job, selected, final_fence, operation_owner=operation_owner)
        return _FreshThumbnailSnapshot((doc, selected, final_fence, lease))
    except FileNotFoundError:
        if lease is not None:
            _thumbnail_release_lease(job, lease, primary_pending=True)
        raise _thumbnail_missing_source(job, canonical, observation, fence, report_stamp) from None
    except exact.ExactError:
        if lease is not None:
            _thumbnail_release_lease(job, lease, primary_pending=True)
        raise _thumbnail_observation_error(job, observation, fence, report_stamp,
            _ThumbnailError('thumbnail_source_conflict', 409, 'Source association unavailable')) from None
    except OSError:
        if lease is not None:
            _thumbnail_release_lease(job, lease, primary_pending=True)
        raise _thumbnail_observation_error(job, observation, fence, report_stamp,
            _ThumbnailError('thumbnail_source_conflict', 409, 'Source association unavailable')) from None
    except BaseException:
        if lease is not None:
            _thumbnail_release_lease(job, lease, primary_pending=True)
        raise


def _review_card_rows(rows):
    """Row index of each Review card's thumbnail, in time order.

    Mirrors reviewDescriptors in APP_JS: rows sharing (category, person or
    track) form one card shown by its highest-confidence member (earliest on
    a tie); zone-dropped and ungrouped rows are their own cards. Pre-rendering
    every dense sample instead wrote one JPEG per row (100k+ on big plate
    jobs) while the user was already reviewing.
    """
    best = {}
    singles = []
    for index, row in enumerate(rows):
        key = None
        if not row.get('zone_dropped'):
            if row.get('person', -1) >= 0:
                key = (row['category'], 'p', row['person'])
            elif row.get('track', -1) >= 0:
                key = (row['category'], 't', row['track'])
        if key is None:
            singles.append(index)
            continue
        rank = (-(row.get('confidence') or 0), row['t_start'], index)
        if key not in best or rank < best[key][0]:
            best[key] = (rank, index)
    chosen = singles + [index for _, index in best.values()]
    return sorted(chosen, key=lambda i: (rows[i]['t_start'], i))


def _thumbnail_validate_report(doc):
    try:
        rows = doc['detections']
        rs = doc['render_state']
        if not isinstance(rows, list) or not isinstance(rs, dict):
            raise ValueError()
        fps, cum = rs['fps'], rs['cum']
        if isinstance(fps, bool) or not isinstance(fps, (float, int)) or not math.isfinite(fps) or fps <= 0:
            raise ValueError()
        if not isinstance(cum, list) or not cum or not math.isfinite(len(cum) / fps):
            raise ValueError()
        for pair in cum:
            if (not isinstance(pair, (list, tuple)) or len(pair) != 2 or any(
                    isinstance(x, bool) or not isinstance(x, (int, float)) or not math.isfinite(x)
                    for x in pair)):
                raise ValueError()
        for row in rows:
            if not isinstance(row, dict):
                raise ValueError()
            # These fields are required by the shared metadata projection as
            # well as by image requests selecting the same generation.
            if not isinstance(row['category'], str) or not isinstance(row['text'], str):
                raise ValueError()
            if not isinstance(row.get('enabled', True), bool):
                raise ValueError()
            for name in ('track', 'person'):
                value = row.get(name, -1)
                if (isinstance(value, bool) or not isinstance(value, (int, float))
                        or not math.isfinite(value) or value != int(value)):
                    raise ValueError()
            confidence = row.get('confidence', 0)
            if (isinstance(confidence, bool) or not isinstance(confidence, (int, float))
                    or not math.isfinite(confidence)):
                raise ValueError()
            try:
                thumbs.recipe_for_row(row, rs, 'crop', bounded_timeline='stop_review' in doc)
            except thumbs.ThumbnailUnavailable:
                pass  # Keep the row visible even if its bounded span has no sample.
        return rows, rs
    except (KeyError, TypeError, ValueError, OverflowError):
        raise _ThumbnailError('thumbnail_invalid_report', 500, 'Report invalid') from None


def _thumbnail_cleanup(job, *, target=None):
    files = FILES.initialize(job)
    state = files.thumbnail
    while True:
        with files.report_lock:
            ticket, discarded = thumbs.claim_deferred_locked(state, target)
        del discarded  # large emptied buckets leave the lock before disposal
        if ticket is None:
            break
        retired = None
        handle = (ticket.file if isinstance(ticket, thumbs.ReaderTicket)
                  else getattr(ticket, 'stage_writer', None))
        settled = getattr(ticket, '_cleanup_settled', False)
        try:
            if not settled:
                try:
                    if handle is not None:
                        handle.close()
                except OSError:
                    pass
                with files.report_lock:
                    if handle is None or handle.closed:
                        if isinstance(ticket, thumbs.ReaderTicket):
                            retired = thumbs.end_reader_locked(state, ticket)
                        else:
                            ticket.stage_closed = True
                            ticket.stage_writer = None
                            retired = thumbs.finish_fill_locked(state, ticket)
                        ticket._cleanup_settled = settled = True
                    else:
                        thumbs.restore_deferred_locked(state, ticket)
            if settled:
                owner = ticket._deferred_lease
                owner.release()
                ticket._deferred_lease = None
                ticket._close_claimed = False
        except BaseException:
            with files.report_lock:
                owner = ticket._deferred_lease
                if owner is not None and not owner.released:
                    if (isinstance(ticket, thumbs.ReaderTicket) and ticket.released
                            or isinstance(ticket, thumbs.FillTicket) and ticket.settled):
                        ticket._cleanup_settled = True
                    if ticket not in state.deferred:
                        thumbs.restore_deferred_locked(state, ticket)
                elif owner is not None:
                    ticket._deferred_lease = None
                    ticket._close_claimed = False
            raise
        finally:
            del retired
        del ticket, handle
        if not settled:
            break
    while True:
        with files.report_lock:
            batch = thumbs.claim_cleanup_locked(files.thumbnail)
        if batch is None:
            break
        succeeded = set()
        try:
            succeeded = thumbs.cleanup(batch, unlink=lambda path: _thumbnail_unlink_owned(path, batch))
        finally:
            with files.report_lock:
                thumbs.complete_cleanup_locked(files.thumbnail, batch, succeeded)
        complete = len(succeeded) == len(batch.paths)
        del batch
        if not complete:
            break


def _thumbnail_lifecycle_cleanup(job, *, target=None):
    """Retry a retained reader while an existing lifecycle request can own it."""
    files = job.get('_files')
    if (files is None or files.active is not None or target is not None and target.active is not None
            or not files.thumbnail.deferred):
        return
    acquire = getattr(files.report_lock, 'acquire', None)
    if acquire is None or not acquire(blocking=False):
        return
    try:
        pending = (files.active is None and bool(
            files.thumbnail.deferred if target is None
            else files.thumbnail.deferred_by_owner.get(target)))
    finally:
        files.report_lock.release()
    if not pending:
        return
    with VAULT_LOCK:
        with JOBS_LOCK:
            registered = any(current is job for current in JOBS.values())
        if (not registered or files.closed or files.active is not None
                or target is not None and target.active is not None or vault_locked()):
            return
        lease = _reserve_files_locked(job, read_source=False)
    try:
        try:
            _thumbnail_cleanup(job, target=target)
        except (OSError, _ThumbnailError):
            pass
    finally:
        lease.release()


def _thumbnail_reserve_discovery(job):
    files = FILES.initialize(job)
    deadline = time.monotonic() + 1.0
    while True:
        with files.report_lock:
            _report_current(job)
            state = files.thumbnail
            if state.current is not None:
                return state.current, None
            try:
                return None, thumbs.begin_discovery_locked(state)
            except thumbs.ThumbnailPending:
                pass
        if time.monotonic() >= deadline:
            raise _ThumbnailError('thumbnail_pending', 409, 'Thumbnail pending')
        time.sleep(.01)


def _thumbnail_generation_matches_locked(files, job, generation, doc, selected, fence, lease):
    rows, rs = doc.get('detections'), doc.get('render_state')
    return (generation is not None and generation.validated is True
            and generation.incarnation == files.incarnation
            and generation.source_epoch == files.source_epoch
            and generation.selected_source is selected and files.current_source is selected
            and generation.source_path == selected['path']
            and generation.source_stamp == selected['stamp']
            and generation.report_path == os.path.join(job['dir'], 'report.json')
            and generation.report_stamp == fence[1]
            and generation.report_epoch == fence[0][0]
            and generation.operation is fence[0][1]
            and generation.source_owner == _thumbnail_source_owner(job, lease)
            and generation.crop_recipe == thumbs.CROP_RECIPE
            and generation.detframe_recipe == thumbs.DETFRAME_RECIPE
            and isinstance(rows, list) and isinstance(rs, dict)
            and generation.row_count == len(rows))


def _thumbnail_validate_snapshot(job, fresh_snapshot, *, operation_owner=None, expected_generation=None):
    """Reuse only the proof for this fresh parse and exact current generation."""
    doc, selected, fence, lease = fresh_snapshot
    files = FILES.initialize(job)
    with _thumbnail_owner_guard(job, lease):
        _thumbnail_current_locked(job, selected, fence, operation_owner=operation_owner)
        generation = files.thumbnail.current
        if expected_generation is not None and generation is not expected_generation:
            raise _ThumbnailError('thumbnail_obsolete', 409, 'Thumbnail generation changed')
        # Windows ctime is creation time; unknown platforms also require validation.
        if (os.name == 'posix' and type(fresh_snapshot) is _FreshThumbnailSnapshot
                and _thumbnail_generation_matches_locked(files, job, generation, doc, selected, fence, lease)):
            return doc['detections'], doc['render_state'], generation
    rows, rs = _thumbnail_validate_report(doc)
    return rows, rs, None


def _thumbnail_select(job, doc, selected, fence, lease, *, operation_owner=None, discovery=None,
                      validated=None, reuse_generation=None):
    """Converge a private coherent report on the current bounded generation."""
    files = FILES.initialize(job)
    state = files.thumbnail
    try:
        if reuse_generation is not None:
            if validated is not None:
                raise ValueError('validated data cannot accompany reused generation')
            with _thumbnail_owner_guard(job, lease, reuse_generation):
                _thumbnail_current_locked(job, selected, fence, operation_owner=operation_owner)
                if (state.current is not reuse_generation
                        or not _thumbnail_generation_matches_locked(
                            files, job, reuse_generation, doc, selected, fence, lease)):
                    raise _ThumbnailError('thumbnail_obsolete', 409, 'Thumbnail generation changed')
                return reuse_generation
        rows, _ = validated if validated is not None else _thumbnail_validate_report(doc)
        if discovery is None:
            _, discovery = _thumbnail_reserve_discovery(job)
        with _thumbnail_owner_guard(job, lease):
            _thumbnail_current_locked(job, selected, fence, operation_owner=operation_owner)
            source_owner = _thumbnail_source_owner(job, lease)
            generation = state.current
            if generation is not None and not _thumbnail_generation_matches_locked(
                    files, job, generation, doc, selected, fence, lease):
                thumbs.invalidate_locked(state, 'selection changed')
                generation = None
            if generation is None:
                if discovery is None:
                    try:
                        discovery = thumbs.begin_discovery_locked(state)
                    except thumbs.ThumbnailPending:
                        raise _ThumbnailError('thumbnail_pending', 409, 'Thumbnail pending') from None
                candidate = thumbs.Candidate(incarnation=files.incarnation,
                    report_epoch=fence[0][0], source_epoch=files.source_epoch,
                    operation=fence[0][1], selected_source=selected,
                    source_path=selected['path'], source_stamp=selected['stamp'],
                    report_path=os.path.join(job['dir'], 'report.json'), report_stamp=fence[1],
                    source_owner=source_owner)
                try:
                    generation = thumbs.accept_discovery_locked(state, discovery, candidate, len(rows))
                except thumbs.ThumbnailObsolete:
                    raise _ThumbnailError('thumbnail_obsolete', 409, 'Thumbnail generation changed') from None
            return generation
    finally:
        if discovery is not None:
            with files.report_lock:
                thumbs.finish_discovery_locked(state, discovery)


def _thumbnail_image(job, index, kind, requested_version=None, *, operation_owner=None, capture=None, snapshot=None):
    files = FILES.initialize(job)
    state = files.thumbnail
    lease = None
    snapshot_lease = None
    fill = None
    discovery = None
    try:
        _thumbnail_cleanup(job)
        with files.report_lock:
            generation = state.current
            if requested_version is not None and (generation is None or generation.version != requested_version):
                raise _ThumbnailError('thumbnail_obsolete', 409, 'Thumbnail generation changed')
        if generation is None:
            generation, discovery = _thumbnail_reserve_discovery(job)
        doc = None
        validated = None
        if generation is not None:
            with files.report_lock:
                if (state.current is not generation or files.current_source is not generation.selected_source
                        or files.source_epoch != generation.source_epoch
                        or files.incarnation != generation.incarnation):
                    raise _ThumbnailError('thumbnail_obsolete', 409, 'Thumbnail generation changed')
                observation = (files.incarnation, files.current_source, files.source_epoch,
                               files.source_status, files.source_pair)
            try:
                prepared, lease = _prepare_observed_source(
                    job, generation.source_path, requested_version is not None)
                with _thumbnail_owner_guard(job, lease, generation):
                    if state.current is not generation:
                        raise _ThumbnailError('thumbnail_obsolete', 409, 'Thumbnail generation changed')
                    _thumbnail_current_locked(job, generation.selected_source,
                        ((generation.report_epoch, generation.operation), generation.report_stamp),
                        operation_owner=operation_owner)
                    if (prepared['path'], prepared['stamp']) != (generation.source_path, generation.source_stamp):
                        raise _ThumbnailError('thumbnail_obsolete', 409, 'Thumbnail generation changed')
            except FileNotFoundError:
                if lease is not None:
                    _thumbnail_release_lease(job, lease, primary_pending=True)
                    lease = None
                raise _thumbnail_missing_source(job, generation.source_path, observation,
                    (generation.report_epoch, generation.operation), generation.report_stamp) from None
            except exact.ExactError:
                raise _ThumbnailError('thumbnail_obsolete', 409, 'Containing source changed') from None
            except BaseException:
                if lease is not None:
                    _thumbnail_release_lease(job, lease, primary_pending=True)
                    lease = None
                raise
        else:
            # Assign the cleanup owner before the fresh witness.
            doc, selected, fence, lease = fresh_snapshot = _thumbnail_snapshot(job, operation_owner=operation_owner)
            rows, rs, reused = _thumbnail_validate_snapshot(job, fresh_snapshot, operation_owner=operation_owner)
            validated = (rows, rs)
            generation = _thumbnail_select(job, doc, selected, fence, lease, operation_owner=operation_owner,
                                           discovery=discovery, validated=None if reused else validated,
                                           reuse_generation=reused)
        if index < 0 or index >= generation.row_count:
            raise _ThumbnailError('thumbnail_unavailable', 404, 'Thumbnail unavailable')
        with files.report_lock:
            if state.current is not generation:
                raise _ThumbnailError('thumbnail_obsolete', 409, 'Thumbnail generation changed')
            entry = state.entries.get((kind, index))
            if entry is None:
                try:
                    fill = thumbs.begin_fill_locked(state, generation, kind, index)
                except thumbs.ThumbnailPending:
                    raise _ThumbnailError('thumbnail_pending', 409, 'Thumbnail pending') from None
                except thumbs.ThumbnailObsolete:
                    raise _ThumbnailError('thumbnail_obsolete', 409, 'Thumbnail generation changed') from None
        if entry is None:
            if snapshot is not None:
                saved_doc, saved_source, saved_fence, saved_rows, saved_rs = snapshot
                if saved_source is not generation.selected_source or saved_fence != ((generation.report_epoch, generation.operation), generation.report_stamp):
                    raise _ThumbnailError('thumbnail_obsolete', 409, 'Thumbnail generation changed')
                doc = saved_doc
            if doc is None:
                # Retain the snapshot owner through validation of its witness.
                doc, selected, fence, snapshot_lease = fresh_snapshot = _thumbnail_snapshot(job, operation_owner=operation_owner)
                with _thumbnail_owner_guard(job, snapshot_lease, generation):
                    if state.current is not generation or selected is not generation.selected_source or fence != ((generation.report_epoch, generation.operation), generation.report_stamp):
                        raise _ThumbnailError('thumbnail_obsolete', 409, 'Thumbnail generation changed')
            if snapshot is not None:
                rows, rs = saved_rows, saved_rs
            elif validated is not None:
                rows, rs = validated
            else:
                rows, rs, _ = _thumbnail_validate_snapshot(job, fresh_snapshot,
                    operation_owner=operation_owner, expected_generation=generation)
                with _thumbnail_owner_guard(job, snapshot_lease, generation):
                    if state.current is not generation:
                        raise _ThumbnailError('thumbnail_obsolete', 409, 'Thumbnail generation changed')
            if snapshot_lease is not None:
                _thumbnail_release_lease(job, snapshot_lease)
                snapshot_lease = None
            try:
                recipe = thumbs.recipe_for_row(rows[index], rs, kind,
                                               bounded_timeline='stop_review' in doc)
            except thumbs.ThumbnailUnavailable:
                raise _ThumbnailError('thumbnail_unavailable', 404, 'Thumbnail unavailable') from None
            with _thumbnail_owner_guard(job, lease, generation):
                _thumbnail_current_locked(job, generation.selected_source,
                    ((generation.report_epoch, generation.operation), generation.report_stamp),
                    operation_owner=operation_owner)
            image = None
            for ordinal, offset in zip(recipe.indices, recipe.offsets):
                try:
                    frame = _read_thumbnail_ordinal(generation.selected_source, ordinal,
                                                    count=len(rs['cum']), capture=capture)
                except thumbs.ThumbnailDecodeError:
                    if capture is not None:
                        break
                    continue
                if kind == 'detframe':
                    x1, y1 = int(recipe.cbox[0] + offset[0]), int(recipe.cbox[1] + offset[1])
                    x2, y2 = int(recipe.cbox[2] + offset[0]), int(recipe.cbox[3] + offset[1])
                    try:
                        cv2.rectangle(frame, (x1 - 4, y1 - 4), (x2 + 4, y2 + 4), (0, 0, 255), 3)
                    except cv2.error:
                        raise _ThumbnailError('thumbnail_encode_failed', 500, 'Thumbnail encoding failed') from None
                    image = frame
                    break
                try:
                    crop, nonblank = thumbs.crop_frame(frame, recipe.cbox, offset)
                except cv2.error:
                    raise _ThumbnailError('thumbnail_encode_failed', 500, 'Thumbnail encoding failed') from None
                if crop is not None:
                    image = crop
                if nonblank:
                    break
                if capture is not None:
                    image = None
                    break
            if image is None:
                raise _ThumbnailError('thumbnail_unavailable', 404, 'Thumbnail unavailable')
            try:
                jpeg = thumbs.encode_jpeg(image, recipe.jpeg_quality)
                import numpy as np
                verified = cv2.imdecode(np.frombuffer(jpeg, dtype=np.uint8), cv2.IMREAD_COLOR)
                if verified is None or not verified.size:
                    raise ValueError('invalid encoded thumbnail')
                del verified
            except openscrub.PipelineCancelled:
                raise
            except Exception:
                raise _ThumbnailError('thumbnail_encode_failed', 500, 'Thumbnail encoding failed') from None
            try:
                with VAULT_LOCK:
                    stage_sequence = FILES.thumbnail_admission
                fill.register_stage = lambda path, fd: _thumbnail_register_stage(job, stage_sequence, path, fd)
                staged = thumbs.stage_jpeg(job['dir'], fill, jpeg)
                with _thumbnail_owner_guard(job, lease, generation):
                    _thumbnail_current_locked(job, generation.selected_source,
                        ((generation.report_epoch, generation.operation), generation.report_stamp),
                        operation_owner=operation_owner)
                    try:
                        entry = thumbs.accept_jpeg_locked(state, fill, staged)
                    except thumbs.ThumbnailObsolete:
                        raise _ThumbnailError('thumbnail_obsolete', 409, 'Thumbnail generation changed') from None
            except OSError:
                raise _ThumbnailError('thumbnail_io_failed', 500, 'Thumbnail storage failed') from None
        opened = reader = None
        stamp = lambda s: (s.st_dev, s.st_ino, s.st_size, s.st_mtime_ns)
        try:
            with _thumbnail_owner_guard(job, lease, generation):
                _thumbnail_current_locked(job, generation.selected_source,
                    ((generation.report_epoch, generation.operation), generation.report_stamp),
                    operation_owner=operation_owner)
                reader = thumbs.reserve_reader_locked(state, generation, entry)
                opened = _thumbnail_open(entry.path, reader)
                reader.file = opened
                observed = os.fstat(opened.fileno())
                path_stat = os.stat(entry.path)
                if (not stat.S_ISREG(observed.st_mode) or stamp(observed) != entry.stamp
                        or stamp(path_stat) != entry.stamp):
                    raise OSError('thumbnail changed')
        except BaseException as error:
            owned = reader.file if reader is not None else opened
            if owned is not None:
                try:
                    owned.close()
                except BaseException:
                    pass
            retired = None
            with files.report_lock:
                if reader is not None:
                    if owned is None or owned.closed:
                        retired = thumbs.end_reader_locked(state, reader)
                    else:
                        if state.current is generation:
                            thumbs.invalidate_locked(state, 'cached thumbnail close failed')
                        thumbs.defer_resource_locked(state, reader, lease)
                        lease = None
                if isinstance(error, (OSError, thumbs.ThumbnailObsolete)) and state.current is generation:
                    thumbs.invalidate_locked(state, 'cached thumbnail changed')
            del retired
            if isinstance(error, (OSError, thumbs.ThumbnailObsolete)):
                raise _ThumbnailError('thumbnail_obsolete', 409, 'Thumbnail generation changed') from None
            raise
        try:
            try:
                try:
                    body = opened.read()
                    observed = os.fstat(opened.fileno())
                except BaseException:
                    try:
                        opened.close()
                    except BaseException:
                        pass
                    raise
                else:
                    opened.close()
            except OSError:
                with files.report_lock:
                    if state.current is generation:
                        thumbs.invalidate_locked(state, 'cached thumbnail read failed')
                raise _ThumbnailError('thumbnail_obsolete', 409, 'Thumbnail generation changed') from None
        finally:
            retired = None
            with files.report_lock:
                if opened.closed:
                    retired = thumbs.end_reader_locked(state, reader)
                else:
                    if state.current is generation:
                        thumbs.invalidate_locked(state, 'cached thumbnail close failed')
                    thumbs.defer_resource_locked(state, reader, lease)
                    lease = None
            del retired
        if (stamp(observed) != entry.stamp or len(body) != entry.size
                or thumbs.jpeg_etag(kind, generation.version, index, body) != entry.etag):
            with files.report_lock:
                if state.current is generation:
                    thumbs.invalidate_locked(state, 'cached thumbnail changed')
            raise _ThumbnailError('thumbnail_obsolete', 409, 'Thumbnail generation changed')
        with _thumbnail_owner_guard(job, lease, generation):
            _thumbnail_current_locked(job, generation.selected_source,
                ((generation.report_epoch, generation.operation), generation.report_stamp),
                operation_owner=operation_owner)
            if state.current is not generation:
                raise _ThumbnailError('thumbnail_obsolete', 409, 'Thumbnail generation changed')
            try:
                if stamp(os.stat(entry.path)) != entry.stamp:
                    raise OSError('thumbnail changed')
            except OSError:
                thumbs.invalidate_locked(state, 'cached thumbnail changed')
                raise _ThumbnailError('thumbnail_obsolete', 409, 'Thumbnail generation changed') from None
        return body, entry.etag
    finally:
        primary_pending = sys.exc_info()[0] is not None
        try:
            if snapshot_lease is not None:
                try:
                    _thumbnail_release_lease(job, snapshot_lease, primary_pending=primary_pending)
                except BaseException:
                    # The retry ticket may not exist yet. Transfer this child to
                    # the still-owned primary before continuing its cleanup.
                    if not snapshot_lease.released:
                        lease.related.append(snapshot_lease)
                    if not primary_pending:
                        raise
        finally:
            primary_pending = primary_pending or sys.exc_info()[0] is not None
            try:
                if discovery is not None:
                    with files.report_lock:
                        thumbs.finish_discovery_locked(state, discovery)
                if fill is not None:
                    retired = None
                    with files.report_lock:
                        if fill.stage_closed:
                            try:
                                retired = thumbs.finish_fill_locked(state, fill)
                            except BaseException:
                                if not fill.settled:
                                    thumbs.defer_resource_locked(state, fill, lease)
                                    lease = None
                                if not primary_pending:
                                    raise
                        else:
                            if state.current is generation:
                                thumbs.invalidate_locked(state, 'stage writer close failed')
                            thumbs.defer_resource_locked(state, fill, lease)
                            lease = None
                    del retired
            finally:
                if lease is not None:
                    releasing_primary = primary_pending or sys.exc_info()[0] is not None
                    try:
                        try:
                            _thumbnail_cleanup(job)
                        except BaseException:
                            if not releasing_primary:
                                raise
                    finally:
                        releasing_primary = releasing_primary or sys.exc_info()[0] is not None
                        _thumbnail_release_lease(job, lease, primary_pending=releasing_primary)


def _checkpoint_marker(doc):
    if 'stop_review' not in doc:
        return None
    try:
        marker = checkpoints.validate_resume(doc)
    except (ValueError, TypeError, RecursionError) as error:
        raise exact.ExactError('invalid checkpoint: ' + str(error), 409, 'sample_conflict') from None
    end = marker['next_frame'] / marker['fps']
    for index, row in enumerate(doc['detections']):
        if row.get('category') == 'manual' and (row['t_start'] >= end or row['t_end'] > end):
            raise exact.ExactError('manual row %s span [%s, %s] exceeds inspected boundary %s' %
                                   (index, row['t_start'], row['t_end'], end), 409, 'sample_conflict')
    return marker


def _completed_checkpoint(doc):
    """Qualify only a fully decoded checkpoint, including its empty-row case."""
    if 'stop_review' in doc or not openscrub._has_checkpoint_identity(doc):
        return None
    try:
        provenance = doc['provenance']
        state = doc['render_state']
        cum, bands, fps = state['cum'], state['bands'], state['fps']
        if (not isinstance(cum, list) or not cum or not isinstance(bands, list) or
                len(bands) != len(cum) or not isinstance(doc['detections'], list)):
            raise ValueError('completed checkpoint timeline is invalid')
        total = len(cum)
        identity = checkpoints._identity(provenance['checkpoint_identity'], total, fps,
                                         provenance['input_sha256'])
        openscrub._report_frame_authorities(doc)
        openscrub._validate_bounded_report_identity(doc, provenance['input_sha256'], state)
    except (KeyError, TypeError, ValueError, RecursionError) as error:
        raise exact.ExactError('invalid completed checkpoint: ' + str(error),
                               409, 'sample_conflict') from None
    return dict(input_sha256=provenance['input_sha256'], fps=fps,
                total_frames=total, next_frame=total, options=identity)


def _checkpoint_source_policy(marker, selected):
    """Tie a parsed prefix to the same bytes and stream described by its owner."""
    facts = selected.get('facts')
    options = marker['options']
    sources, settings = options['sources'], options['effective_settings']
    source = sources['scan']
    categories = settings.get('categories')
    categories = ({value.strip() for value in categories.split(',') if value.strip()}
                  if isinstance(categories, str) else None)
    unsupported = ('original_video', 'hdr_source', 'zones', 'zones_data', 'windows',
                   'windows_data', 'ignore_region', 'ignore_regions', 'detect_windows',
                   'detect_windows_frac', 'skip_start', 'skip_end', 'audio_pii',
                   'allow_names', 'extra_names', 'phrases', 'face_model', 'plate_model',
                   'person_model', 'dense_faces')
    if (categories not in ({'qrcode'}, {'none'}, set()) or
            settings.get('no_vfr_fix') is not True or settings.get('no_backtrack') is not True or
            settings.get('scroll_track') != 'off' or any(settings.get(key) for key in unsupported) or
            options['normalization'] != {'mode': 'none', 'target': 'none', 'transform_version': 'none'} or
            sources.get('original') != source or sources.get('render') is not None or
            source.get('fps_source') != 'mp4_rate_and_observed_pts_v1' or
            options['timeline'].get('fps_source') != 'mp4_rate_and_observed_pts_v1' or
            options['timeline'].get('count_source') != 'mp4_reported_nb_frames'):
        raise exact.ExactError('checkpoint settings are outside the supported review scope', 409, 'sample_conflict')
    if (selected.get('policy_error') or not isinstance(facts, dict) or
            selected.get('checkpoint_sha256') != marker['input_sha256'] or
            facts.get('count') != marker['total_frames'] or
            facts.get('width') != source['width'] or facts.get('height') != source['height']):
        raise exact.ExactError('checkpoint source no longer matches its report', 409, 'sample_conflict')
    return exact.precision_bound(facts, marker['fps'], marker['total_frames'])


def _exact_policy(doc, selected):
    if selected['policy_error']:
        raise exact.ExactError(selected['policy_error'])
    marker = _checkpoint_marker(doc)
    evidence = marker or _completed_checkpoint(doc)
    provenance = doc.get('provenance', {})
    settings = provenance.get('settings', {})
    normalized = (provenance.get('vfr_normalized') and provenance.get('original_input')
                  and os.path.realpath(provenance['original_input']) != selected['path'])
    if evidence is None and not normalized and (settings.get('no_vfr_fix') or settings.get('vfr') == 'ignore'):
        raise exact.ExactError('known raw timing bypass is unsupported')
    fps, cum, timeline_eq = exact.timeline(doc, selected['facts'])
    tolerance = (_checkpoint_source_policy(evidence, selected) if evidence is not None else
                 exact.precision_bound(selected['facts'], fps, len(cum)))
    return fps, cum, timeline_eq, tolerance


def _exact_current_locked(job, selected, fence=None):
    files = FILES.initialize(job)
    _report_current(job)
    if (files.current_source is not selected or files.source_status != 'coherent'
            or files.source_retired or files.active is not None
            or os.path.realpath(job['video']) != selected['path']):
        raise exact.ExactError('source selection changed', 409, 'sample_conflict')
    try:
        if fence is not None and ((files.committed_report_epoch, files.operation) != fence[0]
                or (fence[0][1] is not None and fence[0][1].is_set())
                or _file_stamp(os.stat(os.path.join(job['dir'], 'report.json'))) != fence[1]):
            raise exact.ExactError('report publication overlapped sample', 409, 'sample_conflict')
        if _file_stamp(os.stat(selected['path'])) != selected['stamp']:
            thumbs.invalidate_locked(files.thumbnail, 'source changed')
            files.source_retired = True
            files.current_source = None
            files.source_status, files.source_reason = 'unavailable', 'observed source changed; rescan required'
            raise exact.ExactError(files.source_reason, 409, 'sample_conflict')
    except FileNotFoundError:
        raise exact.ExactError('source/report disappeared', 409, 'sample_conflict') from None


def _exact_error(error):
    return jsonify(error=error.code, detail=str(error)), error.status


def _read_exact_source(selected, index, *, fps, count, tolerance_s):
    """The caller holds source lifetime; this adapter owns only the decode."""
    try:
        opened_source = open(selected['path'], 'rb')
    except FileNotFoundError:
        raise exact.ExactError('selected source disappeared before decode',
                               409, 'sample_conflict') from None
    with opened_source as opened:
        if _file_stamp(os.fstat(opened.fileno())) != selected['stamp']:
            raise exact.ExactError('opened source changed', 409, 'sample_conflict')
        cap = cv2.VideoCapture(selected['path'])
        try:
            facts = selected['facts']
            decoded = exact.read_indexed_capture(cap, index, fps=fps, count=count,
                width=facts['width'], height=facts['height'], tolerance_s=tolerance_s)
        finally:
            cap.release()
        try:
            if (_file_stamp(os.fstat(opened.fileno())) != selected['stamp']
                    or _file_stamp(os.stat(selected['path'])) != selected['stamp']):
                raise exact.ExactError('opened source mutated', 409, 'sample_conflict')
        except FileNotFoundError:
            raise exact.ExactError('selected source disappeared during decode',
                                   409, 'sample_conflict') from None
    return decoded


def _quad_baseline_token(row):
    quad = row.get('manual_plate_quad')
    if not plate_quad.valid_record(quad):
        return None
    # The browser must carry these bytes verbatim: JS numbers do not retain
    # the int/float distinction used by the row-context hash.
    return json.dumps(quad, sort_keys=True, ensure_ascii=True,
                      separators=(',', ':'), allow_nan=False)


def _quad_baseline_value(token):
    if not isinstance(token, str) or len(token) > 8192:
        return None
    try:
        quad = json.loads(token)
    except (ValueError, TypeError, RecursionError):
        return None
    return quad if plate_quad.valid_record(quad) else None


def _quad_scan_supported(doc, selected):
    return (plate_quad.same_sdr_scan(doc.get('provenance', {}), selected['facts'])
            or openscrub.hdr_quad_pairs.usable(selected.get('hdr_quad_proof'), doc, selected))


def _quad_edit_eligibility(doc, selected):
    provenance = doc.get('provenance', {})
    expected = provenance.get('input_sha256') if isinstance(provenance, dict) else None
    if (not _quad_scan_supported(doc, selected)
            or not isinstance(expected, str) or re.fullmatch('[0-9a-f]{64}', expected) is None):
        return 'unavailable'
    verified = selected.get('quad_sha256')
    if verified is None:
        return 'verification_required'
    return 'ready' if verified == expected else 'unavailable'


def _quad_sample_eligibility(row, doc, selected, index, fps, count, timeline_eq):
    quad = row.get('manual_plate_quad')
    if quad is None:
        return 'none'
    if not plate_quad.valid_record(quad):
        return 'unsupported'
    facts, source, frame = selected['facts'], quad['source'], quad['frame']
    if (not _quad_scan_supported(doc, selected)
            or source['width'] != facts['width'] or source['height'] != facts['height']
            or source['stream'] != facts['stream'] or frame['fps'] != fps
            or frame['count'] != count or frame['timeline_eq'] != timeline_eq
            or doc.get('provenance', {}).get('input_sha256') != source['sha256']):
        return 'unavailable'
    if frame['index'] != index:
        return 'other_frame'
    digest = selected.get('quad_sha256')
    if digest is None:
        return 'unverified'
    if digest != source['sha256'] or digest != doc.get('provenance', {}).get('input_sha256'):
        return 'unavailable'
    return 'eligible_sdr_frame'


@app.route('/api/jobs/<jid>/edit_sample')
def job_edit_sample(jid):
    job = JOBS.get(jid) or abort(404)
    lease = None
    try:
        try:
            requested = json.loads(request.args['t'])
            if not exact.finite(requested):
                raise ValueError()
        except (KeyError, ValueError, TypeError):
            raise exact.ExactError('finite numeric t required', 400, 'invalid_sample_request') from None
        if 'src' in request.args:
            raise exact.ExactError('exact samples use scan input only', 400, 'invalid_sample_request')
        doc, selected, fence, lease = _exact_snapshot(job)
        fps, cum, timeline_eq, tolerance = _exact_policy(doc, selected)
        marker = _checkpoint_marker(doc)
        evidence = marker or _completed_checkpoint(doc)
        if marker is not None and requested >= marker['next_frame'] / fps:
            raise exact.ExactError('time outside inspected checkpoint prefix', 400, 'invalid_sample_request')
        index = exact.resolve_time(requested, fps, len(cum))
        if evidence is not None:
            # A JSON representation of index/fps can multiply back just below
            # its integer (for example 123/120). Preserve exact grid roundtrips
            # without rounding a request that is actually before the frame.
            nearest = round(requested * fps)
            if 0 <= nearest < len(cum) and requested == nearest / fps:
                index = nearest
        facts = selected['facts']
        source_count = marker['total_frames'] if marker is not None else len(cum)
        decoded = _read_exact_source(selected, index, fps=fps, count=source_count,
                                     tolerance_s=tolerance)
        try:
            ok, encoded = cv2.imencode('.jpg', decoded.pixels, [cv2.IMWRITE_JPEG_QUALITY, 90])
            if not ok or encoded is None:
                raise ValueError('JPEG encoder returned no image')
            image = base64.b64encode(encoded.tobytes()).decode('ascii')
        except Exception as error:
            raise exact.ExactError('JPEG encoding failed: '+str(error), 500, 'sample_encode_failed') from None
        offset = cum[index]
        boxes = []
        capable = doc.get('plate_policy_evidence_version') == 1
        for i, row in enumerate(doc['detections']):
            if capable and row.get('category') == 'plate':
                if (not openscrub.plate_policy._valid_geometry(row)
                        or row['policy_evidence']['frame'] != index):
                    continue
            baseline = exact.row_base(row)
            start, end, _ = baseline['span']
            authority = openscrub._frame_authority(row, total=len(cum))
            if authority is not None and not authority[0] <= index < authority[1]:
                continue
            if start-.01 <= decoded.canonical_s <= end+.01:
                box = baseline['cbox']
                item = dict(i=i, category=row['category'], text=row.get('text',''),
                    enabled=row.get('enabled',True), t_start=start, t_end=end,
                    box=[box[0]+offset[0], box[1]+offset[1], box[2]+offset[0], box[3]+offset[1]],
                    row_context_eq=exact.row_context_eq(row), base=baseline)
                if row['category'] == 'plate':
                    item['quad_context_eq'] = _quad_context_eq(row)
                    item['quad_baseline'] = _quad_baseline_token(row)
                    item['quad_edit_eligibility'] = _quad_edit_eligibility(doc, selected)
                    item['quad_eligibility'] = _quad_sample_eligibility(
                        row, doc, selected, index, fps, len(cum), timeline_eq)
                    if 'manual_plate_quad' in row:
                        item['manual_plate_quad'] = row['manual_plate_quad']
                if evidence is not None:
                    item['scan_frame_bounds'] = list(authority) if authority is not None else None
                boxes.append(item)
        with _exact_owner_guard(job, lease):
            _exact_current_locked(job, selected, fence)
        return jsonify(version=1, sample=dict(source_ref=selected['source_ref'],
            timeline_eq=timeline_eq, policy=exact.POLICY, index=index, requested_s=requested,
            canonical_s=decoded.canonical_s, observed_s=decoded.observed_s, width=facts['width'],
            height=facts['height'], stream=facts['stream'], origin=[0,0], offset=offset),
            image=dict(mime='image/jpeg', base64=image), boxes=boxes)
    except exact.ExactError as error:
        return _exact_error(error)
    except (KeyError, TypeError, ValueError, OverflowError) as error:
        return _exact_error(exact.ExactError('invalid consumed report geometry: '+str(error)))
    finally:
        if lease is not None:
            lease.release()


def _run_plate_search_child(payload, directory, cancelled, timeout):
    return plate_search_worker.run(payload, directory, cancelled, timeout=timeout)


def _plate_search_json():
    """Read a small request without asking Flask to buffer an unlimited body."""
    if not request.is_json or (request.content_length is not None and request.content_length > 4096):
        return None
    try:
        data = request.stream.read(4097)
        return json.loads(data) if len(data) <= 4096 else None
    except (ValueError, UnicodeError, RecursionError):
        return None


def _plate_search_result(value, width, height, mode):
    """Admit only bounded, source-pixel suggestion data from the child."""
    return plate_search_worker.validate_result(value, width, height, mode)


@app.route('/api/jobs/<jid>/plate_search/cancel', methods=['POST'])
def job_plate_search_cancel(jid):
    job = JOBS.get(jid) or abort(404)
    body = _plate_search_json()
    identity = body.get('request_id') if isinstance(body, dict) else None
    if not isinstance(identity, str) or re.fullmatch('[0-9a-f]{32}', identity) is None:
        return jsonify(error='invalid_request'), 400
    files = FILES.initialize(job)
    with files.report_lock:
        _report_current(job)
        current = files.plate_search
        if current is not None and current['id'] == identity:
            current['cancel'].set()
        elif current is None:
            # One bounded tombstone covers cancellation before admission.
            files.plate_cancel = identity
    return jsonify(ok=True)


@app.route('/api/jobs/<jid>/plate_search', methods=['POST'])
def job_plate_search(jid):
    """Search the inspected sample or four explicit video samples without report writes."""
    job = JOBS.get(jid) or abort(404)
    body = _plate_search_json()
    try:
        fields = {'seed', 'query', 'mode', 'request_id'}
        if (not isinstance(body, dict) or set(body) not in (fields, fields | {'scope'})
                or ('scope' in body and body['scope'] != 'sampled')):
            raise ValueError()
        sampled = body.get('scope') == 'sampled'
        seed = _parse_sample_precondition(body['seed'])
        if set(seed) != {'version','source_ref','timeline_eq','policy','index','width','height','offset'}:
            raise ValueError()
        identity, mode, query = body['request_id'], body['mode'], body['query']
        if (not isinstance(identity, str) or re.fullmatch('[0-9a-f]{32}', identity) is None
                or not isinstance(query, str) or mode not in ('full', 'fragment')):
            raise ValueError()
        normalize_plate_queries(query, mode=mode)
    except (ValueError, TypeError, exact.ExactError):
        return jsonify(error='invalid_request'), 400
    if not _PLATE_SEARCH_SLOT.acquire(blocking=False):
        return jsonify(error='search_busy'), 409
    deadline = time.monotonic() + _PLATE_SEARCH_DEADLINE
    files = FILES.initialize(job)
    work_lease = snapshot_lease = marker = None
    try:
        with files.report_lock:
            _edit_gate(job)
            if job.get('phase') not in ('review', 'done'):
                raise exact.ExactError('search requires an active review',409,'sample_conflict')
            admission_qgen, admission_cancel = job.get('qgen', 0), job['cancel']
            admission_signalled = admission_cancel.is_set()
        work_lease = _own_files(job, work=True)
        doc, selected, fence, snapshot_lease = _exact_snapshot(job)
        fps, cum, timeline_eq, tolerance = _exact_policy(doc, selected)
        _check_sample_precondition(seed, selected, fps, cum, timeline_eq)
        with _exact_owner_guard(job, snapshot_lease):
            _exact_current_locked(job, selected, fence)
            if (work_lease.source != selected['path']
                    or work_lease.source_state is not snapshot_lease.source_state
                    or job.get('qgen', 0) != admission_qgen
                    or job['cancel'] is not admission_cancel
                    or (not admission_signalled and admission_cancel.is_set())):
                raise exact.ExactError('search admission changed',409,'sample_conflict')
            if files.plate_search is not None:
                raise exact.ExactError('search already running',409,'sample_conflict')
            if files.tracker is not None and not files.tracker.released:
                raise exact.ExactError('tracking already running',409,'sample_conflict')
            if files.plate_cancel == identity:
                files.plate_cancel = None
                raise plate_search_worker.WorkerCancelled()
            files.plate_cancel = None
            marker = {'id': identity, 'cancel': threading.Event()}
            files.plate_search = marker
            # Give the lookup its own operation identity. A delayed job-cancel
            # cannot then revoke a newer lookup after this one has finished.
            work_lease.operation = marker['cancel']
            files.operation = marker['cancel']
            job['cancel'] = marker['cancel']
            fence = ((fence[0][0], marker['cancel']), fence[1])

        def current():
            with _exact_owner_guard(job, snapshot_lease):
                if marker['cancel'].is_set() or job.get('qgen', 0) != admission_qgen:
                    raise plate_search_worker.WorkerCancelled()
                if files.plate_search is not marker or not _operation_valid(job, work_lease):
                    raise plate_search_worker.WorkerCancelled()
                _exact_current_locked(job, selected, fence)

        def cancelled():
            return marker['cancel'].is_set() or files.operation is not marker['cancel']

        payload = dict(path=selected['path'], stamp=list(selected['stamp']), index=seed['index'],
                       fps=fps, count=len(cum), width=seed['width'], height=seed['height'],
                       tolerance_s=tolerance, query=query, mode=mode)
        if sampled:
            n = min(4, len(cum))
            indices = [0] if n == 1 else [i*(len(cum)-1)//(n-1) for i in range(n)]
            payload['indices'] = indices
        remaining = deadline - time.monotonic()
        if remaining <= 0:
            raise plate_search_worker.WorkerTimedOut()
        try:
            value = _run_plate_search_child(payload, job['dir'], cancelled, remaining)
        except plate_search_worker.WorkerFailed:
            current()
            raise
        if sampled:
            frames = plate_search_worker.validate_sampled_result(value, seed['width'], seed['height'], mode, indices)
        else:
            suggestions = _plate_search_result(value, seed['width'], seed['height'], mode)
        current()
        if sampled:
            return jsonify(state='complete', frame_count=len(cum), fps=fps, frames=[
                dict(index=frame['index'], time_s=frame['index']/fps, seek_s=(frame['index']+.5)/fps,
                     matches=len(frame['suggestions']), truncated=frame['truncated']) for frame in frames])
        return jsonify(state='complete', index=seed['index'], truncated=value['truncated'],
                       suggestions=suggestions)
    except plate_search_worker.WorkerCancelled:
        return jsonify(state='cancelled', error='search_cancelled'), 409
    except plate_search_worker.WorkerTimedOut:
        return jsonify(state='timeout', error='search_timeout'), 504
    except (plate_search_worker.WorkerFailed, OSError):
        return jsonify(state='error', error='search_unavailable'), 503
    except exact.ExactError as error:
        return _exact_error(error)
    finally:
        if marker is not None:
            with files.report_lock:
                if files.plate_search is marker:
                    files.plate_search = None
                if files.operation is marker['cancel']:
                    files.operation = None
        if snapshot_lease is not None:
            snapshot_lease.release()
        if work_lease is not None:
            work_lease.release()
        _PLATE_SEARCH_SLOT.release()


def _open_preview_capture(path):
    """Open a caller-owned preview decoder, with best-effort thread control."""
    threads = app.config.get("PREVIEW_DECODE_THREADS", 0)
    if not threads or not hasattr(cv2, "CAP_PROP_N_THREADS") or not hasattr(cv2, "CAP_FFMPEG"):
        return cv2.VideoCapture(path)
    try:
        cap = cv2.VideoCapture(path, cv2.CAP_FFMPEG,
                               [cv2.CAP_PROP_N_THREADS, threads])
    except (TypeError, cv2.error):
        return cv2.VideoCapture(path)
    accepted = False
    try:
        try:
            accepted = cap.isOpened() and cap.get(cv2.CAP_PROP_N_THREADS) == threads
        except cv2.error:
            pass
        if accepted:
            return cap
    finally:
        if not accepted:
            cap.release()
    return cv2.VideoCapture(path)


def _frame_at(job, t, rstate):
    def decode(path):
        cap = _open_preview_capture(path)
        try:
            fps = rstate["fps"]
            cap.set(cv2.CAP_PROP_POS_FRAMES, int(t * fps))
            ok, frame = cap.read()
            return frame.copy() if ok else None
        finally:
            cap.release()
    return _validated_frame_read(job, False, decode)



@app.route("/api/jobs/<jid>/mediainfo")
def job_mediainfo(jid):
    """Basic video properties straight from the file — available in every
    job phase, no scan report required."""
    job = JOBS.get(jid) or abort(404)
    cap = _open_preview_capture(_job_video(job))
    try:
        fps = cap.get(cv2.CAP_PROP_FPS) or 30.0
        n = cap.get(cv2.CAP_PROP_FRAME_COUNT) or 0
        w_ = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
        h_ = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
    finally:
        cap.release()
    return jsonify({"duration": n / fps if fps else 0, "fps": fps,
                    "width": w_, "height": h_})


@app.route("/api/jobs/<jid>/detections")
def job_detections(jid):
    job = JOBS.get(jid) or abort(404)
    lease = None
    try:
        _thumbnail_cleanup(job)
        # Assign the cleanup owner before the fresh witness.
        doc, selected, fence, lease = fresh_snapshot = _thumbnail_snapshot(job)
        rows, rs, reused = _thumbnail_validate_snapshot(job, fresh_snapshot)
        generation = _thumbnail_select(job, doc, selected, fence, lease,
            validated=None if reused else (rows, rs), reuse_generation=reused)
        marker = _checkpoint_marker(doc)
        capable = doc.get('plate_policy_evidence_version') == 1
        policy = decisions = None
        if capable:
            provenance = doc.get('provenance')
            settings = provenance.get('settings') if isinstance(provenance, dict) else None
            if isinstance(settings, dict):
                policy = {key: settings.get(key) for key in
                          ('uncertain_policy', 'plate_threshold', 'plate_auto_cutoff')}
                try:
                    if policy['uncertain_policy'] not in ('manual_review', 'blur_candidates', 'off'):
                        raise ValueError('missing policy')
                    openscrub.plate_policy.validate_settings(
                        'manual_review', policy['plate_threshold'], policy['plate_auto_cutoff'])
                    decisions = openscrub.plate_policy.evaluate(
                        rows, policy['uncertain_policy'], policy['plate_threshold'],
                        policy['plate_auto_cutoff'], capable_off=True)
                except ValueError:
                    decisions = None
            if decisions is None:
                policy = {'uncertain_policy': 'unavailable', 'plate_threshold': None,
                          'plate_auto_cutoff': None}
        items = []
        for i, d in enumerate(rows):
            item = {"i": i, "category": d["category"], "text": d["text"],
                          "t_start": d["t_start"], "t_end": d["t_end"] if marker is not None else round(d["t_end"], 2),
                          "enabled": d.get("enabled", True), "track": d.get("track", -1),
                          "person": d.get("person", -1), "confidence": d.get("confidence", 0),
                          "zone_dropped": bool(d.get("zone_dropped")),
                          "thumbnail_row": thumbs.raw_row_fingerprint(d)}
            if capable and d.get('category') == 'plate' and not d.get('zone_dropped'):
                if decisions is not None:
                    item['enabled'] = decisions[i].enabled
                item['policy_status'] = decisions[i].status if decisions is not None else 'unknown'
                item['policy_geometry_supported'] = openscrub.plate_policy.supported_geometry(d)
                if d.get('output_choice') in ('blur', 'keep'):
                    item['output_choice'] = d['output_choice']
            items.append(item)
        files = FILES.initialize(job)
        with _thumbnail_owner_guard(job, lease, generation):
            _thumbnail_current_locked(job, selected, fence)
            if files.thumbnail.current is not generation:
                raise _ThumbnailError('thumbnail_obsolete', 409, 'Thumbnail generation changed')
        result = {"detections": items, "fps": rs['fps'],
                  "duration": (marker['total_frames'] if marker is not None else len(rs['cum'])) / rs['fps'],
                  "thumbnail_version": generation.version}
        if marker is not None:
            result.update(processed_duration=marker['next_frame'] / rs['fps'],
                          processed_frames=marker['next_frame'], total_frames=marker['total_frames'])
        if capable:
            result['plate_policy'] = policy
        if _report_is_assisted(doc):
            # Review then loads /letter_gaps for the gap list and render reminder.
            result['assisted_letters'] = True
        return jsonify(result)
    except _ThumbnailError as error:
        return _thumbnail_error_response(error)
    except (KeyError, TypeError, ValueError, OverflowError):
        return _thumbnail_error_response(_ThumbnailError('thumbnail_invalid_report', 500, 'Report invalid'))
    finally:
        if lease is not None:
            _thumbnail_release_lease(job, lease, primary_pending=sys.exc_info()[0] is not None)


def _thumbnail_route(job, index, kind):
    version = request.args.get('v')
    if version is not None and not re.fullmatch(r'[0-9a-f]{32}', version):
        return _thumbnail_error_response(_ThumbnailError('thumbnail_invalid_version', 400, 'Invalid thumbnail version'))
    for attempt in range(2 if version is None else 1):
        try:
            body, etag = _thumbnail_image(job, index, kind, version)
            if version is not None and request.if_none_match.contains_weak(etag[1:-1]):
                response = Response(status=304)
            else:
                response = Response(body, mimetype='image/jpeg')
            if version is not None:
                response.set_etag(etag[1:-1], weak=False)
                response.headers['Cache-Control'] = 'private, no-cache, max-age=0, must-revalidate'
                g.thumbnail_versioned_response = True
            return response
        except _ThumbnailError as error:
            if version is None and error.code == 'thumbnail_obsolete' and attempt == 0:
                continue
            return _thumbnail_error_response(error)
        except FileNotFoundError:
            return _thumbnail_error_response(_ThumbnailError('missing_source', 404, 'Source unavailable'))
        except (OSError, exact.ExactError):
            return _thumbnail_error_response(_ThumbnailError('thumbnail_source_conflict', 409, 'Source unavailable'))
    return _thumbnail_error_response(_ThumbnailError('thumbnail_obsolete', 409, 'Thumbnail generation changed'))


@app.route("/api/jobs/<jid>/detframe/<int:i>")
def job_detframe(jid, i):
    return _thumbnail_route(JOBS.get(jid) or abort(404), i, 'detframe')


@app.route("/api/jobs/<jid>/boxes_at")
def job_boxes_at(jid):
    """Active blur boxes (screen coords) at time t, plus the scroll offset so
    the client can convert edited boxes back to content coordinates."""
    job = JOBS.get(jid) or abort(404)
    doc = _load_job_report(job)
    rs = doc["render_state"]
    t = float(request.args.get("t", 0))
    fidx = min(int(t * rs["fps"]), len(rs["cum"]) - 1)
    ox, oy = rs["cum"][fidx]
    boxes = []
    want_all = request.args.get("all") == "1"
    capable = doc.get('plate_policy_evidence_version') == 1
    for i, d in enumerate(doc["detections"]):
        if not (d["t_start"] - 0.01 <= t <= d["t_end"] + 0.01):
            continue
        if capable and d.get('category') == 'plate':
            if (not openscrub.plate_policy._valid_geometry(d)
                    or d['policy_evidence']['frame'] != fidx):
                continue
        if not want_all and not d.get("enabled", True):
            continue
        if True:
            boxes.append({"i": i, "category": d["category"],
                          "enabled": d.get("enabled", True),
                          "text": d.get("text", ""),
                          "t_start": d["t_start"], "t_end": d["t_end"],
                          "box": [d["cbox"][0] + ox, d["cbox"][1] + oy,
                                  d["cbox"][2] + ox, d["cbox"][3] + oy]})
    return jsonify({"t": t, "ox": ox, "oy": oy, "boxes": boxes})


@app.route("/api/jobs/<jid>/thumb/<int:i>")
def job_thumb(jid, i):
    return _thumbnail_route(JOBS.get(jid) or abort(404), i, 'crop')


@app.route("/api/jobs/<jid>/frame_at")
def job_frame_at(jid):
    job = JOBS.get(jid) or abort(404)
    t = max(0.0, float(request.args.get("t", 0)))
    def decode(path):
        cap = _open_preview_capture(path)
        # Timestamp seeking/backoff preserves VFR and near-end behavior.
        try:
            frame = None
            for tt in (t, max(0.0, t - 0.34), max(0.0, t - 1.0), 0.0):
                cap.set(cv2.CAP_PROP_POS_MSEC, tt * 1000)
                ok, fr = cap.read()
                if ok:
                    frame = fr
                    break
                if tt == 0.0:
                    break
        finally:
            cap.release()
        if frame is None:
            abort(404)
        ok, buf = cv2.imencode(".jpg", frame, [cv2.IMWRITE_JPEG_QUALITY, 82])
        if not ok:
            abort(404)
        return buf.tobytes()
    payload = _validated_frame_read(job, request.args.get("src") == "output", decode)
    return Response(payload, mimetype="image/jpeg")


@app.route("/api/jobs/<jid>/letter_gaps")
def job_letter_gaps(jid):
    """Assisted plate letters: gaps the saved report's cover leaves visible."""
    job = JOBS.get(jid) or abort(404)
    return jsonify(_letter_gap_plan(job)[0])


@app.route("/api/jobs/<jid>/letter_gap/<int:n>.jpg")
def job_letter_gap(jid, n):
    """Preview of gap n: its middle frame of the scan video, plate box drawn."""
    job = JOBS.get(jid) or abort(404)
    result, fps = _letter_gap_plan(job)
    if (result["mode"] != "assisted" or not 0 <= n < len(result["gaps"]) or not fps
            or request.args.get("v") != result.get("token")):
        abort(404)
    gap = result["gaps"][n]
    t = gap["frame"] / fps

    def decode(path):
        cap = _open_preview_capture(path)
        try:
            frame = openscrub._grab_frame(cap, t, fps)
        finally:
            cap.release()
            openscrub._grab_state.pop(id(cap), None)
        if frame is None:
            abort(404)
        return _letter_gap_jpeg(frame, gap["box"])
    payload = _validated_frame_read(job, False, decode)
    return Response(payload, mimetype="image/jpeg")



def _send_open_file(path, **options):
    """One opened generation supplies body, metadata, conditional and Range."""
    if not path:
        abort(404)
    try:
        stream = open(path, "rb")
    except FileNotFoundError:
        abort(404)
    response = None
    try:
        st = os.fstat(stream.fileno())
        conditional = options.pop("conditional", True)
        options.setdefault("download_name", os.path.basename(path))
        # No hash/media read or path-based X-Sendfile; fstat describes exactly
        # this open inode, even after final names change during transfer.
        etag = "%x-%x-%x-%x-%x" % (st.st_dev, st.st_ino, st.st_size,
                                    st.st_mtime_ns, st.st_ctime_ns)
        response = send_file(stream, conditional=False, etag=etag,
                             last_modified=st.st_mtime, **options)
        response.content_length = st.st_size
        if conditional:
            response.make_conditional(request.environ, accept_ranges=True,
                                      complete_length=st.st_size)
        return response
    except BaseException:
        if response is not None:
            response.close()
        stream.close()
        raise


def _send_job_source(job, **options):
    for attempt in range(2):
        snapshot = _capture_frame_source(job)
        state = snapshot["source_state"] or snapshot["state"]
        owner = snapshot["source_job"] or job
        response = error = None
        try:
            with state.report_lock:
                _report_current(owner)
                _recovery_gate(owner)
                try:
                    response = _send_open_file(snapshot["path"], **options)
                except Exception as caught:
                    error = caught
            if _frame_source_current(snapshot):
                if error is not None:
                    raise error
                validated = response
                response = None  # hand off only a successfully validated response
                return validated
        finally:
            # A stale attempt or validation exception still owns its response.
            # Close after leaving the source lock, before request leases release.
            if response is not None:
                response.close()
    abort(409, "output changed during frame read; retry")


@app.route("/api/jobs/<jid>/video")
def job_video_stream(jid):
    """Range-aware stream of the job's scan video so review can PLAY the
    footage with live boxes (issue #17: the box editor was scrub-only,
    'you cannot play review and see hits'). Serves the same file frame_at
    reads — for HDR/VFR jobs that is the normalized SDR scan copy, which
    every browser can decode."""
    job = JOBS.get(jid) or abort(404)
    return _send_job_source(job, conditional=True)



def _same_json_value(left, right):
    """Compare touched JSON values without losing encoder-visible distinctions.

    Nonfinite or unusual values conservatively require publication. Assignment
    replaces touched containers; their originals need no copy or normalization.
    """
    if type(left) is not type(right):
        return False
    if type(left) is float:
        return (math.isfinite(left) and math.isfinite(right) and left == right
                and (left != 0 or math.copysign(1, left) == math.copysign(1, right)))
    if type(left) in (str, int, bool, type(None)):
        return left == right
    if type(left) is list:
        return (len(left) == len(right)
                and all(_same_json_value(a, b) for a, b in zip(left, right)))
    if type(left) is dict:
        return (left.keys() == right.keys()
                and all(_same_json_value(value, right[key])
                        for key, value in left.items()))
    return False


def _valid_manual_creation(value):
    """Only immutable, finite creation records can establish replay equality."""
    def numbers(items, size):
        try:
            return (isinstance(items, list) and len(items) == size
                    and all(type(v) in (int, float) and math.isfinite(v)
                            for v in items))
        except OverflowError:
            return False
    return (isinstance(value, dict)
            and set(value) == {"t_start", "t_end", "cbox", "aoff"}
            and numbers([value["t_start"], value["t_end"]], 2)
            and numbers(value["cbox"], 4)
            and all(type(v) is int for v in value["cbox"])
            and numbers(value["aoff"], 2))


def _quad_context_eq(row):
    # Existing geometry preconditions include this additive field. For a lost
    # acknowledgement also compare the remainder of the row independently.
    return exact.row_context_eq({key: value for key, value in row.items()
                                 if key != 'manual_plate_quad'})


def _quad_source_digest(job, prepared):
    """One leased, descriptor-fenced digest, reused for this live selection."""
    files = FILES.initialize(job)
    with files.report_lock:
        current = files.current_source
        if (current is not None and (current['path'], current['stamp']) ==
                (prepared['path'], prepared['stamp'])):
            cached = current.get('quad_sha256')
            if cached is not None:
                return cached
    with open(prepared['path'], 'rb') as opened:
        if (_file_stamp(os.fstat(opened.fileno())) != prepared['stamp']
                or _file_stamp(os.stat(prepared['path'])) != prepared['stamp']):
            raise exact.ExactError('source changed before digest', 409, 'geometry_conflict')
        digest = hashlib.sha256()
        while True:
            data = opened.read(1 << 20)
            if not data:
                break
            digest.update(data)
        if (_file_stamp(os.fstat(opened.fileno())) != prepared['stamp']
                or _file_stamp(os.stat(prepared['path'])) != prepared['stamp']):
            raise exact.ExactError('source changed during digest', 409, 'geometry_conflict')
    return digest.hexdigest()


def _parse_sample_precondition(value, row=False):
    def invalid():
        raise exact.ExactError('invalid geometry precondition shape', 400, 'invalid_sample_request')
    if not isinstance(value, dict):
        invalid()
    if (type(value.get('version')) is not int or value['version'] != 1
            or value.get('policy') != exact.POLICY
            or not isinstance(value.get('source_ref'), str) or not 1 <= len(value['source_ref']) <= 128
            or type(value.get('index')) is not int or value['index'] < 0
            or any(type(value.get(k)) is not int or value[k] <= 0 for k in ('width','height'))):
        invalid()
    for key in ('timeline_eq','row_context_eq') if row else ('timeline_eq',):
        if not isinstance(value.get(key), str) or re.fullmatch('[0-9a-f]{64}', value[key]) is None:
            invalid()
    try:
        exact.vector(value.get('offset'), 2)
        if row:
            baseline = value['base']
            if not isinstance(baseline, dict) or set(baseline) != {'cbox','span'}:
                invalid()
            exact.vector(baseline['cbox'], 4)
            exact.vector(baseline['span'], 3)
    except (KeyError, exact.ExactError):
        invalid()
    return value


def _strict_geometry(edits):
    preconditions = edits.get('geometry_preconditions', {})
    quads = edits.get('manual_plate_quads', {})
    if not isinstance(quads, dict):
        raise exact.ExactError('manual_plate_quads must be an index map', 400, 'invalid_sample_request')
    if not isinstance(preconditions, dict):
        raise exact.ExactError('geometry_preconditions must be an index map', 400, 'invalid_sample_request')
    for key, value in preconditions.items():
        if (not isinstance(key, str) or re.fullmatch('0|[1-9][0-9]*', key) is None
                or len(key) > 18 or not any(key in (edits.get(k) or {}) for k in ('box_overrides','time_overrides','manual_plate_quads'))):
            raise exact.ExactError('strict row must name a submitted raw index', 400, 'invalid_sample_request')
        _parse_sample_precondition(value, row=True)
        if key in quads:
            if (not isinstance(value.get('quad_context_eq'), str)
                    or re.fullmatch('[0-9a-f]{64}', value['quad_context_eq']) is None):
                raise exact.ExactError('quad row context required', 400, 'invalid_sample_request')
            quad = quads[key]
            if quad is not None and (not isinstance(quad, dict) or set(quad) != {'points'}):
                raise exact.ExactError('quad must be four corners or null', 400, 'invalid_sample_request')
        try:
            if key in (edits.get('box_overrides') or {}):
                exact.vector(edits['box_overrides'][key], 4)
            if key in (edits.get('time_overrides') or {}):
                span = exact.vector(edits['time_overrides'][key], 2)
                if not span[1] > span[0] >= 0:
                    raise ValueError()
        except (exact.ExactError, ValueError):
            raise exact.ExactError('invalid strict geometry target', 400, 'invalid_sample_request') from None
    if not set(quads).issubset(preconditions):
        raise exact.ExactError('quad needs an inspected row', 400, 'invalid_sample_request')
    if preconditions:
        strict_indices = {int(key) for key in preconditions}
        for field in ('box_overrides', 'time_overrides', 'manual_plate_quads'):
            for key in (edits.get(field) or {}):
                try:
                    index = int(key)
                except (TypeError, ValueError, OverflowError):
                    continue
                if index in strict_indices and key != str(index):
                    raise exact.ExactError('strict row index has an alias', 400, 'invalid_sample_request')
    for manual in edits.get('manual', []):
        if 'sample_precondition' in manual:
            _parse_sample_precondition(manual['sample_precondition'])
    return preconditions


def _manual_candidates(doc, edits):
    """Classify immutable replay before current-source freshness or any mutation."""
    identified = {}
    for row in doc['detections']:
        identity = row.get('manual_id')
        if isinstance(identity, str):
            identified.setdefault(identity, []).append(row)
    additions, strict = [], []
    rs = doc['render_state']
    for manual in edits.get('manual', []):
        has_id, identity = 'manual_id' in manual, manual.get('manual_id')
        pc = manual.get('sample_precondition')
        if has_id and (not isinstance(identity,str) or re.fullmatch(r'[A-Za-z0-9._:-]{1,128}',identity) is None):
            message = 'Invalid manual_id: expected 1–128 ASCII letters, digits or ._:-'
            raise exact.ExactError(message, 400, 'invalid_sample_request' if pc is not None else message)
        try:
            if pc is not None:
                times = exact.vector([manual['t_start'],manual['t_end'],manual.get('t_ref',manual['t_start'])], 3)
                box = exact.vector(manual['screen_box'], 4)
                t0,t1,tref = times
                ox,oy = pc['offset']
            else:
                t0,t1 = float(manual['t_start']),float(manual['t_end'])
                tref = float(manual.get('t_ref',t0)); box = manual['screen_box']
                if has_id and (len(box) != 4 or not all(math.isfinite(v) for v in [t0,t1,tref,*box])):
                    raise ValueError()
                index = min(int(tref*rs['fps']),len(rs['cum'])-1)
                ox,oy = rs['cum'][index]
            creation = dict(t_start=t0,t_end=t1,cbox=[int(box[0]-ox),int(box[1]-oy),int(box[2]-ox),int(box[3]-oy)],aoff=[ox,oy])
            if (has_id or pc is not None) and not _valid_manual_creation(creation):
                raise ValueError()
        except (KeyError, TypeError, ValueError, OverflowError, IndexError):
            if has_id or pc is not None:
                message = 'Invalid manual creation: finite times, four coordinates and two offsets required'
                raise exact.ExactError(message, 400, 'invalid_sample_request' if pc is not None else message) from None
            raise
        if has_id and identity in identified:
            rows = identified[identity]
            if (len(rows) != 1 or not _valid_manual_creation(rows[0].get('manual_creation'))
                    or rows[0]['manual_creation'] != creation):
                message = 'manual_id conflict: creation differs, is missing/invalid, or matches multiple rows'
                raise exact.ExactError(message, 409, 'geometry_conflict' if pc is not None else message)
            continue
        row = dict(creation,category='manual',text='user-drawn',confidence=1.,last_seen=t0,enabled=True)
        if doc.get('plate_policy_evidence_version') == 1:
            row['output_choice'] = 'blur'
        if has_id:
            row.update(manual_id=identity,manual_creation={**creation,'cbox':list(creation['cbox']),'aoff':list(creation['aoff'])})
            identified[identity] = [row]
        additions.append(row)
        if pc is not None:
            strict.append((manual, pc))
    return additions, strict


def _check_sample_precondition(pc, selected, fps, cum, timeline_eq):
    if (pc['source_ref'] != selected['source_ref'] or pc['timeline_eq'] != timeline_eq
            or pc['width'] != selected['facts']['width'] or pc['height'] != selected['facts']['height']
            or pc['index'] >= len(cum) or pc['offset'] != cum[pc['index']]):
        raise exact.ExactError('sample source/timeline differs', 409, 'geometry_conflict')


def _validate_strict_rows(doc, edits, preconditions, selected, fps, cum, timeline_eq, digest=None, marker=None):
    targets = {}
    quads = edits.get('manual_plate_quads', {})
    for key, pc in preconditions.items():
        _check_sample_precondition(pc, selected, fps, cum, timeline_eq)
        index = int(key)
        if index >= len(doc['detections']):
            raise exact.ExactError('raw row no longer exists', 409, 'geometry_conflict')
        row = doc['detections'][index]
        baseline = pc['base']
        desired_box = list((edits.get('box_overrides') or {}).get(key, baseline['cbox']))
        span = (edits.get('time_overrides') or {}).get(key)
        desired_span = ([span[0], span[1], min(max(baseline['span'][2],span[0]),span[1])]
                        if span is not None else list(baseline['span']))
        intended = dict(cbox=desired_box, span=desired_span)
        current = exact.row_base(row)
        if marker is not None:
            if current != baseline and current != intended:
                raise exact.ExactError('geometry baseline/intended tuple differs', 409, 'geometry_conflict')
            prior = pc['scan_frame_bounds']
            authority = openscrub._frame_authority(row, total=len(cum))
            actual = list(authority) if authority is not None else None
            changed_time = span is not None and list(span) != baseline['span'][:2]
            if actual == prior:
                if (exact.row_context_eq(row) != pc['row_context_eq'] or
                        changed_time and current == intended and current != baseline and prior is not None):
                    raise exact.ExactError('raw row context differs', 409, 'geometry_conflict')
            elif prior is not None and actual is None and changed_time and current == intended:
                # A committed time edit deliberately removed the old bounds.
                # Reconstruct only those immutable fields to verify a replay.
                restored = dict(row, scan_frame_start=prior[0], scan_frame_end=prior[1])
                if exact.row_context_eq(restored) != pc['row_context_eq']:
                    raise exact.ExactError('raw row context differs', 409, 'geometry_conflict')
            else:
                raise exact.ExactError('row frame authority differs', 409, 'geometry_conflict')
            targets[key] = intended, current == intended, None
            continue
        desired_quad = None
        if key in quads:
            if (row.get('category') != 'plate'
                    or not baseline['span'][0]-.01 <= pc['index']/fps <= baseline['span'][1]+.01):
                raise exact.ExactError('sample does not inspect this plate row', 409, 'geometry_conflict')
            prov = doc.get('provenance', {})
            if (not _quad_scan_supported(doc, selected)
                    or not digest or prov.get('input_sha256') != digest):
                raise exact.ExactError('verified SDR scan identity unavailable', 409, 'geometry_conflict')
            if _quad_context_eq(row) != pc['quad_context_eq']:
                raise exact.ExactError('raw row context differs', 409, 'geometry_conflict')
            try:
                if quads[key] is not None:
                    desired_quad = plate_quad.make_record(quads[key]['points'], pc, digest, fps, len(cum), selected['facts'])
            except (ValueError, TypeError, OverflowError, cv2.error) as error:
                raise exact.ExactError('invalid plate corners: '+str(error), 400, 'invalid_sample_request') from None
            baseline_matches = current == baseline and exact.row_context_eq(row) == pc['row_context_eq']
            wanted_matches = (current == intended and
                              (('manual_plate_quad' not in row) if desired_quad is None else
                               _same_json_value(row.get('manual_plate_quad'), desired_quad)))
            if not baseline_matches and not wanted_matches:
                raise exact.ExactError('quad baseline/intended tuple differs', 409, 'geometry_conflict')
        else:
            box_requested = key in (edits.get('box_overrides') or {})
            box_changed = box_requested and desired_box != baseline['cbox']
            witness = pc.get('quad_context_eq')
            witness_matches = (isinstance(witness, str)
                               and re.fullmatch('[0-9a-f]{64}', witness) is not None
                               and witness == _quad_context_eq(row))
            context_matches = exact.row_context_eq(row) == pc['row_context_eq']
            original_quad = _quad_baseline_value(pc.get('quad_baseline'))
            valid_original_quad = plate_quad.valid_record(original_quad)
            retired_replay = (row.get('category') == 'plate' and box_changed and current == intended
                              and witness_matches and valid_original_quad
                              and 'manual_plate_quad' not in row
                              and exact.row_context_eq({**row, 'manual_plate_quad': original_quad})
                                  == pc['row_context_eq'])
            if not context_matches and not retired_replay:
                raise exact.ExactError('raw row context differs', 409, 'geometry_conflict')
            if current != baseline and current != intended:
                raise exact.ExactError('geometry baseline/intended tuple differs', 409, 'geometry_conflict')
            if (box_requested and current['cbox'] != desired_box and row.get('category') == 'plate'
                    and plate_quad.valid_record(row.get('manual_plate_quad'))
                    and (not witness_matches or not valid_original_quad
                         or not _same_json_value(original_quad, row['manual_plate_quad']))):
                raise exact.ExactError('plate box change requires quad baseline', 409, 'geometry_conflict')
        targets[key] = intended, current == intended, desired_quad
    return targets


def _checkpoint_audio_key(row):
    if not isinstance(row, dict):
        return None
    try:
        if isinstance(row.get('t0'), bool) or isinstance(row.get('t1'), bool):
            return None
        start, end = float(row['t0']), float(row['t1'])
        if not math.isfinite(start) or not math.isfinite(end) or not 0 <= start < end:
            return None
        mode = row.get('mode') if row.get('mode') in ('mute', 'bleep') else 'mute'
        return start, end, mode
    except (KeyError, TypeError, ValueError, OverflowError):
        return None


def _checkpoint_edit_preflight(doc, edits, preconditions, marker):
    """Require an inspected sample for geometry and disallow future spans."""
    boundary = marker['next_frame'] / marker['fps']
    if edits.get('manual_plate_quads'):
        raise exact.ExactError('plate corners are unavailable in this scan mode', 409, 'geometry_conflict')
    for field in ('box_overrides', 'time_overrides'):
        values = edits.get(field) or {}
        if not isinstance(values, dict) or any(key not in preconditions for key in values):
            raise exact.ExactError('checkpoint geometry requires an inspected sample', 400, 'invalid_sample_request')
    for key, pc in preconditions.items():
        if 'scan_frame_bounds' not in pc:
            raise exact.ExactError('row %s requires frame authority' % key, 400, 'invalid_sample_request')
        bounds = pc['scan_frame_bounds']
        if bounds is not None and (not isinstance(bounds, list) or len(bounds) != 2 or
                any(type(value) is not int for value in bounds) or
                not 0 <= bounds[0] <= pc['index'] < bounds[1] <= marker['next_frame']):
            raise exact.ExactError('row %s has invalid frame authority' % key, 400, 'invalid_sample_request')
    for key, span in (edits.get('time_overrides') or {}).items():
        exact.vector(span, 2)
        if not 0 <= span[0] < span[1] <= boundary:
            raise exact.ExactError('row %s span %s exceeds inspected boundary %s' %
                                   (key, span, boundary), 400, 'invalid_sample_request')
    for index, manual in enumerate(edits.get('manual', [])):
        if not isinstance(manual, dict) or 'sample_precondition' not in manual:
            raise exact.ExactError('manual row %s requires an inspected sample' % index,
                                   400, 'invalid_sample_request')
        span = exact.vector([manual.get('t_start'), manual.get('t_end')], 2)
        if not 0 <= span[0] < span[1] <= boundary:
            raise exact.ExactError('manual row %s span %s exceeds inspected boundary %s' %
                                   (index, span, boundary), 400, 'invalid_sample_request')
    audio = edits.get('audio')
    if audio is not None:
        if not isinstance(audio, list):
            raise exact.ExactError('audio spans must be a list', 400, 'invalid_sample_request')
        allowed_tail = {}
        previous_audio = doc.get('audio_redactions')
        for old in previous_audio if isinstance(previous_audio, list) else ():
            key = _checkpoint_audio_key(old)
            if key is not None and key[1] > boundary:
                allowed_tail[key] = allowed_tail.get(key, 0) + 1
        for index, span in enumerate(audio):
            if (not isinstance(span, dict) or not exact.finite(span.get('t0')) or
                    not exact.finite(span.get('t1')) or
                    not 0 <= span['t0'] < span['t1'] or
                    span.get('mode', 'mute') not in ('mute', 'bleep')):
                raise exact.ExactError('audio span %s exceeds the inspected boundary or is invalid' % index,
                                       400, 'invalid_sample_request')
            if span['t1'] > boundary:
                key = _checkpoint_audio_key(span)
                if not allowed_tail.get(key):
                    raise exact.ExactError('audio span %s exceeds the inspected boundary' % index,
                                           400, 'invalid_sample_request')
                allowed_tail[key] -= 1


def _checkpoint_audio_rows(previous, submitted, boundary):
    """Keep complete raw values for audio spans the reviewer did not alter."""
    by_span, used = {}, {}
    for row in previous if isinstance(previous, list) else ():
        key = _checkpoint_audio_key(row)
        if key is not None:
            by_span.setdefault(key, []).append(row)
    result = []
    for row in submitted or []:
        key = (float(row['t0']), float(row['t1']), row.get('mode', 'mute'))
        offset = used.get(key, 0)
        matching = by_span.get(key, ())
        result.append(matching[offset] if offset < len(matching) else
                      dict(t0=key[0], t1=key[1], mode=key[2]))
        used[key] = offset + 1
    seen = {}
    for row in previous if isinstance(previous, list) else ():
        key = _checkpoint_audio_key(row)
        if key is None:
            result.append(row)
        elif key[1] > boundary:
            offset = seen.get(key, 0)
            seen[key] = offset + 1
            if offset >= used.get(key, 0):
                result.append(row)
    return result


def _load_checkpoint_edit_report(path, *, paused=True):
    """Open and parse the same regular report generation that will be fenced."""
    try:
        with open(path, encoding='utf-8', opener=_thumbnail_nonblocking_opener) as stream:
            opened = os.fstat(stream.fileno())
            named = os.stat(path, follow_symlinks=False)
            if (not stat.S_ISREG(opened.st_mode) or not stat.S_ISREG(named.st_mode) or
                    _file_stamp(opened) != _file_stamp(named)):
                raise OSError('report changed')
            stamp = _file_stamp(opened)
            doc = json.load(stream)
            if (_file_stamp(os.fstat(stream.fileno())) != stamp or
                    _file_stamp(os.stat(path, follow_symlinks=False)) != stamp):
                raise OSError('report changed')
    except (OSError, ValueError, RecursionError):
        raise exact.ExactError('checkpoint report is unavailable or changed', 409, 'geometry_conflict') from None
    if (not isinstance(doc, dict) or
            (paused and 'stop_review' not in doc) or
            (not paused and ('stop_review' in doc or not openscrub._has_checkpoint_identity(doc)))):
        raise exact.ExactError('checkpoint report changed', 409, 'geometry_conflict')
    return doc, stamp


@app.route('/api/jobs/<jid>/detections', methods=['POST'])
def job_save_edits(jid):
    job = JOBS.get(jid) or abort(404)
    edits = request.get_json(force=True)
    path = os.path.join(job['dir'], 'report.json')
    prepared = lease = None
    needs_source = False
    preparation_authority = None
    preparation_report = None
    digest = None
    checkpoint_preparation = None
    try:
        preconditions = _strict_geometry(edits)
        while True:
            candidate = None
            with _exact_owner_guard(job, lease):
                _edit_gate(job)
                try:
                    if job.get('_checkpoint_unfinished'):
                        doc, report_stamp = _load_checkpoint_edit_report(path)
                    else:
                        doc = _load_job_report(job)
                        report_stamp = None
                        if isinstance(doc, dict) and 'stop_review' in doc:
                            doc, report_stamp = _load_checkpoint_edit_report(path)
                        elif openscrub._has_checkpoint_identity(doc):
                            doc, report_stamp = _load_checkpoint_edit_report(path, paused=False)
                except FileNotFoundError:
                    abort(404, 'job report not found')
                marker = _checkpoint_marker(doc)
                evidence = marker or _completed_checkpoint(doc)
                if evidence is not None:
                    _checkpoint_edit_preflight(doc, edits, preconditions, evidence)
                additions, strict_manual = _manual_candidates(doc, edits)
                needs_source = bool(evidence is not None or preconditions or strict_manual)
                if needs_source and prepared is None:
                    candidate = doc.get('provenance', {}).get('input')
                    if not isinstance(candidate,str) or not candidate:
                        raise exact.ExactError('report has no selected scan input')
                    files = FILES.initialize(job)
                    preparation_authority = (files.current_source, files.source_epoch, files.operation)
                    if edits.get('manual_plate_quads'):
                        preparation_report = (files.committed_report_epoch, _file_stamp(os.stat(path)))
                    if evidence is not None:
                        checkpoint_preparation = (evidence['input_sha256'], files.committed_report_epoch,
                                                  report_stamp)
                else:
                    selected = targets = None
                    if needs_source:
                        files = FILES.initialize(job)
                        previous, source_epoch, operation = preparation_authority
                        current = files.current_source
                        if (files.operation is not operation or
                                (current is not previous and
                                 (current is None or (current['path'], current['stamp']) !=
                                  (prepared['path'], prepared['stamp']))) or
                                (current is previous and files.source_epoch != source_epoch)):
                            raise exact.ExactError('source authority changed during save', 409, 'geometry_conflict')
                        if (os.path.realpath(doc.get('provenance', {}).get('input','')) != prepared['path']
                                or os.path.realpath(job['video']) != prepared['path']):
                            raise exact.ExactError('source changed while preparing save', 409, 'geometry_conflict')
                        if (preparation_report is not None and
                                (files.committed_report_epoch, _file_stamp(os.stat(path))) != preparation_report):
                            raise exact.ExactError('report changed during quad preparation', 409, 'geometry_conflict')
                        if checkpoint_preparation is not None:
                            checkpoint_digest, epoch, stamp = checkpoint_preparation
                            try:
                                named = os.stat(path, follow_symlinks=False)
                                report_current = stat.S_ISREG(named.st_mode) and _file_stamp(named) == stamp
                            except OSError:
                                report_current = False
                            if (evidence is None or evidence['input_sha256'] != checkpoint_digest or
                                    files.committed_report_epoch != epoch or not report_current):
                                raise exact.ExactError('checkpoint changed while preparing save', 409, 'geometry_conflict')
                            _checkpoint_source_policy(evidence, prepared)
                        elif evidence is not None:
                            raise exact.ExactError('checkpoint appeared while preparing save', 409, 'geometry_conflict')
                        selected = _select_observed_locked(job, prepared)
                        _exact_current_locked(job, selected)
                        fps,cum,timeline_eq,_ = _exact_policy(doc,selected)
                        targets = _validate_strict_rows(
                            doc, edits, preconditions, selected, fps, cum, timeline_eq, digest, evidence)
                        for manual,pc in strict_manual:
                            _check_sample_precondition(pc,selected,fps,cum,timeline_eq)
                            t0,t1,tref = manual['t_start'],manual['t_end'],manual.get('t_ref',manual['t_start'])
                            box = manual['screen_box']
                            if (tref != pc['index']/fps or not 0 <= t0 <= tref <= t1 <= len(cum)/fps
                                    or t1 <= t0 or not 0 <= box[0] < box[2] <= pc['width']
                                    or not 0 <= box[1] < box[3] <= pc['height']):
                                raise exact.ExactError('strict manual geometry outside inspected sample',400,'invalid_sample_request')
                    # Keep the existing destination-level no-op policy.
                    missing, touched = object(), {}
                    def assign(target, key, value):
                        destination = (id(target), key)
                        if destination not in touched:
                            touched[destination] = (target, key, target.get(key, missing))
                        target[key] = value
                    def remove(target, key):
                        destination = (id(target), key)
                        if destination not in touched:
                            touched[destination] = (target, key, target.get(key, missing))
                        target.pop(key, None)
                    original_count = len(doc['detections'])
                    capable = doc.get('plate_policy_evidence_version') == 1
                    switch = edits.get('plate_policy')
                    settings = doc.get('provenance', {}).get('settings', {})
                    if 'plate_policy' in edits:
                        if not capable:
                            abort(409, 'optional plate evidence requires a fresh optional scan')
                        if (not isinstance(switch, dict) or not switch
                                or set(switch) - {'uncertain_policy', 'plate_auto_cutoff'}):
                            abort(400, 'invalid plate policy request; changing the candidate floor requires a rescan')
                        policy = switch.get('uncertain_policy', settings.get('uncertain_policy'))
                        cutoff = switch.get('plate_auto_cutoff', settings.get('plate_auto_cutoff'))
                        if policy not in ('manual_review', 'blur_candidates', 'off'):
                            abort(400, 'invalid plate policy')
                        try:
                            # Preserve a valid cutoff even while switched off.
                            openscrub.plate_policy.validate_settings(
                                'manual_review', settings.get('plate_threshold'), cutoff)
                        except ValueError as error:
                            abort(400, str(error))
                        assign(settings, 'uncertain_policy', policy)
                        assign(settings, 'plate_auto_cutoff', cutoff)
                    published = False
                    acknowledged_stamp = report_stamp
                    enabled = edits.get('enabled',{})
                    for i,row in enumerate(doc['detections']):
                        if str(i) in enabled:
                            assign(row, 'enabled', bool(enabled[str(i)]))
                            if capable:
                                assign(row, 'output_choice', 'blur' if enabled[str(i)] else 'keep')
                    original_boxes = {}
                    for key,box in (edits.get('box_overrides') or {}).items():
                        i = int(key)
                        if 0 <= i < len(doc['detections']):
                            row = doc['detections'][i]
                            if row.get('category') == 'plate' and plate_quad.valid_record(row.get('manual_plate_quad')):
                                original_boxes.setdefault(i, row.get('cbox'))
                        if key in preconditions:
                            if not targets[key][1]:
                                assign(doc['detections'][i], 'cbox', [float(v) for v in targets[key][0]['cbox']])
                        elif 0 <= i < len(doc['detections']) and len(box) == 4:
                            assign(doc['detections'][i], 'cbox', [float(v) for v in box])
                    for i, original_box in original_boxes.items():
                        row = doc['detections'][i]
                        key = str(i)
                        if (row.get('cbox') != original_box
                                and key not in (edits.get('manual_plate_quads') or {})
                                and row.get('category') == 'plate'
                                and plate_quad.valid_record(row.get('manual_plate_quad'))):
                            remove(row, 'manual_plate_quad')
                    for key,span in (edits.get('time_overrides') or {}).items():
                        i = int(key)
                        if key in preconditions:
                            if not targets[key][1]:
                                t0,t1,last = targets[key][0]['span']
                                row = doc['detections'][i]
                                if evidence is not None and (row['t_start'], row['t_end']) != (t0, t1):
                                    remove(row, 'scan_frame_start')
                                    remove(row, 'scan_frame_end')
                                assign(row, 't_start', t0); assign(row, 't_end', t1); assign(row, 'last_seen', last)
                        elif 0 <= i < len(doc['detections']) and len(span) == 2:
                            t0,t1 = float(span[0]),float(span[1])
                            if t1 > t0 >= 0:
                                row = doc['detections'][i]
                                assign(row, 't_start', t0); assign(row, 't_end', t1)
                                assign(row, 'last_seen', min(max(row.get('last_seen',t0),t0),t1))
                    for key, value in (edits.get('manual_plate_quads') or {}).items():
                        row = doc['detections'][int(key)]
                        desired = targets[key][2]
                        if desired is None:
                            if 'manual_plate_quad' in row:
                                remove(row, 'manual_plate_quad')
                        else:
                            assign(row, 'manual_plate_quad', desired)
                    if digest is not None:
                        selected['quad_sha256'] = digest
                    doc['detections'].extend(additions)
                    if capable:
                        policy = settings.get('uncertain_policy')
                        floor = settings.get('plate_threshold')
                        cutoff = settings.get('plate_auto_cutoff')
                        try:
                            decisions = openscrub.plate_policy.evaluate(
                                doc['detections'], policy, floor, cutoff, capable_off=True)
                        except ValueError as error:
                            abort(400, str(error))
                        for row, decision in zip(doc['detections'], decisions):
                            if row.get('category') == 'plate' and not row.get('zone_dropped'):
                                assign(row, 'enabled', decision.enabled)
                    if 'audio' in edits:
                        if evidence is not None:
                            audio = _checkpoint_audio_rows(doc.get('audio_redactions'), edits.get('audio'),
                                                          evidence['next_frame'] / evidence['fps'])
                        else:
                            audio = [dict(t0=float(s['t0']),t1=float(s['t1']),mode=s.get('mode') if s.get('mode') in ('mute','bleep') else 'mute')
                                     for s in (edits.get('audio') or []) if float(s.get('t1',0)) > float(s.get('t0',0)) >= 0]
                        assign(doc, 'audio_redactions', audio)
                    if (len(doc['detections']) != original_count or
                            any(original is missing or key not in target or not _same_json_value(original, target[key])
                                for target, key, original in touched.values())):
                        if evidence is not None:
                            acknowledged_stamp = _publish_job_report_locked(
                                job, path, doc, expected_stamp=report_stamp, expected_source=selected)
                            published = True
                        else:
                            _publish_job_report_locked(job, path, doc)
                        _report_committed_locked(job, doc)
                    per = {}
                    for row in doc['detections']:
                        if row['category'] in ('name',):
                            per.setdefault(row['text'],[]).append(row.get('enabled',True))
                    result = dict(ok=True,total=len(doc['detections']),suggest_allowlist=sorted(t for t,states in per.items() if len(states)>=2 and not any(states)))
                    if evidence is not None:
                        if marker is not None:
                            try:
                                token = _checkpoint_resume_token_locked(job)
                            except Conflict:
                                if published:
                                    raise RuntimeError('checkpoint save committed but its acknowledgement is uncertain') from None
                                raise
                        try:
                            observed = os.stat(path, follow_symlinks=False)
                            same_report = (stat.S_ISREG(observed.st_mode) and
                                           _file_stamp(observed) == acknowledged_stamp)
                        except OSError:
                            same_report = False
                        if not same_report or not _checkpoint_source_unchanged(selected):
                            if published:
                                raise RuntimeError('checkpoint save committed but its acknowledgement is uncertain')
                            raise exact.ExactError('checkpoint report changed before save acknowledgement',
                                                   409, 'geometry_conflict')
                        if marker is not None:
                            result['resume_token'] = token
                    if preconditions:
                        result['geometry_rows'] = {}
                        for key, pc in preconditions.items():
                            row = doc['detections'][int(key)]
                            accepted = {**pc, 'row_context_eq': exact.row_context_eq(row),
                                        'base': exact.row_base(row), 'quad_context_eq': _quad_context_eq(row)}
                            if row.get('category') == 'plate':
                                accepted['manual_plate_quad'] = row.get('manual_plate_quad')
                                accepted['quad_baseline'] = _quad_baseline_token(row)
                            if evidence is not None:
                                authority = openscrub._frame_authority(row, total=len(cum))
                                accepted['scan_frame_bounds'] = list(authority) if authority is not None else None
                            result['geometry_rows'][key] = accepted
                    return jsonify(result)
            # A genuinely new strict mutation was found, before any mutation.
            # Reserve/probe outside report_lock, then reload/reclassify latest raw.
            if checkpoint_preparation is None:
                prepared, lease = _prepare_observed_source(job,candidate)
            else:
                prepared, lease = _prepare_observed_source(job, candidate,
                    checkpoint_sha256=checkpoint_preparation[0])
            if edits.get('manual_plate_quads'):
                if not _quad_scan_supported(doc, prepared):
                    raise exact.ExactError('SDR scan identity unavailable', 409, 'geometry_conflict')
                fps, cum, _, tolerance = _exact_policy(doc, prepared)
                digest = _quad_source_digest(job, prepared)
                for key in edits['manual_plate_quads']:
                    pc = preconditions[key]
                    _read_exact_source(prepared, pc['index'], fps=fps, count=len(cum), tolerance_s=tolerance)
    except exact.ExactError as error:
        if checkpoint_preparation is not None and error.status in (409, 422):
            error = exact.ExactError(str(error), 409, 'geometry_conflict')
        elif needs_source and error.status in (409, 422) and FILES.initialize(job).source_retired:
            error = exact.ExactError('sample source has changed; rescan required', 409, 'geometry_conflict')
        return _exact_error(error)
    except FileNotFoundError:
        if not needs_source:
            raise
        return _exact_error(exact.ExactError('sample source is no longer available', 409, 'geometry_conflict'))
    finally:
        if lease is not None:
            lease.release()


@app.route("/api/jobs/<jid>/track_object", methods=["POST"])
def job_track_object(jid):
    """Targeted redaction: the user circled an object on one frame and
    picked a time window on the review timeline — template-track it through
    that window and add the result as a dense track in the report, so the
    review shows one card (with fan-out) and the render blurs it wherever
    it went. Runs in a background thread; poll /track_status."""
    job = JOBS.get(jid) or abort(404)
    p = request.get_json(force=True)
    seed_pc, selected, snapshot_lease = None, None, None
    try:
        if isinstance(p, dict) and 'seed' in p:
            seed_pc = _parse_sample_precondition(p['seed'])
            if set(seed_pc) != {'version','source_ref','timeline_eq','policy','index',
                                'width','height','offset'}:
                raise exact.ExactError('seed must be a sample precondition',400,'invalid_sample_request')
            try:
                exact.vector(p.get('box'), 4)
            except exact.ExactError as error:
                raise exact.ExactError(str(error),400,'invalid_sample_request') from None
            if not all(exact.finite(p.get(key)) for key in ('t_ref','t0','t1')):
                raise exact.ExactError('finite strict times required',400,'invalid_sample_request')
        box = [float(v) for v in p["box"]]
        t_ref, t0, t1 = (float(p["t_ref"]), float(p["t0"]), float(p["t1"]))
        if len(box) != 4 or not (t1 > t0 >= 0) or not (t0 <= t_ref <= t1):
            abort(400)
        if seed_pc is not None:
            if (not 0 <= box[0] < box[2] <= seed_pc['width']
                    or not 0 <= box[1] < box[3] <= seed_pc['height']):
                raise exact.ExactError('strict box outside sample',400,'invalid_sample_request')
            with FILES.initialize(job).report_lock:
                admission_cancel = job['cancel']
                admission_qgen = job.get('qgen', 0)
                admission_signalled = admission_cancel.is_set()
            doc, selected, snapshot_fence, snapshot_lease = _exact_snapshot(job)
            fps, cum, timeline_eq, tolerance = _exact_policy(doc, selected)
            _check_sample_precondition(seed_pc, selected, fps, cum, timeline_eq)
            seed_count = len(cum)
            if t_ref != seed_pc['index']/fps or t1 > len(cum)/fps:
                raise exact.ExactError('strict reference/window differs from sample',400,'invalid_sample_request')
    except exact.ExactError as error:
        if snapshot_lease is not None:
            snapshot_lease.release()
        return _exact_error(error)
    except (KeyError, TypeError, ValueError):
        if snapshot_lease is not None:
            snapshot_lease.release()
        abort(400)
    except BaseException:
        if snapshot_lease is not None:
            snapshot_lease.release()
        raise
    st = {"state": "running", "added": 0, "error": None}
    files = FILES.initialize(job)
    current = job.get('video')
    operation = snapshot_fence[0][1] if selected is not None else files.operation
    try:
        lease = _own_files(job, work=True)
    finally:
        if snapshot_lease is not None:
            snapshot_lease.release()

    def track_report_guard():
        if selected is not None:
            return _exact_owner_guard(job, lease)
        return files.report_lock

    def strict_current():
        if lease.operation is None:
            if (job.get('qgen', 0) != admission_qgen
                    or job['cancel'] is not admission_cancel
                    or (not admission_signalled and admission_cancel.is_set())
                    or (operation is not None and operation.is_set())):
                raise exact.ExactError('tracking admission was cancelled',409,'sample_conflict')
        elif (not _operation_valid(job, lease) or job.get('trackbg') is not st
                or lease.operation.is_set()):
            raise exact.ExactError('tracking operation changed or was cancelled',409,'sample_conflict')

    def strict_document():
        _exact_current_locked(job, selected)
        if lease.source != selected['path']:
            raise exact.ExactError('work lease does not own selected source',409,'sample_conflict')
        try:
            latest = _load_job_report(job)
        except (OSError, ValueError):
            raise exact.ExactError('latest tracking report is unavailable', 409, 'sample_conflict') from None
        provenance = latest.get('provenance') if isinstance(latest, dict) else None
        report_input = provenance.get('input') if isinstance(provenance, dict) else None
        if not isinstance(report_input, str) or os.path.realpath(report_input) != selected['path']:
            raise exact.ExactError('report input differs from selected source', 409, 'sample_conflict')
        current_fps, current_cum, current_eq, _ = _exact_policy(latest, selected)
        _check_sample_precondition(seed_pc, selected, current_fps,current_cum,current_eq)
        # Report I/O/projection may block while cancellation signals its Event.
        _exact_current_locked(job, selected)
        strict_current()
        return latest

    try:
        if snapshot_lease is not None:
            if lease.source_state is not snapshot_lease.source_state:
                raise exact.ExactError('containing source changed', 409, 'sample_conflict')
            if lease.source_state is not None and lease.source_state is not files:
                # Use the owner observed with the sample, including changes
                # between releasing the snapshot and entering the work gate.
                lease.exact_source_epoch = snapshot_lease.exact_source_epoch
        with track_report_guard():
            _edit_gate(job)
            if job.get("video") != current or files.operation is not operation:
                abort(409, "job operation or source changed — retry tracking")
            if selected is not None:
                strict_current()
                strict_document()
            if ((files.tracker is not None and not files.tracker.released)
                    or job.get("trackbg", {}).get("state") == "running"):
                abort(409, "tracking already in progress")
            if job["cancel"].is_set():
                if files.work > 1:
                    abort(409, "cancelled job work is still cleaning up")
                job["cancel"].clear()
            lease.operation = threading.Event()
            files.operation = lease.operation
            job["cancel"] = lease.operation
            files.tracker = lease
            job["trackbg"] = st
    except exact.ExactError as error:
        lease.release()
        return _exact_error(error)
    except BaseException:
        lease.release()
        raise

    def _run():
        try:
            class L(openscrub.Callbacks):
                def log(self, m):
                    job["log"].append(m)
                def cancelled(self):
                    return lease.operation.is_set()
            seed_kw = {}
            if selected is not None:
                decoded = _read_exact_source(selected, seed_pc['index'], fps=fps,
                    count=seed_count, tolerance_s=tolerance)
                seed = exact.StrictSeed(decoded.pixels, selected, decoded.index,
                    decoded.canonical_s, decoded.observed_s, fps, seed_count,
                    decoded.width, decoded.height, exact.POLICY, tolerance)
                with track_report_guard():
                    if (not _operation_valid(job, lease) or job.get('trackbg') is not st
                            or lease.operation.is_set()):
                        return
                    strict_document()
                seed_kw['strict_seed'] = seed
            det = None
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
            if selected is not None:
                # Model resolution can block after the decode's source check.
                with track_report_guard():
                    _exact_current_locked(job, selected)
                    strict_current()
            samples = openscrub.track_manual_region(
                lease.source, box, t_ref, t0, t1, cb=L(), person_det=det, **seed_kw)
            with track_report_guard():
                if (not _operation_valid(job, lease)
                        or job.get("trackbg") is not st or lease.operation.is_set()):
                    return
                if not samples:
                    st.update(state="done", added=0,
                              error="could not track that region — try a "
                                    "larger box or a frame where it's clearer")
                    return
                doc = strict_document() if selected is not None else _load_job_report(job)
                rs = doc["render_state"]
                result_fps = float(rs["fps"]) or 30.0
                step = 2.0 / result_fps
                tid = max([d.get("track", -1) for d in doc["detections"]
                           if isinstance(d.get("track", -1), int)] + [-1]) + 1
                new = []
                tcls = samples[0][4] if len(samples[0]) > 4 else None
                label = ("tracked %s" % openscrub.COCO_NAMES[tcls]
                         if tcls is not None
                         and 0 <= tcls < len(openscrub.COCO_NAMES)
                         else "tracked object")
                for s in samples:
                    t, b, score = s[0], s[1], s[2]
                    poly = s[3] if len(s) > 3 and s[3] else ()
                    fidx = (seed_pc['index'] if selected is not None and t == t_ref
                            else min(int(t * result_fps), len(rs["cum"]) - 1))
                    ox, oy = rs["cum"][fidx]
                    new.append({
                        "t_start": t, "t_end": t + step * 1.2,
                        "cbox": [int(b[0] - ox), int(b[1] - oy),
                                 int(b[2] - ox), int(b[3] - oy)],
                        "category": "manual", "text": label,
                        "confidence": round(float(score), 3),
                        "aoff": [ox, oy], "last_seen": t,
                        "dense": True, "track": tid, "enabled": True,
                        "poly": [[[float(x), float(y)] for x, y in c]
                                 for c in poly]})
                    if doc.get('plate_policy_evidence_version') == 1:
                        new[-1]['output_choice'] = 'blur'
                # grace pads: cover the sub-sample sliver at both ends
                new[0]["t_start"] = max(0.0, new[0]["t_start"] - 0.25)
                new[-1]["t_end"] += 0.25
                doc["detections"].extend(new)
                path = os.path.join(job["dir"], "report.json")
                if selected is not None:
                    _exact_current_locked(job, selected)
                    strict_current()
                _publish_job_report_locked(job, path, doc)
                _report_committed_locked(job, doc)
                job["log"].append(
                    "      tracked object: %d position(s), %.1f-%.1fs "
                    "(review card added)" % (len(new),
                                             new[0]["t_start"], new[-1]["t_end"]))
                st.update(state="done", added=len(new))
        except Exception as e:
            with files.report_lock:
                if _operation_valid(job, lease) and job.get("trackbg") is st:
                    st.update(state="done", added=0, error=str(e))

    try:
        _start_owned_thread(_run, lease)
    except BaseException:
        st.update(state="done", added=0, error="tracking could not start")
        raise
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
            out[kind] = True        # can't tell -> don't cry wolf
    try:
        rec = next((m for m in openscrub.load_model_registry("plate")
                    if m.get("recommended")), None)
        out["plate_autofetch"] = bool(
            rec and (rec.get("sha256") or "").strip()
            and str(rec.get("license", "")).lower().startswith(
                ("mit", "apache", "bsd")))
    except Exception:
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
            with open(path, encoding="utf-8") as file:
                existing = [line.strip() for line in file if line.strip()]
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
        with open(path, encoding="utf-8") as file:
            words = [line.strip() for line in file if line.strip()]
    return jsonify({"words": words, "path": path})


@app.route("/api/jobs/<jid>/render", methods=["POST"])
def job_render(jid):
    job = JOBS.get(jid) or abort(404)
    files = FILES.initialize(job)
    def refusal(prepared_work=0):
        _report_current(job)
        if _unfinished_checkpoint_locked(job):
            return jsonify({"error": "unfinished checkpoint cannot be rendered"}), 409
        if job["phase"] in ("rendering", "queued_render"):
            return jsonify({"ok": True, "note": "render already in progress"})
        if files.active is not None or files.work > prepared_work:
            return jsonify({"error": "job work is still cleaning up"}), 409
        if files.tracker is not None and not files.tracker.released:
            return jsonify({"error": "tracking already in progress"}), 409
        if job["phase"] not in ("review", "done", "error", "cancelled"):
            return jsonify({"error": f"cannot render from phase {job['phase']}"}), 400
    with files.report_lock:
        rejected = refusal()
        if rejected is not None:
            return rejected
        current, operation = job.get("video"), files.operation
    # Preparation can reserve/release sources under VAULT_LOCK. Revalidate its
    # operation/source snapshot at admission, after releasing that shared guard.
    prepared = _prepare_work(job, "render")
    ticket = None
    try:
        with files.report_lock:
            rejected = refusal(prepared_work=1)
            if rejected is not None:
                return rejected
            if job.get("video") != current or files.operation is not operation:
                return jsonify({"error": "job operation or source changed — retry render"}), 409
            ticket = _reserve_queue_locked(job, "render", prepared)
            job["error"] = None
    finally:
        if ticket is None:
            prepared.release()
    enqueue(job, "render", ticket)
    return jsonify({"ok": True})



@app.route("/api/jobs/<jid>/download")
def job_download(jid):
    job = JOBS.get(jid) or abort(404)
    with FILES.initialize(job).report_lock:
        _report_current(job)
        _recovery_gate(job)
        if _unfinished_checkpoint_locked(job):
            abort(409, "unfinished checkpoint has no completed output")
        if not job["output"]:
            abort(404)
        return _send_open_file(job["output"], as_attachment=True,
                               download_name=export_filenames(job)[0])


@app.route("/api/jobs/<jid>/report")
def job_report(jid):
    job = JOBS.get(jid) or abort(404)
    with FILES.initialize(job).report_lock:
        _report_current(job)
        _recovery_gate(job)
        return _send_open_file(os.path.join(job["dir"], "report.json"),
                         as_attachment=True,
                         download_name=export_filenames(job)[1])


# ----------------------------------------------------------------------------
# UI
# ----------------------------------------------------------------------------

# ----------------------------------------------------------------------------
# The app page. PAGE is COMPOSED at import time: zones_ui.ZONES_PAGE is the
# shell (dark Scan Setup editor at the top), and the pieces below fill its
# %%MARKER%% slots — jobs list + job detail/review under the editor, the
# settings view behind the header gear, the footer, and the app JS (jobs/
# review/settings) as a second <script>. All intake happens in the editor.
# ----------------------------------------------------------------------------

FAVICON_URI = "data:image/png;base64,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"

LOGO_URI = "data:image/png;base64,iVBORw0KGgoAAAANSUhEUgAAAIAAAACACAYAAADDPmHLAABgLUlEQVR4nO29dbxtR3n//56ZZVuOXnfJjZGQBAuS4FKkRYv1S3GK09LypaFBSwqFIkVKoUihUEqRAqUESlokJFiAhBC363Jctiwb+f0xa+2z7yWFGwhFft95ve49+5yzz9przTzzPJ/n88gI/n80hBCD1865n/nz/zd+S8bwAg8PpdRtev9v4/gtf9L68fyuHh8fl+MTq0aSZnvj5Op157Tb7Tv10/6ezuL8Zd3O0jWLC7Ozc7NzdvDXQvzWa4TfWgEYXrxVq1erDZu2n500x/48Lc2Di7xsamMwWgMQRxFhGBQjreTbUL7/8IHd/7Zvz5701q712zZ+6wRgeLGazSY7TzzlTnFz4q2dXn7/LO3jsARBYJWUWkglcc5a57DWRc45lFI042i3ID/v8IE9/zYzPaWPve5v0/itEYBjF+jEk0/d1B5d86pMu+fmRYESQgdBQJ715fLSouz3exhjCIKAZrPNyOiYDePYFnlmi6KIpFSMtJpfU6I8b/dN113W7XbdrX3Ob/r4LREAQW3nt23fMTK5dtOz+5l9Q57niRDYKI5t1u8FB/fvJpCOnTu2cuIJ2xkbG6Wz3OWmW/Zw0817yArN+o1baY2MWa0L7RBREiU0G8H7097iBddd/eN9g0/8LRGE32gBGF6EtWvXhWs2bn2oE/E70izf4awhiiKtdRkc2HszoTA8/amP55lPeyKnn3wC0egoyACcoVzucNV1N/PPn/w8H/7IJ1jspGzbeTJxo6nzPMMYG8RRZOOAly3MHnrvgf370uoGvOj9BgvCb6QADC98kiRs2b7r9LAx/s5+mt9f64IoCgulgmD68EHZW5rlkb/7YF59/h9z5l1OhSxDpzlaa3AOKQVBECKjCJKE3Tce4K/f9l4+9rFPIqM2GzZvx2J1kWWBkIpWI7kuDnn5of23XDg9NWWOvZ/ftPEbJQDDE62UYscJJ20Mk9GXFoaX5XmGkqIIwzhYnJ+Vs1MHOPded+Y1r/q/POgh9wGdky/MUXam0L0FnHUgBAiBDALC9mqC5hqiZhsabb7/3St43evfxIX/+TXGV61nzboN1littbZREAQ04/BCU/b+Ys/NN/yo1+v9xP39pozfDAGoiZlqcrds3d5evX7zcwoj39br9gBrgzCy/V43OLTvFk7YvoHzz3sRz/jDx0EcY5a65J15yuVD/hpBAlKB88jBWYPVfYJAkYxvRjVWE7SbAHzmM1/kdRe8hauuuZmNW09gZHzCFnmqtTZRHMUkofzbtL/4Nzddf+2hldv9zRGEX3sBGJ7M1WvWBus3b384svEPnW53nXOGOE600WVwYO8ttBuK5z/3abzsJc9gfN0qzFKHot+hXJ7C6YKgMYqQAdZqnKv5Hq8FhAjQusRkC4RRRDy+GRWPE4w0yLop7/nAv/DWt72Hmfkum7fvIowineUpWIJms2ED5V40P33gHw8dOJDd2r3/uo5fWwEYnryR0VGxbsOWk+PWxDvTrHiwLgvCMNSAnDq8X2a9JZ74+Efy2le9jF0n74LeImlnEd2ZxuQ9wqSNiho4a3D1rq+3vwBRexFC4lDoIkWns0SNNvHEduLGGLTbHDkwxRv/5l184IMfRQRNNmzeBlLossgDKQKSKLjSmuyl87OHL56Z+s3gD37tBGB4wqSUbNm2Y3V7cv1r89y8MMtSgkDpMAjk/OyMnJs+yH3OPZvXvPJPecCD7wu6IF9axPRmMb15ZBCh4hYgqh0vcNViO/BrXpkXUcmAw4KQWCcp00XQyyRj6wnbmwgaLUia/OC7P+DVr3szX77oG0ys3sjqdRus1qU2xkSBDGg0wkvy/tJzpw7tv3ZpaenXmj/4tRGAYydo46Ytjck1m56tnXxLmmaREM6GYWS7naXgyIG9nHziVs5/xZ/wlCc9GgJJsbiA7s1hevOoIEIl7cpFs37RRb34x3wuolYE4Fz1fuuxggyx1lH255DkJONbUMlqglYDpOKzn/8vXvf6v+HKq65n07ZdtEfHbFFk1mgTRGFEu518qLM484pbbrx+2lp7q8/5qx6/FgJwLG+/ftP2hzrZeFev39/hnCGOYq3LIjiw92Ymxxr8yUuew4ue+xTak+PopQ5FfxG9dBicI2yOo8IIcB4zClFRREMh38F3ouKQqgWpBADnah3hhwwpi5yyN0MURyTjW1HxOGpsjLyb8e73fZi3vOWdzC+lbN5+AkEY6iLPpTVWJkmSNRrq1XNTB999YN/eQXwBIVY+91c4fqUCMLzwo6OjYtO2XXd3MrkgzfIHWqMJo0gLkEcO7ZNl2uEPn/L7vPov/pitOzdhFhfJeh1sdwZbpgSNUVTUBBxCSmpwB3D0NIuhz2fgCQA4a6sfuMHbnKMSCLBOUGZdXL5IMjJBNLqZMBmB1igH9uzl9W94O//0sU+i4jbrN24FgS6KPBBO0G63dludPmt26sDFszMzvzb8wa9EAI598K3bd61vja95fZbrZxd5RhAoHQShXJiblQuzh3jA/e7Ja1/1p5x733tA1iddWsJ0ZzD9BWTU9OpeCISQIKS364OYfmX/K9Zu+OeDTehqTFDtfLeiIwY/dxZnTXU9gS56YDPi9irC5hrCZgsaTb59yWX85V+9ja9c9A0mVm9g1dr1VhttjS4DpUJajfi/097CCw7t33NDv9+/1fn43xz/qwLgHxTqPbdpy9bWyMT65+SFe31Z5m0h0GEU0+ssBVMH93LaKTt59atexhMe93AQlnxxEd2dqwBeiEra1AssZOB3vpQVql/5nOFvvQcgwNkVT4AVr0AAQsqBsDjrsM7Dx5W/cQipsE6gsw7C5USt1YTNVQSjoyACPvWZL/G6v3wT11x3Exu3nODxQVlYa0wQhiHNOHrP8tLUq/fcfNPc0fPzvysI/2sCMPxwa9auC9Zu3PawUou39LPsJJwljCKtizI4tH83q8ab/PGLn80fv+DptCZGKBeXKLvzlMtHEEDYnkDIoFLVAhA4IQY7X9S2HaixgDUGqQRJHEEcQeCFxfuF1XWMhaLE5AVFaUAoRKVRnHM4ZyoLYYcmTmKMpuzNIRXE41uImpPI0VH6S33e8Xcf5G1v/zsWOxmbt+8iimNdFoV0DhlH4XIcqlfOTe9//8ED+7Ohyfpfwwe/dAE4yp8fGREbt55whlPJm7OseIguC8IoLIQjOHJon7Rln2c89Qmcf96L2bJzG3Z5mbQzj1k+DKYgaI0jg9hfT8hK5R+dzyelHHxvnUMIQdJqQCOGfsqePfv5/uVXc+U1N3Hw4DTL3T5hGLJuzSS7dm7jrDNO4czTTqK9YQ2UBeVSB2MtQkpPH7sVF3KAFwCEosx66GyJsDlKPL6ZKGlBc4S9N+/l9W94Gx/7+KcIkxE2bNkOQuiyKAIcxHF0TaT0yw/t3/uludkZe+y8/VLX55d24aEHEEKwY9cpG+PW+Hn9tHhxkeeEoSqCIArmZo7IpfkjPOgB5/LaV/4J59z3bOilpJ1l9PIUJl0kbI6h4hYOi3PVLpe1AKw8hnAO6xzGaJSUNMZHwRku/fYP+dd/u4ivXnwZR2YWaDYbbNqwjo0b17NqYhwpBMvdHgcOHWH//oMAnHH6yTzlCQ/jsQ+/NypUpMt9ZBBUZqRGiPXTrgBH5yRFfwlbdknG1hK21hE02xC3+Pall/Hq176R//7aN1m1dhOr1q63ZVlqrctIiYAkCb/gdPrKPTdff2WWZT8xj7+UdbrdL3jMDW/eur3Vnlj3jLJ07+j1ulIpqaMoptftBNOH9nLWGafwyvP/jMc9+sGAIV9cQndn0Z0ZhAr9rpfKI3RR+/MMVHPN4Fnr3bdGEiPaTYrFJf7l3y7knf/wrxycWuTsu57F7zzoPpxz9zPYvHacQDqMNjhjwBlUoIiSJoUT/PDyq/nif17Mf1x0CUoKPvye13H3e92J3vQ8QRz7aXNDYeDB19qFlFij0dkSUjqi0XWoZBXB2BhYyb9+8t/5ywvezDXX+fhCq+IPrLZBEIQ0YvXWIu+85abrrjnyP83r7bZet+vFhm5y3foNwaq1mx5sCD/Y6XQ3gCWKIl3keXB4/27Wrh7l5S97IS987tOJRxqYpUWK3iK6M4VwFtUY8wEbnN/pFWFTs7bOOaw1CCCOI0/OqJDdtxzgo//6RT7y8c9TlIbnPuP3efqTH8mmdatIu10OHzzA9PQRup0u2missVhrcNYghWPbjhM49Yw7EcQxxgW88oJ38aa3/j2XXfIZ7nKvO2GOHKLQFqXCFSuA1z4rCsG7kw6J0RpbLKMCSdheT5iMI0ZH6S92eOfff5i3vs3jg03bdqHCUBd5hrM2iOM4a8TqjzuLM/+8b8/uOtx4u2OD20UAjvXn12/adpqK2+9f7vTu4f35WEsh5NSh/dIUXZ76lMfz6r/4E7bs3IztdCh6y+ilQzidE7YmEEG8EqwRsmLyVj5Pa0MjiQlGWqALjhyc4r+++X0+8dmL+Oa3f8Cq8TZPfvSD+JMXPp01Gzew7/rrWJybJy8K+r0epS69TR/wwZ4RzPOUiVVruMOZd8UYSxgoRtav5eUvez1/+56P8eY3nsfz/vARJCMJxfyyTygRaiW0DEML5Cq3sdIIZYHJFwniJmF7A2FjBNoj7L1pN6/7q7fzsY9/hrAxxrqNW3DOev4ASbvd2q2Efs7s1IFvTB85crvHF34hATj2RnbuOnldo73qTUud3tOKIiMMQx2GsVxenJfzUwe4333vwRv+6nzuec7Z3p9fXsQsH8ami6i4RdAcHdzSyqKLwZxaa5BK0pgYZ/+eQ3zuSxfz7xd+lR//+FpM3ufUneu4793uwOknbaNM+wRRxDkPfTSjq9bSXZxncW6axYU5+r3eCn4QAqMLANZv3s7Ok07zDoHRCCDvd5kYa/D5L32D17/5AyylJX/+0mfyvGc/nrLTxTqBQFbaoKJ7Ed5dtBawR8UhdNbFll3ikVUEzbUEzRYkEd/46nd49Wv/hosv+R4TazcxsXqtNbrQujRR6Gnl/y7S5RftvfmG6/I8v9X5/7nW8Of+w6EP37h5SzI+ueFpaWnf2ev1IiWFjaLYpv1eMH1wL9u3reeVr3gJz3rq4yEMyJe6PlK3fAQZNwkaYwNKVsh6xw8TOQ6tS6JAUmjNq9/8AT7xmQtZM6I4YdMqTtu1hQ2rx1FS0en26acZKlAYXXL3c87l3g95GFobyjxnbvoIiwtzZFmKKQuss4xNrmb7rjswMbmaosgwRlfPZimzjJnDBzjlzDvSW+rxiU//B6+44D085CH342Mf+mvypV41F/YoAmmFYnTVazuIS1jjKLNFlDDEI2uR0bjnDwx8/NMX8ldvfDvXXL+bDVt20GyP2KLIrS7LIIlikiS4IOsvvWP3jdfPrizhzy8Ev5AGGBsfF+s373ygtvIfut3eDoA4jrW1Jjh8YA+tRPHiFz6DP3vxM5lYO0G51KHozGOWpxACwpHVCBVWqhKomLwVZO9vzzqLChSLi8s87AkvZm7mEM963P25y+k7GRkZY2RiNXGjjQojwigkCKPqDq1P8262EFKhwoggTLDGUpYFWdrHOceqNesQwlLkORUxiLUWKUGXJT+67LucdMqpTK7dQG9hjqt+fBmPefZf8oo/ez7/98+fS29mnjAIqhjDMP08JATOC4F1tiKUVvBBEAjC1gbC5iRidJz+4jLv/PsP87a3v4eFTsaGLdtRQaDLPJfOOtlqtftBYJ89dXD3J+dnZ80vsoY/twBs3XHCRNycfFOn23+O0QVhFGullJydPiLz3iK//7hH8LpX/RmnnH4S9JZJl5fQy4exRY+wvQoZNRgE52tkX0ftqjBtFUfFOUeQNLjfI57J9IGbefJDz2ZqagGLJIoC1q6Z5IQTtjM+PkaUJMRRTKPVRuBIGgmtVovVGzYRRjFal0gZgBBIqTyuMsar7OqznXOoMMRZx43XXMPUwX2MjI5y6h1PIwhjLv7PL/Ldyy/nA5/9Ptd869O0GzHGVUTUcNDpKC/B+e8HASdbORMKU+bYfIkwqfHBGLRG2HPjTbz+DX/LP3/iswRxmzUbNmGdLYosj4SQNJLwc/3l2WceOXRg4eddR/mz37Iy6tj5rlNO3xW1V1+7sLj0HLC60WzarN8N9t90tTzj1K186Qsf4V//5d2ccuIW8pkpuod3U8zeglAB8eTmlcVHeqRf7Xw3NIGeeXMUeU5ztMXfvvsjfPe73+fh55zGTbsPooE1q8dpt2KiOGRqeoZDh48wPzfL/PwcM1OHmZ6eZt++/Vx7zXVc8b3L6CwvkyQJzhmcs5RFitHFgB6u5VEqxcLMND/67reZOXyAIAxYWlxg3+7dBNKi4gZBkRNR8OWvfpdgfBw7BP6O3lW1OROD1x5/KEAisARRRNhehzaSdPYmsvlbKGcPsX3Lej74j3/LRRf+C3c54wT2XPdjOgvzUZwkVkiKflo8Omquvnbjlu27fukCUNv87btO2a5d+N2F2bl1YRgUSspg/+4bZaIK3v2uN3DpVz/NQx58Dvn8At1Du+kfvBqT94jG1xMkIyt2smbxqskRFbPnal+/3vlK0J1f4D0f+gRn7FrHkakFlnopSRJjrWHjxg2cespJTE5O0k8zer1+xecLVBAQhBFBFLHc7fDdi7/O/t03oZSq4gceb1g8a2id83yDg0N7dzM/O4WxmjztUZYFiwtLHDp4mPXr17K4nLJ+rMGX/vtbICXWmKPjCoPF55jnrQJWUiKkQgifmyicJoybqOZa8rRHOns92cweypkp7n2vs/j6hR/lg+/7a0Ybjr03XC2lEFEUB4Wxep2MRr67YfO2n0sIjksA6sVfvW5Dw7ros91OdzJKYm11GR3cfS1Pe8pj+MH3vsILX/R0KHP6Rw6ST9+I7kwTja4mHlvtn51q14uhCRkGfEIctXusczRHR7nksqvYu+8ga8ZHODy3jLYCiaTUls1btxI3m0xOTrDrxBO489lnc+oZZ7J563a/y/OMIs+RQiDDmOuuuopep+PJpYFp9trGcwKOsizZftJpbN62g5H2CJu37WDHrpNI+z0WFpYQQrB5xw7GWiHf+d4PyWfmCAMF2MqrHGQbIBiKUdQYR8qjBGJFIzikMISNMUQ0Qd6dI1u4if7UXnS/zzOf+US+/60v8YLnPpWDu6+jzPJIBYE21kwGych3123YvKZer+MdwXGsPs45Gq2WGJlc91fd5fSsKI4Ko3U0deBG3vSG1/DyV7wU0kWyI4coFvbjyj5Bc5yoPemv4ax/wCFkfzT8OPaG64ILEI0mn/vSNxlrBCglKIxl64RXuf20oNftkzQSHI7RsTF2nnQqeZ4ihWRyzTp6nWWElCTNNnHSIAhCglBhK9/dg74KqdeA2lmiOOTE084YhICpiKcizzkyPcv2bZvYvGEtX7vyci6/6gbucc87k3a7BIMtVXEDYuXSg0ISBIiaPnY4JxGu9hS8WVCBQKlJjCkp03lssYzWBavb4/zd37+Fs848jT96/kvZsO3kQIWRLotysj257gtFkd1nYW62OF4X8WdqgHppVq3bfHKW2peqQGkhVTS1/3pe8fKX8PJX/BlmaZrOkb30DlyJcIZodC0qTKoHlEP/KlXPyo73P+MnkjOsc4Shojszy0Vfu5Rt68cwxjA+0qTVjBECms2Ebrc3mOzlpUV6vS4gMNaStJqs27yFdZu2MDYxQdyICUIf4fNxHYF1lfq3DmMsxlosAuscRZlTak2pC4oyZ+OWbSRJA2sNiwuLnHLiVpzW/Md/XQLNRmXd5IBYGjxrxTeIo55XHKUBhPAmQaqgCm0rhHAEQUDYWI0TMenCHjrzB8lnDvGc5z2dv3nj6zi893oEIpCB0lla3H1kYvW9GQj1zx4/QwC8FLVGRkQQjb5a68KGYcjMob2cfbc78Ya/+gtMd47e3CGKmZtojK0laIxWV5agghWbN6zupUDKoQcfes9w+LXRavHNb/2A3bv3sW7VmN+9SiKloJEk7DphG2mWYozP9u33Uo7s30cYBoBfVK01RVGQ5TlFXmCNQQhHqASNOGSkmTA+0mRyfIRVkyOsmhhhcqLNxEiD0UZEM5Yo4ZG7BcZWrWXtho1EcUKr1WTrulE+/fmLsN0eoVIgfARSSFXZeYmUCjl4vipcPYR7BmZBKp/PIGUlBEGVm2BQQUTYmCRbPETemaKYn+Fl5/0xD7j//Tiy/xbCMMIYbZVqvHF0fCLw++tnm4KfagJq6rk9tmpVWZZPFAJpjKZIl3jt+X8KQUS2fIhyYS/NVVuqmxeeIpVq4NbVYGhFCGS1Q1jh0sHH9J0HUQ4DScx/fv17JAFIqSiNZ9qKvKC5epJ169Zw6NARSm2I4xghJfv27WN81SoarTbYgihOSJoJSRIjJBRpRlaU9FNNNzcsF5Z+t09vuUs/7RNgSNOUQMLYaJuRVsyWDZO026PE7RaMjxEpR5Gl7L7pBk45cTsXfvNKLrn0+9znvmeTdXoEQTgUpFx5fuecx0HDnP5QTsPwxgMLUgyin2CQEppja8mWDiPCJtH4JK971cu4zwN/j7LIAyGE1cbebXRscufy4sINP3P1f5YA1GokjJJdZZFLFSi9vLQY7Ny5kwfc71xsv0+xeJC4NeYXX3jJ9fa+Vi616mMQ1Bk8Y7XYQsijAyrCLzjWsu/gFO0kRFsfCo5CSVYUlKVGSEl7dIQsK4jiht911rAwdYjNZ5xBL9dMLyxz+LrdXHHVjVz2gys5cOgIs7OLHJmepaUck2VKtHac0fERlhYW+f6NM5xx2ils2bqFfpqS5QWzM7NsXr+KXSfv5E5nnsZZp+xg9erVNELBfQ9N883LruZtf/9x7vPgeyNcb7DLh2MYw7DQQwAPPL3Qr3gN/vkdWACLQK7IhsTjk+Y4ZecwurOae559OqeeejJ7Ds4zuWaN1roMWs32OcANx2MGfjYIBMIwuUtRZCglba/T4W4PPJt4bBX96YOgU1R7zAupCqoInjhK5Q8AUJ2949+BEzXcEyuxFBzCrbhPxliU9K+TKCCOAgKlWFhapp+mqDDAWkMjUoyMTtApHD+4aYoPf/nDXPmjq1nYv4+r9hxi08Z1PP8ZT+BRD78fO7du5LwL/o7Zb13Cg9ZInv7wtZx+3iug+2Pudr838aKXvoCnPesPKecPETYi3vH3/8Lf/tmriX9wGd/5KGTtJut2ncBd7nIaO1c1uO+dd3Hhf36d6350HSefegI6zVFSVNBkxcrWu98/u6twoMOJY7SBpQKo0guBFOAkWA9WVZigi5S8v0RrwxbuetZpXHP9l1izfr0sSy2FlGdIWYXIf1EBkFLihDzJL5qUTpds27oZUJgyQ0pv75CqAi5yEK+vV/XYJE1RUwGs/MwNEal+QlZYM6m82UjiCCn9/Cx1eszPznPCzs30CsPVu6e4+Iff5JYrr2Lx8EHuGhvu14I7jUjeEEjOfsxDOf+Cl6OnD/vWMM5yMHN8Ycpw4buu5Bk3v5xDNuCaQ4Y3vPldXP7DHxAqyY6t67nm+n20I3jIppAoAGFTfnzLj7nkRz/mE3HC5s3rELbkfR/+NG9/1+uwvRSlgno/15JdPenQ11oz1rkFQgzsoatIIj831Wsh/YWkQwqJLXMgYPu2LWDyav4ERVbon7nyxysAAKaswmXgky7ixN+ItSuLL9SKqh9oAED6aNlR87BiIIe+Do/KRari/QiJk4JAKYLAa4U1E6MYZ/jn/7iYq284yNU37uOcqOTuozC5TvHI9Q0C6+hnJbPa8OOrbuBFz3opew5MsdjN6KUl93nsI1kz1qLRajAvHeNxwtvuP0kYKHpZyWIn5YprbuGaa29EbN7Ax6YPM5nBmS3YMCq4/1gD40ree/0+tJN85nNf5oJX/wnNOBnEN7w7e7Qq9lgAT4lUVHg9t4DXjAOK3C++c1UW8xCb6NPYBUEQMCxh2rrjJgKOSwDADl1wKOJ1VGpWbd+HFl9QqfOVv6n94Po9K0kU9fsYuNC2tMzOL9JuxCgpETjGGjEuDLnu8AKfv+Qq7n2PO/GyZz2KC/7uE+wqZ7jrmKPf0fz79Sk3FnBLHNE8/SS2rV/L+k1beOD9782mNRNMtBvoIsU5Q6OR0Gi3ieIEFYQ0W23CVnvgpul+j4NHprn25n388Mrrufx7P+TgFT/k5r0L3HUEThlR7Akm2H/wCP/11W/xyMf/LmZhAaWGNODQAgsxZPIqQCjqKThqisXKNwPcWC/0CsayttaYRy/P8YzjEwA7iG0BVImXtVofAnb1qAmQIRA0/LthHsDvkOGr+++jKGRmdo4bb9rNxvEYXWqMDbji5sPsPjjLqO6xdcc2/vgZv8vszCJ3PnUzH/riIb4zD43N2zn53Ltw7j3P5uV3OoXTdmyi1YhAKXQ/JU0zjJBIFSJlHcpdWah+aTCz84MQr5KS1eOjPOgeZ/GQe96Z7FlP5OaD03ztksv4ty9cxPXfvIS+9tHZ//r6t3jUk34PU+YEqtKUR2k8KhXvH3Ql6FWZghokUmuKFfPod8VQfcOx3sOxzsRxjOMSAMvQc1BrLDlYLOccotq9K/ew4u8O7u6n3Vwt7NX1gjBm34FDLCwscsqmzZSl5qs/vIUiy3j06atZ6AUc1AEf+/RXuOzqPSSNFn/0zCdwlzufzpmn7OS0k0+k2UhI+ymd5WVmpnOKosBYi9GaMs/JsxSrC6IwIEoSGo0GjaRB3GwSxg3qXEPrHIU2aCuwtkQXGZsnmvzBQ8/msQ+8MzdPvYh//cyX+OCHP8GFX/kmb15YpjExgl7uEETJ4BFdDQCHBP7WkPrKvq8Xv77A0C+H319jrcF7jo8EguM2AUM7utbPiAFoFdRqTQzU5sodDY2BmycGN3uUbqkzawHihIOH55HOoLXhBzccoJnEPPLMDaxtSS6+eZHZ8jC7dm7hKY9/GKfu2EQrDkizjPkDe/jqnlsqhs9SFAV5llGWBWEQMDoywtjYGEmrQZI0UEGAtrDc7dPtZ4SdDiPtNiMjLZIkIggStLUUpfa3qEIKU2JFRJZ2WRum/OWfPY1nPPFhPP0F53PW3R/F5z/zXk6540709AwqTDxAHooRHbWIw0Iw+N2QSaznf/h3gzeLQSq8O+oixzeOUwCOHkcxTEJ4FqtWUceyTwOJPLo692ijMvzaDbj5fpqhpOS6fXNEcZNVo00WF5f46rUpG7Zv5RVPfDC7tm1iaanL3lt24yrPwxhDUeQ454ijkEbSYGSkSdJYTRAnCBmQo+ilknw5JSu0j+ZZByrwGb1lThIHTIw2Wbd2FasmJxgbaRFHIcZYMuPAGcZWraUsJ9m/Zy+xK/nXv/u/nPeGf+Csu/0uH/3QW3j8HzwGFmcwukQFPlFFOG/vVzKGOGY2BvaAWg/U8+tNxFAgbRhzUUcib3cBqC9aawCGvr8VfFipBle/1Xmf/9Yv7VYmo3pu4SxOF2BLUm2RRjAy0mR6fomlruSxj3wgv3PP0+j2Cm64+SBRHKGUqrJ7ve/bbjeJ44QgirEyJLOKhY5h+dACy92M5U6PpeUOi0vLLC4u0en2SPs98rwAAY0kZmJinFWrJtmwdg0bN6xm47pJNq4dZ9P6SSbHx5AqxBhNIwnZduIu5mfnObx3N6980ZO44ynf4f887Y/52sXf4x1vey1hItDzC6ggqmbNDYl8PcTgJz+h/iuU6DHDCjD0v6vWYQVRH9+y8vNqgKMW3R2lukW1oCtuzND7htHwcLTqVu5XCMGO7ZsBH6yZmZvnxC2TPOPR9+GE7Zs5fHgRoSTNZuJpdGnQAoQMUFJRWMFyt6CT5iwsZUzNzLN//0EOHp5iZmaOTreLHvJu/aiRdQ2n/VAqZGx0hM0b13HCji2cvGsrd73jidz5jF2MjbaYOzLDxOQEa1aNMNI6hanpWZ76+N/lAfc5hxf/xTs4+bT7848fehv3vf89YeEIxoAMwqHPOGYTwWDxa69pBXTXr1l5fdRf3LbxcwnAyhiyRQ6GkyK9EAwhx2PV0lHSOvBxMMagQoVxARe87R+RApR03O/O2zj3zF0cnO1w3YEraSQxDkdRlqRZijWWO+zcjJCKw3PL7J/qcODIHIePzDE3N0+py+rzJGEY+T5ASWOIlj96+uTAxfVeQlYUXHn19Vx59bUANEbGOPnEbZx+6jYiSk7dsYWHP/R+jLUTdm3fQBAlnHii5rKLPsCr3vQBHvSQJ/OSFz+Tv3nDS1G2QHczVBj/xLz8zGX8n+azeoTbmiR8XAJwDI1zFL35kw+w8tNh0HoUNKg1w0AHukGhh7Ga1ug4f/DMl3Phl/+bO5+4nm0bV7F942o+9bWrkHnKqjik1NpX9lhfJ0Cp+c73rme2V9Dt9ql8F0Aig5Aoblaf621raSyYo2drpV1MxeSLOs3bJ4luaDfY1I4xDsqyoHv99VxyzbW02g0+2814zVs/xs6tmzhx11budbc7csZpO9m+cYzXvOSx3P2Om3nx+X/Hl770VT776fdw8mk70dPzyDAazNKKINbqvM5XsEcrpcFmO/r+fx4dcHwaQA6jznoxa0JCDBb0aFEQDL3rqN8Owx5XPYw1Gm0N7bFRnv5H5/Mvn/wc9z5rG2PtBqvGR7hlqgOLi3z7rqtplA7hEnA+FavMCuKizwNv7jBbOjaNRLiKkq4TMX1gZUWtHuuV1nNqXd0MYgWjBQIWreW5Y01esyFgQYVEso2QoI0lkYavL0p+59oOV11/C1ddfxOf/eJXAcGmDeu446nb+N2H3J3/+o8P8673f5Iz7/IIPvZP7+D3n/AQ9NQcIgiHFvzYnMIVuOxqgDxILHUrczi8XD9tLY8ZxyUANa47ehzrjK78Ez/hDYifkNVhE+Cc84u/bh0vfvFr+cjH/4373XkbrSSmESdeHYeSCQdyzzQLRUlaKqyxg1B6KGF0pMk9JtvILKebl+hqFf1urirCh2LQfqEdxoFxrkoOqYSgzhEEIiGglARC0O3mLBcp0kJhfT+hVZS0jM9TCFSIUj7r2FrHoZklDh7+IV/+6uVs2PBZXvK8J/Oav3ghj3/i8/h4+jc8+cm/SzG3jApCVsznEMpyx8yZWxGEOoo4vPNdnWx7nOO4MYDnoYeXcYh8OOq7YzyD+vVRILC67WpzFmXByPr1vP4v38W73/dP3O+uO1kzErNmcpz2aIusFOy++WaCwhLHEQeRPG7WkEQBoZBEgc+mYbTBqiSka71JqDn3gessjxZMn/8P2kHpBsG2SgPXrpijRLA6EvxrXvLF3E+ys46pwvLwdsi7V8fQcShX+o+REguoQNEMw6plDcwtLPKK17yZpzzpkbzmFc/n/zzj5dzvnLuxfvUkutDV+4bm2B37eiABDOOmn1ir26ACblNa+E9+0q34/T91DEuq/77Ic0Y2rONDH/gkr77gbdzvzidw2tZJ1k2OMr2UcuGlN/DBz1zKj368j0gJlPS+cC9StFe3SVa3iFaP0FjTZrwRUhRmEFmTUqKUQClJICVSSJQUREoRB4okUCShIgkkkRJEShAHkkhJAiWqLJ667AuMgF4oKBNJHgt6EZSBQDQj4kgQSkGuLZmxSIHvQGoMutToUiOVYGR0go994t/RRcYpu7bw7vd9AjG+ymsrP6nH5cX7aa9Lz2rX4ZeFAVY+llvz2W519w+ex1u1QSn30CiKgpHVE3z9om/xrBe8gofcdQcbJiMuvXI/Nx7q0OuXIBytKPBhYGNAa4pSExBQ1/9I6zNtyqoOzxj/vRSghPD/JITSC4CSwi9Qpfa1sQR6xe4bC6UFjUNYBmnjEkjqPD8HTSkIhQCjKYzFOsMpIwEplr1LGUkSUncZqV046xxxY5R/+4+LOfPUzXznsh+B1kM07tDkDTy8nxQJ5wYQEY5LZG593CYBOBbkCRgEM4b78qzQGOKY+xODmzfGkLTb7NlzmEf8/vN5xF3XIwLBv3z9ForSVgyeQltHzziENQinPI+vDc4pSmsBiXQW6Zy375VdCYTA4lBSECpJHEjiQBFIgRIMBMBYMNXuM5Xm0MYiql1sBGjjzZWUEqTAVEKBEBjrKNKShUITKcFdxgPO3rGaby86PnHFQVqtRrV+osJHkjBSLC5nlP1lsrwBeVbhJsfR8ZP/aUfXpsCD22H3m0pQj3f8AiZgRf0PWq0O+fTDHstPjipxMgh51JNewl12NRGNUf7jO0eI4iYjIy2EFKRZQUs4zhiROBwBDiUMa6UlrCa/1Iai1ORFSV6UaK2RAgIlUYLBv0B6FZ8EklYU0I5DRpKIkSSkFQckgSQJFI3Am4dISUIpCKRASoGSkkD6YI4Zmn/lLJExtHAsl5YvHco47+v7uPPOFidtnCA3AlWVoAE4aykKTagsc3NzrFk9CaGs1Hg1p35nsaJR3bHTd/R8//wK4Bclgur7cQO1OBz7p/r5cOYPOMpS01q/mtee/1bmDl3LKXc9lU/+542MjDUx1iLxu+zeq0KeesfN3GVdg5d/9Sa+N1fwjKmA3Elk6CdTm6PvJAkVURgQSIGREEhv3xthQCNURKEkCQKkVwF+B2tLaSzaugE1YCvz4JwllN6+B8onYhhrKBG0pOPS1PLsFPYWgh1NwUPWNbjoYMpVUz3OPX0jN3x1DzIRGOMGfQiLXLNmdISb909z/tPOqRJoh9fxVlZUiBVTMNjsw6Dwp/ztTxm3QQDErXwVx3z4sft9SKKr31oLcaPBwZv28Xfv/ycecKcdfParN5M0Q3+IA4ISR1sJ1oWOL167n68dGuVBu1YzVU7zyRROnoxpI8lLN7Dbvg0DEPrdLoXAGL/7IyVpxQGtOPQ4QInKHfQiGiiDtpa8NBTG4pQHfkoISinQRhBHIVEY4BzM9zK0NUQOikByoQkoneFpGxMaUchYUjKzqLnDpvbQXqj8eyFIkghVdAjba3ni4x+KXe4MnWF4rE0/mkmpmYyV13bwN8dY2uMax8cEHnvBo3L9jr7RQaTrf7gXYw3JxCo+/I5/ZF3bsH+6pNSOMBZY64GNdRaBZefaCULpuHb/LNcULc5d32D5cMaaQLKsKx9fDESRKFS04pBWEiOc9QmlwhEpSRwExEEwsP9BpQXqBg9J6NOrlLSEytKo+IDSGEpjaTZbxGFIabyQgM8taAaCcSfpWktqYHOkOG00ZLd1KAHoEgj8PUpBtxDcbVvENTdN8+73ns/4hrXkR2ZQQVgpUFf73Cuavnq+QRLtrSWDDC/PbZCAXzgcXDN5NXlxtDOzcpM1vyUEUJZ8/Zvf5YTNq/j29R2iRFU0gRjslBLBvXZtYrQR8/1DHaI854cLDiUDnBREVa1AfU0lJUkY0E5i2knkVY1zBNIDwiQKUdKDU6UkYaB8BNF51B8q3yFcCFB2BV+HVlEaRyuOieOIUhtWWUeoJGmp/R/jOLyUc9lcHxmGnNSQNDevoV9YcCnWhCAEvVJw1uaEfXuP8PDHPIKnPfvJ6Ll5gjCqOJajkVOdJu+npZrLauF9ZvExWvh/lon/cfwC0cD6ZmoftL6BobtYAaYVNvSlTt3ZRQ4fOsBJaxSL3ZwoVAPVhhAo68iNoW8V4XLOo05Yx+d2T3Own7FuLAIhiMOA0UZEpBRhoEiikGYSE/pz/xDOVxbjDGVZeK/AWqy1KKkIgoAgCHBIjAWtVRV4MoO6QVmVrmsHUdIgiXxJWiP2wiR7GVprnLUYYCa3GKsxSvGgU7bx99+8BoCsKHEo7rghZnbqCHe457l85MNvx3Z6Q/mC/j9HlTX9U2H0UEiYuhX+UVN+3OMXA4EDiq3+dLHydaAlVgTEWksYhCx0upRZhhJNtINYDgMcQRhIlpYKFmTICeNNLtl7hItnMrY3JIUF4wShVLTjmFYSMZJEjLdbjLWb3s9XavC5WmuyLEXgKIoSbQxCSuI4RqkAV9UJlmXhi3aF8O4ggjAMCFRI4SCIY5pJAyklYRiS5gVpViCdwklHYRytULE2sISTa9nUEFy5ewpkxEgkGFU5e/Z1efgTHstHP/g3KGOwZQlCDhawdgKriaDeVc4dy8JCnSYCrkoKZYAxbss4/v4AQ4t59K0cQ1oc85v61uoghtElceDQTtBQPjQrlTrKrgmhIAi4fLrPmafuYF+3YG0IcehvNwqUZ+wCRagUYRgShoFX7aEiCiRJHBJHvpYwCgOUClCBIghDwjAkimIazRbNZpM4jqpYgTcjcaBIwoBGFJLEIY3I44pWo0ESezDoU9QljTigHUcEgeR+a2Ju7pSccOIWDncyFrop28YFMu2TBS0uePsF/MtH34LMepg8AyFuffEHi1ibour/IabvWHH4yVfHN44vKfRYLeSGBMGtYNBjcz7qOxokNwhBWWrWbFjD6vWb6HX2c+rGFlce6DPWkJTGC4mtmkLuXuhxzcF57r1rCzctdpnKShrtmHYS0oi9Dx+FAY04JI4CwsC7gFEYEAQeV0gBOEtRlAghkdIRRhHNVpMo9hXMzhi6gRpkYSnjm1VFUYxQikgqWiNt4iTBOQ/uklAR1GBYSlbFiv2zPXbc4QR+58ydnP/ly7HGsNCHRz3pcbzmFS/mhFN3oGfmB2V0zh6juo/KmK7mrd5FA7bXwaBzOVB3KDsGcx3vOG4NMOyMDMvDoMihFgrnjrrnlbC1T7CQKkQkTZ7+B4/mwh9O8XunNViVaBa7JbLqnaONJpSOHx+c5tBywfrxEV50j1MJwwghBKMNr/ZHmzEjzZjRZkIrib2rFgVEYUigAqSQVSMIUbF93jxEYUiSJMSR/9ps+L9P4pAwUJ4jqOIAgfL4ot2IGWkltJsxY+0mY82ERqiQ+LLyZrPB8x99b/7wHqeRK8k3rt7D3c8+i4u++ln+6cNv5YQt6yim5xCVtrPOc/jD/+owr29Nf+yOH3qvtYOikKpgsFqaWyGNbi8BOEYMGUZ4jpUQqhfQlQeqVYSoLiGlJJud5VlP+T3OvNudeO+Xb+DJZ8XcZV1Br9+nl5aeJlYwvbjEVTMdzjl1ByduWsdzz9qCkIIkUERKMZIktJOERhx5ex2oqgFEJQBVnaLFh3apvIUoioijmCT2QuCZQ0UUBIRKVVolIkkiGklMs5F4UxDHNJOEkXaTydEWk+0Gk62EKJCMYFiammcOyLtdrjk4z2v//Pmcfc+z6U/NUGbFwNXz8yGGKRI/lbZe3JWF9mnpK8LiF7rqqWQtYAba9uchBG8jFTyMBHy6lMWr7DqZos6jd9VX33LHVQ9hcVZjyhKrS7748bdyzgMfwN9/bZrJMOeJZwbcdZNPsOiXAoIG7/v+9RQyYM34BEdMVE0OVY+AyNcLCjkQPiUlgQoIo4AoCpFKUWpDVpSUpQEhaCQxSRITBAEC4esFjN9RUkrCIKTVTBipNEsShYRK+phCFHiN0GqyarTN6pEma9oJezo514cNHnXGZt596fW0Rkc55+w7Uk4fIgzDoXD6MEAe6nY+AP1VLwJr/LwO/lWbq1oGIeuOKzWNbIcucvyicPwCMNDnK8Nah6v66lCT4/VD1N8fpd78EygVYA2Mjq3ic598L//6ifcxNXoGn728R95Luc8Ww4O3w5lrQg7PzfMnX7iUdSMxD922GgvkpSHNSzppTmE8i1dq/xVAKlF12/AcvNaGvCgpjUGXhiIvydKULE1J075PKcN3C/ENnLwLGIUhcRyRJDFhEPh0AufQZUFZlhhrSYsSYx3b1ozxxt+5M5+5bpa3XPhDXvb8JzOycb3vOHoUcbMC8OoycinE0K/FYAkHDIqAupys1qQDFgw5PO231QIcvxu4cu0VTltgvT+t6s4WqkpqqAtDhjmBo9nDQPismTLNeezvP4zH/u79ufCib/LeD36Kiy/+FrazzOoQViv41PevZ2qxy6pIee7eGNK+5dD8MqNZSSPytrvdjJECojhCqgBtDdoYXxhSaqSRpLkmLR2zy32kVBijsbqgzAukwC+08oWusvIwoigkUApVF2A4R1FqemnOYi8lEJCWjid86nt86ptX8ID73pPzzn8pdrlPGMWeBKsK/1Z6CQ4hZkR1dkWNo+zQZqvPJ7A4Y7Bm5UAr/9dySIm4AVa4/QWgQp+DG6xUmVASoXxhSC2pCLGSOFpz7jWlVYtRldIkcOSzM0gpePjD7s3DH35vDt68l//65g/55mVXcf21NzBz2RVcfPNhcIaT14x484KgNJa8LPEpIgHWBFjjawOcM1ityfOMXpbRzwvfGFIGmDQnrSqoi7IAZxDOEkhJoDRJktAWvgq5ji4ODpQSAq11xc45eoUmkXDzXIdLd1/Ba85/KX/+588jdsazhHWn8+rRB+hpmDOpzJeoTjAZ9BUaIoacEzgpEU7gDAN84DHAsOZlMMe3nwBU3srR/qi35874qhop1YonYC3GGhy+6aKSdU2cHXIZa5qzLm1y5IvLOOfYtGEdT/vDR/K0P3oOL/ijP+GSS7/LupEGC/1sgDEQ0qt+Y5HSQmlw/QwnFSoICQJFluZMzy8zvdynn5feAwi8dxAGCmsteVkQSEEgfMjXt+rx5ExRFJRFSR4G1X16+jXPC8oqhUsKQVoaHz5WXkM1Rkaws0fwjTCDAeir3bpjEz8HTJ6t6R1/6EXtDivvyyKcHYBZ56oEGep096EE25/w239RAeDoA5asNYCumioOy5zAaEMYhUSTo6AkdHtkvT4qCBhuGjFEEFbbomqsBPT6Ka045mUveTl///5/YrIR0JIGE/gEUGstRgr6haY0DiUKhBQESjKel2gHSRTRTzMWOn3SwlBoiyk0jhyJQCnvcRtjCZQgDhTNKEBZqqZTrmoD778XQlCUfgGyvCDNMrSxRGFIRxti5Th9XZM3vPFv2bN3P//4vtejrMOWBlH1JKzncujxB9hIVHyFtRZjNPHYCDQSKEvK+XmsdYNYibMG62y1cYKhuVzZnMc7jgsEuvpGh266Rp0DrWANRZHSGG2SFiXvfNv7edlLXsuVP76OZM3k4OEGIGbgRdY1Af73ZVHQGm3zlS9fwlvf9QFWNQIfz48CGnFAU0kUDmMt2hi0sZRVi7dSG/q5ppPm9HONcd6mt5OIRuRlvdTGg8GqJZyrf6YrjSUl2ljSvEBb60XfrRBUeVHQTzMWeymLvZQ0z9HaN7IIleQxd9vCRZ//DPd9yNPILaAU1mpElZZ+FFVT42Rrq/nLcc4Qr17Ff190KU9/ysv4wPs+QdhsEichRmvfLgZw1lS1huFKmv5tsP23SQCG++B6VLqiwJyzaF1SFCkjk6N86ctf59S7P5o3v/uDXPSNb3DmvR/P6173TsKxcaJmgi6Lwc16rWIHoMcZg7OaIs14xevfQSThhLGQsTggVJJSKKY0TGv/rKU29IuCXpbTy0t6haafl/TTnH6akue+D3AjjmgnEc0oIFQCIbwAFdqQlZp+aejmml6uKR04odBmJV+wnxd0spylXp+FTo/5bsp8N2Wpn3GoV3B9t+Rw7rXFwekez3jo6ey79gc87skvRrUinC5x1rASY2Tl+fFKMc8zGs0ELUOe97xX8qBHP5vdN/2Q//uqv+au938Ke6fmaaweQ5clUoW+qkjUVcFHr8/tLgCDvLOa0as/zDkv/QLGVq/iL17zbh7+hJfwwHudxOf+9ul8//Ov4k3nP503vOUfOOcBT2bPoWmS1WOYoo+rgNfw/RZlSXt0hB9ecT2X/+gqNo9F9AxMNBQ945iwjpc1DHfpdjmwlJHlJcv9nOU0ZznLyYoSbbxm6GcZvTTDGJ9fONJMGG81aCexb+sqfA6gtg5dp4Zb0Nbv09JYsryklxZ0K7Q/1+kzu9xnvtun08+Y7ZcUyxl/EBl+v624eaEgkI5LfzTFs37nVP7ry1/lY//4KcLV4+R5WpnOeqG8EFhnKLWmvWYNP7jyJs6852P4xOe+wofe9mLOe9Jd+ML7XsSayYg73ev3+frF36e1ZZNfZqkq7GAG1625kNtfAGrWsdLdtdXPi5wkhCBOeMLT/4K3vucjvPNVj+UxZ43zo+9czlXfu4IdwSwXvveF6P48Z579KP7t0xeRrF+DcKU/86dqMmWMZWxsFC1CPvjxz+Os5UhHs3su5eYjXQ4t9dkVCl46YnhmbFjsFSynBWlekhYlWV6Sl4asLOlnBf28oDQGpQTNOKJV0b3tJKYRhoRVH8O6545xjkwb0tKynJVML3Y5OLfIgdlFDswucWh2icNzSxyZX2ZuuUcvLZjPS85MFC9fpXjBpGIxLbn60DI/2DPPpy7Zz0gDzrvgvcwdnqG5bh1BEmHKgrpdvC5znNU0V0/ygQ9+kns/7Kns2LGRiz/6p2xxh/nB5bs5eNUVvOqP7sfDHnx3HvJ7f8RH/vEzNDatx5YpedYHSn/w1c+xrHBbwsEDIshijMEWfSbH2uy7fonHPenVzM0e5hXPug+rzCK37O6iogazM4tcc+NBduUZn3v7H/CSN32Rx/3Bi3jZ957D31zwUlye0u/nICSt1ZN8+9IreO5LXs2Pr76Wu5+xlZa07Ni2hsXUcumVB8nSZUoZ0q2oZVMxkHWXrcB4sJdrf1aPDMUgkxfn/XqlJElUFWsIgdQGbR1SCqKqiCM3jkyXILyZMdbjhbwo6Gc5pbUI6+sLrVJoq5gvNAjYuWstu9Ym9Hqau5y+mZunetzxbo/mPufejTe89qXsPGUH+fQ0Wlua7QaFlTzr2efxoY9+igfd9078x989ja998SL2HVqg0WjgpOJTn76Ipz3sXA7u28fTn/3nfP/7V/LGP30SWgisXalwvi2ZQLdZADzC9IUIWdpDRhHf+N6PeNxT/pT1a0b4wCsewWe+9D3KhRbrxhtkecHCwhIj7QYHp7sc2neEB919B1ffcoS3vuP9XHHldXz8Q3/Nmsk2BBHve++/8Lw/eTWrJ0f4h9c/mbFijhv3zLFu3ThJI+Dce2zly++8iDAJSEqHsLqiTOskdAZAMjcG42y1sJ43V1IQhCFJbAeup61AoK2YQANkxuC0ptSeJ3DOoSu201pDoQ15aRDO0S8dWjiC0rLcK9i4doSXP+lO3LJ7jkOzfe5++lqcjHCttbzpny7lDnd5OP/wrtfx1Kc+itg59uw+zGOf9Mfs3r+P817wMA4cmKUzO82huRSplM92znJKI5k+eIh14xGv/5OH88Z/+Azf+tZlfO7j72ZcNtGm6gonbjsGuA0aYAXxr1k9wYWf/SyPeOwz+L0HnM4T772dm6+5gSMLOesn2qRZQaElvV7qJ9ZabtlzhEOHetzz5FW88SWP4Cmv+Dh3uudj+cj738QVP7qel53/Rh754NM5dcsqtrUyrt63QG4MB6eXiAPHkgq8YlOSMPAEknYOi28sGVQoPS1KikolRkFAaSzGQTMOSaKQJIl9mnepfSKocZRG+1y/yn+uvYsa61rrBucJlNp7Hc46Mm0pA29CpHBgLQcOLdDtl+As80sFM/NLnLgp4x0v+R3+5dL9PO2PzuO6627kQQ95AI970ovYsHaEL7/v+czsv5GP7bH0uilZmuEqervbK8jTAmsci0spd96o+NSbnsD/fedXOPvBT+eyb1/ExOSEv0/jK5Gc+SXVBlrjCKMmF37l67z6De/iGY86i4feaT3XXL+HIAhY6vobX+qWGKdY7uWkeUlZag4enqfbKZmZ6xF0p3nP+Y/lz//2Qh7ye8/GOsOD73EiL37kaXzmazdyw25/OHOgfBRsYrTJ4bnMB3NyTWEEhXP0clPl7ltyIyidYYSSKq6DkoVfTOswNsFYXy3kpCKIFJEFVXgQa60lzf17rXVDyNrnQxTW0S8tGI01jkgKlIV2IKERE4UFoRHEQQAuQwqfwCKkYLZTMv/D7/Oqpz6MTasj/vJtH+SNb/sg977HKbzxRQ9i/pbr2XNkmUAI5mfn6fV8p9HSGLJCY4yhLHPCQDI9n5J2Fnj9M8/hnZ/+Pvc693c4644no1TlJoqBc3D7CgB4dZg0Gnzt4m/z8HN2csf1AZdftZcgCCmzcqAuO/0cREg/9YcwSynIyxJdliglOTyzzMZNinPO2spnvnItmzZM8H8euIsjB+dJs4KlTorVGguU2tHPNMZ4YdDa0lQRn9g2SrN6WGccpF3+bD7jCA1awuGkoDTV+cFSIqXEIAiVIlDKB3yCoMoQKklLTVZor+69yA/YSoVgqrC8LDY8YixgGV9PKCQ0Q0legjOeSRQSsrzEGIc2vrmFlALjFHOLPR5x5wne2W6y1Lc87B7bmT+wj8PTPYqixOiC+fkltC4Roc9azosSY3wvBIGj2y9Z7pUcufIWXvyoO/KK91/CF7703zRbY7g6j/E2YIHj7xHkvP9vjWeg1iaWw0cWKQkIrB4cmaK1IS2099tLg7EG8K+FAKtLpBBkhaPX94i4LAqmZ5dpRYo8L+j2JRKHVIq81OS5Rluf+RIEih1KsKM+yMFY8rwkLC0tBIW1NITFOr8gpbHkeUFWAb8wdIQWv8O0q84G8GrfnxTmS8ecE95FrDqUawenCMuJpiBFEjgPInUOcSAoe5q0aQkCQRR6uicrSqIg8MfMa01WGOZnln0qGIKFuQ4zUcNrNmdROLqdftVzy5e19dKMItekaU5ZauYWeggH/cKwMLfEuXdYw00Hlz0KqsCwu/2p4EoMKirAWlhYzmlFktL6gx2ccQMaszSOQFmK0vPU1jpKa0mzEmctvbSgkenqRv2RrVEAWVagS3+gk1ArwM4Jyeqm4v19zeP3Zbhcew4+9UfCt+IA4+BKoZhMPNO+nJVMLZdk2tKMAtaN9Nm5doSxVjxIcatbv/XzgsJaFvoFi71iYCrGmpF/vzE0sZw3a3mvhMKWFIXFWFAKRiPF5alh7aZVtFsJURgQVj0f2u2YLDN0+jndTpcgCDwZZj1t3uvlCKkIlSBUUJaaMFSeqTSWXqaxztLvpxRFQbefMdKI0drQLywBfsFtnU1k3U+m8N0eAuCOSQUrtSEvDCUO4xzOVotVJS7YKmSqlA/0CGvppyW2smv9NEPrErDEgaAZBxxeztixNiEOq7MBrK369hpOP3GcB51zAl+5foq1m8eZWijYcuIkC4t9Du+dAQdhAAsWFnoZk+Mt7nm3jWzbvpq5xYzdB5f49t4F8u4ME2ONAQUshSTLcxbTgsnJUc66y05OPWkj84s9LvvRXn64+zBJIJFKsttIfmQdohFz0smTNJKAxaWUhW5O1Cp43jlbKXJfrxhHIUVpaMQR2hjK0jBzZJpIlYPS7iIvMEYOilojJcjzypSWK3S1quokxYB88x5Qlhl6qa+mqqlqR7VDb08BcG4428QPYx1OeJvsfXG/8EXp8+pLbelnJWGoEE5UIKtASej0cuIkqqJZXm1lufYawvjX1vnEjyQOKbRhfj7lHidMsn0y4VH32sqXL5/jDx5+OhbHc1//JW7ct0Ach8x3+zz2oXfiieduJV3q0mgl5Lmhec5O4okx/u3im/nwp79HIATNZsLSYpfRiTFe8gd345wTJxiNIIpD5pe6vOwp5/CFi6/jbz/yDdLM0IwCTt4ywmufeTfWr57g0OF5FuY7HOzmHNh9mA0jDaYXUkptCIOAflrSbsaAQwWKpcVlQpkTRQGkGqsNgRSkuTeFAsNyLyXLSkptB4kqzUT58xHwrminb8hLS6fbp9fPqg06tD7yl+AFeB5oBVxY67DGVcLmUPhs2UKbyhQI0tzhBCghSTNDKKDZCunnvpq3roiNA4kSgqLUPoxc+qyegf9tNN1+zsGpZXqF5saDHTq9jOuuP8DIeBsR+OKNvNfnKY85mxc+4kQuv2IvC92cRjf32mmux0nA+U+4I2ffYQMX/P3XmJ7rcO697sgrn3N/ssM3Mz87w7KDotTsP7JEFMbc/8yt7D5nK5+79CC9zDI+2iAOFbccWuLAwTkkkn6uSY0gzTX9LMd65UVWFJhayPGATlMgqxwBbTRhIOmkhc87sIblTkaaFd7zKA1laYkCn/9ntKWoIpvaQjctBhjlqP15GzTA8dcFDOK2fpgK8fuqV2+DpKw0Q8UZaGvR2odQtbVEgSAMFIV2HiBW/lqg5AC3Kumrb53zJgXnaMQKbQxh6JtBlqWmLI3vBlLxX0bnnHnKRn7vzmu4/vqDLPZK/NFBllaiaDdDupnluuunOGNNxO/fbwfnnrWFv3nBvVi86Rquvu4w/cJgqo4eSkmuvekgpdbsWqUYbwh0UZJlJZ1eSWe5j9a6yt3zWswYH1Wso3OlthSlIc9LrLGkWUGvnw9+b4yP92vjC1Odcz7LqJNRFH5+pPRzooQ/u8gaT0SV2mKcG/Q2qMPxv6S08PpUz1oavM3xNspTpVr7UGd99l6dFFxqi65cuDpJNC8MWe4PbfCLLnzbN+NRuKlIkFIbtLYoKf01be0K+kXqdFOytPAlYMDZJ02QdrpYoJ/m5IWhn2rywgdMej2fG7D34AIXf+cmzj5hhH033MzMUk5pHL1eRreX089LgkCwtLTM8nKHHVtW0YoFOL+je72cfppXi+iDWl7rmSq1wXsItgaZWV4Jgma5Vw5O8vDP52291l7Ye/2Sbt9XMFnno5bNKMQYU1Uugda2Cmkz0KKDzXkb2eDjJ4JgEG+u40KeYPG+bp0boq0PoQppCJyksJ6m9FG6CqSUhjQryXPvJRjryEsPbHx7F++D56UmDDRJqXHWt1fRVUMIY4yP1vX6g4waZzwmMcaR5iW4gNJocJDEAbmyJFHAkfkea8dD1k806fQ1YeCzdbyg+kyuoDpdtNtNMdqRFt6ddQ6M8bvXOzFe4xWF9tjFeKrZWoMxjqKw9PMSnKMsA9KspK6tLEpNP/UZyWVpMNqSUg6SXp2DLDfYxNIvCkrtd7ypciDKCgyuMD9HF5fdbgJg7crKDxd+1ALgZcMN9d2pXEIcCDnQArW6NNVC2qrFyyDTBXDOsLAwRxw3MNbzAKU25Lk3F2VlB63xuyfrpwMwiXPML6W0GtFA62hj6OcFUeiPie1nOcZa7nTiJDhvboLqaLea75fKHxwtHGRpAdpQaEedgu2zjDX9fo7A9wzKCkM/K7BWYq0mLwTCaZaWFoCArDRIURAMJUVZ69vQ16xfPy9pJQlCCNLCIAWUlcr3CN9VbWzcQGCHN2WtB25LNOC4TICURLWiqVOXHN62m7qcy3n/21V2yWuD2hwIAmHpZDlhKL2dr+wlMhxyyRzTCx2inQ+g3z6RtN+nqKTem4Qqi8f5zKJSG7TRA+LDWUsvs2SlV8V16Xde+IydstR0ehnW1sfeQJZp9MDcmEorVTvcOvK8oJdpSrMyAdpoyrL0BJX2mT6uOhpeSCq3uGB6OWNPOs6e2T7CWbpZQZbXF/ICkBdmkC1VaEMUVo0inKjOPXReAJwH4b5wuYpZ2LpDmGPAAQuBFMeP7X7mGz2zpPdUWUC2rsk31lWpWa4Kl7qB+vQ0qBeOvHS0IsfuqUWmlo1nCI0HR3UmUKQ8g5hlBXuXm4xuPIG8sY4DS3ogUNa5aod5TSOF/5wsKyt3CTrdjH5W0ul7MkcpiRB+l5WlJs18RW9RlJ5erkipolK/WeGFbFihGuOp6MK46sDLWr17QSu0QeKqWoLKnw8k0wvLrL/bY3jWeW9iRqxhvtNlpBmh69y+KgehX5mNrDD00xU6XRtDVhiy0lKUFmPqebWD3S6oQt/OEgTRIOVcwvLxpob/TBPgnMOU2WUqGPEfFPrmbAu9gg0TMcZWaN968kcbrxny0hAo34mjn/a4ZR62rArppCVOQFrx+jhLVmgWuwVpCUr3+ffPfY4QwxlrRilNnTPoqu5g1XGv1puVTrckLzwZsricsXa0gZRusBtrYXV4TKGtQAo1IE6yXNMI/cHPWeHvuVakznmtkZdlpWn9ztWlpiw13X7JSEMQBD5mUZbWawpnMC7g+z/8MQfn5pienmPT2sALo6l3qxjwJYEQpJmhN8AQPtcgK8zgtJJI1GnwGt8ySxJIy2zXa6zqZBIrhcLq9Lu3y9Gxg9w/W9wUKIl1RCoIrQpi9szk2CGAZ6x3WVw1cd6eQigdy5kkbIySl7ZKAxuyVMI3hNLGUhjL5lWKJD3EWesKVo9ElXbz+MAvJKSZHsTl+7mu3EnPQZRakxcaY/xp4N5iuQHtmxfeftcC1UuLCok7skJ7bVDVFljnyLKcolw5hc1W2iuvtIgnvnwUsdTeFJTaMNoMyA9ewSVf+U9GXYdGI2J6oe8JnVoAjCMrDL1Mk5WGfl55VLV77Xz+VV13CVCWhlI7pLDkRckt0wVBGBFGCdbZIFACq/Nrj1q/n1cA6kXq93vTAeaL+FMMbas9QjezXL2/y2QLcuOrb1XVnMmDuQoda0MkBdtGIdMWJXwmz0ruukBS1xQKsgJO2jjKqnbAzHLOWEsRSjHQLAJBNy0oSx++zfK6MKI+hsYOsnjK0ufWl9qQZaUXmsLvaPCBrTTXvjlU6QUnK6rFp84Q9qCvlldtHUXh3VOt/Y7EVS1nfSKST/LUjq2rE85cr9iyKiLN/ecb4wYFU9pU91OZnn6uB2aoxjoe8HkBDxS+o5k2jMbwnZu6ZKVlZHQCIYS2ThC48sJOr7PPL9/P1gI/VQDqv+/2M6vz5VdLXzFBECU0miNce6jg5kPLrG4alKzr1CtQCBV4s/RLy2ioiYUlLXyQwz+0qybC4whZvW7Gkry0ZKUlrur889LHGZSAtNr1/czQ6Zdo44O2UgofgxdeqPJSU5Q+oNLPV3as1sYfQi0862erlC/vrXjPZlhAi9LWh3n6aqG6QFWt9AwEKMqV5+plljS3NGI5AHM1KVY7VbZKPOkVukL8Pn6SV/dojMVZ/5lF6buJxgGsaksuu6XLLVN9Wu0xwrjpiTghpcs7r+qkhV3Zvj99HDcP0FleuHx0ovHRDPmHShjdaI0GAscP9naZ62ruuKVJ0ogRUqCt9W3aHDgsqgp/jiTSq0lZS/bKLTq3orJkZR+zwpMdCM+UedbQ4wspIdO+0NMYrwGkgEgJijJHOocxEuOgl2v6maKfGyLlbeyaiab/HFeXtnvSKlCimnAIQoFTNak11Hja6+ZBraC1EAce3FrnT1CzDnJtkapqQVsRZXU/AZyrvBiP8AMlCQMBeGEEz3tY4+imljAQjESQ5gXfvSlj/1xOszVCa2QCcIVBRi1RfHSxs3i5F9vbWQB6WeGS/tyLg2TVuQa1Q0pTNNpjURBG7Jlb4sB8hztszDhj6wiNUNLJQQpHIFbazPnEEEsQKqzwpEvNW5TaIBBV+pUnlMqKIfOIu6aY/e4MAzHYSXU1TF4ahC3Y241wWrN93GsNnK06hTgK7ZtH5YUhkKYKuvh7yUpDEnlfPy8MKqy6hkkx0IZSiCHNKsgLv2DNJBg0l6yJskI7otBrNeEsAkEoVzRrWVoPYL3rxlhzqFtahaUybWmFUBYlN02l3Dxd4pCMjE6QNEcBV2grolDYq7Le/Iu6WemOd/FvkwAIYG6ps7QlaTxKh6NX5FpESpgiSprRZBjR73W48mCPPbPznLoxYc1oQmoCCuNtF8LfVGkcKOuB3QBZe1PhnC/IMNqCtzZVbp7wHgO+e5g2vvevtY64ii+Ad8f2L1mummsQKEPAAhsmIuJQ0ogVnVRWncOglxYI/OKkuSGvuHUHAwAmq+bSHtNQLZSoTI4A4dW+Nu6oo9tqvsSzopW3g8BZaFQChvCasmZHk6pLeT8z4BwGr81CV3JkIePaw95LShpNGs0RVBADriitiJJA9EW++OhDS93lilM77nGbW8Tsn5r+scoXTgoRV2qCyIGWUulme4zR8VX0TMx3d2d8/5ZlpOkzkdjBuXzGeibLWldV3lS2sAKLtWunh9qjaLPyHm19EkZaVKnaxmGN99dBEAYhyz3fMziK2yz0iirrh8E1mpFCSL9wNXeRFd6rqJtC+2IRhy7tgPqtRbW+J6U83hgux/a23npsA9iK2q5NTO3FCLwm6WamQvmeW1ACeoUGHE2l6fY6fO+WZX64r6AkYmx8Fa2RCVQQaYez2skoEuIKm86feGh2/ma4bYt/mwRgeByYmbvZ9Kbu2aR4AyIKNCoQQugwSuzo+CTtkXGOdCX/fW2fa/cvEdk+sbL0Sx/jN3VDCQAhfdOFaqfX3oOp3MiiStVS1enpdYt3U9GoaWEqN81iMZy4LmLUzmBmb2Dn6jbdzJDmhn5uKU0tgFWuoPBZOIihmnrnUX5Z2sot9C6lVwDecyiqRJJG5IHn8H37RM5ykBijB9S5tw1yqHxeWztgHNPCUlpoBIaQlCv2LPKNG1Lm0oCR0XFGx1YRxg0rhNTGiQCUbMji9WVv5pyp+cVDP886wi/QJ3C20+83svz81ePjnzThyOszG/weziCV0VGjJcejWOZpjxtmeuyZW+KkdQHtZoiQEQ6PB6QUBKECUZ3uIYQnlKzDSrcyQUHVjsauYIBSW7TzrWd9TLwqWHGOO64LkEKR6ZqqFQNVW1VcD/L9PA1dxyocpXGkpa4YzcBTvHa4hM0vZ1lHOO1K3UAtQHlpUBWgNcZWB18fM4QYUMhp6WiGllZUcv2hjGsPaUorabXbxEkLqQILaIuInJMylvaLlMsvnV1eurEoj60Kum3jF2oUmZaG/TNzPxpNlh89Mjp5bxO235uV4hThSqRUOmmOBFGUkPZ7XHU4pR1p7rDRMjnuF6iulq2LMFXVtXul741fsLzi2+v3eaAlKl6gLlb1buhSaigrnS+sxjpJFPgOHHHokba10C/sQIsI4Zm8rDBVXMDX8mqjwYWDpAtRhaWtcbhKIL1LqwemawUkuqEey67O2qoQvhv8XEnHZMsxvZhy1YGM5QyiOGGi5e283xMisMgolO4GWfb+qLu8/M1uVhx/1sdPGbdLu/jlrLTL2dQ3JtvLZzVbE3+QE76zdLYdCGODKLIjYRToskm31+V7ewo2LS1x9s4GSno3rObVpTJVxy4PDEW108oqT2BACRsQkav8/aozqKBSpRqL7zNgjKMwlkYkMda7f3WTB20shdaDRIxC+xM/lCgrJCdxSLT2waIKA1IaSy8rkEoNCM2al6gjkHVSqagLRvCvhaS6D/8sEosUBd+/JePAvEGpkNGxNkGUIIXUCKR2MgiE6DZV+epeZ/G9851+enusWT1uFwGox3w3zemm/7h+fPQLzcbYBX2XPNc5I6UwOoobciyMZJ72OLjQ4wuXd2g1EkKpqhTolVZuNZJ1zqt66yCJquRSPIPm8AdCOFs1spQenWvrO4nmha7ApccPeeE1Q16YAe1caDvw2aQAawoOdSSNTLN+VCGisKK1GTB8ae7JJydK4jDwCZ9GDXAJzpsRKY/uAqKEqMgkjZKCOFTsXSy59kgPYxWt9ihR3EAqZYUQ1jgRSCQt5d5XZIuv3L+wPHt7rlU9frFDo44Z9QMfWVyenZ879LyoXDwhUfybk1FgEFIKWcSNlp2YXEUQt+lmJabM6OUWiaEZWYpKFZfVAQvGrdCiyrfpGmQb1QJSu2XeK/BaoMbbuopMphWwSwtbpVT5rCRtak2i2bug+J1nvoHTf+c5XLt/wTOQVRja1b36KlyS66r1HbU34wY8fmlWvJz6XrWFUDms1hQGBIa0sETJCBOrVpE0WlYppS1SGqeChuRroe6cOj9/+HnT1eLfxmSf4xq3qwYY9kB6haE3N3/LWKP7+FZr7J5atd5dCnWWoEQF6PbIaGB0kzTtsdBN+erVJXfcomknCoGkMHYQanbOq8xI+ViBEFQTv5Jc4YNKXoBKa4iCKnJXAbug8sWLKutHCjHI2YsCSZYXEDb47//+MunyLJmL6Bd60BqGwcdUNIvztt4O7LqPh/j8SC+oUvqCklhBKDTz3YybpnJ6hSKOY9ojYwRhDALtvJ2XoRB7lek/q7u8/PXlfn7MeSi3/7hdBeDWxlJa2KV05tLJVveeSWvs90vReIfBTkqntQpDWsF4EEUJvV6H792SsqotOWWjZbIdEYcMwKD3HIYyXoYYl7qBk19sS2k8vFRS+NI0IaqYgtcY9VFytSeQFxqpQsZY4MYrv0PoCnZO+oWPlalOMvHEkGOFz/BxBYuWskpXq0Ct9TggCiSNQJNnJVcdypjuOqQKaLXbRHGClEpbwDoZhFIUyuYvzHudf57u3r52/qeNX7oA1LTkfC/N6KUfWzs28qW4Mf6KXEZ/ZoxGonUYRXI0mJRF1meu2+XSG/psmSzZsSZkNAnoFD55IqqSPz0a8MUoVS7lAH07fNUwxvvaPjfB0oo8aVNoUE7gnKSsNIYSvsJotB3TMou0Y0Ujjn1OgfAtsuo4Rb3ryyrU7JM3/EOW2puEtMhpK4iFZs+RjJtnDFYEtEerhRfKIoQ1lkBKSWyLt+h+980zy92ZX/Z6HDt+6QJQq61aEKaXOnOttP+ysZHRD5mg9cqC6Mk4jVS2iJvtIIxjmfV77J9PmVrSnLRes3kyRqnY71zJwCMwlpXQKXWPvdruiorOFYMOotRsnAPnLFKstJwzlXfRCCOSUJIXllZcHSU7VGtVJ71o44FdjUV8txtHElqULbhxqmTfvCbXgkazTaPZRqrQeu9RBAgpY6W/IMrOeUudzjX9qm/hbeHxb49xu4LAnzaOxQeH5hau6S0e+T9N079fFITXWBFHQkoZhJFujowzOr4Kp2KuOlhw6Q1dljp9xiJDK5GDTB9PD6908TLWEYd16xdP2frIon+/EPUZgPW5RAKcqMrDK1xg/clhWvtEkrzwIeU6967OH6wFoQZ/gbKMRAUzC11+fCDlxmmNUw3GJ1bRbI+hVFAA0jgZCGcvS2z/IenyzGMOzy0MFv/YefrfGL90DfDTRjfXrpvPfGPNSO+uzcb40zIZv846t1ZKTRTHOgyjQBcZ3V6XS25M2TtbcsrGiNE4qIialQOea4o4UJ70EbgqqOMX21hHoHwipZQSCQjp08Hr5FoffmVQeVPnM5hBpU3V7NJZhPA5C9o62srSTXMu350z3XGoIGJsvPLnpdJA4ISKBGIxNv0/7XWXPjbbz8r/eWb+98avVADqMdPpp3T671010vp40pz4i0JGf26dCZQyOkoajEdxkGd99i90ObTYY/OE4oT1DRqhIvfJPX5RhT86LqgIpno/1UxuDdDqpot1dlqt4uvwdO2+1bkCVBhAKUmgambf0Ywsuiy49kDO3nkNQtFut4iSRkXfVv68kMTotxfZ8hsPLywP7Pz/trq/tfFrIQD1RMx1estxlp433hp5T9Qcf0fuokeDRkh03GjJIIxk2u+xdz5larnLietCVrcjbhESpSRS2kH+nBSCWrGuhJ4B5101oVay6G31fv/eOue2FgQxlA/vfx4pg7OGA7M51x/JKY2g2WoRJ02UiqyQwlonA4eQkbCf09nCH8/2uvvyY3j7X/Xiw6+JAAxPRF5aphaX9o1m/cclzZEzXdh6uxHhfXEaFYS61R4N4jghTfv8+GDBRDMnCBq+zFp69ayNRam6nMwN8gpiNfxp1eIyvPNBOXxPT+coSn+KaVk1Z3bWoq1htmf48f6MtHBEcYPxsRYqiJBSaocMLEpG0l1li86zu73ly7pZebvw9r+M8WshALc2fHxh/vLRRvfBjdbYY4xqv89gx6XUNoobNoziQJcFnV6P0JYgBWlpUcL3DXIIlFqpXKqPjPF2vELu1BjBIT2QqBI8/c/SwlA3gBICwkDRyUu+d0tBEMaMjbcIwhghpUYIaVGBgOXAdJ+T9jufX+xl+a9wCo9r/DLYxV/KWD3SnlCN0RcYlVxgnUWhq8NKTJD2e5R5ijaGtaOKUzY2GG9FdHPo5Za8tLQbAaOxYCn1OYpRIBBSsNgvCZQglJKlviZU/ozg0jjaDcVkE2460ueaw95tdA6SRtvbeSm1L8+QgRQSqbO/KLKl9y50egu/6vk63vEbIwAAYSCZHBndSTR6nlHRc3AaYbV2zkmtS5mnPdI0RQnLCetiTliXoF3AQgojiaQdCRZ6vvN3M/JMYC/zNfqRkiz1S98jSEGiHALNTUdy9s2XKKkI44Q4aRGE3s47VCCERLrioy7vvHax07ml1HWLqV8PG/+zxm+UANSjESpGRifuQjjyViPEfbElwlltrZVaFzJLexR5RiuCO2xKWD3aQIYxOMHccoaSkmbs8w+zUhMpf6D0fE8zmgC25PBCzi0zGuMESZIQJS2CMLZSCu2QkUOiMN+Qund+p7v8rX6ufxPW+yfGb6QA1GMkiVSzPfEooxpvM7htwmrAamddYHRBr9fD6Jy1bckZW1usHkvYO28wFtpxULF/BqUkzRjyLGexU3LDVEa/9IkZSaNFEEQopbQTIrBOorCHpcle2Osu/ns3+wVTcn7F4zdaAOox1mo0k8b4i7WK/9I4GymMrlRwUOYZy51lsCU7Vik2jEc0GnHF9YN1hkha+mnOVQdSjixbVBDSbLYIogaqis9bJwNAR7b4qzxbevt8p7/0q37u22P8VggAgFKC8VZ7Xdgce0NJ9EznDAKjAWmNkVm/R9rvITBsGFVsmIhoxYpebji0UHB42QCKZjMhSpqoILRCyErdCyJh/tVknT+fW+7stfbX1qu7zeO3RgDq0YoD0WqOnOrC0TcYqR6FLRHYwjkCo0tZFjlZUWCNqQpHLUJJGklEFCWoIETKFXUf4C4Xpvf8bmf5e728/I208z9t/NYJQD08Phh/gA5ab7OI06XTCFzhHNIfeOUziamykZEKKaVFyMg6iXBuNhL5+f3u0ocXu2nxMz/wN3T81gpAPSZajUbSmnyaDpLXWSfWCnxPguGDlWr61yEROEJXvDXvL10wt9xd/FXd9//W+K0XgHpMjrRGGs2xJ3ZyXVjEBinkJidcAUJK4awUMowlM7rofqTT6+7Pf33Z2/83bp8hBv+EqM/m+3/jt3b8v+W99fH/AbdaIL4CZkuFAAAAAElFTkSuQmCC"

WORDMARK_URI = "data:image/png;base64,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"

APP_CSS = r"""
[hidden]{display:none!important}
.reviewfilters{flex-wrap:wrap;align-items:end}
.reviewfilters label{display:flex;flex-direction:column;gap:4px;min-width:0;max-width:100%}
.reviewfilters select{max-width:100%}

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
.export-grid{width:100%;display:grid;grid-template-columns:repeat(auto-fit,minmax(min(100%,340px),1fr));gap:12px}
.export-item{min-width:0}
.export-toolbar,.export-actions{display:flex;flex-wrap:wrap;align-items:center;gap:8px}
.export-toolbar button,.export-toolbar a{white-space:nowrap}
.export-toolbar a{font-size:12px}
.export-actions{width:100%}
@media(max-width:440px){.export-toolbar{flex-direction:column;align-items:flex-start}}
#appzone button,#settingsview button{background:var(--acc);color:#fff;
 padding:8px 14px;font-size:13px}
#appzone button.sec,#settingsview button.sec{background:#475569}
#appzone button.danger,#settingsview button.danger{background:#dc2626}
button:disabled{opacity:.5}
progress{width:100%;height:12px;accent-color:var(--acc)}
.det{background:var(--panel);border:1px solid #334155;border-radius:8px;
 padding:6px;text-align:center;font-size:12px;color:#cbd5e1}
.det img{max-width:100%;border-radius:5px}
.thumbwell{height:112px;display:flex;align-items:center;justify-content:center;background:#0f172a}
.thumbwell img{width:100%;height:112px;object-fit:contain}
.thumbwell.unavailable:after{content:"Preview unavailable";font-size:12px;color:#94a3b8}
.thumbwell.unavailable img{display:none}
#letterGaps{margin:8px 0;border:1px solid #f59e0b;border-radius:9px;padding:8px 10px;background:#26200a;min-width:0}
#letterGaps p{margin:6px 0;font-size:13.5px;color:#e2e8f0}
#letterGaps p.detscope{font-size:12px;color:#cbd5e1}
#letterGaps .lgnotice{color:#fbbf24;font-weight:600;cursor:pointer;font-size:15px}
#letterGaps .lgtools{margin:4px 0;align-items:center;gap:8px;font-size:12px;color:#cbd5e1}
#letterGaps .lglist{display:grid;grid-template-columns:repeat(auto-fill,minmax(min(210px,100%),1fr));
 gap:9px;max-height:470px;overflow:auto;margin-top:6px}
#appzone #letterGaps button.lgap{background:var(--panel);border:1px solid #334155;border-radius:8px;
 padding:6px;font-size:12px;color:#cbd5e1;text-align:left;min-width:0;cursor:pointer;
 display:flex;flex-direction:column;gap:3px}
#appzone #letterGaps button.lgap:hover{border-color:#fbbf24}
#appzone #letterGaps button.lgap.lgcur{border-color:#fbbf24;box-shadow:0 0 0 2px #f59e0b}
#letterGaps .lgnum{font-weight:600;color:#fbbf24}
#letterGaps .lgtime{font-variant-numeric:tabular-nums;color:#f1f5f9}
#letterGaps .lgopen{color:#93c5fd;margin-top:2px}
#letterGaps .lgap img{width:100%;height:130px;object-fit:contain;background:#0f172a;border-radius:5px;display:block}
.reviewgrid{position:relative;width:100%;overflow-anchor:none}
.reviewrow{position:absolute;left:0;right:0;align-items:stretch}
.reviewspacer{position:absolute;left:0;right:0;pointer-events:none}
.reviewranges{position:sticky;top:0;z-index:5;background:var(--panel);padding:6px 0}
.reviewranges span{font-size:12px}
.det.off img{opacity:.55}
.det.selected{outline:2px dashed #60a5fa;outline-offset:2px}
.detchoices{display:grid;grid-template-columns:1fr 1fr;gap:5px;margin-top:4px}
.detstate{margin-top:6px;font-weight:600;min-height:2.5em}
.detlabel{display:inline-block;margin-top:6px;padding:2px 9px;border-radius:999px;
 font-size:12px;font-weight:700;background:#334155;color:#e2e8f0}
.detlabel[data-state="review"]{background:#f59e0b;color:#1f2937}
.detlabel[data-state="blur"]{background:#dc2626;color:#fff}
.detlabel[data-state="keep"]{background:#15803d;color:#fff}
.detlabel:not([hidden])+.detstate{margin-top:3px;font-weight:400;font-size:11px;color:#94a3b8}
.det[data-state="review"]{border-color:#f59e0b}
.det[data-state="blur"]{border-color:#dc2626}
.det[data-state="keep"]{border-color:#15803d}
.detscope{margin-top:4px;font-size:11px;color:#94a3b8}
#appzone .blurbtn{width:100%;padding:8px 3px;font-weight:700;
 font-size:13px;border-radius:8px;letter-spacing:.3px;
 transition:background .15s,transform .05s}
.blurbtn:active{transform:scale(.97)}
#appzone .blurbtn.blur{background:#dc2626}
#appzone .blurbtn.keep{background:#15803d}
#appzone .blurbtn[aria-pressed="false"]{background:#334155}
#appzone .detchoices button:focus-visible{outline:3px solid #fbbf24;outline-offset:2px}
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
 padding:10px;border-radius:8px;height:180px;overflow:auto;white-space:pre-wrap;overflow-anchor:none}
#log>span:empty{display:inline-block;min-height:1em}
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
 left:calc(50% + var(--qx,0px));transform:translateX(-50%);bottom:135%;
 background:#0f172a;
 border:1px solid #334155;color:#e5e7eb;padding:9px 11px;border-radius:9px;
 width:var(--qw,250px);box-sizing:border-box;font-size:12px;font-weight:400;line-height:1.4;z-index:90;
 box-shadow:0 8px 24px rgba(0,0,0,.6);white-space:normal;text-align:left}
.qm.below::after{bottom:auto;top:135%}
footer{text-align:center;color:#64748b;font-size:12px;padding:18px 12px 26px}
.hdrtag{display:none}
@media(min-width:900px){.hdrtag{display:inline}}
@media(max-width:640px){.grid2{grid-template-columns:minmax(0,1fr)}}
"""

JOBS_HTML = """<div class="card"><h2>Jobs</h2><div class="joblist" id="jobs">loading…</div></div>
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
   +fmtTime(s.t0)+'&ndash;'+fmtTime(s.t1)+' '
   +'<b>'+(CATDN[s.category]||s.category)+'</b> '
   +'<span style="color:#94a3b8">&ldquo;'
   +String(s.text||"").replace(/[<>&]/g,"")+'&rdquo;</span></div>';
 });
 h+='<div style="margin-top:3px"><button class="tog" style="font-size:11px" '
  +'onclick="applyAudioSugg(-1)">Add all</button></div>';
 el.innerHTML=h;
}
function applyAudioSugg(i){
 if(BE_VIEW?.checkpoint)return;
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
  h+='<span style="'+st+'" title="'+fmtTime(wd[0])+'&ndash;'+fmtTime(wd[1])+(m?' (will be muted)':'')+'" onclick="txWordClick('+i+')">'+esc(wd[2])+'</span>';
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
 if(BE_VIEW?.checkpoint)return;
 const tx=BE.audioTx||[];if(!tx[i])return;
 if(BE.txAnchor<0){BE.txAnchor=i;renderTranscript();return;}
 const a=Math.min(BE.txAnchor,i),b=Math.max(BE.txAnchor,i);
 BE.txAnchor=-1;
 BE.audio.push({t0:Math.max(0,+(tx[a][0]-0.5).toFixed(2)),
                t1:+(tx[b][1]+0.5).toFixed(2),
                mode:(document.getElementById("beAMode")||{}).value||"mute"});
 renderTranscript();renderAudioSugg();beTLDraw();
}
const CATDN={mrn:"regex",person:"person (full body)",manual:"tracked object",qrcode:"QR / barcode",screen:"screen (tv/laptop/phone)",anytext:"all text",bank:"bank number",crypto:"crypto address",passport:"passport / MRZ",phrase:"specific text"};   // display names — ids are a compat surface
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
let CUR=null, EN={}, MAN=[], DUR=0, POLL=null, PHIST=[], PHPH="", LOGN=0, LOGE=null, LOGINIT=false, RECENT_LOG=null, SHELLPH=null, JOBSJSON="";

// VIEW_GEN advances on every openJob (including A -> B -> A) and removal.
// Drafts live only in this page; late acknowledgements reconcile their owner,
// but may never publish into, or start rendering from, a different view.
let VIEW_GEN=0, EDITS=null;
// Polling owns one metadata -> log cycle, using the existing view identity.
let POLL_CYCLE=null, POLL_FAILURES=0, AUTO_REVIEW=null, REVIEW_REQUEST=null;
function pollStatus(message){
 const el=document.getElementById("pollStatus");
 if(el&&el.textContent!==message)el.textContent=message;
}
function stopPolling(){
 if(POLL){clearTimeout(POLL.handle);POLL=null;}
 const old=POLL_CYCLE;POLL_CYCLE=null;
 if(old)old.controller.abort();
}
function schedulePoll(id,gen,delay){
 if(!ownsView(id,gen)||document.hidden)return;
 if(POLL)clearTimeout(POLL.handle);
 const timer={id,gen};POLL=timer;
 timer.handle=setTimeout(()=>{
  if(POLL!==timer||!ownsView(id,gen))return;
  POLL=null;refresh();
 },delay);
}
// Only metadata/log use this deadline. Race body consumption too: abort alone
// cannot settle a transport/body that ignores it. Losing work has no UI effects.
async function pollJson(url,cycle){
 const controller=new AbortController(),signal=cycle.controller.signal;
 let deadline,onCancel;
 const stopped=new Promise((_,reject)=>{
  const fail=message=>{controller.abort();reject(new Error(message));};
  onCancel=()=>fail("Polling cancelled");
  signal.addEventListener("abort",onCancel,{once:true});
  deadline=setTimeout(()=>fail("Polling timed out"),15000);
  if(signal.aborted)onCancel();
 });
 const operation=(async()=>{
  const r=await fetch(url,{signal:controller.signal});
  if(!r.ok)throw new Error("Polling HTTP "+r.status);
  return await r.json();
 })();
 try{return await Promise.race([operation,stopped]);}
 finally{clearTimeout(deadline);signal.removeEventListener("abort",onCancel);}
}
function refresh(){
 if(!CUR||document.hidden)return;
 if(POLL_CYCLE)return POLL_CYCLE.promise;
 if(POLL){clearTimeout(POLL.handle);POLL=null;}
 const cycle={id:CUR,gen:VIEW_GEN,controller:new AbortController()};
 POLL_CYCLE=cycle;
 cycle.promise=(async()=>{
  let delay=900;
  try{
   await refreshCycle(cycle);
   if(POLL_CYCLE!==cycle||!ownsView(cycle.id,cycle.gen))return;
   POLL_FAILURES=0;pollStatus("");
  }catch(e){
   if(POLL_CYCLE!==cycle||!ownsView(cycle.id,cycle.gen))return;
   delay=Math.min(10000,900*Math.pow(2,Math.min(POLL_FAILURES++,4)));
   pollStatus("Job updates interrupted — retrying in "+(delay/1000)+" s.");
  }finally{
   if(POLL_CYCLE===cycle&&ownsView(cycle.id,cycle.gen)){
    POLL_CYCLE=null;
    // Chained after completion: request duration adds to the healthy 900 ms.
    schedulePoll(cycle.id,cycle.gen,delay);
   }
  }
 })();
 return cycle.promise;
}
function wakePolling(){
 if(!CUR||document.hidden)return;
 // A pending immediate wake already coalesces focus/pageshow/online bursts.
 if(POLL&&POLL.wake)return;
 stopPolling();
 schedulePoll(CUR,VIEW_GEN,0);if(POLL)POLL.wake=true;
}
document.addEventListener("visibilitychange",()=>{
 if(document.hidden)stopPolling();else wakePolling();
});
window.addEventListener("pagehide",stopPolling);
for(const event of ["focus","pageshow","online"])window.addEventListener(event,wakePolling);
const REVIEW_DRAFTS=new Map();
function emptyEditor(){return {t:0,ox:0,oy:0,boxes:[],sel:-1,ov:{},dis:{},times:{},quads:{},geometry:{},adds:[],
 add:false,addAnchor:null,drag:null,scale:1,dur:10,
 audio:[],audioSaved:[],audioLoaded:false};}
function sameEdit(a,b){return JSON.stringify(a)===JSON.stringify(b);}
function copyEdit(a){return JSON.parse(JSON.stringify(a));}
function ownsView(id,gen){return CUR===id&&VIEW_GEN===gen;}
function saveStatus(d,message){
 d.status=message;
 if(d!==EDITS)return;
 const el=document.getElementById("reviewSaveStatus");if(el)el.textContent=message;
 document.querySelectorAll("button[data-save-edits]").forEach(b=>{b.disabled=!!d.busy;});
 reviewResolveActions(d);
}
function trimReviewDraft(d){
 const b=d.editor;
 // Clean audio is fetched display state even when other edit kinds are pending.
 // An in-flight audio submission may make a toggle-back a newer pending choice.
 if(!d.audioInFlight&&sameEdit(b.audio,b.audioSaved)){
  b.audio=[];b.audioSaved=[];b.audioLoaded=false;
 }
 if(!d.busy&&!hasReviewEdits(d)){
  d.en={};d.editor=emptyEditor();
 }
}
function hasReviewEdits(d){
 const b=d.editor;
 return !!d.submitted||Object.keys(d.enabled).length||d.manual.length||b.adds.length||
  Object.keys(b.ov).length||Object.keys(b.times).length||Object.keys(b.quads).length||
  !sameEdit(b.audio,b.audioSaved);
}
function reviewGesturePending(editor){
 return !!(editor.addAnchor||editor.drag||editor.tlDrag||editor.pointerId!=null||
  BE_VIEW?.editor===editor&&BE_VIEW.tlGesture);
}

// Job names are text inside the list link and detail heading.
function jobNameHtml(name){
 return String(name).replace(/&/g,"&amp;").replace(/</g,"&lt;").replace(/>/g,"&gt;");
}

async function loadJobs(){
 const r=await fetch("api/jobs");
 if(r.status===423){jobs.innerHTML='<span style="color:#f87171">&#128274; locked — unlock in the Encryption panel below</span>';JOBSJSON="";return;}
 const js=await r.json();
 const s=JSON.stringify(js);
 if(s===JOBSJSON)return;
 JOBSJSON=s;
 jobs.innerHTML=js.length?js.map(j=>
  `<div class="row" style="justify-content:space-between;padding:4px 0">
   <a href="#" onclick="openJob('${j.id}');return false">${jobNameHtml(j.name)}</a>
   <span style="display:flex;gap:10px;align-items:center"><span class="badge">${j.phase==="stopped"?"stopped "+stoppedPct(j)+"%":j.phase}</span>
   ${j.phase==="stopped"?`<a href="#" title="Continue scan" style="text-decoration:none;font-size:15px" onclick="continueScan('${j.id}');return false">&#9654;</a>`:""}
   ${((j.phase=="error"||j.phase=="cancelled")&&!j.checkpoint_unfinished)?(j.failed_action==="render"?`<a href="#" title="Retry the render — keeps your review choices" style="text-decoration:none;font-size:15px" onclick="retryRender('${j.id}');return false">&#8635;</a>`:`<a href="#" title="Retry the scan — reuses the file already on the server, nothing is re-uploaded" style="text-decoration:none;font-size:15px" onclick="retryJob('${j.id}');return false">&#8635;</a>`):""}
   <a href="#" title="Delete this job and all of its files" style="text-decoration:none;font-size:15px" onclick="delJob('${j.id}');return false">&#128465;&#65039;</a></span></div>`).join(""):"none yet";
}

async function retryJob(id,afterRender=false){
 if(afterRender&&!confirm("Scan again from the start? The new scan replaces this job's review, so your Blur / Keep visible choices and box edits are discarded. To keep them, use Retry render instead."))return;
 const r=await fetch("api/jobs/"+id+"/retry",{method:"POST"});
 let j={};try{j=await r.json();}catch(e){}
 if(!r.ok){alert(j.error||"could not retry the job");return;}
 JOBSJSON="";loadJobs();if(typeof openJob==="function")openJob(id);
}
// Stop and continue: a stopped scan's share done, from its saved frame.
function stoppedPct(j){
 return j.stopped_total?Math.floor(100*j.stopped_frame/j.stopped_total):0;
}
async function stopScan(){
 const id=CUR,button=document.getElementById("scanStop");if(!id)return;
 if(button){button.disabled=true;button.textContent="Stopping…";}
 const r=await fetch("api/jobs/"+id+"/stop_scan",{method:"POST"});
 if(!r.ok){let j={};try{j=await r.json();}catch(e){}
  alert(j.error||"could not stop the scan");if(button){button.disabled=false;button.textContent="Stop";}}
}
async function continueScan(id){
 const r=await fetch("api/jobs/"+id+"/continue",{method:"POST"});
 let j={};try{j=await r.json();}catch(e){}
 if(!r.ok){alert(j.error||"could not continue the scan");return;}
 JOBSJSON="";loadJobs();if(typeof openJob==="function")openJob(id);
}
// A failed render keeps the scan and the saved review: render it again.
async function retryRender(id){
 const r=await fetch("api/jobs/"+id+"/render",{method:"POST"});
 let j={};try{j=await r.json();}catch(e){}
 if(!r.ok){alert(j.error||"could not retry the render");return;}
 JOBSJSON="";loadJobs();if(typeof openJob==="function")openJob(id);
}
async function delJob(id){
 if(!confirm("Delete this job and ALL of its files — upload, report, and rendered output?\\n\\nThis cannot be undone."))return;
 const r=await fetch("api/jobs/"+id,{method:"DELETE"});
 if(!r.ok){
  let m="could not delete the job";
  try{const e=await r.json();m=e.error||e.description||m;}catch(_){}
  alert(m);return;
 }
 const track=REVIEW_DRAFTS.get(id)?.track;
 if(track?.timer)clearTimeout(track.timer);
 REVIEW_DRAFTS.delete(id);
 if(CUR===id){BE_OPEN_INTENT++;disposeReview();beUnmount();stopPolling();disposeRecentLog();VIEW_GEN++;CUR=null;EDITS=null;AUTO_REVIEW=null;REVIEW_REQUEST=null;detail.innerHTML="";}
 JOBSJSON="";loadJobs();
}
async function openJob(id){
 BE_OPEN_INTENT++;disposeReview();beUnmount();
 const video=document.getElementById("beVid");
 if(video){try{video.pause();}catch(e){}}
 if(EDITS){
  // Retain edit bookkeeping, not fetched box/report/transcript display data.
  EDITS.en={};
  const b=EDITS.editor;delete b.raw;b.boxes=[];
  delete b.tlspans;delete b.audioSugg;delete b.audioTx;b.playing=false;
  trimReviewDraft(EDITS);
 }
 stopPolling();disposeRecentLog();POLL_FAILURES=0;AUTO_REVIEW=null;REVIEW_REQUEST=null;
 VIEW_GEN++;CUR=id;
 resetReviewView();
 EDITS=REVIEW_DRAFTS.get(id);
 if(!EDITS){EDITS={en:{},enabled:{},manual:[],editor:emptyEditor(),busy:false,status:""};
  REVIEW_DRAFTS.set(id,EDITS);}
 EN=EDITS.en;MAN=EDITS.manual;BE=EDITS.editor;
 PHIST=[];PHPH="";LOGN=0;LOGE=null;LOGINIT=false;SHELLPH=null;
 detail.innerHTML='<div id="pollStatus" role="status" aria-live="polite" style="margin:8px 0;color:#fbbf24"></div><div id="reviewSaveStatus" role="status" aria-live="polite" style="margin:8px 0;color:#fbbf24"></div><div id="reviewAccess"></div><div id="reviewTrackStatus" role="status" aria-live="polite"></div><div id="reviewTrackActions"></div><div id="reviewResolveActions"></div>';
 saveStatus(EDITS,EDITS.status);renderTrackStatus(EDITS);

 refresh();
}

// One mounted view owns recent entry nodes, never a second transcript string.
function disposeRecentLog(){
 if(RECENT_LOG){RECENT_LOG.dispose();RECENT_LOG=null;}
}
function mountRecentLog(id,gen,element,note){
 const MAX_ENTRIES=800,MAX_UNITS=1048576,ENTRY_UNITS=8192;
 const SUFFIX="... [display entry truncated]",NL=String.fromCharCode(10);
 let entries=[],units=0,saved=null,frame=null,disposed=false;
 let omitted=false,truncated=false,displayTruncated=false,replaced=false,lost=false;
 let width=element.clientWidth,height=element.clientHeight,ownedTop=element.scrollTop;
 const owner={publish,dispose};
 const current=()=>!disposed&&RECENT_LOG===owner&&ownsView(id,gen)&&document.getElementById("log")===element;
 function status(){
  const text=[replaced?"Log history was replaced.":"",omitted?"Earlier log messages were omitted.":"",
   truncated?"Some log messages were truncated.":"",displayTruncated?"Some display entries were truncated.":"",
   lost?"Reading position was omitted; showing oldest retained messages.":""].filter(Boolean).join(" ");
  if(note.textContent!==text)note.textContent=text;
 }
 function capture(){
  const bottom=element.scrollHeight-element.clientHeight-element.scrollTop<=40;
  const top=element.getBoundingClientRect().top+element.clientTop;
  let entry=entries.find(e=>e.node.getBoundingClientRect().bottom>top);
  if(!entry)entry=entries[entries.length-1];
  return {bottom,seq:entry?entry.seq:null,offset:entry?top-entry.node.getBoundingClientRect().top:0};
 }
 function remember(){saved=capture();ownedTop=element.scrollTop;}
 function restore(anchor){
  if(anchor.bottom){element.scrollTop=element.scrollHeight;}
  else{
   const entry=entries.find(e=>e.seq===anchor.seq);
   if(entry){
    const rect=entry.node.getBoundingClientRect(),top=element.getBoundingClientRect().top+element.clientTop;
    // Preserve the entry and pixel offset, clamping an offset after rewrap.
    const offset=Math.min(anchor.offset,Math.max(0,rect.height-1));
    element.scrollTop=Math.max(0,Math.min(element.scrollHeight-element.clientHeight,
     element.scrollTop+rect.top-top+offset));
   }else{element.scrollTop=0;if(anchor.seq!==null)lost=true;}
  }
  remember();
 }
 function scroll(){
  if(!current()||Math.abs(element.scrollTop-ownedTop)<.5)return;
  lost=false;remember();status();
 }
 element.addEventListener("scroll",scroll,{passive:true});
 const observer=typeof ResizeObserver==="undefined"?null:new ResizeObserver(()=>{
  if(!current()||(width===element.clientWidth&&height===element.clientHeight))return;
  width=element.clientWidth;height=element.clientHeight;
  if(frame===null)frame=requestAnimationFrame(()=>{
   frame=null;if(!current())return;
   if(saved)restore(saved);status();
  });
 });
 if(observer)observer.observe(element);
 function entrySize(text){
  if(text.length<=ENTRY_UNITS)return text.length;
  let end=ENTRY_UNITS-SUFFIX.length;
  const a=text.charCodeAt(end-1),b=text.charCodeAt(end);
  if(a>=0xD800&&a<=0xDBFF&&b>=0xDC00&&b<=0xDFFF)end--;
  return end+SUFFIX.length;
 }
 function clearSelection(removed){
  if(!removed.length)return;
  const selection=window.getSelection?.();
  if(!selection||!element.contains(selection.anchorNode)||!element.contains(selection.focusNode))return;
  if(removed.some(e=>e.node.contains(selection.anchorNode)||e.node.contains(selection.focusNode))||
     selection.anchorNode===element||selection.focusNode===element)selection.removeAllRanges();
 }
 function publish(snapshot,replace,initial,modern){
  if(!current())return;
  const lines=snapshot.lines;
  if(replace){omitted=false;truncated=false;displayTruncated=false;replaced=!initial;lost=false;}
  if(modern){omitted=omitted||snapshot.base>0||snapshot.dropped>0;truncated=truncated||snapshot.truncated>0;}
  if(!replace&&!lines.length){status();return;}
  // Select only a surviving suffix, before creating or mounting its nodes.
  const floor=replace?Math.max(0,lines.length-400):0;
  const incoming=[];let total=0,start=lines.length;
  while(start>floor&&incoming.length<MAX_ENTRIES){
   const size=entrySize(lines[start-1]),next=total+size+(incoming.length?1:0);
   if(next>MAX_UNITS)break;
   incoming.push(size);total=next;start--;
  }
  let keep=entries.length;
  if(!replace&&start===0){
   while(keep>0&&incoming.length+entries.length-keep<MAX_ENTRIES){
    const next=total+entries[keep-1].units+(incoming.length+entries.length-keep?1:0);
    if(next>MAX_UNITS)break;
    total=next;keep--;
   }
  }
  // The final pre-mutation sample is after all polling awaits and validation.
  const anchor=replace?null:capture(),removed=entries.slice(0,keep);
  omitted=omitted||start>0||keep>0;
  clearSelection(removed);
  for(const entry of removed)entry.node.remove();
  entries.splice(0,keep);
  const fragment=document.createDocumentFragment();
  for(let i=start;i<lines.length;i++){
   const size=incoming[lines.length-1-i],source=lines[i];
   const clipped=source.length>ENTRY_UNITS;
   const node=document.createElement("span");node.dataset.seq=String(snapshot.from+i);
   node.appendChild(document.createTextNode(clipped?source.slice(0,size-SUFFIX.length)+SUFFIX:source));
   if(i<lines.length-1)node.appendChild(document.createTextNode(NL));
   fragment.appendChild(node);entries.push({seq:snapshot.from+i,node,units:size});
   displayTruncated=displayTruncated||clipped;
  }
  // Delimiters are distinct from stable content nodes, including empty entries.
  if(start<lines.length&&entries.length>lines.length-start){
   entries[entries.length-(lines.length-start)-1].node.appendChild(document.createTextNode(NL));
  }
  element.appendChild(fragment);units=total;
  if(replace){element.scrollTop=element.scrollHeight;remember();}
  else restore(anchor);
  status();
 }
 function dispose(){
  disposed=true;if(observer)observer.disconnect();if(frame!==null)cancelAnimationFrame(frame);
  element.removeEventListener("scroll",scroll);entries.length=0;units=0;saved=null;frame=null;
 }
 return owner;
}

function shellHtml(j){
 return `<div class="card" id="jobcard"><h2>${jobNameHtml(j.name)}
  <span class="badge" id="ph"></span><small id="eta"></small></h2>
 <progress id="prog" value="0" max="1"></progress>
 <div class="row" id="actions" style="margin-top:8px"></div>
 <div style="margin-top:8px;text-align:center"><img id="pimg"
   style="max-width:100%;border-radius:8px;display:none;margin:0 auto"></div>
 <div id="pcap" style="font-size:12px;color:#94a3b8"></div>
 <div id="logStatus" style="margin-top:8px;color:#94a3b8"></div>
 <div id="log" tabindex="0" aria-label="Job log" aria-describedby="logStatus" style="margin-top:8px"></div>
 <div class="warn" id="warnbox" style="display:none;margin-top:8px"></div>
 </div>`;
}

// Save As exports stay bound to the clicked job even while the picker is open.
let EXPORT_NAMES={id:null,video:null,report:null};
const CAN_SAVE_AS=!!(window.isSecureContext&&window.showSaveFilePicker);
const EXPORTS=new Map();
function exportControls(id,kind){
 const label=kind==="video"?"redacted video":"audit report";
 const path=kind==="video"?"download":"report";
 const direct=`<a href="api/jobs/${id}/${path}" onclick="exportDownloadStarted('${kind}')">Download ${label}</a>`;
 return `<div id="export-${kind}" data-job="${id}" class="export-item">
  <div class="export-toolbar">${CAN_SAVE_AS?`<button id="save-${kind}" class="${kind==='report'?'sec':''}" onclick="saveExportAs('${kind}',this)">Save ${label} as…</button>
   ${direct}`:direct}</div>
  <div id="export-${kind}-feedback" hidden>
   <progress id="export-${kind}-progress" max="1" aria-label="${label} save progress" style="width:100%"></progress>
   <div id="export-${kind}-status" style="font-size:12px;overflow-wrap:anywhere"></div>
   <div id="export-${kind}-live" role="status" aria-live="polite" aria-atomic="true"
    style="position:absolute;width:1px;height:1px;overflow:hidden;clip-path:inset(50%)"></div>
  </div></div>`;
}
function exportDownloadStarted(kind){
 if(!CUR)return;
 const key=CUR+":"+kind;
 // A direct download cannot observe disk completion or replace a running save.
 if(EXPORTS.get(key)?.active)return;
 EXPORTS.set(key,{id:CUR,kind,phase:"download",written:0,total:null,active:false});
 renderExportProgress();
}
function exportDuration(seconds){
 const s=Math.max(0,Math.floor(seconds));
 return s>=60?`${Math.floor(s/60)} min ${s%60} s`:`${s} s`;
}
function renderExportProgress(){
 const now=performance.now();
 for(const kind of ["video","report"]){
  const box=document.getElementById("export-"+kind),state=EXPORTS.get(CUR+":"+kind);
  if(!box||box.dataset.job!==CUR)continue;
  const button=document.getElementById("save-"+kind);
  if(button)button.disabled=!!state?.active;
  if(!state)continue;
  if(state.active&&state.renderedBox===box&&state.renderedPhase===state.phase&&now-state.renderedAt<250)continue;
  state.renderedBox=box;state.renderedPhase=state.phase;state.renderedAt=now;
  document.getElementById(`export-${kind}-feedback`).hidden=false;
  const bar=document.getElementById(`export-${kind}-progress`);
  if(state.total===null||state.phase==="download")bar.removeAttribute("value");
  else{bar.max=state.total||1;bar.value=state.written;}
  bar.hidden=state.phase==="download";
  let text="Download started — see browser downloads";
  if(state.phase!=="download"){
   const amount=Math.max(state.total||0,state.written);
   const power=amount>0?Math.min(3,Math.floor(Math.log10(amount)/3)):0;
   const unit=["B","KB","MB","GB"][power],scale=1000**power;
   const bytes=n=>`${(n/scale).toFixed(power?1:0)} ${unit}`;
   const elapsed=(now-state.start)/1000;
   const waiting=state.active&&state.phase!=="finalizing"&&now-state.lastWrite>=5000;
   let label=state.phase==="saved"?"Saved":state.phase==="failed"?"Save failed":
    state.phase==="finalizing"?"Finalizing…":state.phase==="choosing"?"Choose a destination…":
    waiting?"Waiting for data or disk…":`Saving ${kind==="video"?"video":"audit report"}`;
   const count=state.total===null?bytes(state.written):
    `${bytes(state.written)} / ${bytes(state.total)} (${state.total?Math.min(100,Math.floor(state.written/state.total*100)):100}%)`;
   text=`${label} — ${count} · ${exportDuration(((state.end??now)-state.start)/1000)} elapsed`;
   if(state.phase==="saving"&&!waiting&&elapsed>=3&&state.samples.length>1){
    // Retain one observation at/before the rolling ten-second boundary.
    while(state.samples.length>2&&state.samples[1][0]<=now-10000)state.samples.shift();
    const [t,b]=state.samples[0],rate=(state.written-b)/((now-Math.max(t,now-10000))/1000);
    if(rate>0){text+=` · ${bytes(rate)}/s`;
     if(state.total!==null&&state.written<state.total)
      text+=` · about ${exportDuration((state.total-state.written)/rate)} left`;}
   }
   if(state.error)text+=` · ${state.error}. Try Save As again or use Download.`;
  }
  document.getElementById(`export-${kind}-status`).textContent=text;
  // Visual updates run at 250ms; live announcements have their own 2s cadence.
  if(state.announcedPhase!==state.phase||now-(state.announcedAt??-Infinity)>=2000){
   document.getElementById(`export-${kind}-live`).textContent=text;
   state.announcedPhase=state.phase;state.announcedAt=now;
  }
 }
}
async function saveExportAs(kind,button){
 const id=CUR,name=EXPORT_NAMES[kind],path=kind==="video"?"download":"report";
 if(!id||EXPORT_NAMES.id!==id||!name||!["video","report"].includes(kind))return;
 const key=id+":"+kind,previous=EXPORTS.get(key);
 if(previous?.active)return;
 const start=performance.now();
 const state={id,kind,phase:"choosing",active:true,written:0,total:null,start,
  lastWrite:start,samples:[[start,0]]};
 EXPORTS.set(key,state);button.disabled=true;renderExportProgress();
 let reader,writable,timer;
 try{
  // Invoke synchronously from the click, before the first network await.
  let handle;
  try{handle=await window.showSaveFilePicker({suggestedName:name});}
  catch(e){if(e.name!=="AbortError")throw e;
   if(previous)EXPORTS.set(key,previous);else EXPORTS.delete(key);
   if(CUR===id){document.getElementById(`export-${kind}-feedback`).hidden=!previous;
    renderExportProgress();}
   return;
  }
  state.phase="saving";state.start=state.lastWrite=performance.now();
  state.samples=[[state.start,0]];
  timer=setInterval(renderExportProgress,250);
  const response=await fetch(`api/jobs/${encodeURIComponent(id)}/${path}`);
  if(!response.ok)throw new Error(response.status===423?"encryption vault is locked":`server returned HTTP ${response.status}`);
  if(!response.body)throw new Error("browser did not provide a file stream");
  reader=response.body.getReader();
  const length=response.headers.get("Content-Length"),encoding=response.headers.get("Content-Encoding");
  // Fetch decodes encoded responses; their transfer length is not a disk total.
  if((!encoding||encoding.toLowerCase()==="identity")&&length!==null&&/^[0-9]+$/.test(length)){
   const total=Number(length);if(Number.isSafeInteger(total))state.total=total;
  }
  writable=await handle.createWritable();
  for(;;){
   const {done,value}=await reader.read();if(done)break;
   await writable.write(value); // backpressure: accepted bytes only
   const now=performance.now();state.written+=value.byteLength;state.lastWrite=now;
   // Coalesce observations to 250ms buckets; keep a bounded ten-second window.
   if(state.samples.length===1||Math.floor(now/250)!==Math.floor(state.samples[state.samples.length-1][0]/250))
    state.samples.push([now,state.written]);
   else state.samples[state.samples.length-1]=[now,state.written];
   while(state.samples.length>2&&state.samples[1][0]<=now-10000)state.samples.shift();
  }
  if(state.total!==null&&state.written!==state.total)throw new Error("received byte count does not match Content-Length");
  state.phase="finalizing";renderExportProgress();
  await writable.close();
  state.phase="saved";
 }catch(e){
  state.phase="failed";state.error=e.message||String(e);
  if(reader)try{await reader.cancel();}catch(_){}
  if(writable)try{await writable.abort();}catch(_){}
 }finally{
  if(timer)clearInterval(timer);
  if(reader)reader.releaseLock();
  state.active=false;state.end=performance.now();
  button.disabled=false;renderExportProgress();
 }
}

async function refreshCycle(cycle){
 const {id,gen}=cycle;
 const current=()=>ownsView(id,gen)&&POLL_CYCLE===cycle;
 const j=await pollJson("api/jobs/"+id,cycle);
 if(!ownsView(id,gen)||!current())return;
 if(!j||typeof j.name!=="string"||typeof j.phase!=="string"||
    typeof j.progress!=="number"||!Number.isFinite(j.progress))throw new Error("Invalid job update");
 EXPORT_NAMES={id,video:j.download_name,report:j.report_name};
 if(SHELLPH===null){
  detail.insertAdjacentHTML("afterbegin",shellHtml(j));SHELLPH="";
  RECENT_LOG=mountRecentLog(id,gen,document.getElementById("log"),document.getElementById("logStatus"));
  const im=document.getElementById("pimg");
  im.onload=()=>{im.style.display="block";};   // show only once a real frame arrives
  im.onerror=()=>{im.style.display="none";};   // 404 before first preview: stay hidden
 }

 // progress + ETA (updated in place — nothing is rebuilt).
 // The server sends a smoothed per-stage estimate (j.eta, seconds) built
 // from the stage's recent processing rate — prefer it. The old
 // client-side extrapolation from bar movement stays only as a fallback
 // (rehydrated jobs mid-phase), with its history reset on phase change so
 // it never extrapolates a scan-speed rate across the render phase.
 if(PHPH!==j.phase){
  if(PHPH==='paused'&&j.phase!=='paused'){
   BE_OPEN_INTENT++;beUnmount();disposeReview();document.getElementById('review')?.remove();resetReviewView();
  }
  PHIST=[];PHPH=j.phase;
  // Phase eligibility is separate from view identity. Leave-and-return creates
  // a new token; slow same-phase review requests remain eligible.
  const pendingManual=REVIEW_REQUEST?.pending&&REVIEW_REQUEST.manual;
  AUTO_REVIEW=(j.phase==="review"||j.phase==="paused"&&j.checkpoint_unfinished===true)?{id,gen,phase:j.phase,state:pendingManual?"loading":
   EDITS?.reviewEditorGen===gen?"deferred":"idle"}:null;
  renderReviewAccess();
 }
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

 // Only a fully accepted body publishes to the mount-owned recent transcript.
 let nl=await pollJson(`api/jobs/${id}/log?from=${LOGN}${LOGE===null?"":"&epoch="+encodeURIComponent(LOGE)}`,cycle);
 if(!ownsView(id,gen)||!current())return;
 const index=n=>Number.isSafeInteger(n)&&n>=0;
 const validLog=n=>n&&index(n.from)&&index(n.len)&&Array.isArray(n.lines)&&
  n.lines.every(line=>typeof line==="string");
 if(!validLog(nl))throw new Error("Invalid log update");
 const modern=["epoch","base","reset","dropped","truncated"].some(k=>k in nl);
 let replace=false,lines=nl.lines,nextEpoch=null;
 if(modern){
  if(!index(nl.base)||nl.base>nl.from||nl.from>nl.len||lines.length!==nl.len-nl.from||
     typeof nl.epoch!=="string"||!/^[A-Za-z0-9_-]{1,128}$/.test(nl.epoch)||
     ![null,"stale","future","epoch"].includes(nl.reset)||!index(nl.dropped)||!index(nl.truncated))
   throw new Error("Invalid log snapshot");
  const expected=LOGE!==null&&nl.epoch!==LOGE?"epoch":LOGN<nl.base?"stale":LOGN>nl.len?"future":null;
  if(nl.reset!==expected||nl.from!==(expected?nl.base:LOGN))throw new Error("Invalid log reset");
  replace=!LOGINIT||nl.reset!==null;
  nextEpoch=nl.epoch;
 }else{
  // Explicit old-backend branch: its shrink response may have from > len.
  if(nl.len<LOGN){
   replace=true;
   if(nl.len){
    nl=await pollJson(`api/jobs/${id}/log?from=0`,cycle);
    if(!ownsView(id,gen)||!current())return;
    if(!validLog(nl)||["epoch","base","reset","dropped","truncated"].some(k=>k in nl))
     throw new Error("Invalid legacy log update");
   }
  }
  if((nl.from!==(replace?0:LOGN)&&nl.len!==0)||nl.lines.length!==Math.max(0,nl.len-nl.from))
   throw new Error("Invalid log cursor");
  replace=replace||!LOGINIT;lines=nl.lines;
 }
 RECENT_LOG.publish(nl,replace,!LOGINIT,modern);
 LOGN=nl.len;LOGE=nextEpoch;LOGINIT=true;

 // live preview: swap src in place (browser keeps old frame until new loads)
 const img=document.getElementById("pimg");
 if(j.phase=="scanning"){
  img.src=`api/jobs/${CUR}/preview.jpg?x=${Date.now()}`;
 }

 const wb=document.getElementById("warnbox");
 if(j.error){wb.style.display="block";wb.textContent=j.error;}
 else wb.style.display="none";

 CANCEL_KIND=j.phase==="stopped"?2:(j.phase==="scanning"&&j.progress>0)?(j.stop_supported?1:3):0;
 // action buttons rebuilt ONLY when the phase changes
 const shellPhase=j.phase+(j.checkpoint_enabled?':checkpoint':'')+(j.checkpoint_stopping?':stopping':'')
  +(j.stop_supported?':stoppable':'')+(j.stopping?':stopping-scan':'');
 if(SHELLPH!==shellPhase){
  SHELLPH=shellPhase;
  let a="";
  if(j.phase=="scanning"||j.phase=="rendering"){
   // Stop (and Continue, once stopped) always sit on the left, Cancel right
   if(j.phase==="scanning"&&j.stop_supported)
    a=`<button id="scanStop" class="sec" title="Stop the scan and free the GPU. Continue later from this point." onclick="stopScan()" ${j.stopping?'disabled':''}>${j.stopping?'Stopping…':'Stop'}</button>`;
   a+=`<button class="danger" onclick="cancelJob()">Cancel</button>`;
  }
  if(j.phase==="stopped")
   a=`<div style="width:100%"><b>Stopped at ${stoppedPct(j)}% (frame ${j.stopped_frame} of ${j.stopped_total})</b></div>
    <div style="width:100%;font-size:12px;color:#9ca3af">Progress is saved in the
    job folder. Continue scan carries on from here; the result is the same as an
    uninterrupted scan.</div>
    <button onclick="continueScan(CUR)">Continue scan</button>
    <button class="sec" onclick="cancelJob()">Cancel scan</button>`;
  if(j.phase==="scanning"&&j.checkpoint_enabled)
   a+=`<button id="checkpointStop" class="sec" onclick="stopCheckpoint()" ${j.checkpoint_stopping?'disabled':''}>${j.checkpoint_stopping?'Stopping…':'Stop &amp; Review'}</button>`;
  if((j.phase=="error"||j.phase=="cancelled")&&!j.checkpoint_unfinished&&j.failed_action==="render")
   a=`<button onclick="retryRender(CUR)">Retry render</button>
    <button class="sec" onclick="loadReview()">Back to review</button>
    <div style="width:100%;font-size:12px;color:#9ca3af">The render did not
    finish, but the scan and your review choices are saved. <b>Retry render</b>
    renders again with them (if the disk was full, free some space first).
    <b>Back to review</b> lets you change choices first; then press Save edits
    &amp; render.</div>
    <div style="width:100%;font-size:12px"><a href="#" onclick="retryJob(CUR,true);return false">Scan again from the start</a>
    <span style="color:#9ca3af">— discards your review choices</span></div>`;
  else if((j.phase=="error"||j.phase=="cancelled")&&!j.checkpoint_unfinished)
   a=`<button onclick="retryJob(CUR)">Retry scan (no re-upload)</button>
    <div style="width:100%;font-size:12px;color:#9ca3af">The uploaded file
    is still on the server — Retry re-runs the scan without uploading it
    again. Delete the job (&#128465;&#65039; in the list) to free its disk
    space.</div>`;
  if(j.phase=="paused")
   a=`<div>Scan paused. Review the processed portion before resuming.</div>`;
  if(j.phase=="review"){
   // no interstitial button: review is the ONLY next step after a scan,
   // so open it directly — both on a live scan finishing and on
   // selecting a job that is already waiting in review
   a="";
   // Automatic review starts below, outside the bounded polling cycle.
  }
  if(j.phase=="done"&&j.has_output)
   a=`<div class="export-grid">${exportControls(id,"video")}${exportControls(id,"report")}</div>
    ${CAN_SAVE_AS?"":'<div style="width:100%;font-size:12px;color:#94a3b8">To choose a destination, enable “Ask where to save each file” in your browser download settings.</div>'}
    <div class="export-actions"><button class="sec" onclick="loadReview()">Re-open review</button>
    <button class="sec" onclick="loadCompare()">Compare before/after</button>
    <button class="sec" onclick="loadBoxEdit()">Preview &amp; edit blur boxes</button></div>
    <div class="warn" style="width:100%">Reminder: scrub the result before
    sharing. This tool is best-effort, not a compliance guarantee.</div>
    <div id="compare" style="width:100%"></div>
    <div id="beslot_done" style="width:100%"></div>`;
  const actions=document.getElementById("actions");beUnmountIn(actions);actions.innerHTML=a;
  if(j.phase=="done"&&j.assisted_letters){LETTER_GAPS=null;startLetterGapLoad(id);}
  if(j.phase!="scanning")img.style.display="none";
 }
 renderExportProgress();
 if(AUTO_REVIEW&&AUTO_REVIEW.state==="idle"){
  const auto=AUTO_REVIEW;auto.state="loading";
  const pending=loadReview(auto),request=REVIEW_REQUEST;
  pending.catch(()=>{
   if(AUTO_REVIEW===auto&&REVIEW_REQUEST===request&&ownsView(id,gen)&&
      auto.state==="loading"&&EDITS?.reviewEditorGen!==gen){
    auto.state="idle";pollStatus("Review could not load — retrying job updates.");
   }
  });
 }
 loadJobs();
}

let BE=emptyEditor();
// Display geometry belongs to this DOM mount, never to a retained draft.
let BE_VIEW=null;
// One page-wide cycle owns fetch, body, candidate decode and cleanup. Retirement
// never releases native decode early; only the latest desired request survives.
let BE_OPEN_INTENT=0;
const EDIT_SAMPLE_IO={active:null,wanted:null};
function beSampleCurrent(view,serial){return !!view&&view.current()&&view.serial===serial&&!view.editor.playing;}
function beInvalidateSample(view,message){
 if(!view)return;
 view.serial++;view.readySample=null;view.loading=true;view.transform=null;view.quadEdit=null;
 bePlateRetire(view,'Frame changed. Search again after inspecting this frame.');
 beEndGesture(view.editor,view.cv);view.editor.sel=-1;
 for(const id of ['beRm','beTimes']){const e=document.getElementById(id);if(e)e.style.display='none';}
 if(view.current()){
  const label=document.getElementById('beL');if(label&&message)label.textContent=message;
  beQuadControls(view);beDraw();
 }
}
function beVector(value,n){return Array.isArray(value)&&value.length===n&&value.every(x=>typeof x==='number'&&Number.isFinite(x));}
function beBase(base){return !!base&&beVector(base.cbox,4)&&beVector(base.span,3);}
function bePrecondition(sample){const {source_ref,timeline_eq,policy,index,width,height,offset}=sample;
 return copyEdit({version:1,source_ref,timeline_eq,policy,index,width,height,offset});}
function beValidateSample(body,t,checkpoint=null){
 const s=body?.sample,hex=x=>typeof x==='string'&&/^[a-f0-9]{64}$/.test(x);
 if(body?.version!==1||!s||typeof s.source_ref!=='string'||s.source_ref.length<1||s.source_ref.length>128||
 !hex(s.timeline_eq)||s.policy!=='opencv-ffmpeg-zero-cfr-v1'||!Number.isSafeInteger(s.index)||s.index<0||
 ![s.width,s.height].every(n=>Number.isSafeInteger(n)&&n>0)||!Number.isInteger(s.stream)||s.stream<0||
 ![s.requested_s,s.canonical_s,s.observed_s].every(n=>typeof n==='number'&&Number.isFinite(n))||s.requested_s!==t||
 s.canonical_s<0||!beVector(s.offset,2)||!sameEdit(s.origin,[0,0])||!Array.isArray(body.boxes)||
 body.image?.mime!=='image/jpeg'||typeof body.image.base64!=='string'||
 !/^[/]9j[/][A-Za-z0-9+/]*={0,2}$/.test(body.image.base64))throw Error('Invalid exact sample response');
 const seen=new Set();
 for(const row of body.boxes){
  if(!Number.isSafeInteger(row.i)||row.i<0||seen.has(row.i)||!hex(row.row_context_eq)||!beBase(row.base)||
   !beVector(row.box,4)||row.t_start!==row.base.span[0]||row.t_end!==row.base.span[1]||
   !row.box.every((v,i)=>Math.abs(v-row.base.cbox[i]-s.offset[i%2])<1e-8)||
   typeof row.enabled!=='boolean'||typeof row.category!=='string')throw Error('Invalid exact sample row');
  seen.add(row.i);
  const hasBounds=Object.prototype.hasOwnProperty.call(row,'scan_frame_bounds');
  if(checkpoint&&!hasBounds)throw Error('Missing checkpoint row bounds');
  if(hasBounds){
   const bounds=row.scan_frame_bounds;
   if(bounds!==null&&
      (!Array.isArray(bounds)||bounds.length!==2||!bounds.every(Number.isSafeInteger)||
       bounds[0]<0||bounds[0]>s.index||s.index>=bounds[1]||checkpoint&&bounds[1]>checkpoint.frames))throw Error('Invalid checkpoint row bounds');
  }
 }
 if(checkpoint&&(t<0||t>=checkpoint.duration||s.index>=checkpoint.frames||
    s.index!==Math.floor(t*checkpoint.fps)||s.canonical_s!==s.index/checkpoint.fps))throw Error('Sample outside processed prefix');
 return {sample:copyEdit(s),precondition:bePrecondition(s),rows:copyEdit(body.boxes),image:body.image};
}
async function beApplySample(view,serial,data){
 let url=null,installed=false;
 try{
  const bytes=Uint8Array.from(atob(data.image.base64),c=>c.charCodeAt(0));
  url=URL.createObjectURL(new Blob([bytes],{type:'image/jpeg'}));
  const candidate=new Image();candidate.src=url;await candidate.decode();
  if(!beSampleCurrent(view,serial))return;
  if(candidate.naturalWidth!==data.sample.width||candidate.naturalHeight!==data.sample.height)throw Error('Exact image dimensions changed');
  const img=view.img;img.src=url;await img.decode();
  if(!beSampleCurrent(view,serial))return;
  if(!img.complete||img.naturalWidth!==data.sample.width||img.naturalHeight!==data.sample.height||img.src!==url)
   throw Error('Exact image is not displayed');
  view.loading=false;
  if(!view.sync())throw Error('Exact image has no visible transform; inspect again when visible');
  const previous=view.imageURL;view.imageURL=url;installed=true;
  if(previous&&previous!==url)URL.revokeObjectURL(previous);
  const b=view.editor;b.raw=data.rows;b.ox=data.sample.offset[0];b.oy=data.sample.offset[1];b.t=data.sample.canonical_s;
  view.readySample={serial,...data,imageURL:url};
  const inspection=view.plate.inspect;
  if(inspection&&inspection.serial===serial){
   view.plate.inspect=null;
   const s=data.sample,old=inspection.sample;
   if(s.index===inspection.index&&bePlateSameSource(s,old)){
    inspection.batch.index=s.index;view.plate.batch=inspection.batch;
    view.plate.message=`Frame ${s.index} is ready. Search this frame to see its suggestions.`;
   }else view.plate.message='The source or frame changed since the sampled search. Inspect and search again.';
  }
  const label=document.getElementById('beL');if(label)label.textContent=`requested ${fmtTime(data.sample.requested_s)} · frame ${data.sample.index} at ${fmtTime(b.t)}`;
  beFilter();beQuadControls(view);beDraw();beTLDraw();bePlateRender(view);
 }finally{if(url&&!installed)URL.revokeObjectURL(url);}
}
function beRequestSample(view,t){
 if(!view||!view.current()||!Number.isFinite(t))return;
 if(view.checkpoint&&(PHPH!=='paused'||t<0||t>=view.checkpoint.duration))return;
 beInvalidateSample(view,`Inspecting ${fmtTime(t)}…`);
 EDIT_SAMPLE_IO.wanted={view,serial:view.serial,t};
 return bePumpSamples();
}
function bePumpSamples(){
 if(EDIT_SAMPLE_IO.active)return EDIT_SAMPLE_IO.active.promise;
 const request=EDIT_SAMPLE_IO.wanted;if(!request)return;
 EDIT_SAMPLE_IO.wanted=null;
 const {view,serial,t}=request;
 EDIT_SAMPLE_IO.active=request;
 request.promise=(async()=>{
  try{
   if(!beSampleCurrent(view,serial))return;
   const response=await fetch(`api/jobs/${view.id}/edit_sample?t=${t}`);
   if(!response.ok){
    // Error headers do not settle the cycle: retain its slot through body cleanup.
    try{await response.text();}catch(_){}
    throw Error(`Exact sample unavailable (HTTP ${response.status}). Inspect again to retry.`);
   }
   const body=await response.json();
   if(!beSampleCurrent(view,serial))return;
   await beApplySample(view,serial,beValidateSample(body,t,view.checkpoint));
  }catch(error){
   if(beSampleCurrent(view,serial)){
    view.readySample=null;view.loading=true;view.transform=null;
    const label=document.getElementById('beL');if(label)label.textContent=String(error.message||error);
    if(view.plate.inspect?.serial===serial){view.plate.inspect=null;view.plate.message='The sampled frame could not be inspected. Try again.';bePlateRender(view);}
    beDraw();
   }
  }finally{if(EDIT_SAMPLE_IO.active===request){EDIT_SAMPLE_IO.active=null;bePumpSamples();}}
 })();
 return request.promise;
}
function beReady(view=BE_VIEW){
 if(!view||!view.current()||view.editor.playing||!view.img.isConnected||!view.cv.isConnected)return false;
 if(view.checkpoint&&PHPH!=='paused')return false;
 const ready=view.readySample;
 if(!ready||ready.serial!==view.serial||ready.imageURL!==view.imageURL||view.img.src!==view.imageURL||
 !view.img.complete||view.img.naturalWidth!==ready.sample.width||view.img.naturalHeight!==ready.sample.height)return false;
 const tr=view.sync(),r=view.cv.getBoundingClientRect();
 const valid=!!tr&&tr.media===view.img&&tr.sw===ready.sample.width&&tr.sh===ready.sample.height&&
 [r.width,r.height].every(n=>Number.isFinite(n)&&n>0);
 if(!valid)beEndGesture(view.editor,view.cv);return valid;
}
function beCaptureGeometry(view,row){
 if(!beReady(view)||!row||!view.readySample.rows.includes(row))return false;
 const b=view.editor,old=b.geometry[row.i];
 const hasBounds=Object.prototype.hasOwnProperty.call(row,'scan_frame_bounds');
 if(row.category==='plate'&&beQuadRecord(row.manual_plate_quad)&&!beQuadWitness(row.quad_baseline,row.manual_plate_quad)){
  saveStatus(EDITS,'The plate baseline is unavailable; inspect the frame again before changing geometry.');return false;
 }
 if(old)return old.precondition.source_ref===view.readySample.sample.source_ref&&
 old.precondition.timeline_eq===view.readySample.sample.timeline_eq&&old.precondition.row_context_eq===row.row_context_eq&&
 Object.prototype.hasOwnProperty.call(old.precondition,'scan_frame_bounds')===hasBounds&&
 (!hasBounds||sameEdit(old.precondition.scan_frame_bounds,row.scan_frame_bounds));
 b.geometry[row.i]={precondition:{...copyEdit(view.readySample.precondition),row_context_eq:row.row_context_eq,base:copyEdit(row.base),
  ...(hasBounds?{scan_frame_bounds:copyEdit(row.scan_frame_bounds)}:{}),
  ...(row.category==='plate'&&beQuadHash(row.quad_context_eq)?{quad_context_eq:row.quad_context_eq}:{}),
  ...(row.category==='plate'&&Object.prototype.hasOwnProperty.call(row,'quad_baseline')?{quad_baseline:row.quad_baseline}:{})},
  quadBaseline:row.category==='plate'&&beQuadRecord(row.manual_plate_quad)?copyEdit(row.manual_plate_quad):null,
  quadStream:row.category==='plate'?view.readySample.sample.stream:null};
 return true;
}
function beQuadHash(value){return typeof value==='string'&&/^[a-f0-9]{64}$/.test(value);}
function beQuadValid(points,width,height){
 if(!Array.isArray(points)||points.length!==4||!Number.isSafeInteger(width)||!Number.isSafeInteger(height))return false;
 if(!points.every(p=>beVector(p,2)&&p[0]>=0&&p[0]<=width&&p[1]>=0&&p[1]<=height))return false;
 for(let i=0;i<4;i++){
  const a=points[i],b=points[(i+1)%4],c=points[(i+2)%4];
  if(!((b[0]-a[0])*(c[1]-b[1])-(b[1]-a[1])*(c[0]-b[0])>0))return false;
 }
 const q=points.map(p=>p.map(Math.round));let area=0;
 for(let i=0;i<4;i++)area+=q[i][0]*q[(i+1)%4][1]-q[(i+1)%4][0]*q[i][1];
 return Number.isFinite(area)&&area>0;
}
function beQuadRecord(q){
 const keys=(o,k)=>!!o&&sameEdit(Object.keys(o).sort(),k.slice().sort());
 if(!keys(q,['version','points','source','frame'])||!keys(q.source,['sha256','stream','width','height'])||
  !keys(q.frame,['index','fps','count','policy','timeline_eq'])||q.version!==1||!q.source||!q.frame||!beQuadHash(q.source.sha256)||
  !Number.isSafeInteger(q.source.stream)||q.source.stream<0||!Number.isSafeInteger(q.source.width)||q.source.width<=0||
  !Number.isSafeInteger(q.source.height)||q.source.height<=0||!Number.isSafeInteger(q.frame.index)||q.frame.index<0||
  !Number.isSafeInteger(q.frame.count)||q.frame.count<=q.frame.index||typeof q.frame.fps!=='number'||!Number.isFinite(q.frame.fps)||q.frame.fps<=0||
  q.frame.policy!=='opencv-ffmpeg-zero-cfr-v1'||!beQuadHash(q.frame.timeline_eq)||!Array.isArray(q.points)||
  q.points.length!==4||!q.points.every(p=>beVector(p,2)&&p.every(v=>v>=0&&v<=1)))return false;
 return beQuadValid(q.points.map(p=>[p[0]*q.source.width,p[1]*q.source.height]),q.source.width,q.source.height);
}
function beSameJson(a,b){
 if(a===b)return true;
 if(!a||!b||typeof a!=='object'||typeof b!=='object'||Array.isArray(a)!==Array.isArray(b))return false;
 const ak=Object.keys(a).sort(),bk=Object.keys(b).sort();
 return sameEdit(ak,bk)&&ak.every(k=>beSameJson(a[k],b[k]));
}
function beQuadWitness(token,record){
 if(!beQuadRecord(record))return token===null;
 if(typeof token!=='string'||token.length===0||token.length>16384)return false;
 try{return beSameJson(JSON.parse(token),record);}catch(_){return false;}
}
function beQuadForSample(q,s){return beQuadRecord(q)&&q.source.width===s.width&&q.source.height===s.height&&
 q.source.stream===s.stream&&q.frame.index===s.index&&q.frame.timeline_eq===s.timeline_eq;}
function beQuadControls(view=BE_VIEW){
 const button=document.getElementById('beQuad'),reset=document.getElementById('beQuadReset'),note=document.getElementById('beQuadStatus');
 if(!button||!reset||!note)return;
 const row=view?.editor?.raw?.find(r=>r.i===view.editor.sel),plate=!view?.checkpoint&&row?.category==='plate';
 button.style.display=reset.style.display=note.style.display=plate?'':'none';if(!plate)return;
 const ready=!!view?.current()&&!!view.readySample&&!view.loading&&!view.editor.playing;
 const family=view.editor.geometry[row.i],sample=view.readySample?.sample;
 const wrongFrame=!!(ready&&family&&(family.precondition.index!==sample.index||family.precondition.source_ref!==sample.source_ref||
  family.precondition.timeline_eq!==sample.timeline_eq||family.precondition.row_context_eq!==row.row_context_eq));
 const allowed=ready&&!wrongFrame&&beQuadHash(row.quad_context_eq)&&['ready','verification_required'].includes(row.quad_edit_eligibility);
 button.disabled=!allowed;reset.disabled=!allowed;
 button.textContent=view.quadEdit?'Done editing corners':'Edit plate corners';
 let message='Corners apply only to this inspected frame; other frames keep the existing mask. Render padding still applies.';
 if(wrongFrame)message='Pending geometry belongs to another frame or source. Save or discard it before editing these corners.';
 else if(!allowed)message='Plate corners unavailable for this source or frame; the existing mask is retained.';
 else if(row.quad_edit_eligibility==='verification_required')message+=' Source identity will be verified on Save.';
 if(allowed&&row.quad_eligibility==='unverified')message+=' Saved corners are unverified and are not shown; new corners replace them.';
 else if(allowed&&row.quad_eligibility==='other_frame')message+=' Saved corners belong to another frame; new corners replace them.';
 else if(allowed&&['unsupported','unavailable'].includes(row.quad_eligibility))message+=' Saved corners are unavailable and are not shown; new corners replace them.';
 if(view.editor.ov[row.i]&&!sameEdit(view.editor.ov[row.i],row.base.cbox)&&!(row.i in view.editor.quads))
  message+=' The pending box change restores the full plate mask unless new corners are saved.';
 note.textContent=message;
}
function beQuadCapture(view,row){
 if(!beReady(view)||!row||row.category!=='plate'||!beQuadHash(row.quad_context_eq)||
  !['ready','verification_required'].includes(row.quad_edit_eligibility))return false;
 const old=view.editor.geometry[row.i],sample=view.readySample.sample;
 if(old&&(old.precondition.index!==sample.index||old.precondition.quad_context_eq&&old.precondition.quad_context_eq!==row.quad_context_eq)){
  saveStatus(EDITS,'Save or discard the earlier geometry before editing corners on another frame.');return false;
 }
 if(!beCaptureGeometry(view,row))return false;
 const family=view.editor.geometry[row.i];
 if(!family.precondition.quad_context_eq)family.precondition.quad_context_eq=row.quad_context_eq;
 return true;
}
function beQuadMode(){
 const view=BE_VIEW;if(!beReady(view))return;const b=view.editor,row=b.raw?.find(r=>r.i===b.sel);
 if(!row||row.category!=='plate'||!beQuadHash(row.quad_context_eq)||!['ready','verification_required'].includes(row.quad_edit_eligibility))return;
 if(view.quadEdit){view.quadEdit=null;beEndGesture(b,view.cv);beQuadControls(view);beDraw();return;}
 const family=b.geometry[row.i],sample=view.readySample.sample;
 if(family&&(family.precondition.index!==sample.index||family.precondition.row_context_eq!==row.row_context_eq||
  family.precondition.source_ref!==sample.source_ref||family.precondition.timeline_eq!==sample.timeline_eq)){
  saveStatus(EDITS,'Save or discard the earlier geometry before editing corners on another frame.');return;
 }
 const pending=b.quads[row.i],changed=b.ov[row.i]&&!sameEdit(b.ov[row.i],row.base.cbox);
 let points;
 if(pending?.points)points=copyEdit(pending.points);
 else if(!(row.i in b.quads)&&!changed&&row.quad_eligibility==='eligible_sdr_frame'&&beQuadForSample(row.manual_plate_quad,sample))
  points=row.manual_plate_quad.points.map(p=>[p[0]*sample.width,p[1]*sample.height]);
 else{
  const box=b.boxes.find(x=>x.i===row.i)?.box;if(!box)return;
  const [x0,y0,x1,y1]=box,clamp=(v,max)=>Math.max(0,Math.min(max,v));
  points=[[clamp(x0,sample.width),clamp(y0,sample.height)],[clamp(x1,sample.width),clamp(y0,sample.height)],
   [clamp(x1,sample.width),clamp(y1,sample.height)],[clamp(x0,sample.width),clamp(y1,sample.height)]];
 }
 if(!beQuadValid(points,sample.width,sample.height)){saveStatus(EDITS,'The visible plate box cannot initialize four valid corners.');return;}
 bePlateDiscardRegion(view);bePlateRender(view);
 b.add=false;b.trk=false;document.getElementById('beAdd')?.classList.remove('on');
 document.getElementById('beTrk')?.classList.remove('on');beEndGesture(b,view.cv);view.quadEdit={row,serial:view.serial,points};
 beQuadControls(view);beDraw();
}
function beQuadReset(){
 const view=BE_VIEW;if(!beReady(view))return;const b=view.editor,row=b.raw?.find(r=>r.i===b.sel);
 if(!row||row.category!=='plate'||!(row.i in b.quads)&&!Object.prototype.hasOwnProperty.call(row,'manual_plate_quad'))return;
 if(!beQuadCapture(view,row))return;
 b.quads[row.i]=null;view.quadEdit=null;beEndGesture(b,view.cv);reviewResolveActions(EDITS);
 beQuadControls(view);beDraw();
}
function beNewBox(view,box,t0,t1){
 if(!beReady(view))return false;const s=view.readySample.sample;
 return beVector(box,4)&&box[0]>=0&&box[1]>=0&&box[2]<=s.width&&box[3]<=s.height&&box[2]>box[0]&&box[3]>box[1]&&
 [t0,t1].every(Number.isFinite)&&t0>=0&&t1>t0&&t1<=view.editor.dur&&t0<=s.canonical_s&&s.canonical_s<=t1;
}

function bePlateSameSource(a,b){
 return !!a&&!!b&&a.source_ref===b.source_ref&&a.timeline_eq===b.timeline_eq&&
  a.policy===b.policy&&a.width===b.width&&a.height===b.height;
}
function bePlateBatchCurrent(view,batch){
 const s=view?.readySample?.sample;
 return !!batch&&beReady(view)&&s.index===batch.index&&bePlateSameSource(s,batch.sample.sample);
}
function bePlateRender(view){
 if(!view?.current())return;
 const p=view.plate,run=document.getElementById('bePlateRun'),cancel=document.getElementById('bePlateCancel');
 const status=document.getElementById('bePlateStatus'),list=document.getElementById('bePlateResults'),
       actions=document.getElementById('bePlateActions'),samples=document.getElementById('bePlateSamples'),
       sampleRun=document.getElementById('bePlateSampleRun');
 if(!run||!cancel||!status||!list||!actions||!samples||!sampleRun)return;
 run.disabled=!!p.request||!beReady(view);
 sampleRun.disabled=run.disabled;
 cancel.hidden=!p.request||p.request.cancelRequested;
 status.textContent=p.message;list.replaceChildren();actions.replaceChildren();samples.replaceChildren();
 p.rows.forEach((row,i)=>{
  const button=document.createElement('button');button.type='button';button.className='sec';
  button.textContent=`Suggestion ${i+1} · ${row.match==='full_equal'?'full text':'fragment'} match`;
  button.setAttribute('aria-pressed',String(p.selected===i));
  if(p.selected===i)button.style.outline='2px solid #22d3ee';
  button.onclick=()=>{
   if(!view.current()||!beReady(view))return;
   bePlateDiscardRegion(view);
   p.selected=i;p.message='Selected suggestion is approximate. Inspect it and adjust a region before tracking.';bePlateRender(view);beDraw();
  };
  list.appendChild(button);
 });
 if(p.selected>=0&&p.sample===view.readySample&&beReady(view)){
  const action=document.createElement('button');action.type='button';action.className='sec';
  if(p.region){
   action.textContent='Track this region';action.onclick=bePlateTrack;
   const discard=document.createElement('button');discard.type='button';discard.className='sec';
   discard.textContent='Cancel region';discard.onclick=()=>{bePlateDiscardRegion(view);p.message='Region discarded. No tracking started.';bePlateRender(view);beDraw();};
   actions.append(action,discard);
  }else{
   action.textContent='Adjust for tracking';action.onclick=bePlatePrepare;actions.appendChild(action);
  }
 }
 if(bePlateBatchCurrent(view,p.batch)){
  for(const frame of p.batch.frames){
   const button=document.createElement('button');button.type='button';button.className='sec';
   button.disabled=!!p.request;
   button.textContent=`Inspect frame ${frame.index} · ${fmtTime(frame.time_s)} · ${frame.matches} ${frame.matches===1?'suggestion':'suggestions'}${frame.truncated?' (truncated)':''}`;
   button.onclick=()=>bePlateInspectSample(view,frame);samples.appendChild(button);
  }
 }
}
function bePlateInspectSample(view,frame){
 const p=view?.plate,batch=p?.batch;
 if(!batch||p.request||!view.current()||!bePlateBatchCurrent(view,batch)||!batch.frames.includes(frame))return;
 const slider=document.getElementById('beT');if(slider)slider.value=frame.seek_s;
 beRequestSample(view,frame.seek_s);
 p.inspect={serial:view.serial,index:frame.index,sample:batch.sample.sample,batch};
 p.message=`Inspecting frame ${frame.index}. Search this frame to see its suggestions.`;
 bePlateRender(view);
}
function bePlateDiscardRegion(view){
 const p=view?.plate;if(!p?.region)return;
 beEndGesture(view.editor,view.cv);
 p.region=null;
}
function bePlatePrepare(){
 const view=BE_VIEW,p=view?.plate,row=p?.rows[p.selected];
 if(!view||!row||!beReady(view)||p.sample!==view.readySample||view.trackLaunch||EDITS?.track)return;
 beEndGesture(view.editor,view.cv);
 view.quadEdit=null;
 const b=view.editor;b.trk=false;b.add=false;b.muteArm=false;b.sel=-1;
 beQuadControls(view);
 for(const id of ['beTrk','beAdd','beMute'])document.getElementById(id)?.classList.remove('on');
 for(const id of ['beRm','beTimes']){const e=document.getElementById(id);if(e)e.style.display='none';}
 p.region={box:[...row.box],sample:view.readySample,serial:view.serial,drag:null};
 p.message='The OCR box is approximate. Drag a corner to expand it or drag inside to move it. Inspect the whole number or plate, set the timeline window, then select Track this region to add tracked blur.';
 bePlateRender(view);beDraw();
}
function bePlateTrack(){
 const view=BE_VIEW,p=view?.plate,region=p?.region,draft=EDITS;
 if(!region||region.drag||!beReady(view)||region.sample!==view.readySample||region.serial!==view.serial||
    p.sample!==view.readySample||view.trackLaunch||!draft||draft.track)return;
 const box=[...region.box],[t0,t1]=view.editor.win||[];
 if(box[2]-box[0]<=10||box[3]-box[1]<=10||!beNewBox(view,box,t0,t1)){
  p.message='Expand the region and set a timeline window containing this frame before tracking.';
  bePlateRender(view);return;
 }
 bePlateDiscardRegion(view);p.batch=null;p.message='Tracking requested. Review the tracked positions.';
 bePlateRender(view);beDraw();beTrackGo(box);
}
function bePlateRetire(view,message){
 const p=view?.plate;if(!p)return;
 if(p.request){
  const request=p.request;request.retired=true;
  if(!request.cancelRequested){
   request.cancelRequested=true;
   // The token also lets the server remember cancellation before admission.
   fetch(`api/jobs/${view.id}/plate_search/cancel`,{method:'POST',headers:{'Content-Type':'application/json'},
    body:JSON.stringify({request_id:request.id})}).catch(()=>{});
  }
 }
 bePlateDiscardRegion(view);p.rows=[];p.selected=-1;p.sample=null;p.batch=null;p.inspect=null;if(message)p.message=message;
 if(view.current()){bePlateRender(view);beDraw();}
}
function bePlateChanged(){
 const view=BE_VIEW;if(!view)return;
 bePlateRetire(view,'Text or match mode changed. Search again.');
 view.plate.message='Text or match mode changed. Search again.';bePlateRender(view);
}
function bePlateClose(view){
 bePlateRetire(view,'Choose a frame search or video samples. Suggestions do not blur anything.');
 const query=document.getElementById('bePlateQuery');if(query)query.value='';
 view.plate.message='Choose a frame search or video samples. Suggestions do not blur anything.';bePlateRender(view);
}
function bePlateSummary(){
 const view=BE_VIEW,details=document.getElementById('bePlate');
 if(view&&details?.open)bePlateClose(view);
}
function bePlateToggle(){
 const view=BE_VIEW,details=document.getElementById('bePlate');
 if(view&&details&&!details.open)bePlateClose(view);
}
function bePlateCancel(){
 const view=BE_VIEW,request=view?.plate?.request;if(!request)return;
 request.userCancelled=true;
 bePlateRetire(view,'Cancellation requested. No suggestions will be applied.');
}
function bePlateValidate(value,sample,mode){
 if(value?.state!=='complete'||value.index!==sample.index||typeof value.truncated!=='boolean'||
  !Array.isArray(value.suggestions)||value.suggestions.length>128)throw Error('invalid search response');
 const kind=mode==='full'?'full_equal':'fragment';
 for(const row of value.suggestions){
  if(!row||row.boundary!=='unknown'||row.match!==kind||!Array.isArray(row.box)||row.box.length!==4||
   !row.box.every(Number.isSafeInteger)||row.box[0]<0||row.box[1]<0||row.box[2]>sample.width||
   row.box[3]>sample.height||row.box[0]>=row.box[2]||row.box[1]>=row.box[3])throw Error('invalid search geometry');
 }
 return value.suggestions.map(row=>({box:[...row.box],match:row.match}));
}
function bePlateValidateSamples(value){
 if(value?.state!=='complete'||!Number.isSafeInteger(value.frame_count)||value.frame_count<1||
    typeof value.fps!=='number'||!Number.isFinite(value.fps)||value.fps<=0||
    !Array.isArray(value.frames)||value.frames.length!==Math.min(4,value.frame_count))throw Error('invalid sampled response');
 let previous=-1;
 for(const frame of value.frames){
  if(!frame||!Number.isSafeInteger(frame.index)||frame.index<=previous||frame.index>=value.frame_count||
     typeof frame.time_s!=='number'||!Number.isFinite(frame.time_s)||frame.time_s<0||
     Math.abs(frame.time_s-frame.index/value.fps)>Number.EPSILON*Math.max(1,frame.time_s)*4||
     typeof frame.seek_s!=='number'||!Number.isFinite(frame.seek_s)||frame.seek_s<frame.time_s||
     Math.floor(frame.seek_s*value.fps)!==frame.index||
     !Number.isSafeInteger(frame.matches)||frame.matches<0||frame.matches>128||typeof frame.truncated!=='boolean')
   throw Error('invalid sampled frame');
  previous=frame.index;
 }
 return value.frames.map(frame=>({...frame}));
}
async function bePlateGo(scope='frame'){
 const view=BE_VIEW;if(!view||view.checkpoint||!view.current()||view.plate.request)return;
 const sampled=scope==='sampled';
 const p=view.plate,query=document.getElementById('bePlateQuery')?.value||'',
       mode=document.getElementById('bePlateMode')?.value;
 if(!beReady(view)){p.message='Pause and inspect a frame before searching.';bePlateRender(view);return;}
 const normalized=query.replace(/[ .\t-]/g,'');
 if(!/^[A-Za-z0-9 .\t-]+$/.test(query)||normalized.length<3||normalized.length>16||!['full','fragment'].includes(mode)){
  p.message='Enter 3–16 letters or digits; spaces, dots and hyphens are allowed.';bePlateRender(view);return;
 }
 let identity;
 try{identity=manualId().replace(/-/g,'');}
 catch(_){p.message='A secure request identifier is unavailable in this browser.';bePlateRender(view);return;}
 const req={id:identity,serial:view.serial,sample:view.readySample,retired:false,cancelRequested:false,userCancelled:false};
 const batch=!sampled&&bePlateBatchCurrent(view,p.batch)?p.batch:null;
 bePlateDiscardRegion(view);p.request=req;p.rows=[];p.selected=-1;p.sample=null;p.batch=batch;
 p.message=sampled?'Searching up to four video samples…':'Searching this frame…';bePlateRender(view);beDraw();
 try{
  const response=await fetch(`api/jobs/${view.id}/plate_search`,{method:'POST',headers:{'Content-Type':'application/json'},
   body:JSON.stringify({request_id:req.id,seed:copyEdit(req.sample.precondition),query,mode,...(sampled?{scope:'sampled'}:{})})});
  let result;try{result=await response.json();}catch(_){throw Error('invalid search response');}
  if(!view.current()||p.request!==req||req.retired||!beSampleCurrent(view,req.serial)||view.readySample!==req.sample)return;
  if(!response.ok){
   if(result?.state==='timeout')p.message=sampled?'Sample search timed out; no sample results were returned.':'Search timed out; this frame was not fully searched.';
   else if(result?.state==='cancelled')p.message='Search cancelled; no suggestions were applied.';
   else if(result?.error==='search_busy')p.message='Another search is running. Try again when it finishes.';
   else if(response.status===409){p.batch=null;p.message='The inspected frame changed. Inspect it again and retry.';}
   else p.message='Search unavailable. Check the local Tesseract installation and supported runtime.';
   return;
  }
  if(sampled){
   const frames=bePlateValidateSamples(result);p.batch={frames,sample:req.sample,index:req.sample.sample.index};
   p.message=`Searched ${frames.length} of ${result.frame_count} scan-timeline frames; only the listed samples were searched. OCR can miss text. Select a frame to inspect it.`;
   if(frames.some(frame=>frame.truncated))p.message+=' Some sample results were truncated.';
  }else{
   p.rows=bePlateValidate(result,req.sample.sample,mode);p.selected=-1;p.sample=req.sample;
   p.message=p.rows.length?`Found ${p.rows.length} ${p.rows.length===1?'suggestion':'suggestions'} on this frame. Select one to inspect and adjust a region for tracking.`:
    'No matching text found in this frame. OCR can miss text.';
   if(result.truncated)p.message+=' Results were truncated.';
  }
 }catch(_){
  if(view.current()&&p.request===req&&!req.retired)p.message='Search failed. Try again.';
 }finally{
  if(p.request===req){
   p.request=null;
   if(req.userCancelled&&view.current()&&view.serial===req.serial)p.message='Search stopped. No suggestions were applied.';
   if(view.current()){bePlateRender(view);beDraw();}
  }
 }
}

function beEndGesture(editor,cv){
 editor.drag=null;editor.addAnchor=null;editor.addFloat=null;
 const view=BE_VIEW;
 if(view?.editor===editor&&view.cv===cv&&view.plate?.region)view.plate.region.drag=null;
 if(editor.pointerId!=null){
  try{cv.releasePointerCapture(editor.pointerId);}catch(e){}
  delete editor.pointerId;
 }
}
function beUnmount(){
 const view=BE_VIEW;if(!view)return;
 bePlateRetire(view,'');
 beRetireTrack(view);BE_VIEW=null;view.serial++;view.playbackSerial++;
 const gesture=view.tlGesture;
 if(gesture){
  if(view.editor.tlDrag===gesture.drag)view.editor.tlDrag=null;
  try{view.tl.releasePointerCapture(gesture.pointerId);}catch(_){}
  view.tlGesture=null;
 }
 if(view.imageURL)URL.revokeObjectURL(view.imageURL);view.imageURL=null;view.readySample=null;
 view.observer.disconnect();
 beEndGesture(view.editor,view.cv);
}
// A panel transition may retain the mounted editor. Dispose only its removed
// subtree, before DOM replacement, so retained video/gestures keep their owner.
function beUnmountIn(root){
 const view=BE_VIEW;if(!view||!root?.contains?.(view.cv))return;
 beUnmount();view.editor.playing=false;
 try{if(view.vid&&!view.vid.paused)view.vid.pause();}catch(e){}
}
function beMount(img,vid,cv,id,gen,editor,checkpoint=null){
 beUnmount();
 const view={img,vid,cv,id,gen,editor,checkpoint,transform:null,serial:0,playbackSerial:0,trackLaunch:null,readySample:null,imageURL:null,loading:false,
  plate:{request:null,rows:[],selected:-1,sample:null,region:null,batch:null,inspect:null,message:'Choose a frame search or video samples. Suggestions do not blur anything.'}};
 view.current=()=>BE_VIEW===view&&ownsView(id,gen)&&BE===editor&&
  document.getElementById("beCv")===cv;
 view.sync=()=>{
  if(!view.current())return null;
  const media=editor.playing?vid:img,r=media.getBoundingClientRect();
  const sw=media===vid?vid.videoWidth:img.naturalWidth,
        sh=media===vid?vid.videoHeight:img.naturalHeight;
  const loaded=media===vid?vid.readyState>=1:img.complete&&!view.loading;
  const valid=loaded&&[sw,sh,r.width,r.height].every(n=>Number.isFinite(n)&&n>0);
  const old=view.transform;
  if(!valid){
   if(old){beEndGesture(editor,cv);view.transform=null;}
   cv.width=0;cv.height=0;cv.style.width="0px";cv.style.height="0px";
   return null;
  }
  const changed=!old||old.media!==media||old.sw!==sw||old.sh!==sh||
   old.width!==r.width||old.height!==r.height;
  if(changed){
   beEndGesture(editor,cv);
   // CSS coordinates keep handles/strokes constant. Rounded backing sizes
   // have their own X/Y ratio, so fractional CSS dimensions lose no scale.
   const dpr=window.devicePixelRatio||1;
   cv.width=Math.max(1,Math.round(r.width*dpr));
   cv.height=Math.max(1,Math.round(r.height*dpr));
   cv.style.width=r.width+"px";cv.style.height=r.height+"px";
   view.transform={media,sw,sh,width:r.width,height:r.height,
    sx:r.width/sw,sy:r.height/sh};
   editor.scale=r.width/sw;
   beDraw();
  }
  return view.transform;
 };
 view.observer=new ResizeObserver(()=>view.sync());
 BE_VIEW=view;view.observer.observe(img);view.observer.observe(vid);
 return view;
}
async function loadBoxEdit(fromReview){
 const id=CUR,gen=VIEW_GEN,editor=BE;
 const checkpoint=PHPH==='paused'?REVIEW_META?.checkpoint:null;
 if(PHPH==='paused'&&(!checkpoint||REVIEW_META.jobId!==id||REVIEW_META.viewGen!==gen))return;
 showPanel(fromReview?"boxedit_rev":"boxedit");
 const intent=++BE_OPEN_INTENT;
 let mi;
 try{
  if(checkpoint)mi={duration:checkpoint.duration};
  else{
   const response=await fetch(`api/jobs/${id}/mediainfo`);
   if(!response.ok)throw Error(`Media information unavailable (HTTP ${response.status})`);
   mi=await response.json();if(!Number.isFinite(mi.duration)||mi.duration<=0)throw Error('Invalid media duration');
  }
 }catch(error){if(ownsView(id,gen)&&BE===editor&&intent===BE_OPEN_INTENT)saveStatus(EDITS,error.message);return;}
 if(!ownsView(id,gen)||BE!==editor||intent!==BE_OPEN_INTENT)return;
 // in review: the slot right under the Preview button; on done: the actions slot
 let c=document.getElementById("beslot")||document.getElementById("beslot_done");
 if(!c){c=document.createElement("div");c.id="beslot";c.style.width="100%";
  (document.getElementById("review")||document.getElementById("jobcard")||detail)
   .appendChild(c);}
 Object.assign(BE,{dur:mi.duration,win:[0,mi.duration],trk:false,muteArm:false,tlDrag:null,
     audioSel:-1,tlspans:[]});

 beUnmountIn(c);
 c.innerHTML=`<div class="row" style="margin-top:8px">
  <button class="sec" id="bePlay" ${checkpoint?'hidden':''} style="padding:3px 11px" title="Play the video with live boxes — pause to edit them" onclick="beTogglePlay()">&#9654;</button>t=
  <input type="range" id="beT" min="0" max="${checkpoint?checkpoint.frames-1:Math.max(0.2,mi.duration-0.1).toFixed(1)}"
   step="${checkpoint?'1':'0.1'}" value="0" style="flex:1" oninput="beScrub()"><span id="beL">0s</span></div>
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
  <details id="bePlate" ${checkpoint?'hidden':''} style="margin-top:8px" ontoggle="bePlateToggle()">
   <summary onclick="bePlateSummary()">Find plate text</summary>
   <p style="font-size:12px;color:#94a3b8;margin:5px 0">Search this frame or up to four evenly spaced video samples with local OCR. Results are approximate suggestions, not redactions.</p>
   <div class="row" style="gap:6px;align-items:end">
    <div style="flex:1 1 145px;min-width:0">
     <label for="bePlateQuery" style="display:block">Plate text</label>
     <input id="bePlateQuery" type="text" maxlength="128" autocomplete="off" spellcheck="false"
      style="width:100%;box-sizing:border-box" oninput="bePlateChanged()">
    </div>
    <div style="flex:0 1 135px;min-width:0">
     <label for="bePlateMode" style="display:block">Match</label>
     <select id="bePlateMode" style="width:100%;box-sizing:border-box" onchange="bePlateChanged()">
      <option value="full">Full text</option><option value="fragment">Text fragment</option>
     </select>
    </div>
    <button class="sec" id="bePlateRun" type="button" onclick="bePlateGo()" disabled>Search this frame</button>
    <button class="sec" id="bePlateSampleRun" type="button" onclick="bePlateGo('sampled')" disabled>Search up to four video samples</button>
    <button class="sec" id="bePlateCancel" type="button" onclick="bePlateCancel()" hidden>Cancel search</button>
   </div>
   <div id="bePlateStatus" role="status" aria-live="polite" style="font-size:12px;color:#cbd5e1;margin-top:5px">Choose a frame search or video samples. Suggestions do not blur anything.</div>
   <div id="bePlateResults" class="row" style="gap:5px;margin-top:5px"></div>
   <div id="bePlateActions" class="row" style="gap:5px;margin-top:5px"></div>
   <div id="bePlateSamples" class="row" style="gap:5px;margin-top:5px"></div>
  </details>
  <div class="row" style="margin-top:6px">
   <button class="tog" id="beAdd" onclick="beAddMode()">&#65291; Add box</button>
   <button class="tog" id="beTrk" ${checkpoint?'hidden':''} onclick="beTrackMode()">&#8857; Track object</button>
   <button class="danger" id="beRm" style="display:none" onclick="beRemove()">Remove blur</button>
   <button class="sec" id="beQuad" style="display:none" onclick="beQuadMode()">Edit plate corners</button>
   <button class="sec" id="beQuadReset" style="display:none" onclick="beQuadReset()">Reset to full plate mask</button>
   <span id="beTimes" style="display:none;align-items:center;gap:4px;font-size:13px">
    from <input type="text" inputmode="decimal" id="beT0" title="h:mm:ss.mmm or seconds" style="width:104px">
    to <input type="text" inputmode="decimal" id="beT1" title="h:mm:ss.mmm or seconds" style="width:104px">
    <button class="sec" onclick="beApplyTimes()">Apply times</button></span>
   <span id="beTrkSt" style="display:none;font-size:13px;color:#fbbf24">tracking&#8230;</span>
   <button data-save-edits onclick="${checkpoint?'saveAndResume()':'beSave()'}">${checkpoint?'Save &amp; Resume':'Save changes &amp; re-render'}</button></div>
  <p id="beQuadStatus" role="status" style="display:none;font-size:12px;color:#bfdbfe;margin:4px 0"></p>
  ${checkpoint?'<p style="font-size:12px;color:#94a3b8">Inspect still frames and edit boxes or audio spans only within the processed portion. Automatic audio scanning is incomplete. Playback and tracking are available after the scan finishes.</p>':`<p style="font-size:12px;color:#94a3b8;margin:4px 0 0">&#9654; plays the
   video with the boxes moving live (pause to edit). Click a red box to
   select — drag inside to move, a corner to resize, edit its from/to times,
   or remove its blur. &#65291; Add box: drag a static region. &#8857; Track object:
   drag the timeline handles to the part of the video you care about, scrub
   to a frame where the object is clear, draw a box around it — it will be
   followed and blurred through the window. &#128263; Audio span: drag on the
   timeline's bottom lane to silence (or bleep) that stretch of sound.</p>`}`;
 const img=document.getElementById("beImg"),bv=document.getElementById("beVid"),
       cv=document.getElementById("beCv");
 const view=beMount(img,bv,cv,id,gen,editor,checkpoint);
 img.onload=()=>{if(view.current()&&!BE.playing){view.sync();beDraw();}};
 bv.addEventListener("loadedmetadata",()=>{if(view.current())view.sync();});
 const stop=()=>{if(ownsView(id,gen)&&BE===editor&&document.getElementById("beVid")===bv&&BE.playing)bePlayStop();};
 bv.addEventListener("pause",stop);bv.addEventListener("ended",stop);
 saveStatus(EDITS,EDITS.status);
 beHook();tlHook();await tlInit();
 if(ownsView(id,gen)&&BE===editor&&intent===BE_OPEN_INTENT&&view.current())beScrub();
}

// ---- playback with live boxes (issue #17: review was scrub-only) ----
async function beTogglePlay(){
 const id=CUR,gen=VIEW_GEN,editor=BE;
 const v=document.getElementById("beVid"),img=document.getElementById("beImg"),view=BE_VIEW;
 if(PHPH==='paused'||view?.checkpoint)return;
 if(!v)return;
 if(BE.playing){bePlayStop();return;}
 const serial=view?++view.playbackSerial:(editor.playbackSerial=(editor.playbackSerial||0)+1);
 if(view)beInvalidateSample(view,"Playback is view only; pause to inspect.");
 const current=()=>ownsView(id,gen)&&BE===editor&&document.getElementById("beVid")===v&&
 BE.playing&&(view?BE_VIEW===view&&view.playbackSerial===serial:editor.playbackSerial===serial);
 if(!v.src)v.src=`api/jobs/${CUR}/video`;
 BE.playing=true;
 v.style.display="block";img.style.display="none";
 if(BE_VIEW)BE_VIEW.sync();
 // boxes are view-only while playing: freeze pointer edits so a moving
 // box can't be grabbed mid-flight
 const cv=document.getElementById("beCv");cv.style.pointerEvents="none";
 document.getElementById("bePlay").innerHTML="&#10074;&#10074;";
 try{
  if(v.readyState<1)await new Promise((res,rej)=>{
   v.onloadedmetadata=res;
   v.onerror=()=>rej(new Error("the browser cannot decode this file"));
   // preload=none defers I/O until Play; request metadata after installing
   // the listeners rather than waiting for a load that has not started.
   v.load();});
  if(!current())return;
  v.currentTime=BE.t||0;
  await v.play();
  if(!current()){if(!view||BE_VIEW!==view||view.playbackSerial===serial)v.pause();return;}
 }catch(e){
  if(!current())return;
  bePlayStop();
  alert("Could not play the video in this browser ("+(e&&e.message||e)
   +") — the scrub slider still works frame by frame.");
  return;
 }
 if(BE_VIEW)BE_VIEW.sync();
 // boxes come from the server per timestamp; refresh them on a throttle
 // while rAF keeps the playhead, label and box painting per-frame smooth
 let lastQ=0,inFlight=false;
 const step=()=>{
  if(!current()||!BE.playing)return;
  BE.t=v.currentTime;
  document.getElementById("beT").value=BE.t;
  document.getElementById("beL").textContent=fmtTime(BE.t);
  const now=performance.now();
  if(!inFlight&&now-lastQ>150){
   inFlight=true;lastQ=now;
   fetch(`api/jobs/${id}/boxes_at?t=${BE.t.toFixed(2)}&all=1`)
    .then(r=>r.json())
    .then(d=>{if(!current())return;BE.ox=d.ox;BE.oy=d.oy;BE.raw=d.boxes;beFilter();})
    .catch(()=>{}).finally(()=>{inFlight=false;});
  }
  beDraw();beTLDraw();
  requestAnimationFrame(step);
 };
 requestAnimationFrame(step);
}
function bePlayStop(){
 const view=BE_VIEW;if(view)view.playbackSerial++;else BE.playbackSerial=(BE.playbackSerial||0)+1;
 const video=document.getElementById("beVid");
 if(BE.playing&&video&&Number.isFinite(video.currentTime)){BE.t=video.currentTime;const sl=document.getElementById("beT");if(sl)sl.value=BE.t;}
 BE.playing=false;
 const v=document.getElementById("beVid");
 if(v){try{v.pause();}catch(e){}v.style.display="none";}
 const img=document.getElementById("beImg");if(img)img.style.display="";
 if(BE_VIEW)BE_VIEW.sync();
 const b=document.getElementById("bePlay");if(b)b.innerHTML="&#9654;";
 const cv=document.getElementById("beCv");if(cv)cv.style.pointerEvents="auto";
 beScrub();   // crisp frame + authoritative boxes at the pause point
}

const TLC={name:"#3b82f6",dob:"#22c55e",phone:"#f59e0b",ssn:"#ef4444",
 mrn:"#8b5cf6",email:"#14b8a6",address:"#f97316",card:"#db2777",
 apikey:"#0891b2",ipaddr:"#65a30d",plate:"#7c3aed",face:"#ec4899",
 person:"#0ea5e9",manual:"#eab308"};
async function tlInit(){
 const id=CUR,gen=VIEW_GEN,editor=BE,view=BE_VIEW;
 const current=()=>ownsView(id,gen)&&BE===editor&&BE_VIEW===view;
 // one fetch of the full report: detection spans for the lanes (dense
 // tracks collapse to one span per track) + stored audio redactions
 try{
  const response=await fetch(`api/jobs/${id}/report`);
  if(!response.ok)throw Error("could not load audio");
  const doc=await response.json();
  if(!current())return;
  const per={};
  for(const d of (doc.detections||[])){
   if(d.enabled===false)continue;
   const key=d.category+((d.track??-1)>=0?(":t"+d.track):(":i"+Math.random()));
   const s=per[key]||(per[key]={cat:d.category,t0:d.t_start,t1:d.t_end});
   s.t0=Math.min(s.t0,d.t_start);s.t1=Math.max(s.t1,d.t_end);
  }
  BE.tlspans=Object.values(per);
  if(!BE.audioLoaded){
   const stored=(doc.audio_redactions||[]).filter(s=>!view?.checkpoint||
    Number.isFinite(s.t0)&&Number.isFinite(s.t1)&&s.t0>=0&&s.t1>s.t0&&s.t1<=view.checkpoint.duration)
    .map(s=>({t0:s.t0,t1:s.t1,mode:s.mode||"mute"}));
   // Audio controls can be used while this initial report request is pending.
   BE.audio=[...stored,...BE.audio];BE.audioSaved=copyEdit(stored);BE.audioLoaded=true;
  }
  BE.audioSugg=view?.checkpoint?[]:doc.audio_suggestions||[];
  BE.audioTx=view?.checkpoint?[]:doc.audio_transcript||[];BE.txAnchor=-1;
  renderAudioSugg();renderTranscript();
 }catch(e){if(!current())return;BE.tlspans=[];}
 beTLDraw();
}
function tlX(t,w){return Math.max(0,Math.min(w,t/(BE_VIEW?.checkpoint?BE.dur:Math.max(0.1,BE.dur))*w));}
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
 document.getElementById("beWinL").textContent=full?(BE_VIEW?.checkpoint?"window: processed portion":"window: whole video")
  :`window: ${fmtTime(BE.win[0])}–${fmtTime(BE.win[1])}`;
}
function tlHook(){
 const cv=document.getElementById("beTL"),view=BE_VIEW,editor=BE;if(!cv||!view)return;
 view.tl=cv;
 const current=()=>view.current()&&BE===editor&&document.getElementById("beTL")===cv;
 const owned=e=>current()&&view.tlGesture?.pointerId===e.pointerId&&editor.tlDrag===view.tlGesture.drag;
 const start=drag=>{editor.tlDrag=drag;view.tlGesture.drag=drag;};
 const release=()=>{const g=view.tlGesture;if(!g)return;
  if(editor.tlDrag===g.drag)editor.tlDrag=null;
  try{cv.releasePointerCapture(g.pointerId);}catch(_){}view.tlGesture=null;};
 const tAt=e=>{const r=cv.getBoundingClientRect();
  return r.width>0&&Number.isFinite(e.clientX)?Math.max(0,Math.min(editor.dur,(e.clientX-r.left)/r.width*editor.dur)):null;};
 const yAt=e=>{const r=cv.getBoundingClientRect();return e.clientY-r.top;};
 cv.addEventListener("pointerdown",e=>{
  if(!current()||view.tlGesture)return;
  const t=tAt(e);if(t===null)return;
  view.tlGesture={pointerId:e.pointerId,drag:null};editor.tlDrag=null;cv.setPointerCapture(e.pointerId);
  const w=cv.clientWidth,px=e.clientX-cv.getBoundingClientRect().left;
  if(!view.checkpoint&&Math.abs(px-tlX(BE.win[0],w))<7){start({k:"w0"});return;}
  if(!view.checkpoint&&Math.abs(px-tlX(BE.win[1],w))<7){start({k:"w1"});return;}
  if(yAt(e)>=54){                                  // audio lane
   if(BE.muteArm){start({k:"anew",t0:t});
    BE.audio.push({t0:t,t1:t,mode:document.getElementById("beAMode").value});
    BE.audioSel=BE.audio.length-1;beTLDraw();return;}
   const hit=BE.audio.findIndex(s=>t>=s.t0&&t<=s.t1);
   BE.audioSel=hit;
   document.getElementById("beARm").style.display=hit>=0?"inline-block":"none";
   beTLDraw();return;
  }
  start({k:"seek"});
  beSetSliderTime(t);beScrub();
 });
 cv.addEventListener("pointermove",e=>{
  if(!owned(e)||!editor.tlDrag)return;
  const t=tAt(e);if(t===null)return;
  if(BE.tlDrag.k==="w0")BE.win[0]=Math.min(t,BE.win[1]-0.2);
  else if(BE.tlDrag.k==="w1")BE.win[1]=Math.max(t,BE.win[0]+0.2);
  else if(BE.tlDrag.k==="anew"){
   const s=BE.audio[BE.audioSel];
   s.t0=Math.min(BE.tlDrag.t0,t);s.t1=Math.max(BE.tlDrag.t0,t);
  }else if(BE.tlDrag.k==="seek"){
   beSetSliderTime(t);beScrub();}
  beTLDraw();
 });
 cv.addEventListener("pointerup",e=>{
  if(!owned(e))return;
  if(BE.tlDrag&&BE.tlDrag.k==="anew"){
   const s=BE.audio[BE.audioSel];
   const minimum=view.checkpoint?Math.min(.15,.5/view.checkpoint.fps):.15;
   if(s.t1-s.t0<minimum){BE.audio.pop();BE.audioSel=-1;}   // stray click
   BE.muteArm=false;document.getElementById("beMute").classList.remove("on");
   document.getElementById("beARm").style.display=BE.audioSel>=0?"inline-block":"none";
   renderTranscript();
  }
  release();beTLDraw();
 });
 cv.addEventListener("pointercancel",e=>{if(owned(e)){release();beTLDraw();}});
}
function beWinReset(){BE.win=[0,BE.dur];beTLDraw();}
function beMuteMode(){
 if(BE_VIEW?.quadEdit){BE_VIEW.quadEdit=null;beEndGesture(BE,BE_VIEW.cv);beQuadControls(BE_VIEW);}
 bePlateDiscardRegion(BE_VIEW);bePlateRender(BE_VIEW);beDraw();
 BE.muteArm=!BE.muteArm;BE.trk=false;BE.add=false;BE.addAnchor=null;
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
 if(PHPH==='paused'||BE_VIEW?.checkpoint||!beReady()||BE_VIEW.trackLaunch||EDITS?.track)return;
 if(BE_VIEW.quadEdit){BE_VIEW.quadEdit=null;beEndGesture(BE,BE_VIEW.cv);beQuadControls(BE_VIEW);}
 bePlateDiscardRegion(BE_VIEW);bePlateRender(BE_VIEW);beDraw();
 BE.trk=!BE.trk;BE.add=false;BE.addAnchor=null;BE.muteArm=false;
 document.getElementById("beTrk").classList.toggle("on",BE.trk);
 document.getElementById("beAdd").classList.remove("on");
 document.getElementById("beMute").classList.remove("on");
}
// A Track operation belongs to the existing job draft, not its transient editor.
function trackOwned(track){return REVIEW_DRAFTS.get(track.id)===track.draft&&track.draft.track===track;}
function renderTrackStatus(d){
 if(d!==EDITS)return;
 const status=document.getElementById('reviewTrackStatus'),actions=document.getElementById('reviewTrackActions');
 if(!status||!actions)return;
 status.textContent='';actions.innerHTML='';const track=d.track;if(!track)return;
 if(track.state==='starting'||track.state==='running'){
  status.textContent='Tracking is in progress. Results will be available to review.';return;
 }
 if(track.state==='done'&&!track.error)status.textContent=track.uncertain?
  `Latest tracking status reports ${track.added} position(s). The request was unconfirmed; review the report.`:
  `Tracked ${track.added} position(s). Review the updated report.`;
 else status.textContent=track.state==='uncertain'?'Tracking may have started; check its status and review the report.':
  'Tracking status: '+track.error;
 if(track.state==='done'&&!track.error||track.state==='uncertain'||track.state==='status_error'){
  const review=document.createElement('button');review.textContent='Review tracked positions';
  review.onclick=()=>reviewTracked(d,track);actions.appendChild(review);
 }
 if(track.state==='uncertain'||track.state==='status_error'){
  const retry=document.createElement('button');retry.textContent='Check tracking status';
  retry.onclick=()=>checkTrackStatus(d,track);actions.appendChild(retry);
 }
 if(track.state!=='done'||track.error){
  const dismiss=document.createElement('button'),state=track.state;dismiss.textContent='Dismiss tracking notice';
  dismiss.onclick=()=>{if(track.state===state)clearTrack(d,track);};actions.appendChild(dismiss);
 }
}
function clearTrack(d,track){
 if(EDITS!==d||d.track!==track)return;
 if(track.timer)clearTimeout(track.timer);track.timer=null;d.track=null;renderTrackStatus(d);
}
async function reviewTracked(d,track){
 if(EDITS!==d||d.track!==track||CUR!==track.id||
  !(track.state==='done'&&!track.error||track.state==='uncertain'||track.state==='status_error'))return;
 const id=CUR,gen=VIEW_GEN,intent=await loadReview();
 if(ownsView(id,gen)&&EDITS===d&&d.track===track&&track.state==='done'&&intent!==undefined&&intent===BE_OPEN_INTENT)clearTrack(d,track);
}
function beRetireTrack(view=BE_VIEW){
 const launch=view?.trackLaunch;if(!launch)return;
 view.trackLaunch=null;
 if(view.current()){
  if(document.getElementById('beTrkSt')===launch.st)launch.st.textContent='';
  view.editor.trk=false;view.editor.addAnchor=null;view.editor.addFloat=null;
  document.getElementById('beTrk')?.classList.remove('on');
 }
 if(launch.view===view){launch.view=null;launch.editor=null;launch.st=null;}
}
function beTrackCurrent(launch){
 const view=launch.view;
 const current=!!view&&view.current()&&BE_VIEW===view&&ownsView(launch.id,launch.gen)&&BE===launch.editor&&
  view.trackLaunch===launch&&BE_OPEN_INTENT===launch.intent&&REVIEW_REQUEST===launch.reviewRequest;
 if(!current&&view?.trackLaunch===launch)beRetireTrack(view);
 return current;
}
function scheduleTrackStatus(track){
 if(!trackOwned(track)||track.timer)return;
 track.timer=setTimeout(()=>{track.timer=null;return pollTrackStatus(track);},1500);
}
async function checkTrackStatus(d,track){
 if(EDITS!==d||d.track!==track||track.polling||!['uncertain','status_error'].includes(track.state))return;
 track.state='running';renderTrackStatus(d);return pollTrackStatus(track);
}
async function pollTrackStatus(track){
 if(!trackOwned(track)||track.polling)return;
 track.polling=true;
 try{
  const response=await fetch(`api/jobs/${track.id}/track_status`);
  if(!response.ok)throw Error(`Track status unavailable (HTTP ${response.status})`);
  const result=await response.json();if(!trackOwned(track))return;
  if(result.state==='running'){
   track.state='running';renderTrackStatus(track.draft);scheduleTrackStatus(track);return;
  }
  if(result.state!=='done'||!Number.isSafeInteger(result.added)||result.added<0)
   throw Error('Tracking status is unavailable; inspect the report or check again.');
  track.state='done';track.added=result.added;track.error=result.error||null;renderTrackStatus(track.draft);
  if(!beTrackCurrent(track))return;
  const view=track.view,editor=track.editor,st=track.st;
  if(track.error){st.textContent='⚠ '+track.error;view.trackLaunch=null;track.view=null;track.editor=null;track.st=null;return;}
  st.textContent=`tracked ✓ ${track.added} position(s) — inspect and review`;
  saveStatus(track.draft,'Tracked positions added. Inspect and review them; pending edits are retained.');
  beInvalidateSample(view,'Inspecting tracked result…');
  await tlInit();if(!trackOwned(track)||!beTrackCurrent(track))return;
  view.trackLaunch=null;track.view=null;track.editor=null;track.st=null;
  if(document.getElementById("review")){
   const intent=await loadReview();
   if(!trackOwned(track)||!ownsView(track.id,track.gen)||BE!==editor||intent===undefined||intent!==BE_OPEN_INTENT)return;
   clearTrack(track.draft,track);await loadBoxEdit(1);
  }else{
   const sample=beScrub();
   if(sample)sample.then(()=>{if(trackOwned(track)&&BE_VIEW===view&&beReady(view))clearTrack(track.draft,track);});
  }
 }catch(error){
  if(!trackOwned(track))return;
  track.state='status_error';track.error=String(error.message||error);renderTrackStatus(track.draft);
  if(beTrackCurrent(track))beRetireTrack(track.view);
 }finally{track.polling=false;}
}
async function beTrackGo(box){
 const view=BE_VIEW,draft=EDITS;if(PHPH==='paused'||view?.checkpoint||!beReady(view)||view.trackLaunch||!draft||draft.track)return;
 const editor=view.editor,[t0,t1]=editor.win||[];
 if(!beNewBox(view,box,t0,t1)){saveStatus(draft,"Track requires an in-frame box and a window containing the canonical frame time.");return;}
 const st=document.getElementById("beTrkSt"),launch={view,editor,draft,id:view.id,gen:view.gen,st,
  intent:BE_OPEN_INTENT,reviewRequest:REVIEW_REQUEST,state:'starting',timer:null,polling:false};
 const payload={box:copyEdit(box),t_ref:view.readySample.sample.canonical_s,t0,t1,seed:copyEdit(view.readySample.precondition)};
 draft.track=launch;view.trackLaunch=launch;renderTrackStatus(draft);
 st.style.display="inline";st.textContent=`tracking ${fmtTime(t0)}–${fmtTime(t1)}…`;
 try{
  await reviewPost(`api/jobs/${launch.id}/track_object`,payload);
  if(!trackOwned(launch))return;
  launch.state='running';renderTrackStatus(draft);scheduleTrackStatus(launch);
 }catch(error){
  if(!trackOwned(launch))return;
  launch.uncertain=!(Number.isInteger(error.status)&&error.status>=400&&error.status<500);
  launch.state=launch.uncertain?'uncertain':'failed';launch.error=String(error.message||error);
  renderTrackStatus(draft);if(beTrackCurrent(launch))beRetireTrack(launch.view);
 }
}

function beSetSliderTime(t){
 const sl=document.getElementById('beT'),checkpoint=BE_VIEW?.checkpoint;if(!sl)return;
 sl.value=checkpoint?Math.max(0,Math.min(checkpoint.frames-1,Math.floor(t*checkpoint.fps))):t.toFixed(1);
}
function beScrub(){
 const view=BE_VIEW,sl=document.getElementById("beT");if(!sl||!view||!view.current())return;
 const value=+sl.value,t=view.checkpoint?(value+.25)/view.checkpoint.fps:value;
 if(!Number.isFinite(t))return;
 if(BE.playing){if(view.vid)view.vid.currentTime=t;return;}
 return beRequestSample(view,t);
}
function beFilter(){
 BE.boxes=(BE.raw||[]).filter(b=>{
  const on=(b.i in EN)?EN[b.i]:b.enabled;   // live: review toggles apply here
  const span=BE.times[b.i]||[b.t_start,b.t_end];
  return on&&(BE.playing||(BE.t>=span[0]-.01&&BE.t<=span[1]+.01));
 }).map(b=>{
  let bb=b;
  if(BE.ov[b.i]){const o=BE.ov[b.i];
   bb={...b,box:[o[0]+BE.ox,o[1]+BE.oy,o[2]+BE.ox,o[3]+BE.oy]};}
  if(BE.times[b.i]){bb={...bb,t_start:BE.times[b.i][0],t_end:BE.times[b.i][1]};}
  return bb;
 });
}
function beDraw(){
 const cv=document.getElementById("beCv");if(!cv)return;
 const view=BE_VIEW;if(!view||!view.current())return;
 const x=cv.getContext("2d"),tr=view.transform;
 x.setTransform(1,0,0,1,0,0);x.clearRect(0,0,cv.width,cv.height);
 if(!tr)return;
 x.setTransform(cv.width/tr.width,0,0,cv.height/tr.height,0,0);
 const mapped=box=>box.map((v,i)=>v*(i%2?tr.sy:tr.sx));
 for(const a of BE.adds){
  if(BE.t<a.t0-0.01||BE.t>a.t1+0.01)continue;
  const[a1,b1,a2,b2]=mapped(a.box);
  x.fillStyle="rgba(245,158,11,.25)";x.strokeStyle="#f59e0b";x.lineWidth=2;
  x.fillRect(a1,b1,a2-a1,b2-b1);x.strokeRect(a1,b1,a2-a1,b2-b1);
 }
 if(BE.add&&BE.addAnchor&&BE.addFloat){
  const[p,q]=[BE.addAnchor,BE.addFloat];
  x.strokeStyle="#f59e0b";x.setLineDash([6,4]);x.lineWidth=2;
  x.strokeRect(Math.min(p[0],q[0])*tr.sx,Math.min(p[1],q[1])*tr.sy,
   Math.abs(q[0]-p[0])*tr.sx,Math.abs(q[1]-p[1])*tr.sy);x.setLineDash([]);
 }
 for(const b of BE.boxes){
  const[a1,b1,a2,b2]=mapped(b.box);
  x.fillStyle=b.i===BE.sel?"rgba(37,99,235,.25)":"rgba(220,38,38,.22)";
  x.strokeStyle=b.i===BE.sel?"#2563eb":"#dc2626";x.lineWidth=2;
  x.fillRect(a1,b1,a2-a1,b2-b1);x.strokeRect(a1,b1,a2-a1,b2-b1);
  if(b.i===BE.sel&&!view.quadEdit)for(const[hx,hy] of [[a1,b1],[a2,b1],[a1,b2],[a2,b2]]){
   x.fillStyle="#fff";x.fillRect(hx-5,hy-5,10,10);
   x.strokeRect(hx-5,hy-5,10,10);}
 }
 const region=view.plate?.region,suggestion=view.plate?.rows[view.plate.selected];
 if(region&&region.sample===view.readySample&&region.serial===view.serial&&!BE.playing){
  const[a1,b1,a2,b2]=mapped(region.box);
  x.fillStyle='rgba(34,211,238,.12)';x.strokeStyle='#22d3ee';x.lineWidth=3;
  x.fillRect(a1,b1,a2-a1,b2-b1);x.strokeRect(a1,b1,a2-a1,b2-b1);
  for(const[hx,hy] of [[a1,b1],[a2,b1],[a1,b2],[a2,b2]]){
   x.fillStyle='#fff';x.fillRect(hx-5,hy-5,10,10);x.strokeRect(hx-5,hy-5,10,10);
  }
 }else if(suggestion&&!BE.playing&&view.readySample?.serial===view.serial){
  const[a1,b1,a2,b2]=mapped(suggestion.box);
  x.strokeStyle='#22d3ee';x.lineWidth=3;x.setLineDash([7,5]);
  x.strokeRect(a1,b1,a2-a1,b2-b1);x.setLineDash([]);
 }
 const row=BE.raw?.find(r=>r.i===BE.sel),sample=view.readySample?.sample;
 if(!BE.playing&&row?.category==='plate'&&sample){
  const draft=BE.quads[row.i],family=BE.geometry[row.i],sameFrame=!family||
   (family.precondition.index===sample.index&&family.precondition.source_ref===sample.source_ref&&
    family.precondition.timeline_eq===sample.timeline_eq&&family.precondition.row_context_eq===row.row_context_eq);
  const boxChanged=BE.ov[row.i]&&!sameEdit(BE.ov[row.i],row.base.cbox);
  let points=sameFrame&&view.quadEdit?.row===row&&view.quadEdit.serial===view.serial?view.quadEdit.points:null;
  if(!points&&sameFrame&&draft?.points)points=draft.points;
  if(!points&&!(row.i in BE.quads)&&!boxChanged&&row.quad_eligibility==='eligible_sdr_frame'&&beQuadForSample(row.manual_plate_quad,sample))
   points=row.manual_plate_quad.points.map(p=>[p[0]*sample.width,p[1]*sample.height]);
  if(points&&beQuadValid(points,sample.width,sample.height)){
   x.beginPath();points.forEach((p,i)=>{const a=p[0]*tr.sx,b=p[1]*tr.sy;if(i)x.lineTo(a,b);else x.moveTo(a,b)});
   x.closePath();x.strokeStyle='#22d3ee';x.lineWidth=2;x.stroke();
   if(view.quadEdit){x.font='12px sans-serif';points.forEach((p,i)=>{const a=p[0]*tr.sx,b=p[1]*tr.sy;
    x.fillStyle='#fff';x.fillRect(a-5,b-5,10,10);x.strokeStyle='#0891b2';x.strokeRect(a-5,b-5,10,10);
    x.fillStyle='#fff';x.fillText(String(i+1),a+7,b-7);});}
  }
 }
}
function beAddMode(){
 if(!beReady())return;
 bePlateDiscardRegion(BE_VIEW);bePlateRender(BE_VIEW);
 if(BE_VIEW.quadEdit){BE_VIEW.quadEdit=null;beEndGesture(BE,BE_VIEW.cv);beQuadControls(BE_VIEW);}
 BE.add=!BE.add;BE.addAnchor=null;BE.sel=-1;beQuadControls(BE_VIEW);
 BE.trk=false;BE.muteArm=false;
 document.getElementById("beAdd").classList.toggle("on",BE.add);
 const tb=document.getElementById("beTrk");if(tb)tb.classList.remove("on");
 const mb=document.getElementById("beMute");if(mb)mb.classList.remove("on");
 document.getElementById("beRm").style.display="none";
 document.getElementById("beTimes").style.display="none";
 beDraw();
}
function beApplyTimes(){
 if(BE.sel<0||!beReady())return;
 const t0=parseTime(document.getElementById("beT0").value),
       t1=parseTime(document.getElementById("beT1").value);
 if(t0===null||t1===null){alert("Enter times as h:mm:ss.mmm (for example 0:01:23.400) or in seconds.");return;}
 if(!(t1>t0&&t0>=0&&t1<=BE.dur)){alert("'to' must be after 'from'.");return;}
 const row=BE.raw.find(x=>x.i===BE.sel);if(!beCaptureGeometry(BE_VIEW,row))return;
 BE.times[BE.sel]=[t0,t1];reviewResolveActions(EDITS);
 const b=BE.boxes.find(x=>x.i===BE.sel);
 if(b){b.t_start=t0;b.t_end=t1;}
 beFilter();beDraw();
}
function beShowTimes(b){
 const el=document.getElementById("beTimes");
 el.style.display="inline-flex";
 // checkpoint review keeps the exact stored seconds; elsewhere h:mm:ss.mmm
 document.getElementById("beT0").value=BE_VIEW?.checkpoint?String(b.t_start):fmtTime(b.t_start);
 document.getElementById("beT1").value=BE_VIEW?.checkpoint?String(b.t_end):fmtTime(b.t_end);
}
function manualId(){
 const c=globalThis.crypto;
 if(c&&typeof c.randomUUID==="function")return c.randomUUID();
 if(!c||typeof c.getRandomValues!=="function")
  throw Error("Secure random generation is unavailable. Use a browser with crypto support to add a box.");
 const b=c.getRandomValues(new Uint8Array(16));
 b[6]=(b[6]&15)|64;b[8]=(b[8]&63)|128;
 const h=Array.from(b,v=>v.toString(16).padStart(2,"0")).join("");
 return `${h.slice(0,8)}-${h.slice(8,12)}-${h.slice(12,16)}-${h.slice(16,20)}-${h.slice(20)}`;
}
function beHook(){
 const cv=document.getElementById("beCv"),view=BE_VIEW;
 const pt=e=>{
  if(!beReady(view))return null;const tr=view.transform;
  const r=cv.getBoundingClientRect();
  return[(e.clientX-r.left)/tr.sx,(e.clientY-r.top)/tr.sy];};
 cv.addEventListener("pointerdown",e=>{
  const p=pt(e);if(!p||BE.pointerId!=null&&BE.pointerId!==e.pointerId)return;
  cv.setPointerCapture(e.pointerId);BE.pointerId=e.pointerId;
  if(view.quadEdit){
   const q=view.quadEdit,row=BE.raw?.find(r=>r.i===BE.sel),tr=view.transform;
   if(q.row!==row||q.serial!==view.serial)return;
   const i=q.points.findIndex(v=>Math.abs(p[0]-v[0])<9/tr.sx&&Math.abs(p[1]-v[1])<9/tr.sy);
   if(i>=0)BE.drag={kind:'quad',ci:i,serial:view.serial,i:BE.sel,row};
   return;
  }
  const region=view.plate.region;
  if(region&&region.sample===view.readySample&&region.serial===view.serial){
   const [x0,y0,x1,y1]=region.box,tr=view.transform;
   for(const[hx,hy,ci] of [[x0,y0,0],[x1,y0,1],[x0,y1,2],[x1,y1,3]]){
    if(Math.abs(p[0]-hx)<9/tr.sx&&Math.abs(p[1]-hy)<9/tr.sy){
     region.drag={kind:'corner',ci,box:[...region.box]};return;
    }
   }
   if(p[0]>=x0&&p[0]<=x1&&p[1]>=y0&&p[1]<=y1)
    region.drag={kind:'move',off:[p[0]-x0,p[1]-y0],box:[...region.box]};
   return;
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
     const serial=view.serial;
     const fr=prompt("Blur this region FROM (seconds):",t0);
     if(fr===null){beDraw();return;}
     const to=prompt("...TO (seconds):",t1);
     if(to===null){beDraw();return;}
     try{
      if(view.serial!==serial||!beNewBox(view,box,+fr,+to)){saveStatus(EDITS,"Inspect the frame and choose a window containing its canonical time before adding a box.");return;}
      BE.adds.push({manual_id:manualId(),box,t0:+fr,t1:+to,tref:view.readySample.sample.canonical_s,
       sample_precondition:copyEdit(view.readySample.precondition)});reviewResolveActions(EDITS);
     }catch(e){saveStatus(EDITS,"Could not add box: "+e.message);}
    }
    beDraw();
   }
   return;
  }
  const sel=BE.boxes.find(b=>b.i===BE.sel);
  if(sel){const[a1,b1,a2,b2]=sel.box,tr=view.transform;
   const corners=[[a1,b1,0],[a2,b1,1],[a1,b2,2],[a2,b2,3]];
   for(const[hx,hy,ci] of corners)
    if(Math.abs(p[0]-hx)<9/tr.sx&&Math.abs(p[1]-hy)<9/tr.sy){
     BE.drag={kind:"corner",ci,serial:view.serial,i:BE.sel,row:BE.raw.find(b=>b.i===BE.sel)};return;}
   if(p[0]>=a1&&p[0]<=a2&&p[1]>=b1&&p[1]<=b2){
    BE.drag={kind:"move",off:[p[0]-a1,p[1]-b1],serial:view.serial,i:BE.sel,row:BE.raw.find(b=>b.i===BE.sel)};return;}
  }
  const hit=[...BE.boxes].reverse().find(b=>{
   const[a1,b1,a2,b2]=b.box;
   return p[0]>=a1&&p[0]<=a2&&p[1]>=b1&&p[1]<=b2;});
  BE.sel=hit?hit.i:-1;view.quadEdit=null;beQuadControls(view);
  document.getElementById("beRm").style.display=hit?"inline-block":"none";
  if(hit)beShowTimes(hit);
  else document.getElementById("beTimes").style.display="none";
  beDraw();
 });
 cv.addEventListener("pointermove",e=>{
  const p=pt(e);if(!p||BE.pointerId!=null&&BE.pointerId!==e.pointerId)return;
  const region=view.plate.region,drag=region?.drag;
  if(drag&&region.sample===view.readySample&&region.serial===view.serial){
   const s=view.readySample.sample,[x0,y0,x1,y1]=drag.box,
         px=Math.max(0,Math.min(s.width,p[0])),py=Math.max(0,Math.min(s.height,p[1]));
   if(drag.kind==='move'){
    const w=x1-x0,h=y1-y0,x=Math.max(0,Math.min(s.width-w,px-drag.off[0])),
          y=Math.max(0,Math.min(s.height-h,py-drag.off[1]));
    region.box=[x,y,x+w,y+h];
   }else{
    const ax=drag.ci%2?x0:x1,ay=drag.ci<2?y1:y0;
    region.box=[Math.min(ax,px),Math.min(ay,py),Math.max(ax,px),Math.max(ay,py)];
   }
   beDraw();return;
  }
  if(BE.add&&BE.addAnchor){BE.addFloat=p;beDraw();return;}
  if(!BE.drag||BE.sel<0||BE.drag.serial!==view.serial||BE.drag.i!==BE.sel||BE.drag.row!==BE.raw.find(b=>b.i===BE.sel))return;
  if(BE.drag.kind==='quad'){
   const q=view.quadEdit,s=view.readySample?.sample;if(!q||q.row!==BE.drag.row||q.serial!==view.serial||!s)return;
   const points=copyEdit(q.points);points[BE.drag.ci]=p;
   if(!beQuadValid(points,s.width,s.height)||!beQuadCapture(view,q.row))return;
   q.points=points;BE.quads[BE.sel]={points:copyEdit(points)};beDraw();return;
  }
  const b=BE.boxes.find(x=>x.i===BE.sel);if(!b)return;
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
  const box=[Math.min(a1,a2),Math.min(b1,b2),Math.max(a1,a2),Math.max(b1,b2)];
  if(!beVector(box,4)||box[2]<=box[0]||box[3]<=box[1]||!beCaptureGeometry(view,BE.raw.find(x=>x.i===BE.sel)))return;
  b.box=box;
  BE.ov[BE.sel]=[b.box[0]-BE.ox,b.box[1]-BE.oy,b.box[2]-BE.ox,b.box[3]-BE.oy];
  beQuadControls(view);beDraw();
 });
 const end=e=>{if(view&&view.current()&&BE.pointerId===e.pointerId){if(view.plate.region)view.plate.region.drag=null;BE.drag=null;delete BE.pointerId;reviewResolveActions(EDITS);}};
 cv.addEventListener("pointerup",end);cv.addEventListener("pointercancel",e=>{
  if(view&&view.current()&&BE.pointerId===e.pointerId){
   const region=view.plate.region;if(region?.drag){region.box=region.drag.box;region.drag=null;}
   beEndGesture(BE,cv);reviewResolveActions(EDITS);beDraw();}
 });
}
function zoomDet(i){REVIEW_SCHED?.openLightbox(i);}
function beRemove(){
 if(BE.sel<0)return;
 applyDet(BE.sel,false);   // syncs thumbnail + refilters editor
 BE.sel=-1;if(BE_VIEW){BE_VIEW.quadEdit=null;beQuadControls(BE_VIEW);}
 document.getElementById("beRm").style.display="none";
 document.getElementById("beTimes").style.display="none";
}
async function beSave(){return saveAndRender();}
// 0: nothing scanned yet, 1: a stoppable scan with progress, 2: a stopped
// scan, 3: a scan with progress that cannot be stopped (text categories)
let CANCEL_KIND=0;
async function cancelJob(){
 if(CANCEL_KIND===2&&!confirm("Cancel throws away the saved progress of this scan."))return;
 if(CANCEL_KIND===1&&!confirm("Cancel throws away the scanning done so far. Use Stop to continue later."))return;
 if(CANCEL_KIND===3&&!confirm("Cancel throws away the scanning done so far."))return;
 await fetch("api/jobs/"+CUR+"/cancel",{method:"POST"});
}
async function stopCheckpoint(){
 const id=CUR,button=document.getElementById('checkpointStop');if(!id||!button)return;
 button.disabled=true;button.textContent='Stopping…';
 try{
  const response=await fetch('api/jobs/'+id+'/stop',{method:'POST'});
  if(!response.ok)throw Error('Stop request was not accepted');
  if(CUR===id)refresh();
 }catch(error){
  if(CUR===id){button.disabled=false;button.textContent='Stop & Review';alert(error.message);}
 }
}

// the three post-render views (compare, review, box editor) are mutually
// exclusive: opening one closes the others instead of stacking them
function showPanel(which){
 if(which!=="review"&&EDITS){
  EDITS.reviewEditorGen=VIEW_GEN;
  if(AUTO_REVIEW&&(AUTO_REVIEW.state!=="ready"||which!=="boxedit_rev"||!document.getElementById("review")))
   AUTO_REVIEW.state="deferred";
  renderReviewAccess();
 }
 beRetireTrack();BE_OPEN_INTENT++;
 const clear=element=>{if(element){beUnmountIn(element);element.innerHTML="";}};
 // boxedit_rev keeps the review, its scheduler and its in-review editor slot.
 if(which!=="compare")clear(document.getElementById("compare"));
 const b=document.getElementById("beslot_done"),b2=document.getElementById("beslot");
 if(which==="boxedit_rev")clear(b);
 else{
  if(which!=="boxedit")clear(b);
  clear(b2);
  if(which!=="review"){
   REVIEW_REQUEST=null;
   document.getElementById("review-load-error")?.remove();
   disposeReview();const rev=document.getElementById("review");
   if(rev){beUnmountIn(rev);rev.remove();}
  }
 }
}

async function loadCompare(){
 showPanel("compare");
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

// Complete metadata stays authoritative even when its cards are unmounted.
let TRKMEM={},ROWCARD={},REVIEW_META=null,REVIEW_SCHED=null;
const THUMB_FLIGHTS=new Set(); // unsettled fetch + body operations, across views
// Compressed, verified preview blobs only. Offscreen DOM and decoded images
// still retire; the cache is scoped to this Review view, never localStorage.
const REVIEW_THUMB_CACHE_MAX_BYTES=64*1024*1024,REVIEW_THUMB_CACHE_MAX_ITEMS=4096;
// held: cards decided since the last filter change stay in place, so a
// Keep/Blur click never makes the card vanish and re-flow every row below it.
let REVIEW_FILTER={jobId:null,viewGen:0,type:null,output:"all",held:new Set()};
function resetReviewView(){
 REVIEW_SCHED?.selectionCleanup?.();clearSel();TRKMEM={};ROWCARD={};REVIEW_META=null;
 REVIEW_FILTER={jobId:CUR,viewGen:VIEW_GEN,type:null,output:"all",held:new Set()};
}
function reviewGroupKey(row){
 return row.zone_dropped?null:row.person>=0?'p'+row.person:row.track>=0?'t'+row.track:null;
}
function reviewCategoryName(category){
 return Object.prototype.hasOwnProperty.call(CATDN,category)?CATDN[category]:category;
}
function reviewMetadata(data){
 if(!data||!Number.isFinite(data.duration)||!Array.isArray(data.detections))return null;
 const version=data.thumbnail_version,rows=new Map();
 if(version!==undefined&&(typeof version!=='string'||!/^[0-9a-f]{32}$/.test(version)))return null;
 for(const row of data.detections){
  if(!row||!Number.isInteger(row.i)||row.i<0||rows.has(row.i)||typeof row.category!=='string'||
     !Number.isFinite(row.t_start)||!Number.isFinite(row.t_end))return null;
  const fingerprint=row.thumbnail_row;
  if(version&&(typeof fingerprint!=='string'||!/^[0-9a-f]{64}$/.test(fingerprint)))return null;
  rows.set(row.i,fingerprint);
 }
 return {version,rows,attempted:false,incompatible:new Set()};
}
function checkpointReviewMetadata(data){
 const {duration,processed_duration,processed_frames,total_frames,fps}=data||{};
 if(![duration,processed_duration,fps].every(v=>typeof v==='number'&&Number.isFinite(v)&&v>0)||
    ![processed_frames,total_frames].every(v=>Number.isSafeInteger(v)&&v>0)||processed_frames>total_frames||
    processed_duration>duration||Math.abs(processed_duration-processed_frames/fps)>
     Number.EPSILON*Math.max(1,processed_duration)*16)return null;
 return {duration:processed_duration,frames:processed_frames,total:total_frames,fps};
}
function reviewDescriptors(rows){
 const groups=Object.create(null),zones=[];TRKMEM={};ROWCARD={};
 const policyRows=new Map();
 for(const x of rows){
  if(typeof x.policy_status==='string'&&typeof x.policy_geometry_supported==='boolean')policyRows.set(x.i,x);
  EN[x.i]=(x.i in EDITS.enabled)?EDITS.enabled[x.i]:x.enabled;
  if(x.zone_dropped)zones.push(x);
  else (groups[x.category]=groups[x.category]||[]).push(x);
 }
 const sections=[];
 function section(category,items,zone=false){
  const cards=items.map(x=>{
   const members=zone?[x.i]:TRKMEM[x.i];
   if(!policyRows.size)return {id:x.i,category,realCategory:x.category,zone,representative:x,members};
   const selected=members.filter(i=>policyRows.has(i));
   return {id:x.i,category,realCategory:x.category,zone,representative:x,members,
    ...(selected.length?{policyRows:new Map(selected.map(i=>[i,policyRows.get(i)]))}:{})};
  });
  for(const c of cards)for(const m of c.members)ROWCARD[m]=c.id;
  sections.push({category,zone,index:sections.length,cards,ids:cards.map(c=>c.id)});
 }
 if(zones.length)section('zdrop',zones,true);
 for(const [cat,raw] of Object.entries(groups)){
  const grouped=new Map(),items=[];
  for(const x of raw){
   const key=reviewGroupKey(x);
   if(key){if(!grouped.has(key))grouped.set(key,[]);grouped.get(key).push(x);}
   else{TRKMEM[x.i]=[x.i];items.push(x);}
  }
  for(const [key,members] of grouped){
   members.sort((a,b)=>a.t_start-b.t_start);
   let best=members[0];
   for(const m of members)if((m.confidence||0)>(best.confidence||0))best=m;
   const rep={...best,t_start:members[0].t_start,t_end:members[members.length-1].t_end,
    frames:members.length,personcard:key[0]==='p'};
   TRKMEM[rep.i]=members.map(m=>m.i);items.push(rep);
  }
  items.sort((a,b)=>((b.personcard?1:0)-(a.personcard?1:0))||a.t_start-b.t_start);
  section(cat,items);
 }
 return sections;
}
function reviewCard(c){
 const x=c.representative,cat=c.category;
 const unit=c.policyRows?'sample':'appearance';
 return `<div class="det" id="det${c.id}" data-cat="${detLabel(cat)}">
  <div class="thumbwell"><img alt="Detection preview" style="cursor:zoom-in" onclick="zoomDet(${c.id})"></div>
  <div>${x.personcard?`<b>Person ${x.person+1}</b>`:`&quot;${detLabel(x.text)}&quot;`}${x.frames?` <span class="badge">×${x.frames} ${c.policyRows?'samples':'frames'}</span>`:''}${x.confidence?` <span class="badge" title="detector confidence — low values on a non-face thumbnail usually mean a false detection">${Math.round(x.confidence*100)}%</span>`:''}<br>${fmtTime(x.t_start)}–${fmtTime(x.t_end)}</div>
  ${x.frames>1?`<div class="detscope">Applies to all ${x.frames} ${unit}s in this ${detLabel(reviewCategoryName(cat))} group</div>`:''}
  ${detChoices(c.id,c.zone?'Outside-zone detection':reviewCategoryName(cat),!!c.policyRows)}
  <button type="button" class="sec" data-thumb-reopen hidden onclick="loadReview()">Re-open review</button></div>`;
}
function reviewLoadFailure(id,gen){
 if(document.getElementById('review-load-error'))return;
 const box=document.createElement('div');box.id='review-load-error';box.className='card';
 const message=document.createElement('p');message.textContent='Review could not be loaded. Try again.';
 message.setAttribute?.('role','status');
 const retry=document.createElement('button');retry.type='button';retry.dataset.reviewRetry='';
 retry.textContent='Retry review';
 retry.onclick=()=>{if(ownsView(id,gen)&&document.getElementById(box.id)===box)loadReview();};
 box.appendChild(message);box.appendChild(retry);detail.appendChild(box);
}
function renderReviewAccess(){
 const el=document.getElementById('reviewAccess');if(!el)return;
 el.innerHTML='';
 if(AUTO_REVIEW?.state!=="deferred")return;
 const button=document.createElement('button');button.textContent='Open review';
 button.onclick=()=>loadReview();el.appendChild(button);
}
async function loadReview(auto=null){
 beRetireTrack();
 if(!auto&&EDITS)EDITS.reviewEditorGen=null;
 const id=CUR,gen=VIEW_GEN,intent=BE_OPEN_INTENT,phase=PHPH,request={pending:true,manual:!auto};REVIEW_REQUEST=request;
 const manualAuto=!auto&&AUTO_REVIEW?.state!=="ready"?AUTO_REVIEW:null;
 if(manualAuto)manualAuto.state="loading";
 renderReviewAccess();
 const current=()=>ownsView(id,gen)&&REVIEW_REQUEST===request&&intent===BE_OPEN_INTENT&&PHPH===phase&&
  (!auto||(AUTO_REVIEW===auto&&auto.phase===phase));
 let d,thumbnails,checkpoint=null;
 try{
  const r=await fetch(`api/jobs/${id}/detections`);
  if(!current()){request.pending=false;return;}
  if(!r.ok)throw new Error("Review HTTP "+r.status);
  d=await r.json();
  if(!current()){request.pending=false;return;}
  thumbnails=reviewMetadata(d);
  if(!thumbnails)throw new Error('Invalid review metadata');
  if(phase==='paused'&&!(checkpoint=checkpointReviewMetadata(d)))throw new Error('Invalid processed-prefix metadata');
 }catch(e){
  request.pending=false;
  if(current()){
   if(!auto&&AUTO_REVIEW&&AUTO_REVIEW.state==="loading")AUTO_REVIEW.state="idle";
   renderReviewAccess();reviewLoadFailure(id,gen);if(auto)throw e;
  }
  return;
 }
 request.pending=false;
 if(AUTO_REVIEW)AUTO_REVIEW.state="ready";
 renderReviewAccess();
 disposeReview();showPanel('review');
 document.getElementById('review-load-error')?.remove();
 DUR=d.duration;
 const sections=reviewDescriptors(d.detections);
 REVIEW_META={jobId:id,viewGen:gen,sections,thumbnails,checkpoint,
  byId:new Map(sections.flatMap(s=>s.cards.map(c=>[c.id,c])))};
 const plateMode=d.plate_policy?.uncertain_policy;
 const plateNote=plateMode==='manual_review'
  ?'Plate policy: Review uncertain. Uncertain observations remain unmasked for review.'
  :plateMode==='blur_candidates'
   ?'Plate policy: Blur candidates. Supported candidates may be masked automatically, including short appearances.'
   :plateMode==='off'?'Plate policy is off; saved output and choices are retained.'
   :plateMode==='unavailable'?'Plate policy settings are unavailable. Inspect the report before rendering.':'';
 let html=`<div class="card" id="review"><h2>Review — choose Blur or Keep visible.
 Drag a box around several to bulk-set.</h2>
 ${plateNote?`<p class="detscope">${plateNote}</p>`:''}
 ${checkpoint?`<p role="status">Processed ${checkpoint.frames} of ${checkpoint.total} frames (${checkpoint.duration.toFixed(2)} s). Review only this portion before resuming.</p>`:''}
 <div class="row" style="margin:0 0 8px"><button class="sec" onclick="loadBoxEdit(1)">▶ Preview video &amp; edit boxes (${checkpoint?'processed frames only':'before rendering'})</button></div>
 <div class="row reviewfilters">
  <label>Detection type <select id="reviewType" onchange="setReviewFilter(this.value||null,REVIEW_FILTER.output)"></select></label>
  <label>Output <select id="reviewOutput" onchange="setReviewFilter(REVIEW_FILTER.type,this.value)"></select></label>
  <button class="sec" id="reviewFilterReset" onclick="setReviewFilter(null,'all')">Show all</button>
 </div>
 <div id="reviewFilterStatus" role="status" aria-live="polite"></div>
 <p class="detscope">Mixed groups appear in both output views. Filters only change the view.</p>
 <p id="reviewFilterHint" class="detscope"></p>
 <p id="reviewFilterEmpty" hidden></p>
 <div id="letterGaps" hidden></div>
 <div id="beslot"></div><div class="row reviewranges">
 <button class="sec" data-review-prev onclick="REVIEW_SCHED?.range(-1)">Previous review cards</button>
 <span data-review-range role="status" aria-live="polite"></span>
 <button class="sec" data-review-next onclick="REVIEW_SCHED?.range(1)">Next review cards</button></div>
 <div id="detwrap" style="position:relative;user-select:none">`;
 sections.forEach((section,n)=>{
  const cat=section.category;
  if(section.zone)html+=`<details id="reviewZones" data-review-zones style="margin:4px 0 10px;border:1px dashed #f59e0b;border-radius:9px;padding:8px 10px;background:#26200a">
   <summary style="cursor:pointer;color:#fbbf24;font-weight:600">⚠ <span id="reviewZoneCount">${section.ids.length} of ${section.ids.length}</span> detection(s) outside your zones — choose output below (mostly logos/labels by design; open only if something real was zoned out)</summary>
   <div class="row" style="margin:8px 0 4px"><button class="sec" onclick="setAllZd(true)">Blur all</button><button class="sec" onclick="setAllZd(false)">Keep all visible</button></div>
   <div class="detscope">These actions affect all outside-zone detections, including filtered-out detections.</div>`;
  else html+=`<section id="reviewSection${section.index}"><h3 style="margin:10px 0 6px">${detLabel(reviewCategoryName(cat))} <span class="badge" id="reviewCount${section.index}">${section.ids.length}</span>
   <button class="sec" style="padding:3px 8px;font-size:12px" onclick="setAll(this.dataset.cat,true)" data-cat="${detLabel(cat)}">Blur all</button>
   <button class="sec" style="padding:3px 8px;font-size:12px" onclick="setAll(this.dataset.cat,false)" data-cat="${detLabel(cat)}">Keep all visible</button></h3>
   <div class="detscope">Category actions affect all ${detLabel(reviewCategoryName(cat))} groups, including filtered-out groups.</div>`;
  html+=`<div class="grid3 reviewgrid" data-review-section="${n}"></div>`;
  html+=section.zone?'</details>':'</section>';
 });
 html+=`</div><div class="row" style="margin-top:12px"><button data-save-edits onclick="${checkpoint?'saveAndResume()':'saveAndRender()'}">${checkpoint?'Save &amp; Resume':'Save edits &amp; render'}</button>
 <span style="font-size:12px;color:#94a3b8">missed something? use ▶ Preview video &amp; edit boxes above — its ＋ Add box replaces the old add-region tool</span></div></div>`;
 const old=document.getElementById('review');if(old){beUnmountIn(old);old.remove();}
 detail.insertAdjacentHTML('beforeend',html);
 REVIEW_SCHED=new ReviewScheduler(id,gen,document.getElementById('review'),REVIEW_META);
 refreshReviewFilters();REVIEW_SCHED.start();initMarquee();saveStatus(EDITS,EDITS.status);
 LETTER_GAPS=null;LETTER_GAPS_LOAD=null;
 if(d.assisted_letters)loadLetterGaps(id,gen);
 return BE_OPEN_INTENT;
}
// Assisted plate letters ("letters only, no box fallback"): the gap list is
// computed server-side from the SAVED report. One notice at the top of the
// job, never on individual cards; the render reminder states the count.
let LETTER_GAPS=null,LETTER_GAPS_LOAD=null;   // last list / {jobId,promise} of the Review load
const ASSISTED_RENDER_REMINDER=n=>`Letters only, no box fallback: ${n} gaps listed in Review will not be covered. Render now?`;
// Output-timeline seconds as H:MM:SS.mmm (1:30:23.370), the form a video
// editor's timecode field takes. Milliseconds are rounded once, so 59.9996
// carries into the next minute instead of printing 60.000.
// Review times: h:mm:ss.mmm everywhere (cards, editor, gap list, audio).
function fmtTime(sec){
 const ms=Math.max(0,Math.round((+sec||0)*1000));
 const h=Math.floor(ms/3600000),m=Math.floor(ms/60000)%60,s=Math.floor(ms/1000)%60,r=ms%1000;
 return `${h}:${String(m).padStart(2,"0")}:${String(s).padStart(2,"0")}.${String(r).padStart(3,"0")}`;
}
// "h:mm:ss.mmm", "m:ss.mmm" or plain seconds -> seconds; anything else -> null
function parseTime(text){
 const t=String(text??"").trim();
 if(!/^(\\d+:)?(\\d+:)?\\d+(\\.\\d+)?$/.test(t))return null;
 const parts=t.split(":").map(Number);
 if(parts.slice(1).some(v=>v>=60))return null;
 const v=parts.reduce((acc,p)=>acc*60+p,0);
 return Number.isFinite(v)?Math.round(v*1000)/1000:null;
}
function lgOutTime(sec){
 return fmtTime(sec);
}
async function fetchLetterGaps(id){
 const r=await fetch(`api/jobs/${id}/letter_gaps`);
 if(!r.ok)throw Error("HTTP "+r.status);
 const g=await r.json();
 if(!g||typeof g.mode!=="string"||!Array.isArray(g.gaps))throw Error("invalid gap list");
 LETTER_GAPS={...g,jobId:id};
 return LETTER_GAPS;
}
function startLetterGapLoad(id){
 const promise=fetchLetterGaps(id);promise.catch(()=>{});
 LETTER_GAPS_LOAD={jobId:id,promise};return promise;
}
async function loadLetterGaps(id,gen){
 let g,err=null;
 try{g=await startLetterGapLoad(id);}catch(e){err=e;}
 if(!ownsView(id,gen))return;
 renderLetterGaps(id,g,err);
}
function lgSecs(x){const n=Math.max(0,+x||0);return n<10?n.toFixed(1):String(Math.round(n));}
function lgFrames(x){
 const f0=+(x.out_f0??x.out_frame??x.frame),f1=+(x.out_f1??f0);
 return f1>f0?`frames ${f0}–${f1}`:`frame ${f0}`;
}
function lgDur(x,fps){
 const f0=+x.out_f0,f1=+x.out_f1;
 return fps>0&&Number.isFinite(f0)&&Number.isFinite(f1)?(f1-f0+1)/fps:+x.frames/(fps||1);
}
function renderLetterGaps(id,g,err){
 const el=document.getElementById("letterGaps");if(!el)return;
 if(err){el.hidden=false;el.textContent="Plate letter gaps could not be checked ("+err.message+"). Open Review again to retry.";return;}
 if(g.mode!=="assisted"){el.hidden=true;el.innerHTML="";return;}
 const s=g.stats||{},masked=+s.masked_frames||0,gapf=+s.gap_frames||0,bridged=+s.bridged_frames||0;
 const fps=+g.fps||0,n=g.gaps.length,wasOpen=el.querySelector("details")?.open;
 // floor: never round a partly covered job up to 100%
 const pct=masked+gapf?Math.floor(100*masked/(masked+gapf)):100;
 const total=g.gaps.reduce((a,x)=>a+lgDur(x,fps),0);
 const items=g.gaps.map((x,k)=>`<button type="button" class="lgap" data-gap="${k}" onclick="openLetterGap(${+x.t0},${k})"
  title="Open this moment in the box editor below">
  <span class="lgnum">Gap ${k+1}</span>
  <img loading="lazy" alt="Plate ${k+1} preview" src="api/jobs/${id}/letter_gap/${k}.jpg?v=${encodeURIComponent(g.token||"")}">
  <span class="lgtime">${lgOutTime(x.out_t0??x.t0)} – ${lgOutTime(x.out_t1??x.t1)}</span>
  <span>${lgFrames(x)} · ${lgSecs(lgDur(x,fps))} s</span>
  <span class="lgopen">Open in editor ▸</span></button>`).join("");
 const head=n?`⚠ ${n} gap${n===1?"":"s"} where a plate stays visible (${lgSecs(total)} s in total)`
  :"✓ No plate gaps: letters were found on every plate frame";
 el.hidden=false;
 el.innerHTML=`<details${wasOpen===false?"":" open"}><summary class="lgnotice">${head}</summary>
  <p>Plate cover is <b>Letters only, no box fallback</b>. Letters were covered on ${pct}% of the frames where a plate was found.${n?" In the gaps below a plate was found but its letters were not, so nothing is drawn over it.":""}</p>
  ${n?`<p class="detscope"><b>To fix a gap:</b> cover it in your video editor afterwards (times and frames are in the rendered video), or click it to open that moment in the box editor below and use <b>Track object</b> on the plate (that blurs the whole plate box). Moving or resizing a plate box does not cover a gap.</p>
  <div class="row lgtools"><button type="button" class="sec" onclick="copyLetterGaps()">Copy gap list</button><span id="lgCopied" role="status" aria-live="polite"></span></div>
  <div class="lglist">${items}</div>`:""}
  <p class="detscope">Not listed: plates OpenScrub never found${bridged?`, and ${bridged} frame${bridged===1?"":"s"} where a plate's cover was carried through a short detector dropout (same scene, up to 1 s)`:""}. Watch the whole output. Blur / Keep visible choices change this list after <b>Save edits &amp; render</b>.</p>
  </details>`;
}
function letterGapText(g){
 const fps=+g.fps||0;
 return ["OpenScrub plate gaps (times in the rendered video)"].concat(g.gaps.map((x,k)=>
  `Gap ${k+1}\\t${lgOutTime(x.out_t0??x.t0)} – ${lgOutTime(x.out_t1??x.t1)}\\t${lgFrames(x)}\\t${lgSecs(lgDur(x,fps))} s`)).join("\\n")+"\\n";
}
async function copyLetterGaps(){
 const g=LETTER_GAPS,st=document.getElementById("lgCopied");if(!g||!st)return;
 const text=letterGapText(g);
 try{await navigator.clipboard.writeText(text);st.textContent="Copied "+g.gaps.length+" gaps.";return;}catch(_){}
 // No clipboard (plain-HTTP page or blocked): show the text, selected, to copy by hand.
 st.innerHTML='<textarea id="lgCopyText" readonly rows="4" style="width:100%"></textarea>';
 const ta=document.getElementById("lgCopyText");ta.value=text;ta.focus();ta.select();
}
async function openLetterGap(t0,k){
 const id=CUR,gen=VIEW_GEN;
 document.querySelectorAll("#letterGaps .lgap").forEach(b=>b.classList.toggle("lgcur",+b.dataset.gap===k));
 await loadBoxEdit(true);
 if(!ownsView(id,gen))return;
 const sl=document.getElementById("beT");if(!sl||!Number.isFinite(t0))return;
 const cp=BE_VIEW?.checkpoint;
 sl.value=String(cp?Math.floor(t0*cp.fps):t0);
 beScrub();
 document.getElementById("beslot")?.scrollIntoView({block:"start",behavior:"smooth"});
}
// Assisted jobs only (Review / done view start a gap load for them, so an
// ordinary job's save stays synchronous and is never asked).
function assistedLetterJob(id){
 return !!(LETTER_GAPS_LOAD&&LETTER_GAPS_LOAD.jobId===id||LETTER_GAPS&&LETTER_GAPS.jobId===id&&LETTER_GAPS.mode==="assisted");
}
// Runs AFTER the edits are saved: the count comes from a fresh gap list of
// the report just written, never from the list loaded before the edits.
async function assistedRenderConfirm(id,gen){
 let g=null,err=null;
 try{g=await fetchLetterGaps(id);}catch(e){err=e;}
 if(!ownsView(id,gen))return false;
 renderLetterGaps(id,g,err);
 if(err)return confirm("The plate letter gap list could not be checked. Render now?");
 return g.mode!=="assisted"||confirm(ASSISTED_RENDER_REMINDER(g.gaps.length));
}
function disposeReview(){
 if(REVIEW_SCHED){const old=REVIEW_SCHED;REVIEW_SCHED=null;old.dispose();}
}
// P15 seam: matchingCardIds is the COMPLETE matching descriptor set. P15 owns
// predicates/counts/focus fallback. This local hook never writes choices or I/O.
function refreshReviewVisibleSet({jobId,viewGen,matchingCardIds}={}){
 const s=REVIEW_SCHED;
 if(!s||s.jobId!==jobId||s.viewGen!==viewGen||!s.owns())return;
 if(matchingCardIds!==undefined)s.matching=new Set(matchingCardIds.filter(i=>s.meta.byId.has(i)));
 s.schedule();
}
// One review-instance owner. It never owns output, editor or unrelated requests.
class ReviewScheduler{
 constructor(jobId,viewGen,root,meta){
  Object.assign(this,{jobId,viewGen,root,meta});
  if(!meta.lightboxFailures)meta.lightboxFailures=new Set();
   this.thumbCache=meta.thumbCache||(meta.thumbCache={entries:new Map(),bytes:0});
  this.token={};this.disposed=false;this.frame=0;this.bindings=new Map();
  this.retries=new Map();this.eligible=new Map();this.queue=[];this.listeners=[];
  this.matching=new Set(meta.byId.keys());this.sections=[];this.normalIds=[];
  this.gesture=false;this.selectionCleanup=null;this.lightbox=null;this.thumbnailRefresh=null;
 }
 owns(){return !this.disposed&&REVIEW_SCHED===this&&ownsView(this.jobId,this.viewGen)&&
  this.root.isConnected&&document.getElementById('review')===this.root;}
 valid(b,eligible=true){
  if(!this.owns()||!b.img.isConnected)return false;
  if(b.overlay)return this.lightbox===b&&b.overlay.isConnected&&b.overlay.contains(b.img)&&this.valid(b.source,false);
  return this.bindings.get(b.id)===b&&b.card.isConnected&&(!eligible||this.eligible.has(b.id));
 }
 listen(target,event,fn,options){target.addEventListener(event,fn,options);
  this.listeners.push(()=>target.removeEventListener(event,fn,options));}
 start(){
  this.sections=this.meta.sections.map((data,n)=>({data,el:this.root.querySelector(`[data-review-section="${n}"]`),
   ids:[],columns:0,width:0,heights:[],prefix:[0],rows:new Map(),spacers:[],cardHeights:new Map()}));
  this.observer=new ResizeObserver(()=>this.schedule());
  this.observer.observe(this.root);
  this.listen(window,'scroll',()=>this.schedule(),{passive:true});
  this.listen(window,'resize',()=>this.schedule(),{passive:true});
  this.listen(this.root,'focusin',()=>this.schedule());
  this.listen(this.root,'focusout',()=>this.schedule());
  const zones=this.root.querySelector('[data-review-zones]');
  if(zones)this.listen(zones,'toggle',()=>{
   if(this.owns())reviewZoneToggle(zones);
  });
  this.listen(window,'pagehide',()=>this.dispose({suspend:true}));
  this.layout();
 }
 schedule(){if(!this.owns()||this.frame)return;
  this.frame=requestAnimationFrame(()=>{this.frame=0;if(this.owns())this.layout();});}
 prefix(section){
  section.prefix=[0];for(const h of section.heights)section.prefix.push(section.prefix.at(-1)+h+9);
  section.el.style.height=Math.max(0,section.prefix.at(-1)-9)+'px';
 }
 rowAt(section,y){
  let lo=0,hi=section.heights.length;
  while(lo<hi){const mid=(lo+hi)>>1;if(section.prefix[mid+1]<=y)lo=mid+1;else hi=mid;}
  return Math.min(lo,Math.max(0,section.heights.length-1));
 }
 anchor(){
  let best=null;
  for(const b of this.bindings.values()){
   if(b.card.dataset.focusPin==='1')continue;
   const r=b.card.getBoundingClientRect();
   if(r.bottom>0&&r.top<window.innerHeight&&(!best||r.top<best.top))best={id:b.id,top:r.top};
  }return best;
 }
 // Reconcile siblings around the actual focused subtree. Moving its other
 // siblings preserves native Tab order without detaching the focused ancestor.
 orderNodes(parent,nodes,active){
  let next=null;
  for(let n=nodes.length-1;n>=0;n--){const node=nodes[n];
   if(!node.contains(active)&&node.nextElementSibling!==next)parent.insertBefore(node,next);
   next=node;
  }
 }
 layout(){
  if(!this.owns()||this.gesture)return;
  let anchor=this.anchor();const active=document.activeElement;
  const focus=active?.closest?.('.det'),focusId=focus?+focus.id.slice(3):null;
  let changed=false;
  for(const section of this.sections){
   const open=!section.data.zone||section.el.closest('details').open;
   const ids=open?section.data.ids.filter(id=>this.matching.has(id)):[];
   const rect=section.el.getBoundingClientRect(),width=section.el.clientWidth;
   section.scale=width?rect.width/width:1;
   const tracks=getComputedStyle(section.el).gridTemplateColumns;
   const columns=tracks&&tracks!=='none'?tracks.split(' ').length:1;
   if(section.width!==width||section.columns!==columns||ids.length!==section.ids.length||ids.some((id,n)=>id!==section.ids[n])){
    if(section.width&&section.width!==width&&this.lastAnchor)anchor=this.lastAnchor;
    // Card heights depend on the column width only; a filter change reuses them
    // so rows below the first do not jump to the estimate and back (flash).
    if(section.width!==width||section.columns!==columns)section.cardHeights=new Map();
    section.width=width;section.columns=columns;section.ids=ids;
    section.heights=Array.from({length:Math.ceil(ids.length/columns)},(_,n)=>
     Math.max(0,...ids.slice(n*columns,(n+1)*columns).map(id=>section.cardHeights.get(id)||0))||260);changed=true;
   }else for(const [n,row] of section.rows){
    if(row.dataset.pin==='1')continue;
    const h=row.getBoundingClientRect().height/section.scale;
    if(h){for(const id of section.ids.slice(n*section.columns,(n+1)*section.columns))section.cardHeights.set(id,h);}
    if(h&&Math.abs(section.heights[n]-h)>.5){section.heights[n]=h;changed=true;}
   }
   this.prefix(section);
  }
  // Correct estimates/widths without shifting the user's first visible card.
  if(changed&&anchor){
   for(const section of this.sections){const n=section.ids.indexOf(anchor.id);if(n<0)continue;
    const top=section.el.getBoundingClientRect().top+section.prefix[Math.floor(n/section.columns)]*section.scale;
    window.scrollBy(0,top-anchor.top);break;}
  }
  const candidates=[],nearby=[];
  for(const section of this.sections){
   if(!section.ids.length)continue;
   const top=section.el.getBoundingClientRect().top;
   const end=section.prefix.at(-1)-9,scale=section.scale;
   if(top>window.innerHeight||top+end*scale<0)continue;
   const first=this.rowAt(section,Math.max(0,-top/scale));
   const last=this.rowAt(section,Math.min(end,(window.innerHeight-top)/scale));
   for(let n=first;n<=last;n++)candidates.push({section,n,rank:0});
   for(let n=last+1;n<section.heights.length&&(section.prefix[n]-section.prefix[last+1])*scale<window.innerHeight;n++)
    nearby.push({section,n,rank:1});
   for(let n=first-1;n>=0&&(section.prefix[first]-section.prefix[n+1])*scale<window.innerHeight;n--)
    nearby.push({section,n,rank:1});
  }
  const selected=new Map(),desired=new Map();let used=0,prefetch=0;
  function admit(item){const {section,n,rank}=item;
   const ids=section.ids.slice(n*section.columns,(n+1)*section.columns);
   if(used+ids.length>64)return false;
   if(rank&&prefetch+(section.heights[n]+9)*section.scale>window.innerHeight)return false;
   if(!selected.has(section))selected.set(section,new Set());selected.get(section).add(n);
   for(const id of ids)desired.set(id,{rank,order:desired.size});
   used+=ids.length;if(rank)prefetch+=(section.heights[n]+9)*section.scale;return true;
  }
  candidates.forEach(admit);nearby.forEach(admit);
  this.normalIds=[...desired.keys()];
  // Keep one actual focused subtree. Its row contains only that card, at its
  // original column; a selected card alone never receives a retention pin.
  const pin=focusId!==null&&!desired.has(focusId)&&this.bindings.has(focusId)&&
   this.sections.some(s=>s.ids.includes(focusId))?focusId:null;
  for(const [id,b]of this.bindings)if(!desired.has(id)&&id!==pin)this.retire(b);
  for(const section of this.sections){
   const rows=selected.get(section)||new Set();
   const pinIndex=pin===null?-1:section.ids.indexOf(pin),pinRow=pinIndex<0?-1:Math.floor(pinIndex/section.columns);
   for(const [n,row]of section.rows)if(!rows.has(n)&&n!==pinRow){this.observer.unobserve(row);row.remove();section.rows.delete(n);}
   const needed=new Set(rows);if(pinRow>=0)needed.add(pinRow);
   const orderedRows=[];
   for(const n of [...needed].sort((a,b)=>a-b)){
    let row=section.rows.get(n);
    if(!row){row=document.createElement('div');row.className='grid3 reviewrow';section.el.appendChild(row);
     section.rows.set(n,row);this.observer.observe(row);}
    orderedRows.push(row);
    row.style.top=section.prefix[n]+'px';row.dataset.pin=String(!rows.has(n)?1:0);
    const ids=section.ids.slice(n*section.columns,(n+1)*section.columns),orderedCards=[];
    for(const [col,id]of ids.entries()){
     if(!desired.has(id)&&id!==pin)continue;
     let b=this.bindings.get(id);
     if(!b){
      const holder=document.createElement('div');holder.innerHTML=reviewCard(this.meta.byId.get(id));
      const card=holder.firstElementChild,img=card.querySelector('img');
      b={id,card,img,token:{},url:null,op:null};this.bindings.set(id,b);
      this.previewStatus(b,false);
     }
     if(b.card.parentElement!==row)row.appendChild(b.card);orderedCards.push(b.card);
     b.card.style.gridColumn=String(col+1);b.card.dataset.focusPin=String(id===pin?1:0);
     b.card.classList.toggle('selected',selSet.has(id));refreshDet(id);
    }
    this.orderNodes(row,orderedCards,active);
   }
   for(const spacer of section.spacers)spacer.remove();section.spacers=[];
   this.orderNodes(section.el,orderedRows,active);
   // Constant before/after spacers (plus a focused row, if any). Offscreen
   // rows are numeric heights only; no per-group placeholder/HTML is kept.
   const ns=[...rows].sort((a,b)=>a-b),first=ns[0]??0,last=ns.at(-1)??-1;
   for(const [top,height]of [[0,section.prefix[first]||0],[section.prefix[last+1]||0,
    section.prefix.at(-1)-(section.prefix[last+1]||0)]]){
    const spacer=document.createElement('div');spacer.className='reviewspacer';
    spacer.setAttribute('aria-hidden','true');spacer.style.top=top+'px';spacer.style.height=height+'px';
    section.el.appendChild(spacer);section.spacers.push(spacer);
   }
  }
  if(active?.isConnected&&document.activeElement!==active)active.focus({preventScroll:true});
  this.eligible=desired;this.updateQueue();this.rangeFeedback();this.lastAnchor=this.anchor();
 }
 rangeFeedback(){
  const ids=this.sections.flatMap(s=>s.ids),mounted=new Set(this.normalIds),positions=[];
  ids.forEach((id,n)=>{if(mounted.has(id))positions.push(n)});
  const first=positions[0]??-1,last=positions.at(-1)??-1;
  this.rangeIds=ids;this.rangeFirst=first;this.rangeLast=last;
  const status=this.root.querySelector('[data-review-range]');
  status.textContent=first<0?`${ids.length} review cards; scroll to view`:`Cards ${first+1}–${last+1} of ${ids.length}`;
  this.root.querySelector('[data-review-prev]').disabled=!ids.length||first===0;
  this.root.querySelector('[data-review-next]').disabled=!ids.length||last===ids.length-1;
 }
 range(direction){
  if(!this.owns())return;
  const ids=this.rangeIds||[],index=direction>0?Math.max(0,this.rangeLast+1):
   (this.rangeFirst<0?ids.length-1:Math.max(0,this.rangeFirst-1));
  const id=ids[index];if(id===undefined)return;
  for(const section of this.sections){const n=section.ids.indexOf(id);if(n<0)continue;
   const top=section.el.getBoundingClientRect().top+window.scrollY+section.prefix[Math.floor(n/section.columns)]*section.scale;
   window.scrollTo(0,Math.max(0,top-55));this.layout();
   this.bindings.get(id)?.card.querySelector('button')?.focus({preventScroll:true});break;}
 }
 retryState(id){if(!this.retries.has(id))this.retries.set(id,{failures:0,pending:0,readyAt:0,timer:0});return this.retries.get(id);}
 retryFor(b){return b.retry||this.retryState(b.id);}
 rememberThumb(b,blob){
  if(b.overlay||!Number.isSafeInteger(blob?.size)||blob.size<=0||
     blob.size>REVIEW_THUMB_CACHE_MAX_BYTES)return;
  const cache=this.thumbCache,old=cache.entries.get(b.id);
  if(old){cache.bytes-=old.size;cache.entries.delete(b.id);}
  cache.entries.set(b.id,{blob,size:blob.size});cache.bytes+=blob.size;
  while(cache.bytes>REVIEW_THUMB_CACHE_MAX_BYTES||cache.entries.size>REVIEW_THUMB_CACHE_MAX_ITEMS){
   const id=cache.entries.keys().next().value,entry=cache.entries.get(id);
   cache.entries.delete(id);cache.bytes-=entry.size;
  }
 }
 forgetThumb(id){
  const cache=this.thumbCache,entry=cache.entries.get(id);
  if(entry){cache.entries.delete(id);cache.bytes-=entry.size;}
 }
 clearThumbCache(){this.thumbCache.entries.clear();this.thumbCache.bytes=0;}
 displayThumb(b,blob,current){
  const urlValue=URL.createObjectURL(blob);
  if(!current()){URL.revokeObjectURL(urlValue);return false;}
  b.url=urlValue;
  b.img.onload=()=>{if(current()&&b.url===urlValue){
   const r=this.retryFor(b);this.clearRetryTimer(r);
   r.failures=0;r.pending=0;r.readyAt=0;
   this.rememberThumb(b,blob);this.previewStatus(b,false);
  }};
  b.img.onerror=()=>{if(current()&&b.url===urlValue){
   if(!b.overlay)this.forgetThumb(b.id);
   this.fail(b);
  }};
  b.img.src=urlValue;
  return true;
 }
 reuseThumb(b){
  if(b.overlay||this.meta.thumbnails?.incompatible.has(b.id))return false;
  const cache=this.thumbCache,entry=cache.entries.get(b.id);
  if(!entry)return false;
  // Refresh LRU order, but do not start a fetch or consume a network slot.
  cache.entries.delete(b.id);cache.entries.set(b.id,entry);
  const version=this.meta.thumbnails?.version;
  const current=()=>this.valid(b)&&this.meta.thumbnails?.version===version;
  return this.displayThumb(b,entry.blob,current);
 }
 clearURL(b){
  b.img.onload=null;b.img.onerror=null;b.img.removeAttribute('src');
  if(b.url){URL.revokeObjectURL(b.url);b.url=null;}
 }
 cancel(b){if(b.op&&!b.op.cancelled){b.op.cancelled=true;b.op.controller.abort();}}
 clearRetryTimer(r){if(r?.timer){clearTimeout(r.timer);r.timer=0;}}
 retire(b){
  if(this.lightbox?.source===b)this.closeLightbox();
  this.cancel(b);this.clearURL(b);this.bindings.delete(b.id);
  this.clearRetryTimer(this.retries.get(b.id));
  b.card.remove?.();
 }
 openLightbox(id){
  const source=this.bindings.get(id);
  if(!source||!this.valid(source,false)||this.meta.thumbnails?.incompatible.has(id))return;
  this.closeLightbox();
  const overlay=document.createElement('div');overlay.id='lb';
  overlay.style.cssText='position:fixed;inset:0;background:rgba(0,0,0,.82);'+
   'z-index:100;display:flex;align-items:center;justify-content:center;cursor:zoom-out;padding:18px';
  overlay.innerHTML=`<img alt="Detection frame" style="max-width:96%;max-height:96%;border-radius:8px;box-shadow:0 12px 50px rgba(0,0,0,.6)">
   <div data-thumb-status hidden><p role="status">Preview unavailable. Re-open review to refresh.</p>
   <button type="button" class="sec" data-thumb-reopen>Re-open review</button></div>`;
  const b={id,source,overlay,img:overlay.querySelector('img'),token:{},url:null,op:null,
   retry:{failures:0,readyAt:0,timer:0},status:overlay.querySelector('[data-thumb-status]')};
  document.body.appendChild(overlay);this.lightbox=b;
  overlay.onclick=()=>{if(this.lightbox===b){this.closeLightbox();this.updateQueue();}};
  overlay.querySelector('[data-thumb-reopen]').onclick=event=>{
   event.stopPropagation();
   if(this.valid(b))loadReview();
  };
  this.updateQueue();
 }
 closeLightbox(){
  const b=this.lightbox;if(!b)return;
  this.lightbox=null;this.cancel(b);this.clearURL(b);this.clearRetryTimer(b.retry);
  b.overlay.remove();
 }
 previewStatus(b,unavailable){
  if(b.overlay){b.status.hidden=!unavailable;b.img.hidden=unavailable;}
  else b.img.parentElement.classList[unavailable?'add':'remove']('unavailable');
  const card=b.source||b;
  if(b.overlay){
   if(unavailable)this.meta.lightboxFailures.add(card.id);
   else this.meta.lightboxFailures.delete(card.id);
  }
  const reopen=card.card.querySelector?.('[data-thumb-reopen]');
  if(reopen)reopen.hidden=!(this.meta.lightboxFailures.has(card.id)||this.retries.get(card.id)?.failures>=4||
   this.meta.thumbnails?.incompatible.has(card.id));
 }
 fail(b,obsolete=false){
  if(!this.valid(b))return;
  this.clearURL(b);const r=this.retryFor(b);
  r.pending=0;r.failures=obsolete?4:r.failures+1;
  if(r.failures>=4){
   this.previewStatus(b,true);
   this.recoverThumbnails();
  }else r.readyAt=Date.now()+600*r.failures;
  this.updateQueue();
 }
 // A scan/fill owner may still be preparing this card. Delay pending work
 // without exhausting the normal network/decoder failure budget.
 deferPending(b){
  if(!this.valid(b))return;
  this.clearURL(b);const r=this.retryFor(b);
  r.pending=(r.pending||0)+1;
  if(r.pending>=6){
   r.failures=4;this.previewStatus(b,true);
  }else r.readyAt=Date.now()+Math.min(8000,1000*2**(r.pending-1));
  this.updateQueue();
 }
 async recoverThumbnails(){
  const state=this.meta.thumbnails;
  if(!state?.version||state.attempted)return;
  state.attempted=true;
  const controller=new AbortController(),version=state.version;
  this.thumbnailRefresh=controller;
  try{
   const r=await fetch(`api/jobs/${this.jobId}/detections`,{cache:'no-store',signal:controller.signal});
   if(!this.owns()||!r.ok)return;
   const data=await r.json();
   if(!this.owns())return;
   const next=reviewMetadata(data);
   if(!next?.version||next.version===version)return;
   const groups=new Map();
   for(const row of data.detections){
    const key=reviewGroupKey(row);if(!key)continue;
    const group=JSON.stringify([row.category,key]);
    if(!groups.has(group))groups.set(group,new Set());
    groups.get(group).add(row.i);
   }
   for(const card of this.meta.byId.values()){
    const key=reviewGroupKey(card.representative);
    const group=key?groups.get(JSON.stringify([card.realCategory,key])):null;
    const sameGroup=!key||(group?.size===card.members.length&&card.members.every(id=>group.has(id)));
    if(!sameGroup||card.members.some(id=>state.rows.get(id)!==next.rows.get(id)))state.incompatible.add(card.id);
   }
   state.version=next.version;
   // Cached blobs belong to the old generation even if row IDs still match.
   this.clearThumbCache();
   // Compatible descriptors may remount later. Only the current scheduler
   // can cancel old reads, revoke URLs, or publish to connected bindings.
   for(const r of this.retries.values())this.clearRetryTimer(r);
   this.retries.clear();
   for(const b of this.bindings.values()){
    this.cancel(b);this.clearURL(b);
    this.previewStatus(b,state.incompatible.has(b.id));
   }
   if(this.lightbox){
    const b=this.lightbox;this.cancel(b);this.clearURL(b);this.clearRetryTimer(b.retry);
    b.retry={failures:0,readyAt:0,timer:0};
    if(state.incompatible.has(b.id))this.previewStatus(b,true);
   }
  }catch(error){/* Keep the current review and the spent budget. */}
  finally{
   this.thumbnailRefresh=null;
   if(this.owns())this.updateQueue();
  }
 }
 updateQueue(){
  if(!this.owns())return;
  this.queue=[];
  for(const [id,b]of this.bindings){
   const priority=this.eligible.get(id);
   if(!priority){this.cancel(b);this.clearRetryTimer(this.retries.get(id));}
   this.queueBinding(b,priority);
  }
  if(this.lightbox)this.queueBinding(this.lightbox,{rank:0,order:-1});
  this.queue.sort((a,b)=>a.rank-b.rank||a.order-b.order);this.pump();
 }
 queueBinding(b,priority){
  const r=this.retryFor(b);
  if(this.meta.thumbnails?.incompatible.has(b.id)||r.failures>=4){
   this.previewStatus(b,true);return;
  }
  if(!priority||b.url||b.op||this.thumbnailRefresh)return;
  if(this.reuseThumb(b))return;
  if(r.readyAt>Date.now()){
   if(!r.timer){const token=b.token;
    r.timer=setTimeout(()=>{r.timer=0;if(this.valid(b)&&b.token===token)this.updateQueue();},r.readyAt-Date.now());}
   return;
  }
  this.queue.push({b,rank:b.overlay?-1:priority.rank?2:r.failures?1:0,order:priority.order});
 }
 pump(){
  if(!this.owns())return;
  while(THUMB_FLIGHTS.size<4&&this.queue.length){
   const {b}=this.queue.shift();if(!this.valid(b)||b.op||b.url)continue;
   this.request(b);
  }
 }
 async request(b){
  const controller=new AbortController(),op={controller,cancelled:false,token:b.token};
  const version=this.meta.thumbnails?.version,kind=b.overlay?'detframe':'thumb';
  const current=()=>!op.cancelled&&this.valid(b)&&b.token===op.token&&this.meta.thumbnails?.version===version;
  b.op=op;THUMB_FLIGHTS.add(op);
  try{
   const url=new URL(`api/jobs/${this.jobId}/${kind}/${b.id}`,document.baseURI);
   if(version)url.searchParams.set('v',version);
   if(this.retryFor(b).failures)url.searchParams.set('r',String(Date.now()));
   const response=await fetch(url.href,{signal:controller.signal});
   if(response.status===409){
    const problem=await response.json().catch(()=>null);
    if(current()){
     if(problem?.error==='thumbnail_pending')this.deferPending(b);
     else this.fail(b,!!version&&problem?.error==='thumbnail_obsolete');
    }
    return;
   }
   const blob=await response.blob();
   if(!response.ok)throw Error('Thumbnail HTTP '+response.status);
   if(!current())return;
   this.displayThumb(b,blob,current);
  }catch(error){if(current())this.fail(b);}
  finally{
   if(b.op===op)b.op=null;THUMB_FLIGHTS.delete(op);
   // Replacements can mount immediately, but never borrow an unsettled slot.
   if(REVIEW_SCHED?.owns())REVIEW_SCHED.updateQueue();
  }
 }
 dispose({suspend=false}={}){
  if(this.disposed){if(!suspend){this.retries.clear();this.clearThumbCache();this.suspended=false;}return;}
  this.disposed=true;this.suspended=suspend;
  this.thumbnailRefresh?.abort();this.closeLightbox();
  if(this.frame)cancelAnimationFrame(this.frame);this.frame=0;
  this.observer?.disconnect();this.listeners.splice(0).forEach(remove=>remove());
  this.selectionCleanup?.();this.selectionCleanup=null;
  const wrap=this.root.querySelector?.('#detwrap');if(wrap)delete wrap.dataset.mq;
  for(const b of [...this.bindings.values()])this.retire(b);
  for(const section of this.sections){
   for(const row of section.rows.values())row.remove();section.rows.clear();
   for(const spacer of section.spacers)spacer.remove();section.spacers=[];
  }
  for(const r of this.retries.values())if(r.timer)clearTimeout(r.timer);
  if(!suspend)this.clearThumbCache();
  // A hidden page keeps only numeric retry history for this exact view.
  // Timers/bindings/controllers belong to the retired scheduler, never resume.
  this.retries=suspend?new Map([...this.retries].map(([id,r])=>
   [id,{failures:r.failures,pending:r.pending||0,readyAt:r.readyAt,timer:0}])):new Map();
  this.eligible.clear();this.queue=[];
  clearSel();if(marqEl){marqEl.remove();marqEl=null;}mStart=null;
 }
}
// Back/forward-cache restoration reuses this view's complete metadata/drafts.
window.addEventListener?.('pageshow',()=>{
 const s=REVIEW_SCHED;
 if(s?.disposed&&s.suspended&&ownsView(s.jobId,s.viewGen)&&s.root.isConnected&&document.getElementById('review')===s.root){
  REVIEW_SCHED=new ReviewScheduler(s.jobId,s.viewGen,s.root,s.meta);
  REVIEW_SCHED.matching=s.matching;REVIEW_SCHED.retries=s.retries;
  s.retries=new Map();s.suspended=false;
  REVIEW_SCHED.start();initMarquee();
 }
});
function reviewOn(card,i){
 const evidence=card.policyRows?.get(i);
 if(evidence?.policy_status==='unknown')return null;
 return !!EN[i]&&(!evidence||evidence.policy_geometry_supported===true);
}
function reviewMatches(card,type,output){
 return (type===null||card.realCategory===type)&&(output==="all"||
  card.members.some(i=>output==="blur"?reviewOn(card,i)===true:reviewOn(card,i)===false));
}
function setReviewFilter(type,output){
 if(!ownsView(REVIEW_FILTER.jobId,REVIEW_FILTER.viewGen))return;
 REVIEW_SCHED?.selectionCleanup?.();clearSel();REVIEW_FILTER.type=type;REVIEW_FILTER.output=output;
 REVIEW_FILTER.held.clear();
 refreshReviewFilters();
}
function reviewSelectable(i){
 const c=REVIEW_META?.byId.get(i);if(!c||!reviewMatches(c,REVIEW_FILTER.type,REVIEW_FILTER.output))return false;
 return !c.zone||!!document.getElementById("reviewZones")?.open;
}
function pruneReviewSelection(){
 let changed=false;
 for(const i of [...selSet])if(!reviewSelectable(i)){
  selSet.delete(i);document.getElementById("det"+i)?.classList.remove("selected");changed=true;}
 if(changed&&menuEl){
  if(!selSet.size){menuEl.remove();menuEl=null;}
  else menuEl.querySelector("span").textContent=selSet.size+" selected";
 }
}
function reviewZoneToggle(node){
 if(!ownsView(REVIEW_FILTER.jobId,REVIEW_FILTER.viewGen)||
  (node&&node!==document.getElementById("reviewZones")))return;
 pruneReviewSelection();refreshReviewFilters();
}
function refreshReviewFilters(){
 if(!ownsView(REVIEW_FILTER.jobId,REVIEW_FILTER.viewGen))return;
 const typeControl=document.getElementById("reviewType"),outputControl=document.getElementById("reviewOutput");
 if(!typeControl||!outputControl)return;
 const types=[...new Set([...[...REVIEW_META.byId.values()].filter(c=>!c.zone),...[...REVIEW_META.byId.values()].filter(c=>c.zone)].map(c=>c.realCategory))];
 if(REVIEW_FILTER.type!==null&&!types.includes(REVIEW_FILTER.type))REVIEW_FILTER.type=null;
 const {type,output}=REVIEW_FILTER,typeCounts=new Map(types.map(t=>[t,0])),outputCounts={all:0,blur:0,visible:0};
 let count=0,ordinary=0,zones=0,otherTypeCount=0,held=0;
 const sectionCounts=new Map(REVIEW_META.sections.map(s=>[s.index,0]));
 const matching=[];
 const active=document.activeElement,focusedCard=active?.closest?.(".det");
 let lostFocus=false;
 // Derive aggregates once per transaction, independently of mounted/closed cards.
 for(const s of REVIEW_META.sections)for(const c of s.cards){
  let blurred=0,kept=0;for(const i of c.members){
   const on=reviewOn(c,i);if(on===true)blurred++;else if(on===false)kept++;}
  const typeMatch=type===null||c.realCategory===type;
  const outputMatch=output==="all"||(output==="blur"?blurred>0:kept>0),match=typeMatch&&outputMatch;
  if(outputMatch){typeCounts.set(c.realCategory,typeCounts.get(c.realCategory)+1);otherTypeCount++;}
  if(typeMatch){outputCounts.all++;if(blurred)outputCounts.blur++;if(kept)outputCounts.visible++;}
  if(match){matching.push(c.id);count++;if(c.zone)zones++;else ordinary++;sectionCounts.set(s.index,sectionCounts.get(s.index)+1);}
  const shown=match||typeMatch&&REVIEW_FILTER.held.has(c.id);
  if(!match&&shown){matching.push(c.id);held++;sectionCounts.set(s.index,sectionCounts.get(s.index)+1);}
  const node=document.getElementById("det"+c.id);
  if(node&&!shown&&focusedCard===node)lostFocus=true;
 }
 typeControl.innerHTML=`<option value="">All detected types (${otherTypeCount})</option>`+types.map(t=>`<option value="${detLabel(t)}">${detLabel(reviewCategoryName(t))} (${typeCounts.get(t)})</option>`).join("");
 typeControl.value=type??"";
 outputControl.innerHTML=[["all","All outputs"],["blur","Includes blurred appearances"],["visible","Includes visible appearances"]].map(([v,label])=>`<option value="${v}">${label} (${outputCounts[v]})</option>`).join("");
 outputControl.value=output;
 const zoneDetails=document.getElementById("reviewZones");
 for(const s of REVIEW_META.sections){
  const n=sectionCounts.get(s.index),node=document.getElementById(s.zone?"reviewZones":"reviewSection"+s.index);
  if(node){if(!n&&node.contains?.(active))lostFocus=true;node.hidden=!n;}
  const badge=document.getElementById(s.zone?"reviewZoneCount":"reviewCount"+s.index);
  if(badge)badge.textContent=s.zone?`${n} of ${s.cards.length}`:String(n);
 }
 document.getElementById("reviewFilterStatus").textContent=`${count} of ${[...REVIEW_META.byId.values()].length} cards match`+
  (held?` · ${held} just reviewed shown until filters change`:"");
 const empty=document.getElementById("reviewFilterEmpty");empty.hidden=count+held>0;
 empty.textContent=[...REVIEW_META.byId.values()].length?"No cards match these filters.":"No detections in this job.";
 document.getElementById("reviewFilterHint").textContent=count>0&&!ordinary&&zones&&!zoneDetails?.open?
  `${zones} matching card${zones===1?" is":"s are"} outside your zones; open that section to inspect them.`:"";
 pruneReviewSelection();
 if(lostFocus)outputControl.focus({preventScroll:true});
 refreshReviewVisibleSet({jobId:REVIEW_META.jobId,viewGen:REVIEW_META.viewGen,matchingCardIds:matching});
}

function detLabel(s){return String(s).replace(/[&<>"\']/g,c=>({"&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;","\'":"&#39;"}[c]));}
function detChoices(i,category,samples=false){
 const count=(TRKMEM[i]||[i]).length;
 const unit=samples?'sample':'appearance';
 return `<div class="detlabel" id="dl${i}" role="status" hidden></div><div class="detstate" id="ds${i}"></div>
 <div class="detchoices" id="dc${i}" role="group"
  aria-label="${detLabel(category)} output, ${unit} ${i+1}, ${count} ${unit}${count===1?"":"s"}"
  aria-describedby="ds${i}">
  <button class="blurbtn blur" id="bb${i}" aria-pressed="false"
   onclick="applyDet(${i},true)">Blur</button>
  <button class="blurbtn keep" id="kb${i}" aria-pressed="false"
   onclick="applyDet(${i},false)">Keep visible</button></div>`;
}
function setDetLabel(i,card,state,text){
 const label=document.getElementById("dl"+i);
 if(label){label.hidden=false;label.dataset.state=state;label.textContent=text;}
 if(card)card.dataset.state=state;
}
function refreshDet(i){
 const members=TRKMEM[i]||[i],meta=REVIEW_META?.byId.get(i);
 const blurred=members.reduce((n,m)=>n+(meta?reviewOn(meta,m):!!EN[m]),0);
 const kept=members.length-blurred;
 const state=document.getElementById("ds"+i),card=document.getElementById("det"+i);
 if(meta?.policyRows){
  let uncertain=0,gaps=0,automatic=0,unknown=0;const choices=[];
  for(const m of members){
   const row=meta.policyRows.get(m),pending=Object.prototype.hasOwnProperty.call(EDITS.enabled,m);
   if(row&&!row.policy_geometry_supported)gaps++;
   if(row?.policy_status==='suggestion'&&!pending)uncertain++;
   if(row?.policy_status==='automatic'&&!pending)automatic++;
   if(row?.policy_status==='unknown')unknown++;
   choices.push(pending?(EDITS.enabled[m]?'blur':'keep'):(row?.output_choice||null));
  }
  let text=unknown?'Plate policy unavailable; inspect before rendering':
   `${blurred} of ${members.length} samples will be blurred`;
  if(uncertain)text+=` · ${uncertain} uncertain observation${uncertain===1?' remains':'s remain'} unmasked`;
  if(gaps)text+=` · ${gaps} unsupported sample${gaps===1?'':'s'} cannot be blurred without mask geometry`;
  if(automatic)text+=` · ${automatic} automatic mask${automatic===1?'':'s'}`;
  if(state)state.textContent=text;
  // One glanceable word per card; the sentence above stays as the detail line.
  const allKeep=choices.every(x=>x==='keep'),allBlur=choices.every(x=>x==='blur');
  // Fail closed: anything not fully covered and not explicitly kept asks for review.
  const [decision,label]=unknown?['review','Needs review']:
   allKeep?['keep','Kept visible']:
   allBlur?(gaps?['review','Blurred — has gaps']:['blur','Blurred']):
   uncertain?['review','Needs review']:
   choices.some(x=>x)?['mixed','Mixed choices']:
   blurred===members.length?['blur','Blurred automatically']:['review','Needs review'];
  setDetLabel(i,card,decision,label);
  const blur=document.getElementById("bb"+i),keep=document.getElementById("kb"+i);
  // The button records an explicit choice, not the availability of mask geometry.
  // Output counts above and reviewOn() still exclude unsupported samples.
  if(blur)blur.setAttribute("aria-pressed",String(choices.every(x=>x==='blur')));
  if(keep)keep.setAttribute("aria-pressed",String(choices.every(x=>x==='keep')));
  if(card)card.classList.toggle("off",blurred===0&&!uncertain&&!unknown);
  return;
 }
 if(state)state.textContent=kept===0?"Will be blurred":blurred===0?"Will stay visible":
  `Mixed — ${blurred} will be blurred; ${kept} will stay visible`;
 const blur=document.getElementById("bb"+i),keep=document.getElementById("kb"+i);
 if(blur)blur.setAttribute("aria-pressed",String(kept===0));
 if(keep)keep.setAttribute("aria-pressed",String(blurred===0));
 if(card){card.classList.toggle("off",blurred===0);
  card.dataset.state=kept===0?'blur':blurred===0?'keep':'mixed';}
}
let DET_BATCH=0,DET_DIRTY=new Set();
function finishDetChoices(){
 if(!EDITS.busy)saveStatus(EDITS,PHPH==='paused'?'Unsaved edits — save before resuming.':'Unsaved edits — save to include them in the render.');
 DET_DIRTY.forEach(refreshDet);DET_DIRTY.clear();
 if(document.getElementById('beCv')){beFilter();beDraw();}
 refreshReviewFilters();
}
function applyDet(i,blur){
 if(!DET_BATCH)REVIEW_FILTER.held.add(i);  // single-card clicks only; bulk actions re-filter
 for(const m of (TRKMEM[i]||[i])){
  EN[m]=blur;EDITS.enabled[m]=blur;DET_DIRTY.add(ROWCARD[m]??m);
 }
 if(!DET_BATCH)finishDetChoices();
}
function applyDetBatch(ids,on){
 const targets=[...ids];DET_BATCH++;
 try{for(const i of targets)applyDet(i,on);}
 finally{if(!--DET_BATCH)finishDetChoices();}
}
function setAll(cat,on){
 applyDetBatch(REVIEW_META?.sections.filter(s=>!s.zone&&s.category===cat).flatMap(s=>s.ids)||[],on);
}
function setAllZd(on){applyDetBatch(REVIEW_META?.sections.filter(s=>s.zone).flatMap(s=>s.ids)||[],on);}

let selSet=new Set(),marqEl=null,menuEl=null,mStart=null;
function clearSel(){
 selSet.forEach(i=>{const t=document.getElementById("det"+i);
  if(t)t.classList.remove("selected");});
 selSet.clear();
 if(menuEl){menuEl.remove();menuEl=null;}
}
function initMarquee(){
 const wrap=document.getElementById('detwrap'),owner=REVIEW_SCHED;
 if(!wrap||!owner||wrap.dataset.mq)return;wrap.dataset.mq=1;
 owner.listen(wrap,'pointerdown',e=>{
  if(e.pointerType==='touch'||e.target.closest('button')||!owner.owns())return;
  owner.selectionCleanup?.();clearSel();owner.gesture=true;mStart=[e.pageX,e.pageY];
  // A bounded frozen set; scrolling during the gesture does not mount more.
  const targets=[...owner.bindings.values()].filter(b=>reviewSelectable(b.id)&&b.card.dataset.focusPin!=='1'&&
   b.card.getBoundingClientRect().bottom>0&&b.card.getBoundingClientRect().top<window.innerHeight);
  marqEl=document.createElement('div');marqEl.className='marq';document.body.appendChild(marqEl);
  const cleanup=()=>{
   document.removeEventListener('pointermove',move);document.removeEventListener('pointerup',up);
   document.removeEventListener('pointercancel',cancel);document.removeEventListener('keydown',key);
   if(marqEl){marqEl.remove();marqEl=null;}mStart=null;owner.gesture=false;owner.selectionCleanup=null;
   owner.schedule();
  };
  const move=ev=>{
   if(!owner.owns()||!mStart)return;
   const x1=Math.min(mStart[0],ev.pageX),y1=Math.min(mStart[1],ev.pageY),
    x2=Math.max(mStart[0],ev.pageX),y2=Math.max(mStart[1],ev.pageY);
   Object.assign(marqEl.style,{left:x1+'px',top:y1+'px',width:(x2-x1)+'px',height:(y2-y1)+'px'});
  };
  const up=ev=>{
   if(!owner.owns()||!marqEl){cleanup();return;}
   const r=marqEl.getBoundingClientRect();cleanup();
   if(r.width<8&&r.height<8)return;
   for(const b of targets){if(!owner.valid(b,false)||!reviewSelectable(b.id))continue;
    const t=b.card,rect=t.getBoundingClientRect();
    if(rect.width&&rect.height&&rect.left<r.right&&rect.right>r.left&&rect.top<r.bottom&&rect.bottom>r.top){selSet.add(b.id);t.classList.add('selected');}}
   if(selSet.size)showSelMenu(ev.pageX,ev.pageY);
  };
  const cancel=()=>cleanup(),key=ev=>{if(ev.key==='Escape')cleanup();};
  owner.selectionCleanup=cleanup;
  document.addEventListener('pointermove',move);document.addEventListener('pointerup',up);
  document.addEventListener('pointercancel',cancel);document.addEventListener('keydown',key);
  e.preventDefault();
 });
}
function showSelMenu(x,y){
 menuEl=document.createElement("div");menuEl.className="selmenu";
 menuEl.innerHTML=`<span>${selSet.size} selected</span>
  <button class="mkeep" onclick="bulkSet(false)">Keep visible</button>
  <button class="mblur" onclick="bulkSet(true)">Blur</button>`;
 Object.assign(menuEl.style,{left:x+"px",top:(y+10)+"px"});
 document.body.appendChild(menuEl);
}
function bulkSet(blur){const ids=[...selSet].filter(reviewSelectable);clearSel();applyDetBatch(ids,blur);}
document.addEventListener("pointerdown",e=>{
 if(menuEl&&!e.target.closest(".selmenu")
    &&!e.target.closest("#detwrap"))clearSel();});
// "?" help tips: keep the bubble fully on screen (a tip beside a phone's
// screen edge used to be cut off), and a tap on a "?" inside a checkbox
// label must open the tip, not tick the box
function qmPlace(q){
 const w=Math.min(250,window.innerWidth-24),r=q.getBoundingClientRect(),
       c=r.left+r.width/2;
 let dx=0;
 if(c-w/2<12)dx=12-(c-w/2);
 else if(c+w/2>window.innerWidth-12)dx=(window.innerWidth-12)-(c+w/2);
 q.style.setProperty("--qw",w+"px");q.style.setProperty("--qx",dx+"px");
 q.classList.toggle("below",r.top<260);}   // no room above: open downward
document.addEventListener("mouseover",e=>{
 const q=e.target.closest&&e.target.closest(".qm");if(q)qmPlace(q);});
document.addEventListener("click",e=>{
 const q=e.target.closest(".qm");
 document.querySelectorAll(".qm.open").forEach(x=>{if(x!==q)x.classList.remove("open");});
 if(q){e.preventDefault();qmPlace(q);q.classList.toggle("open");}});
document.addEventListener("keydown",e=>{
 if(e.key==="Escape"){REVIEW_SCHED?.selectionCleanup?.();clearSel();
  const lb=document.getElementById("lb");if(lb)lb.remove();}});

async function reviewPost(url,payload){
 const response=await fetch(url,{method:"POST",headers:{"Content-Type":"application/json"},
  ...(payload===undefined?{}:{body:JSON.stringify(payload)})});
 if(!response.ok){
  let body;try{body=await response.json();}catch(_){}
  const error=Error(body?.error||("Request failed (HTTP "+response.status+")"));
  error.status=response.status;error.code=body?.error;throw error;
 }
 let body;try{body=await response.json();}catch(_){throw Error("Invalid server response (HTTP "+response.status+")");}
 if(!body||body.error||body.ok!==true)throw Error(body?.error||"Invalid success acknowledgement");
 return body;
}
function acknowledgeMap(current,submitted){
 for(const [key,value] of Object.entries(submitted))
  if(sameEdit(current[key],value))delete current[key];
}
function acknowledgePolicyChoices(owner,submitted){
 if(!owner||REVIEW_SCHED!==owner)return [];
 const changed=new Set();
 for(const [key,value] of Object.entries(submitted)){
  const id=ROWCARD[key]??+key,card=owner.meta.byId.get(id),row=card?.policyRows?.get(+key);
  if(!row)continue;
  row.output_choice=value?'blur':'keep';
  row.policy_status=value?(row.policy_geometry_supported?'blur':'gap'):'keep';
  changed.add(id);
 }
 return [...changed];
}
function acknowledgeAdds(current,refs,submitted){
 for(let i=current.length-1;i>=0;i--){
  const index=refs.indexOf(current[i]);
  if(index>=0&&sameEdit(current[i],submitted[index]))current.splice(i,1);
 }
}
function reviewResolveActions(d){
 if(d!==EDITS)return;const el=document.getElementById('reviewResolveActions');if(!el)return;
 const b=d.editor,rows=[...new Set([...Object.keys(b.ov),...Object.keys(b.times),...Object.keys(b.quads)])];
 el.innerHTML='';
 if(d.submitted?.everUncertain){const button=document.createElement('button');button.textContent='Abandon unconfirmed save…';button.disabled=!!d.busy;button.onclick=reviewAbandon;el.appendChild(button);}
 if(!rows.length&&!b.adds.length)return;
 const select=document.createElement('select');select.id='reviewResolveSelection';select.disabled=!!d.busy||!!d.submitted;
 for(const key of rows){const option=document.createElement('option');option.value='row:'+key;option.textContent='Position/time row '+key;select.appendChild(option);}
 b.adds.forEach((a,i)=>{const option=document.createElement('option');option.value='add:'+a.manual_id;option.textContent='New box '+(i+1);select.appendChild(option)});
 el.appendChild(select);const button=document.createElement('button');button.textContent='Discard geometry and inspect';
 button.disabled=!!d.busy||!!d.submitted;button.onclick=()=>reviewDiscard(select.value);el.appendChild(button);
}
function reviewAbandon(){
 const d=EDITS,submitted=d?.submitted;if(!submitted?.everUncertain||d.busy)return;
 if(!confirm('Abandon this unconfirmed save retry? This does not undo changes that may already be saved. All current drafts and baselines will remain.'))return;
 if(EDITS!==d||d.busy||d.submitted!==submitted)return;
 d.submitted=null;saveStatus(d,'Unconfirmed retry abandoned. Inspect saved state; current drafts and baselines are retained.');
}
async function reviewDiscard(key){
 const d=EDITS;if(!d||d.busy||d.submitted)return;
 const b=d.editor,view=BE_VIEW,id=CUR,gen=VIEW_GEN;
 const row=key?.startsWith('row:')?key.slice(4):null;
 const addition=key?.startsWith('add:')?b.adds.find(a=>a.manual_id===key.slice(4)):null;
 if(row!==null&&!/^[0-9]+$/.test(row)||row===null&&!addition)return;
 const family=row!==null?b.geometry[row]:null,familySnapshot=family?copyEdit(family):null;
 const values=row!==null?copyEdit({ov:b.ov[row]??null,times:b.times[row]??null,quad:row in b.quads?{value:b.quads[row]}:null}):copyEdit(addition);
 if(row!==null&&values.ov===null&&values.times===null&&values.quad===null)return;
 if(!confirm('Discard only this pending geometry and inspect the saved frame? Other edits stay pending. This does not undo saved changes.'))return;
 if(EDITS!==d||d.editor!==b||!ownsView(id,gen)||BE_VIEW!==view||d.busy||d.submitted)return;
 if(row!==null){
  if(b.geometry[row]!==family||!sameEdit(b.geometry[row]||null,familySnapshot)||!sameEdit(values,{ov:b.ov[row]??null,times:b.times[row]??null,quad:row in b.quads?{value:b.quads[row]}:null}))return;
  delete b.ov[row];delete b.times[row];delete b.quads[row];delete b.geometry[row];
 }else{
  if(!b.adds.includes(addition)||!sameEdit(addition,values))return;
  b.adds.splice(b.adds.indexOf(addition),1);
 }
 if(view&&view.current()){beEndGesture(b,view.cv);beRequestSample(view,view.readySample?.sample.requested_s??b.t);}
 else await loadBoxEdit(!!document.getElementById('review'));
 saveStatus(d,'Selected geometry discarded. Inspect the exact frame, then deliberately edit again; missing rows are never remapped.');
}
function reviewSubmission(d,checkpoint=false){
 const b=d.editor;
 for(const a of [...d.manual,...b.adds])if(!Object.prototype.hasOwnProperty.call(a,'manual_id'))a.manual_id=manualId();
 const manualRefs=[...d.manual],addRefs=[...b.adds],manualSnapshot=copyEdit(d.manual),addSnapshot=copyEdit(b.adds);
 const payload=copyEdit({enabled:d.enabled,manual:[...manualSnapshot,...addSnapshot.map(a=>({
  manual_id:a.manual_id,t_start:a.t0,t_end:a.t1,t_ref:a.tref,screen_box:a.box,
  ...(a.sample_precondition?{sample_precondition:a.sample_precondition}:{})}))],box_overrides:b.ov,time_overrides:b.times});
 const geometryOwners={},geometrySnapshot={},quadBaselines={},quadStreams={};
 if(Object.keys(b.quads).length)payload.manual_plate_quads=copyEdit(b.quads);
 for(const key of new Set([...Object.keys(payload.box_overrides),...Object.keys(payload.time_overrides),...Object.keys(b.quads)])){
  if(!b.geometry[key]){if(key in b.quads)throw Error('Inspect the plate frame before saving corners.');continue;}
  geometryOwners[key]=b.geometry[key];geometrySnapshot[key]=copyEdit(b.geometry[key].precondition);
  quadBaselines[key]=copyEdit(b.geometry[key].quadBaseline??null);quadStreams[key]=b.geometry[key].quadStream;
 }
 if(Object.keys(geometrySnapshot).length)payload.geometry_preconditions=copyEdit(geometrySnapshot);
 if(b.audioLoaded&&!sameEdit(b.audio,b.audioSaved))payload.audio=copyEdit(b.audio);
 return {payload,manualRefs,addRefs,manualSnapshot,addSnapshot,geometryOwners,geometrySnapshot,quadBaselines,quadStreams,view:BE_VIEW,checkpoint,everUncertain:false};
}
function beQuadAck(record,requested,pc,stream){
 if(requested===null)return record===null;
 if(!requested||!beQuadRecord(record)||record.source.width!==pc.width||record.source.height!==pc.height||
  record.source.stream!==stream||record.frame.index!==pc.index||record.frame.policy!==pc.policy||record.frame.timeline_eq!==pc.timeline_eq)return false;
 return sameEdit(record.points,requested.points.map(p=>[p[0]/pc.width,p[1]/pc.height]));
}
function acknowledgeGeometry(editor,submission,result){
 const pcs=submission.geometrySnapshot,payload=submission.payload,validated={},quads=payload.manual_plate_quads||{};
 let needFresh=false;
 // Validate the whole strict acknowledgement before acknowledging any edit kind.
 for(const [key,pc] of Object.entries(pcs)){
  const hasBounds=Object.prototype.hasOwnProperty.call(pc,'scan_frame_bounds');
  if(submission.checkpoint&&!hasBounds)throw Error('Missing checkpoint row bounds; inspect again.');
  const row=result.geometry_rows?.[key],explicit=Object.prototype.hasOwnProperty.call(quads,key);
  const plate=beQuadHash(pc.quad_context_eq);
  const boxChanged=Object.prototype.hasOwnProperty.call(payload.box_overrides,key)&&!sameEdit(payload.box_overrides[key],pc.base.cbox);
  const retired=!explicit&&boxChanged&&beQuadRecord(submission.quadBaselines[key])&&row?.manual_plate_quad===null&&
   beQuadHash(pc.quad_context_eq)&&row?.quad_context_eq===pc.quad_context_eq;
  const timeChanged=Object.prototype.hasOwnProperty.call(payload.time_overrides,key)&&
   !sameEdit(payload.time_overrides[key],pc.base.span.slice(0,2));
  const released=hasBounds&&pc.scan_frame_bounds!==null&&timeChanged;
  const identityValid=beQuadHash(row?.row_context_eq)&&(released?row.scan_frame_bounds===null:
   (explicit||retired||row.row_context_eq===pc.row_context_eq)&&
   (!hasBounds||sameEdit(row.scan_frame_bounds,pc.scan_frame_bounds)));
  if(!row||!beBase(row.base)||!sameEdit(bePrecondition(row),bePrecondition(pc))||row.version!==1||
   !identityValid||
   !sameEdit(row.base.cbox,payload.box_overrides[key]||pc.base.cbox)||
   !sameEdit(row.base.span.slice(0,2),payload.time_overrides[key]||pc.base.span.slice(0,2))||
   (plate&&(!Object.prototype.hasOwnProperty.call(row,'manual_plate_quad')||
    !Object.prototype.hasOwnProperty.call(row,'quad_baseline')||!beQuadWitness(row.quad_baseline,row.manual_plate_quad)))||
   (explicit&&(!beQuadHash(pc.quad_context_eq)||row.quad_context_eq!==pc.quad_context_eq||
    !Object.prototype.hasOwnProperty.call(row,'manual_plate_quad')||!beQuadAck(row.manual_plate_quad,quads[key],pc,submission.quadStreams[key]))))
   throw Error('Missing or invalid geometry acknowledgement; retry the same save.');
  if(released)needFresh=true;
  validated[key]=copyEdit(row);
 }
 for(const [key,row] of Object.entries(validated)){
  const owner=editor.geometry[key];if(owner!==submission.geometryOwners[key])continue;
  if(sameEdit(editor.ov[key],payload.box_overrides[key]))delete editor.ov[key];
  if(sameEdit(editor.times[key],payload.time_overrides[key]))delete editor.times[key];
  if(Object.prototype.hasOwnProperty.call(quads,key)&&sameEdit(editor.quads[key],quads[key]))delete editor.quads[key];
  const {manual_plate_quad,quad_baseline,quad_context_eq,...precondition}=row;
  // The backend may report a quad-independent hash for any row. Only a
  // captured plate owner may carry it into the next geometry transaction.
  if(beQuadHash(pcs[key].quad_context_eq))precondition.quad_context_eq=quad_context_eq;
  if(Object.prototype.hasOwnProperty.call(row,'quad_baseline'))precondition.quad_baseline=quad_baseline;
  owner.precondition=copyEdit(precondition);
  if(Object.prototype.hasOwnProperty.call(row,'manual_plate_quad'))owner.quadBaseline=beQuadRecord(manual_plate_quad)?copyEdit(manual_plate_quad):null;
  if(!(key in editor.ov)&&!(key in editor.times)&&!(key in editor.quads))delete editor.geometry[key];
 }
 // Legacy compatibility is intentionally separate from strict ownership.
 for(const [key,value] of Object.entries(payload.box_overrides))if(!(key in pcs)&&sameEdit(editor.ov[key],value))delete editor.ov[key];
 for(const [key,value] of Object.entries(payload.time_overrides))if(!(key in pcs)&&sameEdit(editor.times[key],value))delete editor.times[key];
 const view=BE_VIEW;
 if(!Object.keys(validated).length||!view||view.editor!==editor||!view.current())return;
 let refresh=needFresh||view!==submission.view||!beReady(view);
 if(!refresh)for(const [key,ack] of Object.entries(validated)){
  const pc=pcs[key],ready=view.readySample,old=ready.rows.find(r=>String(r.i)===key);
  if(!old||ready.sample.source_ref!==pc.source_ref||ready.sample.timeline_eq!==pc.timeline_eq||
   old.row_context_eq!==pc.row_context_eq||(!sameEdit(old.base,pc.base)&&!sameEdit(old.base,ack.base))){refresh=true;break;}
 }
 if(refresh){beRequestSample(view,view.readySample?.sample.requested_s??editor.t);return;}
 for(const [key,ack] of Object.entries(validated)){
  const row=view.readySample.rows.find(r=>String(r.i)===key);row.base=copyEdit(ack.base);row.row_context_eq=ack.row_context_eq;
  if(row.category==='plate'&&Object.prototype.hasOwnProperty.call(ack,'manual_plate_quad')){
   row.quad_context_eq=ack.quad_context_eq;row.quad_baseline=ack.quad_baseline;
   if(ack.manual_plate_quad===null){delete row.manual_plate_quad;row.quad_eligibility='none';}
   else{row.manual_plate_quad=copyEdit(ack.manual_plate_quad);
    if(key in quads)row.quad_eligibility=beQuadForSample(ack.manual_plate_quad,view.readySample.sample)?'eligible_sdr_frame':'other_frame';}
   if(key in quads)row.quad_edit_eligibility='ready';
  }
  row.t_start=ack.base.span[0];row.t_end=ack.base.span[1];
  row.box=ack.base.cbox.map((v,i)=>v+view.readySample.sample.offset[i%2]);
 }
 beFilter();beQuadControls(view);beDraw();
}

async function saveAndResume(){return saveAndRender(true);}
async function saveAndRender(resume=false){
 const id=CUR,gen=VIEW_GEN,d=EDITS,reviewOwner=REVIEW_SCHED,editorIntent=BE_OPEN_INTENT;
 if(!id||!d||d.busy)return false;
 if(resume?(PHPH!=='paused'||!REVIEW_META?.checkpoint||REVIEW_META.jobId!==id||REVIEW_META.viewGen!==gen):PHPH==='paused')return false;
 // Assisted plate letters: save first, then remind with the fresh gap count.
 const assistedJob=!resume&&assistedLetterJob(id);
 const b=d.editor;
 if(resume&&reviewGesturePending(b)){saveStatus(d,'Finish or cancel the current edit before resuming.');return false;}
 let submission;
 try{
  if(d.submitted&&!!d.submitted.checkpoint!==resume)throw Error('Resolve the previous unconfirmed save before continuing.');
  submission=d.submitted||(d.submitted=reviewSubmission(d,resume));
 }
 catch(e){saveStatus(d,"Could not save edits: "+e.message);return false;}
 const payload=submission.payload;
 d.audioInFlight=payload.audio!==undefined;
 d.busy=true;saveStatus(d,"Saving edits… You can keep editing; newer edits stay pending.");
 let saved=false;
 try{
  const result=await reviewPost(`api/jobs/${id}/detections`,payload);
  if(resume&&(typeof result.resume_token!=='string'||!result.resume_token||result.resume_token.length>1024))
   throw Error('Missing or invalid resume token.');
  acknowledgeGeometry(b,submission,result);
  saved=true;d.submitted=null;d.audioInFlight=false;
  const policyCards=ownsView(id,gen)?acknowledgePolicyChoices(reviewOwner,payload.enabled):[];
  acknowledgeMap(d.enabled,payload.enabled);
  if(policyCards.length){policyCards.forEach(refreshDet);refreshReviewFilters();}
  acknowledgeAdds(d.manual,submission.manualRefs,submission.manualSnapshot);acknowledgeAdds(b.adds,submission.addRefs,submission.addSnapshot);
  if(payload.audio!==undefined)b.audioSaved=copyEdit(payload.audio);
  // A switched-away view never opens a confirmation or changes current UI.
  if(!ownsView(id,gen)){
   saveStatus(d,resume?"Edits saved. Reopen review before resuming.":"Edits saved. Review pending edits, then save to render this job.");return false;
  }
  if(resume){
   if(PHPH!=='paused'||REVIEW_SCHED!==reviewOwner||BE_OPEN_INTENT!==editorIntent){
    saveStatus(d,'Edits saved. Reopen review before resuming.');return false;
   }
   if(hasReviewEdits(d)||reviewGesturePending(b)){
    saveStatus(d,'Submitted edits saved. Newer or unfinished edits are still pending — finish and save again before resuming.');return false;
   }
   saveStatus(d,'Edits saved; requesting resume…');
   await reviewPost(`api/jobs/${id}/resume`,{resume_token:result.resume_token});
   if(hasReviewEdits(d)){
    saveStatus(d,'Scan resuming. Newer edits remain pending and were not included.');return true;
   }
   saveStatus(d,'Scan resuming with saved edits…');return true;
  }
  let allowError="";
  if(result.suggest_allowlist&&result.suggest_allowlist.length&&
     confirm("You disabled every instance of: "+result.suggest_allowlist.join(", ")+". Add these to the permanent allow-list so future scans skip them?")){
   try{await reviewPost("api/allowlist",{words:result.suggest_allowlist});loadPersist();}
   catch(e){allowError=" Allow-list update failed: "+e.message;}
  }
  if(!ownsView(id,gen)){
   saveStatus(d,"Edits saved. Review pending edits, then save to render this job."+allowError);return false;
  }
  if(hasReviewEdits(d)){
   saveStatus(d,"Submitted edits saved. Newer edits are still pending — save again to include them before rendering."+allowError);return false;
  }
  if(assistedJob){
   saveStatus(d,"Edits saved; checking plate letter gaps…"+allowError);
   const go=await assistedRenderConfirm(id,gen);
   if(!ownsView(id,gen)){
    saveStatus(d,"Edits saved. Review pending edits, then save to render this job."+allowError);return false;
   }
   if(!go){saveStatus(d,"Edits saved. Render cancelled — save again to render."+allowError);return false;}
   if(hasReviewEdits(d)){
    saveStatus(d,"Submitted edits saved. Newer edits are still pending — save again to include them before rendering."+allowError);return false;
   }
  }
  saveStatus(d,"Edits saved; requesting render…");
  await reviewPost(`api/jobs/${id}/render`);
  // Edits can also arrive while the render request is pending.
  if(hasReviewEdits(d)){
   saveStatus(d,"Render started with submitted edits. Newer edits are pending — save again to render them."+allowError);return true;
  }
  saveStatus(d,"Rendering with saved edits…"+allowError);
  if(ownsView(id,gen)&&REVIEW_SCHED===reviewOwner&&BE_OPEN_INTENT===editorIntent){
   disposeReview();const rv=document.getElementById("review");if(rv){beUnmountIn(rv);rv.remove();}
   const c=document.getElementById("beslot_done");if(c){beUnmountIn(c);c.innerHTML="rendering with your edits…";}
  }
  return true;
 }catch(e){
  // A failed response leaves the audio baseline uncertain. Retain even a
  // newer toggle-back to the old baseline and deliberately send it on retry.
  let rejected=false;
  if(!saved){
   if(!submission.everUncertain&&(e.status===409&&e.code==="geometry_conflict"||resume&&e.status>=400&&e.status<500)){
    d.submitted=null;rejected=resume;
   }
   else {submission.everUncertain=true;if(payload.audio!==undefined)b.audioSaved=null;}
  }
  saveStatus(d,(rejected?"Save rejected; your drafts remain editable. ":saved?(resume?"Edits saved; resume was not confirmed. Check the job before retrying. ":"Edits saved; render was not confirmed. Retry with Save to render. "):
   "Save was not confirmed; drafts retained. Retry with Save. ")+e.message);
  return false;
 }finally{d.audioInFlight=false;d.busy=false;saveStatus(d,d.status);if(d!==EDITS)trimReviewDraft(d);}
}
function persistFailure(error){
 const nt=document.getElementById("persistnote"),message=String(error.message||error);
 nt.style.display="block";nt.style.color="#f87171";
 nt.textContent=message.includes("HTTP 423")?
  "Allow-list unavailable: the vault is locked or needs recovery. Unlock and retry.":
  "Allow-list request failed: "+message;
}
async function loadPersist(){
 try{
  const response=await fetch("api/allowlist");
  if(!response.ok)throw Error("Request failed (HTTP "+response.status+")");
  const a=await response.json();
  if(!a||!Array.isArray(a.words))throw Error("Invalid allow-list response");
  const el=document.getElementById("persistlist"),
        nt=document.getElementById("persistnote");
  const html=a.words.map(x=>
   `<div class="pw">${x}<span title="remove from allow-list"
     onclick="rmPersist('${x.replace(/'/g,"")}')">✕</span></div>`).join("");
  el.innerHTML=html;nt.style.color="";
  if(a.words.length){
   nt.style.display="block";
   nt.textContent="Green words load automatically from "+a.path+
    " — marked safe during previous reviews. They are always applied in "+
    "addition to anything typed above. Click ✕ to remove one.";
  }else nt.style.display="none";
  document.getElementById("clearpersist").style.display=
   a.words.length?"inline-block":"none";
  return true;
 }catch(error){persistFailure(error);return false;}
}
async function clearPersist(){
 if(!confirm("Remove ALL learned safe words? Future scans will flag them again until re-reviewed."))return;
 try{
  await reviewPost("api/allowlist",{clear:true});
  return await loadPersist();
 }catch(error){persistFailure(error);return false;}
}
async function rmPersist(word){
 try{
  await reviewPost("api/allowlist",{remove:[word]});
  return await loadPersist();
 }catch(error){persistFailure(error);return false;}
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
  else if(d.locked){st.textContent="LOCKED — "+d.encrypted_files+" file(s) encrypted on disk. Unlock to work with jobs.";st.style.color="#f87171";}
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
 vaultStatus();loadJobs();
}
async function vaultAutolockSave(){
 const on=document.getElementById("valk").checked;
 const m=on?parseInt(document.getElementById("valkmin").value||"30",10):0;
 await fetch("/api/vault/autolock",{method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify({minutes:m})});
 vaultStatus();
}
async function vaultDoLock(){
 if(!confirm("Encrypt all job files now?\\n\\nYou will need the password to access them again."))return;
 const r=await fetch("/api/vault/lock",{method:"POST"});
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
loadPersist();loadCertInfo();loadJobs();setInterval(loadJobs,5000);
function showView(){
 const s=location.hash==="#settings";
 document.getElementById("mainview").style.display=s?"none":"block";
 document.getElementById("settingsview").style.display=s?"block":"none";
 if(s)window.scrollTo(0,0);
}
window.addEventListener("hashchange",showView);
updCheck();vaultStatus();extrasStatus();showView();
"""

PAGE = (zones_ui.ZONES_PAGE
        .replace("%%FAVICON%%", FAVICON_URI)
        .replace("%%LOGO%%", LOGO_URI)
        .replace("%%WORDMARK%%", WORDMARK_URI)
        .replace("%%APP_CSS%%", APP_CSS)
        .replace("%%JOBS_HTML%%", JOBS_HTML)
        .replace("%%SETTINGS_HTML%%", SETTINGS_HTML)
        .replace("%%FOOT_HTML%%", FOOT_HTML)
        .replace("%%APP_JS%%", APP_JS))


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
                                      "queued_render")
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
FILES = FileOwners(VAULT_LOCK)
WEB_SETTINGS_PATH = os.path.join(_data_root(), "web_settings.json")
LAST_ACTIVITY = {"t": time.time()}


def _web_settings():
    try:
        with open(WEB_SETTINGS_PATH, encoding="utf-8") as f:
            return json.load(f)
    except Exception:
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
            n = _vault_lock_now()
            print("vault: auto-locked after %d idle minute(s) — "
                  "%d file(s) encrypted" % (mins, n))
        except Exception:
            pass


def vault_enabled():
    return vault.keystore_exists(_data_root())


def vault_locked():
    return VAULT.get("closed", False) or (vault_enabled() and VAULT["key"] is None)


def _vault_entry(path):
    # Resolve the parent, but never follow the leaf being witnessed.
    return os.path.join(os.path.realpath(os.path.dirname(path)), os.path.basename(path))


def _vault_video_snapshot(job, path):
    video = job.get('video') or ''
    return video, (os.path.realpath(video) == path or _vault_entry(video) == path)


def _vault_live_owners():
    """Side-effect-free discovery while VAULT_LOCK prevents new admission."""
    with JOBS_LOCK:
        jobs = list(JOBS.values())
    root = os.path.realpath(JOBS_DIR)
    owners, discarded, sealed = [], [], []
    for job in jobs:
        files = job.get('_files')
        if files is None:
            continue
        selected = files.current_source
        path = selected['path'] if selected is not None else ''
        video = _vault_video_snapshot(job, path)
        try:
            managed = bool(path) and os.path.commonpath((root, path)) == root
        except ValueError:
            managed = False
        with files.report_lock:
            if (managed and selected is not None
                    and _vault_same_owner(job, files, selected, path, video)):
                owners.append((job, files, selected, path))
                marker = files.vault_transition
                if marker is not None and marker['selected'] is selected:
                    sealed.append((job, files, selected, path, marker))
            elif files.vault_transition is not None:
                marker = files.vault_transition
                discarded.append((job, files, marker['selected'], path, marker))
    return owners, discarded, sealed


def _vault_same_owner(job, files, selected, path, video):
    return (not files.closed and not files.source_retired
            and files.source_status == 'coherent' and files.active is None
            and files.current_source is selected and selected['path'] == path
            and (job.get('video') or '') == video[0] and video[1])


def _vault_discard_markers(discarded, affected):
    for item in discarded:
        job, files, selected, path, marker = item
        with files.report_lock:
            if files.vault_transition is marker:
                affected.append(item)
                files.vault_transition = None


def _vault_retire(files, selected):
    if files.current_source is selected:
        files.source_retired = True
        files.current_source = None
        files.source_status, files.source_reason = 'unavailable', 'observed source changed; rescan required'
    files.vault_transition = None


def _vault_observer(owners, direction, affected):
    by_path = {}
    for owner in owners:
        by_path.setdefault(owner[3], []).append(owner)

    def observe(actual_direction, path):
        matches = by_path.get(_vault_entry(path), ())
        started = []
        for job, files, selected, canonical in matches:
            video = _vault_video_snapshot(job, canonical)
            with files.report_lock:
                if not _vault_same_owner(job, files, selected, canonical, video):
                    continue
                marker = files.vault_transition
                if direction == 'encrypt':
                    marker = dict(selected=selected, old_stamp=selected['stamp'], phase='started')
                    files.vault_transition = marker
                elif marker is None or marker['selected'] is not selected or marker['phase'] != 'sealed':
                    continue
                started.append((job, files, selected, canonical, marker))
                affected.append((job, files, selected, canonical, marker))
        if not started:
            return None

        def finish(receipt):
            for job, files, selected, canonical, marker in started:
                video = _vault_video_snapshot(job, canonical)
                with files.report_lock:
                    if (files.vault_transition is not marker
                            or not _vault_same_owner(job, files, selected, canonical, video)
                            or selected['stamp'] != marker['old_stamp']):
                        continue
                    if direction == 'encrypt':
                        valid = (receipt.input_stamp == marker['old_stamp']
                                 and receipt.plaintext_bytes == marker['old_stamp'][2])
                        if valid:
                            marker.update(phase='sealed', cipher=receipt.output_stamp, nonce=receipt.nonce)
                    else:
                        valid = (receipt.input_stamp == marker['cipher']
                                 and receipt.nonce == marker['nonce']
                                 and receipt.plaintext_bytes == marker['old_stamp'][2])
                        if valid:
                            marker.update(phase='restored', restored=receipt.output_stamp)
                    if not valid:
                        _vault_retire(files, selected)
        if direction == 'decrypt':
            expected = {marker['old_stamp'][2] for _, _, _, _, marker in started}
            if len(expected) != 1:
                raise OSError("vault plaintext sizes disagree")
            finish.expected_plaintext_size = expected.pop()
        return finish
    return observe


def _vault_invalidate(affected):
    for job, files, selected, path, marker in affected:
        with files.report_lock:
            if files.vault_transition is marker or files.current_source is selected:
                _vault_retire(files, selected)


def _vault_finalize(owners, affected):
    # Prepare all outcomes before installing any stamp. Filesystem checks do
    # not hold a report lock; admission remains closed throughout this pass.
    with JOBS_LOCK:
        registered = {id(job) for job in JOBS.values()}
    outcomes = []
    for job, files, selected, path in owners:
        video = _vault_video_snapshot(job, path)
        with files.report_lock:
            marker = files.vault_transition
            if marker is None or marker['selected'] is not selected:
                continue
            affected.append((job, files, selected, path, marker))
            valid = (id(job) in registered and _vault_same_owner(job, files, selected, path, video)
                     and selected['stamp'] == marker['old_stamp'] and marker['phase'] == 'restored')
        if valid:
            try:
                valid = vault._entry_stamp(path) == marker['restored']
            except OSError:
                valid = False
        outcomes.append((job, files, selected, path, marker, valid))
    for job, files, selected, path, marker, valid in outcomes:
        if valid:
            try:
                valid = vault._entry_stamp(path) == marker['restored']
            except OSError:
                valid = False
        video = _vault_video_snapshot(job, path)
        with files.report_lock:
            if files.vault_transition is not marker:
                continue
            valid = (valid and _vault_same_owner(job, files, selected, path, video)
                     and selected['stamp'] == marker['old_stamp'])
            if valid:
                selected['stamp'] = marker['restored']
                files.vault_transition = None
            else:
                _vault_retire(files, selected)


def _evict_thumbnails_for_store_transition(blocking=True):
    """Invalidate after admission closes and all job lifetimes have drained."""
    _forget_report_parses()
    if not JOBS_LOCK.acquire(blocking=blocking):
        raise FilesBusy('job registry is in use')
    try:
        jobs = list(JOBS.values())
    finally:
        JOBS_LOCK.release()
    for job in jobs:
        files = FILES.initialize(job)
        if blocking:
            with files.report_lock:
                thumbs.invalidate_locked(files.thumbnail, 'store transition')
        else:
            acquire = getattr(files.report_lock, 'acquire', None)
            if acquire is None or not acquire(blocking=False):
                raise FilesBusy('job report is in use')
            try:
                thumbs.invalidate_locked(files.thumbnail, 'store transition')
            finally:
                files.report_lock.release()


def _vault_lock_locked(blocking_jobs=True):
    if _files_busy_locked(blocking=blocking_jobs):
        raise FilesBusy("job files are still in use")
    key = VAULT["key"]
    if key is None:
        return 0
    owners, discarded, _ = _vault_live_owners() if blocking_jobs else ([], [], [])
    _evict_thumbnails_for_store_transition(blocking=blocking_jobs)
    FILES.thumbnail_authority = object()
    VAULT["closed"] = True
    affected = []
    try:
        _vault_discard_markers(discarded, affected)
        if owners:
            n = vault.encrypt_tree(key, JOBS_DIR, _vault_observer(owners, 'encrypt', affected))
        else:
            n = vault.encrypt_tree(key, JOBS_DIR)
    except BaseException:
        _vault_invalidate(affected)
        VAULT["error"] = "Encryption failed; unlock to recover before accessing jobs."
        raise
    VAULT["key"] = None
    VAULT["error"] = None
    return n


def _vault_lock_now(blocking=True):
    """One guarded busy/admission decision, also used by auto-lock/shutdown."""
    if blocking:
        with JOBS_LOCK:
            jobs = list(JOBS.values())
        for job in jobs:
            _thumbnail_lifecycle_cleanup(job)
    if not VAULT_LOCK.acquire(blocking=blocking):
        raise FilesBusy("a lifecycle transition is in progress")
    try:
        return _vault_lock_locked(blocking_jobs=blocking)
    finally:
        VAULT_LOCK.release()


def _vault_lock_atexit():
    try:
        if vault_enabled() and VAULT["key"] is not None:
            # A Python signal can run while this very thread owns VAULT_LOCK.
            # Never join or wait for it; timeout is not permission to encrypt.
            # If the signal interrupted JOBS_LOCK itself, do not even
            # attempt VAULT_LOCK in the inverse order. Release this probe
            # before taking the normal VAULT_LOCK -> JOBS_LOCK path.
            if not JOBS_LOCK.acquire(blocking=False):
                raise FilesBusy("job registry is in use")
            JOBS_LOCK.release()
            n = _vault_lock_now(blocking=False)
            print("vault: locked on shutdown (%d file(s) encrypted)" % n)
            return "locked"
        return "already_locked" if vault_enabled() else "not_enabled"
    except FilesBusy:
        print("vault: NOT locking on exit — job files or a lifecycle transition "
              "are still active; files may remain in plaintext. Restart and lock.")
        return "busy"
    except Exception:
        print("vault: LOCK ON SHUTDOWN FAILED — job files may remain in plaintext. "
              "Restart the server and use the Lock button.")
        return "failed"


@app.route("/api/vault")
def vault_status():
    enc, plain = (0, 0)
    if vault_enabled():
        enc, plain = vault.tree_locked_state(JOBS_DIR)
    return jsonify({"enabled": vault_enabled(), "locked": vault_locked(),
                    "encrypted_files": enc, "plaintext_files": plain,
                    "error": VAULT.get("error"),
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
        if vault_enabled():
            abort(409, "vault already set up")
        if _files_busy_locked():
            abort(409, "job files are still in use")
        VAULT["closed"] = True
        try:
            key = vault.create_keystore(_data_root(), pw)
        except BaseException:
            VAULT["error"] = "Vault setup failed; retry setup or unlock to recover."
            raise
        VAULT["key"] = key
        VAULT["closed"] = False
        VAULT["error"] = None
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
        if _files_busy_locked():
            abort(409, "job files are still in use")
        owners, discarded, sealed = _vault_live_owners()
        VAULT["closed"] = True
        FILES.thumbnail_authority = object()
        affected = sealed + discarded
        try:
            _vault_discard_markers(discarded, affected)
            if owners:
                n = vault.decrypt_tree(key, JOBS_DIR, _vault_observer(owners, 'decrypt', affected))
            else:
                n = vault.decrypt_tree(key, JOBS_DIR)
            _evict_thumbnails_for_store_transition()
            _rehydrate_jobs()  # registration is part of the closed transition
            _vault_finalize(owners, affected)
        except BaseException:
            _vault_invalidate(affected)
            VAULT["error"] = "Decryption or recovery failed; unlock again to recover."
            raise
        VAULT["key"] = key
        VAULT["closed"] = False
        VAULT["error"] = None
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
                "passport", "phrase"}


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


def _regex_min_width(pattern):
    """Shortest text a regex can match, from its parse tree (0 = it can
    match empty text). Pure analysis — the pattern is never executed."""
    try:
        from re import _parser as sre      # Python 3.11+
    except ImportError:                      # pragma: no cover — 3.10
        import sre_parse as sre
    try:
        return sre.parse(pattern).getwidth()[0]
    except Exception:
        return 0                             # unparseable: treat as unsafe


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
        _re.compile(pattern)          # syntax check only — never executed
    except Exception as e:
        abort(400, "invalid regex: %s" % e)
    if not pattern:
        abort(400, "a regex pattern is required")
    # a pattern that can match EMPTY text "matches" every OCR word (e.g.
    # `\d*`, `x|`, `\b`) — the category would blur the whole screen.
    # Decided STATICALLY from the parsed pattern's minimum match width,
    # never by running the user's regex here: executing request-supplied
    # patterns on the server is a ReDoS risk (code-scanning #22,
    # py/regex-injection — the v1.0.91 version test-ran it on samples).
    if _regex_min_width(pattern) == 0:
        abort(400, "this pattern can match empty text, so it would blur "
                   "every word — make it require at least one character "
                   "(for example use + instead of *)")
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
    try:
        n = _vault_lock_now()
    except FilesBusy:
        abort(409, "job files are still in use — lock after cleanup finishes")
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
    p = _request_source_path(request.args.get("path", ""))
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
    lease = g.get("file_owner")
    if lease is not None and lease.source_job is not None:
        owner = lease.source_job
        with lease.source_state.report_lock:
            _report_current(owner)
            _recovery_gate(owner)
            return _send_open_file(p, conditional=True)
    return _send_open_file(p, conditional=True)


@app.route("/api/waveform")
def waveform():
    """Audio peak envelope for a server-side video's track — powers the
    editor's waveform lanes. Same confinement as every server-path route:
    server_path_error runs first, and the containment guard is repeated
    inline in the CodeQL-recognized shape before any use."""
    p = _request_source_path(request.args.get("path", ""))
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
    if vault_locked():
        return
    with _own_files():
        return _rehydrate_jobs()


def _register_stopped_job(jid, jdir, progress_file):
    saved = _saved_progress(progress_file)
    opts = {}
    try:
        with open(os.path.join(jdir, OPTIONS_FILE), encoding="utf-8") as f:
            opts = json.load(f)
        if not isinstance(opts, dict):
            opts = {}
    except (OSError, ValueError):
        opts = {}
    up = next((os.path.join(jdir, "input" + e) for e in sorted(MEDIA_EXTS)
               if os.path.exists(os.path.join(jdir, "input" + e))), None)
    frame, total, meta = saved if saved is not None else (None, None, {})
    video = meta.get("video") if isinstance(meta.get("video"), str) else up
    name = meta.get("name") if isinstance(meta.get("name"), str) else (
        os.path.basename(video) if video else jid)
    if saved is None:
        error = ("the saved scan progress is unreadable — Cancel the scan and "
                 "start it again")
    elif not video or not os.path.exists(video):
        error = ("source video not found at %s — Continue scan works again once "
                 "the video is available at that path" % (video or "(unknown)"))
    else:
        error = None
    try:
        size = os.path.getsize(video) if video else 0
    except OSError:
        size = 0
    job = {
        "id": jid, "dir": jdir, "video": video, "name": name, "options": opts,
        "phase": "stopped", "stopped_frame": frame, "stopped_total": total,
        "progress": _stopped_progress(frame or 0, total or 1), "size": size,
        "log": JobLog(["(recovered after server restart — the scan was stopped "
                       "with its progress saved)"]),
        "error": error, "output": None, "created": os.path.getmtime(jdir),
        "cancel": threading.Event(), "stats": {},
    }
    FILES.initialize(job)
    with JOBS_LOCK:
        JOBS[jid] = job


def _rehydrate_jobs():
    """Re-register jobs found on disk after a restart. A job with a report
    is a reviewable job; one with an output file is a finished one — either
    way the person's work survives the server going down."""
    n = 0
    for jid in sorted(os.listdir(JOBS_DIR)):
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
        checkpoint_recovery = os.path.lexists(os.path.join(jdir, _CHECKPOINT_RECOVERY_NAME))
        render_recovery = _has_render_recovery(jdir)
        if checkpoint_recovery and not render_recovery:
            checkpoint_recovery = not _recover_checkpoint_publication(jdir)
        if render_recovery or checkpoint_recovery:
            # Do not follow descriptor paths or infer validity from final names.
            up = next((os.path.join(jdir, "input" + e) for e in sorted(MEDIA_EXTS)
                       if os.path.isfile(os.path.join(jdir, "input" + e))), None)
            opts = {}
            try:
                with open(os.path.join(jdir, OPTIONS_FILE), encoding="utf-8") as f:
                    opts = json.load(f)
                if not isinstance(opts, dict):
                    opts = {}
            except (OSError, ValueError):
                pass
            reason = ('checkpoint publication requires recovery' if checkpoint_recovery
                      else 'render delivery requires recovery')
            job = dict(id=jid, dir=jdir, video=up, name=os.path.basename(up) if up else jid,
                       options=opts, phase="error", progress=0.0, size=0,
                       log=JobLog([reason]), error=reason, output=None,
                       created=os.path.getmtime(jdir), cancel=threading.Event(), stats={},
                       _checkpoint_unfinished=checkpoint_recovery)
            FILES.initialize(job).recovery_required = True
            with JOBS_LOCK:
                JOBS[jid] = job
            n += 1
            continue
        progress_file = os.path.join(jdir, scan_progress.PROGRESS_NAME)
        scan_progress.discard_stage(progress_file)
        stopped_rescan = False
        if os.path.exists(rep) and os.path.exists(progress_file):
            saved = _saved_progress(progress_file)
            before = saved[2].get("report_before") if saved is not None else None
            if before is not None and before == _report_digest(jdir):
                stopped_rescan = True       # the report is the OLD one it replaces
            else:
                # published, but the server stopped before the progress file
                # was removed
                scan_progress.remove(progress_file)
        if (stopped_rescan or not os.path.exists(rep)) and os.path.exists(progress_file):
            # A stopped (or crashed, autosaved) scan: list it as stopped even
            # when its source video is not mounted right now.
            _register_stopped_job(jid, jdir, progress_file)
            n += 1
            continue
        if not os.path.exists(rep):
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
            opts = {}
            try:
                with open(os.path.join(jdir, OPTIONS_FILE),
                          encoding="utf-8") as f:
                    opts = json.load(f)
                if not isinstance(opts, dict):
                    opts = {}
            except (OSError, ValueError):
                opts = {}
            job = {
                "id": jid, "dir": jdir, "video": up,
                "name": os.path.basename(up), "options": opts,
                "phase": "error", "progress": 0.0, "size": size,
                "log": JobLog(["(recovered after server restart — the scan had "
                               "not completed)"]),
                "error": "recovered after a server restart before the "
                         "scan finished — Retry re-runs it with "
                         + ("its original settings" if opts else
                            "default settings")
                         + " (the uploaded file was kept), or "
                         "Delete frees its disk space",
                "output": None, "created": os.path.getmtime(jdir),
                "cancel": threading.Event(), "stats": {},
            }
            files = FILES.initialize(job)
            with JOBS_LOCK:
                JOBS[jid] = job
            n += 1
            continue
        try:
            with open(rep, encoding="utf-8") as f:
                doc = json.load(f)
            if not isinstance(doc, dict):
                continue
            checkpoint = 'stop_review' in doc
            prov = doc.get("provenance", {})
            if not isinstance(prov, dict):
                if not checkpoint:
                    continue
                prov = {}
            video = prov.get("input")
            if not isinstance(video, str):
                video = None
            source_available = isinstance(video, str) and bool(video) and os.path.exists(video)
            if not source_available and not checkpoint:
                continue
            out = os.path.join(jdir, "output.mp4")
            has_out = os.path.exists(out)
            # Completion invalidates the previous render's provenance. A
            # leftover file beside the report is not the completed output.
            if 'checkpoint_identity' in prov:
                recorded_output = prov.get('output')
                has_out = (has_out and isinstance(recorded_output, str) and
                           os.path.realpath(recorded_output) == os.path.realpath(out))
            checkpoint_error = None if source_available else "checkpoint source is unavailable"
            opts = prov.get("settings", {}) or {}
            if checkpoint:
                try:
                    with open(os.path.join(jdir, OPTIONS_FILE), encoding="utf-8") as f:
                        saved_opts = json.load(f)
                    if not isinstance(saved_opts, dict):
                        raise ValueError('original job options are invalid')
                    opts = saved_opts
                    checkpoints.validate_resume(doc)
                except (OSError, ValueError, TypeError):
                    checkpoint_error = "unfinished checkpoint or its original job options are invalid"
            original = prov.get("original_input")
            display_source = (original if isinstance(original, str) and original else
                              video if isinstance(video, str) and video else jid)
            job = {
                "id": jid, "dir": jdir, "video": video,
                "name": os.path.basename(display_source),
                "options": opts,
                "phase": ("error" if checkpoint_error else "paused") if checkpoint else ("done" if has_out else "review"),
                "progress": 0.5 if checkpoint else (1.0 if has_out else 0.5),
                "log": JobLog(["(recovered after server restart)"]),
                "error": checkpoint_error, "output": out if has_out and not checkpoint else None,
                "created": os.path.getmtime(jdir),
                "cancel": threading.Event(), "stats": {},
                "_checkpoint_unfinished": checkpoint,
            }
            try:
                # original upload size, for the editor's duplicate-upload
                # warning (prov input may be the normalized scan copy)
                orig = next((os.path.join(jdir, "input" + e)
                             for e in sorted(MEDIA_EXTS)
                             if os.path.exists(
                                 os.path.join(jdir, "input" + e))), video)
                job["size"] = os.path.getsize(orig)
            except (OSError, TypeError):
                pass
            files = FILES.initialize(job)
            with JOBS_LOCK:
                JOBS[jid] = job
            n += 1
        except Exception:
            continue
    if n:
        print(f"  recovered {n} job(s) from {JOBS_DIR}")


def retention_sweep(days):
    try:
        lease = _own_files()
    except Exception:  # locked/failed transition: defer until access is ready
        return
    with lease:
        cutoff = time.time() - days * 86400
        for jid in os.listdir(JOBS_DIR):
            p = os.path.join(JOBS_DIR, jid)
            if not os.path.isdir(p):
                continue
            if os.path.exists(os.path.join(p, DELETE_MARKER)):
                _reap_job_dir(p, jid, retries=1)
                continue
            if os.path.getmtime(p) < cutoff:
                job = JOBS.get(jid)
                if job is not None:
                    try:
                        _delete_job(job)
                    except Exception:  # owned jobs stay registered for next sweep
                        continue
                else:
                    _reap_job_dir(p, jid, retries=1)


def stop_scan_for_shutdown(timeout=20.0, poll=0.2):
    """docker stop: ask a running stoppable scan to save its progress first.

    Waits at most `timeout` seconds; a save that does not finish in time
    leaves the last autosave. Returns True when the scan stopped."""
    jid = WORKER.get("current")
    job = JOBS.get(jid) if jid else None
    if job is None or job.get("phase") != "scanning":
        return False
    stop = getattr(FILES.initialize(job).active, 'progress_stop', None)
    if stop is None:
        return False
    stop.set()
    print("stopping the running scan to save its progress…", flush=True)
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if job.get("phase") != "scanning":
            return job.get("phase") == "stopped"
        time.sleep(poll)
    return False


def retention_loop(days):
    while True:
        retention_sweep(days)
        time.sleep(6 * 3600)


def main():
    global TOKEN, DIAGNOSTICS
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
    ap.add_argument("--preview-decode-threads", type=int, choices=(0, 1, 2, 4),
                    default=0, help="preview decoder threads (default 0: ordinary decoder); "
                    "fewer threads may reduce memory but slow seeking; unsupported "
                    "builds use the ordinary decoder")
    ap.add_argument("--diagnostics", action="store_true",
                    help="retain bounded sanitized service lifecycle records")
    args = ap.parse_args()
    app.config["PREVIEW_DECODE_THREADS"] = args.preview_decode_threads
    if args.diagnostics:
        try:
            DIAGNOSTICS = diagnostics.Diagnostics(os.path.join(_data_root(), "logs"),
                                                   "http" if args.http else "https",
                                                   openscrub.VERSION)
        except Exception:
            try:
                print("[web] diagnostics unavailable", flush=True)
            except Exception:
                pass
    TOKEN = args.token or None
    app.config["MAX_CONTENT_LENGTH"] = _max_upload_bytes(args.max_upload_gb)
    os.makedirs(JOBS_DIR, exist_ok=True)
    import atexit
    _shutdown_state = {"failed": False, "closed": False}

    def _shutdown(reason="normal"):
        if _shutdown_state["closed"]:
            return
        _shutdown_state["closed"] = True
        vault_result = _vault_lock_atexit()
        if DIAGNOSTICS is not None and not _shutdown_state["failed"]:
            DIAGNOSTICS.close(reason, vault_result)

    atexit.register(_shutdown)
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
        stop_scan_for_shutdown()
        _shutdown("sigterm")
        os._exit(0)
    signal.signal(signal.SIGTERM, _on_sigterm)
    def _run_service():
        threading.Thread(target=_autolock_watcher, daemon=True).start()
        rehydrate_jobs()
        start_worker()
        threading.Thread(target=_worker_watchdog, daemon=True).start()
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
        _serve(args.host, args.port, ssl_ctx)

    try:
        _run_service()
    except KeyboardInterrupt:
        _shutdown("interrupt")
        raise
    except BaseException:
        _shutdown_state["failed"] = True
        raise
    else:
        _shutdown("normal")


def _serve(host, port, ssl_ctx):
    """Run under cheroot (a production WSGI server that supports TLS and
    Windows) when available; otherwise fall back to Flask's built-in dev
    server, which works fine for a small LAN but prints a warning."""
    try:
        from cheroot.wsgi import Server
    except ImportError:
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
    # Browsers probing/rejecting the self-signed certificate abort mid-
    # handshake on every new socket, and cheroot logs each one. Harmless
    # noise (install a trusted cert to stop the aborts themselves) —
    # filter just that class of message, pass everything else through.
    _orig_log = server.error_log
    _TLS_NOISE = ("during handshake", "certificate unknown", "unknown ca",
                  "peer dropped the tls connection", "http request")

    def _quiet_log(msg="", level=20, traceback=False):
        if any(s in str(msg).lower() for s in _TLS_NOISE):
            return
        _orig_log(msg, level, traceback)

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
