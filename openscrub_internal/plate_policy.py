"""Pure decisions over provenance-capable plate observations.

Track association is supplied by the existing dense-track assignment. Only
consecutive eligible *direct* observations in that association can activate
review-mode output; synthetic samples never contribute evidence. No cutoff
or time window is calibrated here.

Output is decided per TRACK: once any sample of a track is blurred (an
explicit Blur or an automatic decision), every sample of that track with a
usable box is blurred too, including synthetic (interpolated, continuation)
samples and low-score observations. Per-frame decisions left the frames
between direct hits unblurred, so the mask flashed off a known plate.
"""

from collections.abc import Mapping
from dataclasses import dataclass
import math


@dataclass(frozen=True)
class Decision:
    enabled: bool
    status: str


def _finite_number(value):
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return False
    try:
        return math.isfinite(value)
    except OverflowError:
        return False


def validate_settings(policy, candidate_floor, auto_cutoff):
    """Validate explicit optional settings; absent policy retains upstream output."""
    if policy is None or policy == "off":
        return
    if policy not in ("manual_review", "blur_candidates"):
        raise ValueError("invalid uncertain plate policy")
    values = (candidate_floor, auto_cutoff)
    if not all(_finite_number(v) for v in values):
        raise ValueError("plate floor and automatic cutoff must be finite numbers")
    if not .05 <= candidate_floor <= auto_cutoff <= .95:
        raise ValueError("require 0.05 <= plate floor <= automatic cutoff <= 0.95")


def _get(row, key, default=None):
    if isinstance(row, Mapping):
        return row.get(key, default)
    name = {"policy_evidence": "_plate_policy_evidence",
            "output_choice": "_plate_output_choice",
            "enabled": "_plate_saved_enabled"}.get(key, key)
    return getattr(row, name, default)


def _valid_geometry(row):
    evidence = _get(row, "policy_evidence")
    if not isinstance(evidence, Mapping) or evidence.get("origin") != "detection":
        return False
    frame = evidence.get("frame")
    if type(frame) is not int or frame < 0 or evidence.get("geometry_valid") is not True:
        return False
    box = _get(row, "cbox")
    if not isinstance(box, (list, tuple)) or len(box) != 4:
        return False
    if not all(_finite_number(v) for v in box):
        return False
    return box[0] < box[2] and box[1] < box[3]


SYNTHETIC_ORIGINS = ("interpolation", "visual_continuation", "grace", "held", "weak", "manual_seed")


def _box_ok(row):
    box = _get(row, "cbox")
    if not isinstance(box, (list, tuple)) or len(box) != 4:
        return False
    if not all(_finite_number(v) for v in box):
        return False
    return box[0] < box[2] and box[1] < box[3]


def is_direct(row):
    evidence = _get(row, "policy_evidence")
    return isinstance(evidence, Mapping) and evidence.get("origin") == "detection"


def supported_geometry(row):
    """A usable box: a direct observation on its frame, or a synthetic sample's span."""
    if _valid_geometry(row):
        return True
    evidence = _get(row, "policy_evidence")
    return (isinstance(evidence, Mapping) and evidence.get("origin") in SYNTHETIC_ORIGINS
            and _box_ok(row))


def active_on_frame(row, t, index):
    """Render a decided sample over its smoothed span, like standard plates.

    The span includes smoothing's grace pads and gap bridging; only enabled
    samples reach the renderer, so this widens coverage, never the decision.
    """
    if not supported_geometry(row):
        return False
    return _get(row, "t_start") - 0.01 <= t <= _get(row, "t_end") + 0.01


def _extend_tracks(rows, results):
    """Blur every usable sample of a track that has any blurred sample."""
    on, explicit = set(), set()
    for row, decision in zip(rows, results):
        track = _get(row, "track")
        if _get(row, "category") != "plate" or type(track) is not int or track < 0:
            continue
        if decision.enabled:
            on.add(track)
        if _get(row, "output_choice") == "blur":
            explicit.add(track)
    if not on:
        return results
    out = []
    for row, decision in zip(rows, results):
        track = _get(row, "track")
        if (not decision.enabled and decision.status == "suggestion"
                and _get(row, "category") == "plate" and track in on
                and _get(row, "output_choice") != "keep" and supported_geometry(row)):
            decision = Decision(True, "blur" if track in explicit else "automatic")
        out.append(decision)
    return out


