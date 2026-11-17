from pathlib import Path
import sys,json,inspect
root=Path('/home/tahv0/.codex/worktrees/c832/OpenScrub');sys.path.insert(0,str(root))
from benchmark import review_io as b
art=Path('/tmp/openscrub-task632/count-smoke');art.mkdir(exist_ok=False)
sources={label:b.export_source(root,ref,art/('export-'+label)) for label,ref in [('before','3457efac574d74a7d2377cbc0d44bb0b87462c3a'),('after','4a62e49d2f0896b737081cc92e1f92e9bcaee93f')]}
assert inspect.signature(b.count_operations).parameters['before_noop_publications'].default==1
result=b.count_operations(sources,6,art,before_noop_publications=0)
for scenario,versions in result.items():
    for label,sample in versions.items():
        c=sample['after']['counts'];expected=int(scenario!='noop')
        assert c['json_dump_calls']==(expected if label=='before' else 0)
        assert c['encoder_instances']==(expected if label=='after' else 0)
        assert c['stream_writelines']==(expected if label=='after' else 0)
        assert (c['stream_writes']>0)==(bool(expected) and label=='before')
        assert (c['encoder_chunks']>0)==(bool(expected) and label=='after')
        print(scenario,label,c)
for label in sources:
    assert b.sha_file(Path(result['bulk'][label]['worker']['path']))==b.expected_hash(6,'bulk',1)
for source in sources.values():
    for name,expected in source['sha256'].items():assert b.sha_file(Path(source['export'])/name)==expected
(art/'results.json').write_text(json.dumps(dict(sources=sources,counts=result,exports_verified_after=True),indent=2))
