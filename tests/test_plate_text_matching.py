"""Public contract for dormant, literal plate-text matching."""
import copy
from dataclasses import FrozenInstanceError
import subprocess
import sys
import textwrap
from types import MappingProxyType

import pytest


def api():
    from openscrub_internal.plate_search import matching
    return matching


def test_query_normalization_bounds_and_stable_duplicates():
    m = api()
    assert [(q.text, q.mode) for q in m.normalize_queries("ab-c 123; XY987\nABC123")] == [
        ("ABC123", "full"), ("XY987", "full")]
    assert m.normalize_queries(" ,;\r\n\t ABC ;\t ")[0].text == "ABC"
    for raw, expected in [("abc", "ABC"), ("a" * 16, "A" * 16),
                          (" " * 125 + "ABC", "ABC")]:
        assert m.PlateQuery(raw).text == expected
    assert m.normalize_queries(["ABC"] * 10) == (m.PlateQuery("ABC"),)
    assert m.normalize_queries(tuple(["ABC"] * 10)) == (m.PlateQuery("ABC"),)
    payload = "," * 1021 + "ABC"
    assert len(payload) == 1024
    assert m.normalize_queries(payload) == (m.PlateQuery("ABC"),)
    entries = [" " * 125 + "ABC"] * 8
    assert sum(map(len, entries)) == 1024
    assert m.normalize_queries(entries) == (m.PlateQuery("ABC"),)
    for value in ["", " \t,;\r\n", [], (), [""], [" \t"], ["ABC", ""],
                  "AB", "A" * 17, " " * 126 + "ABC", payload + ",",
                  [" " * 125 + "ABC"] * 7 + [" " * 123 + "ABC", "ABC"], ["ABC"] * 11, ",".join(["ABC"] * 11),
                  ["ABC,DEF"], ["ABC;DEF"], ["ABC\nDEF"]]:
        with pytest.raises(ValueError):
            m.normalize_queries(value)
    with pytest.raises(FrozenInstanceError):
        m.PlateQuery("ABC").text = "DEF"


def test_query_ascii_validation_precedes_case_conversion():
    m = api()
    for value in ["ßAB", "ÅBC123", "A\u0301BC", "ＡＢＣ", "AB–123", "AB−123",
                  "AB\u00a0123", "\u2003", "AB/123", "AB*123", "ABC?", "ABC_",
                  "ABC\v", "ABC\f", "ABC\r", "ABC\n", None, 123, b"ABC", True]:
        with pytest.raises(ValueError):
            m.PlateQuery(value)
    for value in [None, 123, b"ABC", {"ABC"}, iter(["ABC"]), [123], [None]]:
        with pytest.raises(ValueError):
            m.normalize_queries(value)
    for mode in ["", "FULL", "exact", "partial", None, 1, ["full"]]:
        with pytest.raises(ValueError):
            m.PlateQuery("ABC", mode)
        with pytest.raises(ValueError):
            m.normalize_queries("ABC", mode=mode)


def test_full_requires_entire_normalized_observation():
    m = api()
    q = m.normalize_queries("ABC123")
    result = m.match_text("ab-c\t1.23", q)
    assert len(result) == 1
    assert result[0].query is q[0]
    assert (result[0].observed_text, result[0].normalized_observed,
            result[0].match_kind) == ("ab-c\t1.23", "ABC123", "full_equal")
    assert m.match_text("XABC123Y", q) == ()
    assert m.match_text("BC123", m.normalize_queries("ABC1234")) == ()


def test_fragment_is_explicit_entire_literal_query():
    m = api()
    assert m.match_text("BC123", m.normalize_queries(["BC1"], mode="fragment"))[0].match_kind == "fragment"
    q = m.normalize_queries("ABC123", mode="fragment")
    assert m.match_text("XABC123Y", q)[0].match_kind == "fragment"
    assert m.match_text("ABC123", q)[0].match_kind == "fragment"
    assert m.match_text("ABC12", q) == ()
    assert m.match_text("BC123", m.normalize_queries("ABC1234")) == ()
    with pytest.raises(ValueError):
        m.normalize_queries("BC", mode="fragment")


