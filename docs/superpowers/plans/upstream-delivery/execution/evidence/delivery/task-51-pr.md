# test(web): pin preview cache headers over configured HTTP

Preview snapshots intentionally omit Last-Modified and use content ETags, but the existing HTTP tests did not pin date-only conditional requests. Add two regression cases using valid old/future If-Modified-Since dates. Through the existing production Cheroot fixture, both requests must return the complete200 JPEG, correct length, unchanged ETag, and no Last-Modified header (compared case-insensitively).

This follows reviewed P05 before upstream submission. Only `tests/test_live_preview.py` changes; existing304, Range, If-Range and changed-ETag coverage remains intact. Production/cache policy, dependencies, metadata, recipe bytes and defaults are unchanged.

Validation: complete owning file28pass on actual Python3.12.16; exact new cases2pass on actual Python3.9.25; Python3.9 grammar, diff check, recursive sdist inclusion and all113 other tracked files byte-identical to the P05 base. No new package/browser/full-project run is claimed. Full local commands/identities and limits: `task-51-report.md` and `task51-evidence/`.

Base: `b70d42011168192cdf7a9ef93a5e9419a92a1cdb`. Candidate: `ac0f5e4661701e954e04dbc95eb00d9317c04cc6`. Draft only; independent review and upstream publication remain separate supervisor steps.
