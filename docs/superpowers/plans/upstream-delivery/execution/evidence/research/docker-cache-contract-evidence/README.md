# P13 immutable source evidence

Product pin: `a10e485962571a566f99225541735ab1ada1f4c0`; original workspace HEAD observed `5d3a15ae683c08f368d6ba4bd0d2d77b4e7b8e2f`. Product was read only through Git objects in `/home/tahv0/src/OpenScrub`. Native task checkout was not read. Numbered source snapshots preserve original line numbers; `source-manifest.tsv` records path, blob ID and SHA256 of original unnumbered bytes. Dot-prefixed evidence files retain `.dockerignore` and workflow names.

Files: `Dockerfile*.numbered.txt`, `.dockerignore.numbered.txt`, `.github__workflows__*.numbered.txt`, `docker__*.numbered.txt`, `requirements.txt.numbered.txt`, `pyproject.toml.numbered.txt`, `openscrub_internal__opencv_compat.py.numbered.txt`, engine/install/setup numbered excerpts, B02b packaging delta, four exact donor identity and relevant-diff files. No donor code was executed. Merge36636c4 uses its first-parent delta. The duplicate file-specific donor deltas are retained to distinguish their provenance from the merge's extra context/workflow mechanisms.

Commands used (all source reads exited0 unless noted below):

```sh
git rev-parse HEAD
git rev-parse a10e485962571a566f99225541735ab1ada1f4c0
git ls-tree -r --name-only a10e485962571a566f99225541735ab1ada1f4c0
git log --format='%h %H %s' -12 a10e485962571a566f99225541735ab1ada1f4c0
git show a10e485962571a566f99225541735ab1ada1f4c0:<path>
git show a10e485962571a566f99225541735ab1ada1f4c0:<path> | nl -ba
git rev-parse a10e485962571a566f99225541735ab1ada1f4c0:<path>
git show a10e485962571a566f99225541735ab1ada1f4c0:<path> | sha256sum
git show -s --format='%H%n%P%n%s' <donor>
git diff <donor>^ <donor> -- Dockerfile Dockerfile.cuda Dockerfile.intel .dockerignore .github/workflows/docker-image.yml
git diff e21ebdf6e3ee46e6c65050dc956a9a3459152269 a10e485962571a566f99225541735ab1ada1f4c0 -- Dockerfile Dockerfile.cuda Dockerfile.intel requirements.txt pyproject.toml
```

`<path>` is enumerated in the manifest. Engine excerpts use `sed -n '3454,3487p;5810,5835p'`; install excerpts `128,166p;185,228p;413,435p`; setup excerpts `165,245p`. Source/data reading tools were Git, shell text readers and hashing; no product interpreter or workload was started. Report/evidence writes used shell redirection and apply_patch. Scratch is `/tmp/openscrub-docker-cache-contract`.

Requirement provenance: named local planning/SDD files are not in product HEAD and were explicitly approved for direct read by the supervisor. `local-requirements-sha256.txt` identifies the consulted snapshot. No mutable native product source was used. Existing plan links to [Docker cache mounts](https://docs.docker.com/reference/dockerfile/#run---mounttypecache) and [GitHub Actions cache behavior](https://docs.docker.com/build/ci/github-actions/cache/) supply prior documentation context; no new external documentation research or GitHits call was necessary.

Benign discovery failures: attempts to `git show HEAD` the untracked planning/SDD paths exited128; then direct requirement reads were authorized. `.superpowers/sdd/README` is a directory, so an initial `cat` exited1. An abbreviated `e21` revision was ambiguous and exited128; subsequent comparisons use exact e21ebdf SHA. An initial setup excerpt selected nonexistent later lines, returned empty exit0, and was corrected to165–245. No success claim uses those failed/empty reads. These caused no product/Git mutation.
