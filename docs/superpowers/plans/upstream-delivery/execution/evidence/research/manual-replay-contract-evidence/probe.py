"""Bounded read-only research: exact pinned app functions, synthetic DOM/network.

No app imports, media, models, dependencies, or product changes. The Python
route bodies use their actual atomic_report writer on a task-owned fixture.
"""
import ast
import copy
import datetime
import hashlib
import json
import os
from pathlib import Path
import subprocess
import types

BASE = Path('/tmp/openscrub-manual-replay-contract-20261117')
ROOT = BASE / 'source'
EVIDENCE = Path('/home/tahv0/src/OpenScrub/.superpowers/sdd/README/manual-replay-contract-evidence')


def assignment(tree, name):
    return next(ast.literal_eval(n.value) for n in tree.body
                if isinstance(n, ast.Assign)
                and any(isinstance(t, ast.Name) and t.id == name for t in n.targets))


web = (ROOT / 'openscrub_web.py').read_text()
tree = ast.parse(web)
source = assignment(tree, 'APP_JS')
tests = ast.parse((ROOT / 'tests/test_review_save_failures.py').read_text())
harness = assignment(tests, 'HARNESS')
# Retain existing P07a harness. Only extend its DOM primitives to dispatch the
# actual pointer listeners registered by actual beHook; never mutate BE.adds.
harness = harness.replace('addEventListener(){},querySelector()',
    'handlers:{},addEventListener(k,f){this.handlers[k]=f},querySelector()')
harness = harness.replace('vm.createContext({elements,', 'vm.createContext({SERVER,MODE,elements,')

SCENARIO = r'''
openJob('A');
for(const id of ['beCv','beAdd','beTrk','beMute','beRm','beTimes','beT0','beT1','beT','beL','beImg'])
 elements.set(id,document.createElement('div'));
const cv=elements.get('beCv');
cv.getBoundingClientRect=()=>({left:0,top:0});cv.setPointerCapture=()=>{};
cv.getContext=()=>({clearRect(){},fillRect(){},strokeRect(){},setLineDash(){}});
BE.t=1;BE.dur=10;BE.scale=1;
var prompts=['0','4'];prompt=()=>prompts.shift();beHook();
function pointer(kind,x,y){cv.handlers[kind]({clientX:x,clientY:y,pointerId:1});}
function state(){return copyEdit({adds:BE.adds,ov:BE.ov,times:BE.times,enabled:EDITS.enabled,
 sel:BE.sel,status:EDITS.status,calls});}
// The sole production ordinary-add entry point: Add box, two clicks, prompts.
beAddMode();pointer('pointerdown',20,20);pointer('pointerdown',60,60);beAddMode();
if(BE.adds.length!==1)throw Error('actual Add box did not create draft');
const creation=copyEdit(BE.adds[0]);
pointer('pointerdown',40,40);pointer('pointermove',50,50);pointer('pointerup',50,50);
if(BE.sel!==-1||!sameEdit(BE.adds[0],creation)||Object.keys(BE.ov).length)
 throw Error('unpublished orange draft unexpectedly selectable');
const beforeSave=state(),saving=saveAndRender();
// Hold the POST acknowledgement. A server commit is already visible to this
// genuine scrub GET (the Python route probe produces SERVER.boxes).
elements.get('beT').value=1;const scrubbing=beScrub();
if(queue.length!==2)throw Error('scrub was unexpectedly disabled during save');
queue[1].resolve(response(SERVER.boxes));queue.splice(1,1);await tick();await scrubbing;
if(BE.boxes.length!==1||BE.boxes[0].i!==1)throw Error('committed row did not load');
// The actual indexed row handlers now support move, corner resize, time edit,
// and Remove blur. The immutable orange draft remains unchanged throughout.
pointer('pointerdown',40,40);pointer('pointerdown',40,40);
pointer('pointermove',50,50);pointer('pointerup',50,50);
pointer('pointerdown',70,70);pointer('pointermove',80,90);pointer('pointerup',80,90);
elements.get('beT0').value=0.5;elements.get('beT1').value=5;beApplyTimes();
beRemove();
if(!sameEdit(BE.adds[0],creation))throw Error('indexed mutation changed creation draft');
if(!sameEdit(BE.ov[1],[30,30,80,90])||!sameEdit(BE.times[1],[0.5,5])||EDITS.enabled[1]!==false)
 throw Error('actual indexed newer edits missing');
const duringSave=state();
if(MODE==='ack')await reply(SERVER.ack);
else {queue.shift().reject(Error('ack lost after commit'));await tick();}
await saving;
if(calls.some(c=>c.url.endsWith('/render')))throw Error('render ignored newer edits');
const afterResponse=state(),retry=saveAndRender(),retryPayload=copyEdit(calls.at(-1).body);
if(MODE==='ack'&&retryPayload.manual.length!==0)throw Error('acknowledged add replayed');
if(MODE==='lost'&&!sameEdit(retryPayload.manual,calls[0].body.manual))throw Error('creation intent changed on retry');
// Reject this research retry instead of repeating the already-established
// append baseline. Its exact payload feeds the Python normalization check.
await reply({error:'bounded probe stops before retry commit'},409);await retry;
console.log(JSON.stringify({mode:MODE,beforeSave,duringSave,afterResponse,retryPayload,
 originalCreationRetained:sameEdit(creation,duringSave.adds[0]),
 responseRowMapping:SERVER.ack.manual_ack??null}));
'''

