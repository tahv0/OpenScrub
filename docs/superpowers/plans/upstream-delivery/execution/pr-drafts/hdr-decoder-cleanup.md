# Close the HDR decoder pipe during partial cleanup

- Branch: pr/hdr-decoder-cleanup
- HDR-owned base: e21ebdf6e3ee46e6c65050dc956a9a3459152269
- Reviewed head: ded411cbec308333d1416ae3d58b4f6e918d7849
- Status: [merged as upstream PR#23](https://github.com/austinmabry/OpenScrub/pull/23) on 2026-11-19. This prepared description remains evidence; the user's submitted wording is authoritative. [Merge and Austin feedback](../submissions/hdr-decoder-cleanup.md).

When HDR rendering is cancelled or the encoder's first write fails, existing cleanup waits for both children, but decoder stdout can remain open while the caller retains the exception traceback. Close decoder stdout alongside encoder stdin in the existing partial-cleanup path. The production change is two added lines; the regressions retain the real exception and process owners while checking both pipes and child reaping. A successful ten-bit PQ/BT.2020 render is the preservation control.

This candidate is based on the separate shared test-only prerequisite `e21ebdf6e3ee46e6c65050dc956a9a3459152269`. That prerequisite changes four lines in the tracking handoff test: it checks post-occlusion sample existence while retaining the geometric rejection assertion. Relative to main at `5d3a15ae683c08f368d6ba4bd0d2d77b4e7b8e2f`, the raw comparison contains both that prerequisite and the four-file HDR change; they remain separate commits.

Validation: all three HDR cleanup cases and the shared handoff test passed on Linux CPU with Python 3.12.16 and Python 3.9.25, four passed with no skips in each run. Historical checks on the same source included 137 full-suite tests, 11 focused render/codec cases on each Python version, package build and installed startup, and a baseline/candidate success comparison. Source/pre-encoder equality and equality of baseline/candidate decoded lossy output are separate observations; lossy output differs from raw source. These results do not establish Windows, GPU encoder, or arbitrary native-call cancellation behavior.

[Current readiness and portable checks](../evidence/delivery/hdr-decoder-pr-readiness.md).
