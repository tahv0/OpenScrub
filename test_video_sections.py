"""Section reports retain source coordinates and own half-open frame ranges."""
from copy import deepcopy
import importlib
import importlib.util
import json
import math

import pytest


def sections():
    assert importlib.util.find_spec("video_sections"), "Section report helpers are missing"
    return importlib.import_module("video_sections")


def report(rows=(), *, frames=12, total=12, offset=0, fps=10.0):
    return {
        "source_identity": {"input_sha256": "a" * 64, "fps": fps,
                            "total_frames": total},
        "provenance": {"input": "/recording/cfr.mp4", "input_sha256": "a" * 64,
                       "original_input": "/recording/original.mov",
                       "vfr_normalized": True, "settings": {"categories": "plate",
                       "plate_model": "old-model"}},
        "render_state": {"fps": fps,
                         "cum": [[offset + i * 2, offset - i] for i in range(frames)],
                         "bands": [[i, -i] for i in range(frames)]},
        "detections": deepcopy(list(rows)),
        "custom_metadata": {"reviewer_note": "Keep the source timeline"},
    }


def row(frame, **changes):
    value = {"t_start": frame / 10, "t_end": (frame + .3) / 10,
             "last_seen": frame / 10, "frame_index": frame,
             "cbox": [10, 20, 50, 40], "aoff": [frame * 2, -frame],
             "category": "plate", "text": "plate", "enabled": True,
             "dense": True, "track": 7, "person": 3, "confidence": .8}
    value.update(changes)
    return value


def span(**changes):
    value = row(1, frame_index=-1, dense=False, t_end=1.0, last_seen=.6,
                category="manual", text="manual", track=-1, person=-1)
    value.update(changes)
    return value


def active_frames(value, fps=10.0):
    """Independent rendering oracle, including the existing legacy tolerance."""
    return [i for i in range(12)
            if (value.get("owned_start_frame", -1) < 0 or i >= value["owned_start_frame"])
            and (value.get("owned_end_frame", -1) < 0 or i < value["owned_end_frame"])
            and (value.get("frame_index", -1) == i if value.get("frame_index", -1) >= 0
                 else value["t_start"] - .01 <= i / fps <= value["t_end"] + .01)]


def test_bounds_use_the_source_timeline_and_ceil_both_edges():
    module = sections()
    source = report(frames=7)
    assert module.bounds(source, .21, .71) == (3, 8)
    assert module.bounds(source, 0, 1.2) == (0, 12)
    assert module.bounds(source, .3, .8) == (3, 8)


@pytest.mark.parametrize("start,end", [(math.nan, 1), (0, math.inf), (-.1, .2),
                                      (.8, .7), (.2, .2), (0, 1.21), (.21, .22)])
def test_bounds_reject_invalid_or_empty_frame_intervals(start, end):
    with pytest.raises(ValueError):
        sections().bounds(report(), start, end)


def test_identity_requires_explicit_total_and_consistent_hash_fps():
    module = sections()
    source = report()
    assert module.identity(source) == {"input_sha256": "a" * 64, "fps": 10.0,
                                       "total_frames": 12}
    del source["source_identity"]
    with pytest.raises(ValueError, match="identity|total|frame count"):
        module.identity(source)
    source["stop_review"] = {"next_frame": 6, "total_frames": 12, "fps": 10,
                             "input_sha256": "a" * 64, "state": "paused"}
    assert module.identity(source)["total_frames"] == 12
    source["stop_review"]["fps"] = 20
    with pytest.raises(ValueError, match="FPS|fps|timeline"):
        module.identity(source)


def test_slice_keeps_global_timeline_rejections_human_shapes_and_metadata():
    module = sections()
    quad = [[.1, .2], [.9, .1], [.8, .9], [.2, .8]]
    source = report([row(3), row(4, enabled=False, verified_label="not_plate"),
                     row(5, verified_label="plate", plate_quad=quad), span(), row(8)])
    source["stop_review"] = {"next_frame": 8, "total_frames": 12, "fps": 10,
                             "input_sha256": "a" * 64, "state": "paused"}
    saved = deepcopy(source)
    result = module.slice_report(source, 4, 8)
    assert source == saved
    assert "stop_review" not in result
    assert result["render_state"] == source["render_state"]
    assert result["source_identity"] == source["source_identity"]
    assert result["provenance"]["input"] == "/recording/cfr.mp4"
    assert result["custom_metadata"] == source["custom_metadata"]
    assert [r["frame_index"] for r in result["detections"]] == [4, 5, -1]
    assert result["detections"][0]["enabled"] is False
    assert result["detections"][0]["verified_label"] == "not_plate"
    assert result["detections"][1]["plate_quad"] == quad
    assert active_frames(result["detections"][2]) == [4, 5, 6, 7]
    result["detections"][1]["plate_quad"][0][0] = 0
    assert source == saved


