# Task119 compact evidence

Literal filename display correctness only. Exact base/head and source identities: source-manifest.json. Complete commands/isolation/attempt notes: commands.md. Human report and local PR draft are one directory above.

- RED: red.log(initial fixture expectation), red-stable.log(actual four display failures), exact-base-red.log(independent exported-base control).
- GREEN: green.log(native8), floor39-final.log(actual3.9 owning8), installed-final.log(installed owning8).
- Full: full-incomplete.log(exit143, unknown cause); full.log(140passed/2low-disk failures); resolved-full-routes.log(the2failures pass after real disk recovery). disk-refusal.json and temporary-storage-recovery-119.json retain the environmental boundary.
- Package: package-build-missing-tomlkit.log, build-tools.log, package-build.log, install.log, package-smoke.{log,json}. Archive/package SHA256 and exact source/test bytes are asserted; wheel built from extracted sdist. No package/environment/export trees retained here.
- UI: evaluated-page-*.js/js-parse.json; final native/installed browser JSON/logs, server logs, and desktop/mobile PNGs. Actual intake/list/detail/download routes; controlled worker done/output fixture. Initial browser records retained separately; initial installed low-disk failure retained.
- Reproducibility: source hashes, product.diff, owning test copy, task harness/env/server/browser/package scripts. Final task-local Node TMPDIR explicitly set; direct Python sitecustomize guards are retained.

No media, user data, environment, installed target or exported source tree is included. file-manifest.json binds retained evidence bytes.
