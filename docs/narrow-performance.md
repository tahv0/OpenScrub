# Narrow plate CPU validation benchmark

Narrow mode checks connected image components for lettering that falls
outside its proposed mask. The original implementation compared every
component label with the entire plate crop. Large noisy crops could
therefore cause thousands of repeated full-crop scans.

The optimized implementation uses `numpy.bincount` to count covered pixels
for all labels in one pass per evidence map. Each label receives exactly
the same integer overlap count. Component order, thresholds, mask geometry,
fallback reasons, model calls and source-frame alignment are preserved.

## Scope and results

These are **synthetic CPU validation timings**, not video scan timings.
They exclude both plate-model and lettering-model inference, decoding,
tracking, rendering and I/O. Large noisy crops deliberately stress the
component-counting loop; they are not a representative-footage benchmark.
The existing every-frame model cadence and 4K tiling cost remain.

Measured on 2026-11-05 with OpenCV 5.0.0 and NumPy 2.3.5. Values are medians
of seven iterations, alternating baseline/candidate execution order in a
single process. The baseline is the original Narrow PR commit
`77755f075425331081d7f2b747f803f5dbf02131`. Hardware, crop contents and
library versions affect timings.

| Synthetic crop | Baseline CPU guard | Optimized CPU guard | Ratio |
|---|---:|---:|---:|
| Clean disconnected text | 1.616 ms | 1.453 ms | 1.11× |
| Uncovered-letter fallback | 0.910 ms | 0.944 ms | 0.96× |
| Low-contrast fallback | 0.013 ms | 0.013 ms | 0.99× |
| Occlusion fallback | 0.900 ms | 0.949 ms | 0.95× |
| Noisy 240×80 | 4.379 ms | 1.777 ms | 2.46× |
| Noisy 640×160 | 51.278 ms | 5.675 ms | 9.04× |
| Noisy 1280×320 | 723.073 ms | 17.887 ms | 40.42× |

Early fallbacks can incur extra upfront counting work; a universal
speedup is not claimed. This optimization addresses CPU validation cost,
and its effect on complete scans depends on how much time that stage takes.

All seven fixtures and 48 deterministic exposure/noise/polarity variants
produced exactly matching polygons and fallback reasons against the
original implementation. The combined branch's full test suite passed:
194 tests, including 33 Narrow regressions. No new model is required.

[Raw benchmark output](performance/narrow-guard-cpu.json)

## Reproduce

In a Git checkout containing the baseline commit, with Python, NumPy and
OpenCV installed:

```bash
python tools/benchmark_narrow_guard.py --iterations 7 --variants 48
```

The script reads both pure CPU guard implementations from source and runs
them without importing the application or downloading any models. It
writes no video, job or model files. A local benchmark gate can be added
with `--min-noisy-speedup 1.5`; timing thresholds are not part of CI tests.

To measure overall speed, compare the original and optimized versions on
the same representative video, with the same models, categories, Narrow
settings, tiling, hardware and verified execution providers. Compare
completed scan times and output masks; an early ETA is insufficient.
