# Preserve source identity across a verified vault round trip

- Branch: pr/vault-source-continuity
- Declared base: 6fde5ad60c6d78d69dbbd8e049a9196f15e4095f
- Reviewed head: 0788899563f1a9861fe94a16e167868d0644cf0c
- Status: prepared locally as the narrow prerequisite for thumbnail coherence.

Encrypting and restoring an unchanged source replaces its physical file identity. Existing source-bound geometry can consequently become obsolete even after a successful vault round trip. Preserve its logical source reference and epoch when the managed encryption/decryption, publication and predecessor-removal evidence establishes continuity; update the verified physical observation after completion.

Partial or unverified transitions invalidate the affected continuity evidence. Close owned readers before removal and retain the existing operation marker through cleanup admission. The ciphertext format, key handling, report schema and redaction choices remain unchanged.

Validation: 215 affected tests on each of Python 3.12.16 and 3.9.25 at the reviewed head, rebuilt source/wheel and installed HTTP checks. A real round trip preserves bytes and accepts the existing geometry precondition after restoration.

[Acceptance and scope](../evidence/delivery/vault-source-continuity-acceptance.md) distinguish this local managed-transition proof from arbitrary external writers and native-platform certification.
