# Preservation source accounting

Pinned Austin baseline: `5d3a15ae683c08f368d6ba4bd0d2d77b4e7b8e2f`.
Preserved donor: `b4d0c75f25d91510fe1692f901d11853dc7db005`.
Reconciled 2026-11-17. These are local planning records, not a proposed upstream feature diff.

Every one of the 500 donor-only historical commits now has a source disposition. The two supplements form an exact, duplicate-free partition of the original inventory, including all 62 merges. First-parent production changes were examined or matched through documented exact source/blob evidence. Three large introductions and two associated merges explicitly limit their supporting-test review to meaningful retained boundaries; excluded custom-only test bodies and narrative docs were not exhaustively reread.

| Record | Coverage | Use |
| --- | ---: | --- |
| [Core historical report](core-history-audit.md) / [CSV](core-history-dispositions.csv) | 180 commits, 48 merges | Engine, web and zones histories, including mixed training introductions and merge-resolution changes. |
| [Other historical report](history-disposition-audit.md) / [CSV](history-dispositions.csv) | 320 commits, 14 merges | Other production, packaging and supporting-source histories. |
| [Core final-diff report](core-semantic-audit.md) | 438 engine/web hunks | Function/UI ownership in the final donor tree; accompanying CSVs retain exact scopes. |
| [Other final-path report](noncore-preservation-audit.md) / [CSV](noncore-path-dispositions.csv) | 42 production/build paths | Final-path ownership including `zones_ui.py`; together with engine/web, all 44 production/build paths. |
| [Reconciled counts](coverage.json) | Exact 500-SHA union | Current supplemental counts and separately labeled original inventory counts. |

The current historical dispositions are 132 mapped-owned, 154 excluded-artifact/retained-contract, 60 support-owned, 113 removed-system-only, 28 historical-support-only, 11 already-upstream and 2 superseded. Thus 346 rows retain an owning implementation/test gate; 154 have source-equivalent, excluded-only, historical-repair or superseded dispositions. These count commits, not independent bugs or PRs.

The earlier inventory's 463 metadata-only / 469 investigate counts describe its initial state. They must not be reused as current unresolved-source counts. The older noncore report's statement that core history remained separate is historical; the completed core supplement closes that production-source coverage gap.

Source accounting does not mean a fix was extracted, reproduced or accepted. The [execution record](../status.md) lists reviewed local implementations; S01–S06 and remaining P/O acceptance gates still apply. Retained contracts are scoped by the current task cards: for example, P15 does not gain new handled/training/confirmation states merely because donor workbench histories contained them. Existing Austin behavior/defaults and the user's selected exclusions remain authoritative.

These copies preserve source-accounting evidence beyond temporary execution scratch. Reports describe the conditions of their own passes, including tests not run and old integration boundaries; later reviewed task results are recorded separately.
