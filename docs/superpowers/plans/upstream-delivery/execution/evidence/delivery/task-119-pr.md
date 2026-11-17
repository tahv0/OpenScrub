# Preserve literal filenames in the job list and title

Local PR draft only; not published. Base `e21ebdf6e3ee46e6c65050dc956a9a3459152269`; head `f399ebe1bd3c17561b44c06f7169a61e21becb43` on `pr/literal-job-filenames`.

An accepted filename such as `Family &amp; friends — café.mp4` previously displayed as `Family & friends — café.mp4` in the ordinary job link and detail heading. Escape those two HTML text interpolations with a small local helper so the visible and accessible filename stays literal. Existing basename normalization, metadata, job selection, layout and ordinary download names remain unchanged.

Adds eight emitted-JavaScript/intake/download regression cases under `tests/`, includes them in the sdist, and updates contributor test discovery instructions. No new runtime dependency or product module. No P01 Save As/P02 choices work.

Validation: benign exact-base RED on both sinks; native/floor Python3.9/installed owning8passed each; complete discovered suite140passed and2environment507 failures, then those2tests passed after real /tmp headroom recovery with no disk stub. Both evaluated PAGE scripts parse. Offline sdist→extracted-sdist wheel, exact source/test bytes, Python>=3.9 metadata, unchanged full parser defaults, installed CLI/web smoke and native+installed actual affected Playwright flow pass. Browser checks cover upload/server accepted names, accessible text/structure, A→B→A ordinary list switching and unchanged video/report download names/bytes at desktop width; mobile checks cover the selected title and layout only. Worker phase/output is a labeled synthetic fixture, not a real scan/render.

Limits: initial full attempt exited143 without a summary (cause unknown); low-disk failures and corrected harness/build attempts are retained. Only harmless text fixtures; no executable-filename probe or exploit/security certification claim. Fresh review and any adoption remain supervisor-owned. See [full report](task-119-report.md) and [evidence](task119-evidence/README.md).
