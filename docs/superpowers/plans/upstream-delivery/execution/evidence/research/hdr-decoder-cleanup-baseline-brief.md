# N09 ordinary HDR decoder cleanup baseline

Read-only evidence for the generic decoder stdout cleanup in section-titled donor `08f432b`. No product/Git/dependency/model changes or subagents. Use a full pinned export of `e21ebdf6e3ee46e6c65050dc956a9a3459152269`, never the active native implementation worktree. Runtime under `/tmp/openscrub-hdr-cleanup-20261117`; report/evidence under `/home/tahv0/src/OpenScrub/.superpowers/sdd/README`.

Source audit: upstream render_hdr.cleanup_partial explicitly closes encoder stdin but not decoder stdout; donor includes the latter independently of sections. Investigate actual child/descriptor cleanup on ordinary HDR cancellation/error and successful controls. Read relevant fixture/tool details in `mask-fidelity-research.md` and its retained scripts; reuse the isolated compatible FFmpeg/tools read-only. Generate only a tiny valid10-bit PQ/BT2020 clip with clear metadata, no user media/models or heavy benchmark.

Use the actual complete render_hdr/run_render boundaries and real child processes. Trigger bounded cancellation at an existing callback/checkpoint and a representative error at an actual compute/I/O boundary. Instrument Popen handles/capture real descriptor state and process return/reaping, without replacing cleanup with a miniature function. Distinguish a retained diagnostic reference from actual application lifetime; where a retained exception traceback keeps a handle alive, report that precisely. No arbitrary native-decode deadline guarantee.

Check uncancelled output/frame correctness sufficiently to validate the fixture, and record every spawned child/pipe's terminal state. Clean all task-created processes/descriptors in harness finally even when the baseline does not. Do not change output overwrite semantics, geometry, section short-read handling, or renderer algorithms. Prior-output preservation and broader encoder failure handling belong to P16C; record concrete adjacent observations separately rather than silently expanding this candidate.

Deliver a demonstrated defect or explicit non-reproduction/closure plus the smallest generic cleanup contract. No product fix, full suite/build, platform claim or timing speedup. Notify supervisor before any expensive workload; the intended fixture is only a few small frames.

Write `hdr-decoder-cleanup-baseline-research.md` and compact `hdr-decoder-cleanup-baseline-evidence/` with exact source identity, actual command/results, process/FD evidence, cleanup and limits. Return concise finding/disposition and paths.
