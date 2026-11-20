# Bounded detached-plate text search

`optional/detached-plate-search-core` at `0d1de02e7627c62961fb0caa3fea6e9f06f4504e` places the accepted literal matcher and a stock Tesseract adapter on the clean application base.

| What | Why | When to deliver |
| --- | --- | --- |
| Read native-resolution tiles and a bounded set of classical contour crops on explicit CFR sample indices. Match full literals or explicitly marked fragments and retain the geometry of the entire matched token. | A loose or displayed plate can be outside the vehicle detector's results. Full-frame sparse OCR can miss bordered lettering, and a full-image reduction can lose small targets. | First downstream OCR slice, before the ordinary exact-editor action. |
| Mark results as suggestions with approximate geometry and explicit sample coverage. Keep raw query strings out of subprocess arguments and diagnostics. | Matching text can belong to another object. The user needs the location and its limits before choosing an edit or Track seed. | The app integration supplies source lifecycle, cancellation, job-owned temporary storage, and view ownership. |

175 selected tests and 36 installed-wheel checks passed on each Python version. Actual Tesseract 5.5 found full and fragment queries on encoded wall and skewed-ground samples, plus a 210×52-pixel plate in a 4K sample using 12 native-resolution tiles. Blank controls had no hits. Other matching text can be suggested, and an occluded fragment probe produced no hit. The search reports completed sample indices. The source guide is in the checkout and belongs in the distribution once the app action is available.