def test_slice_clips_audio_and_transcript_without_rebasing_time():
    source = report()
    source["audio_redactions"] = [{"t0": .1, "t1": .5, "mode": "mute"},
                                   {"t0": .7, "t1": 1.0, "mode": "bleep"},
                                   {"t0": .8, "t1": .9, "mode": "mute"}]
    source["audio_suggestions"] = [{"t0": .2, "t1": .9, "text": "secret",
                                    "enabled": False, "category": "name"}]
    source["audio_transcript"] = [[.1, .4, "before"], [.3, .5, "boundary"],
                                   [.7, .9, "after"]]
    result = sections().slice_report(source, 4, 8)
    assert result["audio_redactions"] == [{"t0": .4, "t1": .5, "mode": "mute"},
                                          {"t0": .7, "t1": .8, "mode": "bleep"}]
    assert result["audio_suggestions"] == [{"t0": .4, "t1": .8, "text": "secret",
                                           "enabled": False, "category": "name"}]
    assert result["audio_transcript"] == [[.4, .5, "boundary"], [.7, .8, "after"]]


def test_coverage_checks_checkpoint_and_both_timeline_arrays():
    module = sections()
    source = report()
    source["stop_review"] = {"next_frame": 6, "total_frames": 12, "fps": 10,
                             "input_sha256": "a" * 64, "state": "paused"}
    assert module.covered(source, 2, 6) is True
    with pytest.raises(ValueError, match="scanned|checkpoint|coverage"):
        module.covered(source, 2, 7)
    for key in ("cum", "bands"):
        short = report()
        short["render_state"][key] = short["render_state"][key][:5]
        with pytest.raises(ValueError, match="timeline|scanned|coverage"):
            module.covered(short, 4, 6)


@pytest.mark.parametrize("provenance", [
    {"windows": [{"t0": .0, "t1": .25}, {"t0": .5, "t1": 1.0}]},
    {"settings": {"windows_data": [{"t0": .0, "t1": .25}, {"t0": .5, "t1": 1.0}]}},
    {"settings": {"detect_windows": "0-0.3,0.6-1.2"}},
    {"settings": {"detect_windows_frac": "0-.25,.5-1"}},
])
def test_coverage_rejects_fast_skipped_gaps_even_with_full_zero_timeline(provenance):
    source = report()
    source["provenance"].update(provenance)
    module = sections()
    assert module.covered(source, 0, 3)
    assert module.covered(source, 6, 12)
    with pytest.raises(ValueError, match="scanned|coverage|window"):
        module.covered(source, 2, 7)


def test_coverage_respects_skip_and_resume_limits_but_windows_override_skip():
    module = sections()
    source = report()
    source["provenance"]["settings"].update(skip_start=.2, skip_end=.3)
    assert module.covered(source, 2, 9)
    with pytest.raises(ValueError):
        module.covered(source, 1, 9)
    with pytest.raises(ValueError):
        module.covered(source, 2, 10)
    source["provenance"]["windows"] = [{"t0": 0, "t1": 1}]
    assert module.covered(source, 0, 12)
    source["provenance"]["settings"]["resume_start"] = .4
    with pytest.raises(ValueError):
        module.covered(source, 3, 5)


def test_replace_preserves_outside_rows_ids_and_masks_with_no_boundary_leaks():
    module = sections()
    previous = report([row(1, enabled=False, verified_label="not_plate"),
                       row(3, verified_label="plate", plate_quad=[[0, 0], [1, 0], [1, 1], [0, 1]]),
                       row(4), row(7), row(8), row(10), span(category="name", text="sensitive")])
    candidate = report([row(i, track=7, person=3, text="new") for i in range(3, 9)], offset=100)
    candidate["provenance"]["settings"]["plate_model"] = "new-model"
    before, incoming = deepcopy(previous), deepcopy(candidate)
    merged = module.replace_range(previous, candidate, 4, 8)
    assert previous == before and candidate == incoming
    old = [r for r in merged["detections"] if r["text"] != "new"]
    for index in (1, 3, 8, 10):
        assert next(r for r in old if r["frame_index"] == index) == next(
            r for r in previous["detections"] if r["frame_index"] == index)
    fresh = [r for r in merged["detections"] if r["text"] == "new"]
    assert [r["frame_index"] for r in fresh] == [4, 5, 6, 7]
    assert len({r["track"] for r in fresh}) == 1
    assert fresh[0]["track"] != 7 and fresh[0]["person"] != 3
    kept_span = [r for r in old if r["text"] == "sensitive"]
    assert [active_frames(r) for r in kept_span] == [[1, 2, 3], [8, 9, 10]]
    assert merged["render_state"]["cum"][:4] == previous["render_state"]["cum"][:4]
    assert merged["render_state"]["cum"][8:] == previous["render_state"]["cum"][8:]
    assert merged["render_state"]["bands"][:4] == previous["render_state"]["bands"][:4]
    assert merged["render_state"]["bands"][8:] == previous["render_state"]["bands"][8:]
    # Reconciliation must preserve both screen positions and drift anchors.
    for changed in fresh:
        index = changed["frame_index"]
        original = next(r for r in candidate["detections"] if r["frame_index"] == index)
        ox, oy = merged["render_state"]["cum"][index]
        cx, cy = candidate["render_state"]["cum"][index]
        assert [changed["cbox"][0] + ox, changed["cbox"][1] + oy] == [10 + cx, 20 + cy]
        assert [ox - changed["aoff"][0], oy - changed["aoff"][1]] == [cx - original["aoff"][0], cy - original["aoff"][1]]
    assert module.covered(merged, 0, 12)
    assert merged["provenance"]["settings"]["plate_model"] == "old-model"
    assert merged["provenance"]["range_specific"] is True
    records = merged["range_provenance"]
    assert [(r["start_frame"], r["end_frame"], r["provenance"]["settings"]["plate_model"])
            for r in records] == [(0, 4, "old-model"), (4, 8, "new-model"), (8, 12, "old-model")]


