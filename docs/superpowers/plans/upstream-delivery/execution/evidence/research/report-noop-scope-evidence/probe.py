"""Small deterministic work-count probe; no latency measurement or product edits."""
import copy
import hashlib
import json
import os
from pathlib import Path
import platform
import subprocess
import sys

ROOT = Path('/tmp/openscrub-report-noop-20261117')
SOURCE = ROOT / 'export'
OUT = Path('/home/tahv0/src/OpenScrub/.superpowers/sdd/README/report-noop-scope-evidence')
PIN = 'f2cdf4813c86296644911f3f0b09bfc56d3e03c5'
sys.path.insert(0, str(SOURCE))
os.environ['OPENSCRUB_NO_AUTOFETCH'] = '1'
import openscrub as engine
def blocked(*a, **kw):
    raise RuntimeError('Research policy: model downloads prohibited')
engine._fetch_model = blocked
engine._model_dir = lambda: os.environ['OPENSCRUB_BASELINE_MODEL_DIR']
import openscrub_web as web
from openscrub_internal import reports

DATA = ROOT / 'data'
DATA.mkdir(exist_ok=True)
web._data_root = lambda: str(DATA)
for name in ('JOBS_DIR', 'ZONES_PATH', 'MODEL_SELECT_PATH', 'CERT_DIR',
             'WEB_SETTINGS_PATH', 'CUSTOM_CATS_PATH'):
    setattr(web, name, str(DATA / Path(getattr(web, name)).name))
web.TOKEN = None
web.JOBS = {}
web.VAULT = {'key': None}
web.app.config.update(TESTING=False, PROPAGATE_EXCEPTIONS=False)
web.app.logger.disabled = True  # Expected invalid-input 500s are recorded in results.
job = web.new_job('', {}, 'synthetic.avi')
job.update(phase='review', created=0)
path = Path(job['dir']) / 'report.json'
url = '/api/jobs/' + job['id'] + '/detections'

row = dict(t_start=0.0, t_end=1.0, cbox=[1.,2.,8.,9.], category='name',
           text='synthetic-recurring', confidence=.9, aoff=[0,0],
           last_seen=.5, enabled=False,
           extra={'bool': True, 'number': 1, 'nested': [None, {'label': '雪'}]})
BASE = dict(provenance={'input': 'synthetic.avi', 'settings': {}},
            render_state={'fps': 30, 'cum': [[0,0]] * 6,
                          'bands': [[0,0]] * 6, 'future': {'v': 1}},
            detections=[row, copy.deepcopy(row)],
            audio_redactions=[{'t0': .2, 't1': .4, 'mode': 'mute'}],
            audio_suggestions=[{'t0': .1, 't1': .3, 'future': [1, True]}],
            audio_transcript=[{'start': 0, 'end': 1, 'text': 'synthetic'}],
            unknown={'bool': True, 'number': 1, 'nested': [None, {'label': '雪'}]})

def same(a, b):
    if type(a) is not type(b):
        return False
    if isinstance(a, dict):
        return a.keys() == b.keys() and all(same(a[k], b[k]) for k in a)
    if isinstance(a, list):
        return len(a) == len(b) and all(same(x,y) for x,y in zip(a,b))
    return a == b

def differences(a, b, at='$'):
    if isinstance(a, dict) and isinstance(b, dict):
        return [x for k in a.keys() | b.keys()
                for x in ([at+'.'+k+': key inserted/removed'] if k not in a or k not in b
                          else differences(a[k], b[k], at+'.'+k))]
    if isinstance(a, list) and isinstance(b, list) and len(a) == len(b):
        return [x for i,(left,right) in enumerate(zip(a,b))
                for x in differences(left,right,at+'[%d]' % i)]
    return [] if same(a,b) else [{'path': at, 'before': a, 'after': b,
                                 'before_type': type(a).__name__, 'after_type': type(b).__name__}]

def snapshot():
    if not path.exists():
        return None
    data = path.read_bytes()
    stat = path.stat()
    return dict(bytes=len(data), sha256=hashlib.sha256(data).hexdigest(),
                dev=stat.st_dev, inode=stat.st_ino, mtime_ns=stat.st_mtime_ns,
                ctime_ns=stat.st_ctime_ns, mode=oct(stat.st_mode & 0o777))

class Delegate:
    def __init__(self, target): self.target = target
    def __getattr__(self, key): return getattr(self.target, key)

counts = None
class WebJSON(Delegate):
    def load(self, stream, *a, **kw):
        if Path(stream.name) == path: counts['report_parse_attempts'] += 1
        doc = self.target.load(stream, *a, **kw)
        if Path(stream.name) == path: counts['report_parse_successes'] += 1
        return doc

