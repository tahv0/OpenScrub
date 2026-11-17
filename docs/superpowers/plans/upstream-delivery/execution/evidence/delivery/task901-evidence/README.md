# Task901 evidence

Tooling candidate `afbd2078a292e4ba2ced55ffdc89fcacaa27502e` on `tools/local-verification`; documentation base `04677434d43d8acc54aebdcf9073db4d234f1ceb`.

- [Commands](commands.md) and [export/config generator](prepare_smoke.py); complete caller-frozen configs `product312.json`, `product39.json`, `installed39.json` bind 125 export files.
- [Final actual3.12 focused suite](green312-final.log), [final actual3.9 focused suite](green39-final.log): 16 passing each. [Initial RED](red.log), [source-default regression RED](source-default-red.log), [nested-parent regression RED](parent-import-red.log), and intermediate logs retain discovered setup mistakes.
- [Final package/installed CLI/listening HTTP transcript](package312-final.log), [server child log](listening-server.log), [package identities](package-identities.json), [preflight manifest](preflight.json).
- [Final source3.12](source312-final.log), [final source3.9](source39-final.log), [final installed3.9 CLI/defaults](installed39-final.log).
- [Small successful child output](fixture-success-output.log) and [nonzero child output](fixture-nonzero-output.log) retain stdout/stderr after fresh-root workloads; no browser/timing work was executed.
- `environment312.json` and `environment39.json` identify actual interpreters/dependencies and prepared tool paths/hashes. `identities.json` binds helper/evidence bytes.

Runtime exports/environments/builds/installs/fixtures remain under assigned ignored `runtime/task901`; they are not copied into evidence. These checks establish the new tooling's setup/package boundary, not renewed acceptance for product f44e0b7. D01 adoption remains pending the next real candidate and root's fresh review.
