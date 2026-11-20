# Protect checkpoint reports after a web restart

`pr/checkpoint-web-restart-protection` at `4dbffd9065e41c2b7c8fbb2a5087b66b5ecbff97` follows the [staged web publication owner](checkpoint-web-owner-acceptance.md).

| What | Why | When to deliver |
| --- | --- | --- |
| Restore a paused checkpoint and its saved job options when restarting, even if an older output remains. Keep recoverable reports visible when source or original settings are missing. | The old output is not evidence that the checkpoint finished. A saved report should remain discoverable for recovery. | After guarded publication and before web Stop and Resume. Verify real native video and restart from disk. |
| Fence unbounded edit, preview, Retry, Render and video download on unfinished checkpoints. | Ordinary operations can expose an older output or replace the inspected prefix if allowed to consume unfinished state. | In the same recovery prerequisite. Give each later interface its own bounded index or transaction check before enabling it. |

Both Python 3.12 and 3.9 passed 118 independent selected checks, including loopback report transactions. The restart restriction applies to unfinished checkpoint reports. Bounded editing, the actual Stop and Resume actions and restart-durable publication recovery remain subsequent work.
