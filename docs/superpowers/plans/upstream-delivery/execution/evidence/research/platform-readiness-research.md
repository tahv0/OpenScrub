# P13/P14 local platform readiness — 2026-11-17

The current WSL2 host has a reachable Linux Docker daemon and a visible NVIDIA RTX 3080. The earlier Docker permission denial and CPU-only Python packages do **not** establish missing host capability. Actual builds, container GPU handoff, plate inference, cache deltas and Windows packaging remain unverified. This is a bounded read-only readiness investigation, not completion of P13 or P14.

## Scope and evidence

Followed [platform-readiness-brief.md](platform-readiness-brief.md). No native product worktree access, Git mutation, Docker build/pull/run/removal, service/config/group/permission change, installation, model download, benchmark, external publication or subagent was performed. No workload overlapped Task20 UI tests. Writes are this report, [platform-readiness-evidence](platform-readiness-evidence/) and `/tmp/openscrub-platform-readiness-20261117`.

Original repository source was pinned with `git rev-parse HEAD` (exit 0) to `5d3a15ae683c08f368d6ba4bd0d2d77b4e7b8e2f`. Only P13/P14 cards, Task61 platform limits, Task1 environment JSON, and permitted Docker/workflow/Windows sources were consulted for source conclusions. [source-anchors.json](platform-readiness-evidence/source-anchors.json) records exact `git show` commands, return codes, file SHA-256 values and numbered excerpts. Local versions below are observations, not assertions about current external releases.

## Access and platform findings

| Gate | Ordinary sandbox | Authorized bounded check outside sandbox | Meaning |
| --- | --- | --- | --- |
| Docker API | Exit 1: `permission denied while trying to connect to the docker API at unix:///var/run/docker.sock` | Exit 0: server 29.7.2, Linux/x86_64, Ubuntu 26.04.1 LTS | Sandbox access restriction; no persistent OS socket denial was established. Daemon is running and reachable through the authorized tool path. |
| NVIDIA NVML | Exit 255: `Failed to initialize NVML: Generic operating system error` | Exit 0: `NVIDIA GeForce RTX 3080, 621.01, 10240 MiB` | Sandbox failure does not establish absent GPU/driver. Host GPU metadata is available; inference is untested. |
| Device visibility | No matching `/dev/dxg`, NVIDIA nodes or DRM render nodes visible | `/dev/dxg` and `/dev/dri/renderD128` visible; no `/dev/nvidiactl` or numbered NVIDIA nodes | Sandbox device views differ. Traditional Linux NVIDIA node absence is not sufficient to reject WSL GPU capability. |
| Windows interop | Standard Windows tools absent from PATH; standard C-drive paths and WSLInterop file not visible | WSLInterop registration exists; `cmd.exe`, PowerShell, `python.exe`, PyInstaller, ISCC, cl/MSBuild/dotnet and Wine are absent from PATH; tested standard C-drive cmd/PowerShell/VS installer/Inno paths do not exist | No usable native Windows build environment was established in this session. No native Windows program was invoked. Exact-path/PATH absence does not establish that the Windows host has no tools elsewhere. |

Docker client is 29.7.2, Buildx is v0.38.1, Compose is v5.7.0; those version calls all exited 0. Current context name is `default`; the ordinary failure identifies the Unix socket endpoint. Kernel is `6.18.58.1-microsoft-standard-WSL2`, architecture x86_64, userspace Ubuntu 26.04.1 LTS. No context was switched or configuration read/changed.

The daemon advertises runtime names `io.containerd.runc.v2` and `runc`, with no named `nvidia` runtime. This leaves the CUDA image's GPU handoff unverified; it is not proof that every possible GPU/CDI handoff is unavailable. Toolkit/CDI configuration was not inspected. The exposed DRM render node has no readable numeric `device/vendor` or `device/device` file at the tested standard sysfs paths, so it does not establish an Intel GPU. No serials/UUIDs, running containers/images, process inventory, private mounts, credentials or unrelated host profile data were enumerated.

All requested read-only escalations succeeded. There was no automatic approval rejection, no use of sudo, and no permission/group/daemon adjustment. [local-capability.json](platform-readiness-evidence/local-capability.json) preserves sandbox command results; [outside-sandbox-capability.json](platform-readiness-evidence/outside-sandbox-capability.json) preserves successful bounded daemon/device checks; [adapter-and-windows-paths.json](platform-readiness-evidence/adapter-and-windows-paths.json) records the final exact-path checks. Collector scripts are included for reproducibility.

## What validation is currently possible

| Target | Capability established | Still required before claiming validation |
| --- | --- | --- |
| CPU image | Linux/x86_64 daemon and Docker/Buildx clients are available through authorized execution. An amd64 build is a viable next task, rather than ruled out by socket permissions. | Actual dependency/model-fetching image build, startup and CPU plate inference; disk/network/artifact availability and selected builder behavior were not exercised. CPU arm64/QEMU is unverified. |
| Intel image | The Linux/x86_64 build target matches the daemon. Image construction/provider-registration checks do not require proof of an Intel GPU. | Actual build and OpenVINO model execution. A real supported Intel GPU and usable render-node/device handoff have not been established; CPU fallback cannot validate Intel GPU execution. |
| CUDA image | Linux/x86_64 Docker is available, and host RTX 3080/driver metadata is visible. The build's provider-registration assertion can run without a GPU, as its own source documents. | Actual build/startup, CUDA container device handoff, registered plate model execution with per-session/operator provider evidence and comparison to CPU. Host NVML success and a registered provider do not prove CUDA inference. |
| Native Windows package | WSL2/interop presence is established. | A reachable native Windows Python/build environment, PyInstaller and Inno Setup, Windows path/context reproduction, actual frozen package build/run and native provider/model validation. Linux CUDA success would not satisfy these Windows gates. |

