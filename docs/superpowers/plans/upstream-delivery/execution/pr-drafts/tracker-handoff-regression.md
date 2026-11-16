Title: Test size-jump handoff rejection through track geometry

The existing engulfing-look-alike regression expects a `size jump` log that the tracker intentionally suppresses when already held. Assert that post-occlusion samples exist, then retain the existing area checks to verify the larger look-alike cannot steal the target.

Only two test assertion lines change; the synthetic fixture and production tracker are unchanged.

Validation: original assertion reproduced RED; revised focused test passes; disabling only the size-jump guard in an isolated snapshot fails on a 19,500px² box at 3.03s. Full root suite: 134 passed. Default sdist → wheel build passes. Validation uses Python 3.12.16 and OpenCV 4.14.0; the separately known OpenCV 5 dependency compatibility issue remains outside this test-only patch.
