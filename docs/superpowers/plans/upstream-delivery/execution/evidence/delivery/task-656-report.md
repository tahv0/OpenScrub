# Task 656 implementer report

Task656 assembled the four independently approved readiness follow-ups on `integration/upstream-focused-readiness` in managed `/home/tahv0/.codex/worktrees/bde3/OpenScrub`. Exact base: `c205ef5379778f63313b519411a2d5e37d07cba5`. Clean frozen and tested HEAD: `d1eeebd2b12645a7284344fb16ec589c8aba0ce7`. The worker changed only this assigned branch. Independent review and any expected-old advancement of `integration/upstream-focused` belong to root; that working reference remains at c205.

## Inputs and composition

Read Task656 brief, private execution notes, canonical verification README/current environment handoff, and the four independent approved review reports. Each report had no Critical, Important or Minor finding. Report byte identities are retained in `task656-evidence/recipe-identities.json`.

The exact Git mutation was `git -c gc.auto=0 -c maintenance.auto=false cherry-pick -x ac0f5e4661701e954e04dbc95eb00d9317c04cc6 af862c8c9700b7b2b06426e4c4287e469fe28038 bb4e129ae620f72a691971de1010d38d8cf661ad c7f9dcc29affe5da363094b8646b3064966e52ed` from the clean exact-base assigned branch, using the already authorized managed-worktree permission. Every whole pick succeeded without a conflict or manual resolution.

| Original | Composed | Ownership |
| --- | --- | --- |
| `ac0f5e4661701e954e04dbc95eb00d9317c04cc6` | `942c1b92d2cbf3c6e9cfd96afbd7da5718a4b0b2` | P05 configured HTTP date-only conditionals |
| `af862c8c9700b7b2b06426e4c4287e469fe28038` | `5066e03edccadbadc1f55096e6e7fe7fe5fae79e` | P16C-P recovery-stage comment |
| `bb4e129ae620f72a691971de1010d38d8cf661ad` | `115bad52df262278699f089d6784ebde9508d528` | N12 assertion coverage comment |
| `c7f9dcc29affe5da363094b8646b3064966e52ed` | `d1eeebd2b12645a7284344fb16ec589c8aba0ce7` | P16B actual-media prerequisites/contracts |

Stable patch IDs of every original and composed commit match, and every composed commit retains the exact `-x` footer. `provenance.json` records all current refs; a final comparison confirms they remained unchanged after assembly. All original candidate/donor/standalone refs remain present; the existing c832 documentation branch remains `6f055a4604563d1adc79da8264c3e56abd953fc2`.

## Static/source verification

`task656-evidence/prepare.py` was executed with actual prepared Python 3.12.16 using `-B`, producing `static-check.log`, `static-checks.json`, `source-identities.json`, `provenance.json`, frozen native/floor configs, and interpreter/recipe identities. It inspected pinned Git objects before any product execution, checked the clean working bytes against HEAD, and passed. `finalize.py` rechecked frozen working bytes, clean status, refs and `git diff --check` after both acceptance invocations; `final-check.log` records the successful result.

Exactly these four files differ from c205: `tests/test_live_preview.py`, `openscrub_internal/render_delivery.py`, `tests/test_first_scan_sanity.py`, `tests/test_polygon_fallback.py`. All other 165 tracked files and all file modes are equal to c205. No production file was copied wholesale. All 15 root/private production Python files have complete AST equality, including docstrings, defaults and constants, and equal non-comment token streams. The sole production byte change is the reviewed comment. The first-scan comment also preserves complete AST/tokens. Hashes for all 169 tracked files and the derived actual 12-module runtime inventory are recorded.

AST serialization uses recorded actual Python 3.12.16: `ast.parse(..., type_comments=True)` and `ast.dump(..., annotate_fields=True, include_attributes=False)`. Token equality compares `(type, string)` after excluding COMMENT/NL; interpreter-specific AST and token hashes are retained. All 69 tracked Python files also parse with `feature_version=(3, 9), type_comments=True`. Actual Python 3.9 runtime execution is separately established below.

Every existing top-level test/helper/fixture definition in both owning files has unchanged complete AST, except the reviewed replacement of the first prerequisite statement in `tiny_media`. The remainder of that fixture is AST-identical. Combined `observe_render` retains `_render_into`/`_render_hdr_into`, `frame`/`buf`, real child containment, pre-write bytes and decoded-output assertions. Existing report/media oracle functions and all their assertions remain intact. Fixture/helper AST hashes and generated actual-media hashes/byte counts are retained without copying media. The date-only cases retain the exact 1970 and 2100 strings and real configured Cheroot fixture.

`pyproject.toml` and every dependency/recipe/default/PAGE/APP_JS source are byte-identical. Static metadata confirms `Requires-Python >=3.9`, recursive `tests` inclusion in sdist and recursive `openscrub_internal` inclusion in both sdist and wheel. Source-default path checks and all 12 active module origins/hashes appear in both complete runtime logs.

## Actual acceptance

