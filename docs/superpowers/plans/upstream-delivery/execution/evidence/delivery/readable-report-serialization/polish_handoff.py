from pathlib import Path
import re,json,hashlib
root=Path('/home/tahv0/src/OpenScrub/.superpowers/sdd/README')
for name in ('task-632-report.md','task-632-pr.md'):
 p=root/name;s=p.read_text().replace('All127before/after Git blobs','All 126 before and 127 after Git blobs').replace('golden/stdout expected bytes','golden/stdlib expected bytes')
 for source,target in {'base3457efa':'base `3457efa`','before3457efa':'before `3457efa`','before12919c9':'before `12919c9`','to4a62e49':'to `4a62e49`','was3457efa':'was `3457efa`','exact3457efa→4a62e49':'exact `3457efa`→`4a62e49`'}.items():s=s.replace(source,target)
 lines=[]; fenced=False
 for line in s.splitlines():
  if line.startswith('```'):fenced=not fenced;lines.append(line);continue
  if fenced:lines.append(line);continue
  segments=re.split(r'(`[^`]*`|\b[0-9a-f]{7,64}\b)',line)
  for i in range(0,len(segments),2):
   t=segments[i]
   t=re.sub(r'(?<=[A-Za-z])(?=[0-9])',' ',t)
   t=re.sub(r'(?<=[0-9])(?=[A-Za-z])',lambda m:'' if t[m.start():].startswith(('k ','k/','k;','k,','k)','k→','k-')) else ' ',t)
   t=re.sub(r';(?=\S)','; ',t)
   t=re.sub(r':(?=[0-9])',': ',t)
   segments[i]=t
  lines.append(''.join(segments))
 p.write_text('\n'.join(lines)+'\n')
art=Path('/tmp/openscrub-task632');manifest=json.loads((art/'handoff-manifest.json').read_text())
for name in ('task-632-report.md','task-632-pr.md'):manifest[name]=hashlib.sha256((root/name).read_bytes()).hexdigest()
manifest['polish_handoff.py']=hashlib.sha256(Path(__file__).read_bytes()).hexdigest()
(art/'handoff-manifest.json').write_text(json.dumps(manifest,indent=2))
