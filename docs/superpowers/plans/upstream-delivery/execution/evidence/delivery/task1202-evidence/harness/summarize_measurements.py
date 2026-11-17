import hashlib,json,os,statistics
from pathlib import Path
ROOT=Path(os.environ['TASK1202_ROOT'])
rows=[json.loads(line) for line in (ROOT/'measurements.jsonl').read_text().splitlines()]
assert len(rows)==216,len(rows)
summary=[]
for case in ('short','unicode','multiline','maximum'):
    for count in (500,5000,20000):
        record={'case':case,'count':count}
        for mode in ('base','candidate'):
            group=[r for r in rows if r['mode']==mode and r['case']==case and r['count']==count and r['sample'].startswith('observed-')]
            assert len(group)==5
            record[mode]={
                'append_median_us_per_entry':statistics.median(r['append_us_per_entry'] for r in group),
                'http_full_median_ms':statistics.median(value/1e6 for r in group for value in r['http_full_ns']),
                'http_full_median_of_observation_means_ms':statistics.median(sum(r['http_full_ns'])/len(r['http_full_ns'])/1e6 for r in group),
                'http_matched_median_ms':statistics.median(value/1e6 for r in group for value in r['http_matched_ns']),
                'http_full_bytes':group[0]['http_full_bytes'][0],
                'http_matched_bytes':group[0]['http_matched_bytes'][0],
                'state':group[0]['state'],
                'allocation':next(r for r in rows if r['mode']==mode+'-allocation' and r['case']==case and r['count']==count),
            }
        record['append_cost_ratio']=record['candidate']['append_median_us_per_entry']/record['base']['append_median_us_per_entry']
        record['matched_http_cost_ratio']=record['candidate']['http_matched_median_ms']/record['base']['http_matched_median_ms']
        record['needs_candidate_supervisor_ruling']=(record['candidate']['append_median_us_per_entry']>100 or max(record['candidate']['http_full_median_ms'],record['candidate']['http_full_median_of_observation_means_ms'])>50)
        summary.append(record)
(ROOT/'measurement-summary.json').write_text(json.dumps(summary,indent=2)+'\n')
print('raw_records',len(rows),'raw_sha256',hashlib.sha256((ROOT/'measurements.jsonl').read_bytes()).hexdigest())
for row in summary:
    print(row['case'],row['count'],'append_us',row['base']['append_median_us_per_entry'],row['candidate']['append_median_us_per_entry'],'full_ms',row['base']['http_full_median_ms'],row['candidate']['http_full_median_ms'],'matched_ms',row['base']['http_matched_median_ms'],row['candidate']['http_matched_median_ms'],'ruling',row['needs_candidate_supervisor_ruling'])
