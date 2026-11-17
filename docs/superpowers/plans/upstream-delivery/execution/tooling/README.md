# Local verification setup

`verify.py` is a stdlib controller for an already prepared environment. It checks caller-supplied identities, allocates one owned run, starts the selected Python with shared isolation, and optionally builds an offline sdist → extracted source → wheel → installed target. It installs only the resulting product wheel into that run. It does not install dependencies, choose tests, schedule timing, switch branches, or reuse passing results automatically.

Keep `verify.py`, `verification_hook.py`, and `sitecustomize.py` together. Source the prepared environment named by the live handoff when native dependencies need its library/tool paths, then supply explicit configuration. The helper discards inherited Python import paths and old pytest hooks/options. Put required Node/browser/library paths in `environment`; their values are preserved. `TMPDIR`, profile, app/models/cache paths and pytest roots always belong to the new run. HOME and CODEX_HOME are never changed.

## Configuration and caller responsibility

Use an absolute JSON config path and absolute source, scratch, Python, tool and adapter paths. The source must be outside the assigned scratch directory (an export and a `runs` directory can be siblings under the task root). Scratch must already exist, have no symlink components, and overlap neither source nor the user's home itself. It must be exclusively assigned to this task. The tool never clears runs or recovers stale ownership locks automatically.

A minimal config looks like this; replace every placeholder with the task's frozen values:

```json
{
  "task": "taskNNN",
  "scratch": "/assigned/taskNNN/runs",
  "source": "/assigned/taskNNN/source-export",
  "source_kind": "export",
  "base": "EXPECTED_BASE_COMMIT",
  "head": "EXPECTED_HEAD_COMMIT",
  "policy": "frozen",
  "files": {"openscrub.py": "CALLER_EXPECTED_SHA256"},
  "modules": {"openscrub": "openscrub.py"},
  "python": "/prepared/venv/bin/python",
  "python_version": [3, 12, 16],
  "min_free_bytes": 2000000000,
  "configure_app": false,
  "prerequisites": [{"path": "/prepared/tool", "sha256": "EXPECTED_SHA256"}],
  "environment": {"LD_LIBRARY_PATH": "/prepared/library/path"}
}
```

Freeze `files` from the caller's expected Git object/reviewed manifest, **before** running product code. Include the required runtime/private modules, tests, fixtures and recipe files for the claimed boundary. Do not derive the acceptance expectation from whichever module happens to import. Every `modules` entry must name its relative file in `files`. All declared file hashes are checked; selected import origins and bytes are also checked in every guarded Python child before its workload starts. Parent packages are inspected without executing their initialization. A task-local import finder then pins declared modules to those frozen files and rechecks their bytes when resolved. CPython adding a direct script directory or module cwd after startup cannot shadow those declared imports, including in guarded Python children.

For `source_kind: "git"`, preflight checks exact HEAD and that the declared base is its ancestor. `policy: "frozen"` rejects tracked or untracked dirt. Explicit `policy: "development"` allows dirt, still requires declared hashes, and labels evidence as development. An export requires frozen policy plus `.verification-source.json` containing the caller's exact `{"head": "...", "base": "..."}`. That marker records provenance; the exporter must establish it from the pinned Git object. It does not independently prove ancestry or replace frozen byte identities. Task901's `prepare_smoke.py` evidence records an example exporter, not a required general export interface.

`python_version` is the exact three-part actual version, not the pip/bootstrap version. Preflight launches that executable with `-I` to identify it without inherited task hooks. Prerequisites accept existing paths, optional `executable: true`, and optional SHA-256 for files. Include every cached prerequisite needed by the invocation. Directories prove presence only; use exact files/hashes for identity-sensitive tools. No missing prerequisite triggers a download or rebuild.

Set `configure_app: true` for OpenScrub source/default/CLI/server checks, and declare all imported product modules, including `openscrub`, `openscrub_web`, `zones_ui`, private package/leaf, and updater where used. The hook checks defaults first (source-relative jobs in source mode; profile-relative installed jobs/models), then retargets app settings/jobs/certificates and models into the run. It preserves offline model fetch policy. Arbitrary fixture scripts can leave it false.

## Commands

```bash
python3 /path/to/tooling/verify.py --config /absolute/task-config.json preflight
python3 /path/to/tooling/verify.py --config /absolute/task-config.json run -- -m pytest /absolute/selected-test.py -q
python3 /path/to/tooling/verify.py --config /absolute/task-config.json run -- /absolute/task-server-adapter.py
python3 /path/to/tooling/verify.py --config /absolute/task-config.json package
```

The controller can run under any supported prepared Python; workloads always use the config's actual Python. Run cwd is the unique run directory, so workload script paths must be absolute. The optional `--run-id` is exclusive and never reused; otherwise a UUID name is allocated. `scratch/.verification-active` prevents overlapping invocations using that scratch. An interrupted controller may leave a lock: inspect its PID/processes and stop any owned children before an owner manually removes only that stale lock. Never delete another run. Separate scratch roots need a supervisor's serial/sole-runtime ownership discipline.

