"""Strict-installed CLI server; actual descriptor Range/conditional/early-close."""
import http.client
import json
import os
from pathlib import Path
import socket
import subprocess
import sys
import time

import openscrub_web as web
root=Path(os.environ['VERIFY_RUN']);target=Path(sys.argv[1])
job=web.new_job('',{},'synthetic.mp4');directory=Path(job['dir'])
video=directory/'input.mp4';output=directory/'output.mp4'
payload=bytes(range(256))*8192
video.write_bytes(payload);output.write_bytes(payload)
(directory/'report.json').write_text(json.dumps(dict(provenance=dict(input=str(video),settings={}),detections=[])))
with socket.socket() as listener:
 listener.bind(('127.0.0.1',0));port=listener.getsockname()[1]
log=root/'logs/installed-listening.log'
with log.open('w') as stream:
 proc=subprocess.Popen([sys.executable,str(target/'bin/openscrub-web'),'--http','--host','127.0.0.1','--port',str(port),'--retain-days','0'],cwd=root,stdout=stream,stderr=subprocess.STDOUT)
 def api(method,path,headers=None,early=False):
  connection=http.client.HTTPConnection('127.0.0.1',port,timeout=5)
  try:
   connection.request(method,path,headers=dict({'Connection':'close'},**(headers or {})))
   result=connection.getresponse();body=result.read(64) if early else result.read()
   return result.status,dict(result.getheaders()),body
  finally:connection.close()
 try:
  for attempt in range(100):
   try:
    status,headers,body=api('GET','/api/jobs')
    if status==200:break
   except OSError:
    assert proc.poll() is None,'server exited; inspect installed-listening.log'
   time.sleep(.1)
  else:raise AssertionError('installed server readiness deadline')
  jobs=json.loads(body);assert len(jobs)==1 and jobs[0]['phase']=='done'
  url='/api/jobs/'+job['id']+'/download'
  status,headers,body=api('GET',url);assert status==200 and body==payload
  etag=headers['ETag'];modified=headers['Last-Modified']
  cases=[('GET',{'Range':'bytes=3-9'},206,payload[3:10]),('GET',{'Range':'bytes=-5'},206,payload[-5:]),('GET',{'Range':'bytes=99999999-'},416,None),('GET',{'If-None-Match':etag},304,b''),('GET',{'If-Modified-Since':modified},304,b''),('GET',{'Range':'bytes=3-9','If-Range':etag},206,payload[3:10]),('GET',{'Range':'bytes=3-9','If-Range':'"old"'},200,payload),('HEAD',{},200,b'')]
  for method,request_headers,expected_status,expected in cases:
   status,headers,body=api(method,url,request_headers)
   assert status==expected_status,(method,request_headers,status)
   if expected is not None:assert body==expected
  api('GET',url,early=True)
  for attempt in range(50):
   status,headers,body=api('DELETE','/api/jobs/'+job['id'])
   if status==200:break
   assert status==409
   time.sleep(.05)
  assert status==200,'early-close ownership did not retire'
  print(json.dumps(dict(installed_server='actual configured Cheroot',ranges='partial/suffix/416',conditional='304/If-Range',head=True,early_close_delete=status,payload_sha256=__import__('hashlib').sha256(payload).hexdigest())))
 finally:
  proc.terminate()
  try:proc.wait(timeout=15)
  except subprocess.TimeoutExpired:proc.kill();proc.wait(timeout=5)
  assert proc.poll() is not None
  print('SERVER_CLEANUP',proc.returncode)
