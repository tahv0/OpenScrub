# Retrieve only needed dense-smoothing frames

Late dense tracks can go through thousands of leading frames before the first gray-cache span the matcher needs. The smoother still advances sequentially, using `grab()` outside needed spans and retrieving pixels inside them. The capture releases on success, failed opening, EOF, error, and cancellation. Cache spans, frame identities, matching results, and cancellation checkpoints stay the same.

On two generated 610-second, 256×144 H.264 clips, earlier median smoothing times went from 5.531 s to 1.797 s with GOP 30, and from 5.480 s to 1.387 s with one keyframe. On each clip, 18,001 reads became 17,872 grabs and 129 reads. All 129 needed frame markers and all 38 detection records matched. These measurements belong to the original `e21ebdf6` and `f19be5fe` comparison on a shared machine. The refreshed smoothing function is byte-identical. Native prefix decoding still takes place, and the timing is specific to these clips.

The refreshed head passed all 157 native tests with no skips, including all three HDR cleanup regressions, and the 20 smoothing cases also passed on Python 3.9. The offline package build and installed-engine marked-video check passed. The installed test retrieved the expected 45 frames, skipped pixel retrieval for 16 prefix frames, released the decoder once, and matched the complete baseline detection records.

<details>
<summary>Reproduce the synthetic benchmark</summary>

From the topic checkout with NumPy, OpenCV, and FFmpeg with libx264 available, generate the two marked clips and compare the current candidate with its Austin base. This reruns the comparison in your environment.

```bash
dense_dir=$(mktemp -d)
python - "$dense_dir" <<'PY'
import json
from pathlib import Path
import subprocess
import sys

import cv2
import numpy as np

FPS, WIDTH, HEIGHT, FRAMES = 30, 256, 144, 18300

def generate(work):
    rng = np.random.default_rng(20261116)
    background = rng.integers(30, 85, (HEIGHT, WIDTH, 3), dtype=np.uint8)
    texture = rng.integers(0, 256, (48, 64, 3), dtype=np.uint8)
    commands, processes = [], []
    for name, gop in (("gop30", 30), ("single-keyframe", FRAMES + 1)):
        command = ["ffmpeg", "-hide_banner", "-loglevel", "error", "-y",
                   "-f", "rawvideo", "-pix_fmt", "bgr24", "-s", f"{WIDTH}x{HEIGHT}",
                   "-r", str(FPS), "-i", "pipe:0", "-an", "-c:v", "libx264",
                   "-preset", "fast", "-crf", "18", "-threads", "1", "-pix_fmt", "yuv420p",
                   "-x264-params", f"keyint={gop}:min-keyint={gop}:scenecut=0:open-gop=0:bframes=2",
                   str(work / (name + ".mp4"))]
        commands.append(command)
        processes.append(subprocess.Popen(command, stdin=subprocess.PIPE))
    for index in range(FRAMES):
        frame = background.copy()
        # 16 high-contrast little-endian cells survive YUV420/H.264.
        for bit in range(16):
            frame[0:16, bit * 14:(bit + 1) * 14] = 240 if index & (1 << bit) else 12
        cv2.putText(frame, f"frame {index:05d}", (2, 40), cv2.FONT_HERSHEY_SIMPLEX,
                    0.48, (240, 240, 240), 1, cv2.LINE_8)
        # Fixed texture, slow deterministic motion, starts two seconds before detection.
        if 17940 <= index <= 18060:
            x = 100 + (index - 18000) // 6
            frame[70:118, x:x + 64] = texture
        raw = frame.tobytes()
        for process in processes:
            process.stdin.write(raw)
    for process in processes:
        process.stdin.close()
        assert process.wait() == 0
    (work / "generation-commands.json").write_text(json.dumps(commands, indent=2) + "\n")

generate(Path(sys.argv[1]))
PY

dense_base=50c5a9e03564983ea0bc2a7841824b1fffaf35e0
git show "$dense_base:openscrub.py" > "$dense_dir/before.py"
python benchmark/dense_smoothing.py \
  --before "$dense_dir/before.py" --before-revision "$dense_base" \
  --after openscrub.py --after-revision "$(git rev-parse HEAD)" \
  --media-dir "$dense_dir" --output "$dense_dir/result.json"
```

The script records each sample and checks frame markers, decoder operation counts, and full detection records for equality. The comparison times only the smoother.

</details>

Private head: `66e7c10` on Austin `50c5a9e`. [Verification and source attribution](../evidence/delivery/dense-smoothing-current-readiness.md).
