import json,statistics
from pathlib import Path
r=json.loads(Path('/tmp/openscrub-task632/measurement/results.json').read_text())
for x in r['runs']:
 print(x['rows'],x['operation'],'delta%',100*(x['summary']['after']['median_ms']/x['summary']['before']['median_ms']-1))
 for version in ('before','after'):
  s=[s for s in x['recorded'] if s['version']==version];m=[p for sample in s for p in sample['rss_samples']]
  print(version,'warmups',[p['milliseconds'] for p in x['warmup'] if p['version']==version], 'recorded',[p['milliseconds'] for p in s], 'RSS_before_median',statistics.median(p['rss_samples'][0]['VmRSS_kib'] for p in s),'RSS_max',max(p['VmRSS_kib'] for p in m),'HWM_max',max(p['VmHWM_kib'] for p in m),'counts',x['instrumented'][version]['after']['counts'])
for rows in (10000,100000):
 x=next(x for x in r['runs'] if x['rows']==rows)
 for label,worker in x['workers'].items(): print('worker',rows,label,'import',worker['imported_memory'],'fixture',worker['fixture_memory'],'ready',worker['ready_memory'])
print('python',r['python'],r['executable'])
