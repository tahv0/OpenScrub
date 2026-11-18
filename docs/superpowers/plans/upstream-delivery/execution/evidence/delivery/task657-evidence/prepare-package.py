from pathlib import Path
import hashlib,json,tomllib
E=Path(__file__).parent;R=E.parent;S=Path('/home/tahv0/.codex/worktrees/bde3/OpenScrub')
c=json.loads((E/'config-312.json').read_text());old=json.loads((R/'task655-evidence/package-312.json').read_text());meta=tomllib.loads((S/'pyproject.toml').read_text());includes=meta['tool']['hatch']['build']['targets']['sdist']['include']+['pyproject.toml']
sdist=[p for p in c['files'] if any(p==i or p.startswith(i+'/') for i in includes)]
p=E/'installed.py';p.write_text((R/'task150-evidence/installed.py').read_text())
c['prerequisites'].append(dict(path=str(p),sha256=hashlib.sha256(p.read_bytes()).hexdigest()))
c['package']=dict(tool_paths=old['package']['tool_paths'],sdist_files=sdist,wheel_files=old['package']['wheel_files'],requires_python='>=3.9',installed_commands=[['{target}/bin/openscrub','--help'],['{target}/bin/openscrub-web','--help'],[str(p)]])
(E/'package-312.json').write_text(json.dumps(c,indent=2)+'\n');print('package exact inventory',len(sdist),'sdist files',len(c['package']['wheel_files']),'wheel entries')