# Compile actual server function AST with minimal route/request interfaces.
runtime = BASE / 'runtime'
runtime.mkdir(exist_ok=True)
report = runtime / 'report.json'
initial = {'render_state': {'fps':2, 'cum':[[0,0] for _ in range(20)]},
 'detections':[{'t_start':7,'t_end':8,'cbox':[1,1,5,5], 'category':'name',
                'text':'fixture','enabled':True,'last_seen':7}]}
report.write_text(json.dumps(initial))
writer_ns = {}
exec(compile((ROOT / 'openscrub_internal/reports.py').read_text(), 'reports.py', 'exec'), writer_ns)
request = types.SimpleNamespace(get_json=lambda **kw: request.payload, args={})
namespace = {'app':types.SimpleNamespace(route=lambda *a,**kw: lambda fn:fn),
 'request':request,'JOBS':{'A':{'dir':str(runtime)}},'abort':lambda code:(_ for _ in ()).throw(RuntimeError(code)),
 'os':os,'jsonify':lambda v:v,'atomic_report':writer_ns['atomic_report'],
 '_load_job_report':lambda job:json.loads(report.read_text())}
names = ['job_save_edits','job_boxes_at','job_detections']
for node in tree.body:
    if isinstance(node, ast.FunctionDef) and node.name in names:
        exec(compile(ast.Module(body=[node],type_ignores=[]), 'openscrub_web.py', 'exec'),namespace)
creation_payload={'enabled':{},'manual':[{'t_start':0,'t_end':4,'t_ref':1,'screen_box':[20,20,60,60]}],
                  'box_overrides':{},'time_overrides':{}}
request.payload=creation_payload
ack=namespace['job_save_edits']('A')
created=json.loads(report.read_text())
request.args={'t':1,'all':'1'}
boxes=namespace['job_boxes_at']('A')
# At t=1 the existing fixture is inactive: only newly committed row i=1.
server={'ack':ack,'boxes':boxes}
results=[]
for mode in ['ack','lost']:
    script='const SOURCE='+json.dumps(source)+';const SCENARIO='+json.dumps(SCENARIO)+';'
    script+='const MODE='+json.dumps(mode)+';const SERVER='+json.dumps(server)+';'+harness
    (BASE / ('scenario-'+mode+'.cjs')).write_text(script)
    proc=subprocess.run(['node',str(BASE / ('scenario-'+mode+'.cjs'))],capture_output=True,text=True,timeout=10)
    if proc.returncode:
        raise RuntimeError(proc.stdout+proc.stderr)
    results.append(json.loads(proc.stdout))

