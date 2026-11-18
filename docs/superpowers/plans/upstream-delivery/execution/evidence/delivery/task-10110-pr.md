# Make optional media test evidence output portable

The retained exact-media and strict-route tests can complete their production assertions and then fail with `KeyError: VERIFY_RUN` when run with only the documented media opt-in. Add a small test-only directory helper that uses pytest's temporary directory when the output setting is missing or empty, while preserving explicit `<VERIFY_RUN>/logs` output, original JSON filenames, and payloads.

Migrate exactly three evidence writes across the two owning modules. Six helper cases exercise directory creation, missing/empty/explicit settings, independent outputs, idempotent reuse, and filesystem errors. No application code, defaults, assertions, dependencies, or packaging settings change; the helper ships in the existing tests sdist include and stays out of the wheel.

Validation: actual prior failure reproduced in all seven retained-media cases; focused 3.12 fallback 48 passed; frozen normal native suite 566 passed; actual Python 3.9 affected fallback and explicit output each 48 passed; offline native sdist → extracted source → wheel, installed identities/defaults and both CLI help checks passed. Four owned file bytes verified in the sdist and extracted source.

Depends only on the owning exact/strict tests at `6fde5ad60c6d78d69dbbd8e049a9196f15e4095f`. Local draft candidate `d3d02770b8a42575236b11309b5a334170f7ec89`; independent review pending. No push, PR publication, merge, or working-version adoption.
