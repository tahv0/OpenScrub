"""Static immutable-source collection only; no application imports or execution."""
import hashlib, json, pathlib, subprocess
root = pathlib.Path('/home/tahv0/src/OpenScrub')
scratch = root / '.superpowers/sdd/README/runtime/optional-policy-research'
pins = {'combined': '4b9bd7e576a8ae30369672b4b4722fc9752e233f', 'austin': '5d3a15ae683c08f368d6ba4bd0d2d77b4e7b8e2f', 'donor': 'b4d0c75f25d91510fe1692f901d11853dc7db005'}
files = {'combined': ['openscrub.py','openscrub_web.py','openscrub_gui.py','openscrub_internal/reports.py','pyproject.toml','zones_ui.py'], 'austin': ['openscrub.py','openscrub_web.py'], 'donor': ['openscrub.py','openscrub_web.py']}
manifest = []
for label, names in files.items():
    out = scratch / label
    out.mkdir(parents=True, exist_ok=True)
    for name in names:
        data = subprocess.check_output(['git','show',f'{pins[label]}:{name}'],cwd=root)
        dest=out / name
        dest.parent.mkdir(parents=True,exist_ok=True)
        dest.write_bytes(data)
        manifest.append({'label':label,'commit':pins[label],'path':name,'sha256':hashlib.sha256(data).hexdigest(),'bytes':len(data),'lines':len(data.splitlines())})
evidence = root / '.superpowers/sdd/README/optional-policy-contract-evidence'
evidence.mkdir(parents=True, exist_ok=True)
(evidence / 'source-manifest.json').write_text(json.dumps(manifest,indent=2)+'\n')
