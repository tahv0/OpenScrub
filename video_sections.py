"""Pure helpers for reviewable sections on an absolute source-frame timeline.

All frame intervals are half open: ``[start_frame, end_frame)``. Report rows
retain the source video's coordinates and times; a sliced report is rendered
with a separate output trim. ``owned_start_frame`` / ``owned_end_frame`` bound
legacy detection holds, whose renderer otherwise includes a time tolerance.

Callers verify the actual source file before persisting ``source_identity``.
These helpers never infer a full video's length from a selected scan's arrays
when combining reports, and never mutate an input report.
"""
from copy import deepcopy
import math


class SectionError(ValueError):
    """An interval or report cannot safely be used as a video section."""


def _number(value, name):
    if isinstance(value, bool):
        raise SectionError("Invalid " + name)
    try:
        value = float(value)
    except (TypeError, ValueError, OverflowError) as error:
        raise SectionError("Invalid " + name) from error
    if not math.isfinite(value):
        raise SectionError("Invalid " + name)
    return value


def _integer(value, name):
    if not isinstance(value, int) or isinstance(value, bool):
        raise SectionError("Invalid integer " + name)
    return value


def _timeline(doc):
    try:
        rs = doc["render_state"]
        fps = _number(rs["fps"], "FPS")
    except (KeyError, TypeError) as error:
        raise SectionError("Missing render timeline") from error
    if fps <= 0:
        raise SectionError("Invalid FPS")
    explicit = []
    for meta in (doc.get("source_identity"), doc.get("stop_review"), rs):
        if meta is None:
            continue
        if not isinstance(meta, dict):
            raise SectionError("Invalid source timeline metadata")
        if "fps" in meta and not math.isclose(
                _number(meta["fps"], "FPS"), fps, rel_tol=1e-12, abs_tol=1e-8):
            raise SectionError("Source FPS differs from render timeline")
        if "total_frames" in meta:
            explicit.append(_integer(meta["total_frames"], "total frame count"))
    try:
        total = explicit[0] if explicit else len(rs["cum"])
    except (KeyError, TypeError) as error:
        raise SectionError("Missing frame-aligned render timeline") from error
    if total <= 0 or any(value != total for value in explicit):
        raise SectionError("Source frame count differs from render timeline")
    return fps, total, bool(explicit)


def identity(doc):
    """Return the verified source hash/FPS/total, requiring an explicit total.

    New reports store this result as ``source_identity``. Existing checkpoint
    metadata or ``render_state.total_frames`` can supply the explicit length.
    Paths are not identities: normalized and original paths remain provenance.
    """
    fps, total, explicit = _timeline(doc)
    if not explicit:
        raise SectionError("Missing source identity total frame count")
    source = doc.get("provenance", {}).get("input_sha256")
    if (not isinstance(source, str) or len(source) != 64
            or any(character not in "0123456789abcdef" for character in source)):
        raise SectionError("Missing verified source hash")
    for meta in (doc.get("source_identity"), doc.get("stop_review")):
        if meta is not None and meta.get("input_sha256") != source:
            raise SectionError("Source hash differs from report provenance")
    return {"input_sha256": source, "fps": fps, "total_frames": total}


def _ceil_frame(seconds, fps):
    value = seconds * fps
    nearest = round(value)
    # Arithmetic such as (frame / fps) * fps can land a few ULPs above an
    # integer. Do not turn an already snapped boundary into the next frame.
    if abs(value - nearest) <= 4 * math.ulp(value):
        value = nearest
    return int(math.ceil(value))


def _frames(doc, start_frame, end_frame):
    fps, total, _ = _timeline(doc)
    start = _integer(start_frame, "start frame")
    end = _integer(end_frame, "end frame")
    if not 0 <= start < end <= total:
        raise SectionError("Section frame interval is empty or outside the source timeline")
    return fps, total, start, end


def bounds(doc, start_seconds, end_seconds):
    """Validate seconds and snap both edges upward to source frame indices."""
    fps, total, _ = _timeline(doc)
    start = _number(start_seconds, "section start")
    end = _number(end_seconds, "section end")
    if not 0 <= start < end <= total / fps:
        raise SectionError("Section time interval is empty or outside the source timeline")
    _, _, first, last = _frames(doc, _ceil_frame(start, fps), _ceil_frame(end, fps))
    return first, last


def _merge_intervals(intervals):
    merged = []
    for start, end in sorted(intervals):
        if end <= start:
            continue
        if merged and start <= merged[-1][1]:
            merged[-1] = (merged[-1][0], max(merged[-1][1], end))
        else:
            merged.append((start, end))
    return merged