class ReportJSON(Delegate):
    def dump(self, doc, stream, *a, **kw):
        counts['report_serializations'] += 1
        class Sink:
            def write(self, text):
                counts['stream_write_calls'] += 1
                counts['output_characters'] += len(text)
                return stream.write(text)
        return self.target.dump(doc, Sink(), *a, **kw)

class ReportOS(Delegate):
    def fsync(self, fd):
        counts['fsync_calls'] += 1
        return self.target.fsync(fd)
    def replace(self, src, dst):
        counts['replace_attempts'] += 1
        result = self.target.replace(src, dst)
        counts['replace_successes'] += 1
        return result

class ReportTempfile(Delegate):
    def NamedTemporaryFile(self, *a, **kw):
        result = self.target.NamedTemporaryFile(*a, **kw)
        counts['staging_file_creations'] += 1
        return result

real_atomic = web.atomic_report
def atomic(*a, **kw):
    counts['publication_attempts'] += 1
    result = real_atomic(*a, **kw)
    counts['publication_successes'] += 1
    return result
web.json = WebJSON(json)
reports.json = ReportJSON(json)
reports.os = ReportOS(os)
reports.tempfile = ReportTempfile(reports.tempfile)
web.atomic_report = atomic
real_loads = web.app.json.loads
real_dumps = web.app.json.dumps
def request_loads(*a, **kw):
    counts['http_json_parses'] += 1
    return real_loads(*a, **kw)
def response_dumps(*a, **kw):
    counts['http_json_serializations'] += 1
    return real_dumps(*a, **kw)
web.app.json.loads = request_loads
web.app.json.dumps = response_dumps

CASES = []
def add(name, payload, mutate=None, compact=False, phase='review', raw=None):
    doc = copy.deepcopy(BASE)
    if mutate: mutate(doc)
    CASES.append((name,payload,doc,compact,phase,raw))
add('empty-noncanonical', {}, compact=True)
add('empty-canonical', {})
add('same-enabled', {'enabled': {'0': False}})
add('same-box', {'box_overrides': {'0': [1,2,8,9]}})
add('same-time', {'time_overrides': {'0': [0,1]}})
add('same-audio', {'audio': BASE['audio_redactions']})
add('sparse-change-unknown-preserved', {'enabled': {'0': True}})
add('audio-omitted', {'enabled': {}})
add('audio-explicit-empty-clears', {'audio': []})
add('audio-explicit-empty-already-empty', {'audio': []}, lambda d:d.update(audio_redactions=[]))
add('audio-omitted-absent', {}, lambda d:d.pop('audio_redactions'))
add('audio-explicit-empty-absent', {'audio': []}, lambda d:d.pop('audio_redactions'))
add('audio-null-clears', {'audio': None})
add('enabled-absent-omitted', {}, lambda d:d['detections'][0].pop('enabled'))
add('enabled-absent-explicit-default', {'enabled': {'0': True}}, lambda d:d['detections'][0].pop('enabled'))
add('enabled-equal-number-bool', {'enabled': {'0': True}}, lambda d:d['detections'][0].update(enabled=1))
add('enabled-string-false-truthy', {'enabled': {'0': 'false'}})
add('box-equal-int-float', {'box_overrides': {'0': [1,2,8,9]}}, lambda d:d['detections'][0].update(cbox=[1,2,8,9]))
add('time-equal-int-float', {'time_overrides': {'0': [0,1]}}, lambda d:d['detections'][0].update(t_start=0,t_end=1,last_seen=0))
add('same-time-clamps-last-seen', {'time_overrides': {'0': [0,1]}}, lambda d:d['detections'][0].update(last_seen=2.0))
add('same-time-adds-last-seen', {'time_overrides': {'0': [0,1]}}, lambda d:d['detections'][0].pop('last_seen'))
add('audio-equal-number-bool', {'audio': [{'t0': 0, 't1': 1, 'mode': 'mute'}]}, lambda d:d.update(audio_redactions=[{'t0': False, 't1': True, 'mode': 'mute'}]))
add('audio-explicit-drops-unknown', {'audio': BASE['audio_redactions']}, lambda d:d['audio_redactions'][0].update(future={'keep': True}))
add('ignored-indices-and-invalid-ranges', {'enabled': {'-1': True,'999':True,'bogus':True}, 'box_overrides': {'-1': None,'999':None,'0':[1,2,3]}, 'time_overrides': {'999':None,'0':[1,0]}})
add('malformed-box-index-errors', {'box_overrides': {'bogus': [1,2,8,9]}})
add('malformed-enabled-null-errors', {'enabled': None})
add('manual-legacy-appends', {'manual': [{'t_start': 0,'t_end':1,'screen_box':[1,2,8,9]}]})
add('queued-empty-refused', {}, phase='queued')
add('malformed-request-json', None, raw=b'{')
add('malformed-report-json', {}, raw='REPORT_INVALID')
add('missing-report', {}, raw='REPORT_MISSING')

