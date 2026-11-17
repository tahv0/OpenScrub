import collections, hashlib, json, pathlib, re, subprocess, tomllib, urllib.parse
from packaging.requirements import Requirement
from packaging.specifiers import SpecifierSet
from packaging.utils import canonicalize_name
from packaging.version import Version
root=pathlib.Path('/tmp/openscrub-opencv-resolution-20261117')
meta=json.loads((root/'metadata-declarations.json').read_text())
byversion={(canonicalize_name(d['name']),d['version']):d for d in meta['metadata']}
manifest=json.loads((root/'source-manifest.json').read_text())
targets=json.loads((root/'targets.json').read_text())
results={}
for key in ['312','39']:
    lock=tomllib.loads((root/('pylock.'+key+'.toml')).read_text())
    selected={p['name']:p for p in lock['packages']}
    env=targets[key]['marker_environment'];env['extra']=''
    exact=env['python_full_version']
    assert Version(exact) in SpecifierSet(manifest['requires_python'])
    failures=[]; edges=[]; pyreq={}; opencv_edges=[]
    for reqstr in manifest['core_candidate']:
        req=Requirement(reqstr)
        if not req.marker or req.marker.evaluate(env):
            assert req.name in selected and Version(selected[req.name]['version']) in req.specifier,reqstr
    for name,p in selected.items():
        d=byversion[name,p['version']]
        pyreq[name]=d['requires_python']
        if d['requires_python'] and Version(exact) not in SpecifierSet(d['requires_python']):failures.append([name,'Requires-Python',d['requires_python']])
        for raw in d['requires_dist']:
            req=Requirement(raw); active=not req.marker or req.marker.evaluate(env)
            dep=canonicalize_name(req.name)
            edge={'from':name,'requirement':raw,'active':active}
            edges.append(edge)
            if 'opencv' in dep:opencv_edges.append(edge)
            if active and (dep not in selected or Version(selected[dep]['version']) not in req.specifier):failures.append(edge)
    wheel_names={name:[urllib.parse.unquote(w['url'].rsplit('/',1)[-1]) for w in p['wheels']] for name,p in selected.items()}
    tagcode='''import json,sys
from packaging.tags import sys_tags
from packaging.utils import parse_wheel_filename
tags=set(sys_tags())
print(json.dumps({name:[fn for fn in names if parse_wheel_filename(fn)[3]&tags] for name,names in json.loads(sys.argv[1]).items()}))'''
    compatible=json.loads(subprocess.check_output([targets[key]['executable'],'-B','-c',tagcode,json.dumps(wheel_names)],cwd=root,env={'PATH':'/usr/bin:/bin','PYTHONDONTWRITEBYTECODE':'1','PYTHONNOUSERSITE':'1'}))
    assert all(compatible.values()),compatible
    opencv=[p for p in selected if p in ['opencv-python','opencv-python-headless','opencv-contrib-python','opencv-contrib-python-headless']]
    assert opencv==['opencv-python']
    assert Version(selected['opencv-python']['version'])<Version('5')
    assert not failures,failures
    log=(root/('resolver-'+key+'-online.log')).read_text()
    requests=re.findall(r'DEBUG Sending fresh GET request for: (\S+)',log)
    assert all(url.startswith('https://pypi.org/simple/') or url.endswith('.whl.metadata') for url in requests)
    cachefiles=[p for p in (root/('cache-'+key)).rglob('*') if p.is_file()]
    result={'status':'pass','target_python':exact,'lock_requires_python':lock['requires-python'],'package_count':len(selected),'selected_versions':{n:p['version'] for n,p in selected.items()},'selected_markers':{n:p['marker'] for n,p in selected.items() if 'marker' in p},'requires_python':pyreq,'compatible_wheels':compatible,'core_requirements_checked':manifest['core_candidate'],'all_active_dependency_edges_valid':True,'active_dependency_count':sum(e['active'] for e in edges),'dependency_edges':edges,'opencv_distributions':opencv,'transitive_opencv_requirements':opencv_edges,'fresh_get_count':len(requests),'fresh_get_urls':requests,'only_index_and_metadata_gets':True,'cache_file_bytes':sum(p.stat().st_size for p in cachefiles),'cache_wheel_archive_count':sum(p.suffix in ['.whl','.zip','.gz','.bz2'] for p in cachefiles)}
    results[key]=result
(root/'validation.json').write_text(json.dumps(results,indent=2)+'\n')
print(json.dumps({k:{f:v for f,v in r.items() if f in ['status','target_python','package_count','selected_versions','selected_markers','opencv_distributions','transitive_opencv_requirements','fresh_get_count','cache_file_bytes','cache_wheel_archive_count']} for k,r in results.items()},indent=2))