def _window_pairs(value, scale):
    pairs = []
    for part in value.split(","):
        if not part.strip():
            continue
        start, separator, end = part.strip().partition("-")
        if not separator:
            raise SectionError("Invalid detection window coverage")
        pairs.append((_number(start, "window start") * scale,
                      _number(end, "window end") * scale))
    return pairs


def _provenance_intervals(provenance, fps, total):
    duration = total / fps
    settings = provenance.get("settings") or {}
    if not isinstance(settings, dict):
        raise SectionError("Invalid scan settings coverage")
    windows = provenance.get("windows") or settings.get("windows_data")
    if not windows and isinstance(settings.get("windows"), (list, dict)):
        windows = settings["windows"]
    if isinstance(windows, dict):
        windows = windows.get("windows")
    if windows:
        if not isinstance(windows, list):
            raise SectionError("Invalid scan window coverage")
        pairs = []
        for window in windows:
            if not isinstance(window, dict):
                raise SectionError("Invalid scan window coverage")
            pairs.append((_number(window.get("t0", 0), "window start") * duration,
                          _number(window.get("t1", 1), "window end") * duration))
    elif settings.get("detect_windows_frac"):
        pairs = _window_pairs(settings["detect_windows_frac"], duration)
    elif settings.get("detect_windows"):
        pairs = _window_pairs(settings["detect_windows"], 1)
    else:
        skip_start = _number(settings.get("skip_start") or 0, "skip start")
        skip_end = _number(settings.get("skip_end") or 0, "skip end")
        if skip_start < 0 or skip_end < 0:
            raise SectionError("Invalid skipped scan coverage")
        pairs = [(skip_start, duration - skip_end)]
    resume = _number(settings.get("resume_start") or 0, "resume start")
    if not 0 <= resume < duration:
        raise SectionError("Invalid resume scan coverage")
    intervals = []
    for start, end in pairs:
        if not 0 <= start < end <= duration:
            raise SectionError("Invalid detection window coverage")
        start = max(start, resume)
        intervals.append((_ceil_frame(start, fps), _ceil_frame(end, fps)))
    return _merge_intervals(intervals)


def _coverage_intervals(doc):
    fps, total, _ = _timeline(doc)
    rs = doc["render_state"]
    if not all(isinstance(rs.get(key), (list, tuple)) for key in ("cum", "bands")):
        raise SectionError("Missing frame-aligned render timeline")
    available = min(total, len(rs["cum"]), len(rs["bands"]))
    checkpoint = doc.get("stop_review")
    if checkpoint is not None:
        next_frame = _integer(checkpoint.get("next_frame"), "checkpoint frame")
        if checkpoint.get("state") != "paused" or not 0 <= next_frame <= total:
            raise SectionError("Invalid checkpoint coverage")
        available = min(available, next_frame)
    section = doc.get("section_range") or {"start_frame": 0, "end_frame": total}
    _, _, first, last = _frames(doc, section["start_frame"], section["end_frame"])
    records = doc.get("range_provenance")
    if records is None:
        records = [{"start_frame": 0, "end_frame": total,
                    "provenance": doc.get("provenance", {})}]
    if not isinstance(records, list):
        raise SectionError("Invalid per-range provenance coverage")
    intervals = []
    for record in records:
        _, _, low, high = _frames(doc, record["start_frame"], record["end_frame"])
        if record.get("source_identity") is not None and record["source_identity"] != identity(doc):
            raise SectionError("Per-range source identity differs from report")
        for start, end in _provenance_intervals(record["provenance"], fps, total):
            intervals.append((max(start, low, first), min(end, high, last, available)))
    return _merge_intervals(intervals)


def _vectors(doc, start, end):
    rs = doc["render_state"]
    for key in ("cum", "bands"):
        values = rs.get(key)
        if not isinstance(values, (list, tuple)) or len(values) < end:
            raise SectionError("Frame-aligned render timeline is incomplete")
        for point in values[start:end]:
            if not isinstance(point, (list, tuple)) or len(point) != 2:
                raise SectionError("Invalid render timeline coordinate")
            _number(point[0], "render timeline coordinate")
            _number(point[1], "render timeline coordinate")


def covered(doc, start_frame, end_frame):
    """Return True for scanned coverage, otherwise raise ``SectionError``.

    Array length alone is insufficient: fast-skip fills unscanned frames with
    zero offsets. Honor checkpoint limits and the actual scan-window settings.
    """
    _, _, start, end = _frames(doc, start_frame, end_frame)
    _vectors(doc, start, end)
    if not any(low <= start and end <= high for low, high in _coverage_intervals(doc)):
        raise SectionError("Section includes unscanned frames or a gap in scan coverage")
    return True