def test_replace_adopts_candidate_manual_and_audio_review_only_in_owned_range():
    previous = report([span()])
    previous["audio_redactions"] = [{"t0": .1, "t1": 1.0, "mode": "mute"}]
    previous["audio_transcript"] = [[.1, 1.0, "old"]]
    candidate = report([span(enabled=False, text="reviewed manual")])
    candidate["audio_redactions"] = [{"t0": .5, "t1": .6, "mode": "bleep"}]
    candidate["audio_transcript"] = [[.3, .9, "new"]]
    merged = sections().replace_range(previous, candidate, 4, 8)
    assert [active_frames(r) for r in merged["detections"]] == [[1, 2, 3], [8, 9, 10], [4, 5, 6, 7]]
    assert merged["detections"][2]["enabled"] is False
    assert merged["audio_redactions"] == [{"t0": .1, "t1": .4, "mode": "mute"},
                                           {"t0": .5, "t1": .6, "mode": "bleep"},
                                           {"t0": .8, "t1": 1.0, "mode": "mute"}]
    assert merged["audio_transcript"] == [[.1, .4, "old"], [.4, .8, "new"], [.8, 1.0, "old"]]


def test_replace_accepts_short_candidate_timeline_with_verified_total():
    previous = report()
    candidate = report([row(5)], frames=8)
    merged = sections().replace_range(previous, candidate, 4, 8)
    assert len(merged["render_state"]["cum"]) == 12
    assert merged["source_identity"]["total_frames"] == 12


@pytest.mark.parametrize("field,value", [("input_sha256", "b" * 64), ("fps", 12),
                                        ("total_frames", 13)])
def test_replace_rejects_changed_source_identity(field, value):
    candidate = report()
    candidate["source_identity"][field] = value
    if field == "input_sha256":
        candidate["provenance"][field] = value
    if field == "fps":
        candidate["render_state"][field] = value
    with pytest.raises(ValueError, match="source|Source|FPS|frame|timeline|hash"):
        sections().replace_range(report(), candidate, 4, 8)


def test_sliced_report_cannot_claim_coverage_outside_its_owned_section():
    module = sections()
    sliced = module.slice_report(report(), 4, 8)
    assert module.covered(sliced, 4, 8)
    with pytest.raises(ValueError, match="coverage|scanned|section"):
        module.covered(sliced, 3, 8)


def test_second_replacement_keeps_provenance_and_coverage_of_each_owned_range():
    module = sections()
    first = report()
    first["provenance"]["settings"]["detect_windows"] = "0-.4,.8-1.2"
    candidate = report()
    candidate["provenance"]["settings"].update(plate_model="new-model", detect_windows=".4-.8")
    merged = module.replace_range(first, candidate, 4, 8)
    assert module.covered(merged, 0, 12)
    latest = report()
    latest["provenance"]["settings"].update(plate_model="latest-model", detect_windows=".5-.6")
    merged = module.replace_range(merged, latest, 5, 6)
    assert [(r["start_frame"], r["end_frame"])
            for r in merged["range_provenance"]] == [(0, 4), (4, 5), (5, 6), (6, 8), (8, 12)]
    assert module.covered(merged, 0, 12)


