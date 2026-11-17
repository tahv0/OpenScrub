"""Rebuild bounded numbered excerpts and symbol comparisons from collected source."""
import ast, hashlib, json, pathlib
root=pathlib.Path('/home/tahv0/src/OpenScrub/.superpowers/sdd/README')
src=root/'runtime/optional-policy-research'
out=root/'optional-policy-contract-evidence'
ranges={
'combined/openscrub.py':[(102,119),(734,753),(1343,1390),(1392,1443),(1536,1569),(1602,1624),(2447,2472),(2506,2569),(2614,2654),(2709,2729),(2935,2944),(2985,3034),(3036,3075),(3860,3892),(4022,4032),(4061,4081),(4226,4237),(4272,4303),(5079,5095),(5118,5161),(5162,5194),(5252,5258),(6118,6128),(6371,6404),(6424,6450),(6860,6865),(7307,7333),(7761,7787),(8362,8402),(8425,8456),(8504,8514),(8554,8580),(8596,8646)],
'combined/openscrub_web.py':[(498,517),(672,691),(811,824),(1620,1640),(1663,1689),(1821,1865),(1890,1921),(1991,2038),(3290,3310),(3454,3468),(3624,3628),(3681,3689),(3717,3742),(3783,3810),(3868,3868),(3902,3940),(3948,3973),(4148,4155),(4870,4888)],
'combined/openscrub_internal/reports.py':[(1,50)],
'combined/pyproject.toml':[(79,113)],
'combined/openscrub_gui.py':[(406,430)],
'combined/zones_ui.py':[(176,180),(1170,1188)],
'donor/openscrub_web.py':[(2437,2470),(7038,7068)]}
for key,spans in ranges.items():
    lines=(src/key).read_text().splitlines()
    text=[f'# {key} (line numbers are original pinned source; see source-manifest.json)']
    for start,end in spans:
        text.extend([f'\n## L{start}–L{end}']+[f'{i}: {lines[i-1]}' for i in range(start,min(end,len(lines))+1)])
    (out/(key.replace('/','__')+'.txt')).write_text('\n'.join(text)+'\n')
results=[]
for label in ('combined','austin'):
    for fname,names in {'openscrub.py':{'Detection','PlateDetector','assign_dense_tracks','smooth_dense_tracks','merge_detections','track_manual_region','_ctc_greedy_decode','render','render_hdr','run_scan','run_render','_decode_report','write_report'},'openscrub_web.py':{'_plate_threshold','job_save_edits','job_track_object','job_boxes_at','job_detections'}}.items():
        data=(src/label/fname).read_text(); lines=data.splitlines(keepends=True)
        for node in ast.parse(data).body:
            if isinstance(node,(ast.ClassDef,ast.FunctionDef,ast.AsyncFunctionDef)) and node.name in names:
                raw=''.join(lines[node.lineno-1:node.end_lineno]).encode()
                results.append({'label':label,'path':fname,'symbol':node.name,'start':node.lineno,'end':node.end_lineno,'sha256':hashlib.sha256(raw).hexdigest()})
(out/'symbol-hashes.json').write_text(json.dumps(results,indent=2)+'\n')
for x in results:
    if x['label']=='combined':
        y=next((a for a in results if a['label']=='austin' and a['path']==x['path'] and a['symbol']==x['symbol']),{})
        print(x['path'],x['symbol'],'identical' if x['sha256']==y.get('sha256') else 'different',f"combined L{x['start']}-{x['end']}",f"Austin L{y.get('start')}-{y.get('end')}")
