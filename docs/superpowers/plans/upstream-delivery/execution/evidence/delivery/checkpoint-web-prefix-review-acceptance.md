# Read the verified checkpoint prefix in the web editor

`pr/checkpoint-web-prefix-review` at `47991497521024a8cea4380342b9fbebab769dc2` follows [restart protection](checkpoint-web-restart-protection-acceptance.md). It adds read-only access to exact samples, review rows and thumbnails from the known processed prefix.

| What | Why | When to deliver |
| --- | --- | --- |
| Bind the current source to the checkpoint digest, native stream and total frame count. Return both total and processed duration. | A paused report contains only a prefix. The editor needs to distinguish the recorded video length from the frames that can be inspected. | After safe restart discovery and before enabling bounded edits. Include a byte-changed source, future times, and actual HTTP checks. |
| Apply each row's half-open frame bounds to exact samples and thumbnails. Check a 120 fps timestamp on the intended frame grid. | A sample outside the row's authority can show a position the system never observed. | In the same read prerequisite, with frame-edge fixtures and tests for the immediately preceding representable time. |

The independent selected run passed 332 tests on each of Python 3.12 and 3.9, including actual loopback preview and cancellation races. The combined branch also contains the [FFmpeg timestamp repair](checkpoint-decoder-timestamps-acceptance.md). This slice is read-only. Bounded Save and the worker controls are separate changes.
