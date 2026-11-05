# Test all four PRs with Docker Compose on Windows

The `integration/all-prs` branch combines PRs #1–#4. This setup builds its
local checkout with the CPU `Dockerfile`, so you test the combined code
rather than a published release image. It works without GPU passthrough;
CPU scans and renders can take longer. GPU configuration is outside this
test setup.

Included PR snapshots:

| PR | Head commit | Included change |
|---|---|---|
| #1 | `4a6675f` | Mask review display, including supplied compound geometry |
| #2 | `39b4ed8` | Explicit, idempotent Blur and Keep actions |
| #3 | `77755f0` | Opt-in Narrow plate coverage with zero extra margin |
| #4 | `2900930` | Browser Save As for video and audit report |

Automatic precise segmentation with a small model is deferred and is not
included in this CPU test setup. Compound shapes can be displayed and
rendered when their geometry is supplied; that does not imply automatic
segmentation of arbitrary objects.

Use Docker Desktop in **Linux containers** mode with its WSL 2 engine,
Git for Windows, and a current Docker Compose v2. Run the commands below
in **PowerShell on Windows**, with Docker Desktop running. Docker Desktop
must be allowed to access your D: drive; accept its file access prompt if
one appears. These paths assume a local Docker Desktop engine, not a
remote Docker context.

## Get the branch and start

```powershell
git clone --branch integration/all-prs https://github.com/tahv0/OpenScrub.git OpenScrubTest
Set-Location OpenScrubTest
git status --short --branch
git rev-parse --short HEAD

New-Item -ItemType Directory -Force -Path D:\OpenScrubTest\data | Out-Null
docker compose -f compose.windows-test.yml config --quiet
docker compose -f compose.windows-test.yml up --build -d
docker compose -f compose.windows-test.yml ps
docker compose -f compose.windows-test.yml logs --tail 100 openscrub
```

The first build downloads Python packages and detection models and can
take a while. Later builds reuse cached dependency layers. `up --build`
builds from the directory containing this Compose file and then starts
the app; running `docker compose pull` does not build the branch.

