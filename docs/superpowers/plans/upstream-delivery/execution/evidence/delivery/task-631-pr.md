# Skip publication for effectively unchanged report saves

An empty, same-value or replay-only review save currently re-encodes, fsyncs and replaces the complete report. Compare only the final effective assignment destinations after existing normalization/replay validation, then skip publication when nothing changed. No-ops retain exact bytes and file metadata; real edits keep one existing atomic readable publication and the same acknowledgement response.

Preserves Task622/P06B transaction/lifetime gates, Task72/P07b immutable manual creation/replay/conflicts and P07a deliberate same-value/newer-edit acknowledgement behavior. No browser/default/dependency/version or serializer change. Nonfinite touched values conservatively publish; no-op saves do not refresh retention's directory mtime.

Validation:440-test combined suite;96 Python3.9 focused cases; actual browser acknowledgement/newer-edit/failed-publication/no-op save-and-render and fresh-process reopen; offline sdist→wheel/source/tests/benchmark inclusion and installed CLI/web smoke. All pass.

Pinned alternating loopback HTTP (three warmups/five recorded samples each, uninstrumented routes): no-op medians46.24→5.27ms at1k,481.03→61.75ms at10k,5,413.88→1,189.39ms at100k. Separate counts:one fresh report parse, zero report dump/stage/fsync/replace after a no-op; true sparse/bulk changes publish once.100k sparse median+1.3%, bulk+4.4%; no changed-save speed claim. Shared Linux host/warm-cache/sampled-RSS limits and all samples/costs are in task-631-report.md.

Base:`12919c96c6f7558136b50d7b4d85e5e6b62f1971`; head:`3457efac574d74a7d2377cbc0d44bb0b87462c3a`. Local draft only; not published.
