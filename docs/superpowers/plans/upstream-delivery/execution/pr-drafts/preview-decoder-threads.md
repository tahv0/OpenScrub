# Offer an optional decoder thread count for web previews

- Branch: pr/optional-preview-decode-threads
- Base: 5d3a15ae683c08f368d6ba4bd0d2d77b4e7b8e2f
- Reviewed head: 5ef9e644c3a80e72c8116ee2e5c49f8664f7fbcf
- Status: independently approved locally; private, awaiting its delivery cycle.

Concurrent high-resolution previews can make decoder memory expensive. Add --preview-decode-threads 0/1/2/4 for users who want to trade seek time for lower decoder memory. Default 0 preserves the original capture constructor without probing optional OpenCV capabilities. One private helper serves the four existing web capture sites; explicit settings are used only when the FFmpeg capture opens and reports the requested count. Unsupported or ignored settings release the candidate and fall back to the existing constructor.

Frame selection, crops, preview output, scan, render and tracking behavior retain their existing owners. The qualified comparison found lower sampled decoder RSS with slower long-GOP seeks; this is an optional tradeoff and carries no general speed or hard-memory guarantee.

Validation: 21 owning tests pass on each actual Python 3.12.16 and 3.9.25. The final sdist contains the strengthened tests and the wheel is byte-identical to the earlier tested wheel. Earlier checks on unchanged runtime bytes cover real H.264 consumers, evaluated PAGE/JavaScript, offline packaging and an installed configured service. The historical full suite reported 153 passed and one existing tracker-log assertion failure; this contribution leaves that test and engine unchanged. Its separate correction is in HDR PR #23.

Checks cover Linux CPU/OpenCV 4.14 and synthetic CFR media. Windows, GPU, other codecs and VFR/HDR remain unvalidated. No native-call cancellation or application-wide performance claim.

[Local acceptance record](../evidence/delivery/preview-decoder-threads-acceptance.md).
