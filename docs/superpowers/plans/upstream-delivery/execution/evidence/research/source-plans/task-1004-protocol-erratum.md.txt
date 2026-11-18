# Task1004 exact-sample policy erratum

This binding correction supersedes the API-table policy literal in exact-editor-ui-source-plan.md, exact-editor-ui-implementation-plan.md and task-1004-brief.md. Their original dispatch bytes remain preserved for attribution.

The accepted07cfaa9539a2561c26b6f7280fae6702eb07137c backend defines POLICY = 'opencv-ffmpeg-zero-cfr-v1' at openscrub_internal/exact_samples.py:16. The UI must validate and retain exactly that value in sampled geometry, manual creation and strict Track preconditions. The 'cfr-index-v1' value in the plan is incorrect. Do not rename the backend, accept arbitrary policy values, substitute a default or weaken exact admission.

What/why/when: apply this correction during Task1004 development before final PAGE/floor/package acceptance. Actual PAGE fetched HTTP200 exact samples, but the plan-derived validator refused their real policy before decode. Retain those attempts as plan/fixture mismatches, not backend regressions. Fix the client and VM fixture against the immutable accepted source, and retain a negative control rejecting the incorrect policy. Final actual HTTP/PAGE evidence supplies the positive wire check.

Root verified the immutable source directly and issued the binding correction to the sole implementer. No backend, engine, model, decoder, report schema or upstream default change is authorized by this erratum.
