# Optional plate confidence in Scan Setup

`optional/plate-confidence-setup` at `f79611a7fef6113d4f4a8d79aaf465bfeddb5201` follows the [optional CLI and API](optional-plate-confidence-runtime-acceptance.md).

| What | Why | When to deliver |
| --- | --- | --- |
| Keep Standard as the default and put the two experimental policies in advanced settings. Require an explicit cutoff when selecting either option. | Existing jobs should keep their settings while users can decide how many uncertain detections to handle manually or how much short automatic coverage to allow. | After the runtime policy is stable. Verify unchanged default requests, the controls at desktop/mobile widths, and live job intake. |
| Explain that Blur candidates uses the plate threshold and stores the separate cutoff for Review uncertain. | The lower candidate floor and two-observation automatic cutoff have different effects. Changing the stored cutoff alone does not change Blur candidates output. | Include with the Scan Setup controls. Verify validity and re-selection without presetting a cutoff. |

The final source passed 148 selected checks on each of Python 3.12 and 3.9. The exact installed wheel passed 51 checks and one Chromium job-admission flow on each version. The flow submits Standard as the original request and both optional policies with deliberate settings. It checks missing and below-floor cutoffs, desktop and mobile layout, and console health. Playwright was used because the Browser plugin was unavailable. The report retains the policy and explicit choices. Review-card labels are a separate change.
