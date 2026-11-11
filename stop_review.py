"""Atomic report checkpoints and safe, review-preserving scan continuation.

Stop & Review is intentionally separate from the generic Cancel action. An
ordinary cancelled scan still has no report. A cooperatively stopped scan is
post-processed first, then committed here as a reviewable partial report.
"""
import copy
import json
import math
import os
import tempfile


class CheckpointError(ValueError):
    pass


def _write_compact_json(out, document):
    """Batch large arrays through the C encoder without a whole-report string.

    Reports have string-keyed objects and large detection/timeline arrays.
    Keep standard JSON conversions for unusual keys and values. Batches bound
    the number of rows encoded at once, not the size of an individual row.
    """
    encoder = json.JSONEncoder(separators=(",", ":"))
    active = set()

    def write(value):
        if isinstance(value, dict) and all(isinstance(k, str) for k in value):
            if id(value) in active:
                raise ValueError("Circular reference detected")
            active.add(id(value))
            try:
                out.write("{")
                for i, (key, item) in enumerate(value.items()):
                    if i:
                        out.write(",")
                    out.write(encoder.encode(key) + ":")
                    write(item)
                out.write("}")
            finally:
                active.remove(id(value))
        elif isinstance(value, (list, tuple)):
            out.write("[")
            for start in range(0, len(value), 256):
                if start:
                    out.write(",")
                out.write(encoder.encode(value[start:start + 256])[1:-1])
            out.write("]")
        else:
            out.write(encoder.encode(value))

    write(document)


def atomic_report(path, document):
    """Publish a whole report or leave the preceding verified one unchanged."""
    directory = os.path.dirname(os.path.abspath(path))
    fd, tmp = tempfile.mkstemp(prefix=".report-", suffix=".json", dir=directory)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as out:
            _write_compact_json(out, document)
            out.flush()
            os.fsync(out.fileno())
        try:
            os.chmod(tmp, 0o600)
        except OSError:
            pass
        os.replace(tmp, path)
    finally:
        if os.path.exists(tmp):
            os.remove(tmp)


def with_checkpoint(doc, frame, total, options):
    """First partial scan; source hash/length live beside report data."""
    result = copy.deepcopy(doc)
    fps = float(result["render_state"]["fps"])
    frame, total = int(frame), int(total)
    if not (math.isfinite(fps) and fps > 0 and
            0 < frame < total and len(result["render_state"]["cum"]) >= frame and
            len(result["render_state"]["bands"]) >= frame):
        raise CheckpointError("Invalid stop frame or incomplete render timeline")
    source_hash = result.get("provenance", {}).get("input_sha256")
    if not source_hash:
        raise CheckpointError("Missing input provenance; cannot safely resume")
    result["stop_review"] = {
        "schema": 1, "state": "paused",
        "next_frame": frame, "total_frames": total, "fps": fps,
        "input_sha256": source_hash, "options": copy.deepcopy(options),
    }
    return result


def validate_resume(doc, source_sha256=None):
    meta = doc.get("stop_review")
    if not isinstance(meta, dict) or meta.get("state") != "paused":
        raise CheckpointError("Job is not paused at a saved checkpoint")
    fps = float(meta.get("fps", 0))
    frame, total = int(meta.get("next_frame", -1)), int(meta.get("total_frames", 0))
    if (not math.isfinite(fps) or fps <= 0 or frame <= 0 or total <= frame
            or len(doc["render_state"].get("cum", [])) < frame
            or len(doc["render_state"].get("bands", [])) < frame):
        raise CheckpointError("Corrupt checkpoint frame/timeline")
    if (source_sha256 is not None and
            meta.get("input_sha256") != source_sha256):
        raise CheckpointError("Source video changed after checkpoint; "
                              "resume refused to avoid wrong blur positions")
    return meta


