# Optional plate confidence and continuity runtime

`optional/plate-confidence-policy` at `3da2d7f3b6b50ab9225b4aff34389168c4059718` follows the [isolated evaluator](plate-confidence-evaluator-acceptance.md). The CLI and job API accept the explicit policy and cutoff. The ordinary web controls and suggestion labels remain open.

| What | Why | When to deliver |
| --- | --- | --- |
| Capture the direct plate observation's source index before smoothing. Keep synthetic rows from counting toward confidence or supplying a new mask position. | One unlikely detection and its copied samples can otherwise resemble a long-lived target. | After the pure evaluator. Verify actual scan, report reopen and encoded output for both optional modes. |
| Preserve intentional Blur and Keep choices when falling back, correcting geometry or switching modes on an optional report. Validate intake and require a matching source on replay. | The user needs to leave weak results unhandled and make independent choices without the program reapplying an earlier policy against the wrong video. | Review the intake and report transaction after the output path. Test old reports and stock behavior at the same time. |

The final source passed 448 tests on each of Python 3.12 and 3.9, including the loopback cases. The rebuilt installed wheels passed 66 checks on each version. The opt-in has two modes. Review uncertain requires two consecutive eligible direct observations before masking. Blur uncertain can mask after one eligible retained detection. Both retain user choices and valid frame geometry. The ordinary absent/off scan path and default report shape remain available.

The same final source was tested using the pinned stock YOLOv9-T model on a 16-frame synthetic clip at 8 fps. With an explicit 0.10 candidate floor and 0.48 control cutoff, the manual policy masked frames 6–8, and the candidate policy masked frames 2, 5–8 and 11–13. Each listed result covered more than half of the measured ROI. The ordinary control did so on all 16 frames. These observations describe one fixture and do not establish a production cutoff or decrease in unwanted masks across arbitrary footage.
