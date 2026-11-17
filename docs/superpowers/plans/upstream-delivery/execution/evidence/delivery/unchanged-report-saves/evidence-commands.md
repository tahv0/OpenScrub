# Task631 evidence command preservation (no rerun)

check_reopen.py contains the exact Python body copied from the already-executed
inline heredoc in this agent's tool history. It originally ran as `python -`
with stdout redirected to /tmp/openscrub-task631/reopen.log. The named .py file
was created afterward for preservation; it has NOT been run as a named file.
This is copied executed body text, not a reconstructed or newly validated check.
The prior browser fixture server was stopped before this fresh interpreter ran.

Original environment and equivalent reusable invocation:

```sh
cd /home/tahv0/.codex/worktrees/c832/OpenScrub
. /tmp/openscrub-baseline-20261116/env-opencv4.sh
export PYTHONPATH=/home/tahv0/.codex/worktrees/c832/OpenScrub:/tmp/openscrub-baseline-20261116
python /tmp/openscrub-task631/check_reopen.py > /tmp/openscrub-task631/reopen-rerun.log
```

The original invocation used the identical body via `python - <<'PY' >
/tmp/openscrub-task631/reopen.log`, not this newly named file. The original log
remains untouched. A future rerun should use a new output path, as above.
The check depends on preserved browser-job.json/browser-runtime synthetic media
and reports, actual active-source imports and the prepared baseline harness.
It checks a kept-region pixel in the first decoded frame only. It reopens and
verifies the already-rendered output; it does not itself launch another render.
The actual renderer was run previously by browser.cjs/serve_browser.py.

committed-bytes.log was written by the assertion block near the top of
/tmp/openscrub-task631/finalize_report.py, which remains preserved. Its actual
executed shell command was:

```sh
python3 /tmp/openscrub-task631/finalize_report.py
```

The complete exact script from the last execution is also frozen as
/tmp/openscrub-task631/executed-finalize_report.py. Its prefix checks pinned
result source SHAs, clean HEAD, each frozen source file against disk and Git,
installed engine/web/report/lifetime bytes, every recorded/warmup HTTP status,
file identities and final report hashes, and all instrumented publication/JSON
counts, before writing committed-bytes.log. The remainder generates the handoff
report/PR files; do not run it just to inspect the assertions, because doing so
rewrites those documents. This preservation task reran none of those assertions.

SHA256 of preserved bodies:
- check_reopen.py: d2f30873420fd3ff336e593e28924af391b618961a1dff6f1c092956d27722a8
- executed-finalize_report.py: 77ffdacaf660bbd9ae9cdb00103d380d5dd266975b3e19358048ce08feb114f9