def join_reports(previous, continuation, next_frame, total_frames,
                 completed=False):
    """Append a resumed suffix, preserving all prior human edits and polygons.

    A small overlap is re-scanned for detector continuity. It is NOT trusted
    to replace or remove prior reviewer decisions. Dense track/person IDs in
    the new scan are remapped so two unrelated objects cannot inherit each
    other's review decisions.
    """
    meta = validate_resume(previous)
    cutoff = int(meta["next_frame"])
    next_frame, total_frames = int(next_frame), int(total_frames)
    if not (cutoff < next_frame <= total_frames or
            completed and cutoff <= next_frame <= total_frames):
        raise CheckpointError("Resumed scan did not advance beyond checkpoint")
    if total_frames != int(meta["total_frames"]):
        raise CheckpointError("Source frame count changed since checkpoint")
    fps = float(meta["fps"])
    rs = continuation["render_state"]
    if abs(float(rs["fps"]) - fps) > 0.001:
        raise CheckpointError("Source FPS changed since checkpoint")
    if continuation.get("provenance", {}).get("input_sha256") != meta["input_sha256"]:
        raise CheckpointError("Source hash differs; refusing report merge")
    old_rs = previous["render_state"]
    for key in ("cum", "bands"):
        if len(old_rs[key]) < cutoff or len(rs[key]) < next_frame:
            raise CheckpointError("Frame-aligned render state is incomplete")
    merged = copy.deepcopy(continuation)
    merged["render_state"] = {
        **rs,
        "cum": old_rs["cum"][:cutoff] + rs["cum"][cutoff:],
        "bands": old_rs["bands"][:cutoff] + rs["bands"][cutoff:],
    }
    # Previously approved/denied detections and 4-corner annotations are
    # retained byte-for-byte apart from the ID remap applied to the suffix.
    older = copy.deepcopy(previous.get("detections", []))
    track_max = max([int(d.get("track", -1)) for d in older] + [-1])
    person_max = max([int(d.get("person", -1)) for d in older] + [-1])
    remap_track, remap_person = {}, {}
    newer = []
    boundary = cutoff / fps
    for det in continuation.get("detections", []):
        if float(det.get("t_end", 0)) <= boundary:
            continue
        d = copy.deepcopy(det)
        d["t_start"] = max(boundary, float(d["t_start"]))
        if float(d["t_end"]) < d["t_start"]:
            continue
        for field, mapping, last in (("track", remap_track, track_max),
                                     ("person", remap_person, person_max)):
            old_id = int(d.get(field, -1))
            if old_id >= 0:
                if old_id not in mapping:
                    mapping[old_id] = last + 1 + len(mapping)
                d[field] = mapping[old_id]
        newer.append(d)
    merged["detections"] = older + newer
    # Rows keep the checker SHA/mode that produced their machine decisions.
    # Retain every corresponding assessment across paused prefixes, without
    # claiming the latest chunk's checker also assessed those earlier rows.
    verification_history = []
    for document in (previous, continuation):
        audits = list(document.get("verification_history") or [])
        if document.get("verification"):
            audits.append(document["verification"])
        for audit in audits:
            if audit not in verification_history:
                verification_history.append(copy.deepcopy(audit))
    if verification_history:
        merged["verification_history"] = verification_history
    # Audio review, if edited, belongs to the reviewer; never wipe it.
    if "audio_redactions" in previous:
        merged["audio_redactions"] = copy.deepcopy(previous["audio_redactions"])
    if "audio_suggestions" in previous:
        merged["audio_suggestions"] = copy.deepcopy(previous["audio_suggestions"])
    if "audio_transcript" in previous:
        merged["audio_transcript"] = copy.deepcopy(previous["audio_transcript"])
    # Custom provenance options are captured once, not replaced with the
    # resume-only CLI flags.
    merged["provenance"] = copy.deepcopy(previous.get("provenance", {}))
    if completed:
        merged.pop("stop_review", None)
    else:
        fresh = copy.deepcopy(meta)
        fresh["next_frame"] = next_frame
        merged["stop_review"] = fresh
    return merged
