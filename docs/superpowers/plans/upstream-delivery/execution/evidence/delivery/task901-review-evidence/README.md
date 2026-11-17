# Task901 independent review probes

Review target: base `04677434d43d8acc54aebdcf9073db4d234f1ceb`, head `afbd2078a292e4ba2ced55ffdc89fcacaa27502e`.

One tiny dummy-source run tested ordinary file-based adapter import selection. The controller and guarded workload used actual Python3.12.16. The controller used `-I` to isolate its own imports, as allowed by its controller/runtime split; the workload used normal guarded startup. No product module, pytest suite, build, package or network workload ran. The source manifest was frozen before invocation.

- [Replay recipe](probe.py): equivalent reconstruction of the executed inline stdlib driver; use a new UUID run. It creates only tiny dummy fixtures under the assigned Task901 root. It was not rerun for evidence packaging.
- [Raw direct-script transcript](script-origin-transcript.log): actual retained stdout/stderr. `ACTIVE_SOURCE` identifies frozen `source/sample.py`; the workload prints an import from `adapter/sample.py` and exits0.
- [Argument probe output](argument-probe.log): retained tool-output observations of the pure `python_command` function. Neither pytest nor the bypassed interpreter was executed.
- [Frozen config](config.json), [selected source](selected-sample.py), [conflicting sibling](adapter-sample.py), [adapter](adapter-probe.py).
- [Identities](identities.json): helper byte identities checked against implementer manifest, exact source/config/transcript hashes, expected base/head and actual runtime executable/version. No Git state mutation or runtime tree is included here.

Original owned runtime scratch remains `runtime/task901/review-09753b19932d4c9a9433784fe72e6181` for inspection. These probes supplement retained owning tests only for the two named untested review doubts.
