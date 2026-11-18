"""Strict installed identity, evaluated JS and real listening HTTP smoke."""
from pathlib import Path
import os,subprocess,threading,urllib.request
from cheroot.wsgi import Server
import openscrub as o,openscrub_web as w,zones_ui
root=Path(os.environ['VERIFY_RUN']);target=Path(os.environ['VERIFY_CONFIG'])
assert 'site-packages' in str(Path(w.__file__).parent)
assert o.build_parser().parse_args(['dummy.mp4']).mode=='blur'
result=subprocess.run(['node','--check'],input=w.APP_JS,text=True,capture_output=True);assert result.returncode==0,result.stderr
server=Server(('127.0.0.1',18552),w.app,numthreads=2);thread=threading.Thread(target=server.start,daemon=True);thread.start()
try:
 with urllib.request.urlopen('http://127.0.0.1:18552/') as response:
  assert response.status==200;page=response.read().decode();assert 'id="reviewType"' in page and 'id="reviewOutput"' in page and 'Filters only change the view.' in page
 print('INSTALLED_LISTENING_HTTP_AND_JS_OK',w.__file__,flush=True)
finally:server.stop();thread.join(10);assert not thread.is_alive()