def _row_frames(row, fps):
    start = _number(row["t_start"], "detection start")
    end = _number(row["t_end"], "detection end")
    if end < start:
        raise SectionError("Invalid detection interval")
    exact = _integer(row.get("frame_index", -1), "detection frame")
    if exact >= 0:
        low, high = exact, exact + 1
    else:
        # Mirror the existing renderer's inclusive legacy tolerance. The
        # explicit owner fields will enforce the strict splice boundaries.
        lower, upper = start - .01, end + .01
        low, high = int(math.ceil(lower * fps)), int(math.floor(upper * fps)) + 1
        while low / fps < lower:
            low += 1
        while (low - 1) / fps >= lower:
            low -= 1
        while (high - 1) / fps > upper:
            high -= 1
        while high / fps <= upper:
            high += 1
    owned_start = _integer(row.get("owned_start_frame", -1), "owned start frame")
    owned_end = _integer(row.get("owned_end_frame", -1), "owned end frame")
    if owned_start >= 0:
        low = max(low, owned_start)
    if owned_end >= 0:
        high = min(high, owned_end)
    return low, high


def intersects(row, start_frame, end_frame, fps):
    """Whether a row renders in any frame of a half-open interval."""
    low, high = _row_frames(row, fps)
    return max(low, start_frame) < min(high, end_frame)


def _clip_row(row, start, end, fps):
    low, high = _row_frames(row, fps)
    first, last = max(low, start), min(high, end)
    if first >= last:
        return None
    result = deepcopy(row)
    if first == low and last == high:
        return result
    result["owned_start_frame"], result["owned_end_frame"] = first, last
    result["t_start"] = max(float(row["t_start"]), first / fps)
    result["t_end"] = max(result["t_start"], min(float(row["t_end"]), last / fps))
    if "last_seen" in result:
        result["last_seen"] = max(result["t_start"], min(float(result["last_seen"]), (last - 1) / fps))
    return result


def _audio_times(row):
    if isinstance(row, dict):
        return _number(row["t0"], "audio start"), _number(row["t1"], "audio end")
    if isinstance(row, (list, tuple)) and len(row) >= 2:
        return _number(row[0], "audio start"), _number(row[1], "audio end")
    raise SectionError("Invalid audio timeline row")


def _clip_audio(rows, start, end):
    clipped = []
    for row in rows:
        low, high = _audio_times(row)
        if high < low:
            raise SectionError("Invalid audio interval")
        first, last = max(low, start), min(high, end)
        if first >= last:
            continue
        result = deepcopy(row)
        if isinstance(result, dict):
            result["t0"], result["t1"] = first, last
        else:
            result = [first, last, *result[2:]]
        clipped.append(result)
    return clipped


def _provenance_records(doc, start, end):
    _, total, _ = _timeline(doc)
    records = doc.get("range_provenance")
    if records is None:
        records = [{"start_frame": 0, "end_frame": total,
                    "source_identity": identity(doc),
                    "provenance": deepcopy(doc.get("provenance", {}))}]
        for key in ("refinement", "learning"):
            if key in doc:
                records[0][key] = deepcopy(doc[key])
    result = []
    for record in records:
        first, last = max(start, record["start_frame"]), min(end, record["end_frame"])
        if first < last:
            item = deepcopy(record)
            item.update(start_frame=first, end_frame=last)
            result.append(item)
    return result


def slice_report(doc, start_frame, end_frame):
    """Copy a scanned section, preserving absolute source times and offsets.

    Export approval is a caller responsibility. The returned report has no
    ``stop_review`` block, but ``section_range`` prevents reuse as a whole scan.
    """
    fps, _, start, end = _frames(doc, start_frame, end_frame)
    covered(doc, start, end)
    result = deepcopy(doc)
    result.pop("stop_review", None)
    result["section_range"] = {"start_frame": start, "end_frame": end}
    result["detections"] = [clipped for row in doc.get("detections", [])
                            if (clipped := _clip_row(row, start, end, fps)) is not None]
    for key in ("audio_redactions", "audio_suggestions", "audio_transcript"):
        if key in doc:
            result[key] = _clip_audio(doc[key], start / fps, end / fps)
    if "range_provenance" in doc:
        result["range_provenance"] = _provenance_records(doc, start, end)
    return result


def _translate(row, delta):
    result = deepcopy(row)
    dx, dy = delta
    if dx or dy:
        box = result["cbox"]
        anchor = result.get("aoff", (0, 0))
        result["cbox"] = [box[0] - dx, box[1] - dy, box[2] - dx, box[3] - dy]
        result["aoff"] = [anchor[0] + dx, anchor[1] + dy]
    return result


