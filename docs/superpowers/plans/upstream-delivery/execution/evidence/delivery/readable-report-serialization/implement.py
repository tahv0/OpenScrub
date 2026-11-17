from pathlib import Path
import subprocess
root=Path('/home/tahv0/.codex/worktrees/c832/OpenScrub')
p=root/'openscrub_internal/reports.py'
s=p.read_text().replace('            json.dump(report, stream, indent=1)', '''            # Consume the public encoder iterator in TextIOWrapper rather than
            # dispatching one Python stream.write call for every JSON token.
            # Tokens remain streamed; a single large string is still one token.
            stream.writelines(json.JSONEncoder(indent=1).iterencode(report))''')
p.write_text(s)
p=root/'benchmark/review_io.py'
p.write_bytes(subprocess.check_output(['git','-C',str(root),'show','ac6496810b03d8b062ab9da150aeea1e62285fed:benchmark/review_io.py']))
s=p.read_text()
a=s.index('    dump = reports.json.dump\n'); b=s.index("    wrap(reports.os, 'fsync'", a)
s=s[:a]+'''    dump = reports.json.dump
    encoder = reports.json.JSONEncoder
    def encode(doc, stream, **kwargs):
        counts['report_dump'] += 1
        return dump(doc, stream, **kwargs)
    def make_encoder(**kwargs):
        counts['report_dump'] += 1
        instance = encoder(**kwargs)
        original = instance.iterencode
        def chunks(doc):
            for value in original(doc):
                counts['encoder_chunks'] += 1
                yield value
        instance.iterencode = chunks
        return instance
    reports.json = SimpleNamespace(dump=encode, JSONEncoder=make_encoder)
    temporary_file = reports.tempfile.NamedTemporaryFile
    class Stream:
        def __init__(self, stream): self.stream = stream
        def __getattr__(self, name): return getattr(self.stream, name)
        def __enter__(self): self.stream.__enter__(); return self
        def __exit__(self, *args): return self.stream.__exit__(*args)
        def write(self, value):
            counts['stream_writes'] += 1
            counts['serialized_characters'] += len(value)
            return self.stream.write(value)
        def writelines(self, values):
            counts['stream_writelines'] += 1
            def measured():
                for value in values:
                    counts['serialized_characters'] += len(value)
                    yield value
            return self.stream.writelines(measured())
    def stage(*args, **kwargs):
        counts['stage'] += 1
        return Stream(temporary_file(*args, **kwargs))
    reports.tempfile.NamedTemporaryFile = stage
'''+s[b:]
s=s.replace('stream_writes=0, serialized_characters=0, request_json=0, response_json=0)', 'stream_writes=0, stream_writelines=0, encoder_chunks=0,\n                  serialized_characters=0, request_json=0, response_json=0)')
p.write_text(s)
p=root/'tests/test_large_report_io.py'; s=p.read_text()
s=s.replace('load, dump = web._load_job_report, json.dump','load, encoder = web._load_job_report, json.JSONEncoder')
a=s.index('    def encode(doc, stream, **kwargs):\n',s.index('def report_work(')); b=s.index("    for owner, name, key in",a)
s=s[:a]+'''    def encode(**kwargs):
        counts['dump'] += 1
        instance = encoder(**kwargs)
        original = instance.iterencode
        def chunks(doc):
            for value in original(doc):
                counts['stream_writes'] += 1  # Encoder pieces, not OS syscalls.
                yield value
        instance.iterencode = chunks
        return instance
    monkeypatch.setattr(web, '_load_job_report', parse)
    monkeypatch.setattr(reports, 'json', SimpleNamespace(JSONEncoder=encode))
'''+s[b:]
# Preserve old fixture key for existing expectations, but give it honest meaning.
s=s.replace('"""Count report operations only, leaving request/response JSON untouched."""','"""Count report operations; legacy stream_writes key counts encoder chunks."""')
s=s.replace("assert report_work['stream_writes'] > 0  # Python writes, not syscalls.","assert report_work['stream_writes'] > 0  # Encoder chunks, not Python writes or syscalls.")
p.write_text(s)
p=root/'tests/test_report_transactions.py';s=p.read_text().replace("target, name = reports.json, 'dump'","target, name = reports.json, 'JSONEncoder'"); p.write_text(s)
p=root/'benchmark/README.md'; s=p.read_text(); s+='''

For a baseline that already skips unchanged publication (for example `3457efa`),
pass `--before-noop-publications 0`. The historical default remains 1.
Separate counted workers report `report_dump` as publication encoding starts,
`stream_writes` as Python calls to the staging stream's `write`, and
`stream_writelines` as calls to `writelines`. `encoder_chunks` counts pieces
from the explicit public encoder iterator when used. TextIOWrapper's internal
writes are not Python stream calls or measured OS syscalls. No counted latency
is part of the uninstrumented HTTP comparison.
'''; p.write_text(s)
