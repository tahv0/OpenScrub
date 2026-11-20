# Whole-frame scanner stop boundary

The local `pr/scan-stop-boundary` topic at `0ef5e318ef86b00b4662ff743d9a2ea3ec2ceab2` follows [the portable checkpoint contract](portable-scan-checkpoint-acceptance.md). The equivalent stack on the clean application was tested at `a7e79591e82e1ede015fce8f2e64bee7ea3e4a07`.

| What | Why | When to deliver |
| --- | --- | --- |
| An optional operation-owned stop callback in `run_scan`, with a separate cancellation path and first unprocessed frame index. | A long scan can describe a completed prefix after finishing processing the current frame. The engine can distinguish an explicit stop, a selected-window fast stop and decoder termination. | Review after the portable data contract. Test actual small encoded clips with a controlled detector and exercise the ordinary scanner as a control. |
| Sequential accounting through skipped windows and aligned offset and band arrays. Close primary, deep-backtrack and gap-check captures across completion, cancellation and errors. | A boundary needs one coherent prefix. Retained exceptions can otherwise hold secondary decoders in memory after the scan has stopped. | Include with the engine boundary and demonstrate both cleanup failures and success controls. |
| Keep reported media metadata separate from verified source, settings and completion identity. Defer configured whole-file audio on a stopped prefix and refuse an unfinished setup track. | An early decoder stop or metadata count can misrepresent which frames were examined. A setup track also needs known future frame and scroll coordinates. | Add source and completion evidence, frame-bound output, suffix overlap and scroll reconciliation before the web or CLI Stop & Review controls. |

The engine marks the boundary candidate as unverified, and the normal report builder and renderer refuse that internal state. The work supplies frame accounting and cleanup. It leaves resumable publication and partial rendering to subsequent topics with verified ownership.

## Verification

- The standalone reviewed source passed 191 owning tests on each of Python 3.12 and 3.9. Two actual legacy backtrack and gap-verification success controls also passed.
- The original secondary-capture reproductions retained open captures during cancellation and decode exceptions. The repaired gap-check and deep-backtrack code close their captures even while the traceback is retained. The new tests cover each owner and both error modes.
- The clean-build stack passed 196 selected tests on each Python version, including checkpoint data, scan options, report and job lifecycle. The rebuilt installed wheel passed 104 tests on each Python version from outside the source tree. The packaged engine and checkpoint documentation matched their source bytes.

For Austin, lead with the frame-boundary symptom and one synthetic encoded clip. Include recorded termination, output arrays and cleanup as the behavior to review. List the portable contract as a prerequisite. The scan controls, suffix scheduler and partial render will need their own end-to-end reproduction.
