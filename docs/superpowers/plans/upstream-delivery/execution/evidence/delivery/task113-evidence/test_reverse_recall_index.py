"""Reverse recall contracts at the real module boundary, independent of indexing."""
from collections import OrderedDict
from dataclasses import asdict

import pytest
import openscrub as core


def remembered(*pairs):
    memory = core.PhiMemory()
    for word, category in pairs:
        memory.add(word, category)
    return memory


def scan(*words):
    return [(0., (0., 0.), [(w, (1, 2, 11, 12), .99) for w in words])]


def record(text, category, t=0., box=(1, 2, 11, 12), confidence=.99,
           offset=(0., 0.)):
    return dict(t_start=t, t_end=t, cbox=box, category=category, text=text,
                confidence=confidence, aoff=offset, last_seen=0., dense=False,
                track=-1, person=-1, poly=())


def observed(scans, memory, cats=None, namer=None, **kwargs):
    return [asdict(d) for d in core.reverse_pass(
        scans, memory, {'email', 'phone', 'mrn', 'name'} if cats is None else cats,
        namer, **kwargs)]


@pytest.mark.parametrize('cats,expected', [
    ({'email', 'phone', 'mrn'}, 'email'), ({'phone', 'mrn'}, 'phone')])
def test_earlier_fuzzy_key_beats_later_exact_across_lengths(cats, expected):
    # Sorting length buckets or taking an exact shortcut changes the category.
    memory = remembered(('alphaaa', 'email'), ('alpha', 'phone'), ('alphaa', 'mrn'))
    assert observed(scan('alphaa'), memory, cats) == [record('alphaa', expected)]


def test_under_gate_match_does_not_hide_later_eligible_winner():
    memory = remembered(('alphaaa', 'name'), ('alpha', 'phone'))
    assert observed(scan('alphaa'), memory) == [record('alphaa', 'phone')]
    memory.add('ALPHAAA', 'mrn')  # Increment count without changing category/order.
    assert observed(scan('alphaa'), memory) == [record('alphaa', 'name')]


@pytest.mark.parametrize('key,query,hit', [
    ('12345678', '12345678', True), ('12345678', '12345699', True),
    ('12345678', '12345999', False), ('12345678', '123456789', False),
    ('12345678', '1234567x', False), ('1234567x', '12345678', False),
    ('１２３４５６７８', '１２３４５６９９', True),
    ('¹²³⁴', '¹²³⁹', True), ('1234', '１２３４', False),
])
def test_numeric_two_mismatch_rule_keeps_unicode_digit_semantics(key, query, hit):
    memory = remembered((key, 'mrn'))
    assert observed(scan(query), memory) == ([record(query, 'mrn')] if hit else [])


@pytest.mark.parametrize('key,query,lenient,hit', [
    ('abcdef', 'abcd', 76, True), ('abcdefg', 'abcd', 0, False),
    ('abcd', 'abcdef', 76, True), ('abcd', 'abcdefg', 0, False),
    ('abc', 'abcd', 76, True), ('abcde', 'abxde', 80, True),
    ('abcde', 'abxde', 80.01, False), ('abcdefg', 'abcxefg', 76, True),
    ('abcdefg', 'abcxefg', 72, True),
    ('abcdefgh', 'abxxefgh', 72, True), ('abcdefgh', 'abxxefgh', 76, False),
])
def test_alpha_length_and_inclusive_score_boundaries(key, query, lenient, hit):
    memory = remembered((key, 'email'))
    assert observed(scan(query), memory, lenient=lenient) == (
        [record(query, 'email')] if hit else [])


def test_normalization_allowlist_and_short_stopword_filtering():
    memory = remembered(('alphaa', 'email'), ('active', 'email'), ('abc', 'email'))
    namer = core.NameDetector(use_ner=False)
    namer.allow = {'alphaa'}
    assert observed(scan('(Alphaa.)', 'active', 'abc'), memory, namer=namer) == []
    assert observed(scan('(Alphaa.)'), memory) == [record('(Alphaa.)', 'email')]


def test_allowlist_receives_original_word_before_lookup():
    # A caller's exact-word allowlist must not accidentally receive normalized text.
    class OriginalWordAllowlist:
        def _allowed(self, word):
            return word == '(Alphaa.)'
    memory = remembered(('alphaa', 'email'))
    assert observed(scan('(Alphaa.)', 'alphaa'), memory,
                    namer=OriginalWordAllowlist()) == [record('alphaa', 'email')]


