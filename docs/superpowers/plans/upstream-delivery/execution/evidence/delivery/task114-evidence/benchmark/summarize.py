"""Derive compact summaries without modifying the retained original measurements."""
import gzip,hashlib,json,pathlib
r=pathlib.Path('/tmp/openscrub-task114/evidence')
c=json.loads(gzip.decompress((r/'comparison.json.gz').read_bytes()))
b=json.loads(gzip.decompress((r/'baseline.json.gz').read_bytes()))
summary=[]
for case,old in zip(c['cases'],b['cases']):
 assert case['name']==old['name']
 samples={label:[x['ns']/1e6 for x in case['samples'] if x['implementation']==label] for label in ('base','head')}
 med={label:case['median_ns'][label]/1e6 for label in ('base','head')}
 work=case['instrumentation']['head']['index_work'].copy()
 # A lambda defined on the same line produces additional source-line events.
 # The raw trace remains untouched; subtract exactly those key invocations.
 raw=work['order_restorations'];emitted=work['emitted_entries_and_order_elements']
 work['raw_sort_line_events']=raw
 work['order_restorations']=raw-emitted
 sort=[f for f in case['profile_and_memory']['head']['profile_functions'] if f['function']=="<method 'sort' of 'list' objects>"]
 assert len(sort)==1 and work['order_restorations']==sort[0]['total_calls']==2*int(case['name'].rsplit('_',1)[1])
 pred={label:sum(n for line,n in case['instrumentation'][label]['selected'].items() if 'if m.category != d.category' in line) for label in ('base','head')}
 summary.append({'name':case['name'],'initial_baseline_median_ms':old['median_ns']['base']/1e6,
                 'comparison_samples_ms':samples,'comparison_median_ms':med,
                 'head_over_base_ratio':med['head']/med['base'],
                 'change_percent':100*(med['head']/med['base']-1),
                 'final_predicate_visits':pred,'corrected_index_work':work,
                 'traced_python_peak_bytes':{label:case['profile_and_memory'][label]['traced_python_peak_bytes'] for label in ('base','head')},
                 'output_sha256':case['samples'][0]['output_sha256'],'all_outputs_equal':case['all_outputs_equal']})
raw=json.dumps({'derivation':'raw sort-line events include key-lambda events; actual order restorations = raw minus emitted key elements, independently checked against cProfile list.sort calls. Original measurements unchanged.', 'cases':summary},indent=2)+'\n'
(r/'summary.json').write_text(raw)
for f in ('fixtures.json.gz','baseline.json.gz','comparison.json.gz'):
 compressed=(r/f).read_bytes();decoded=gzip.decompress(compressed);parsed=json.loads(decoded)
 print(json.dumps({'file':f,'compressed_bytes':len(compressed),'compressed_sha256':hashlib.sha256(compressed).hexdigest(),
 'uncompressed_bytes':len(decoded),'uncompressed_sha256':hashlib.sha256(decoded).hexdigest(),'reparse':'ok'}))
for x in summary:
 print(x['name'],[round(x['comparison_median_ms'][l],6) for l in ('base','head')],round(x['change_percent'],2),x['corrected_index_work'])
