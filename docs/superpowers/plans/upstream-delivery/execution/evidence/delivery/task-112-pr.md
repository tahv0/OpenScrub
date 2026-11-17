# Skip chronological OCR history before each detection tail

Base: `e21ebdf6e3ee46e6c65050dc956a9a3459152269`  
Head: `952af20da205133886ba69799e134b86d1654137`

`merge_detections` restarted OCR history for every text span, including timestamps before its last sighting. Build one validated local timestamp index for reused chronological histories and begin each tail walk with `bisect_right(last_seen + .01)`. Keep the original support walk and fallback for unordered, unsupported or malformed input; single-region histories avoid index construction. Matching rules, Detection fields and defaults are preserved.

The detector-consistent sparse fixture (10,000 scans / 30 detections) measures complete merge calls including construction: median **12.272 → 3.384 ms (−72.42%)**, with 85,176 bytes of timestamp-list references. Tiny-case differences are not claimed as gains; the original repeated control's **+27 µs / +1.97%** observation is retained alongside the complete corrected four-case repeat. This measures merge/tail work, excluding inference and other scan-finalization stages.

Validation: one full discovered suite passed **153 cases** before test-only strengthening; final focused checks passed **27 cases on Python 3.12 and 3.9**, and final semantic controls passed **20 cases on the exact base**. Includes real `run_scan` → report with controlled OCR, complete-record equality in all measured calls, offline sdist → wheel, exact packaged control/runtime bytes, installed CLI/web smoke and unchanged parser defaults. Runtime bytes stayed identical throughout.

[Full report and evidence](task-112-report.md). Draft only; no PR published.
