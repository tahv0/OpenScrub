## Task 116 source checks and self-review

The assertion immediately below the changed comment compares `document["detections"]` with a list containing an expected dictionary (or an empty list). Dictionary equality checks keys and values without considering key insertion order; list equality compares ordered elements. A later, separate `list(document)` assertion checks top-level report key order. The replacement comment describes the detection assertion precisely.

Old: `# All Detection fields and report-only choices are pinned, including order.`

New: `# Detection fields, report-only values, and Detection list order are pinned.`

The proof reads the exact base Git blob and requires that the working bytes equal that blob with precisely this replacement. It also requires the exact one-line diff, one changed source path, unchanged mode, complete AST equality including docstrings and type comments, non-comment token equality, and Python 3.9 grammar parsing for both versions. Token positions are omitted; each token's type and spelling are compared. The committed pass additionally checks the exact parent, committed/working source equality, clean worktree, and preservation of every other ref.

Self-review: no assertion or serialization change, no new tests, no scope expansion, no concerns identified. Independent review is pending with root. JSON records give the exact interpreter, AST options, hashes, and results; AST hashes are interpreter-version-specific.
