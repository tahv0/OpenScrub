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

Composition tests exercise both lettering and confidence on the same report and preservation of explicit user choices. Native HDR tests check exact corner correspondence. A 120 fps encode verifies that a plate policy and a checkpoint must both authorize a frame before a narrow mask appears.

The initial integrated wheel passed the package byte audit and 77 installed tests on each of Python 3.12 and 3.9. A separate installed profile on loopback port `8391` completed a real synthetic scan, review, render and download, with 12 output frames independently counted. The preview has its own job store and uses available stock model files. The existing app and its jobs were kept out of the preview.

The next integrated candidate adds the sampled OCR and direct tracking workflow, the first checkpoint restart protection and compatibility repairs caught by the full suite. These continue from the frozen initial snapshot. [Submission of the separate scan-options fix](../../submissions/scan-options-validation.md)
