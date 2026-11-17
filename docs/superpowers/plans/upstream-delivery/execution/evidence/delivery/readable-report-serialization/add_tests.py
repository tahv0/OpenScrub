from pathlib import Path
root=Path('/home/tahv0/.codex/worktrees/c832/OpenScrub')
(root/'tests/test_report_serialization.py').write_text('''"""Readable bytes, streaming dispatch and atomic failure contracts."""
import json
import os

import pytest

from openscrub_internal import reports


def test_encoder_stream_uses_bulk_iterator_consumption(tmp_path, monkeypatch):
    # The optimization must avoid one Python write dispatch per encoder token.
    original = reports.tempfile.NamedTemporaryFile
    calls = []
    class Stream:
        def __init__(self, stream): self.stream = stream
        def __getattr__(self, key): return getattr(self.stream, key)
        def __enter__(self): self.stream.__enter__(); return self
        def __exit__(self, *args): return self.stream.__exit__(*args)
        def write(self, value):
            pytest.fail('per-token Python write dispatch')
        def writelines(self, values):
            calls.append('writelines')
            return self.stream.writelines(values)
    monkeypatch.setattr(reports.tempfile, 'NamedTemporaryFile',
                        lambda **kwargs: Stream(original(**kwargs)))
    path = tmp_path / 'report.json'
    reports.atomic_report(path, {'rows': [{'nested': [1, True, None]}] * 200})
    assert calls == ['writelines']
    assert json.loads(path.read_bytes()) == {'rows': [{'nested': [1, True, None]}] * 200}


def test_exact_readable_bytes_for_additive_scalars_keys_and_unicode(tmp_path):
    doc = {'future': {'ordered': [False, 0, 0.0, -0.0, None, True],
                      'escaped': 'snow☃ é 😀 \\"\\\\\\n\\t'},
           'keys': {2: 'int', None: 'null', False: 'bool', 1.5: 'float'},
           'nonfinite': [float('nan'), float('inf'), -float('inf')]}
    expected = (b'{\\n "future": {\\n  "ordered": [\\n   false,\\n   0,\\n   0.0,\\n   -0.0,\\n   null,\\n   true\\n  ],'
                b'\\n  "escaped": "snow\\\\u2603 \\\\u00e9 \\\\ud83d\\\\ude00 \\\\"\\\\\\\\\\\\n\\\\t"\\n },'
                b'\\n "keys": {\\n  "2": "int",\\n  "null": "null",\\n  "false": "bool",\\n  "1.5": "float"\\n },'
                b'\\n "nonfinite": [\\n  NaN,\\n  Infinity,\\n  -Infinity\\n ]\\n}')
    path = tmp_path / 'report.json'
    reports.atomic_report(path, doc)
    assert path.read_bytes() == expected
    assert path.read_bytes() == json.dumps(doc, indent=1).encode('utf-8')
    assert not path.read_bytes().endswith(b'\\n')


def test_large_individual_token_keeps_default_escaping(tmp_path):
    # No target chunk size can cap a token: iterencode yields this string whole.
    value = '☃\\n"\\\\' * 100000
    doc = {'unknown': {'large': value, 'tail': [1, 1.0, False]}}
    path = tmp_path / 'report.json'
    reports.atomic_report(path, doc)
    assert path.read_bytes() == json.dumps(doc, indent=1).encode('utf-8')
    assert json.loads(path.read_bytes()) == doc


@pytest.mark.parametrize('kind, error', [('object', TypeError), ('key', TypeError),
                                        ('circular', ValueError)])
@pytest.mark.parametrize('exists', [False, True])
def test_encoder_errors_leave_previous_report_and_clean_stage(tmp_path, kind, error, exists):
    path = tmp_path / 'report.json'
    if exists: path.write_bytes(b'old complete report')
    if kind == 'object': doc = {'partial': [1, 2], 'invalid': object()}
    elif kind == 'key': doc = {'partial': [1, 2], (1, 2): 'invalid key'}
    else:
        doc = {'partial': [1, 2]}; doc['cycle'] = doc
    with pytest.raises(error): reports.atomic_report(path, doc)
    assert list(tmp_path.iterdir()) == ([path] if exists else [])
    if exists: assert path.read_bytes() == b'old complete report'


@pytest.mark.parametrize('failure', ['encoding', 'flush', 'fsync', 'replace'])
@pytest.mark.parametrize('exists', [False, True])
def test_stream_and_durability_failures_propagate_without_publication(tmp_path, monkeypatch, failure, exists):
    path = tmp_path / 'report.json'
    if exists: path.write_bytes(b'old complete report')
    original = reports.tempfile.NamedTemporaryFile
    error = UnicodeEncodeError('utf-8', 'x', 0, 1, 'injected encoding failure') if failure == 'encoding' else OSError('injected ' + failure)
    def fail(*args, **kwargs): raise error
    if failure in ('fsync', 'replace'):
        monkeypatch.setattr(reports.os, failure, fail)
    else:
        class Stream:
            def __init__(self, stream): self.stream = stream
            def __getattr__(self, key): return getattr(self.stream, key)
            def __enter__(self): self.stream.__enter__(); return self
            def __exit__(self, *args): return self.stream.__exit__(*args)
            def write(self, value):
                if failure == 'encoding': fail()
                return self.stream.write(value)
            def writelines(self, values):
                if failure == 'encoding':
                    iterator = iter(values)
                    self.stream.write(next(iterator))
                    fail()
                return self.stream.writelines(values)
            def flush(self): fail()
        monkeypatch.setattr(reports.tempfile, 'NamedTemporaryFile', lambda **kwargs: Stream(original(**kwargs)))
    with pytest.raises(type(error)) as raised:
        reports.atomic_report(path, {'complete': [1, 2, 3]})
    assert raised.value is error
    assert list(tmp_path.iterdir()) == ([path] if exists else [])
    if exists: assert path.read_bytes() == b'old complete report'
''')