def test_no_character_substitution_or_fuzzy_matching():
    m = api()
    for query, observed in [("ABO1", "AB01"), ("ABI", "AB1"), ("ABC123", "ABC124"),
                            ("ABC123", "ABC23"), ("ABC123", "ABXC123")]:
        for mode in ["full", "fragment"]:
            assert m.match_text(observed, m.normalize_queries(query, mode=mode)) == ()


def test_all_matching_queries_keep_order_and_mode_distinction():
    m = api()
    queries = [m.PlateQuery("ABC", "fragment"), m.PlateQuery("ABCABC"),
               m.PlateQuery("ABCABC", "fragment"), m.PlateQuery("ABC", "fragment")]
    matches = m.match_text("ABCABC", queries)
    assert [(r.query.text, r.query.mode, r.match_kind) for r in matches] == [
        ("ABC", "fragment", "fragment"), ("ABCABC", "full", "full_equal"),
        ("ABCABC", "fragment", "fragment")]
    assert matches[0].query is queries[0]
    for bad in [[], (), "ABC", ["ABC"], iter(queries), [m.PlateQuery("ABC")] * 11]:
        with pytest.raises(ValueError):
            m.match_text("ABC", bad)
    corrupted = m.PlateQuery("ABC")
    object.__setattr__(corrupted, "text", "ab-c")
    with pytest.raises(ValueError):
        m.match_text("ABC", [corrupted])
    object.__setattr__(corrupted, "text", "ABC")
    object.__setattr__(corrupted, "mode", "partial")
    with pytest.raises(ValueError):
        m.match_text("ABC", [corrupted])


def test_invalid_observations_do_not_coerce_strip_or_truncate():
    m = api()
    class StringTrap:
        def __str__(self):
            raise AssertionError("must not coerce")
    queries = m.normalize_queries("ABC")
    for value in [None, 123, b"ABC", StringTrap(), "", " .-\t", "AB", "ABC/", "ABC\n",
                  "ABC\u00a0", "ＡＢＣ", "ABC" + " " * 510, " " * 512 + "ABC"]:
        assert m.match_text(value, queries) == ()
        with pytest.raises(ValueError):
            m.match_text(value, [])
        with pytest.raises(ValueError):
            m.match_observation(value, [])
    assert len(m.match_text("ABC" + " " * 509, queries)) == 1
    for value in [None, [], "ABC", {}, {"text": 123}, {"text": "ABC/"}]:
        assert m.match_observation(value, queries) == ()


def test_separate_observations_never_join():
    m = api()
    queries = m.normalize_queries("ABC123")
    assert m.match_observation({"text": "ABC"}, queries) == ()
    assert m.match_observation({"text": "123"}, queries) == ()
    assert len(m.match_observation({"text": "ABC 123"}, queries)) == 1


def test_fragment_preserves_entire_original_candidate_evidence():
    m = api()
    observation = {"text": "XABC123Y", "candidate_box": [0, 0, 900, 400],
                   "protection": {"polygon": [[0, 0], [900, 400]], "mask": [1, 2, 3]},
                   "text_geometry": {"contours": [[1, 2], [40, 80]]},
                   "ocr_score": 0.172, "opaque": {"nested": [None, {"private": "evidence"}]}}
    before = copy.deepcopy(observation)
    result = m.match_observation(observation, m.normalize_queries("ABC123", mode="fragment"))[0]
    assert result.observation is observation
    assert observation == before
    assert result.observation["protection"] is observation["protection"]
    assert result.observation["ocr_score"] == 0.172
    with pytest.raises(FrozenInstanceError):
        result.observation = {}
    with pytest.raises(FrozenInstanceError):
        result.text_match.match_kind = "full_equal"
    observation["opaque"]["nested"].append("caller retains ownership")
    assert result.observation["opaque"]["nested"][-1] == "caller retains ownership"


