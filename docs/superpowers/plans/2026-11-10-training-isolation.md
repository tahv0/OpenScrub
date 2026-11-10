# Packaged training runtime isolation

> Execute with superpowers:executing-plans; red/green verification before publication.

Goal: prevent the packaged trainer's server site-packages directory from shadowing
its dedicated training environment, as demonstrated by the user's RTX 3080 A/B check.

Architecture: share the `python -I -u <absolute trainer>` launch prefix between
readiness and training. Add a no-dataset `preflight` command to the actual trainer;
retain CUDA-only enforcement, optional dependency checks and underlying import errors.

Scope: learning_session.py, scripts/train_plate_seg.py, test_training_isolation.py.
No dependency, Docker, dataset, source video, annotation or training threshold changes.
No LD_LIBRARY_PATH/preload hacks or changes to the running web server's imports.

- [x] Reproduce packaged-path, working-directory and PYTHONPATH contamination with real subprocesses.
- [x] Record failing tests for both launch paths, missing CUDA, and actionable import errors.
- [x] Implement shared isolated/unbuffered launch and actual-script readiness command.
- [x] Verify missing checkpoint, missing dependencies and CPU-only environments still fail closed.
- [ ] Run new tests, related backend tests, unfiltered full suite and PR CI; report all failures honestly.
- [x] Review subprocess flags, packaging, paths containing spaces and error preservation.

The subprocess test environments contain small fake library modules, not GPU models.
The user's non-isolated ncclCommShrink failure and isolated GPU success are the real
CUDA evidence. This environment cannot certify full RTX 3080 training.
