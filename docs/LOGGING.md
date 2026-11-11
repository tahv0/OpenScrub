# Runtime diagnostics

The web server writes timestamped logs to stderr (visible in Docker Compose logs)
and `<OpenScrub data root>/logs/openscrub.log`. In the supplied Windows Docker
configuration the container path is `/root/.local/share/OpenScrub/logs` on the
existing persistent data mount. No separate logging volume or training flag is
required. Logs start when `openscrub-web` starts, not just during training.

The default is 10 MiB per regular log with five backups (about 60 MiB maximum
for these regular logs). Fault dumps use `faults.log`, rotated at startup to
`.1` and `.2` because an active faulthandler descriptor must not be rotated.
Each restart gets a timestamp/PID header. `running.json` contains the last
observed active job IDs/stages. A stale marker is reported on the next startup;
it is evidence of an unclean/interrupted exit, NOT a diagnosis of an OOM crash.

## What is recorded

* Job start/return, callback messages, caught scan/render/learning failures with
  full Python exception chains, and job ID/phase/learning stage.
* Training subprocess PID, exit code, cancellation/forced termination, final
  output, and preflight stderr. Complete trainer stdout/stderr remains in each
  pass's existing `learning/passes/pass-*/training.log`.
* Failed HTTP responses (including handled 4xx/5xx), slow responses >=5s,
  method/route template/status/duration and a generated request ID also returned
  as `X-OpenScrub-Request-ID`. Unexpected Flask request failures include their
  traceback. No request body, query string, cookies or headers are captured.
* Preview decoder timeout/start/exit failures and stderr; caught thumbnail,
  tracking, model download/tier, settings, update/dependency and vault failures.
* Python uncaught main/thread exceptions and third-party Python warnings/errors.
  Cheroot's error logger is routed into the same diagnostics (TLS errors are no
  longer silently discarded).
* During active worker actions, a heartbeat every 30 seconds includes phase,
  stage, last progress counter, seconds since activity, disk free and available
  process/cgroup memory counters. After five minutes without reported activity,
  a warning says the worker may be slow or blocked. It does NOT cancel a job or
  claim the machine has crashed. Refinement and collection update these counters
  in memory; there is no disk write per video frame.

## Reading and preserving logs (PowerShell)

Use the same three Compose files and existing data/media variables as normal:

```powershell
$compose = @('-f','compose.windows-test.yml','-f','compose.windows-cuda.yml','-f','compose.windows-training.yml')
docker compose @compose logs --no-color --timestamps --since 24h openscrub 2>&1 | Out-File -Encoding utf8 .\openscrub-container.log
$cid = docker compose @compose ps -a -q openscrub
if ($cid) { docker inspect --format '{{json .State}}' $cid }
docker compose @compose logs --follow --tail 100 openscrub
# Ctrl+C stops viewing the logs, not the service.
docker compose @compose cp openscrub:/root/.local/share/OpenScrub/logs .\openscrub-runtime-logs
```

Preserve the original container output and state BEFORE recreating a possibly
crashed container. Docker's State may show exit code/OOMKilled when the existing
container was terminated. A running process is not proof that its worker is
making progress, and exit 137 alone is not proof of an OOM kill. The application
cannot query the host Docker engine and is not given its socket.

## Limits and privacy

Nothing here can reconstruct last night's missing log records. A SIGKILL,
host power loss, severe out-of-memory condition, stuck filesystem or host crash
may prevent any final message. Native supported faults produce a Python stack
dump in `faults.log`; raw native-library stdout/stderr still belongs to Docker's
logs, not necessarily to Python's rotating log. Failures during imports before
logging setup are also only available from process/Docker output; Docker images
enable Python's faulthandler from startup.

Regular records flush per event, but there is no fsync per frame or guarantee
against power loss. If file logging fails, an explicit warning goes to stderr
and job handling continues. File-write warnings are throttled to once a minute
per failed handler. Regular logs are bounded, not an unlimited audit archive.

Logs are local plaintext, OUTSIDE the vault-encrypted job tree, so diagnostic
access survives vault locking. They may contain private file paths, exception
messages or existing callback text. Treat them as sensitive. Known configured
auth tokens and common token/password/key patterns are scrubbed, not every
possible form of personal information. No frames, crops, model weights, request
bodies or environment dumps are added by this change. Review logs before sharing.

No model selection, segmentation geometry, training examples, thresholds,
review data, retry/activation rules or output masking rules are changed.

## Integration with live progress and saved models

Training epoch/batch and validation counters feed the same diagnostic heartbeat
as frame-based scanning and section rendering. Polling a status endpoint does
not count as worker progress. The calibrated outward margin for a recovered
model remains attached when saving/exporting/importing it; later section and
whole-video inference use that same policy rather than silently removing it.

These changes ship as normal source on the integration branch; installing a
separate patch archive is not required.