Invoke pytest as `-m pytest`, optionally after the supported interpreter flags; pytest scripts or wrappers are outside this launcher contract. This form gets one fresh `--basetemp` and cache directory. The helper rejects basetemp/cache/xdist ownership overrides, disables automatic third-party plugins, and shares the same startup hook with direct scripts, servers, CLI children and pytest. Explicit additional plugins remain a task choice. The supported interpreter prefixes are individual `-B` and/or `-u` options before a script, `-c code` or `-m module`; for example, `-B -u -m pytest` gets the same ownership enforcement. Other interpreter options and combined prefixes (including `-Bu`, `-Es`, `-IS`, `-I`, `-E` and `-S`) are rejected. Workload CLI arguments after the script/code/module are kept as workload arguments. Alternate child environments/interpreters or unguarded native tools must not bypass the startup hook. A process launching its own children remains responsible for terminating/reaping them on success/failure; the helper does not manage process groups. Use `try/finally` in listening-server adapters.

For strict installed checks, set `mode: "installed"`, `installed_target` to the existing task target (name it `site-packages` to exercise the product's installed defaults), and `excluded_paths` to known editable/native checkouts. Runtime import paths contain only hooks and target plus interpreter dependencies; source/native checkout paths and tool/bootstrap PYTHONPATH are filtered. The package action prepares this mode itself after installation.

## Offline package input

Add `package` to the same config:

```json
{
  "tool_paths": ["/prepared/hatch-backend", "/prepared/pip-bootstrap-site-packages"],
  "sdist_files": ["openscrub.py", "tests/owning_test.py", "benchmark/owning_recipe.py"],
  "wheel_files": ["openscrub.py"],
  "requires_python": ">=3.9",
  "installed_commands": [
    ["{target}/bin/openscrub", "--help"],
    ["/absolute/task-listening-http-adapter.py", "{target}"]
  ]
}
```

These lists are task-owned, not a built-in package inventory. All listed files need frozen hashes. The action builds without isolation using the selected actual Python and prepared read-only backend; validates sdist bytes before safe extraction; compares extracted bytes; builds the wheel **from the extracted sdist**; compares selected wheel bytes and exact Python requirement; and installs with offline/no-deps/no-compile pip into run-local `site-packages`. Bootstrap paths supply tooling only and are absent from installed runtime imports. It checks installed identities/defaults, then executes explicit adapters/CLI commands. A test-client request never constitutes a listening-server check. A Python floor requires its own config with the actual prepared floor interpreter; do not infer execution from wheel metadata alone.

Output consists of concise source/environment/prerequisite identity records and command/log/result records. Each run retains complete `preflight.json`, frozen runtime configs, logs and package identities. Nonzero child output is retained too; logs exist before child execution. Helper setup errors use exit 78, while ordinary workload exit codes are preserved. Archive errors and application errors remain visible in raw logs. Copy only compact owning logs/manifests/adapter sources into evidence, not exports, installations, media or shared environments.

## Isolation and evidence limits

The hooks redirect Python expanduser/profile paths, configure known OpenScrub mutable paths, block ordinary audited Python writes outside the run, and reject outward Python socket connections while allowing loopback. They are safeguards for cooperative verification code, **not an OS sandbox**. Native extensions/processes, arbitrary inherited descriptors, fd-relative operations, deliberately changed environments/sys.path, filesystem races and alternate interpreters can escape those checks. Node inherits task TMPDIR and requested prepared settings; it is not constrained by Python audit hooks. This helper supplies no generic native-process/network containment. Use task adapters and supervisor ownership for ports, cleanup, browser/media fixtures and timing grants. It never stubs the product's free-space guard.

Reuse an earlier gate only when its relevant source/tests/fixtures/dependencies/environment are unchanged and its claimed boundary matches. Record exact identities and limits. A new defect or affected source/helper/environment contract requires rerunning its affected gate; do not silently skip verification. Required full/floor/package/browser/media checks and implementation/fresh-review model quality remain the task brief's authority.

A compact handoff should contain: exact branch/base/head; owned scratch and evidence paths; named relevant interfaces/research; frozen helper config; focused and required acceptance commands; retained failure/review findings; and outstanding gates. Task901 establishes tooling only. D01 closes after the supervisor records its adoption on the next real candidate.

## Tooling tests

Use one prepared actual interpreter at a time, with socket permission for the tiny hook check. This suite creates only small fixtures beneath the explicit test root and leaves them owned there for inspection:

```bash
VERIFICATION_TEST_ROOT=/assigned/task901 PYTHONDONTWRITEBYTECODE=1 /prepared/venv/bin/python -m unittest discover -s /path/to/tooling/tests -v
```

No product-wide suite, browser workload or timing comparison is needed to rerun these setup behavior checks.