results=[]
for name,payload,doc,compact,phase,raw in CASES:
    job['phase'] = phase
    original = json.dumps(doc, separators=(',',':')) if compact else json.dumps(doc, indent=1)
    path.write_text(original, encoding='utf-8')
    path.chmod(0o640)
    os.utime(path, ns=(1700000000000000000,1700000000000000000))
    if raw == 'REPORT_INVALID': path.write_bytes(b'{')
    if raw == 'REPORT_MISSING': path.unlink()
    before = snapshot()
    before_public = copy.deepcopy(web.job_public(job))
    before_activity = web.LAST_ACTIVITY['t']
    counts = {key: 0 for key in ('http_json_parses','http_json_serializations',
        'report_parse_attempts','report_parse_successes','publication_attempts',
        'publication_successes','report_serializations','staging_file_creations',
        'stream_write_calls','output_characters','fsync_calls','replace_attempts','replace_successes')}
    body = raw if isinstance(raw, bytes) else json.dumps(payload).encode()
    with web.app.test_client() as client:
        response = client.post(url, data=body, content_type='application/json')
        response_body = response.get_data()
        status = response.status_code
        cache = response.headers.get('Cache-Control')
        response.close()
    observed_counts = copy.deepcopy(counts)
    after = snapshot()
    after_doc = json.loads(path.read_bytes()) if after and raw != 'REPORT_INVALID' else None
    results.append(dict(case=name,payload=payload,status=status,
        response=json.loads(response_body) if response.mimetype == 'application/json' else None,
        response_mimetype=response.mimetype,cache_control=cache,before=before,after=after,
        bytes_equal=before and after and before['sha256']==after['sha256'],
        same_file_identity=before and after and (before['dev'],before['inode'])==(after['dev'],after['inode']),
        counts=observed_counts,public_job_unchanged=same(before_public,web.job_public(job)),
        activity_touched=web.LAST_ACTIVITY['t'] >= before_activity,
        outstanding_file_owners=web.FILES.count,
        unknown_top_and_rows_preserved=after_doc is not None and same(doc['unknown'],after_doc['unknown']) and
            all(same(d['extra'],a['extra']) for d,a in zip(doc['detections'],after_doc['detections'])),
        type_sensitive_differences=differences(doc,after_doc) if after_doc is not None else None,
        staging_files_remaining=[p.name for p in path.parent.glob('.report-*.tmp')]))

tracked = subprocess.check_output(['git','ls-tree','-r','--name-only',PIN], cwd='/home/tahv0/src/OpenScrub',text=True).splitlines()
tree_hash = hashlib.sha256()
for rel in tracked:
    data = (SOURCE/rel).read_bytes()
    expected = subprocess.check_output(['git','show',PIN+':'+rel],cwd='/home/tahv0/src/OpenScrub')
    assert data == expected, rel
    tree_hash.update(rel.encode()+b'\0'+hashlib.sha256(data).digest())
imports = {module.__name__: str(Path(module.__file__).resolve()) for module in (engine,web,reports)}
assert all(p.startswith(str(SOURCE)+'/') for p in imports.values())
for result in results:
    assert result['outstanding_file_owners'] == 0
    assert result['public_job_unchanged']
    assert result['staging_files_remaining'] == []
    c = result['counts']
    if result['status']==200:
        assert c['report_parse_successes']==c['publication_successes']==c['report_serializations']==c['fsync_calls']==c['replace_successes']==1
        assert result['same_file_identity'] is False
        assert result['unknown_top_and_rows_preserved']
    else:
        assert c['publication_attempts']==0
        assert result['before']==result['after']
output=dict(pin=PIN,source=str(SOURCE),imports=imports,tracked_files_verified=len(tracked),
            tracked_path_and_sha256_manifest_sha256=tree_hash.hexdigest(),
            source_files_sha256={rel:hashlib.sha256((SOURCE/rel).read_bytes()).hexdigest() for rel in ('openscrub.py','openscrub_web.py','openscrub_internal/reports.py','openscrub_internal/lifetimes.py')},
            python=sys.version,platform=platform.platform(),transport='Flask test client; full registered routes and hooks; no socket timing',
            results=results)
OUT.mkdir(exist_ok=True)
(OUT/'results.json').write_text(json.dumps(output,indent=2,ensure_ascii=False)+'\n')
print(json.dumps({'cases':len(results),'statuses':{str(status):sum(r['status']==status for r in results) for status in sorted({r['status'] for r in results})},'tracked_files_verified':len(tracked),'imports':imports},indent=2))
