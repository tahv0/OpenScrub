# Optional plate confidence decisions

`optional/plate-confidence-policy-core` at `375c22a54abb2f84a9f7d6557415a5c7fd04632c` implements the [approved decision rules](../research/optional-policy-contract-research.md) as an isolated evaluator. The ordinary case uses the existing saved output.

| What | Why | When to deliver |
| --- | --- | --- |
| Require two independent cutoff-eligible observations for the manual-review policy. In the aggressive option, permit a single floor-eligible observation with usable geometry. Preserve explicit Blur and Keep choices and identify unsupported positions. | A single confidence spike can briefly mask the wrong region. Users also asked for an option that favors retaining short matches. | First evaluator slice. Capture real observation evidence at the scan boundary before wiring decisions into output. |
| Validate scores, geometry and configuration without promoting synthetic or repeated same-frame boxes to evidence. | Smoothing copies scores and geometry, so a large group can otherwise look more certain than the actual observations. | Test the decision cases first, then compare default and opted-in output on real encoded sample clips. |

Both Python versions passed 19 focused and 19 installed checks. A separate synthetic stock YOLOv9-T inference probe produced scores of 0.485 on a clean plate, 0.159 under partial shadow and 0.469 in the dim fixture, with no detection in the blank control. These are reproducible examples for choosing test cases. Runtime parameter selection and calibration remain separate. The pinned stock PP-OCRv5 probe for lettering masks covered all measured strong strokes in three clean or inverted controls and selected fallback for four difficult crops.
