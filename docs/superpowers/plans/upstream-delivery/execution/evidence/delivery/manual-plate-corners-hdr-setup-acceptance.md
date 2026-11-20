# HDR plate-corner verification in Scan Setup

`pr/manual-plate-corners-hdr-setup` at `cd8fb26326f3677f5350ba3d12c98feafe27d548` follows the [actual HDR editor and renderer](manual-plate-corners-hdr-acceptance.md). The checkbox is off by default in Advanced Scan Setup and sends the existing option only when selected.

| What | Why | When to deliver |
| --- | --- | --- |
| Expose the existing HDR frame-verification option through normal web job admission. | The renderer can use an inspected four-corner mask on a fully matched 10-bit original. Users need an explicit choice because obtaining that proof takes extra work. | After the native proof and actual HDR pixel tests. Verify the unchecked request is unchanged and the checked request preserves every prior option. |
| Explain supported fresh PQ/HLG timebases, lost live proof after restart, and the ordinary full-box fallback. | Geometry from a preview copy must only narrow the original when its frame correspondence is established. | In the same setup PR, with a true 10-bit encoded output check and regressions for lost proof, changed source and early EOF. |

The final source passed 142 selected checks and the installed wheel passed 60 checks plus the real Chromium upload and admission flow on each of Python 3.12 and 3.9. Upload tests initially hit the application's existing 1 GiB reserve on the test filesystem. After releasing completed synthetic outputs, the exact source and installed gates passed in fresh fixture directories. The reruns used the ordinary application storage settings.

The checkbox and proof are opt-in. This branch keeps the existing live proof rules for supported progressive 10-bit CFR originals and the existing separate route for verified SDR and normalized render inputs. A restarted job without its live proof, a changed source, or an unverified transform uses the normal fallback.
