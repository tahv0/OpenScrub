# Stock plate lettering-region localization

`optional/plate-lettering-guard` at `202fba8b3be91caa42e4936a35dba6321a0c1590` restores the stock PP-OCRv5 plate region calculation and its one-pass component check from the reviewed donor path.

| What | Why | When to deliver |
| --- | --- | --- |
| Find separate lettering regions inside a supplied plate crop. Check contrast, clipping, geometric ambiguity and residual strokes. | A tight optical proposal may leave visible lettering when it is too dim, occluded or clipped. | As the first optional guard slice, before applying masks to any output. |
| Count component coverage in one pixel traversal and compare it to the earlier implementation. | Repeated full-crop scans on noisy input consume time while checking equivalent overlaps. | Report this as a guard measurement. Historical and local synthetic loads say little about overall video time. |

149 selected tests and five installed tests passed on each Python version. The localized synthetic model probe used the pinned 4,826,518-byte PP-OCRv5 detector and measured complete coverage of strong-stroke pixels on three accepted crops. Four difficult crops used fallback. The guard-only equivalence benchmark compared 7 base and 24 modified crops. Its largest noisy example measured 486.1 ms before and 14.9 ms after in one local run. Frame-bound scan and render integration is the next slice. The exact regions still require their own review because character shapes may carry recoverable information.