def test_unordered_one_shot_scans_keep_duplicates_conversion_and_all_defaults():
    memory = remembered(('alphaa', 'email'))
    scans = iter([(2., [3.5, -2.], [('Alphaa', (-1.9, 2.9, 11.1, 12.9), -.12356)] * 2),
                  (0., [0., 1.], [('alphaa', (1, 2, 11, 12), .12356)]),
                  (2., [3.5, -2.], [('ALPHAA', (1, 2, 11, 12), .9999)])])
    assert observed(scans, memory) == [
        record('Alphaa', 'email', 2., (-1, 2, 11, 12), -.124, (3.5, -2.)),
        record('Alphaa', 'email', 2., (-1, 2, 11, 12), -.124, (3.5, -2.)),
        record('alphaa', 'email', 0., confidence=.124, offset=(0., 1.)),
        record('ALPHAA', 'email', 2., confidence=1., offset=(3.5, -2.))]


def test_pre_call_mapping_and_count_mutations_are_visible_every_invocation():
    memory = remembered(('alphaaa', 'name'), ('alpha', 'phone'))
    assert observed(scan('alphaa'), memory) == [record('alphaa', 'phone')]
    memory.items['alphaaa'] = 'email'
    memory.items.pop('alpha')
    memory.items['alphaa'] = 'mrn'
    assert observed(scan('alphaa'), memory) == [record('alphaa', 'email')]
    memory.items['alphaaa'] = 'name'
    memory.counts['alphaaa'] = 2
    assert observed(scan('alphaa'), memory) == [record('alphaa', 'name')]
    memory.items.pop('alphaaa')
    assert observed(scan('alphaa'), memory) == [record('alphaa', 'mrn')]


@pytest.mark.parametrize('mapping', [dict, OrderedDict])
def test_malformed_key_retains_category_gate_and_original_failure(mapping):
    memory = remembered(('alphaa', 'email'))
    memory.items = mapping([(None, 'phone'), ('alphaa', 'email')])
    assert observed(scan('alphaa'), memory, {'email'}) == [record('alphaa', 'email')]
    with pytest.raises(AttributeError):
        observed(scan('alphaa'), memory, {'phone', 'email'})
    assert observed([], memory) == []
    assert observed(scan('abc', 'active'), memory) == []


def test_nonstring_category_is_not_silently_dropped_or_eagerly_raised():
    memory = remembered(('alphaa', 'email'))
    memory.items['zzzz'] = []
    assert observed(scan('alphaa'), memory) == [record('alphaa', 'email')]
    with pytest.raises(TypeError):
        observed(scan('nomatch'), memory)


@pytest.mark.parametrize('box,confidence,error', [
    (('bad', 2, 11, 12), .9, ValueError), ((1, 2, 11, 12), 'bad', ValueError)])
def test_conversion_failures_only_occur_for_matched_words(box, confidence, error):
    memory = remembered(('alphaa', 'email'))
    assert observed([(0., (0., 0.), [('nomatch', box, confidence)])], memory) == []
    with pytest.raises(error):
        observed([(0., (0., 0.), [('alphaa', box, confidence)])], memory)


def test_custom_mapping_iteration_order_keeps_its_original_priority():
    class ReverseItems(dict):
        def items(self):
            return reversed(list(super().items()))
    memory = remembered(('alphaaa', 'email'), ('alphaa', 'mrn'))
    memory.items = ReverseItems(memory.items)
    assert observed(scan('alphaa'), memory) == [record('alphaa', 'mrn')]


def test_missing_mapping_is_only_accessed_for_an_eligible_word():
    memory = core.PhiMemory()
    memory.items = None
    assert observed([], memory) == []
    assert observed(scan('abc', 'active'), memory) == []
    with pytest.raises(AttributeError):
        observed(scan('alphaa'), memory)


