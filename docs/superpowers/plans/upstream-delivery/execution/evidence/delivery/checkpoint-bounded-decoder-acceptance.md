# Checkpoint decoder cancellation

`pr/checkpoint-bounded-decoder` at `ccc8761eeef5bb6e87202b563af8a4f6684129f1` follows the [guarded checkpoint producer](guarded-checkpoint-producer-acceptance.md). The change is confined to the checkpoint operation.

| What | Why | When to deliver |
| --- | --- | --- |
| Bound raw decoder and metadata waits with small queues, a cancellation callback and owned child cleanup. | A decoder that stalls mid-frame could prevent Cancel from reaching report cleanup. | After the guarded producer and before exposing an interactive Stop or Cancel. |
| Keep Stop at whole-frame boundaries and reserve completion for verified decoded EOF. | A partial read or extra frame must never advance a checkpoint or certify a complete report. | Verify with both a normal B-frame source and a real subprocess that stalls, exits late or ignores termination. |

On both Python 3.12 and 3.9, 286 selected non-listener checks and the three separately rerun loopback report checks passed. The latter needed local listener access. Installed wheels passed 95 checks per version. Tests cover partial raw bytes, unavailable metadata, child exit delay, queue pressure and escalation from termination to kill. Cancel leaves prior report bytes intact. An independent FFmpeg pixel comparison exercises clean sequential and suffix reads.

## Application delivery sequence

| What | Why | When to deliver |
| --- | --- | --- |
| Connect staged checkpoint publication to the existing operation generation, cancellation event and ordered report/source owner. Advance the report and source generations and change job phase under that owner. | A cancelled or older scan must not publish after a newer job operation has taken over. | After ordinary completion through the checkpoint producer. Test acknowledgement order, source replacement, stale results and rollback. |
| Represent actual source duration separately from the processed-frame boundary. Grant editing, preview and exact sample authority only where the checkpoint and inspected source agree. | Existing review uses the report timeline length as the whole duration. A partial report needs the correct duration without making unscanned frames editable. | After the owner can publish a paused state. Include high-frame-rate boundaries, manual rows and source changes. |
| Add opt-in admission, separate Stop and Resume actions, recognition after restart, and Save followed by acknowledged Resume. | Restart and resume must use the same effective settings and include current review edits. | After owner and timeline contracts. Test a partial report beside an older output, a delayed save, resuming without losing a newer draft, and cancellation. |