Canonical helper remains `/home/tahv0/src/OpenScrub/docs/superpowers/plans/upstream-delivery/execution/tooling/verify.py`, SHA256 `354cf49b0c83d11f3945137fbdffc3ac6b2793f1217ac39a9b62270097940067`. Its companion hook/sitecustomize/README, tool executables and both interpreters are pinned by exact hashes. The old Task655 inventory supplied names only; every new expected source hash came from frozen new HEAD. Both runs used `source_kind=git`, `policy=frozen`, `configure_app=true`, clean `env -i` with explicit PATH/PYTHONDONTWRITEBYTECODE and `login:false`, the unchanged helper, and no model seeding or adapter. Native Cheroot sockets/media execution used authorization at the original call. Runs were serial and each had its own non-reused helper run ID and scratch subtree. Private execution-control material is not included in public evidence.

Exact inner helper invocations (controller is always actual prepared 3.12.16):

```text
/tmp/openscrub-baseline-20261116/venv-opencv4/bin/python /home/tahv0/src/OpenScrub/docs/superpowers/plans/upstream-delivery/execution/tooling/verify.py --config /home/tahv0/src/OpenScrub/.superpowers/sdd/README/task656-evidence/frozen-312.json --run-id task656-native-312-01 run -- -m pytest /home/tahv0/.codex/worktrees/bde3/OpenScrub/tests/test_live_preview.py /home/tahv0/.codex/worktrees/bde3/OpenScrub/tests/test_polygon_fallback.py -q
/tmp/openscrub-baseline-20261116/venv-opencv4/bin/python /home/tahv0/src/OpenScrub/docs/superpowers/plans/upstream-delivery/execution/tooling/verify.py --config /home/tahv0/src/OpenScrub/.superpowers/sdd/README/task656-evidence/frozen-39.json --run-id task656-floor-39-01 run -- -m pytest /home/tahv0/.codex/worktrees/bde3/OpenScrub/tests/test_live_preview.py /home/tahv0/.codex/worktrees/bde3/OpenScrub/tests/test_polygon_fallback.py -q
```

| Run | Actual workload interpreter | Complete result | Exit | Complete command log SHA256 |
| --- | --- | --- | --- | --- |
| task656-native-312-01 | 3.12.16, `/tmp/openscrub-baseline-20261116/venv-opencv4/bin/python` | 585 passed in 15.97s, zero skips | 0 | `9b4f624c19689bf97a57dc06f6bb9ae3d82d48ba1e8f4e11b5b039c9a251f203` |
| task656-floor-39-01 | 3.9.25, `/tmp/openscrub-python39-20261117/venv/bin/python` | 585 passed in 17.08s, zero skips | 0 | `6223f76db6911234fa97db343338a3a23bc2bd97e5807b3c2f1f17dddee7ee44` |

Each serial invocation executes complete `test_live_preview.py` (28 cases) and `test_polygon_fallback.py` (557 cases), including the two actual-HTTP date-only cases, nine prerequisite contracts and every existing 14 actual SDR/HDR media case. The zero-skip result establishes real ffmpeg/ffprobe/libx264/libx265 availability in these prepared environments; it does not claim universal encoder availability. Missing-tool/encoder/query contracts assert the exact early-skip boundary before fixture allocation, while real production paint/render/encode/decode failures remain failures after prerequisite success.

The helper adds run-owned `--basetemp` and pytest cache arguments; exact resulting workload argv, outer clean environment, source/default records, actual interpreter identities, expected tool hashes, complete logs, preflights and runtime configs are retained in `commands-results.json`, `frozen-*.json`, and each compact run directory. Native tools are the read-only prepared `/tmp/openscrub-baseline-20261116/tools/usr/bin/ffmpeg` and `ffprobe`; native library paths are explicit in both frozen configs. Only metadata/hashes, logs and configs are copied into evidence, no media/export/environment/install content.

No unexpected runtime/test failure, semantic conflict, phase denial, runtime peak issue or source change occurred. One read-only metadata command guessed nonexistent `config-native.json` filenames and exited2 before any workload; its exact stderr, command and corrected lookup are retained in `failures.json`. That is not a product RED. No artificial RED or full-project/browser/package/timing replay was performed for this reviewed test/comment assembly.

## Self-review and limits

Self-review found no issue: exact four whole commits with provenance, four-file scope, complete production AST/docstring/token preservation, unchanged existing assertion/oracle/observer owners, zero-skip complete native/floor results, final clean state and preserved refs all passed. Evidence hashes cover the scripts, configs, source proofs, complete runtime logs, reports and manifests. Root must still perform fresh independent review before working-ref advancement.

The earlier C01 package/build/installed-startup evidence remains evidence for exact c205 only. The new HEAD has different production comment bytes despite equal runtime AST; its artifacts were not rebuilt and must not be described as built from d1eeebd. This task establishes only the two complete owner files in these prepared Linux Python environments. It adds no new full-project, browser, benchmark, packaging, installed-startup, platform, model-quality or publication claim. Austin defaults, Python floor, current C01 metadata/owners and original refs are preserved. No downloads, environment/helper edits, source exports, new dependencies/runtime behavior, user-data adoption or publication occurred.
