"""Edit public validation wrappers without changing renderer computation."""
import ast
from pathlib import Path
p=Path('/home/tahv0/.codex/worktrees/c832/OpenScrub/openscrub.py')
s=p.read_text()
for name,stage in [('render_hdr','HDR'),('render','SDR')]:
    tree=ast.parse(s);node=next(n for n in tree.body if isinstance(n,ast.FunctionDef) and n.name==name)
    lines=s.splitlines(True);start=sum(map(len,lines[:node.lineno-1]));end=sum(map(len,lines[:node.end_lineno]))
    original=s[start:end]
    # Keep the original public signature byte-for-byte and forward its parameters.
    header=original[:original.index('\n',original.index('):'))+1]
    arguments=[arg.arg for arg in node.args.args]
    rows=[];line='        '
    for arg in arguments:
        token=arg+', '
        if len(line)+len(token)>83:
            rows.append(line.rstrip());line='        '
        line+=token
    rows.append(line.rstrip(', ')+')')
    wrapper=header
    if node.body and isinstance(node.body[0],ast.Expr) and isinstance(node.body[0].value,ast.Constant) and isinstance(node.body[0].value.value,str):
        doc=node.body[0];wrapper+=''.join(lines[doc.lineno-1:doc.end_lineno])
    wrapper+=f'    _geometry_preflight(detections, cum, bands, fps, pad, band_margin, "{stage}")\n'
    wrapper+=f'    return _{name}(\n'+'\n'.join(rows)+'\n\n\n'
    body=original.replace('def '+name+'(', 'def _'+name+'(',1)
    body=body.replace(f'    _geometry_preflight(detections, cum, bands, fps, pad, band_margin, "{stage}")\n','',1)
    s=s[:start]+wrapper+body+s[end:]
start=s.index('def run_render(');end=s.index('\ndef run_pipeline(',start)
section=s[start:end].replace('        render_hdr(', '        _render_hdr(',1).replace('        render(args.video,', '        _render(args.video,',1)
s=s[:start]+section+s[end:];p.write_text(s)
p=p.with_name('tests')/'test_render_geometry.py';s=p.read_text().replace('monkeypatch.setattr(o, "render", lambda *a, **kw: observed.append(kw["clip"]))','monkeypatch.setattr(o, "_render", lambda *a, **kw: observed.append(kw["clip"]))');p.write_text(s)
