"""Task1003 installed PAGE bytes plus unchanged exact/strict HTTP owner gate."""
import hashlib,json,os,runpy,threading,urllib.request,re
from pathlib import Path
from werkzeug.serving import make_server
import openscrub_web as web
root=Path(os.environ['VERIFY_RUN'])
cfg=json.loads(Path(os.environ['VERIFY_CONFIG']).read_text())
expected=json.loads(Path(__file__).with_name('page-identities-final.json').read_text())
for key in ('APP_JS','APP_CSS'):
 assert hashlib.sha256(getattr(web,key).encode()).hexdigest()==expected[key]
 assert getattr(web,key) in web.PAGE
actual_urlopen=urllib.request.urlopen
try:
 runpy.run_path('/home/tahv0/src/OpenScrub/.superpowers/sdd/README/runtime/task1002/http_counts.py')
finally:
 urllib.request.urlopen=actual_urlopen
web.TOKEN=None
server=make_server('127.0.0.1',0,web.app,threaded=True)
thread=threading.Thread(target=server.serve_forever);thread.start()
try:
 with urllib.request.urlopen('http://127.0.0.1:'+str(server.server_port)+'/',timeout=8) as response:
  assert response.status==200
  page=response.read().decode()
 # Exact shipped index substitutions; the observed guest disk field may vary.
 assert web.load_custom_cats()==[]
 expected_page=web.PAGE.replace('%%MAXUP%%',str(web.app.config.get('MAX_CONTENT_LENGTH') or 0)).replace('%%VERSION%%',web.openscrub.VERSION)
 assert expected_page.count('%%FREEDISK%%')==1
 match=re.fullmatch(re.escape(expected_page).replace(re.escape('%%FREEDISK%%'),'([0-9]+)'),page)
 assert match,'installed HTTP PAGE differs from exact index substitutions'
 assert int(match.group(1))>=0
 assert web.APP_JS in page and web.APP_CSS in page
finally:
 server.shutdown();thread.join(8);server.server_close();assert not thread.is_alive()
checks={}
for name in ('tests/editor_resize_browser.cjs','tests/editor_resize_server.py','tests/test_editor_resize.py','tests/test_review_save_failures.py'):
 digest=hashlib.sha256((root/'updater-fixture'/name).read_bytes()).hexdigest()
 assert digest==cfg['files'][name];checks[name]=digest
record=dict(APP_JS=expected['APP_JS'],APP_CSS=expected['APP_CSS'],PAGE=hashlib.sha256(page.encode()).hexdigest(),HTTP='actual loopback PAGE equals installed PAGE with exact max/version and observed guest disk substitution',observed_guest_free_bytes=int(match.group(1)),updater_checks=checks)
(root/'logs/resize-installed-page.json').write_text(json.dumps(record,indent=2)+'\n')
print('INSTALLED_RESIZE_PAGE_AND_UPDATER_BYTES_OK',json.dumps(record),flush=True)
