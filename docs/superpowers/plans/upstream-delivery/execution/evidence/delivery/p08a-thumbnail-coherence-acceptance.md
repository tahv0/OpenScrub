# P08A thumbnail coherence: local acceptance

- Accepted branch: pr/thumbnail-generations
- Reviewed head: 194864493962d9951cab482bde507d489f07c998
- Declared comparison base: 0788899563f1a9861fe94a16e167868d0644cf0c
- Prerequisite: [vault/source continuity](vault-source-continuity-acceptance.md), on the reviewed source/report/lifetime lineage.

The whole contribution received independent review and scoped repair checks. All named P08A findings are closed; the final check approves specification and quality with no open Critical, Important or Minor findings. This is local contribution readiness. Upstream submission, composition with the reviewed application and working-version adoption remain separate.

## What changed and why

- Derive ordinary review images from a current source/report generation. Demand and pre-generation share checked ordinal crop geometry; late or obsolete fills cannot publish current images.
- Check generation and verified JPEG bytes before a current conditional response. Matching validators for an obsolete generation receive the obsolete response.
- Keep source reservations, stage writers and image readers owned until release or indexed cleanup. Release contributions by identity so an interrupted retry cannot consume another request's ownership. One and two interruptions before secondary release-ticket registration preserve the first exception, drain both reservations and permit later access and deletion.
- Use the existing file/source owner for cleanup. Only proven owned current-process artifacts may be removed; media aliases, replaced leaves and unknown earlier artifacts retain their protection. Four active fills, one retirement barrier and bounded cleanup batches limit admitted work.
- Reserve existing-generation work before expensive cold parsing. Shared stalled retirement ends opportunistic pre-generation; its log describes images ready, including warm reads.
- Version crop and lightbox URLs. One coalesced metadata recovery attempt per mounted review can patch equal full raw rows at the same index with unchanged complete group membership. Pending decisions, manual additions, audio, selection and editor ownership remain intact. Failed replacement preserves the current review; visible retry/reopen handles initial errors and spent recovery.
- Render detection/category labels as literal text and bind the image constructed for its card. Enumerate card and heading nodes once. The synthetic 80-card control checks operation counts; it establishes no wall-clock speedup.
- Validate consumed metadata consistently across metadata and both image endpoints. Finite integral JSON IDs such as 7.0 and -1.0 remain usable, with original report bytes and fingerprints preserved. Opaque additive fields survive.

The private openscrub_internal/thumbnails.py module earns its boundary through shared geometry, tickets, staging and validator bookkeeping. Existing web/source/lifetime owners retain orchestration and authority. Entry points, pretrained inference, report choices and upstream redaction defaults are preserved.

## Verification and source attribution

| Check | Tested source | Result |
| --- | --- | --- |
| Four complete thumbnail/browser/save owning files, Python 3.12.16 | 1948644 | 353 passed |
| Same complete owning files, Python 3.9.25 | 1948644 | 353 passed |
| Fresh source → extracted wheel → install; real HTTP/defaults/CLI/updater | 1948644 | Passed |
| Complete package-byte checks | 1948644 | 50 tracked sdist, 49 updater, 21 installed wheel members; three Docker COPY checks |
| Real Chromium page file, including literal/group/retry/reopen ownership | e3c38f3 | Five passed; final APP_JS/PAGE source segments are identical |
| Broad native discovery, including the prepared real page | 3f66ad8 | 860 passed |
| Broad affected Python 3.9 selection | 3f66ad8 | 629 passed |
| Python 3.9 streamed-video ending controls | 3f66ad8 | Three passed |

The final correction also preserves the complete engine, lifetime-accounting, exact-sample and zone source bytes from e3c38f3. The two new regression cases fail on that predecessor and pass at 1948644; five focused ownership controls pass. A separate source audit compared all 139 committed/live source files, test/module/prerequisite identities and packaged bytes.

- Final source archive SHA-256: fc1f11aa0ea0a8113674e0dce1ae90d006de5e3d858c11546ada4e51a3dd3ec3.
- Final wheel SHA-256: 19dd83fdf4a171ed9c037cb956e79068456e0e621644e0fad98e5e0fd7665a2f.

The wheel comparison excludes pip's rewritten RECORD. Source-archive extraction and every eligible updater member were compared with their committed source. Installed HTTP covers metadata, crop, detframe, integral decimal IDs/raw fingerprints, strong and weak current 304, obsolete 409 and delivered DOM bytes.

Earlier 1k/10k observations remain attached to 944f6df. Its metadata samples used active tracemalloc, and its saved report size was collected after a choice-save reformat. They do not establish uninstrumented latency, the original timed-input byte size, RSS, p95 or a cache speedup for this final head.

## Portable verification

Prepare the project's runtime/test dependencies and FFmpeg/OpenCV tools in a supported environment. The recorded runs used OpenCV 4 with a prepared pretrained face model and test media. The separate OpenCV compatibility contribution retains its own installer/platform scope.

From the checked-out candidate:

    python -m pytest tests/test_thumbnail_io.py tests/test_thumbnail_primitives.py tests/test_thumbnail_browser.py tests/test_review_save_failures.py -q
    python -m build

For normal complete discovery:

    python -m pytest test_openscrub.py tests -q

The latter is a contributor recipe; the table above gives the actual broad-suite pin. Optional exact-media controls require their documented fixture manifest.

For the real page, supply an already prepared Node, Playwright module and Chromium, then run:

    export OPENSCRUB_PLAYWRIGHT_MODULE=/path/to/node_modules/playwright
    export OPENSCRUB_CHROMIUM=/path/to/chromium
    export OPENSCRUB_BROWSER_ARTIFACTS=/path/to/local/test-artifacts
    python -m pytest tests/test_thumbnail_page.py -q

Without those browser inputs the optional page tests skip; a skip does not establish browser acceptance. The installed-package check must import the installed wheel, serve loopback HTTP and compare the delivered code with the candidate; a source-checkout import is insufficient.

## Limits and next delivery stage

The evidence covers managed in-process changes and the exercised Linux hosts. File observations do not certify arbitrary external writers preserving all observed attributes, weak platform identities, permanent lock failure, OOM recovery or total erasure. Unknown earlier artifacts are preserved under the declared ownership policy.

Coarse report invalidation and the single automatic recovery budget can require explicit reopening after a save; pending drafts remain preserved. Native Windows/macOS, frozen binaries, production playback/render and large-video latency/RSS need their owning checks.

P08B starts with representative read-cost/memory measurement before selecting a cache. C01 must bridge this image-generation owner with P09's fetch/body slots, Blob URLs and virtualized card disposal while preserving hidden choices and held saves. Neither integration nor adoption follows from separate candidate acceptance.

[PR description](../../pr-drafts/thumbnail-coherence.md) is the reviewer-facing summary.
