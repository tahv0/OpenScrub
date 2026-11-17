from pathlib import Path
art=Path('/tmp/openscrub-task652')
s=Path('/tmp/openscrub-task651/serve_browser.py').read_text().replace('task651','task652').replace('Task651','Task652').replace('18651','18652')
a=s.index("alpha['options'].update");b=s.index('real=web.atomic_report',a)
s=s[:a]+'''# Reuse the reviewed second-batch mixed raw fixture at an explicit imported-input boundary.
doc=json.loads(Path('/tmp/openscrub-task651/initial-report.json').read_text())
doc['provenance']['input']=alpha['video']
(Path(alpha['dir'])/'report.json').write_text(json.dumps(doc,indent=1))
Path('/tmp/openscrub-task652/initial-report.json').write_text(json.dumps(doc))
alpha['phase']='done'
'''+s[b:]
# remove unused old body/poll schedule, retaining real server and actual publisher fault.
a=s.index('@web.app.before_request');b=s.index("web.app.view_functions['update_check']",a);s=s[:a]+s[b:]
a=s.index('# Real HTTP headers');s=s[:a]+"print('Task652 browser server ready',flush=True)\nserver.start()\n"
(art/'serve_browser.py').write_text(s)
for n in ['check_fresh.py','check_output.py']:
 (art/n).write_text((Path('/tmp/openscrub-task651')/n).read_text().replace('task651','task652').replace('Task651','Task652').replace('batch651','batch652'))