def evaluate(rows, policy, candidate_floor, auto_cutoff, *, capable_off=False):
    """Return output decisions in row order without modifying the observations.

    A track must have been assigned by the scan's existing association pass.
    Low/invalid direct observations interrupt cutoff support, and same-frame
    duplicates never count twice. Automatic support starts at a direct source
    frame; the resulting blur then covers the whole track (see module doc).
    Only samples without a usable box are gaps, and Keep always wins.
    """
    validate_settings(policy, candidate_floor, auto_cutoff)
    if policy is None or policy == "off":
        results = []
        for row in rows:
            choice = _get(row, "output_choice")
            if capable_off and _get(row, "category") == "plate":
                if choice == "keep":
                    results.append(Decision(False, "keep"))
                elif not supported_geometry(row):
                    results.append(Decision(False, "gap"))
                elif choice == "blur":
                    results.append(Decision(True, "blur"))
                else:
                    results.append(Decision(bool(_get(row, "enabled", True)), "saved"))
            else:
                results.append(Decision(bool(_get(row, "enabled", True)), "saved"))
        return _extend_tracks(rows, results) if capable_off else results

    results = [None] * len(rows)
    previous = {}
    uncertain_tracks = set()
    for row in rows:
        if _get(row, "category") != "plate":
            continue
        track = _get(row, "track")
        if type(track) is not int or track < 0:
            continue
        evidence = _get(row, "policy_evidence")
        origin = evidence.get("origin") if isinstance(evidence, Mapping) else None
        frame = evidence.get("frame") if isinstance(evidence, Mapping) else None
        if (origin not in ("detection", "interpolation", "visual_continuation",
                           "grace", "held", "weak", "manual_seed")
                or (origin == "detection" and (type(frame) is not int or frame < 0))):
            # With no origin/frame we cannot place this row relative to the
            # direct observations; it might be an intervening failed hit.
            uncertain_tracks.add(track)
    def order(item):
        evidence = _get(item[1], "policy_evidence")
        frame = evidence.get("frame") if isinstance(evidence, Mapping) else None
        return (frame if type(frame) is int and frame >= 0 else math.inf, item[0])

    for index, row in sorted(enumerate(rows), key=order):
        if _get(row, "category") != "plate":
            results[index] = Decision(bool(_get(row, "enabled", True)), "saved")
            continue
        evidence = _get(row, "policy_evidence")
        valid = _valid_geometry(row)
        direct = isinstance(evidence, Mapping) and evidence.get("origin") == "detection"
        frame = evidence.get("frame") if direct else None
        track = _get(row, "track")
        associated = type(track) is int and track >= 0
        score = _get(row, "confidence")
        eligible = (valid and _finite_number(score)
                    and candidate_floor <= score <= 1.0)
        cutoff_eligible = eligible and score >= auto_cutoff
        prior = previous.get(track) if associated else None
        supported = bool(track not in uncertain_tracks and cutoff_eligible and prior and prior[1]
                         and type(frame) is int and frame > prior[0])
        # Synthetic rows do not become, or reset, direct-observation evidence.
        # A repeated same-frame hit cannot replace the first observation.
        if associated and direct and type(frame) is int and frame >= 0:
            if prior is None or frame > prior[0]:
                previous[track] = (frame, bool(cutoff_eligible))

        choice = _get(row, "output_choice")
        if choice == "keep":
            results[index] = Decision(False, "keep")
        elif choice not in (None, "blur") or not supported_geometry(row):
            results[index] = Decision(False, "gap")
        elif choice == "blur":
            results[index] = Decision(True, "blur")
        elif valid and ((policy == "blur_candidates" and eligible) or (
                policy == "manual_review" and supported)):
            results[index] = Decision(True, "automatic")
        else:
            # Synthetic samples are never evidence; they follow their track.
            results[index] = Decision(False, "suggestion")
    return _extend_tracks(rows, results)
