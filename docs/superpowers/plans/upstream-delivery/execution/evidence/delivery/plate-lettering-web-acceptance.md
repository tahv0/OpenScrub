# Optional lettering-only masks in Scan Setup

`optional/plate-lettering-web` at `61c755361c7fb7e7823dfc4c5589a5598cbfa357` follows the [native SDR lettering masks](plate-lettering-masks-acceptance.md). Advanced Scan Setup offers a default-off checkbox for the plate category. The report's saved mode governs later rendering and reopening.

| What | Why | When to deliver |
| --- | --- | --- |
| Send the explicit lettering mode through normal web job admission. Load the saved report's choice on render. | Users should be able to opt in from Scan Setup and keep their selected mode after restart. | After the standalone scan and render work. Keep the original job request when the box is clear. |
| Show the narrower mask trade-offs and package the guide. | Text localization can miss characters, the plate itself stays visible when the mask narrows, and inspecting each frame costs more. | In the same web PR. Verify the real controls on desktop and mobile and include a stock-model reopen and rerender scenario. |

The final source passed 151 selected checks and the installed wheel passed 69 checks plus a live Chromium admission check on each of Python 3.12 and 3.9. A real web scan, saved report reload, and render used stock YOLOv9-T and PP-OCRv5 on the four-frame synthetic native SDR fixture. The output covered all 1,080 marked strong glyph pixels per frame and preserved a visible plate-paper sample on narrower frames. Transcoding the source invalidated the old exact pixel evidence and forced ordinary full plate boxes where a plate was already located. This is an opt-in native SDR/CFR result, with HDR or unverified frames using normal coverage.
