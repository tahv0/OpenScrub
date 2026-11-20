# Initial checkpoint scan completion

`pr/checkpoint-first-completion` at `85afd5be58a90cb761955ba751d4d4aa0bb0e0c7` follows [bounded decoder cancellation](checkpoint-bounded-decoder-acceptance.md). A scan opted into checkpointing can now finish normally on its first attempt, with or without a prior Stop request.

| What | Why | When to deliver |
| --- | --- | --- |
| Read verified decoder EOF when Stop reaches the last reported frame and write a completed source identity, including when there are no detections. | An advertised frame count alone cannot distinguish a completed scan from a truncated or extra decoded tail. Manual-only scans may have a valid empty report. | After bounded cancellation. Run real native H.264 first-completion, final-frame Stop and terminal Cancel scenarios. |
| Parse configured audio redactions before the checkpoint scan and retain exact source and extent checks during completed render. | The checkpoint producer bypasses the ordinary pipeline parser. A completed report needs its explicit audio choices and its verified full frame range. | In the same producer PR. Exercise an altered source and an early render decoder with zero rows, with prior output intact. |

The final source passed 420 selected checks and the installed wheel passed 102 checks per interpreter on Python 3.12 and 3.9. A real QR fixture finished and rendered all 24 frames on an initial attempt. Cancellation during the terminal read preserved the prior paused report. This internal producer still needs integration with the app's operation owner and partial review authority before exposing controls.
