# Save As progress: private PR readiness

The unchanged candidate pr/save-as-progress atca0f2ce7458347afd2e6156a97df580b6623767a is independently approved for private readiness on its original Austin parent5d3a15ae683c08f368d6ba4bd0d2d77b4e7b8e2f. [HDR PR#23 has now merged](../../submissions/hdr-decoder-cleanup.md); Austin's feedback supports focused PRs and main has advanced to50c5a9e/v1.0.97. The checks below retain their old source attribution. Refresh Save As privately against the actual accepted baseline before submission.

The existing Save As donor displayed a static Saving message. This contribution adds feedback for the redacted video and audit report: bytes count after each destination write completes, a valid response length enables a total and approximate remaining time, unknown totals stay indeterminate, stalls show waiting, and Saved follows successful close. Direct Download remains available. It preserves output generation, redaction behavior, existing streaming routes and upstream defaults.

| Verification | Source and result |
| --- | --- |
| Current owning suite | 24 passed on Python 3.12.16 and 24 passed on actual Python 3.9.25, each exit 0, on a frozen nine-file export matched to the accepted Git objects before execution. |
| Runtime identity | Both canonical runs configured application paths locally and identified the five selected modules. Explicit Node prerequisite, source hashes, interpreter versions, preflights, workload commands and exits were verified. Existing prepared environments were inputs; this establishes no OS sandbox or complete environment-write inventory. |
| Historical full suites | Required combined and default discovery each reported 157 passed and one unchanged tracker-log assertion failure. Its separate test correction is in HDR #23. This readiness run did not repeat or relabel those suites. |
| Historical package | Retained sdist and wheel match the accepted Git: 25 source members, 11 wheel runtime/data members, all 16 hashed RECORD entries plus the unhashed RECORD self-entry, and Python >=3.9 metadata. No rebuild. |
| Historical browser scenario | Real loopback HTTP to a controlled picker backed by an origin-private writable in headless Chromium saved exactly 268,435,456 bytes. One destination write was in flight; the app reader was at most 2,097,152 bytes ahead of accepted writes. Browser-internal network buffers were outside that measurement. Waiting and Finalizing preceded successful close and Saved. |
| Historical memory observation | Maximum sampled JavaScript heap plus backing storage was about 84.8 MiB. No whole-browser RSS, throughput or physical-durability claim. |

Independent readiness review found no critical or important issues. Its three minor wording qualifications are incorporated above. The actual source remains unchanged.

The browser scenario was not replayed for freshness. Native picker interaction, Windows permissions, other browser engines, multi-GB exports, physical disk durability and OpenCV 5 remain unverified. Current Python 3.9 coverage is the focused suite, not a new installed-package or whole-application claim.

With project dependencies and Node 18+ available, reproduce the owning suite from the topic checkout:

    python -m pytest tests/test_export_save_as.py -q

Retained archive SHA-256 values: sdist 45629ac9dc852131b4655e50512a459e2c4241af8d2aace4c2830314c2db5cc9; wheel 513e3ae0efc3f9fd14aee7a1ffde1d4097b8de9c996353ecee0183de9dee4daf.

[Prepared PR description](../../pr-drafts/save-as-progress.md). C01 composition and working-version adoption remain separate.

## Next private refresh

Preserveca0f2ce and create a separate candidate from50c5a9e. Keep upstream's1.0.97 version, full-discovery contributor command, HDR regressions, tracker geometry assertion and sdist-only tests/contributor files. Reconcile only CONTRIBUTING.md and pyproject.toml overlap; the upstream web implementation and zones_ui.py are unchanged. Verify Save As web/tests/README bytes againstca0f2ce.

Run one fresh full native discovery (expected161: upstream137 plus24 Save As cases; verify the actual result and no HDR skips), the24 owning cases on actual Python3.9, evaluated joined PAGE, and fresh offline sdist-to-wheel/installed checks. Matching UI and route bytes can justify retaining the historical256MiB browser scenario at its original pin and limits. The old tracker-log failure is historical; do not carry it forward as an accepted failure after its upstream correction. No refresh execution or second submission is claimed here.
