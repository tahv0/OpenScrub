# Optional plate confidence in review

`optional/plate-confidence-review` at `3f2dac412327bbfc9b556e3249fdcee361f96e5b` follows the [Scan Setup controls](optional-plate-confidence-setup-acceptance.md). The existing review cards show how optional policy evidence affects each plate group.

| What | Why | When to deliver |
| --- | --- | --- |
| Distinguish uncertain unmasked observations, automatic masks, explicit choices and unsupported samples. Show the job's selected mode after reopening. | An automatic decision or a pending suggestion must never look like a human Blur or Keep choice. | After confidence setup. Verify report save and reopen, older or malformed optional metadata, and the normal manual Add and Track paths. |
| Preserve newer drafts after an acknowledged save and skip policy-specific filtering for ordinary review cards. | A late acknowledgement should update only the captured choice. Long ordinary reviews should not pay for per-card candidate filtering. | In the same review series. Exercise opposite edits while a save is open and measure a 3,000-card ordinary control. |

The final source passed 488 selected checks on each of Python 3.12 and 3.9. The installed wheel passed 41 checks and the desktop/mobile Chromium review flow on each version. The browser fixture validates review, save, reopen, and ordinary exact-editor actions without doing the actual encoding. That render was verified separately in the engine milestone. The 3,000-card control observes zero policy row/member filter passes after the repair, down from one row pass and 3,000 member filters.

Review cards expose uncertain candidates. The exact editor continues to apply its verified current-frame and draft rules. A dedicated candidate overlay spanning paused and playback views is separate work.
