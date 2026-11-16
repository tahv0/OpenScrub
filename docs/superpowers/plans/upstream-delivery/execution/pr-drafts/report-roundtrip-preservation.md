# Preserve Keep choices and review grouping through rendering and reopening

Rendering an existing report now keeps all review rows in their original
positions, including Keep choices, disabled zone/manual rows, precise manual
geometry, dense track/person grouping, and additive metadata. The engine still
renders only enabled rows. Previously the actual synthetic render/reopen case
changed **10 rows to 7**; the new real-render/fresh-Flask-route regression keeps
**10 rows as 10**, while decoded output frames confirm only seven enabled
regions are redacted.

The from-report path reads one source snapshot, retains the full review document
separately from render objects, and publishes it with fresh output provenance.
Audio suggestions/transcript and saved spans survive; explicit audio changes
win, including an empty span list. Public `load_report()` behavior, legacy
loading/error handling, and ordinary scan report generation remain compatible.
Separate report destinations leave the source bytes unchanged.

Validation: **168 tests passed**, including 13 new roundtrip cases; full
**sdist→wheel-from-sdist** build passed. A standalone 60-frame synthetic render
checks seven black/three visible regions on every decoded frame and reopens ten
rows with unchanged indices through the actual Flask route in a fresh process.
Saved audio spans, suggestions, and transcript compare equal. Distinct paths,
successive renders, empty/absent metadata, current output hashes, explicit audio
overrides, render-object isolation, failure preservation, and legacy behavior
are covered. Commands: `python -m pytest -q` and `python -m build`; standalone synthetic evidence is retained in the local execution record.

Depends on P06A's shared atomic report publisher already present in the branch.
P06B owns coordination with overlapping edits, tracking, vault and deletion;
this content-preservation change does not fix concurrent writers. The new
fixture is silent, so audio metadata checks do not establish audible mute/bleep
quality. No models, dependencies, versions, training/session schema, or unrelated
features changed.

Local commit: `7063082ef2a2ff5e56d9aafacff9bd43363b05b3`.
Base: `66787aa09a958154e81e75f9bdc54d9788feb843`.
