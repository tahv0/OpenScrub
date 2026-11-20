# Combined local OpenScrub branch

`integration/current-work` was created at `f322e2ddc71bf3265fd814d339e3cb4de3afd02d` from the clean `integration/upstream-focused-candidate` at `9db95db`. It brings the completed work together for local use. The individual topics remain the source of focused upstream PRs.

| Work retained | Source topic |
| --- | --- |
| Generic v1.0.97 long-video, editor, report and export work | `integration/upstream-focused-candidate` |
| Exact-frame plate text search | `optional/detached-plate-search` |
| Optional confidence choices and review labels | `optional/plate-confidence-review` |
| Optional native SDR lettering masks | `optional/plate-lettering-web` |
| Manual corners on verified SDR and supported HDR sources | `pr/manual-plate-corners-hdr-setup` |
| Checkpoint engine and staged web publication owner | `pr/checkpoint-web-publication-owner` |
| Default-off preview decode threads and bounded lifecycle diagnostics | `pr/optional-preview-decode-threads`, `pr/optional-runtime-diagnostics` |
| Video-sampled plate search and direct, confirmed Track | `optional/detached-video-search-controls`, `optional/detached-suggestion-track` |
| Stop, edit, restart and continue a supported native scan | [Checkpoint app topics](checkpoint-app-integration.md) |

Composition tests exercise both lettering and confidence on the same report and preservation of explicit user choices. Native HDR tests check exact corner correspondence. A 120 fps encode verifies that a plate policy and a checkpoint must both authorize a frame before a narrow mask appears.

The initial integrated wheel passed the package byte audit and 77 installed tests on each of Python 3.12 and 3.9. A separate installed profile on loopback port `8391` completed a real synthetic scan, review, render and download, with 12 output frames independently counted. The preview has its own job store and uses available stock model files. The existing app and its jobs were kept out of the preview.

The integrated app at `474b625` passed 117 checkpoint, plate and ordinary-job regressions on each of Python 3.12 and 3.9. Each installed wheel run passed seven cases across Chromium and actual local HTTP. The native checkpoint test stops a generated 24-frame clip after seven frames, restarts the job registry, saves a manual region and mute span, resumes, inspects a later exact frame, and renders all 24 frames. The separately launched preview also completed a normal synthetic job and counted 12 exported frames.

An earlier full run at `6651913` passed 3,338 tests on Python 3.12. Python 3.9 passed 3,337 with one intermittent response-ownership assertion. All 23 tests in that file passed when rerun at the same commit. The 117-case gate targets the later checkpoint and plate integration.

The preview is available at [http://127.0.0.1:8391/](http://127.0.0.1:8391/), with an isolated job store. The combined branch is for local testing. [Submission of the separate scan-options fix](../../submissions/scan-options-validation.md)
