# Vault/source continuity: local acceptance

- Accepted branch: pr/vault-source-continuity
- Reviewed head: 0788899563f1a9861fe94a16e167868d0644cf0c
- Declared base: 6fde5ad60c6d78d69dbbd8e049a9196f15e4095f.

Independent review approves the combined contribution, including its operation-cleanup admission follow-up. This is a focused source/lifetime prerequisite; the reviewed application assembly and publication status remain unchanged.

## What, why and delivery position

Vault encryption and restoration replace physical files even when the source bytes are unchanged. The contribution carries verified managed-transition evidence through actual input observation, completed crypto output/publication and predecessor removal. After successful decryption and rehydration it updates the physical observation while preserving the logical source reference, epoch, geometry and report association.

Partial or unverified transitions invalidate the affected proof rather than authorizing an optimistic rebase. Owned readers close before removal. The active operation marker continues to exclude competing cleanup during its admission boundary.

This precedes P08A thumbnail coherence so restored sources can keep valid source-bound contexts without weakening external-change checks. Existing ciphertext/key handling, report schema and redaction defaults are preserved.

## Verification

| Check | Source | Result |
| --- | --- | --- |
| Affected native Python 3.12.16 cases | 0788899 | 215 passed |
| Same actual Python 3.9.25 cases | 0788899 | 215 passed |
| Fresh source/wheel, configured source-byte checks, installed HTTP | 0788899 | Passed |
| Real encrypt/decrypt/rehydrate round trip and old strict geometry save | Combined reviewed lineage | Bytes and logical source/geometry context preserved |

Earlier broad runs remain attributed to their earlier source heads. The final validation checked the current source and installed package; it does not certify native Windows, arbitrary external replacement races or weak file identities.

Portable owning checks use the project's prepared dependencies:

    python -m pytest tests/test_vault_source_continuity.py tests/test_vault_cleanup.py tests/test_exact_samples.py tests/test_exact_adoption.py -q
    python -m build

Run the relevant installed HTTP/round-trip scenario from the wheel as well. This recipe is not a new execution claim.

[PR description](../../pr-drafts/vault-source-continuity.md) preserves the narrow submission scope.