def test_carry_manual_keeps_screen_masks_and_padding_when_scroll_tracks_differ():
    module = sections()
    manual = span(plate_quad=[[0, 0], [1, 0], [1, 1], [0, 1]], enabled=False)
    previous = report([manual])
    candidate = report([row(5)], offset=100)
    candidate["render_state"]["cum"][5] = [200, 250]
    saved = deepcopy(candidate)
    result = module.carry_manual(previous, candidate, 4, 8)
    assert candidate == saved
    manual_rows = [r for r in result["detections"] if r["category"] == "manual"]
    assert [active_frames(r) for r in manual_rows] == [[4], [5], [6], [7]]
    assert all(r["enabled"] is False for r in manual_rows)
    for carried in manual_rows:
        index = carried["frame_index"]
        ox, oy = previous["render_state"]["cum"][index]
        cx, cy = candidate["render_state"]["cum"][index]
        assert [carried["cbox"][0] + cx, carried["cbox"][1] + cy] == [10 + ox, 20 + oy]
        assert [cx - carried["aoff"][0], cy - carried["aoff"][1]] == [ox - manual["aoff"][0], oy - manual["aoff"][1]]
        assert carried["plate_quad"] == manual["plate_quad"]


def test_carry_manual_avoids_per_frame_growth_for_constant_coordinate_translation():
    module = sections()
    previous = report([span()])
    candidate = report(offset=100)
    result = module.carry_manual(previous, candidate, 4, 8)
    assert len(result["detections"]) == 1
    assert active_frames(result["detections"][0]) == [4, 5, 6, 7]
    assert result["detections"][0]["cbox"] == [-90, -80, -50, -60]


@pytest.mark.parametrize("start,end", [(4.5, 8), (4, 8.5), (True, 8), (4, 4), (-1, 4)])
def test_frame_apis_reject_noninteger_or_invalid_intervals(start, end):
    with pytest.raises(ValueError):
        sections().slice_report(report(), start, end)


def test_range_provenance_records_the_actual_learned_model_and_learning_pass():
    previous = report()
    previous["refinement"] = {"model_sha256": "1" * 64, "id": "old"}
    previous["learning"] = {"pass_id": "first", "review_fraction": .1}
    candidate = report()
    candidate["refinement"] = {"model_sha256": "2" * 64, "id": "new"}
    candidate["learning"] = {"pass_id": "second", "review_fraction": .1}
    result = sections().replace_range(previous, candidate, 4, 8)
    assert [record["refinement"]["id"] for record in result["range_provenance"]] == ["old", "new", "old"]
    assert [record["learning"]["pass_id"] for record in result["range_provenance"]] == ["first", "second", "first"]
    assert "refinement" not in result and "learning" not in result


def test_range_provenance_keeps_checker_modes_and_machine_decisions_in_owned_ranges():
    previous = report([row(1), row(5), row(9)])
    previous['verification'] = {'name': 'First checker', 'mode': 'review',
                                'model_sha256': '1' * 64}
    machine = {'decision': 'suppress', 'mode': 'filter', 'applied': True,
               'previous_enabled': True, 'threshold': .5, 'score': .1}
    candidate = report([row(5, enabled=False, plate_verification=machine)])
    candidate['verification'] = {'name': 'Second checker', 'mode': 'filter',
                                 'model_sha256': '2' * 64}
    before, incoming = deepcopy(previous), deepcopy(candidate)
    result = sections().replace_range(previous, candidate, 4, 8)
    assert 'verification' not in result
    assert [(item['start_frame'], item['end_frame'], item['verification']['mode'])
            for item in result['range_provenance']] == [
                (0, 4, 'review'), (4, 8, 'filter'), (8, 12, 'review')]
    chosen = next(item for item in result['detections'] if item['frame_index'] == 5)
    assert chosen['enabled'] is False and chosen['plate_verification'] == machine
    assert not chosen.get('verified_label')
    sliced = sections().slice_report(result, 4, 8)
    assert len(sliced['range_provenance']) == 1
    assert sliced['range_provenance'][0]['verification'] == candidate['verification']
    assert previous == before and candidate == incoming


def test_carried_manual_track_cannot_share_candidate_detector_identity():
    previous = report([span(track=7, person=3)])
    candidate = report([row(5)])
    result = sections().carry_manual(previous, candidate, 4, 8)
    assert result["detections"][0]["track"] == 7
    assert result["detections"][1]["track"] != 7
    assert result["detections"][1]["person"] != 3


def test_legacy_span_splice_renders_exactly_once_at_both_boundaries(tmp_path):
    import openscrub

    previous = report([span(category="name", text="old")])
    candidate = report([span(category="name", text="new")])
    result = sections().replace_range(previous, candidate, 4, 8)
    path = tmp_path / "section.json"
    path.write_text(json.dumps(result))
    rows, _, _ = openscrub.load_report(path)
    for frame, expected in ((3, ["old"]), (4, ["new"]), (7, ["new"]), (8, ["old"])):
        assert [row.text for row in rows if openscrub._sample_active(row, frame, frame / 10)] == expected
