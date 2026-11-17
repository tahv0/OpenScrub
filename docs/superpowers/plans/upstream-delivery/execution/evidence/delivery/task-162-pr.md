# Fix unusable silhouette polygons falling through known-box redaction

Malformed/nonfinite polygon coordinates previously raised despite a valid detection box, while collinear or repeated points could leave only a tiny nonempty mask. SDR and HDR now share local geometry validation and select their existing full-box renderer over the same clipped/padded known region when polygon data is unusable. Point/box shape, finite mapping, int32 safety and integer noncollinearity are checked before rasterization; usable concave, clipped and self-intersecting contours retain their original pixels.

The patch preserves requested fill modes, padding/dilation, existing HDR chroma behavior, schema/defaults and encoder/color policy. Invalid primary boxes, output publication and arbitrary-failure resource lifecycle remain separate work. Tests and contributor guidance ship in the sdist; the contributor command discovers the new tests directory.

Validation at `a3c3193e8dff41ec0588e66443398048a5c15ece` from base `e21ebdf6e3ee46e6c65050dc956a9a3459152269`:

- Test-first owning baseline failures, followed by focused3.12 **556 passed** and one full discovered suite **682 passed**.
- Actual Python3.9.25 focused run: **556 passed**.
- **96 direct** and **8 actual SDR/HDR media** baseline/current controls retain exact pre-encode behavior; decoded equality is checked separately.
- Offline sdist→wheel, exact source/test inclusion, installed CLI and real local web startup passed under the correct3.12 interpreter; HTTP200 and clean server shutdown verified.
- Final native/installed/committed byte identity and clean Git status verified. Inherited optional-model/GPU-fallback diagnostics remain documented; no downloads or dependency additions.

Full evidence, RED/GREEN corrections, source binding and limitations: `task-162-report.md`; retained artifacts: `/tmp/openscrub-task162`. Draft only; no publication.
