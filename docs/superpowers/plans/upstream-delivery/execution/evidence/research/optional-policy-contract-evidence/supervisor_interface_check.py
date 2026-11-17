"""Bounded static interface evidence; reads only the already exported pinned engine."""
import ast, hashlib, json, pathlib
root=pathlib.Path('/home/tahv0/src/OpenScrub/.superpowers/sdd/README')
src=root/'runtime/optional-policy-research/combined/openscrub.py'
s=src.read_text(); lines=s.splitlines()
tree=ast.parse(s)
wanted={'Detection','assign_dense_tracks','smooth_dense_tracks','merge_detections','apply_coverage','_settings_dict','write_report','_decode_report'}
spans={}
for node in tree.body:
    if isinstance(node,(ast.ClassDef,ast.FunctionDef)) and node.name in wanted:
        spans[node.name]=(min([node.lineno]+[d.lineno for d in node.decorator_list]),node.end_lineno)
ranges=[(733,753),(1361,1389),(1433,1442),(2985,3000),(3811,3836),(6118,6128),(6371,6400),(6424,6446)]
text=['# Bounded supervisor interface check',f'# combined openscrub.py SHA-256 {hashlib.sha256(src.read_bytes()).hexdigest()}', '# This is source evidence only; no application module was imported or executed.']
for a,b in ranges:
    text.extend([f'\n## Original L{a}–L{b}']+[f'{i}: {lines[i-1]}' for i in range(a,b+1)])
out=root/'optional-policy-contract-evidence'
(out/'supervisor-interface-excerpts.txt').write_text('\n'.join(text)+'\n')
print(json.dumps(spans,sort_keys=True))
