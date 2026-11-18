from pathlib import Path
import os,subprocess
import openscrub_web as w
root=Path(os.environ['VERIFY_RUN'])
(root/'page.html').write_text(w.index())
result=subprocess.run(['node',str(Path(__file__).with_name('browser.cjs'))],check=False)
raise SystemExit(result.returncode)
