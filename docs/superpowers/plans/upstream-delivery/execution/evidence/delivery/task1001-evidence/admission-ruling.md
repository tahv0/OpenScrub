# Exact admission wire clarification

Supervisor ruling: retain existing pre-route admission formats and statuses, including missing-job404 and auth/vault/deletion refusals. Route-managed exact failures use JSON with stable codes. Every exact response remains private, no-store and a refusal contains no usable sample. Future clients check HTTP failure before expecting JSON. The original interface proposal remains preserved. This clarification changes no frozen product bytes.
