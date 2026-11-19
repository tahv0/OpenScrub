# Invalidate stale review thumbnails after report and source changes

- Branch: pr/thumbnail-generations
- Declared base: 0788899563f1a9861fe94a16e167868d0644cf0c
- Reviewed head: 194864493962d9951cab482bde507d489f07c998
- Status: prepared locally; submission follows its source/lifetime prerequisites.

A box edit or report/source replacement can leave ordinary review crops and lightboxes showing old pixels. A late producer can also publish an obsolete image under a reusable URL. Bind metadata and JPEGs to the current source/report generation, share checked crop geometry between demand and pre-generation, and verify currency before publication or conditional HTTP responses.

Keep active source and image ownership through interrupted cleanup, admit existing-generation fills before cold parsing, and stop opportunistic pre-generation at stalled retirement. The browser versions its images and makes one coalesced metadata recovery attempt per mounted review. Equal indexed raw rows and complete groups can receive replacement images while drafts remain owned by the existing editor. Explicit retry/reopen handles failed loads or a spent recovery budget. Detection and category labels render literally, and card binding enumerates the review nodes once.

The shared recipe, image tickets and staging bookkeeping live in openscrub_internal/thumbnails.py. Existing entry points, report data, pretrained inference and redaction defaults are preserved.

Validation:

- Final head: 353 owning tests on Python 3.12.16 and 353 on Python 3.9.25; fresh offline source/wheel build, installed HTTP/defaults/CLI/updater and complete package-member checks.
- Five real Chromium page cases at e3c38f3; the final APP_JS/PAGE bytes are identical. The broader 860 native, 629 floor and three floor-video checks remain attributed to 3f66ad8.
- Real controls cover changed pixels, obsolete validators, interrupted source/stage/reader release, complete raw choices, integral decimal IDs, literal labels, retry/reopen and late callbacks.

[Technical acceptance and portable verification](../evidence/delivery/p08a-thumbnail-coherence-acceptance.md) records exact source attribution and limits. Native Windows/macOS, frozen binaries and large-video throughput/RSS are separate validation work. The reviewed application assembly is unchanged.