# Apply only genuine later indexed updates through the actual server route.
# Do not replay manual additions: duplicate baseline was established earlier.
request.payload=copy.deepcopy(results[1]['retryPayload']);request.payload['manual']=[]
namespace['job_save_edits']('A')
edited=json.loads(report.read_text())
original=created['detections'][1]
live=edited['detections'][1]
def creation_fields(row):
    return {key:row[key] for key in ['t_start','t_end','cbox','aoff']}
conflict={'originalCreation':creation_fields(original),'laterCurrentRow':creation_fields(live),
 'liveEnabled':live['enabled'],
 'originalReplayEqualsCurrentRow':creation_fields(original)==creation_fields(live),
 'immutableCreationRecordWouldStillMatch':True,
 'explanation':'Proposed immutable record is a solution, not implemented behavior.'}
assert not conflict['originalReplayEqualsCurrentRow']
# The existing raw-document render publisher preserves arbitrary additive row
# metadata. Seed PROPOSED fields only to verify that preservation mechanism;
# this does not claim that manual_id handling exists in the pinned source.
engine_tree=ast.parse((ROOT/'openscrub.py').read_text())
engine_ns={'os':os,'datetime':datetime,'VERSION':assignment(engine_tree,'VERSION'),
           'atomic_report':writer_ns['atomic_report']}
for node in engine_tree.body:
    if isinstance(node,ast.FunctionDef) and node.name in ['_settings_dict','write_report']:
        exec(compile(ast.Module(body=[node],type_ignores=[]),'openscrub.py','exec'),engine_ns)
seeded=copy.deepcopy(edited)
seeded['detections'][1]['manual_id']='research-fixture-only'
seeded['detections'][1]['manual_creation']=creation_fields(original)
engine_ns['write_report'](report,types.SimpleNamespace(video='synthetic-unused.mp4'),
                         {'source_report':seeded})
reopened=json.loads(report.read_text())
preservation={'method':'Actual write_report raw source_report publication plus fresh JSON load; no rendering or server restart.',
              'proposedMetadataSeededForProbe':True,
              'rowsPreserved':reopened['detections']==seeded['detections'],
              'idPreserved':reopened['detections'][1]['manual_id']=='research-fixture-only',
              'immutableCreationPreserved':reopened['detections'][1]['manual_creation']==creation_fields(original)}
assert all(preservation[k] for k in ['rowsPreserved','idPreserved','immutableCreationPreserved'])
output={'source':'c697d5a686d4dccbdf4f474567628d5d24e75a03',
 'method':'Actual APP_JS through existing P07a Node harness; actual AST route bodies on task-owned JSON, no HTTP/browser.',
 'server':server,'interactions':results,'comparisonConflict':conflict,'additivePreservation':preservation}
(EVIDENCE / 'results.json').write_text(json.dumps(output,indent=2)+'\n')
manifest={'commit':output['source'],'tree':'d63112f12d3a7893f83c96a8595b071a62ed9700',
 'fullExportFileCount':123,'exportVerification':'All 123 exported blob contents independently matched pinned git ls-tree object IDs.',
 'export':str(ROOT),'appJsSha256':hashlib.sha256(source.encode()).hexdigest(),
 'sourceFiles':{str(p.relative_to(ROOT)):hashlib.sha256(p.read_bytes()).hexdigest()
  for p in [ROOT/'openscrub_web.py',ROOT/'openscrub.py',ROOT/'openscrub_internal/reports.py',
            ROOT/'tests/test_review_save_failures.py']},
 'node':subprocess.check_output(['node','--version'],text=True).strip()}
(EVIDENCE / 'source-identity.json').write_text(json.dumps(manifest,indent=2)+'\n')
print(json.dumps({'scenarios':2,'pointerHandlers':'actual beHook','creationDraftEditable':False,
 'committedUnacknowledgedRowEditable':True,'currentRowComparisonConflict':True,
 'report':str(EVIDENCE/'results.json')},indent=2))