Task1's recorded Python 3.12.16 environment has ORT 1.32.0 with Azure/CPU providers only. Its OpenCV 5.0.0 diagnostic reported zero CUDA devices; its 4.14.0 compatibility environment also lists only Azure/CPU ORT providers. Those describe installed Python packages, not the host GPU or the contents of the intended CUDA/OpenVINO images. No existing model files were inspected or executed in this task.

## Preserve the pinned provider and platform choices

P13/P14 contracts are at `docs/superpowers/plans/upstream-delivery/03-packaging-and-review-features.md:49-78`; Task61's earlier bounded limitations are at `task-61-report.md:135-150`. The new evidence clarifies capability without retroactively claiming Task61 performed image builds.

At pinned source `5d3a15a`, CPU uses `Dockerfile` and `python:3.12-slim`; Intel uses `Dockerfile.intel` and `python:3.12-slim-bookworm`, replaces stock ORT with `onnxruntime-openvino` and asserts OpenVINO provider registration. Intel's `/dev/dri` handoff and real GPU use remain separate runtime gates. The workflow retains CPU `linux/amd64,linux/arm64` and Intel `linux/amd64`; CUDA has no explicit workflow platform override. Preserve these choices.

CUDA uses `Dockerfile.cuda` with `ghcr.io/austinmabry/opencv-cuda:4.10.0-cu126`. Its source base is `docker/Dockerfile.opencv-cuda`: `OPENCV_VERSION=4.10.0` selects **both** OpenCV and `opencv_contrib` source tags; CUDA 12.6.3/cuDNN build/runtime stages use Ubuntu 22.04. CMake installs into `/opt/opencv`, sets `OPENCV_EXTRA_MODULES_PATH=/src/opencv_contrib/modules`, includes `cudev` in `BUILD_LIST`, and enables `WITH_CUDA`, `OPENCV_DNN_CUDA`, `WITH_CUDNN` and Python 3 bindings. Build and runtime NumPy are pinned to 1.26.4. The runtime copies compiled libraries and `cv2` from `/opt/opencv` into the Python site directory.

The CUDA app image deliberately bypasses the ordinary Python OpenCV wheel path: its requirements filter removes `opencv`, `numpy` and `onnxruntime`; GPU ORT/Paddle are installed separately; pip OpenCV variants introduced by Paddle are uninstalled; compiled `cv2` is restored from `/opt/opencv`; NumPy is restored to 1.26.4; app installation uses `pip install --no-cache-dir --no-deps .`. This preserves source-built CUDA OpenCV rather than letting an `opencv-python` dependency replace it. B02b/P13/P14 must retain this path unless separately justified and validated. The `cv2`/provider build assertions are registration/import checks, not actual CUDA model execution.

Native Windows uses `windows/build_installer.bat` and the `windows-latest` workflow with Python 3.12, PyInstaller and Inno Setup. The batch helper replaces stock ORT with `onnxruntime-directml`; that native DirectML path is distinct from the Linux CUDA container path. No old fork ORT pin or parallel inference Dockerfile was restored.

All three app Dockerfiles retain their separate late `ARG SECURITY_REFRESH=0` apt/pip refresh layer. The pinned workflow retains Monday `17 8 * * 1` refreshes, scheduled latest-release code selection, per-run `SECURITY_REFRESH=${{ github.run_id }}`, existing image/tag ownership and separate registry layer caches (`buildcache`, `buildcache-cuda`, `buildcache-intel`). No cache timing, reuse or cross-run mount persistence was measured.

## Smallest next checks in owning tasks

1. **P13, after Task20 finishes:** use the intended task checkout/build context and existing builder without changing defaults; confirm dependency/model download and disk budget. Run the focused Docker cache tests and actual affected builds. Record cold, source-only/same-refresh, dependency-change and changed-refresh stages separately, then startup/provider checks. Keep local cache-mount lifetime distinct from CI registry layer cache; do not infer arm64 support from an x86_64 daemon.
2. **P14 CUDA:** first establish GPU handoff using the supported image and configured environment, with no assumption that host NVML or runtime names settles it. Then execute an existing registered plate model on representative synthetic input, retain versions/model hash and provider execution evidence, and compare output to CPU under a justified tolerance. Preserve explicit fallback behavior and record any real failure before changing setup.
3. **Intel hardware:** establish a supported Intel adapter and usable render-device handoff before GPU claims; then run the actual model with OpenVINO device evidence. A successful Intel image build can be reported separately while GPU validation stays outstanding.
4. **Windows:** use a reachable native Windows task environment for the actual path/context issue, package and DirectML/model checks; record OS/tool/provider/model versions. Current WSL observations leave that requirement open. No benchmark or build/model workload should overlap active Task20 UI tests.
