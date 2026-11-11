# Persistent runtime error logging

Goal: make overnight worker failures diagnosable without changing learning or
redaction policy. Scope: web runtime, subprocess diagnostics, build inclusion.
Use a stdlib logger with a rotating persistent sink and independent stderr sink;
a stable faulthandler file; an unclean-exit marker; bounded-frequency progress.
Keep all source clips, annotations, model candidates and review reports intact.

Validation: injected failures at worker, learning, HTTP, preview, model download,
preflight, trainer subprocess and thread boundaries; actual native abort in an
isolated child; file rotation/disk-error fallback; context/token redaction; both
plain integration source and user-installed coverage-recovery source compatibility.
Existing CPU/browser tests are environment-dependent and all limitations must be
reported. No independent reviewer agent or access to Windows/NVIDIA/user footage.

Rulings: no promise that SIGKILL/OOM/power loss can log; no new frame decoding for
logging; no frame-level log writes; keep exact trainer output in its existing
pass log; avoid request payload/header/query capture. Retain current UI state
handling and expose diagnostics through console/files rather than UI redesign.

Publication integration (2026-11-11): rebase both prepared local changes onto
08f432b while retaining portable learned models, section guards, and resilient
progress polling. Keep the current structured trainer-output reader and final
drain. Feed real progress (not polling liveness) into diagnostics. Persist and
validate the optional recovery margin in model-library metadata and inference;
legacy models without the field retain zero extra margin. Added regressions
cover policy preservation/rejection, section bounds, and heartbeat semantics.
Publish via a pull request into integration/all-prs; main is not a target.
