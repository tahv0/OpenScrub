# Cache-first review previews implementation plan

Goal: existing valid plate previews remain immediately usable even while another
finding is decoding; missing previews retain bounded on-demand generation.

Architecture: read validated, atomically published disk crops before acquiring
the decoder gate. Use the cache lock for cache reads/publication and vault
locking, never holding it while waiting for decoder work. Add a cache-only
thumbnail request and a small independent browser cache-read queue; retain one
cold decoder request. Keep source/frame/geometry token checks and no-store HTTP.
No stale or unverifiable crop may be used to place or save a mask.

Files: openscrub_web.py, test_review_performance.py, test_review_browser.py.
No decoder, scan engine, training, dependency or Docker changes.

- [x] Reproduce cached-hit rejection under a busy decoder, duplicate report reads,
      and cache-only misses accidentally triggering decoding.
- [x] Add cache-first reads, cache-only responses, vault/read synchronization,
      and pass the already-loaded report into the plate path.
- [x] Add a three-request cache queue independent of the single decode queue.
      Keep existing image until a replacement decodes successfully; clean up
      queued/active tasks and blob URLs on review teardown.
- [x] Verify invalidation, corrupt/missing cache, vault lock, warm reuse,
      request limits, real HTTP browser interactions and regression suites.
- [ ] Publish to integration/all-prs via a verified PR; leave main untouched.
