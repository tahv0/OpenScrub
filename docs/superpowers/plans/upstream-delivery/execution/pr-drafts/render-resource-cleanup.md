# Fix owned renderer cleanup across setup and exceptional exits

Rendering could leave captures, fallback writers, FFmpeg children, pipe endpoints or stderr open when setup, frame callbacks, final waits or logging raised. It could also return success after a resource-close failure. Give SDR/HDR renderers explicit ownership through finalization, preserve render-local primary errors and useful encoder stderr, and bound exceptional status discovery and child shutdown. Healthy encoder finalization keeps its existing wait behavior.

Keep output deletion restricted to the existing cancellation/write-error paths; staged video/report preservation remains separate P16C-P work. Public signatures, defaults, masks, geometry, encoder commands and dependencies are unchanged.

Validation: final resource/N09/render controls passed 64 cases each on actual Python 3.12 and 3.9. Tests include caller-exception isolation, independent stdin-close failure after encoder exit zero, useful nonzero encoder diagnostics and bounded shutdown without delivered EOF. Offline sdist→extracted-source→wheel, exact packaged bytes, installed defaults/CLI and actual listening HTTP startup passed. Tests retain actual owners/tracebacks and assert production closure/reaping before harness containment. The earlier frozen full-suite result (174 passed at `e9fd0d3`) is retained separately from final scoped verification.

Base: `ded411cbec308333d1416ae3d58b4f6e918d7849`. Head: `70ec464ca70b5e49751d778890f56029dced0b8a`. Detailed scope, failures, evidence and limitations: [delivery report](../evidence/delivery/task-1632-report.md) and [fix report](../evidence/delivery/task-1632-fix1-report.md). No publication performed.
