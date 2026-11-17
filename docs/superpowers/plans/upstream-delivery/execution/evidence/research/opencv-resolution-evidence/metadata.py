import concurrent.futures, datetime, email.parser, hashlib, json, pathlib, re, urllib.request
root=pathlib.Path('/tmp/openscrub-opencv-resolution-20261117')
urls=set()
for key in ['312','39']:
    urls.update(re.findall(r'DEBUG Sending fresh GET request for: (https://files\.pythonhosted\.org/\S+\.whl\.metadata)',(root/('resolver-'+key+'-online.log')).read_text()))
assert len(urls)<=60
start=datetime.datetime.now(datetime.timezone.utc).isoformat()
def fetch(url):
    req=urllib.request.Request(url,headers={'User-Agent':'OpenScrub-bounded-core-resolution-evidence/1.0'})
    with urllib.request.urlopen(req,timeout=20) as response:
        raw=response.read(256000+1)
        if len(raw)>256000: raise ValueError('metadata budget exceeded')
        msg=email.parser.BytesParser().parsebytes(raw)
        return {'url':url,'retrieved_utc':datetime.datetime.now(datetime.timezone.utc).isoformat(),'http_status':response.status,'server_date':response.headers.get('Date'),'bytes':len(raw),'sha256':hashlib.sha256(raw).hexdigest(),'name':msg['Name'],'version':msg['Version'],'requires_python':msg['Requires-Python'],'requires_dist':msg.get_all('Requires-Dist',[])}
with concurrent.futures.ThreadPoolExecutor(max_workers=6) as pool:
    results=list(pool.map(fetch,sorted(urls)))
summary={'started_utc':start,'finished_utc':datetime.datetime.now(datetime.timezone.utc).isoformat(),'request_limit_bytes':256000,'metadata_only':True,'total_bytes':sum(x['bytes'] for x in results),'metadata':results}
(root/'metadata-declarations.json').write_text(json.dumps(summary,indent=2)+'\n')
print(json.dumps({'metadata_count':len(results),'total_bytes':summary['total_bytes'],'output':str(root/'metadata-declarations.json')},indent=2))
