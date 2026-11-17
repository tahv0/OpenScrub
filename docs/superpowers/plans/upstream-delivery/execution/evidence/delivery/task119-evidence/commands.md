# Task119 commands and boundaries

Native root: /home/tahv0/.codex/worktrees/c832/OpenScrub; exact base e21ebdf6e3ee46e6c65050dc956a9a3459152269.
All commands used login=false (login shell otherwise reset cwd); actual Python3.12.16 or3.9.25, Node22.22.1, OpenCV4.14.0. No bootstrap Python interpreter execution. Browser plugin and browser skill absent; prepared Playwright1.65.1/Chromium159.0.8154.6 fallback used. No new browser/model/dependency network download.

Retained env312.sh/env39.sh source the prepared runtimes then retarget mutable paths to /tmp/openscrub-task119. Harness sitecustomize installs write/outward-network guards and task-only expanduser before application import, including standalone server/CLI children. Task configure retargets models, jobs, settings, certificates and disables remote model fetches. Cached YuNet copied task-locally. Installed-only sitecustomize filters original/native/export paths. Native/base/floor/installed import path+hash assertions execute before test collection; standalone server asserts both modules and hashes before serving.

Pytest invocations were sequential, each with a distinct --basetemp under TASK/tmp. No basetemp was shared/deleted during another invocation.

Commands (TASK=/tmp/openscrub-task119):
- Native cwd: source TASK/env312.sh; python -m pytest tests/test_job_filename_display.py -q --basetemp=TASK/tmp/red (initial fixture failure retained); red-stable; green.
- Native cwd: python -m pytest -q --basetemp=TASK/tmp/full (incomplete143); --basetemp=TASK/tmp/full-supervised (full summary retained).
- Exact base exported using git archive into TASK/base. Empty TASK/runner cwd; TASK119_SOURCE=TASK/base PYTHONPATH=TASK/harness:TASK/base python -m pytest NATIVE/tests/test_job_filename_display.py -k emitted -q --basetemp=TASK/tmp/base-red.
- Native cwd: source TASK/env39.sh; python -m pytest tests/test_job_filename_display.py -k emitted -q --basetemp=TASK/tmp/floor39-emitted.
- TASK/runtime cwd: source env312; TASK119_INSTALLED_ONLY=1 TASK119_SOURCE=TASK/installed PYTHONPATH=TASK/harness:TASK/installed python -m pytest TASK/sdist/openscrub-1.0.96/tests/test_job_filename_display.py -k emitted -q --basetemp=TASK/tmp/installed-emitted.
- Cached backend wheels installed --no-index --no-deps --target=TASK/build-tools through actual3.12 python -m pip, bootstrapPYTHONPATH supplies pip only. tomlkit added after dependency-check failure. No prepared environment mutation.
- Source cwd with TASK/build-tools on PYTHONPATH: python -m build --sdist --no-isolation --outdir TASK/dist; extract sdist; python -m build --wheel --no-isolation --outdir TASK/dist TASK/sdist/openscrub-1.0.96. Wheel built FROM extracted sdist. Actual3.12 python -m pip install --no-index --no-deps --target=TASK/installed TASK/dist/*.whl.
- Installed-only env/cwd: python TASK/package-smoke.py. Exact source/test inclusion, installed bytes, Python>=3.9 metadata, complete parser-default equality to exported base, both CLI --help children and five actual test-client routes asserted.
- Evaluated page scripts extracted from actual Flask index response and each node --check passed. Retained JS files and hashes, no source-string-only parse claim.
- Native/installed standalone HTTP server: TASK/serve.py using task-local sitecustomize/configure; cheroot on http://127.0.0.1:18489. Authorized escalation required for localhost listening and browser launch. Browser Node script TASK/browser.cjs uses prepared node_modules/browsers/tools with PLAYWRIGHT_BROWSERS_PATH and LD_LIBRARY_PATH. Native passed; initial installed failed existing low-disk guard. Actual intake/list/detail/log/download/report/index routes, controlled enqueue phase/output fixture and disabled auxiliary remote update check. Synthetic input/output bytes are not a real media scan/render. No P01 Save As APIs involved.

Benign fixtures only: spaces, apostrophes, quotes, ampersands, Unicode and literal entity-looking text. Initial upload fixture submitted folder\\name; multipart parser accepted foldername; this was a test expectation error, not product RED. Stable actual upload submitted folder/Family &amp; friends — café.mp4 and accepted Family &amp; friends — café.mp4. Existing normalizer unchanged. Exact exported-base RED confirms decoding errors on both emitted surfaces.


After supervisor recovered real /tmp free space above the unchanged 1 GiB guard:
- Native Python3.12: python -m pytest test_openscrub.py -k 'upload_cap_configurable_and_413_explains_the_way_out or server_path_intake_guard_precedes_size_lookup' -q --basetemp=TASK/tmp/resolved-full-routes:2 passed,132 deselected. This resolves the two environmental failures; it is not a second full-suite pass.
- Native actual Python3.9: python -m pytest tests/test_job_filename_display.py -q --basetemp=TASK/tmp/floor39-final:8 passed.
- Installed-only actual Python3.12: python -m pytest TASK/sdist/openscrub-1.0.96/tests/test_job_filename_display.py -q --basetemp=TASK/tmp/installed-final:8 passed.
- Final installed browser and final native browser both passed the same narrow actual-route flow. Browser harness now explicitly sets process.env.TMPDIR=TASK/tmp before requiring Playwright, and closes owned Chromium on assertion failure. Initial native successful browser used default /tmp transient profile (cleaned on normal close); final native recheck resolves that isolation gap. Direct Python server hooks were task-local in both initial/final runs. Initial installed assertion held browser open; owned session60205 was stopped after the recorded507 failure. Final browser exits0.
- Full supervised session15715 exit1 (55.31s;140 passed,2 environmental failures); affected resolution command exit0. Initial full session10580 exit143/cause unknown. Final installed server session73423 and native23590 cleaned up through their owned PTY sessions; no process-group kill or other-agent cleanup.
- git diff --check passed. Product commit f399ebe1bd3c17561b44c06f7169a61e21becb43; native clean after commit. Complete product change inspected; no runtime/test source changed after full-suite run.
