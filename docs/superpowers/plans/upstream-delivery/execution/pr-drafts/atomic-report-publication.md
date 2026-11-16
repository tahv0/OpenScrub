# Preserve the last complete report when a review save is interrupted

Interrupted review saves can truncate the previous valid report before JSON
encoding or writing finishes. Publish reports through a shared private helper
that stages JSON beside the destination, flushes/fsyncs, closes, and replaces
it; failures propagate and staging is cleaned up. Apply it to review saves,
engine reports and background tracking, and include the package in wheel,
sdist and app-image sources. Existing JSON and response semantics are retained.

Vault crash cleanup now tolerates an enumerated `.tmp` name that disappeared
after successful publication, so that ordering cannot abort encryption or key
reset. Only missing temporary cleanup names are tolerated; ordinary source
failures and other cleanup errors remain visible.

Validation: the original change passed 147 full-suite tests, a full build,
installed/source startup and updater checks, real HTTP failures/fresh-process
reopen, and a 60-frame synthetic scan/render. The narrow vault follow-up passes
23 focused/root-vault tests and 21 installed-wheel tests, including controlled
actual publication/encryption interleaving and byte-for-byte decryption. Its
rebuilt sdist and wheel contain the changed vault and focused regressions.

Docker/Windows builds were unavailable. File fsync plus replacement does not
guarantee power-loss durability on every filesystem. Complete concurrent-edit
and vault/job lifecycle coordination remains separate work; vault cleanup can
still remove a stage before publication, causing that publication to fail.
