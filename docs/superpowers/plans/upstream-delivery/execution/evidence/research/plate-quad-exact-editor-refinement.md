# Four-corner masks after the exact-editor work: source refinement

This is source research, not an implemented plate-mask feature. It examines exact-editor backend335435e1e1120de9e6773656b7dfdfabf220e27b, strict seeds6fde5ad60c6d78d69dbbd8e049a9196f15e4095f and ordinary editor/Trackd1f056e86fcae2dcfaa01bbc7f97e79ca662faaa. Those revisions form the inspected prerequisite chain; the reviewed applicationb4fc209 has not adopted it. Keep P17A source-bound record/transaction/render support before P17B ordinary corner editing.

## What is now available

The edit_sample route returns an indexed image and geometry using source_ref, timeline_eq, policy, index, requested_s, canonical_s, observed_s, dimensions, stream, origin and offset. Raw row index i, row_context_eq and base box/span values support the existing optional transaction preconditions. The current policy is opencv-ffmpeg-zero-cfr-v1, a qualified CFR/normalized subset. It supplies no integer PTS/timebase contract or general HDR correspondence.

source_ref is a transient path/stat incarnation and timeline_eq hashes metadata and offsets. Neither proves durable source bytes. The route does not verify provenance.input_sha256. Scan hashes its selected input after normalization/scanning: that can be the original, a CFR copy or a tone-mapped HDR copy. The current hash reads a path without a decoder-bound descriptor/stat fence. Web publication/adoption transfers operation/epoch/path/report-stamp continuity, not a verified digest. Reopening an exact sample does not add hashing.

Render recomputes its selected-input digest, but existing mismatch behavior warns and continues. Preserve that legacy behavior. A new quad may become ineligible and fall back to ordinary coverage; it must not turn legacy reports into hard failures. Existing scan hash work can only be reused after an explicit verified handoff and continuity contract. Do not hash a whole long video on every edit or treat an unverified report digest as proof.

## What, why and delivery order

| Part | Required work | Why / gate |
| --- | --- | --- |
| P17A source binding | Define a versioned durable source/sample record and a verified handoff, or conservatively reject quad eligibility when identity is unproven. Resolve original/normalized/HDR mapping through its actual owner. | Matching dimensions, frame counts or transient tokens do not prove the selected pixels. HDR mapping remains open. |
| P17A row transaction | Admit quad-only edits at an inspected frame; existing geometry_preconditions currently require box/time changes. Extend row context/CAS with prior and intended quad values and idempotent lost-ACK handling. | An added quad changes row_context_eq. Preserve unrelated edits, opaque fields, disabled rows and raw ordering. |
| P17A schema/render | Append optional geometry after Detection's existing12 positional fields; omit absent keys on fresh ordinary reports. Use it only for the verified exact frame/source, retaining ordinary padding/full-plate fallback elsewhere. | Avoid changing legacy data, assuming perspective tracking or propagating one quad across a whole interval/group. |
| P17B editor | Build on the existing inspected-sample/context/resize/draft owner. Add ordinary corner handles and whole-value ACK checks that preserve newer or unrelated Blur/Keep/audio edits. | The current editor's transaction and draft boundaries must remain intact. |
| Validation and PR | Test identity loss, quad-only/context conflicts, reload/lost ACK, exact rendered frame and unchanged ordinary output before browser editing. Retain the SDR/HDR distinction in the PR description. | Source inspection is not pixel/frame capability evidence. No custom model, training, segmentation or tracking system is introduced. |

The HDR normalization cache's timestamp/frame-count tolerance is not an exact scan-to-original mapping. P17 HDR acceptance remains open until real correspondence is established. P17A and P17B can be combined only if the resulting diff is still small and reviewable. Automatic boundaries, lettering-only modes and selected-target tracking retain their separate optional cycles.
