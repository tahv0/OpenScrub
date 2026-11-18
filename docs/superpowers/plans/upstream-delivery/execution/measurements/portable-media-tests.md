The portable output helper removes two explicit output setup actions: setting `VERIFY_RUN` and creating its `logs` directory. It preserves the seven JSON evidence outputs and the existing media assertions. No repeatable test-speed gain was established.

A matched local Python 3.9.25 comparison used old source `6fde5ad` with explicit output (A), and accepted source `d3d0277` with fallback output (B). Three predeclared pairs ran AB, BA, AB. Every sample passed the same seven retained-media cases with 35 deselected; there were zero unexpected failures, invalid samples or retries. The six new helper tests were excluded. The three original media inputs, native dependencies, ten product modules, observation plugin and pytest flags matched; source switches happened outside the timer.

| Sample | Mode | Pytest seconds | Controlled invocation seconds |
| --- | --- | ---: | ---: |
| 1 | A | 1.85 | 3.849 |
| 2 | B | 1.55 | 2.677 |
| 3 | B | 1.42 | 2.462 |
| 4 | A | 1.46 | 2.482 |
| 5 | A | 1.45 | 2.478 |
| 6 | B | 1.45 | 2.473 |

Pytest median/range: A **1.46 s (1.45–1.85)**; B **1.45 s (1.42–1.55)**. Controlled invocation median/range: A **2.482 s (2.478–3.849)**; B **2.473 s (2.462–2.677)**. That second measure includes verification, startup and logging. The first A sample was slower; later samples overlap. This small single-session sample, with no cache reset, does not support a speedup claim. Pytest reports elapsed time to 0.01 seconds, and the same observer adds fixture/location-recording overhead to both modes.

Each sample produced seven artifacts totaling **4,542 bytes**: `media-cfr24.json`, `media-cfr5.json`, `media-normalized.json`, `media-coarse.json`, and `strict-media-{cfr24,cfr5,normalized}.json`. All schemas and deterministic values matched. The coarse remux's container hash and derived `source_ref` varied. The protocol also excluded `timeline_eq`, which in fact matched across all six samples; equality for that field is stronger than the normalized comparison requires. Explicit output collects files in one `logs` directory; fallback writes to each test's `tmp_path/artifacts`.

The measured recipe reduction is **2 output setup actions to 0** (one environment assignment and one directory preparation removed). This is an action count, not measured human time. Common manifest configuration and prepared dependencies remain necessary. From a fresh environment with `VERIFY_RUN` unset, the recipes are:

```bash
# Common: use the existing pinned fixture manifest and prepared dependencies.
export OPENSCRUB_EXACT_MEDIA=/absolute/path/to/media.json

# Old explicit-output setup, before pytest:
export VERIFY_RUN=/absolute/path/to/test-evidence
mkdir -p "$VERIFY_RUN/logs"

# Both sources run the same retained selection:
python -m pytest tests/test_exact_media.py tests/test_strict_tracking_routes.py \
  -k 'production_pixels or retained_strict' -q
```

With the new helper, omit the two output setup commands. Pytest supplies temporary artifact directories. `VERIFY_RUN` remains supported when a stable explicit destination is desired.

Previously retained final-source 48-case observations (explicit 3.40 s; fallback 3.43 s) establish mode compatibility only and are excluded from this source comparison. The seven old missing-`VERIFY_RUN` failures establish reliability only and are never treated as a successful timing baseline. No project-wide, full-suite, package, product-performance or human-time savings are inferred.