def test_full_frame_observation_needs_no_detector_box():
    m = api()
    queries = m.normalize_queries("ABC", mode="fragment")
    for origin in ["full_frame_text", "text_contour", "other", None]:
        observation = MappingProxyType({"text": "XABCY", "origin": origin})
        result = m.match_observation(observation, queries)
        assert len(result) == 1
        assert result[0].observation is observation
        assert dict(observation) == {"text": "XABCY", "origin": origin}


def test_distinct_observations_remain_distinct_evidence():
    m = api()
    first, second = {"text": "ABC"}, {"text": "ABC"}
    queries = m.normalize_queries("ABC")
    assert m.match_observation(first, queries)[0].observation is first
    assert m.match_observation(second, queries)[0].observation is second


def test_errors_and_reprs_exclude_sensitive_text(capsys, caplog):
    m = api()
    raw, normalized = "se-cr.et123", "SECRET123"
    query = m.PlateQuery(raw)
    result = m.match_observation({"text": raw, "private": normalized}, [query])[0]
    for value in [query, result, result.text_match]:
        assert raw not in repr(value)
        assert normalized not in repr(value)
    operations = [lambda: m.PlateQuery(raw + "/"),
                  lambda: m.PlateQuery(raw, "unsupported"),
                  lambda: m.normalize_queries([raw] * 11),
                  lambda: m.match_text(raw, [raw]),
                  lambda: m.match_observation({"text": raw}, [raw])]
    for operation in operations:
        with pytest.raises(ValueError) as error:
            operation()
        assert raw not in str(error.value)
        assert normalized not in str(error.value)
    assert capsys.readouterr() == ("", "")
    assert not caplog.records


def test_matcher_import_is_stdlib_only():
    # Intercept imports themselves, including cached app/third-party imports.
    code = textwrap.dedent('''
        import builtins
        import sys
        import sysconfig
        from pathlib import Path
        import importlib.util
        original_import = builtins.__import__
        stdlib = Path(sysconfig.get_path("stdlib")).resolve()
        def restricted_import(name, globals=None, locals=None, fromlist=(), level=0):
            root = name.split(".")[0]
            if level == 0 and root != "openscrub_internal":
                spec = importlib.util.find_spec(root)
                origin = None if spec is None else spec.origin
                if origin not in ("built-in", "frozen"):
                    path = None if not origin else Path(origin).resolve()
                    if path is None or stdlib not in path.parents or "site-packages" in path.parts:
                        raise AssertionError("non-stdlib import attempted: " + root)
            if name.startswith("openscrub_internal") and name not in (
                "openscrub_internal", "openscrub_internal.plate_search",
                "openscrub_internal.plate_search.matching"):
                raise AssertionError("other internal module attempted")
            if name == "openscrub_internal" and any(part != "plate_search" for part in fromlist):
                raise AssertionError("other internal import attempted")
            if name == "openscrub_internal.plate_search" and any(part != "matching" for part in fromlist):
                raise AssertionError("other plate_search import attempted")
            return original_import(name, globals, locals, fromlist, level)
        builtins.__import__ = restricted_import
        from openscrub_internal.plate_search.matching import normalize_queries, match_text
        assert match_text("ab-c123", normalize_queries("ABC123"))[0].match_kind == "full_equal"
        assert not match_text("XABC123Y", normalize_queries("ABC123"))
        assert match_text("XABC123Y", normalize_queries("ABC123", mode="fragment"))[0].match_kind == "fragment"
    ''')
    child = subprocess.run([sys.executable, "-B", "-c", code], capture_output=True, text=True)
    assert child.returncode == 0, child.stdout + child.stderr
    assert all(line.startswith("ACTIVE_SOURCE ") for line in child.stdout.splitlines())
    assert child.stderr == ""
