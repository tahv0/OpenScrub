# Next precise-mask backend screen

This is an authorized research spike for the existing precise/narrow design,
not a production feature or a claim that the missing precise mode is complete.

The first measured candidate is official Light HQ-SAM Tiny, using the upstream
TinyViT encoder and HQ decoder, not ordinary MobileSAM. Pin code and weights,
verify the checkpoint SHA-256, preserve official RGB preprocessing and early
features, and compare the adapter's fixed outputs with the public upstream API.
PyTorch is confined to this research runner. Only a candidate that passes the
quality screen would justify ONNX export and a separate production plan/PR.

Freeze two prompt policies before execution: upstream single-mask box output,
and the model-score-selected alternative among tokens 1–3. Truth masks never
select an output, prompt, model, component or threshold. Use the same 25%/35%
context crop policy as the prior EfficientSAM experiment. Keep all components
and holes; use raw logit > 0. Report a separate three-pixel dilation tradeoff.

Run the existing 12 deterministic synthetic fixtures, including rotated,
perspective, disconnected-cross, interior-hole and moving-occluder cases.
Measure visible plate and glyph omissions, unwanted pixels, occluder spill,
component/hole counts, and warmed two-thread CPU p50/p95. A high model score
does not certify any of these properties. Failed masks are reported directly;
do not hide them behind box fallback and call the precise behavior successful.

Independently screen a model-free GrabCut baseline and one frozen photometric
refinement. Specifically measure dark-glyph loss instead of optimizing IoU.
Do not tune parameters to names, coordinates, colors or truth from these cases.

A public-domain real physical-occlusion image may be downloaded to scratch and
annotated before model results are seen. Keep real image pixels, identifying
text and real screenshots out of commits, documentation and uploaded artifacts.
One image is a smoke test, not a representative corpus; it cannot establish
real-world coverage or plate-locator recall. External visible-mask annotations
and source provenance remain separate from inference.

If a candidate fails visible-lettering coverage or foreground exclusion,
preserve the result and explain the remaining work. Do not add a placeholder
precise setting, unsafe model, extra product runtime dependency or empty PR.