def test_controlled_ocr_scan_reverse_and_report_keep_accepted_and_zone_dropped(tmp_path, monkeypatch):
    """Inference is controlled; scan, primary matching, reverse, merge/report are real."""
    import json
    import numpy as np

    video = tmp_path / 'fixed.avi'
    writer = core.cv2.VideoWriter(str(video), core.cv2.VideoWriter_fourcc(*'FFV1'),
                                  6., (160, 96))
    assert writer.isOpened()
    frame = np.random.default_rng(1411).integers(0, 256, (96, 160, 3), dtype=np.uint8)
    for _ in range(12):
        writer.write(frame)
    writer.release()

    class ControlledOCR:
        calls = 0
        def read(self, image):
            # Four altered characters: reverse's76 passes, forward's82 fails.
            words = (['abcdef@sample.invalid', 'ghijkl@sample.invalid']
                     if self.calls == 0 else
                     ['zzzdef#sample.invalid', 'zzzikl#sample.invalid'])
            self.calls += 1
            return [(words[0], (8, 8, 70, 28), .99),
                    (words[1], (90, 8, 150, 28), .99),
                    ('active', (8, 40, 70, 60), .99)]

    ocr = ControlledOCR()
    monkeypatch.setattr(core, 'make_ocr', lambda *args, **kwargs: ocr)
    parser = core.build_parser()
    args = core._prep_args(parser.parse_args([
        str(video), '--categories', 'email', '--engine', 'tesseract',
        '--sample-interval', '0.3333333333333333', '--scroll-track', 'off',
        '--adaptive', 'off', '--ocr-upscale', 'off', '--no-vfr-fix',
        '--no-backtrack']), parser)
    args.zones_data = {'email': [(0., 0., .5, 1.)]}

    class Quiet(core.Callbacks):
        def log(self, message):
            pass

    state = core.run_scan(args, Quiet())
    assert ocr.calls == 6
    assert state['stats'] == dict(scans=6, raw_hits=7, regions=1, recalls=0,
                                  remembered=2, zone_dropped={'email': 7})
    accepted = dict(record('abcdef@sample.invalid', 'email', box=(8, 8, 70, 28)),
                    t_end=2.3, last_seen=5/3)
    dropped = dict(record('ghijkl@sample.invalid', 'email', box=(90, 8, 150, 28)),
                   t_end=2.3, last_seen=5/3)
    assert [asdict(d) for d in state['detections']] == [accepted]
    assert [asdict(d) for d in state['zdropped']] == [dropped]
    report = tmp_path / 'report.json'
    core.write_report(str(report), args, state)
    document = json.loads(report.read_text())
    assert document['detections'] == json.loads(json.dumps([
        dict(accepted, enabled=True), dict(dropped, enabled=False, zone_dropped=True)]))
    assert document['render_state'] == dict(fps=6., cum=[[0., 0.]] * 12,
                                           bands=[[0., 0.]] * 12)


@pytest.mark.parametrize('malformed,error', [
    ('count', TypeError), ('counts_mapping', AttributeError), ('threshold', TypeError)])
def test_malformed_gate_data_keeps_errors_before_length_rejection(malformed, error):
    memory = remembered(('a-much-longer-remembered-name', 'name'), ('alphaa', 'email'))
    if malformed == 'count':
        memory.counts['a-much-longer-remembered-name'] = None
    elif malformed == 'counts_mapping':
        memory.counts = None
    else:
        memory.name_sightings = None
    # Category rejection comes first, even for malformed name gate data.
    assert observed(scan('alphaa'), memory, {'email'}) == [record('alphaa', 'email')]
    with pytest.raises(error):
        observed(scan('alphaa'), memory, {'email', 'name'})


def test_defaultdict_counts_and_changed_sighting_threshold_keep_gate_meaning():
    from collections import defaultdict
    memory = remembered(('alphaaa', 'name'), ('alphaaa', 'name'), ('alpha', 'phone'))
    memory.counts = defaultdict(int, memory.counts)
    assert observed(scan('alphaa'), memory) == [record('alphaa', 'name')]
    memory.name_sightings = 3
    assert observed(scan('alphaa'), memory) == [record('alphaa', 'phone')]
    assert dict(memory.counts) == {'alphaaa': 2, 'alpha': 1}


def test_missing_gate_attributes_do_not_break_an_immediate_earlier_winner():
    memory = remembered(('alphaa', 'email'), ('a-much-longer-name', 'name'))
    del memory.counts
    del memory.name_sightings
    assert observed(scan('alphaa'), memory) == [record('alphaa', 'email')]
    with pytest.raises(AttributeError):
        observed(scan('nomatch'), memory)
