# Keep FFmpeg progress out of checkpoint timestamps

`pr/checkpoint-decoder-timestamps` at `60645f747574e24d5e88bf6a392349802bdf18d0` follows the [bounded decoder](checkpoint-bounded-decoder-acceptance.md). The same repair is present in the combined branch at `ef09878`.

When raw frame consumption slowed, FFmpeg joined carriage-return progress records to several `showinfo` lines. The old parser observed only 21 anchored timestamp records for 24 decoded frames and refused the scan. Disabling terminal progress with `-nostats` restored all 24 while retaining the same frame-number, dimension, timestamp and EOF validation. This belongs with the decoder prerequisite before exposing interactive Stop or Resume.

A new slow-reader test failed against the old flag set and passed on Python 3.12 and 3.9 with the flag. Both complete standalone decoder selections passed 15 tests. The combined preview and HDR/OCR selection containing the repair passed 291 checks per interpreter.