def _matching_sources(previous, candidate):
    if identity(previous) != identity(candidate):
        raise SectionError("Source hash, FPS or total frame count changed during rescan")


def _remap_ids(rows, previous):
    for field in ("track", "person"):
        highest = max([_integer(row.get(field, -1), field + " ID")
                       for row in previous] + [-1])
        mapping = {}
        for row in rows:
            value = _integer(row.get(field, -1), field + " ID")
            if value >= 0:
                if value not in mapping:
                    mapping[value] = highest + 1 + len(mapping)
                row[field] = mapping[value]


def replace_range(previous, candidate, start_frame, end_frame):
    """Adopt a reviewed candidate only within its owned frame interval.

    Earlier/later timeline entries, reviewer decisions and masks are retained.
    A constant coordinate translation aligns the candidate's scroll origin;
    inverse box translation preserves its screen geometry and drift padding.
    Candidate manual/audio edits are adopted along with automated detections.
    """
    _matching_sources(previous, candidate)
    fps, total, start, end = _frames(previous, start_frame, end_frame)
    covered(candidate, start, end)
    _vectors(previous, start, end)
    old_rs, new_rs = previous["render_state"], candidate["render_state"]
    delta = [old_rs["cum"][start][axis] - new_rs["cum"][start][axis] for axis in (0, 1)]
    result = deepcopy(previous)
    result["render_state"]["cum"][start:end] = [
        [point[0] + delta[0], point[1] + delta[1]] for point in new_rs["cum"][start:end]]
    result["render_state"]["bands"][start:end] = deepcopy(new_rs["bands"][start:end])
    older = []
    for row in previous.get("detections", []):
        if not intersects(row, start, end, fps):
            older.append(deepcopy(row))
            continue
        for first, last in ((0, start), (end, total)):
            clipped = _clip_row(row, first, last, fps)
            if clipped is not None:
                older.append(clipped)
    newer = []
    for row in candidate.get("detections", []):
        clipped = _clip_row(row, start, end, fps)
        if clipped is not None:
            newer.append(_translate(clipped, delta))
    _remap_ids(newer, previous.get("detections", []))
    result["detections"] = older + newer
    for key in ("audio_redactions", "audio_suggestions", "audio_transcript"):
        if key in previous or key in candidate:
            combined = (_clip_audio(previous.get(key, []), 0, start / fps)
                        + _clip_audio(candidate.get(key, []), start / fps, end / fps)
                        + _clip_audio(previous.get(key, []), end / fps, total / fps))
            result[key] = sorted(combined, key=lambda row: _audio_times(row)[0])
    result["range_provenance"] = sorted(
        _provenance_records(previous, 0, start)
        + _provenance_records(candidate, start, end)
        + _provenance_records(previous, end, total),
        key=lambda record: record["start_frame"])
    result["provenance"]["range_specific"] = True
    result["provenance"]["settings_scope"] = "initial_scan"
    # Refiner checksums and learning-pass settings describe the corresponding
    # owned range, not every frame after a partial replacement.
    result.pop("refinement", None)
    result.pop("learning", None)
    return result


def carry_manual(previous, candidate, start_frame, end_frame):
    """Stage prior manual masks in candidate coordinates before human review.

    Exclude manual rows from ``video_learning`` constraints before calling this
    helper. Constant scroll translations retain one row; varying translations
    use exact-frame rows to preserve every source-frame mask and drift anchor.
    No later acceptance step restores these rows over the reviewer's changes.
    """
    _matching_sources(previous, candidate)
    fps, _, start, end = _frames(previous, start_frame, end_frame)
    covered(candidate, start, end)
    _vectors(previous, start, end)
    result = deepcopy(candidate)
    rows = []
    for row in previous.get("detections", []):
        if row.get("category") != "manual":
            continue
        clipped = _clip_row(row, start, end, fps)
        if clipped is None:
            continue
        low, high = _row_frames(clipped, fps)
        deltas = [[candidate["render_state"]["cum"][frame][axis]
                   - previous["render_state"]["cum"][frame][axis] for axis in (0, 1)]
                  for frame in range(low, high)]
        if all(delta == deltas[0] for delta in deltas):
            rows.append(_translate(clipped, deltas[0]))
        else:
            for frame, delta in zip(range(low, high), deltas):
                carried = _translate(clipped, delta)
                carried.update(frame_index=frame, t_start=frame / fps,
                               t_end=(frame + .3) / fps, last_seen=frame / fps,
                               owned_start_frame=frame, owned_end_frame=frame + 1)
                rows.append(carried)
    _remap_ids(rows, candidate.get("detections", []))
    result.setdefault("detections", []).extend(rows)
    return result
