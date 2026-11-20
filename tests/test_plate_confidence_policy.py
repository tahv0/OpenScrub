"""Policy contracts use literal source evidence, not a detector mock."""

import math

import pytest

try:
    from openscrub_internal.plate_policy import evaluate, validate_settings
except ImportError:
    evaluate = validate_settings = None


def row(frame=0, score=.8, *, track=3, origin="detection", box=(1, 2, 11, 8),
        valid=True, choice=None, enabled=True):
    value = {"category": "plate", "track": track, "confidence": score,
             "cbox": box, "enabled": enabled,
             "policy_evidence": {"origin": origin, "frame": frame,
                                 "geometry_valid": valid}}
    if choice is not None:
        value["output_choice"] = choice
    return value


def decisions(rows, policy):
    assert evaluate is not None, "plate policy evaluator has not been implemented"
    return [(x.enabled, x.status) for x in evaluate(rows, policy, .1, .8)]


def test_single_detection_is_a_suggestion_or_candidate_mask():
    sample = [row(score=.9)]
    assert decisions(sample, "manual_review") == [(False, "suggestion")]
    assert decisions(sample, "blur_candidates") == [(True, "automatic")]


@pytest.mark.parametrize("policy", ["manual_review", "blur_candidates"])
def test_choice_and_geometry_truth_table(policy):
    samples = [row(choice="keep"), row(choice="blur"),
               row(choice="blur", valid=False), row(origin="grace"),
               row(box=(1, 2, 1, 8)), row(box=(1, 2, math.nan, 8))]
    assert decisions(samples, policy) == [
        (False, "keep"), (True, "blur"), (False, "gap"),
        (False, "gap"), (False, "gap"), (False, "gap")]


def test_off_preserves_saved_output_even_with_absent_evidence():
    rows = [{"enabled": False}, {"enabled": True}, {}]
    assert decisions(rows, None) == [(False, "saved"), (True, "saved"), (True, "saved")]


def test_manual_review_requires_two_distinct_associated_cutoff_frames_without_retroactive_onset():
    rows = [row(10, .8), row(10, .9), row(11, .79), row(12, .8), row(13, .8),
            row(14, .95, track=4), row(15, .95, track=4)]
    assert decisions(rows, "manual_review") == [
        (False, "suggestion"), (False, "suggestion"), (False, "suggestion"),
        (False, "suggestion"), (True, "automatic"), (False, "suggestion"),
        (True, "automatic")]


def test_synthetic_rows_cannot_promote_detector_support_or_geometry():
    rows = [row(1, .9), row(2, .99, origin="interpolation"),
            row(3, .99, origin="held"), row(4, .9)]
    assert decisions(rows, "manual_review") == [(False, "suggestion"),
        (False, "gap"), (False, "gap"), (True, "automatic")]


def test_invalid_evidence_and_untracked_frames_do_not_create_support():
    rows = [row(1, .9, track=-1), row(2, .9, track=-1),
            row(3, .9, valid=False), row(4, .9), row(5, .9)]
    rows[1]["policy_evidence"]["frame"] = None
    assert decisions(rows, "manual_review") == [(False, "suggestion"),
        (False, "gap"), (False, "gap"), (False, "suggestion"), (True, "automatic")]


def test_candidate_mode_uses_retained_floor_including_equality():
    assert decisions([row(score=.1), row(score=.099)], "blur_candidates") == [
        (True, "automatic"), (False, "suggestion")]


@pytest.mark.parametrize("floor,cutoff", [(.05, .05), (.35, .8), (.95, .95)])
def test_optional_settings_accept_finite_ordered_bounds(floor, cutoff):
    assert validate_settings is not None, "plate policy settings validator has not been implemented"
    validate_settings("manual_review", floor, cutoff)


@pytest.mark.parametrize("policy,floor,cutoff", [
    ("manual_review", .04, .8), ("manual_review", .8, .7),
    ("blur_candidates", .1, .96), ("manual_review", math.nan, .8),
    ("manual_review", .1, math.inf), ("unknown", .1, .8),
    ("manual_review", .1, None)])
def test_optional_settings_reject_invalid_requests(policy, floor, cutoff):
    assert validate_settings is not None, "plate policy settings validator has not been implemented"
    with pytest.raises(ValueError):
        validate_settings(policy, floor, cutoff)


def test_oversized_json_integers_are_invalid_evidence_and_settings():
    huge = 10 ** 1000
    with pytest.raises(ValueError):
        validate_settings("manual_review", .1, huge)
    assert decisions([row(box=(1, 2, huge, 8)), row(score=huge)],
                     "blur_candidates") == [(False, "gap"), (False, "suggestion")]
