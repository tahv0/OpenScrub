# Task 61 — scoped fix-round 1 review

## Finding verdict

**Vanished report stage aborts vault encryption — ADDRESSED.** `encrypt_tree` now catches `FileNotFoundError` only around removal of an enumerated `.tmp` (`openscrub_vault.py:169`–`172`); the decryption loop applies the same narrow compatibility rule (`openscrub_vault.py:184`–`187`). Ordinary-source processing remains outside those catches (`openscrub_vault.py:173`, `openscrub_vault.py:188`), and other cleanup errors still propagate. A successfully published stage can therefore disappear after enumeration without aborting the encryption pass or preventing the caller's key reset.

The new regression exercises actual report publication through actual `_vault_lock_now` and encryption, with only scheduling/enumeration order controlled (`tests/test_vault_cleanup.py:12`). Its permitted stage-first snapshot freezes the exact previously failing ordering. Assertions verify successful encryption of both ordinary files, key reset, zero remaining plaintext files, and real decryption recovering the complete newly published report and original input (`tests/test_vault_cleanup.py:62`–`69`). Additional cases cover disappeared staging during decryption, cleanup of a real leftover, propagation of permission/generic cleanup errors, and propagation of missing ordinary-source errors (`tests/test_vault_cleanup.py:72`, `tests/test_vault_cleanup.py:98`, `tests/test_vault_cleanup.py:114`).

## New Critical/Important breakage in the fix diff

**None.** The production change is restricted to temporary-file cleanup in the two vault loops. No publisher, transaction, key-management, or ordinary-file processing logic changed. The eight new cases test the required compatibility behavior and its error boundary.

## Covering evidence checked

- Read the supplied fix package once, base `c7cf1f02d98742e93a728e4b1e94d8c6bd02c318` to head `66787aa09a958154e81e75f9bdc54d9788feb843`, and the appended fix-round report. No Git commands or additional product-source reads were needed.
- `task61-evidence/fix1-red.log` records **2 failed, 6 passed**: the actual vault-lock/publication ordering and decrypt symmetry failed at the original unguarded temporary removal; the six error-propagation cases already passed.
- `task61-evidence/fix1-green.log` records **23 passed**, covering the 13 original publication cases, eight new vault cases, and both named existing vault regressions. This matches the report's covering command and the diff's parametrization.
- `task61-evidence/fix1-build.log` records successful isolated sdist-to-wheel build. Inspected `verify_fix1_packaging.py` and `fix1-packaging.log`: archive reads compare shipped vault/helper bytes and sdist tests against source, and actual imports resolve to the installed wheel.
- `task61-evidence/fix1-installed-final.log` records **21 passed**. The report's command runs both focused files from outside the checkout against the installed wheel using importlib mode and a scratch cache. Final focused/build/package outputs inspected are clean.
- No tests or build were rerun for this review; the code and existing focused evidence leave no unanswered doubt requiring another execution. Review remained read-only on product/Git; only this review artifact was written.

## Out-of-scope observations

**None newly discovered.** The already ledgered packaging extraction warning is outside this gate. This verdict covers the vanished-stage ordering only; it does not claim full vault/write transaction coordination or resolve the other P06B lifecycle orderings. Docker, Windows/frozen, and power-loss limits remain unverified.

## Verdict

**All findings addressed, no new Critical/Important breakage.** The narrow fix satisfies the reviewed compatibility requirement and the supervisor-authorized scope expansion.
