# Fresh HDR source-pair evidence

`pr/plate-quad-hdr-pair-proof` at `ea894400bc8d3a602fe26382d20f7776585ce18d` follows [same-file SDR scan-copy corners](quad-sdr-scan-copy-acceptance.md). The explicit fresh-scan option records evidence during the existing HDR-to-SDR conversion. The live editor and renderer need that evidence before using a manual quad on the original HDR frame.

| What | Why | When to deliver |
| --- | --- | --- |
| Verify the actual before/after frame indices, integer PTS grid and spatial dimensions during the fresh tone-map. Verify encoded packet times without a second decode. Attach source and scan hashes to the live source witness. | A cached copy with a similar count or size can select different original pixels. The actual per-frame evidence supports a narrower HDR mask on the same scene frame. | Review the explicit proof producer before allowing the editor or renderer to consume it. |
| Clear stale evidence on reused intake arguments and refuse known unsupported spatial or temporal transformations. | A cached or re-normalized copy needs its own proof. Runtime flags can otherwise preserve an older attempt's evidence. | Exercise cache hits, source changes, cancellation, and real PQ output in the focused proof checks. |

120 selected source tests and 20 installed-wheel checks passed on each of Python 3.12 and 3.9. Both encoded streams agreed on the verified sample sequence. This milestone supports a fresh, zero-origin, unrotated 10-bit CFR PQ/HLG pair with the declared dimensions and cadence. Ordinary masking remains in use until the live editor and 10-bit renderer adopt the proof.