Open **[http://localhost:8384](http://localhost:8384)** in Chrome or Edge on
the same Windows computer. Wait for startup if the first request fails.
The published port is bound to `127.0.0.1`, so this setup is for local
testing. The app runs HTTP to use the browser's trusted localhost context
without a self-signed certificate prompt. Keep this loopback binding when
using HTTP.

## Read a video directly from D:

| Windows host path | Container/server path | Access |
|---|---|---|
| `D:\` | `/media/d/` | Read only |
| `D:\Videos\clip.mp4` | `/media/d/Videos/clip.mp4` | Read only source example |
| `D:\OpenScrubTest\data` | `/root/.local/share/OpenScrub` | Writable app data |

In Scan Setup, enter `/media/d/Videos/clip.mp4` in **“a path on the
server”**, then press Enter. Use forward slashes and the container path,
including the exact filename. Configure categories/windows and choose
**Start scan**. The app reads that source in place; it does not upload a
second copy through the browser. The browser's **choose a video file**
control is the upload flow instead.

`OPENSCRUB_MEDIA_ROOT=/media/d` confines server video paths to the mounted
D: tree. Other drives are not mounted by this configuration. Source
videos remain read only even though the app has a separate writable data
mount.

To check one known test filename without listing other drive contents,
change `Videos` and `clip.mp4` below to match your test clip:

```powershell
docker compose -f compose.windows-test.yml exec -T openscrub python -c "from pathlib import Path; print([p.name for p in Path('/media/d/Videos').glob('clip.mp4') if p.is_file()]); p = Path('/media/d/Videos/clip.mp4'); print('Readable:', bool(p.open('rb').read(1)))"
```

It should print `['clip.mp4']` and `Readable: True` for a nonempty readable
file. If it fails, check the Windows filename, Docker Desktop drive
access, and the resolved mount sources:

```powershell
docker compose -f compose.windows-test.yml config
```

Both bind mounts use `create_host_path: false`: a misspelled or missing
host directory fails startup instead of creating an empty directory.
Create the data directory before `up`.

## Review and save an output

Review the masks and the rendered video before trusting the redaction.
The app first renders into its writable job store. **Save redacted video
as…** and **Save audit report as…** then ask Chrome/Edge for a destination
on the computer running the browser. Choose
a folder such as `D:\OpenScrubTest\exports` in the native Windows picker.
The browser writes the downloaded output there, so that folder does not
need a writable container mount. Canceling the picker should leave the
generated output available in the job.

The native picker uses `showSaveFilePicker`, which requires a supported
browser and a secure context; browsers consider `http://localhost`
trustworthy for this purpose. If the picker API is unavailable, the app
falls back to the browser's normal download behavior. That behavior may
save directly to Downloads or ask where to save, depending on browser
settings. Test the native picker in current Chrome/Edge; test the fallback
in a browser without this API, such as Firefox.

App data persists at `D:\OpenScrubTest\data`. Jobs, review state, reports,
thumbnails, intermediate files, and generated outputs live under
`D:\OpenScrubTest\data\openscrub_jobs\<job-id>\`; generated output is
`output.mp4`, `output.mov`, or `output.mkv` there, according to the chosen
export format. For source `clip.mp4` rendered as MKV, Save As suggests
`clip_redacted.mkv`; the audit report suggests `clip_audit.json`.
Server-path jobs retain a reference to the source on D:, so keep the
original file in place to resume or retry them. Uploaded sources are
stored inside their job directory.

This test profile sets `--retain-days 0`, disabling automatic age-based
job deletion. Delete test jobs from the app when finished; deleting a
server-path job does not remove the original source. Job data can contain
the original sensitive content, so choose test media accordingly.

## Checklist for the combined branch

Use a short test clip with known faces/plates or synthetic text. Record
the commit printed by `git rev-parse` alongside any findings.

Full-plate coverage remains the default. Narrow coverage is opt-in and
uses a conservative fallback, often masking the full plate when lettering
cannot be localized confidently. Narrow HDR output is rejected: for an
HDR input, explicitly choose **HDR output → tone-map to SDR** before testing Narrow.
It does not switch to SDR automatically. Full-plate HDR behavior is
unchanged.

| Change | Manual check |
|---|---|
| PR #1: mask display | Check masks against selected render settings. Scrub and step frames; masks should stay aligned with the frame and selected detection. With supplied compound geometry, check multiple components and holes against the final render. Automatic precise segmentation is not included. |
| PR #2: Blur / Keep | Check that individual **Blur** and **Keep** actions are both visible. Click each twice: Blur stays blurred, Keep stays kept. Repeat the bulk Blur/Keep actions, then change one row and apply each bulk action again; every applicable row should reach the requested state. |
| PR #3: zero plate margin / explicit SDR | Set Narrow plate coverage with margin `0`, save, and render. Confirm zero survives and the output matches the preview, including conservative full-plate fallbacks. For an HDR input, confirm Narrow HDR output is rejected, then explicitly choose SDR and test Narrow again. |
| PR #4: Save As | After a render, save the video and audit report to a chosen D: folder in Chrome/Edge. Check the video plays and the report opens. Repeat and cancel each picker: no unwanted download should start and the outputs should remain available. Check normal-download fallback in a browser without the native picker API. |

Also restart after a completed MP4 job and check that it appears again.
This snapshot's restart recovery recognizes `output.mp4` only: MOV/MKV
files remain on disk but their jobs may return to review after restart.
Review the output itself; a passing scan or build does not establish that
every sensitive detail was found.

## Stop, restart, or update

Wait for active scans/renders to finish before stopping or updating.

```powershell
# Stop the existing container; restart it later with the same data.
docker compose -f compose.windows-test.yml stop
docker compose -f compose.windows-test.yml start

# Or remove this test container/network. Bind-mounted data stays on D:.
docker compose -f compose.windows-test.yml down
```

After all scans/renders have finished, update the checkout and rebuild:

```powershell
git fetch origin
git switch integration/all-prs
git pull --ff-only origin integration/all-prs
git rev-parse --short HEAD
docker compose -f compose.windows-test.yml up --build -d --force-recreate
docker compose -f compose.windows-test.yml logs --tail 100 openscrub
```

The in-app updater does not update a container image. A rebuild and
container recreation are required to test a new branch commit. The
120-second stop grace period gives the app's vault shutdown handler time
to run if encryption is enabled; large encrypted job stores may need a
longer grace period.

## Override paths for another host or CI

Host mount paths can be changed without editing the Compose file. For
example, these PowerShell variables restrict the source mount to just the
Videos folder and put data on the C: drive:

```powershell
$env:OPENSCRUB_TEST_MEDIA_DIR = 'D:/Videos'
$env:OPENSCRUB_TEST_DATA_DIR = 'C:/OpenScrubTest/data'
New-Item -ItemType Directory -Force -Path $env:OPENSCRUB_TEST_DATA_DIR | Out-Null
docker compose -f compose.windows-test.yml up --build -d
```

With this source override, `D:\Videos\clip.mp4` becomes
`/media/d/clip.mp4` in the app. Keep the same overrides in the shell used
for subsequent Compose commands. Alternatively, put those two variables
in an uncommitted `.env` file in this checkout; shell variables take
precedence over `.env`.

On Linux CI, point both variables at existing absolute Linux directories:

```bash
export OPENSCRUB_TEST_MEDIA_DIR="$RUNNER_TEMP/openscrub-media"
export OPENSCRUB_TEST_DATA_DIR="$RUNNER_TEMP/openscrub-data"
mkdir -p "$OPENSCRUB_TEST_MEDIA_DIR" "$OPENSCRUB_TEST_DATA_DIR"
docker compose -f compose.windows-test.yml config --quiet
docker compose -f compose.windows-test.yml up --build -d
```

CI with Linux bind paths can check the image and server, but does not
verify Windows drive sharing, native picker behavior, or real GPU paths.

## References

- [Docker Desktop WSL 2 backend](https://docs.docker.com/desktop/features/wsl/)
- [Compose build configuration](https://docs.docker.com/reference/compose-file/build/)
- [Compose bind mounts](https://docs.docker.com/reference/compose-file/services/#volumes)
- [Compose variable interpolation](https://docs.docker.com/compose/how-tos/environment-variables/variable-interpolation/)
- [docker compose up](https://docs.docker.com/reference/cli/docker/compose/up/)
- [MDN: secure contexts and localhost](https://developer.mozilla.org/en-US/docs/Web/Security/Defenses/Secure_Contexts)
- [MDN: showSaveFilePicker](https://developer.mozilla.org/en-US/docs/Web/API/Window/showSaveFilePicker)
