"""Post-run exact-report, operation and pinned-source verification."""
from pathlib import Path
import hashlib
import json
import subprocess
import sys

ROOT = Path('/home/tahv0/.codex/worktrees/c832/OpenScrub')
ART = Path('/tmp/openscrub-task652')
sys.path.insert(0, str(ROOT))
from benchmark import review_io as b

def equal_files(left, right):
    with Path(left).open('rb') as first, Path(right).open('rb') as second:
        while True:
            a, c = first.read(1024*1024), second.read(1024*1024)
            assert a == c, (str(left), str(right))
            if not a: return

def main():
    result = json.loads((ART/'measurement/results.json').read_text())
    assert result['exports_verified_after'] and result['before_noop_publications'] == 0
    assert result['warmups'] == 3 and result['samples'] == 5
    statuses = []
    for record in result['runs']:
        for label in ('before', 'after'):
            previous = record['files_before'][label]
            observations = [s for s in record['warmup']+record['recorded'] if s['version'] == label]
            assert len(observations) == 8
            for sample in observations:
                statuses.append(sample['status'])
                assert sample['after']['owners'] == 0
                current = sample['file_after']
                if record['operation'] == 'noop':
                    for field in ('bytes', 'inode', 'mtime_ns'): assert current[field] == previous[field]
                else: assert current['inode'] != previous['inode']
                previous = current
            if record['operation'] == 'noop': assert record['files_after'][label] == record['files_before'][label]
            counted = record['instrumented'][label]
            statuses.append(counted['status'])
            assert counted['after']['owners'] == 0
            counts = counted['after']['counts']
            changed = int(record['operation'] != 'noop')
            assert counts['report_parse'] == counts['request_json'] == counts['response_json'] == 1
            assert all(counts[k] == changed for k in ('report_encode', 'stage', 'fsync', 'replace'))
            assert counts['json_dump_calls'] == (changed if label == 'before' else 0)
            assert counts['encoder_instances'] == counts['stream_writelines'] == (changed if label == 'after' else 0)
            assert counts['stream_writes'] == (0 if label == 'after' or not changed else counts['stream_writes'])
        left = record['instrumented']['before']['after']['counts']
        right = record['instrumented']['after']['after']['counts']
        assert left['serialized_characters'] == right['serialized_characters']
        assert left['stream_writes'] == right['encoder_chunks']
    assert len(statuses) == 54 and set(statuses) == {200}
    expected_files = {}
    for rows in (100000,):
        doc = b.fixture(rows)
        expected = ART/('expected-final-%d.json' % rows)
        with expected.open('w', encoding='utf-8') as stream: json.dump(doc, stream, indent=1)
        expected_files[str(rows)] = dict(path=str(expected), bytes=expected.stat().st_size, sha256=b.sha_file(expected))
        for record in [r for r in result['runs'] if r['rows'] == rows]:
            for label in ('before', 'after'):
                assert record['files_after'][label]['sha256'] == b.sha_file(expected)
                equal_files(expected, record['workers'][label]['path'])
        for key, value in b.payload(rows, 'bulk', 1)['enabled'].items():
            doc['detections'][int(key)]['enabled'] = value
        counted_expected = ART/('expected-counted-bulk-%d.json' % rows)
        with counted_expected.open('w', encoding='utf-8') as stream: json.dump(doc, stream, indent=1)
        bulk = next(r for r in result['runs'] if r['rows'] == rows and r['operation'] == 'bulk')
        for label in ('before', 'after'): equal_files(counted_expected, bulk['instrumented'][label]['worker']['path'])
        del doc
    for source in result['sources'].values():
        for name, expected in source['sha256'].items(): assert b.sha_file(Path(source['export'])/name) == expected
    frozen = json.loads((ART/'verification-source.json').read_text())['files']
    head = subprocess.check_output(['git', '-C', str(ROOT), 'rev-parse', 'HEAD'], text=True).strip()
    for name, expected in frozen.items():
        assert b.sha_file(ROOT/name) == expected
        assert hashlib.sha256(subprocess.check_output(['git', '-C', str(ROOT), 'show', head+':'+name])).hexdigest() == expected
    assert not subprocess.check_output(['git', '-C', str(ROOT), 'status', '--porcelain'])
    subprocess.run(['git', '-C', str(ROOT), 'diff', '--check'], check=True)
    output = dict(base=result['sources']['before']['revision'], head=head,
                  expected_final_reports=expected_files, main_http200=54,
                  timed_http200=48, counted_http200=6,
                  every_noop_identity_and_mtime_retained=True,
                  every_changed_request_replaces_inode=True,
                  all_complete_final_reports_byte_equal=True,
                  all_pinned_exports_unchanged=True, frozen_committed_blobs=len(frozen), clean_head=True)
    (ART/'committed-evidence.json').write_text(json.dumps(output, indent=2))
    print(json.dumps(output, indent=2))

if __name__ == '__main__': main()
