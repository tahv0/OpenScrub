"""Pure decisions over provenance-capable plate observations.

Track association is supplied by the existing dense-track assignment. Only
consecutive eligible *direct* observations in that association can activate
review-mode output; synthetic samples never contribute evidence. No cutoff
or time window is calibrated here.
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


def evaluate(rows, policy, candidate_floor, auto_cutoff, *, capable_off=False):
    """Return output decisions in row order without modifying the observations.

    A track must have been assigned by the scan's existing association pass.
    Low/invalid direct observations interrupt cutoff support, and same-frame
    duplicates never count twice. A decision starts at its own source frame.
    Synthetic and unsupported positions are gaps even for explicit Blur.
    """
    validate_settings(policy, candidate_floor, auto_cutoff)
    if policy is None or policy == "off":
        results = []
        for row in rows:
            choice = _get(row, "output_choice")
            if capable_off and _get(row, "category") == "plate":
                if choice == "keep":
                    results.append(Decision(False, "keep"))
                elif not _valid_geometry(row):
                    results.append(Decision(False, "gap"))
                elif choice == "blur":
                    results.append(Decision(True, "blur"))
                else:
                    results.append(Decision(bool(_get(row, "enabled", True)), "saved"))
            else:
                results.append(Decision(bool(_get(row, "enabled", True)), "saved"))
        return results

    results = [None] * len(rows)
    previous = {}
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
        supported = bool(cutoff_eligible and prior and prior[1]
                         and type(frame) is int and frame > prior[0])
        # Synthetic rows do not become, or reset, direct-observation evidence.
        # A repeated same-frame hit cannot replace the first observation.
        if associated and direct and type(frame) is int and frame >= 0:
            if prior is None or frame > prior[0]:
                previous[track] = (frame, bool(cutoff_eligible))

        choice = _get(row, "output_choice")
        if choice == "keep":
            results[index] = Decision(False, "keep")
        elif not valid or choice not in (None, "blur"):
            results[index] = Decision(False, "gap")
        elif choice == "blur":
            results[index] = Decision(True, "blur")
        elif (policy == "blur_candidates" and eligible) or (
                policy == "manual_review" and supported):
            results[index] = Decision(True, "automatic")
        else:
            results[index] = Decision(False, "suggestion")
    return results
